"""Calidad de los datos del caso 68, averías de discos duros en Backblaze.

Diagnostica, sin corregir, juntar ni transformar nada, los cuatro datasets del caso (data/raw/podado/): fotos
mensuales, ventanas de fallo, recuento diario y lista de fallos. El esquema de Backblaze no es un dataset: solo entra
en la revisión de nombres.

Parte del diccionario del origen, contexto-proyecto/fuentes/diccionario-datos-origen.json, que escribe
scripts/01_diccionario_datos.py: tiene que existir, no estar PARADO ni en ERROR y ser más nuevo que ese script. De él
toma filas, tipos, roles, vacíos, valores distintos, variantes, categorías raras y la clase de cada campo.

Sigue el plan aprobado por Juan el 17/11/2026 (informes/plan_calidad_datos.md, «Lo aprobado»). En validación (del
01/07/2024 al 30/06/2025) solo cuenta filas, vacíos y formatos: las colas, los atípicos y el objetivo se miran con la
construcción, y nada se compara contra el fallo.

Escribe informes/calidad-datos.json y, a partir de él, informes/calidad-datos.md.

Uso: python -W error scripts/02_calidad_datos.py
Skill: calidad-datos (versión 11/11/2026, WF-87), con programacion-del-caso.
"""

# =================================================================================================================
# 1. Configuración
# =================================================================================================================
import datetime as dt
import hashlib
import json
import platform
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

# -----------------------------------------------------------------------------------------------------------------
# 1.1 Rutas y versión
# -----------------------------------------------------------------------------------------------------------------
CASO = Path(__file__).resolve().parents[1]
SCRIPT_DICCIONARIO = Path(__file__).resolve().parent / "01_diccionario_datos.py"
SKILL = "calidad-datos"
VERSION_SKILL = "11/11/2026 (WF-87)"
SCRIPT = "scripts/02_calidad_datos.py"

# -----------------------------------------------------------------------------------------------------------------
# 1.2 Fechas de las reglas de negocio: §5 (referencia), §7 (partición) y §4 (desde cuándo consta el sitio)
# -----------------------------------------------------------------------------------------------------------------
FECHA_DATOS = "2025-06-30"
INICIO_SITIO = dt.date(2023, 7, 1)
FIN_CONSTRUCCION = dt.date(2024, 6, 30)
INICIO_VALIDACION = dt.date(2024, 7, 1)
FIN_DATOS = dt.date(2025, 6, 30)
EPOCA = dt.date(1970, 1, 1)

# -----------------------------------------------------------------------------------------------------------------
# 1.3 Parámetros de la skill (parametros.md), con los valores del plan aprobado
# -----------------------------------------------------------------------------------------------------------------
LIMITE_IQR = 1.5
LIMITE_Z = 3.5
# La desviación absoluta mediana se lleva a la escala de una desviación típica con 1 / Φ⁻¹(0,75), como scipy
# (median_abs_deviation con scale="normal"); es el z robusto de Iglewicz y Hoaglin, que usa el límite de 3,5
ESCALA_MAD = 1.482602218505602
SEGMENTO_MIN = 30
FACTOR_CONCENTRACION = 2.0
RARA_PCT = 2.5
RARA_MIN = 5
CODIGO_PCT = 5.0
COLAS_N = 10
HORIZONTE = FIN_DATOS
# Columna casi vacía: el plan aprobado cuenta 49 columnas de las fotos vacías en más del 99 % de las filas que las traen
CASI_VACIA_PCT = 99.0

PARAMETROS = [
    {"nombre": "límite del rango intercuartílico", "valor": LIMITE_IQR, "origen": "por defecto; las reglas no fijan otro"},
    {"nombre": "límite del z robusto", "valor": LIMITE_Z, "origen": "por defecto; las reglas no fijan otro"},
    {"nombre": "segmento mínimo para el reparto de nulos", "valor": SEGMENTO_MIN, "origen": "por defecto"},
    {"nombre": "concentración de nulos en un segmento", "valor": f"{FACTOR_CONCENTRACION:g} veces el porcentaje global",
     "origen": "por defecto"},
    {"nombre": "categoría rara", "valor": f"menos del {str(RARA_PCT).replace('.', ',')} % de las filas o menos de {RARA_MIN} apariciones",
     "origen": "diccionario-datos, el mismo que usó el diccionario del origen"},
    {"nombre": "código de ausencia numérico candidato", "valor": f"un valor en un extremo del rango con el {CODIGO_PCT:g} % de las filas o más",
     "origen": "por defecto; se fijó sin fuente y este caso es de los primeros que lo usan"},
    {"nombre": "colas de cada magnitud", "valor": COLAS_N, "origen": "por defecto"},
    {"nombre": "fecha de Excel candidata", "valor": "no aplica",
     "origen": "plan aprobado: ninguna fecha llega como número, vienen como fecha o como texto ISO"},
    {"nombre": "horizonte de fechas futuras", "valor": HORIZONTE.isoformat(), "origen": "reglas de negocio §5, fecha de referencia"},
    {"nombre": "columna casi vacía", "valor": f"más del {CASI_VACIA_PCT:g} % de vacíos en las filas que traen la columna",
     "origen": "plan aprobado, bloque 3.2"},
]

# -----------------------------------------------------------------------------------------------------------------
# 1.4 Reglas de negocio llevadas a código (reglas-negocio.md) y lo que fija el plan aprobado
# -----------------------------------------------------------------------------------------------------------------
# Reglas §3: los discos de arranque son los de 0,2 a 2 TB; los de datos, de 4 TB o más; -1 y 0,1 TB son lecturas malas.
# El grupo de una fila sale de la capacidad de su modelo. Los cortes caen en huecos donde no hay ninguna capacidad.
CAPACIDAD_MIN_VALIDA = 2e11
CAPACIDAD_MAX_ARRANQUE = 3e12
GRUPOS = ["datos", "arranque", "sin capacidad única"]

# Reglas §3: el fabricante sale del nombre del modelo, con dos excepciones
PREFIJOS_FABRICANTE = (("TOSHIBA ", "Toshiba"), ("WDC ", "WDC"), ("HGST ", "HGST"), ("ST", "Seagate"))
EXCEPCIONES_FABRICANTE = {"Hitachi HDS5C4040ALE630": "HGST", "WUH721816ALE6L4": "WDC"}
FABRICANTES = ["Seagate", "Toshiba", "WDC", "HGST", "sin patrón"]

# Reglas §3: los cinco contadores de avería; reglas §5 y plan: los de formato propio de cada fabricante
CONTADORES_AVERIA = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]
FORMATO_PROPIO = ["smart_1_raw", "smart_7_raw", "smart_188_raw", "smart_195_raw"]
HORAS = "smart_9_raw"
TEMPERATURA = "smart_194_raw"
COLUMNAS_SITIO = ["datacenter", "cluster_id", "vault_id", "pod_id", "pod_slot_num"]

# Plan aprobado: el 188 se mira por encima de mil millones (D2); el 5 y el 187 pegados al tope de 16 bits (D3);
# la temperatura entre 10 y 70 grados (RC-04); horas que bajan más de un día y más de un año (reconocimiento)
UMBRAL_188 = 1e9
TOPE_16_BITS = 65535
TEMPERATURA_MIN, TEMPERATURA_MAX = 10, 70
HORAS_DIA, HORAS_ANO = 24, 8760

# Objetivo del modelo a 30 días (CP-004); a 90 días, el que usó el reconocimiento, para comparar
HORIZONTES_OBJETIVO = (30, 90)

# Días hundidos del recuento que dejó el reconocimiento para este paso (plan aprobado)
DIAS_HUNDIDOS = ["2022-06-06", "2023-03-19", "2023-04-13", "2023-04-16", "2023-07-05", "2023-12-18", "2025-05-12"]

# Textos que se buscan como códigos de ausencia (SKILL §3.4 y comprobaciones §4), en minúsculas y sin espacios de los lados
TEXTOS_AUSENCIA = {"", "none", "null", "nan", "n/a", "na", "-", "pendiente", "unknown", "desconocido", "sin dato", "sin datos",
                   "0000-00-00", "1900-01-01"}
# Reglas §4 y §5: «sin dato» del centro en el recuento quiere decir que no consta
TEXTOS_DOCUMENTADOS = {("recuento_diario", "datacenter", "sin dato"): "reglas de negocio §4 y §5"}
PATRON_INSTRUCCION = re.compile(r"ignor|recalcul|instrucci|olvida|prompt", re.I)
PATRON_ISO = r"\d{4}-\d{2}-\d{2}"

# Lo que el plan aprobado cerró el 17/11/2026 como criterio técnico (Juan: «Sí, apruebo»)
LO_CERRADO = {
    "D1": {"fecha": "2026-11-17", "pendientes_del_diccionario": ["P-01", "P-05", "P-09"],
           "texto": "los modelos que solo se distinguen por los dos espacios tras «WDC» son el mismo modelo; los junta la corrección"},
    "D2": {"fecha": "2026-11-17", "pendientes_del_diccionario": ["P-04", "P-08"],
           "texto": "el 188 cuenta como aviso cuando pasa de cero (reglas §3) y no entra en la suma de la regla de los contadores (reglas §7, CP-010)"},
    "D3": {"fecha": "2026-11-17", "pendientes_del_diccionario": ["P-02", "P-03", "P-06", "P-07"],
           "texto": "el 5 y el 187 pegados a 65.535 son el tope del contador; el disco avisa igual"},
    "D4": {"fecha": "2026-11-17", "pendientes_del_diccionario": [],
           "texto": "el 0 de cluster_id no se decide, porque ninguna pregunta usa esa columna: se cuenta y se dice"},
}
PLAN_APROBADO = {"por": "Juan", "fecha": "2026-11-17"}
# Las ocho reglas candidatas entraron como comprobaciones con el plan aprobado («Lo aprobado»)
RC_APROBADAS_CON_EL_PLAN = True
# Qué lado de cada relación cuenta como problema si se queda sin pareja; el otro lado sin pareja es lo normal
LADOS_QUE_CUENTAN = {("fallos", "ventanas_fallo"): ("izquierda", "derecha"), ("fallos", "fotos_mensuales"): (),
                     ("ventanas_fallo", "fotos_mensuales"): ("izquierda", "derecha"), ("recuento_diario", "fotos_mensuales"): ("izquierda", "derecha"),
                     ("recuento_diario", "ventanas_fallo"): ("derecha",), ("recuento_diario", "fallos"): ("izquierda", "derecha")}

# Las ocho reglas candidatas del plan, aprobadas por Juan como comprobaciones el 17/11/2026
REGLAS_CANDIDATAS = [
    ("RC-01", "fotos_mensuales", ["smart_9_raw"], "Las horas encendido de un disco no bajan entre dos fotos."),
    ("RC-02", "fotos_mensuales", ["model", "capacity_bytes"], "El modelo y la capacidad de un disco no cambian entre fotos."),
    ("RC-03", "fotos_mensuales", CONTADORES_AVERIA, "Los cinco contadores de avería no bajan con el tiempo en un mismo disco."),
    ("RC-04", "fotos_mensuales y ventanas_fallo", [TEMPERATURA], "La temperatura está entre 10 y 70 grados."),
    ("RC-05", "fotos_mensuales y fallos", ["failure", "serial_number", "fecha", "dia_fallo"],
     "Toda foto con failure = 1 está en la lista de fallos, el mismo disco y el mismo día."),
    ("RC-06", "ventanas_fallo", ["failure", "fecha", "dia_fallo"], "En cada ventana, failure = 1 solo el día del fallo."),
    ("RC-07", "recuento_diario", ["fallos", "discos"], "En el recuento, los fallos no pasan de los discos de su fila."),
    ("RC-08", "recuento_diario y fallos", ["fallos", "fecha", "dia_fallo"],
     "Los fallos de cada día del recuento suman los de la lista de fallos de ese día."),
]

TABLAS = ["fotos_mensuales", "ventanas_fallo", "recuento_diario", "fallos"]
NOMBRE_TABLA = {"fotos_mensuales": "fotos mensuales", "ventanas_fallo": "ventanas de fallo", "recuento_diario": "recuento diario",
                "fallos": "lista de fallos", "esquema_backblaze": "esquema de Backblaze"}
TEORIA = ("Manual 7.1 y 7.2 para el orden del diagnóstico; 7.3 para los vacíos por fila y los códigos de ausencia; 7.4 para "
          "los duplicados con clave; 7.5 y 33.10 para las categorías raras; 7.6, 3.6 y 33.9 para la escala, las colas y los "
          "atípicos, que se miden en la construcción porque lo que se aprende de los datos se ajusta solo con ella (33.2); "
          "14.13 para comprobar que las fechas son fechas; 7.8 a 7.10 antes de dar el diagnóstico por terminado.")


# =================================================================================================================
# 2. Utilidades
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leída por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


def huellas(carpeta):
    """Huella de cada fichero de una carpeta, por su ruta relativa."""
    return {p.relative_to(carpeta).as_posix(): sha256(p) for p in sorted(carpeta.rglob("*")) if p.is_file()}


def dia_de(fecha):
    """Número de día desde el 01/01/1970 de una fecha."""
    return (fecha - EPOCA).days


