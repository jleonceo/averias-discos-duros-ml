"""Análisis exploratorio del caso 68 (método analisis-exploratorio), un informe por tabla de análisis.

Describe las seis tablas de análisis de la transformación (reglas-transformacion.md §3 a §9): fotos_riesgo,
fallos_detalle, vida_discos, dias_por_tramo, modelo_trimestre y centro_mes. inicio_trimestre, dim_modelo y dim_precio_gb
no llevan informe propio: describen las otras (inicio_trimestre y las dos dimensiones, dentro de modelo_trimestre).

fotos_riesgo se lee bloque a bloque con pyarrow (un bloque es un mes) y solo con las columnas de cada cálculo: los
recuentos y las sumas se acumulan bloque a bloque; las medianas y los percentiles salen de una muestra fija de fotos con
semilla 42. El objetivo (falla_30d) solo se cruza con las fotos de construcción; de la validación solo se dan filas,
fotos con objetivo 1 y su parte, en total y por fabricante (reglas-negocio.md §7). Frente al objetivo entran los grupos
«del_modelo» y «conocidas_el_dia_de_la_foto»; el «sitio», solo desde el día en que consta; las «no_previstas», solo cuánto
vienen llenas.

Depende de scripts/05_transformacion_datos.py: lee informes/transformacion-datos.json (para si falta, si está parado o
si la huella de una tabla no es la de su salida) y las nueve tablas de data/processed/, que no modifica.

Deja, para cada tabla, informes/analisis-exploratorio__<tabla>.json y, generado de él, el .html. Si para o falla,
escribe igualmente los JSON con su estado.

Uso: python -W error scripts/06_analisis_exploratorio.py [--raiz CARPETA_DEL_CASO]
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import html
import json
import math
import platform
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
# Las piezas comunes se usan desde assets/, sin copiarlas (programacion-del-caso §1)
sys.path.insert(0, str(CASO / "assets"))
import graficos  # noqa: E402

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
METODO = "analisis-exploratorio"
VERSION_METODO = "11/11/2026"
SCRIPT = "scripts/06_analisis_exploratorio.py"
PETICION = "peticiones/10_exploratorio.md"
TRANSFORMACION = "informes/transformacion-datos.json"
CALIDAD = "informes/calidad-datos.json"
CORRECCION = "informes/correccion-datos.json"
REGLAS = "config/negocio/reglas-negocio.md"
PROTECCION = "config/fuentes/proteccion-datos.json"
CSS = CASO / "assets" / "estilo.css"

TABLAS = ["fotos_riesgo", "fallos_detalle", "vida_discos", "dias_por_tramo", "modelo_trimestre", "centro_mes"]
TODAS = ["dim_modelo", "dim_precio_gb", "fotos_riesgo", "fallos_detalle", "vida_discos", "dias_por_tramo",
         "inicio_trimestre", "modelo_trimestre", "centro_mes"]

OBJETIVO = "falla_30d"                          # reglas-transformacion §3: 1 si falla en los 30 días siguientes
PERIODO = "periodo"
CONSTRUCCION = "construcción"                   # valores de periodo del Calendario (reglas-negocio §7)
VALIDACION = "validación"
FAB = "fabricante"
CAP = "capacidad_tb"
CONTADORES = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]  # reglas, apartado 3

# Parámetros de parametros.md de el método, con su valor por defecto (ninguno lo cambian las reglas del caso)
MIN_FILAS_CATEGORIA = 30                        # §12: filas mínimas para comparar una categoría frente al objetivo
ALTA_CARDINALIDAD = 50                          # §15
MAS_FRECUENTES = 10                             # §15
TEXTO_CORTO = 3                                 # §14
LIMITE_DISCRETA = 20                            # §13: entera y con como mucho min(20, 5 % de las filas) distintos
PARTE_DISCRETA = 0.05

# Umbrales que el método no fija: elegidos antes de calcular, escritos en el JSON y en el informe (comprobaciones, intro)
SEMILLA = 42
TAM_MUESTRA = 400_000                           # fotos de la muestra fija para medianas y percentiles
TOPE_DISTINTOS = 60                             # valores distintos que se siguen por columna para tipificar
UMBRAL_DIBUJAR = 0.10                           # diferencia |2·AUC − 1| desde la que se dibuja una variable
UMBRAL_FUGA = 0.90                              # diferencia desde la que se avisa de posible fuga
FACTOR_TAMANO = 2.0                             # al separar, cambia de tamaño si la diferencia es < 1/2 o > 2 veces
UMBRAL_MEDIA_MEDIANA = 0.5                      # señal 1 de la comprobación 17, en desviaciones típicas
UMBRAL_ORDENES = 1000.0                         # señal 3: máximo entre mínimo positivo
UMBRAL_CORRELACION = 0.9                        # correlación fuerte (comprobación 7)
ANOMALIA_BAJA, ANOMALIA_ALTA = 0.8, 1.25        # serie de volumen: mes fuera de este rango frente a sus vecinos
VECINOS = 3
MOVIL_MES, MOVIL_TRIMESTRE = 3, 4

# Criterios del caso que se usan al describir (reglas-negocio §7)
MINIMO_DIAS = 50_000                            # mínimo de días de disco para comparar una tasa (ranking, §7)
MINIMO_FALLOS_EDAD = 20                         # un año de edad con menos fallos se enseña sin conclusión (cuestión 009)
FACTOR_TASA_ANUAL = 100 * 365                   # tasa anual = 100 × 365 × fallos / días de disco (§6)
VACIO = "(vacío)"
SIN_ORDENAR = ("model", "capacity_bytes")         # el modelo no se ordena aquí: su ranking es del paso 5 (petición)
MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

AVISO_EDADES = ("Comparar fabricantes o capacidades mezcla discos de edades y modelos distintos (reglas-negocio §7): "
                "la diferencia no es de la marca ni de la capacidad.")

TEORIA = [
    "34.1 y 34.2, qué es y el esquema: cada columna se tipifica por su papel y cada análisis es una función que se "
    "aplica a todo el bloque.",
    "3.1, descriptiva: el informe describe estos datos y no extrapola; no se dan intervalos ni contrastes.",
    "34.3, 34.4, 3.5 y 3.6: frecuencias y cardinalidad en las categóricas; describe con la mediana al lado y la tabla "
    "leída con sus cuatro señales en las numéricas.",
    "34.5, 34.6 y 10.6: barras para categóricas y discretas, histograma para continuas, sin cajas; la escala "
    "logarítmica se dice en el eje.",
    "34.7 y 13.14: el cruce con el objetivo solo con la construcción; describe y no elige variables.",
    "5.4, 5.5 y 5.6: cada tasa con su base, la tasa de un grupo como suma entre suma y cada comparación repetida por "
    "fabricante y capacidad, por si se invierte (paradoja de Simpson).",
    "34.8, 34.9 y 34.10: hallazgo, alerta, anomalía e hipótesis separados; Pareto, ABC y series de negocio.",
]


class Parar(Exception):
    """Una regla del exploratorio pide parar: el JSON queda en PARADO."""


# =================================================================================================================
# 3. Utilidades
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leída por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 22), b""):
            h.update(trozo)
    return h.hexdigest()


def limpio(x):
    """Pasa a tipos de JSON: los números de numpy a Python, los vacíos y NaN a None y las fechas a ISO."""
    if isinstance(x, dict):
        return {str(k): limpio(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [limpio(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, (pd.Timestamp, dt.date, np.datetime64)):
        return None if pd.isna(x) else pd.Timestamp(x).strftime("%Y-%m-%d")
    if x is pd.NA or x is pd.NaT:
        return None
    return x


def clave(v):
    """Valor de una categoría como clave estable: el vacío como «(vacío)», números de numpy a Python."""
    if v is None or v is pd.NA or v is pd.NaT:
        return VACIO
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return VACIO if not math.isfinite(float(v)) else float(v)
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    return str(v)


def r(x, d=6):
    """Redondea un número para el JSON, o deja None."""
    return None if x is None or not math.isfinite(float(x)) else round(float(x), d)


def es_valor(s, valor):
    """1 donde la columna vale `valor` y 0 en lo demás; el vacío cuenta como no (sirve con bool, boolean y object)."""
    return s.eq(valor).fillna(False).astype(int)


def parte(num, den):
    """Porcentaje num / den, o None si el denominador es cero."""
    return None if not den else 100.0 * num / den


def tasa_anual(fallos, dias):
    """Tasa anual de fallo en %: 100 × 365 × fallos / días de disco (reglas-negocio §6)."""
    return None if not dias or dias <= 0 else FACTOR_TASA_ANUAL * fallos / dias


def f(x, dec=0, unidad=""):
    """Número a la española para el texto, o «sin dato»."""
    return "sin dato" if x is None else graficos.numero(x, dec, unidad)


def fp(x, dec=2):
    """Porcentaje a la española con su signo, o «sin dato»."""
    return "sin dato" if x is None else graficos.numero(x, dec, " %")


def et(v):
    """Etiqueta de una categoría para leer: un decimal entero sin «.0» (4.0 -> «4»)."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    t = str(v)
    return t[:-2] if t.endswith(".0") and t[:-2].lstrip("-").isdigit() else t


def nombre_mes(fecha):
    """«ene 2020» a partir de una fecha (los meses, con su nombre: comprobación 10)."""
    t = pd.Timestamp(fecha)
    return f"{MESES_ES[t.month - 1]} {t.year}"


def fin_de_periodo(inicio, frecuencia):
    """Último día del mes o del trimestre que empieza en `inicio`."""
    t = pd.Timestamp(inicio)
    meses = 1 if frecuencia == "mes" else 3
    return t + pd.DateOffset(months=meses) - pd.Timedelta(days=1)


def ano_completo(ano, fecha_datos):
    """Un año es completo si su 31 de diciembre no pasa de la fecha de los datos (reglas-negocio §5)."""
    return pd.Timestamp(year=int(ano), month=12, day=31) <= fecha_datos


def leer_json(ruta):
    """Lee un JSON en UTF-8, o None si no existe."""
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


# =================================================================================================================
# 4. Descripción de una tabla que cabe en memoria
# =================================================================================================================
def es_booleana(s):
    """Cierto si los valores no vacíos son todos verdadero o falso."""
    if pd.api.types.is_bool_dtype(s):
        return True
    v = s.dropna()
    return len(v) > 0 and s.dtype == object and all(isinstance(x, (bool, np.bool_)) for x in v.head(1000))


def tipo_de(s, rol, filas):
    """Tipifica una columna (§2 y comprobación 13): papel fijo, booleana, fecha, numérica discreta o continua, texto."""
    if rol:
        return rol, None, None
    if es_booleana(s):
        return "booleana", int(s.nunique(dropna=True)), None
    if pd.api.types.is_datetime64_any_dtype(s):
        return "fecha", None, None
    if pd.api.types.is_numeric_dtype(s):
        v = s.dropna().to_numpy(dtype=float)
        distintos = int(len(np.unique(v)))
        entera = bool(len(v) and np.all(v == np.floor(v)))
        limite = min(LIMITE_DISCRETA, PARTE_DISCRETA * filas)
        return ("discreta" if entera and distintos <= limite else "continua"), distintos, entera
    distintos = int(s.nunique(dropna=True))
    return ("alta_cardinalidad" if distintos > ALTA_CARDINALIDAD else "categorica"), distintos, None


def senales(media, mediana, desv, p25, p75, minimo, maximo, distintos):
    """Las cuatro señales de la tabla de estadísticos (comprobación 17), calculadas con los umbrales fijados."""
    out = []
    if desv and desv > 0 and mediana is not None and abs(media - mediana) / desv > UMBRAL_MEDIA_MEDIANA:
        out.append("media lejos de la mediana")
    if p25 is not None and p75 is not None and p25 == p75 and (distintos is None or distintos > 2):
        out.append(f"cuartiles 25 y 75 iguales, en {f(p25, 2)}")
    if minimo is not None and minimo > 0 and maximo / minimo >= UMBRAL_ORDENES:
        out.append("mínimo y máximo de órdenes de magnitud distintos")
    if distintos == 2:
        out.append("binaria entre las numéricas")
    return out


def bins_histograma(v):
    """Tramos y cuentas de un histograma, guardados en el JSON para que el gráfico salga de él.

    Si más de la mitad de los valores son cero, se dibujan solo los positivos en escala logarítmica, y se dice la parte
    de ceros.
    """
    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return None
    ceros = float(np.mean(v == 0))
    solo_positivos = bool(v.min() >= 0 and ceros > 0.5)
    datos = v[v > 0] if solo_positivos else v
    if len(datos) == 0:
        return {"bordes": None, "cuentas": None, "log": False, "solo_positivos": True, "parte_ceros_pct": 100.0,
                "n": int(len(v))}
    menor, mayor = float(datos.min()), float(datos.max())
    log = bool(solo_positivos and menor > 0 and mayor / menor >= 100) or bool(menor > 0 and mayor / menor >= 1e4)
    if menor == mayor:
        bordes = np.array([menor - 0.5, mayor + 0.5])
        log = False
    elif log:
        bordes = np.logspace(math.log10(menor), math.log10(mayor), 13)
    else:
        bordes = np.linspace(menor, mayor, 13)
    cuentas, _ = np.histogram(datos, bins=bordes)
    return {"bordes": [float(b) for b in bordes], "cuentas": [int(c) for c in cuentas], "log": log,
            "solo_positivos": solo_positivos, "parte_ceros_pct": r(100 * ceros, 4), "n": int(len(datos))}


def estadisticos(s):
    """Conteo, vacíos, media, mediana, desviación, extremos y percentiles de una serie numérica."""
    v = pd.to_numeric(s, errors="coerce").astype(float)
    q = v.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]) if v.notna().any() else None
    val = lambda k: None if q is None else r(q.loc[k])
    return {"conteo": int(v.notna().sum()), "nulos": int(v.isna().sum()), "media": r(v.mean()),
            "mediana": val(0.5), "desviacion": r(v.std()), "minimo": r(v.min()), "maximo": r(v.max()),
            "p01": val(0.01), "p05": val(0.05), "p25": val(0.25), "p75": val(0.75), "p95": val(0.95),
            "p99": val(0.99)}


def frecuencias(s, n_max=15):
    """Frecuencias de una categórica, con el vacío como una fila más: cardinalidad, dominante y las más frecuentes."""
    vc = s.value_counts(dropna=False)
    total = int(vc.sum())
    filas = [{"valor": clave(k), "filas": int(n), "pct": r(parte(n, total), 4)} for k, n in vc.items()]
    filas.sort(key=lambda x: -x["filas"])
    top10 = sum(x["filas"] for x in filas[:MAS_FRECUENTES])
    return {"cardinalidad": int(s.nunique(dropna=True)), "nulos": int(s.isna().sum()),
            "dominante": filas[0]["valor"] if filas else None, "pct_dominante": filas[0]["pct"] if filas else None,
            "pct_10_mas_frecuentes": r(parte(top10, total), 4), "frecuencias": filas[:n_max], "total": total}


def describir(df, spec):
    """Tipificación, numéricas, categóricas y fechas de una tabla pequeña, con sus gráficos (§2, §3 y §4)."""
    tip, num, cat, fechas, graf = [], [], [], [], []
    roles = {}
    for rol in ("identificador", "fecha", "temporal", "codigo"):
        for c in spec.get(rol, []):
            roles[c] = rol
    for c in df.columns:
        base, nivel = df, "fila"
        for claves_nivel, cols in spec.get("niveles", []):
            if c in cols:
                base, nivel = df.drop_duplicates(claves_nivel), "+".join(claves_nivel)
        s = base[c]
        tipo, distintos, entera = tipo_de(s, roles.get(c), len(base))
        tip.append({"columna": c, "tipo": tipo, "nivel": nivel, "distintos": distintos, "entera": entera,
                    "filas_del_nivel": int(len(base))})
        if tipo in ("continua", "discreta"):
            e = estadisticos(s)
            e.update({"columna": c, "tipo": tipo, "nivel": nivel, "base": f"{f(len(base))} filas ({nivel})"})
            e["senales"] = senales(e["media"], e["mediana"], e["desviacion"], e["p25"], e["p75"], e["minimo"],
                                   e["maximo"], distintos)
            num.append(e)
            if tipo == "continua" and e["conteo"]:
                h = bins_histograma(s.dropna().to_numpy(dtype=float))
                if h and h["bordes"]:
                    graf.append(grafico_histograma(c, e, h, nivel))
        if tipo in ("discreta", "categorica", "alta_cardinalidad", "booleana", "codigo"):
            fr = frecuencias(s)
            fr.update({"columna": c, "tipo": tipo, "nivel": nivel})
            cat.append(fr)
            if tipo != "codigo" and fr["total"]:
                graf.append(grafico_frecuencias(c, fr, tipo, nivel))
        if tipo == "fecha":
            v = pd.to_datetime(s)
            fechas.append({"columna": c, "minimo": limpio(v.min()), "maximo": limpio(v.max()),
                           "nulos": int(v.isna().sum())})
    return {"tipificacion": tip, "numericas": num, "categoricas": cat, "fechas": fechas, "graficos": graf}


def grafico_histograma(c, e, h, nivel, base_texto=None):
    """Especificación de un histograma: título calculado del dato y tramos del JSON."""
    extra = f"; el {f(h['parte_ceros_pct'], 1)} % vale cero y se dibujan los positivos" if h["solo_positivos"] else ""
    return {"id": f"num-{c}", "seccion": "numericas", "tipo": "histograma",
            "titulo": f"{c}: mediana {f(e['mediana'], 2)} y media {f(e['media'], 2)}",
            "subtitulo": f"Cuántas filas caen en cada tramo{extra}",
            "fuente": base_texto or f"{f(h['n'])} valores, uno por {nivel}",
            "datos": {"bordes": h["bordes"], "cuentas": h["cuentas"], "log": h["log"], "etiqueta_x": c}}


def grafico_frecuencias(c, fr, tipo, nivel):
    """Especificación de unas barras de frecuencia: las más frecuentes, con su recuento."""
    filas = fr["frecuencias"]
    if tipo == "discreta":
        filas = sorted(filas, key=lambda x: (x["valor"] == VACIO, x["valor"] if x["valor"] != VACIO else 0))
    return {"id": f"cat-{c}", "seccion": "categoricas", "tipo": "barras",
            "titulo": f"{c}: «{et(fr['dominante'])}» reúne el {f(fr['pct_dominante'], 1)} % de las filas",
            "subtitulo": f"Filas de cada valor ({'los 15 más frecuentes de ' if fr['cardinalidad'] > 15 else ''}"
                         f"{f(fr['cardinalidad'])} valores)",
            "fuente": f"{f(fr['total'])} filas, una por {nivel}",
            "datos": {"etiquetas": [et(x["valor"]) for x in filas], "series": {"filas": [x["filas"] for x in filas]},
                      "decimales": 0, "ordenar": tipo != "discreta"}}


# =================================================================================================================
# 5. Tasas por grupo y la vista al separar por fabricante y por capacidad (método, apartado 5)
# =================================================================================================================
def medida_por(df, dim, num, den, factor, minimo):
    """Una fila por categoría de `dim`: numerador, denominador, la medida (factor × num / den) y si se compara."""
    if df.empty:
        return []
    g = df.groupby(dim, dropna=False, sort=False)[[num, den]].sum()
    out = []
    for cat, (n, d) in zip(g.index, g.to_numpy()):
        out.append({"categoria": clave(cat), "num": float(n), "den": float(d),
                    "valor": None if not d or d < minimo else factor * float(n) / float(d),
                    "comparada": bool(d >= minimo)})
    return out


