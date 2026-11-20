"""Prueba de scripts/06_analisis_exploratorio.py.

Parte 1: monta en tests/tmp_exploratorio/ un caso pequeño con las nueve tablas de la transformación escritas aquí
(fotos_riesgo con un bloque por mes, de enero de 2023 a septiembre de 2024: dieciocho meses de construcción y tres de
validación), con su informes/transformacion-datos.json (huellas, grupos de columnas y partición) y unas reglas de
negocio cortas. Ejecuta el script con -W error y comprueba los casos que pide la petición, cada uno con un caso que tiene
que salir mal (una copia del JSON estropeada a propósito, o un trozo de código que lee la tabla entera):
  - una foto de validación que entra en un cálculo con falla_30d, salvo los totales, hace fallar la prueba
    (el modelo ZZ_VAL solo sale en la validación, siempre con objetivo 1);
  - una columna de «no_previstas» cruzada con el objetivo la hace fallar (smart_9_raw separa el objetivo del todo);
  - una categoría con menos de 30 fotos no se compara (la capacidad de 22 TB tiene 10 fotos de construcción);
  - una columna de sitio antes del 2023-07-01 no entra en el cruce (el centro «zz_antes» solo sale antes);
  - el script no carga fotos_riesgo entera (se mira en el código);
  - y un control que no debe disparar: la capacidad de 20 TB, con 30 fotos justas, sí se compara, y los totales de la
    validación por fabricante sí se dan.
Además: la variable que separa el objetivo del todo sale como posible fuga y la que no, no; las cifras por año de
modelo_trimestre y los discos del primer día de cada trimestre; los quince apartados del informe en su orden; las
dieciocho comprobaciones con estado; fecha_datos; JSON sin NaN; las huellas de la entrada iguales al acabar; y una
huella que no coincide con la de la transformación deja el JSON en PARADO.
Parte 2: si ya existen los JSON reales del exploratorio, compara sus cifras con los controles de la petición
(peticiones/10_exploratorio.md, «Controles»).

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "06_analisis_exploratorio.py"
TMP = CASO / "tests" / "tmp_exploratorio"
FALLOS = []
TABLAS = ["fotos_riesgo", "fallos_detalle", "vida_discos", "dias_por_tramo", "modelo_trimestre", "centro_mes"]
TODAS = ["dim_modelo", "dim_precio_gb", "fotos_riesgo", "fallos_detalle", "vida_discos", "dias_por_tramo",
         "inicio_trimestre", "modelo_trimestre", "centro_mes"]
APARTADOS = ["Resumen ejecutivo", "Contexto", "Visión general", "Variables numéricas", "Variables categóricas",
             "Análisis temporal", "Frente al objetivo", "Hallazgos principales", "Alertas y limitaciones",
             "Hipótesis y preguntas abiertas", "Observaciones de la persona", "Comprobaciones aplicadas",
             "Parámetros usados", "Datos personales", "Siguiente paso"]
HASTA_CONSTRUCCION = pd.Timestamp("2024-06-30")
INICIO_SITIO = pd.Timestamp("2023-07-01")
MESES = pd.date_range("2023-01-01", "2024-09-01", freq="MS")

# Grupos de columnas de fotos_riesgo del caso pequeño (la forma de grupos_fotos_riesgo de la transformación)
GRUPOS = {
    "identificacion_y_fecha": ["serial_number", "fecha"],
    "del_modelo": ["model", "capacity_bytes", "capacidad_tb", "fabricante", "garantia_anos"],
    "conocidas_el_dia_de_la_foto": ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw",
                                    "smart_198_raw", "edad_anos", "edad_de_horas", "avisa", "contadores_que_avisan",
                                    "suma_contadores_sin_188", "smart_188_no_cero", "cambio_smart_5",
                                    "meses_desde_foto_anterior"],
    "no_previstas": ["smart_9_raw", "smart_9_normalized"],
    "sitio": ["datacenter", "vault_id", "pod_id", "pod_slot_num"],
    "particion": ["periodo"],
    "objetivo": ["horizonte_hasta", "falla_30d"],
}
# Modelos: fabricante, capacidad en TB, garantía y tipo
MODELOS = {
    "ST4000DM000": ("Seagate", 4.0, 2, "datos"),
    "HGST HUH721212ALE600": ("HGST", 12.0, 5, "datos"),
    "WDC WUH722222ALE6L4": ("WDC", 22.0, 5, "datos"),
    "TOSHIBA MG10ACA20TE": ("Toshiba", 20.0, 5, "datos"),
    "ZZ_VAL": ("Seagate", 16.0, 5, "datos"),
    "Seagate SSD": (None, 0.3, None, "arranque"),
}


def comprobar(nombre, condicion, detalle=""):
    """Apunta un caso que falla, con su nombre y lo que se vio."""
    if not condicion:
        FALLOS.append(f"{nombre}: {detalle}")
        print(f"FALLA  {nombre}  {detalle}")
    else:
        print(f"pasa   {nombre}")


def sha(ruta):
    """SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------------------------
