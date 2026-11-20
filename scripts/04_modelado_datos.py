"""Comprueba lo que el diseño del modelo de datos del caso 68 afirma sobre los datos (método modelado-datos).

Lee las cuatro tablas corregidas de data/processed/ (solo las columnas que necesita cada comprobación), comprueba el
grano de cada tabla, las fechas que entran en el Calendario, los modelos y sus capacidades, la relación entre fallos y
ventanas, y saca los recuentos del registro de exclusiones y de la población de la pregunta 4. No cruza tablas, no
corrige nada y no construye ninguna dimensión. Solo si el diseño está aprobado (la línea «Aprobado: sí · <nombre> ·
AAAA-MM-DD» en «Decisiones de modelado» de config/modelo/modelo-datos.md) construye el Calendario en
data/processed/calendario.parquet.

Depende de scripts/03_correccion_datos.py: lee informes/correccion-datos.json y para si falta, si está parado o si la
huella de una tabla no es la que dejó la corrección.

Deja informes/modelado-datos.json, con el plan de cruces que lee integracion-datos, e informes/modelado-datos.md,
generado del JSON.

Uso: python -W error scripts/04_modelado_datos.py [--raiz CARPETA_DEL_CASO]
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------------------------------------------
# 2. Configuración, copiada del diseño (config/modelo/modelo-datos.md)
# ---------------------------------------------------------------------------------------------------------------
# Parámetros que fijan las reglas de negocio; las fechas que dependen de los datos se calculan, no se escriben.
FECHA_DATOS = "2025-06-30"                       # reglas, apartado 5, fecha de referencia
FIN_CONSTRUCCION = pd.Timestamp("2024-06-30")    # reglas, apartado 7, partición por fecha
FIN_VALIDACION = pd.Timestamp("2025-06-30")      # reglas, apartado 7
FIN_RESERVA = pd.Timestamp("2026-06-30")         # reglas, apartado 5, la reserva
INICIO_SITIO = pd.Timestamp("2023-07-01")        # reglas, apartado 4, el sitio solo consta desde ese día
HORIZONTE_DIAS = 30                              # reglas, apartado 7, cuestión 004
MINIMO_DIAS_ANO = 50_000                         # reglas, apartado 7, mínimo para entrar en un ranking
MINIMO_FALLOS_EDAD = 20                          # reglas, apartado 7, cuestión 009
HORAS_ANO = 24 * 365.25                          # horas encendido pasadas a años, como el reconocimiento
LIMITE_ARRANQUE_BYTES = 2_048_408_248_320        # reglas, apartado 3: los de arranque van de 0,2 a 2 TB
INICIO_DATOS_BYTES = 4_000_000_000_000           # reglas, apartado 7: los de datos son todos de 4 TB o más
SIN_DATO = "sin dato"                            # etiqueta del centro que no consta en el recuento (R-009)
CONTADORES_AVISO = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]  # reglas, apartado 3

TABLAS = {
    "hechos_fotos": {
        "fichero": "data/processed/fotos_mensuales_corregido.parquet", "tipo": "hechos",
        "grano": "un disco el día 1 de un mes: la foto mensual de cada disco en servicio",
        "clave_grano": ["serial_number", "fecha"],
        "columnas": ["fecha", "date", "serial_number", "model", "capacity_bytes", "failure", "datacenter", "vault_id",
                     "pod_id", "pod_slot_num", "smart_9_raw", *CONTADORES_AVISO],
        "nota": "date repite fecha; el modelo usa fecha"},
    "hechos_ventanas": {
        "fichero": "data/processed/ventanas_fallo_corregido.parquet", "tipo": "hechos",
        "grano": "un disco un día, dentro de los 30 días anteriores a uno de sus fallos o el del fallo",
        "clave_grano": ["serial_number", "fecha"],
        "columnas": ["fecha", "date", "dia_fallo", "serial_number", "model", "capacity_bytes", "failure",
                     "datacenter", "vault_id", "pod_id", "pod_slot_num", "smart_9_raw", *CONTADORES_AVISO],
        "nota": "cada fila pertenece a la ventana de un fallo (serial_number, dia_fallo); date repite fecha"},
    "hechos_recuento": {
        "fichero": "data/processed/recuento_diario_corregido.parquet", "tipo": "hechos",
        "grano": "un día, un modelo, una capacidad y un centro: cuántos discos había y cuántos fallaron",
        "clave_grano": ["fecha", "model", "capacity_bytes", "datacenter"],
        "columnas": ["fecha", "model", "capacity_bytes", "datacenter", "discos", "fallos"],
        "nota": "«sin dato» es el centro que no consta"},
    "hechos_fallos": {
        "fichero": "data/processed/fallos_corregido.parquet", "tipo": "hechos",
        "grano": "un disco el día que Backblaze lo da por fallado",
        "clave_grano": ["serial_number", "dia_fallo"],
        "columnas": ["serial_number", "dia_fallo"],
        "nota": "no trae modelo: lo toma de la fila del día del fallo de su ventana"},
    "dim_modelo": {
        "fichero": None, "tipo": "dimension",
        "grano": "un modelo de disco", "clave_grano": ["model"],
        "columnas": ["model", "capacidad_tb", "fabricante", "tipo_disco", "garantia_anos", "fecha_compra",
                     "precio_dolares"],
        "nota": "la construye la transformación; tipo de la clave: string"},
    "dim_precio_gb": {
        "fichero": None, "tipo": "dimension",
        "grano": "una capacidad un año: lo que costaba el GB", "clave_grano": ["capacidad_tb", "ano"],
        "columnas": ["capacidad_tb", "ano", "dolares_gb", "origen"],
        "nota": "la construye la transformación desde config/sector/precios_de_coste_discos.md"},
    "Calendario": {
        "fichero": None, "tipo": "dimension",
        "grano": "un día, del primer al último día del recuento", "clave_grano": ["fecha"],
        "columnas": ["fecha", "ano", "trimestre", "mes", "periodo", "trimestre_completo", "ano_completo"],
        "nota": "lo construye este script solo con el diseño aprobado"},
}

# Tipo de la clave de cada dimensión que todavía no existe, tal como la declara el diseño
TIPO_CLAVE_DIMENSION = {("dim_modelo", "model"): "string", ("Calendario", "fecha"): "timestamp[ms]"}

PROC_MODELO = ("reglas, apartado 3 (el modelo es la unidad de compra y la capacidad de un disco es la de su modelo); "
               "como_estan_organizados_los_datos.md (dimensión modelo)")
PROC_FECHA = "reglas, apartado 5 (cada registro es el estado de un disco un día; un día de disco es un disco un día)"
RELACIONES = [
    {"desde": "hechos_fotos", "hacia": "dim_modelo", "clave_desde": ["model"], "clave_hacia": ["model"],
     "maestro": "dim_modelo", "cardinalidad": "N:1", "procedencia": PROC_MODELO},
    {"desde": "hechos_ventanas", "hacia": "dim_modelo", "clave_desde": ["model"], "clave_hacia": ["model"],
     "maestro": "dim_modelo", "cardinalidad": "N:1", "procedencia": PROC_MODELO},
    {"desde": "hechos_recuento", "hacia": "dim_modelo", "clave_desde": ["model"], "clave_hacia": ["model"],
     "maestro": "dim_modelo", "cardinalidad": "N:1", "procedencia": PROC_MODELO},
    {"desde": "hechos_fotos", "hacia": "Calendario", "clave_desde": ["fecha"], "clave_hacia": ["fecha"],
     "maestro": "Calendario", "cardinalidad": "N:1", "procedencia": PROC_FECHA},
    {"desde": "hechos_ventanas", "hacia": "Calendario", "clave_desde": ["fecha"], "clave_hacia": ["fecha"],
     "maestro": "Calendario", "cardinalidad": "N:1", "procedencia": PROC_FECHA},
    {"desde": "hechos_recuento", "hacia": "Calendario", "clave_desde": ["fecha"], "clave_hacia": ["fecha"],
     "maestro": "Calendario", "cardinalidad": "N:1", "procedencia": PROC_FECHA},
    {"desde": "hechos_fallos", "hacia": "Calendario", "clave_desde": ["dia_fallo"], "clave_hacia": ["fecha"],
     "maestro": "Calendario", "cardinalidad": "N:1",
     "procedencia": "reglas, apartado 3 (un fallo es el día en que Backblaze da un disco por fallado)"},
    {"desde": "hechos_ventanas", "hacia": "hechos_fallos", "clave_desde": ["serial_number", "dia_fallo"],
     "clave_hacia": ["serial_number", "dia_fallo"], "maestro": "hechos_fallos", "cardinalidad": "N:1",
     "procedencia": "como_estan_organizados_los_datos.md (una ventana son los 30 días antes de un fallo y el del "
                    "fallo); reglas, apartado 5 («salvo los 30 días antes de un fallo, que van día a día»)"},
    {"desde": "hechos_fallos", "hacia": "hechos_ventanas", "clave_desde": ["serial_number", "dia_fallo"],
     "clave_hacia": ["serial_number", "fecha"], "maestro": "hechos_ventanas (su fila del día del fallo)",
     "cardinalidad": "1:1",
     "procedencia": "reglas, apartado 5 (un registro por disco y día, el del fallo incluido); como_estan_organizados_los_datos.md"},
    {"desde": "hechos_fallos", "hacia": "dim_modelo", "clave_desde": ["model"], "clave_hacia": ["model"],
     "maestro": "dim_modelo", "cardinalidad": "N:1",
     "procedencia": PROC_MODELO + "; el modelo es el de la fila del día del fallo",
     "columna_origen": ("hechos_ventanas", "model")},
    {"desde": "hechos_fallos", "hacia": "dim_precio_gb", "clave_desde": ["capacidad_tb", "ano_fallo"],
     "clave_hacia": ["capacidad_tb", "ano"], "maestro": "dim_precio_gb", "cardinalidad": "N:1",
     "procedencia": "reglas, apartado 6 (el disco nuevo que sustituye a uno que falla, al coste por GB del año del fallo)",
     "columna_origen": None},
]

PLAN_CRUCES = [
    {"orden": 1, "partida": "hechos_fallos", "se_une": "hechos_ventanas", "clave_partida": ["serial_number", "dia_fallo"],
     "clave_une": ["serial_number", "fecha"], "cardinalidad": "1:1", "tipo_cruce": "left",
     "magnitudes_control": ["filas de hechos_fallos"],
     "agregar_antes": "ventanas filtradas a la fila con fecha = dia_fallo: una por fallo",
     "aporta": "modelo, capacidad y horas encendido del día del fallo (el modelo de cada fila es el que trae esa fila)",
     "fecha_del_cruce": "el día del fallo"},
    {"orden": 2, "partida": "hechos_fallos", "se_une": "hechos_ventanas", "clave_partida": ["serial_number", "dia_fallo"],
     "clave_une": ["serial_number", "fecha"], "cardinalidad": "1:1", "tipo_cruce": "left",
     "magnitudes_control": ["filas de hechos_fallos"],
     "agregar_antes": "ventanas filtradas a la fila con fecha = dia_fallo - 1 día: una por fallo, o ninguna",
     "aporta": "los cinco contadores de avería del día anterior (fallo sin aviso, reglas, apartado 6)",
     "fecha_del_cruce": "el día anterior al fallo"},
    {"orden": 3, "partida": "hechos_fallos", "se_une": "hechos_ventanas", "clave_partida": ["serial_number", "dia_fallo"],
     "clave_une": ["serial_number", "dia_fallo"], "cardinalidad": "1:1", "tipo_cruce": "left",
     "magnitudes_control": ["filas de hechos_fallos"],
     "agregar_antes": "por fallo, la última fila de su ventana hasta el día del fallo que trae centro (para las tasas por "
                      "centro) y la última que trae centro, vault, servidor y ranura (para el tomo): una por fallo",
     "aporta": "el sitio del fallo (reglas, apartado 5)", "fecha_del_cruce": "el último día con sitio, hasta el del fallo"},
    {"orden": 4, "partida": "hechos_fallos", "se_une": "dim_modelo", "clave_partida": ["model"], "clave_une": ["model"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["filas de hechos_fallos"],
     "agregar_antes": None, "aporta": "capacidad, fabricante, tipo de disco y garantía", "fecha_del_cruce": None},
    {"orden": 5, "partida": "hechos_fallos", "se_une": "dim_precio_gb", "clave_partida": ["capacidad_tb", "ano_fallo"],
     "clave_une": ["capacidad_tb", "ano"], "cardinalidad": "N:1", "tipo_cruce": "left",
     "magnitudes_control": ["filas de hechos_fallos"], "agregar_antes": None,
     "aporta": "precio del disco nuevo (reglas, apartado 6)", "fecha_del_cruce": "el año del fallo"},
    {"orden": 6, "partida": "hechos_fallos", "se_une": "Calendario", "clave_partida": ["dia_fallo"],
     "clave_une": ["fecha"], "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["filas de hechos_fallos"],
     "agregar_antes": None, "aporta": "año, trimestre, mes y periodo del fallo", "fecha_del_cruce": "el día del fallo"},
    {"orden": 7, "partida": "hechos_recuento", "se_une": "dim_modelo", "clave_partida": ["model"], "clave_une": ["model"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["discos", "fallos"], "agregar_antes": None,
     "aporta": "tipo de disco, fabricante, capacidad y precio", "fecha_del_cruce": None},
    {"orden": 8, "partida": "hechos_recuento", "se_une": "Calendario", "clave_partida": ["fecha"], "clave_une": ["fecha"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["discos", "fallos"], "agregar_antes": None,
     "aporta": "año, trimestre, mes, periodo y marca de parcial", "fecha_del_cruce": None},
    {"orden": 9, "partida": "hechos_fotos", "se_une": "dim_modelo", "clave_partida": ["model"], "clave_une": ["model"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["filas de hechos_fotos"], "agregar_antes": None,
     "aporta": "tipo de disco, fabricante, capacidad y garantía", "fecha_del_cruce": None},
    {"orden": 10, "partida": "hechos_fotos", "se_une": "Calendario", "clave_partida": ["fecha"], "clave_une": ["fecha"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["filas de hechos_fotos"], "agregar_antes": None,
     "aporta": "año, trimestre, mes y periodo", "fecha_del_cruce": None},
    {"orden": 11, "partida": "hechos_fotos", "se_une": "hechos_recuento", "clave_partida": ["model", "datacenter", "mes"],
     "clave_une": ["model", "datacenter", "mes"], "cardinalidad": "N:1", "tipo_cruce": "left",
     "magnitudes_control": ["días de disco del recuento"],
     "agregar_antes": "fotos: discos por modelo, centro (el vacío como «sin dato»), mes y tramo (edad, aviso), y su parte "
                      "dentro de modelo, centro y mes; recuento: días de disco (discos sumados por día) y fallos por "
                      "modelo, centro y mes. Los días de cada tramo son la parte de la foto por los días del recuento",
     "aporta": "los días de disco de cada tramo (reglas, apartado 5, «Con qué se cuentan»)", "fecha_del_cruce": "el mes de la foto"},
    {"orden": 12, "partida": "hechos_fotos", "se_une": "hechos_fallos", "clave_partida": ["serial_number", "fecha"],
     "clave_une": ["serial_number", "fecha_foto"], "cardinalidad": "N:1", "tipo_cruce": "left",
     "magnitudes_control": ["filas del tablón de la pregunta 4", "objetivo: pares foto-fallo distintos"],
     "agregar_antes": "por fallo, las fechas de las fotos de su disco con fecha < dia_fallo <= fecha + 30 días, con el "
                      "horizonte recortado al último día del periodo de la foto; una fila por (serial_number, fecha_foto)",
     "aporta": "el objetivo de la pregunta 4 (reglas, apartado 7, cuestión 003 y cuestión 004)",
     "fecha_del_cruce": "los 30 días siguientes a la foto"},
    {"orden": 13, "partida": "hechos_fallos", "se_une": "hechos_fotos", "clave_partida": ["serial_number", "fecha_foto"],
     "clave_une": ["serial_number", "fecha"], "cardinalidad": "N:1", "tipo_cruce": "left",
     "magnitudes_control": ["filas de hechos_fallos"],
     "agregar_antes": "a cada fallo, la fecha de la última foto de su disco anterior al fallo dentro de su horizonte",
     "aporta": "el puesto del disco en la lista del mes, para los fallos señalados en tomos en peligro",
     "fecha_del_cruce": "la última foto anterior al fallo"},
    {"orden": 14, "partida": "hechos_fotos", "se_une": "hechos_recuento",
     "clave_partida": ["model", "ano_edad", "trimestre"], "clave_une": ["model", "ano_edad", "trimestre"],
     "cardinalidad": "N:1", "tipo_cruce": "left", "magnitudes_control": ["discos del primer día del trimestre"],
     "agregar_antes": "fotos del primer día de cada trimestre (discos de datos), contadas por modelo y año de edad; "
                      "tasas por modelo y año de edad con los días (cruce 11) y los fallos (cruces 1 y 4) hasta el día "
                      "anterior al trimestre",
     "aporta": "los fallos esperados del bloque 9 (reglas, apartado 7, previsión)",
     "fecha_del_cruce": "el primer día del trimestre"},
    {"orden": 15, "partida": "hechos_recuento", "se_une": "hechos_fallos",
     "clave_partida": ["model", "datacenter", "mes", "tramo"], "clave_une": ["model", "datacenter", "mes", "tramo"],
     "cardinalidad": "1:1", "tipo_cruce": "left", "magnitudes_control": ["días de disco", "fallos"],
     "agregar_antes": "días de disco repartidos (cruce 11) y fallos (cruces 1, 3 y 4) agregados al mismo grano; los "
                      "fallos sin días en su celda son huérfanas que cuenta integracion-datos",
     "aporta": "numerador y denominador de cada tasa por modelo, centro, mes y tramo, en tablas separadas",
     "fecha_del_cruce": None},
]

EXCLUSIONES_META = {
    "discos_de_arranque": {
        "que_sale": "los discos de 0,2 a 2 TB, con sus fotos, días de disco y fallos",
        "sale_de": "todas las tasas, rankings, coste por terabyte, previsión y la pregunta 4",
        "como_se_trata": "fuera de todo cálculo; se pueden contar aparte",
        "por_que": "reglas, apartado 3: no guardan datos de clientes y Backblaze los quita de sus tasas",
        "recuperable": "sí: siguen en las tablas y se cuentan aparte si una petición lo pide"},
    "sitio_no_consta_antes": {
        "que_sale": "los días de disco y fallos de discos de datos antes del 01/07/2023, sin centro",
        "sale_de": "tasas por centro y fallos del mismo tomo (pregunta 3)",
        "como_se_trata": "fuera de las cifras por sitio; siguen en las demás",
        "por_que": "reglas, apartado 4: el sitio solo consta desde el 01/07/2023 y no se rellena hacia atrás",
        "recuperable": "no: el sitio no está en los datos"},
    "sitio_no_consta_desde": {
        "que_sale": "los días de disco y fallos de discos de datos desde el 01/07/2023 con el centro «sin dato»",
        "sale_de": "tasas por centro (pregunta 3)",
        "como_se_trata": "se cuentan y se dicen (reglas, apartado 5)",
        "por_que": "reglas, apartado 5 y §7: un dato de sitio vacío no consta",
        "recuperable": "no, con estos datos"},
    "fallos_sin_ranura": {
        "que_sale": "los fallos de discos de datos desde el 01/07/2023 sin ningún día de su ventana, hasta el del fallo, "
                    "con centro (sin centro) o con centro, vault y ranura (sin tomo)",
        "sale_de": "tasas por centro (sin centro) y fallos del mismo tomo (sin tomo), pregunta 3 y aviso de tomos en "
                   "peligro de la pregunta 4",
        "como_se_trata": "se cuentan y se dicen (reglas, apartado 5)",
        "por_que": "reglas, apartado 5: el sitio de un fallo es el del último día anterior que lo trae, dentro de su ventana",
        "recuperable": "no, con estos datos"},
    "fallos_sin_dia_anterior": {
        "que_sale": "los fallos de discos de datos cuya ventana no trae el día anterior al fallo",
        "sale_de": "el indicador de fallos sin aviso",
        "como_se_trata": "fuera del indicador; se cuentan y se dicen",
        "por_que": "reglas, apartado 6: el fallo sin aviso se mira el día anterior; sin ese día no se sabe",
        "recuperable": "no: el día no está en los datos"},
    "modelos_bajo_minimo": {
        "que_sale": "los modelos de datos con menos de 50.000 días de disco en el año",
        "sale_de": "los rankings de modelos (preguntas 1 y 2, bloque 2)",
        "como_se_trata": "se enseñan aparte con su recuento (reglas, apartado 7)",
        "por_que": "reglas, apartado 7: mínimo fijo para entrar en un ranking, el umbral anual de Backblaze",
        "recuperable": "sí: se enseñan aparte; no entran en el ranking"},
    "anos_de_edad_con_menos_de_20_fallos": {
        "que_sale": "los años de edad, de todos los discos o de un modelo, con menos de 20 fallos",
        "sale_de": "la conclusión de la pregunta 2 (a qué edad sube la tasa)",
        "como_se_trata": "se enseñan sin conclusión (reglas, apartado 7, cuestión 009)",
        "por_que": "cuestión 009: con menos de 20 fallos el intervalo no permite concluir",
        "recuperable": "sí: se enseñan, sin conclusión"},
    "p4_fotos_del_dia_del_fallo": {
        "que_sale": "las fotos de discos de datos con failure = 1, del mismo día del fallo",
        "sale_de": "el tablón de la pregunta 4",
        "como_se_trata": "fuera del tablón; su fallo sigue siendo objetivo de la foto anterior si cae en su horizonte",
        "por_que": "ese día el disco ya está marcado como fallado (decisión de modelado, el analista)",
        "recuperable": "no: no hay nada que predecir en ellas"},
    "p4_horizonte_recortado": {
        "que_sale": "los fallos que caen después del último día del periodo de la foto",
        "sale_de": "el objetivo de la pregunta 4",
        "como_se_trata": "el horizonte se recorta al borde del periodo (reglas, apartado 7: «se recorta o se queda fuera»)",
        "por_que": "un objetivo no puede mirar al periodo siguiente (decisión de modelado, el analista)",
        "recuperable": "el de construcción, no sin mezclar periodos; el de validación, solo con la reserva"},
    "filas_del_10_12_2022": {
        "que_sale": "las 228 filas de las ventanas fechadas el 10/12/2022 que eran copia del 11/12/2022",
        "sale_de": "las ventanas de fallo, ya en la corrección (R-007)",
        "como_se_trata": "quitadas en la corrección; ninguna traía un fallo",
        "por_que": "registro de transformaciones, R-007: no son datos de su fecha",
        "recuperable": "no: eran copias; siguen en data/raw/"},
}


# ---------------------------------------------------------------------------------------------------------------
# 3. Utilidades
# ---------------------------------------------------------------------------------------------------------------
def sha256(ruta):
    """Huella SHA-256 de un fichero, leída por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


