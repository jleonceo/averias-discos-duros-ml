"""Prueba de scripts/02_calidad_datos.py.

Parte 1: monta en tests/tmp_calidad/ un caso pequeño con datos escritos aquí (el esquema y los cuatro datasets), le
hace su diccionario con scripts/01_diccionario_datos.py, ejecuta el script de calidad sobre él y comprueba lo que tiene
que salir. Trae casos que tienen que salir mal: filas que incumplen cada regla candidata y las cuatro comprobaciones de
la validación (6, 7, 9 y 10) rotas a propósito, que tienen que parar con ERROR.
Parte 2: si ya existe informes/calidad-datos.json real, compara sus cifras de control con tests/cifras_de_referencia.json
(clave «cifras_calidad») y rehace cuatro cifras por otro camino, con pandas y desde otra tabla o columna.

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

import numpy as np
import pandas as pd

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "02_calidad_datos.py"
SCRIPT_DICCIONARIO = CASO / "scripts" / "01_diccionario_datos.py"
TMP = CASO / "tests" / "tmp_calidad"
FALLOS = []

APARTADOS = ["Fuente analizada", "Resumen", "Inspección general", "Estructura", "Tipos y formatos", "Valores ausentes",
             "Duplicados", "Claves y granularidad", "Categóricas y texto", "Numéricas y outliers", "Fechas",
             "Reglas lógicas e integridad", "Cruces entre tablas", "Reglas candidatas para aprobar",
             "Resumen de problemas detectados", "Posibles acciones", "Parámetros usados", "Datos personales",
             "Límites de esta revisión"]


def comprobar(nombre, condicion, detalle=""):
    """Apunta un caso que falla, con su nombre y lo que se vio."""
    if not condicion:
        FALLOS.append(f"{nombre}: {detalle}")
        print(f"FALLA  {nombre}  {detalle}")
    else:
        print(f"pasa   {nombre}")


def cargar(ruta, nombre):
    """Carga un script como módulo, sin ejecutar su parte principal."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
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
def foto(fecha, filas):
    """Tabla de una foto mensual: cada fila es (serie, modelo, capacidad, failure, centro, ranura, s5, s9, s187, s188, s194)."""
    columnas = ["serial_number", "model", "capacity_bytes", "failure", "datacenter", "pod_slot_num", "smart_5_raw",
                "smart_9_raw", "smart_187_raw", "smart_188_raw", "smart_194_raw"]
    df = pd.DataFrame(filas, columns=columnas)
    df.insert(0, "date", fecha)
    df.insert(0, "fecha", pd.to_datetime([fecha] * len(df)))
    df["cluster_id"] = [0 if c is not None else None for c in df["datacenter"]]
    # Los contadores 197 y 198 llegan vacíos en la fila sin horas: así la fila de capacidad no válida no trae ninguno
    df["smart_197_raw"] = np.where(pd.isna(df["smart_9_raw"]), np.nan, 0.0)
    df["smart_198_raw"] = np.where(pd.isna(df["smart_9_raw"]), np.nan, 0.0)
    for c in ["pod_slot_num", "smart_5_raw", "smart_9_raw", "smart_187_raw", "smart_188_raw", "smart_194_raw"]:
        df[c] = df[c].astype("float64")
    return df


ST4, WD14, WD14B, ST05, ST16 = "ST4000DM000", "WDC WUH721414ALE6L4", "WDC  WUH721414ALE6L4", "ST500LM030", "ST16000NM001G"
C4, C14, C05, C16 = 4000787030016, 14000519643136, 500107862016, 16000900661248