# 2. Datos pequeños escritos en la prueba
# ---------------------------------------------------------------------------------------------------------------
def filas_fotos():
    """Fotos de riesgo: una fila por disco y mes, con el objetivo y lo demás pensado para cada caso de la prueba."""
    filas = []
    for k, mes in enumerate(MESES):
        construccion = mes <= HASTA_CONSTRUCCION
        con_sitio = mes >= INICIO_SITIO
        discos = []
        # 30 discos Seagate de 4 TB y 30 HGST de 12 TB todos los meses
        discos += [("S%02d" % i, "ST4000DM000") for i in range(30)]
        discos += [("H%02d" % i, "HGST HUH721212ALE600") for i in range(30)]
        # 22 TB: un disco los diez primeros meses (10 fotos de construcción, menos de 30)
        if k < 10:
            discos.append(("W00", "WDC WUH722222ALE6L4"))
        # 20 TB: dos discos los quince primeros meses (30 fotos de construcción justas)
        if k < 15:
            discos += [("T00", "TOSHIBA MG10ACA20TE"), ("T01", "TOSHIBA MG10ACA20TE")]
        # ZZ_VAL: solo en la validación, cinco discos con objetivo 1
        if not construccion:
            discos += [("Z%02d" % i, "ZZ_VAL") for i in range(5)]
        for serie, modelo in discos:
            fab, cap, gar, _ = MODELOS[modelo]
            i = int(serie[1:])
            if modelo == "ZZ_VAL":
                falla = 1
            elif modelo == "ST4000DM000":
                falla = int((i + k) % 10 == 0)          # uno de cada diez Seagate cada mes
            elif modelo == "HGST HUH721212ALE600":
                falla = int((i + k) % 30 == 0)          # uno de cada treinta HGST cada mes
            else:
                falla = 0
            seagate = fab == "Seagate"
            # El centro: «zz_antes» o vacío antes de julio de 2023; sac0 o phx1 desde julio
            if con_sitio:
                dc = "sac0" if i % 2 == 0 else "phx1"
                vault, pod, ranura = 1000 + i % 3, i % 20, i % 4
            else:
                dc = "zz_antes" if i % 3 == 0 else None
                vault, pod, ranura = None, None, None
            filas.append({
                "serial_number": serie, "fecha": mes, "model": modelo,
                "capacity_bytes": int(cap * 1e12), "capacidad_tb": cap, "fabricante": fab, "garantia_anos": gar,
                "smart_5_raw": 0.0, "smart_187_raw": 0.0 if seagate else None,
                "smart_188_raw": 0.0 if seagate else None, "smart_197_raw": 0.0, "smart_198_raw": 0.0,
                "edad_anos": 1.0 + ((i * 7 + k) % 13) / 4.0,
                "edad_de_horas": True, "avisa": bool(falla), "contadores_que_avisan": int(falla),
                # suma_contadores_sin_188 separa el objetivo del todo: es la posible fuga del caso pequeño
                "suma_contadores_sin_188": falla * (5.0 + i * 0.37 + k * 0.013),
                "smart_188_no_cero": 0.0 if seagate else None,
                "cambio_smart_5": float((i + k) % 5) - 2.0 if k > 0 else None,
                "meses_desde_foto_anterior": 1 if k > 0 else None,
                # smart_9_raw es «no prevista» y también separa el objetivo: no se puede cruzar
                "smart_9_raw": 1000.0 * falla + i, "smart_9_normalized": 100.0,
                "datacenter": dc, "vault_id": vault, "pod_id": pod, "pod_slot_num": ranura,
                "periodo": "construcción" if construccion else "validación",
                "horizonte_hasta": min(mes + pd.Timedelta(days=30),
                                       HASTA_CONSTRUCCION if construccion else pd.Timestamp("2025-06-30")),
                "falla_30d": falla,
            })
    return pd.DataFrame(filas)


ESQUEMA_FOTOS = pa.schema([
    ("serial_number", pa.string()), ("fecha", pa.timestamp("ms")), ("model", pa.string()),
    ("capacity_bytes", pa.int64()), ("capacidad_tb", pa.float64()), ("fabricante", pa.string()),
    ("garantia_anos", pa.int64()), ("smart_5_raw", pa.float64()), ("smart_187_raw", pa.float64()),
    ("smart_188_raw", pa.float64()), ("smart_197_raw", pa.float64()), ("smart_198_raw", pa.float64()),
    ("edad_anos", pa.float64()), ("edad_de_horas", pa.bool_()), ("avisa", pa.bool_()),
    ("contadores_que_avisan", pa.int64()), ("suma_contadores_sin_188", pa.float64()),
    ("smart_188_no_cero", pa.float64()), ("cambio_smart_5", pa.float64()), ("meses_desde_foto_anterior", pa.int64()),
    ("smart_9_raw", pa.float64()), ("smart_9_normalized", pa.float64()), ("datacenter", pa.string()),
    ("vault_id", pa.int64()), ("pod_id", pa.int64()), ("pod_slot_num", pa.int64()), ("periodo", pa.string()),
    ("horizonte_hasta", pa.timestamp("ms")), ("falla_30d", pa.int8())])


def escribir_fotos(df, ruta):
    """Escribe fotos_riesgo con un bloque por mes, como la tabla de la transformación."""
    with pq.ParquetWriter(ruta, ESQUEMA_FOTOS) as w:
        for mes in MESES:
            parte = df.loc[df["fecha"] == mes]
            w.write_table(pa.Table.from_pandas(parte, schema=ESQUEMA_FOTOS, preserve_index=False))


def tabla_dim_modelo():
    """dim_modelo: una fila por modelo."""
    filas = []
    for m, (fab, cap, gar, tipo) in MODELOS.items():
        filas.append({"model": m, "capacity_bytes": int(cap * 1e12), "capacidad_tb": cap, "tipo_disco": tipo,
                      "fabricante": fab, "garantia_anos": gar,
                      "fecha_compra": pd.Timestamp("2021-03-01") if tipo == "datos" else pd.NaT,
                      "coste_gb_compra": 0.015 if tipo == "datos" else None,
                      "precio_usd": 0.015 * cap * 1000 if tipo == "datos" else None,
                      "origen_precio": ("inferido" if cap >= 20 else "curva") if tipo == "datos" else None})
    return pd.DataFrame(filas)


def tabla_dim_precio():
    """dim_precio_gb: una fila por capacidad y año."""
    filas = [{"capacidad_tb": c, "ano": a, "coste_gb": 0.02 - 0.002 * (a - 2020), "origen": "curva",
              "capacidades_usadas": str(c)} for c in (4.0, 12.0, 16.0, 20.0, 22.0) for a in range(2020, 2026)]
    return pd.DataFrame(filas)


