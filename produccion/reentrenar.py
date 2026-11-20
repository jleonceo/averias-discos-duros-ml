"""Reentreno del modelo de riesgo del caso 68 con la receta fija del contrato (método preproduccion §2.2).

No busca algoritmo ni hiperparámetros: rehace el HistGradientBoosting aprobado con la tabla que se le pasa.
  1. Lee la tabla de entrenamiento del argumento --tabla, sin valor por defecto. Con la tabla de la partición solo
     se ejecuta en modo de comprobación (--comprobacion).
  2. Quita y cuenta: los discos de arranque (P11), las fotos posteriores a la fecha del entrenamiento y las que aún
     no conocían su objetivo en esa fecha, con sus fallos (P18), y las sanas que no entran en la muestra (P19).
  3. Guarda el Pipeline sin entrenar antes del fit; lo ajusta y lo guarda con joblib y su ficha en
     modelos/reentrenos/AAAA-MM-DD/, aparte del modelo en uso.
  4. Compara: con modelo en uso y su misma tabla, igual bit a bit; con otra tabla, tiene que cambiar (validación 8);
     sin modelo en uso y en modo de comprobación, puntúa la validación mes a mes y tiene que dar lo que guardó el
     modelado (los fallos en las listas de 20 y de 100 y el AUC). Con --medir, mide el reentrenado y el modelo en uso
     en las mismas filas.
No sustituye el modelo en uso: lo aprueba el responsable del caso.

Uso: python -W error produccion/reentrenar.py --tabla RUTA (--fecha AAAA-MM-DD | --comprobacion) [--medir RUTA]
     [--validacion RUTA] [--raiz CARPETA_DEL_CASO] [--hoy AAAA-MM-DD]
"""

# =================================================================================================================
# 1. Configuración
# =================================================================================================================
import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
sys.path.insert(0, str(CASO / "assets"))
import pipeline_riesgo as pr  # noqa: E402  (módulo de producción del caso)
import evaluacion_binaria as eb  # noqa: E402  (pieza común: el AUC, como lo midió el modelado)

CONFIGURACION = "produccion/configuracion.json"
MODELADO = "informes/modelado.json"
NOMBRE = "modelo_riesgo"
OBJETIVO, FECHA, HORIZONTE = "falla_30d", "fecha", "horizonte_hasta"
LISTAS_DEL_MODELADO = (20, 100)


# =================================================================================================================
# 2. Utilidades
# =================================================================================================================
def a_json(v):
    """Pasa a tipos que JSON acepta, sin NaN."""
    if isinstance(v, dict):
        return {str(k): a_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [a_json(x) for x in v]
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) or np.isinf(v) else float(v)
    return v


def ruta_de(raiz, texto):
    """Una ruta de la configuración: absoluta, o relativa a la carpeta del caso."""
    p = Path(texto)
    return p if p.is_absolute() else raiz / p


def fallos_en_lista(claves, y, n):
    """Fallos entre los N primeros, de mayor a menor; un empate en el puesto N se reparte en proporción (como el modelado)."""
    claves = [np.asarray(k, dtype=float) for k in claves]
    y = np.asarray(y, dtype=float)
    orden = np.lexsort([-k for k in claves[::-1]])
    ks = [k[orden] for k in claves]
    ys = y[orden]
    cambio = np.ones(len(ys), dtype=bool)
    if len(ys) > 1:
        cambio[1:] = np.any([k[1:] != k[:-1] for k in ks], axis=0)
    inicio = np.flatnonzero(cambio)
    tam = np.diff(np.append(inicio, len(ys)))
    fal = np.add.reduceat(ys, inicio) if len(ys) else np.array([])
    quedan, total = n, 0.0
    for t, f in zip(tam, fal):
        toma = min(quedan, t)
        total += f * toma / t
        quedan -= toma
        if quedan <= 0:
            break
    return float(total)