def miles(n):
    """Número entero con el punto de miles, sin tocar el resto del texto."""
    return f"{n:,}".replace(",", ".")


def iso(x):
    """Fecha en ISO 8601 (AAAA-MM-DD), o None."""
    return None if x is None or pd.isna(x) else pd.Timestamp(x).strftime("%Y-%m-%d")


def grano(tabla, claves):
    """Filas, combinaciones distintas de la clave, filas repetidas de más y filas con algún vacío en la clave."""
    distintas = tabla.select(claves).group_by(claves).aggregate([]).num_rows
    nulos = sum(tabla.column(c).null_count for c in claves)
    return {"filas": tabla.num_rows, "claves_distintas": distintas, "filas_repetidas": tabla.num_rows - distintas,
            "nulos_en_clave": int(nulos)}


def distinta(a, b):
    """Filas en que dos columnas de fecha no son iguales, contando como distinta la fila con un vacío."""
    return int(pc.sum(pc.fill_null(pc.not_equal(a, b), True)).as_py() or 0)


def leer_aprobacion(ruta):
    """Busca la línea «Aprobado: sí · <nombre> · AAAA-MM-DD» solo dentro del apartado «Decisiones de modelado»."""
    vacia = {"aprobado": False, "fecha": None, "quien": None}
    if not ruta.exists():
        return vacia
    dentro = False
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.startswith("## "):
            dentro = "Decisiones de modelado" in linea
            continue
        m = re.match(r"^\s*Aprobado: sí · (.+?) · (\d{4}-\d{2}-\d{2})\s*$", linea)
        if dentro and m:
            return {"aprobado": bool(m), "fecha": m.group(2), "quien": m.group(1).strip()}
    return vacia