def separar(df, dim, num, den, factor, minimo, grupos=(FAB, CAP), orden=None):
    """La medida por `dim`, en total y dentro de cada fabricante y cada capacidad, con las alertas al separar.

    Se comparan dos categorías del total: con `orden` (periodos), la primera y la última de la lista; sin él, la más
    alta y la más baja. Al separar, es alerta si la diferencia cambia de signo (se invierte) o si queda por debajo de
    la mitad o por encima del doble (cambia de tamaño). Una dimensión anidada en el grupo (cada categoría en un solo
    grupo) no se separa: no cambia nada.
    """
    total = medida_por(df, dim, num, den, factor, minimo)
    elegibles = {x["categoria"]: x["valor"] for x in total if x["comparada"]}
    if orden is not None:
        lista = [c for c in orden if c in elegibles]
        par = (lista[-1], lista[0]) if len(lista) >= 2 else None
    else:
        lista = sorted(elegibles, key=lambda c: elegibles[c])
        par = (lista[-1], lista[0]) if len(lista) >= 2 else None
    res = {"dimension": dim, "medida": {"numerador": num, "denominador": den, "factor": factor, "minimo": minimo},
           "total": total, "par": list(par) if par else None, "por_grupo": {}, "anidada": [], "alertas": []}
    for g in grupos:
        if g == dim or g not in df.columns:
            continue
        por_cat = df.groupby(dim, dropna=False)[g].nunique(dropna=False)
        if len(por_cat) and int(por_cat.max()) <= 1:
            res["anidada"].append(g)
            continue
        vista = {}
        for valor, sub in df.groupby(g, dropna=False, sort=True):
            vista[str(clave(valor))] = medida_por(sub, dim, num, den, factor, minimo)
        res["por_grupo"][g] = vista
        if not par:
            continue
        d_total = elegibles[par[0]] - elegibles[par[1]]
        for valor, filas in vista.items():
            v = {x["categoria"]: x["valor"] for x in filas if x["comparada"]}
            if par[0] not in v or par[1] not in v or d_total == 0:
                continue
            d = v[par[0]] - v[par[1]]
            tipo = None
            if d * d_total < 0:
                tipo = "se invierte"
            elif abs(d) < abs(d_total) / FACTOR_TAMANO or abs(d) > abs(d_total) * FACTOR_TAMANO:
                tipo = "cambia de tamaño"
            if tipo:
                res["alertas"].append({"grupo_dim": g, "grupo": valor, "a": par[0], "b": par[1],
                                       "diferencia_total": r(d_total), "diferencia_grupo": r(d), "tipo": tipo})
    return res


def separar_total(df, num, den, factor, minimo, grupos=(FAB, CAP)):
    """Una medida total y la misma en cada grupo: es alerta si un grupo queda por debajo de la mitad o por encima del doble."""
    n, d = float(df[num].sum()), float(df[den].sum())
    total = None if not d else factor * n / d
    res = {"total": {"num": n, "den": d, "valor": total}, "por_grupo": {}, "alertas": []}
    for g in grupos:
        if g not in df.columns:
            continue
        filas = medida_por(df, g, num, den, factor, minimo)
        res["por_grupo"][g] = filas
        for x in filas:
            if x["comparada"] and total and x["valor"] is not None and (
                    x["valor"] < total / FACTOR_TAMANO or x["valor"] > total * FACTOR_TAMANO):
                res["alertas"].append({"grupo_dim": g, "grupo": x["categoria"], "valor": r(x["valor"]),
                                       "total": r(total), "tipo": "cambia de tamaño"})
    return res


def texto_alertas_separar(nombre, sep, unidad):
    """Una línea por cada cambio al separar, para la lista de alertas."""
    out = []
    for a in sep["alertas"]:
        if "a" in a:
            out.append(f"{nombre}: la diferencia entre {et(a['a'])} y {et(a['b'])} es de {f(a['diferencia_total'], 2)} "
                       f"{unidad} en el total y de {f(a['diferencia_grupo'], 2)} dentro de {a['grupo_dim']} = "
                       f"{et(a['grupo'])}: {a['tipo']}.")
        else:
            out.append(f"{nombre}: {f(a['valor'], 2)} {unidad} en {a['grupo_dim']} = {a['grupo']}, frente a "
                       f"{f(a['total'], 2)} en el total: {a['tipo']}.")
    return out


# =================================================================================================================
# 6. Series de negocio, Pareto y anomalías (comprobaciones 1, 2 y 11)
# =================================================================================================================
def ajuste(y, log=False):
    """Pendiente y R² de una recta sobre el índice del periodo (en logaritmos si `log`)."""
    y = np.asarray(y, dtype=float)
    if len(y) < 3 or (log and np.any(y <= 0)):
        return None, None
    yy = np.log(y) if log else y
    x = np.arange(len(yy), dtype=float)
    pend, corte = np.polyfit(x, yy, 1)
    sst = float(np.sum((yy - yy.mean()) ** 2))
    r2 = None if sst == 0 else 1 - float(np.sum((yy - (pend * x + corte)) ** 2)) / sst
    return float(pend), r2


def serie_negocio(fechas, valores, completos, frecuencia, tipo):
    """Media móvil, variación, interanual, estacionalidad, tendencias y CAGR, solo con los periodos completos."""
    s = pd.Series([float(v) for v in valores], index=pd.to_datetime(fechas))
    s = s[np.asarray(completos, dtype=bool)]
    por_ano = 12 if frecuencia == "mes" else 4
    ventana = MOVIL_MES if frecuencia == "mes" else MOVIL_TRIMESTRE
    out = {"frecuencia": frecuencia, "tipo": tipo, "periodos": int(len(s)), "ventana_movil": ventana,
           "fuera": int(len(completos) - len(s))}
    if len(s) < 2:
        out["motivo"] = "menos de dos periodos completos"
        return out
    movil = s.rolling(ventana).mean()
    var = (s / s.shift(1) - 1) * 100
    inter = (s / s.shift(por_ano) - 1) * 100 if len(s) > por_ano else None
    out["detalle"] = [{"periodo": k.strftime("%Y-%m-%d"), "valor": r(v), "movil": r(movil.loc[k]),
                       "var_anterior_pct": r(var.loc[k], 4),
                       "interanual_pct": None if inter is None else r(inter.loc[k], 4)} for k, v in s.items()]
    anos = s.groupby(s.index.year).agg(["sum", "mean", "size"])
    llenos = anos.loc[anos["size"] == por_ano]
    out["anos_completos"] = [int(a) for a in llenos.index]
    if len(llenos) >= 2:
        pos = s.index.month if frecuencia == "mes" else s.index.quarter
        dentro = s[np.isin(s.index.year, llenos.index)]
        est = dentro.groupby(pos[np.isin(s.index.year, llenos.index)]).mean()
        out["estacionalidad"] = [{"posicion": int(k), "media": r(v)} for k, v in est.items()]
        agregado = llenos["sum"] if tipo == "flujo" else llenos["mean"]
        ini, fin = float(agregado.iloc[0]), float(agregado.iloc[-1])
        anos_n = int(agregado.index[-1] - agregado.index[0])
        out["cagr_pct"] = r(100 * ((fin / ini) ** (1 / anos_n) - 1), 4) if ini > 0 and anos_n > 0 else None
        out["cagr_base"] = {"desde": int(agregado.index[0]), "hasta": int(agregado.index[-1]),
                            "agregado": "suma" if tipo == "flujo" else "media"}
    else:
        out["estacionalidad"] = None
        out["cagr_pct"] = None
        out["motivo_cagr"] = "menos de dos años completos"
    pend, r2 = ajuste(s.to_numpy())
    pend_l, r2_l = ajuste(s.to_numpy(), log=True)
    out["tendencia_lineal"] = {"pendiente_por_periodo": r(pend), "r2": r(r2, 4)}
    out["tendencia_exponencial"] = {"crecimiento_por_periodo_pct": None if pend_l is None else r(100 * (math.exp(pend_l) - 1), 4),
                                    "r2": r(r2_l, 4)}
    return out


def anomalias(fechas, valores, nombre):
    """Periodos de una serie de volumen fuera de 0,8 a 1,25 veces la mediana de sus vecinos (anomalía concentrada)."""
    v = pd.Series([float(x) for x in valores], index=pd.to_datetime(fechas))
    a = v.to_numpy()
    out = []
    for i, (k, x) in enumerate(v.items()):
        vec = np.concatenate([a[max(0, i - VECINOS):i], a[i + 1:i + 1 + VECINOS]])
        if len(vec) < 2:
            continue
        med = float(np.median(vec))
        if med > 0 and not (ANOMALIA_BAJA <= x / med <= ANOMALIA_ALTA):
            out.append({"serie": nombre, "periodo": k.strftime("%Y-%m-%d"), "valor": r(x), "mediana_vecinos": r(med),
                        "razon": r(x / med, 4), "parte_del_total_pct": r(parte(x, float(v.sum())), 4)})
    return out


def pareto(valores, elemento, magnitud):
    """Concentración de una magnitud por elemento: parte de elementos que suma el 80 % y clases A, B y C."""
    s = pd.Series({clave(k): float(v) for k, v in valores.items()}).sort_values(ascending=False, kind="mergesort")
    n = len(s)
    out = {"pareja": f"{magnitud} por {elemento}", "elemento": elemento, "magnitud": magnitud, "elementos": n,
           "total": r(float(s.sum()))}
    if n == 0 or s.sum() <= 0:
        out["motivo"] = "sin total positivo"
        return out
    if (s < 0).any():
        out["negativos"] = {"elementos": int((s < 0).sum()), "restan": r(float(s[s < 0].sum()))}
        out["motivo"] = "hay valores negativos: no se dibuja la curva"
        return out
    acum = s.cumsum() / s.sum() * 100
    k80 = int(np.searchsorted(acum.to_numpy(), 80.0 - 1e-9) + 1)
    out["pct_elementos_80"] = r(100 * k80 / n, 4)
    clase = np.where(acum.shift(fill_value=0) < 80, "A", np.where(acum.shift(fill_value=0) < 95, "B", "C"))
    out["clases"] = {c: {"elementos": int((clase == c).sum()), "parte_pct": r(float(s[clase == c].sum() / s.sum() * 100), 4)}
                     for c in ("A", "B", "C")}
    out["tabla"] = [{"elemento": k, "valor": r(v), "acumulado_pct": r(a, 4), "clase": c}
                    for (k, v), a, c in zip(s.items(), acum.to_numpy(), clase)]
    out["valores_ordenados"] = [r(v) for v in s.to_numpy()]
    out["pocos_elementos"] = bool(n < 10)
    return out


# =================================================================================================================
# 7. fotos_riesgo, bloque a bloque
# =================================================================================================================
def tipo_arrow(t):
    """Tipo de una columna según su tipo de Arrow: numérica, booleana, texto, fecha."""
    if pa.types.is_boolean(t):
        return "bool"
    if pa.types.is_integer(t) or pa.types.is_floating(t):
        return "num"
    if pa.types.is_timestamp(t) or pa.types.is_date(t):
        return "fecha"
    return "texto"


def sumar(acc, k, a, b=0):
    """Suma dos recuentos en un acumulador de pares."""
    x = acc.get(k)
    acc[k] = (a, b) if x is None else (x[0] + a, x[1] + b)


def combinar_momentos(m, v):
    """Combina conteo, media y M2 de un bloque con los acumulados (fórmula de Chan): media y desviación exactas."""
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return m
    n_b, media_b = len(v), float(v.mean())
    m2_b = float(((v - media_b) ** 2).sum())
    if m is None:
        return [n_b, media_b, m2_b, float(v.min()), float(v.max())]
    n, media, m2, mn, mx = m
    tot = n + n_b
    delta = media_b - media
    return [tot, media + delta * n_b / tot, m2 + m2_b + delta ** 2 * n * n_b / tot, min(mn, v.min()), max(mx, v.max())]


def agrupar_conteos(df, col, otras, valor=None):
    """Recuento (y suma de `valor`) por `col` y las columnas `otras`, sin repetir una columna en la clave."""
    claves = [col] + [o for o in otras if o != col]
    g = df.groupby(claves, dropna=False, sort=False)
    if valor is None:
        res = g.size()
        filas = [(k if isinstance(k, tuple) else (k,), int(n), 0) for k, n in res.items()]
    else:
        res = g[valor].agg(["size", "sum"])
        filas = [(k if isinstance(k, tuple) else (k,), int(a), int(b)) for k, (a, b) in zip(res.index, res.to_numpy())]
    out = []
    for k, a, b in filas:
        d = dict(zip(claves, k))
        out.append((tuple(clave(d[c]) for c in [col] + list(otras)), a, b))
    return out


