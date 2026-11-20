"""Prueba de scripts/20_prueba_final_prevision.py (encargo 24; skill programacion-del-caso).

Monta en tests/tmp_prevision/ un caso pequeño, que se borra al terminar, con dos trimestres (2024T3 y 2024T4):
  - seis fotos mensuales en bruto, de julio a diciembre de 2024, y la de junio, fuera del periodo, como historia de la de
    julio, con cinco discos de datos y uno de arranque:
      A1 y A2 del modelo MA (4 TB; en la foto de julio A1 llega con el nombre «MA OLD», que el mapeo corrige), B1 y S1
      del MB (8 TB; B1 sin centro y S1 sin horas), N1 del MN (8 TB, modelo nuevo desde octubre, sin tasa propia) y BT
      del BOOT (0,25 TB, de arranque);
  - la lista de fallos y sus ventanas: S1 el 15/08 sin horas (su edad sale de su primera aparición), A2 el 01/10, el
    primer día de 2024T4 (cuenta en ese trimestre y no en la historia de su previsión), BT el 10/11 (de arranque, fuera)
    y OLD1 en marzo, fuera del periodo;
  - el recuento diario, con el nombre «MA OLD» en julio y una celda sin ninguna foto: MB en el centro c2 en agosto, con
    31 días;
  - las tablas del análisis de juguete (dias_por_tramo con la historia de enero de 2024 y los seis meses del periodo,
    inicio_trimestre y dim_modelo) y los pares de B9, con las cifras calculadas a mano en esta prueba.
Los periodos de los dos modos se cambian en el módulo para el caso pequeño; lo demás es el script de verdad.

Casos:
  1. sin modo, o con los dos, el script no arranca (sin valor por defecto);
  2. las cinco funciones copiadas del script 10 son las mismas, letra a letra, y la comparación sale en rojo con una copia
     cambiada;
  3. las comprobaciones en rojo: un mes del trimestre en la historia; unos totales que no son la suma de los trimestres;
     unos días repartidos que no suman los del recuento; unos fallos que no suman los de la lista; la huella de data/raw/
     que cambia; una validación con su resultado escrito; dos diferencias admitidas;
  4. --reserva sin el ensayo en OK: ERROR;
  5. el ensayo con las tablas de juguete: OK, con las piezas calculadas a mano (filas, discos, días, fallos), la celda sin
     foto contada aparte, el fallo de arranque fuera, el fallo sin horas con edad 0, el del primer día fuera de la
     historia de 2024T4 y el modelo nuevo en el nivel de capacidad;
  6. --reserva: escribe el JSON y el informe, con los mismos pares y la primera frase que dice si gana la cuenta;
     data/raw/ sin cambios;
  7. --reserva por segunda vez: PARADO sin tocar lo medido;
  8. el ensayo con unos pares de juguete con una cifra distinta: ERROR, y dice cuál.
Sale con 0 si todo pasa y con 1 si algo falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import hashlib
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "20_prueba_final_prevision.py"
SCRIPT_10 = CASO / "scripts" / "10_indicadores_coste_prevision.py"
TMP = CASO / "tests" / "tmp_prevision"
POD = TMP / "data" / "raw" / "podado"
RES = TMP / "data" / "raw" / "reserva"
FALLOS = []
COPIADAS = ["inicio_trimestre", "prever_trimestre", "error_ponderado", "montar_pares", "resumen_error"]

# Capacidades en bytes de los cuatro modelos de juguete
C4, C8, C_BOOT = 4_000_000_000_000, 8_000_000_000_000, 250_000_000_000
HORAS_ANO, MES = 8766.0, 730.0
CONTADORES = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]


def cargar(nombre, ruta):
    """Carga un fichero Python como módulo; su trabajo está bajo __main__ y no se ejecuta."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def comprobar(condicion, caso):
    """Apunta el caso si no se cumple y lo imprime."""
    print(("ok    " if condicion else "FALLA ") + caso)
    if not condicion:
        FALLOS.append(caso)


def cerca(a, b, tol=1e-9):
    """Dos números iguales salvo la tolerancia."""
    return a is not None and b is not None and math.isclose(float(a), float(b), rel_tol=0, abs_tol=tol)


# ---------------------------------------------------------------------------------------------------------------
# 2. Los datos en bruto del caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def discos_del_mes(k):
    """Los discos de la foto del mes k (0 = julio de 2024): (serial, modelo, capacidad, centro, horas, failure)."""
    filas = [("A1", "MA OLD" if k == 0 else "MA", C4, "c1", 1.5 * HORAS_ANO + MES * k, 0)]
    if k <= 3:
        filas.append(("A2", "MA", C4, "c1", 2.2 * HORAS_ANO + MES * k, 1 if k == 3 else 0))
    filas.append(("B1", "MB", C8, None, 0.5 * HORAS_ANO + MES * k, 0))
    if k <= 1:
        filas.append(("S1", "MB", C8, "c1", None, 0))
    if k >= 3:
        filas.append(("N1", "MN", C8, "c1", 100.0 + MES * (k - 3), 0))
    if k <= 4:
        filas.append(("BT", "BOOT", C_BOOT, "c1", 1000.0, 0))
    return filas