def leer_cuestiones_abiertas(ruta):
    """Las cuestiones con estado «abierta» de cuestiones-pendientes.md, como pendientes del JSON."""
    if not ruta.exists():
        return []
    pendientes = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) >= 6 and re.fullmatch(r"CP-\d{3}", celdas[0]) and celdas[-1].lower().startswith("abierta"):
            pendientes.append({"id": celdas[0], "tabla": "", "columna": "", "pregunta": celdas[2],
                               "opciones": [celdas[4]]})
    return pendientes


def construir_calendario(primero, ultimo):
    """Calendario diario continuo del primer al último día, con año, trimestre, mes, periodo y marcas de parcial."""
    fechas = pd.date_range(primero, ultimo, freq="D")
    cal = pd.DataFrame({"fecha": fechas.astype("datetime64[ms]")})
    cal["ano"] = cal["fecha"].dt.year.astype("int64")
    cal["trimestre"] = cal["fecha"].dt.quarter.astype("int64")
    cal["mes"] = cal["fecha"].dt.month.astype("int64")
    # El periodo de la partición (reglas, apartado 7) y la reserva (reglas, apartado 5); fuera de ellos no hay periodo definido
    cal["periodo"] = np.select([cal["fecha"] <= FIN_CONSTRUCCION, cal["fecha"] <= FIN_VALIDACION,
                                cal["fecha"] <= FIN_RESERVA], ["construcción", "validación", "reserva"], default=None)
    # Un trimestre o un año es parcial si le falta algún día dentro del rango (reglas, apartado 5)
    dias_trim = cal.groupby(["ano", "trimestre"])["fecha"].transform("size")
    trim = cal["fecha"].dt.to_period("Q")
    cal["trimestre_completo"] = dias_trim.to_numpy() == (trim.dt.end_time.dt.normalize() - trim.dt.start_time).dt.days + 1
    dias_ano = cal.groupby("ano")["fecha"].transform("size")
    cal["ano_completo"] = dias_ano.to_numpy() == np.where(pd.to_datetime(cal["ano"].astype(str) + "-12-31").dt.is_leap_year, 366, 365)
    return cal