def auc_rangos(x1, x0):
    """Área bajo la curva ROC de una variable sola (Mann-Whitney con rangos medios); None sin las dos clases."""
    n1, n0 = len(x1), len(x0)
    if n1 == 0 or n0 == 0:
        return None
    rg = pd.Series(np.concatenate([x1, x0])).rank(method="average").to_numpy()
    return float((rg[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def auc_categorias(cats):
    """AUC de una categórica: las categorías comparadas, ordenadas por su parte, como puntuación."""
    usadas = sorted([c for c in cats if c["comparada"]], key=lambda c: c["parte_pct"])
    n1 = sum(c["fallan"] for c in usadas)
    n0 = sum(c["filas"] - c["fallan"] for c in usadas)
    if n1 == 0 or n0 == 0:
        return None
    acum0, s = 0, 0.0
    i = 0
    while i < len(usadas):
        j = i
        while j < len(usadas) and usadas[j]["parte_pct"] == usadas[i]["parte_pct"]:
            j += 1
        g1 = sum(c["fallan"] for c in usadas[i:j])
        g0 = sum(c["filas"] - c["fallan"] for c in usadas[i:j])
        s += g1 * (acum0 + 0.5 * g0)
        acum0 += g0
        i = j
    return s / (n1 * n0)


def categorias_objetivo(acc_col):
    """Fotos, fotos que fallan y su parte por categoría, a partir del acumulado por categoría, fabricante y capacidad."""
    tot = {}
    for (v, _, _), (a, b) in acc_col.items():
        sumar(tot, v, a, b)
    out = []
    for v, (a, b) in tot.items():
        comp = a >= MIN_FILAS_CATEGORIA
        out.append({"valor": v, "filas": a, "fallan": b, "parte_pct": r(parte(b, a), 6) if comp else None,
                    "comparada": comp})
    out.sort(key=lambda c: -c["filas"])
    return out


def df_acumulado(acc_col):
    """El acumulado de una variable como tabla: valor, fabricante, capacidad, fotos y fotos que fallan."""
    return pd.DataFrame([{"valor": v, FAB: fb, CAP: cp, "fotos": a, "fallan": b}
                         for (v, fb, cp), (a, b) in acc_col.items()],
                        columns=["valor", FAB, CAP, "fotos", "fallan"])


def analizar_fotos(raiz, tj, ctx):
    """El exploratorio de fotos_riesgo, leído bloque a bloque: devuelve el diccionario del informe."""
    t0 = time.time()
    ruta = raiz / "data" / "processed" / "fotos_riesgo.parquet"
    pf = pq.ParquetFile(ruta)
    md = pf.metadata
    esquema = pf.schema_arrow
    grupos = tj["grupos_fotos_riesgo"]
    columnas = list(esquema.names)
    sin_grupo = [c for c in columnas if not any(c in v for v in grupos.values())]
    ident, del_modelo, conocidas = grupos["identificacion_y_fecha"], grupos["del_modelo"], grupos["conocidas_el_dia_de_la_foto"]
    sitio, no_prev = grupos.get("sitio", []), grupos.get("no_previstas", [])
    variables = [c for c in del_modelo + conocidas if c in columnas]
    sitio = [c for c in sitio if c in columnas]
    tipos = {c: tipo_arrow(esquema.field(c).type) for c in columnas}
    numericas = [c for c in variables if tipos[c] == "num"]
    leer = list(dict.fromkeys(ident + variables + sitio + [PERIODO, OBJETIVO]))
    total = md.num_rows
    desde_c = pd.Timestamp(tj["particion"]["desarrollo"]["desde"])
    hasta_c = pd.Timestamp(tj["particion"]["desarrollo"]["hasta"])
    desde_v = pd.Timestamp(tj["particion"]["validacion"]["desde"])
    hasta_v = pd.Timestamp(tj["particion"]["validacion"]["hasta"])
    inicio_sitio = ctx["inicio_sitio"]

    # La muestra fija: posiciones al azar con semilla 42, repartidas en los bloques
    rng = np.random.default_rng(SEMILLA)
    n_muestra = min(TAM_MUESTRA, total)
    idx = np.sort(rng.choice(total, size=n_muestra, replace=False))

    momentos = {c: None for c in numericas}
    distintos = {c: set() for c in variables + sitio if tipos[c] in ("num", "bool")}
    entera = {c: True for c in numericas}
    uni = {c: {} for c in variables + sitio}            # (valor, periodo) -> fotos, todas las filas
    cruce = {c: {} for c in variables}                   # (valor, fabricante, capacidad) -> fotos, fallan; construcción
    cruce_sitio = {c: {} for c in sitio}                 # lo mismo, construcción desde que consta el sitio
    por_mes = {}                                         # (mes, fabricante, periodo) -> fotos; todas las filas
    cons_mes_fab, cons_mes_cap = {}, {}                  # (mes, grupo) -> fotos, fallan; construcción
    val_fab = {}                                         # fabricante -> fotos, fallan; validación (solo totales)
    llenos, filas_mf = {}, {}                            # (mes, fabricante, columna) -> llenos; (mes, fab) -> filas
    series_serial = set()
    num_y_cap = list(dict.fromkeys(numericas + [CAP]))
    muestra = {c: [] for c in num_y_cap + [FAB, PERIODO, OBJETIVO]}
    positivos = {c: [] for c in num_y_cap + [FAB]}
    n_sitio = 0
    inicio = 0
    for i in range(md.num_row_groups):
        # Lectura del bloque con las columnas del análisis; el resto de columnas, solo para contar lo lleno
        df = pf.read_row_group(i, columns=leer).to_pandas()
        nb = len(df)
        per = df[PERIODO].astype(object).to_numpy()
        es_c, es_v = per == CONSTRUCCION, per == VALIDACION
        if np.any(~(es_c | es_v)):
            raise Parar(f"el bloque {i} trae valores de periodo que no son construcción ni validación")
        fecha = pd.to_datetime(df["fecha"])
        if ((fecha[es_c] < desde_c) | (fecha[es_c] > hasta_c)).any() or (
                (fecha[es_v] < desde_v) | (fecha[es_v] > hasta_v)).any():
            raise Parar(f"el bloque {i} tiene fotos cuyo periodo no casa con las fechas de la partición")
        df["_mes"] = fecha.to_numpy().astype("datetime64[M]").astype("datetime64[s]")
        series_serial.update(df["serial_number"].astype(object).tolist())

        # Momentos exactos y valores distintos (para tipificar sin tener la tabla entera)
        for c in numericas:
            v = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
            momentos[c] = combinar_momentos(momentos[c], v)
            vv = v[np.isfinite(v)]
            if entera[c] and len(vv) and not np.all(vv == np.floor(vv)):
                entera[c] = False
        for c in list(distintos):
            if distintos[c] is not None:
                distintos[c].update(clave(x) for x in pd.unique(df[c].dropna()))
                if len(distintos[c]) > TOPE_DISTINTOS:
                    distintos[c] = None
        contables = [c for c in variables + sitio if tipos[c] == "texto" or c in sitio
                     or (c in distintos and distintos[c] is not None)]
        for c in list(uni):
            if c not in contables:
                uni.pop(c, None)
                cruce.pop(c, None)

        # Fotos por mes y fabricante (sin el objetivo) y frecuencias de cada categórica, en todas las filas
        for k, a, _ in agrupar_conteos(df, "_mes", [FAB, PERIODO]):
            sumar(por_mes, k, a)
        for c in uni:
            for k, a, _ in agrupar_conteos(df, c, [PERIODO]):
                sumar(uni[c], k, a)

        # El objetivo, solo con las fotos de construcción
        dc = df.loc[es_c]
        if len(dc):
            for c in cruce:
                for k, a, b in agrupar_conteos(dc, c, [FAB, CAP], OBJETIVO):
                    sumar(cruce[c], k, a, b)
            for k, a, b in agrupar_conteos(dc, "_mes", [FAB], OBJETIVO):
                sumar(cons_mes_fab, k, a, b)
            for k, a, b in agrupar_conteos(dc, "_mes", [CAP], OBJETIVO):
                sumar(cons_mes_cap, k, a, b)
            ds = dc.loc[pd.to_datetime(dc["fecha"]) >= inicio_sitio]
            n_sitio += len(ds)
            if len(ds):
                for c in cruce_sitio:
                    for k, a, b in agrupar_conteos(ds, c, [FAB, CAP], OBJETIVO):
                        sumar(cruce_sitio[c], k, a, b)
            pos = dc.loc[dc[OBJETIVO] == 1]
            for c in positivos:
                positivos[c].append(pos[c].to_numpy(dtype=float, na_value=np.nan) if c in num_y_cap
                                    else pos[c].astype(object).to_numpy())

        # De la validación, solo filas y fotos con objetivo 1 por fabricante
        dv = df.loc[es_v, [FAB, OBJETIVO]]
        if len(dv):
            for k, a, b in agrupar_conteos(dv, FAB, [], OBJETIVO):
                sumar(val_fab, k[0], a, b)

        # La muestra fija; el objetivo de una foto de validación no entra en ella
        local = idx[(idx >= inicio) & (idx < inicio + nb)] - inicio
        if len(local):
            m = df.iloc[local]
            for c in num_y_cap:
                muestra[c].append(m[c].to_numpy(dtype=float, na_value=np.nan))
            muestra[FAB].append(m[FAB].astype(object).to_numpy())
            muestra[PERIODO].append(m[PERIODO].astype(object).to_numpy())
            obj = m[OBJETIVO].to_numpy(dtype=float, na_value=np.nan)
            muestra[OBJETIVO].append(np.where(m[PERIODO].astype(object).to_numpy() == CONSTRUCCION, obj, np.nan))

        # Lo lleno de todas las columnas, por mes y fabricante, leyendo las columnas por trozos
        mes_cod, meses_u = pd.factorize(df["_mes"])
        fab_cod, fabs_u = pd.factorize(df[FAB].astype(object), use_na_sentinel=False)
        cod = mes_cod * len(fabs_u) + fab_cod
        k_tot = len(meses_u) * len(fabs_u)
        n_por = np.bincount(cod, minlength=k_tot)
        pares = [(meses_u[j // len(fabs_u)], clave(fabs_u[j % len(fabs_u)])) for j in range(k_tot)]
        for (m_, f_), n_ in zip(pares, n_por):
            sumar(filas_mf, (clave(m_), f_), int(n_))
        resto = [c for c in columnas if c not in (FAB,)]
        for j in range(0, len(resto), 24):
            trozo = pf.read_row_group(i, columns=resto[j:j + 24])
            for c in trozo.column_names:
                a = trozo[c]
                valido = pc.is_valid(a)
                if pa.types.is_floating(a.type):
                    valido = pc.and_(valido, pc.invert(pc.fill_null(pc.is_nan(a), False)))
                w = np.asarray(valido.to_numpy(), dtype=np.float64)
                cuenta = np.bincount(cod, weights=w, minlength=k_tot)
                for (m_, f_), n_ in zip(pares, cuenta):
                    sumar(llenos, (clave(m_), f_, c), int(n_))
        inicio += nb
    if inicio != total:
        raise Parar(f"los bloques suman {inicio} filas y la tabla dice {total}")
    t_lectura = time.time() - t0

    # Muestra y positivos como tablas
    def juntar(d):
        """Une los trozos de cada columna sin concatenar tablas vacías."""
        return pd.DataFrame({c: (np.concatenate(v) if v else np.array([], dtype=float)) for c, v in d.items()})
    ms = juntar(muestra)
    ps = juntar(positivos)
    ms_c = ms.loc[ms[PERIODO] == CONSTRUCCION]
    neg = ms_c.loc[ms_c[OBJETIVO] == 0]
    # Grupo de cada foto de la muestra y de los positivos, como texto, para separar sin recorrer fila a fila
    claves_neg = {g: np.array([str(clave(v)) for v in neg[g]], dtype=object) for g in (FAB, CAP)}
    claves_pos = {g: np.array([str(clave(v)) for v in ps[g]], dtype=object) for g in (FAB, CAP)}

    # Tipificación con lo acumulado (§2 y comprobación 13)
    tip = []
    limite = min(LIMITE_DISCRETA, PARTE_DISCRETA * total)
    tipo_col = {}
    for g, cols in grupos.items():
        for c in cols:
            if c not in columnas:
                continue
            if g in ("identificacion_y_fecha",):
                t = "identificador" if tipos[c] == "texto" else "fecha"
            elif g == "objetivo":
                t = "objetivo" if c == OBJETIVO else "fecha"
            elif g == "particion":
                t = "particion"
            elif g == "no_previstas":
                t = "no_prevista"
            elif g == "sitio" and tipos[c] == "num":
                t = "codigo"
            elif tipos[c] == "bool":
                t = "booleana"
            elif tipos[c] == "texto":
                nd = len({k[0] for k in uni.get(c, {})} - {VACIO})
                t = "alta_cardinalidad" if nd > ALTA_CARDINALIDAD else "categorica"
            elif tipos[c] == "num":
                nd = None if distintos.get(c) is None else len(distintos[c] - {VACIO})
                t = "discreta" if (entera.get(c) and nd is not None and nd <= limite) else "continua"
            else:
                t = "fecha"
            tipo_col[c] = t
            tip.append({"columna": c, "grupo": g, "tipo": t,
                        "distintos": None if distintos.get(c) is None and tipos[c] == "num" else (
                            len(distintos[c] - {VACIO}) if c in distintos and distintos[c] is not None
                            else (len({k[0] for k in uni.get(c, {})} - {VACIO}) if c in uni else None)),
                        "entera": entera.get(c)})

    # Variables numéricas: momentos exactos y percentiles de la muestra
    num, graf = [], []
    for c in numericas:
        if tipo_col.get(c) not in ("continua", "discreta"):
            continue
        m = momentos[c]
        conteo = 0 if m is None else int(m[0])
        e = estadisticos(ms[c]) if len(ms) else {}
        st = {"columna": c, "tipo": tipo_col[c], "conteo": conteo, "nulos": int(total - conteo),
              "media": None if m is None else r(m[1]),
              "desviacion": None if m is None or m[0] < 2 else r(math.sqrt(m[2] / (m[0] - 1))),
              "minimo": None if m is None else r(m[3]), "maximo": None if m is None else r(m[4]),
              "base": f"conteo, media, desviación y extremos con las {f(total)} fotos; mediana y percentiles con la "
                      f"muestra de {f(n_muestra)}"}
        for k in ("mediana", "p01", "p05", "p25", "p75", "p95", "p99"):
            st[k] = e.get(k)
        nd = None if distintos.get(c) is None else len(distintos[c] - {VACIO})
        st["senales"] = senales(st["media"] or 0, st["mediana"], st["desviacion"], st["p25"], st["p75"], st["minimo"],
                                st["maximo"], nd)
        num.append(st)
        if tipo_col[c] == "continua" and len(ms):
            h = bins_histograma(ms[c].to_numpy(dtype=float))
            if h and h["bordes"]:
                graf.append(grafico_histograma(c, st, h, "foto", f"{f(h['n'])} fotos de la muestra fija"))

    # Variables categóricas y discretas: frecuencias exactas de todas las filas
    cat = []
    for c in uni:
        if tipo_col.get(c) in (None, "continua"):
            continue
        tot = {}
        for (v, _), (a, _) in uni[c].items():
            sumar(tot, v, a)
        s = pd.Series({k: a for k, (a, _) in tot.items()})
        totaln = int(s.sum())
        filas = [{"valor": k, "filas": int(a), "pct": r(parte(a, totaln), 4)} for k, a in s.sort_values(ascending=False).items()]
        top10 = sum(x["filas"] for x in filas[:MAS_FRECUENTES])
        fr = {"columna": c, "tipo": tipo_col[c], "nivel": "foto", "cardinalidad": len([x for x in filas if x["valor"] != VACIO]),
              "nulos": int(tot.get(VACIO, (0, 0))[0]), "dominante": filas[0]["valor"] if filas else None,
              "pct_dominante": filas[0]["pct"] if filas else None, "pct_10_mas_frecuentes": r(parte(top10, totaln), 4),
              "frecuencias": filas[:15], "total": totaln}
        cat.append(fr)
        if tipo_col[c] != "codigo" and totaln:
            graf.append(grafico_frecuencias(c, fr, tipo_col[c], "foto"))

    # Temporal: fotos por mes (todas), y la parte de fotos que fallan en 30 días por mes en la construcción
    meses = sorted({k[0] for k in por_mes})
    fotos_mes = {m: sum(a for (mm, _, _), (a, _) in por_mes.items() if mm == m) for m in meses}
    fabs = sorted({k[1] for k in por_mes if k[1] != VACIO})
    cons_meses = sorted({k[0] for k in cons_mes_fab})
    por_mes_c = []
    for m in cons_meses:
        a = sum(x[0] for (mm, _), x in cons_mes_fab.items() if mm == m)
        b = sum(x[1] for (mm, _), x in cons_mes_fab.items() if mm == m)
        por_mes_c.append({"mes": m, "fotos": a, "fallan": b, "parte_pct": r(parte(b, a), 6)})
    mes_fab = [{"mes": m, "fabricante": fb, "fotos": a, "fallan": b, "parte_pct": r(parte(b, a), 6)}
               for (m, fb), (a, b) in sorted(cons_mes_fab.items(), key=lambda x: (x[0][0], str(x[0][1])))]
    mes_cap = [{"mes": m, CAP: cp, "fotos": a, "fallan": b, "parte_pct": r(parte(b, a), 6)}
               for (m, cp), (a, b) in sorted(cons_mes_cap.items(), key=lambda x: (x[0][0], str(x[0][1])))]
    fecha_datos = ctx["fecha_datos"]
    serie_fotos = serie_negocio(meses, [fotos_mes[m] for m in meses], [True] * len(meses), "mes", "stock")
    anom = anomalias(meses, [fotos_mes[m] for m in meses], "fotos por mes")

    # Por año: dos granularidades (comprobación 1); la parte por año en la construcción, con su vista por grupos
    dfa = pd.DataFrame([{"ano": int(m[:4]), FAB: fb, "fotos": a, "fallan": b} for (m, fb), (a, b) in cons_mes_fab.items()])
    dfa_cap = pd.DataFrame([{"ano": int(m[:4]), CAP: cp, "fotos": a, "fallan": b} for (m, cp), (a, b) in cons_mes_cap.items()])
    meses_por_ano = pd.Series([int(m[:4]) for m in cons_meses]).value_counts()
    anos_c = sorted(int(a) for a in meses_por_ano.index)
    anos_completos_c = [a for a in anos_c if meses_por_ano.loc[a] == 12]
    sep_ano = None
    if len(dfa):
        sep_fab = separar(dfa, "ano", "fallan", "fotos", 100, MIN_FILAS_CATEGORIA, grupos=(FAB,), orden=anos_completos_c)
        sep_cap = separar(dfa_cap, "ano", "fallan", "fotos", 100, MIN_FILAS_CATEGORIA, grupos=(CAP,), orden=anos_completos_c)
        sep_ano = {**sep_fab, "por_grupo": {**sep_fab["por_grupo"], **sep_cap["por_grupo"]},
                   "alertas": sep_fab["alertas"] + sep_cap["alertas"], "anidada": sep_fab["anidada"] + sep_cap["anidada"]}

    # Frente al objetivo: categóricas con recuentos exactos; continuas con la muestra (comprobación 12)
    def variable_categorica(c, acc, grupo):
        """Una categórica frente al objetivo: parte por categoría, diferencia y vista por fabricante y capacidad."""
        cats = categorias_objetivo(acc)
        auc = auc_categorias(cats)
        sep = separar(df_acumulado(acc), "valor", "fallan", "fotos", 100, MIN_FILAS_CATEGORIA)
        dif = None if auc is None else abs(2 * auc - 1)
        return {"columna": c, "grupo": grupo, "tipo": tipo_col[c], "auc": r(auc, 4), "diferencia": r(dif, 4),
                "posible_fuga": bool(dif is not None and dif >= UMBRAL_FUGA), "categorias": cats,
                "pequenas": [{"valor": x["valor"], "filas": x["filas"]} for x in cats if not x["comparada"]],
                "separar": sep}

    def variable_continua(c, grupo):
        """Una continua frente al objetivo: lleno, parte mayor que cero y cuartiles en cada clase, y su AUC."""
        x1 = ps[c].to_numpy(dtype=float) if c in ps else np.array([])
        x0 = neg[c].to_numpy(dtype=float) if c in neg else np.array([])
        clases = {}
        for nombre, x in (("1", x1), ("0", x0)):
            s = pd.Series(x)
            ll = s.dropna()
            clases[nombre] = {"filas": int(len(s)), "lleno_pct": r(parte(len(ll), len(s)), 4),
                              "mayor_que_cero_pct": r(parte(int((ll > 0).sum()), len(ll)), 4),
                              "p25": r(ll.quantile(0.25)) if len(ll) else None,
                              "mediana": r(ll.median()) if len(ll) else None,
                              "p75": r(ll.quantile(0.75)) if len(ll) else None}
        auc = auc_rangos(x1[np.isfinite(x1)], x0[np.isfinite(x0)])
        dif = None if auc is None else abs(2 * auc - 1)
        # La dirección de las medianas dentro de cada fabricante y capacidad, por si se invierte
        alertas = []
        d_tot = None if clases["1"]["mediana"] is None or clases["0"]["mediana"] is None else (
            clases["1"]["mediana"] - clases["0"]["mediana"])
        por_grupo = {}
        for g in (FAB, CAP):
            por_grupo[g] = {}
            for valor in sorted(set(claves_neg[g].tolist()) | set(claves_pos[g].tolist())):
                a1 = pd.Series(x1[claves_pos[g] == valor], dtype=float).dropna()
                a0 = pd.Series(x0[claves_neg[g] == valor], dtype=float).dropna()
                fila = {"filas_1": int(len(a1)), "filas_0": int(len(a0)),
                        "mediana_1": r(a1.median()) if len(a1) else None, "mediana_0": r(a0.median()) if len(a0) else None}
                por_grupo[g][str(valor)] = fila
                if (d_tot and len(a1) >= MIN_FILAS_CATEGORIA and len(a0) >= MIN_FILAS_CATEGORIA):
                    d = fila["mediana_1"] - fila["mediana_0"]
                    if d * d_tot < 0:
                        alertas.append({"grupo_dim": g, "grupo": valor, "diferencia_total": r(d_tot),
                                        "diferencia_grupo": r(d), "tipo": "se invierte"})
        return {"columna": c, "grupo": grupo, "tipo": "continua", "auc": r(auc, 4), "diferencia": r(dif, 4),
                "posible_fuga": bool(dif is not None and dif >= UMBRAL_FUGA), "por_clase": clases,
                "categorias": [], "separar": {"por_grupo": por_grupo, "alertas": alertas, "anidada": []}}

    vars_obj = []
    for c in variables:
        grupo = "del_modelo" if c in del_modelo else "conocidas_el_dia_de_la_foto"
        t = tipo_col.get(c)
        if t == "continua":
            vars_obj.append(variable_continua(c, grupo))
        elif c in cruce:
            vars_obj.append(variable_categorica(c, cruce[c], grupo))
    vars_obj.sort(key=lambda v: -(v["diferencia"] or 0))
    vars_sitio = [variable_categorica(c, cruce_sitio[c], "sitio") for c in sitio]
    vars_sitio.sort(key=lambda v: -(v["diferencia"] or 0))
    n_cons = sum(a for (a, _) in cons_mes_fab.values())
    n_cons_1 = sum(b for (_, b) in cons_mes_fab.values())
    n_val = sum(a for (a, _) in val_fab.values())
    n_val_1 = sum(b for (_, b) in val_fab.values())

    # Correlaciones de Pearson y Spearman entre las numéricas y con el objetivo, en la muestra de construcción
    corr = None
    cols_corr = [c for c in numericas if tipo_col.get(c) in ("continua", "discreta") and ms_c[c].nunique() > 1]
    if len(ms_c) > 2 and cols_corr:
        base = ms_c[cols_corr + [OBJETIVO]].astype(float)
        base = base.loc[:, base.nunique() > 1]
        fuertes, con_obj = [], []
        for metodo in ("pearson", "spearman"):
            mat = base.corr(method=metodo)
            cs = list(mat.columns)
            for a_i in range(len(cs)):
                for b_i in range(a_i + 1, len(cs)):
                    v = mat.iloc[a_i, b_i]
                    if pd.notna(v) and abs(v) >= UMBRAL_CORRELACION:
                        fuertes.append({"a": cs[a_i], "b": cs[b_i], "metodo": metodo, "r": r(v, 4)})
            if OBJETIVO in mat.columns:
                for c in cs:
                    if c != OBJETIVO and pd.notna(mat.loc[c, OBJETIVO]):
                        con_obj.append({"columna": c, "metodo": metodo, "r": r(mat.loc[c, OBJETIVO], 4)})
        corr = {"filas": int(len(base)), "fuertes": fuertes, "con_objetivo": con_obj,
                "nota": "muestra uniforme de construcción; el objetivo, en su proporción real"}

    # Lo lleno: total y por fabricante (todas las fotos), y en la construcción por fabricante
    meses_c = set(cons_meses)

    def lleno(col, solo_cons):
        """Parte de fotos con `col` lleno, en total y por fabricante."""
        por_f, tot_l, tot_n = {}, 0, 0
        for (m_, f_), (n_, _) in filas_mf.items():
            if solo_cons and m_ not in meses_c:
                continue
            l_ = llenos.get((m_, f_, col), (0, 0))[0]
            x = por_f.get(f_, [0, 0])
            por_f[f_] = [x[0] + l_, x[1] + n_]
            tot_l += l_
            tot_n += n_
        return r(parte(tot_l, tot_n), 4), {k: r(parte(a, b), 4) for k, (a, b) in sorted(por_f.items(), key=str)}, por_f

    llen_np = []
    for c in no_prev:
        if c in columnas:
            t_, pf_, _ = lleno(c, False)
            llen_np.append({"columna": c, "lleno_pct": t_, "por_fabricante": pf_})
    llen_sitio = []
    for c in sitio:
        t_, pf_, _ = lleno(c, True)
        llen_sitio.append({"columna": c, "lleno_construccion_pct": t_, "por_fabricante": pf_})
    cont_llenos = []
    for c in CONTADORES:
        if c in columnas:
            _, _, por_f = lleno(c, True)
            for fb, (a, b) in sorted(por_f.items(), key=str):
                cont_llenos.append({"columna": c, "fabricante": fb, "filas": b, "llenos": a, "lleno_pct": r(parte(a, b), 4)})
    dc_lleno = lleno("datacenter", True)[0] if "datacenter" in columnas else None
    dc_mes = []
    if "datacenter" in columnas:
        for m in meses:
            n_ = sum(x[0] for (mm, _), x in filas_mf.items() if mm == m)
            l_ = sum(x[0] for (mm, _, c), x in llenos.items() if mm == m and c == "datacenter")
            dc_mes.append({"mes": m, "lleno_pct": r(parte(l_, n_), 4)})

    # Diccionario de la tabla
    R = base_tabla("fotos_riesgo", ctx)
    R["contexto"].update({
        "que_es_una_fila": ctx["salida"]["fotos_riesgo"]["que_es_una_fila"], "clave": ["serial_number", "fecha"],
        "granularidad": "un disco de datos en la foto del día 1 de cada mes", "periodo": {"desde": meses[0] if meses else None,
                                                                                         "hasta": meses[-1] if meses else None},
        "reglas": "reglas-transformacion.md §3; partición en reglas-negocio.md §7",
        "columnas_sin_grupo": sin_grupo})
    R["vision_general"] = {
        "filas": total, "columnas": md.num_columns, "bloques": md.num_row_groups, "discos_distintos": len(series_serial),
        "filas_construccion": n_cons, "filas_validacion": n_val, "meses": len(meses), "meses_construccion": len(cons_meses),
        "tipos": pd.Series([t["tipo"] for t in tip]).value_counts().to_dict(),
        "columnas_por_grupo": {g: len([c for c in v if c in columnas]) for g, v in grupos.items()}}
    R["tipificacion"] = tip
    R["numericas"] = num
    R["categoricas"] = cat
    R["muestra"] = {"tamano": n_muestra, "semilla": SEMILLA, "de": total, "construccion": int(len(ms_c)),
                    "construccion_objetivo_0": int(len(neg)), "positivos_construccion": int(len(ps)),
                    "nota": "medianas y percentiles de cada variable con la muestra uniforme; frente al objetivo, la "
                            "clase 1 son todas las fotos de construcción con objetivo 1 y la clase 0, las de la muestra"}
    R["temporal"] = {"fotos_por_mes": [{"mes": m, "fotos": fotos_mes[m]} for m in meses],
                     "periodos_incompletos": [{"periodo": str(a), "motivo": "año sin sus doce meses en los datos"}
                                              for a in sorted({int(m[:4]) for m in meses})
                                              if not ano_completo(a, fecha_datos)],
                     "construccion_por_ano": sep_ano, "anos_completos_construccion": anos_completos_c,
                     "datacenter_lleno_por_mes": dc_mes}
    R["series_negocio"] = [{"serie": "fotos por mes", **serie_fotos}]
    R["anomalias"] = anom
    R["frente_al_objetivo"] = {
        "objetivo": OBJETIVO, "tipo": "si_no", "filas_usadas": CONSTRUCCION, "n_filas": n_cons, "n_objetivo_1": n_cons_1,
        "parte_pct": r(parte(n_cons_1, n_cons), 6), "nombre_tasa": "parte de fotos que fallan en 30 días",
        "variables": vars_obj,
        "sitio": {"desde": inicio_sitio.strftime("%Y-%m-%d"), "n_filas": n_sitio, "variables": vars_sitio},
        "validacion": {"filas": n_val, "fallan": n_val_1, "parte_pct": r(parte(n_val_1, n_val), 6),
                       "por_fabricante": [{"fabricante": fb, "filas": a, "fallan": b, "parte_pct": r(parte(b, a), 6)}
                                          for fb, (a, b) in sorted(val_fab.items(), key=str)]},
        "correlaciones": corr}
    R["llenado"] = {"no_previstas": llen_np, "sitio": llen_sitio,
                    "base": "no previstas: todas las fotos; sitio: fotos de construcción"}
    R["cifras_para_siguiente"] = {"construccion_por_mes": por_mes_c, "construccion_por_mes_y_fabricante": mes_fab,
                                  "construccion_por_mes_y_capacidad": mes_cap, "contadores_llenos_construccion": cont_llenos,
                                  "datacenter_lleno_construccion_pct": dc_lleno}
    R["cifras_de_control"] = {"fotos.construccion": n_cons, "fotos.construccion_objetivo_1": n_cons_1,
                              "fotos.validacion": n_val, "fotos.validacion_objetivo_1": n_val_1,
                              "fotos.meses_construccion": len(cons_meses), "fotos.discos": len(series_serial),
                              "fotos.datacenter_lleno_construccion_pct": dc_lleno}
    R["graficos"] = graf
    R["_tiempos"] = {"lectura_por_bloques": round(t_lectura, 1)}
    interpretar_fotos(R, ctx)
    return R


def interpretar_fotos(R, ctx):
    """Gráficos temporales y de objetivo, hallazgos, alertas e hipótesis de fotos_riesgo, con cifras del diccionario."""
    fo = R["frente_al_objetivo"]
    t = R["temporal"]
    g = R["graficos"]
    pm = R["cifras_para_siguiente"]["construccion_por_mes"]
    if t["fotos_por_mes"]:
        fm = t["fotos_por_mes"]
        g.append({"id": "tmp-fotos", "seccion": "temporal", "tipo": "linea", "ancho": "completo",
                  "titulo": f"Las fotos por mes pasan de {f(fm[0]['fotos'])} en {nombre_mes(fm[0]['mes'])} a "
                            f"{f(fm[-1]['fotos'])} en {nombre_mes(fm[-1]['mes'])}",
                  "subtitulo": "Fotos de discos de datos el día 1 de cada mes, los dos periodos",
                  "fuente": "fotos_riesgo, recuento exacto bloque a bloque",
                  "datos": {"periodos": [nombre_mes(x["mes"]) for x in fm], "series": {"fotos": [x["fotos"] for x in fm]},
                            "decimales": 0}})
    if pm:
        fabs = sorted({x[FAB] for x in R["cifras_para_siguiente"]["construccion_por_mes_y_fabricante"]
                       if x[FAB] != VACIO}, key=str)[:4]
        series = {}
        for fb in fabs:
            d = {x["mes"]: x["parte_pct"] for x in R["cifras_para_siguiente"]["construccion_por_mes_y_fabricante"]
                 if x[FAB] == fb}
            series[str(fb)] = [d.get(x["mes"]) or 0.0 for x in pm]
        mayor = max(pm, key=lambda x: x["fallan"])
        menor = min(pm, key=lambda x: x["fallan"])
        g.append({"id": "tmp-parte-mes", "seccion": "temporal", "tipo": "linea", "ancho": "completo",
                  "titulo": f"Las fotos que fallan en 30 días van de {f(menor['fallan'])} en {nombre_mes(menor['mes'])} "
                            f"a {f(mayor['fallan'])} en {nombre_mes(mayor['mes'])}",
                  "subtitulo": "Parte de fotos que fallan en 30 días, en %, por mes y fabricante; solo construcción. "
                               + AVISO_EDADES,
                  "fuente": f"{f(fo['n_filas'])} fotos de construcción, recuento exacto",
                  "datos": {"periodos": [nombre_mes(x["mes"]) for x in pm], "series": series, "decimales": 2}})
    if t["datacenter_lleno_por_mes"]:
        dm_ = t["datacenter_lleno_por_mes"]
        g.append({"id": "tmp-sitio", "seccion": "temporal", "tipo": "linea", "ancho": "completo",
                  "titulo": f"El centro de datos consta desde {nombre_mes(fo['sitio']['desde'])}",
                  "subtitulo": "Parte de fotos con el centro de datos lleno, en %, por mes",
                  "fuente": "fotos_riesgo, recuento exacto de lo lleno",
                  "datos": {"periodos": [nombre_mes(x["mes"]) for x in dm_],
                            "series": {"centro lleno": [x["lleno_pct"] or 0.0 for x in dm_]}, "decimales": 1}})
    vis = [v for v in fo["variables"] if (v["diferencia"] or 0) >= UMBRAL_DIBUJAR]
    # Las categorías de model y capacity_bytes no se dibujan ni se dan como hallazgo: serían el ranking de modelos
    vis_cat = [v for v in vis if v["columna"] not in SIN_ORDENAR]
    if vis:
        g.append({"id": "obj-diferencia", "seccion": "objetivo", "tipo": "barras",
                  "titulo": f"{vis[0]['columna']} es la variable que más separa las fotos que fallan en 30 días",
                  "subtitulo": f"Diferencia |2·AUC − 1| de cada variable sola; solo las de {f(UMBRAL_DIBUJAR, 2)} o más",
                  "fuente": f"construcción: {f(fo['n_filas'])} fotos, {f(fo['n_objetivo_1'])} con objetivo 1",
                  "datos": {"etiquetas": [v["columna"] for v in vis], "series": {"diferencia": [v["diferencia"] for v in vis]},
                            "decimales": 2}})
    for v in vis_cat[:4]:
        if v["categorias"]:
            cs = [c for c in v["categorias"] if c["comparada"]][:15]
            if cs:
                top = max(cs, key=lambda c: c["parte_pct"])
                g.append({"id": f"obj-{v['columna']}", "seccion": "objetivo", "tipo": "barras",
                          "titulo": f"Con {v['columna']} = {et(top['valor'])} falla en 30 días el {f(top['parte_pct'], 2)} % "
                                    f"de las fotos",
                          "subtitulo": "Parte de fotos que fallan en 30 días, en %, por valor (n = fotos); solo "
                                       "construcción y categorías con 30 fotos o más",
                          "fuente": f"{f(fo['n_filas'])} fotos de construcción",
                          "datos": {"etiquetas": [et(c["valor"]) for c in cs],
                                    "series": {"parte": [c["parte_pct"] for c in cs]}, "n": [c["filas"] for c in cs],
                                    "decimales": 2}})

    # Hallazgos y alertas
    H, A, Hi = R["hallazgos"], R["alertas"], R["hipotesis"]
    tot_sep = separar_total(pd.DataFrame([{FAB: c["valor"], "fotos": c["filas"], "fallan": c["fallan"]}
                                          for c in next((v["categorias"] for v in fo["variables"] if v["columna"] == FAB), [])]
                                         or [{FAB: VACIO, "fotos": 0, "fallan": 0}]),
                            "fallan", "fotos", 100, MIN_FILAS_CATEGORIA, grupos=(FAB,))
    texto = (f"En la construcción falla en 30 días el {f(fo['parte_pct'], 3)} % de las fotos: "
             f"{f(fo['n_objetivo_1'])} de {f(fo['n_filas'])}.")
    nuevo_hallazgo(R, texto, tot_sep["alertas"], fo["parte_pct"], fo["n_filas"], [OBJETIVO, PERIODO],
                   ["fabricante"], "tmp-parte-mes", "parte de fotos que fallan en 30 días", "puntos")
    for v in [v for v in vis_cat if not v["posible_fuga"]][:3]:
        if v["categorias"]:
            cs = [c for c in v["categorias"] if c["comparada"]]
            if len(cs) < 2:
                continue
            hi, lo = max(cs, key=lambda c: c["parte_pct"]), min(cs, key=lambda c: c["parte_pct"])
            texto = (f"Con {v['columna']} = {et(hi['valor'])} falla en 30 días el {f(hi['parte_pct'], 3)} % de las fotos "
                     f"({f(hi['filas'])} fotos). Con {et(lo['valor'])}, el {f(lo['parte_pct'], 3)} % ({f(lo['filas'])}).")
            dims = ["fabricante", "capacidad_tb"]
            if v["separar"]["anidada"]:
                texto += f" No se separa por {', '.join(v['separar']['anidada'])}: cada valor cae en uno solo."
            nuevo_hallazgo(R, texto, v["separar"]["alertas"], hi["parte_pct"], hi["filas"], [v["columna"], OBJETIVO],
                           dims, f"obj-{v['columna']}", f"parte por {v['columna']}", "puntos")
        else:
            c1, c0 = v["por_clase"]["1"], v["por_clase"]["0"]
            texto = (f"{v['columna']}: mediana {f(c1['mediana'], 2)} en las fotos que fallan en 30 días "
                     f"({f(c1['filas'])}) y {f(c0['mediana'], 2)} en las demás ({f(c0['filas'])} de la muestra); "
                     f"diferencia {f(v['diferencia'], 2)}.")
            nuevo_hallazgo(R, texto, v["separar"]["alertas"], v["diferencia"], c1["filas"] + c0["filas"],
                           [v["columna"], OBJETIVO], ["fabricante", "capacidad_tb"], "obj-diferencia",
                           f"mediana de {v['columna']}", "")
    for v in fo["variables"] + fo["sitio"]["variables"]:
        if v["posible_fuga"]:
            A.append({"id": None, "tipo": "posible_fuga", "origen": None,
                      "texto": f"Posible fuga: {v['columna']} separa el objetivo casi del todo (diferencia "
                               f"{f(v['diferencia'], 2)}). Puede conocerse después del hecho; no se elige ni se descarta aquí."})
    if fo["sitio"]["variables"]:
        A.append({"id": None, "tipo": "limitacion", "origen": None,
                  "texto": f"El sitio solo se cruza con las {f(fo['sitio']['n_filas'])} fotos de construcción desde el "
                           f"{fo['sitio']['desde']}; antes no consta (reglas-negocio §4). El centro está lleno en el "
                           f"{f(R['cifras_para_siguiente']['datacenter_lleno_construccion_pct'], 1)} % de la construcción."})
    sep = R["temporal"]["construccion_por_ano"]
    if sep:
        for linea in texto_alertas_separar("parte por año en la construcción", sep, "puntos"):
            A.append({"id": None, "tipo": "separar", "origen": None, "texto": linea, "vista": "construccion_por_ano"})
    A.append({"id": None, "tipo": "limitacion", "origen": None,
              "texto": "La parte de fotos que fallan en 30 días no es la tasa anual de fallo: cuenta fotos, y un fallo "
                       "en el horizonte de dos fotos cuenta en las dos (reglas-transformacion §3)."})
    A.append({"id": None, "tipo": "limitacion", "origen": None, "texto": AVISO_EDADES})
    if any(c in [x["columna"] for x in R["tipificacion"]] for c in ("smart_187_raw", "smart_188_raw")):
        A.append({"id": None, "tipo": "codigos", "origen": "calidad-datos C-14",
                  "texto": "Los contadores 187 y 188 solo los traen los Seagate, y el 188 no es un recuento creíble: se "
                           "usa como cero o no cero (plan de la analítica). Sus valores en bruto no se comparan entre "
                           "fabricantes (reglas-negocio §5)."})
    hipotesis_separar(R)


# =================================================================================================================
# 8. Las cinco tablas de la parte analítica
# =================================================================================================================
def con_dim(df, dm, columnas=(FAB, CAP)):
    """Añade fabricante y capacidad de dim_modelo por el modelo, sin cambiar el número de filas."""
    faltan = [c for c in columnas if c not in df.columns]
    if not faltan:
        return df
    out = df.merge(dm[["model"] + faltan], on="model", how="left", validate="many_to_one")
    if len(out) != len(df):
        raise Parar("el cruce con dim_modelo cambió el número de filas")
    return out


def tasas(R, nombre, df, dim, num="fallos", den="dias_disco", orden=None, grafico=True, titulo_dim=None):
    """Tasa anual por `dim`, separada por fabricante y capacidad; la guarda y dibuja sus barras."""
    sep = separar(df, dim, num, den, FACTOR_TASA_ANUAL, MINIMO_DIAS, orden=orden)
    R["tasas"].append({"nombre": nombre, **sep})
    if grafico:
        filas = [x for x in sep["total"] if x["comparada"]]
        if orden is not None:
            filas.sort(key=lambda x: orden.index(x["categoria"]) if x["categoria"] in orden else 1e9)
        else:
            filas.sort(key=lambda x: str(x["categoria"]))
        if filas:
            top = max(filas, key=lambda x: x["valor"])
            aviso = (" " + AVISO_EDADES) if dim in (FAB, CAP) else ""
            R["graficos"].append({
                "id": f"tasa-{nombre}", "seccion": "categoricas" if orden is None else "temporal", "tipo": "barras",
                "titulo": f"La tasa anual de fallo más alta por {titulo_dim or dim} es la de {et(top['categoria'])}: "
                          f"{f(top['valor'], 2)} %",
                "subtitulo": f"Tasa anual de fallo en %, con sus fallos (n); solo con {f(MINIMO_DIAS)} días de disco o "
                             f"más{aviso}",
                "fuente": f"{f(sum(x['den'] for x in sep['total']))} días de disco y {f(sum(x['num'] for x in sep['total']))} fallos",
                "datos": {"etiquetas": [et(x["categoria"]) for x in filas], "series": {"tasa": [x["valor"] for x in filas]},
                          "n": [int(x["num"]) for x in filas], "decimales": 2, "ordenar": orden is None}})
    return sep


def hallazgo_tasa(R, nombre, sep, columnas, grafico, unidad="puntos", etiqueta="tasa anual de fallo"):
    """Hallazgo (o alerta, si cambia al separar) con la categoría más alta y la más baja de una tasa."""
    filas = [x for x in sep["total"] if x["comparada"]]
    if len(filas) < 2 or not sep["par"]:
        return
    a = next(x for x in filas if x["categoria"] == sep["par"][0])
    b = next(x for x in filas if x["categoria"] == sep["par"][1])
    texto = (f"{etiqueta.capitalize()} por {nombre}: {f(a['valor'], 2)} % en {et(a['categoria'])} ({f(a['num'])} fallos en "
             f"{f(a['den'])} días de disco) frente a {f(b['valor'], 2)} % en {et(b['categoria'])} ({f(b['num'])} fallos en "
             f"{f(b['den'])}).")
    if sep["anidada"]:
        texto += f" No se separa por {', '.join(sep['anidada'])}: cada valor cae en uno solo."
    nuevo_hallazgo(R, texto, sep["alertas"], a["valor"], int(a["num"] + b["num"]), columnas, [FAB, CAP], grafico,
                   f"{etiqueta} por {nombre}", unidad)


def nuevo_hallazgo(R, texto, alertas, cifra, filas, columnas, dims, grafico, nombre, unidad):
    """Da un total o una comparación como hallazgo; si cambia al separar, pasa a alerta con su vista por grupos (§5)."""
    if alertas:
        R["alertas"].append({"id": None, "tipo": "separar", "origen": None,
                             "texto": texto + " Al separar por " + ", ".join(dims) + " cambia: "
                                      + "; ".join(texto_alertas_separar(nombre, {"alertas": alertas[:3]}, unidad))
                                      + (f" (y {len(alertas) - 3} más)" if len(alertas) > 3 else ""),
                             "vista": nombre})
        R["_separaciones"].append({"nombre": nombre, "alertas": alertas})
    else:
        R["hallazgos"].append({"id": None, "texto": texto, "cifra": r(cifra, 6), "filas": filas, "columnas": columnas,
                               "dimensiones_comprobadas": dims, "grafico": grafico})


def anomalia_preguntas():
    """Las tres preguntas de una anomalía concentrada (método, apartado 5), contestadas con lo que se puede saber aquí."""
    return {"afecta_de_mas_a_la_entidad": "no se puede saber con esta tabla sola",
            "fuera_del_rango_dominante": "sí, por cómo se detecta",
            "coincide_con_otra_senal": "no se puede saber con esta tabla sola",
            "lecturas": "error del dato (filas que faltan en el origen) o hecho real (una migración o una baja en bloque); "
                        "para distinguirlas haría falta el recuento diario de ese mes y el registro de migraciones"}


def hipotesis_separar(R):
    """Una hipótesis por cada comparación que cambia al separar, con lo que haría falta para aceptarla (comprobación 8)."""
    for s in R["_separaciones"][:4]:
        R["hipotesis"].append({
            "id": None,
            "texto": f"El cambio de {s['nombre']} al separar puede venir de que cada grupo tiene otra mezcla de modelos "
                     f"y edades.",
            "que_haria_falta": "compararla a igual modelo y edad, que es del paso 5 (reglas-negocio §7)",
            "alternativas_repasadas": ["el tamaño del grupo", "el calendario", "la regresión a la media",
                                       "la causa al revés", "una variable que no está en la tabla (edad, vault)"]})


def base_tabla(nombre, ctx):
    """Diccionario vacío de una tabla, con el bloque común de resultado.md."""
    return {"metodo": METODO, "version_metodo": VERSION_METODO, "script": SCRIPT, "peticion": PETICION,
            "fecha_datos": ctx["fecha_datos"].strftime("%Y-%m-%d"), "fecha_ejecucion": ctx["fecha_ejecucion"],
            "tabla": nombre, "entradas": [], "resultado": {}, "pendientes": [],
            "dataset": {"ruta": f"data/processed/{nombre}.parquet", "sha256": ctx["huellas_antes"].get(nombre),
                        "bytes": ctx["bytes"].get(nombre)},
            "premisa": {"afirmacion": None, "la_sostienen_los_datos": None},
            "contexto": {"limitaciones": []}, "vision_general": {}, "tipificacion": [], "numericas": [],
            "categoricas": [], "fechas": [], "temporal": {}, "tasas": [], "partes": [], "pareto": [],
            "series_negocio": [], "anomalias": [], "frente_al_objetivo": None, "hallazgos": [], "alertas": [],
            "hipotesis": [], "comprobaciones": [], "observaciones": [], "parametros": [], "siguiente_paso": None,
            "graficos": [], "graficos_no_dibujados": [], "cifras_para_siguiente": {}, "cifras_de_control": {},
            "_separaciones": []}


def describir_en(R, df, spec):
    """Mete en el diccionario la descripción genérica de la tabla (tipificación, numéricas, categóricas y fechas)."""
    d = describir(df, spec)
    R["tipificacion"], R["numericas"], R["categoricas"], R["fechas"] = (d["tipificacion"], d["numericas"],
                                                                         d["categoricas"], d["fechas"])
    R["graficos"].extend(d["graficos"])
    R["vision_general"].update({"filas": int(len(df)), "columnas": int(df.shape[1]),
                                "tipos": pd.Series([t["tipo"] for t in d["tipificacion"]]).value_counts().to_dict()})


def serie_y_grafico(R, nombre, fechas, valores, frecuencia, tipo, completos, decimales=0, volumen=False, id_=None):
    """Serie de negocio de una magnitud por periodo, con su gráfico de línea y, si es volumen, sus anomalías."""
    sn = serie_negocio(fechas, valores, completos, frecuencia, tipo)
    R["series_negocio"].append({"serie": nombre, **sn})
    if volumen:
        R["anomalias"].extend(anomalias(fechas, valores, nombre))
    etq = [nombre_mes(x) if frecuencia == "mes" else f"{pd.Timestamp(x).year} T{pd.Timestamp(x).quarter}" for x in fechas]
    mayor = int(np.argmax(valores)) if len(valores) else 0
    R["graficos"].append({"id": id_ or f"tmp-{nombre}", "seccion": "temporal", "tipo": "linea", "ancho": "completo",
                          "titulo": f"{nombre.capitalize()}: el máximo es {f(valores[mayor], decimales)} en {etq[mayor]}",
                          "subtitulo": f"{nombre.capitalize()}, por {frecuencia}",
                          "fuente": f"{len(valores)} periodos",
                          "datos": {"periodos": etq, "series": {nombre: [float(v) for v in valores]},
                                    "decimales": decimales}})
    return sn


def pareto_y_grafico(R, valores, elemento, magnitud, dibujar):
    """Pareto de una pareja y, si se pide, su curva acumulada."""
    p = pareto(valores, elemento, magnitud)
    R["pareto"].append(p)
    if dibujar and p.get("valores_ordenados"):
        R["graficos"].append({"id": f"pareto-{magnitud}-{elemento}", "seccion": "categoricas", "tipo": "curva",
                              "titulo": f"El {f(p['pct_elementos_80'], 1)} % de los {elemento} reúne el 80 % de {magnitud}",
                              "subtitulo": f"Parte acumulada de {magnitud}, con los {elemento} de mayor a menor",
                              "fuente": f"{p['elementos']} {elemento}",
                              "datos": {"valores": p["valores_ordenados"]}})
    return p


def analizar_modelo_trimestre(raiz, ctx, t):
    """modelo_trimestre, con inicio_trimestre, dim_modelo y dim_precio_gb para describirla."""
    mt, dm, dp, it, fd = t["modelo_trimestre"], t["dim_modelo"], t["dim_precio_gb"], t["inicio_trimestre"], t["fallos_detalle"]
    R = base_tabla("modelo_trimestre", ctx)
    fd_ = ctx["fecha_datos"]
    spec = {"temporal": ["ano", "trimestre"], "fecha": ["fecha_compra"],
            "niveles": [(["model"], [CAP, FAB, "fecha_compra", "precio_usd", "origen_precio"]),
                        (["model", "ano"], ["dias_disco_ano", "pasa_minimo_ano"])]}
    describir_en(R, mt, spec)
    R["contexto"].update({"que_es_una_fila": ctx["salida"]["modelo_trimestre"]["que_es_una_fila"],
                          "clave": ["model", "ano", "trimestre"], "granularidad": "un modelo de datos en un trimestre",
                          "periodo": {"desde": f"{int(mt['ano'].min())} T{int(mt.loc[mt['ano'] == mt['ano'].min(), 'trimestre'].min())}",
                                      "hasta": f"{int(mt['ano'].max())} T{int(mt.loc[mt['ano'] == mt['ano'].max(), 'trimestre'].max())}"},
                          "reglas": "reglas-transformacion.md §8; describe también §1 (dimensiones) y §7 (inicio_trimestre)"})
    R["vision_general"].update({"modelos": int(mt["model"].nunique()), "trimestres": int(mt[["ano", "trimestre"]].drop_duplicates().shape[0]),
                                "dias_disco": int(mt["dias_disco"].sum()), "fallos": int(mt["fallos"].sum())})

    # Por año: lo que espera el paso siguiente (petición, punto 10)
    pa_ = mt.groupby("ano").agg(dias_disco=("dias_disco", "sum"), fallos=("fallos", "sum"),
                                fallos_en_garantia=("fallos_en_garantia", "sum"),
                                coste_fallos_usd=("coste_fallos_usd", "sum"),
                                coste_fallos_garantia_usd=("coste_fallos_garantia_usd", "sum"))
    por_ano = [{"ano": int(a), "dias_disco": int(x["dias_disco"]), "fallos": int(x["fallos"]),
                "tasa_anual_pct": r(tasa_anual(x["fallos"], x["dias_disco"]), 6),
                "fallos_en_garantia": int(x["fallos_en_garantia"]), "coste_fallos_usd": r(x["coste_fallos_usd"], 2),
                "coste_fallos_garantia_usd": r(x["coste_fallos_garantia_usd"], 2), "completo": ano_completo(a, fd_)}
               for a, x in pa_.iterrows()]
    completos = [x["ano"] for x in por_ano if x["completo"]]
    itq = it.groupby(["ano", "trimestre"])["discos"].sum()
    itc = it.groupby(["ano", "trimestre", CAP])["discos"].sum()
    R["cifras_para_siguiente"] = {
        "por_ano": por_ano,
        "inicio_trimestre": [{"ano": int(a), "trimestre": int(q), "discos": int(n)} for (a, q), n in itq.items()],
        "inicio_trimestre_por_capacidad": [{"ano": int(a), "trimestre": int(q), CAP: float(c), "discos": int(n)}
                                           for (a, q, c), n in itc.items()]}
    R["cifras_de_control"] = {f"modelo_trimestre.{x['ano']}.{k}": x[k] for x in por_ano
                              for k in ("dias_disco", "fallos", "tasa_anual_pct", "coste_fallos_usd", "coste_fallos_garantia_usd")}
    R["temporal"]["periodos_incompletos"] = [{"periodo": str(x["ano"]), "motivo": "año que acaba después de la fecha "
                                              "de los datos"} for x in por_ano if not x["completo"]]
    R["temporal"]["por_ano"] = por_ano
    R["graficos"].append({"id": "tmp-tasa-ano", "seccion": "temporal", "tipo": "columnas",
                          "titulo": f"La tasa anual de fallo va del {f(por_ano[0]['tasa_anual_pct'], 2)} % en "
                                    f"{por_ano[0]['ano']} al {f(por_ano[-1]['tasa_anual_pct'], 2)} % en {por_ano[-1]['ano']}",
                          "subtitulo": "Tasa anual de fallo en %, por año" + (
                              f"; {', '.join(str(x['ano']) for x in por_ano if not x['completo'])} incompleto, no se "
                              f"compara con los completos" if len(completos) < len(por_ano) else ""),
                          "fuente": f"{f(R['vision_general']['dias_disco'])} días de disco y "
                                    f"{f(R['vision_general']['fallos'])} fallos de discos de datos",
                          "datos": {"periodos": [str(x["ano"]) for x in por_ano],
                                    "valores": [x["tasa_anual_pct"] or 0.0 for x in por_ano], "decimales": 2}})

    # Tasas por año, fabricante y capacidad, con su vista por grupos
    sep_ano = tasas(R, "año", mt, "ano", orden=completos, grafico=False)
    hallazgo_tasa(R, "año", sep_ano, ["fallos", "dias_disco", "ano"], "tmp-tasa-ano")
    sep_fab = tasas(R, "fabricante", mt, FAB)
    hallazgo_tasa(R, "fabricante", sep_fab, ["fallos", "dias_disco", FAB], "tasa-fabricante")
    sep_cap = tasas(R, "capacidad", mt, CAP, titulo_dim="capacidad")
    hallazgo_tasa(R, "capacidad", sep_cap, ["fallos", "dias_disco", CAP], "tasa-capacidad")

    # Series por trimestre (todos los trimestres llegan al 30 de junio de 2025)
    q = mt.groupby(["ano", "trimestre"])[["dias_disco", "fallos"]].sum().reset_index()
    q["inicio"] = [pd.Timestamp(year=int(a), month=3 * int(t_) - 2, day=1) for a, t_ in zip(q["ano"], q["trimestre"])]
    comp_q = [fin_de_periodo(x, "trimestre") <= fd_ for x in q["inicio"]]
    serie_y_grafico(R, "días de disco por trimestre", list(q["inicio"]), list(q["dias_disco"]), "trimestre", "flujo",
                    comp_q, volumen=True)
    serie_y_grafico(R, "fallos por trimestre", list(q["inicio"]), list(q["fallos"]), "trimestre", "flujo", comp_q)

    # Pareto por modelo: volumen, no ranking por tasa
    pm_ = mt.groupby("model")[["fallos", "dias_disco", "coste_fallos_usd", "coste_fallos_garantia_usd"]].sum()
    for mag, dib in (("fallos", True), ("dias_disco", False), ("coste_fallos_usd", True), ("coste_fallos_garantia_usd", False)):
        pareto_y_grafico(R, pm_[mag].to_dict(), "modelos", mag, dib)

    # Las dimensiones, descritas aquí
    dmd = dm.loc[dm["tipo_disco"] == "datos"]
    sin_precio = dmd.loc[dmd["precio_usd"].isna(), "model"].tolist()
    dias_inferido = int(mt.loc[mt["origen_precio"] == "inferido", "dias_disco"].sum())
    R["vision_general"]["dim_modelo"] = {
        "modelos": int(len(dm)), "por_tipo": dm["tipo_disco"].value_counts().to_dict(),
        "datos_por_fabricante": dmd[FAB].value_counts(dropna=False).rename(index=clave).to_dict(),
        "datos_por_capacidad": dmd[CAP].value_counts().sort_index().rename(index=clave).to_dict(),
        "datos_por_garantia": dmd["garantia_anos"].value_counts(dropna=False).rename(index=clave).to_dict(),
        "datos_por_origen_precio": dmd["origen_precio"].value_counts(dropna=False).rename(index=clave).to_dict(),
        "sin_precio": sin_precio, "dias_sin_precio": int(mt.loc[mt["model"].isin(sin_precio), "dias_disco"].sum()),
        "dias_con_precio_inferido_pct": r(parte(dias_inferido, mt["dias_disco"].sum()), 4)}
    R["vision_general"]["dim_precio_gb"] = [{CAP: float(x[CAP]), "ano": int(x["ano"]), "coste_gb": r(x["coste_gb"], 6),
                                             "origen": x["origen"]} for _, x in dp.sort_values([CAP, "ano"]).iterrows()]
    celdas = mt.drop_duplicates(["model", "ano"])
    R["vision_general"]["minimo_ranking"] = {"celdas_modelo_ano": int(len(celdas)),
                                             "pasan": int(celdas["pasa_minimo_ano"].sum()),
                                             "dias_en_celdas_que_pasan_pct": r(parte(mt.loc[mt["pasa_minimo_ano"], "dias_disco"].sum(),
                                                                                     mt["dias_disco"].sum()), 4)}

    # Segunda vía: los fallos y el coste por año desde fallos_detalle
    fdd = fd.loc[fd["tipo_disco"] == "datos"]
    otra = fdd.groupby("ano").agg(fallos=("serial_number", "size"), coste=("coste_fallo_usd", "sum"),
                                  coste_g=("coste_fallo_garantia_usd", "sum"))
    cuadre = []
    for x in por_ano:
        o = otra.loc[x["ano"]] if x["ano"] in otra.index else None
        cuadre.append({"ano": x["ano"], "fallos_modelo_trimestre": x["fallos"],
                       "fallos_fallos_detalle": None if o is None else int(o["fallos"]),
                       "coste_modelo_trimestre": x["coste_fallos_usd"], "coste_fallos_detalle": None if o is None else r(o["coste"], 2),
                       "iguales": bool(o is not None and int(o["fallos"]) == x["fallos"]
                                       and abs(float(o["coste"]) - x["coste_fallos_usd"]) < 0.01)})
    R["vision_general"]["cuadre_con_fallos_detalle"] = cuadre
    if not all(c["iguales"] for c in cuadre):
        R["alertas"].append({"id": None, "tipo": "cuadre", "origen": None,
                             "texto": "Los fallos o el coste por año de modelo_trimestre no coinciden con los de "
                                      "fallos_detalle en " + ", ".join(str(c["ano"]) for c in cuadre if not c["iguales"]) + "."})
    if sin_precio:
        R["alertas"].append({"id": None, "tipo": "limitacion", "origen": "transformacion-datos, exclusiones",
                             "texto": f"{len(sin_precio)} modelos de datos no tienen precio ({', '.join(sin_precio)}), con "
                                      f"{f(R['vision_general']['dim_modelo']['dias_sin_precio'])} días de disco."})
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": None,
                         "texto": f"El precio es inferido desde el 15/11/2022: los modelos con precio inferido suman el "
                                  f"{f(R['vision_general']['dim_modelo']['dias_con_precio_inferido_pct'], 1)} % de los días "
                                  f"de disco, y el coste vale lo que valga ese precio (reglas-negocio §6)."})
    for x in por_ano:
        if not x["completo"]:
            R["alertas"].append({"id": None, "tipo": "periodo_incompleto", "origen": None,
                                 "texto": f"{x['ano']} solo llega al {fd_.strftime('%d/%m/%Y')}: es un año incompleto y "
                                          f"no se compara con los completos (reglas-negocio §5)."})
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": None, "texto": AVISO_EDADES})
    hipotesis_separar(R)
    return R


def analizar_centro_mes(raiz, ctx, t):
    """centro_mes: tasa bruta por centro desde que consta el sitio, con la vista por grupos sacada de dias_por_tramo."""
    cm, dpt, dm = t["centro_mes"], t["dias_por_tramo"], t["dim_modelo"]
    R = base_tabla("centro_mes", ctx)
    fd_ = ctx["fecha_datos"]
    ini = ctx["inicio_sitio"]
    describir_en(R, cm, {"fecha": ["mes"]})
    R["contexto"].update({"que_es_una_fila": ctx["salida"]["centro_mes"]["que_es_una_fila"], "clave": ["datacenter", "mes"],
                          "granularidad": "un centro de datos en un mes", "reglas": "reglas-transformacion.md §9",
                          "periodo": {"desde": limpio(cm["mes"].min()), "hasta": limpio(cm["mes"].max())}})
    cs = cm.loc[cm["con_sitio"]]
    R["vision_general"].update({"centros": sorted(cm["datacenter"].unique().tolist()), "meses": int(cm["mes"].nunique()),
                                "filas_con_sitio": int(len(cs)), "dias_disco": int(cm["dias_disco"].sum()),
                                "fallos": int(cm["fallos"].sum())})
    reparto = cs.groupby("datacenter")[["dias_disco", "fallos"]].sum()
    R["vision_general"]["reparto_desde_sitio"] = [{"datacenter": k, "dias_disco": int(x["dias_disco"]), "fallos": int(x["fallos"]),
                                                   "dias_pct": r(parte(x["dias_disco"], reparto["dias_disco"].sum()), 4)}
                                                  for k, x in reparto.iterrows()]
    # Tasa bruta por centro desde el sitio; la vista por fabricante y capacidad sale de dias_por_tramo
    tasas(R, "centro (centro_mes, desde que consta el sitio)", cs, "datacenter", titulo_dim="centro")
    d2 = con_dim(dpt.loc[pd.to_datetime(dpt["mes"]) >= ini].rename(columns={"centro": "datacenter"}), dm)
    sep = tasas(R, "centro (dias_por_tramo, por fabricante y capacidad)", d2, "datacenter", grafico=False)
    hallazgo_tasa(R, "centro", sep, ["fallos", "dias_disco", "datacenter"], "tasa-centro (centro_mes, desde que consta el sitio)")
    tasas(R, "periodo", cm, "periodo", orden=[CONSTRUCCION, VALIDACION], grafico=False)
    # Serie mensual del total de centros
    tm = cm.groupby("mes")[["dias_disco", "fallos"]].sum()
    comp = [fin_de_periodo(x, "mes") <= fd_ for x in tm.index]
    serie_y_grafico(R, "días de disco por mes", list(tm.index), list(tm["dias_disco"]), "mes", "flujo", comp, volumen=True)
    serie_y_grafico(R, "fallos por mes", list(tm.index), list(tm["fallos"]), "mes", "flujo", comp)
    pareto_y_grafico(R, reparto["fallos"].to_dict(), "centros", "fallos", False)
    sd = cs.loc[cs["datacenter"] == "sin dato"]
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": "transformacion-datos, exclusiones",
                         "texto": f"Desde el {ini.strftime('%d/%m/%Y')}, el centro «sin dato» suma {f(sd['dias_disco'].sum())} "
                                  f"días de disco y {f(sd['fallos'].sum())} fallos, contados aparte. Antes, el centro no consta."})
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": None,
                         "texto": "La tasa por centro es bruta: mezcla modelos y edades. La ajustada es del paso 5 "
                                  "(reglas-negocio §7). La vista por fabricante y capacidad sale de dias_por_tramo, que "
                                  "deja fuera los días de disco sin foto (reglas-transformacion §6)."})
    hipotesis_separar(R)
    return R