def tabla_fallos():
    """fallos_detalle: 24 fallos de discos de datos y 2 de arranque, de 2023 a 2025."""
    filas = []
    dias = pd.date_range("2023-01-15", "2025-06-15", periods=24)
    for j, d in enumerate(dias):
        modelo = ["ST4000DM000", "HGST HUH721212ALE600", "TOSHIBA MG10ACA20TE"][j % 3]
        fab, cap, gar, tipo = MODELOS[modelo]
        sitio = d >= INICIO_SITIO
        filas.append({
            "serial_number": f"F{j:02d}", "dia_fallo": d, "model": modelo, "capacidad_tb": cap, "fabricante": fab,
            "tipo_disco": tipo, "garantia_anos": gar, "horas_al_fallar": 20000.0 + 1000 * j,
            "edad_al_fallar_anos": (20000.0 + 1000 * j) / 8766, "edad_de_horas": True,
            "en_garantia": (20000.0 + 1000 * j) / 8766 < gar, "hay_dia_anterior": j % 6 != 0,
            "avisa_dia_anterior": None if j % 6 == 0 else bool(j % 2), "sin_aviso": None if j % 6 == 0 else not bool(j % 2),
            "datacenter": ("sac0" if j % 2 else "phx1") if sitio else None, "vault_id": 1000 if sitio else None,
            "pod_id": j % 20 if sitio else None, "pod_slot_num": j % 4 if sitio else None,
            "tomo": f"sac0-1000-{j % 4}" if sitio else None, "plazo_reconstruccion_dias": cap + 1,
            "dias_desde_anterior_del_tomo": 30 + j if sitio and j % 4 else None,
            "coincide_con_anterior": False if sitio and j % 4 else None,
            "precio_nuevo_usd": 0.015 * cap * 1000, "coste_fallo_usd": 0.015 * cap * 1000 + 37,
            "coste_fallo_garantia_usd": 37.0 if (20000.0 + 1000 * j) / 8766 < gar else 0.015 * cap * 1000 + 37,
            "ultima_foto_anterior": d.to_period("M").to_timestamp(), "objetivo_de_alguna_foto": j % 5 != 0,
            "periodo": "construcción" if d <= HASTA_CONSTRUCCION else "validación",
            "ano": d.year, "trimestre": d.quarter, "mes": d.month, "primer_fallo_del_disco": True})
    for j in range(2):
        d = pd.Timestamp("2024-02-10") + pd.Timedelta(days=j)
        filas.append({**filas[0], "serial_number": f"B{j}", "dia_fallo": d, "model": "Seagate SSD",
                      "capacidad_tb": 0.3, "fabricante": None, "tipo_disco": "arranque", "garantia_anos": None,
                      "en_garantia": False, "ano": 2024, "trimestre": 1, "mes": 2, "periodo": "construcción"})
    return pd.DataFrame(filas)


def tabla_vida():
    """vida_discos: un disco por fila, con su evento."""
    filas = []
    for j in range(80):
        modelo = ["ST4000DM000", "HGST HUH721212ALE600", "TOSHIBA MG10ACA20TE", "WDC WUH722222ALE6L4"][j % 4]
        entra = pd.Timestamp("2023-01-01") + pd.DateOffset(months=j % 12)
        evento = ["sigue", "fallo", "desaparece", "sigue"][j % 4]
        fin = pd.Timestamp("2025-06-01") if evento == "sigue" else entra + pd.DateOffset(months=6)
        filas.append({"serial_number": f"V{j:02d}", "model": modelo, "primera_aparicion": entra,
                      "edad_entrada_anos": (j % 9) / 2.0, "ultima_foto": fin if evento != "fallo" else entra,
                      "primer_fallo": fin if evento == "fallo" else pd.NaT, "evento": evento, "fecha_fin": fin,
                      "edad_fin_anos": (j % 9) / 2.0 + 0.5, "avisa_ultima_foto": j % 5 == 0,
                      "desaparece_avisando": evento == "desaparece" and j % 5 == 0})
    return pd.DataFrame(filas)


def tabla_dias_tramo():
    """dias_por_tramo: modelo, centro, mes y año de edad, con sus días y fallos."""
    filas = []
    for mes in pd.date_range("2023-01-01", "2025-06-01", freq="MS"):
        for modelo in ("ST4000DM000", "HGST HUH721212ALE600"):
            for edad in (1, 3, 5):
                centro = ("sac0" if edad != 3 else "phx1") if mes >= INICIO_SITIO else "sin dato"
                filas.append({"model": modelo, "centro": centro, "mes": mes, "edad_anos_cumplidos": edad,
                              "fotos": 10 * edad, "dias_disco": 300.0 * edad * (2 if modelo[0] == "H" else 1),
                              "fallos": int((mes.month + edad) % 4 == 0), "desaparecen_avisando": int(edad == 5)})
    filas.append({"model": "ST4000DM000", "centro": "sac0", "mes": pd.Timestamp("2024-03-01"),
                  "edad_anos_cumplidos": 7, "fotos": 0, "dias_disco": None, "fallos": 1, "desaparecen_avisando": 0})
    return pd.DataFrame(filas)


def tabla_modelo_trimestre():
    """modelo_trimestre: un modelo de datos por trimestre, de 2023 a junio de 2025."""
    filas = []
    for ano in (2023, 2024, 2025):
        for t in (1, 2, 3, 4):
            if ano == 2025 and t > 2:
                continue
            for m in ("ST4000DM000", "HGST HUH721212ALE600", "TOSHIBA MG10ACA20TE"):
                fab, cap, gar, _ = MODELOS[m]
                dias = 90_000 + 1000 * t + (ano - 2023) * 5000 + (30_000 if m[0] == "H" else 0)
                fallos = (t + ano) % 4 + (2 if m[0] == "S" else 0)
                filas.append({"model": m, "ano": ano, "trimestre": t, "capacidad_tb": cap, "fabricante": fab,
                              "fecha_compra": pd.Timestamp("2021-03-01"), "precio_usd": 0.015 * cap * 1000,
                              "origen_precio": "inferido" if cap >= 20 else "curva", "dias_disco": dias,
                              "fallos": fallos, "fallos_en_garantia": fallos // 2,
                              "coste_fallos_usd": fallos * (0.015 * cap * 1000 + 37.0),
                              "coste_fallos_garantia_usd": (fallos // 2) * 37.0 + (fallos - fallos // 2) * (
                                  0.015 * cap * 1000 + 37.0),
                              "dias_disco_ano": 0, "pasa_minimo_ano": True})
    df = pd.DataFrame(filas)
    df["dias_disco_ano"] = df.groupby(["model", "ano"])["dias_disco"].transform("sum")
    df["pasa_minimo_ano"] = df["dias_disco_ano"] >= 50_000
    return df