# ---------------------------------------------------------------------------------------------------------------
# 4. Entrada: el JSON de la corrección y las huellas
# ---------------------------------------------------------------------------------------------------------------
def comprobar_entrada(raiz):
    """Lee correccion-datos.json y compara la huella de cada tabla con la que dejó; devuelve (entradas, motivo)."""
    ruta = raiz / "informes" / "correccion-datos.json"
    if not ruta.exists():
        return [], "falta informes/correccion-datos.json: las tablas no están corregidas"
    corr = json.loads(ruta.read_text(encoding="utf-8"))
    estado = corr.get("resultado", {}).get("estado")
    if estado in ("PARADO", "ERROR") or estado is None:
        return [], f"correccion-datos.json está en {estado}: las tablas no están listas para modelar"
    salidas = {s["ruta"]: s for s in corr.get("salidas", [])}
    entradas, malas = [], []
    for nombre, cfg in TABLAS.items():
        if cfg["fichero"] is None or cfg["tipo"] != "hechos":
            continue
        f = raiz / cfg["fichero"]
        if not f.exists():
            malas.append(f"falta {cfg['fichero']}")
            continue
        meta = pq.ParquetFile(f).metadata
        huella = sha256(f)
        entradas.append({"ruta": cfg["fichero"], "sha256": huella, "filas": meta.num_rows, "columnas": meta.num_columns})
        if salidas.get(cfg["fichero"], {}).get("sha256") != huella:
            malas.append(f"la huella de {cfg['fichero']} no es la que dejó la corrección")
    return entradas, ("; ".join(malas) or None), corr