def analizar_dias_por_tramo(raiz, ctx, t):
    """dias_por_tramo: tasa por año de edad cumplido, con la cifra contando a los que desaparecen avisando."""
    dpt, dm, cm = t["dias_por_tramo"], t["dim_modelo"], t["centro_mes"]
    R = base_tabla("dias_por_tramo", ctx)
    fd_ = ctx["fecha_datos"]
    describir_en(R, dpt, {"fecha": ["mes"]})
    R["contexto"].update({"que_es_una_fila": ctx["salida"]["dias_por_tramo"]["que_es_una_fila"],
                          "clave": ["model", "centro", "mes", "edad_anos_cumplidos"], "reglas": "reglas-transformacion.md §6",
                          "granularidad": "un modelo, un centro, un mes y un año de edad cumplido",
                          "periodo": {"desde": limpio(dpt["mes"].min()), "hasta": limpio(dpt["mes"].max())}})
    d = con_dim(dpt, dm)
    d["fallos_con_desaparecen"] = d["fallos"] + d["desaparecen_avisando"]
    edades = sorted(int(x) for x in d["edad_anos_cumplidos"].unique())
    sep = tasas(R, "año de edad", d, "edad_anos_cumplidos", titulo_dim="año de edad")
    hallazgo_tasa(R, "año de edad", sep, ["fallos", "dias_disco", "edad_anos_cumplidos"], "tasa-año de edad")
    con = medida_por(d, "edad_anos_cumplidos", "fallos_con_desaparecen", "dias_disco", FACTOR_TASA_ANUAL, MINIMO_DIAS)
    pocos = [x["categoria"] for x in sep["total"] if x["num"] < MINIMO_FALLOS_EDAD]
    R["partes"].append({"nombre": "tasa por año de edad contando como fallo a los que desaparecen avisando",
                        "filas": sorted(con, key=lambda x: x["categoria"]), "nota": "reglas-negocio §3"})
    R["vision_general"].update({"edades": edades, "dias_disco": r(d["dias_disco"].sum(), 2), "fallos": int(d["fallos"].sum()),
                                "filas_sin_dias": int(d["dias_disco"].isna().sum()),
                                "fallos_sin_dias": int(d.loc[d["dias_disco"].isna(), "fallos"].sum())})
    if pocos:
        R["alertas"].append({"id": None, "tipo": "pocos", "origen": None,
                             "texto": f"Los años de edad {', '.join(str(x) for x in pocos)} tienen menos de "
                                      f"{MINIMO_FALLOS_EDAD} fallos: su tasa se enseña sin conclusión (reglas-negocio §7, cuestión 009)."})
    if R["vision_general"]["filas_sin_dias"]:
        R["alertas"].append({"id": None, "tipo": "limitacion", "origen": "transformacion-datos",
                             "texto": f"{f(R['vision_general']['filas_sin_dias'])} filas solo tienen fallos, "
                                      f"{f(R['vision_general']['fallos_sin_dias'])} en total: no hubo foto con que repartir sus días."})
    tm = d.groupby("mes")[["dias_disco", "fallos"]].sum()
    comp = [fin_de_periodo(x, "mes") <= fd_ for x in tm.index]
    serie_y_grafico(R, "días de disco repartidos por mes", list(tm.index), list(tm["dias_disco"]), "mes", "flujo", comp,
                    volumen=True)
    # Segunda vía: los días y los fallos del mes frente a centro_mes
    cmm = cm.groupby("mes")[["dias_disco", "fallos"]].sum()
    dif_d = float(cmm["dias_disco"].sum() - tm["dias_disco"].sum())
    dif_f = int(cmm["fallos"].sum() - tm["fallos"].sum())
    R["vision_general"]["cuadre_con_centro_mes"] = {"dias_centro_mes": int(cmm["dias_disco"].sum()),
                                                    "dias_dias_por_tramo": r(tm["dias_disco"].sum(), 2),
                                                    "diferencia_dias": r(dif_d, 2), "fallos_centro_mes": int(cmm["fallos"].sum()),
                                                    "fallos_dias_por_tramo": int(tm["fallos"].sum()), "diferencia_fallos": dif_f}
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": None,
                         "texto": f"Frente a centro_mes faltan {f(dif_d)} días de disco, los de celdas sin foto, y la "
                                  f"diferencia de fallos es {f(dif_f)} (reglas-transformacion §6). La tasa por centro está "
                                  f"en el informe de centro_mes y no se repite aquí."})
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": None, "texto": AVISO_EDADES})
    hipotesis_separar(R)
    return R