# =================================================================================================================
# 3. Las filas que entrenan: lo que quita filas, contado (P11, P18 y P19)
# =================================================================================================================
class Tabla:
    """Una tabla con la forma de fotos_riesgo, leída grupo a grupo: sus meses y las filas de cada uno."""

    def __init__(self, ruta, columnas):
        self.pf = pq.ParquetFile(ruta)
        self.columnas = columnas
        self.grupos = {}
        for i in range(self.pf.num_row_groups):
            for f in np.unique(self.pf.read_row_group(i, columns=[FECHA])[FECHA].to_numpy()):
                self.grupos.setdefault(pd.Timestamp(f), []).append(i)
        self.meses = sorted(self.grupos)

    def mes(self, m):
        """Las fotos de un mes, en el orden del fichero."""
        partes = []
        for i in self.grupos[m]:
            t = self.pf.read_row_group(i, columns=self.columnas)
            partes.append(t.filter(pd.Series(t[FECHA].to_numpy() == np.datetime64(m, "ms")).to_numpy()).to_pandas())
        return pd.concat(partes, ignore_index=True)


def muestra(ruta, fecha, columnas, semilla, fraccion):
    """Las filas que entrenan, como el modelado (scripts/15_modelado.py, Datos.muestra): fotos anteriores a la fecha del
    entrenamiento cuyo horizonte acabó antes; de ellas, todos los fallos y la fracción de las sanas de cada mes,
    sorteadas con la semilla en el orden de los meses. Quita antes los discos de arranque. Lo cuenta todo."""
    tabla = Tabla(ruta, columnas)
    corte = np.datetime64(pd.Timestamp(fecha), "ms")
    rng = np.random.default_rng(semilla)
    c = {"posteriores": 0, "posteriores_fallos": 0, "arranque": 0, "arranque_fallos": 0, "sin_conocer": 0,
         "sin_conocer_fallos": 0, "filas_entrena": 0, "fallos_entrena": 0, "sanas_fuera": 0}
    trozos = []
    for m in tabla.meses:
        for i in tabla.grupos[m]:
            t = tabla.pf.read_row_group(i, columns=columnas)
            fe, ho = t[FECHA].to_numpy(), t[HORIZONTE].to_numpy()
            y = t[OBJETIVO].to_numpy().astype(np.int64)
            del_mes = fe == np.datetime64(m, "ms")
            if m >= pd.Timestamp(fecha):
                c["posteriores"] += int(del_mes.sum())
                c["posteriores_fallos"] += int(y[del_mes].sum())
                continue
            arranque = del_mes & (t["capacidad_tb"].to_numpy() * 1e12 <= pr.LIMITE_ARRANQUE_BYTES)
            antes = del_mes & ~arranque
            ok = antes & (ho < corte)
            c["arranque"] += int(arranque.sum())
            c["arranque_fallos"] += int(y[arranque].sum())
            c["sin_conocer"] += int((antes & ~ok).sum())
            c["sin_conocer_fallos"] += int(y[antes & ~ok].sum())
            c["filas_entrena"] += int(ok.sum())
            c["fallos_entrena"] += int(y[ok].sum())
            sanas = np.flatnonzero(ok & (y == 0))
            k = int(np.floor(fraccion * len(sanas) + 0.5))
            elegidas = rng.choice(sanas, size=k, replace=False) if k else np.array([], dtype=np.int64)
            c["sanas_fuera"] += len(sanas) - k
            filas = np.sort(np.concatenate([np.flatnonzero(ok & (y == 1)), elegidas]))
            if len(filas):
                trozos.append(t.take(filas).to_pandas())
    if not trozos:
        raise pr.ErrorDeProduccion("ninguna foto entrena con esa fecha: no hay nada anterior con el objetivo conocido")
    df = pd.concat(trozos, ignore_index=True)
    return df, df[OBJETIVO].to_numpy().astype(np.int64), c