def escribir_foto(carpeta, k):
    """La foto en bruto del mes k, con las columnas que lee el script y sus tipos de data/raw/."""
    fecha = pd.Timestamp(2024, 7 + k, 1)
    filas = discos_del_mes(k)
    df = pd.DataFrame({
        "fecha": pd.Series([fecha] * len(filas), dtype="datetime64[ms]"),
        "date": [fecha.strftime("%Y-%m-%d")] * len(filas),
        "serial_number": [f[0] for f in filas], "model": [f[1] for f in filas],
        "capacity_bytes": pd.Series([f[2] for f in filas], dtype="int64"),
        "failure": pd.Series([f[5] for f in filas], dtype="int64"),
        "datacenter": pd.Series([f[3] for f in filas], dtype=object),
        "smart_9_raw": pd.Series([f[4] for f in filas], dtype="float64"),
        **{c: pd.Series([0.0] * len(filas), dtype="float64") for c in CONTADORES}})
    esquema = pa.schema([("fecha", pa.timestamp("ms")), ("date", pa.string()), ("serial_number", pa.string()),
                         ("model", pa.string()), ("capacity_bytes", pa.int64()), ("failure", pa.int64()),
                         ("datacenter", pa.string()), ("smart_9_raw", pa.float64()),
                         *[(c, pa.float64()) for c in CONTADORES]])
    pq.write_table(pa.Table.from_pandas(df, schema=esquema, preserve_index=False),
                   carpeta / f"{fecha.strftime('%Y-%m')}.parquet")


def escribir_ventanas(ruta, filas):
    """Ventanas de fallo en bruto: (serial, día, día del fallo, modelo, capacidad, horas)."""
    df = pd.DataFrame(filas, columns=["serial_number", "date", "dia_fallo", "model", "capacity_bytes", "smart_9_raw"])
    df["fecha"] = pd.to_datetime(df["date"], format="%Y-%m-%d").astype("datetime64[ms]")
    df["dia_fallo"] = pd.to_datetime(df["dia_fallo"], format="%Y-%m-%d").astype("datetime64[ns]")
    df["failure"] = (df["fecha"] == df["dia_fallo"]).astype("int64")
    df["capacity_bytes"] = df["capacity_bytes"].astype("int64")
    df["smart_9_raw"] = df["smart_9_raw"].astype("float64")
    df["datacenter"] = "c1"
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), ruta)


def escribir_lista(ruta, filas):
    """La lista de fallos en bruto: serial_number y dia_fallo en nanosegundos, como data/raw/."""
    df = pd.DataFrame({"serial_number": [s for s, _ in filas],
                       "dia_fallo": pd.to_datetime([d for _, d in filas], format="%Y-%m-%d").astype("datetime64[ns]")})
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), ruta)


def escribir_recuento(ruta):
    """El recuento diario: los días de cada modelo y centro del mes, en una o dos filas; MB en c2 en agosto no tiene foto."""
    filas = [("2024-07-01", "MA OLD", C4, "c1", 40, 0), ("2024-07-20", "MA OLD", C4, "c1", 22, 0),
             ("2024-07-01", "MB", C8, None, 31, 0), ("2024-07-01", "MB", C8, "c1", 31, 0),
             ("2024-07-01", "BOOT", C_BOOT, "c1", 31, 0),
             ("2024-08-02", "MA", C4, "c1", 62, 0), ("2024-08-02", "MB", C8, "sin dato", 31, 0),
             ("2024-08-02", "MB", C8, "c1", 15, 1), ("2024-08-02", "MB", C8, "c2", 31, 0),
             ("2024-08-02", "BOOT", C_BOOT, "c1", 31, 0),
             ("2024-09-01", "MA", C4, "c1", 60, 0), ("2024-09-01", "MB", C8, "sin dato", 30, 0),
             ("2024-09-01", "BOOT", C_BOOT, "c1", 30, 0),
             ("2024-10-01", "MA", C4, "c1", 32, 1), ("2024-10-01", "MB", C8, "sin dato", 31, 0),
             ("2024-10-01", "MN", C8, "c1", 31, 0), ("2024-10-01", "BOOT", C_BOOT, "c1", 31, 0),
             ("2024-11-01", "MA", C4, "c1", 30, 0), ("2024-11-01", "MB", C8, "sin dato", 30, 0),
             ("2024-11-01", "MN", C8, "c1", 30, 0), ("2024-11-01", "BOOT", C_BOOT, "c1", 10, 1),
             ("2024-12-01", "MA", C4, "c1", 31, 0), ("2024-12-01", "MB", C8, "sin dato", 31, 0),
             ("2024-12-01", "MN", C8, "c1", 31, 0)]
    df = pd.DataFrame(filas, columns=["fecha", "model", "capacity_bytes", "datacenter", "discos", "fallos"])
    df["fecha"] = pd.to_datetime(df["fecha"], format="%Y-%m-%d").astype("datetime64[ms]")
    for c in ("capacity_bytes", "discos", "fallos"):
        df[c] = df[c].astype("int64")
    df["datacenter"] = df["datacenter"].astype(object)
    esquema = pa.schema([("fecha", pa.timestamp("ms")), ("model", pa.string()), ("capacity_bytes", pa.int64()),
                         ("datacenter", pa.string()), ("discos", pa.int64()), ("fallos", pa.int64())])
    pq.write_table(pa.Table.from_pandas(df, schema=esquema, preserve_index=False), ruta)