def a_json(valor):
    """Pasa a tipos que JSON acepta: enteros, decimales sin NaN, listas y diccionarios."""
    if isinstance(valor, dict):
        return {str(k): a_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [a_json(v) for v in valor]
    if isinstance(valor, (np.bool_, bool)):
        return bool(valor)
    if isinstance(valor, (np.integer,)):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        v = float(valor)
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return int(v) if v.is_integer() and abs(v) < 2**53 else round(v, 6)
    if isinstance(valor, dt.datetime):
        return pd.Timestamp(valor).isoformat()
    if isinstance(valor, dt.date):
        return valor.isoformat()
    return valor


def pct(parte, total):
    """Porcentaje con cuatro decimales; null si el total es cero."""
    return round(100.0 * parte / total, 4) if total else None


def grupo_de_capacidad(capacidad):
    """Grupo de una capacidad válida: datos o arranque (reglas §3)."""
    return "arranque" if capacidad < CAPACIDAD_MAX_ARRANQUE else "datos"


def fabricante_de(modelo):
    """Fabricante de un modelo por su nombre, con las dos excepciones de las reglas §3; «sin patrón» si no sigue ninguno."""
    if modelo in EXCEPCIONES_FABRICANTE:
        return EXCEPCIONES_FABRICANTE[modelo]
    for prefijo, fabricante in PREFIJOS_FABRICANTE:
        if modelo.startswith(prefijo):
            return fabricante
    return "sin patrón"


def modelo_normalizado(modelo):
    """El modelo con un solo espacio entre palabras: solo para contar las variantes de D1, no se guarda."""
    return " ".join(str(modelo).split())


def nombre_normalizado(nombre):
    """Nombre de columna en minúsculas, sin tildes y con guion bajo (comprobaciones §9)."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sin_tildes.lower()).strip("_")


def leer_tabla(ruta, columnas):
    """Lee de un Parquet las columnas pedidas que traiga, con el centro siempre como texto, y añade vacías las que falten."""
    pf = pq.ParquetFile(ruta)
    presentes = [c for c in columnas if c in pf.schema_arrow.names]
    t = pf.read(columns=presentes)
    if "datacenter" in presentes and pa.types.is_null(t.schema.field("datacenter").type):
        t = t.set_column(t.schema.get_field_index("datacenter"), "datacenter", t["datacenter"].cast(pa.string()))
    df = t.to_pandas()
    for c in columnas:
        if c not in df.columns:
            df[c] = pd.Series(np.nan, index=df.index, dtype="float64")
    return df[columnas]


# =================================================================================================================
# 3. El diccionario del origen
# =================================================================================================================
def leer_diccionario(raiz, huella_raw):
    """Lee el diccionario del origen y comprueba que describe estos mismos ficheros (resultado.md, «Al empezar»)."""
    ruta = raiz / "contexto-proyecto" / "fuentes" / "diccionario-datos-origen.json"
    if not ruta.exists():
        raise FileNotFoundError("no existe el diccionario del origen: hay que ejecutar antes scripts/01_diccionario_datos.py")
    if ruta.stat().st_mtime < SCRIPT_DICCIONARIO.stat().st_mtime:
        raise RuntimeError("el diccionario del origen es más viejo que el script que lo escribe: hay que volver a ejecutarlo")
    dic = json.loads(ruta.read_text(encoding="utf-8"))
    if dic["resultado"]["estado"] in ("PARADO", "ERROR"):
        raise RuntimeError(f"el diccionario del origen está en {dic['resultado']['estado']}: no se empieza")
    suyas = {e["ruta"].removeprefix("data/raw/"): e["sha256"] for e in dic["entradas"]}
    coincide = suyas == huella_raw
    tablas = {t["tabla"]: t for t in dic["tablas"]}
    campos = {nombre: {c["columna"]: c for c in t["campos"]} for nombre, t in tablas.items()}
    return dic, tablas, campos, coincide


# =================================================================================================================
# 4. Dimensiones de cada fila de las fotos y las ventanas
# =================================================================================================================
class Catalogo:
    """Códigos enteros para los modelos y los centros que van apareciendo, para segmentar sin guardar texto por fila."""

    def __init__(self, primero=None):
        self.valores, self.indice = [], {}
        if primero is not None:
            self.codigo(primero)

    def codigo(self, valor):
        """Código de un valor, que se crea si es nuevo."""
        if valor not in self.indice:
            self.indice[valor] = len(self.valores)
            self.valores.append(valor)
        return self.indice[valor]

    def codificar(self, columna):
        """Pasa una columna de pyarrow a códigos; el vacío va al código de None."""
        unicos = pc.unique(columna)
        unicos = unicos.combine_chunks() if isinstance(unicos, pa.ChunkedArray) else unicos
        mapa = np.array([self.codigo(v) for v in unicos.to_pylist()], dtype=np.int32)
        local = pc.index_in(columna, value_set=unicos)
        local = (local.combine_chunks() if isinstance(local, pa.ChunkedArray) else local).fill_null(0).to_numpy()
        if columna.null_count and None not in unicos.to_pylist():
            raise ValueError("vacío sin código")
        return mapa[local]


def leer_dimensiones(ficheros, columna_periodo, modelos, centros):
    """Lee fichero a fichero la fecha, el periodo, el modelo, la capacidad y el centro de cada fila."""
    partes = {k: [] for k in ("dia", "dia_periodo", "modelo", "capacidad", "centro")}
    filas, pfs = [], []
    for ruta in ficheros:
        pf = pq.ParquetFile(ruta)
        cols = ["fecha", "model", "capacity_bytes", "datacenter"] + ([columna_periodo] if columna_periodo != "fecha" else [])
        t = pf.read(columns=cols)
        partes["dia"].append(t["fecha"].to_numpy().astype("datetime64[D]").astype(np.int32))
        partes["dia_periodo"].append(t[columna_periodo].to_numpy().astype("datetime64[D]").astype(np.int32))
        partes["modelo"].append(modelos.codificar(t["model"]))
        partes["capacidad"].append(pc.cast(t["capacity_bytes"], pa.float64()).to_numpy())
        centro = t["datacenter"].cast(pa.string()) if pa.types.is_null(t.schema.field("datacenter").type) else t["datacenter"]
        partes["centro"].append(centros.codificar(centro))
        filas.append(t.num_rows)
        pfs.append(pf)
    d = {k: np.concatenate(v) for k, v in partes.items()}
    d["filas_por_fichero"] = filas
    d["offsets"] = np.r_[0, np.cumsum(filas)]
    d["pfs"] = pfs
    d["ficheros"] = ficheros
    return d


def completar_dimensiones(d, grupo_modelo, fabricante_modelo):
    """Añade a cada fila sus dimensiones del reparto: periodo, año, fabricante, grupo y sitio (plan aprobado)."""
    d["periodo"] = np.where(d["dia_periodo"] < dia_de(INICIO_VALIDACION), 0,
                            np.where(d["dia_periodo"] <= dia_de(FIN_DATOS), 1, 2)).astype(np.int8)
    fechas = d["dia"].astype("datetime64[D]")
    anos = fechas.astype("datetime64[Y]").astype(np.int32) + 1970
    d["mes"] = fechas.astype("datetime64[M]").astype(np.int32)
    d["anos"] = np.unique(anos).tolist()
    d["ano"] = np.searchsorted(np.array(d["anos"]), anos).astype(np.int8)
    d["sitio"] = (d["dia"] >= dia_de(INICIO_SITIO)).astype(np.int8)
    d["grupo"] = grupo_modelo[d["modelo"]]
    d["fabricante"] = fabricante_modelo[d["modelo"]]
    d["invalida"] = d["capacidad"] < CAPACIDAD_MIN_VALIDA
    return d


def etiquetas_dimension(d, nombre, modelos):
    """Códigos de cada fila y nombres de los segmentos de una dimensión."""
    return {"periodo": (d["periodo"], ["construcción", "validación", "fuera de los datos"]),
            "fabricante": (d["fabricante"], FABRICANTES),
            "año": (d["ano"], [str(a) for a in d["anos"]]),
            "grupo": (d["grupo"], GRUPOS),
            "sitio": (d["sitio"], ["antes del 01/07/2023", "desde el 01/07/2023"]),
            "modelo": (d["modelo"], modelos.valores)}[nombre]


# =================================================================================================================
# 5. Cálculos de una columna: reparto de vacíos, escala, colas y atípicos
# =================================================================================================================
def veredicto_reparto(filas, nulos):
    """Veredicto del reparto de vacíos en una dimensión (SKILL §3.4): sin nulos, repartidos, concentrados o no se puede saber."""
    total, vacios = int(filas.sum()), int(nulos.sum())
    if vacios == 0:
        return "sin_nulos", 0.0
    glob = vacios / total
    validos = filas >= SEGMENTO_MIN
    if validos.sum() < 2:
        return "no_se_puede_saber", round(100 * glob, 4)
    tasas = np.divide(nulos, filas, out=np.zeros(len(filas)), where=filas > 0)
    concentrado = bool(np.any(tasas[validos] >= FACTOR_CONCENTRACION * glob))
    return ("concentrados" if concentrado else "repartidos"), round(100 * glob, 4)


def escala(valores):
    """Cuántas cifras enteras tiene cada valor y si hay un salto de orden de magnitud sin valores en medio (comprobaciones §3)."""
    if len(valores) == 0:
        return None
    a = np.abs(valores)
    cifras = np.where(a < 1, 1, np.floor(np.log10(np.maximum(a, 1))) + 1).astype(np.int16)
    n, cuenta = np.unique(cifras, return_counts=True)
    huecos = np.diff(n) - 1
    salto = bool(np.any(huecos > 0))
    return {"cifras": {str(int(k)): int(v) for k, v in zip(n, cuenta)}, "salto": salto,
            "factor": int(10 ** (int(huecos.max()) + 1)) if salto else None, "factor_uniforme": None}


def colas(ordenados):
    """Los diez valores distintos más bajos y más altos, con su recuento, y el mayor salto entre dos seguidos (comprobaciones §7)."""
    if len(ordenados) == 0:
        return None
    inicios = np.r_[0, np.flatnonzero(np.diff(ordenados)) + 1]
    valores = ordenados[inicios]
    cuentas = np.diff(np.r_[inicios, len(ordenados)])
    salto = {"desde": None, "hasta": None}
    if len(valores) > 1:
        i = int(np.argmax(np.diff(valores)))
        salto = {"desde": valores[i], "hasta": valores[i + 1]}
    return {"distintos": len(valores),
            "bajos": [{"valor": v, "filas": int(c)} for v, c in zip(valores[:COLAS_N], cuentas[:COLAS_N])],
            "altos": [{"valor": v, "filas": int(c)} for v, c in zip(valores[-COLAS_N:], cuentas[-COLAS_N:])],
            "mayor_salto": salto}


def atipicos(ordenados):
    """Atípicos por rango intercuartílico y por z robusto sobre valores ya ordenados (SKILL §3.8); solo detectan."""
    n = len(ordenados)
    vacio = {"iqr": None, "z_robusto": None, "los_dos": None, "limite_iqr": LIMITE_IQR, "limite_z": LIMITE_Z, "motivo": None}
    if n == 0:
        return {**vacio, "motivo": "sin valores"}
    q1, mediana, q3 = np.quantile(ordenados, [0.25, 0.5, 0.75])
    mad = float(np.median(np.abs(ordenados - mediana)))
    rango = q3 - q1
    salida = {**vacio, "q1": q1, "mediana": mediana, "q3": q3, "mad": mad}
    motivos = []
    lo = hi = lo_z = hi_z = None
    if rango > 0:
        lo, hi = q1 - LIMITE_IQR * rango, q3 + LIMITE_IQR * rango
        salida["iqr"] = int(np.searchsorted(ordenados, lo, "left") + n - np.searchsorted(ordenados, hi, "right"))
        salida["corte_iqr"] = [lo, hi]
    else:
        motivos.append("rango intercuartílico cero: no se marca ningún atípico por este método")
    if mad > 0:
        ancho = LIMITE_Z * mad * ESCALA_MAD
        lo_z, hi_z = mediana - ancho, mediana + ancho
        salida["z_robusto"] = int(np.searchsorted(ordenados, lo_z, "left") + n - np.searchsorted(ordenados, hi_z, "right"))
        salida["corte_z"] = [lo_z, hi_z]
    else:
        motivos.append("desviación absoluta mediana cero: no se marca ningún atípico por este método")
    if lo is not None and lo_z is not None:
        salida["los_dos"] = int(np.searchsorted(ordenados, min(lo, lo_z), "left") + n - np.searchsorted(ordenados, max(hi, hi_z), "right"))
    salida["motivo"] = "; ".join(motivos) or None
    return salida


def leer_columna(d, columna):
    """Lee una columna numérica de todos los ficheros, con NaN en los vacíos, y dice en qué filas existe y qué tipos trae."""
    n = int(d["offsets"][-1])
    x = np.full(n, np.nan)
    presente = np.zeros(n, dtype=bool)
    tipos, muestra = Counter(), []
    for i, pf in enumerate(d["pfs"]):
        if columna not in pf.schema_arrow.names:
            continue
        a, b = d["offsets"][i], d["offsets"][i + 1]
        col = pf.read(columns=[columna]).column(0)
        tipos[str(col.type)] += len(col)
        presente[a:b] = True
        if not pa.types.is_null(col.type):
            x[a:b] = pc.cast(col, pa.float64()).to_numpy()
        if len(muestra) < 3:
            for v in pc.unique(col.drop_null()).to_pylist():
                if len(muestra) < 3 and v not in muestra:
                    muestra.append(v)
    return x, presente, tipos, muestra


def nulos_texto(d, columna):
    """Vacíos de una columna de texto o fecha, fila a fila, en qué filas existe la columna y tres valores de muestra."""
    n = int(d["offsets"][-1])
    nul = np.zeros(n, dtype=bool)
    presente = np.zeros(n, dtype=bool)
    muestra = []
    for i, pf in enumerate(d["pfs"]):
        if columna in pf.schema_arrow.names:
            a, b = d["offsets"][i], d["offsets"][i + 1]
            presente[a:b] = True
            col = pf.read(columns=[columna]).column(0)
            nul[a:b] = col.is_null().to_numpy()
            if len(muestra) < 3 and not pa.types.is_null(col.type):
                for v in pc.unique(col.drop_null()).to_pylist()[:3]:
                    if len(muestra) < 3 and v not in muestra:
                        muestra.append(v.date().isoformat() if isinstance(v, dt.datetime) else v)
    return nul, presente, muestra


def reparto_de_nulos(tabla, columna, nul, presente, d, dimensiones, modelos, cache):
    """Porcentaje de vacíos por segmento en cada dimensión y su veredicto (SKILL §3.4)."""
    total, vacios = int(presente.sum()), int(nul.sum())
    if vacios == 0:
        return None
    clave_presencia = hash(presente[d["offsets"][:-1]].tobytes())
    glob = vacios / total
    por_dimension, veredictos = [], []
    for nombre in dimensiones:
        codigos, etiquetas = etiquetas_dimension(d, nombre, modelos)
        k = len(etiquetas)
        if (nombre, clave_presencia) not in cache:
            cache[(nombre, clave_presencia)] = np.bincount(codigos[presente], minlength=k)
        filas = cache[(nombre, clave_presencia)]
        nulos = np.bincount(codigos[nul], minlength=k)
        veredicto, _ = veredicto_reparto(filas, nulos)
        veredictos.append(veredicto)
        segmentos = []
        for i in np.flatnonzero(filas):
            tasa = nulos[i] / filas[i]
            explica = filas[i] >= SEGMENTO_MIN and tasa >= FACTOR_CONCENTRACION * glob
            if nombre != "modelo" or explica:
                segmentos.append({"segmento": etiquetas[i], "pct": round(100 * tasa, 4), "filas": int(filas[i]), "nulos": int(nulos[i]),
                                  "concentra": bool(explica)})
        por_dimension.append({"dimension": nombre, "veredicto": veredicto, "segmentos": segmentos,
                              **({"modelos_con_filas": int((filas > 0).sum())} if nombre == "modelo" else {})})
    general = ("concentrados" if "concentrados" in veredictos else "repartidos" if "repartidos" in veredictos else "no_se_puede_saber")
    return {"tabla": tabla, "columna": columna, "global_pct": round(100 * glob, 4), "filas": total, "nulos": vacios,
            "dimensiones": dimensiones, "veredicto": general, "por_dimension": por_dimension,
            "segmentos": [dict(s, dimension=p["dimension"]) for p in por_dimension for s in p["segmentos"] if s["concentra"]]}


# =================================================================================================================
# 6. Fotos y ventanas, columna a columna
# =================================================================================================================
def vacios_por_tramo(columna, nul, presente, d, centros):
    """Vacíos por periodo de las columnas que miran las reglas y, en las de sitio, antes y desde el 01/07/2023 (reglas §4)."""
    e = {}
    if columna in COLUMNAS_SITIO or columna in CONTADORES_AVERIA or columna in (HORAS, TEMPERATURA, "capacity_bytes", "failure"):
        e["vacios_por_periodo"] = [int((nul & (d["periodo"] == p)).sum()) for p in (0, 1)]
        e["filas_por_periodo"] = [int((presente & (d["periodo"] == p)).sum()) for p in (0, 1)]
    if columna in COLUMNAS_SITIO:
        for tramo, codigo in (("antes_sitio", 0), ("desde_sitio", 1)):
            e[tramo] = {"filas": int((d["sitio"] == codigo).sum()), "sin_columna": int(((d["sitio"] == codigo) & ~presente).sum()),
                        "vacios": int((nul & (d["sitio"] == codigo)).sum())}
        desde = nul & (d["sitio"] == 1)
        e["vacios_desde_sitio_por_grupo"] = {GRUPOS[i]: int(n) for i, n in enumerate(np.bincount(d["grupo"][desde], minlength=3)) if n}
        e["vacios_desde_sitio_por_periodo"] = [int((desde & (d["periodo"] == p)).sum()) for p in (0, 1)]
        e["vacios_desde_sitio_por_centro"] = {str(centros.valores[i]): int(n) for i, n in enumerate(np.bincount(d["centro"][desde], minlength=len(centros.valores))) if n}
    return e


def perfilar_columnas(tabla, d, campos, modelos, centros, salida):
    """Recorre cada columna de una tabla partida en ficheros: tipos, vacíos por segmento, escala, colas, atípicos y códigos."""
    cache = {}
    construccion = d["periodo"] == 0
    datos = d["grupo"] == 0
    especiales = {}
    for columna, ficha in campos.items():
        rol = ficha["rol"]
        es_smart = columna.startswith("smart_")
        dimensiones = ["periodo", "fabricante", "año", "grupo"] + (["sitio"] if columna in COLUMNAS_SITIO else []) + (["modelo"] if es_smart else [])
        tipo = {"tabla": tabla, "columna": columna, "leido": ficha["tipo_leido"], "rol": rol, "pct_no_convierte": 0.0, "muestra": [], "aviso": None}
        if rol in ("magnitud", "codigo", "booleana") and ficha["tipo_leido"] not in ("string",):
            x, presente, tipos, muestra = leer_columna(d, columna)
            nul = presente & np.isnan(x)
            v = x[presente & ~nul]
            tipo["toca"] = {"magnitud": "número entero", "codigo": "entero (código)", "booleana": "booleano 0/1"}[rol]
            tipo["muestra"] = muestra
            no_conv = int(np.count_nonzero(v != np.floor(v))) if rol != "booleana" else int(np.count_nonzero(~np.isin(v, [0, 1])))
            tipo["pct_no_convierte"] = pct(no_conv, len(v)) or 0.0
            if rol == "codigo":
                tipo["aviso"] = "codigo_numerico"
            if len(tipos) > 1:
                tipo["tipos_por_fichero"] = dict(tipos)
        else:
            nul, presente, muestra = nulos_texto(d, columna)
            x, v = None, None
            tipo["toca"] = {"fecha": "fecha", "categorica": "texto", "identificador": "texto"}.get(rol, "texto")
            tipo["muestra"] = muestra
        salida["tipos"].append(tipo)
        # Los vacíos se toman del diccionario; el recuento propio se compara con él para ver que es la misma fuente
        if int(nul.sum()) != ficha["nulos"] + (ficha.get("nan") or 0):
            raise RuntimeError(f"{tabla}.{columna}: {int(nul.sum())} vacíos frente a {ficha['nulos']} del diccionario")
        r = reparto_de_nulos(tabla, columna, nul, presente, d, dimensiones, modelos, cache)
        if r:
            salida["nulos_por_segmento"].append(r)
        # Regla §5: un contador vacío quiere decir que ese modelo no lo apunta; se mira modelo a modelo
        if es_smart and columna.endswith("_raw"):
            k = len(modelos.valores)
            for etiqueta, mascara in (("todas", presente), ("sin_capacidad_no_valida", presente & ~d["invalida"])):
                filas_m = np.bincount(d["modelo"][mascara], minlength=k)
                nulos_m = np.bincount(d["modelo"][mascara & nul], minlength=k)
                parciales = [{"modelo": modelos.valores[i], "filas": int(filas_m[i]), "vacios": int(nulos_m[i])}
                             for i in np.flatnonzero(filas_m) if 0 < nulos_m[i] < filas_m[i]]
                salida["contadores_por_modelo"].append({"tabla": tabla, "columna": columna, "filas": etiqueta,
                                                        "modelos_con_filas": int((filas_m > 0).sum()),
                                                        "modelos_todo_vacio": int(((nulos_m == filas_m) & (filas_m > 0)).sum()),
                                                        "modelos_parciales": parciales})
        # Vacíos por periodo y por tramo del sitio: valen también para el centro, que es texto
        e = vacios_por_tramo(columna, nul, presente, d, centros)
        if x is None:
            if e:
                especiales[columna] = e
            continue
        # Escala con todas las filas (es formato); colas y atípicos con la construcción (manual 33.2)
        if rol == "magnitud":
            salida["escala"].append({"tabla": tabla, "columna": columna, **escala(v)})
            cons = np.sort(x[construccion & presente & ~nul])
            c = colas(cons)
            salida["colas"].append({"tabla": tabla, "columna": columna, "filas": "construcción", **(c or {"bajos": [], "altos": [], "mayor_salto": None})})
            salida["outliers"].append({"tabla": tabla, "columna": columna, "filas": "construcción", "valores": len(cons), **atipicos(cons)})
            del cons
        # Códigos numéricos en un extremo del rango (comprobaciones §4); en los contadores el cero es un valor (reglas §5)
        if rol == "magnitud" or columna in COLUMNAS_SITIO:
            for extremo, valor in (("mínimo", np.min(v) if len(v) else None), ("máximo", np.max(v) if len(v) else None)):
                if valor is None or (es_smart and valor == 0):
                    continue
                n_v = int(np.count_nonzero(v == valor))
                if 100 * n_v / len(v) >= CODIGO_PCT:
                    salida["codigos_candidatos"].append({"tabla": tabla, "columna": columna, "codigo": valor, "extremo": extremo,
                                                          "filas": n_v, "pct_filas": pct(n_v, len(v))})
        # Lo que el plan pide de columnas concretas
        if columna == "capacity_bytes":
            e["no_valida"] = int(np.count_nonzero(x < CAPACIDAD_MIN_VALIDA))
            e["no_valida_por_periodo"] = [int(np.count_nonzero((x < CAPACIDAD_MIN_VALIDA) & (d["periodo"] == p))) for p in (0, 1)]
            e["valores_no_validos"] = {str(int(k)): int(n) for k, n in zip(*np.unique(x[x < CAPACIDAD_MIN_VALIDA], return_counts=True))}
            bad = x < CAPACIDAD_MIN_VALIDA
            e["no_valida_por_modelo"] = {modelos.valores[i]: int(n) for i, n in enumerate(np.bincount(d["modelo"][bad], minlength=len(modelos.valores))) if n}
            e["no_valida_por_grupo_del_modelo"] = {GRUPOS[i]: int(n) for i, n in enumerate(np.bincount(d["grupo"][bad], minlength=3)) if n}
        if columna == HORAS:
            e["vacias_datos"] = int(np.count_nonzero(nul & datos))
            e["vacias_datos_capacidad_no_valida"] = int(np.count_nonzero(nul & datos & d["invalida"]))
            e["vacias_datos_resto"] = e["vacias_datos"] - e["vacias_datos_capacidad_no_valida"]
        if columna == "smart_188_raw":
            alto = presente & ~nul & (x > UMBRAL_188)
            e["mas_de_mil_millones"] = int(alto.sum())
            e["mas_de_mil_millones_datos"] = int((alto & datos).sum())
            e["mas_de_mil_millones_datos_por_periodo"] = [int((alto & datos & (d["periodo"] == p)).sum()) for p in (0, 1)]
            e["por_fabricante_datos"] = {FABRICANTES[i]: int(n) for i, n in enumerate(np.bincount(d["fabricante"][alto & datos], minlength=5)) if n}
            filas_mod = np.bincount(d["modelo"][presente & ~nul & datos], minlength=len(modelos.valores))
            altos_mod = np.bincount(d["modelo"][alto & datos], minlength=len(modelos.valores))
            e["por_modelo_datos"] = sorted(({"modelo": modelos.valores[i], "filas": int(altos_mod[i]), "filas_con_valor": int(filas_mod[i]),
                                             "pct": pct(altos_mod[i], filas_mod[i])} for i in np.flatnonzero(altos_mod)), key=lambda z: -z["filas"])
        if columna in ("smart_5_raw", "smart_187_raw"):
            e["en_65535"] = int(np.count_nonzero(x == TOPE_16_BITS))
            e["maximo"] = float(np.nanmax(x)) if presente.any() and (~nul).any() else None
        if columna == TEMPERATURA:
            e["por_encima"] = int(np.count_nonzero(x > TEMPERATURA_MAX))
            e["por_debajo"] = int(np.count_nonzero(x < TEMPERATURA_MIN))
            e["por_encima_por_periodo"] = [int(np.count_nonzero((x > TEMPERATURA_MAX) & (d["periodo"] == p))) for p in (0, 1)]
            e["por_debajo_por_periodo"] = [int(np.count_nonzero((x < TEMPERATURA_MIN) & (d["periodo"] == p))) for p in (0, 1)]
            e["maximo"] = float(np.nanmax(x)) if (~nul & presente).any() else None
            e["minimo"] = float(np.nanmin(x)) if (~nul & presente).any() else None
        if columna == "cluster_id":
            cero = presente & (x == 0)
            e["ceros"] = int(cero.sum())
            e["filas_con_columna"] = int(presente.sum())
            e["ceros_por_centro"] = {centros.valores[i] or "sin centro": int(n) for i, n in enumerate(np.bincount(d["centro"][cero], minlength=len(centros.valores))) if n}
            e["filas_por_centro"] = {str(centros.valores[i]): int(n) for i, n in enumerate(np.bincount(d["centro"][presente], minlength=len(centros.valores))) if n}
        if columna in FORMATO_PROPIO and rol == "magnitud":
            por_fab = {}
            for i, fab in enumerate(FABRICANTES):
                m = construccion & presente & ~nul & (d["fabricante"] == i)
                if m.any():
                    w = x[m]
                    cif = np.where(np.abs(w) < 1, 1, np.floor(np.log10(np.maximum(np.abs(w), 1))) + 1).astype(int)
                    n_c, c_c = np.unique(cif, return_counts=True)
                    por_fab[fab] = {"filas": int(m.sum()), "minimo": float(w.min()), "maximo": float(w.max()),
                                    "cifras": {str(int(a)): int(b) for a, b in zip(n_c, c_c)}}
            e["por_fabricante_construccion"] = por_fab
        if e:
            especiales[columna] = e
        del x, v, nul, presente
    return especiales


# =================================================================================================================
# 7. Fotos fichero a fichero: vacíos por fila, columnas vacías o constantes, duplicados, fechas y agregados para cruzar
# =================================================================================================================
def recorrer_fotos(d, casi_vacias, seriales_fallos):
    """Lee cada foto entera una vez y acumula lo que se mira fila a fila o fichero a fichero."""
    acc = {"vacios_fila": Counter(), "vacios_fila_sin_casi": Counter(), "por_fichero": [], "exactos": 0, "sin_serie": 0,
           "serie_repetida": 0, "no_valida": 0, "no_valida_sin_contadores": 0, "no_valida_con_horas": 0,
           "date_distinta": 0, "date_no_iso": 0, "dia_no_1": 0, "agregado": [], "failure1": [], "fotos_falladores": [],
           "centro_sin_tipo": []}
    for ruta, pf in zip(d["ficheros"], d["pfs"]):
        t = pf.read()
        if pa.types.is_null(t.schema.field("datacenter").type):
            acc["centro_sin_tipo"].append(ruta.name)
            t = t.set_column(t.schema.get_field_index("datacenter"), "datacenter", t["datacenter"].cast(pa.string()))
        df = t.to_pandas()
        del t
        nul = df.isna()
        for clave, cols in (("vacios_fila", list(df.columns)), ("vacios_fila_sin_casi", [c for c in df.columns if c not in casi_vacias])):
            cuenta = np.bincount(nul[cols].sum(axis=1).to_numpy())
            acc[clave].update({int(k): int(n) for k, n in enumerate(cuenta) if n})
        vacias = [c for c in df.columns if nul[c].all()]
        constantes = []
        for c in df.columns:
            s = df[c].dropna()
            if len(s) == 0:
                continue
            numerica = pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s)
            if (s.min() == s.max()) if numerica else (s.nunique() == 1):
                constantes.append(c)
        acc["por_fichero"].append({"fichero": ruta.name, "filas": len(df), "columnas": df.shape[1],
                                   "fecha_min": df["fecha"].min().date().isoformat(), "fecha_max": df["fecha"].max().date().isoformat(),
                                   "vacias": vacias, "constantes": constantes})
        # Duplicados exactos y sin el número de serie, por huella de fila; las candidatas se confirman comparando de verdad
        resto = [c for c in df.columns if c != "serial_number"]
        h_resto = pd.util.hash_pandas_object(df[resto], index=False).to_numpy()
        h_todo = (h_resto * np.uint64(1000003)) ^ pd.util.hash_pandas_object(df["serial_number"], index=False).to_numpy()
        for h, cols, clave in ((h_todo, list(df.columns), "exactos"), (h_resto, resto, "sin_serie")):
            cand = pd.Series(h).duplicated(keep=False).to_numpy()
            if cand.any():
                acc[clave] += int(df.loc[cand, cols].duplicated().sum())
        acc["serie_repetida"] += int(df["serial_number"].duplicated().sum())
        # Ausencia de la fila: las de capacidad no válida, ¿traen algún contador?
        smart_raw = [c for c in df.columns if c.startswith("smart_") and c.endswith("_raw")]
        mala = df["capacity_bytes"].lt(CAPACIDAD_MIN_VALIDA)
        acc["no_valida"] += int(mala.sum())
        acc["no_valida_sin_contadores"] += int(nul.loc[mala, smart_raw].all(axis=1).sum())
        acc["no_valida_con_horas"] += int(df.loc[mala, HORAS].notna().sum()) if HORAS in df else 0
        # Las dos fechas de la fila y el día 1 de cada foto
        texto_fecha = df["fecha"].dt.strftime("%Y-%m-%d")
        acc["date_distinta"] += int(df["date"].ne(texto_fecha).sum())
        acc["date_no_iso"] += int((~df["date"].str.fullmatch(PATRON_ISO)).sum())
        acc["dia_no_1"] += int(df["fecha"].dt.day.ne(1).sum())
        # Agregado por la clave del recuento para cruzarlo con él, sin guardar ningún cruce
        g = df.groupby(["fecha", "model", "capacity_bytes", "datacenter"], dropna=False).size().rename("filas").reset_index()
        acc["agregado"].append(g)
        acc["failure1"].append(df.loc[df["failure"].eq(1), ["serial_number", "fecha"]])
        acc["fotos_falladores"].append(df.loc[df["serial_number"].isin(seriales_fallos),
                                              ["serial_number", "fecha", "model", "capacity_bytes", "datacenter"]])
        del df, nul
    for k in ("agregado", "failure1", "fotos_falladores"):
        acc[k] = pd.concat(acc[k], ignore_index=True)
    return acc


# =================================================================================================================
# 8. Fotos disco a disco: huecos, horas y contadores que bajan, cambios de modelo, edad y objetivo
# =================================================================================================================
def seguir_discos(d, modelos, fallos):
    """Ordena las fotos por disco y fecha y mide lo que se ve siguiendo a cada disco en el tiempo."""
    ser = pa.chunked_array([pf.read(columns=["serial_number"]).column(0).cast(pa.string()) for pf in d["pfs"]]).combine_chunks()
    enc = pc.dictionary_encode(ser)
    del ser
    codigo = enc.indices.to_numpy().astype(np.int32)
    unicos = enc.dictionary
    orden = np.lexsort((d["mes"], codigo))
    c = codigo[orden]
    mismo = c[1:] == c[:-1]
    primero = np.r_[True, ~mismo]
    idx_primero = np.flatnonzero(primero)
    idx_ultimo = np.r_[idx_primero[1:] - 1, len(c) - 1]
    disco_fila = np.cumsum(primero) - 1
    n_discos = len(idx_primero)
    grupo_fila = d["grupo"][orden]
    grupo_disco = grupo_fila[idx_primero]
    datos_disco = grupo_disco == 0
    datos_trans = grupo_fila[1:] == 0
    periodo_trans = d["periodo"][orden][1:]
    r = {"discos": int(n_discos), "discos_datos": int(datos_disco.sum())}

    # 8.1 Huecos: un disco que falta en una foto y vuelve (reglas §3)
    m = d["mes"][orden]
    dm = m[1:] - m[:-1]
    hueco = mismo & (dm > 1)
    con_hueco = np.zeros(n_discos, dtype=bool)
    con_hueco[disco_fila[1:][hueco]] = True
    tam = (dm[hueco] - 1)
    r["huecos"] = {"discos": int(con_hueco.sum()), "discos_datos": int((con_hueco & datos_disco).sum()),
                   "pct_discos_datos": pct((con_hueco & datos_disco).sum(), datos_disco.sum()), "huecos": int(hueco.sum()),
                   "meses_que_faltan": {str(k): int(v) for k, v in zip(*np.unique(np.minimum(tam, 13), return_counts=True))},
                   "nota_meses": "13 quiere decir 13 meses o más"}
    del dm, m

    # 8.2 Horas encendido: bajan entre dos fotos (RC-01) y discos sin horas (reglas §3, la edad)
    h = leer_columna(d, HORAS)[0][orden]
    valido = mismo & ~np.isnan(h[1:]) & ~np.isnan(h[:-1])
    dif = h[1:] - h[:-1]
    baja = valido & (dif < 0)
    r["horas_bajan"] = {"veces": int(baja.sum()), "mas_de_un_dia": int((baja & (dif < -HORAS_DIA)).sum()),
                        "mas_de_un_dia_datos": int((baja & (dif < -HORAS_DIA) & datos_trans).sum()),
                        "discos_mas_de_un_dia_datos": int(len(np.unique(disco_fila[1:][baja & (dif < -HORAS_DIA) & datos_trans]))),
                        "mas_de_un_ano_datos": int((baja & (dif < -HORAS_ANO) & datos_trans).sum()),
                        "por_periodo": [int((baja & (periodo_trans == p)).sum()) for p in (0, 1)]}
    con_horas = np.bincount(disco_fila, weights=~np.isnan(h), minlength=n_discos)
    fotos_disco = np.bincount(disco_fila, minlength=n_discos)
    r["horas_discos"] = {"sin_horas_en_ninguna_foto_datos": int(((con_horas == 0) & datos_disco).sum()),
                         "con_horas_en_unas_fotos_y_no_en_otras_datos": int(((con_horas > 0) & (con_horas < fotos_disco) & datos_disco).sum()),
                         "sin_horas_en_ninguna_foto": int((con_horas == 0).sum())}
    del h, valido, dif

    # 8.3 Modelo y capacidad que cambian entre fotos (RC-02)
    mod = d["modelo"][orden]
    norm = np.array([modelos.valores.index(v) if v in modelos.valores else -1 for v in
                     [modelo_normalizado(x) for x in modelos.valores]], dtype=np.int32)
    cambio_modelo = mismo & (mod[1:] != mod[:-1])
    cambio_norm = mismo & (norm[mod[1:]] != norm[mod[:-1]])
    cap = d["capacidad"][orden]
    cambio_cap = mismo & (cap[1:] != cap[:-1])
    validas = (cap[1:] >= CAPACIDAD_MIN_VALIDA) & (cap[:-1] >= CAPACIDAD_MIN_VALIDA)
    r["cambios"] = {"modelo": int(cambio_modelo.sum()), "modelo_sin_variantes_de_espacios": int(cambio_norm.sum()),
                    "capacidad": int(cambio_cap.sum()), "capacidad_entre_validas": int((cambio_cap & validas).sum()),
                    "modelo_o_capacidad": int((cambio_modelo | cambio_cap).sum()),
                    "discos_modelo": int(len(np.unique(disco_fila[1:][cambio_modelo])))}
    # D1: filas y discos de cada variante de modelo en las fotos
    pares = np.unique(codigo.astype(np.int64) * 1000 + d["modelo"])
    discos_por_modelo = np.bincount((pares % 1000).astype(np.int64), minlength=len(modelos.valores))
    filas_por_modelo = np.bincount(d["modelo"], minlength=len(modelos.valores))
    r["modelos"] = {"filas": filas_por_modelo, "discos": discos_por_modelo}
    discos_de = {}
    for p in pares:
        discos_de.setdefault(int(p % 1000), set()).add(int(p // 1000))
    r["discos_de_modelo"] = discos_de
    del mod, cap, cambio_modelo, cambio_norm, cambio_cap, validas, pares

    # 8.4 Los cinco contadores de avería que bajan en un mismo disco (RC-03)
    alguno = np.zeros(len(c) - 1, dtype=bool)
    por_contador = {}
    for col in CONTADORES_AVERIA:
        if not any(col in pf.schema_arrow.names for pf in d["pfs"]):
            continue
        x = leer_columna(d, col)[0][orden]
        b = mismo & ~np.isnan(x[1:]) & ~np.isnan(x[:-1]) & (x[1:] < x[:-1])
        por_contador[col] = {"veces": int(b.sum()), "discos": int(len(np.unique(disco_fila[1:][b]))),
                             "por_periodo": [int((b & (periodo_trans == p)).sum()) for p in (0, 1)]}
        alguno |= b
        del x, b
    r["contadores_bajan"] = {"veces_alguno": int(alguno.sum()), "discos_alguno": int(len(np.unique(disco_fila[1:][alguno]))),
                             "por_contador": por_contador}
    del alguno

    # 8.5 La lista de fallos frente a las fotos: sin foto, edad negativa, discos que siguen tras su fallo
    dia_orden = d["dia"][orden]
    primer_dia = dia_orden[idx_primero]
    ultimo_dia = dia_orden[idx_ultimo]
    disco_de_codigo = np.full(len(unicos), -1, dtype=np.int64)
    disco_de_codigo[c[idx_primero]] = np.arange(n_discos)
    cod_fallo = pc.index_in(pa.array(fallos["serial_number"].astype(str).tolist(), pa.string()), value_set=unicos)
    cod_fallo = np.array(cod_fallo.fill_null(-1).to_numpy(), dtype=np.int64)
    disco_fallo = np.where(cod_fallo >= 0, disco_de_codigo[np.maximum(cod_fallo, 0)], -1)
    dia_fallo = fallos["dia_fallo"].to_numpy().astype("datetime64[D]").astype(np.int32)
    con_foto = disco_fallo >= 0
    tras = con_foto & (ultimo_dia[np.maximum(disco_fallo, 0)] > dia_fallo)
    discos_tras = set(disco_fallo[tras].tolist())
    veces_disco = pd.Series(disco_fallo[con_foto]).value_counts()
    otra_vez = int(sum(1 for disco in discos_tras if veces_disco.get(disco, 0) > 1))
    r["fallos_y_fotos"] = {"fallos_sin_foto": int((~con_foto).sum()), "discos_sin_foto": int(fallos.loc[~con_foto, "serial_number"].nunique()),
                           "fallos_con_edad_negativa": int((con_foto & (dia_fallo < primer_dia[np.maximum(disco_fallo, 0)])).sum()),
                           "discos_que_siguen_tras_su_fallo": len(discos_tras),
                           "de_ellos_con_dos_fallos_en_la_lista": otra_vez}

    # 8.6 Objetivo del modelo en la construcción: falla en los N días siguientes a la foto, en discos de datos (riesgos)
    fk = np.sort(np.where(con_foto, cod_fallo, -1)[con_foto].astype(np.int64) * 100000 + dia_fallo[con_foto])
    pk = codigo.astype(np.int64) * 100000 + d["dia"]
    r["objetivo"] = {}
    for dias_h in HORIZONTES_OBJETIVO:
        entra = (d["grupo"] == 0) & (d["periodo"] == 0) & (d["dia"] + dias_h <= dia_de(FIN_CONSTRUCCION))
        i = np.searchsorted(fk, pk[entra], side="right")
        siguiente = fk[np.minimum(i, len(fk) - 1)] if len(fk) else np.zeros(int(entra.sum()), dtype=np.int64)
        positivo = (i < len(fk)) & (siguiente <= pk[entra] + dias_h)
        r["objetivo"][str(dias_h)] = {"fotos": int(entra.sum()), "casos": int(positivo.sum()), "no_casos": int((~positivo).sum()),
                                      "pct_casos": pct(positivo.sum(), entra.sum()),
                                      "definicion": f"fotos de discos de datos de la construcción cuyo día más {dias_h} no pasa del 30/06/2024; "
                                                    f"caso si el disco falla después del día de la foto y no más tarde de {dias_h} días"}
    r["seriales"] = set(unicos.to_pylist())
    del codigo, orden, c, pk
    return r


# =================================================================================================================
# 9. Ventanas, recuento y lista de fallos en memoria: reglas, sitio del fallo y lo que se cruza
# =================================================================================================================
def mirar_ventanas(ficheros, grupo_de_modelo):
    """Lee las columnas de las ventanas que piden las reglas y mide lo que se mira fallo a fallo."""
    cols = ["serial_number", "fecha", "date", "dia_fallo", "model", "capacity_bytes", "failure", "datacenter", "vault_id", "pod_id",
            "pod_slot_num", TEMPERATURA, HORAS]
    v = pd.concat([leer_tabla(f, cols) for f in ficheros], ignore_index=True)
    v["grupo"] = v["model"].map(grupo_de_modelo)
    v["periodo"] = np.where(v["dia_fallo"].dt.date >= INICIO_VALIDACION, "validacion", "construccion")
    r = {}
    r["filas"] = len(v)
    # La fecha en texto frente a la fecha: si no coinciden, se mira si la fila trae las horas del día que dice el texto
    distinta = v["date"].ne(v["fecha"].dt.strftime("%Y-%m-%d"))
    r["date_distinta"] = int(distinta.sum())
    r["date_no_iso"] = int((~v["date"].astype(str).str.fullmatch(PATRON_ISO)).sum())
    malas = v.loc[distinta, ["serial_number", "fecha", "date", HORAS]]
    texto = v[["serial_number", "fecha", HORAS]].assign(date=v["fecha"].dt.strftime("%Y-%m-%d"))
    pareja = malas.merge(texto, on=["serial_number", "date"], how="left", suffixes=("", "_del_texto"))
    r["date_distinta_detalle"] = {"pares": [{"fecha": f.date().isoformat(), "texto": t, "filas": int(n)}
                                            for (f, t), n in malas.groupby(["fecha", "date"]).size().items()],
                                  "con_fila_del_dia_del_texto": int(pareja[HORAS + "_del_texto"].notna().sum()),
                                  "mismas_horas_que_la_fila_del_dia_del_texto": int((pareja[HORAS] == pareja[HORAS + "_del_texto"]).sum()),
                                  "failure_1": int(v.loc[distinta, "failure"].eq(1).sum())}
    v = v.drop(columns=["date", HORAS])
    r["clave_repetida"] = int(v.duplicated(["serial_number", "fecha"]).sum())
    r["rc06"] = int((v["failure"].eq(1) & v["fecha"].ne(v["dia_fallo"])).sum())
    r["rc06_por_periodo"] = [int((v["failure"].eq(1) & v["fecha"].ne(v["dia_fallo"]) & v["periodo"].eq(p)).sum()) for p in ("construccion", "validacion")]
    caliente = v.loc[v[TEMPERATURA].gt(TEMPERATURA_MAX)]
    r["temperatura_alta"] = [{"serial_number": s, "fecha": f.date().isoformat(), "dia_fallo": df_.date().isoformat(), "valor": t}
                             for s, f, df_, t in caliente[["serial_number", "fecha", "dia_fallo", TEMPERATURA]].itertuples(index=False)]
    # Ventanas sin el día anterior al fallo
    claves = v[["serial_number", "dia_fallo"]].drop_duplicates()
    antes = v.loc[(v["dia_fallo"] - v["fecha"]).dt.days.eq(1), ["serial_number", "dia_fallo"]].drop_duplicates()
    sin_antes = claves.merge(antes, how="left", indicator=True).query("_merge == 'left_only'")
    del_dia = v.loc[v["fecha"].eq(v["dia_fallo"])].copy()
    sin_antes = sin_antes.merge(del_dia[["serial_number", "dia_fallo", "grupo"]], how="left")
    r["sin_dia_anterior"] = int(len(sin_antes))
    r["sin_dia_anterior_datos"] = int(sin_antes["grupo"].eq("datos").sum())
    # El sitio de un fallo: el del día del fallo o el del último día anterior de su ventana que lo trae (reglas §5)
    sitio = {}
    desde = del_dia["dia_fallo"].dt.date >= INICIO_SITIO
    # El tomo es centro, vault y ranura juntos (reglas §4): falta si falta cualquiera de los tres
    v["tomo"] = v["datacenter"].where(v["datacenter"].notna() & v["vault_id"].notna() & v["pod_slot_num"].notna())
    del_dia["tomo"] = del_dia["datacenter"].where(del_dia["datacenter"].notna() & del_dia["vault_id"].notna() & del_dia["pod_slot_num"].notna())
    for col in ("pod_slot_num", "datacenter", "tomo"):
        con_dato = v.loc[v[col].notna() & v["fecha"].lt(v["dia_fallo"]), ["serial_number", "dia_fallo"]].drop_duplicates().assign(antes=True)
        f = del_dia.loc[desde & del_dia["grupo"].eq("datos"), ["serial_number", "dia_fallo", col, "periodo"]].merge(con_dato, how="left")
        sin_dia = f[col].isna()
        recupera = sin_dia & f["antes"].eq(True)
        sitio[col] = {"fallos_datos_desde_sitio": int(len(f)), "con_dato_el_dia": int((~sin_dia).sum()),
                      "sin_dato_el_dia": int(sin_dia.sum()), "lo_recuperan_un_dia_anterior": int(recupera.sum()),
                      "sin_dato_ningun_dia": int((sin_dia & ~f["antes"].eq(True)).sum()),
                      "sin_dato_el_dia_por_periodo": [int((sin_dia & f["periodo"].eq(p)).sum()) for p in ("construccion", "validacion")],
                      "sin_dato_ningun_dia_por_periodo": [int((sin_dia & ~f["antes"].eq(True) & f["periodo"].eq(p)).sum()) for p in ("construccion", "validacion")]}
    r["sitio_del_fallo"] = sitio
    return v, del_dia, r


def mirar_recuento(rec, fallos, modelos_variantes):
    """Reglas del recuento: fallos por encima de discos, cuadre por día con la lista, sin dato, capacidad y días hundidos."""
    r = {}
    r["rc07"] = int(rec["fallos"].gt(rec["discos"]).sum())
    por_dia = rec.groupby("fecha")["fallos"].sum()
    lista = fallos.groupby("dia_fallo").size()
    union = por_dia.to_frame("recuento").join(lista.rename("lista"), how="outer").fillna(0)
    r["rc08_dias"] = int(len(union))
    r["rc08_dias_que_no_cuadran"] = int(union["recuento"].ne(union["lista"]).sum())
    r["rc08_fallos_de_diferencia"] = int((union["recuento"] - union["lista"]).abs().sum())
    sin = rec["datacenter"].eq("sin dato")
    r["sin_dato"] = int(sin.sum())
    r["sin_dato_desde_sitio"] = int((sin & rec["fecha"].dt.date.ge(INICIO_SITIO)).sum())
    r["sin_dato_dias_de_disco"] = int(rec.loc[sin, "discos"].sum())
    r["sin_dato_desde_sitio_dias_de_disco"] = int(rec.loc[sin & rec["fecha"].dt.date.ge(INICIO_SITIO), "discos"].sum())
    mala = rec["capacity_bytes"].lt(CAPACIDAD_MIN_VALIDA)
    r["capacidad_no_valida"] = int(mala.sum())
    r["capacidad_no_valida_por_periodo"] = [int((mala & rec["periodo"].eq(p)).sum()) for p in ("construccion", "validacion")]
    r["capacidad_no_valida_por_modelo"] = {str(k): int(n) for k, n in rec.loc[mala, "model"].value_counts().sort_index().items()}
    r["capacidad_no_valida_dias_de_disco"] = int(rec.loc[mala, "discos"].sum())
    r["capacidad_no_valida_fallos"] = int(rec.loc[mala, "fallos"].sum())
    # Días hundidos: discos del día frente a la media del día de antes y el de después
    total = rec.groupby("fecha")["discos"].sum().sort_index()
    vecinos = (total.shift(1) + total.shift(-1)) / 2
    r["dias_hundidos"] = [{"dia": dia, "discos": int(total.get(pd.Timestamp(dia), 0)),
                           "media_vecinos": None if pd.isna(vecinos.get(pd.Timestamp(dia))) else float(vecinos.get(pd.Timestamp(dia))),
                           "faltan": None if pd.isna(vecinos.get(pd.Timestamp(dia))) else int(round(float(vecinos.get(pd.Timestamp(dia))) - total.get(pd.Timestamp(dia), 0)))}
                          for dia in DIAS_HUNDIDOS]
    mediana = total.rolling(7, center=True, min_periods=4).median()
    caida = ((mediana - total) / mediana).dropna().sort_values(ascending=False).head(10)
    r["mayores_caidas"] = [{"dia": k.date().isoformat(), "discos": int(total[k]), "mediana_7_dias": float(mediana[k]), "pct_caida": round(100 * float(v), 4)}
                           for k, v in caida.items()]
    # D1 en el recuento: filas y días de disco de cada variante
    r["variantes"] = {m: {"filas": int(rec["model"].eq(m).sum()), "dias_de_disco": int(rec.loc[rec["model"].eq(m), "discos"].sum())}
                      for m in modelos_variantes}
    return r


# =================================================================================================================
# 10. Cruces entre los cuatro datasets (comprobaciones §13): solo se cuentan, no se guarda ninguna tabla cruzada
# =================================================================================================================
def sin_pareja(izq, der, clave):
    """Claves distintas de cada lado que no tienen pareja en el otro."""
    a = izq[clave].drop_duplicates()
    b = der[clave].drop_duplicates()
    m = a.merge(b, how="outer", indicator=True)
    return int(m["_merge"].eq("left_only").sum()), int(m["_merge"].eq("right_only").sum()), int(len(a)), int(len(b))


def cruzar(acc_fotos, v, del_dia, rec, fallos, seriales_fotos):
    """Las seis relaciones entre los cuatro datasets, con cardinalidad, claves sin pareja y formato de la clave."""
    cruces = []
    # 10.1 Lista de fallos y ventanas: un fallo, su ventana
    l, r, nl, nr = sin_pareja(fallos, v, ["serial_number", "dia_fallo"])
    cruces.append({"izquierda": "fallos", "derecha": "ventanas_fallo", "clave": ["serial_number", "dia_fallo"], "cardinalidad_esperada": "1:N",
                   "supuesta": False, "documentada_en": "metodo/como_estan_organizados_los_datos.md", "claves_izquierda": nl, "claves_derecha": nr,
                   "sin_pareja_izquierda": l, "sin_pareja_derecha": r, "pct_sin_pareja_izquierda": pct(l, nl), "pct_sin_pareja_derecha": pct(r, nr),
                   "formato_distinto": str(fallos["dia_fallo"].dtype) != str(v["dia_fallo"].dtype),
                   "unica_en_maestro": not fallos.duplicated(["serial_number", "dia_fallo"]).any()})
    # 10.2 Lista de fallos y fotos, por el disco: los dos son hechos del mismo disco
    en_fotos = fallos["serial_number"].isin(seriales_fotos)
    discos_fallo = set(fallos["serial_number"])
    cruces.append({"izquierda": "fallos", "derecha": "fotos_mensuales", "clave": ["serial_number"], "cardinalidad_esperada": "N:M, por el disco",
                   "supuesta": False, "documentada_en": "metodo/como_estan_organizados_los_datos.md (dimensión disco)",
                   "claves_izquierda": len(discos_fallo), "claves_derecha": len(seriales_fotos),
                   "sin_pareja_izquierda": int(fallos.loc[~en_fotos, "serial_number"].nunique()),
                   "sin_pareja_derecha": int(len(seriales_fotos) - len(discos_fallo & seriales_fotos)),
                   "filas_izquierda_sin_pareja": int((~en_fotos).sum()),
                   "pct_sin_pareja_izquierda": pct(fallos.loc[~en_fotos, "serial_number"].nunique(), len(discos_fallo)),
                   "pct_sin_pareja_derecha": pct(len(seriales_fotos) - len(discos_fallo & seriales_fotos), len(seriales_fotos)),
                   "nota": "un disco de las fotos sin fallo es lo normal: casi ningún disco falla", "formato_distinto": False,
                   "unica_en_maestro": None})
    # 10.3 Ventanas y fotos el día 1: la misma fila de un disco el mismo día
    fotos_f = acc_fotos["fotos_falladores"]
    vent1 = v.loc[v["fecha"].dt.day.eq(1)]
    rangos = v.groupby(["serial_number", "dia_fallo"])["fecha"].agg(["min", "max"]).reset_index()
    en_ventana = fotos_f.merge(rangos, on="serial_number")
    en_ventana = en_ventana.loc[en_ventana["fecha"].between(en_ventana["dia_fallo"] - pd.Timedelta(days=30), en_ventana["dia_fallo"])]
    en_ventana = en_ventana[["serial_number", "fecha", "model", "capacity_bytes"]].drop_duplicates(["serial_number", "fecha"])
    l, r, nl, nr = sin_pareja(vent1, en_ventana, ["serial_number", "fecha"])
    casan = vent1.merge(en_ventana, on=["serial_number", "fecha"], suffixes=("_v", "_f"))
    cruces.append({"izquierda": "ventanas_fallo", "derecha": "fotos_mensuales", "clave": ["serial_number", "fecha"], "cardinalidad_esperada": "1:1",
                   "supuesta": True, "alcance": "filas de las ventanas del día 1 de un mes y fotos que caen dentro de una ventana",
                   "claves_izquierda": nl, "claves_derecha": nr, "sin_pareja_izquierda": l, "sin_pareja_derecha": r,
                   "pct_sin_pareja_izquierda": pct(l, nl), "pct_sin_pareja_derecha": pct(r, nr),
                   "casan_con_otro_modelo": int(casan["model_v"].ne(casan["model_f"]).sum()),
                   "casan_con_otra_capacidad": int(casan["capacity_bytes_v"].ne(casan["capacity_bytes_f"]).sum()),
                   "formato_distinto": False, "unica_en_maestro": not en_ventana.duplicated(["serial_number", "fecha"]).any()})
    # 10.4 Recuento y fotos el día 1: una fila del recuento resume las fotos de su clave
    clave = ["fecha", "model", "capacity_bytes", "datacenter"]
    ag = acc_fotos["agregado"]
    rec1 = rec.loc[rec["fecha"].isin(set(ag["fecha"]))]
    l0, r0, _, _ = sin_pareja(ag.assign(datacenter=ag["datacenter"].fillna("(vacío)")), rec1, clave)
    ag_igual = ag.assign(datacenter=ag["datacenter"].fillna("sin dato"))
    ag_igual = ag_igual.groupby(clave, dropna=False)["filas"].sum().reset_index()
    l, r, nl, nr = sin_pareja(rec1, ag_igual, clave)
    casan = rec1.merge(ag_igual, on=clave)
    cruces.append({"izquierda": "recuento_diario", "derecha": "fotos_mensuales", "clave": clave, "cardinalidad_esperada": "1:N",
                   "supuesta": False, "documentada_en": "metodo/como_estan_organizados_los_datos.md", "alcance": "los 66 días 1 de mes",
                   "claves_izquierda": nl, "claves_derecha": nr, "sin_pareja_izquierda": l, "sin_pareja_derecha": r,
                   "pct_sin_pareja_izquierda": pct(l, nl), "pct_sin_pareja_derecha": pct(r, nr),
                   "formato_distinto": True, "antes_de_igualar": {"sin_pareja_izquierda": r0, "sin_pareja_derecha": l0},
                   "igualado": "el centro vacío de las fotos se compara como «sin dato», sin guardar el cambio",
                   "claves_con_otro_numero_de_discos": int(casan["discos"].ne(casan["filas"]).sum()),
                   "discos_recuento_dia_1": int(rec1["discos"].sum()), "filas_fotos": int(ag["filas"].sum()),
                   "unica_en_maestro": not rec.duplicated(clave).any()})
    # 10.5 Recuento y ventanas: cada fila de una ventana cae en una fila del recuento de su día
    vk = v.assign(datacenter=v["datacenter"].fillna("sin dato")).groupby(clave, dropna=False).size().rename("filas").reset_index()
    vk0 = v.assign(datacenter=v["datacenter"].fillna("(vacío)"))
    _, r0, _, _ = sin_pareja(rec, vk0, clave)
    l, r, nl, nr = sin_pareja(rec, vk, clave)
    casan = vk.merge(rec, on=clave)
    cruces.append({"izquierda": "recuento_diario", "derecha": "ventanas_fallo", "clave": clave, "cardinalidad_esperada": "1:N",
                   "supuesta": True, "claves_izquierda": nl, "claves_derecha": nr, "sin_pareja_izquierda": l, "sin_pareja_derecha": r,
                   "pct_sin_pareja_izquierda": pct(l, nl), "pct_sin_pareja_derecha": pct(r, nr),
                   "nota": "una fila del recuento sin ventana es lo normal: ese día ningún disco de su clave estaba a 30 días de fallar",
                   "formato_distinto": True, "antes_de_igualar": {"sin_pareja_derecha": r0},
                   "igualado": "el centro vacío de las ventanas se compara como «sin dato», sin guardar el cambio",
                   "claves_con_mas_filas_que_discos": int(casan["filas"].gt(casan["discos"]).sum()),
                   "unica_en_maestro": not rec.duplicated(clave).any()})
    # 10.6 Recuento y lista de fallos: los fallos de cada clave, con el modelo, la capacidad y el centro del día del fallo
    fk = fallos.merge(del_dia[["serial_number", "dia_fallo", "model", "capacity_bytes", "datacenter"]], on=["serial_number", "dia_fallo"], how="left")
    fk = fk.assign(fecha=fk["dia_fallo"], datacenter=fk["datacenter"].fillna("sin dato")).groupby(clave, dropna=False).size().rename("lista").reset_index()
    rf = rec.loc[rec["fallos"].gt(0)]
    l, r, nl, nr = sin_pareja(rf, fk, clave)
    casan = rf.merge(fk, on=clave)
    cruces.append({"izquierda": "recuento_diario", "derecha": "fallos", "clave": clave, "cardinalidad_esperada": "1:N",
                   "supuesta": True, "alcance": "filas del recuento con algún fallo; la lista toma modelo, capacidad y centro de la fila del día del fallo en su ventana",
                   "claves_izquierda": nl, "claves_derecha": nr, "sin_pareja_izquierda": l, "sin_pareja_derecha": r,
                   "pct_sin_pareja_izquierda": pct(l, nl), "pct_sin_pareja_derecha": pct(r, nr),
                   "claves_con_otro_numero_de_fallos": int(casan["fallos"].ne(casan["lista"]).sum()),
                   "formato_distinto": True, "igualado": "el centro vacío se compara como «sin dato», sin guardar el cambio",
                   "unica_en_maestro": not rec.duplicated(clave).any()})
    return cruces


# =================================================================================================================
# 11. Validación en código (SKILL §6, comprobaciones 6, 7, 9 y 10): si falla, para con ERROR
# =================================================================================================================
def validar(cal, huella_antes, huella_despues):
    """Devuelve la lista de fallos de las cuatro comprobaciones que van en el script; vacía si todo está bien."""
    errores = []
    # 6: cada variable con vacíos tiene su veredicto de reparto
    con_veredicto = {(x["tabla"], x["columna"]) for x in cal["nulos_por_segmento"] if x.get("veredicto")}
    for t in cal["tipos"]:
        if t.get("vacios", 0) > 0 and (t["tabla"], t["columna"]) not in con_veredicto:
            errores.append(f"6: {t['tabla']}.{t['columna']} tiene vacíos y no tiene veredicto de reparto")
    # 7: cada relación entre tablas tiene sus claves sin pareja en los dos lados
    for c in cal["cruces"]:
        if not isinstance(c.get("sin_pareja_izquierda"), int) or not isinstance(c.get("sin_pareja_derecha"), int):
            errores.append(f"7: la relación {c['izquierda']} y {c['derecha']} no tiene su recuento de claves sin pareja")
    if not cal["cruces"]:
        errores.append("7: no hay ninguna relación entre tablas")
    # 9: data/raw/ igual antes y después
    if huella_antes != huella_despues:
        cambiados = sorted(k for k in set(huella_antes) | set(huella_despues) if huella_antes.get(k) != huella_despues.get(k))
        errores.append(f"9: data/raw/ cambió durante la ejecución: {', '.join(cambiados[:5])}")
    # 10: cada magnitud con su escala y sus colas, y los parámetros con que se ejecutó
    magnitudes = {(t["tabla"], t["columna"]) for t in cal["tipos"] if t["rol"] == "magnitud"}
    for nombre in ("escala", "colas"):
        tienen = {(x["tabla"], x["columna"]) for x in cal[nombre]}
        for falta in sorted(magnitudes - tienen):
            errores.append(f"10: {falta[0]}.{falta[1]} es magnitud y no tiene {nombre}")
    nombres = {p["nombre"] for p in cal["parametros"]}
    for p in PARAMETROS:
        if p["nombre"] not in nombres:
            errores.append(f"10: falta el parámetro «{p['nombre']}» en el JSON")
    return errores


# =================================================================================================================
# 12. Problemas, riesgos y cifras de control a partir de lo medido
# =================================================================================================================
def problema(lista, bloque, tabla, columna, resultado, cifra, total, observacion, accion, decision=False, cerrado=None, principal=False,
             unidad="filas"):
    """Añade un problema con su cifra; si la cifra es cero, no hay problema y no se añade. Si no cuenta filas, dice su unidad."""
    if not cifra:
        return
    p = {"id": f"C-{len(lista) + 1:02d}", "bloque": bloque, "tabla": tabla, "columna": columna, "resultado": resultado,
         "filas_afectadas": int(cifra) if unidad == "filas" else None, "pct_filas": pct(cifra, total) if unidad == "filas" else None,
         "cifra": int(cifra), "unidad": unidad, "observacion": observacion, "posible_accion": accion,
         "decision_de_negocio": decision, "principal": principal}
    if cerrado:
        p["cerrado"] = {"decision": cerrado, **LO_CERRADO[cerrado]}
    lista.append(p)


def fmt(n, dec=2):
    """Número en formato español: punto de miles y coma decimal."""
    if n is None:
        return "sin dato"
    if isinstance(n, bool):
        return "sí" if n else "no"
    if isinstance(n, (int, np.integer)) or (isinstance(n, float) and n.is_integer() and abs(n) < 1e15):
        return f"{int(n):,}".replace(",", ".")
    texto = f"{n:,.{dec}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


# =================================================================================================================
# 13. Informe Markdown, generado del JSON
# =================================================================================================================
def tablas_legibles(texto):
    """Cambia los nombres técnicos de las tablas por los que lee la persona."""
    for tecnico, legible in NOMBRE_TABLA.items():
        texto = texto.replace(tecnico, legible)
    return texto


def escribir_markdown(cal, ruta):
    """Escribe el informe para la persona con los 19 apartados de plantilla_informe.md, en su orden, desde el JSON."""
    L = []
    T = {t["tabla"]: t for t in cal["fuente"]["tablas"]}
    ctl = cal["cifras_de_control"]
    reg = {x["id"]: x for x in cal["comprobaciones_reglas"]}
    cue = {x["id"]: x for x in cal["cuestiones_reconocimiento"]}
    add = L.append

    add("# Calidad de los datos del caso 68")
    add("")
    add(f"Diagnóstico de los cuatro datasets del caso, generado por `{cal['script']}` el {cal['fecha_ejecucion'][:10]} a partir de "
        "`informes/calidad-datos.json`. No se ha corregido ningún dato. Lo leen la persona responsable del caso y la fase de corrección.")
    add("")

    # 1. Fuente analizada
    add("## 1. Fuente analizada")
    add("")
    intacto = next((v["ok"] for v in cal.get("validacion", []) if v["comprobacion"].startswith("9 ")), None)
    add(f"Se leyeron enteros los cuatro datasets de `data/raw/podado/`, sin muestra, y el esquema de Backblaze, que solo entra en la "
        f"revisión de nombres. La huella de los {fmt(ctl['huella.ficheros'])} ficheros de `data/raw/` "
        + ("es la misma al empezar y al acabar." if intacto else "no se pudo comparar al acabar."))
    add("")
    for t in cal["fuente"]["tablas"]:
        fich = "1 fichero que pesa" if t["ficheros"] == 1 else f"{fmt(t['ficheros'])} ficheros que pesan"
        add(f"- **{NOMBRE_TABLA[t['tabla']]}** (`{t['ruta']}`): {fich} {fmt(t['bytes'])} bytes.")
    add(f"- **{NOMBRE_TABLA['esquema_backblaze']}** (`{cal['fuente']['esquema']['ruta']}`): {fmt(cal['fuente']['esquema']['bytes'])} bytes.")
    add(f"- Huella SHA-256 de la lista de fallos: `{cal['fuente']['huella_fallos']}`. La del esquema: `{cal['fuente']['huella_esquema']}`. "
        "Las de los demás ficheros están en `entradas` del JSON.")
    add(f"- Ejecución: {cal['fecha_ejecucion']}, con Python {cal['ejecucion']['python']} y pandas {cal['ejecucion']['pandas']}; "
        f"tardó {fmt(cal['ejecucion']['segundos_total'], 0)} segundos.")
    add("- Se partió del diccionario del origen, cuyas huellas coinciden con las de los ficheros analizados: filas, tipos, roles, vacíos y "
        "categorías raras se toman de él sin recalcular." if cal["con_diccionario"] else "- No se partió del diccionario del origen.")
    add("")

    # 2. Resumen
    add("## 2. Resumen")
    add("")
    add(f"Estado: {cal['resultado']['estado']}. Riesgo: {cal['resultado']['riesgo']}. {cal['resultado']['resumen']}")
    add("")
    add("Los problemas principales, con su identificador para la corrección:")
    add("")
    for p in cal["problemas"]:
        if p["principal"]:
            add(f"- {p['id']}, {tablas_legibles(p['tabla'])}, `{p['columna']}`: {p['resultado']}.")
    add("")
    n_pend = len(cal["pendientes"])
    add(f"Hay {fmt(len(cal['problemas']))} problemas en total y " + ("una cuestión pendiente:" if n_pend == 1 else f"{fmt(n_pend)} cuestiones pendientes."))
    for p in cal["pendientes"]:
        add(f"- {p['id']} ({p['problema']}): {p['pregunta']} Opciones: {'; '.join(p['opciones'])}. Cifra: {p['cifra']}. "
            f"{p['nota'][0].upper()}{p['nota'][1:]}.")
    add("")

    # 3. Inspección general
    add("## 3. Inspección general")
    add("")
    futuras = sum(f["futuras"] for f in cal["fechas"])
    add(f"Los cuatro datasets cubren del {min(f['minimo'] for f in cal['fechas'])} al {max(f['maximo'] for f in cal['fechas'])}. "
        + ("Ninguna fila cae en la reserva." if futuras == 0 else f"{fmt(futuras)} filas caen en la reserva."))
    add("")
    for t in cal["fuente"]["tablas"]:
        cols = f"de {fmt(t['columnas_min'])} a {fmt(t['columnas_max'])} columnas" if t["columnas_min"] != t["columnas_max"] else f"{fmt(t['columnas_max'])} columnas"
        add(f"- **{NOMBRE_TABLA[t['tabla']]}**: {fmt(t['filas'])} filas y {cols}. Construcción, {fmt(t['filas_construccion'])} filas; "
            f"validación, {fmt(t['filas_validacion'])}.")
    ins = cal["inspeccion"]
    add(f"- Las fotos van del {ins['fotos_primera']} al {ins['fotos_ultima']}. Ficheros con más de una fecha: {fmt(ins['ficheros_de_fotos_con_mas_de_una_fecha'])}.")
    add(f"- Las ventanas van del {ins['ventanas_primera']} al {ins['ventanas_ultima']}; sus fallos, del {ins['dia_fallo_primero']} al {ins['dia_fallo_ultimo']}.")
    add(f"- El recuento trae {fmt(ins['recuento_dias'])} días; entre el primero y el último faltan {fmt(ins['recuento_dias_que_faltan'])}.")
    add("")

    # 4. Estructura
    add("## 4. Estructura")
    add("")
    est = cal["estructura"]
    for t in ("fotos_mensuales", "ventanas_fallo"):
        e = est[t]
        add(f"En las {NOMBRE_TABLA[t]}, {fmt(len(e['casi_vacias']))} columnas están vacías en más del {fmt(CASI_VACIA_PCT, 0)} % de las filas que las traen, "
            f"y {fmt(len(e['vacias']))} lo están del todo.")
        add("")
        add(f"- Columnas constantes en todas sus filas: {', '.join(f'`{c}`' for c in e['constantes']) or 'ninguna'}.")
        primeros = sorted({x["primer_fichero"] for x in e["a_mitad"]})
        add(f"- Columnas que no traen todos los ficheros: {fmt(len(e['a_mitad']))}. Entran a mitad del periodo"
            + (f", entre {primeros[0]} y {primeros[-1]}, y en los ficheros anteriores no existen." if primeros else "."))
        if t == "fotos_mensuales":
            add(f"- Ficheros con alguna columna vacía entera: {fmt(e['ficheros_con_vacias'])} de {fmt(e['ficheros'])}; "
                f"con alguna columna constante: {fmt(e['ficheros_con_constantes'])}.")
        add("")
    con_aviso = [n for n in cal["nombres"] if n["avisos"]]
    en_datos = [n for n in con_aviso if n["tabla"] != "esquema_backblaze"]
    colisiones = [n for n in cal["nombres"] if n["colision_con"]]
    add(f"Nombres de columna de los cuatro datasets con algún aviso: {fmt(len(en_datos))}. Colisiones al normalizarlos: {fmt(len(colisiones))}. "
        f"Nombres del esquema con aviso: {fmt(len(con_aviso) - len(en_datos))}.")
    add("")
    for n in con_aviso:
        add(f"- `{n['columna']}` ({NOMBRE_TABLA.get(n['tabla'], n['tabla'])}): {', '.join(n['avisos'])}.")
    add("")

    # 5. Tipos y formatos
    add("## 5. Tipos y formatos")
    add("")
    tf = cal["tipos_y_formatos"]
    no_convierten = [t for t in cal["tipos"] if (t["pct_no_convierte"] or 0) > 0]
    add(f"Columnas con algún valor que no se convierte al tipo que les toca por su rol: {fmt(len(no_convierten))}"
        + (": " + ", ".join(f"`{t['columna']}` ({NOMBRE_TABLA[t['tabla']]}, {fmt(t['pct_no_convierte'])} %)" for t in no_convierten) + "." if no_convierten else "."))
    add("")
    add(f"- La ranura (`pod_slot_num`) se lee como decimal en las fotos y en las ventanas, y el {fmt(tf['ranura_pct_no_entera'])} % de sus valores no es entero.")
    if tf["centro_sin_tipo"]:
        add(f"- El centro viene sin tipo en {fmt(len(tf['centro_sin_tipo']))} ficheros de fotos, del {tf['centro_sin_tipo'][0][:7]} al {tf['centro_sin_tipo'][-1][:7]}, porque está vacío entero.")
    add(f"- La fecha llega dos veces, como texto (`date`) y como fecha (`fecha`). Filas en que no dicen lo mismo: {fmt(tf['date_distinta'])}. "
        f"Textos que no siguen el formato ISO: {fmt(tf['date_no_iso'])}.")
    add(f"- Magnitudes con un salto de orden de magnitud sin valores en medio: {fmt(len(tf['escala_con_salto']))}. "
        "Lo que mide un contador en bruto explica casi siempre que vaya de 0 a miles de millones, así que el salto solo señala dónde mirar.")
    for e in tf["escala_con_salto"]:
        add(f"  - `{e['columna']}` ({NOMBRE_TABLA[e['tabla']]}): cifras enteras {', '.join(f'{k}: {fmt(v)}' for k, v in e['cifras'].items())}.")
    add("")

    # 6. Valores ausentes
    add("## 6. Valores ausentes")
    add("")
    add(f"Las filas con capacidad no válida de las fotos llegan sin ningún contador en {fmt(ctl['fotos.capacidad_no_valida_sin_ningun_contador'])} "
        f"de {fmt(ctl['fotos.capacidad_no_valida'])} casos: es una ausencia de la fila. Los demás vacíos se reparten así por variable.")
    add("")
    add("### Códigos de ausencia")
    add("")
    for c in cal["codigos_de_ausencia"]:
        doc = "documentado" if c["documentado"] else "sin documentar"
        codigo = fmt(c["codigo"]) if isinstance(c["codigo"], (int, float)) else c["codigo"]
        add(f"- `{c['columna']}` = {codigo} en {NOMBRE_TABLA[c['tabla']]}: {fmt(c['filas'])} filas ({fmt(c['pct_filas'])} %), {doc}. {c.get('nota', '')}".rstrip())
    add("")
    add("### Reparto de los vacíos")
    add("")
    vr = cal["resumen_reparto"]
    for t, cuenta in vr.items():
        add(f"- {NOMBRE_TABLA[t]}: " + "; ".join(f"{k.replace('_', ' ')}, {fmt(n)}" for k, n in cuenta.items()) + ".")
    add("")
    add("Las variables que más pesan en las preguntas, con su porcentaje global y el segmento que más lo concentra:")
    add("")
    for x in cal["nulos_por_segmento"]:
        if x["tabla"] == "fotos_mensuales" and x["columna"] in COLUMNAS_SITIO + CONTADORES_AVERIA + [HORAS, TEMPERATURA]:
            top = max(x["segmentos"], key=lambda s: s["pct"], default=None)
            extra = f" El segmento que más concentra es {top['segmento']} ({top['dimension']}), con el {fmt(top['pct'])} %." if top else ""
            add(f"- `{x['columna']}`: {fmt(x['global_pct'])} % vacío, {x['veredicto'].replace('_', ' ')}.{extra}")
    add("")
    add("### Vacíos por fila")
    add("")
    for t, vf in cal["vacios_por_fila"].items():
        con = vf["con_todas"]
        sin = vf["sin_casi_vacias"]
        if sin is None:
            add(f"- {NOMBRE_TABLA[t]}: ninguna fila tiene vacíos." if set(con) <= {"0"} else
                f"- {NOMBRE_TABLA[t]}: la mediana de vacíos por fila es {fmt(vf['mediana_con_todas'])}.")
            continue
        add(f"- {NOMBRE_TABLA[t]}: la mediana de vacíos por fila es {fmt(vf['mediana_con_todas'])} contando todas las columnas, "
            f"y {fmt(vf['mediana_sin_casi_vacias'])} sin las {fmt(len(vf['excluidas']))} casi vacías. Filas sin ningún vacío: {fmt(con.get('0', 0))} y {fmt(sin.get('0', 0))}.")
    add("")

    # 7. Duplicados
    add("## 7. Duplicados")
    add("")
    exactos = sum(x["exactos"] for x in cal["duplicados"])
    add(f"Filas repetidas enteras en las cuatro tablas: {fmt(exactos)}. Sin el número de serie, dos discos pueden coincidir en todo: "
        "esas filas se cuentan como evidencia, no como error.")
    add("")
    for x in cal["duplicados"]:
        add(f"- {NOMBRE_TABLA[x['tabla']]}: exactos, {fmt(x['exactos'])}; sin identificadores, {fmt(x['exactos_sin_identificadores'])}; "
            f"por clave, {fmt(x['por_clave'])}; casi duplicados, {fmt(x['casi_duplicados'])}; lógicos, {fmt(x['logicos'])}.")
    add("")
    add("Los casi duplicados del recuento son filas cuya clave se repite si se quita la capacidad, la misma combinación partida por una capacidad no válida. "
        "Los lógicos son filas con un modelo escrito con dos espacios tras «WDC» (D1). En la lista de fallos, sin el número de serie se repiten los días con más de un fallo.")
    add("")

    # 8. Claves y granularidad
    add("## 8. Claves y granularidad")
    add("")
    repetidas = sum(x["repetidas"] for x in cal["claves"])
    add(f"Claves repetidas en las cuatro tablas: {fmt(repetidas)}. " + ("La granularidad observada es la documentada." if repetidas == 0
                                                                          else "La granularidad observada no es la documentada en alguna tabla."))
    add("")
    for x in cal["claves"]:
        add(f"- {NOMBRE_TABLA[x['tabla']]}: una fila es {x['que_es_una_fila']}; clave {', '.join(f'`{c}`' for c in x['clave'])}, "
            f"con {fmt(x['repetidas'])} repetidas.")
    add(f"- Ningún disco sale dos veces en la misma foto ({fmt(ctl['fotos.disco_repetido_en_foto'])} repeticiones).")
    add("")

    # 9. Categóricas y texto
    add("## 9. Categóricas y texto")
    add("")
    cat = cal["categoricas"]
    add(f"El modelo tiene {fmt(cat['modelos_fotos'])} valores en las fotos y el centro, {fmt(len(cat['centros']))}. Columnas de texto libre: "
        f"{fmt(sum(1 for t in cal['tipos'] if t['rol'] == 'texto_libre'))}. Valores con forma de instrucción: {fmt(len(cal['instrucciones_en_texto']))}. "
        f"Textos de ausencia sin documentar: {fmt(len(cal['textos_de_ausencia']))}.")
    add("")
    add("- Variantes de escritura del modelo (D1, cerrada el 17/11/2026: son el mismo modelo y los junta la corrección):")
    for vte in cat["variantes"]:
        add(f"  - «{vte['variante']}» frente a «{vte['normal']}»: en las fotos, {fmt(vte['fotos_filas'])} filas de {fmt(vte['fotos_discos'])} discos; "
            f"en las ventanas, {fmt(vte['ventanas_filas'])} filas; en el recuento, {fmt(vte['recuento_filas'])} filas. Discos con los dos nombres: {fmt(vte['discos_con_los_dos'])}.")
    add(f"- Modelos que no siguen el patrón de su fabricante: {fmt(len(cat['sin_patron']))}. De ellos, {fmt(cat['sin_patron_explicados'])} son discos de arranque "
        "o una de las dos excepciones de las reglas.")
    raras_codigo = sum(1 for r in cal["categorias_raras"] if r["es_codigo_de_ausencia"])
    add(f"- Categorías raras del diccionario: {fmt(cat['raras_fotos'])} modelos de las fotos y {fmt(cat['raras_centro'])} centro. Las que son un código de ausencia: {fmt(raras_codigo)}.")
    add(f"- El centro «sin dato» del recuento es un código documentado (reglas §4 y §5), no una categoría.")
    add("")

    # 10. Numéricas y outliers
    add("## 10. Numéricas y outliers")
    add("")
    out = cal["resumen_atipicos"]
    add(f"Los atípicos se buscan solo en las magnitudes y solo con la construcción, por rango intercuartílico (1,5 veces) y por z robusto (3,5). "
        f"Solo detectan: ningún valor se ha tocado. {TEORIA}")
    add("")
    add(f"- Magnitudes revisadas: {fmt(out['magnitudes'])}. Con dispersión cero por los dos métodos, sin atípicos que marcar: {fmt(out['dispersion_cero'])}.")
    add(f"- Magnitudes con algún valor marcado por los dos métodos: {fmt(out['con_marcados'])}.")
    add("")
    add("Las colas que piden las decisiones del plan, con la construcción:")
    add("")
    for col in (TEMPERATURA, "smart_5_raw", "smart_187_raw", "smart_188_raw", HORAS, "capacity_bytes"):
        for t in ("fotos_mensuales", "ventanas_fallo"):
            c = next((x for x in cal["colas"] if x["tabla"] == t and x["columna"] == col), None)
            if c and c.get("altos"):
                altos = ", ".join(f"{fmt(a['valor'])} ({fmt(a['filas'])})" for a in c["altos"][-5:])
                bajos = ", ".join(f"{fmt(a['valor'])} ({fmt(a['filas'])})" for a in c["bajos"][:3])
                add(f"- `{col}`, {NOMBRE_TABLA[t]}: los más bajos, {bajos}; los cinco más altos, {altos}.")
    add("")

    # 11. Fechas
    add("## 11. Fechas")
    add("")
    add(f"Textos de fecha que no siguen el formato ISO: {fmt(cal['tipos_y_formatos']['date_no_iso'])}; con formato ISO no hay duda entre día y mes. "
        f"Fechas después del horizonte, el {next(p['valor'] for p in cal['parametros'] if p['nombre'] == 'horizonte de fechas futuras')}: "
        f"{fmt(sum(f['futuras'] for f in cal['fechas']))}.")
    add("")
    for f in cal["fechas"]:
        add(f"- `{f['columna']}` ({NOMBRE_TABLA[f['tabla']]}): del {f['minimo']} al {f['maximo']}; fuera del horizonte, {fmt(f['futuras'])}.")
    add(f"- Fotos que no son de un día 1: {fmt(cal['tipos_y_formatos']['dia_no_1'])}. Filas de ventana fuera de los 30 días anteriores a su fallo: "
        f"{fmt(cal['inspeccion']['ventanas_fuera'])}.")
    add("")

    # 12. Reglas lógicas e integridad
    add("## 12. Reglas lógicas e integridad")
    add("")
    add("Cada regla del caso se ha mirado con su medida, sin aplicarla a los datos. Las reglas no traen tabla de valores esperables, "
        "así que no hay rangos de negocio que mirar.")
    add("")
    add("### Comprobaciones de las reglas")
    add("")
    for x in cal["comprobaciones_reglas"]:
        add(f"- {x['id']}, {x['regla']} ({x['seccion']}): {x['resultado']}")
    add("")
    add("### Cuestiones del reconocimiento")
    add("")
    for x in cal["cuestiones_reconocimiento"]:
        add(f"- {x['id']}, {x['cuestion']}: {x['resultado']}")
    add("")
    add("### Riesgos para un modelo")
    add("")
    for x in cal["riesgos_modelo"]:
        add(f"- {x['riesgo']}")
    add("")

    # 13. Cruces entre tablas
    add("## 13. Cruces entre tablas")
    add("")
    add("Se revisaron las seis relaciones entre los cuatro datasets, sin guardar ninguna tabla cruzada.")
    add("")
    for c in cal["cruces"]:
        sup = " (relación supuesta)" if c["supuesta"] else ""
        add(f"- {NOMBRE_TABLA[c['izquierda']]} con {NOMBRE_TABLA[c['derecha']]}{sup}, por {', '.join(f'`{k}`' for k in c['clave'])}, "
            f"{c['cardinalidad_esperada']}: sin pareja a la izquierda, {fmt(c['sin_pareja_izquierda'])}; a la derecha, {fmt(c['sin_pareja_derecha'])}."
            + (f" {c['nota'][0].upper()}{c['nota'][1:]}." if c.get("nota") else ""))
        etiquetas = {"claves_con_otro_numero_de_discos": "Claves con otro número de discos", "claves_con_mas_filas_que_discos": "Claves con más filas que discos",
                     "claves_con_otro_numero_de_fallos": "Claves con otro número de fallos", "casan_con_otro_modelo": "Filas que casan con otro modelo",
                     "casan_con_otra_capacidad": "Filas que casan con otra capacidad"}
        for k, etiqueta in etiquetas.items():
            if k in c:
                add(f"  - {etiqueta}: {fmt(c[k])}.")
        if c.get("antes_de_igualar"):
            add(f"  - Antes de igualar el centro vacío con «sin dato»: " + "; ".join(f"{k.replace('_', ' ')}, {fmt(v)}" for k, v in c["antes_de_igualar"].items()) + ".")
    add("")

    # 14. Reglas candidatas para aprobar
    add("## 14. Reglas candidatas para aprobar")
    add("")
    add("Juan aprobó las ocho como comprobaciones el 17/11/2026. Aquí se cuentan las filas que las incumplen y no se cambia ni se quita ninguna. "
        "Pasarlas a las reglas de negocio va por la cascada.")
    add("")
    for x in cal["reglas_candidatas"]:
        add(f"- {x['id']}. {x['regla']} Columnas: {', '.join(f'`{c}`' for c in x['columnas'])}. Incumplen: {fmt(x['filas_que_incumplen'])} {x['unidad']}.")
    add("")

    # 15. Resumen de problemas detectados
    add("## 15. Resumen de problemas detectados")
    add("")
    for p in cal["problemas"]:
        cer = f" Cerrado el {p['cerrado']['fecha']} ({p['cerrado']['decision']}): {p['cerrado']['texto']}." if p.get("cerrado") else ""
        add(f"- **{p['id']}** · bloque {p['bloque']} · {tablas_legibles(p['tabla'])} · `{p['columna']}`: {p['resultado']}.{cer}")
    add("")

    # 16. Posibles acciones
    add("## 16. Posibles acciones")
    add("")
    add("Ninguna se ha ejecutado. La corrección mide primero si quitar o arreglar cada cosa cambia la respuesta a alguna pregunta del caso.")
    add("")
    for p in cal["problemas"]:
        add(f"- {p['id']}: {p['posible_accion']}")
    add("")

    # 17. Parámetros usados
    add("## 17. Parámetros usados")
    add("")
    for p in cal["parametros"]:
        valor = fmt(p["valor"], 1) if isinstance(p["valor"], (int, float)) else p["valor"]
        add(f"- {p['nombre'][0].upper()}{p['nombre'][1:]}: {valor} ({p['origen']}).")
    add("")
    add(f"El plan lo aprobó {cal['plan_aprobado']['por']} el {cal['plan_aprobado']['fecha']}.")
    add("")

    # 18. Datos personales
    add("## 18. Datos personales")
    add("")
    for linea in cal["datos_personales_texto"]:
        add(f"- {linea}")
    add("")

    # 19. Límites de esta revisión
    add("## 19. Límites de esta revisión")
    add("")
    add("- Relaciones revisadas en el bloque 3.11: " + "; ".join(f"{NOMBRE_TABLA[c['izquierda']]} con {NOMBRE_TABLA[c['derecha']]}" for c in cal["cruces"]) + ".")
    add("- Dimensiones del reparto de vacíos: el periodo, el fabricante, el año, disco de datos o de arranque y, en las columnas de sitio, "
        "antes y después del 01/07/2023; en los contadores, también el modelo. Un segmento que no se ha mirado puede esconder una concentración.")
    for x in cal["no_aplicado"]:
        add(f"- {x['control'][0].upper()}{x['control'][1:]}: {x['motivo']}")
    add("")
    ruta.write_text("\n".join(L) + "\n", encoding="utf-8")


# =================================================================================================================
# 14. Principal
# =================================================================================================================
def escribir_json(cal, ruta):
    """Escribe el JSON sin NaN, que no es JSON válido."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(a_json(cal), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")