# =================================================================================================================
# 4. Medir un modelo mes a mes (como la validación del modelado)
# =================================================================================================================
def medir(modelos, ruta, contrato):
    """Puntúa cada mes de la tabla con cada modelo; devuelve, por modelo, los fallos en las listas y el AUC."""
    tabla = Tabla(ruta, contrato["lee"] + [OBJETIVO, FECHA])
    salida = [{"por_mes": [], "ys": [], "ps": []} for _ in modelos]
    for m in tabla.meses:
        dm = tabla.mes(m)
        ym = dm[OBJETIVO].to_numpy().astype(int)
        for j, mdl in enumerate(modelos):
            p = mdl.predict_proba(dm[contrato["lee"]])[:, 1]
            fila = {"mes": m.date().isoformat(), "filas": int(len(ym)), "fallos": int(ym.sum())}
            for n in contrato["corte"]["valores"]:
                fila[f"lista_{n}"] = fallos_en_lista([p], ym, n)
            salida[j]["por_mes"].append(fila)
            salida[j]["ys"].append(ym)
            salida[j]["ps"].append(p)
    for s in salida:
        y_all, p_all = np.concatenate(s.pop("ys")), np.concatenate(s.pop("ps"))
        s["auc"] = float(eb.medidas_globales(y_all, p_all)["auc"])
        s["filas"] = int(len(y_all))
        s["lista_100_media"] = float(np.mean([f["lista_100"] for f in s["por_mes"]])) if 100 in contrato["corte"]["valores"] else None
    return salida


def frente_al_modelado(medido, raiz):
    """Si el primer reentreno da lo que guardó el modelado: los fallos de cada mes en las listas de 20 y de 100 y el AUC."""
    mo = json.loads((raiz / MODELADO).read_text(encoding="utf-8"))["validacion"]
    guardado = {r["mes"]: r for r in mo["por_mes"]}
    distintos = []
    if sorted(guardado) != [r["mes"] for r in medido["por_mes"]]:
        distintos.append(f"meses: guardados {sorted(guardado)}, medidos {[r['mes'] for r in medido['por_mes']]}")
    for r in medido["por_mes"]:
        g = guardado.get(r["mes"], {})
        for n in LISTAS_DEL_MODELADO:
            if g.get(f"modelo_lista_{n}") != r[f"lista_{n}"]:
                distintos.append(f"{r['mes']} lista de {n}: guardado {g.get(f'modelo_lista_{n}')}, medido {r[f'lista_{n}']}")
    if mo["medidas"]["auc"] != medido["auc"]:
        distintos.append(f"AUC: guardado {mo['medidas']['auc']}, medido {medido['auc']}")
    return {"iguales": not distintos, "distintos": distintos, "medido": medido}


# =================================================================================================================
# 5. Principal
# =================================================================================================================
def archivar(carpeta):
    """Si ese día ya había un reentreno, lo pasa a _archivo/ antes de escribir el nuevo."""
    viejos = [p for p in carpeta.iterdir() if p.name != "_archivo"] if carpeta.exists() else []
    if viejos:
        destino = carpeta / "_archivo" / dt.datetime.now().strftime("%H%M%S%f")
        destino.mkdir(parents=True)
        for p in viejos:
            shutil.move(str(p), str(destino / p.name))
    carpeta.mkdir(parents=True, exist_ok=True)