def montar_raw(base):
    """Los datos en bruto del caso pequeño en una carpeta (podado o reserva)."""
    (base / "fotos_mensuales").mkdir(parents=True)
    (base / "ventanas_fallo").mkdir(parents=True)
    # Junio, fuera del periodo: la historia de la foto de julio, como en los datos reales, que empiezan en 2020
    for k in range(-1, 6):
        escribir_foto(base / "fotos_mensuales", k)
    escribir_ventanas(base / "ventanas_fallo" / "data_Q1_2024.parquet",
                      [("OLD1", "2024-03-09", "2024-03-10", "MA", C4, 30000.0),
                       ("OLD1", "2024-03-10", "2024-03-10", "MA", C4, 30024.0)])
    escribir_ventanas(base / "ventanas_fallo" / "data_Q3_2024.parquet",
                      [("S1", "2024-08-13", "2024-08-15", "MB", C8, None), ("S1", "2024-08-14", "2024-08-15", "MB", C8, None),
                       ("S1", "2024-08-15", "2024-08-15", "MB", C8, None),
                       ("A2", "2024-09-29", "2024-10-01", "MA", C4, 2.2 * HORAS_ANO + 3 * MES - 48),
                       ("A2", "2024-09-30", "2024-10-01", "MA", C4, 2.2 * HORAS_ANO + 3 * MES - 24)])
    escribir_ventanas(base / "ventanas_fallo" / "data_Q4_2024.parquet",
                      [("A2", "2024-10-01", "2024-10-01", "MA", C4, 2.2 * HORAS_ANO + 3 * MES),
                       ("BT", "2024-11-09", "2024-11-10", "BOOT", C_BOOT, 1000.0),
                       ("BT", "2024-11-10", "2024-11-10", "BOOT", C_BOOT, 1024.0)])
    escribir_lista(base / "fallos.parquet", [("OLD1", "2024-03-10"), ("S1", "2024-08-15"), ("A2", "2024-10-01"),
                                             ("BT", "2024-11-10")])
    escribir_recuento(base / "recuento_diario.parquet")


# ---------------------------------------------------------------------------------------------------------------
# 3. Las tablas del análisis de juguete, calculadas a mano
# ---------------------------------------------------------------------------------------------------------------
# dias_por_tramo: (modelo, centro, mes, año de edad, fotos, días, fallos). Enero de 2024 es la historia anterior al
# periodo; los seis meses salen de repartir el recuento entre las fotos (MA en c1, 62 días entre dos fotos en julio).
DPT = [("MA", "c1", "2024-01", 1, 10, 60000.0, 3), ("MA", "c1", "2024-01", 2, 10, 60000.0, 6),
       ("MB", "sin dato", "2024-01", 0, 10, 70000.0, 7),
       ("MA", "c1", "2024-07", 1, 1, 31.0, 0), ("MA", "c1", "2024-07", 2, 1, 31.0, 0),
       ("MB", "sin dato", "2024-07", 0, 1, 31.0, 0), ("MB", "c1", "2024-07", 0, 1, 31.0, 0),
       ("MA", "c1", "2024-08", 1, 1, 31.0, 0), ("MA", "c1", "2024-08", 2, 1, 31.0, 0),
       ("MB", "sin dato", "2024-08", 0, 1, 31.0, 0), ("MB", "c1", "2024-08", 0, 1, 15.0, 1),
       ("MA", "c1", "2024-09", 1, 1, 30.0, 0), ("MA", "c1", "2024-09", 2, 1, 30.0, 0),
       ("MB", "sin dato", "2024-09", 0, 1, 30.0, 0),
       ("MA", "c1", "2024-10", 1, 1, 16.0, 0), ("MA", "c1", "2024-10", 2, 1, 16.0, 1),
       ("MB", "sin dato", "2024-10", 0, 1, 31.0, 0), ("MN", "c1", "2024-10", 0, 1, 31.0, 0),
       ("MA", "c1", "2024-11", 1, 1, 30.0, 0), ("MB", "sin dato", "2024-11", 0, 1, 30.0, 0),
       ("MN", "c1", "2024-11", 0, 1, 30.0, 0),
       ("MA", "c1", "2024-12", 1, 1, 31.0, 0), ("MB", "sin dato", "2024-12", 0, 1, 31.0, 0),
       ("MN", "c1", "2024-12", 0, 1, 31.0, 0)]