# ---------------------------------------------------------------------------------------------------------------
# 5. Comprobaciones
# ---------------------------------------------------------------------------------------------------------------
def comprobar_todo(raiz, corr, tiempos):
    """Hace todas las comprobaciones del diseño sobre las cuatro tablas y devuelve sus resultados."""
    c, r = {}, {}
    t0 = time.perf_counter()

    # 5.1 Recuento: grano, días, modelos y capacidades. Es la tabla que da el rango del Calendario.
    rec_t = pq.read_table(raiz / TABLAS["hechos_recuento"]["fichero"], columns=TABLAS["hechos_recuento"]["columnas"])
    r["grano_hechos_recuento"] = grano(rec_t, TABLAS["hechos_recuento"]["clave_grano"])
    rec = rec_t.to_pandas()
    dias = pd.DatetimeIndex(rec["fecha"].drop_duplicates()).sort_values()
    faltan = pd.date_range(dias.min(), dias.max(), freq="D").difference(dias)
    c.update({"recuento.filas": len(rec), "recuento.primer_dia": iso(dias.min()), "recuento.ultimo_dia": iso(dias.max()),
              "recuento.dias": len(dias), "recuento.dias_que_faltan": len(faltan)})
    r["recuento_dias_que_faltan"] = [iso(x) for x in faltan[:20]]
    tiempos["recuento"] = round(time.perf_counter() - t0, 1)

    # 5.2 Fallos y ventanas: grano, fechas, la fila del día del fallo y el modelo que trae
    t0 = time.perf_counter()
    fal_t = pq.read_table(raiz / TABLAS["hechos_fallos"]["fichero"], columns=TABLAS["hechos_fallos"]["columnas"])
    r["grano_hechos_fallos"] = grano(fal_t, TABLAS["hechos_fallos"]["clave_grano"])
    fal = fal_t.to_pandas()
    # Solo las columnas que usan las comprobaciones; los contadores no se miran aquí
    ven_cols = ["fecha", "date", "dia_fallo", "serial_number", "model", "capacity_bytes", "failure", "datacenter",
                "vault_id", "pod_id", "pod_slot_num", "smart_9_raw"]
    ven_t = pq.read_table(raiz / TABLAS["hechos_ventanas"]["fichero"], columns=ven_cols)
    r["grano_hechos_ventanas"] = grano(ven_t, TABLAS["hechos_ventanas"]["clave_grano"])
    c["ventanas.date_distinta_de_fecha"] = distinta(ven_t["date"], ven_t["fecha"])
    ven = ven_t.to_pandas()
    c.update({"fallos.filas": len(fal), "ventanas.filas": len(ven)})
    c["fallos.discos_con_dos_fallos"] = int((fal["serial_number"].value_counts() == 2).sum())
    vdias = pd.DatetimeIndex(ven["fecha"].drop_duplicates()).sort_values()
    vfaltan = pd.date_range(vdias.min(), vdias.max(), freq="D").difference(vdias)
    c.update({"ventanas.dias": len(vdias), "ventanas.dias_que_faltan_n": len(vfaltan),
              "ventanas.dias_que_faltan": [iso(x) for x in vfaltan[:20]]})
    # Cada fallo con su ventana y con su fila del día: se miran conjuntos de claves, sin unir filas
    llave = lambda s, d: s.astype(str) + "|" + pd.to_datetime(d).dt.strftime("%Y-%m-%d")
    fal["llave"] = llave(fal["serial_number"], fal["dia_fallo"])
    ven["llave"] = llave(ven["serial_number"], ven["dia_fallo"])
    c["fallos.sin_ventana"] = int((~fal["llave"].isin(set(ven["llave"]))).sum())
    dia0 = ven.loc[ven["fecha"] == ven["dia_fallo"]].set_index("llave")
    c["fallos.sin_fila_del_dia"] = int((~fal["llave"].isin(dia0.index)).sum())
    c["fallos.fila_del_dia_sin_failure_1"] = int((dia0["failure"] != 1).sum())
    tiempos["fallos_y_ventanas"] = round(time.perf_counter() - t0, 1)

    # 5.3 Modelos y capacidades en las tres tablas que traen modelo
    t0 = time.perf_counter()
    fot_cols = ["fecha", "date", "serial_number", "model", "capacity_bytes", "failure", "datacenter"]
    fot = pq.read_table(raiz / TABLAS["hechos_fotos"]["fichero"], columns=fot_cols)
    tiempos["fotos_lectura"] = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    r["grano_hechos_fotos"] = grano(fot, TABLAS["hechos_fotos"]["clave_grano"])
    c["fotos.filas"] = fot.num_rows
    c["fotos.date_distinta_de_fecha"] = distinta(fot["date"], fot["fecha"])
    tiempos["fotos_grano"] = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    pares = pd.concat([fot.select(["model", "capacity_bytes"]).group_by(["model", "capacity_bytes"]).aggregate([]).to_pandas(),
                       ven[["model", "capacity_bytes"]], rec[["model", "capacity_bytes"]]]).drop_duplicates()
    capacidades = pares.groupby("model")["capacity_bytes"]
    capacidad = capacidades.max()
    m_fot = set(pc.unique(fot["model"]).to_pylist())
    m_rec, m_ven = set(rec["model"]), set(ven["model"])
    datos = set(capacidad.index[capacidad > LIMITE_ARRANQUE_BYTES])
    arranque = set(capacidad.index[capacidad <= LIMITE_ARRANQUE_BYTES])
    c.update({"modelos.fotos": len(m_fot), "modelos.recuento": len(m_rec), "modelos.fotos_igual_recuento": m_fot == m_rec,
              "modelos.ventanas": len(m_ven), "modelos.ventanas_fuera_del_recuento": len(m_ven - m_rec),
              "modelos.con_mas_de_una_capacidad": int((capacidades.nunique() > 1).sum()),
              "modelos.arranque": len(arranque), "modelos.datos": len(datos),
              "modelos.entre_arranque_y_datos": int(((capacidad > LIMITE_ARRANQUE_BYTES) &
                                                      (capacidad < INICIO_DATOS_BYTES)).sum())})

    # 5.4 Fotos: meses, día 1, discos de datos por periodo y día del fallo
    fechas_f = pd.DatetimeIndex(pc.unique(fot["fecha"]).to_pandas()).sort_values()
    meses = fechas_f.to_period("M")
    c.update({"fotos.meses": len(fechas_f), "fotos.fechas_no_dia_1": int((fechas_f.day != 1).sum()),
              "fotos.meses_que_faltan": len(pd.period_range(meses.min(), meses.max(), freq="M").difference(meses)),
              "fotos.primera": iso(fechas_f.min()), "fotos.ultima": iso(fechas_f.max())})
    es_dato = pc.is_in(fot["model"], value_set=pa.array(sorted(datos), type=pa.string()))
    fin_c = pa.scalar(FIN_CONSTRUCCION.to_datetime64().astype("datetime64[ms]"), type=pa.timestamp("ms"))
    en_constr = pc.less_equal(fot["fecha"], fin_c)
    contar = lambda m: int(pc.sum(pc.cast(m, pa.int64())).as_py() or 0)
    falla = pc.equal(fot["failure"], 1)
    c.update({"fotos.filas_datos": contar(es_dato),
              "fotos.filas_datos_construccion": contar(pc.and_(es_dato, en_constr)),
              "fotos.filas_datos_validacion": contar(pc.and_(es_dato, pc.invert(en_constr))),
              "fotos.filas_datos_dia_del_fallo": contar(pc.and_(es_dato, falla))})
    dato_fallo_c = contar(pc.and_(pc.and_(es_dato, falla), en_constr))
    sitio_c = pa.scalar(INICIO_SITIO.to_datetime64().astype("datetime64[ms]"), type=pa.timestamp("ms"))
    sin_centro = pc.and_(es_dato, pc.is_null(fot["datacenter"]))
    desde_sitio = pc.greater_equal(fot["fecha"], sitio_c)
    fotos_sin_centro = {"antes": contar(pc.and_(sin_centro, pc.invert(desde_sitio))),
                        "desde": contar(pc.and_(sin_centro, desde_sitio))}
    tiempos["fotos_cuentas"] = round(time.perf_counter() - t0, 1)

    # 5.5 Fallos de discos de datos: modelo del día del fallo, discos sin foto, edad al fallar y sitio
    t0 = time.perf_counter()
    series_fotos = set(pc.unique(fot["serial_number"]).to_pylist())
    c["fallos.discos_sin_foto"] = int((~fal["serial_number"].drop_duplicates().isin(series_fotos)).sum())
    fal = fal.join(dia0[["model", "capacity_bytes", "smart_9_raw"]], on="llave")
    fal["de_datos"] = fal["model"].isin(datos)
    fd = fal.loc[fal["de_datos"]].copy()
    # Horas del día del fallo o, sin ellas, del día anterior; sin ninguna, la edad desde la primera aparición (reglas, apartado 3)
    dia1 = ven.loc[ven["fecha"] == ven["dia_fallo"] - pd.Timedelta(days=1)].set_index("llave")
    fd["horas_1"] = fd["llave"].map(dia1["smart_9_raw"])
    fd["horas"] = fd["smart_9_raw"].fillna(fd["horas_1"])
    sin_horas = fd.loc[fd["horas"].isna(), "serial_number"].unique()
    if len(sin_horas):
        sub = fot.filter(pc.is_in(fot["serial_number"], value_set=pa.array(sin_horas, type=pa.string())))
        prim_f = sub.group_by("serial_number").aggregate([("fecha", "min")]).to_pandas().set_index("serial_number")["fecha_min"]
    else:
        prim_f = pd.Series(dtype="datetime64[ms]")
    prim_v = ven.groupby("serial_number")["fecha"].min()
    primera = pd.concat([prim_f, prim_v], axis=1).min(axis=1)
    dias_vida = (fd["dia_fallo"] - fd["serial_number"].map(primera)).dt.days
    fd["edad"] = np.floor(fd["horas"].fillna(dias_vida * 24) / HORAS_ANO)
    todos_edad = fd.groupby("edad").size()
    celdas = fd.groupby(["model", "edad"]).size()
    # Sitio del fallo: hay algún día de su ventana, hasta el del fallo, con centro o con el tomo entero (reglas, apartado 5)
    hasta = ven.loc[ven["fecha"] <= ven["dia_fallo"]]
    con_centro = set(hasta.loc[hasta["datacenter"].notna(), "llave"])
    con_tomo = set(hasta.loc[hasta[["datacenter", "vault_id", "pod_id", "pod_slot_num"]].notna().all(axis=1), "llave"])
    fd_sitio = fd.loc[fd["dia_fallo"] >= INICIO_SITIO]
    tiempos["fallos_de_datos"] = round(time.perf_counter() - t0, 1)

    # 5.6 Pregunta 4: población del tablón y fotos con el horizonte recortado
    t0 = time.perf_counter()
    p4 = {"filas_tablon": c["fotos.filas_datos"] - c["fotos.filas_datos_dia_del_fallo"],
          "filas_tablon_construccion": c["fotos.filas_datos_construccion"] - dato_fallo_c,
          "filas_tablon_validacion": c["fotos.filas_datos_validacion"] - (c["fotos.filas_datos_dia_del_fallo"] - dato_fallo_c),
          "horizonte_recortado": []}
    ultimo_dato = dias.max()
    for periodo, fin in (("construcción", FIN_CONSTRUCCION), ("validación", FIN_VALIDACION)):
        for f in fechas_f[(fechas_f <= fin) & (fechas_f + pd.Timedelta(days=HORIZONTE_DIAS) > fin)]:
            tope = f + pd.Timedelta(days=HORIZONTE_DIAS)
            fc = pa.scalar(f.to_datetime64().astype("datetime64[ms]"), type=pa.timestamp("ms"))
            en_foto = set(fot.filter(pc.and_(pc.equal(fot["fecha"], fc), es_dato))["serial_number"].to_pylist())
            ventana = fd.loc[(fd["dia_fallo"] > f) & (fd["dia_fallo"] <= tope)]
            de_foto = ventana.loc[ventana["serial_number"].isin(en_foto)]
            se_ve = tope <= ultimo_dato
            p4["horizonte_recortado"].append({
                "periodo": periodo, "foto": iso(f), "horizonte_completo": iso(tope), "corte": iso(fin),
                "fallos_horizonte": len(ventana) if se_ve else None,
                "fallos_disco_en_foto": len(de_foto) if se_ve else None,
                "fallos_perdidos": int((ventana["dia_fallo"] > fin).sum()) if se_ve else None,
                "fallos_perdidos_disco_en_foto": int((de_foto["dia_fallo"] > fin).sum()) if se_ve else None,
                "nota": None if se_ve else "el horizonte entero pasa del último día de los datos: lo que se pierde "
                                           "no se puede saber hasta la prueba final"})
    tiempos["pregunta_4"] = round(time.perf_counter() - t0, 1)

    # 5.7 Registro de exclusiones: recuentos sacados del código
    rec["ano"] = rec["fecha"].dt.year
    rec_d = rec.loc[rec["model"].isin(datos)]
    rec_a = rec.loc[rec["model"].isin(arranque)]
    antes = rec_d["fecha"] < INICIO_SITIO
    sd = rec_d["datacenter"] == SIN_DATO
    por_ano = {}
    dias_modelo_ano = rec_d.groupby(["ano", "model"])[["discos", "fallos"]].sum()
    for ano, g in dias_modelo_ano.groupby(level="ano"):
        bajo = g["discos"] < MINIMO_DIAS_ANO
        dias_ano = int((rec["ano"] == ano).groupby(rec["fecha"]).any().sum())
        por_ano[str(ano)] = {"modelos_con_dias": int(len(g)), "modelos_bajo_minimo": int(bajo.sum()),
                             "dias_de_disco_bajo_minimo": int(g.loc[bajo, "discos"].sum()),
                             "fallos_bajo_minimo": int(g.loc[bajo, "fallos"].sum()),
                             "dias_de_disco_del_ano": int(g["discos"].sum()), "dias_del_ano_en_datos": dias_ano}
    pasan_algun_ano = int((dias_modelo_ano["discos"] >= MINIMO_DIAS_ANO).groupby(level="model").any().sum())
    ex = {
        "discos_de_arranque": {"modelos": len(arranque), "filas_fotos": c["fotos.filas"] - c["fotos.filas_datos"],
                               "filas_ventanas": int((~ven["model"].isin(datos)).sum()),
                               "dias_de_disco": int(rec_a["discos"].sum()), "fallos_recuento": int(rec_a["fallos"].sum())},
        "sitio_no_consta_antes": {"dias_de_disco": int(rec_d.loc[antes & sd, "discos"].sum()),
                                  "fallos_recuento": int(rec_d.loc[antes & sd, "fallos"].sum()),
                                  "fallos_lista": int((fd["dia_fallo"] < INICIO_SITIO).sum()),
                                  "filas_fotos_sin_centro": fotos_sin_centro["antes"]},
        "sitio_no_consta_desde": {"dias_de_disco": int(rec_d.loc[~antes & sd, "discos"].sum()),
                                  "fallos_recuento": int(rec_d.loc[~antes & sd, "fallos"].sum()),
                                  "dias_de_disco_desde": int(rec_d.loc[~antes, "discos"].sum()),
                                  "filas_fotos_sin_centro": fotos_sin_centro["desde"]},
        "fallos_sin_ranura": {"fallos_desde": len(fd_sitio),
                              "fallos_sin_centro": int((~fd_sitio["llave"].isin(con_centro)).sum()),
                              "fallos_sin_tomo": int((~fd_sitio["llave"].isin(con_tomo)).sum())},
        "fallos_sin_dia_anterior": {"fallos_de_datos": len(fd), "fallos": int((~fd["llave"].isin(dia1.index)).sum())},
        "modelos_bajo_minimo": {"minimo_dias_ano": MINIMO_DIAS_ANO, "modelos_de_datos": len(datos),
                                "modelos_que_pasan_algun_ano": pasan_algun_ano, "por_ano": por_ano},
        "anos_de_edad_con_menos_de_20_fallos": {
            "todos_anos": int((todos_edad < MINIMO_FALLOS_EDAD).sum()),
            "todos_fallos": int(todos_edad[todos_edad < MINIMO_FALLOS_EDAD].sum()),
            "todos_anos_de_edad": {str(int(k)): int(v) for k, v in todos_edad.items()},
            "celdas_modelo_edad": int((celdas < MINIMO_FALLOS_EDAD).sum()),
            "celdas_modelo_edad_total": int(len(celdas)),
            "fallos_en_esas_celdas": int(celdas[celdas < MINIMO_FALLOS_EDAD].sum()),
            "fallos_con_edad_por_primera_aparicion": int(fd["horas"].isna().sum())},
        "p4_fotos_del_dia_del_fallo": {"filas": c["fotos.filas_datos_dia_del_fallo"],
                                       "construccion": dato_fallo_c,
                                       "validacion": c["fotos.filas_datos_dia_del_fallo"] - dato_fallo_c},
        "p4_horizonte_recortado": {"fotos": [x["foto"] for x in p4["horizonte_recortado"]],
                                   "fallos_perdidos_disco_en_foto": [x["fallos_perdidos_disco_en_foto"]
                                                                     for x in p4["horizonte_recortado"]]},
        "filas_del_10_12_2022": {"filas": corr.get("controles", {}).get("ventanas.filas_quitadas"),
                                 "fecha": (corr.get("controles", {}).get("ventanas.fechas_quitadas") or [None])[0],
                                 "fuente": "informes/correccion-datos.json, controles"},
    }
    c["fallos.de_datos"] = len(fd)
    c["fallos.datos_construccion"] = int((fd["dia_fallo"] <= FIN_CONSTRUCCION).sum())
    c["fallos.datos_validacion"] = int(((fd["dia_fallo"] > FIN_CONSTRUCCION) & (fd["dia_fallo"] <= FIN_VALIDACION)).sum())
    return c, r, p4, ex, {"fot": fot, "ven_tipos": ven_t.schema, "fal_tipos": fal_t.schema, "rec_tipos": rec_t.schema,
                          "primer_dia": dias.min(), "ultimo_dia": dias.max()}