def principal(args):
    """El reentreno entero; devuelve el resumen que se escribe en reentreno.json."""
    raiz = args.raiz.resolve()
    c = pr.leer_contrato(raiz)
    conf = json.loads((raiz / CONFIGURACION).read_text(encoding="utf-8"))
    tabla = Path(args.tabla).resolve()
    particion = ruta_de(raiz, conf["tabla_de_la_particion"]).resolve()
    # 5.1 La tabla de la partición solo en modo de comprobación; la fecha, del argumento o, en comprobación, del contrato
    if tabla == particion and not args.comprobacion:
        raise pr.ErrorDeProduccion("la tabla de la partición solo se usa en modo de comprobación (--comprobacion): "
                                   "una ejecución programada tiene que pasar su propia tabla")
    fecha = args.fecha or (c["receta"]["objetivo_conocido"]["fecha_en_el_modelado"] if args.comprobacion else None)
    if fecha is None:
        raise pr.ErrorDeProduccion("falta --fecha, la fecha que fija el entrenamiento")
    rc = c["receta"]
    # 5.2 Lo que quita filas, contado
    df, y, cu = muestra(tabla, fecha, c["lee"] + [OBJETIVO, FECHA, HORIZONTE], rc["semilla"], rc["muestra"]["fraccion_sanas"])
    tasa_real = cu["fallos_entrena"] / cu["filas_entrena"]
    carpeta = ruta_de(raiz, conf["carpeta_reentrenos"]) / args.hoy
    archivar(carpeta)
    # 5.3 El Pipeline sin entrenar se guarda antes del fit; después, el entrenado con su ficha
    pipe = pr.construir_pipeline(c, tasa_real=tasa_real)
    pr.guardar_modelo(pipe, carpeta / f"{NOMBRE}_sin_entrenar.joblib", estado="sin entrenar: la receta")
    pipe.fit(df[c["lee"]], y)
    salen = pr.comprobar_columnas_de_salida(pipe, c["esperadas"])
    vacias = pipe.named_steps["sin_vacias"].columnas_vacias_
    columnas_ok = salen == [x for x in c["esperadas"] if x not in vacias]
    dentro = pr.filas_dentro(pipe, len(df))
    ficha = pr.guardar_modelo(
        pipe, carpeta / f"{NOMBRE}.joblib", semilla=rc["semilla"], fecha_entrenamiento=str(fecha),
        tabla=str(tabla), huella_tabla=pr.huella(tabla), filas={"tabla": pq.ParquetFile(tabla).metadata.num_rows,
                                                                 "entrenan": cu["filas_entrena"], "muestra": int(len(df))},
        tasa_muestra=float(np.mean(y)), tasa_real=tasa_real, columnas_entrada=c["lee"], columnas_salida=salen,
        columnas_vacias_del_ajuste=vacias, estructura=a_json(pr.estructura(pipe)), lleva_filas_de_entrenamiento=dentro,
        contrato=c["aprobado_por"])
    res = {"tabla": str(tabla), "fecha_entrenamiento": str(fecha), "filas_entrada": ficha["filas"]["tabla"],
           "filas_quitadas": [
               {"motivo": "disco de arranque", "filas": cu["arranque"], "casos_del_evento": cu["arranque_fallos"]},
               {"motivo": "fotos posteriores a la fecha del entrenamiento", "filas": cu["posteriores"], "casos_del_evento": cu["posteriores_fallos"]},
               {"motivo": "objetivo sin conocer", "fecha": str(fecha), "filas": cu["sin_conocer"], "casos_del_evento": cu["sin_conocer_fallos"]},
               {"motivo": "sanas que no entran en la muestra", "filas": cu["sanas_fuera"], "casos_del_evento": 0}],
           "filas_entrena": cu["filas_entrena"], "fallos_entrena": cu["fallos_entrena"], "tasa_real": tasa_real,
           "muestra": {"filas": int(len(df)), "fallos": int(y.sum()), "sanas": int(len(df) - y.sum())},
           "hoja": pipe.named_steps["modelo"].modelo_.min_samples_leaf, "columnas_del_contrato": columnas_ok,
           "ruta": str(carpeta.relative_to(raiz)) if carpeta.is_relative_to(raiz) else str(carpeta),
           "lleva_filas_de_entrenamiento": dentro, "igual_bit_a_bit": None, "cambia_con_datos_nuevos": None,
           "comparacion_con_el_modelado": None, "comparacion_con_el_en_uso": None}
    # 5.4 Frente al modelo en uso o, si no lo hay, frente a lo que guardó el modelado
    en_uso = conf.get("modelo_en_uso")
    res["modelo_en_uso"] = {"existia": bool(en_uso), "de_donde": en_uso or "no hay: el modelo en uso sale de este reentreno cuando el responsable del caso lo apruebe"}
    errores = []
    if en_uso:
        viejo, ficha_vieja = pr.cargar_modelo(ruta_de(raiz, en_uso))
        X = df[c["lee"]]
        iguales = bool(np.array_equal(pipe.predict_proba(X)[:, 1], viejo.predict_proba(X)[:, 1]))
        if ficha_vieja.get("huella_tabla") == ficha["huella_tabla"] and ficha_vieja.get("fecha_entrenamiento") == str(fecha):
            res["igual_bit_a_bit"] = iguales
            if not iguales:
                errores.append("con la misma tabla y la misma fecha que el modelo en uso, el reentreno no sale igual bit a bit")
        else:
            res["cambia_con_datos_nuevos"] = not iguales
            if iguales:
                errores.append("con una tabla distinta de la del modelo en uso el reentreno sale igual: no ha leído los datos nuevos")
        if args.medir:
            nuevo_m, viejo_m = medir([pipe, viejo], Path(args.medir), c)
            res["comparacion_con_el_en_uso"] = {"periodo": f"{nuevo_m['por_mes'][0]['mes']} a {nuevo_m['por_mes'][-1]['mes']}",
                                                "filas": nuevo_m["filas"], "medida": "media de los fallos en la lista de 100 de cada mes; AUC",
                                                "en_uso": {"lista_100": viejo_m["lista_100_media"], "auc": viejo_m["auc"]},
                                                "reentrenado": {"lista_100": nuevo_m["lista_100_media"], "auc": nuevo_m["auc"]}}
    elif args.comprobacion:
        validacion = Path(args.validacion).resolve() if args.validacion else ruta_de(raiz, conf["validacion"])
        comp = frente_al_modelado(medir([pipe], validacion, c)[0], raiz)
        res["comparacion_con_el_modelado"] = comp
        res["igual_bit_a_bit"] = comp["iguales"]
        if not comp["iguales"]:
            errores.append("el primer reentreno no da lo que guardó el modelado: " + "; ".join(comp["distintos"][:6]))
    if not columnas_ok:
        errores.append("las columnas que llegan al modelo no son las del contrato")
    res["estado"] = "ERROR" if errores else "OK"
    res["resumen"] = "; ".join(errores) if errores else (
        f"Reentreno hecho con {cu['filas_entrena']} fotos que entrenan y una muestra de {len(df)}; guardado en {res['ruta']}, "
        "aparte del modelo en uso, que aprueba el responsable del caso.")
    return res, carpeta


