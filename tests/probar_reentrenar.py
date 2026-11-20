"""Prueba de produccion/reentrenar.py (método preproduccion §2.2 y validaciones 2, 4, 7 y 8).

Monta en tests/tmp_produccion/ un caso pequeño: una tabla de entrenamiento con la forma de fotos_riesgo (las 64
columnas que lee el modelo, el identificador, el objetivo y su horizonte; un grupo de filas por mes, de octubre de 2023
a junio de 2024), una de validación de dos meses, el contrato (copia de informes/preproduccion.json con la aprobación
escrita en la copia), un modelado.json de juguete y produccion/configuracion.json. Casos:
  1. la tabla de la partición sin --comprobacion: ERROR, sin modelo;
  2. sin --tabla: el script no arranca;
  3. modo de comprobación, sin modelo en uso, con un modelado.json que no es el suyo: ERROR, porque no da lo que guardó
     el modelado (lo que sí dio queda en el JSON);
  4. con el modelado.json que dan esas cifras: OK e igual a lo guardado; se comprueba que las filas, las quitadas, la
     muestra (todos los fallos y el 2 % de las sanas de cada mes) y la tasa real salen como se cuentan aquí con pandas;
     que el Pipeline sin entrenar se guardó antes del fit; que la ficha trae versiones, semilla, huella de la tabla,
     columnas, registro del caso y que el modelo no guarda filas de entrenamiento;
  5. una fecha del entrenamiento que deja el horizonte de junio abierto: quita esas fotos y las cuenta con sus fallos;
  6. un disco de arranque colado en la tabla: se quita y se cuenta;
  7. con modelo en uso y la misma tabla: igual bit a bit;
  8. con modelo en uso y otra tabla (otros datos): el modelo cambia (validación 8, verde) y se mide frente al modelo en
     uso en un periodo que ninguno vio;
  9. con modelo en uso y una tabla que solo añade fotos posteriores a la fecha del entrenamiento: sale igual, y eso es
     rojo de la validación 8 (no ha leído datos nuevos);
 10. con la ficha del modelo en uso estropeada: para al cargarlo (validación 7).
Sale con 0 si todo pasa y con 1 si algo falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "produccion" / "reentrenar.py"
TMP = CASO / "tests" / "tmp_produccion"
ENT = "data/processed/fotos_riesgo_entrenamiento.parquet"
VAL = "data/processed/fotos_riesgo_validacion.parquet"
HOY = "2026-11-19"
APROBADO = "El responsable del caso, 19/11/2026: «Sí, con el arreglo» (copia de prueba)"
FALLOS = []
MESES_ENT = pd.date_range("2023-10-01", "2024-06-01", freq="MS")
MESES_VAL = pd.date_range("2024-07-01", "2024-08-01", freq="MS")


def comprobar(condicion, caso):
    """Apunta el caso si no se cumple y lo imprime."""
    print(("ok    " if condicion else "FALLA ") + caso)
    if not condicion:
        FALLOS.append(caso)


# ---------------------------------------------------------------------------------------------------------------
# 2. El caso pequeño (también lo usa tests/probar_ejecutar.py)
# ---------------------------------------------------------------------------------------------------------------
def contrato():
    """El contrato del caso, copiado, con la aprobación escrita en la copia (programacion-del-caso §2)."""
    js = json.loads((CASO / "informes" / "preproduccion.json").read_text(encoding="utf-8"))
    js["contrato"]["aprobado_por"], js["contrato"]["fecha"] = APROBADO, "2026-11-19"
    js["reentreno"], js["lote"], js["prueba_por_otro_camino"] = None, None, None
    return js


def variables(js):
    """Las numéricas y las nominales que lee el modelo, de la cadena del contrato."""
    lee = [f["variable"] for f in js["finalistas"] if any(p["paso"][:3] in ("P20", "P22") for p in f["cadena"])]
    nom = [f["variable"] for f in js["finalistas"] if any(p["paso"][:3] == "P22" for p in f["cadena"])]
    return [v for v in lee if v not in nom], nom


def mes_de_juguete(js, mes, n, fallos, semilla, fin):
    """Un mes con la forma de fotos_riesgo: las columnas del modelo, el identificador, el objetivo y su horizonte."""
    num, _ = variables(js)
    rng = np.random.default_rng(semilla)
    y = np.zeros(n, dtype=np.int8)
    y[:fallos] = 1
    rng.shuffle(y)
    d = {"serial_number": [f"S{i:05d}" for i in range(n)], "fecha": [mes] * n,
         "model": rng.choice(["ST4000DM000", "ST12000NM0008", "TOSHIBA MG07ACA14TA"], n),
         "datacenter": rng.choice(np.array(["phx1", None], dtype=object), n)}
    d["fabricante"] = ["Seagate" if m.startswith("ST") else "Toshiba" for m in d["model"]]
    for v in num:
        x = rng.integers(0, 40, n).astype(float) + 25 * y * (rng.random(n) < 0.6)
        x[rng.random(n) < 0.1] = np.nan
        d[v] = x
    d["capacidad_tb"] = np.where(np.array(d["model"]) == "ST4000DM000", 4.0, 12.0)
    d["avisa"] = rng.random(n) < 0.1 + 0.5 * y
    d["falla_30d"] = y
    d["horizonte_hasta"] = [min(mes + pd.Timedelta(days=30), fin)] * n
    return pd.DataFrame(d)


def escribir_tabla(ruta, meses, js, semilla, por_mes=1500, fallos=15, fin=pd.Timestamp("2024-06-30"), extra=None):
    """Escribe la tabla con un grupo de filas por mes; extra(df) cambia un mes antes de escribirlo."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escritor = None
    for k, mes in enumerate(meses):
        df = mes_de_juguete(js, mes, por_mes, fallos, semilla + k, fin)
        if extra:
            df = extra(df)
        t = pa.Table.from_pandas(df, preserve_index=False)
        t = t.cast(pa.schema([pa.field(f.name, pa.timestamp("ms")) if pa.types.is_timestamp(f.type) else f for f in t.schema]))
        if escritor is None:
            escritor = pq.ParquetWriter(ruta, t.schema)
        escritor.write_table(t, row_group_size=len(df))
    escritor.close()