# inicio_trimestre: (año, trimestre, modelo, año de edad, capacidad, discos); A2 cuenta en octubre, el día de su fallo
INICIO = [(2024, 3, "MA", 1, 4.0, 1), (2024, 3, "MA", 2, 4.0, 1), (2024, 3, "MB", 0, 8.0, 2),
          (2024, 4, "MA", 1, 4.0, 1), (2024, 4, "MA", 2, 4.0, 1), (2024, 4, "MB", 0, 8.0, 1), (2024, 4, "MN", 0, 8.0, 1)]
# La previsión, a mano. 2024T3: solo enero; MA (1) 3 fallos y MA (2) 6 en 60.000 días; MB (0), 7 en 70.000.
# 2024T4: enero más julio a septiembre: MA (1) y MA (2) con 60.092 días; MB (0) con 70.138 días y 8 fallos (S1); el
# fallo de A2 del 01/10 no entra. MN no tiene días propios y toma la tasa de 8 TB y edad 0, la de MB.
PREVISTO = {("2024T3", 4.0): 92 * 3 / 60000 + 92 * 6 / 60000, ("2024T3", 8.0): 2 * 92 * 7 / 70000,
            ("2024T4", 4.0): 92 * 3 / 60092 + 92 * 6 / 60092, ("2024T4", 8.0): 92 * 8 / 70138 + 92 * 8 / 70138}
REAL = {("2024T3", 4.0): 0, ("2024T3", 8.0): 1, ("2024T4", 4.0): 1, ("2024T4", 8.0): 0}
REFERENCIA = {("2024T3", 4.0): 1, ("2024T3", 8.0): 0, ("2024T4", 4.0): 0, ("2024T4", 8.0): 1}


def par(t, k, previsto, real, ref):
    """Un par de B9 con las columnas del JSON del script 10."""
    return {"trimestre": t, "capacidad_tb": k, "previsto": previsto, "real": real, "referencia": ref,
            "previsto_entre_real": previsto / real if real else None, "horas_tecnico": previsto * 0.74}


def pares_b9(cambio=None):
    """Los pares de 2024T2 (la referencia de 2024T3; el de 12 TB sin fallos no tiene que entrar) y de los dos trimestres."""
    pares = [par("2024T2", 4.0, 1.0, 1, 0), par("2024T2", 12.0, 0.5, 0, 0)]
    pares += [par(t, k, PREVISTO[(t, k)], REAL[(t, k)], REFERENCIA[(t, k)]) for (t, k) in sorted(PREVISTO)]
    if cambio:
        for p in pares:
            if (p["trimestre"], p["capacidad_tb"]) == cambio[0]:
                p[cambio[1]] = cambio[2]
    return pares


def escribir_b9(pares):
    """informes/indicadores__coste_prevision.json de juguete, solo con lo que lee el script."""
    js = {"fecha_datos": "2025-06-30", "resultado": {"estado": "AVISO"},
          "preguntas": [{"id": "B4", "tablas": {}}, {"id": "B9", "tablas": {"pares": pares}}]}
    (TMP / "informes" / "indicadores__coste_prevision.json").write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")