def analizar_fallos_detalle(raiz, ctx, t):
    """fallos_detalle: los discos de datos; los de arranque se cuentan aparte."""
    fd = t["fallos_detalle"]
    R = base_tabla("fallos_detalle", ctx)
    fd_ = ctx["fecha_datos"]
    d = fd.loc[fd["tipo_disco"] == "datos"].copy()
    spec = {"identificador": ["serial_number", "tomo"], "fecha": ["dia_fallo", "ultima_foto_anterior"],
            "temporal": ["ano", "trimestre", "mes"], "codigo": ["vault_id", "pod_id", "pod_slot_num"]}
    describir_en(R, d, spec)
    R["contexto"].update({"que_es_una_fila": ctx["salida"]["fallos_detalle"]["que_es_una_fila"],
                          "clave": ["serial_number", "dia_fallo"], "granularidad": "un fallo", "reglas": "reglas-transformacion.md §4",
                          "periodo": {"desde": limpio(fd["dia_fallo"].min()), "hasta": limpio(fd["dia_fallo"].max())},
                          "poblacion": "discos de datos; los de arranque se cuentan aparte (reglas-negocio §3)"})
    R["vision_general"].update({"fallos": int(len(fd)), "datos": int(len(d)), "arranque": int((fd["tipo_disco"] == "arranque").sum()),
                                "discos": int(d["serial_number"].nunique()),
                                "por_periodo": d["periodo"].value_counts().to_dict()})
    d["uno"] = 1
    d["sin_aviso_n"] = es_valor(d["sin_aviso"], True)
    d["con_anterior_n"] = es_valor(d["hay_dia_anterior"], True)
    d["en_garantia_n"] = es_valor(d["en_garantia"], True)
    d["sin_objetivo_n"] = es_valor(d["objetivo_de_alguna_foto"], False)
    anos = sorted(int(a) for a in d["ano"].unique())
    completos = [a for a in anos if ano_completo(a, fd_)]
    for nombre, num, den, dims in (("parte sin aviso", "sin_aviso_n", "con_anterior_n", (FAB, CAP, "ano")),
                                   ("parte en garantía", "en_garantia_n", "uno", (FAB, CAP, "ano"))):
        res = {"nombre": nombre, "numerador": num, "denominador": den,
               "total": {"num": int(d[num].sum()), "den": int(d[den].sum()), "pct": r(parte(d[num].sum(), d[den].sum()), 4)},
               "por": {}}
        for dim in dims:
            sep = separar(d, dim, num, den, 100, MIN_FILAS_CATEGORIA, orden=completos if dim == "ano" else None)
            res["por"][dim] = sep
            if dim in (FAB, "ano"):
                filas = [x for x in sep["total"] if x["comparada"]]
                if len(filas) >= 2 and sep["par"]:
                    a = next(x for x in filas if x["categoria"] == sep["par"][0])
                    b = next(x for x in filas if x["categoria"] == sep["par"][1])
                    texto = (f"{nombre.capitalize()} por {dim}: {f(a['valor'], 1)} % en {et(a['categoria'])} "
                             f"({f(a['num'])} de {f(a['den'])}) frente a {f(b['valor'], 1)} % en {et(b['categoria'])} "
                             f"({f(b['num'])} de {f(b['den'])}).")
                    nuevo_hallazgo(R, texto, sep["alertas"], a["valor"], int(a["den"] + b["den"]), [num, dim],
                                   [x for x in (FAB, CAP) if x != dim], f"parte-{nombre}-{dim}", f"{nombre} por {dim}", "puntos")
                if filas:
                    filas.sort(key=lambda x: str(x["categoria"]))
                    R["graficos"].append({"id": f"parte-{nombre}-{dim}", "seccion": "categoricas", "tipo": "barras",
                                          "titulo": f"{nombre.capitalize()} por {dim}: de {f(min(x['valor'] for x in filas), 1)} % "
                                                    f"a {f(max(x['valor'] for x in filas), 1)} %",
                                          "subtitulo": f"{nombre.capitalize()}, en %, con la base (n)"
                                                       + (". " + AVISO_EDADES if dim == FAB else ""),
                                          "fuente": f"{f(res['total']['den'])} fallos de discos de datos",
                                          "datos": {"etiquetas": [et(x["categoria"]) for x in filas],
                                                    "series": {"parte": [x["valor"] for x in filas]},
                                                    "n": [int(x["den"]) for x in filas], "decimales": 1, "ordenar": dim != "ano"}})
        R["partes"].append(res)
    mes = d.groupby(pd.to_datetime(d["dia_fallo"]).dt.to_period("M").dt.to_timestamp())["uno"].sum()
    comp = [fin_de_periodo(x, "mes") <= fd_ for x in mes.index]
    serie_y_grafico(R, "fallos de discos de datos por mes", list(mes.index), list(mes.to_numpy()), "mes", "flujo", comp)
    R["temporal"]["por_ano"] = [{"ano": int(a), "fallos": int(n), "completo": ano_completo(a, fd_),
                                 "coste_fallos_usd": r(d.loc[d["ano"] == a, "coste_fallo_usd"].sum(), 2),
                                 "coste_fallos_garantia_usd": r(d.loc[d["ano"] == a, "coste_fallo_garantia_usd"].sum(), 2)}
                                for a, n in d.groupby("ano")["uno"].sum().items()]
    R["temporal"]["periodos_incompletos"] = [{"periodo": str(a), "motivo": "año que acaba después de la fecha de los datos"}
                                             for a in anos if not ano_completo(a, fd_)]
    ini = ctx["inicio_sitio"]
    ds = d.loc[pd.to_datetime(d["dia_fallo"]) >= ini]
    R["vision_general"]["desde_sitio"] = {"fallos": int(len(ds)), "sin_centro": int(ds["datacenter"].isna().sum()),
                                          "sin_tomo": int(ds["tomo"].isna().sum()), "tomos": int(ds["tomo"].nunique()),
                                          "coinciden_con_anterior": int(es_valor(ds["coincide_con_anterior"], True).sum())}
    sin_obj = int(d["sin_objetivo_n"].sum())
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": "transformacion-datos, exclusiones",
                         "texto": f"{f(sin_obj)} fallos de discos de datos no son objetivo de ninguna foto de fotos_riesgo; "
                                  f"{f(int(len(d) - d['con_anterior_n'].sum()))} no tienen el día anterior y salen del indicador "
                                  f"de fallos sin aviso."})
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": None,
                         "texto": "Fuera de Seagate, avisar depende de tres contadores: la parte sin aviso no se compara "
                                  "entre fabricantes (reglas-negocio §3). " + AVISO_EDADES})
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": None,
                         "texto": f"El sitio solo consta desde el {ini.strftime('%d/%m/%Y')}: {f(len(ds))} fallos de discos "
                                  f"de datos, {R['vision_general']['desde_sitio']['sin_tomo']} sin tomo. Los fallos agrupados "
                                  f"por tomo son del paso 5."})
    hipotesis_separar(R)
    return R


