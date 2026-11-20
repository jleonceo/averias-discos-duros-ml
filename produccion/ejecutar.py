"""Puntuación de una foto mensual con el modelo de riesgo del caso 68 (skill preproduccion §2.3).

  1. Carga el modelo en uso (o el de --modelo) solo si su ficha cuadra: versiones, huella del fichero y del módulo, y
     las columnas de entrada iguales a las del contrato.
  2. Lee la foto en bruto y comprueba las columnas por nombre, que ningún número llega como texto y que la foto es la
     del mes que se pide.
  3. Aplica las correcciones y la transformación del módulo con la historia hasta el día de la foto, y el Pipeline. La
     historia puede estar en varias carpetas (las de la configuración, en su orden, o las de los argumentos); dos
     ficheros con el mismo nombre en carpetas distintas son ficheros distintos y se leen los dos.
  4. Saca una fila por cada fila de entrada, en el mismo orden: serial_number, la probabilidad, una marca por lista
     (los N de más riesgo de la foto, con el desempate por serial_number) y el motivo de lo que no se puntúa. No quita
     ninguna fila.
  5. Guarda en data/predicciones/AAAA-MM-DD/ la salida y su resumen; si ese día ya estaban la salida y el resumen de
     ese mismo mes, pasan antes a _archivo/. Los de otros meses del mismo día se quedan a la vista.

Uso: python -W error produccion/ejecutar.py --foto RUTA --mes AAAA-MM [--modelo RUTA] [--fotos-anteriores CARPETA ...]
     [--ventanas CARPETA ...] [--raiz CARPETA_DEL_CASO] [--hoy AAAA-MM-DD]
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

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
import pipeline_riesgo as pr  # noqa: E402  (módulo de producción del caso)

CONFIGURACION = "produccion/configuracion.json"


def ruta_de(raiz, texto):
    """Una ruta de la configuración: absoluta, o relativa a la carpeta del caso."""
    p = Path(texto)
    return p if p.is_absolute() else raiz / p


# =================================================================================================================
# 2. Las comprobaciones de entrada
# =================================================================================================================
def cargar(raiz, conf, contrato, modelo):
    """El modelo, solo si su ficha cuadra y lee las columnas del contrato (validaciones 2 y 7)."""
    texto = modelo or conf.get("modelo_en_uso")
    if not texto:
        raise pr.ErrorDeProduccion("no hay modelo en uso en produccion/configuracion.json ni se ha pasado --modelo: "
                                   "el modelo en uso lo aprueba Juan")
    pipe, ficha = pr.cargar_modelo(ruta_de(raiz, texto))
    if ficha.get("columnas_entrada") != contrato["lee"]:
        raise pr.ErrorDeProduccion("las columnas de entrada del modelo no son las del contrato: el modelo se entrenó con otro contrato")
    return pipe, ficha, ruta_de(raiz, texto)


def ficha_cuadra(ruta_modelo, ficha, lee):
    """Validación 7, rehecha con lo que se cargó: versiones de scikit-learn y pandas, huella del fichero y del módulo
    iguales a las de la ficha, y columnas de entrada iguales a las del contrato. cargar() ya para si algo no cuadra;
    esto deja en el lote el resultado calculado, no escrito a mano."""
    actuales = pr.versiones()
    return bool(all(ficha["versiones"][k] == actuales[k] for k in ("scikit-learn", "pandas"))
                and pr.huella(ruta_modelo) == ficha["huella"]
                and pr.huella(Path(pr.__file__)) == ficha["huella_modulo"]
                and ficha.get("columnas_entrada") == lee)


def carpetas_de(raiz, valor):
    """Las carpetas de la historia: una lista (o una sola, como texto) de la configuración o de los argumentos. Para si
    una no existe: una carpeta mal escrita dejaría la historia corta sin avisar."""
    lista = [valor] if isinstance(valor, (str, Path)) else list(valor)
    carpetas = [ruta_de(raiz, c) for c in lista]
    faltan = [str(c) for c in carpetas if not c.is_dir()]
    if faltan:
        raise pr.ErrorDeProduccion(f"no existe la carpeta de historia {faltan}")
    return carpetas


def pares_unicos(df):
    """Los pares (modelo, capacidad) distintos de la historia, vacíos incluidos. Solo resumen la historia: la foto que se
    puntúa no pasa por aquí."""
    return df.groupby(["model", "capacity_bytes"], dropna=False, sort=False).size().reset_index()[["model", "capacity_bytes"]]


def leer_historia(carpetas_fotos, carpetas_ventanas, fecha, mapeo, discos):
    """La historia hasta el día de la foto leída de varias carpetas, en su orden y cada una con sus ficheros por nombre.

    Es la lectura de pr.leer_historia, que lee una sola carpeta, sobre la lista de ficheros de todas; el módulo no se
    cambia, porque su huella va en la ficha del modelo en uso. Lo que la historia aporta lo calcula pr.historia_de.
    """
    fecha = pd.Timestamp(fecha)
    columnas_f = ["serial_number", "fecha", "model", "capacity_bytes", *pr.CONTADORES_SIN_188]
    columnas_v = ["serial_number", "fecha", "date", "dia_fallo", "model", "capacity_bytes"]
    pares, filas = [], []
    for ruta in [r for c in carpetas_fotos for r in sorted(Path(c).glob("*.parquet"))]:
        df = pr._leer_columnas(ruta, columnas_f)
        df = df.loc[(df["fecha"] < fecha).to_numpy()]
        if df.empty:
            continue
        pares.append(pares_unicos(df))
        filas.append(df.loc[df["serial_number"].isin(discos).to_numpy()])
    fotos = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame(columns=columnas_f)
    p = pd.concat(pares, ignore_index=True) if pares else pd.DataFrame(columns=["model", "capacity_bytes"])
    p["model"] = p["model"].replace(mapeo)
    ventanas = []
    for ruta in [r for c in carpetas_ventanas for r in sorted(Path(c).glob("*.parquet"))]:
        df = pr._leer_columnas(ruta, columnas_v)
        ventanas.append(df.loc[(df["dia_fallo"] < fecha).to_numpy()])
    v = pd.concat(ventanas, ignore_index=True) if ventanas else pd.DataFrame(columns=columnas_v)
    return pr.historia_de(fotos, v, fecha, mapeo, pares_fotos=pares_unicos(p) if len(p) else p)


def comprobar_mes(foto, mes):
    """La foto es la del mes que se pide: todas sus filas son del día 1 de ese mes (validación 9)."""
    fecha = pd.Timestamp(f"{mes}-01")
    fechas = sorted({pd.Timestamp(f).strftime("%Y-%m-%d") for f in foto["fecha"].unique()})
    if fechas != [fecha.strftime("%Y-%m-%d")]:
        raise pr.ErrorDeProduccion(f"la foto no es la del mes que se pide ({mes}): trae las fechas {fechas}")
    return fecha


# =================================================================================================================
# 3. La puntuación y las listas
# =================================================================================================================
def marcas(serial, probabilidad, listas):
    """Una marca por lista: 1 en los N de más riesgo de la foto (empate por serial_number), 0 en el resto y vacío en
    lo que no se puntúa."""
    puntuadas = np.flatnonzero(~np.isnan(probabilidad))
    orden = puntuadas[np.lexsort((serial[puntuadas], -probabilidad[puntuadas]))]
    puesto = np.full(len(serial), -1)
    puesto[orden] = np.arange(len(orden))
    salida = {}
    for n in listas:
        m = pd.array(np.where(puesto < n, 1, 0), dtype="Int8")
        m[puesto < 0] = pd.NA
        salida[f"en_lista_{n}"] = m
    return salida


def puntuar(pipe, contrato, foto, historia, mapeo, minimo, listas):
    """La salida: una fila por fila de la foto, en su orden, con la probabilidad, las marcas y el motivo."""
    df, motivo = pr.preparar_foto(foto, historia, mapeo, minimo)
    se_puntua = motivo == ""
    probabilidad = np.full(len(df), np.nan)
    if se_puntua.any():
        probabilidad[se_puntua] = pipe.predict_proba(df.loc[se_puntua, contrato["lee"]])[:, 1]
    serial = df["serial_number"].astype(str).to_numpy()
    salida = pd.DataFrame({"serial_number": serial, "probabilidad": probabilidad,
                           **marcas(serial, probabilidad, listas),
                           "motivo": pd.Series(motivo, dtype=object).where(~se_puntua, None)})
    assert len(salida) == len(foto), "la salida no tiene una fila por cada fila de la foto"
    assert (salida["serial_number"].to_numpy() == foto["serial_number"].astype(str).to_numpy()).all(), "la salida cambió el orden"
    return salida


def sin_quitar_filas(foto, salida):
    """Validación 6: salen los mismos discos que entran, en su orden, y cada fila está puntuada o lleva su motivo, nunca
    las dos cosas ni ninguna. Va más allá de contar filas: una fila cambiada por otra o sin motivo también falla."""
    misma = len(salida) == len(foto) and bool(
        (salida["serial_number"].to_numpy() == foto["serial_number"].astype(str).to_numpy()).all())
    return bool(misma and (salida["probabilidad"].notna() ^ salida["motivo"].notna()).all())


# =================================================================================================================
# 4. Guardar
# =================================================================================================================
def archivar(carpeta, mes):
    """Si ese día ya estaban la salida y el resumen de ese mes, los pasa a _archivo/ antes de escribir los nuevos; los
    de otros meses del mismo día se quedan donde están."""
    nombres = {f"predicciones_{mes}.parquet", f"resumen_{mes}.json"}
    viejos = [p for p in carpeta.iterdir() if p.name in nombres] if carpeta.exists() else []
    if viejos:
        destino = carpeta / "_archivo" / dt.datetime.now().strftime("%H%M%S%f")
        destino.mkdir(parents=True)
        for p in viejos:
            shutil.move(str(p), str(destino / p.name))
    carpeta.mkdir(parents=True, exist_ok=True)


def principal(args):
    """La ejecución entera; devuelve el resumen y la ruta de la salida."""
    raiz = args.raiz.resolve()
    conf = json.loads((raiz / CONFIGURACION).read_text(encoding="utf-8"))
    contrato = pr.leer_contrato(raiz)
    pipe, ficha, ruta_modelo = cargar(raiz, conf, contrato, args.modelo)
    foto = pr.leer_foto(args.foto, contrato["entrada"])
    fecha = comprobar_mes(foto, args.mes)
    dec = json.loads(ruta_de(raiz, conf["decisiones_correccion"]).read_text(encoding="utf-8"))
    mapeo, minimo = dec["modelos"]["mapeo"], dec["capacidad"]["minimo_valido_bytes"]
    dir_fotos = carpetas_de(raiz, args.fotos_anteriores or conf["historia_fotos"])
    dir_ventanas = carpetas_de(raiz, args.ventanas or conf["historia_ventanas"])
    historia = leer_historia(dir_fotos, dir_ventanas, fecha, mapeo, set(foto["serial_number"]))
    salida = puntuar(pipe, contrato, foto, historia, mapeo, minimo, conf["listas"])
    carpeta = ruta_de(raiz, conf["carpeta_predicciones"]) / args.hoy
    archivar(carpeta, args.mes)
    ruta = carpeta / f"predicciones_{args.mes}.parquet"
    salida.to_parquet(ruta, index=False)
    sin = salida["motivo"].value_counts()
    resumen = {"mes": args.mes, "foto": str(Path(args.foto).resolve()), "huella_foto": pr.huella(args.foto),
               "modelo": str(ruta_modelo), "huella_modelo": ficha["huella"], "fecha_entrenamiento": ficha.get("fecha_entrenamiento"),
               "contrato": contrato["aprobado_por"], "filas_entrada": int(len(foto)), "filas_salida": int(len(salida)),
               "puntuadas": int(salida["probabilidad"].notna().sum()),
               "sin_puntuar": [{"motivo": str(k), "filas": int(v)} for k, v in sin.items()],
               "listas": list(conf["listas"]), "lista_principal": conf["lista_principal"],
               "salida": str(ruta.relative_to(raiz)) if ruta.is_relative_to(raiz) else str(ruta),
               "historial": {"ruta": {"fotos": [str(c) for c in dir_fotos], "ventanas": [str(c) for c in dir_ventanas]}, "filas": None,
                             "discos_con_foto_anterior": int(len(historia["anterior"])),
                             "discos_con_ventana_ya_ocurrida": int(len(historia["primer_dia_ventana"]))},
               "ficha_cuadra": ficha_cuadra(ruta_modelo, ficha, contrato["lee"]),
               "sin_quitar_filas": sin_quitar_filas(foto, salida),
               "ejecutado": dt.datetime.now().isoformat(timespec="seconds")}
    (carpeta / f"resumen_{args.mes}.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    return resumen


def main():
    """Punto de entrada: puntúa la foto y escribe el lote en informes/preproduccion.json."""
    ap = argparse.ArgumentParser(description="Puntúa una foto mensual con el modelo de riesgo")
    ap.add_argument("--foto", required=True, help="la foto mensual en bruto (Parquet)")
    ap.add_argument("--mes", required=True, help="el mes que se pide, AAAA-MM; la foto tiene que ser la de ese mes")
    ap.add_argument("--modelo", help="el modelo (por defecto, el modelo en uso de la configuración)")
    ap.add_argument("--fotos-anteriores", nargs="+",
                    help="carpetas de las fotos mensuales de la historia, en su orden (por defecto, las de la configuración)")
    ap.add_argument("--ventanas", nargs="+", help="carpetas de las ventanas de fallo, en su orden (por defecto, las de la configuración)")
    ap.add_argument("--raiz", type=Path, default=CASO)
    ap.add_argument("--hoy", default=dt.date.today().isoformat())
    args = ap.parse_args()
    print(f"sys.executable: {sys.executable}")
    try:
        res = principal(args)
    except pr.ErrorDeProduccion as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    lote = {"ruta": res["foto"], "mes": res["mes"], "filas_entrada": res["filas_entrada"], "filas_salida": res["filas_salida"],
            "puntuadas": res["puntuadas"], "sin_puntuar": res["sin_puntuar"], "salida": res["salida"], "modelo": res["modelo"],
            "historial": res["historial"]}
    pr.actualizar_json(args.raiz.resolve(), {"lote": lote},
                       {"filas_ejecucion": res["filas_entrada"] == res["filas_salida"], "ficha_cuadra": res["ficha_cuadra"],
                        "sin_quitar_filas_al_ejecutar": res["sin_quitar_filas"]})
    print(f"OK: {res['filas_salida']} filas de {res['filas_entrada']}, {res['puntuadas']} puntuadas; guardado en {res['salida']}")


if __name__ == "__main__":
    main()