def montar_analisis():
    """Las tablas del análisis de juguete y los pares de B9."""
    proc = TMP / "data" / "processed"
    proc.mkdir(parents=True)
    d = pd.DataFrame(DPT, columns=["model", "centro", "mes", "edad_anos_cumplidos", "fotos", "dias_disco", "fallos"])
    d["mes"] = pd.to_datetime(d["mes"], format="%Y-%m").astype("datetime64[us]")
    d["desaparecen_avisando"] = 0
    d.to_parquet(proc / "dias_por_tramo.parquet", index=False)
    i = pd.DataFrame(INICIO, columns=["ano", "trimestre", "model", "edad_anos_cumplidos", "capacidad_tb", "discos"])
    i["fecha"] = [pd.Timestamp(a, 3 * t - 2, 1) for a, t in zip(i["ano"], i["trimestre"])]
    i["fecha"] = i["fecha"].astype("datetime64[ms]")
    i["dias_trimestre"] = 92
    i[["ano", "trimestre", "model", "edad_anos_cumplidos", "fecha", "capacidad_tb", "discos", "dias_trimestre"]].to_parquet(
        proc / "inicio_trimestre.parquet", index=False)
    pd.DataFrame({"model": ["MA", "MB", "MN", "BOOT"], "capacidad_tb": [4.0, 8.0, 8.0, 0.3],
                  "tipo_disco": ["datos", "datos", "datos", "arranque"]}).to_parquet(proc / "dim_modelo.parquet", index=False)
    (TMP / "informes").mkdir(parents=True)
    escribir_b9(pares_b9())


def escribir_configuracion(carpetas):
    """produccion/configuracion.json de juguete: la historia en las carpetas que se pasan."""
    conf = {"historia_fotos": [f"{c}/fotos_mensuales" for c in carpetas],
            "historia_ventanas": [f"{c}/ventanas_fallo" for c in carpetas],
            "decisiones_correccion": "contexto-proyecto/modelo/decisiones-correccion.json"}
    (TMP / "produccion" / "configuracion.json").write_text(json.dumps(conf), encoding="utf-8")


def montar():
    """El caso pequeño entero; la reserva de juguete es una copia de los mismos datos en bruto."""
    if TMP.exists():
        shutil.rmtree(TMP)
    montar_raw(POD)
    montar_raw(RES)
    (TMP / "contexto-proyecto" / "modelo").mkdir(parents=True)
    (TMP / "contexto-proyecto" / "modelo" / "decisiones-correccion.json").write_text(json.dumps(
        {"modelos": {"mapeo": {"MA OLD": "MA"}}, "capacidad": {"minimo_valido_bytes": 200_000_000_000}}), encoding="utf-8")
    (TMP / "produccion").mkdir(parents=True)
    escribir_configuracion(["data/raw/podado", "data/raw/reserva"])
    montar_analisis()


def periodos_de_prueba(M):
    """Los periodos de los dos modos, cambiados para el caso pequeño; lo demás, como en el script."""
    M.MODOS["ensayo"].update({"desde": "2024-07", "hasta": "2024-12", "fin": "2024-12-31"})
    M.MODOS["reserva"].update({"desde": "2024-07", "hasta": "2024-12", "fin": "2024-12-31"})


def leer(ruta):
    """Un JSON del caso pequeño, o None si no existe."""
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def huella_carpeta(carpeta):
    """Huella de cada fichero de una carpeta, por ruta."""
    return {p.relative_to(carpeta).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(carpeta.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------------------------------------------
# 4. Casos
# ---------------------------------------------------------------------------------------------------------------
def funcion(texto, nombre):
    """El texto de una función de primer nivel, de su def a la línea que empieza fuera de ella."""
    m = re.search(rf"^def {nombre}\(.*?(?=^\S|\Z)", texto, flags=re.S | re.M)
    return m.group(0).rstrip() if m else None


def casos_de_argumentos():
    """Caso 1: sin modo o con los dos, el script no arranca."""
    for args in ([], ["--ensayo-validacion", "--reserva"]):
        r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP), *args], capture_output=True,
                           text=True, encoding="utf-8")
        comprobar(r.returncode != 0 and "usage" in (r.stderr or "").lower(), f"1. con {args or 'ningún modo'}, el script no arranca")


def casos_de_copias():
    """Caso 2: las funciones copiadas del script 10, letra a letra, y la comparación en rojo con una copia cambiada."""
    t20, t10 = SCRIPT.read_text(encoding="utf-8"), SCRIPT_10.read_text(encoding="utf-8")
    for nombre in COPIADAS:
        a, b = funcion(t20, nombre), funcion(t10, nombre)
        comprobar(a is not None and a == b, f"2. {nombre} es la del script 10, letra a letra")
        comprobar(f"# Origen: scripts/10_indicadores_coste_prevision.py, {nombre}" in t20, f"2. {nombre} lleva su origen")
    cambiada = funcion(t20, "error_ponderado").replace("abs(p - x)", "(p - x)")
    comprobar(cambiada != funcion(t10, "error_ponderado"), "2. rojo: una copia cambiada no es la del script 10")


