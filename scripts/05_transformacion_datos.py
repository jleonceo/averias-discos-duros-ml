"""Transformación de los datos del caso 68 (método transformacion-datos).

Construye, con las reglas de config/negocio/reglas-transformacion.md (aprobadas por el responsable del caso el 17/11/2026), las
dos dimensiones y las siete tablas del análisis, cada una en su Parquet de data/processed/:

- dim_modelo y dim_precio_gb (§1);
- fotos_riesgo (§3), fallos_detalle (§4), vida_discos (§5), dias_por_tramo (§6), inicio_trimestre (§7),
  modelo_trimestre (§8) y centro_mes (§9);
- y el registro de exclusiones (§10), que va en el informe y no crea ningún dataset.

Parte de las cuatro tablas corregidas y del Calendario, que no se modifican. Solo cruza lo que está en el plan de
cruces aprobado (informes/modelado-datos.json), con merge(validate=..., indicator=True); si las filas crecen en un cruce
N:1 o 1:1, para. Las fotos se leen bloque a bloque (un bloque es un mes) y fotos_riesgo se escribe bloque a bloque.

Depende de scripts/03_correccion_datos.py y de scripts/04_modelado_datos.py: lee informes/correccion-datos.json (para si
falta, si está parado o si la huella de una tabla no es la de su salida) e informes/modelado-datos.json (para si el
diseño no está aprobado), y data/processed/calendario.parquet, que deja el script 04.

Deja informes/transformacion-datos.json y, generado de él, informes/transformacion-datos.md. Añade al registro de
transformaciones una ficha por transformación nueva, la primera vez que la aplica. Si una validación falla, no guarda
ninguna tabla y el JSON queda en PARADO.

Uso: python -W error scripts/05_transformacion_datos.py [--raiz CARPETA_DEL_CASO]
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import sys
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]

# =================================================================================================================
# 2. Configuración, copiada de las reglas (reglas-transformacion.md y reglas-negocio.md)
# =================================================================================================================
METODO = "transformacion-datos"
VERSION_METODO = "06/10/2026"
SCRIPT = "scripts/05_transformacion_datos.py"
PETICION = "peticiones/09_transformacion.md"
FECHA_DATOS = "2025-06-30"                       # reglas, apartado 5, fecha de referencia

FOTOS = "data/processed/fotos_mensuales_corregido.parquet"
VENTANAS = "data/processed/ventanas_fallo_corregido.parquet"
RECUENTO = "data/processed/recuento_diario_corregido.parquet"
LISTA_FALLOS = "data/processed/fallos_corregido.parquet"
CALENDARIO = "data/processed/calendario.parquet"
CORREGIDAS = {"fotos_mensuales": FOTOS, "ventanas_fallo": VENTANAS, "recuento_diario": RECUENTO, "fallos": LISTA_FALLOS}

HORAS_ANO = 8766.0                               # convención técnica 1: el año de edad son 8.766 horas
DIAS_ANO = 365.25                                # la edad sin horas: días desde la primera aparición entre 365,25
LIMITE_ARRANQUE_BYTES = 2_048_408_248_320        # reglas, apartado 3 y §7: arranque hasta aquí, datos por encima
INICIO_SITIO = pd.Timestamp("2023-07-01")        # reglas, apartado 4: el sitio solo consta desde ese día
HORIZONTE_DIAS = 30                              # reglas, apartado 7, cuestión 004
MINIMO_DIAS_ANO = 50_000                         # reglas, apartado 7, mínimo para entrar en un ranking
COSTE_CAMBIO_USD = 37.0                          # reglas, apartado 6, mano de obra de un cambio
SIN_DATO = "sin dato"                            # etiqueta del centro que no consta, la del recuento (R-009)
CONTADORES = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]   # reglas, apartado 3
CONTADORES_SIN_188 = ["smart_5_raw", "smart_187_raw", "smart_197_raw", "smart_198_raw"]          # cuestión 010
CANDIDATAS = ["smart_194_raw", "smart_199_raw", "smart_12_raw", "smart_192_raw", "smart_1_raw", "smart_7_raw"]
FUERA_DE_FOTOS_RIESGO = ["failure", "date", "cluster_id"]                                       # reglas, apartado 3
SITIO = ["datacenter", "vault_id", "pod_id", "pod_slot_num"]

# Fabricante: el nombre del modelo y las dos excepciones de las reglas, apartado 3
FABRICANTE_EXCEPCIONES = {"Hitachi HDS5C4040ALE630": "HGST", "WUH721816ALE6L4": "WDC"}
FABRICANTE_PREFIJOS = [("TOSHIBA", "Toshiba"), ("WDC", "WDC"), ("HGST", "HGST")]

# Precios de precios_de_coste_discos.md: el valor al empezar y al acabar cada año de compra, por capacidad en TB
CURVAS = {4: [(2012, 0.073, 0.050), (2013, 0.054, 0.042), (2014, 0.040, 0.036), (2015, 0.034, 0.031),
              (2016, 0.028, 0.023)],
          8: [(2016, 0.051, 0.030), (2017, 0.033, 0.025)],
          12: [(2017, 0.0245, 0.024), (2018, 0.024, 0.0225), (2019, 0.0225, 0.017), (2020, 0.0167, 0.0167)],
          14: [(2018, 0.024, 0.023), (2019, 0.022, 0.018), (2020, 0.0158, 0.0158), (2021, 0.0155, 0.015)],
          16: [(2021, 0.0162, 0.0157), (2022, 0.0157, 0.0145)]}
INFERIDO = [("2022-11-15", 0.0145), ("2023-07-01", 0.0132), ("2024-07-01", 0.0115), ("2025-07-01", 0.0100)]
INICIO_INFERIDO = pd.Timestamp(INFERIDO[0][0])
DIA_PRECIO_ANO = (7, 1)                          # dim_precio_gb: el coste el 1 de julio de cada año (§1)
SIN_PRECIO = ["WDC WD60EFRX", "ST6000DM001", "TOSHIBA HDWE160", "ST6000DM004"]   # reglas, apartado 6: los 6 TB sin precio

# Grupos de columnas de fotos_riesgo (reglas de transformación §3); «no previstas» son las demás smart_*
GRUPOS_FIJOS = {
    "identificacion_y_fecha": ["serial_number", "fecha"],
    "del_modelo": ["model", "capacity_bytes", "capacidad_tb", "fabricante", "garantia_anos"],
    "conocidas_el_dia_de_la_foto": CONTADORES + CANDIDATAS + [
        "edad_anos", "edad_de_horas", "avisa", "contadores_que_avisan", "suma_contadores_sin_188",
        "smart_188_no_cero", "cambio_smart_5", "cambio_smart_187", "cambio_smart_197", "cambio_smart_198",
        "meses_desde_foto_anterior"],
    "sitio": SITIO,
    "particion": ["periodo"],
    "objetivo": ["horizonte_hasta", "falla_30d"],
}
ORDEN_GRUPOS = ["identificacion_y_fecha", "del_modelo", "conocidas_el_dia_de_la_foto", "no_previstas", "sitio",
                "particion", "objetivo"]
PATRON_SMART = re.compile(r"^smart_\d+_(raw|normalized)$")

VALIDATE = {"1:1": "one_to_one", "N:1": "many_to_one"}

TEORIA = [
    "11.9, retardos: el cambio de un contador y los meses desde la foto anterior se calculan dentro de cada disco, "
    "con las fotos en orden de fecha; la foto anterior se guarda de un bloque al siguiente.",
    "13.9, primero y último de cada grupo: la primera aparición, la última foto y el último día de la ventana con "
    "sitio se toman de la fila real, ordenada por fecha, no con first(), que salta los vacíos.",
    "14.7, tiempo transcurrido: la edad, los días entre fallos del mismo tomo y los meses entre fotos se miden en "
    "unidades totales (horas entre 8.766, días entre 365,25), no con las partes de la fecha.",
    "12.6 y 11.14, cambiar el nivel: los días de disco y los fallos son flujos y se suman; cada agregación cuadra sus "
    "sumas antes y después, y las variables que usan información posterior quedan marcadas.",
    "Método, «Agregar por tiempo»: en un flujo, una celda sin registros vale cero solo si se sabe que no hubo nada; "
    "las filas de dias_por_tramo que solo tienen fallos dejan sus días de disco vacíos.",
]

QUE_ES_UNA_FILA = {
    "dim_modelo": "un modelo de disco",
    "dim_precio_gb": "una capacidad de datos en un año: lo que costaba el GB el 1 de julio",
    "fotos_riesgo": "un disco de datos en una foto mensual, sin la foto del día en que falla",
    "fallos_detalle": "un fallo de la lista: un disco el día que Backblaze lo da por fallado",
    "vida_discos": "un disco de datos que sale en alguna foto o en alguna ventana",
    "dias_por_tramo": "un modelo de datos, un centro, un mes y un año de edad cumplido",
    "inicio_trimestre": "un trimestre, un modelo de datos y un año de edad cumplido, el primer día del trimestre",
    "modelo_trimestre": "un modelo de datos en un trimestre",
    "centro_mes": "un centro de datos en un mes, solo discos de datos",
}
SALIDA = {t: f"data/processed/{t}.parquet" for t in QUE_ES_UNA_FILA}
CLAVES = {"dim_modelo": ["model"], "dim_precio_gb": ["capacidad_tb", "ano"],
          "fotos_riesgo": ["serial_number", "fecha"], "fallos_detalle": ["serial_number", "dia_fallo"],
          "vida_discos": ["serial_number"], "dias_por_tramo": ["model", "centro", "mes", "edad_anos_cumplidos"],
          "inicio_trimestre": ["ano", "trimestre", "model", "edad_anos_cumplidos"],
          "modelo_trimestre": ["model", "ano", "trimestre"], "centro_mes": ["datacenter", "mes"]}


class Parada(Exception):
    """Una regla para el script a propósito: el estado es PARADO y no se guarda ninguna tabla."""


# =================================================================================================================
# 3. Utilidades
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leída por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


def a_json(valor):
    """Pasa a tipos que JSON acepta: sin NaN ni infinitos, fechas en ISO y números como números."""
    if isinstance(valor, dict):
        return {str(k): a_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [a_json(v) for v in valor]
    if valor is None or valor is pd.NA or valor is pd.NaT:
        return None
    if isinstance(valor, (np.bool_, bool)):
        return bool(valor)
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        v = float(valor)
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return int(v) if v.is_integer() and abs(v) < 2**53 else round(v, 6)
    if isinstance(valor, pd.Timestamp):
        return valor.date().isoformat() if valor == valor.normalize() else valor.isoformat()
    if isinstance(valor, (dt.datetime, dt.date)):
        return valor.isoformat()
    return valor


def fmt(n, decimales=1):
    """Número con punto de miles y coma decimal, como se escribe en español."""
    if n is None:
        return "sin dato"
    if isinstance(n, float) and not n.is_integer():
        return f"{n:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{int(n):,}".replace(",", ".")


def dia(ts):
    """Fecha en ISO, AAAA-MM-DD."""
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).date().isoformat()


def inicio_de_mes(serie):
    """Primer día del mes de cada fecha, en milisegundos como las demás fechas."""
    return serie.dt.to_period("M").dt.start_time.astype("datetime64[ms]")


def a_milisegundos(serie, nombre):
    """Pasa una fecha de nanosegundos a milisegundos; para si se pierde algo (reglas de transformación, «Antes de cruzar»)."""
    ms = serie.astype("datetime64[ms]")
    if not (ms.astype("datetime64[ns]") == serie.astype("datetime64[ns]")).all():
        raise Parada(f"{nombre}: pasar de nanosegundos a milisegundos cambiaría alguna fecha")
    return ms


def nuevo_cruce(orden, etiqueta, partida, se_une, clave_partida, clave_une, tipo, plan):
    """Ficha vacía de un cruce, con los campos de un cruce de integracion-datos."""
    return {"orden": orden, "etiqueta": etiqueta, "partida": partida, "se_une": se_une,
            "clave_partida": clave_partida, "clave_une": clave_une, "tipo_cruce": tipo,
            "cardinalidad_esperada": None if plan is None else plan["cardinalidad"], "cardinalidad_observada": None,
            "repetidas_maestro": {"claves": 0, "filas": 0}, "claves_nulas": {"partida": 0, "se_une": 0},
            "huerfanas_partida": {"filas": 0}, "huerfanas_maestro": {"claves": 0}, "filas_antes": 0,
            "filas_despues": 0, "sumas_control": [], "veces": 0, "hecho": False, "motivo_parada": None}


def cruzar(ctx, orden, etiqueta, partida, se_une, izq, der, izq_on, der_on, how="left"):
    """Cruza dos tablas con un cruce del plan aprobado, validando su cardinalidad y marcando el origen de cada fila.

    Para si el cruce no está en el plan, si la clave del lado maestro no cumple la cardinalidad o si las filas crecen.
    Acumula los recuentos en ctx["cruces"] (los cruces que se hacen bloque a bloque suman sus filas).
    Devuelve la tabla cruzada con la columna _merge.
    """
    plan = ctx["plan"].get(orden)
    reg = ctx["cruces"].setdefault((orden, etiqueta), nuevo_cruce(orden, etiqueta, partida, se_une, izq_on, der_on,
                                                                   how, plan))
    if plan is None:
        reg["motivo_parada"] = "el cruce no está en el plan de cruces aprobado"
        raise Parada(f"el cruce {orden} ({etiqueta}) no está en el plan de cruces aprobado")
    repetidas = der.duplicated(der_on, keep=False)
    reg["repetidas_maestro"]["claves"] += int(der.loc[repetidas, der_on].drop_duplicates().shape[0])
    reg["repetidas_maestro"]["filas"] += int(repetidas.sum())
    reg["claves_nulas"]["partida"] += int(izq[izq_on].isna().any(axis=1).sum())
    reg["claves_nulas"]["se_une"] += int(der[der_on].isna().any(axis=1).sum())
    reg["veces"] += 1
    try:
        m = izq.merge(der, left_on=izq_on, right_on=der_on, how=how, validate=VALIDATE[plan["cardinalidad"]],
                      indicator=True, suffixes=("", "_der"))
    except pd.errors.MergeError as e:
        reg["motivo_parada"] = f"la clave no cumple la cardinalidad {plan['cardinalidad']}: {e}"
        raise Parada(f"el cruce {orden} ({etiqueta}) para: la clave no cumple la cardinalidad "
                     f"{plan['cardinalidad']} ({e})") from e
    solo_der = int((m["_merge"] == "right_only").sum())
    esperadas = len(izq) + (solo_der if how == "outer" else 0)
    reg["filas_antes"] += len(izq)
    reg["filas_despues"] += len(m)
    reg["huerfanas_partida"]["filas"] += int((m["_merge"] == "left_only").sum())
    reg["huerfanas_maestro"]["claves"] += solo_der if how == "outer" else int(
        len(der.drop_duplicates(der_on)) - m.loc[m["_merge"] == "both", izq_on].drop_duplicates().shape[0])
    izq_unica = not izq.duplicated(izq_on).any()
    reg["cardinalidad_observada"] = ("1:1" if izq_unica and not repetidas.any() else
                                     "N:1" if not repetidas.any() else "N:N")
    reg["hecho"] = len(m) == esperadas
    if not reg["hecho"]:
        reg["motivo_parada"] = f"las filas pasan de {len(izq)} a {len(m)}"
        raise Parada(f"el cruce {orden} ({etiqueta}) para: las filas pasan de {len(izq)} a {len(m)}")
    for c in der_on:
        if c not in izq_on and c in m.columns and c not in izq.columns:
            m = m.drop(columns=c)
    return m


def suma_de_control(ctx, orden, etiqueta, magnitud, antes, despues):
    """Apunta una suma de control de un cruce: la magnitud antes y después, y si coinciden."""
    ctx["cruces"][(orden, etiqueta)]["sumas_control"].append(
        {"magnitud": magnitud, "antes": float(antes), "despues": float(despues),
         "coincide": bool(np.isclose(antes, despues, rtol=0, atol=1e-6))})


# =================================================================================================================
# 4. Entradas: los JSON de las fases anteriores, el plan de cruces y las huellas
# =================================================================================================================
def leer_entradas(raiz, r):
    """Comprueba que se puede transformar (resultado.md, «Al empezar») y devuelve el plan de cruces por orden."""
    ruta_corr = raiz / "informes" / "correccion-datos.json"
    if not ruta_corr.exists():
        raise Parada("no existe informes/correccion-datos.json")
    corr = json.loads(ruta_corr.read_text(encoding="utf-8"))
    if corr["resultado"].get("estado") in ("PARADO", "ERROR"):
        raise Parada(f"la corrección está en {corr['resultado']['estado']}")
    salidas = {s["ruta"]: s for s in corr.get("salidas", [])}
    r["huellas_inicio"] = {}
    for tabla, ruta in CORREGIDAS.items():
        if ruta not in salidas:
            raise Parada(f"la corrección no trae la salida {ruta}")
        huella = sha256(raiz / ruta)
        r["huellas_inicio"][ruta] = huella
        if huella != salidas[ruta]["sha256"]:
            raise Parada(f"la huella de {ruta} no es la que dejó la corrección")
    ruta_mod = raiz / "informes" / "modelado-datos.json"
    if not ruta_mod.exists():
        raise Parada("no existe informes/modelado-datos.json")
    mod = json.loads(ruta_mod.read_text(encoding="utf-8"))
    if mod["resultado"].get("estado") in ("PARADO", "ERROR") or not mod.get("aprobado", {}).get("aprobado"):
        raise Parada("el diseño del modelo de datos no está aprobado o su JSON está parado")
    if not (raiz / CALENDARIO).exists():
        raise Parada("no existe data/processed/calendario.parquet")
    r["entradas"] = []
    for ruta in list(CORREGIDAS.values()) + [CALENDARIO]:
        md = pq.ParquetFile(raiz / ruta).metadata
        r["entradas"].append({"ruta": ruta, "sha256": r["huellas_inicio"].get(ruta) or sha256(raiz / ruta),
                              "filas": md.num_rows, "columnas": md.num_columns})
    return {int(p["orden"]): p for p in mod.get("plan_cruces", [])}


# =================================================================================================================
# 5. Las dos dimensiones (§1)
# =================================================================================================================
def puntos_curva(capacidad):
    """Puntos (fecha, dólares por GB) de la curva de una capacidad: el 1 de enero y el 31 de diciembre de cada año."""
    puntos = []
    for ano, inicio, final in CURVAS[capacidad]:
        puntos += [(pd.Timestamp(year=ano, month=1, day=1), inicio), (pd.Timestamp(year=ano, month=12, day=31), final)]
    return puntos


def en_recta(puntos, fecha):
    """Valor de una curva de puntos en una fecha, con rectas entre puntos."""
    x = np.array([p[0].value for p in puntos], dtype=float)
    return float(np.interp(pd.Timestamp(fecha).value, x, [p[1] for p in puntos]))


def tiene_curva(capacidad, fecha):
    """Si la capacidad tiene curva ese día."""
    if capacidad not in CURVAS:
        return False
    p = puntos_curva(capacidad)
    return p[0][0] <= fecha <= p[-1][0]


def coste_gb(capacidad, fecha):
    """Dólares por GB de una capacidad en una fecha, con su origen y las capacidades usadas (reglas, apartado 1 y §6).

    Desde el 15/11/2022, lo inferido; antes, la curva de su capacidad o, si no la tiene ese día, la media de las dos
    capacidades más cercanas que la tengan (convención técnica 2); con una sola, esa. Devuelve (valor, origen, usadas,
    motivo); valor None si ninguna regla lo llena.
    """
    fecha = pd.Timestamp(fecha)
    if fecha >= INICIO_INFERIDO:
        return en_recta([(pd.Timestamp(f), v) for f, v in INFERIDO], fecha), "inferido", [], None
    if tiene_curva(capacidad, fecha):
        return en_recta(puntos_curva(capacidad), fecha), "curva", [capacidad], None
    candidatas = sorted((abs(c - capacidad), c) for c in CURVAS if tiene_curva(c, fecha))
    if not candidatas:
        return None, None, [], f"ninguna capacidad tiene curva el {dia(fecha)}"
    if len(candidatas) >= 3 and candidatas[2][0] == candidatas[1][0] and candidatas[1][0] != candidatas[0][0]:
        return None, None, [], (f"la segunda capacidad más cercana a {capacidad} TB el {dia(fecha)} está empatada "
                                f"entre {candidatas[1][1]} y {candidatas[2][1]} TB")
    usadas = [c for _, c in candidatas[:2]]
    return float(np.mean([en_recta(puntos_curva(c), fecha) for c in usadas])), "vecinas", usadas, None


def capacidad_en_tb(capacity_bytes):
    """capacity_bytes entre 10^12, redondeada a un decimal hacia arriba en el medio, como Excel."""
    return float((Decimal(int(capacity_bytes)) / Decimal(10**12)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fabricante(modelo):
    """Fabricante por el nombre del modelo, con las dos excepciones de las reglas, apartado 3; None si no sigue ningún patrón."""
    if modelo in FABRICANTE_EXCEPCIONES:
        return FABRICANTE_EXCEPCIONES[modelo]
    if modelo.startswith("ST"):
        return "Seagate"
    for prefijo, nombre in FABRICANTE_PREFIJOS:
        if modelo.startswith(prefijo):
            return nombre
    return None


def garantia(modelo, fab):
    """Años de garantía por familia, en el orden de las reglas de transformación §1; None sin garantía comprobada."""
    if fab == "Seagate" and "NM" in modelo:
        return 5
    if fab == "Seagate" and "DM" in modelo:
        return 2
    if "HMS5C" in modelo:
        return 3
    if any(f in modelo for f in ("HUH", "HUS", "WUH")) or modelo.startswith("TOSHIBA MG"):
        return 5
    return None


def construir_dim_modelo(recuento, primeras, ctx):
    """dim_modelo: una fila por modelo del recuento, con su capacidad, tipo, fabricante, garantía, compra y precio."""
    dm = recuento[["model", "capacity_bytes"]].drop_duplicates().sort_values("model").reset_index(drop=True)
    if dm["model"].duplicated().any():
        raise Parada("dim_modelo: un modelo del recuento tiene más de una capacidad")
    dm["capacidad_tb"] = [capacidad_en_tb(c) for c in dm["capacity_bytes"]]
    dm["tipo_disco"] = np.select([dm["capacity_bytes"] <= LIMITE_ARRANQUE_BYTES,
                                  dm["capacity_bytes"] > LIMITE_ARRANQUE_BYTES], ["arranque", "datos"], "SIN_REGLA")
    dm["fabricante"] = [fabricante(m) for m in dm["model"]]
    datos = dm["tipo_disco"] == "datos"
    dm["garantia_anos"] = pd.array([garantia(m, f) if d else None
                                    for m, f, d in zip(dm["model"], dm["fabricante"], datos)], dtype="Int64")
    # Fecha de compra: la entrada media de los discos del modelo; cada disco, su primera foto menos sus horas (§1)
    con_horas = primeras.dropna(subset=["horas_primera"])
    entrada = con_horas["primera_foto"] - pd.to_timedelta(con_horas["horas_primera"], unit="h")
    ms = pd.Series(entrada.to_numpy().astype("datetime64[ms]").astype("int64"), index=con_horas.index)
    media = ms.groupby(con_horas["model_primera"].to_numpy()).mean()
    compra = pd.Series(pd.to_datetime(np.round(media.to_numpy()).astype("int64"), unit="ms"), index=media.index)
    dm["fecha_compra"] = dm["model"].map(compra).where(datos).astype("datetime64[ms]")
    dm["discos_con_horas"] = dm["model"].map(con_horas.groupby("model_primera").size()).fillna(0).astype("int64")
    # Coste por GB y precio en la fecha de compra; los cuatro 6 TB de la tabla de precios quedan sin precio
    costes, origenes = [], []
    for _, f in dm.iterrows():
        if f["tipo_disco"] != "datos" or pd.isna(f["fecha_compra"]) or f["model"] in SIN_PRECIO:
            costes.append(np.nan)
            origenes.append(None)
            continue
        valor, origen, usadas, motivo = coste_gb(f["capacidad_tb"], f["fecha_compra"])
        if valor is None:
            ctx["pendientes_precio"].append({"tabla": "dim_modelo", "columna": "coste_gb_compra", "modelo": f["model"],
                                             "motivo": motivo})
        costes.append(np.nan if valor is None else valor)
        origenes.append(origen)
    dm["coste_gb_compra"] = costes
    dm["precio_usd"] = dm["coste_gb_compra"] * dm["capacidad_tb"] * 1000
    dm["origen_precio"] = pd.array(origenes, dtype="str")
    return dm


def construir_dim_precio_gb(dm, cal, ctx):
    """dim_precio_gb: el coste por GB de cada capacidad de datos el 1 de julio de cada año del Calendario."""
    capacidades = sorted(dm.loc[dm["tipo_disco"] == "datos", "capacidad_tb"].unique())
    filas = []
    for ano in sorted(cal["ano"].unique()):
        for cap in capacidades:
            valor, origen, usadas, motivo = coste_gb(cap, pd.Timestamp(year=int(ano), month=DIA_PRECIO_ANO[0],
                                                                         day=DIA_PRECIO_ANO[1]))
            if valor is None:
                ctx["pendientes_precio"].append({"tabla": "dim_precio_gb", "columna": "coste_gb",
                                                 "modelo": f"{cap} TB en {ano}", "motivo": motivo})
            filas.append({"capacidad_tb": float(cap), "ano": int(ano), "coste_gb": np.nan if valor is None else valor,
                          "origen": origen, "capacidades_usadas": ", ".join(f"{c:g}" for c in usadas) or None})
    dpg = pd.DataFrame(filas)
    dpg["ano"] = dpg["ano"].astype("int64")
    return dpg


# =================================================================================================================
# 6. Primera pasada por las fotos: la primera foto de cada disco
# =================================================================================================================
def primera_pasada(ruta):
    """Lee las fotos bloque a bloque, con tres columnas, y devuelve la primera foto de cada disco y la fecha de cada bloque.

    Comprueba que cada bloque es un mes y que los bloques van en orden de fecha: la primera foto de un disco es la del
    primer bloque en que sale.
    """
    pf = pq.ParquetFile(ruta)
    vistos = pa.array([], type=pa.string())
    partes, fechas = [], []
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=["serial_number", "fecha", "model", "smart_9_raw"])
        unicas = pc.unique(t["fecha"])
        if len(unicas) != 1:
            raise Parada(f"el bloque {i} de las fotos trae {len(unicas)} fechas: un bloque tiene que ser un mes")
        f = pd.Timestamp(unicas[0].as_py())
        if fechas and f <= fechas[-1]:
            raise Parada(f"los bloques de las fotos no van en orden de fecha: el {i} es del {dia(f)}")
        fechas.append(f)
        serie = t["serial_number"].combine_chunks()
        nuevo = t.filter(pc.invert(pc.is_in(serie, value_set=vistos)))
        vistos = pa.concat_arrays([vistos, nuevo["serial_number"].combine_chunks()])
        partes.append(nuevo.select(["serial_number", "model", "smart_9_raw"]).to_pandas().assign(primera_foto=f))
    primeras = pd.concat(partes, ignore_index=True).rename(columns={"model": "model_primera",
                                                                   "smart_9_raw": "horas_primera"})
    primeras["primera_foto"] = primeras["primera_foto"].astype("datetime64[ms]")
    return primeras, fechas


# =================================================================================================================
# 7. fallos_detalle (§4), la parte que sale de las ventanas, las dimensiones y el Calendario
# =================================================================================================================
def construir_fallos(ctx, fl, ve, dm, dpg, cal, primera):
    """Una fila por fallo con el día del fallo, el día anterior, el sitio, la edad, el valor y el calendario (cruces 1 a 6)."""
    fd = fl[["_id", "serial_number", "dia_fallo"]].copy()
    # 7.1 Cruce 1: la fila de la ventana del día del fallo, con el modelo y las horas
    del_dia = ve.loc[ve["fecha"] == ve["dia_fallo"], ["serial_number", "fecha", "model", "smart_9_raw"]].rename(
        columns={"smart_9_raw": "horas_dia"})
    fd = cruzar(ctx, 1, "fallos_detalle, día del fallo", "fallos", "ventanas (día del fallo)", fd, del_dia,
                ["serial_number", "dia_fallo"], ["serial_number", "fecha"])
    fd["con_fila_del_dia"] = fd["_merge"] == "both"
    fd = fd.drop(columns=["_merge"])
    # 7.2 Cruce 2: la fila del día anterior de la misma ventana, con los cinco contadores
    anterior = ve.loc[ve["fecha"] == ve["dia_fallo"] - pd.Timedelta(days=1),
                      ["serial_number", "dia_fallo", "smart_9_raw", *CONTADORES]].rename(
        columns={"smart_9_raw": "horas_ant", **{c: f"ant_{c}" for c in CONTADORES}})
    fd = cruzar(ctx, 2, "fallos_detalle, día anterior", "fallos", "ventanas (día anterior)", fd, anterior,
                ["serial_number", "dia_fallo"], ["serial_number", "dia_fallo"])
    hay = fd["_merge"] == "both"
    fd = fd.drop(columns=["_merge"])
    # 7.3 Cruce 3: la última fila hasta el día del fallo con centro, y la última con centro, vault, servidor y ranura
    hasta = ve.loc[ve["fecha"] <= ve["dia_fallo"]].sort_values(["serial_number", "dia_fallo", "fecha"])
    con_centro = (hasta.loc[hasta["datacenter"].notna()].groupby(["serial_number", "dia_fallo"], sort=False).tail(1)
                  [["serial_number", "dia_fallo", "datacenter"]])
    completa = (hasta.loc[hasta[SITIO].notna().all(axis=1)].groupby(["serial_number", "dia_fallo"], sort=False).tail(1)
                [["serial_number", "dia_fallo", *SITIO]].rename(columns={"datacenter": "centro_tomo"}))
    completa["tomo"] = (completa["centro_tomo"] + "|" + completa["vault_id"].astype("int64").astype("str") + "|"
                        + completa["pod_slot_num"].astype("int64").astype("str"))
    fd = cruzar(ctx, 3, "fallos_detalle, último día con centro", "fallos", "ventanas (último día con centro)", fd,
                con_centro, ["serial_number", "dia_fallo"], ["serial_number", "dia_fallo"]).drop(columns=["_merge"])
    fd = cruzar(ctx, 3, "fallos_detalle, último día con ranura", "fallos", "ventanas (último día con ranura)", fd,
                completa, ["serial_number", "dia_fallo"], ["serial_number", "dia_fallo"]).drop(columns=["_merge"])
    for c in ("vault_id", "pod_id", "pod_slot_num"):
        fd[c] = fd[c].astype("Int64")
    # 7.4 Cruce 4: capacidad, fabricante, tipo y garantía del modelo
    fd = cruzar(ctx, 4, "fallos_detalle", "fallos", "dim_modelo", fd,
                dm[["model", "capacidad_tb", "fabricante", "tipo_disco", "garantia_anos"]], ["model"], ["model"])
    fd = fd.drop(columns=["_merge"])
    # 7.5 La edad al fallar: las horas del día o del anterior; sin ellas, desde la primera aparición
    fd["horas_al_fallar"] = fd["horas_dia"].combine_first(fd["horas_ant"])
    desde = (fd["dia_fallo"] - fd["serial_number"].map(primera)) / pd.Timedelta(days=1)
    fd["edad_de_horas"] = fd["horas_al_fallar"].notna()
    fd["edad_al_fallar_anos"] = np.where(fd["edad_de_horas"], fd["horas_al_fallar"] / HORAS_ANO, desde / DIAS_ANO)
    negativas = int((fd["edad_al_fallar_anos"] < 0).sum())
    sin_edad = int(fd["edad_al_fallar_anos"].isna().sum())
    if negativas or sin_edad:
        raise Parada(f"fallos_detalle: {negativas} fallos con edad negativa y {sin_edad} sin edad")
    fd["en_garantia"] = (fd["edad_al_fallar_anos"] < fd["garantia_anos"].astype("Float64")).fillna(False).astype(bool)
    # 7.6 El aviso del día anterior: un contador vacío no cuenta; sin día anterior, vacío
    avisa = (fd[[f"ant_{c}" for c in CONTADORES]] > 0).any(axis=1)
    fd["hay_dia_anterior"] = hay
    fd["avisa_dia_anterior"] = pd.array(np.where(hay, avisa, None), dtype="boolean")
    fd["sin_aviso"] = pd.array(np.where(hay, ~avisa, None), dtype="boolean")
    # 7.7 El tomo: días desde el fallo anterior del mismo tomo y si coincide con él (convención del plazo, reglas, apartado 7)
    fd["plazo_reconstruccion_dias"] = fd["capacidad_tb"] + 1
    fd = fd.sort_values(["tomo", "dia_fallo", "serial_number"], na_position="last")
    g = fd.groupby("tomo", sort=False)
    dias_tomo = (fd["dia_fallo"] - g["dia_fallo"].shift(1)) / pd.Timedelta(days=1)
    fd["dias_desde_anterior_del_tomo"] = dias_tomo.round().astype("Int64")
    fd["coincide_con_anterior"] = (fd["dias_desde_anterior_del_tomo"].astype("Float64")
                                   < g["plazo_reconstruccion_dias"].shift(1).astype("Float64"))
    fd = fd.sort_values("_id")
    # 7.8 Cruce 5: el precio del disco nuevo, al coste por GB de su capacidad el año del fallo
    fd["ano_fallo"] = fd["dia_fallo"].dt.year.astype("int64")
    fd = cruzar(ctx, 5, "fallos_detalle", "fallos", "dim_precio_gb", fd, dpg[["capacidad_tb", "ano", "coste_gb"]],
                ["capacidad_tb", "ano_fallo"], ["capacidad_tb", "ano"]).drop(columns=["_merge", "ano_fallo"])
    fd["precio_nuevo_usd"] = fd["coste_gb"] * fd["capacidad_tb"] * 1000
    fd["coste_fallo_usd"] = fd["precio_nuevo_usd"] + COSTE_CAMBIO_USD
    fd["coste_fallo_garantia_usd"] = fd["coste_fallo_usd"].where(~fd["en_garantia"], COSTE_CAMBIO_USD)
    # 7.9 Cruce 6: periodo, año, trimestre y mes del Calendario
    fd = cruzar(ctx, 6, "fallos_detalle", "fallos", "Calendario", fd, cal[["fecha", "periodo", "ano", "trimestre", "mes"]],
                ["dia_fallo"], ["fecha"]).drop(columns=["_merge"])
    fd["primer_fallo_del_disco"] = fd["dia_fallo"] == fd.groupby("serial_number")["dia_fallo"].transform("min")
    return fd.reset_index(drop=True)


# =================================================================================================================
# 8. Segunda pasada por las fotos: fotos_riesgo bloque a bloque y lo que las demás tablas necesitan de las fotos
# =================================================================================================================
def grupos_de(columnas):
    """Los grupos de fotos_riesgo para estas columnas: los fijos y «no previstas» con las demás smart_*."""
    fijas = {c for g in GRUPOS_FIJOS.values() for c in g}
    grupos = {g: list(GRUPOS_FIJOS[g]) for g in GRUPOS_FIJOS}
    grupos["no_previstas"] = [c for c in columnas if PATRON_SMART.match(c) and c not in fijas]
    return {g: grupos[g] for g in ORDEN_GRUPOS}


def comprobar_grupos(columnas, grupos):
    """Para si una columna de la tabla no está en ningún grupo, está en dos o un grupo nombra una que no está."""
    cuenta = {}
    for cols in grupos.values():
        for c in cols:
            cuenta[c] = cuenta.get(c, 0) + 1
    sin_grupo = [c for c in columnas if c not in cuenta]
    en_dos = [c for c, n in cuenta.items() if n > 1]
    faltan = [c for c in cuenta if c not in columnas]
    if sin_grupo or en_dos or faltan:
        raise Parada(f"fotos_riesgo: columnas sin grupo {sin_grupo}, en dos grupos {en_dos} y de un grupo que no "
                     f"están en la tabla {faltan}")
    return {"columnas": len(columnas), "sin_grupo": len(sin_grupo), "en_dos_grupos": len(en_dos),
            "que_faltan": len(faltan)}


def columna_arrow(serie, tipo):
    """Columna de Arrow desde una serie de pandas, con su tipo y los vacíos como nulos."""
    return pa.array(serie, type=tipo, from_pandas=True)


def segunda_pasada(ctx, raiz, dm, cal, primera, fl, parcial):
    """Recorre las fotos bloque a bloque: escribe fotos_riesgo y acumula lo que necesitan las demás tablas.

    Guarda de un bloque al siguiente la última foto de cada disco (fecha, contadores, aviso, edad, modelo y centro) y
    la une por serial_number para los cambios. Acumula por bloque las fotos por modelo, centro, mes y año de edad, las
    del primer día de cada trimestre, los pares foto-fallo del objetivo y la última foto anterior a cada fallo.
    """
    pf = pq.ParquetFile(raiz / FOTOS)
    columnas = [c for c in pf.schema_arrow.names if c not in ("date", "cluster_id")]
    dim = dm[["model", "capacidad_tb", "fabricante", "tipo_disco", "garantia_anos"]]
    calp = cal[["fecha", "periodo"]]
    fin_periodo = cal.groupby("periodo")["fecha"].max()
    acu = {"tramo": [], "inicio": [], "pares": [], "n_pares": 0, "fotos": 0, "fotos_arranque": 0, "fotos_datos": 0,
           "fotos_dia_fallo": 0, "filas": {}, "objetivo": {}, "meses": {"uno": 0, "mas_de_uno": 0, "ninguno": 0},
           "edades_negativas": 0, "sin_periodo": 0, "claves_repetidas": 0, "minmax": {}, "valores": {}, "grupos": None, "comprobacion_grupos": None}
    ultima = pd.Series(pd.NaT, index=fl["_id"], dtype="datetime64[ms]")
    estado = None
    escritor, esquema = None, None
    try:
        for i in range(pf.num_row_groups):
            t = pf.read_row_group(i, columns=columnas)
            F = pd.Timestamp(pc.unique(t["fecha"])[0].as_py())
            df = t.select(["serial_number", "fecha", "model", "capacity_bytes", "failure", "datacenter", "smart_9_raw",
                           *CONTADORES]).to_pandas()
            df["_pos"] = np.arange(len(df))
            acu["fotos"] += len(df)
            # 8.1 Cruces 9 y 10: el modelo y el periodo de cada foto
            df = cruzar(ctx, 9, "fotos", "fotos", "dim_modelo", df, dim, ["model"], ["model"]).drop(columns=["_merge"])
            df = cruzar(ctx, 10, "fotos", "fotos", "Calendario", df, calp, ["fecha"], ["fecha"]).drop(columns=["_merge"])
            df = df.sort_values("_pos").reset_index(drop=True)
            # 8.2 La edad: horas encendido entre 8.766; sin horas, días desde la primera aparición entre 365,25
            con_horas = df["smart_9_raw"].notna()
            desde = (F - df["serial_number"].map(primera)) / pd.Timedelta(days=1)
            edad = np.where(con_horas, df["smart_9_raw"] / HORAS_ANO, desde / DIAS_ANO)
            negativas = int((edad < 0).sum()) + int(np.isnan(edad).sum())
            if negativas:
                acu["edades_negativas"] += negativas
                raise Parada(f"edad negativa o vacía en {negativas} fotos del {dia(F)}")
            df["edad_anos"] = edad
            df["edad_de_horas"] = con_horas
            # 8.3 Los avisos: un contador vacío no cuenta como aviso (reglas, apartado 3 y §5)
            positivos = df[CONTADORES] > 0
            df["avisa"] = positivos.any(axis=1)
            df["contadores_que_avisan"] = positivos.sum(axis=1).astype("int64")
            df["suma_contadores_sin_188"] = df[CONTADORES_SIN_188].sum(axis=1, min_count=1)
            df["smart_188_no_cero"] = pd.array(np.where(df["smart_188_raw"].isna(), None,
                                                        (df["smart_188_raw"] > 0).astype("int64")), dtype="Int8")
            # 8.4 La foto anterior del mismo disco, guardada del bloque anterior (convención técnica 3)
            if estado is None:
                previo = pd.DataFrame({"serial_number": pd.Series([], dtype="str"),
                                       "fecha_ant": pd.Series([], dtype="datetime64[ms]"),
                                       **{f"ant_{c}": pd.Series([], dtype="float64") for c in CONTADORES_SIN_188}})
            else:
                previo = estado[["serial_number", "fecha_ant", *[f"ant_{c}" for c in CONTADORES_SIN_188]]]
            antes = len(df)
            df = df.merge(previo, on="serial_number", how="left", validate="one_to_one")
            if len(df) != antes:
                raise Parada(f"la foto anterior del {dia(F)} cambia las filas del bloque")
            for c in CONTADORES_SIN_188:
                df[f"cambio_{c.replace('_raw', '')}"] = df[c] - df[f"ant_{c}"]
            fa = df["fecha_ant"]
            df["meses_desde_foto_anterior"] = ((F.year - fa.dt.year) * 12 + (F.month - fa.dt.month)).astype("Int64")
            # 8.5 La última foto de cada disco pasa al bloque siguiente (todas las fotos del bloque)
            centro = df["datacenter"].fillna(SIN_DATO)
            nuevo = pd.DataFrame({"serial_number": df["serial_number"], "fecha_ant": df["fecha"],
                                  **{f"ant_{c}": df[c] for c in CONTADORES_SIN_188},
                                  "avisa_ult": df["avisa"], "edad_ult": df["edad_anos"], "model_ult": df["model"],
                                  "centro_ult": centro})
            if estado is None:
                estado = nuevo
            else:
                quedan = estado.loc[~estado["serial_number"].isin(nuevo["serial_number"])]
                estado = pd.concat([quedan, nuevo], ignore_index=True) if len(quedan) else nuevo
            # 8.6 Lo que necesitan dias_por_tramo e inicio_trimestre: fotos de discos de datos, todas
            datos = (df["tipo_disco"] == "datos").to_numpy()
            acu["fotos_arranque"] += int((df["tipo_disco"] == "arranque").sum())
            acu["fotos_datos"] += int(datos.sum())
            cumplidos = np.floor(df["edad_anos"]).astype("int64")
            d = df.loc[datos].assign(centro=centro[datos], edad_anos_cumplidos=cumplidos[datos])
            acu["tramo"].append(d.groupby(["model", "centro", "edad_anos_cumplidos"]).size().rename("fotos")
                                .reset_index().assign(mes=F))
            if F == F.to_period("Q").start_time:
                acu["inicio"].append(d.groupby(["model", "capacidad_tb", "edad_anos_cumplidos"]).size().rename("discos")
                                     .reset_index().assign(fecha=F))
            # 8.7 Cruce 13: la última foto de cada disco anterior a cada fallo (los bloques van en orden de fecha)
            b = df[["serial_number"]].assign(_foto=F)
            m = cruzar(ctx, 13, "fallos y fotos", "fallos", "fotos (última anterior al fallo)",
                       fl[["_id", "serial_number", "dia_fallo"]], b, ["serial_number"], ["serial_number"])
            sel = (m["_merge"] == "both") & (m["dia_fallo"] > F)
            ultima.loc[m.loc[sel, "_id"].to_numpy()] = F
            # 8.8 Las filas de fotos_riesgo: discos de datos, sin la foto del día del fallo
            riesgo = datos & (df["failure"] == 0).to_numpy()
            acu["fotos_dia_fallo"] += int((datos & (df["failure"] != 0).to_numpy()).sum())
            r = df.loc[riesgo].copy()
            sin_periodo = int(r["periodo"].isna().sum())
            acu["sin_periodo"] += sin_periodo
            if sin_periodo:
                raise Parada(f"{sin_periodo} fotos del {dia(F)} sin periodo en el Calendario")
            tope = F + pd.Timedelta(days=HORIZONTE_DIAS)
            fin = r["periodo"].map(fin_periodo).astype("datetime64[ms]")
            r["horizonte_hasta"] = fin.where(fin < tope, tope)
            # 8.9 Cruce 12: el objetivo, con los fallos del disco del día siguiente a la foto al horizonte, los dos incluidos
            pares = r[["serial_number", "horizonte_hasta"]].merge(fl[["serial_number", "dia_fallo"]], on="serial_number",
                                                                    how="inner", validate="one_to_many")
            pares = pares.loc[(pares["dia_fallo"] > F) & (pares["dia_fallo"] <= pares["horizonte_hasta"])]
            acu["n_pares"] += len(pares)
            if len(pares):
                acu["pares"].append(pares[["serial_number", "dia_fallo"]])
            marcas = pares[["serial_number"]].drop_duplicates().assign(falla_30d=1)
            r = cruzar(ctx, 12, "fotos_riesgo", "fotos de discos de datos", "fallos (como horizontes)", r, marcas,
                       ["serial_number"], ["serial_number"]).drop(columns=["_merge"])
            r["falla_30d"] = r["falla_30d"].fillna(0).astype("int8")
            r = r.sort_values("_pos")
            # 8.10 La tabla de Arrow: las columnas de la foto que pasan sin cambios y las nuevas
            base = t.filter(pa.array(riesgo)).drop_columns(["failure"])
            if base["serial_number"].to_pylist() != r["serial_number"].tolist():
                raise Parada(f"las filas de fotos_riesgo del {dia(F)} no van en el orden de la foto")
            nuevas = {
                "capacidad_tb": columna_arrow(r["capacidad_tb"], pa.float64()),
                "fabricante": columna_arrow(r["fabricante"], pa.string()),
                "garantia_anos": columna_arrow(r["garantia_anos"], pa.int64()),
                "edad_anos": columna_arrow(r["edad_anos"], pa.float64()),
                "edad_de_horas": columna_arrow(r["edad_de_horas"], pa.bool_()),
                "avisa": columna_arrow(r["avisa"], pa.bool_()),
                "contadores_que_avisan": columna_arrow(r["contadores_que_avisan"], pa.int64()),
                "suma_contadores_sin_188": columna_arrow(r["suma_contadores_sin_188"], pa.float64()),
                "smart_188_no_cero": columna_arrow(r["smart_188_no_cero"], pa.int8()),
                **{f"cambio_{c.replace('_raw', '')}": columna_arrow(r[f"cambio_{c.replace('_raw', '')}"], pa.float64())
                   for c in CONTADORES_SIN_188},
                "meses_desde_foto_anterior": columna_arrow(r["meses_desde_foto_anterior"], pa.int64()),
                "periodo": columna_arrow(r["periodo"], pa.string()),
                "horizonte_hasta": columna_arrow(r["horizonte_hasta"], pa.timestamp("ms")),
                "falla_30d": columna_arrow(r["falla_30d"], pa.int8()),
            }
            out = base
            for nombre, arr in nuevas.items():
                out = out.append_column(nombre, arr)
            # 8.11 Los grupos: cada columna en uno solo, comprobado antes de escribir el primer bloque
            if acu["grupos"] is None:
                acu["grupos"] = grupos_de(out.column_names)
                acu["comprobacion_grupos"] = comprobar_grupos(out.column_names, acu["grupos"])
            elif sorted(out.column_names) != sorted(c for g in acu["grupos"].values() for c in g):
                comprobar_grupos(out.column_names, acu["grupos"])
            out = out.select([c for g in ORDEN_GRUPOS for c in acu["grupos"][g]])
            if escritor is None:
                esquema = out.schema
                escritor = pq.ParquetWriter(parcial, esquema)
            elif not out.schema.equals(esquema):
                out = out.cast(esquema)
            escritor.write_table(out)
            # 8.12 Recuentos y rangos para el informe y para «Pendiente para el modelo»
            periodo = r["periodo"].iloc[0] if len(r) else None
            if periodo is not None:
                acu["filas"][periodo] = acu["filas"].get(periodo, 0) + len(r)
                acu["objetivo"][periodo] = acu["objetivo"].get(periodo, 0) + int(r["falla_30d"].sum())
            meses = r["meses_desde_foto_anterior"]
            acu["meses"]["uno"] += int((meses == 1).sum())
            acu["meses"]["mas_de_uno"] += int((meses > 1).sum())
            acu["meses"]["ninguno"] += int(meses.isna().sum())
            acu["claves_repetidas"] += int(r["serial_number"].duplicated().sum())
            for nombre in out.column_names:
                acumular_rango(acu, nombre, out[nombre])
    finally:
        if escritor is not None:
            escritor.close()
    acu["ultima"] = ultima
    acu["estado"] = estado
    return acu


def acumular_rango(acu, nombre, columna):
    """Acumula el mínimo y el máximo de una columna numérica, o sus valores si es una categórica o un código."""
    if nombre in ("model", "fabricante", "datacenter", "periodo", "vault_id", "pod_id", "pod_slot_num"):
        acu["valores"].setdefault(nombre, set()).update(v for v in pc.unique(columna).to_pylist() if v is not None)
    elif pa.types.is_integer(columna.type) or pa.types.is_floating(columna.type) or pa.types.is_boolean(columna.type):
        mm = pc.min_max(columna).as_py()
        if mm["min"] is None:
            return
        actual = acu["minmax"].get(nombre)
        acu["minmax"][nombre] = (mm["min"], mm["max"]) if actual is None else (min(actual[0], mm["min"]),
                                                                               max(actual[1], mm["max"]))


# =================================================================================================================
# 9. Las tablas que salen de lo acumulado: vida_discos, dias_por_tramo, inicio_trimestre, modelo_trimestre, centro_mes
# =================================================================================================================
def construir_vida(ctx, disco, dm, fd, estado, ultima_de_los_datos):
    """vida_discos (§5): una fila por disco de datos, con su entrada, su final y si desaparece avisando."""
    v = disco.copy()
    v["model"] = v["model_primera"].fillna(v["model_ventana"])
    v = cruzar(ctx, 9, "vida_discos", "discos (primera foto o ventana)", "dim_modelo", v, dm[["model", "tipo_disco"]],
               ["model"], ["model"]).drop(columns=["_merge"])
    v = v.loc[v["tipo_disco"] == "datos"].copy()
    # La edad de entrada: la de la fila de su primera aparición; sin horas, cero días desde ella
    desde_foto = v["primera_foto"].notna() & (v["primer_dia_ventana"].isna()
                                              | (v["primera_foto"] <= v["primer_dia_ventana"]))
    horas = v["horas_primera"].where(desde_foto, v["horas_ventana"])
    v["edad_entrada_anos"] = (horas / HORAS_ANO).fillna(0.0)
    # La última foto, con su aviso, edad, modelo y centro, guardada en la segunda pasada
    v = v.merge(estado[["serial_number", "fecha_ant", "avisa_ult", "edad_ult", "model_ult", "centro_ult"]],
                on="serial_number", how="left", validate="one_to_one").rename(columns={"fecha_ant": "ultima_foto"})
    # Cruce 13 al grano del disco: su primer fallo, su último fallo y la edad en el primero
    por_disco = (fd.groupby("serial_number").agg(primer_fallo=("dia_fallo", "min"), ultimo_fallo=("dia_fallo", "max"))
                 .reset_index())
    edad_primero = fd.loc[fd["primer_fallo_del_disco"], ["serial_number", "edad_al_fallar_anos"]]
    por_disco = por_disco.merge(edad_primero, on="serial_number", how="left", validate="one_to_one")
    v = cruzar(ctx, 13, "vida_discos", "discos de datos", "fallos (por disco)", v, por_disco, ["serial_number"],
               ["serial_number"]).drop(columns=["_merge"])
    falla_despues = (v["ultimo_fallo"] >= v["ultima_foto"]).fillna(False)
    v["evento"] = np.select([v["primer_fallo"].notna(),
                             v["ultima_foto"].notna() & (v["ultima_foto"] < ultima_de_los_datos) & ~falla_despues,
                             v["primer_fallo"].isna()], ["fallo", "desaparece", "sigue"], "SIN_REGLA")
    v["fecha_fin"] = v["primer_fallo"].where(v["evento"] == "fallo", v["ultima_foto"])
    v["edad_fin_anos"] = v["edad_al_fallar_anos"].where(v["evento"] == "fallo", v["edad_ult"])
    v["avisa_ultima_foto"] = v["avisa_ult"].astype("boolean")
    v["desaparece_avisando"] = (v["evento"] == "desaparece") & v["avisa_ultima_foto"].fillna(False).astype(bool)
    return v.sort_values("serial_number").reset_index(drop=True)


def construir_tramo(ctx, acu, rd, fd, vd):
    """dias_por_tramo (§6): fotos, días de disco repartidos, fallos y desaparecidos avisando por modelo, centro, mes y edad."""
    claves = ["model", "centro", "mes"]
    F = pd.concat(acu["tramo"], ignore_index=True)
    F["parte"] = F["fotos"] / F.groupby(claves)["fotos"].transform("sum")
    R = (rd.assign(centro=rd["datacenter"]).groupby(claves).agg(dias_recuento=("discos", "sum"),
                                                                fallos_recuento=("fallos", "sum")).reset_index())
    # Cruce 11: los días de cada celda del recuento se reparten entre sus años de edad en proporción a sus fotos
    m = cruzar(ctx, 11, "dias_por_tramo", "fotos agregadas", "recuento agregado", F, R, claves, claves)
    m["dias_disco"] = m["parte"] * m["dias_recuento"]
    con_foto = R.merge(F[claves].drop_duplicates(), on=claves, how="left", validate="one_to_one", indicator=True)
    sin_foto = con_foto.loc[con_foto["_merge"] == "left_only"]
    repartibles = con_foto.loc[con_foto["_merge"] == "both", "dias_recuento"].sum()
    suma_de_control(ctx, 11, "dias_por_tramo", "días de disco de las celdas con foto", repartibles, m["dias_disco"].sum())
    # Cruce 15: los fallos de discos de datos al mismo grano, con el centro del fallo y su edad al fallar
    datos = fd.loc[fd["tipo_disco"] == "datos"]
    Fa = (datos.assign(centro=datos["datacenter"].fillna(SIN_DATO), mes=inicio_de_mes(datos["dia_fallo"]),
                       edad_anos_cumplidos=np.floor(datos["edad_al_fallar_anos"]).astype("int64"))
          .groupby(claves + ["edad_anos_cumplidos"]).size().rename("fallos").reset_index())
    t = cruzar(ctx, 15, "dias_por_tramo", "días repartidos", "fallos agregados",
               m[claves + ["edad_anos_cumplidos", "fotos", "dias_disco"]], Fa, claves + ["edad_anos_cumplidos"],
               claves + ["edad_anos_cumplidos"], how="outer")
    solo_fallos = t["_merge"] == "right_only"
    t["fotos"] = t["fotos"].fillna(0).astype("int64")
    t["fallos"] = t["fallos"].fillna(0).astype("int64")
    suma_de_control(ctx, 15, "dias_por_tramo", "fallos de discos de datos", len(datos), t["fallos"].sum())
    suma_de_control(ctx, 15, "dias_por_tramo", "días de disco repartidos", m["dias_disco"].sum(), t["dias_disco"].sum())
    # Los discos que desaparecen avisando, en el modelo, el centro, el mes y la edad de su última foto (convención 6)
    dv = vd.loc[vd["desaparece_avisando"]]
    D = (pd.DataFrame({"model": dv["model_ult"], "centro": dv["centro_ult"], "mes": dv["ultima_foto"],
                       "edad_anos_cumplidos": np.floor(dv["edad_ult"]).astype("int64")})
         .groupby(claves + ["edad_anos_cumplidos"]).size().rename("desaparecen_avisando").reset_index())
    t = t.drop(columns=["_merge"]).merge(D, on=claves + ["edad_anos_cumplidos"], how="left", validate="one_to_one")
    t["desaparecen_avisando"] = t["desaparecen_avisando"].fillna(0).astype("int64")
    info = {"filas_solo_fallos": int(solo_fallos.sum()), "fallos_sin_dias": int(t.loc[solo_fallos, "fallos"].sum()),
            "dias_sin_foto": float(sin_foto["dias_recuento"].sum()), "celdas_sin_foto": len(sin_foto),
            "fallos_recuento_sin_foto": int(sin_foto["fallos_recuento"].sum()),
            "dias_recuento": float(R["dias_recuento"].sum()),
            "desaparecen_avisando_sin_fila": int(len(dv) - t["desaparecen_avisando"].sum())}
    t = t[claves + ["edad_anos_cumplidos", "fotos", "dias_disco", "fallos", "desaparecen_avisando"]]
    return t.sort_values(claves + ["edad_anos_cumplidos"]).reset_index(drop=True), info


def construir_inicio(ctx, acu, rd, cal):
    """inicio_trimestre (§7): los discos de datos de la foto del primer día de cada trimestre, por modelo y año de edad."""
    I = pd.concat(acu["inicio"], ignore_index=True)
    I["fecha"] = I["fecha"].astype("datetime64[ms]")
    I = cruzar(ctx, 10, "inicio_trimestre", "fotos del primer día del trimestre", "Calendario", I,
               cal[["fecha", "ano", "trimestre"]], ["fecha"], ["fecha"]).drop(columns=["_merge"])
    dias_trim = cal.groupby(["ano", "trimestre"]).size().rename("dias_trimestre").reset_index()
    I = I.merge(dias_trim, on=["ano", "trimestre"], how="left", validate="many_to_one")
    # Cruce 14: los discos de la foto frente a los del recuento ese día, modelo a modelo
    Fm = I.groupby(["fecha", "model"])["discos"].sum().reset_index()
    Rm = (rd.loc[rd["fecha"].isin(I["fecha"].unique())].groupby(["fecha", "model"])["discos"].sum()
          .rename("discos_recuento").reset_index())
    c = cruzar(ctx, 14, "inicio_trimestre", "fotos del primer día del trimestre", "recuento de ese día", Fm, Rm,
               ["fecha", "model"], ["fecha", "model"], how="outer")
    c["igual"] = c["discos"].fillna(0) == c["discos_recuento"].fillna(0)
    por_trimestre = c.groupby("fecha")["igual"].all()
    suma_de_control(ctx, 14, "inicio_trimestre", "discos del primer día del trimestre", Fm["discos"].sum(),
                    I["discos"].sum())
    info = {"trimestres": int(I["fecha"].nunique()), "trimestres_iguales_al_recuento": int(por_trimestre.sum()),
            "discos_recuento": float(Rm["discos_recuento"].sum())}
    I = I[["ano", "trimestre", "model", "edad_anos_cumplidos", "fecha", "capacidad_tb", "discos", "dias_trimestre"]]
    return I.sort_values(["ano", "trimestre", "model", "edad_anos_cumplidos"]).reset_index(drop=True), info


def construir_modelo_trimestre(ctx, rd, fd, dm):
    """modelo_trimestre (§8): días de disco, fallos y su coste por modelo de datos y trimestre, con el mínimo del año."""
    claves = ["model", "ano", "trimestre"]
    R = rd.groupby(claves).agg(dias_disco=("discos", "sum"), fallos_recuento=("fallos", "sum")).reset_index()
    datos = fd.loc[fd["tipo_disco"] == "datos"]
    Fq = datos.groupby(claves).agg(fallos=("dia_fallo", "size"), fallos_en_garantia=("en_garantia", "sum"),
                                   coste_fallos_usd=("coste_fallo_usd", "sum"),
                                   coste_fallos_garantia_usd=("coste_fallo_garantia_usd", "sum")).reset_index()
    # El cruce 15 del plan, recuento y fallos al mismo grano, aquí con el grano de modelo y trimestre (§8)
    m = cruzar(ctx, 15, "modelo_trimestre", "recuento por modelo y trimestre", "fallos por modelo y trimestre", R, Fq,
               claves, claves, how="outer")
    info = {"filas_sin_dias": int((m["_merge"] == "right_only").sum())}
    m = m.drop(columns=["_merge"])
    for c in ("fallos", "fallos_en_garantia"):
        m[c] = m[c].fillna(0).astype("int64")
    for c in ("coste_fallos_usd", "coste_fallos_garantia_usd"):
        m[c] = m[c].fillna(0.0)
    suma_de_control(ctx, 15, "modelo_trimestre", "fallos de discos de datos", len(datos), m["fallos"].sum())
    suma_de_control(ctx, 15, "modelo_trimestre", "días de disco", rd["discos"].sum(), m["dias_disco"].sum())
    m["dias_disco_ano"] = m.groupby(["model", "ano"])["dias_disco"].transform("sum")
    m["pasa_minimo_ano"] = m["dias_disco_ano"] >= MINIMO_DIAS_ANO
    info["filas_fallos_iguales"] = int((m["fallos"] == m["fallos_recuento"]).sum())
    m = cruzar(ctx, 7, "modelo_trimestre", "modelo_trimestre", "dim_modelo", m,
               dm[["model", "capacidad_tb", "fabricante", "fecha_compra", "precio_usd", "origen_precio"]],
               ["model"], ["model"]).drop(columns=["_merge"])
    celdas = m[["model", "ano", "pasa_minimo_ano"]].drop_duplicates()
    info.update({"celdas_modelo_ano": len(celdas), "celdas_pasan": int(celdas["pasa_minimo_ano"].sum()),
                 "modelos_pasan": int(celdas.loc[celdas["pasa_minimo_ano"], "model"].nunique())})
    m = m[["model", "ano", "trimestre", "capacidad_tb", "fabricante", "fecha_compra", "precio_usd", "origen_precio",
           "dias_disco", "fallos", "fallos_en_garantia", "coste_fallos_usd", "coste_fallos_garantia_usd",
           "dias_disco_ano", "pasa_minimo_ano"]]
    return m.sort_values(claves).reset_index(drop=True), info


def construir_centro_mes(ctx, rd, cal):
    """centro_mes (§9): días de disco y fallos del recuento por centro y mes, solo discos de datos."""
    C = rd.groupby(["datacenter", "mes"]).agg(dias_disco=("discos", "sum"), fallos=("fallos", "sum")).reset_index()
    C = cruzar(ctx, 8, "centro_mes", "recuento por centro y mes", "Calendario", C,
               cal[["fecha", "periodo"]].rename(columns={"fecha": "mes"}), ["mes"], ["mes"]).drop(columns=["_merge"])
    C["con_sitio"] = C["mes"] >= INICIO_SITIO
    suma_de_control(ctx, 8, "centro_mes", "días de disco", rd["discos"].sum(), C["dias_disco"].sum())
    suma_de_control(ctx, 8, "centro_mes", "fallos", rd["fallos"].sum(), C["fallos"].sum())
    return C.sort_values(["datacenter", "mes"]).reset_index(drop=True)


# =================================================================================================================
# 10. Registro de exclusiones (§10) y clases de los fallos que no son objetivo
# =================================================================================================================
def clases_sin_objetivo(fd, primeras, cal):
    """Clasifica los fallos de discos de datos que no son objetivo de ninguna foto (§10)."""
    fin_periodo = cal.groupby("periodo")["fecha"].max()
    periodo_de = cal.set_index("fecha")["periodo"]
    x = fd.loc[(fd["tipo_disco"] == "datos") & ~fd["objetivo_de_alguna_foto"]].copy()
    tiene_foto = x["serial_number"].isin(primeras["serial_number"])
    u = x["ultima_foto_anterior"]
    fin = u.map(periodo_de).map(fin_periodo).astype("datetime64[ms]")
    tope = u + pd.Timedelta(days=HORIZONTE_DIAS)
    horizonte = fin.where(fin < tope, tope)
    hueco = (x["dia_fallo"] - u) / pd.Timedelta(days=1)
    x["clase"] = np.select([~tiene_foto, u.isna(), (x["dia_fallo"] > horizonte) & (hueco <= HORIZONTE_DIAS),
                            hueco > HORIZONTE_DIAS + 1, (hueco == HORIZONTE_DIAS + 1) & (x["dia_fallo"].dt.day == 1)],
                           ["de_discos_sin_foto", "antes_de_la_primera_foto", "recorte_del_horizonte",
                            "mas_de_31_dias_tras_la_ultima_foto", "dia_1_tras_mes_de_31_dias"], "otros")
    return x


def exclusiones(fd, rec, rd, dm, acu, info_tramo, x):
    """Una fila por cada clase que sale de algún cálculo, con sus días de disco, fallos y fotos, sacados del código."""
    datos = fd["tipo_disco"] == "datos"
    arr = rec["tipo_disco"] == "arranque"
    desde = fd["dia_fallo"] >= INICIO_SITIO
    rd_desde = rd["fecha"] >= INICIO_SITIO
    sin_precio = dm.loc[(dm["tipo_disco"] == "datos") & dm["precio_usd"].isna(), "model"].tolist()
    otros = x.loc[x["clase"] == "otros", ["serial_number", "dia_fallo", "ultima_foto_anterior"]]
    return [
        {"clase": "discos_de_arranque", "que_sale": "los discos de 0,2 a 2 TB", "sale_de": "todo cálculo",
         "recuentos": {"dias_de_disco": int(rec.loc[arr, "discos"].sum()), "fallos": int((fd["tipo_disco"] == "arranque").sum()),
                       "fotos": acu["fotos_arranque"]}},
        {"clase": "sitio_antes", "que_sale": "días y fallos de discos de datos antes del 01/07/2023",
         "sale_de": "lo que va por centro y por tomo",
         "recuentos": {"dias_de_disco": int(rd.loc[~rd_desde, "discos"].sum()), "fallos": int((datos & ~desde).sum())}},
        {"clase": "centro_sin_dato_desde", "que_sale": "días y fallos con el centro «sin dato» desde el 01/07/2023",
         "sale_de": "las tasas por centro", "recuentos": {
             "dias_de_disco": int(rd.loc[rd_desde & (rd["datacenter"] == SIN_DATO), "discos"].sum()),
             "fallos": int(rd.loc[rd_desde & (rd["datacenter"] == SIN_DATO), "fallos"].sum())}},
        {"clase": "fallos_sin_tomo_desde", "que_sale": "fallos de discos de datos sin tomo desde el 01/07/2023",
         "sale_de": "los tomos y el aviso de tomos en peligro",
         "recuentos": {"fallos": int((datos & desde & fd["tomo"].isna()).sum())}},
        {"clase": "fallos_sin_dia_anterior", "que_sale": "fallos de discos de datos sin el día anterior en su ventana",
         "sale_de": "el indicador de fallos sin aviso",
         "recuentos": {"fallos": int((datos & ~fd["hay_dia_anterior"]).sum())}},
        {"clase": "fotos_del_dia_del_fallo", "que_sale": "fotos de discos de datos con failure = 1",
         "sale_de": "fotos_riesgo", "recuentos": {"fotos": acu["fotos_dia_fallo"]}},
        {"clase": "fallos_sin_objetivo", "que_sale": "fallos de discos de datos que no son objetivo de ninguna foto",
         "sale_de": "el objetivo de fotos_riesgo",
         "recuentos": {"fallos": len(x), **{k: int(v) for k, v in x["clase"].value_counts().items()}},
         "otros": [{"serial_number": s, "dia_fallo": dia(d), "ultima_foto_anterior": dia(u)}
                   for s, d, u in otros.itertuples(index=False)]},
        {"clase": "dias_sin_foto", "que_sale": "días de disco de celdas del recuento sin ninguna foto en su modelo, "
                                               "centro y mes", "sale_de": "dias_por_tramo",
         "recuentos": {"dias_de_disco": int(round(info_tramo["dias_sin_foto"])), "celdas": info_tramo["celdas_sin_foto"],
                       "fallos_recuento": info_tramo["fallos_recuento_sin_foto"]}},
        {"clase": "modelos_sin_precio", "que_sale": "modelos de datos sin precio", "sale_de": "el coste por TB y año",
         "recuentos": {"modelos": len(sin_precio), "dias_de_disco": int(rd.loc[rd["model"].isin(sin_precio), "discos"].sum())},
         "modelos": sin_precio},
    ]


# =================================================================================================================
# 11. Variables generadas, transformaciones y lo pendiente para el modelo
# =================================================================================================================
# (tabla, columna, fórmula, columnas de origen, unidad, información posterior, sale del objetivo, suma de otras)
VARIABLES = [
    ("dim_modelo", "capacidad_tb", "capacity_bytes / 10^12, a un decimal", ["capacity_bytes"], "TB", False, False, False),
    ("dim_modelo", "tipo_disco", "arranque hasta 2.048.408.248.320 bytes; datos por encima", ["capacity_bytes"], None, False, False, False),
    ("dim_modelo", "fabricante", "prefijo del modelo y dos excepciones (reglas, apartado 3)", ["model"], None, False, False, False),
    ("dim_modelo", "garantia_anos", "familia del modelo (reglas, apartado 6)", ["model"], "años", False, False, False),
    ("dim_modelo", "fecha_compra", "media de (primera foto - horas encendido) de los discos del modelo; ficha de hoy", ["fecha", "smart_9_raw"], None, True, False, False),
    ("dim_modelo", "coste_gb_compra", "coste por GB de su capacidad en su fecha de compra (curva, inferido o vecinas)", ["capacidad_tb", "fecha_compra"], "USD/GB", True, False, False),
    ("dim_modelo", "precio_usd", "coste_gb_compra × capacidad_tb × 1.000; ficha de hoy", ["coste_gb_compra", "capacidad_tb"], "USD", True, False, False),
    ("dim_modelo", "origen_precio", "curva, inferido o vecinas", ["fecha_compra"], None, True, False, False),
    ("dim_precio_gb", "coste_gb", "coste por GB de la capacidad el 1 de julio del año", ["capacidad_tb", "ano"], "USD/GB", False, False, False),
    ("fotos_riesgo", "edad_anos", "smart_9_raw / 8.766; sin horas, días desde la primera aparición / 365,25", ["smart_9_raw", "fecha"], "años", False, False, False),
    ("fotos_riesgo", "edad_de_horas", "smart_9_raw no vacío", ["smart_9_raw"], None, False, False, False),
    ("fotos_riesgo", "avisa", "algún contador de avería > 0; un vacío no cuenta", CONTADORES, None, False, False, False),
    ("fotos_riesgo", "contadores_que_avisan", "cuántos de los cinco contadores > 0", CONTADORES, "contadores", False, False, True),
    ("fotos_riesgo", "suma_contadores_sin_188", "smart_5 + smart_187 + smart_197 + smart_198 sin los vacíos; vacía si los cuatro lo están", CONTADORES_SIN_188, None, False, False, True),
    ("fotos_riesgo", "smart_188_no_cero", "1 si smart_188 > 0, 0 si vale 0, vacío si no consta", ["smart_188_raw"], None, False, False, False),
    *[("fotos_riesgo", f"cambio_{c.replace('_raw', '')}", f"{c} - {c} de la foto anterior del mismo disco", [c], None, False, False, True)
      for c in CONTADORES_SIN_188],
    ("fotos_riesgo", "meses_desde_foto_anterior", "meses entre la foto y la anterior del mismo disco", ["fecha"], "meses", False, False, False),
    ("fotos_riesgo", "capacidad_tb, fabricante, garantia_anos", "de dim_modelo (cruce 9)", ["model"], None, False, False, False),
    ("fotos_riesgo", "periodo", "el del Calendario en la fecha de la foto (cruce 10)", ["fecha"], None, False, False, False),
    ("fotos_riesgo", "horizonte_hasta", "fecha + 30 días, recortado al último día de su periodo", ["fecha", "periodo"], None, True, False, False),
    ("fotos_riesgo", "falla_30d", "1 si el disco tiene un fallo con fecha < dia_fallo <= horizonte_hasta (cruce 12)", ["serial_number", "fecha", "dia_fallo"], None, True, True, False),
    ("fallos_detalle", "horas_al_fallar", "horas del día del fallo o, si no las trae, del anterior", ["smart_9_raw"], "horas", False, False, False),
    ("fallos_detalle", "edad_al_fallar_anos", "horas_al_fallar / 8.766; sin horas, días desde la primera aparición / 365,25", ["horas_al_fallar", "dia_fallo"], "años", False, False, False),
    ("fallos_detalle", "en_garantia", "edad_al_fallar_anos < garantia_anos; falso sin garantía comprobada", ["edad_al_fallar_anos", "garantia_anos"], None, False, False, False),
    ("fallos_detalle", "hay_dia_anterior, avisa_dia_anterior, sin_aviso", "la fila del día anterior de la ventana y sus cinco contadores", CONTADORES, None, False, False, False),
    ("fallos_detalle", "tomo", "centro|vault|ranura de la última fila con los cuatro datos de sitio", SITIO, None, False, False, False),
    ("fallos_detalle", "plazo_reconstruccion_dias", "capacidad_tb + 1", ["capacidad_tb"], "días", False, False, True),
    ("fallos_detalle", "dias_desde_anterior_del_tomo, coincide_con_anterior", "días desde el fallo anterior del tomo; coincide si son menos que su plazo", ["tomo", "dia_fallo"], "días", False, False, True),
    ("fallos_detalle", "precio_nuevo_usd", "coste_gb del año del fallo × capacidad_tb × 1.000 (cruce 5)", ["capacidad_tb", "dia_fallo"], "USD", False, False, False),
    ("fallos_detalle", "coste_fallo_usd", "precio_nuevo_usd + 37", ["precio_nuevo_usd"], "USD", False, False, True),
    ("fallos_detalle", "coste_fallo_garantia_usd", "37 si en_garantia; si no, coste_fallo_usd", ["coste_fallo_usd", "en_garantia"], "USD", False, False, False),
    ("fallos_detalle", "ultima_foto_anterior", "última foto del disco anterior al fallo (cruce 13)", ["fecha"], None, False, False, False),
    ("fallos_detalle", "objetivo_de_alguna_foto", "el fallo está en el horizonte de alguna fila de fotos_riesgo", ["falla_30d"], None, True, True, False),
    ("fallos_detalle", "periodo, ano, trimestre, mes, primer_fallo_del_disco", "del Calendario en dia_fallo (cruce 6); el primer fallo de cada disco", ["dia_fallo"], None, False, False, False),
    ("vida_discos", "primera_aparicion, edad_entrada_anos", "primera foto o primer día de ventana; su edad ese día", ["fecha", "smart_9_raw"], "años", False, False, False),
    ("vida_discos", "ultima_foto, primer_fallo, evento, fecha_fin, edad_fin_anos", "última foto; primer fallo; fallo, desaparece o sigue", ["fecha", "dia_fallo"], None, True, False, False),
    ("vida_discos", "avisa_ultima_foto, desaparece_avisando", "aviso en la última foto; desaparece y avisaba", CONTADORES, None, True, False, False),
    ("dias_por_tramo", "fotos, dias_disco, fallos, desaparecen_avisando", "fotos por celda; días del recuento repartidos por sus fotos (cruce 11); fallos (cruce 15)", ["discos", "fallos"], "días de disco", False, False, False),
    ("inicio_trimestre", "discos, dias_trimestre", "discos de la foto del primer día del trimestre; días del trimestre", ["fecha"], None, False, False, False),
    ("modelo_trimestre", "dias_disco, fallos, fallos_en_garantia, coste_fallos_usd, coste_fallos_garantia_usd, dias_disco_ano, pasa_minimo_ano", "sumas del recuento y de fallos_detalle; mínimo de 50.000 días en el año", ["discos", "dia_fallo"], None, False, False, False),
    ("centro_mes", "dias_disco, fallos, periodo, con_sitio", "sumas del recuento; con_sitio desde julio de 2023", ["discos", "fallos"], "días de disco", False, False, False),
]

TRANSFORMACIONES = [
    ("igualacion", "Igualar las claves antes de cruzar, sin guardarlo en las tablas corregidas",
     ["dia_fallo", "datacenter"], "reglas de transformación, «De qué se parte»"),
    ("dim_modelo", "Construir dim_modelo", ["model", "capacidad_tb", "tipo_disco", "fabricante", "garantia_anos",
                                            "fecha_compra", "coste_gb_compra", "precio_usd", "origen_precio"], "§1"),
    ("dim_precio_gb", "Construir dim_precio_gb", ["capacidad_tb", "ano", "coste_gb", "origen"], "§1"),
    ("fotos_riesgo", "Construir fotos_riesgo bloque a bloque", ["edad_anos", "avisa", "falla_30d", "horizonte_hasta"], "§3"),
    ("fallos_detalle", "Construir fallos_detalle", ["model", "edad_al_fallar_anos", "sin_aviso", "tomo",
                                                    "coincide_con_anterior", "coste_fallo_usd"], "§4"),
    ("vida_discos", "Construir vida_discos", ["primera_aparicion", "evento", "desaparece_avisando"], "§5"),
    ("dias_por_tramo", "Construir dias_por_tramo", ["fotos", "dias_disco", "fallos", "desaparecen_avisando"], "§6"),
    ("inicio_trimestre", "Construir inicio_trimestre", ["discos", "dias_trimestre"], "§7"),
    ("modelo_trimestre", "Construir modelo_trimestre", ["dias_disco", "fallos", "coste_fallos_usd", "pasa_minimo_ano"],
     "§8"),
    ("centro_mes", "Construir centro_mes", ["dias_disco", "fallos", "con_sitio"], "§9"),
]

TIPO_COLUMNA = {"serial_number": "identificador", "fecha": "fecha", "horizonte_hasta": "fecha",
                "falla_30d": "objetivo", "periodo": "particion"}
CATEGORICAS = {"model", "fabricante", "datacenter"}
CODIGOS = {"vault_id", "pod_id", "pod_slot_num"}
BINARIAS = {"edad_de_horas", "avisa", "smart_188_no_cero"}
UNIDADES = {"edad_anos": "años", "capacidad_tb": "TB", "capacity_bytes": "bytes", "garantia_anos": "años",
            "meses_desde_foto_anterior": "meses", "contadores_que_avisan": "contadores", "smart_9_raw": "horas"}


def pendiente_modelo(acu):
    """Para cada columna de fotos_riesgo: su tipo, sus valores si es categórica o código, su rango si es magnitud."""
    salida = []
    for g in ORDEN_GRUPOS:
        for c in acu["grupos"][g]:
            tipo = TIPO_COLUMNA.get(c) or ("categorica" if c in CATEGORICAS else "codigo_numerico" if c in CODIGOS
                                          else "binaria" if c in BINARIAS else "magnitud")
            mm = acu["minmax"].get(c)
            valores = acu["valores"].get(c)
            salida.append({"columna": c, "grupo": g, "tipo": tipo,
                           "valores": None if valores is None else len(valores),
                           "orden_real": False if tipo in ("categorica", "codigo_numerico") else None,
                           "unidad": UNIDADES.get(c), "minimo": None if mm is None or tipo != "magnitud" else mm[0],
                           "maximo": None if mm is None or tipo != "magnitud" else mm[1]})
    return salida


# =================================================================================================================
# 12. Registro de transformaciones: una ficha por transformación nueva, la primera vez que se aplica
# =================================================================================================================
def ficha(numero, titulo, como_estaba, problema, decision, codigo, comprobacion, como_quedo, deshacer, fecha):
    """Texto de una ficha del registro, con sus nueve campos."""
    return (f"\n## {numero} · {titulo}\n\n"
            f"Escrita el {fecha} por {SCRIPT}.\n\n"
            f"1. **Tabla y columna:** {titulo}.\n"
            f"2. **Cómo estaba:** {como_estaba}\n"
            f"3. **Problema o finalidad:** {problema}\n"
            f"4. **Decisión:** {decision}\n"
            f"5. **Qué se hizo:**\n\n```python\n{codigo}\n```\n\n"
            f"6. **Quién y con qué permiso:** el analista, con la petición {PETICION} y las "
            f"reglas de transformación aprobadas por el responsable del caso el 17/11/2026 («Sí, las apruebo»).\n"
            f"7. **Comprobación:** {comprobacion}\n"
            f"8. **Cómo quedó:** {como_quedo}\n"
            f"9. **Cómo deshacer:** {deshacer} Las tablas corregidas no se tocan, así que basta con borrar la tabla "
            f"nueva o volver a ejecutar el script sin la regla.\n")


def numerar_fichas(texto, titulos):
    """Número de cada ficha: el que ya tiene en el registro o el siguiente libre, en orden (R-010 en adelante)."""
    existentes = {m.group(2): m.group(1) for m in re.finditer(r"^## (R-\d+) · (.+)$", texto, re.M)}
    siguiente = max([int(n[2:]) for n in re.findall(r"^## (R-\d+) ", texto, re.M)] or [0]) + 1
    numeros, nuevas = {}, []
    for t in titulos:
        if t in existentes:
            numeros[t] = existentes[t]
        else:
            numeros[t] = f"R-{siguiente:03d}"
            nuevas.append(t)
            siguiente += 1
    return numeros, nuevas


def fichas_del_registro(r):
    """Las fichas de esta transformación, con las cifras de esta ejecución: (clave, título, campos)."""
    c = r["cifras_de_control"]
    x = {e["clase"]: e["recuentos"] for e in r["exclusiones"]}
    return [
        ("igualacion", "igualación antes de cruzar · dia_fallo y centro vacío",
         "dia_fallo llega en nanosegundos en la lista de fallos y en las ventanas, y fecha en milisegundos; el centro "
         "que no consta está vacío en las fotos y las ventanas y es «sin dato» en el recuento.",
         "las claves tienen que tener el mismo tipo y el mismo valor para lo que no consta a los dos lados de un cruce "
         "(modelo-datos.md §4).",
         "reglas de transformación, «De qué se parte»: se igualan antes de cruzar y no se guardan en las tablas corregidas.",
         'fl["dia_fallo"] = a_milisegundos(fl["dia_fallo"], "fallos")\ncentro = df["datacenter"].fillna(SIN_DATO)',
         f"ninguna fecha cambia al pasar a milisegundos (el script para si alguna cambia); {fmt(c['fallos_detalle.filas'])} "
         f"fallos cruzados con su ventana.", "las claves cruzan con el mismo tipo; las tablas corregidas siguen igual.",
         "quitar las dos líneas."),
        ("dim_modelo", "dim_modelo · tabla nueva",
         "no existía: la capacidad está en cada fila y no hay fecha de compra, garantía ni precio.",
         "las tablas del análisis necesitan por modelo su capacidad, tipo, fabricante, garantía, compra y precio (§1).",
         "reglas de transformación §1, con las convenciones técnicas 1 y 2.",
         'dm["tipo_disco"] = np.select([cb <= LIMITE_ARRANQUE_BYTES, cb > LIMITE_ARRANQUE_BYTES], ["arranque", "datos"], "SIN_REGLA")\n'
         'valor, origen, usadas, motivo = coste_gb(capacidad_tb, fecha_compra)',
         f"{fmt(c['dim_modelo.modelos'])} modelos, {fmt(c['dim_modelo.arranque'])} de arranque y {fmt(c['dim_modelo.datos'])} "
         f"de datos; {fmt(c['dim_modelo.con_fecha_compra'])} con fecha de compra y {fmt(c['dim_modelo.con_precio'])} con precio; "
         f"los modelos sin precio suman {fmt(c['dim_modelo.dias_sin_precio'])} días de disco.",
         "data/processed/dim_modelo.parquet, una fila por modelo.", "borrar data/processed/dim_modelo.parquet."),
        ("dim_precio_gb", "dim_precio_gb · tabla nueva", "no existía.",
         "el disco nuevo que sustituye a uno que falla se paga al coste por GB del año del fallo (reglas, apartado 6).",
         "reglas de transformación §1: el coste el 1 de julio de cada año, con la misma regla que dim_modelo.",
         "coste_gb(cap, pd.Timestamp(year=ano, month=7, day=1))",
         f"{fmt(c['dim_precio_gb.filas'])} filas; los fallos de discos de datos de 2024 cuestan "
         f"{fmt(c['fallos_2024.coste_usd'])} dólares, y {fmt(c['fallos_2024.coste_garantia_usd'])} con garantía.",
         "data/processed/dim_precio_gb.parquet, una fila por capacidad y año.", "borrar data/processed/dim_precio_gb.parquet."),
        ("fotos_riesgo", "fotos_riesgo · tabla nueva",
         "las fotos mensuales traen todos los discos, la foto del día del fallo y ningún objetivo.",
         "la pregunta 4 necesita una fila por disco de datos y foto con lo que se sabía ese día y el objetivo a 30 días.",
         "reglas de transformación §3, con las convenciones técnicas 3 y 4; salen failure, date y cluster_id.",
         "for i in range(pf.num_row_groups):\n    t = pf.read_row_group(i, columns=columnas)\n    ...\n"
         "    escritor.write_table(out)",
         f"{fmt(c['fotos_riesgo.filas'])} filas, {fmt(c['fotos_riesgo.construccion'])} de construcción y "
         f"{fmt(c['fotos_riesgo.validacion'])} de validación; quedan fuera {fmt(x['fotos_del_dia_del_fallo']['fotos'])} fotos "
         f"del día del fallo y {fmt(x['discos_de_arranque']['fotos'])} de arranque; "
         f"{fmt(c['fotos_riesgo.filas_objetivo'])} filas con objetivo 1 para {fmt(c['fotos_riesgo.fallos_objetivo'])} fallos.",
         "data/processed/fotos_riesgo.parquet, escrito bloque a bloque.", "borrar data/processed/fotos_riesgo.parquet."),
        ("fallos_detalle", "fallos_detalle · tabla nueva", "la lista de fallos solo trae el disco y el día.",
         "las preguntas 1 a 4 necesitan de cada fallo su modelo, edad, aviso, sitio, tomo y coste.",
         "reglas de transformación §4 (cruces 1 a 6 y 13).",
         'fd = cruzar(ctx, 1, ..., fd, del_dia, ["serial_number", "dia_fallo"], ["serial_number", "fecha"])',
         f"{fmt(c['fallos_detalle.filas'])} fallos, {fmt(c['fallos_detalle.datos'])} de discos de datos; "
         f"{fmt(c['fallos_detalle.sin_aviso'])} sin aviso de {fmt(c['fallos_detalle.con_dia_anterior'])} con día anterior; "
         f"{fmt(c['fallos_detalle.coinciden'])} coinciden con el anterior de su tomo.",
         "data/processed/fallos_detalle.parquet, una fila por fallo.", "borrar data/processed/fallos_detalle.parquet."),
        ("vida_discos", "vida_discos · tabla nueva", "no existía una fila por disco.",
         "la supervivencia de la pregunta 2 y las altas y bajas del bloque 1.",
         "reglas de transformación §5, con la convención técnica 5.",
         'np.select([primer_fallo.notna(), desaparece, primer_fallo.isna()], ["fallo", "desaparece", "sigue"], "SIN_REGLA")',
         f"{fmt(c['vida_discos.filas'])} discos: {fmt(c['vida_discos.fallo'])} en fallo, {fmt(c['vida_discos.desaparece'])} "
         f"desaparecen y {fmt(c['vida_discos.sigue'])} siguen.",
         "data/processed/vida_discos.parquet, una fila por disco de datos.", "borrar data/processed/vida_discos.parquet."),
        ("dias_por_tramo", "dias_por_tramo · tabla nueva", "los días de disco están por modelo, centro y día, sin edad.",
         "la tasa por edad de la pregunta 2, la ajustada por centro de la 3 y la previsión del bloque 9.",
         "reglas de transformación §6, con las convenciones técnicas 6 y 7 (cruces 11 y 15).",
         'm["dias_disco"] = m["parte"] * m["dias_recuento"]',
         f"{fmt(c['dias_por_tramo.filas'])} filas; se reparten {fmt(c['dias_por_tramo.dias_repartidos'])} días de disco de "
         f"{fmt(c['dias_por_tramo.dias_recuento'])}; quedan sin repartir {fmt(c['dias_por_tramo.dias_sin_foto'])} en "
         f"{fmt(c['dias_por_tramo.celdas_sin_foto'])} celdas sin foto.",
         "data/processed/dias_por_tramo.parquet.", "borrar data/processed/dias_por_tramo.parquet."),
        ("inicio_trimestre", "inicio_trimestre · tabla nueva", "no existía.",
         "la previsión del bloque 9 usa los discos del primer día de cada trimestre con su edad.",
         "reglas de transformación §7 (cruce 14).",
         'd.groupby(["model", "capacidad_tb", "edad_anos_cumplidos"]).size()',
         f"{fmt(c['inicio_trimestre.filas'])} filas de {fmt(c['inicio_trimestre.trimestres'])} trimestres con "
         f"{fmt(c['inicio_trimestre.discos'])} discos; {fmt(c['inicio_trimestre.trimestres_iguales_al_recuento'])} "
         f"trimestres iguales al recuento, modelo a modelo.",
         "data/processed/inicio_trimestre.parquet.", "borrar data/processed/inicio_trimestre.parquet."),
        ("modelo_trimestre", "modelo_trimestre · tabla nueva", "no existía.", "la pregunta 1, por modelo y trimestre.",
         "reglas de transformación §8 (cruces 7, 8 y 15).",
         'm["pasa_minimo_ano"] = m["dias_disco_ano"] >= MINIMO_DIAS_ANO',
         f"{fmt(c['modelo_trimestre.filas'])} filas; {fmt(c['modelo_trimestre.fallos'])} fallos y "
         f"{fmt(c['modelo_trimestre.dias'])} días de disco; pasan el mínimo {fmt(c['modelo_trimestre.celdas_pasan'])} de "
         f"{fmt(c['modelo_trimestre.celdas_modelo_ano'])} celdas de modelo y año.",
         "data/processed/modelo_trimestre.parquet.", "borrar data/processed/modelo_trimestre.parquet."),
        ("centro_mes", "centro_mes · tabla nueva", "no existía.",
         "la tasa bruta por centro de la pregunta 3 y el reparto de los discos del bloque 1.",
         "reglas de transformación §9 (cruce 8).",
         'rd.groupby(["datacenter", "mes"]).agg(dias_disco=("discos", "sum"), fallos=("fallos", "sum"))',
         f"{fmt(c['centro_mes.filas'])} filas, {fmt(c['centro_mes.desde_sitio'])} desde julio de 2023.",
         "data/processed/centro_mes.parquet.", "borrar data/processed/centro_mes.parquet."),
    ]


def escribir_registro(raiz, r):
    """Añade al registro las fichas nuevas y devuelve el número de cada transformación y las fichas añadidas."""
    ruta = raiz / "config" / "modelo" / "registro-transformaciones.md"
    texto = ruta.read_text(encoding="utf-8")
    fichas = fichas_del_registro(r)
    numeros, nuevas = numerar_fichas(texto, [f[1] for f in fichas])
    hoy = dt.date.today().isoformat()
    añadir = "".join(ficha(numeros[f[1]], *f[1:], hoy) for f in fichas if f[1] in nuevas)
    if añadir:
        ruta.write_text(texto.rstrip("\n") + "\n" + añadir, encoding="utf-8")
    return {f[0]: numeros[f[1]] for f in fichas}, [numeros[t] for t in nuevas]


# =================================================================================================================
# 13. Informe para la persona, generado del JSON
# =================================================================================================================
NOMBRE_TABLA = {"dim_modelo": "dim_modelo", "dim_precio_gb": "dim_precio_gb", "fotos_riesgo": "fotos_riesgo",
                "fallos_detalle": "fallos_detalle", "vida_discos": "vida_discos", "dias_por_tramo": "dias_por_tramo",
                "inicio_trimestre": "inicio_trimestre", "modelo_trimestre": "modelo_trimestre", "centro_mes": "centro_mes"}


def informe_md(r):
    """Genera informes/transformacion-datos.md a partir del diccionario del JSON, con la estructura de el método."""
    res = r["resultado"]
    L = ["# Informe de transformación de datos", "", f"**Estado: {res['estado']}.** {res['resumen']}", ""]
    L += ["## Fuente", ""]
    L += [f"- **Entrada:** `{e['ruta']}`, {fmt(e['filas'])} filas y {fmt(e['columnas'])} columnas, huella "
          f"`{e['sha256'][:12]}…`." for e in r["entradas"]]
    L += [f"- **Salida:** las nueve tablas de `data/processed/` que lista «Dataset generado»." if r["salidas"]
          else "- **Salida:** ninguna; la ejecución paró antes de guardar.",
          "- **Contexto:** `config/negocio/reglas-transformacion.md` (aprobado el 17/11/2026), "
          "`reglas-negocio.md`, `modelo/modelo-datos.md`, el plan de cruces de `informes/modelado-datos.json` y "
          "`sector/precios_de_coste_discos.md`.",
          f"- **Ejecución:** {r['fecha_ejecucion']}, con Python {r['ejecucion']['python']}, pandas "
          f"{r['ejecucion']['pandas']} y pyarrow {r['ejecucion']['pyarrow']}. Fecha de los datos: {r['fecha_datos']}.", ""]
    L += ["## Objetivo", "",
          "Preparar las tablas con las que el análisis contesta las cuatro preguntas del caso: dos dimensiones de "
          "modelo y precio, la tabla de fotos con el objetivo a 30 días para el modelo de la pregunta 4, el detalle de "
          "cada fallo, la vida de cada disco y cuatro agregados de días de disco y fallos. No se calcula ninguna tasa, "
          "ranking ni modelo.", ""]
    L += ["## Transformaciones aplicadas", ""]
    if r["transformaciones"]:
        L += [f"- **{t['id']} · {t['transformacion']}** ({t['regla']}): {t['resultado']} Ficha {t['ficha']}."
              for t in r["transformaciones"]]
    else:
        L.append("- Ninguna: la ejecución paró antes de guardar.")
    L.append("")
    L += ["## Variables generadas", "",
          "Marcas: (P) usa información posterior a la fila; (O) sale del objetivo; (S) es suma o resta de otras.", ""]
    for v in r["variables_generadas"]:
        marcas = "".join(m for m, k in (("P", "informacion_posterior"), ("O", "sale_del_objetivo"), ("S", "suma_de_otras"))
                         if v[k])
        L.append(f"- `{v['columna']}`{' (' + marcas + ')' if marcas else ''}: {v['formula']}. De "
                 f"{', '.join('`' + c + '`' for c in v['columnas_origen'])}.")
    L += ["", "`falla_30d` no se suma entre filas para contar fallos: un fallo puede ser objetivo de dos fotos. Los "
          "fallos se cuentan en `fallos_detalle`.", ""]
    L += ["## Transformaciones pendientes", ""]
    L += [f"- **{p['id']}** ({p['tabla']}, `{p['columna']}`): {p['pregunta']}" for p in r["pendientes"]] or [
        "- Ninguna: cada columna de las reglas de transformación se llenó con su regla."]
    L.append("")
    L += ["## Cambios estructurales", ""]
    for cg in r["cambios_granularidad"]:
        L.append(f"- De «{cg['antes']}» a «{cg['despues']}»:")
        L += [f"  - {s['magnitud']}: {fmt(s['antes'])} antes y {fmt(s['despues'])} después; "
              f"{'coinciden' if s['coincide'] else 'NO coinciden'}." for s in cg["sumas_control"]]
    L += ["", "| Cruce | Etiqueta | Cardinalidad esperada | Observada | Filas antes | Filas después | Sin pareja en la partida | Hecho |",
          "|---:|---|---|---|---:|---:|---:|---|"]
    for c in r["cruces"]:
        L.append(f"| {c['orden']} | {c['etiqueta']} | {c['cardinalidad_esperada']} | {c['cardinalidad_observada']} | "
                 f"{fmt(c['filas_antes'])} | {fmt(c['filas_despues'])} | {fmt(c['huerfanas_partida']['filas'])} | "
                 f"{'sí' if c['hecho'] else 'no: ' + str(c['motivo_parada'])} |")
    L.append("")
    L += ["## Validación", ""]
    L += [f"- {v['validacion']}: {v['resultado']}." for v in r["validaciones"]]
    L += ["", "**Comprobaciones de las reglas** (no paran el guardado; si una no pasa, el estado es AVISO):", ""]
    L += [f"- {v['comprobacion']}: {v['resultado']}{'. ' + v['detalle'] if v.get('detalle') else ''}."
          for v in r["comprobaciones"]]
    L.append("")
    L += ["## Registro de exclusiones", "", "| Clase | Qué sale | De qué cálculo | Recuentos |", "|---|---|---|---|"]
    for e in r["exclusiones"]:
        rec = "; ".join(f"{k.replace('_', ' ')}: {fmt(v)}" for k, v in e["recuentos"].items())
        L.append(f"| {e['clase'].replace('_', ' ')} | {e['que_sale']} | {e['sale_de']} | {rec} |")
    otros = next((e.get("otros") for e in r["exclusiones"] if e["clase"] == "fallos_sin_objetivo"), None)
    if otros:
        L += ["", "Fallos sin objetivo que no caen en ninguna clase, uno a uno:", ""]
        L += [f"- `{o['serial_number']}`, fallo el {o['dia_fallo']}, última foto anterior "
              f"{o['ultima_foto_anterior'] or 'ninguna'}." for o in otros]
    L += ["", "Los modelos que no llegan al mínimo y los años de edad con menos de 20 fallos no salen de ninguna tabla: se "
          "marcan y el análisis los enseña aparte. Las 228 filas que quitó la corrección están en R-007.", ""]
    L += ["## Dataset generado", ""]
    L += [f"- `{s['ruta']}`: {fmt(s['filas'])} filas y {fmt(s['columnas'])} columnas; una fila es {s['que_es_una_fila']}."
          for s in r["salidas"]] or ["- Ninguno."]
    L.append("")
    L += ["## Datos personales", ""]
    L += [f"- {t}" for t in r["datos_personales_texto"]]
    L.append("")
    L += ["## Pendiente para el modelo", ""]
    if r["particion"]:
        p = r["particion"]
        L += [f"- **Partición** por `{p['columna_fecha']}`: desarrollo del {p['desarrollo']['desde']} al "
              f"{p['desarrollo']['hasta']} y validación del {p['validacion']['desde']} al {p['validacion']['hasta']}, "
              f"los dos días incluidos ({p['fuente']}). Ninguna fila de fotos_riesgo queda fuera de los dos tramos."]
    agrupadas = {}
    for c in r["pendiente_modelo"]:
        agrupadas.setdefault(c["tipo"], []).append(c)
    for tipo in ("categorica", "codigo_numerico", "binaria"):
        for c in agrupadas.get(tipo, []):
            L.append(f"- `{c['columna']}` ({tipo.replace('_', ' ')}, grupo {c['grupo'].replace('_', ' ')}): "
                     f"{fmt(c['valores']) if c['valores'] is not None else 'dos'} valores, sin orden real.")
    mag = agrupadas.get("magnitud", [])
    L.append(f"- {len(mag)} magnitudes, con su unidad y su rango en `pendiente_modelo` del JSON; las de la foto que "
             f"no están en las reglas van en el grupo «no previstas», y la preselección del paso 5 decide cuáles entran.")
    L.append("")
    L += ["## Teoría aplicada", ""]
    L += [f"- {t}" for t in r["teoria"]]
    L.append("")
    L += ["## Límites", ""]
    L += [f"- {t}" for t in r["limites"]]
    L.append("")
    return "\n".join(L)


# =================================================================================================================
# 14. Ejecución
# =================================================================================================================
def base_resultado(fecha_ejecucion):
    """El JSON vacío, con el bloque común, para escribirlo también si el script para o falla."""
    return {"metodo": METODO, "version_metodo": VERSION_METODO, "script": SCRIPT, "fecha_datos": FECHA_DATOS,
            "fecha_ejecucion": fecha_ejecucion, "entradas": [], "resultado": {}, "pendientes": [], "salidas": [],
            "transformaciones": [], "variables_generadas": [], "cambios_granularidad": [], "cruces": [],
            "validaciones": [], "comprobaciones": [], "pendiente_modelo": [], "particion": None,
            "grupos_fotos_riesgo": {}, "exclusiones": [], "cifras_de_control": {}, "fichas_nuevas": [],
            "parametros": {"horas_ano": HORAS_ANO, "dias_ano": DIAS_ANO, "limite_arranque_bytes": LIMITE_ARRANQUE_BYTES,
                           "inicio_sitio": dia(INICIO_SITIO), "horizonte_dias": HORIZONTE_DIAS,
                           "minimo_dias_ano": MINIMO_DIAS_ANO, "coste_cambio_usd": COSTE_CAMBIO_USD,
                           "etiqueta_sin_dato": SIN_DATO, "inicio_inferido": dia(INICIO_INFERIDO),
                           "modelos_sin_precio": SIN_PRECIO},
            "teoria": TEORIA, "datos_personales_texto": [], "limites": [],
            "ejecucion": {"python": platform.python_version(), "pandas": pd.__version__, "pyarrow": pa.__version__,
                          "numpy": np.__version__, "segundos_por_parte": {}}}


def datos_personales(raiz):
    """El apartado «Datos personales», con lo que diga config/fuentes/proteccion-datos.json si existe."""
    ruta = raiz / "config" / "fuentes" / "proteccion-datos.json"
    if ruta.exists():
        return ["Existe config/fuentes/proteccion-datos.json: la protección se describe allí.",
                "Esta transformación no usa ni deja ninguna columna de datos personales."]
    return ["No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección.",
            "No hay datos de personas (reglas, apartado 9): el número de serie identifica un disco, no a una persona.",
            "Esta transformación no usa ni deja ninguna columna de datos personales."]


def transformar(raiz):
    """Construye las nueve tablas del caso que está en raiz y devuelve el diccionario del JSON."""
    t0 = time.time()
    tiempos = {}
    fecha_ejecucion = dt.datetime.now().replace(microsecond=0).isoformat()
    r = base_resultado(fecha_ejecucion)
    r["datos_personales_texto"] = datos_personales(raiz)
    ctx = {"cruces": {}, "pendientes_precio": []}
    proc = raiz / "data" / "processed"
    parcial = proc / "fotos_riesgo.parquet.parcial"
    try:
        # 14.1 Entradas: JSON anteriores, huellas y plan de cruces
        ctx["plan"] = leer_entradas(raiz, r)
        tiempos["entradas"] = round(time.time() - t0, 1)

        # 14.2 Tablas pequeñas: Calendario, recuento, lista de fallos y ventanas (estas, solo sus columnas)
        cal = pd.read_parquet(raiz / CALENDARIO, columns=["fecha", "ano", "trimestre", "mes", "periodo"])
        cal["fecha"] = cal["fecha"].astype("datetime64[ms]")
        rec = pd.read_parquet(raiz / RECUENTO)
        fl = pd.read_parquet(raiz / LISTA_FALLOS)
        fl["dia_fallo"] = a_milisegundos(fl["dia_fallo"], "fallos")
        if fl.duplicated(["serial_number", "dia_fallo"]).any():
            raise Parada("la lista de fallos tiene la clave (serial_number, dia_fallo) repetida")
        fl = fl.reset_index(drop=True)
        fl["_id"] = np.arange(len(fl))
        ve = pd.read_parquet(raiz / VENTANAS, columns=["fecha", "dia_fallo", "serial_number", "model", "capacity_bytes",
                                                       "failure", *SITIO, "smart_9_raw", *CONTADORES])
        ve["dia_fallo"] = a_milisegundos(ve["dia_fallo"], "ventanas")
        ve["fecha"] = ve["fecha"].astype("datetime64[ms]")

        # 14.3 Primera pasada por las fotos y primera aparición de cada disco, antes de recorrer los bloques
        primeras, fechas_fotos = primera_pasada(raiz / FOTOS)
        pv = (ve.sort_values(["serial_number", "fecha"]).groupby("serial_number", sort=False).head(1)
              [["serial_number", "fecha", "model", "smart_9_raw"]]
              .rename(columns={"fecha": "primer_dia_ventana", "model": "model_ventana", "smart_9_raw": "horas_ventana"}))
        disco = primeras.merge(pv, on="serial_number", how="outer", validate="one_to_one")
        disco["primera_aparicion"] = disco[["primera_foto", "primer_dia_ventana"]].min(axis=1).astype("datetime64[ms]")
        primera = disco.set_index("serial_number")["primera_aparicion"]
        tiempos["primera_pasada"] = round(time.time() - t0, 1)

        # 14.4 Las dos dimensiones, que usan las demás tablas
        dm = construir_dim_modelo(rec, primeras, ctx)
        dpg = construir_dim_precio_gb(dm, cal, ctx)

        # 14.5 El recuento con su modelo y su Calendario (cruces 7 y 8)
        antes = (rec["discos"].sum(), rec["fallos"].sum())
        rec = cruzar(ctx, 7, "recuento", "recuento", "dim_modelo", rec, dm[["model", "tipo_disco"]], ["model"],
                     ["model"]).drop(columns=["_merge"])
        suma_de_control(ctx, 7, "recuento", "discos", antes[0], rec["discos"].sum())
        suma_de_control(ctx, 7, "recuento", "fallos", antes[1], rec["fallos"].sum())
        rec = cruzar(ctx, 8, "recuento", "recuento", "Calendario", rec, cal[["fecha", "ano", "trimestre", "periodo"]],
                     ["fecha"], ["fecha"]).drop(columns=["_merge"])
        suma_de_control(ctx, 8, "recuento", "discos", antes[0], rec["discos"].sum())
        rec["mes"] = inicio_de_mes(rec["fecha"])
        rd = rec.loc[rec["tipo_disco"] == "datos"].copy()

        # 14.6 fallos_detalle, la parte de las ventanas
        fd = construir_fallos(ctx, fl, ve, dm, dpg, cal, primera)
        tiempos["fallos"] = round(time.time() - t0, 1)

        # 14.7 Segunda pasada: fotos_riesgo bloque a bloque y lo acumulado
        acu = segunda_pasada(ctx, raiz, dm, cal, primera, fl, parcial)
        r["grupos_fotos_riesgo"] = acu["grupos"]
        tiempos["segunda_pasada"] = round(time.time() - t0, 1)

        # 14.8 fallos_detalle, lo que viene de las fotos (cruces 12 y 13)
        fd["ultima_foto_anterior"] = fd["_id"].map(acu["ultima"]).astype("datetime64[ms]")
        objetivos = (pd.concat(acu["pares"], ignore_index=True).drop_duplicates() if acu["pares"]
                     else pd.DataFrame({"serial_number": pd.Series([], dtype="str"),
                                        "dia_fallo": pd.Series([], dtype="datetime64[ms]")}))
        fd = fd.merge(objetivos.assign(_obj=True), on=["serial_number", "dia_fallo"], how="left", validate="one_to_one")
        fd["objetivo_de_alguna_foto"] = fd["_obj"].fillna(False).astype(bool)
        fd = fd.drop(columns=["_obj"])

        # 14.9 Las tablas de lo acumulado
        ultima_de_los_datos = max(fechas_fotos)
        vd = construir_vida(ctx, disco, dm, fd, acu["estado"], ultima_de_los_datos)
        dpt, info_tramo = construir_tramo(ctx, acu, rd, fd, vd)
        ini, info_inicio = construir_inicio(ctx, acu, rd, cal)
        mt, info_mt = construir_modelo_trimestre(ctx, rd, fd, dm)
        cm = construir_centro_mes(ctx, rd, cal)
        x = clases_sin_objetivo(fd, primeras, cal)
        r["exclusiones"] = exclusiones(fd, rec, rd, dm, acu, info_tramo, x)
        tiempos["agregados"] = round(time.time() - t0, 1)

        # 14.10 Las tablas, con sus columnas en el orden de las reglas
        fd_out = fd[["serial_number", "dia_fallo", "model", "capacidad_tb", "fabricante", "tipo_disco", "garantia_anos",
                     "horas_al_fallar", "edad_al_fallar_anos", "edad_de_horas", "en_garantia", "hay_dia_anterior",
                     "avisa_dia_anterior", "sin_aviso", "datacenter", "vault_id", "pod_id", "pod_slot_num", "tomo",
                     "plazo_reconstruccion_dias", "dias_desde_anterior_del_tomo", "coincide_con_anterior",
                     "precio_nuevo_usd", "coste_fallo_usd", "coste_fallo_garantia_usd", "ultima_foto_anterior",
                     "objetivo_de_alguna_foto", "periodo", "ano", "trimestre", "mes", "primer_fallo_del_disco"]]
        vd_out = vd[["serial_number", "model", "primera_aparicion", "edad_entrada_anos", "ultima_foto", "primer_fallo",
                     "evento", "fecha_fin", "edad_fin_anos", "avisa_ultima_foto", "desaparece_avisando"]]
        dm_out = dm[["model", "capacity_bytes", "capacidad_tb", "tipo_disco", "fabricante", "garantia_anos",
                     "fecha_compra", "coste_gb_compra", "precio_usd", "origen_precio"]]
        dpg_out = dpg[["capacidad_tb", "ano", "coste_gb", "origen", "capacidades_usadas"]]
        tablas = {"dim_modelo": dm_out, "dim_precio_gb": dpg_out, "fallos_detalle": fd_out, "vida_discos": vd_out,
                  "dias_por_tramo": dpt, "inicio_trimestre": ini, "modelo_trimestre": mt, "centro_mes": cm}

        # 14.11 Cifras de control, que la sesión principal compara con las de referencia
        datos_f = fd["tipo_disco"] == "datos"
        desde = fd["dia_fallo"] >= INICIO_SITIO
        f24 = fd.loc[datos_f & (fd["ano"] == 2024)]
        st6 = dm.set_index("model").reindex(["ST6000DX000"])
        con_horas = fd.loc[datos_f & fd["hay_dia_anterior"]]
        con_tomo = fd.loc[datos_f & desde & fd["tomo"].notna()]
        pares_obj = pd.concat(acu["pares"], ignore_index=True) if acu["pares"] else objetivos
        c = {
            "dim_modelo.modelos": len(dm), "dim_modelo.arranque": int((dm["tipo_disco"] == "arranque").sum()),
            "dim_modelo.datos": int((dm["tipo_disco"] == "datos").sum()),
            "dim_modelo.con_fecha_compra": int(dm["fecha_compra"].notna().sum()),
            "dim_modelo.con_precio": int(dm["precio_usd"].notna().sum()),
            "dim_modelo.dias_sin_precio": int(rd.loc[rd["model"].isin(dm.loc[(dm["tipo_disco"] == "datos")
                                                                            & dm["precio_usd"].isna(), "model"]),
                                                     "discos"].sum()),
            "dim_modelo.ST6000DX000.mes_compra": (None if st6["fecha_compra"].isna().all()
                                                  else st6["fecha_compra"].iloc[0].strftime("%Y-%m")),
            "dim_modelo.ST6000DX000.precio_usd": (None if st6["precio_usd"].isna().all()
                                                  else round(float(st6["precio_usd"].iloc[0]), 2)),
            "dim_precio_gb.filas": len(dpg),
            "fallos_2024.fallos": len(f24), "fallos_2024.coste_usd": round(float(f24["coste_fallo_usd"].sum())),
            "fallos_2024.coste_garantia_usd": round(float(f24["coste_fallo_garantia_usd"].sum())),
            "fotos_riesgo.filas": sum(acu["filas"].values()),
            "fotos_riesgo.construccion": acu["filas"].get("construcción", 0),
            "fotos_riesgo.validacion": acu["filas"].get("validación", 0),
            "fotos_riesgo.objetivo_construccion": acu["objetivo"].get("construcción", 0),
            "fotos_riesgo.objetivo_validacion": acu["objetivo"].get("validación", 0),
            "fotos_riesgo.filas_objetivo": sum(acu["objetivo"].values()),
            "fotos_riesgo.pares_foto_fallo": acu["n_pares"],
            "fotos_riesgo.fallos_objetivo": int(pares_obj.drop_duplicates().shape[0]),
            "fotos_riesgo.anterior_un_mes": acu["meses"]["uno"],
            "fotos_riesgo.anterior_mas_de_un_mes": acu["meses"]["mas_de_uno"],
            "fotos_riesgo.sin_anterior": acu["meses"]["ninguno"],
            "fallos_detalle.filas": len(fd), "fallos_detalle.datos": int(datos_f.sum()),
            "fallos_detalle.datos_construccion": int((datos_f & (fd["periodo"] == "construcción")).sum()),
            "fallos_detalle.datos_validacion": int((datos_f & (fd["periodo"] == "validación")).sum()),
            "fallos_detalle.arranque": int((fd["tipo_disco"] == "arranque").sum()),
            "fallos_detalle.sin_fila_del_dia": int((~fd["con_fila_del_dia"]).sum()) if "con_fila_del_dia" in fd else None,
            "fallos_detalle.sin_horas": int((~fd["edad_de_horas"]).sum()),
            "fallos_detalle.sin_dia_anterior": int((datos_f & ~fd["hay_dia_anterior"]).sum()),
            "fallos_detalle.con_dia_anterior": len(con_horas),
            "fallos_detalle.sin_aviso": int(con_horas["sin_aviso"].sum()),
            "fallos_detalle.desde_sitio": int((datos_f & desde).sum()),
            "fallos_detalle.desde_sitio_sin_centro": int((datos_f & desde & fd["datacenter"].isna()).sum()),
            "fallos_detalle.desde_sitio_sin_tomo": int((datos_f & desde & fd["tomo"].isna()).sum()),
            "fallos_detalle.con_tomo": len(con_tomo), "fallos_detalle.tomos": int(con_tomo["tomo"].nunique()),
            "fallos_detalle.coinciden": int(con_tomo["coincide_con_anterior"].fillna(False).sum()),
            "fallos_detalle.parte_en_garantia_pct": round(100 * float(fd.loc[datos_f, "en_garantia"].mean()), 1)
            if datos_f.any() else None,
            "fallos_detalle.sin_objetivo": len(x),
            "vida_discos.filas": len(vd), "vida_discos.solo_ventana": int(vd["primera_foto"].isna().sum()),
            "vida_discos.fallo": int((vd["evento"] == "fallo").sum()),
            "vida_discos.desaparece": int((vd["evento"] == "desaparece").sum()),
            "vida_discos.sigue": int((vd["evento"] == "sigue").sum()),
            "vida_discos.desaparece_avisando": int(vd["desaparece_avisando"].sum()),
            "vida_discos.entran_4_anos_o_mas": int((vd["edad_entrada_anos"] >= 4).sum()),
            "vida_discos.fallan_antes_de_su_primera_foto": int((vd["primer_fallo"] < vd["primera_foto"]).sum()),
            "dias_por_tramo.filas": len(dpt), "dias_por_tramo.filas_solo_fallos": info_tramo["filas_solo_fallos"],
            "dias_por_tramo.dias_repartidos": round(float(dpt["dias_disco"].sum())),
            "dias_por_tramo.dias_recuento": round(info_tramo["dias_recuento"]),
            "dias_por_tramo.fallos": int(dpt["fallos"].sum()),
            "dias_por_tramo.fallos_sin_dias": info_tramo["fallos_sin_dias"],
            "dias_por_tramo.dias_sin_foto": round(info_tramo["dias_sin_foto"]),
            "dias_por_tramo.celdas_sin_foto": info_tramo["celdas_sin_foto"],
            "dias_por_tramo.fallos_recuento_sin_foto": info_tramo["fallos_recuento_sin_foto"],
            "inicio_trimestre.filas": len(ini), "inicio_trimestre.trimestres": info_inicio["trimestres"],
            "inicio_trimestre.discos": int(ini["discos"].sum()),
            "inicio_trimestre.trimestres_iguales_al_recuento": info_inicio["trimestres_iguales_al_recuento"],
            "modelo_trimestre.filas": len(mt), "modelo_trimestre.filas_fallos_iguales": info_mt["filas_fallos_iguales"],
            "modelo_trimestre.fallos": int(mt["fallos"].sum()), "modelo_trimestre.dias": int(mt["dias_disco"].sum()),
            "modelo_trimestre.celdas_modelo_ano": info_mt["celdas_modelo_ano"],
            "modelo_trimestre.celdas_pasan": info_mt["celdas_pasan"],
            "modelo_trimestre.modelos_pasan": info_mt["modelos_pasan"],
            "centro_mes.filas": len(cm), "centro_mes.desde_sitio": int(cm["con_sitio"].sum()),
        }
        r["cifras_de_control"] = c

        # 14.12 Cambios de granularidad, con sus sumas de control calculadas aquí
        sumas = lambda lista: [{"magnitud": m, "antes": float(a), "despues": float(d_),  # noqa: E731
                                "coincide": bool(np.isclose(a, d_, rtol=0, atol=1e-6))} for m, a, d_ in lista]
        con_foto_dias = info_tramo["dias_recuento"] - info_tramo["dias_sin_foto"]
        r["cambios_granularidad"] = [
            {"antes": "un disco el día 1 de un mes (fotos)", "despues": QUE_ES_UNA_FILA["fotos_riesgo"],
             "sumas_control": sumas([("filas: fotos de datos menos las del día del fallo",
                                      acu["fotos_datos"] - acu["fotos_dia_fallo"], c["fotos_riesgo.filas"])])},
            {"antes": "un disco un día de la ventana de un fallo, y la lista de fallos",
             "despues": QUE_ES_UNA_FILA["fallos_detalle"],
             "sumas_control": sumas([("fallos de la lista", len(fl), len(fd))])},
            {"antes": "fotos y ventanas", "despues": QUE_ES_UNA_FILA["vida_discos"],
             "sumas_control": sumas([("discos de datos distintos", int(disco["serial_number"].isin(vd["serial_number"]).sum()),
                                      len(vd))])},
            {"antes": "un día, un modelo, una capacidad y un centro (recuento)", "despues": QUE_ES_UNA_FILA["dias_por_tramo"],
             "sumas_control": sumas([("días de disco de las celdas con foto", con_foto_dias, dpt["dias_disco"].sum()),
                                     ("fallos de discos de datos de la lista", int(datos_f.sum()), dpt["fallos"].sum())])},
            {"antes": "fotos del primer día de cada trimestre", "despues": QUE_ES_UNA_FILA["inicio_trimestre"],
             "sumas_control": sumas([("discos de datos de esas fotos",
                                      sum(int(a["discos"].sum()) for a in acu["inicio"]), ini["discos"].sum())])},
            {"antes": "un día, un modelo, una capacidad y un centro (recuento)", "despues": QUE_ES_UNA_FILA["modelo_trimestre"],
             "sumas_control": sumas([("días de disco de datos", rd["discos"].sum(), mt["dias_disco"].sum()),
                                     ("fallos de discos de datos de la lista", int(datos_f.sum()), mt["fallos"].sum())])},
            {"antes": "un día, un modelo, una capacidad y un centro (recuento)", "despues": QUE_ES_UNA_FILA["centro_mes"],
             "sumas_control": sumas([("días de disco de datos", rd["discos"].sum(), cm["dias_disco"].sum()),
                                     ("fallos del recuento de discos de datos", rd["fallos"].sum(), cm["fallos"].sum())])},
        ]

        # 14.13 Validaciones: si alguna falla, no se guarda ninguna tabla
        V = []

        def validar(texto, ok):
            """Apunta una validación con su resultado calculado."""
            V.append({"validacion": texto, "resultado": "pasa" if ok else "falla"})

        validar("cada bloque de las fotos es un mes y van en orden de fecha", len(fechas_fotos) == len(set(fechas_fotos)))
        validar("ninguna edad negativa ni vacía en las fotos", acu["edades_negativas"] == 0)
        validar("cada columna de fotos_riesgo está en un solo grupo",
                acu["comprobacion_grupos"]["sin_grupo"] + acu["comprobacion_grupos"]["en_dos_grupos"]
                + acu["comprobacion_grupos"]["que_faltan"] == 0)
        validar("ningún modelo de las fotos sin fila en dim_modelo",
                ctx["cruces"][(9, "fotos")]["huerfanas_partida"]["filas"] == 0)
        validar("ningún tipo de disco ni evento sin regla", not (dm["tipo_disco"] == "SIN_REGLA").any()
                and not (vd["evento"] == "SIN_REGLA").any())
        validar("ningún cruce gana filas", all(cr["hecho"] for cr in ctx["cruces"].values()))
        validar("todas las sumas de control de los cruces coinciden",
                all(s["coincide"] for cr in ctx["cruces"].values() for s in cr["sumas_control"]))
        validar("todas las sumas de control de los cambios de granularidad coinciden",
                all(s["coincide"] for cg in r["cambios_granularidad"] for s in cg["sumas_control"]))
        for nombre, tabla in tablas.items():
            validar(f"{nombre}: clave {', '.join(CLAVES[nombre])} única", not tabla.duplicated(CLAVES[nombre]).any())
        validar("fotos_riesgo: clave serial_number, fecha única (cada bloque es una fecha distinta)",
                acu["claves_repetidas"] == 0 and c["fotos_riesgo.filas"] == pq.ParquetFile(parcial).metadata.num_rows)
        r["validaciones"] = V

        # 14.14 Comprobaciones de las reglas, que no paran el guardado
        K = []
        cf = fd.loc[datos_f & desde].assign(centro=lambda d: d["datacenter"].fillna(SIN_DATO)).groupby("centro").size()
        cr_ = rd.loc[rd["fecha"] >= INICIO_SITIO].groupby("datacenter")["fallos"].sum()
        cr_ = cr_.loc[cr_ > 0]
        igual_centro = cf.sort_index().to_dict() == {k: int(v) for k, v in cr_.sort_index().items()}
        K.append({"comprobacion": "los fallos de cada centro desde el 01/07/2023 son los mismos en fallos_detalle y en "
                                  "el recuento", "resultado": "pasa" if igual_centro else "no pasa",
                  "detalle": "; ".join(f"{k}: {int(v)}" for k, v in cf.items())})
        K.append({"comprobacion": "en cada fila de modelo_trimestre, los fallos de la lista son los del recuento",
                  "resultado": "pasa" if info_mt["filas_fallos_iguales"] == len(mt) else "no pasa",
                  "detalle": f"{fmt(info_mt['filas_fallos_iguales'])} de {fmt(len(mt))} filas"})
        K.append({"comprobacion": "el primer día de cada trimestre, los discos de la foto son los del recuento, modelo a "
                                  "modelo", "resultado": "pasa" if info_inicio["trimestres_iguales_al_recuento"]
                                  == info_inicio["trimestres"] else "no pasa",
                  "detalle": f"{info_inicio['trimestres_iguales_al_recuento']} de {info_inicio['trimestres']} trimestres"})
        K.append({"comprobacion": "todos los fallos tienen la fila del día del fallo en su ventana",
                  "resultado": "pasa" if c["fallos_detalle.sin_fila_del_dia"] == 0 else "no pasa",
                  "detalle": f"{c['fallos_detalle.sin_fila_del_dia']} sin ella"})
        K.append({"comprobacion": "cada disco que desaparece avisando tiene su fila en dias_por_tramo",
                  "resultado": "pasa" if info_tramo["desaparecen_avisando_sin_fila"] == 0 else "no pasa",
                  "detalle": f"{info_tramo['desaparecen_avisando_sin_fila']} sin fila"})
        r["comprobaciones"] = K

        # 14.15 Variables, transformaciones, partición y lo pendiente para el modelo
        r["variables_generadas"] = [{"tabla": t, "columna": col, "formula": f, "columnas_origen": o, "unidad": u,
                                     "informacion_posterior": p, "sale_del_objetivo": s, "suma_de_otras": su}
                                    for t, col, f, o, u, p, s, su in VARIABLES]
        construccion = cal.loc[cal["periodo"] == "construcción", "fecha"]
        validacion = cal.loc[cal["periodo"] == "validación", "fecha"]
        r["particion"] = {"columna_fecha": "fecha",
                          "desarrollo": {"desde": dia(construccion.min()), "hasta": dia(construccion.max())},
                          "validacion": {"desde": dia(validacion.min()), "hasta": dia(validacion.max())},
                          "fuente": "reglas-negocio §7"}
        r["pendiente_modelo"] = pendiente_modelo(acu)
        r["pendientes"] = [{"id": f"P-{i + 1:02d}", "tabla": p["tabla"], "columna": p["columna"],
                            "pregunta": f"Ninguna regla da el precio de {p['modelo']}: {p['motivo']}.",
                            "opciones": ["que la persona responsable fije el criterio en las reglas de transformación"]}
                           for i, p in enumerate(ctx["pendientes_precio"])]
        r["limites"] = [
            "La fecha de compra y el precio de dim_modelo son una ficha de hoy, calculada con todo el periodo: no "
            "entran en fotos_riesgo.",
            "En las tablas agregadas, «mes» es el primer día del mes y la clave de trimestre lleva el año al lado "
            "(«ano» y «trimestre» del Calendario), porque el trimestre del Calendario va de 1 a 4.",
            "suma_contadores_sin_188 queda vacía cuando los cuatro contadores lo están: un contador vacío no es un cero "
            "(reglas, apartado 5).",
            "coincide_con_anterior queda vacía cuando no hay días desde el anterior del tomo (el primero de su tomo o "
            "sin tomo), como dias_desde_anterior_del_tomo.",
            "En dias_por_tramo, las filas que solo tienen fallos dejan sus días de disco vacíos: hubo discos, pero "
            "ninguna foto con que repartir sus días.",
            "Las fotos de dias_por_tramo e inicio_trimestre son todas las de discos de datos, también la del día del "
            "fallo, porque ese día el disco está en servicio y cuenta como día de disco.",
            "No se calcula ninguna tasa, intervalo, ranking ni previsión: es el análisis de las preguntas 1 a 3.",
        ]
        if any(v["resultado"] == "falla" for v in V):
            fallan = [v["validacion"] for v in V if v["resultado"] == "falla"]
            raise Parada("no pasan estas validaciones: " + "; ".join(fallan))

        # 14.16 Guardar: fotos_riesgo pasa de parcial a definitiva y las demás se escriben ahora
        destino = raiz / SALIDA["fotos_riesgo"]
        parcial.replace(destino)
        for nombre, tabla in tablas.items():
            pq.write_table(pa.Table.from_pandas(tabla, preserve_index=False), raiz / SALIDA[nombre])
        r["salidas"] = []
        for nombre in QUE_ES_UNA_FILA:
            md = pq.ParquetFile(raiz / SALIDA[nombre]).metadata
            r["salidas"].append({"tabla": nombre, "ruta": SALIDA[nombre], "sha256": sha256(raiz / SALIDA[nombre]),
                                 "filas": md.num_rows, "columnas": md.num_columns,
                                 "que_es_una_fila": QUE_ES_UNA_FILA[nombre]})
        tiempos["guardar"] = round(time.time() - t0, 1)

        # 14.17 Las huellas de la entrada, iguales al terminar
        cambiadas = [ruta for ruta, h in r["huellas_inicio"].items() if sha256(raiz / ruta) != h]
        r["validaciones"].append({"validacion": "las huellas de las tablas corregidas son las mismas al terminar",
                                  "resultado": "pasa" if not cambiadas else "falla"})
        if cambiadas:
            raise Parada(f"cambió la huella de {cambiadas}")

        # 14.18 Registro de transformaciones y transformaciones del JSON
        numeros, r["fichas_nuevas"] = escribir_registro(raiz, r)
        resultado_de = {
            "igualacion": f"{fmt(len(fd))} fallos cruzados con dia_fallo en milisegundos; el centro vacío como «sin dato» "
                          f"al cruzar fotos y ventanas con el recuento.",
            "dim_modelo": f"{fmt(c['dim_modelo.modelos'])} modelos, {fmt(c['dim_modelo.con_precio'])} con precio.",
            "dim_precio_gb": f"{fmt(c['dim_precio_gb.filas'])} filas.",
            "fotos_riesgo": f"{fmt(c['fotos_riesgo.filas'])} filas, {fmt(c['fotos_riesgo.filas_objetivo'])} con objetivo 1.",
            "fallos_detalle": f"{fmt(c['fallos_detalle.filas'])} fallos.",
            "vida_discos": f"{fmt(c['vida_discos.filas'])} discos.",
            "dias_por_tramo": f"{fmt(c['dias_por_tramo.filas'])} filas.",
            "inicio_trimestre": f"{fmt(c['inicio_trimestre.filas'])} filas.",
            "modelo_trimestre": f"{fmt(c['modelo_trimestre.filas'])} filas.",
            "centro_mes": f"{fmt(c['centro_mes.filas'])} filas.",
        }
        r["transformaciones"] = [{"id": f"T-{i + 1:02d}", "transformacion": texto, "columnas": cols,
                                  "regla": f"reglas de transformación {regla}" if regla.startswith("§") else regla,
                                  "ficha": numeros[clave], "resultado": resultado_de[clave]}
                                 for i, (clave, texto, cols, regla) in enumerate(TRANSFORMACIONES)]
        r["artefactos"] = [s["ruta"] for s in r["salidas"]]

        # 14.19 Estado
        no_pasan = [k["comprobacion"] for k in K if k["resultado"] != "pasa"]
        estado = "OK" if not r["pendientes"] and not no_pasan else "AVISO"
        r["resultado"] = {
            "estado": estado, "riesgo": "bajo" if estado == "OK" else "medio",
            "resumen": (f"Nueve tablas en data/processed/: {fmt(c['fotos_riesgo.filas'])} fotos de riesgo, "
                        f"{fmt(c['fallos_detalle.filas'])} fallos y {fmt(c['vida_discos.filas'])} discos, con todas las "
                        f"validaciones en verde. " + (f"{len(no_pasan)} comprobaciones de las reglas no pasan y "
                                                      f"{len(r['pendientes'])} celdas quedan pendientes." if estado == "AVISO"
                                                      else "Ninguna celda queda pendiente.")),
            "artefactos": r["artefactos"] + ["informes/transformacion-datos.json", "informes/transformacion-datos.md",
                                             "config/modelo/registro-transformaciones.md"],
            "siguiente": "analisis-exploratorio, con las tablas de data/processed/; el objetivo de fotos_riesgo solo con "
                         "el periodo de construcción"}
    except Parada as e:
        r["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": f"La transformación para: {e}",
                          "artefactos": ["informes/transformacion-datos.json", "informes/transformacion-datos.md"],
                          "siguiente": "resolver el motivo de la parada y volver a ejecutar"}
        r["salidas"] = []
        if "cruce" in str(e):
            r["pendientes"].append({"id": f"P-{len(r['pendientes']) + 1:02d}", "tabla": "", "columna": "",
                                    "pregunta": f"Un cruce paró: {e}", "opciones": ["revisar la clave del cruce"]})
    except Exception as e:  # noqa: BLE001
        r["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"Fallo técnico: {type(e).__name__}: {e}",
                          "artefactos": ["informes/transformacion-datos.json", "informes/transformacion-datos.md"],
                          "siguiente": "corregir el script y volver a ejecutar"}
        r["salidas"] = []
        raise
    finally:
        if parcial.exists():
            parcial.unlink()
        r["cruces"] = [dict(v) for v in ctx["cruces"].values()]
        tiempos["total"] = round(time.time() - t0, 1)
        r["ejecucion"]["segundos_por_parte"] = tiempos
        r.pop("huellas_inicio", None)
    return r


def escribir_salidas_de_informe(raiz, r):
    """Escribe el JSON y, del mismo diccionario, el informe Markdown."""
    (raiz / "informes").mkdir(exist_ok=True)
    limpio = a_json(r)
    (raiz / "informes" / "transformacion-datos.json").write_text(
        json.dumps(limpio, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (raiz / "informes" / "transformacion-datos.md").write_text(informe_md(limpio), encoding="utf-8")


def main():
    """Ejecuta la transformación, escribe el JSON y el informe, y sale con 1 si para o falla."""
    parser = argparse.ArgumentParser(description="Transformación de los datos del caso 68")
    parser.add_argument("--raiz", type=Path, default=CASO, help="carpeta del caso (por defecto, la de este script)")
    raiz = parser.parse_args().raiz.resolve()
    print("sys.executable:", sys.executable)
    r = None
    try:
        r = transformar(raiz)
    finally:
        if r is not None:
            escribir_salidas_de_informe(raiz, r)
    print(f"estado: {r['resultado']['estado']} · {r['resultado']['resumen']}")
    print("segundos por parte:", json.dumps(r["ejecucion"]["segundos_por_parte"], ensure_ascii=False))
    sys.exit(0 if r["resultado"]["estado"] in ("OK", "AVISO") else 1)


if __name__ == "__main__":
    main()