def montar_caso():
    """Crea el caso pequeño. Lo que tiene que salir mal está anotado en cada fila."""
    if TMP.exists():
        shutil.rmtree(TMP)
    raw = TMP / "data" / "raw"
    pod = raw / "podado"
    (pod / "fotos_mensuales").mkdir(parents=True)
    (pod / "ventanas_fallo").mkdir(parents=True)
    nombres = ["Last Updated Q2 2024", "date", "serial_number", "model", "capacity_bytes", "failure", "datacenter",
               "cluster_id", "pod_slot_num", "smart_5_raw", "smart_9_raw", "smart_187_raw", "smart_188_raw",
               "smart_194_raw", "smart_197_raw", "smart_198_raw", "smart_211_normailized"]
    (raw / "Drive_Stats_Schema_Current.csv").write_bytes(b"\xef\xbb\xbf" + "\r\n".join(nombres).encode("utf-8") + b"\r\n")
    # A1: falta en junio y vuelve en julio (un hueco de un mes)
    # A2: sus horas bajan de 5.000 a 4.000 (RC-01), su contador 5 baja de 3 a 2 (RC-03), su modelo sale con dos
    #     espacios en junio (D1, RC-02 en bruto) y falla el 15/06
    # B1: disco de arranque, sin ranura
    # C1: capacidad -1 y sin ningún contador en abril (ausencia de la fila, RC-02 de capacidad); 188 por encima de mil
    #     millones en mayo; 187 en 65.535 en junio; falla el 01/07 y su foto de julio trae failure = 1 (RC-05 cumple)
    abril = [("A1", ST4, C4, 0, "sac0", 1, 0, 1000, 0, 0, 30), ("A2", WD14, C14, 0, "sac0", 2, 3, 5000, None, None, 31),
             ("B1", ST05, C05, 0, "sac0", None, 0, 100, 0, 0, 30), ("C1", ST16, -1, 0, "sac0", 4, None, None, None, None, None)]
    mayo = [("A1", ST4, C4, 0, "sac0", 1, 0, 1720, 0, 0, 30), ("A2", WD14, C14, 0, "sac0", 2, 2, 4000, None, None, 31),
            ("B1", ST05, C05, 0, "sac0", None, 0, 820, 0, 0, 30), ("C1", ST16, C16, 0, "sac0", 4, 0, 50, 0, 4295032833, 32)]
    junio = [("A2", WD14B, C14, 0, None, None, 2, 4700, None, None, 31), ("B1", ST05, C05, 0, "sac0", None, 0, 1540, 0, 0, 30),
             ("C1", ST16, C16, 0, "sac0", 4, 0, 770, 65535, 4295032833, 33)]
    julio = [("A1", ST4, C4, 0, "sac0", 1, 0, 3000, 0, 0, 30), ("B1", ST05, C05, 0, "sac0", None, 0, 2260, 0, 0, 30),
             ("C1", ST16, C16, 1, "sac0", 4, 0, 1490, 65535, 4295032833, 34)]
    for fecha, filas in (("2024-04-01", abril), ("2024-05-01", mayo), ("2024-06-01", junio), ("2024-07-01", julio)):
        foto(fecha, filas).to_parquet(pod / "fotos_mensuales" / f"{fecha[:7]}.parquet")
    # Ventanas: la de A2 (14 y 15/06) y la de C1 (30/06 y 01/07). La de C1 trae 117 grados (RC-04) y un failure = 1 el
    # día antes del fallo (RC-06); la de A2 no trae ranura el día del fallo y la recupera el día antes, y su fila del 14/06
    # dice 15/06 en el texto de la fecha (una lectura nueva que va a pendientes)
    vent = pd.DataFrame({
        "fecha": pd.to_datetime(["2024-06-14", "2024-06-15", "2024-06-30", "2024-07-01"]),
        "date": ["2024-06-15", "2024-06-15", "2024-06-30", "2024-07-01"],
        "serial_number": ["A2", "A2", "C1", "C1"], "model": [WD14, WD14, ST16, ST16],
        "capacity_bytes": [C14, C14, C16, C16], "failure": [0, 1, 1, 1], "datacenter": ["sac0", "sac0", "sac0", "sac0"],
        "pod_slot_num": [2.0, None, 4.0, 4.0], "smart_5_raw": [2.0, 2.0, 0.0, 0.0], "smart_9_raw": [4900.0, 4910.0, 1480.0, 1490.0],
        "smart_187_raw": [None, None, 65535.0, 65535.0], "smart_188_raw": [None, None, 4295032833.0, 4295032833.0],
        "smart_194_raw": [31.0, 31.0, 117.0, 34.0], "smart_197_raw": [0.0] * 4, "smart_198_raw": [0.0] * 4,
        "dia_fallo": pd.to_datetime(["2024-06-15", "2024-06-15", "2024-07-01", "2024-07-01"])})
    vent["cluster_id"] = 0
    vent.iloc[:2].to_parquet(pod / "ventanas_fallo" / "data_Q2_2024.parquet")
    vent.iloc[2:].to_parquet(pod / "ventanas_fallo" / "data_Q3_2024.parquet")
    # Recuento: el 01/06 con un fallo de más (RC-07, fallos por encima de discos, y RC-08, no cuadra con la lista)
    dias = pd.date_range("2024-04-01", "2024-07-01", freq="D")
    filas = []
    for d in dias:
        filas.append((d, ST4, C4, "sac0", 1, 0))
        filas.append((d, ST05, C05, "sac0", 1, 0))
        filas.append((d, WD14, C14, "sac0", 1, 1 if d == pd.Timestamp("2024-06-15") else 0))
        filas.append((d, ST16, C16, "sac0", 1, 1 if d == pd.Timestamp("2024-07-01") else 0))
    rec = pd.DataFrame(filas, columns=["fecha", "model", "capacity_bytes", "datacenter", "discos", "fallos"])
    rec.loc[(rec["fecha"] == "2024-06-01") & (rec["model"] == ST4), "fallos"] = 2
    rec.loc[(rec["fecha"] == "2024-04-01") & (rec["model"] == ST16), "capacity_bytes"] = -1
    rec.to_parquet(pod / "recuento_diario.parquet")
    pd.DataFrame({"serial_number": ["A2", "C1"], "dia_fallo": pd.to_datetime(["2024-06-15", "2024-07-01"])}).to_parquet(pod / "fallos.parquet")