def casos_de_comprobaciones(M):
    """Caso 3: cada comprobación sale en rojo con su caso."""
    inicio = pd.Timestamp("2024-10-01")
    comprobar(M.comp_sin_futuro([pd.Timestamp("2024-09-01")], [inicio]), "3. sin futuro: el último mes antes del trimestre pasa")
    comprobar(not M.comp_sin_futuro([pd.Timestamp("2024-10-01")], [inicio]), "3. rojo: un mes del trimestre en la historia")
    pares = [{"trimestre": "T1", "previsto": 1.5, "real": 2, "referencia": 1},
             {"trimestre": "T2", "previsto": 0.5, "real": 1, "referencia": 3}]
    total, por_t = M.resumen_error(pares), M.resumen_error(pares, "trimestre")
    comprobar(M.comp_totales(total, por_t), "3. los totales son la suma de los trimestres")
    comprobar(not M.comp_totales({**total, "real": 4}, por_t), "3. rojo: un total que no es la suma de los trimestres")
    comprobar(M.comp_cuadre([10.0, 5.0], [10.0, 5.0]), "3. los días repartidos suman los del recuento")
    comprobar(not M.comp_cuadre([10.0, 5.0], [10.0, 6.0]), "3. rojo: unos días repartidos que no suman los del recuento")
    comprobar(not M.comp_cuadre([3], [4]), "3. rojo: unos fallos que no suman los de la lista")
    comprobar(M.comp_huellas({"a": "1"}, {"a": "1"}) and not M.comp_huellas({"a": "1"}, {"a": "2"}),
              "3. rojo: la huella de data/raw/ que cambia")
    escrito = '"igual" + ": ' + "Tr" + 'ue"'
    comprobar(M.sin_resultados_escritos(SCRIPT.read_text(encoding="utf-8")), "3. el script no lleva ninguna validación escrita")
    comprobar(not M.sin_resultados_escritos('v = {"igual_al_analisis": ' + "Tr" + "ue}"),
              f"3. rojo: una validación con su resultado escrito ({escrito})")
    una = [{"tipo": "foto", "serial_number": "X", "fecha": "2024-07-01"}]
    comprobar(M.admitidas_ok(una) and M.admitidas_ok([]), "3. una diferencia admitida pasa")
    comprobar(not M.admitidas_ok(una * 2), "3. rojo: dos diferencias admitidas")
    comprobar(not M.admitidas_ok([{"tipo": "fallo", "serial_number": "X", "fecha": "2024-07-01"}]),
              "3. rojo: un fallo con la edad distinta no es una diferencia admitida")


def pares_de(js):
    """{(trimestre, capacidad): par} de un JSON del script."""
    return {(p["trimestre"], float(p["capacidad_tb"])): p for p in js["pares"]}