def tabla_inicio_trimestre():
    """inicio_trimestre: los discos del primer día de cada trimestre, por modelo y año de edad."""
    filas = []
    for ano in (2023, 2024, 2025):
        for t in (1, 2, 3, 4):
            if ano == 2025 and t > 2:
                continue
            for m in ("ST4000DM000", "HGST HUH721212ALE600"):
                for edad in (1, 4):
                    filas.append({"ano": ano, "trimestre": t, "model": m, "edad_anos_cumplidos": edad,
                                  "fecha": pd.Timestamp(year=ano, month=3 * t - 2, day=1),
                                  "capacidad_tb": MODELOS[m][1], "discos": 100 * t + edad + (ano - 2023),
                                  "dias_trimestre": 91})
    return pd.DataFrame(filas)


def tabla_centro_mes():
    """centro_mes: un centro por mes; «sin dato» antes de julio de 2023."""
    filas = []
    for mes in pd.date_range("2023-01-01", "2025-06-01", freq="MS"):
        centros = ["sac0", "phx1", "sin dato"] if mes >= INICIO_SITIO else ["sin dato"]
        for c in centros:
            filas.append({"datacenter": c, "mes": mes, "dias_disco": 60_000 if c != "sin dato" else 90_000,
                          "fallos": (mes.month % 3) + (2 if c == "sac0" else 0),
                          "periodo": "construcción" if mes <= HASTA_CONSTRUCCION else "validación",
                          "con_sitio": bool(mes >= INICIO_SITIO)})
    return pd.DataFrame(filas)


def tipos_reales(tabla):
    """Los tipos de pandas de la tabla real, leídos solo del esquema del Parquet (sin cargar datos); {} si no está."""
    ruta = CASO / "data" / "processed" / f"{tabla}.parquet"
    if not ruta.exists():
        return {}
    meta = pq.read_schema(ruta).pandas_metadata or {}
    return {c["name"]: c["numpy_type"] for c in meta.get("columns", []) if c.get("name")}


def con_tipos_reales(tabla, df):
    """La tabla pequeña con los mismos tipos que la real (boolean, Int64, str...): así sale el error de los vacíos."""
    tipos = tipos_reales(tabla)
    faltan = [c for c in df.columns if tipos and c not in tipos]
    if faltan:
        raise ValueError(f"{tabla}: la tabla pequeña tiene columnas que la real no tiene: {faltan}")
    out = df.copy()
    for c, t in tipos.items():
        if c in out.columns and t != "object":
            out[c] = out[c].astype(t)
    return out


def montar(huella_mala=False):
    """Monta el caso pequeño en TMP y devuelve las fotos."""
    if TMP.exists():
        shutil.rmtree(TMP)
    proc = TMP / "data" / "processed"
    proc.mkdir(parents=True)
    (TMP / "informes").mkdir()
    (TMP / "config" / "negocio").mkdir(parents=True)
    fotos = filas_fotos()
    escribir_fotos(fotos, proc / "fotos_riesgo.parquet")
    pequenas = {"dim_modelo": tabla_dim_modelo(), "dim_precio_gb": tabla_dim_precio(), "fallos_detalle": tabla_fallos(),
                "vida_discos": tabla_vida(), "dias_por_tramo": tabla_dias_tramo(),
                "inicio_trimestre": tabla_inicio_trimestre(), "modelo_trimestre": tabla_modelo_trimestre(),
                "centro_mes": tabla_centro_mes()}
    for nombre, df in pequenas.items():
        con_tipos_reales(nombre, df).to_parquet(proc / f"{nombre}.parquet", index=False)
    salidas = []
    for t in TODAS:
        ruta = proc / f"{t}.parquet"
        md = pq.ParquetFile(ruta).metadata
        salidas.append({"tabla": t, "ruta": f"data/processed/{t}.parquet", "sha256": sha(ruta),
                        "filas": md.num_rows, "columnas": md.num_columns, "que_es_una_fila": f"una fila de {t}"})
    if huella_mala:
        salidas[3]["sha256"] = "0" * 64
    tj = {"metodo": "transformacion-datos", "fecha_datos": "2025-06-30",
          "resultado": {"estado": "OK", "riesgo": "bajo"}, "salidas": salidas, "grupos_fotos_riesgo": GRUPOS,
          "particion": {"columna_fecha": "fecha", "desarrollo": {"desde": "2023-01-01", "hasta": "2024-06-30"},
                        "validacion": {"desde": "2024-07-01", "hasta": "2025-06-30"}, "fuente": "reglas-negocio §7"},
          "parametros": {"inicio_sitio": "2023-07-01", "minimo_dias_ano": 50000}}
    (TMP / "informes" / "transformacion-datos.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    (TMP / "config" / "negocio" / "reglas-negocio.md").write_text(
        "# Reglas de prueba\n\n## 7. Criterios\n\nSin tabla de rangos.\n", encoding="utf-8")
    return fotos


def ejecutar():
    """Ejecuta el script sobre el caso pequeño con -W error."""
    return subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)],
                          capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})


def sin_nan(texto):
    """Lee un JSON y para si trae NaN o Infinity."""
    def no(c):
        raise ValueError(f"constante no válida en el JSON: {c}")
    return json.loads(texto, parse_constant=no)