def tipos_relaciones(esquemas):
    """Compara el tipo de las claves de cada relación a los dos lados, sin corregir nada."""
    tipo = {"hechos_fotos": esquemas["fot"].schema, "hechos_ventanas": esquemas["ven_tipos"],
            "hechos_fallos": esquemas["fal_tipos"], "hechos_recuento": esquemas["rec_tipos"]}

    def de(tabla, col):
        if tabla in tipo and col in tipo[tabla].names:
            return str(tipo[tabla].field(col).type)
        return TIPO_CLAVE_DIMENSION.get((tabla, col))

    salida = []
    for rel in RELACIONES:
        r = {k: v for k, v in rel.items() if k != "columna_origen"}
        pares = []
        for a, b in zip(rel["clave_desde"], rel["clave_hacia"]):
            origen = rel.get("columna_origen")
            ta = de(*origen) if origen else de(rel["desde"], a)
            tb = de(rel["hacia"].split(" ")[0], b)
            pares.append({"desde": a, "hacia": b, "tipo_desde": ta, "tipo_hacia": tb})
        conocidos = [p for p in pares if p["tipo_desde"] and p["tipo_hacia"]]
        r["tipos"] = pares
        r["mismo_tipo"] = (all(p["tipo_desde"] == p["tipo_hacia"] for p in conocidos)
                           if len(conocidos) == len(pares) else None)
        if r["mismo_tipo"] is None:
            r["motivo_tipo"] = "una de las claves se calcula en la transformación y todavía no tiene tipo"
        salida.append(r)
    return salida