def buscar(lista, **filtro):
    """Primer elemento de una lista de diccionarios que cumple el filtro."""
    return next((x for x in lista if all(x.get(k) == v for k, v in filtro.items())), None)


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 1 · el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def parte_1():
    """Ejecuta el script sobre el caso pequeño y comprueba cada salida, también las que tienen que fallar."""
    montar_caso()
    cargar(SCRIPT_DICCIONARIO, "diccionario").main(raiz=TMP)
    modulo = cargar(SCRIPT, "calidad")
    raw = TMP / "data" / "raw"
    antes = huella_carpeta(raw)

    # 3.1 Ejecución completa
    modulo.main(raiz=TMP)
    ruta_json = TMP / "informes" / "calidad-datos.json"
    cal = json.loads(ruta_json.read_text(encoding="utf-8"))
    rc = {r["id"]: r for r in cal["reglas_candidatas"]}
    control = cal["cifras_de_control"]
    comprobar("estado AVISO", cal["resultado"]["estado"] == "AVISO", cal["resultado"]["estado"])
    comprobar("fecha_datos", cal.get("fecha_datos") == "2025-06-30", cal.get("fecha_datos"))
    comprobar("parte del diccionario", cal.get("con_diccionario") is True, cal.get("con_diccionario"))
    comprobar("plan aprobado", cal.get("plan_aprobado") == {"por": "El responsable del caso", "fecha": "2026-11-17"}, cal.get("plan_aprobado"))
    comprobar("nueve parámetros", len(cal["parametros"]) >= 9, len(cal["parametros"]))
    comprobar("ocho reglas candidatas aprobadas", sorted(rc) == [f"RC-0{i}" for i in range(1, 9)] and all(r["aprobada"] is True for r in rc.values()),
              sorted(rc))
    comprobar("RC-01 horas que bajan", rc["RC-01"]["filas_que_incumplen"] == 1, rc["RC-01"]["filas_que_incumplen"])
    comprobar("RC-02 modelo o capacidad que cambia", rc["RC-02"]["filas_que_incumplen"] == 2, rc["RC-02"]["filas_que_incumplen"])
    comprobar("RC-03 contador que baja", rc["RC-03"]["filas_que_incumplen"] == 1, rc["RC-03"]["filas_que_incumplen"])
    comprobar("RC-04 temperatura fuera de 10 a 70", rc["RC-04"]["filas_que_incumplen"] == 1, rc["RC-04"]["filas_que_incumplen"])
    comprobar("RC-05 foto con fallo fuera de la lista", rc["RC-05"]["filas_que_incumplen"] == 0 and control["fotos.failure_1"] == 1,
              (rc["RC-05"]["filas_que_incumplen"], control["fotos.failure_1"]))
    comprobar("RC-06 failure fuera del día del fallo", rc["RC-06"]["filas_que_incumplen"] == 1, rc["RC-06"]["filas_que_incumplen"])
    comprobar("RC-07 fallos por encima de discos", rc["RC-07"]["filas_que_incumplen"] == 1, rc["RC-07"]["filas_que_incumplen"])
    comprobar("RC-08 días que no cuadran", rc["RC-08"]["filas_que_incumplen"] == 1, rc["RC-08"]["filas_que_incumplen"])
    comprobar("capacidad no válida en fotos", control["fotos.capacidad_no_valida"] == 1, control["fotos.capacidad_no_valida"])
    comprobar("ausencia de la fila con capacidad no válida", control["fotos.capacidad_no_valida_sin_ningun_contador"] == 1,
              control["fotos.capacidad_no_valida_sin_ningun_contador"])
    comprobar("capacidad no válida en el recuento", control["recuento.capacidad_no_valida"] == 1, control["recuento.capacidad_no_valida"])
    comprobar("discos con hueco", control["fotos.discos_con_hueco"] == 1, control["fotos.discos_con_hueco"])
    comprobar("188 por encima de mil millones", control["fotos.s188_mas_de_mil_millones"] == 3, control["fotos.s188_mas_de_mil_millones"])
    comprobar("187 en 65.535", control["fotos.s187_en_65535"] == 2, control["fotos.s187_en_65535"])
    comprobar("variante de modelo con dos espacios", control["fotos.filas_variante_espacios"] == 1, control["fotos.filas_variante_espacios"])
    comprobar("temperatura de las ventanas", control["ventanas.temp_mas_70"] == 1 and control["ventanas.temp_max"] == 117,
              (control["ventanas.temp_mas_70"], control["ventanas.temp_max"]))
    comprobar("fallo sin ranura el día que la recupera antes", control["ventanas.fallos_ranura_recuperada"] == 1,
              control["ventanas.fallos_ranura_recuperada"])
    comprobar("huella de los ficheros", control["huella.ficheros"] == 9, control["huella.ficheros"])
    comprobar("fecha y texto distintos en las ventanas", control["ventanas.fecha_y_texto_distintos"] == 1, control["ventanas.fecha_y_texto_distintos"])
    comprobar("la lectura nueva va a pendientes con dos opciones", len(cal["pendientes"]) == 1 and len(cal["pendientes"][0]["opciones"]) == 2, cal["pendientes"])
    comprobar("las decisiones cerradas no van a pendientes", not any(p["columna"] in ("model", "smart_188_raw", "smart_5_raw", "smart_187_raw") for p in cal["pendientes"]),
              cal["pendientes"])

    # 3.2 Cada variable con vacíos tiene su veredicto; con menos de 30 filas por segmento, no se puede saber
    s9 = buscar(cal["nulos_por_segmento"], tabla="fotos_mensuales", columna="smart_9_raw")
    comprobar("veredicto de smart_9_raw", s9 is not None and s9["veredicto"] == "no_se_puede_saber", s9)
    comprobar("contadores también por modelo", s9 is not None and "modelo" in s9["dimensiones"], s9 and s9["dimensiones"])
    sin = buscar(cal["nulos_por_segmento"], tabla="fotos_mensuales", columna="capacity_bytes")
    comprobar("columna sin vacíos no entra como vacía", sin is None or sin["veredicto"] == "sin_nulos", sin)

    # 3.3 Cada magnitud con su escala y sus colas; las seis relaciones con sus claves sin pareja
    magnitudes = {(t["tabla"], t["columna"]) for t in cal["tipos"] if t["rol"] == "magnitud"}
    con_escala = {(e["tabla"], e["columna"]) for e in cal["escala"]}
    con_colas = {(c["tabla"], c["columna"]) for c in cal["colas"]}
    comprobar("escala y colas de cada magnitud", magnitudes and magnitudes <= con_escala and magnitudes <= con_colas, magnitudes - con_colas)
    comprobar("seis relaciones", len(cal["cruces"]) == 6 and all(isinstance(c["sin_pareja_izquierda"], int) and isinstance(c["sin_pareja_derecha"], int)
                                                               for c in cal["cruces"]), [(c["izquierda"], c["derecha"]) for c in cal["cruces"]])
    vf = buscar(cal["cruces"], izquierda="fallos", derecha="ventanas_fallo")
    comprobar("fallos y ventanas casan", vf is not None and vf["sin_pareja_izquierda"] == 0 and vf["sin_pareja_derecha"] == 0, vf)

    # 3.4 JSON e informe dicen lo mismo y el informe trae los 19 apartados en su orden
    md = (TMP / "informes" / "calidad-datos.md").read_text(encoding="utf-8")
    titulos = re.findall(r"^## (?:\d+\. )?(.+)$", md, re.M)
    comprobar("los 19 apartados en orden", titulos == APARTADOS, titulos)
    comprobar("el informe dice el estado del JSON", f"Estado: {cal['resultado']['estado']}" in md, "falta el estado")
    comprobar("datos personales sin proteccion-datos.json", "proteccion-datos.json" in md.split("## 18. Datos personales")[1].split("## 19.")[0],
              "el apartado no lo dice")
    comprobar("JSON sin NaN", "NaN" not in ruta_json.read_text(encoding="utf-8"), "hay NaN")
    comprobar("las cuatro validaciones en código, en verde", [v["ok"] for v in cal["validacion"]] == [True] * 4, cal["validacion"])

    # 3.5 Casos que tienen que fallar: la validación caza cada una de sus cuatro comprobaciones
    roto = json.loads(json.dumps(cal))
    roto["nulos_por_segmento"] = [x for x in roto["nulos_por_segmento"] if x["columna"] != "smart_9_raw"]
    comprobar("validación 6 caza una variable sin veredicto", any(e.startswith("6:") for e in modulo.validar(roto, {"a": "1"}, {"a": "1"})),
              modulo.validar(roto, {"a": "1"}, {"a": "1"}))
    roto = json.loads(json.dumps(cal))
    roto["cruces"][0]["sin_pareja_derecha"] = None
    comprobar("validación 7 caza una relación sin recuento", any(e.startswith("7:") for e in modulo.validar(roto, {"a": "1"}, {"a": "1"})),
              modulo.validar(roto, {"a": "1"}, {"a": "1"}))
    comprobar("validación 9 caza un data/raw cambiado", any(e.startswith("9:") for e in modulo.validar(cal, {"a": "1"}, {"a": "2"})),
              modulo.validar(cal, {"a": "1"}, {"a": "2"}))
    roto = json.loads(json.dumps(cal))
    roto["colas"] = roto["colas"][1:]
    roto["parametros"] = []
    errores10 = [e for e in modulo.validar(roto, {"a": "1"}, {"a": "1"}) if e.startswith("10:")]
    comprobar("validación 10 caza una magnitud sin colas y sin parámetros", len(errores10) >= 2, errores10)
    comprobar("validación vacía con el bueno", modulo.validar(cal, {"a": "1"}, {"a": "1"}) == [], modulo.validar(cal, {"a": "1"}, {"a": "1"}))

    # 3.6 Caso que tiene que fallar dentro de main: data/raw cambia a mitad de la ejecución y el JSON queda en ERROR
    original = modulo.huellas
    llamadas = []

    def huellas_que_cambian(carpeta):
        """La segunda lectura de las huellas devuelve otra cosa, como si un fichero hubiera cambiado."""
        h = original(carpeta)
        llamadas.append(1)
        return h if len(llamadas) == 1 else {k: "cambiada" for k in h}

    modulo.huellas = huellas_que_cambian
    try:
        modulo.main(raiz=TMP)
        paro = False
    except Exception:
        paro = True
    modulo.huellas = original
    err = json.loads(ruta_json.read_text(encoding="utf-8"))
    comprobar("data/raw que cambia para con ERROR", paro and err["resultado"]["estado"] == "ERROR", err["resultado"]["estado"])

    # 3.7 Caso que tiene que fallar: un Parquet ilegible para con ERROR
    malo = raw / "podado" / "fotos_mensuales" / "2024-08.parquet"
    malo.write_bytes(b"esto no es un parquet")
    try:
        modulo.main(raiz=TMP)
        paro = False
    except Exception:
        paro = True
    err = json.loads(ruta_json.read_text(encoding="utf-8"))
    comprobar("un Parquet ilegible para con ERROR", paro and err["resultado"]["estado"] == "ERROR", err["resultado"]["estado"])
    malo.unlink()

    # 3.8 Funciones de cálculo contra un caso hecho a mano y contra scipy
    v = modulo.veredicto_reparto
    comprobar("veredicto concentrados", v(np.array([100, 100]), np.array([0, 20]))[0] == "concentrados", v(np.array([100, 100]), np.array([0, 20])))
    comprobar("veredicto repartidos", v(np.array([100, 100]), np.array([10, 10]))[0] == "repartidos", v(np.array([100, 100]), np.array([10, 10])))
    comprobar("veredicto no se puede saber", v(np.array([10, 10]), np.array([1, 1]))[0] == "no_se_puede_saber", v(np.array([10, 10]), np.array([1, 1])))
    from scipy import stats
    x = np.array([1.0, 2, 2, 3, 3, 3, 4, 4, 5, 40])
    o = modulo.atipicos(np.sort(x))
    mad = stats.median_abs_deviation(x, scale="normal")
    esperado_z = int((np.abs(x - np.median(x)) / mad > 3.5).sum())
    q1, q3 = np.quantile(x, [0.25, 0.75])
    esperado_iqr = int(((x < q1 - 1.5 * (q3 - q1)) | (x > q3 + 1.5 * (q3 - q1))).sum())
    comprobar("z robusto igual que scipy", o["z_robusto"] == esperado_z, (o["z_robusto"], esperado_z))
    comprobar("rango intercuartílico igual que numpy", o["iqr"] == esperado_iqr, (o["iqr"], esperado_iqr))
    comprobar("dispersión cero no marca", modulo.atipicos(np.zeros(50))["iqr"] is None, modulo.atipicos(np.zeros(50)))

    # 3.9 Ninguna comprobación escrita con su resultado puesto (error 24) y data/raw intacto
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestas = re.findall(r'"(ok|cumple|valida|pasa|unica|clave_unica|unica_en_maestro|aprobada_ok)"\s*:\s*(True|False)', codigo)
    comprobar("sin comprobaciones con el resultado puesto", puestas == [], puestas)
    comprobar("data/raw intacto", huella_carpeta(raw) == antes, "cambió algún fichero")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 2 · el JSON real contra las cifras de referencia y por otro camino