def configuracion(modelo_en_uso=None):
    """produccion/configuracion.json del caso pequeño."""
    real = json.loads((CASO / "produccion" / "configuracion.json").read_text(encoding="utf-8"))
    real["modelo_en_uso"] = modelo_en_uso
    return real


def montar(semilla=1):
    """Monta tests/tmp_produccion/ con el contrato, el modelado de juguete, la configuración y las dos tablas."""
    if TMP.exists():
        shutil.rmtree(TMP)
    js = contrato()
    (TMP / "informes").mkdir(parents=True)
    (TMP / "produccion").mkdir()
    (TMP / "informes" / "preproduccion.json").write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    (TMP / "produccion" / "configuracion.json").write_text(json.dumps(configuracion(), ensure_ascii=False), encoding="utf-8")
    escribir_tabla(TMP / ENT, MESES_ENT, js, semilla)
    escribir_tabla(TMP / VAL, MESES_VAL, js, 500, fin=pd.Timestamp("2025-06-30"))
    modelado({m.date().isoformat(): (0.0, 0.0) for m in MESES_VAL}, 0.5)
    return js


def modelado(por_mes, auc):
    """informes/modelado.json de juguete: lo que guardó el modelado en la validación."""
    js = {"resultado": {"estado": "OK"},
          "validacion": {"medidas": {"auc": auc},
                         "por_mes": [{"mes": k, "modelo_lista_20": a, "modelo_lista_100": b} for k, (a, b) in por_mes.items()]}}
    (TMP / "informes" / "modelado.json").write_text(json.dumps(js), encoding="utf-8")


def ejecutar(*args):
    """Ejecuta reentrenar.py con -W error sobre el caso pequeño; devuelve el código, la salida y el resumen."""
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP), "--hoy", HOY, *args],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=150)
    ruta = TMP / "modelos" / "reentrenos" / HOY / "reentreno.json"
    res = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return r.returncode, r.stdout + r.stderr, res


# ---------------------------------------------------------------------------------------------------------------
# 3. Los casos
# ---------------------------------------------------------------------------------------------------------------
def contar_con_pandas(ruta, fecha, fraccion=0.02):
    """Las filas que entrenan, sus fallos y el tamaño de la muestra, contados aquí con pandas por otro camino."""
    df = pd.read_parquet(ruta, columns=["fecha", "horizonte_hasta", "falla_30d", "capacidad_tb"])
    antes = df[df["fecha"] < fecha]
    arranque = antes["capacidad_tb"] * 1e12 <= 2_048_408_248_320
    ok = antes[~arranque & (antes["horizonte_hasta"] < fecha)]
    muestra = sum(int(g["falla_30d"].sum()) + int(np.floor(fraccion * int((g["falla_30d"] == 0).sum()) + 0.5))
                  for _, g in ok.groupby("fecha"))
    return {"filas": len(ok), "fallos": int(ok["falla_30d"].sum()), "quitadas": int(len(antes) - len(ok) - arranque.sum()),
            "arranque": int(arranque.sum()), "muestra": muestra}