def main(raiz=CASO):
    """Diagnostica los cuatro datasets y escribe el JSON y el informe; devuelve el diccionario escrito."""
    inicio = time.time()
    tiempos = {}

    def marca(parte, desde):
        """Apunta lo que tardó una parte y lo dice en pantalla."""
        tiempos[parte] = round(time.time() - desde, 1)
        print(f"  {parte}: {tiempos[parte]} s", flush=True)
        return time.time()

    raw = raiz / "data" / "raw"
    pod = raw / "podado"
    ruta_json, ruta_md = raiz / "informes" / "calidad-datos.json", raiz / "informes" / "calidad-datos.md"
    cal = {"skill": SKILL, "version_skill": VERSION_SKILL, "script": SCRIPT, "fecha_datos": FECHA_DATOS,
           "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"), "entradas": [], "resultado": None, "pendientes": []}
    try:
        t0 = time.time()
        # 14.1 Huellas al empezar y el diccionario del origen
        huella_antes = huellas(raw)
        dic, tablas_dic, campos_dic, coincide = leer_diccionario(raiz, huella_antes)
        if not coincide:
            raise RuntimeError("el diccionario del origen describe otros ficheros: su huella no es la de data/raw/; hay que repetir la cadena desde diccionario-datos")
        ruta_prot = raiz / "contexto-proyecto" / "fuentes" / "proteccion-datos.json"
        proteccion = json.loads(ruta_prot.read_text(encoding="utf-8")) if ruta_prot.exists() else None
        t0 = marca("huellas y diccionario", t0)

        # 14.2 Las cuatro tablas pequeñas o estrechas en memoria
        fallos = pd.read_parquet(pod / "fallos.parquet")
        rec = pd.read_parquet(pod / "recuento_diario.parquet")
        columnas_rec = list(rec.columns)
        rec["periodo"] = np.where(rec["fecha"].dt.date >= INICIO_VALIDACION, "validacion", "construccion")
        ficheros_f = sorted((pod / "fotos_mensuales").glob("*.parquet"))
        ficheros_v = sorted((pod / "ventanas_fallo").glob("*.parquet"))

        # 14.3 Dimensiones de cada fila y la capacidad válida de cada modelo (reglas §3)
        modelos, centros = Catalogo(), Catalogo(primero=None)
        df_ = leer_dimensiones(ficheros_f, "fecha", modelos, centros)
        dv = leer_dimensiones(ficheros_v, "dia_fallo", modelos, centros)
        for m in rec["model"].unique():
            modelos.codigo(m)
        capacidades = {}
        for d in (df_, dv):
            mod, cap = d["modelo"], d["capacidad"]
            ok = cap >= CAPACIDAD_MIN_VALIDA
            pares = pd.DataFrame({"m": mod[ok], "c": cap[ok]}).drop_duplicates()
            for a, b in pares.itertuples(index=False):
                capacidades.setdefault(modelos.valores[int(a)], set()).add(float(b))
        for m, c in rec.loc[rec["capacity_bytes"] >= CAPACIDAD_MIN_VALIDA, ["model", "capacity_bytes"]].drop_duplicates().itertuples(index=False):
            capacidades.setdefault(m, set()).add(float(c))
        grupo_modelo = np.array([GRUPOS.index(grupo_de_capacidad(next(iter(capacidades[m])))) if len(capacidades.get(m, ())) == 1 else 2
                                 for m in modelos.valores], dtype=np.int8)
        fabricante_modelo = np.array([FABRICANTES.index(fabricante_de(m)) for m in modelos.valores], dtype=np.int8)
        grupo_de_modelo = {m: GRUPOS[g] for m, g in zip(modelos.valores, grupo_modelo)}
        completar_dimensiones(df_, grupo_modelo, fabricante_modelo)
        completar_dimensiones(dv, grupo_modelo, fabricante_modelo)
        modelos_varias = sorted(m for m, c in capacidades.items() if len(c) > 1)
        t0 = marca("dimensiones", t0)

        # 14.4 Fotos y ventanas, columna a columna
        salida = {k: [] for k in ("tipos", "nulos_por_segmento", "escala", "colas", "outliers", "codigos_candidatos", "contadores_por_modelo")}
        esp_f = perfilar_columnas("fotos_mensuales", df_, campos_dic["fotos_mensuales"], modelos, centros, salida)
        t0 = marca("fotos columna a columna", t0)
        esp_v = perfilar_columnas("ventanas_fallo", dv, campos_dic["ventanas_fallo"], modelos, centros, salida)
        t0 = marca("ventanas columna a columna", t0)

        # 14.5 Fotos fichero a fichero
        casi = {c for c, f in campos_dic["fotos_mensuales"].items() if f["filas_con_columna"] and 100 * f["nulos"] / f["filas_con_columna"] > CASI_VACIA_PCT}
        acc = recorrer_fotos(df_, casi, set(fallos["serial_number"]))
        t0 = marca("fotos fichero a fichero", t0)

        # 14.6 Fotos disco a disco
        seg = seguir_discos(df_, modelos, fallos)
        seriales_fotos = seg.pop("seriales")
        t0 = marca("fotos disco a disco", t0)

        # 14.7 Ventanas, recuento y lista de fallos
        v, del_dia, rv = mirar_ventanas(ficheros_v, grupo_de_modelo)
        variantes = []
        for t in ("fotos_mensuales", "ventanas_fallo", "recuento_diario"):
            for grupo in campos_dic[t]["model"].get("variantes", []):
                for m in grupo:
                    if m != modelo_normalizado(m) and m not in [x[0] for x in variantes]:
                        variantes.append((m, modelo_normalizado(m)))
        rr = mirar_recuento(rec, fallos, [m for par in variantes for m in par])
        t0 = marca("ventanas, recuento y lista de fallos", t0)

        # 14.8 Cruces entre los cuatro datasets
        cruces = cruzar(acc, v, del_dia, rec, fallos, seriales_fotos)
        t0 = marca("cruces", t0)

        # 14.9 Reglas candidatas, aprobadas como comprobaciones
        f1 = acc["failure1"]
        rc05 = int(len(f1.merge(fallos, left_on=["serial_number", "fecha"], right_on=["serial_number", "dia_fallo"], how="left", indicator=True)
                       .query("_merge == 'left_only'")))
        temp_f, temp_v = esp_f.get(TEMPERATURA, {}), esp_v.get(TEMPERATURA, {})
        rc_valores = {
            "RC-01": (seg["horas_bajan"]["veces"], "pares de fotos seguidas de un disco",
                      f"{fmt(seg['horas_bajan']['veces'])} veces bajan las horas entre dos fotos seguidas; {fmt(seg['horas_bajan']['mas_de_un_dia'])} más de un día"),
            "RC-02": (seg["cambios"]["modelo_o_capacidad"], "pares de fotos seguidas de un disco",
                      f"el modelo cambia {fmt(seg['cambios']['modelo'])} veces ({fmt(seg['cambios']['modelo_sin_variantes_de_espacios'])} sin contar las variantes de espacios) y la capacidad {fmt(seg['cambios']['capacidad'])} ({fmt(seg['cambios']['capacidad_entre_validas'])} entre capacidades válidas)"),
            "RC-03": (seg["contadores_bajan"]["veces_alguno"], "pares de fotos seguidas de un disco",
                      "; ".join(f"{k} baja {fmt(x['veces'])} veces en {fmt(x['discos'])} discos" for k, x in seg["contadores_bajan"]["por_contador"].items())),
            "RC-04": (temp_f.get("por_encima", 0) + temp_f.get("por_debajo", 0) + temp_v.get("por_encima", 0) + temp_v.get("por_debajo", 0), "filas",
                      f"fotos: {fmt(temp_f.get('por_encima', 0))} por encima de 70 y {fmt(temp_f.get('por_debajo', 0))} por debajo de 10; ventanas: {fmt(temp_v.get('por_encima', 0))} y {fmt(temp_v.get('por_debajo', 0))}"),
            "RC-05": (rc05, "filas", f"{fmt(len(f1))} fotos con failure = 1; {fmt(rc05)} no están en la lista de fallos con el mismo disco y día"),
            "RC-06": (rv["rc06"], "filas", f"{fmt(rv['rc06'])} filas de ventana con failure = 1 fuera del día de su fallo"),
            "RC-07": (rr["rc07"], "filas", f"{fmt(rr['rc07'])} filas del recuento con más fallos que discos"),
            "RC-08": (rr["rc08_dias_que_no_cuadran"], "días", f"{fmt(rr['rc08_dias_que_no_cuadran'])} de {fmt(rr['rc08_dias'])} días no cuadran con la lista de fallos"),
        }
        reglas_candidatas = [{"id": i, "tabla": t, "columnas": cols, "regla": regla, "filas_que_incumplen": rc_valores[i][0],
                              "unidad": rc_valores[i][1], "detalle": rc_valores[i][2], "aprobada": RC_APROBADAS_CON_EL_PLAN}
                             for i, t, cols, regla in REGLAS_CANDIDATAS]
        t0 = marca("reglas candidatas", t0)

        # 14.10 Lo que se escribe: bloques del JSON a partir de lo medido
        tablas_f = {t: tablas_dic[t] for t in TABLAS}
        def tam(ruta):
            """Bytes de un fichero o de todos los de una carpeta."""
            return sum(p.stat().st_size for p in ruta.rglob("*") if p.is_file()) if ruta.is_dir() else ruta.stat().st_size

        fuente_tablas = []
        for t, ruta in (("fotos_mensuales", pod / "fotos_mensuales"), ("ventanas_fallo", pod / "ventanas_fallo"),
                        ("recuento_diario", pod / "recuento_diario.parquet"), ("fallos", pod / "fallos.parquet")):
            td = tablas_f[t]
            cpf = td.get("columnas_por_fichero", {"min": td["columnas"], "max": td["columnas"]})
            fuente_tablas.append({"tabla": t, "ruta": ruta.relative_to(raiz).as_posix(), "ficheros": td.get("ficheros", 1), "bytes": tam(ruta),
                                  "filas": td["filas"], "columnas_min": cpf["min"], "columnas_max": cpf["max"],
                                  "filas_construccion": td["filas_por_periodo"]["construccion"], "filas_validacion": td["filas_por_periodo"]["validacion"]})
        # Las filas por periodo medidas aquí tienen que ser las del diccionario
        for nombre, d in (("fotos_mensuales", df_), ("ventanas_fallo", dv)):
            medidas = [int((d["periodo"] == p).sum()) for p in (0, 1)]
            if medidas != [tablas_f[nombre]["filas_por_periodo"]["construccion"], tablas_f[nombre]["filas_por_periodo"]["validacion"]]:
                raise RuntimeError(f"{nombre}: filas por periodo {medidas} distintas de las del diccionario")
        # Entradas del bloque común: filas y columnas del diccionario, huella de ahora
        filas_dic = {e["ruta"]: e for e in dic["entradas"]}
        cal["entradas"] = [{"ruta": f"data/raw/{k}", "sha256": h, "filas": filas_dic.get(f"data/raw/{k}", {}).get("filas"),
                            "columnas": filas_dic.get(f"data/raw/{k}", {}).get("columnas")} for k, h in huella_antes.items()]

        # Tipos: lo leído y el rol salen del diccionario; los vacíos, para la validación 6
        for tdesc in salida["tipos"]:
            tdesc["vacios"] = campos_dic[tdesc["tabla"]][tdesc["columna"]]["nulos"]
        for t in ("recuento_diario", "fallos"):
            for col, f in campos_dic[t].items():
                salida["tipos"].append({"tabla": t, "columna": col, "leido": f["tipo_leido"], "rol": f["rol"],
                                        "toca": {"magnitud": "número entero", "fecha": "fecha", "categorica": "texto", "identificador": "texto"}.get(f["rol"], "texto"),
                                        "pct_no_convierte": 0.0, "muestra": [], "aviso": None, "vacios": f["nulos"]})
        # Magnitudes del recuento: escala con todas las filas; colas y atípicos con la construcción
        for col in [c for c, f in campos_dic["recuento_diario"].items() if f["rol"] == "magnitud"]:
            x = rec[col].to_numpy(dtype="float64")
            salida["escala"].append({"tabla": "recuento_diario", "columna": col, **escala(x)})
            cons = np.sort(rec.loc[rec["periodo"].eq("construccion"), col].to_numpy(dtype="float64"))
            salida["colas"].append({"tabla": "recuento_diario", "columna": col, "filas": "construcción", **colas(cons)})
            salida["outliers"].append({"tabla": "recuento_diario", "columna": col, "filas": "construcción", "valores": len(cons), **atipicos(cons)})
            if col == "capacity_bytes":
                for tdesc in salida["tipos"]:
                    if tdesc["tabla"] == "recuento_diario" and tdesc["columna"] == col:
                        tdesc["muestra"] = rec[col].drop_duplicates().head(3).tolist()
        # Muestra y conversión de las fechas en texto
        for tdesc in salida["tipos"]:
            if tdesc["columna"] == "date":
                malas = acc["date_no_iso"] if tdesc["tabla"] == "fotos_mensuales" else rv["date_no_iso"]
                tdesc["pct_no_convierte"] = pct(malas, tablas_f[tdesc["tabla"]]["filas"])

        # Códigos de ausencia: los documentados por las reglas y los candidatos que salen de los datos
        cap_f, cap_v = esp_f.get("capacity_bytes", {}), esp_v.get("capacity_bytes", {})
        codigos = [
            {"tabla": "fotos_mensuales", "columna": "capacity_bytes", "codigo": "-1 o 0,1 TB", "tipo": "numérico", "filas": cap_f.get("no_valida", 0),
             "pct_filas": pct(cap_f.get("no_valida", 0), tablas_f["fotos_mensuales"]["filas"]), "documentado": True,
             "coincide_con": "filas sin horas encendido ni ningún contador", "mismas_filas_que": [HORAS, "todos los contadores en bruto"],
             "nota": f"{fmt(acc['no_valida_sin_contadores'])} de ellas no traen ningún contador: es una ausencia de la fila. Reglas §3: la capacidad es la de su modelo."},
            {"tabla": "ventanas_fallo", "columna": "capacity_bytes", "codigo": "-1 o 0,1 TB", "tipo": "numérico", "filas": cap_v.get("no_valida", 0),
             "pct_filas": pct(cap_v.get("no_valida", 0), tablas_f["ventanas_fallo"]["filas"]), "documentado": True, "coincide_con": "", "mismas_filas_que": [],
             "nota": "Reglas §3: la capacidad es la de su modelo."},
            {"tabla": "recuento_diario", "columna": "capacity_bytes", "codigo": "-1 o 0,1 TB", "tipo": "numérico", "filas": rr["capacidad_no_valida"],
             "pct_filas": pct(rr["capacidad_no_valida"], len(rec)), "documentado": True, "coincide_con": "", "mismas_filas_que": [],
             "nota": f"Llevan {fmt(rr['capacidad_no_valida_dias_de_disco'])} días de disco y {fmt(rr['capacidad_no_valida_fallos'])} fallos."},
            {"tabla": "recuento_diario", "columna": "datacenter", "codigo": "sin dato", "tipo": "texto", "filas": rr["sin_dato"],
             "pct_filas": pct(rr["sin_dato"], len(rec)), "documentado": True, "coincide_con": "fechas anteriores al 01/07/2023 en casi todas", "mismas_filas_que": [],
             "nota": f"{fmt(rr['sin_dato_desde_sitio'])} son desde el 01/07/2023. Reglas §4 y §5: el centro no consta y se cuenta."},
        ]
        for cc in salida["codigos_candidatos"]:
            ya = any(x["tabla"] == cc["tabla"] and x["columna"] == cc["columna"] for x in codigos)
            if not ya:
                extra = ""
                if cc["columna"] == "cluster_id":
                    extra = "Por centro: " + ", ".join(f"{k} {fmt(n)}" for k, n in esp_f.get("cluster_id", {}).get("ceros_por_centro", {}).items()) + "." if cc["tabla"] == "fotos_mensuales" else ""
                codigos.append({"tabla": cc["tabla"], "columna": cc["columna"], "codigo": cc["codigo"], "tipo": "numérico", "filas": cc["filas"],
                                "pct_filas": cc["pct_filas"], "documentado": False, "coincide_con": "", "mismas_filas_que": [],
                                "nota": f"Valor del {cc['extremo']} con el {fmt(cc['pct_filas'])} % de las filas que traen la columna. {extra}".strip()})
        textos = []
        for t in TABLAS:
            for col, f in campos_dic[t].items():
                if f["rol"] in ("categorica", "identificador") and (f.get("vacios") or f.get("espacios")):
                    textos.append({"tabla": t, "columna": col, "codigo": "cadena vacía o solo espacios", "filas": f.get("vacios", 0) + f.get("espacios", 0)})
        for t, col, serie in (("recuento_diario", "model", rec["model"]), ("recuento_diario", "datacenter", rec["datacenter"]),
                              ("ventanas_fallo", "model", v["model"]), ("ventanas_fallo", "datacenter", v["datacenter"])):
            vc = serie.dropna().value_counts()
            for val, n in vc.items():
                if str(val).strip().lower() in TEXTOS_AUSENCIA and (t, col, val) not in TEXTOS_DOCUMENTADOS:
                    textos.append({"tabla": t, "columna": col, "codigo": val, "filas": int(n)})
        for val in modelos.valores + [c for c in centros.valores if c is not None]:
            if str(val).strip().lower() in TEXTOS_AUSENCIA:
                textos.append({"tabla": "fotos_mensuales y ventanas_fallo", "columna": "model o datacenter", "codigo": val, "filas": None})
        instrucciones = [{"tabla": "fotos_mensuales, ventanas_fallo o recuento_diario", "columna": "model o datacenter", "valor": val}
                         for val in modelos.valores + [c for c in centros.valores if c is not None] if PATRON_INSTRUCCION.search(str(val))]

        # Reparto de vacíos: cuántas variables hay en cada veredicto
        resumen_reparto = {}
        for x in salida["nulos_por_segmento"]:
            resumen_reparto.setdefault(x["tabla"], Counter())[x["veredicto"]] += 1
        for t in ("fotos_mensuales", "ventanas_fallo"):
            resumen_reparto.setdefault(t, Counter())["sin_nulos"] = sum(1 for f in campos_dic[t].values() if f["nulos"] == 0)
        resumen_reparto = {t: dict(c) for t, c in resumen_reparto.items()}

        # Vacíos por fila: fotos fichero a fichero; ventanas, recuento y lista de fallos de una vez
        def mediana_de(contador):
            """Mediana de un recuento de filas por número de vacíos."""
            claves = sorted(contador)
            acumulado, mitad = 0, sum(contador.values()) / 2
            for k in claves:
                acumulado += contador[k]
                if acumulado >= mitad:
                    return k
            return None

        casi_v = {c for c, f in campos_dic["ventanas_fallo"].items() if f["filas_con_columna"] and 100 * f["nulos"] / f["filas_con_columna"] > CASI_VACIA_PCT}
        vf_todas, vf_sin = Counter(), Counter()
        enteras = []
        for ruta in ficheros_v:
            dfv = leer_tabla(ruta, [c for c in campos_dic["ventanas_fallo"]])
            dfv = dfv[[c for c in dfv.columns if c in pq.ParquetFile(ruta).schema_arrow.names]]
            nul = dfv.isna()
            vf_todas.update(nul.sum(axis=1).tolist())
            vf_sin.update(nul[[c for c in dfv.columns if c not in casi_v]].sum(axis=1).tolist())
            enteras.append(dfv)
        # Duplicados de las ventanas con todas sus columnas; las que un fichero no trae cuentan como vacías
        ventanas_enteras = pd.concat(enteras, ignore_index=True)
        dup_v = {"exactos": int(ventanas_enteras.duplicated().sum()),
                 "sin_serie": int(ventanas_enteras.drop(columns=["serial_number"]).duplicated().sum())}
        del enteras, ventanas_enteras
        vf_rec = Counter(rec[columnas_rec].isna().sum(axis=1).tolist())
        vf_fal = Counter(fallos.isna().sum(axis=1).tolist())
        vacios_por_fila = {
            "fotos_mensuales": {"con_todas": {str(k): n for k, n in sorted(acc["vacios_fila"].items())},
                                "sin_casi_vacias": {str(k): n for k, n in sorted(acc["vacios_fila_sin_casi"].items())}, "excluidas": sorted(casi),
                                "mediana_con_todas": mediana_de(acc["vacios_fila"]), "mediana_sin_casi_vacias": mediana_de(acc["vacios_fila_sin_casi"])},
            "ventanas_fallo": {"con_todas": {str(k): n for k, n in sorted(vf_todas.items())}, "sin_casi_vacias": {str(k): n for k, n in sorted(vf_sin.items())},
                               "excluidas": sorted(casi_v), "mediana_con_todas": mediana_de(vf_todas), "mediana_sin_casi_vacias": mediana_de(vf_sin)},
            "recuento_diario": {"con_todas": {str(k): int(n) for k, n in sorted(vf_rec.items())}, "sin_casi_vacias": None, "excluidas": [],
                                "mediana_con_todas": mediana_de(vf_rec), "mediana_sin_casi_vacias": None},
            "fallos": {"con_todas": {str(k): int(n) for k, n in sorted(vf_fal.items())}, "sin_casi_vacias": None, "excluidas": [],
                       "mediana_con_todas": mediana_de(vf_fal), "mediana_sin_casi_vacias": None},
        }
        t0 = marca("vacíos por fila de las ventanas", t0)

        # Estructura: vacías, casi vacías, constantes y columnas que entran a mitad, por tabla y por fichero
        estructura = {}
        for t in ("fotos_mensuales", "ventanas_fallo"):
            cf = campos_dic[t]
            estructura[t] = {"vacias": [c for c, f in cf.items() if f["filas_con_columna"] and f["nulos"] == f["filas_con_columna"]],
                             "casi_vacias": sorted(c for c, f in cf.items() if f["filas_con_columna"] and 100 * f["nulos"] / f["filas_con_columna"] > CASI_VACIA_PCT),
                             "constantes": [c for c, f in cf.items() if f["distintos"] == 1],
                             "a_mitad": [{"columna": c, "primer_fichero": f["primer_trozo"], "ficheros": f["trozos_con_columna"]} for c, f in cf.items() if f["filas_sin_columna"]],
                             "ficheros": tablas_f[t]["ficheros"]}
        pf_info = acc["por_fichero"]
        estructura["fotos_mensuales"].update({"ficheros_con_vacias": sum(1 for x in pf_info if x["vacias"]),
                                              "ficheros_con_constantes": sum(1 for x in pf_info if x["constantes"]),
                                              "por_fichero": [{"fichero": x["fichero"], "filas": x["filas"], "columnas": x["columnas"],
                                                               "vacias": len(x["vacias"]), "constantes": len(x["constantes"])} for x in pf_info],
                                              "columnas_vacias_en_algun_fichero": dict(Counter(c for x in pf_info for c in x["vacias"]).most_common()),
                                              "columnas_constantes_en_algun_fichero": dict(Counter(c for x in pf_info for c in x["constantes"]).most_common())})
        for t in ("recuento_diario", "fallos"):
            cf = campos_dic[t]
            estructura[t] = {"vacias": [c for c, f in cf.items() if f["nulos"] == f["filas_con_columna"]], "casi_vacias": [],
                             "constantes": [c for c, f in cf.items() if f["distintos"] == 1], "a_mitad": [], "ficheros": 1}

        # Nombres de columna (comprobaciones §9), en las cuatro tablas y en el esquema, leído tal cual
        lineas_esquema = [x.strip() for x in (raw / "Drive_Stats_Schema_Current.csv").read_text(encoding="utf-8-sig").splitlines() if x.strip()]
        nombres = []
        for t in TABLAS + ["esquema_backblaze"]:
            cols = list(campos_dic[t]) if t != "esquema_backblaze" else lineas_esquema
            for c in cols:
                avisos = [a for a, cond in (("espacios", " " in c), ("mayúsculas", c != c.lower()), ("tildes o eñes", c != nombre_normalizado(c) and bool(re.search(r"[^\x00-\x7f]", c))),
                                            ("puntos", "." in c), ("símbolos", bool(re.search(r"[^A-Za-z0-9_ .]", c)))) if cond]
                if t == "esquema_backblaze" and re.fullmatch(r"smart_\d+_\w+", c) and not re.fullmatch(r"smart_\d+_(raw|normalized)", c):
                    avisos.append("errata: no sigue la forma smart_N_raw o smart_N_normalized")
                if t == "esquema_backblaze" and not re.fullmatch(r"[a-z0-9_]+", c):
                    avisos.append("no es un nombre de columna")
                nombres.append({"tabla": t, "columna": c, "normalizado": nombre_normalizado(c), "avisos": avisos,
                                "colision_con": [o for o in cols if o != c and nombre_normalizado(o) == nombre_normalizado(c)]})

        # Categorías raras, tomadas del diccionario, y comprobado que ninguna es un código de ausencia
        raras = [{"tabla": t, "columna": col, "categoria": r["categoria"], "filas": r["filas"], "pct": r["pct"], "de_diccionario": True,
                  "es_codigo_de_ausencia": str(r["categoria"]).strip().lower() in TEXTOS_AUSENCIA}
                 for t in TABLAS for col, f in campos_dic[t].items() if f["rol"] == "categorica" for r in (f.get("categorias_raras") or [])]

        # Variantes de modelo (D1) en los tres datasets que traen el modelo
        variantes_salida = []
        for var, normal in variantes:
            iv, inn = modelos.indice.get(var), modelos.indice.get(normal)
            dv_ = seg["discos_de_modelo"]
            variantes_salida.append({"variante": var, "normal": normal,
                                     "fotos_filas": int(seg["modelos"]["filas"][iv]) if iv is not None else 0,
                                     "fotos_discos": int(seg["modelos"]["discos"][iv]) if iv is not None else 0,
                                     "fotos_filas_normal": int(seg["modelos"]["filas"][inn]) if inn is not None else 0,
                                     "discos_con_los_dos": len(dv_.get(iv, set()) & dv_.get(inn, set())),
                                     "ventanas_filas": int(v["model"].eq(var).sum()), "ventanas_discos": int(v.loc[v["model"].eq(var), "serial_number"].nunique()),
                                     "recuento_filas": rr["variantes"].get(var, {}).get("filas", 0),
                                     "recuento_dias_de_disco": rr["variantes"].get(var, {}).get("dias_de_disco", 0)})
        discos_dos_nombres = len(set().union(*[seg["discos_de_modelo"].get(modelos.indice[var], set()) & seg["discos_de_modelo"].get(modelos.indice[n], set())
                                               for var, n in variantes if var in modelos.indice and n in modelos.indice])) if variantes else 0
        sin_patron = [{"modelo": m, "grupo": grupo_de_modelo[m], "excepcion_de_las_reglas": m in EXCEPCIONES_FABRICANTE}
                      for m in modelos.valores if fabricante_de(m) == "sin patrón" or m in EXCEPCIONES_FABRICANTE]
        sin_patron_sin_explicar = [x for x in sin_patron if not x["excepcion_de_las_reglas"] and x["grupo"] != "arranque"]

        # Duplicados y claves
        clave_rec = tablas_f["recuento_diario"]["clave"]
        duplicados = [
            {"tabla": "fotos_mensuales", "exactos": acc["exactos"], "exactos_sin_identificadores": acc["sin_serie"], "identificadores_quitados": ["serial_number"],
             "clave_unica": tablas_f["fotos_mensuales"]["clave_unica"] and acc["serie_repetida"] == 0, "por_clave": acc["serie_repetida"], "casi_duplicados": 0,
             "logicos": sum(x["fotos_filas"] for x in variantes_salida)},
            {"tabla": "ventanas_fallo", "exactos": dup_v["exactos"], "exactos_sin_identificadores": dup_v["sin_serie"],
             "identificadores_quitados": ["serial_number"], "clave_unica": rv["clave_repetida"] == 0, "por_clave": rv["clave_repetida"], "casi_duplicados": 0,
             "logicos": sum(x["ventanas_filas"] for x in variantes_salida)},
            {"tabla": "recuento_diario", "exactos": int(rec[columnas_rec].duplicated().sum()),
             "exactos_sin_identificadores": int(rec[columnas_rec].duplicated().sum()), "identificadores_quitados": [],
             "clave_unica": not rec.duplicated(clave_rec).any(), "por_clave": int(rec.duplicated(clave_rec).sum()),
             "casi_duplicados": int(rec.duplicated(["fecha", "model", "datacenter"]).sum()), "logicos": sum(x["recuento_filas"] for x in variantes_salida)},
            {"tabla": "fallos", "exactos": int(fallos.duplicated().sum()), "exactos_sin_identificadores": int(fallos.drop(columns=["serial_number"]).duplicated().sum()),
             "identificadores_quitados": ["serial_number"], "clave_unica": not fallos.duplicated().any(), "por_clave": int(fallos.duplicated().sum()),
             "casi_duplicados": 0, "logicos": 0,
             "nota": "sin el número de serie se repiten los días con más de un fallo: no son copias, son fallos distintos del mismo día"},
        ]
        claves = [{"tabla": t, "que_es_una_fila": tablas_f[t]["que_es_una_fila"], "clave": tablas_f[t]["clave"],
                   "repetidas": tablas_f[t]["filas_clave_repetida"], "unica": tablas_f[t]["clave_unica"]} for t in TABLAS]

        # Fechas
        fechas = [
            {"tabla": "fotos_mensuales", "columna": "fecha", "minimo": campos_dic["fotos_mensuales"]["fecha"]["minimo"], "maximo": campos_dic["fotos_mensuales"]["fecha"]["maximo"],
             "convencion": "ISO", "demostrada": acc["date_no_iso"] == 0, "futuras": int((df_["dia"] > dia_de(HORIZONTE)).sum())},
            {"tabla": "fotos_mensuales", "columna": "date", "minimo": campos_dic["fotos_mensuales"]["date"]["minimo"], "maximo": campos_dic["fotos_mensuales"]["date"]["maximo"],
             "convencion": "ISO AAAA-MM-DD en texto", "demostrada": acc["date_no_iso"] == 0, "futuras": int((df_["dia"] > dia_de(HORIZONTE)).sum())},
            {"tabla": "ventanas_fallo", "columna": "fecha", "minimo": v["fecha"].min().date().isoformat(), "maximo": v["fecha"].max().date().isoformat(),
             "convencion": "ISO", "demostrada": bool(v["fecha"].notna().all()), "futuras": int(v["fecha"].dt.date.gt(HORIZONTE).sum())},
            {"tabla": "ventanas_fallo", "columna": "dia_fallo", "minimo": v["dia_fallo"].min().date().isoformat(), "maximo": v["dia_fallo"].max().date().isoformat(),
             "convencion": "ISO", "demostrada": bool(v["dia_fallo"].notna().all()), "futuras": int(v["dia_fallo"].dt.date.gt(HORIZONTE).sum())},
            {"tabla": "recuento_diario", "columna": "fecha", "minimo": rec["fecha"].min().date().isoformat(), "maximo": rec["fecha"].max().date().isoformat(),
             "convencion": "ISO", "demostrada": bool(rec["fecha"].notna().all()), "futuras": int(rec["fecha"].dt.date.gt(HORIZONTE).sum())},
            {"tabla": "fallos", "columna": "dia_fallo", "minimo": fallos["dia_fallo"].min().date().isoformat(), "maximo": fallos["dia_fallo"].max().date().isoformat(),
             "convencion": "ISO", "demostrada": bool(fallos["dia_fallo"].notna().all()), "futuras": int(fallos["dia_fallo"].dt.date.gt(HORIZONTE).sum())},
        ]

        # Comprobaciones de las reglas (plan aprobado, «Las comprobaciones de las reglas»)
        sitio_f, sitio_v = {c: esp_f.get(c, {}) for c in COLUMNAS_SITIO}, {c: esp_v.get(c, {}) for c in COLUMNAS_SITIO}
        contadores_parciales = [x for x in salida["contadores_por_modelo"] if x["tabla"] == "fotos_mensuales" and x["filas"] == "sin_capacidad_no_valida" and x["modelos_parciales"]]
        contadores_parciales_todas = [x for x in salida["contadores_por_modelo"] if x["tabla"] == "fotos_mensuales" and x["filas"] == "todas" and x["modelos_parciales"]]
        pares_parciales = sum(len(x["modelos_parciales"]) for x in contadores_parciales)
        filas_parciales = sum(m["vacios"] for x in contadores_parciales for m in x["modelos_parciales"])
        caps_v = sum(1 for m, c in capacidades.items() if len(c) > 1)
        fp = seg["fallos_y_fotos"]
        slot, tomo = rv["sitio_del_fallo"]["pod_slot_num"], rv["sitio_del_fallo"]["tomo"]
        # Días de las ventanas cuya fecha en texto es otra: discos y fallos del recuento ese día y el día del texto
        por_dia_rec = rec.groupby("fecha")[["discos", "fallos"]].sum()
        ddd = rv["date_distinta_detalle"]
        def del_recuento(dia, col):
            """Discos o fallos del recuento un día; null si el día no está."""
            return int(por_dia_rec.loc[pd.Timestamp(dia), col]) if pd.Timestamp(dia) in por_dia_rec.index else None

        ddd["recuento"] = [{"fecha": x["fecha"], "texto": x["texto"], "filas": x["filas"], "discos_fecha": del_recuento(x["fecha"], "discos"),
                            "discos_texto": del_recuento(x["texto"], "discos"), "fallos_fecha": del_recuento(x["fecha"], "fallos")}
                           for x in ddd["pares"]]

        def pct_sitio(e, cuando):
            """Porcentaje de filas sin dato de sitio (vacías o sin la columna) en un tramo."""
            x = e.get(cuando, {})
            return pct(x.get("vacios", 0) + x.get("sin_columna", 0), x.get("filas", 0))

        comprobaciones = [
            {"id": "R-01", "regla": "la capacidad de un disco es la de su modelo", "seccion": "reglas §3",
             "medidas": {"modelos_con_varias_capacidades_validas": modelos_varias, "fotos_no_validas_por_modelo": cap_f.get("no_valida_por_modelo", {}),
                         "fotos_no_validas_por_grupo": cap_f.get("no_valida_por_grupo_del_modelo", {}), "fallos_con_capacidad_no_valida_el_dia_del_fallo": int(del_dia["capacity_bytes"].lt(CAPACIDAD_MIN_VALIDA).sum())},
             "resultado": f"ningún modelo trae dos capacidades válidas ({fmt(caps_v)} con más de una). Filas con -1 o 0,1 TB: {fmt(cap_f.get('no_valida', 0))} en fotos, {fmt(cap_v.get('no_valida', 0))} en ventanas y {fmt(rr['capacidad_no_valida'])} en el recuento; {fmt(int(del_dia['capacity_bytes'].lt(CAPACIDAD_MIN_VALIDA).sum()))} fallos la traen el día del fallo."},
            {"id": "R-02", "regla": "el fabricante sale del nombre del modelo, con dos excepciones", "seccion": "reglas §3",
             "medidas": {"sin_patron": sin_patron, "sin_explicar": sin_patron_sin_explicar},
             "resultado": f"{fmt(len(sin_patron))} modelos no siguen el patrón; {fmt(len(sin_patron_sin_explicar))} no son ni de arranque ni una de las dos excepciones."},
            {"id": "R-03", "regla": "la edad son las horas encendido y, sin ellas, cuenta desde la primera aparición", "seccion": "reglas §3",
             "medidas": {**seg["horas_discos"], "fallos_con_edad_negativa": fp["fallos_con_edad_negativa"]},
             "resultado": f"discos de datos sin horas en ninguna foto, {fmt(seg['horas_discos']['sin_horas_en_ninguna_foto_datos'])}; con horas en unas fotos y no en otras, {fmt(seg['horas_discos']['con_horas_en_unas_fotos_y_no_en_otras_datos'])}. Fallos con edad negativa por la primera aparición en las fotos: {fmt(fp['fallos_con_edad_negativa'])}."},
            {"id": "R-04", "regla": "un disco puede fallar dos veces y seguir en servicio tras un fallo", "seccion": "reglas §3",
             "medidas": {"discos_con_mas_de_un_fallo": int((fallos.groupby('serial_number').size() > 1).sum()), **{k: fp[k] for k in ("discos_que_siguen_tras_su_fallo", "de_ellos_con_dos_fallos_en_la_lista")}},
             "resultado": f"{fmt(int((fallos.groupby('serial_number').size() > 1).sum()))} discos fallan dos veces. {fmt(fp['discos_que_siguen_tras_su_fallo'])} discos salen en alguna foto después de su fallo, y {fmt(fp['de_ellos_con_dos_fallos_en_la_lista'])} de ellos tienen dos fallos en la lista."},
            {"id": "R-05", "regla": "un disco que falta en una foto y vuelve no ha desaparecido", "seccion": "reglas §3", "medidas": seg["huecos"],
             "resultado": f"{fmt(seg['huecos']['discos_datos'])} discos de datos ({fmt(seg['huecos']['pct_discos_datos'])} %) faltan en alguna foto y vuelven; huecos de un mes: {fmt(seg['huecos']['meses_que_faltan'].get('1', 0))} de {fmt(seg['huecos']['huecos'])}."},
            {"id": "R-06", "regla": "el sitio solo consta desde el 01/07/2023 y no se rellena hacia atrás", "seccion": "reglas §4",
             "medidas": {"fotos": {c: {"antes": e.get("antes_sitio"), "desde": e.get("desde_sitio")} for c, e in sitio_f.items() if e},
                         "ventanas": {c: {"antes": e.get("antes_sitio"), "desde": e.get("desde_sitio")} for c, e in sitio_v.items() if e}},
             "resultado": "en las fotos, sin dato antes y desde el 01/07/2023: " + "; ".join(f"{c} {fmt(pct_sitio(e, 'antes_sitio'))} % y {fmt(pct_sitio(e, 'desde_sitio'))} %" for c, e in sitio_f.items() if e) + "."},
            {"id": "R-07", "regla": "un disco con dos registros el mismo día cuenta una vez", "seccion": "reglas §5",
             "medidas": {"fotos": acc["serie_repetida"], "ventanas": rv["clave_repetida"]},
             "resultado": f"repeticiones de disco y día: {fmt(acc['serie_repetida'])} en las fotos y {fmt(rv['clave_repetida'])} en las ventanas."},
            {"id": "R-08", "regla": "un contador vacío quiere decir que ese modelo no lo apunta", "seccion": "reglas §5",
             "medidas": {"contadores_con_modelos_parciales": len(contadores_parciales), "pares_modelo_contador_parciales": pares_parciales,
                         "filas_vacias_en_esos_pares": filas_parciales, "contadores_con_modelos_parciales_contando_capacidad_no_valida": len(contadores_parciales_todas)},
             "resultado": f"sin las filas de capacidad no válida, {fmt(pares_parciales)} pares de modelo y contador tienen vacíos solo en parte de sus filas, en {fmt(len(contadores_parciales))} contadores; suman {fmt(filas_parciales)} filas vacías. Son los que contradicen la regla."},
            {"id": "R-09", "regla": "un sitio vacío quiere decir que no consta", "seccion": "reglas §5",
             "medidas": {"fotos": {c: e.get("vacios_desde_sitio_por_centro") for c, e in sitio_f.items() if e},
                         "ventanas": {c: e.get("vacios_desde_sitio_por_centro") for c, e in sitio_v.items() if e},
                         "fotos_por_grupo": {c: e.get("vacios_desde_sitio_por_grupo") for c, e in sitio_f.items() if e}},
             "resultado": "filas de fotos sin dato de sitio desde el 01/07/2023: " + "; ".join(f"{c} {fmt(e.get('desde_sitio', {}).get('vacios', 0))}" for c, e in sitio_f.items() if e) + ". El reparto por centro y por grupo está en el JSON."},
            {"id": "R-10", "regla": "el sitio de un fallo es el del último día anterior que lo trae, dentro de su ventana", "seccion": "reglas §5",
             "medidas": rv["sitio_del_fallo"],
             "resultado": f"de {fmt(slot['fallos_datos_desde_sitio'])} fallos de discos de datos desde el 01/07/2023, {fmt(slot['sin_dato_el_dia'])} no traen ranura el día del fallo; {fmt(slot['lo_recuperan_un_dia_anterior'])} la recuperan un día anterior y {fmt(slot['sin_dato_ningun_dia'])} no la tienen ningún día."},
            {"id": "R-11", "regla": "los valores en bruto de algunos contadores tienen formato de cada fabricante", "seccion": "reglas §5",
             "medidas": {c: esp_f.get(c, {}).get("por_fabricante_construccion") for c in FORMATO_PROPIO},
             "resultado": "rango y cifras por fabricante, con la construcción: " + "; ".join(
                 f"{c} de {fmt(min(x['minimo'] for x in esp_f[c]['por_fabricante_construccion'].values()))} a {fmt(max(x['maximo'] for x in esp_f[c]['por_fabricante_construccion'].values()))}"
                 for c in FORMATO_PROPIO if esp_f.get(c, {}).get("por_fabricante_construccion")) + ". El detalle por fabricante, en el JSON."},
        ]

        # Cuestiones del reconocimiento (plan aprobado, «Lo que el reconocimiento dejó para este paso»)
        s188 = esp_f.get("smart_188_raw", {})
        hb = seg["horas_bajan"]
        hundidos = rr["dias_hundidos"]
        cuestiones = [
            {"id": "Q-01", "cuestion": "modelos con dos espacios tras «WDC» (D1)", "medidas": {"variantes": variantes_salida, "discos_con_dos_nombres": discos_dos_nombres},
             "resultado": f"{fmt(len(variantes_salida))} variantes; {fmt(sum(x['fotos_filas'] for x in variantes_salida))} filas de fotos, {fmt(sum(x['ventanas_filas'] for x in variantes_salida))} de ventanas y {fmt(sum(x['recuento_filas'] for x in variantes_salida))} del recuento. {fmt(discos_dos_nombres)} discos salen con los dos nombres. Cerrada el 17/11/2026 (D1)."},
            {"id": "Q-02", "cuestion": "capacidad -1 o 0,1 TB", "medidas": {"fotos_por_periodo": cap_f.get("no_valida_por_periodo"), "ventanas_por_periodo": cap_v.get("no_valida_por_periodo"),
                                                                              "recuento_por_periodo": rr["capacidad_no_valida_por_periodo"], "recuento_por_modelo": rr["capacidad_no_valida_por_modelo"],
                                                                              "valores_fotos": cap_f.get("valores_no_validos"), "valores_ventanas": cap_v.get("valores_no_validos")},
             "resultado": f"{fmt(cap_f.get('no_valida', 0))} filas de fotos, {fmt(cap_v.get('no_valida', 0))} de ventanas y {fmt(rr['capacidad_no_valida'])} del recuento; en construcción, {fmt(cap_f.get('no_valida_por_periodo', [0])[0])} de las fotos."},
            {"id": "Q-03", "cuestion": "centro «sin dato» en el recuento", "medidas": {k: rr[k] for k in ("sin_dato", "sin_dato_desde_sitio", "sin_dato_dias_de_disco", "sin_dato_desde_sitio_dias_de_disco")},
             "resultado": f"{fmt(rr['sin_dato'])} filas con {fmt(rr['sin_dato_dias_de_disco'])} días de disco; {fmt(rr['sin_dato_desde_sitio'])} son desde el 01/07/2023."},
            {"id": "Q-04", "cuestion": "horas encendido que faltan", "medidas": {**esp_f.get(HORAS, {}), "fallos_con_edad_negativa": fp["fallos_con_edad_negativa"]},
             "resultado": f"{fmt(esp_f.get(HORAS, {}).get('vacias_datos', 0))} filas de fotos de discos de datos sin horas: {fmt(esp_f.get(HORAS, {}).get('vacias_datos_capacidad_no_valida', 0))} son de capacidad no válida y {fmt(esp_f.get(HORAS, {}).get('vacias_datos_resto', 0))} del resto. Fallos con edad negativa: {fmt(fp['fallos_con_edad_negativa'])}."},
            {"id": "Q-05", "cuestion": "el 188 por encima de mil millones (D2)", "medidas": s188,
             "resultado": f"{fmt(s188.get('mas_de_mil_millones_datos', 0))} filas de fotos de discos de datos; por fabricante: " + ", ".join(f"{k} {fmt(n)}" for k, n in s188.get("por_fabricante_datos", {}).items()) + ". Cerrada el 17/11/2026 (D2)."},
            {"id": "Q-06", "cuestion": "el 5 y el 187 en su tope (D3)", "medidas": {"fotos": {c: esp_f.get(c) for c in ("smart_5_raw", "smart_187_raw")}, "ventanas": {c: esp_v.get(c) for c in ("smart_5_raw", "smart_187_raw")}},
             "resultado": f"el 187 vale 65.535 en {fmt(esp_f.get('smart_187_raw', {}).get('en_65535', 0))} filas de fotos y {fmt(esp_v.get('smart_187_raw', {}).get('en_65535', 0))} de ventanas; el máximo del 5 es {fmt(esp_f.get('smart_5_raw', {}).get('maximo'))} en fotos y {fmt(esp_v.get('smart_5_raw', {}).get('maximo'))} en ventanas. Las colas, en «colas». Cerrada el 17/11/2026 (D3)."},
            {"id": "Q-07", "cuestion": "fallos sin ranura", "medidas": {"ranura": slot, "tomo": tomo},
             "resultado": f"{fmt(slot['sin_dato_el_dia'])} fallos de discos de datos sin ranura el día del fallo desde el 01/07/2023, {fmt(slot['sin_dato_ningun_dia'])} sin ranura ningún día de su ventana. "
                          f"Sin tomo completo (centro, vault y ranura) ningún día de su ventana: {fmt(tomo['sin_dato_ningun_dia'])}."},
            {"id": "Q-08", "cuestion": "fallos sin foto o sin día anterior", "medidas": {"fallos_sin_foto": fp["fallos_sin_foto"], "discos_sin_foto": fp["discos_sin_foto"],
                                                                                          "sin_dia_anterior_datos": rv["sin_dia_anterior_datos"], "sin_dia_anterior": rv["sin_dia_anterior"],
                                                                                          "ventanas_de_menos_de_31_filas": tablas_f["ventanas_fallo"]["medidas"]["ventanas con menos de 31 filas"]},
             "resultado": f"{fmt(fp['fallos_sin_foto'])} fallos de discos que no salen en ninguna foto; {fmt(rv['sin_dia_anterior_datos'])} fallos de discos de datos sin el día anterior en su ventana ({fmt(rv['sin_dia_anterior'])} con los de arranque)."},
            {"id": "Q-09", "cuestion": "horas que bajan", "medidas": hb,
             "resultado": f"{fmt(hb['mas_de_un_dia_datos'])} veces bajan más de un día en discos de datos, en {fmt(hb['discos_mas_de_un_dia_datos'])} discos; {fmt(hb['mas_de_un_ano_datos'])} bajan más de un año."},
            {"id": "Q-10", "cuestion": "días hundidos en el recuento", "medidas": {"dias": hundidos, "mayores_caidas": rr["mayores_caidas"]},
             "resultado": "discos que faltan frente a la media del día de antes y el de después: " + "; ".join(f"{x['dia']}, {fmt(x['faltan'])}" for x in hundidos) + "."},
            {"id": "Q-11", "cuestion": "tipos y nombres", "medidas": {"centro_sin_tipo": acc["centro_sin_tipo"], "erratas": [n["columna"] for n in nombres if any(a.startswith("errata") for a in n["avisos"])]},
             "resultado": f"la ranura llega como decimal; el centro, sin tipo en {fmt(len(acc['centro_sin_tipo']))} ficheros de fotos; erratas del esquema: " + ", ".join(n["columna"] for n in nombres if any(a.startswith("errata") for a in n["avisos"])) + "."},
            {"id": "Q-12", "cuestion": "temperatura por encima de 70 grados en las ventanas", "medidas": {"filas": rv["temperatura_alta"], "fotos_maximo": temp_f.get("maximo"), "ventanas_maximo": temp_v.get("maximo")},
             "resultado": f"{fmt(len(rv['temperatura_alta']))} filas de ventanas de {fmt(len({x['serial_number'] for x in rv['temperatura_alta']}))} discos, con máximo de {fmt(temp_v.get('maximo'))} grados; en las fotos el máximo es {fmt(temp_f.get('maximo'))}."},
        ]

        # Riesgos para un modelo (comprobaciones §2): la pregunta 4 entrena uno
        def sin_dato_periodo(e, p):
            """Porcentaje de filas de las fotos de un periodo sin el dato: vacías o de ficheros que no traen la columna."""
            total = tablas_f["fotos_mensuales"]["filas_por_periodo"]["construccion" if p == 0 else "validacion"]
            return pct(e["vacios_por_periodo"][p] + total - e["filas_por_periodo"][p], total) if e else None

        obj = seg["objetivo"]
        sitio_riesgo = [c for c in ("datacenter", "vault_id", "pod_slot_num") if c in esp_f]
        contadores_riesgo = [c for c in ("smart_187_raw", "smart_188_raw") if c in esp_f]
        riesgos = [
            {"tabla": "fotos_mensuales", "columna": ", ".join(sitio_riesgo), "riesgo":
             "El sitio falta al construir y está al validar. Sin dato en construcción: " + ", ".join(f"{c} {fmt(sin_dato_periodo(esp_f[c], 0))} %" for c in sitio_riesgo)
             + ". En validación: " + ", ".join(f"{c} {fmt(sin_dato_periodo(esp_f[c], 1))} %" for c in sitio_riesgo) + "."},
            {"tabla": "fotos_mensuales", "columna": ", ".join(contadores_riesgo), "riesgo":
             "Los contadores 187 y 188 solo los traen los Seagate y su vacío cambia entre periodos: " + "; ".join(f"{c}, {fmt(sin_dato_periodo(esp_f[c], 0))} % en construcción y {fmt(sin_dato_periodo(esp_f[c], 1))} % en validación" for c in contadores_riesgo) + "."},
            {"tabla": "fotos_mensuales y fallos", "columna": "objetivo", "riesgo":
             f"La variable objetivo está muy desequilibrada. Con el fallo a 30 días, la construcción tiene {fmt(obj['30']['casos'])} casos frente a {fmt(obj['30']['no_casos'])} no casos ({fmt(obj['30']['pct_casos'], 4)} %). "
             f"A 90 días, como el reconocimiento, {fmt(obj['90']['casos'])} frente a {fmt(obj['90']['no_casos'])}."},
            {"tabla": "ventanas_fallo", "columna": "todas", "riesgo": f"Las ventanas solo existen para los {fmt(tablas_f['ventanas_fallo']['discos_distintos'])} discos que fallan: usar sus columnas día a día mezclaría con el objetivo información que solo tienen los que fallan."},
            {"tabla": "fotos_mensuales", "columna": "model", "riesgo": f"El modelo tiene {fmt(campos_dic['fotos_mensuales']['model']['distintos'])} valores en las fotos, {fmt(len(campos_dic['fotos_mensuales']['model'].get('categorias_raras') or []))} de ellos por debajo del umbral de categoría rara."},
            {"tabla": "fotos_mensuales", "columna": "smart_N_normalized, capacity_bytes", "riesgo": f"Columnas calculadas a partir de otras: las {fmt(sum(1 for c in campos_dic['fotos_mensuales'] if c.endswith('_normalized')))} notas normalizadas salen del valor en bruto de su contador, y la capacidad sale del modelo."},
        ]

        # Cifras de control: las del encargo y las de la prueba, leídas de lo medido
        tv = tablas_f["ventanas_fallo"]
        control = {
            "fotos.ficheros": tablas_f["fotos_mensuales"]["ficheros"], "fotos.filas": int(df_["offsets"][-1]),
            "fotos.filas_construccion": int((df_["periodo"] == 0).sum()), "fotos.filas_validacion": int((df_["periodo"] == 1).sum()),
            "ventanas.ficheros": tv["ficheros"], "ventanas.filas": int(dv["offsets"][-1]),
            "ventanas.filas_construccion": int((dv["periodo"] == 0).sum()), "ventanas.filas_validacion": int((dv["periodo"] == 1).sum()),
            "recuento.filas": len(rec), "recuento.filas_construccion": int(rec["periodo"].eq("construccion").sum()), "recuento.filas_validacion": int(rec["periodo"].eq("validacion").sum()),
            "fallos.filas": len(fallos), "fallos.discos": int(fallos["serial_number"].nunique()),
            "fallos.filas_construccion": int(fallos["dia_fallo"].dt.date.lt(INICIO_VALIDACION).sum()), "fallos.filas_validacion": int(fallos["dia_fallo"].dt.date.ge(INICIO_VALIDACION).sum()),
            "fotos.capacidad_no_valida": cap_f.get("no_valida", 0), "ventanas.capacidad_no_valida": cap_v.get("no_valida", 0), "recuento.capacidad_no_valida": rr["capacidad_no_valida"],
            "fotos.capacidad_no_valida_sin_ningun_contador": acc["no_valida_sin_contadores"],
            "recuento.sin_dato": rr["sin_dato"], "recuento.sin_dato_desde_sitio": rr["sin_dato_desde_sitio"],
            "fotos.cluster_cero": esp_f.get("cluster_id", {}).get("ceros", 0), "fotos.cluster_filas": esp_f.get("cluster_id", {}).get("filas_con_columna", 0),
            "fotos.temp_mas_70": temp_f.get("por_encima", 0), "fotos.temp_max": temp_f.get("maximo"),
            "ventanas.temp_mas_70": temp_v.get("por_encima", 0), "ventanas.temp_max": temp_v.get("maximo"),
            "fotos.failure_1": len(f1), "rc05.fuera_de_lista": rc05, "fotos.disco_repetido_en_foto": acc["serie_repetida"],
            "rc06": rv["rc06"], "rc07": rr["rc07"], "rc08.dias_que_no_cuadran": rr["rc08_dias_que_no_cuadran"], "rc08.dias": rr["rc08_dias"],
            "fotos.discos_con_hueco": seg["huecos"]["discos"], "fotos.discos_datos_con_hueco": seg["huecos"]["discos_datos"],
            "fotos.s188_mas_de_mil_millones": s188.get("mas_de_mil_millones", 0), "fotos.s187_en_65535": esp_f.get("smart_187_raw", {}).get("en_65535", 0),
            "fotos.filas_variante_espacios": sum(x["fotos_filas"] for x in variantes_salida),
            "ventanas.fallos_ranura_recuperada": slot["lo_recuperan_un_dia_anterior"],
            "ventanas.fallos_sin_tomo_ningun_dia": tomo["sin_dato_ningun_dia"],
            "ventanas.fecha_y_texto_distintos": rv["date_distinta"],
            "huella.ficheros": len(huella_antes), "huella.esquema": huella_antes.get("Drive_Stats_Schema_Current.csv"),
            "huella.fallos": huella_antes.get("podado/fallos.parquet"),
        }

        # Problemas, uno por resultado con algo que valorar; si su cifra es cero no se añade
        P = []
        nf, nv, nr = tablas_f["fotos_mensuales"]["filas"], tablas_f["ventanas_fallo"]["filas"], len(rec)
        quitar = "la corrección mide si quitarlas cambia la respuesta a alguna pregunta del caso"
        problema(P, "3.2", "fotos_mensuales", "(varias)", f"{fmt(len(estructura['fotos_mensuales']['casi_vacias']))} columnas vacías en más del 99 % de las filas que las traen",
                 len(estructura["fotos_mensuales"]["casi_vacias"]), None, "son contadores que casi ningún modelo apunta; la lista está en «estructura»",
                 "la corrección decide si las deja fuera de las tablas de trabajo; ninguna es uno de los cinco contadores de avería"
                 if not set(estructura["fotos_mensuales"]["casi_vacias"]) & set(CONTADORES_AVERIA) else "la corrección decide si las deja fuera de las tablas de trabajo",
                 unidad="columnas")
        erratas = [n["columna"] for n in nombres if any(a.startswith("errata") for a in n["avisos"])]
        problema(P, "3.2", "esquema_backblaze", ", ".join(erratas), f"{fmt(len(erratas))} nombres con errata en el esquema", len(erratas), None,
                 "el esquema no es un dataset: solo afecta a la documentación", "nada en los datos; avisar al documentar las columnas", unidad="nombres")
        problema(P, "3.3", "fotos_mensuales", "datacenter", f"el centro llega sin tipo en {fmt(len(acc['centro_sin_tipo']))} ficheros de fotos", len(acc["centro_sin_tipo"]), None,
                 "es la forma de un centro vacío entero antes del 01/07/2023 (reglas §4)", "leer el centro como texto al juntar los ficheros", unidad="ficheros")
        ranura = campos_dic["fotos_mensuales"].get("pod_slot_num", {})
        problema(P, "3.3", "fotos_mensuales", "pod_slot_num", "la ranura llega como decimal",
                 (ranura.get("filas_con_columna", 0) - ranura.get("nulos", 0)) if ranura.get("tipo_leido") == "double" else 0, nf,
                 f"el {fmt(next((t['pct_no_convierte'] for t in salida['tipos'] if t['tabla'] == 'fotos_mensuales' and t['columna'] == 'pod_slot_num'), 0))} % de sus valores no es entero; el decimal sale de los vacíos", "leerla como entero con vacíos")
        problema(P, "3.4", "fotos_mensuales", "capacity_bytes", f"{fmt(cap_f.get('no_valida', 0))} filas con capacidad -1 o 0,1 TB; {fmt(acc['no_valida_sin_contadores'])} de ellas sin ningún contador",
                 cap_f.get("no_valida", 0), nf, "ausencia de la fila: no traen horas ni contadores", "tomar la capacidad del modelo (reglas §3); " + quitar + " por no traer contadores", principal=True)
        problema(P, "3.4", "ventanas_fallo", "capacity_bytes", f"{fmt(cap_v.get('no_valida', 0))} filas con capacidad -1 o 0,1 TB", cap_v.get("no_valida", 0), nv, "", "tomar la capacidad del modelo (reglas §3)")
        problema(P, "3.4", "recuento_diario", "capacity_bytes", f"{fmt(rr['capacidad_no_valida'])} filas con capacidad -1 o 0,1 TB, con {fmt(rr['capacidad_no_valida_fallos'])} fallos",
                 rr["capacidad_no_valida"], nr, f"parten una clave en dos: {fmt(duplicados[2]['casi_duplicados'])} filas repiten clave si se quita la capacidad",
                 "tomar la capacidad del modelo y sumar las filas que quedan con la misma clave (reglas §3)", principal=True)
        problema(P, "3.4", "recuento_diario", "datacenter", f"{fmt(rr['sin_dato'])} filas con centro «sin dato», {fmt(rr['sin_dato_desde_sitio'])} desde el 01/07/2023",
                 rr["sin_dato"], nr, "código documentado (reglas §4 y §5)", "contarlas y decirlas en las tasas por centro; no se apartan en silencio", principal=True)
        for c in ("datacenter", "pod_slot_num"):
            e = esp_f.get(c, {})
            desde = e.get("desde_sitio", {}).get("vacios", 0)
            problema(P, "3.4", "fotos_mensuales", c, f"{fmt(desde)} filas sin dato desde el 01/07/2023; de discos de datos, {fmt(e.get('vacios_desde_sitio_por_grupo', {}).get('datos', 0))}",
                     desde, e.get("desde_sitio", {}).get("filas"), "el sitio vacío quiere decir que no consta (reglas §5); en la ranura, casi todas son discos de arranque, que no tienen ranura",
                     "contarlas y decirlas en las cifras por centro y por tomo (reglas §7, población del análisis)")
        cl = esp_f.get("cluster_id", {})
        problema(P, "3.4", "fotos_mensuales", "cluster_id", f"vale 0 en {fmt(cl.get('ceros', 0))} de {fmt(cl.get('filas_con_columna', 0))} filas que traen la columna",
                 cl.get("ceros", 0), cl.get("filas_con_columna"), "código de ausencia candidato: un extremo del rango con más del 5 %", "ninguna: ninguna pregunta usa la columna", cerrado="D4")
        conc = [x for x in salida["nulos_por_segmento"] if x["veredicto"] == "concentrados"]
        problema(P, "3.4", "fotos_mensuales y ventanas_fallo", "(varias)", f"{fmt(len(conc))} variables con los vacíos concentrados en algún segmento", len(conc), None,
                 "cambia las comparaciones entre segmentos aunque el porcentaje global sea bajo; el detalle, en «nulos_por_segmento»",
                 "tenerlo en cuenta al comparar fabricantes, modelos o periodos con esas columnas", unidad="variables")
        problema(P, "3.5", "fotos_mensuales, ventanas_fallo y recuento_diario", "model", f"{fmt(len(variantes_salida))} modelos escritos con dos espacios tras «WDC»; {fmt(discos_dos_nombres)} discos salen con los dos nombres",
                 sum(x["fotos_filas"] + x["ventanas_filas"] + x["recuento_filas"] for x in variantes_salida), None, "duplicado lógico de la misma entidad",
                 "la corrección junta cada variante con su modelo", decision=True, cerrado="D1", principal=True)
        problema(P, "3.7", "fotos_mensuales", "model", f"{fmt(len(sin_patron_sin_explicar))} modelos de datos no siguen el patrón de su fabricante ni son excepción de las reglas",
                 len(sin_patron_sin_explicar), None, ", ".join(x["modelo"] for x in sin_patron_sin_explicar), "preguntar su fabricante antes de compararlos por fabricante",
                 unidad="modelos")
        problema(P, "3.8", "fotos_mensuales", "smart_188_raw", f"{fmt(s188.get('mas_de_mil_millones_datos', 0))} filas de discos de datos por encima de mil millones",
                 s188.get("mas_de_mil_millones_datos", 0), nf, "formato propio del fabricante; por fabricante: " + ", ".join(f"{k} {fmt(n)}" for k, n in s188.get("por_fabricante_datos", {}).items()),
                 "se lee como aviso si pasa de cero y no entra en la suma de la regla de los contadores; su valor como variable se mira en la preselección", decision=True, cerrado="D2", principal=True)
        tope = esp_f.get("smart_187_raw", {}).get("en_65535", 0) + esp_v.get("smart_187_raw", {}).get("en_65535", 0)
        problema(P, "3.8", "fotos_mensuales y ventanas_fallo", "smart_5_raw, smart_187_raw", f"el 187 en 65.535 en {fmt(tope)} filas; el 5 llega a {fmt(esp_f.get('smart_5_raw', {}).get('maximo'))} en las fotos",
                 tope, None, "tope del contador de 16 bits", "ninguna: el disco avisa igual", decision=True, cerrado="D3")
        problema(P, "3.8", "ventanas_fallo", TEMPERATURA, f"{fmt(temp_v.get('por_encima', 0))} filas por encima de 70 grados, con máximo de {fmt(temp_v.get('maximo'))}",
                 temp_v.get("por_encima", 0), nv, "en las fotos el máximo es 70; incumple RC-04", quitar + "; son de discos a punto de fallar", principal=True)
        problema(P, "3.8", "fotos_mensuales y ventanas_fallo", TEMPERATURA, f"{fmt(temp_f.get('por_debajo', 0) + temp_v.get('por_debajo', 0))} filas por debajo de 10 grados",
                 temp_f.get("por_debajo", 0) + temp_v.get("por_debajo", 0), None, "incumple RC-04", quitar)
        problema(P, "3.9", "fotos_mensuales", "date", f"{fmt(acc['date_distinta'])} filas en que el texto de la fecha no dice lo mismo que la fecha", acc["date_distinta"], nf, "", "usar una sola de las dos")
        problema(P, "3.9", "ventanas_fallo", "fecha, date",
                 f"{fmt(rv['date_distinta'])} filas en que la fecha y su texto no coinciden: " + "; ".join(f"fecha {x['fecha']}, texto {x['texto']}" for x in ddd["recuento"]),
                 rv["date_distinta"], nv,
                 f"{fmt(ddd['mismas_horas_que_la_fila_del_dia_del_texto'])} de ellas traen las mismas horas encendido que la fila del día que dice el texto; "
                 "en el recuento, " + "; ".join(f"{x['fecha']} tiene {fmt(x['discos_fecha'])} discos y {fmt(x['fallos_fecha'])} fallos, y {x['texto']} {fmt(x['discos_texto'])} discos" for x in ddd["recuento"]),
                 "la corrección mide si quitar ese día cambia alguna respuesta; la lectura está en pendientes", principal=True)
        for rc in reglas_candidatas:
            if rc["id"] in ("RC-04",):
                continue
            problema(P, "3.10", rc["tabla"], ", ".join(rc["columnas"]), f"{rc['id']} incumplida: {rc['detalle']}", rc["filas_que_incumplen"], None,
                     "regla candidata aprobada como comprobación", quitar, principal=True, unidad=rc["unidad"])
        problema(P, "3.10", "fotos_mensuales", HORAS, f"{fmt(esp_f.get(HORAS, {}).get('vacias_datos', 0))} filas de discos de datos sin horas encendido", esp_f.get(HORAS, {}).get("vacias_datos", 0), nf,
                 f"{fmt(esp_f.get(HORAS, {}).get('vacias_datos_capacidad_no_valida', 0))} son de capacidad no válida", "la edad sale de la primera aparición en esos discos (reglas §3)")
        problema(P, "3.10", "fallos", "dia_fallo", f"{fmt(fp['fallos_con_edad_negativa'])} fallos antes de la primera foto de su disco", fp["fallos_con_edad_negativa"], len(fallos),
                 "con la primera aparición, la edad sale negativa", "tomar la primera aparición también de las ventanas")
        problema(P, "3.10", "fallos", "serial_number", f"{fmt(fp['fallos_sin_foto'])} fallos de {fmt(fp['discos_sin_foto'])} discos que no salen en ninguna foto", fp["fallos_sin_foto"], len(fallos),
                 "sin foto no hay edad por horas en la foto del mes ni fila en el tablón de la pregunta 4", quitar, principal=True)
        problema(P, "3.10", "fotos_mensuales", "serial_number", f"{fmt(fp['discos_que_siguen_tras_su_fallo'])} discos salen en alguna foto después de su fallo", fp["discos_que_siguen_tras_su_fallo"], None,
                 "las reglas §3 lo admiten: sus días siguen contando", "ninguna en los días de disco; en la supervivencia la vida acaba en el primer fallo",
                 unidad="discos")
        problema(P, "3.10", "fotos_mensuales", "serial_number", f"{fmt(seg['huecos']['discos_datos'])} discos de datos faltan en alguna foto y vuelven", seg["huecos"]["discos_datos"], None,
                 "las reglas §3 dicen que no han desaparecido", "no contarlos como desaparecidos; los meses que faltan no son días de disco", unidad="discos")
        problema(P, "3.10", "fotos_mensuales", "contadores en bruto", f"{fmt(pares_parciales)} pares de modelo y contador con vacíos solo en parte de sus filas; suman {fmt(filas_parciales)} filas vacías",
                 pares_parciales, None, "contradicen la regla de que un contador vacío es que el modelo no lo apunta (reglas §5)",
                 "la corrección mide si cambian alguna respuesta; si cambian, preguntar cómo se lee un vacío en un modelo que sí apunta el contador",
                 unidad="pares de modelo y contador")
        problema(P, "3.10", "ventanas_fallo", "pod_slot_num", f"{fmt(slot['sin_dato_ningun_dia'])} fallos de discos de datos desde el 01/07/2023 sin ranura ningún día de su ventana",
                 slot["sin_dato_ningun_dia"], slot["fallos_datos_desde_sitio"], f"{fmt(slot['lo_recuperan_un_dia_anterior'])} más la recuperan un día anterior (reglas §5)",
                 "contarlos y decirlos en los fallos del mismo tomo (reglas §7)", unidad="fallos")
        problema(P, "3.10", "ventanas_fallo", "datacenter, vault_id, pod_slot_num", f"{fmt(tomo['sin_dato_ningun_dia'])} fallos de discos de datos desde el 01/07/2023 sin tomo completo ningún día de su ventana",
                 tomo["sin_dato_ningun_dia"], tomo["fallos_datos_desde_sitio"], f"les falta el centro, el vault o la ranura; {fmt(tomo['sin_dato_el_dia'])} no lo traen el día del fallo",
                 "contarlos y decirlos en los fallos del mismo tomo (reglas §7, población del análisis)", unidad="fallos")
        problema(P, "3.10", "ventanas_fallo", "fecha", f"{fmt(rv['sin_dia_anterior_datos'])} fallos de discos de datos sin el día anterior en su ventana", rv["sin_dia_anterior_datos"], len(fallos),
                 "el fallo sin aviso se mira el día anterior (reglas §6)", "decir cuántos fallos no tienen día anterior al contar los fallos sin aviso", unidad="fallos")
        hundidos_con_falta = [x for x in hundidos if x["faltan"] and x["faltan"] > 0]
        problema(P, "3.10", "recuento_diario", "discos", f"{fmt(len(hundidos_con_falta))} días hundidos del reconocimiento con discos de menos frente a sus vecinos",
                 len(hundidos_con_falta), None, "; ".join(f"{x['dia']} faltan {fmt(x['faltan'])}" for x in hundidos),
                 "mirar si cambian alguna tasa diaria; en tasas por trimestre o año pesan poco", unidad="días")
        for c in cruces:
            lados = LADOS_QUE_CUENTAN.get((c["izquierda"], c["derecha"]), ("izquierda", "derecha"))
            if not lados:
                continue
            extra = sum(c.get(k, 0) for k in ("claves_con_otro_numero_de_discos", "claves_con_mas_filas_que_discos", "claves_con_otro_numero_de_fallos",
                                              "casan_con_otro_modelo", "casan_con_otra_capacidad"))
            problema(P, "3.11", f"{c['izquierda']} y {c['derecha']}", ", ".join(c["clave"]),
                     f"sin pareja: {fmt(c['sin_pareja_izquierda'])} a la izquierda y {fmt(c['sin_pareja_derecha'])} a la derecha; claves que casan con otra cifra o valor: {fmt(extra)}",
                     sum(c[f"sin_pareja_{lado}"] for lado in lados) + extra, None, c.get("nota", ""),
                     "revisarlas al cruzar con integracion-datos; una clave sin pareja no es un error por sí sola", unidad="claves")

        # Pendientes: D1 a D4 están cerradas. Solo entra lo que no estaba en el plan y tiene más de una lectura legítima
        # que las reglas no fijan; la corrección mide si cambia alguna respuesta (CLAUDE.md, «Datos que no sirven o están mal»)
        pendientes = []
        if rv["date_distinta"]:
            pendientes.append({
                "id": f"P-{len(pendientes) + 1:02d}", "tabla": "ventanas_fallo y recuento_diario", "columna": "fecha, date",
                "pregunta": "¿Las filas cuya fecha no coincide con su texto son una copia del día que dice el texto, o son de su fecha con el texto mal?",
                "opciones": ["son una copia del día que dice el texto: su fecha no tiene datos propios y sus filas sobran",
                             "son de su fecha y solo el texto está mal: se quedan como están"],
                "cifra": f"{fmt(rv['date_distinta'])} filas de ventanas; {fmt(ddd['mismas_horas_que_la_fila_del_dia_del_texto'])} traen las mismas horas que la fila del día del texto",
                "nota": "no estaba en el plan; la corrección mide si quitarlas cambia alguna respuesta, y solo si cambia se lleva a la persona responsable",
                "problema": next(p["id"] for p in P if p["tabla"] == "ventanas_fallo" and p["columna"] == "fecha, date")})

        # Lo que no se aplicó y por qué
        no_aplicado = [
            {"control": "forma de la tabla (comprobaciones §1)", "motivo": "no hay periodos repartidos en columnas ni dos datos en una celda (plan aprobado)."},
            {"control": "fecha de Excel", "motivo": "ninguna fecha llega como número: vienen como fecha o como texto ISO."},
            {"control": "atípicos en códigos, notas normalizadas e identificadores", "motivo": "no son magnitudes (SKILL §3.8); la ranura, el centro, el vault, el servidor y el cluster son códigos."},
            {"control": "códigos de ausencia en las notas normalizadas", "motivo": "son notas ordinales de cada fabricante: un valor alto en el extremo es la nota sana, no una ausencia."},
            {"control": "cero como código de ausencia en los contadores en bruto", "motivo": "el cero es un valor del contador y el vacío es que el modelo no lo apunta (reglas §5)."},
            {"control": "colas, atípicos y objetivo en validación", "motivo": "en validación solo se cuentan filas, vacíos y formatos; nada se mira contra el fallo (reglas §7 y encargo)."},
            {"control": "rangos de negocio de la tabla «Lo esperable»", "motivo": "las reglas del caso no traen esa tabla."},
            {"control": "texto libre", "motivo": "no hay columnas de texto libre; el modelo y el centro se miraron por si traían algo con forma de instrucción."},
            {"control": "correlación entre variables", "motivo": "no es un bloque de la skill; las columnas calculadas a partir de otras se señalan en los riesgos para un modelo."},
            {"control": "las 66 columnas del esquema que no traen los datasets", "motivo": "se quitaron al preparar los cuatro datasets; desde aquí no se puede saber si estaban vacías o eran constantes."},
            {"control": "seguimiento de un disco día a día", "motivo": "de los discos que no fallan solo hay una foto al mes: huecos, horas y contadores que bajan tienen un mes de margen."},
        ]

        datos_personales_texto = [
            "No existe contexto-proyecto/fuentes/proteccion-datos.json: los datos no pasaron por la protección." if proteccion is None
            else "Los datos pasaron por la protección de proteccion-datos.json.",
            "No hay datos de personas (reglas §9): el paso de protección se saltó el 17/11/2026 con el sí de Juan.",
            "El número de serie identifica un disco, no a una persona. Ninguna columna es un dato personal.",
            "Esta skill no usa ni deja columnas de datos personales.",
        ]

        problemas_v = [p for p in P]
        estado = "AVISO" if (problemas_v or pendientes) else "OK"
        riesgo = "medio" if problemas_v else "bajo"
        cal.update({
            "con_diccionario": coincide,
            "ejecucion": {"python": platform.python_version(), "pandas": pd.__version__, "pyarrow": pa.__version__, "numpy": np.__version__},
            "fuente": {"tablas": fuente_tablas, "esquema": {"ruta": "data/raw/Drive_Stats_Schema_Current.csv", "bytes": (raw / "Drive_Stats_Schema_Current.csv").stat().st_size},
                       "huella_fallos": huella_antes.get("podado/fallos.parquet"), "huella_esquema": huella_antes.get("Drive_Stats_Schema_Current.csv")},
            "inspeccion": {"fotos_primera": min(x["fecha_min"] for x in pf_info), "fotos_ultima": max(x["fecha_max"] for x in pf_info),
                           "ficheros_de_fotos_con_mas_de_una_fecha": sum(1 for x in pf_info if x["fecha_min"] != x["fecha_max"]),
                           "ventanas_primera": fechas[2]["minimo"], "ventanas_ultima": fechas[2]["maximo"],
                           "dia_fallo_primero": fechas[3]["minimo"], "dia_fallo_ultimo": fechas[3]["maximo"],
                           "recuento_dias": tablas_f["recuento_diario"]["dias"], "recuento_dias_que_faltan": tablas_f["recuento_diario"]["dias_que_faltan"],
                           "ventanas_fuera": tablas_f["ventanas_fallo"]["medidas"]["filas fuera de los 30 días anteriores al fallo"],
                           "cobertura_por_fichero": [{"fichero": x["fichero"], "desde": x["fecha_min"], "hasta": x["fecha_max"]} for x in pf_info]},
            "estructura": estructura,
            "tipos_y_formatos": {"ranura_pct_no_entera": next((t["pct_no_convierte"] for t in salida["tipos"] if t["tabla"] == "fotos_mensuales" and t["columna"] == "pod_slot_num"), None),
                                 "centro_sin_tipo": acc["centro_sin_tipo"], "date_distinta": acc["date_distinta"] + rv["date_distinta"],
                                 "date_no_iso": acc["date_no_iso"] + rv["date_no_iso"],
                                 "dia_no_1": acc["dia_no_1"], "escala_con_salto": [e for e in salida["escala"] if e["salto"]]},
            "problemas": P,
            "nulos_por_segmento": salida["nulos_por_segmento"],
            "resumen_reparto": resumen_reparto,
            "codigos_de_ausencia": codigos,
            "textos_de_ausencia": textos,
            "duplicados": duplicados,
            "claves": claves,
            "escala": salida["escala"],
            "colas": salida["colas"],
            "tipos": salida["tipos"],
            "vacios_por_fila": vacios_por_fila,
            "nombres": nombres,
            "categorias_raras": raras,
            "categoricas": {"modelos_fotos": campos_dic["fotos_mensuales"]["model"]["distintos"],
                            "centros": [c for c in centros.valores if c is not None], "variantes": variantes_salida, "sin_patron": sin_patron,
                            "sin_patron_explicados": len(sin_patron) - len(sin_patron_sin_explicar),
                            "raras_fotos": sum(1 for r in raras if r["tabla"] == "fotos_mensuales" and r["columna"] == "model"),
                            "raras_centro": sum(1 for r in raras if r["tabla"] == "fotos_mensuales" and r["columna"] == "datacenter")},
            "reglas_candidatas": reglas_candidatas,
            "parametros": PARAMETROS,
            "plan_aprobado": PLAN_APROBADO,
            "decisiones_cerradas": LO_CERRADO,
            "outliers": salida["outliers"],
            "resumen_atipicos": {"magnitudes": len(salida["outliers"]),
                                 "dispersion_cero": sum(1 for o in salida["outliers"] if o["iqr"] is None and o["z_robusto"] is None),
                                 "con_marcados": sum(1 for o in salida["outliers"] if o.get("los_dos"))},
            "fechas": fechas,
            "cruces": cruces,
            "comprobaciones_reglas": comprobaciones,
            "cuestiones_reconocimiento": cuestiones,
            "contadores_por_modelo": salida["contadores_por_modelo"],
            "riesgos_modelo": riesgos,
            "instrucciones_en_texto": instrucciones,
            "datos_personales": [],
            "datos_personales_texto": datos_personales_texto,
            "no_aplicado": no_aplicado,
            "teoria": TEORIA,
            "cifras_de_control": control,
        })
        resumen = (f"Los cuatro datasets diagnosticados enteros, sin corregir nada: {fmt(len(P))} problemas para la corrección y {fmt(len(pendientes))} pendientes. "
                   f"Las cuatro lecturas del plan (D1 a D4) están cerradas; de las ocho reglas candidatas, {fmt(sum(1 for r in reglas_candidatas if r['filas_que_incumplen']))} tienen filas que las incumplen.")
        cal["resultado"] = {"estado": estado, "riesgo": riesgo, "resumen": resumen,
                            "artefactos": [ruta_json.relative_to(raiz).as_posix(), ruta_md.relative_to(raiz).as_posix()],
                            "siguiente": "correccion-datos: medir si cada problema cambia la respuesta a alguna pregunta del caso, con su encargo"}
        cal["pendientes"] = pendientes
        t0 = marca("montar el resultado", t0)

        # 14.11 Validación en código, con las huellas de después; si falla, ERROR
        huella_despues = huellas(raw)
        cal_json = a_json(cal)
        errores = validar(cal_json, huella_antes, huella_despues)
        cal["validacion"] = [{"comprobacion": n, "ok": not any(e.startswith(f"{n.split(' ')[0]}:") for e in errores)}
                             for n in ("6 vacíos con veredicto", "7 relaciones con claves sin pareja", "9 data/raw intacto", "10 escala, colas y parámetros")]
        if errores:
            raise RuntimeError("la validación del diagnóstico falla: " + " | ".join(errores[:20]))
        cal["ejecucion"]["segundos_por_parte"] = tiempos
        cal["ejecucion"]["segundos_total"] = round(time.time() - inicio, 1)
        escribir_json(cal, ruta_json)
        escribir_markdown(json.loads(ruta_json.read_text(encoding="utf-8")), ruta_md)
        print(f"calidad escrita: {ruta_json.relative_to(raiz).as_posix()} y .md; estado {estado}; {cal['ejecucion']['segundos_total']} s", flush=True)
        return cal
    except Exception as error:
        # 14.12 Si algo falla, el JSON se escribe igual con su estado (resultado.md, regla 5)
        base = {k: cal[k] for k in ("skill", "version_skill", "script", "fecha_datos", "fecha_ejecucion", "entradas")}
        base["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(error).__name__}: {error}",
                             "artefactos": [ruta_json.relative_to(raiz).as_posix()], "siguiente": "arreglar el fallo y volver a lanzar el script"}
        base["pendientes"] = []
        escribir_json(base, ruta_json)
        raise


if __name__ == "__main__":
    print("intérprete:", sys.executable, flush=True)
    main(CASO)