def casos_del_ensayo(M):
    """Casos 4 y 5: --reserva sin ensayo y el ensayo con las tablas de juguete."""
    codigo = M.principal(TMP, "reserva")
    j = leer(TMP / "informes" / "prueba_final_prevision.json")
    comprobar(codigo == 1 and j is not None and j["resultado"]["estado"] == "ERROR" and "ensayo" in j["resultado"]["resumen"],
              "4. --reserva sin el ensayo en OK: ERROR")
    (TMP / "informes" / "prueba_final_prevision.json").unlink()

    antes = huella_carpeta(TMP / "data" / "raw")
    t0 = time.time()
    codigo = M.principal(TMP, "ensayo")
    duracion = time.time() - t0
    j = leer(TMP / "informes" / "prueba_final_prevision_ensayo.json")
    comprobar(duracion < 150, f"5. el ensayo del caso pequeño tarda menos de 150 s ({duracion:.1f} s)")
    comprobar(codigo == 0 and j["resultado"]["estado"] == "OK", f"5. el ensayo con sus tablas: OK ({j['resultado']['resumen'][:300]})")
    if "traza" in j:
        print(j["traza"])
    comprobar(all(v is True for v in j["validaciones"].values()) and len(j["validaciones"]) >= 7,
              f"5. todas las validaciones del ensayo en verde: {j['validaciones']}")
    ini = {q["trimestre"]: q for q in j["piezas"]["inicio"]}
    comprobar(ini["2024T3"]["filas"] == 3 and ini["2024T3"]["discos"] == 4 and ini["2024T3"]["dias_trimestre"] == 92,
              "5. inicio de 2024T3: 3 filas y 4 discos (sin el de arranque), 92 días")
    comprobar(ini["2024T4"]["filas"] == 4 and ini["2024T4"]["discos"] == 4,
              "5. inicio de 2024T4: 4 filas y 4 discos (A2, el día de su fallo, dentro; el modelo nuevo, también)")
    meses = {m["mes"]: m for m in j["piezas"]["meses"]}
    comprobar(sum(m["dias_disco"] for m in meses.values()) == sum(x[5] for x in DPT if x[2] >= "2024-07"),
              "5. los días de disco de los seis meses son los de la tabla de juguete")
    comprobar(meses["2024-08-01"]["celdas_sin_foto"] == 1 and meses["2024-08-01"]["dias_sin_foto"] == 31,
              "5. la celda del recuento sin foto (MB en c2, agosto) se cuenta aparte con sus 31 días")
    comprobar(sum(m["celdas_sin_foto"] for m in meses.values()) == 1, "5. los días del modelo de arranque no cuentan como celda sin foto")
    comprobar(meses["2024-08-01"]["fallos"] == 1 and meses["2024-10-01"]["fallos"] == 1 and meses["2024-11-01"]["fallos"] == 0,
              "5. fallos de discos de datos: S1 en agosto, A2 en octubre; el de arranque de noviembre no")
    comprobar(meses["2024-11-01"]["fallos_fuera"].get("de_arranque") == 1, "5. el fallo de arranque se cuenta aparte")
    comprobar(meses["2024-08-01"]["fallos_sin_horas"] == 1, "5. el fallo sin horas toma la edad de su primera aparición")
    tramo = pd.DataFrame(j["piezas"]["historia_rehecha"])
    s1 = tramo.loc[(tramo["model"] == "MB") & (tramo["mes"] == "2024-08-01")]
    comprobar(len(s1) == 1 and int(s1["edad_anos_cumplidos"].iloc[0]) == 0 and int(s1["fallos"].iloc[0]) == 1,
              "5. S1 falla con edad 0, de los 45 días desde su primera foto")
    t4 = {n["trimestre"]: n for n in j["niveles"]}
    comprobar(t4["2024T4"]["capacidad"] == 1 and t4["2024T4"]["modelo"] == 3,
              "5. el modelo nuevo sin tasa propia pasa al nivel de capacidad")
    comprobar(t4["2024T4"]["ultimo_mes_usado"] == "2024-09-01", "5. la historia de 2024T4 acaba en septiembre (el fallo del 01/10 no entra)")
    p = pares_de(j)
    comprobar(set(p) == set(PREVISTO), f"5. los pares son los cuatro calculados a mano (sin el de 12 TB sin fallos): {sorted(p)}")
    comprobar(all(cerca(p[k]["previsto"], PREVISTO[k]) and p[k]["real"] == REAL[k] and p[k]["referencia"] == REFERENCIA[k]
                  for k in PREVISTO if k in p), "5. previsto, real y referencia de cada par, los calculados a mano")
    comprobar(j["comparacion"]["iguales"] is True and not j["comparacion"]["distintos"], "5. el ensayo es igual a las tablas de juguete")
    comprobar(j["diferencias_admitidas"] == [], "5. sin diferencias admitidas en el caso pequeño")
    comprobar(huella_carpeta(TMP / "data" / "raw") == antes, "5. data/raw/ sin cambios tras el ensayo")
    return j


def casos_de_la_reserva(M, ensayo):
    """Casos 6 y 7: el año guardado de juguete, una vez y después PARADO."""
    escribir_configuracion(["data/raw/reserva"])
    antes = huella_carpeta(TMP / "data" / "raw")
    codigo = M.principal(TMP, "reserva")
    j = leer(TMP / "informes" / "prueba_final_prevision.json")
    md_ruta = TMP / "informes" / "prueba_final_prevision.md"
    comprobar(codigo == 0 and j["resultado"]["estado"] in ("OK", "AVISO"), f"6. --reserva: {j['resultado']['resumen'][:300]}")
    comprobar(all(v is True for v in j["validaciones"].values()), f"6. todas las validaciones del año guardado en verde: {j['validaciones']}")
    p, pe = pares_de(j), pares_de(ensayo)
    comprobar(set(p) == set(pe) and all(cerca(p[k]["previsto"], pe[k]["previsto"]) and p[k]["real"] == pe[k]["real"]
                                        and p[k]["referencia"] == pe[k]["referencia"] for k in p),
              "6. los pares del año guardado de juguete son los del ensayo (mismos datos)")
    tot = j["total"]
    comprobar(cerca(tot["previsto"], sum(PREVISTO.values())) and tot["real"] == 2 and tot["referencia"] == 2,
              "6. el total previsto, real y de referencia es la suma de los pares")
    gana = j["gana_la_cuenta"]
    esperado = sum(abs(PREVISTO[k] - REAL[k]) for k in PREVISTO) / 2 < sum(abs(REFERENCIA[k] - REAL[k]) for k in PREVISTO) / 2
    comprobar(gana is esperado and gana is True, "6. gana la cuenta en el caso pequeño, calculado a mano")
    md = md_ruta.read_text(encoding="utf-8") if md_ruta.exists() else ""
    primera = next((x for x in md.splitlines()[1:] if x.strip()), "")
    comprobar(primera.startswith("La cuenta por modelo y edad gana"), f"6. la primera frase del informe dice si gana: {primera[:120]}")
    comprobar("—" not in md and "–" not in md, "6. el informe no lleva rayas")
    comprobar(all(s in md for s in ("## Lo que lo sostiene", "## Cada trimestre y capacidad", "## Límites",
                                     "## Lo que se puede hacer ya")), "6. el informe trae sus cuatro apartados")
    print("--- informe del caso pequeño ---\n" + md + "--- fin del informe ---")
    comprobar(huella_carpeta(TMP / "data" / "raw") == antes, "6. data/raw/ sin cambios tras el año guardado")

    sello = {r: (TMP / "informes" / r).read_bytes() for r in ("prueba_final_prevision.json", "prueba_final_prevision.md")}
    codigo = M.principal(TMP, "reserva")
    comprobar(codigo == 2 and all((TMP / "informes" / r).read_bytes() == b for r, b in sello.items()),
              "7. --reserva por segunda vez: PARADO, sin tocar lo medido")