def analizar_vida_discos(raiz, ctx, t):
    """vida_discos: cómo acaba cada disco de datos, sus altas y bajas por mes; sin supervivencia (paso 5)."""
    vd, dm = t["vida_discos"], t["dim_modelo"]
    R = base_tabla("vida_discos", ctx)
    fd_ = ctx["fecha_datos"]
    describir_en(R, vd, {"identificador": ["serial_number"],
                         "fecha": ["primera_aparicion", "ultima_foto", "primer_fallo", "fecha_fin"]})
    R["contexto"].update({"que_es_una_fila": ctx["salida"]["vida_discos"]["que_es_una_fila"], "clave": ["serial_number"],
                          "granularidad": "un disco de datos", "reglas": "reglas-transformacion.md §5",
                          "periodo": {"desde": limpio(vd["primera_aparicion"].min()), "hasta": limpio(vd["fecha_fin"].max())}})
    d = con_dim(vd, dm)
    for ev in sorted(d["evento"].dropna().unique()):
        d[f"ev_{ev}"] = (d["evento"] == ev).astype(int)
    d["uno"] = 1
    R["vision_general"].update({"discos": int(len(d)), "por_evento": d["evento"].value_counts().to_dict(),
                                "desaparecen_avisando": int(d["desaparece_avisando"].sum())})
    for ev in ("fallo", "desaparece"):
        if f"ev_{ev}" not in d.columns:
            continue
        res = {"nombre": f"parte de discos con evento «{ev}»", "por": {}}
        for dim in (FAB, CAP):
            sep = separar(d, dim, f"ev_{ev}", "uno", 100, MIN_FILAS_CATEGORIA)
            res["por"][dim] = sep
            filas = [x for x in sep["total"] if x["comparada"]]
            if len(filas) >= 2 and sep["par"] and dim == FAB:
                a = next(x for x in filas if x["categoria"] == sep["par"][0])
                b = next(x for x in filas if x["categoria"] == sep["par"][1])
                texto = (f"Acaba en «{ev}» el {f(a['valor'], 1)} % de los discos de {et(a['categoria'])} ({f(a['den'])}) y el "
                         f"{f(b['valor'], 1)} % de los de {et(b['categoria'])} ({f(b['den'])}). No es una tasa anual: mezcla "
                         f"edades y años observados.")
                nuevo_hallazgo(R, texto, sep["alertas"], a["valor"], int(a["den"] + b["den"]), ["evento", dim], [CAP],
                               "cat-evento", f"parte «{ev}» por {dim}", "puntos")
        R["partes"].append(res)
    alt = d.groupby(pd.to_datetime(d["primera_aparicion"]).dt.to_period("M").dt.to_timestamp())["uno"].sum()
    if len(alt) > 1:
        comp = [True] * len(alt)
        comp[0] = False
        serie_y_grafico(R, "altas por mes", list(alt.index), list(alt.to_numpy()), "mes", "flujo", comp)
        R["temporal"]["periodos_incompletos"] = [{"periodo": alt.index[0].strftime("%Y-%m-%d"),
                                                  "motivo": "primer mes de los datos: junta todos los discos que ya estaban"}]
    bajas = d.loc[d["evento"].isin(["fallo", "desaparece"])]
    if len(bajas):
        b = bajas.groupby([pd.to_datetime(bajas["fecha_fin"]).dt.to_period("M").dt.to_timestamp(), "evento"])["uno"].sum().unstack(fill_value=0)
        R["temporal"]["bajas_por_mes"] = [{"mes": k.strftime("%Y-%m-%d"), **{str(c): int(v) for c, v in x.items()}}
                                          for k, x in b.iterrows()]
        R["graficos"].append({"id": "tmp-bajas", "seccion": "temporal", "tipo": "linea", "ancho": "completo",
                              "titulo": f"Las bajas por mes llegan a {f(int(b.to_numpy().max()))}",
                              "subtitulo": "Discos que acaban en fallo o desaparecen, por el mes de su fecha de fin",
                              "fuente": f"{f(len(bajas))} discos", "datos": {"periodos": [nombre_mes(k) for k in b.index],
                                                                            "series": {str(c): [float(v) for v in b[c]] for c in b.columns[:4]},
                                                                            "decimales": 0}})
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": None,
                         "texto": "Un disco que desaparece se va en algún día del mes siguiente a su última foto, que no se "
                                  "sabe (reglas-transformacion §5). La supervivencia, con su censura, es del paso 5."})
    R["alertas"].append({"id": None, "tipo": "limitacion", "origen": None, "texto": AVISO_EDADES})
    hipotesis_separar(R)
    return R


# =================================================================================================================
# 9. Lo común a las seis tablas: comprobaciones, parámetros, alertas heredadas y estado
# =================================================================================================================
NOMBRES_COMPROBACIONES = ["1 Tiempo", "2 Pareto y ABC", "3 Respaldo de cada cifra", "4 Datos personales en el informe",
                          "5 Códigos sin etiqueta", "6 Reproducibilidad", "7 Correlaciones", "8 Forma de las hipótesis",
                          "9 Variables asimétricas", "10 Gráficos", "11 Series de negocio", "12 Frente al objetivo",
                          "13 Discreta o continua", "14 Texto", "15 Alta cardinalidad",
                          "16 Observaciones de la persona", "17 La tabla de estadísticos se lee", "18 Lo esperable"]


def comprobaciones(R, ctx):
    """El estado de cada comprobación de comprobaciones.md, con lo que se calculó o el dato que faltaba."""
    c = {}
    inc = R["temporal"].get("periodos_incompletos") or []
    c[1] = ("aplicada_con_resultado", f"ordenado por fecha; dos granularidades (mes o trimestre y año); periodos "
            f"incompletos: {', '.join(x['periodo'] for x in inc) or 'ninguno'}; el primer mes de las fotos es "
            f"{ctx['primer_mes_fotos']}")
    if R["pareto"]:
        c[2] = ("aplicada_con_resultado", "; ".join(f"{p['pareja']}: el {f(p.get('pct_elementos_80'), 1)} % de los elementos "
                                                     f"suma el 80 %" for p in R["pareto"] if p.get("pct_elementos_80") is not None))
    else:
        c[2] = ("no_aplica", "la tabla no tiene una magnitud que se sume por elemento fuera de lo ya descrito en otro informe")
    c[3] = ("aplicada_con_resultado", "cada hallazgo lleva su cifra, sus filas y sus columnas")
    c[4] = ("aplicada_sin_nada_relevante", "ninguna columna trae nombres, correos, teléfonos, documentos ni cuentas "
            "(reglas-negocio §9); el número de serie identifica un disco y no sale en ningún gráfico")
    cods = [t["columna"] for t in R["tipificacion"] if t["tipo"] in ("codigo", "no_prevista")]
    c[5] = (("aplicada_con_resultado", f"códigos sin etiqueta que no se interpretan: {', '.join(cods[:12])}"
             + (f" y {len(cods) - 12} más" if len(cods) > 12 else "")) if cods else
            ("aplicada_sin_nada_relevante", "todas las columnas tienen su significado en las reglas de transformación"))
    c[6] = ("aplicada_con_resultado", "versiones, fecha de ejecución, tamaño y huella en «Contexto»")
    fo = R["frente_al_objetivo"]
    if fo and fo.get("correlaciones"):
        n = len(fo["correlaciones"]["fuertes"])
        c[7] = ("aplicada_con_resultado" if n else "aplicada_sin_nada_relevante",
                f"Pearson y Spearman en {f(fo['correlaciones']['filas'])} fotos de la muestra de construcción; {n} parejas "
                f"con |r| ≥ {f(UMBRAL_CORRELACION, 1)}")
    else:
        c[7] = ("no_aplica", "esta tabla no lleva el objetivo y nadie pidió correlaciones")
    c[8] = (("aplicada_con_resultado", f"{len(R['hipotesis'])} hipótesis, cada una con lo que haría falta y las cinco "
             f"alternativas repasadas") if R["hipotesis"] else
            ("aplicada_sin_nada_relevante", "ninguna comparación cambió al separar: no hay hipótesis que escribir"))
    asim = [x["columna"] for x in R["numericas"] if "media lejos de la mediana" in x.get("senales", [])]
    c[9] = (("aplicada_con_resultado", f"muy asimétricas, que se comparan con la mediana: {', '.join(asim)}") if asim else
            ("aplicada_sin_nada_relevante", "ninguna numérica con la media lejos de la mediana"))
    c[10] = ("aplicada_con_resultado", "un eje por gráfico, color por papel, meses con su nombre, títulos calculados del "
             "dato; gráficos repetidos quitados: {rep}")
    if R["series_negocio"]:
        c[11] = ("aplicada_con_resultado", "; ".join(
            f"{s['serie']}: {s['periodos']} periodos completos, CAGR {fp(s.get('cagr_pct'))}" for s in R["series_negocio"]))
    else:
        c[11] = ("no_aplica", "no hay una magnitud agregable por periodo")
    if fo:
        c[12] = ("aplicada_con_resultado", f"solo construcción: {f(fo['n_filas'])} fotos; de la validación, solo totales")
    else:
        c[12] = ("no_aplica", "esta tabla no lleva el objetivo; se describe entera, con los dos periodos (reglas-negocio §7)")
    c[13] = ("aplicada_con_resultado", f"discreta si es entera y tiene como mucho min({LIMITE_DISCRETA}, 5 % de las filas) "
             f"valores distintos; {sum(t['tipo'] == 'discreta' for t in R['tipificacion'])} discretas y "
             f"{sum(t['tipo'] == 'continua' for t in R['tipificacion'])} continuas")
    c[14] = ("no_aplica", "no hay columnas de texto libre")
    alta = [x for x in R["categoricas"] if x["tipo"] == "alta_cardinalidad"]
    c[15] = (("aplicada_con_resultado", "; ".join(f"{x['columna']}: {x['cardinalidad']} valores, las 10 más frecuentes "
                                                  f"reúnen el {f(x['pct_10_mas_frecuentes'], 1)} %" for x in alta)) if alta else
             ("aplicada_sin_nada_relevante", f"ninguna categórica pasa de {ALTA_CARDINALIDAD} valores"))
    c[16] = ("aplicada_sin_nada_relevante", "apartado vacío: la persona escribe sus observaciones y se vuelve a ejecutar")
    sen = [f"{x['columna']} ({', '.join(x['senales'])})" for x in R["numericas"] if x.get("senales")]
    c[17] = (("aplicada_con_resultado", "; ".join(sen[:10]) + (f" y {len(sen) - 10} más" if len(sen) > 10 else ""))
             if sen else ("aplicada_sin_nada_relevante", "ninguna de las cuatro señales"))
    c[18] = (("no_aplica", "las reglas de negocio no tienen la tabla «Lo esperable»") if not ctx["lo_esperable"] else
             ("aplicada_sin_nada_relevante", "las reglas traen la tabla «Lo esperable» y este script no la mide: hay que "
              "ampliarlo"))
    R["comprobaciones"] = [{"comprobacion": NOMBRES_COMPROBACIONES[k - 1], "estado": c[k][0], "detalle": c[k][1]}
                           for k in range(1, 19)]


