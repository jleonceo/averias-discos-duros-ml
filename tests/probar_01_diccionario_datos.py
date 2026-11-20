"""Prueba de scripts/01_diccionario_datos.py.

Parte 1: monta en tests/tmp_diccionario/ un caso pequeño con datos escritos aquí (el esquema y las cuatro tablas del
dataset), ejecuta el script sobre él y comprueba lo que tiene que salir, también los casos que tienen que fallar.
Parte 2: si ya existe el diccionario real, compara sus cifras con tests/cifras_de_referencia.json y rehace tres cifras
por otro camino (pandas sobre otra tabla u otra lectura, no el perfil de pyarrow del script).

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "01_diccionario_datos.py"
TMP = CASO / "tests" / "tmp_diccionario"
FALLOS = []


def comprobar(nombre, condicion, detalle=""):
    """Apunta un caso que falla, con su nombre y lo que se vio."""
    if not condicion:
        FALLOS.append(f"{nombre}: {detalle}")
        print(f"FALLA  {nombre}  {detalle}")
    else:
        print(f"pasa   {nombre}")


def cargar_script():
    """Carga el script como módulo, sin ejecutar su parte principal."""
    spec = importlib.util.spec_from_file_location("diccionario", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def huella_carpeta(carpeta):
    """SHA-256 de cada fichero de una carpeta, para ver que el script no la toca."""
    return {p.relative_to(carpeta).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(carpeta.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------------------------------------------
# 2. Datos pequeños escritos en la prueba
# ---------------------------------------------------------------------------------------------------------------
def montar_caso():
    """Crea el caso pequeño: el esquema y las cuatro tablas del dataset."""
    if TMP.exists():
        shutil.rmtree(TMP)
    raw = TMP / "data" / "raw"
    pod = raw / "podado"
    (pod / "fotos_mensuales").mkdir(parents=True)
    (pod / "ventanas_fallo").mkdir(parents=True)
    # Esquema de la organización: primera línea que no es un nombre, una errata y columnas que el dataset no trae
    nombres = ["Last Updated Q2 2024", "date", "serial_number", "model", "capacity_bytes", "failure", "datacenter",
               "is_legacy_format", "smart_5_normalized", "smart_5_raw", "smart_9_raw", "smart_15_raw",
               "smart_211_normailized", "smart_211_raw"]
    (raw / "Drive_Stats_Schema_Current.csv").write_bytes(b"\xef\xbb\xbf" + "\r\n".join(nombres).encode("utf-8") + b"\r\n")
    # Fotos: junio en construcción, julio en validación; un -1 de capacidad, una columna vacía, una sin documentar
    # y una que solo trae el segundo mes
    pd.DataFrame({"fecha": pd.to_datetime(["2024-06-01"] * 3), "date": ["2024-06-01"] * 3, "serial_number": ["A1", "A2", "B1"],
                  "model": ["ST4000DM000", "WDC WUH721414ALE6L4", "ST500LM030"],
                  "capacity_bytes": [4000787030016, 14000519643136, 500107862016], "failure": [0, 0, 0],
                  "smart_5_raw": [0.0, 3.0, 0.0], "smart_9_raw": [100.0, None, 50.0], "smart_15_raw": [None, None, None],
                  "smart_250_raw": [1.0, 2.0, 3.0]}).to_parquet(pod / "fotos_mensuales" / "2024-06.parquet")
    pd.DataFrame({"fecha": pd.to_datetime(["2024-07-01"] * 2), "date": ["2024-07-01"] * 2, "serial_number": ["A1", "C1"],
                  "model": ["ST4000DM000", "ST16000NM001G"], "capacity_bytes": [-1, 16000900661248], "failure": [0, 0],
                  "smart_5_raw": [0.0, 0.0], "smart_9_raw": [844.0, 10.0], "smart_15_raw": [None, None],
                  "smart_211_raw": [0.0, 1.0], "smart_250_raw": [1.0, 2.0]}).to_parquet(pod / "fotos_mensuales" / "2024-07.parquet")
    # Ventanas: el fallo de A2, con su modelo escrito con dos espacios el primer día
    pd.DataFrame({"fecha": pd.to_datetime(["2024-06-29", "2024-06-30"]), "date": ["2024-06-29", "2024-06-30"],
                  "serial_number": ["A2", "A2"], "model": ["WDC  WUH721414ALE6L4", "WDC WUH721414ALE6L4"],
                  "capacity_bytes": [14000519643136, 14000519643136], "failure": [0, 1], "smart_5_raw": [3.0, 5.0],
                  "dia_fallo": pd.to_datetime(["2024-06-30", "2024-06-30"])}).to_parquet(pod / "ventanas_fallo" / "data_Q2_2024.parquet")
    pd.DataFrame({"fecha": pd.to_datetime(["2024-06-29", "2024-06-30", "2024-06-30", "2024-07-01"]),
                  "model": ["ST4000DM000", "ST4000DM000", "WDC WUH721414ALE6L4", "ST4000DM000"],
                  "capacity_bytes": [4000787030016, -1, 14000519643136, 4000787030016],
                  "datacenter": ["sin dato", "sin dato", "sin dato", "sac0"], "discos": [1, 1, 1, 1],
                  "fallos": [0, 0, 1, 0]}).to_parquet(pod / "recuento_diario.parquet")
    pd.DataFrame({"serial_number": ["A2"], "dia_fallo": pd.to_datetime(["2024-06-30"])}).to_parquet(pod / "fallos.parquet")


def tabla(dic, nombre):
    """Devuelve la tabla del diccionario con ese nombre."""
    return next(t for t in dic["tablas"] if t["tabla"] == nombre)


def campo(t, columna):
    """Devuelve la ficha de una columna de una tabla."""
    return next(c for c in t["campos"] if c["columna"] == columna)


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 1 · el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def parte_1():
    """Ejecuta el script sobre el caso pequeño y comprueba cada salida."""
    montar_caso()
    modulo = cargar_script()
    raw = TMP / "data" / "raw"
    antes = huella_carpeta(raw)

    # 3.1 Ejecución completa
    modulo.main(raiz=TMP)
    ruta_json = TMP / "contexto-proyecto" / "fuentes" / "diccionario-datos-origen.json"
    dic = json.loads(ruta_json.read_text(encoding="utf-8"))
    nombres_tablas = [t["tabla"] for t in dic["tablas"]]
    comprobar("estado AVISO", dic["resultado"]["estado"] == "AVISO", dic["resultado"]["estado"])
    comprobar("fecha_datos", dic.get("fecha_datos") == "2025-06-30", dic.get("fecha_datos"))
    comprobar("cinco tablas, ninguna de ZIP", nombres_tablas == ["fotos_mensuales", "ventanas_fallo", "recuento_diario", "fallos", "esquema_backblaze"],
              nombres_tablas)
    comprobar("huella de todo data/raw", len(dic["entradas"]) == 6, len(dic["entradas"]))
    f = tabla(dic, "fotos_mensuales")
    comprobar("filas de fotos", f["filas"] == 5 and f["ficheros"] == 2, (f["filas"], f["ficheros"]))
    comprobar("columnas por fichero", f["columnas_por_fichero"] == {"min": 10, "max": 11}, f["columnas_por_fichero"])
    comprobar("filas por periodo", f["filas_por_periodo"] == {"construccion": 3, "validacion": 2}, f["filas_por_periodo"])
    comprobar("grupos por capacidad de la fila", f["filas_por_grupo"] == {"datos": 3, "arranque": 1, "capacidad_no_valida": 1}, f["filas_por_grupo"])
    comprobar("no válida resuelta por el modelo", f["capacidad_no_valida_por_modelo"] == {"datos": 1, "arranque": 0, "sin_capacidad_unica": 0},
              f["capacidad_no_valida_por_modelo"])
    comprobar("datos con la capacidad del modelo", f["filas_datos_con_capacidad_del_modelo"] == 4, f["filas_datos_con_capacidad_del_modelo"])
    comprobar("discos distintos", f["discos_distintos"] == 4, f["discos_distintos"])
    comprobar("columna vacía no se puede saber", campo(f, "smart_15_raw")["clase"] == "no_se_puede_saber", campo(f, "smart_15_raw")["clase"])
    comprobar("nulos de una columna", campo(f, "smart_9_raw")["nulos"] == 1, campo(f, "smart_9_raw")["nulos"])
    comprobar("columna que falta en un fichero", campo(f, "smart_211_raw")["filas_sin_columna"] == 3, campo(f, "smart_211_raw")["filas_sin_columna"])
    comprobar("valores de failure", campo(f, "failure")["valores"] == [{"valor": 0, "frecuencia": 5}], campo(f, "failure")["valores"])
    v = tabla(dic, "ventanas_fallo")
    comprobar("modelo con variantes es decisión", campo(v, "model")["clase"] == "decision_de_negocio", campo(v, "model")["clase"])
    comprobar("pendiente del modelo", any(p["columna"] == "model" and p["tabla"] == "ventanas_fallo" for p in dic["pendientes"]), dic["pendientes"])
    comprobar("ventanas", v["ventanas"] == 1 and v["medidas"]["ventanas con menos de 31 filas"] == 1, (v["ventanas"], v["medidas"]))
    contra = {c["columna"] for c in dic["contradicciones"]}
    comprobar("contradicción primera línea", "Last Updated Q2 2024" in contra, contra)
    comprobar("contradicción errata del esquema", "smart_211_normailized" in contra, contra)
    comprobar("contradicción columna sin documentar", "smart_250_raw" in contra, contra)
    comprobar("contradicción columna que falta en un fichero", "smart_211_raw" in contra, contra)
    comprobar("una columna quitada no es contradicción", "is_legacy_format" not in contra and "datacenter" not in contra, contra)
    no_llegan = {c["columna"] for c in dic["columnas_que_no_llegan"]}
    comprobar("columnas quitadas del dataset listadas", {"datacenter", "is_legacy_format", "smart_5_normalized"} <= no_llegan, no_llegan)
    fa = tabla(dic, "fallos")
    comprobar("fallos por periodo", fa["filas_por_periodo"] == {"construccion": 1, "validacion": 0}, fa["filas_por_periodo"])
    comprobar("fallos de discos de datos", fa["filas_datos_con_capacidad_del_modelo_por_periodo"] == {"construccion": 1, "validacion": 0},
              fa["filas_datos_con_capacidad_del_modelo_por_periodo"])
    r = tabla(dic, "recuento_diario")
    comprobar("suma de días de disco", r["suma_discos"] == 4 and r["dias"] == 3 and r["dias_que_faltan"] == 0, (r["suma_discos"], r["dias"], r["dias_que_faltan"]))
    e = tabla(dic, "esquema_backblaze")
    comprobar("líneas del esquema", e["filas"] == 14 and e["primera_linea"] == "Last Updated Q2 2024", (e["filas"], e.get("primera_linea")))
    md = (TMP / "contexto-proyecto" / "fuentes" / "diccionario-datos-origen.md").read_text(encoding="utf-8")
    comprobar("Markdown con las filas del JSON", "| fotos_mensuales | 5 |" in md, "no está la fila del resumen")
    comprobar("Markdown con datos personales", "## 10. Datos personales" in md, "falta el apartado")
    texto = (md + json.dumps(dic, ensure_ascii=False)).replace("data/raw/podado", "")
    comprobar("los textos no dicen «el dataset» en singular", re.search(r"\b(el|del) dataset\b", texto, re.I) is None,
              re.findall(r".{30}\b(?:el|del) dataset\b.{20}", texto, re.I)[:3])
    comprobar("los textos dicen dataset, no poda", re.search(r"\bpoda", texto) is None, re.findall(r".{30}\bpoda.{30}", texto)[:3])

    # 3.2 Caso que tiene que fallar: un Parquet ilegible para el script y deja el JSON en ERROR
    malo = raw / "podado" / "fotos_mensuales" / "2024-08.parquet"
    malo.write_bytes(b"esto no es un parquet")
    try:
        modulo.main(raiz=TMP)
        paro = False
    except Exception:
        paro = True
    dic_err = json.loads(ruta_json.read_text(encoding="utf-8"))
    comprobar("un Parquet ilegible para con ERROR", paro and dic_err["resultado"]["estado"] == "ERROR", dic_err["resultado"]["estado"])
    malo.unlink()

    # 3.3 Caso que tiene que fallar: la validación caza una columna sin ficha y un significado sin procedencia
    roto = json.loads(json.dumps(dic))
    tabla(roto, "fallos")["campos"].pop()
    campo(tabla(roto, "recuento_diario"), "discos")["procedencia"] = ""
    errores = modulo.validar(roto)
    comprobar("validación caza columna sin ficha", any("sin ficha" in x for x in errores), errores)
    comprobar("validación caza significado sin procedencia", any("procedencia" in x for x in errores), errores)
    comprobar("validación da vacío con el bueno", modulo.validar(dic) == [], modulo.validar(dic))

    # 3.4 Ninguna comprobación escrita con su resultado puesto (error 24)
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestas = re.findall(r'"(ok|cumple|valida|pasa|unica|clave_unica)"\s*:\s*(True|False)', codigo)
    comprobar("sin comprobaciones con el resultado puesto", puestas == [], puestas)
    comprobar("el script no busca ZIP", "zip_originales" not in codigo and "import zipfile" not in codigo, "nombra zip_originales o zipfile")

    # 3.5 data/raw del caso pequeño, intacto
    comprobar("data/raw intacto", huella_carpeta(raw) == antes, "cambió algún fichero")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 2 · el diccionario real contra las cifras de referencia y por otro camino
# ---------------------------------------------------------------------------------------------------------------
def parte_2():
    """Compara el diccionario real con las cifras de referencia y rehace tres cifras con pandas."""
    ruta = CASO / "contexto-proyecto" / "fuentes" / "diccionario-datos-origen.json"
    if not ruta.exists():
        print("parte 2: no hay diccionario real todavía; no se compara")
        return
    dic = json.loads(ruta.read_text(encoding="utf-8"))
    if dic["resultado"]["estado"] not in ("OK", "AVISO") or "tablas" not in dic:
        print(f"parte 2: el diccionario real está en {dic['resultado']['estado']} o es de antes del cambio de alcance; no se compara")
        return
    ref = json.loads((CASO / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))["cifras"]
    fo, ve, re_, fa, es = (tabla(dic, n) for n in ("fotos_mensuales", "ventanas_fallo", "recuento_diario", "fallos", "esquema_backblaze"))
    valores = {
        "fotos.ficheros": fo["ficheros"], "fotos.filas": fo["filas"], "fotos.columnas_min": fo["columnas_por_fichero"]["min"],
        "fotos.columnas_max": fo["columnas_por_fichero"]["max"], "fotos.discos": fo["discos_distintos"],
        "fotos.filas_datos_con_modelo": fo["filas_datos_con_capacidad_del_modelo"],
        "fotos.filas_construccion": fo["filas_por_periodo"]["construccion"], "fotos.filas_validacion": fo["filas_por_periodo"]["validacion"],
        "fotos.ficheros_construccion": fo["ficheros_por_periodo"]["construccion"], "fotos.ficheros_validacion": fo["ficheros_por_periodo"]["validacion"],
        "ventanas.ficheros": ve["ficheros"], "ventanas.filas": ve["filas"], "ventanas.columnas_min": ve["columnas_por_fichero"]["min"],
        "ventanas.columnas_max": ve["columnas_por_fichero"]["max"], "ventanas.ventanas": ve["ventanas"],
        "ventanas.filas_construccion": ve["filas_por_periodo"]["construccion"], "ventanas.filas_validacion": ve["filas_por_periodo"]["validacion"],
        "recuento.filas": re_["filas"], "recuento.columnas": re_["columnas"], "recuento.dias": re_["dias"],
        "recuento.dias_sin_hueco": re_["dias_que_faltan"], "recuento.filas_construccion": re_["filas_por_periodo"]["construccion"],
        "recuento.filas_validacion": re_["filas_por_periodo"]["validacion"], "recuento.suma_discos": re_["suma_discos"],
        "recuento.suma_fallos": re_["suma_fallos"],
        "fallos.filas": fa["filas"], "fallos.discos": fa["discos_distintos"],
        "fallos.filas_construccion": fa["filas_por_periodo"]["construccion"], "fallos.filas_validacion": fa["filas_por_periodo"]["validacion"],
        "fallos.datos_construccion": fa["filas_datos_con_capacidad_del_modelo_por_periodo"]["construccion"],
        "fallos.datos_validacion": fa["filas_datos_con_capacidad_del_modelo_por_periodo"]["validacion"],
        "esquema.lineas": es["filas"], "esquema.primera_linea": es["primera_linea"], "esquema.nombres": es["nombres_de_columna"],
        "huella.ficheros": len(dic["entradas"]),
        "huella.esquema": next(e["sha256"] for e in dic["entradas"] if e["ruta"].endswith("Drive_Stats_Schema_Current.csv")),
        "huella.fallos": next(e["sha256"] for e in dic["entradas"] if e["ruta"].endswith("podado/fallos.parquet")),
    }
    for clave, esperado in ref.items():
        comprobar(f"referencia {clave}", valores.get(clave) == esperado, f"sale {valores.get(clave)}, referencia {esperado}")

    pod = CASO / "data" / "raw" / "podado"
    # Segunda vía 1: filas de la lista de fallos frente a la suma de fallos del recuento, otra tabla
    recuento = pd.read_parquet(pod / "recuento_diario.parquet", columns=["fallos"])
    comprobar("segunda vía: fallos del recuento = filas de la lista de fallos", int(recuento["fallos"].sum()) == fa["filas"],
              (int(recuento["fallos"].sum()), fa["filas"]))
    # Segunda vía 2: ventanas contadas con pandas por disco y día del fallo frente a las filas de la lista de fallos
    ventanas = pd.concat([pd.read_parquet(p, columns=["serial_number", "dia_fallo"]) for p in sorted((pod / "ventanas_fallo").glob("*.parquet"))])
    comprobar("segunda vía: ventanas = filas de la lista de fallos", ventanas.drop_duplicates().shape[0] == fa["filas"] == ve["ventanas"],
              (ventanas.drop_duplicates().shape[0], fa["filas"], ve["ventanas"]))
    # Segunda vía 3: nulos de smart_9_raw en las fotos, contados con pandas fichero a fichero
    nulos = sum(int(pd.read_parquet(p, columns=["smart_9_raw"])["smart_9_raw"].isna().sum()) for p in sorted((pod / "fotos_mensuales").glob("*.parquet")))
    comprobar("segunda vía: nulos de smart_9_raw en fotos", nulos == campo(fo, "smart_9_raw")["nulos"], (nulos, campo(fo, "smart_9_raw")["nulos"]))


# ---------------------------------------------------------------------------------------------------------------
# 5. Principal
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print("intérprete:", sys.executable)
    try:
        try:
            parte_1()
        except Exception as error:  # un fallo al ejecutar se apunta como caso que falla, no se tapa
            FALLOS.append(f"parte 1 no se pudo ejecutar: {type(error).__name__}: {error}")
            print("FALLA  parte 1:", type(error).__name__, error)
        parte_2()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\ntodas las comprobaciones pasan")
    sys.exit(1 if FALLOS else 0)