def casos_de_pares_cambiados(M):
    """Caso 8: unos pares de juguete con una cifra distinta paran el ensayo, y dice cuál."""
    escribir_configuracion(["data/raw/podado", "data/raw/reserva"])
    escribir_b9(pares_b9((("2024T3", 8.0), "real", 2)))
    codigo = M.principal(TMP, "ensayo")
    j = leer(TMP / "informes" / "prueba_final_prevision_ensayo.json")
    comprobar(codigo == 1 and j["resultado"]["estado"] == "ERROR" and "2024T3" in j["resultado"]["resumen"],
              f"8. rojo: un par distinto para el ensayo y dice cuál ({j['resultado']['resumen'][:200]})")
    escribir_b9(pares_b9((("2024T4", 4.0), "previsto", PREVISTO[("2024T4", 4.0)] + 1e-3)))
    codigo = M.principal(TMP, "ensayo")
    j = leer(TMP / "informes" / "prueba_final_prevision_ensayo.json")
    comprobar(codigo == 1 and "previsto" in j["resultado"]["resumen"], "8. rojo: un previsto que difiere en una milésima")


def casos_del_modelo_a_mitad_de_trimestre(M):
    """Caso 9 (R68-145): un modelo nuevo que entra a mitad de trimestre sale en las fotos de un mes, pero no en la del
    primer día ni entre los fallos; su capacidad sale de esas fotos. En el año guardado real, ST12000NM002H paró el
    script con «modelos de la historia sin capacidad»."""
    dm = pd.DataFrame({"model": ["MA"], "capacidad_tb": [4.0], "tipo_disco": ["datos"]})
    inicio = pd.DataFrame({"model": ["MA"], "capacidad_tb": [4.0]})
    fallos = pd.DataFrame({"model": pd.Series([], dtype=object), "capacidad_tb": pd.Series([], dtype=float)})
    capacidades = pd.DataFrame({"model": ["MA", "MX"], "capacidad_tb": [4.0, 12.0]})
    mapa = M.mapa_de_capacidad(dm, {"inicio": inicio, "fallos": fallos, "capacidades": capacidades})
    comprobar(mapa.get("MX") == 12.0, f"9. el modelo que solo sale en las fotos de un mes toma su capacidad de ellas ({mapa})")
    try:
        M.mapa_de_capacidad(dm, {"inicio": inicio, "fallos": fallos,
                                 "capacidades": pd.DataFrame({"model": ["MX", "MX"], "capacidad_tb": [12.0, 16.0]})})
        comprobar(False, "9. rojo: un modelo con dos capacidades en las fotos de los meses tiene que parar")
    except M.Parada:
        comprobar(True, "9. rojo: un modelo con dos capacidades en las fotos de los meses para")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"sys.executable: {sys.executable}")
    t_inicio = time.time()
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe {SCRIPT.relative_to(CASO).as_posix()}")
        else:
            montar()
            M = cargar("prueba_final_prevision", SCRIPT)
            periodos_de_prueba(M)
            casos_de_argumentos()
            casos_de_copias()
            casos_de_comprobaciones(M)
            ensayo = casos_del_ensayo(M)
            casos_de_la_reserva(M, ensayo)
            casos_de_pares_cambiados(M)
            casos_del_modelo_a_mitad_de_trimestre(M)
    except Exception as e:  # noqa: BLE001 - un fallo inesperado también es un caso que falla
        import traceback
        traceback.print_exc()
        comprobar(False, f"sin excepciones ({type(e).__name__}: {e})")
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"{time.time() - t_inicio:.1f} s")
    print(f"{len(FALLOS)} casos fallan" if FALLOS else "todos los casos pasan")
    sys.exit(1 if FALLOS else 0)