def parametros():
    """Los parámetros con que se ejecutó: los de parametros.md y los umbrales que el método no fija."""
    return [
        {"nombre": "numérica discreta", "valor": f"entera y con como mucho min({LIMITE_DISCRETA}, 5 % de las filas) valores distintos",
         "origen": "por defecto (parametros.md)"},
        {"nombre": "filas mínimas para comparar una categoría frente al objetivo", "valor": MIN_FILAS_CATEGORIA,
         "origen": "por defecto (parametros.md)"},
        {"nombre": "alta cardinalidad", "valor": f"más de {ALTA_CARDINALIDAD} valores distintos", "origen": "por defecto"},
        {"nombre": "las más frecuentes en alta cardinalidad", "valor": MAS_FRECUENTES, "origen": "por defecto"},
        {"nombre": "texto muy corto", "valor": f"menos de {TEXTO_CORTO} caracteres", "origen": "por defecto; no hay texto libre"},
        {"nombre": "diagrama de caja", "valor": "no se dibuja ninguno: todas las tablas pasan de 1.000 filas o el "
         "histograma ya lo enseña", "origen": "por defecto"},
        {"nombre": "parte con que se cruza el objetivo", "valor": CONSTRUCCION, "origen": "reglas-negocio §7, la partición por fecha"},
        {"nombre": "muestra fija de fotos", "valor": f"{TAM_MUESTRA} fotos, semilla {SEMILLA}", "origen": "petición y criterio de este análisis"},
        {"nombre": "valores distintos que se siguen por columna al leer por bloques", "valor": TOPE_DISTINTOS,
         "origen": "criterio de este análisis, por encima del límite de discreta y del de alta cardinalidad"},
        {"nombre": "diferencia frente al objetivo", "valor": f"|2·AUC − 1|; se dibujan las de {UMBRAL_DIBUJAR} o más; "
         f"posible fuga desde {UMBRAL_FUGA}", "origen": "criterio de este análisis, fijado antes de calcular"},
        {"nombre": "cambio al separar", "valor": f"se invierte, o la diferencia del grupo es menos de 1/{FACTOR_TAMANO:g} o más de "
         f"{FACTOR_TAMANO:g} veces la del total", "origen": "criterio de este análisis, fijado antes de calcular"},
        {"nombre": "días mínimos para comparar una tasa anual", "valor": MINIMO_DIAS, "origen": "reglas-negocio §7, mínimo del ranking"},
        {"nombre": "fallos mínimos para concluir sobre un año de edad", "valor": MINIMO_FALLOS_EDAD, "origen": "reglas-negocio §7, cuestión 009"},
        {"nombre": "señales de la tabla de estadísticos", "valor": f"media y mediana a más de {UMBRAL_MEDIA_MEDIANA} desviaciones; "
         f"máximo / mínimo positivo de {f(UMBRAL_ORDENES)} o más", "origen": "criterio de este análisis"},
        {"nombre": "correlación fuerte", "valor": f"|r| ≥ {UMBRAL_CORRELACION}", "origen": "criterio de este análisis"},
        {"nombre": "anomalía en una serie de volumen", "valor": f"un periodo fuera de {ANOMALIA_BAJA} a {ANOMALIA_ALTA} veces la "
         f"mediana de los {VECINOS} periodos de cada lado", "origen": "criterio de este análisis"},
        {"nombre": "media móvil", "valor": f"{MOVIL_MES} meses o {MOVIL_TRIMESTRE} trimestres", "origen": "criterio de este análisis"},
    ]


def alertas_heredadas(R, ctx):
    """Las alertas de calidad y corrección que tocan a la tabla, con su origen."""
    if R["tabla"] == "fotos_riesgo" and ctx.get("calidad"):
        for x in ctx["calidad"].get("riesgos_modelo", []):
            if "fotos" in x.get("tabla", ""):
                R["alertas"].append({"id": None, "tipo": "heredada", "origen": "calidad-datos, riesgos_modelo",
                                     "texto": f"{x['columna']}: {x['riesgo']}"})
    if ctx.get("correccion"):
        for x in ctx["correccion"].get("sin_cambios", []):
            if x.get("problema_calidad") in ("C-20", "C-26") and R["tabla"] in ("fotos_riesgo", "fallos_detalle"):
                R["alertas"].append({"id": None, "tipo": "heredada", "origen": f"correccion-datos {x['problema_calidad']}",
                                     "texto": f"{x['resultado_calidad']}: {x['motivo']}"})


def cerrar(R, ctx):
    """Numera, añade lo común y decide estado, riesgo, resumen y siguiente paso con lo calculado."""
    alertas_heredadas(R, ctx)
    for an in R["anomalias"]:
        R["alertas"].append({"id": None, "tipo": "anomalia", "origen": None,
                             "texto": f"Anomalía concentrada en {an['serie']}: el periodo que empieza el "
                                      f"{an['periodo']} da {f(an['valor'])}, {f(an['razon'], 2)} veces la mediana de sus "
                                      f"vecinos; es el {f(an['parte_del_total_pct'], 2)} % del total.",
                             "preguntas": anomalia_preguntas()})
    comprobaciones(R, ctx)
    R["parametros"] = parametros()
    R["teoria"] = TEORIA
    previas = ctx["observaciones_previas"].get(R["tabla"]) or []
    R["observaciones"] = previas
    for i, h in enumerate(R["hallazgos"], 1):
        h["id"] = f"H-{i:02d}"
    for i, a in enumerate(R["alertas"], 1):
        a["id"] = f"A-{i:02d}"
    for i, h in enumerate(R["hipotesis"], 1):
        h["id"] = f"Hi-{i:02d}"
    anomala = any(a["tipo"] == "anomalia" for a in R["alertas"])
    fuga = any(a["tipo"] == "posible_fuga" for a in R["alertas"])
    if anomala:
        R["siguiente_paso"] = "volver_a_limpiar"
    elif R["tabla"] == "fotos_riesgo":
        R["siguiente_paso"] = "hace_falta_modelar"
    else:
        R["siguiente_paso"] = "con_esto_basta"
    if not previas:
        R["pendientes"].append({"id": "P-01", "tabla": R["tabla"], "columna": None,
                                "pregunta": "Observaciones de la persona sobre este exploratorio (comprobación 16)",
                                "opciones": ["escribirlas en «observaciones» de este JSON y volver a ejecutar", "ninguna"]})
    R["entradas"] = [{"ruta": f"data/processed/{t}.parquet", "sha256": ctx["huellas_antes"][t],
                      "filas": ctx["salida"][t]["filas"], "columnas": ctx["salida"][t]["columnas"]}
                     for t in ctx["entradas_por_tabla"][R["tabla"]]]
    R["versiones"] = ctx["versiones"]
    R["datos_personales_texto"] = ctx["datos_personales"]
    estado = "AVISO" if R["pendientes"] else "OK"
    riesgo = "medio" if (anomala or fuga or any(a["tipo"] == "separar" for a in R["alertas"])) else "bajo"
    R["resultado"] = {
        "estado": estado, "riesgo": riesgo,
        "resumen": f"{f(R['vision_general'].get('filas', 0))} filas descritas: {len(R['hallazgos'])} hallazgos, "
                   f"{len(R['alertas'])} alertas y {len(R['hipotesis'])} hipótesis. "
                   + ("La validación solo da totales." if R["tabla"] == "fotos_riesgo" else "Los dos periodos, enteros."),
        "artefactos": [f"informes/analisis-exploratorio__{R['tabla']}.json", f"informes/analisis-exploratorio__{R['tabla']}.html"],
        "siguiente": {"hace_falta_modelar": "paso 5: preparacion-modelo y preselección con fotos_riesgo",
                      "con_esto_basta": "paso 5: los bloques del plan de la analítica con esta tabla",
                      "volver_a_limpiar": "revisar la anomalía concentrada con calidad-datos antes de interpretar ese periodo",
                      "falta_un_dato": "el dato que falta"}[R["siguiente_paso"]]}


# =================================================================================================================
# 10. Gráficos e informe HTML (las cifras salen del diccionario, que es el JSON)
# =================================================================================================================
def dibujar(g):
    """Dibuja un gráfico con las piezas comunes a partir de su especificación del JSON."""
    d = g["datos"]
    if g["tipo"] == "histograma":
        bordes = np.array(d["bordes"], dtype=float)
        medios = np.sqrt(bordes[:-1] * bordes[1:]) if d["log"] else (bordes[:-1] + bordes[1:]) / 2
        valores = np.repeat(medios, d["cuentas"])
        paso = (bordes[-1] - bordes[0]) / max(len(bordes) - 1, 1)
        dec = 0 if paso >= 5 and bordes[0] >= 1 else (1 if paso >= 0.5 else 2)
        return graficos.histograma(valores.tolist(), bordes=d["bordes"], log=d["log"], decimales=dec,
                                   etiqueta_x=d.get("etiqueta_x", ""))
    if g["tipo"] == "barras":
        return graficos.barras_ordenadas(d["etiquetas"], d["series"], decimales=d.get("decimales", 0),
                                         n=d.get("n"), ordenar=d.get("ordenar", True), medida=g["titulo"][:40])
    if g["tipo"] == "linea":
        return graficos.linea_tiempo(d["periodos"], d["series"], decimales=d.get("decimales", 0), ancho=1000)
    if g["tipo"] == "columnas":
        return graficos.columnas_tiempo(d["periodos"], d["valores"], decimales=d.get("decimales", 0))
    if g["tipo"] == "curva":
        return graficos.curva_acumulada(d["valores"])
    raise ValueError(f"tipo de gráfico desconocido: {g['tipo']}")


def dibujar_todos(R):
    """Dibuja cada gráfico; el que una pieza rechaza o repite otro se apunta en el JSON y no se enseña."""
    svgs, vistos = {}, {}
    for g in R["graficos"]:
        try:
            svg = dibujar(g)
        except (ValueError, TypeError) as e:
            R["graficos_no_dibujados"].append({"id": g["id"], "motivo": str(e)})
            continue
        h = hashlib.sha256(svg.encode("utf-8")).hexdigest()
        if h in vistos:
            R["graficos_no_dibujados"].append({"id": g["id"], "motivo": f"igual que {vistos[h]}"})
            continue
        vistos[h] = g["id"]
        svgs[g["id"]] = svg
    rep = [x["id"] for x in R["graficos_no_dibujados"] if x["motivo"].startswith("igual que")]
    for c in R["comprobaciones"]:
        if c["comprobacion"].startswith("10 "):
            c["detalle"] = c["detalle"].replace("{rep}", ", ".join(rep) or "ninguno")
            if R["graficos_no_dibujados"]:
                c["detalle"] += f"; {len(R['graficos_no_dibujados'])} gráficos no dibujados, con su motivo en el JSON"
    return svgs


def e(x):
    """Escapa un texto para el HTML."""
    return html.escape(str(x))