# ---------------------------------------------------------------------------------------------------------------
# 6. JSON e informe
# ---------------------------------------------------------------------------------------------------------------
def escribir_informe(res, ruta):
    """Genera informes/modelado-datos.md a partir del diccionario del JSON, sin cifras que no estén en él."""
    c = res.get("cifras_de_control", {})
    L = ["# Modelado de datos · caso 68", ""]
    L += ["## Fuente", "",
          f"- Diseño: `{res['diseno']}`. Ejecución: {res['fecha_ejecucion']}. Fecha de los datos: {res['fecha_datos']}.",
          *[f"- `{e['ruta']}`: {miles(e['filas'])} filas, {e['columnas']} columnas, huella `{e['sha256'][:16]}…`"
            for e in res["entradas"]], ""]
    L += ["## Resumen", "", f"**Estado {res['resultado']['estado']}.** {res['resultado']['resumen']}", "",
          f"Siguiente: {res['resultado']['siguiente']}", ""]
    if not c:
        L += ["El script paró antes de comprobar los datos.", ""]
    else:
        L += ["## Tablas y grano", "", "| Tabla | Tipo | Grano | Clave | Filas | Clave única | Filas repetidas |",
              "|---|---|---|---|---:|---|---:|"]
        for t in res["tablas"]:
            unica = {True: "sí", False: "**no**", None: "sin datos"}[t["clave_unica"]]
            filas = "" if t["filas"] is None else miles(t["filas"])
            rep = "" if t["filas_repetidas"] is None else t["filas_repetidas"]
            L.append(f"| {t['tabla']} | {t['tipo']} | {t['grano']} | {', '.join(t['clave_grano'])} | {filas} | {unica} | {rep} |")
        L += ["", f"- date distinta de fecha: {c['fotos.date_distinta_de_fecha']} filas en las fotos y "
                  f"{c['ventanas.date_distinta_de_fecha']} en las ventanas.",
              f"- Discos con dos fallos: {c['fallos.discos_con_dos_fallos']}. Fallos sin ventana: {c['fallos.sin_ventana']}; "
              f"sin la fila del día del fallo: {c['fallos.sin_fila_del_dia']}.",
              f"- Fallos de discos que no salen en ninguna foto: {c['fallos.discos_sin_foto']}.",
              f"- Modelos: {c['modelos.fotos']} en las fotos y {c['modelos.recuento']} en el recuento "
              f"({'los mismos' if c['modelos.fotos_igual_recuento'] else 'distintos'}); {c['modelos.ventanas']} en las "
              f"ventanas, {c['modelos.ventanas_fuera_del_recuento']} fuera del recuento. Con más de una capacidad: "
              f"{c['modelos.con_mas_de_una_capacidad']}. De arranque {c['modelos.arranque']} y de datos "
              f"{c['modelos.datos']}; entre 2 y 4 TB, {c['modelos.entre_arranque_y_datos']}.", ""]
        L += ["## Relaciones", "", "| Desde | Hacia | Clave | Maestro | Cardinalidad | Mismo tipo | Procedencia |",
              "|---|---|---|---|---|---|---|"]
        for x in res["relaciones"]:
            mt = {True: "sí", False: "**no**", None: "sin tipo aún"}[x["mismo_tipo"]]
            tipos = "; ".join(f"{p['desde']} {p['tipo_desde']} / {p['hacia']} {p['tipo_hacia']}" for p in x["tipos"]
                              if p["tipo_desde"] != p["tipo_hacia"])
            L.append(f"| {x['desde']} | {x['hacia']} | {', '.join(x['clave_desde'])} → {', '.join(x['clave_hacia'])} | "
                     f"{x['maestro']} | {x['cardinalidad']} | {mt}{(' (' + tipos + ')') if tipos and x['mismo_tipo'] is False else ''} | {x['procedencia']} |")
        L += [""]
        cal = res["calendario"]
        L += ["## Fechas y calendario", "",
              f"- Recuento: del {c['recuento.primer_dia']} al {c['recuento.ultimo_dia']}, {c['recuento.dias']} días; "
              f"faltan {c['recuento.dias_que_faltan']}.",
              f"- Fotos: {c['fotos.meses']} meses, del {c['fotos.primera']} al {c['fotos.ultima']}; "
              f"{c['fotos.fechas_no_dia_1']} fechas que no son día 1 y {c['fotos.meses_que_faltan']} meses que faltan.",
              f"- Ventanas: {c['ventanas.dias']} días; faltan {c['ventanas.dias_que_faltan_n']} dentro de su rango "
              f"({', '.join(c['ventanas.dias_que_faltan'][:5])}).",
              f"- Calendario: por {cal['periodo']}, del {cal['desde']} al {cal['hasta']}. "
              + (f"Construido en `{cal['fichero']}`." if cal["fichero"] else
                 "No se construye hasta que el diseño esté aprobado."), ""]
        L += ["## Registro de exclusiones", "", "| Clase | Sale de | Cómo se trata | Recuperable | Recuentos |",
              "|---|---|---|---|---|"]
        for e in res["exclusiones"]:
            rc = "; ".join(f"{k}: {v}" for k, v in e["recuentos"].items() if not isinstance(v, (dict, list)))
            L.append(f"| {e['que_sale']} | {e['sale_de']} | {e['como_se_trata']} | {e['recuperable']} | {rc} |")
        mb = {e["clase"]: e for e in res["exclusiones"]}["modelos_bajo_minimo"]["recuentos"]["por_ano"]
        L += ["", "Modelos de datos por debajo del mínimo, por año:", ""]
        L += [f"- {a}: {v['modelos_bajo_minimo']} de {v['modelos_con_dias']} modelos, con "
              f"{miles(v['dias_de_disco_bajo_minimo'])} días de disco y {v['fallos_bajo_minimo']} fallos; el año tiene "
              f"{v['dias_del_ano_en_datos']} días en los datos." for a, v in mb.items()]
        L += [""]
        p4 = res["pregunta_4"]
        L += ["## Población de la pregunta 4", "",
              f"- Filas del tablón: {miles(p4['filas_tablon'])} ({miles(p4['filas_tablon_construccion'])} de construcción y "
              f"{miles(p4['filas_tablon_validacion'])} de validación)."]
        for h in p4["horizonte_recortado"]:
            if h["fallos_horizonte"] is None:
                L.append(f"- Foto del {h['foto']} ({h['periodo']}): se recorta al {h['corte']}; {h['nota']}.")
            else:
                L.append(f"- Foto del {h['foto']} ({h['periodo']}): se recorta al {h['corte']}. De "
                         f"{h['fallos_disco_en_foto']} fallos de discos de la foto en su horizonte, el recorte pierde "
                         f"{h['fallos_perdidos_disco_en_foto']}.")
        L += [""]
    L += ["## Plan de cruces", "", "| Orden | Partida | Se une | Clave | Cardinalidad | Antes de cruzar | Control |",
          "|---:|---|---|---|---|---|---|"]
    for x in res["plan_cruces"]:
        L.append(f"| {x['orden']} | {x['partida']} | {x['se_une']} | {', '.join(x['clave_partida'])} → "
                 f"{', '.join(x['clave_une'])} | {x['cardinalidad']} | {x['agregar_antes'] or '—'} | "
                 f"{', '.join(x['magnitudes_control'])} |")
    L += ["", "## Decisiones pendientes", ""]
    L += [f"- {p['id']}: {p['pregunta']}" for p in res["pendientes"]] or ["- Ninguna."]
    L += ["", "## Datos personales", "", *[f"- {x}" for x in res["datos_personales_texto"]], ""]
    L += ["## Teoría aplicada", "", *[f"- {x}" for x in res["teoria"]], ""]
    L += ["## Límites", "", *[f"- {x}" for x in res["limites"]], ""]
    ruta.write_text("\n".join(L), encoding="utf-8")


def resultado_base(raiz):
    """El diccionario del JSON con el bloque común y lo que no depende de los datos."""
    return {
        "metodo": "modelado-datos", "version_metodo": "31/10/2026", "script": "scripts/04_modelado_datos.py",
        "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
        "entradas": [], "resultado": {}, "pendientes": [],
        "diseno": "config/modelo/modelo-datos.md",
        "aprobado": leer_aprobacion(raiz / "config" / "modelo" / "modelo-datos.md"),
        "parametros": {"limite_arranque_bytes": LIMITE_ARRANQUE_BYTES, "inicio_datos_bytes": INICIO_DATOS_BYTES,
                       "fin_construccion": iso(FIN_CONSTRUCCION), "fin_validacion": iso(FIN_VALIDACION),
                       "fin_reserva": iso(FIN_RESERVA), "inicio_sitio": iso(INICIO_SITIO),
                       "horizonte_dias": HORIZONTE_DIAS, "minimo_dias_ano": MINIMO_DIAS_ANO,
                       "minimo_fallos_edad": MINIMO_FALLOS_EDAD, "horas_ano": HORAS_ANO, "etiqueta_sin_dato": SIN_DATO},
        "tablas": [], "relaciones": [], "calendario": {"periodo": "día", "desde": None, "hasta": None,
                                                       "primer_periodo_completo": None, "ultimo_periodo_completo": None,
                                                       "fichero": None},
        "forma_entrega": "tablas_separadas", "plan_cruces": PLAN_CRUCES,
        "integracion_antes_de_transformar": False,
        "motivo_integracion": "ningún cruce del plan se puede hacer con las tablas tal como están: todos piden una "
                              "dimensión o el Calendario, que construye la transformación, o filtrar o agregar antes "
                              "por una regla (el día del fallo, el día anterior, el último día con sitio, el horizonte, "
                              "el reparto de días). Los hace la transformación con los controles de integracion-datos "
                              "(transformacion-datos)",
        "datos_personales_texto": [
            "No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección.",
            "No hay datos de personas (reglas, apartado 9): el número de serie identifica un disco, no a una persona.",
            "Este método no usa ni deja ninguna columna de datos personales."],
        "teoria": [
            "9.5, granularidad y cardinalidad: el grano de cada tabla y la cardinalidad de cada relación salen de las "
            "reglas y de la organización de los datos, no de los datos que se validan.",
            "12.5 y 12.6, cambiar el nivel: los días de disco se suman (flujo) y la foto del mes reparte (nivel); los "
            "hechos de grano distinto se llevan al grano común antes de unirse.",
            "14.9, regularizar una serie: el Calendario es diario y continuo; el recuento no tiene días que falten."],
        "limites": [
            "El script comprueba el grano y los tipos de las claves; si las claves casan entre tablas lo mide "
            "integracion-datos o la transformación con sus controles.",
            "En pandas, a diferencia de SQL, las claves vacías se emparejan entre sí al cruzar: el centro vacío de "
            "fotos y ventanas se iguala a «sin dato» antes de cruzar con el recuento.",
            "Un maestro que cambia con el tiempo se modela con la versión que hay: la fecha de compra y el precio de "
            "cada modelo se calculan con todo el periodo, como una ficha de hoy.",
            "La edad al fallar del registro de exclusiones usa las horas del día del fallo o del anterior y, sin "
            "ellas, la primera aparición; la regla exacta la fija la transformación.",
        ],
        "exclusiones": [], "pregunta_4": {}, "cifras_de_control": {}, "tiempos_segundos": {},
    }