# ---------------------------------------------------------------------------------------------------------------
def parte_2():
    """Compara las cifras de control del JSON real con las de referencia y rehace cuatro por otro camino."""
    ruta = CASO / "informes" / "calidad-datos.json"
    if not ruta.exists():
        print("parte 2: no hay JSON de calidad real todavía; no se compara")
        return
    cal = json.loads(ruta.read_text(encoding="utf-8"))
    if cal["resultado"]["estado"] not in ("OK", "AVISO"):
        print(f"parte 2: el JSON real está en {cal['resultado']['estado']}; no se compara")
        return
    ref = json.loads((CASO / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))
    control = cal["cifras_de_control"]
    for clave, esperado in ref.get("cifras_calidad", {}).items():
        comprobar(f"referencia {clave}", control.get(clave) == esperado, f"sale {control.get(clave)}, referencia {esperado}")
    comprobar("hay cifras de calidad de referencia", bool(ref.get("cifras_calidad")), "falta la clave cifras_calidad")

    pod = CASO / "data" / "raw" / "podado"
    # Segunda vía 1: fallos por día desde las filas con failure = 1 del día del fallo en las ventanas (otra tabla) frente al recuento
    ventanas = pd.concat([pd.read_parquet(p, columns=["fecha", "dia_fallo", "failure", "smart_194_raw"])
                          for p in sorted((pod / "ventanas_fallo").glob("*.parquet"))], ignore_index=True)
    del_dia = ventanas.loc[ventanas["fecha"].eq(ventanas["dia_fallo"]) & ventanas["failure"].eq(1)].groupby("fecha").size()
    recuento = pd.read_parquet(pod / "recuento_diario.parquet")
    por_dia = recuento.groupby("fecha")["fallos"].sum()
    distintos = int((por_dia.sub(del_dia.reindex(por_dia.index, fill_value=0))).ne(0).sum())
    comprobar("segunda vía: RC-08 desde las ventanas", distintos == control["rc08.dias_que_no_cuadran"], (distintos, control["rc08.dias_que_no_cuadran"]))
    # Segunda vía 2: temperatura de las ventanas por encima de 70, con pandas sobre la columna
    comprobar("segunda vía: temperatura de las ventanas", int(ventanas["smart_194_raw"].gt(70).sum()) == control["ventanas.temp_mas_70"],
              (int(ventanas["smart_194_raw"].gt(70).sum()), control["ventanas.temp_mas_70"]))
    # Segunda vía 3: ceros de cluster_id en las fotos, contados con pandas fichero a fichero
    ceros = 0
    for p in sorted((pod / "fotos_mensuales").glob("*.parquet")):
        df = pd.read_parquet(p)
        if "cluster_id" in df.columns:
            ceros += int(df["cluster_id"].eq(0).sum())
    comprobar("segunda vía: ceros de cluster_id", ceros == control["fotos.cluster_cero"], (ceros, control["fotos.cluster_cero"]))
    # Segunda vía 4: centro «sin dato» del recuento, con pandas
    comprobar("segunda vía: centro sin dato", int(recuento["datacenter"].eq("sin dato").sum()) == control["recuento.sin_dato"],
              (int(recuento["datacenter"].eq("sin dato").sum()), control["recuento.sin_dato"]))


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