def tabla_html(cabeceras, filas, numeros=()):
    """Tabla HTML con las cifras a la derecha."""
    th = "".join(f'<th class="num">{e(c)}</th>' if i in numeros else f"<th>{e(c)}</th>" for i, c in enumerate(cabeceras))
    trs = "".join("<tr>" + "".join(f'<td class="num">{e(v)}</td>' if i in numeros else f"<td>{e(v)}</td>"
                                   for i, v in enumerate(fila)) + "</tr>" for fila in filas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def bloque_grafico(g, svgs):
    """Un gráfico con su título, subtítulo y fuente."""
    if g["id"] not in svgs:
        return ""
    return (f'<div class="grafico"><p class="g-titulo">{e(g["titulo"])}</p><p class="g-subtitulo">{e(g["subtitulo"])}</p>'
            f'{svgs[g["id"]]}<p class="g-fuente">Fuente: {e(g["fuente"])}</p></div>')


def rejilla(graf, svgs):
    """Gráficos de dos en dos; los de ancho completo, solos."""
    out, fila = [], []
    for g in graf:
        b = bloque_grafico(g, svgs)
        if not b:
            continue
        if g.get("ancho") == "completo":
            out.append(b)
        else:
            fila.append(b)
            if len(fila) == 2:
                out.append('<div class="fila-bloque"><div class="fila">' + "".join(fila) + "</div></div>")
                fila = []
    if fila:
        out.append('<div class="fila-bloque"><div class="fila">' + "".join(fila) + "</div></div>")
    return "".join(out)


def vista_grupos_html(sep, unidad_dec=2):
    """Tabla de la vista por grupos de una comparación que cambia al separar: las dos categorías comparadas."""
    if not sep.get("par") or not sep.get("alertas"):
        return ""
    a, b = sep["par"]
    filas = []
    tot = {x["categoria"]: x for x in sep["total"]}
    filas.append(["total", f(tot[a]["valor"], unidad_dec), f(tot[b]["valor"], unidad_dec)])
    for g, vista in sep["por_grupo"].items():
        for valor, fs in vista.items():
            v = {x["categoria"]: x for x in fs}
            fa, fb = v.get(a), v.get(b)
            filas.append([f"{g} = {valor}", f(fa["valor"], unidad_dec) if fa and fa["comparada"] else "no se compara",
                          f(fb["valor"], unidad_dec) if fb and fb["comparada"] else "no se compara"])
    return (f"<p>Vista por grupos de {e(sep['dimension'])}: {e(et(a))} frente a {e(et(b))}.</p>"
            + tabla_html(["grupo", et(a), et(b)], filas, (1, 2)))


def informe_html(R, svgs):
    """El informe HTML con los apartados de plantilla_informe.md, en su orden, a partir del diccionario."""
    css = CSS.read_text(encoding="utf-8")
    graf = R["graficos"]
    p = []
    p.append(f"<h1>Análisis exploratorio de datos · {e(R['tabla'])}</h1>")
    # Resumen ejecutivo: de los hallazgos, las alertas y el siguiente paso, sin nada que no esté en el informe
    p.append("<h2>Resumen ejecutivo</h2><ul>")
    for h in R["hallazgos"][:3]:
        p.append(f"<li>{e(h['texto'])}</li>")
    for a in [a for a in R["alertas"] if a["tipo"] in ("posible_fuga", "anomalia", "separar")][:2]:
        p.append(f"<li>{e(a['texto'])}</li>")
    p.append(f"<li>Siguiente paso: {e(R['resultado']['siguiente'])}.</li></ul>")
    # Contexto
    cx, vg = R["contexto"], R["vision_general"]
    p.append("<h2>Contexto</h2>")
    p.append(f"<p>Una fila es {e(cx.get('que_es_una_fila'))}, con clave {e(', '.join(cx.get('clave', [])))}. "
             f"La tabla tiene {f(vg.get('filas'))} filas y {f(vg.get('columnas'))} columnas. Periodo: de "
             f"{e((cx.get('periodo') or {}).get('desde'))} a {e((cx.get('periodo') or {}).get('hasta'))}. "
             f"Fecha de los datos: {e(R['fecha_datos'])}. Reglas: {e(cx.get('reglas'))}.</p>")
    if cx.get("poblacion"):
        p.append(f"<p>Población: {e(cx['poblacion'])}.</p>")
    if R.get("muestra"):
        m = R["muestra"]
        p.append(f"<p>Muestra fija: {f(m['tamano'])} fotos de {f(m['de'])}, con semilla {m['semilla']}. {e(m['nota'])}.</p>")
    v = R["versiones"]
    p.append(f"<p>Reproducibilidad: ejecutado el {e(R['fecha_ejecucion'])} con Python {e(v['python'])}, pandas {e(v['pandas'])}, "
             f"numpy {e(v['numpy'])}, pyarrow {e(v['pyarrow'])} y matplotlib {e(v['matplotlib'])}. Fichero de "
             f"{f(R['dataset']['bytes'])} bytes, huella {e(R['dataset']['sha256'])}.</p>")
    p.append("<p>Teoría del manual aplicada:</p><ul>" + "".join(f"<li>{e(x)}</li>" for x in R["teoria"]) + "</ul>")
    # Visión general
    p.append("<h2>Visión general</h2>")
    filas = [[k, f(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else x]
             for k, x in vg.items() if not isinstance(x, (dict, list))]
    p.append(tabla_html(["medida", "valor"], filas, (1,)))
    p.append(tabla_html(["tipo de columna", "columnas"], [[k, x] for k, x in vg.get("tipos", {}).items()], (1,)))
    if R["tabla"] == "modelo_trimestre":
        pa_ = R["cifras_para_siguiente"]["por_ano"]
        p.append("<p>Por año, la base de las preguntas 1 a 3 y del informe ejecutivo:</p>")
        p.append(tabla_html(["año", "días de disco", "fallos", "tasa anual", "coste de los fallos (USD)",
                             "con garantía (USD)", "completo"],
                            [[x["ano"], f(x["dias_disco"]), f(x["fallos"]), fp(x["tasa_anual_pct"]),
                              f(x["coste_fallos_usd"], 2), f(x["coste_fallos_garantia_usd"], 2), "sí" if x["completo"] else "no"]
                             for x in pa_], (1, 2, 3, 4, 5)))
        it = R["cifras_para_siguiente"]["inicio_trimestre"]
        p.append("<p>Discos de datos el primer día de cada trimestre (inicio_trimestre):</p>")
        p.append(tabla_html(["trimestre", "discos"], [[f"{x['ano']} T{x['trimestre']}", f(x["discos"])] for x in it], (1,)))
        dm_ = vg["dim_modelo"]
        p.append(f"<p>dim_modelo: {dm_['modelos']} modelos ({', '.join(f'{k}: {x}' for k, x in dm_['por_tipo'].items())}). "
                 f"Sin precio: {e(', '.join(dm_['sin_precio']) or 'ninguno')}.</p>")
        cu = vg["cuadre_con_fallos_detalle"]
        p.append("<p>Segunda vía: los fallos y el coste por año, sacados de fallos_detalle.</p>")
        p.append(tabla_html(["año", "fallos aquí", "fallos en fallos_detalle", "coste aquí", "coste en fallos_detalle", "iguales"],
                            [[x["ano"], f(x["fallos_modelo_trimestre"]), f(x["fallos_fallos_detalle"]),
                              f(x["coste_modelo_trimestre"], 2), f(x["coste_fallos_detalle"], 2), "sí" if x["iguales"] else "no"]
                             for x in cu], (1, 2, 3, 4)))
    # Numéricas
    p.append("<h2>Variables numéricas</h2>")
    if R["numericas"]:
        p.append(tabla_html(["columna", "tipo", "conteo", "vacíos", "media", "mediana", "desviación", "mínimo", "p25",
                             "p75", "máximo", "señales"],
                            [[x["columna"], x["tipo"], f(x["conteo"]), f(x["nulos"]), f(x["media"], 2), f(x["mediana"], 2),
                              f(x["desviacion"], 2), f(x["minimo"], 2), f(x["p25"], 2), f(x["p75"], 2), f(x["maximo"], 2),
                              "; ".join(x.get("senales", [])) or "ninguna"] for x in R["numericas"]],
                            tuple(range(2, 11))))
        p.append(f"<p class=\"fuente\">Base: {e(R['numericas'][0].get('base', 'todas las filas'))}.</p>")
    p.append(rejilla([g for g in graf if g["seccion"] == "numericas"], svgs))
    # Categóricas, tasas y Pareto
    p.append("<h2>Variables categóricas</h2>")
    if R["categoricas"]:
        p.append(tabla_html(["columna", "tipo", "valores", "vacíos", "dominante", "% dominante", "% de las 10 más frecuentes"],
                            [[x["columna"], x["tipo"], f(x["cardinalidad"]), f(x["nulos"]), et(x["dominante"]),
                              f(x["pct_dominante"], 1), f(x["pct_10_mas_frecuentes"], 1)] for x in R["categoricas"]],
                            (2, 3, 5, 6)))
    p.append(rejilla([g for g in graf if g["seccion"] == "categoricas"], svgs))
    for t in R["tasas"]:
        filas = [[et(x["categoria"]), f(x["num"]), f(x["den"]), fp(x["valor"]) if x["comparada"] else "no se compara"]
                 for x in t["total"]]
        p.append(f"<p>Tasa anual de fallo por {e(t['nombre'])}, con su base:</p>")
        p.append(tabla_html([t["dimension"], "fallos", "días de disco", "tasa anual"], filas, (1, 2, 3)))
        p.append(vista_grupos_html(t))
    for t in R["partes"]:
        if "filas" in t:
            p.append(f"<p>{e(t['nombre'].capitalize())}:</p>")
            p.append(tabla_html(["categoría", "fallos y desaparecen avisando", "días de disco", "tasa anual"],
                                [[x["categoria"], f(x["num"]), f(x["den"]), fp(x["valor"]) if x["comparada"] else "no se compara"]
                                 for x in t["filas"]], (1, 2, 3)))
        for dim, sep in t.get("por", {}).items():
            p.append(vista_grupos_html(sep, 1))
    if R["pareto"]:
        p.append("<p>Concentración (Pareto y ABC). Es volumen, no un ranking por tasa:</p>")
        p.append(tabla_html(["pareja", "elementos", "% de elementos que suma el 80 %", "A", "B", "C"],
                            [[x["pareja"], x["elementos"], f(x.get("pct_elementos_80"), 1),
                              *[f"{x['clases'][c]['elementos']} ({f(x['clases'][c]['parte_pct'], 1)} %)" if x.get("clases") else "sin dato"
                                for c in ("A", "B", "C")]] for x in R["pareto"]], (1, 2)))
    # Temporal
    p.append("<h2>Análisis temporal</h2>")
    inc = R["temporal"].get("periodos_incompletos") or []
    p.append(f"<p>Periodos incompletos: {e(', '.join(x['periodo'] + ' (' + x['motivo'] + ')' for x in inc) or 'ninguno')}. "
             f"El primer mes de las fotos es {e(R['_primer_mes'])}.</p>")
    p.append(rejilla([g for g in graf if g["seccion"] == "temporal"], svgs))
    if R["series_negocio"]:
        p.append(tabla_html(["serie", "periodos completos", "pendiente por periodo", "R² lineal", "crecimiento exponencial",
                             "R² exponencial", "CAGR", "años completos"],
                            [[s["serie"], s["periodos"], f((s.get("tendencia_lineal") or {}).get("pendiente_por_periodo"), 1),
                              f((s.get("tendencia_lineal") or {}).get("r2"), 3),
                              fp((s.get("tendencia_exponencial") or {}).get("crecimiento_por_periodo_pct")),
                              f((s.get("tendencia_exponencial") or {}).get("r2"), 3), fp(s.get("cagr_pct")),
                              ", ".join(str(a) for a in s.get("anos_completos", []))] for s in R["series_negocio"]],
                            (1, 2, 3, 4, 5, 6)))
    sep = R["temporal"].get("construccion_por_ano")
    if sep:
        p.append(tabla_html(["año", "fotos", "fallan en 30 días", "parte"],
                            [[x["categoria"], f(x["den"]), f(x["num"]), fp(x["valor"], 3)] for x in sorted(sep["total"], key=lambda x: x["categoria"])],
                            (1, 2, 3)))
        p.append(vista_grupos_html(sep, 3))
    # Frente al objetivo
    p.append("<h2>Frente al objetivo</h2>")
    fo = R["frente_al_objetivo"]
    if not fo:
        p.append("<p>No aplica: esta tabla no lleva el objetivo. Se describe entera, con los dos periodos, porque la parte "
                 "analítica usa todos los datos de trabajo (reglas-negocio §7).</p>")
    else:
        p.append(f"<p>Con las {f(fo['n_filas'])} fotos de construcción, {f(fo['n_objetivo_1'])} con objetivo 1: falla en "
                 f"30 días el {fp(fo['parte_pct'], 3)}. Esta parte de fotos que fallan en 30 días no es la tasa anual de "
                 f"fallo. Una categoría con menos de {MIN_FILAS_CATEGORIA} fotos no se compara.</p>")
        p.append(rejilla([g for g in graf if g["seccion"] == "objetivo"], svgs))
        p.append(tabla_html(["variable", "grupo", "tipo", "diferencia", "posible fuga", "categorías pequeñas"],
                            [[v["columna"], v["grupo"], v["tipo"], f(v["diferencia"], 3), "sí" if v["posible_fuga"] else "no",
                              len(v.get("pequenas", []))] for v in fo["variables"]], (3, 5)))
        cont = [v for v in fo["variables"] if v["tipo"] == "continua"]
        if cont:
            p.append(tabla_html(["variable", "mediana si falla", "mediana si no", "lleno si falla", "lleno si no",
                                 "> 0 si falla", "> 0 si no"],
                                [[v["columna"], f(v["por_clase"]["1"]["mediana"], 2), f(v["por_clase"]["0"]["mediana"], 2),
                                  fp(v["por_clase"]["1"]["lleno_pct"], 1), fp(v["por_clase"]["0"]["lleno_pct"], 1),
                                  fp(v["por_clase"]["1"]["mayor_que_cero_pct"], 1), fp(v["por_clase"]["0"]["mayor_que_cero_pct"], 1)]
                                 for v in cont], (1, 2, 3, 4, 5, 6)))
        s = fo["sitio"]
        p.append(f"<p>El sitio entra solo con las {f(s['n_filas'])} fotos de construcción desde el {e(s['desde'])}.</p>")
        if s["variables"]:
            p.append(tabla_html(["variable", "diferencia", "categorías comparadas"],
                                [[v["columna"], f(v["diferencia"], 3), sum(c["comparada"] for c in v["categorias"])]
                                 for v in s["variables"]], (1, 2)))
        val = fo["validacion"]
        p.append(f"<p>Validación, solo totales: {f(val['filas'])} fotos, {f(val['fallan'])} con objetivo 1 "
                 f"({fp(val['parte_pct'], 3)}).</p>")
        p.append(tabla_html(["fabricante", "fotos", "con objetivo 1", "parte"],
                            [[x["fabricante"], f(x["filas"]), f(x["fallan"]), fp(x["parte_pct"], 3)] for x in val["por_fabricante"]],
                            (1, 2, 3)))
        ll = R["llenado"]["no_previstas"]
        fabs = sorted({k for x in ll for k in x["por_fabricante"]}, key=str)
        p.append("<p>Columnas no previstas: no se cruzan con el objetivo. Parte de fotos con la columna llena, en todas las fotos:</p>")
        p.append(tabla_html(["columna", "total"] + fabs, [[x["columna"], f(x["lleno_pct"], 1)] +
                                                          [f(x["por_fabricante"].get(k), 1) for k in fabs] for x in ll],
                            tuple(range(1, 2 + len(fabs)))))
        cl = R["cifras_para_siguiente"]["contadores_llenos_construccion"]
        p.append("<p>Contadores de avería llenos en la construcción, por fabricante (%):</p>")
        p.append(tabla_html(["columna", "fabricante", "fotos", "llenas", "%"],
                            [[x["columna"], x["fabricante"], f(x["filas"]), f(x["llenos"]), f(x["lleno_pct"], 1)] for x in cl],
                            (2, 3, 4)))
    # Hallazgos, alertas, hipótesis
    p.append("<h2>Hallazgos principales</h2>")
    if R["hallazgos"]:
        p.append("<ul>" + "".join(f"<li>{e(h['id'])}. {e(h['texto'])} Columnas: {e(', '.join(h['columnas']))}; comprobado por "
                                  f"{e(', '.join(h['dimensiones_comprobadas']))}.</li>" for h in R["hallazgos"]) + "</ul>")
        ids = {h["grafico"] for h in R["hallazgos"] if h.get("grafico") in svgs}
        if ids:
            p.append(f"<p>Cada hallazgo remite a su gráfico de arriba: {e(', '.join(sorted(ids)))}.</p>")
    else:
        p.append("<p>Ninguna comparación se sostiene al separar por fabricante y capacidad: todo pasa a alertas.</p>")
    p.append("<h2>Alertas y limitaciones</h2><ul>")
    for a in R["alertas"]:
        o = f" Origen: {a['origen']}." if a.get("origen") else ""
        q = ""
        if a.get("preguntas"):
            q = " " + "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in a["preguntas"].items()) + "."
        p.append(f"<li>{e(a['id'])}. {e(a['texto'])}{e(o)}{e(q)}</li>")
    for x in R["graficos_no_dibujados"]:
        p.append(f"<li>Gráfico {e(x['id'])} sin dibujar: {e(x['motivo'])}.</li>")
    p.append("</ul>")
    p.append("<h2>Hipótesis y preguntas abiertas</h2>")
    if R["hipotesis"]:
        p.append("<ul>" + "".join(f"<li>{e(h['id'])}. {e(h['texto'])} Haría falta {e(h['que_haria_falta'])}. Alternativas "
                                  f"repasadas: {e(', '.join(h['alternativas_repasadas']))}.</li>" for h in R["hipotesis"]) + "</ul>")
    else:
        p.append("<p>Ninguna.</p>")
    p.append("<h2>Observaciones de la persona</h2>")
    if R["observaciones"]:
        p.append("<ul>" + "".join(f"<li>{e(o.get('fecha'))}, {e(o.get('bloque'))}, {e(o.get('tipo'))}: {e(o.get('texto'))}</li>"
                                  for o in R["observaciones"]) + "</ul>")
    else:
        p.append("<p>Todavía no hay observaciones. La persona las escribe en «observaciones» del JSON y se vuelve a ejecutar.</p>")
    p.append("<h2>Comprobaciones aplicadas</h2>")
    p.append(tabla_html(["comprobación", "estado", "detalle"],
                        [[c["comprobacion"], c["estado"].replace("_", " "), c["detalle"]] for c in R["comprobaciones"]]))
    p.append("<h2>Parámetros usados</h2>")
    p.append(tabla_html(["parámetro", "valor", "de dónde sale"], [[x["nombre"], x["valor"], x["origen"]] for x in R["parametros"]]))
    p.append("<h2>Datos personales</h2>" + "".join(f"<p>{e(x)}</p>" for x in R["datos_personales_texto"]))
    p.append("<h2>Siguiente paso</h2>")
    p.append(f"<p>{e(R['siguiente_paso'].replace('_', ' ').capitalize())}: {e(R['resultado']['siguiente'])}.</p>")
    cuerpo = "\n".join(x for x in p if x)
    return ("<!doctype html>\n<html lang=\"es\"><head><meta charset=\"utf-8\">"
            f"<title>Exploratorio · {e(R['tabla'])}</title><style>{css}\nmain {{ margin-left: 0; }}</style></head>"
            f"<body><main><div class=\"pagina\">{cuerpo}</div></main></body></html>\n")


# =================================================================================================================
# 11. Ejecución
# =================================================================================================================
def escribir_json(raiz, R):
    """Escribe el JSON de una tabla sin NaN ni Infinity."""
    datos = {k: v for k, v in R.items() if not k.startswith("_")}
    texto = json.dumps(limpio(datos), ensure_ascii=False, indent=1, allow_nan=False)
    (raiz / "informes" / f"analisis-exploratorio__{R['tabla']}.json").write_text(texto, encoding="utf-8")


def escribir_estado(raiz, estado, motivo, fecha_datos):
    """Escribe los seis JSON con el estado PARADO o ERROR y su motivo (resultado.md, regla 5)."""
    (raiz / "informes").mkdir(exist_ok=True)
    for t in TABLAS:
        R = {"metodo": METODO, "version_metodo": VERSION_METODO, "script": SCRIPT, "fecha_datos": fecha_datos,
             "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"), "tabla": t, "entradas": [],
             "resultado": {"estado": estado, "riesgo": "alto", "resumen": motivo, "artefactos": [],
                           "siguiente": "resolver el motivo y volver a ejecutar"}, "pendientes": []}
        (raiz / "informes" / f"analisis-exploratorio__{t}.json").write_text(
            json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    """Lee las entradas, comprueba sus huellas, describe las seis tablas y deja sus JSON e informes."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raiz", type=Path, default=CASO, help="carpeta del caso (por defecto, la de este script)")
    raiz = ap.parse_args().raiz.resolve()
    t_inicio = time.time()
    tj = leer_json(raiz / TRANSFORMACION)
    fecha_datos = (tj or {}).get("fecha_datos")
    try:
        if tj is None:
            raise Parar(f"falta {TRANSFORMACION}")
        if tj["resultado"]["estado"] in ("PARADO", "ERROR"):
            raise Parar(f"la transformación está en {tj['resultado']['estado']}")
        if not fecha_datos:
            raise Parar("la transformación no trae fecha_datos")
        salida = {s["tabla"]: s for s in tj["salidas"]}
        faltan = [t for t in TODAS if t not in salida]
        if faltan:
            raise Parar(f"faltan en las salidas de la transformación: {', '.join(faltan)}")
        # Huellas antes: cada tabla tiene que ser la que dejó la transformación
        huellas = {t: sha256(raiz / salida[t]["ruta"]) for t in TODAS}
        distintas = [t for t in TODAS if huellas[t] != salida[t]["sha256"]]
        if distintas:
            raise Parar(f"la huella de {', '.join(distintas)} no es la de la transformación")
    except Parar as ex:
        escribir_estado(raiz, "PARADO", str(ex), fecha_datos)
        print(f"PARADO: {ex}", file=sys.stderr)
        return 1

    calidad = leer_json(raiz / CALIDAD)
    correccion = leer_json(raiz / CORRECCION)
    reglas = (raiz / REGLAS).read_text(encoding="utf-8") if (raiz / REGLAS).exists() else ""
    prot = raiz / PROTECCION
    if prot.exists():
        dp_ = leer_json(prot)
        dp_texto = [f"Protección de datos: {json.dumps(dp_, ensure_ascii=False)[:500]}"]
    else:
        dp_texto = ["No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección.",
                    "No hay datos de personas (reglas-negocio §9): el número de serie identifica un disco, no a una persona.",
                    "Este exploratorio no usa ni deja ninguna columna de datos personales."]
    previas = {}
    for t in TABLAS:
        j = leer_json(raiz / "informes" / f"analisis-exploratorio__{t}.json")
        previas[t] = (j or {}).get("observaciones") or []
    ctx = {"fecha_datos": pd.Timestamp(fecha_datos), "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
           "inicio_sitio": pd.Timestamp((tj.get("parametros") or {}).get("inicio_sitio")),
           "salida": salida, "huellas_antes": huellas,
           "bytes": {t: (raiz / salida[t]["ruta"]).stat().st_size for t in TODAS},
           "calidad": calidad, "correccion": correccion, "lo_esperable": "Lo esperable" in reglas,
           "datos_personales": dp_texto, "observaciones_previas": previas,
           "versiones": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                         "pyarrow": pa.__version__, "matplotlib": matplotlib.__version__},
           "entradas_por_tabla": {"fotos_riesgo": ["fotos_riesgo"], "fallos_detalle": ["fallos_detalle"],
                                  "vida_discos": ["vida_discos", "dim_modelo"],
                                  "dias_por_tramo": ["dias_por_tramo", "dim_modelo", "centro_mes"],
                                  "modelo_trimestre": ["modelo_trimestre", "inicio_trimestre", "dim_modelo",
                                                       "dim_precio_gb", "fallos_detalle"],
                                  "centro_mes": ["centro_mes", "dias_por_tramo", "dim_modelo"]}}
    if pd.isna(ctx["inicio_sitio"]):
        escribir_estado(raiz, "PARADO", "la transformación no trae parametros.inicio_sitio", fecha_datos)
        return 1
    try:
        # Las tablas pequeñas, enteras; fotos_riesgo, por bloques
        pequenas = {t: pd.read_parquet(raiz / salida[t]["ruta"]) for t in TODAS if t != "fotos_riesgo"}
        primer = pq.ParquetFile(raiz / salida["fotos_riesgo"]["ruta"]).read_row_group(0, columns=["fecha"])
        ctx["primer_mes_fotos"] = nombre_mes(pd.Timestamp(pc.min(primer["fecha"]).as_py()))
        resultados = [analizar_fotos(raiz, tj, ctx)]
        for funcion in (analizar_fallos_detalle, analizar_vida_discos, analizar_dias_por_tramo, analizar_modelo_trimestre,
                        analizar_centro_mes):
            resultados.append(funcion(raiz, ctx, pequenas))
        # Huellas después: los datos de entrada no cambian
        despues = {t: sha256(raiz / salida[t]["ruta"]) for t in TODAS}
        huellas_tabla = [{"tabla": t, "antes": huellas[t], "despues": despues[t], "iguales": huellas[t] == despues[t]}
                         for t in TODAS]
        for R in resultados:
            R["_primer_mes"] = ctx["primer_mes_fotos"]
            cerrar(R, ctx)
            R["huellas"] = huellas_tabla
            if not all(h["iguales"] for h in huellas_tabla):
                R["resultado"]["estado"] = "ERROR"
                R["resultado"]["resumen"] = "una tabla de entrada cambió durante la ejecución"
            R["ejecucion"] = {"segundos_total": round(time.time() - t_inicio, 1), **R.get("_tiempos", {})}
            svgs = dibujar_todos(R)
            escribir_json(raiz, R)
            (raiz / "informes" / f"analisis-exploratorio__{R['tabla']}.html").write_text(informe_html(R, svgs),
                                                                                      encoding="utf-8")
            print(f"{R['tabla']}: {R['resultado']['estado']}, {len(R['hallazgos'])} hallazgos, {len(R['alertas'])} alertas, "
                  f"{len(svgs)} gráficos")
        return 0 if all(h["iguales"] for h in huellas_tabla) else 1
    except Parar as ex:
        escribir_estado(raiz, "PARADO", str(ex), fecha_datos)
        print(f"PARADO: {ex}", file=sys.stderr)
        return 1
    except Exception as ex:
        escribir_estado(raiz, "ERROR", f"{type(ex).__name__}: {ex}", fecha_datos)
        raise


if __name__ == "__main__":
    sys.exit(main())