def casos():
    """Los diez casos del docstring."""
    js = montar()
    carpeta = TMP / "modelos" / "reentrenos" / HOY
    # 1. La tabla de la partición sin --comprobacion
    codigo, salida, _ = ejecutar("--tabla", str(TMP / ENT), "--fecha", "2024-07-01")
    comprobar(codigo != 0 and "comprobación" in salida and not (carpeta / "modelo_riesgo.joblib").exists(),
              f"1 la tabla de la partición sin --comprobacion para ({codigo})")
    # 2. Sin --tabla no arranca
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)], capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    comprobar(r.returncode != 0 and "--tabla" in r.stderr, "2 sin --tabla no arranca: no tiene valor por defecto")
    # 3. Comprobación con un modelado que no es el suyo
    codigo, salida, res = ejecutar("--tabla", str(TMP / ENT), "--comprobacion")
    comprobar(codigo != 0 and res is not None and res["estado"] == "ERROR" and res["comparacion_con_el_modelado"]["iguales"] is False,
              f"3 con un modelado que no es el suyo para con ERROR ({codigo}; {salida[-400:]})")
    if res is None:
        return
    # 4. Con las cifras que dio: OK, igual a lo guardado
    medido = res["comparacion_con_el_modelado"]["medido"]
    modelado({m["mes"]: (m["lista_20"], m["lista_100"]) for m in medido["por_mes"]}, medido["auc"])
    codigo, salida, res = ejecutar("--tabla", str(TMP / ENT), "--comprobacion")
    comprobar(codigo == 0 and res["estado"] == "OK" and res["igual_bit_a_bit"] is True,
              f"4 con el modelado que dan sus cifras: OK e igual a lo guardado ({codigo}; {salida[-600:]})")
    cuenta = contar_con_pandas(TMP / ENT, pd.Timestamp("2024-07-01"))
    comprobar(res["filas_entrena"] == cuenta["filas"] and res["fallos_entrena"] == cuenta["fallos"]
              and res["muestra"]["filas"] == cuenta["muestra"] and res["muestra"]["fallos"] == cuenta["fallos"],
              f"4 las filas, los fallos y la muestra, como se cuentan con pandas ({res['filas_entrena']}, {res['muestra']}, {cuenta})")
    comprobar(abs(res["tasa_real"] - cuenta["fallos"] / cuenta["filas"]) < 1e-15, "4 la tasa real del entrenamiento")
    sin = carpeta / "modelo_riesgo_sin_entrenar.joblib"
    import joblib
    sys.path.insert(0, str(CASO / "scripts"))
    comprobar(sin.exists() and not hasattr(joblib.load(sin).named_steps["modelo"], "modelo_"),
              "4 el Pipeline sin entrenar se guardó antes del fit")
    ficha = json.loads((carpeta / "modelo_riesgo_versiones.json").read_text(encoding="utf-8"))
    comprobar(all(k in ficha for k in ("versiones", "semilla", "huella_tabla", "columnas_entrada", "columnas_salida", "estructura",
                                       "lleva_filas_de_entrenamiento", "filas")) and ficha["semilla"] == 42
              and ficha["lleva_filas_de_entrenamiento"] == [] and ficha["columnas_entrada"] == variables(js)[0] + variables(js)[1],
              "4 la ficha: versiones, semilla, huella, columnas, registro del caso y sin filas de entrenamiento dentro")
    pre = json.loads((TMP / "informes" / "preproduccion.json").read_text(encoding="utf-8"))
    comprobar(pre["reentreno"]["igual_bit_a_bit"] is True and pre["validaciones"]["bit_a_bit"] is True
              and pre["validaciones"]["columnas_del_contrato"] is True and (TMP / "informes" / "preproduccion.md").exists(),
              "4 escribe el reentreno en informes/preproduccion.json y regenera el informe")
    primero = TMP / "modelo_en_uso" / "modelo_riesgo.joblib"
    primero.parent.mkdir()
    for f in ("modelo_riesgo.joblib", "modelo_riesgo_versiones.json"):
        shutil.copy(carpeta / f, primero.parent / f)
    # 5. Una fecha que deja abierto el horizonte de junio (otra tabla, para no ser la de la partición)
    otra = TMP / "data" / "nuevos" / "tabla_a.parquet"
    otra.parent.mkdir(parents=True)
    shutil.copy(TMP / ENT, otra)
    codigo, salida, res = ejecutar("--tabla", str(otra), "--fecha", "2024-06-15")
    q = {x["motivo"]: x for x in res["filas_quitadas"]} if res else {}
    cuenta = contar_con_pandas(otra, pd.Timestamp("2024-06-15"))
    comprobar(codigo == 0 and q.get("objetivo sin conocer", {}).get("filas") == cuenta["quitadas"] == 1500
              and q["objetivo sin conocer"]["casos_del_evento"] == 15 and q["objetivo sin conocer"]["fecha"] == "2024-06-15",
              f"5 quita las fotos con el horizonte abierto y cuenta sus fallos ({q.get('objetivo sin conocer')}, {salida[-300:]})")
    # 6. Un disco de arranque colado
    arr = TMP / "data" / "nuevos" / "tabla_arranque.parquet"
    escribir_tabla(arr, MESES_ENT, js, 1, extra=lambda d: d.assign(capacidad_tb=np.where(d.index < 3, 0.5, d["capacidad_tb"])))
    codigo, salida, res = ejecutar("--tabla", str(arr), "--fecha", "2024-07-01")
    q = {x["motivo"]: x for x in res["filas_quitadas"]} if res else {}
    comprobar(codigo == 0 and q.get("disco de arranque", {}).get("filas") == 3 * len(MESES_ENT),
              f"6 el disco de arranque se quita y se cuenta ({q.get('disco de arranque')})")
    # 7. Con modelo en uso y la misma tabla: igual bit a bit
    (TMP / "produccion" / "configuracion.json").write_text(json.dumps(configuracion(str(primero)), ensure_ascii=False), encoding="utf-8")
    codigo, salida, res = ejecutar("--tabla", str(TMP / ENT), "--comprobacion")
    comprobar(codigo == 0 and res["modelo_en_uso"]["existia"] is True and res["igual_bit_a_bit"] is True,
              f"7 con el modelo en uso y la misma tabla, igual bit a bit ({codigo}; {salida[-400:]})")
    # 8. Con otra tabla, otros datos: cambia y se mide frente al en uso
    nueva = TMP / "data" / "nuevos" / "tabla_b.parquet"
    escribir_tabla(nueva, MESES_ENT, js, 900)
    codigo, salida, res = ejecutar("--tabla", str(nueva), "--fecha", "2024-07-01", "--medir", str(TMP / VAL))
    comp = (res or {}).get("comparacion_con_el_en_uso") or {}
    comprobar(codigo == 0 and res["cambia_con_datos_nuevos"] is True and comp.get("filas") == 3000
              and comp.get("en_uso") is not None and comp.get("reentrenado") is not None,
              f"8 con otros datos el modelo cambia y se mide frente al en uso ({comp}; {salida[-300:]})")
    # 9. Una tabla que solo añade fotos posteriores a la fecha: sale igual, rojo de la validación 8
    mas = TMP / "data" / "nuevos" / "tabla_c.parquet"
    escribir_tabla(mas, list(MESES_ENT) + [pd.Timestamp("2024-07-01")], js, 1)
    codigo, salida, res = ejecutar("--tabla", str(mas), "--fecha", "2024-07-01")
    comprobar(codigo != 0 and res is not None and res["cambia_con_datos_nuevos"] is False and "no ha leído" in res["resumen"],
              f"9 una tabla nueva que deja el modelo igual para (validación 8 en rojo) ({codigo}; {(res or {}).get('resumen')})")
    # 10. La ficha del modelo en uso estropeada
    f = primero.parent / "modelo_riesgo_versiones.json"
    fi = json.loads(f.read_text(encoding="utf-8"))
    fi["huella"] = "0" * 64
    f.write_text(json.dumps(fi), encoding="utf-8")
    codigo, salida, res = ejecutar("--tabla", str(nueva), "--fecha", "2024-07-01")
    comprobar(codigo != 0 and "huella" in salida, f"10 con la ficha del modelo en uso estropeada para al cargarlo ({codigo})")


def sin_resultados_escritos():
    """Error 24: ninguna validación del script lleva su resultado escrito."""
    import re
    texto = SCRIPT.read_text(encoding="utf-8")
    patron = re.compile(r"""["'](igual_bit_a_bit|cambia_con_datos_nuevos|bit_a_bit|columnas_del_contrato|iguales)["']\s*:\s*True""")
    comprobar(not patron.search(texto) and patron.search('{"iguales": True}'), "ninguna validación con su resultado escrito")


# ---------------------------------------------------------------------------------------------------------------
# 4. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"intérprete: {sys.executable}")
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe {SCRIPT.relative_to(CASO).as_posix()}")
        elif not (CASO / "produccion" / "configuracion.json").exists():
            comprobar(False, "existe produccion/configuracion.json")
        else:
            casos()
            sin_resultados_escritos()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos" if FALLOS else "\ntodo en verde")
    sys.exit(1 if FALLOS else 0)