def main():
    """Punto de entrada: escribe reentreno.json en la carpeta del reentreno y el reentreno en informes/preproduccion.json."""
    ap = argparse.ArgumentParser(description="Reentreno con la receta fija del contrato")
    ap.add_argument("--tabla", required=True, help="tabla de entrenamiento con la forma de fotos_riesgo (sin valor por defecto)")
    ap.add_argument("--fecha", help="la fecha que fija el entrenamiento (AAAA-MM-DD); en comprobación, la del modelado")
    ap.add_argument("--comprobacion", action="store_true", help="modo de comprobación: permite la tabla de la partición")
    ap.add_argument("--validacion", help="tabla de validación para comparar con el modelado (por defecto, la de la configuración)")
    ap.add_argument("--medir", help="tabla de un periodo con desenlace conocido para medir frente al modelo en uso")
    ap.add_argument("--raiz", type=Path, default=CASO)
    ap.add_argument("--hoy", default=dt.date.today().isoformat())
    args = ap.parse_args()
    print(f"sys.executable: {sys.executable}")
    try:
        res, carpeta = principal(args)
    except pr.ErrorDeProduccion as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    (carpeta / "reentreno.json").write_text(json.dumps(a_json(res), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    validaciones = {"columnas_del_contrato": res["columnas_del_contrato"]}
    if res["igual_bit_a_bit"] is not None:
        validaciones["bit_a_bit"] = res["igual_bit_a_bit"]
    if res["cambia_con_datos_nuevos"] is not None:
        validaciones["cambia_con_datos_nuevos"] = res["cambia_con_datos_nuevos"]
    reentreno = {k: res[k] for k in ("tabla", "filas_entrada", "filas_quitadas", "modelo_en_uso", "igual_bit_a_bit", "ruta",
                                     "comparacion_con_el_en_uso")}
    pr.actualizar_json(args.raiz.resolve(), {"reentreno": a_json(reentreno)}, validaciones)
    print(f"{res['estado']}: {res['resumen']}")
    sys.exit(0 if res["estado"] == "OK" else 1)


if __name__ == "__main__":
    main()