def leer_json(tabla):
    """El JSON del exploratorio de una tabla en el caso pequeño, o None."""
    ruta = TMP / "informes" / f"analisis-exploratorio__{tabla}.json"
    return sin_nan(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


# ---------------------------------------------------------------------------------------------------------------
# 3. Los comprobadores: cada uno devuelve la lista de problemas que encuentra en un JSON
# ---------------------------------------------------------------------------------------------------------------
def variables_cruzadas(js):
    """Todas las variables cruzadas con el objetivo, también las del sitio."""
    fo = js.get("frente_al_objetivo") or {}
    return list(fo.get("variables", [])) + list((fo.get("sitio") or {}).get("variables", []))


def problemas_validacion(js, fotos):
    """Una foto de validación en un cálculo con falla_30d, salvo los totales."""
    p = []
    fo = js.get("frente_al_objetivo") or {}
    cons = fotos.loc[fotos["periodo"] == "construcción"]
    if fo.get("filas_usadas") != "construcción":
        p.append(f"filas_usadas = {fo.get('filas_usadas')}")
    if fo.get("n_filas") != len(cons) or fo.get("n_objetivo_1") != int(cons["falla_30d"].sum()):
        p.append(f"n_filas {fo.get('n_filas')} / {len(cons)}; objetivo 1 {fo.get('n_objetivo_1')} / "
                 f"{int(cons['falla_30d'].sum())}")
    for v in variables_cruzadas(js):
        for c in v.get("categorias", []):
            if str(c.get("valor")) == "ZZ_VAL" or str(c.get("valor")) == "16.0":
                p.append(f"la categoría {c.get('valor')} de {v.get('columna')}, que solo sale en la validación")
    esperado = cons.groupby("fabricante")["falla_30d"].agg(["size", "sum"])
    fab = next((v for v in fo.get("variables", []) if v.get("columna") == "fabricante"), None)
    if fab is None:
        p.append("falta fabricante frente al objetivo")
    else:
        for c in fab.get("categorias", []):
            if c["valor"] in esperado.index and (c["filas"] != int(esperado.loc[c["valor"], "size"])
                                                 or c["fallan"] != int(esperado.loc[c["valor"], "sum"])):
                p.append(f"fabricante {c['valor']}: {c['filas']}/{c['fallan']} frente a "
                         f"{int(esperado.loc[c['valor'], 'size'])}/{int(esperado.loc[c['valor'], 'sum'])}")
    for f in (js.get("cifras_para_siguiente") or {}).get("construccion_por_mes_y_fabricante", []):
        if pd.Timestamp(f["mes"]) > HASTA_CONSTRUCCION:
            p.append(f"el mes {f['mes']} de la validación en las fotos por mes con objetivo")
    return p


def problemas_no_previstas(js):
    """Una columna de «no_previstas» cruzada con el objetivo, o sin su llenado."""
    p = [f"{v['columna']} cruzada con el objetivo" for v in variables_cruzadas(js)
         if v.get("columna") in GRUPOS["no_previstas"]]
    llenas = {x["columna"] for x in (js.get("llenado") or {}).get("no_previstas", [])}
    p += [f"falta el llenado de {c}" for c in GRUPOS["no_previstas"] if c not in llenas]
    return p


def categoria(js, columna, valor):
    """La categoría `valor` de la variable `columna` frente al objetivo, o None."""
    for v in variables_cruzadas(js):
        if v.get("columna") == columna:
            for c in v.get("categorias", []):
                if str(c.get("valor")) == str(valor):
                    return c
    return None


def problemas_pocas_filas(js):
    """Una categoría con menos de 30 fotos que se compara."""
    p = []
    for v in variables_cruzadas(js):
        for c in v.get("categorias", []):
            if c.get("filas", 0) < 30 and (c.get("comparada") or c.get("parte_pct") is not None):
                p.append(f"{v['columna']} = {c['valor']}, con {c['filas']} fotos, se compara")
    return p


def problemas_sitio(js, fotos):
    """Una columna de sitio antes del 2023-07-01 que entra en el cruce."""
    p = []
    sitio = (js.get("frente_al_objetivo") or {}).get("sitio") or {}
    esperado = int(((fotos["periodo"] == "construcción") & (fotos["fecha"] >= INICIO_SITIO)).sum())
    if sitio.get("n_filas") != esperado:
        p.append(f"el sitio se cruza con {sitio.get('n_filas')} fotos y desde julio de 2023 son {esperado}")
    if sitio.get("desde") != "2023-07-01":
        p.append(f"el sitio dice desde {sitio.get('desde')}")
    for v in sitio.get("variables", []):
        for c in v.get("categorias", []):
            if c.get("valor") == "zz_antes":
                p.append("el centro zz_antes, que solo sale antes de julio de 2023, entra en el cruce")
    return p


def problemas_codigo(codigo):
    """El script lee fotos_riesgo entera, o no la lee bloque a bloque."""
    p = []
    if "read_row_group" not in codigo:
        p.append("no usa read_row_group")
    if re.search(r"(read_table|read_parquet)\([^)]*(FOTOS|fotos_riesgo)", codigo):
        p.append("lee fotos_riesgo entera con read_table o read_parquet")
    if re.search(r"ParquetFile\([^)]*\)\.read\(", codigo):
        p.append("lee fotos_riesgo entera con ParquetFile(...).read()")
    return p


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 1: el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def parte_1():
    """Ejecuta el script sobre el caso pequeño y comprueba cada caso, con su copia estropeada que tiene que fallar."""
    comprobar("existe el script", SCRIPT.exists(), str(SCRIPT))
    if not SCRIPT.exists():
        return
    fotos = montar()
    huellas_antes = {t: sha(TMP / "data" / "processed" / f"{t}.parquet") for t in TODAS}
    p = ejecutar()
    comprobar("el script acaba sin error con -W error", p.returncode == 0, p.stderr[-2500:])
    huellas_despues = {t: sha(TMP / "data" / "processed" / f"{t}.parquet") for t in TODAS}
    comprobar("las huellas de las nueve tablas no cambian", huellas_antes == huellas_despues)
    js = {}
    for t in TABLAS:
        for ext in ("json", "html"):
            comprobar(f"deja analisis-exploratorio__{t}.{ext}",
                      (TMP / "informes" / f"analisis-exploratorio__{t}.{ext}").exists())
        try:
            js[t] = leer_json(t)
        except ValueError as e:
            comprobar(f"{t}: JSON sin NaN ni Infinity", False, str(e))
            js[t] = None
    if any(v is None for v in js.values()):
        return
    fr = js["fotos_riesgo"]

    # Bloque común en los seis
    for t, j in js.items():
        comprobar(f"{t}: fecha_datos 2025-06-30", j.get("fecha_datos") == "2025-06-30", j.get("fecha_datos"))
        comprobar(f"{t}: estado OK o AVISO", j["resultado"]["estado"] in ("OK", "AVISO"), j["resultado"])
        comprobar(f"{t}: dieciocho comprobaciones con estado",
                  len(j.get("comprobaciones", [])) == 18 and all(
                      c["estado"] in ("aplicada_con_resultado", "aplicada_sin_nada_relevante", "no_aplica")
                      for c in j.get("comprobaciones", [])), j.get("comprobaciones"))
        c18 = next((c for c in j.get("comprobaciones", []) if str(c.get("comprobacion", "")).startswith("18")), {})
        comprobar(f"{t}: la comprobación 18 no aplica", c18.get("estado") == "no_aplica", c18)
        comprobar(f"{t}: observaciones vacías", j.get("observaciones") == [], j.get("observaciones"))
        versiones = j.get("versiones", {})
        comprobar(f"{t}: versiones de las cinco librerías",
                  all(versiones.get(k) for k in ("python", "pandas", "numpy", "pyarrow", "matplotlib")), versiones)
        comprobar(f"{t}: huellas antes y después iguales",
                  all(h["antes"] == h["despues"] for h in j.get("huellas", [])) and len(j.get("huellas", [])) == 9)
        html = (TMP / "informes" / f"analisis-exploratorio__{t}.html").read_text(encoding="utf-8")
        posiciones = [html.find(f"<h2>{a}</h2>") for a in APARTADOS]
        comprobar(f"{t}: los quince apartados en su orden", all(x >= 0 for x in posiciones)
                  and posiciones == sorted(posiciones), list(zip(APARTADOS, posiciones)))
        comprobar(f"{t}: el siguiente paso del JSON está en el informe",
                  j.get("siguiente_paso") in ("con_esto_basta", "hace_falta_modelar", "volver_a_limpiar",
                                              "falta_un_dato"), j.get("siguiente_paso"))

    # Caso 1: la validación no se cruza con el objetivo, salvo los totales
    p1 = problemas_validacion(fr, fotos)
    comprobar("caso 1: ninguna foto de validación en un cálculo con el objetivo", not p1, p1)
    malo = copy.deepcopy(fr)
    malo["frente_al_objetivo"]["variables"][0]["categorias"].append(
        {"valor": "ZZ_VAL", "filas": 15, "fallan": 15, "parte_pct": 100.0, "comparada": False})
    comprobar("caso 1 en rojo: con ZZ_VAL en el cruce, el comprobador lo ve", bool(problemas_validacion(malo, fotos)))
    malo = copy.deepcopy(fr)
    malo["cifras_para_siguiente"]["construccion_por_mes_y_fabricante"].append(
        {"mes": "2024-07-01", "fabricante": "Seagate", "fotos": 35, "fallan": 8})
    comprobar("caso 1 en rojo: con un mes de validación en las fotos por mes, el comprobador lo ve",
              bool(problemas_validacion(malo, fotos)))
    # Control que no debe disparar: los totales de la validación por fabricante sí se dan
    val = fotos.loc[fotos["periodo"] == "validación"]
    tot = (fr.get("frente_al_objetivo") or {}).get("validacion") or {}
    comprobar("control: totales de la validación", tot.get("filas") == len(val)
              and tot.get("fallan") == int(val["falla_30d"].sum()), tot)
    por_fab = {x["fabricante"]: (x["filas"], x["fallan"]) for x in tot.get("por_fabricante", [])}
    esperado = {f: (int(g["falla_30d"].size), int(g["falla_30d"].sum())) for f, g in val.groupby("fabricante")}
    comprobar("control: totales de la validación por fabricante", por_fab == esperado, (por_fab, esperado))
    comprobar("control: el comprobador no dispara con los totales de la validación",
              not problemas_validacion(fr, fotos))

    # Caso 2: ninguna columna «no_previstas» cruzada con el objetivo; su llenado sí se da
    p2 = problemas_no_previstas(fr)
    comprobar("caso 2: ninguna no prevista cruzada con el objetivo", not p2, p2)
    malo = copy.deepcopy(fr)
    malo["frente_al_objetivo"]["variables"].append({"columna": "smart_9_raw", "categorias": []})
    comprobar("caso 2 en rojo: con smart_9_raw cruzada, el comprobador lo ve", bool(problemas_no_previstas(malo)))
    ll = {x["columna"]: x for x in (fr.get("llenado") or {}).get("no_previstas", [])}
    comprobar("caso 2: llenado de smart_9_raw al 100 % en Seagate",
              ll.get("smart_9_raw", {}).get("por_fabricante", {}).get("Seagate") == 100.0, ll.get("smart_9_raw"))

    # Caso 3: una categoría con menos de 30 fotos no se compara; con 30 justas, sí
    p3 = problemas_pocas_filas(fr)
    comprobar("caso 3: ninguna categoría con menos de 30 fotos comparada", not p3, p3)
    c22 = categoria(fr, "capacidad_tb", 22.0)
    comprobar("caso 3: la capacidad de 22 TB dice sus 10 fotos y no se compara",
              c22 is not None and c22["filas"] == 10 and c22["comparada"] is False and c22["parte_pct"] is None, c22)
    malo = copy.deepcopy(fr)
    for v in malo["frente_al_objetivo"]["variables"]:
        for c in v.get("categorias", []):
            if v["columna"] == "capacidad_tb" and str(c["valor"]) == "22.0":
                c["comparada"], c["parte_pct"] = True, 0.0
    comprobar("caso 3 en rojo: con la de 22 TB comparada, el comprobador lo ve", bool(problemas_pocas_filas(malo)))
    c20 = categoria(fr, "capacidad_tb", 20.0)
    comprobar("control: la capacidad de 20 TB, con 30 fotos justas, sí se compara",
              c20 is not None and c20["filas"] == 30 and c20["comparada"] is True and c20["parte_pct"] == 0.0, c20)

    # Caso 4: el sitio solo desde el 2023-07-01
    p4 = problemas_sitio(fr, fotos)
    comprobar("caso 4: el sitio solo con las fotos desde julio de 2023", not p4, p4)
    malo = copy.deepcopy(fr)
    sv = malo["frente_al_objetivo"]["sitio"]["variables"]
    if sv:
        sv[0]["categorias"].append({"valor": "zz_antes", "filas": 40, "fallan": 2, "parte_pct": 5.0,
                                    "comparada": True})
    comprobar("caso 4 en rojo: con zz_antes en el cruce, el comprobador lo ve", bool(problemas_sitio(malo, fotos)))

    # Caso 5: fotos_riesgo no se carga entera
    codigo = SCRIPT.read_text(encoding="utf-8")
    p5 = problemas_codigo(codigo)
    comprobar("caso 5: fotos_riesgo se lee bloque a bloque", not p5, p5)
    comprobar("caso 5 en rojo: un código que la lee entera, el comprobador lo ve",
              bool(problemas_codigo("t = pq.read_table(FOTOS)\nx = pf.read_row_group(0)")))

    # La posible fuga, dicha; la variable que no separa, no
    vs = {v["columna"]: v for v in fr["frente_al_objetivo"]["variables"]}
    comprobar("posible fuga: suma_contadores_sin_188", vs.get("suma_contadores_sin_188", {}).get("posible_fuga") is True,
              vs.get("suma_contadores_sin_188"))
    comprobar("posible fuga: también en las alertas", any("suma_contadores_sin_188" in a["texto"] and "fuga" in a["texto"]
                                                           for a in fr.get("alertas", [])))
    comprobar("control: edad_anos no es posible fuga", vs.get("edad_anos", {}).get("posible_fuga") is False,
              vs.get("edad_anos"))
    comprobar("tamaño de la muestra dicho", (fr.get("muestra") or {}).get("tamano") == len(fotos), fr.get("muestra"))

    # Lo que espera el paso siguiente: modelo_trimestre por año y los discos del primer día de cada trimestre
    mt = tabla_modelo_trimestre()
    esperado = mt.groupby("ano").agg(dias=("dias_disco", "sum"), fallos=("fallos", "sum"),
                                     coste=("coste_fallos_usd", "sum"), coste_g=("coste_fallos_garantia_usd", "sum"))
    por_ano = {x["ano"]: x for x in (js["modelo_trimestre"].get("cifras_para_siguiente") or {}).get("por_ano", [])}
    for ano, fila in esperado.iterrows():
        x = por_ano.get(int(ano), {})
        tasa = 100 * 365 * fila["fallos"] / fila["dias"]
        ok = (x.get("dias_disco") == int(fila["dias"]) and x.get("fallos") == int(fila["fallos"])
              and x.get("tasa_anual_pct") is not None and math.isclose(x["tasa_anual_pct"], tasa, rel_tol=1e-6)
              and math.isclose(x.get("coste_fallos_usd", -1), fila["coste"], rel_tol=1e-9)
              and math.isclose(x.get("coste_fallos_garantia_usd", -1), fila["coste_g"], rel_tol=1e-9))
        comprobar(f"modelo_trimestre {ano}: días, fallos, tasa y costes", ok, x)
    comprobar("modelo_trimestre: 2025 marcado como año incompleto", por_ano.get(2025, {}).get("completo") is False,
              por_ano.get(2025))
    it = tabla_inicio_trimestre().groupby(["ano", "trimestre"])["discos"].sum()
    sale = {(x["ano"], x["trimestre"]): x["discos"]
            for x in (js["modelo_trimestre"].get("cifras_para_siguiente") or {}).get("inicio_trimestre", [])}
    comprobar("inicio_trimestre: discos del primer día de cada trimestre",
              sale == {k: int(v) for k, v in it.items()}, sale)

    # Las fotos con objetivo 1 por mes y fabricante en la construcción
    cons = fotos.loc[fotos["periodo"] == "construcción"]
    esp = cons.groupby([cons["fecha"].dt.strftime("%Y-%m-%d"), "fabricante"])["falla_30d"].agg(["size", "sum"])
    sale = {(x["mes"], x["fabricante"]): (x["fotos"], x["fallan"])
            for x in fr["cifras_para_siguiente"]["construccion_por_mes_y_fabricante"]}
    comprobar("fotos y fotos con objetivo 1 por mes y fabricante",
              sale == {k: (int(v["size"]), int(v["sum"])) for k, v in esp.iterrows()})


def parte_1_huella_mala():
    """Una huella que no coincide con la de la transformación deja el JSON en PARADO y sale con 1."""
    if not SCRIPT.exists():
        return
    montar(huella_mala=True)
    p = ejecutar()
    js = leer_json("fotos_riesgo")
    estado = None if js is None else js["resultado"]["estado"]
    comprobar("huella distinta: PARADO", estado == "PARADO", (estado, p.stderr[-800:]))
    comprobar("huella distinta: sale con 1", p.returncode == 1, p.returncode)


def parte_1_codigo():
    """Ninguna comprobación escrita con su resultado puesto y sin filterwarnings."""
    if not SCRIPT.exists():
        return
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestas = re.findall(r'"(?:iguales|coincide|pasa|ok|comparada|posible_fuga)"\s*:\s*(?:True|"pasa")\s*[,}]', codigo)
    comprobar("ninguna comprobación con su resultado escrito", not puestas, puestas)
    comprobar("sin filterwarnings", "filterwarnings" not in codigo)
    comprobar("semilla 42 en la configuración", re.search(r"^SEMILLA\s*=\s*42\b", codigo, re.M) is not None)


# ---------------------------------------------------------------------------------------------------------------
# 5. Parte 2: las cifras reales frente a los controles de la petición
# ---------------------------------------------------------------------------------------------------------------
CONTROL_POR_ANO = {2020: (51345918, 1307, 0.93, 250485.20, 80209.00), 2021: (66072034, 1823, 1.01, 352673.77, 109169.07),
                   2022: (78890669, 2999, 1.39, 565844.09, 200888.03), 2023: (90077756, 4201, 1.70, 755878.60, 284506.60),
                   2024: (103839696, 4538, 1.60, 832698.00, 305124.00), 2025: (55882610, 2128, 1.39, 366916.00, 170296.00)}
CONTROL_CONSTRUCCION = {"HGST": (2114301, 1566), "Seagate": (5653315, 8163), "Toshiba": (2407073, 1955),
                        "WDC": (851363, 278)}
CONTROL_VALIDACION = {"HGST": (387260, 992), "Seagate": (1279885, 1744), "Toshiba": (1148695, 1158),
                      "WDC": (762969, 410)}


def parte_2():
    """Si existen los JSON reales, compara sus cifras con los controles de la petición."""
    ruta_f = CASO / "informes" / "analisis-exploratorio__fotos_riesgo.json"
    ruta_m = CASO / "informes" / "analisis-exploratorio__modelo_trimestre.json"
    if not ruta_f.exists() or not ruta_m.exists():
        print("salta  parte 2: no existen los JSON reales del exploratorio")
        return
    # Solo valen los JSON que dejó el script actual: uno más viejo que el script es de otra versión (error 2)
    if min(ruta_f.stat().st_mtime, ruta_m.stat().st_mtime) < SCRIPT.stat().st_mtime:
        print("salta  parte 2: los JSON reales son anteriores al script actual; se comparan al volver a ejecutarlo")
        return
    fr = sin_nan(ruta_f.read_text(encoding="utf-8"))
    mt = sin_nan(ruta_m.read_text(encoding="utf-8"))
    estados = (fr["resultado"]["estado"], mt["resultado"]["estado"])
    comprobar("real: los JSON acabaron en OK o AVISO", all(x in ("OK", "AVISO") for x in estados),
              (estados, fr["resultado"].get("resumen")))
    if not all(x in ("OK", "AVISO") for x in estados):
        return
    fo = fr["frente_al_objetivo"]
    comprobar("real: construcción 11.026.052 fotos y 11.962 con objetivo 1",
              (fo["n_filas"], fo["n_objetivo_1"]) == (11026052, 11962), (fo["n_filas"], fo["n_objetivo_1"]))
    comprobar("real: validación 3.578.809 y 4.304",
              (fo["validacion"]["filas"], fo["validacion"]["fallan"]) == (3578809, 4304), fo["validacion"])
    fab = next(v for v in fo["variables"] if v["columna"] == "fabricante")
    sale = {c["valor"]: (c["filas"], c["fallan"]) for c in fab["categorias"]}
    comprobar("real: construcción por fabricante", sale == CONTROL_CONSTRUCCION, sale)
    sale = {x["fabricante"]: (x["filas"], x["fallan"]) for x in fo["validacion"]["por_fabricante"]}
    comprobar("real: validación por fabricante", sale == CONTROL_VALIDACION, sale)
    meses = fr["cifras_para_siguiente"]["construccion_por_mes"]
    comprobar("real: 54 meses de construcción", len(meses) == 54, len(meses))
    menor = min(meses, key=lambda x: x["fallan"])
    mayor = max(meses, key=lambda x: x["fallan"])
    comprobar("real: de 64 (2020-06) a 559 (2023-04)",
              (menor["fallan"], menor["mes"][:7], mayor["fallan"], mayor["mes"][:7]) == (64, "2020-06", 559, "2023-04"),
              (menor, mayor))
    llenos = {(x["columna"], x["fabricante"]): x["lleno_pct"]
              for x in fr["cifras_para_siguiente"]["contadores_llenos_construccion"]}
    for col in ("smart_5_raw", "smart_198_raw"):
        comprobar(f"real: {col} lleno al 100 % en los cuatro", all(round(llenos[(col, f)], 1) == 100.0
                                                                    for f in CONTROL_CONSTRUCCION))
    for col in ("smart_187_raw", "smart_188_raw"):
        comprobar(f"real: {col} solo en Seagate", all(round(llenos[(col, f)], 1) == (100.0 if f == "Seagate" else 0.0)
                                                      for f in CONTROL_CONSTRUCCION))
    comprobar("real: smart_197_raw en Toshiba 92,5 %", round(llenos[("smart_197_raw", "Toshiba")], 1) == 92.5,
              llenos[("smart_197_raw", "Toshiba")])
    comprobar("real: datacenter lleno en el 28,4 % de la construcción",
              round(fr["cifras_para_siguiente"]["datacenter_lleno_construccion_pct"], 1) == 28.4,
              fr["cifras_para_siguiente"]["datacenter_lleno_construccion_pct"])
    por_ano = {x["ano"]: x for x in mt["cifras_para_siguiente"]["por_ano"]}
    for ano, (dias, fallos, tasa, coste, coste_g) in CONTROL_POR_ANO.items():
        x = por_ano.get(ano, {})
        ok = (x.get("dias_disco") == dias and x.get("fallos") == fallos and round(x.get("tasa_anual_pct", -1), 2) == tasa
              and round(x.get("coste_fallos_usd", -1), 2) == coste
              and round(x.get("coste_fallos_garantia_usd", -1), 2) == coste_g)
        comprobar(f"real: modelo_trimestre {ano}", ok, x)


# ---------------------------------------------------------------------------------------------------------------
# 6. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print("sys.executable:", sys.executable)
    try:
        parte_1()
        parte_1_huella_mala()
        parte_1_codigo()
        parte_2()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\ntodos los casos pasan")
    sys.exit(1 if FALLOS else 0)