# ---------------------------------------------------------------------------------------------------------------
# 7. Ejecución
# ---------------------------------------------------------------------------------------------------------------
def main():
    """Comprueba el diseño, escribe el JSON y el informe y, con el diseño aprobado, construye el Calendario."""
    parser = argparse.ArgumentParser(description="Comprobación del diseño del modelo de datos del caso 68")
    parser.add_argument("--raiz", default=str(CASO), help="carpeta del caso (para las pruebas)")
    raiz = Path(parser.parse_args().raiz).resolve()
    print("sys.executable:", sys.executable)
    res = resultado_base(raiz)
    ruta_json = raiz / "informes" / "modelado-datos.json"
    ruta_md = raiz / "informes" / "modelado-datos.md"
    inicio = time.perf_counter()
    codigo = 0
    try:
        # La entrada: sin la corrección lista y con sus huellas, no se comprueba nada
        entradas, motivo, *resto = comprobar_entrada(raiz)
        res["entradas"] = entradas
        res["pendientes"] = leer_cuestiones_abiertas(raiz / "config" / "negocio" / "cuestiones-pendientes.md")
        if motivo:
            res["resultado"] = {"estado": "PARADO", "riesgo": "alto", "resumen": f"No se comprueba el diseño: {motivo}.",
                                "artefactos": ["informes/modelado-datos.json", "informes/modelado-datos.md"],
                                "siguiente": "rehacer la corrección (scripts/03_correccion_datos.py) y volver a ejecutar"}
            codigo = 1
        else:
            tiempos = {}
            c, r, p4, ex, esquemas = comprobar_todo(raiz, resto[0], tiempos)
            res["cifras_de_control"], res["pregunta_4"] = c, p4
            filas = {"hechos_fotos": c["fotos.filas"], "hechos_ventanas": c["ventanas.filas"],
                     "hechos_recuento": c["recuento.filas"], "hechos_fallos": c["fallos.filas"]}
            for nombre, cfg in TABLAS.items():
                g = r.get(f"grano_{nombre}")
                res["tablas"].append({
                    "tabla": nombre, "fichero": cfg["fichero"], "grano": cfg["grano"], "clave_grano": cfg["clave_grano"],
                    "tipo": cfg["tipo"], "filas": filas.get(nombre),
                    "clave_unica": None if g is None else g["filas_repetidas"] == 0 and g["nulos_en_clave"] == 0,
                    "filas_repetidas": None if g is None else g["filas_repetidas"],
                    "nulos_en_clave": None if g is None else g["nulos_en_clave"], "nota": cfg["nota"]})
                if g is not None:
                    c[f"{nombre.replace('hechos_', '')}.clave_repetidas"] = g["filas_repetidas"]
            res["relaciones"] = tipos_relaciones(esquemas)
            res["exclusiones"] = [{"clase": k, **EXCLUSIONES_META[k], "recuentos": v} for k, v in ex.items()]
            # Una clave de grano repetida contradice el diseño: manda el dato y queda como pendiente
            for t in res["tablas"]:
                if t["clave_unica"] is False:
                    res["pendientes"].append({"id": f"GRANO-{t['tabla']}", "tabla": t["tabla"],
                                              "columna": ", ".join(t["clave_grano"]),
                                              "pregunta": f"la clave del grano de {t['tabla']} se repite en "
                                                          f"{t['filas_repetidas']} filas: el grano declarado no se cumple",
                                              "opciones": ["revisar el grano en el diseño", "corregir la tabla con correccion-datos"]})
            cal = construir_calendario(esquemas["primer_dia"], esquemas["ultimo_dia"])
            res["calendario"].update({"desde": iso(esquemas["primer_dia"]), "hasta": iso(esquemas["ultimo_dia"]),
                                      "dias": len(cal),
                                      "primer_periodo_completo": bool(cal["trimestre_completo"].iloc[0]),
                                      "ultimo_periodo_completo": bool(cal["trimestre_completo"].iloc[-1]),
                                      "trimestres_parciales": sorted({f"{a}T{t}" for a, t, ok in zip(
                                          cal["ano"], cal["trimestre"], cal["trimestre_completo"]) if not ok}),
                                      "anos_parciales": sorted({int(a) for a, ok in zip(cal["ano"], cal["ano_completo"])
                                                                if not ok}),
                                      "fecha_de_union": {"hechos_fotos": "fecha", "hechos_ventanas": "fecha",
                                                         "hechos_recuento": "fecha", "hechos_fallos": "dia_fallo"}})
            # El Calendario solo se guarda con el diseño aprobado y si pasa sus controles (continuo, sin repetidos)
            if res["aprobado"]["aprobado"]:
                continuo = cal["fecha"].is_unique and len(cal) == (esquemas["ultimo_dia"] - esquemas["primer_dia"]).days + 1
                if continuo:
                    destino = raiz / "data" / "processed" / "calendario.parquet"
                    pq.write_table(pa.Table.from_pandas(cal, preserve_index=False), destino)
                    res["calendario"]["fichero"] = "data/processed/calendario.parquet"
            grano_mal = [t["tabla"] for t in res["tablas"] if t["clave_unica"] is False]
            if not res["aprobado"]["aprobado"]:
                estado, siguiente = "PARADO", "falta la aprobación de el responsable del caso del diseño (config/modelo/modelo-datos.md)"
            else:
                estado = "AVISO" if res["pendientes"] else "OK"
                siguiente = "transformacion-datos, con el plan de cruces aprobado y los controles de integracion-datos"
            resumen = (f"Diseño comprobado sobre las cuatro tablas: {len(PLAN_CRUCES)} cruces en el plan y "
                       f"{len(res['exclusiones'])} clases en el registro de exclusiones. "
                       + (f"Claves de grano repetidas en {', '.join(grano_mal)}. " if grano_mal else
                          "Las cuatro claves de grano son únicas. ")
                       + (f"Decisiones pendientes para el responsable del caso: {len(res['pendientes'])}." if res["pendientes"] else ""))
            res["resultado"] = {"estado": estado, "riesgo": "medio", "resumen": resumen.strip(),
                                "artefactos": ["informes/modelado-datos.json", "informes/modelado-datos.md"]
                                + (["data/processed/calendario.parquet"] if res["calendario"]["fichero"] else []),
                                "siguiente": siguiente}
            res["tiempos_segundos"] = tiempos
    except Exception as error:  # el JSON se escribe también cuando falla (resultado.md, regla 5)
        res["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"Fallo técnico: {error!r}",
                            "artefactos": ["informes/modelado-datos.json"], "siguiente": "revisar el script"}
        codigo = 1
    res["tiempos_segundos"]["total"] = round(time.perf_counter() - inicio, 1)
    ruta_json.parent.mkdir(parents=True, exist_ok=True)
    ruta_json.write_text(json.dumps(res, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    escribir_informe(res, ruta_md)
    print(f"estado {res['resultado']['estado']} · {res['resultado']['resumen']}")
    print("tiempos (s):", res["tiempos_segundos"])
    return codigo


if __name__ == "__main__":
    sys.exit(main())
