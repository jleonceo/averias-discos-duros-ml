"""Indicadores de los bloques 5 a 8 del plan de la analítica del caso 68, el minicubo y lo que falta en los datos.

Método indicadores-y-analisis (paso 5, parte sin modelo), con la petición peticiones/15_indicadores_centros_avisos_tomos.md.
Calcula, comprueba y deja en informes/indicadores__centros_avisos_tomos.json (y su informe .md, generado del mismo
diccionario en la misma ejecución):

  - B5, si un centro de datos falla más por sí mismo: tasa bruta por centro y trimestre, tasa ajustada a la misma
    mezcla de modelo, año de edad y trimestre (estandarización indirecta; el trimestre, desde la petición 19), con el
    intervalo ensanchado por φ, la prueba de quitar cada modelo en sac0 y sac2, el reparto de cada centro por modelo y
    la temperatura por centro y mes.
  - B6, qué hace Backblaze con los avisos: fotos que avisan por mes, modelo y fabricante; desenlace a 90 días por tipo de
    aviso, y repetido solo con las fotos de Seagate, el único fabricante con los cinco contadores, con el recuento de
    fotos que marcan el 197 y el 198 (petición 17, peticiones/17_correcciones_del_auditor.md), cada grupo con su φ
    binomial y el intervalo de Clopper-Pearson (petición 19); fallos sin aviso, en total y por año, y lo que dice la
    ventana antes del fallo; los contadores que suben en la construcción; la serie de los 30 días antes del fallo.
  - B7, dónde está el riesgo de perder datos: tomos con k fallos en d días frente al azar, que baraja los días dentro de
    cada centro y trimestre (petición 19; el de solo centro, al lado), discos a la vez frente a la paridad supuesta, los
    peores tomos y el riesgo vivo de cada mes frente a la binomial.
  - B8, otros factores del disco: temperatura, arranques, datos escritos y datos leídos por tramos, dentro de su grupo.
  - MC, el minicubo de perfiles (nivel 1 y nivel 2), con el intervalo ensanchado por el φ de la edad, y lo que falta
    en los datos.

φ (petición 19, peticiones/19_correcciones_del_segundo_auditor.md; reglas, apartado 7) es lo que varían los fallos entre
trimestres más de lo que supone Poisson o la binomial: se calcula con los datos y nunca baja de 1.

Los días de disco de un corte que no está en el recuento se reparten con las fotos (criterio 7 de la petición). Cada cifra
lleva su segunda vía, que parte de otra tabla o de otro cálculo; si una no coincide, para con ERROR. Las comprobaciones y
las validaciones de el método se calculan; ninguna lleva el resultado escrito.

Lee data/processed/ y los JSON de informes/ de la transformación y de las peticiones 13 y 14, que no modifica.
fotos_riesgo se lee por bloques y solo con sus columnas necesarias. Depende de scripts/05_transformacion_datos.py, de
09_indicadores_discos_modelos_edad.py y de 10_indicadores_coste_prevision.py: comprueba la huella de cada tabla contra
informes/transformacion-datos.json y el estado de los JSON de los que parte. No importa ningún script.

Uso: python -W error scripts/11_indicadores_centros_avisos_tomos.py [--raiz CARPETA_DEL_CASO]
Sale con 0 si termina, con 2 si para (PARADO o ERROR) y con 1 si falla por otra causa; en los tres casos escribe el JSON.
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import calendar
import datetime as dt
import hashlib
import itertools
import json
import math
import platform
import re
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import scipy
from scipy import stats

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "assets"))
from graficos import numero  # noqa: E402  (pieza común: números a la española, redondeo como Excel)

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SCRIPT = "scripts/11_indicadores_centros_avisos_tomos.py"
PETICION = ("peticiones/15_indicadores_centros_avisos_tomos.md; B6 ampliado por "
           "peticiones/17_correcciones_del_auditor.md; B5, B6, B7 y el minicubo corregidos por "
           "peticiones/19_correcciones_del_segundo_auditor.md")
SALIDA_JSON = "informes/indicadores__centros_avisos_tomos.json"
SALIDA_MD = "informes/indicadores__centros_avisos_tomos.md"
TRANSFORMACION = "informes/transformacion-datos.json"
METODO_MD = "metodos/indicadores-y-analisis/METODO.md"
PROTECCION = "config/fuentes/proteccion-datos.json"
# JSON de los que parte la petición; si uno falta o está en PARADO o ERROR, no se calcula nada
PREVIOS = ["indicadores__discos_modelos_edad", "indicadores__coste_prevision"]
# Tablas salidas de la transformación y tablas de entrada que lee la petición
TABLAS_SALIDA = ["dim_modelo", "fotos_riesgo", "fallos_detalle", "vida_discos", "dias_por_tramo", "centro_mes"]
TABLAS_ENTRADA = ["ventanas_fallo_corregido", "recuento_diario_corregido", "calendario"]
# Columnas de fotos_riesgo que hacen falta (petición, ALCANCE: por bloques y solo las necesarias)
COL_FOTOS = ["serial_number", "fecha", "model", "edad_anos", "avisa", "smart_5_raw", "smart_187_raw", "smart_188_raw",
             "smart_197_raw", "smart_198_raw", "smart_194_raw", "smart_12_raw", "smart_241_raw", "smart_242_raw",
             "smart_9_raw", "smart_90_raw", "cambio_smart_5", "cambio_smart_187", "cambio_smart_197",
             "cambio_smart_198", "datacenter", "vault_id", "pod_slot_num", "periodo", "falla_30d"]

# Fechas: primer día de los datos, primer día con sitio y fecha de referencia (reglas, apartado 4 y §5)
FECHA_INICIO = dt.date(2020, 1, 1)
INICIO_SITIO = dt.date(2023, 7, 1)
FECHA_DATOS = dt.date(2025, 6, 30)
# El sitio cubre dos años, del 01/07/2023 al 30/06/2025 (reglas, apartado 4)
ANOS_SITIO = 2
# Mínimo para un ranking: días de disco en el año (reglas, apartado 7); fallos mínimos de un grupo o celda (petición, criterio 8;
# reglas, apartado 7, cuestión 009, para el año de edad); casos mínimos de un grupo de fotos (método, parametros.md)
MINIMO_DIAS_ANO = 50_000
MINIMO_FALLOS = 20
MINIMO_CASOS = 30
# Confianza de los intervalos (método, parametros.md; 42.6 del manual) y factor de la tasa anual en % (reglas, apartado 6)
CONFIANZA = 0.95
FACTOR_TASA = 100 * 365
# Horas de un año de edad (reglas de transformación, criterio técnico 1) y horizonte del desenlace (petición, criterio 2)
H_ANO = 8766
HORIZONTE = 90
# Contadores de avería (reglas, apartado 3); los que tienen cambio en fotos_riesgo (sin el 188, reglas de transformación §3)
CONTADORES = (5, 187, 188, 197, 198)
CONT_CAMBIO = (5, 187, 197, 198)
# El único fabricante que trae los cinco contadores: el desenlace por contador se repite solo con sus fotos (reglas, apartado 3;
# plan, bloque 6; petición 17)
FABRICANTE_CINCO = "Seagate"
# Tomos con k fallos en d días y los dos que van frente al azar (petición, criterios 3 y 4)
K_D = [(2, 7), (2, 30), (3, 7), (3, 30), (4, 7), (4, 30)]
AZAR = [(2, 30), (3, 7)]
ITERACIONES = 200
SEMILLA = 68
# Centros en los que se quita cada modelo uno a uno (petición, criterio 1; directriz 37 del auditor)
CENTROS_QUITAR = ("sac0", "sac2")
# Cuántos modelos del reparto de cada centro, cuántos peores tomos y cuántas celdas del nivel 2 (petición)
N_MODELOS_REPARTO = 5
N_TOMOS = 5
N_NIVEL2 = 10
# Tramos del bloque 8 (El responsable del caso, 18/11/2026, una nota del caso) y de la edad del minicubo (petición, criterio 9)
TRAMOS = {"temperatura": ["01_frio", "02_medio", "03_caliente"],
          "arranques": ["01_hasta_mediana", "02_hasta_doble", "03_mas_del_doble"],
          "escritos": ["01_bajo", "02_medio", "03_alto"], "leidos": ["01_bajo", "02_medio", "03_alto"]}
TOPE_EDAD = 8
DIMENSIONES = ["fabricante", "capacidad_tb", "edad", "centro", "avisa"]
ANTES = "antes_de_07_2023"
SIN_DATO = "sin dato"
# Diferencia que se admite entre dos vías en días repartidos (petición, «SEGUNDA VÍA»)
TOLERANCIA = 1e-6
# Base de las claves numéricas: meses y días caben por debajo
BASE_MES = 10 ** 3
BASE_DIA = 10 ** 5
# La palabra vetada para el conjunto de discos (El responsable del caso, 17/11; una nota del caso), partida para que el código no la lleve
VETADA = "flo" + "ta"

COMPROBACIONES = ["unidad", "minimo", "empates", "referencia", "azar_en_grupos", "pesos", "hacia_adelante",
                  "cobertura", "periodos"]
VALIDACIONES = ["planteamiento_completo", "cifras_con_poblacion", "segunda_via", "minimo_respetado",
                "con_referencia", "comprobaciones_calculadas", "reproducible", "sin_resultados_escritos",
                "raw_intacto"]
EXTRAS = ["sin_validacion", "partes_suman_total", "sin_palabra_vetada", "lado_del_azar", "phi_minimo_uno",
          "veredicto_del_intervalo"]
POBLACION = "discos de datos (dim_modelo, tipo_disco «datos»); los de arranque no entran"


class Parada(Exception):
    """Condición que para el script a propósito; lleva el estado (PARADO o ERROR) y el motivo."""

    def __init__(self, estado, motivo):
        super().__init__(motivo)
        self.estado = estado
        self.motivo = motivo


# =================================================================================================================
# 3. Utilidades
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leído por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def huellas_raw(raiz):
    """Huella de cada fichero de data/raw/, con su ruta relativa a la carpeta del caso."""
    base = raiz / "data" / "raw"
    return {str(p.relative_to(raiz)).replace("\\", "/"): sha256(p) for p in sorted(base.rglob("*")) if p.is_file()}


def r(x, d=6):
    """Número para el JSON: float redondeado; None si no se pudo calcular (nunca NaN)."""
    if x is None:
        return None
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, d)


def iso(t):
    """Fecha en ISO (AAAA-MM-DD)."""
    return pd.Timestamp(t).date().isoformat()


def nativo(x):
    """Convierte tipos de numpy y pandas a tipos de Python para el JSON; NaN pasa a None."""
    if isinstance(x, dict):
        return {str(k): nativo(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [nativo(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return r(x, 10)
    if isinstance(x, pd.Timestamp):
        return iso(x)
    return x


def mes_indice(fechas):
    """Meses desde enero del primer año de los datos: enero del primer año es 0."""
    f = pd.DatetimeIndex(fechas)
    return ((f.year - FECHA_INICIO.year) * 12 + f.month - 1).to_numpy()


def dia_indice(fechas):
    """Días desde el primer día de los datos."""
    f = pd.DatetimeIndex(fechas).astype("datetime64[ms]")
    return ((f - pd.Timestamp(FECHA_INICIO)) // pd.Timedelta(days=1)).to_numpy()


def mes_fecha(mi):
    """El primer día del mes `mi`."""
    return pd.Timestamp(FECHA_INICIO) + pd.DateOffset(months=int(mi))


def trimestre_de(fecha):
    """«2024T1»."""
    f = pd.Timestamp(fecha)
    return f"{f.year}T{(f.month - 1) // 3 + 1}"


def etiqueta_valor(x):
    """El valor de una dimensión como texto: 12.0 -> «12»."""
    if isinstance(x, (float, np.floating)) and float(x).is_integer():
        return str(int(x))
    return str(x)


# =================================================================================================================
# 4. Estadística
# =================================================================================================================
def intervalo_poisson(fallos, dias, confianza=CONFIANZA, phi=1.0):
    """Tasa anual en % y su intervalo exacto de Poisson (con chi2), con los mismos días de disco (peticiones 13 y 14).

    Con φ (petición 19, reglas, apartado 7), los fallos y los días se dividen entre φ: la tasa no cambia y el intervalo se ensancha.
    """
    a = 1 - confianza
    f = int(fallos)
    fp, dp = f / phi, float(dias) / phi
    lo = 0.0 if f == 0 else stats.chi2.ppf(a / 2, 2 * fp) / 2
    hi = stats.chi2.ppf(1 - a / 2, 2 * fp + 2) / 2
    # Con φ = 1, dp son los mismos días y la cuenta es la de antes, cifra a cifra (B8 no cambia)
    k = FACTOR_TASA / dp
    return f * (FACTOR_TASA / float(dias)), float(lo) * k, float(hi) * k


def razon_poisson(observados, esperados, confianza=CONFIANZA, phi=1.0):
    """Razón observados / esperados y el intervalo exacto de Poisson de los observados dividido por los esperados.

    Con φ (petición 19), observados y esperados entre φ: la razón no cambia.
    """
    a = 1 - confianza
    o = int(observados)
    op, e = o / phi, float(esperados) / phi
    lo = 0.0 if o == 0 else stats.chi2.ppf(a / 2, 2 * op) / 2
    hi = stats.chi2.ppf(1 - a / 2, 2 * op + 2) / 2
    return o / float(esperados), float(lo) / e, float(hi) / e


def phi_poisson(grupos, celdas, observados, esperados):
    """φ, lo que varían los fallos entre celdas más de lo que supone Poisson (petición 19; reglas, apartado 7).

    Suma observados y esperados por grupo y celda; deja fuera las celdas sin esperados; reescala los esperados de cada
    grupo para que sumen sus observados; chi2 de Pearson = suma de (o − e)² / e; grados de libertad = celdas − grupos.
    φ = chi2 / gl, y si sale menor que 1, vale 1. Es la misma cuenta que la del script 09.
    """
    t = (pd.DataFrame({"g": list(grupos), "c": list(celdas), "o": np.asarray(observados, dtype=float),
                       "e": np.asarray(esperados, dtype=float)})
         .groupby(["g", "c"], sort=True)[["o", "e"]].sum().reset_index())
    fuera = t.loc[~(t["e"] > 0)]
    t = t.loc[t["e"] > 0].copy()
    tot = t.groupby("g")[["o", "e"]].transform("sum")
    t["ee"] = t["e"] * tot["o"] / tot["e"]
    t = t.loc[t["ee"] > 0]
    chi2 = float(((t["o"] - t["ee"]) ** 2 / t["ee"]).sum())
    n, g = int(len(t)), int(t["g"].nunique())
    gl = n - g
    bruto = chi2 / gl if gl > 0 else None
    return {"phi": max(1.0, bruto) if bruto is not None else 1.0, "phi_bruto": bruto, "chi2": chi2, "celdas": n,
            "grupos": g, "gl": gl, "celdas_sin_esperados": int(len(fuera)), "fallos_sin_esperados": int(fuera["o"].sum())}


def phi_edad(dpt):
    """φ del minicubo, el de B3 del 09 calculado igual (petición 19; el 11 no lee el JSON del 09): celdas de modelo × año
    de edad × trimestre de dias_por_tramo, con el esperado de cada una = sus días × la tasa de su modelo y año de edad
    en todo el periodo; grupo, modelo y año de edad. Una fila sin días cuenta 0 días y sus fallos."""
    d = dpt.assign(dias=dpt["dias_disco"].fillna(0.0), q=dpt["mes"].dt.year * 10 + dpt["mes"].dt.quarter)
    g = d.groupby(["model", "edad_anos_cumplidos"])[["dias", "fallos"]].transform("sum")
    tasa = (g["fallos"] / g["dias"].where(g["dias"] > 0)).fillna(0.0)
    grupo = list(zip(d["model"], d["edad_anos_cumplidos"]))
    return phi_poisson(grupo, d["q"].tolist(), d["fallos"], d["dias"] * tasa)


def phi_binomial(celdas, exitos):
    """φ binomial de un grupo de fotos (petición 19, B6): por celda, fotos n y fotos que fallan x; p, la de todo el grupo;
    chi2 = suma de (x − n·p)² / (n·p·(1 − p)); gl = celdas − 1; φ = chi2 / gl, y si sale menor que 1, vale 1. Con menos
    de dos celdas, o sin ninguna foto que falle o con todas, φ = 1."""
    t = pd.DataFrame({"c": np.asarray(celdas), "x": np.asarray(exitos, dtype=float)}).groupby("c")["x"].agg(["size", "sum"])
    k = int(len(t))
    n_t, x_t = float(t["size"].sum()), float(t["sum"].sum())
    if k < 2 or x_t == 0 or x_t == n_t:
        return {"phi": 1.0, "phi_bruto": None, "chi2": None, "celdas": k, "gl": k - 1}
    p = x_t / n_t
    chi2 = float(((t["sum"] - t["size"] * p) ** 2 / (t["size"] * p * (1 - p))).sum())
    gl = k - 1
    bruto = chi2 / gl
    return {"phi": max(1.0, bruto), "phi_bruto": bruto, "chi2": chi2, "celdas": k, "gl": gl}


def intervalo_cp(si, n, phi=1.0, confianza=CONFIANZA):
    """Intervalo exacto de Clopper-Pearson de una proporción, con si/φ y n/φ (petición 19): inferior beta(α/2; x, n − x
    + 1), 0 si x = 0; superior beta(1 − α/2; x + 1, n − x), 1 si x = n."""
    a = 1 - confianza
    x, m = si / phi, n / phi
    lo = 0.0 if si == 0 else float(stats.beta.ppf(a / 2, x, m - x + 1))
    hi = 1.0 if si == n else float(stats.beta.ppf(1 - a / 2, x + 1, m - x))
    return lo, hi


def frente_a(lo, hi, referencia):
    """«por encima», «por debajo» o «no se distingue» de la referencia, por el intervalo."""
    if lo > referencia:
        return "por encima"
    if hi < referencia:
        return "por debajo"
    return "no se distingue"


# =================================================================================================================
# 5. Tramos y reparto de los días
# =================================================================================================================
def paridad(capacidad):
    """Paridad supuesta de un tomo: 3 hasta 8 TB, 4 de 10 a 14 TB y 5 desde 16 TB (reglas, apartado 4, supuesto)."""
    if capacidad <= 8:
        return 3
    if capacidad < 16:
        return 4
    return 5


def tramo_edad(edad):
    """Tramo de edad por el entero por abajo de la edad, con el último tramo desde el tope (petición, criterio 9)."""
    e = np.clip(np.floor(np.asarray(edad, dtype=float)), 0, TOPE_EDAD).astype(int)
    return np.array([f"{x:02d}_{x}" if x < TOPE_EDAD else f"{TOPE_EDAD:02d}_{TOPE_EDAD}_o_mas" for x in e])


def tramo_temperatura(diferencia):
    """0 frío (< −3), 1 medio (de −3 a < 3), 2 caliente (≥ 3), −1 sin tramo (petición, criterio 8)."""
    x = np.asarray(diferencia, dtype=float)
    t = np.where(x < -3, 0, np.where(x < 3, 1, 2))
    return np.where(np.isnan(x), -1, t).astype(np.int8)


def tramo_arranques(razon):
    """0 hasta la mediana (≤ 1), 1 hasta el doble (> 1 y ≤ 2), 2 más del doble (> 2), −1 sin tramo (criterio 8)."""
    x = np.asarray(razon, dtype=float)
    t = np.where(x <= 1, 0, np.where(x <= 2, 1, 2))
    return np.where(np.isnan(x), -1, t).astype(np.int8)


def tramo_tercio(pct):
    """0 bajo (≤ 1/3), 1 medio (≤ 2/3), 2 alto (el resto), −1 sin tramo (criterio 8)."""
    x = np.asarray(pct, dtype=float)
    t = np.where(x <= 1 / 3, 0, np.where(x <= 2 / 3, 1, 2))
    return np.where(np.isnan(x), -1, t).astype(np.int8)


def rango_por_grupo(grupo, valor):
    """Rango en tanto por uno dentro de cada grupo, con los empates en la media; el vacío queda vacío (criterio 8)."""
    s = pd.Series(np.asarray(valor, dtype=float))
    return s.groupby(np.asarray(grupo)).rank(pct=True, method="average").to_numpy()


def pesos_por_celda(foto_celda, dias_celda):
    """Cada foto pesa los días de su celda divididos entre las fotos de la celda (petición, criterio 7).

    `foto_celda` es la celda de cada foto; `dias_celda`, una serie con los días del recuento de cada celda. Una celda
    del recuento sin foto deja sus días sin repartir; una foto en una celda sin días pesa 0 y se cuenta.
    """
    celdas, inversa, n = np.unique(np.asarray(foto_celda), return_inverse=True, return_counts=True)
    dias = dias_celda.reindex(celdas).to_numpy(dtype=float)
    sin_dias = np.isnan(dias)
    pesos = np.where(sin_dias, 0.0, dias / n)[inversa]
    con_foto = dias_celda.index.isin(celdas)
    return {"pesos": pesos, "dias_sin_foto": float(dias_celda[~con_foto].sum()),
            "celdas_sin_foto": int((~con_foto).sum()), "fotos_sin_dias": int(n[sin_dias].sum()),
            "celdas_sin_foto_lista": dias_celda.index[~con_foto]}


# =================================================================================================================
# 6. Piezas de los bloques
# =================================================================================================================
def ajustada(dpt):
    """Estandarización indirecta por centro (petición 15, criterio 1; manual 5.6), con la mezcla de la petición 19.

    Tasa de cada modelo, año de edad y trimestre con todos los centros juntos, «sin dato» incluido; esperados de un
    centro = suma de sus días × esa tasa; razón = observados / esperados; tasa ajustada = razón × tasa de todos. φ se
    mide en las celdas centro × trimestre de los centros que constan (sin «sin dato»), con el centro como grupo, y el
    intervalo exacto de Poisson de la razón lleva ese φ. Una fila sin días cuenta 0 días y sus fallos. Los fallos de una
    celda de modelo, edad y trimestre sin ningún día no tienen tasa: cuentan en los observados de su centro, no pueden
    tener esperados y van contados aparte (fallos_sin_tasa). Devuelve la tabla por centro y φ.
    """
    d = dpt.assign(dias=dpt["dias_disco"].fillna(0.0), q=dpt["mes"].dt.year * 10 + dpt["mes"].dt.quarter)
    claves = ["model", "edad_anos_cumplidos", "q"]
    celda = d.groupby(claves).agg(dc=("dias", "sum"), fc=("fallos", "sum"))
    with np.errstate(divide="ignore", invalid="ignore"):
        celda["tasa"] = np.where(celda["dc"] > 0, celda["fc"] / celda["dc"], np.nan)
    d = d.join(celda["tasa"], on=claves)
    d["esp"] = np.where(d["dias"] > 0, d["dias"] * d["tasa"], 0.0)
    d["sin_tasa"] = np.where(d["tasa"].isna(), d["fallos"], 0)
    constan = d.loc[d["centro"] != SIN_DATO]
    ph = phi_poisson(constan["centro"].tolist(), constan["q"].tolist(), constan["fallos"], constan["esp"])
    c = d.groupby("centro").agg(observados=("fallos", "sum"), esperados=("esp", "sum"), dias=("dias", "sum"),
                                sin_tasa=("sin_tasa", "sum"))
    tasa_todos = FACTOR_TASA * c["observados"].sum() / c["dias"].sum()
    filas = []
    for centro, x in c.iterrows():
        rz, lo, hi = razon_poisson(x["observados"], x["esperados"], phi=ph["phi"])
        filas.append({"centro": centro, "observados": int(x["observados"]), "esperados": float(x["esperados"]),
                      "fallos_sin_tasa": int(x["sin_tasa"]),
                      "dias": float(x["dias"]), "razon": rz, "razon_desde": lo, "razon_hasta": hi,
                      "tasa_bruta_tramos": FACTOR_TASA * x["observados"] / x["dias"], "tasa_ajustada": rz * tasa_todos,
                      "tasa_todos": tasa_todos})
    return pd.DataFrame(filas).sort_values("centro", kind="mergesort").reset_index(drop=True), ph


def veredicto(centro, dias_ano, fallos, desde, hasta):
    """Lo que dice la razón de un centro: solo con el mínimo de días al año y de fallos (reglas, apartado 7; petición)."""
    if centro == SIN_DATO:
        return "aparte"
    if dias_ano < MINIMO_DIAS_ANO or fallos < MINIMO_FALLOS:
        return "sin conclusión"
    if desde > 1:
        return "falla más por sí mismo"
    if hasta < 1:
        return "falla menos"
    return "no se distingue"


def falla_en_90_merge(sc, dia_foto, sc_fallo, dia_fallo, horizonte=HORIZONTE):
    """Cierto si el disco de la foto tiene un fallo del día siguiente al día `horizonte` después (por unión)."""
    sc_fallo = np.asarray(sc_fallo)
    f = pd.DataFrame({"i": np.arange(len(sc)), "sc": np.asarray(sc), "d": np.asarray(dia_foto)})
    f = f.loc[f["sc"].isin(sc_fallo)]
    m = f.merge(pd.DataFrame({"sc": sc_fallo, "df": np.asarray(dia_fallo)}), on="sc")
    ok = (m["df"] > m["d"]) & (m["df"] <= m["d"] + horizonte)
    out = np.zeros(len(sc), dtype=bool)
    out[m.loc[ok, "i"].unique()] = True
    return out


def falla_en_90_busqueda(sc, dia_foto, sc_fallo, dia_fallo, horizonte=HORIZONTE):
    """Lo mismo por búsqueda en la lista ordenada de claves disco·día (segunda vía, otro cálculo)."""
    claves = np.sort(np.asarray(sc_fallo, dtype=np.int64) * BASE_DIA + np.asarray(dia_fallo, dtype=np.int64))
    base = np.asarray(sc, dtype=np.int64) * BASE_DIA + np.asarray(dia_foto, dtype=np.int64)
    n = np.searchsorted(claves, base + horizonte, side="right") - np.searchsorted(claves, base + 1, side="left")
    return n > 0


def desenlace_por_grupo(grupos_m, falla, falla_otra, desaparece, discos, celdas):
    """Desenlace a 90 días de cada grupo de fotos (petición 15, criterio 2), con «sin aviso» como referencia.

    `grupos_m` da la máscara de cada grupo sobre las fotos con 90 días por delante; `falla` y `falla_otra` son las dos
    cuentas de si la foto falla en 90 días, `desaparece` si desaparece, `discos` el disco de cada foto y `celdas` el
    trimestre de cada foto. Cada grupo lleva sus fotos, sus discos distintos, sigue, falla y desaparece, su φ binomial
    por trimestre de la foto y el intervalo de Clopper-Pearson de la parte que falla con fallan/φ y fotos/φ (petición 19)
    y, con 30 fotos o más, si queda por encima, por debajo o no se distingue de las fotos sin aviso del mismo conjunto.
    """
    grupos, ref = [], None
    for g, m in grupos_m.items():
        n = int(m.sum())
        fa, de = int((falla & m).sum()), int((desaparece & m).sum())
        ph = phi_binomial(celdas[m], falla[m])
        lo, hi = intervalo_cp(fa, n, ph["phi"]) if n > 0 else (None, None)
        x = {"grupo": g, "fotos": n, "discos": int(np.unique(discos[m]).size), "phi": ph, "sigue": n - fa - de, "falla": fa,
             "desaparece": de, "pct_sigue": 100 * (n - fa - de) / n if n else None, "pct_falla": 100 * fa / n if n else None,
             "pct_desaparece": 100 * de / n if n else None, "falla_desde": None if lo is None else 100 * lo,
             "falla_hasta": None if hi is None else 100 * hi, "sin_conclusion": n < MINIMO_CASOS,
             "falla_busqueda": int((falla_otra & m).sum())}
        if g == "sin aviso":
            ref = x
        grupos.append(x)
    for x in grupos:
        x["frente_a_sin_aviso"] = (None if x["grupo"] == "sin aviso" or x["sin_conclusion"] or ref is None
                                   or ref["pct_falla"] is None
                                   else frente_a(x["falla_desde"], x["falla_hasta"], ref["pct_falla"]))
    return grupos, ref


def _k_codigos(codigos, dia, k, d):
    """Tomos (por código) con k fallos en d días o menos, y la posición del fallo que completa su primer grupo."""
    orden = np.lexsort((dia, codigos))
    c, x = codigos[orden], dia[orden]
    if len(c) < k:
        return {}
    mismo = c[: len(c) - k + 1] == c[k - 1:]
    cerca_ = (x[k - 1:] - x[: len(x) - k + 1]) <= d
    pos = np.nonzero(mismo & cerca_)[0]
    out = {}
    for i in pos:
        out.setdefault(int(c[i]), int(orden[i + k - 1]))
    return out


def k_en_d(tomo, dia, k, d):
    """Tomos con dos fallos a distancia k − 1 entre sí con d días o menos (petición, criterio 3).

    Devuelve {tomo: índice del fallo i + k − 1 de su primer grupo}, que da el trimestre en que cuenta el tomo.
    """
    codigos, nombres = pd.factorize(np.asarray(tomo), sort=True)
    return {nombres[c]: i for c, i in _k_codigos(codigos, np.asarray(dia), k, d).items()}


def azar_tomos(estrato, tomo, dia, combinaciones, iteraciones, semilla):
    """Los días de los fallos se barajan entre los fallos del mismo estrato; cada fallo se queda en su tomo (criterio 4).

    El estrato es el centro y el trimestre del fallo desde la petición 19; con solo el centro, la comparación de antes.
    Devuelve {(k, d): [tomos con k fallos en d días en cada repetición]}.
    """
    rng = np.random.default_rng(semilla)
    codigos = pd.factorize(np.asarray(tomo), sort=True)[0]
    dia = np.asarray(dia)
    estrato = np.asarray(estrato)
    grupos = [np.nonzero(estrato == c)[0] for c in sorted(set(estrato.tolist()))]
    out = {kd: [] for kd in combinaciones}
    for _ in range(iteraciones):
        barajado = dia.copy()
        for idx in grupos:
            barajado[idx] = rng.permutation(dia[idx])
        for k, d in combinaciones:
            out[(k, d)].append(len(_k_codigos(codigos, barajado, k, d)))
    return out


def a_la_vez(tomo, dia, plazo):
    """Al llegar cada fallo, los fallos anteriores de su tomo que siguen rehaciéndose, más uno (petición, criterio 5).

    Un fallo anterior sigue rehaciéndose si su día más su plazo es posterior al día del que llega. Los fallos se
    ordenan por tomo y día; a igual día, por su orden de entrada.
    """
    n = len(tomo)
    f = pd.DataFrame({"i": np.arange(n), "tomo": np.asarray(tomo), "dia": np.asarray(dia), "plazo": np.asarray(plazo)})
    f = f.sort_values(["tomo", "dia", "i"], kind="mergesort")
    f["pos"] = np.arange(n)
    m = f.merge(f, on="tomo", suffixes=("", "_a"))
    m = m.loc[(m["pos_a"] < m["pos"]) & (m["dia_a"] + m["plazo_a"] > m["dia"])]
    cuenta = m.groupby("i").size()
    out = np.ones(n, dtype=int)
    out[cuenta.index.to_numpy()] += cuenta.to_numpy()
    return out


def coincidencias_bucle(tomos, dias, plazos):
    """Recuento propio, en bucle: fallos con tomo, tomos y fallos que llegan antes de que acabe de rehacerse el
    anterior de su tomo (reglas, apartado 7; segunda vía de las columnas de fallos_detalle)."""
    filas = sorted((t, d, p) for t, d, p in zip(tomos, dias, plazos) if t is not None)
    vistos, coinciden, anterior = set(), 0, None
    for t, d, p in filas:
        if anterior is not None and anterior[0] == t and d - anterior[1] < anterior[2]:
            coinciden += 1
        vistos.add(t)
        anterior = (t, d, p)
    return len(filas), len(vistos), coinciden


def riesgo_vivo(mes, tomo, avisa):
    """Cada mes, tomos con 2 o más y con 3 o más discos que avisan, frente a la binomial (petición, criterio 6).

    La probabilidad de avisar es la del mes entre las fotos con tomo; los esperados suman la de cada tomo con sus discos.
    """
    g = (pd.DataFrame({"mes": np.asarray(mes), "tomo": np.asarray(tomo), "a": np.asarray(avisa, dtype=int)})
         .groupby(["mes", "tomo"]).agg(n=("a", "size"), a=("a", "sum")).reset_index())
    out = []
    for m, x in g.groupby("mes", sort=True):
        p = x["a"].sum() / x["n"].sum()
        out.append({"mes": m, "tomos": int(len(x)), "discos": int(x["n"].sum()), "p": float(p),
                    "dos_o_mas": int((x["a"] >= 2).sum()), "tres_o_mas": int((x["a"] >= 3).sum()),
                    "esperados_dos": float(stats.binom.sf(1, x["n"], p).sum()),
                    "esperados_tres": float(stats.binom.sf(2, x["n"], p).sum())})
    return out


def grupos_factor(grupo_foto, tramo_foto, peso, grupo_fallo, tramo_fallo, minimo=MINIMO_FALLOS):
    """Un factor del bloque 8 dentro de su grupo (petición, criterio 8).

    Un grupo entra si tiene `minimo` fallos o más en cada uno de sus tres tramos; si no, sale aparte entero. Por tramo,
    en los grupos que entran: días, fallos, tasa, y razón observados / esperados, con los esperados por la tasa de su
    grupo. La foto o el fallo con grupo −1 o tramo −1 no tiene tramo.
    """
    gf, tf = np.asarray(grupo_foto), np.asarray(tramo_foto)
    gl, tl = np.asarray(grupo_fallo), np.asarray(tramo_fallo)
    peso = np.asarray(peso, dtype=float)
    con = (gf >= 0) & (tf >= 0)
    dias = pd.DataFrame({"g": gf[con], "t": tf[con], "p": peso[con]}).groupby(["g", "t"])["p"].sum()
    conl = (gl >= 0) & (tl >= 0)
    fallos = pd.DataFrame({"g": gl[conl], "t": tl[conl]}).groupby(["g", "t"]).size()
    tabla = pd.concat([dias.rename("dias"), fallos.rename("fallos")], axis=1).fillna(0.0)
    tabla = tabla.reindex(pd.MultiIndex.from_product([sorted(set(gf[gf >= 0].tolist())), [0, 1, 2]],
                                                     names=["g", "t"]), fill_value=0.0)
    piv = tabla["fallos"].unstack("t")
    entran = sorted(piv.index[(piv >= minimo).all(axis=1)].tolist())
    tg = tabla.groupby(level="g").sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        tasa_g = (tg["fallos"] / tg["dias"]).where(tg["dias"] > 0)
    t_in = tabla.loc[tabla.index.get_level_values("g").isin(entran)].reset_index()
    t_in["esp"] = t_in["dias"] * t_in["g"].map(tasa_g)
    tramos = []
    for t in (0, 1, 2):
        x = t_in.loc[t_in["t"] == t]
        dd, ff, ee = float(x["dias"].sum()), int(x["fallos"].sum()), float(x["esp"].sum())
        tasa = intervalo_poisson(ff, dd) if dd > 0 else (None, None, None)
        rz = razon_poisson(ff, ee) if ee > 0 else (None, None, None)
        tramos.append({"tramo": t, "dias": dd, "fallos": ff, "tasa": tasa[0], "tasa_desde": tasa[1],
                       "tasa_hasta": tasa[2], "esperados": ee, "razon": rz[0], "desde": rz[1], "hasta": rz[2]})
    fuera = piv.loc[~piv.index.isin(entran)]
    lista = [{"grupo": int(g), "fallos_por_tramo": [int(v) for v in fila.tolist()], "fallos": int(fila.sum())}
             for g, fila in fuera.iterrows() if fila.sum() > 0]
    return {"grupos": int(len(piv)), "grupos_entran": len(entran), "fallos_entran": int(t_in["fallos"].sum()),
            "tramos": tramos,
            "aparte": {"grupos": int(len(fuera)), "grupos_con_fallos": len(lista), "fallos": int(fuera.values.sum()),
                       "lista": lista},
            "sin_tramo": {"fallos": int((~conl).sum()), "dias": float(peso[~con].sum())},
            "entran": entran, "tasa_grupo": tasa_g, "tabla": t_in}


def codigos(valores, categorias=None):
    """Códigos enteros y etiquetas de una dimensión; con `categorias`, los de esas categorías (−1 si no está)."""
    c = pd.Categorical(valores, categories=categorias)
    return np.asarray(c.codes, dtype=np.int64), list(c.categories)


def suma_por_codigo(codigo, peso, k):
    """Suma de los pesos de cada código de 0 a k − 1, con la suma compensada de pandas.

    np.bincount suma uno detrás de otro y, con 14,6 millones de pesos, pierde milésimas de día; groupby().sum() de pandas
    compensa el error y deja la suma por debajo del 1e-6 de la petición.
    """
    return pd.Series(peso).groupby(codigo).sum().reindex(range(k), fill_value=0.0).to_numpy()


def minicubo(dims, peso, fallo_dims, minimo_dias=MINIMO_DIAS_ANO, minimo_fallos=MINIMO_FALLOS, phi=1.0):
    """Minicubo de la tasa anual por el reparto de los días (assets/23_metodo_minicubo.md; petición, criterio 9).

    Nivel 1: cada valor de cada dimensión, con sus fotos, días, fallos, tasa e intervalo. Nivel 2: cada par de
    dimensiones, todas sus celdas y las diez de tasa más alta con el mínimo de días y de fallos. La métrica es una
    razón de sumas, no una mediana. Cada intervalo lleva el φ de la edad (petición 19).
    """
    peso = np.asarray(peso, dtype=float)
    nombres = list(dims)
    cod, cat, codf = {}, {}, {}
    for dim in nombres:
        cod[dim], cat[dim] = codigos(dims[dim])
        codf[dim] = codigos(np.asarray(fallo_dims[dim]), cat[dim])[0]
        if (codf[dim] < 0).any():
            raise Parada("ERROR", f"un fallo tiene en {dim} un valor que no sale en ninguna foto")
    total_fallos = len(codf[nombres[0]])
    tasa_todos = FACTOR_TASA * total_fallos / float(peso.sum())
    n1 = []
    for dim in nombres:
        k = len(cat[dim])
        fotos = np.bincount(cod[dim], minlength=k)
        dias = suma_por_codigo(cod[dim], peso, k)
        fallos = np.bincount(codf[dim], minlength=k)
        orden = sorted(range(k), key=lambda i: str(cat[dim][i]))
        for i in orden:
            dd, ff = float(dias[i]), int(fallos[i])
            t, lo, hi = intervalo_poisson(ff, dd, phi=phi) if dd > 0 else (None, None, None)
            sin = dd < minimo_dias or ff < minimo_fallos
            n1.append({"dimension": dim, "valor": etiqueta_valor(cat[dim][i]), "fotos": int(fotos[i]), "dias": dd,
                       "fallos": ff, "tasa": t, "desde": lo, "hasta": hi, "sin_conclusion": bool(sin),
                       "frente_al_total": None if sin or lo is None else frente_a(lo, hi, tasa_todos)})
    n2 = []
    for a, b in itertools.combinations(nombres, 2):
        kb = len(cat[b])
        celda = cod[a] * kb + cod[b]
        celdaf = codf[a] * kb + codf[b]
        m = len(cat[a]) * kb
        dias = suma_por_codigo(celda, peso, m)
        fallos = np.bincount(celdaf, minlength=m)
        presentes = np.nonzero((np.bincount(celda, minlength=m) > 0) | (fallos > 0))[0]
        filas = []
        for c in presentes:
            dd, ff = float(dias[c]), int(fallos[c])
            if dd >= minimo_dias and ff >= minimo_fallos:
                filas.append((-FACTOR_TASA * ff / dd, etiqueta_valor(cat[a][c // kb]), etiqueta_valor(cat[b][c % kb]),
                              dd, ff))
        filas.sort()
        primeras = []
        for _, va, vb, dd, ff in filas[:N_NIVEL2]:
            tt, lo, hi = intervalo_poisson(ff, dd, phi=phi)
            primeras.append({"valores": [va, vb], "dias": dd, "fallos": ff, "tasa": tt, "desde": lo, "hasta": hi,
                             "tasa_todos": tasa_todos})
        n2.append({"dimensiones": [a, b], "celdas": int(len(presentes)), "celdas_que_pasan": len(filas),
                   "primeras": primeras})
    return n1, n2


# =================================================================================================================
# 7. Comprobaciones (método §4 y petición): cada una devuelve True o False calculado con lo ejecutado
# =================================================================================================================
def comp_unidad(claves):
    """La unidad se cuenta una vez: ninguna clave repetida."""
    claves = list(claves)
    return len(set(claves)) == len(claves)


def comp_empates(valores, puestos):
    """Dos entidades con el mismo valor tienen el mismo puesto o el mismo tramo."""
    por_valor = {}
    for v, p in zip(valores, puestos):
        por_valor.setdefault(v, set()).add(p)
    return all(len(ps) == 1 for ps in por_valor.values())


def comp_minimo(conclusion, dias, fallos, minimo_dias, minimo_fallos):
    """Ningún grupo con conclusión está por debajo del mínimo de días o de fallos."""
    return all((not c) or (d >= minimo_dias and f >= minimo_fallos) for c, d, f in zip(conclusion, dias, fallos))


def comp_referencia(partes, total):
    """La referencia se calcula con las mismas filas que los grupos: las partes suman el total."""
    return math.isclose(float(sum(partes)), float(total), rel_tol=1e-12, abs_tol=TOLERANCIA)


def comp_azar(grupos, esperados, intervalos, confianza=CONFIANZA):
    """Cada grupo lleva su intervalo y los que saldrían distintos por azar son grupos × (1 − confianza) (42.6)."""
    return (len(intervalos) == grupos and math.isclose(esperados, grupos * (1 - confianza))
            and all(lo is not None and hi is not None for lo, hi in intervalos))


def comp_cobertura(parte):
    """La parte cubierta está calculada y entre 0 y 1."""
    return parte is not None and 0 < parte <= 1 + 1e-12


def comp_periodos(filas, clave, parciales, campo="parcial"):
    """Cada fila de un periodo incompleto lleva su marca, y las de un periodo completo no."""
    return all(bool(f[campo]) == (f[clave] in parciales) for f in filas)


def comp_sin_validacion(periodos):
    """Ninguna foto que se cruza con falla_30d es de validación: todas de construcción (reglas, apartado 7)."""
    return len(periodos) > 0 and all(str(p).startswith("constru") for p in periodos)


def comp_partes(en_tramos, aparte, sin_tramo, total):
    """Los fallos de los tramos, más los de los grupos aparte, más los sin tramo, suman los fallos con foto."""
    return int(en_tramos) + int(aparte) + int(sin_tramo) == int(total)


def comp_phi(registros):
    """Cada φ usado es el medido, y nunca menor que 1: si el medido sale por debajo de 1, se usa 1 (petición 19)."""
    for x in registros:
        bruto = x.get("phi_bruto")
        debe = 1.0 if bruto is None else max(1.0, bruto)
        if x.get("phi") is None or x["phi"] < 1 or not math.isclose(x["phi"], debe, rel_tol=1e-12):
            return False
    return True


def comp_veredicto_centros(centros, phi):
    """El veredicto de cada centro sale de su intervalo con φ (petición 19): se rehace con la gamma desde los observados,
    los esperados y φ, y con el mínimo de días al año y de fallos."""
    for x in centros:
        if x["esperados"] > 0:
            _, lo, hi = razon_poisson(x["observados"], x["esperados"], phi=phi)
        else:
            lo, hi = math.nan, math.nan
        if x["veredicto"] != veredicto(x["centro"], x["dias_ano"], x["observados"], lo, hi):
            return False
    return True


def comp_lado_azar(resultados):
    """La marca «por encima del percentil 95» de cada medida del azar sale de comparar sus observados con su p95
    (petición 19: el lado es un resultado, no una condición para seguir)."""
    return len(resultados) > 0 and all(bool(x["por_encima_del_p95"]) == (x["observados"] > x["p95"]) for x in resultados)


def comp_sin_vetada(textos):
    """Ningún texto lleva la palabra vetada para el conjunto de discos, en mayúsculas o minúsculas."""
    return not any(VETADA in t.lower() for t in textos)


# =================================================================================================================
# 8. Entradas: estado de la fase anterior, huellas y lectura
# =================================================================================================================
def comprobar_previos(raiz):
    """Para con PARADO si falta un JSON del que parte la petición o su estado es PARADO o ERROR."""
    estados = {}
    for n in PREVIOS:
        ruta = raiz / "informes" / f"{n}.json"
        if not ruta.exists():
            raise Parada("PARADO", f"falta informes/{n}.json")
        estado = json.loads(ruta.read_text(encoding="utf-8"))["resultado"]["estado"]
        estados[n] = estado
        if estado in ("PARADO", "ERROR"):
            raise Parada("PARADO", f"informes/{n}.json está en {estado}")
    return estados


def comprobar_huellas(raiz):
    """Compara la huella de cada tabla con la de informes/transformacion-datos.json; para con ERROR si una cambia."""
    ruta = raiz / TRANSFORMACION
    if not ruta.exists():
        raise Parada("ERROR", f"falta {TRANSFORMACION}")
    tj = json.loads(ruta.read_text(encoding="utf-8"))
    conocidas = {Path(s["ruta"]).stem: s["sha256"] for s in tj["salidas"] + tj["entradas"]}
    entradas = []
    for t in TABLAS_SALIDA + TABLAS_ENTRADA:
        p = raiz / "data" / "processed" / f"{t}.parquet"
        if t not in conocidas or not p.exists():
            raise Parada("ERROR", f"{t} no está en {TRANSFORMACION} o falta su parquet")
        huella = sha256(p)
        meta = pq.read_metadata(p)
        entradas.append({"ruta": f"data/processed/{t}.parquet", "sha256": huella, "filas": meta.num_rows,
                         "columnas": meta.num_columns, "coincide_con_transformacion": huella == conocidas[t]})
        if huella != conocidas[t]:
            raise Parada("ERROR", f"la huella de data/processed/{t}.parquet no es la de {TRANSFORMACION}")
    return entradas


def bandera(serie):
    """−1 si el valor está vacío, 1 si pasa de cero y 0 si no: un vacío no es un cero (reglas, apartado 5)."""
    v = serie.to_numpy(dtype=float, na_value=np.nan)
    return np.where(np.isnan(v), -1, (v > 0).astype(np.int8)).astype(np.int8)


def leer_fotos(ruta, vida_index, modelos, centros, periodos):
    """Lee fotos_riesgo por bloques y deja columnas compactas: códigos de disco, mes, modelo, centro y periodo."""
    pf = pq.ParquetFile(ruta)
    trozos = {k: [] for k in ["sc", "mi", "mo", "edad", "avisa", "t194", "s12", "s241", "s242", "s9", "s90", "dc",
                              "vault", "slot", "per", "falla"] + [f"f{c}" for c in CONTADORES]
              + [f"k{c}" for c in CONT_CAMBIO]}
    for i in range(pf.num_row_groups):
        x = pf.read_row_group(i, columns=COL_FOTOS).to_pandas()
        fecha = x["fecha"].astype("datetime64[ms]")
        if (fecha.dt.day != 1).any():
            raise Parada("ERROR", "fotos_riesgo trae una foto que no es del día 1 del mes")
        sc = vida_index.get_indexer(x["serial_number"])
        mo = pd.Categorical(x["model"], categories=modelos).codes
        dc = pd.Categorical(x["datacenter"], categories=centros).codes
        per = pd.Categorical(x["periodo"], categories=periodos).codes
        if (sc < 0).any() or (mo < 0).any() or ((dc < 0) & x["datacenter"].notna().to_numpy()).any() or (per < 0).any():
            raise Parada("ERROR", "fotos_riesgo trae un disco, un modelo, un centro o un periodo desconocido")
        trozos["sc"].append(sc.astype(np.int32))
        trozos["mi"].append(mes_indice(fecha).astype(np.int16))
        trozos["mo"].append(mo.astype(np.int16))
        trozos["dc"].append(dc.astype(np.int8))
        trozos["per"].append(per.astype(np.int8))
        trozos["edad"].append(x["edad_anos"].to_numpy(dtype=float, na_value=np.nan))
        trozos["avisa"].append(x["avisa"].to_numpy(dtype=bool))
        for c in CONTADORES:
            trozos[f"f{c}"].append(bandera(x[f"smart_{c}_raw"]))
        for c in CONT_CAMBIO:
            trozos[f"k{c}"].append(bandera(x[f"cambio_smart_{c}"]))
        for k, col in [("t194", "smart_194_raw"), ("s12", "smart_12_raw"), ("s241", "smart_241_raw"),
                       ("s242", "smart_242_raw"), ("s9", "smart_9_raw")]:
            trozos[k].append(x[col].to_numpy(dtype=float, na_value=np.nan))
        trozos["s90"].append(x["smart_90_raw"].notna().to_numpy())
        trozos["vault"].append(x["vault_id"].fillna(-1).to_numpy(dtype=np.int64))
        trozos["slot"].append(x["pod_slot_num"].fillna(-1).to_numpy(dtype=np.int64))
        trozos["falla"].append(x["falla_30d"].to_numpy(dtype=np.int8))
    return pd.DataFrame({k: np.concatenate(v) for k, v in trozos.items()})


def leer(raiz):
    """Lee las tablas pequeñas enteras, con solo sus columnas, y fotos_riesgo por bloques; discos de datos marcados."""
    p = raiz / "data" / "processed"
    d = {}
    dm = pd.read_parquet(p / "dim_modelo.parquet", columns=["model", "capacidad_tb", "tipo_disco", "fabricante"])
    d["dmd"] = dm.loc[dm["tipo_disco"] == "datos"].sort_values("model", kind="mergesort").reset_index(drop=True)
    d["modelos"] = d["dmd"]["model"].tolist()
    datos = set(d["modelos"])
    d["cal"] = pd.read_parquet(p / "calendario.parquet", columns=["fecha", "ano", "trimestre"])
    d["cal"]["fecha"] = d["cal"]["fecha"].astype("datetime64[ms]")
    d["cm"] = pd.read_parquet(p / "centro_mes.parquet", columns=["datacenter", "mes", "dias_disco", "fallos"])
    d["cm"]["mes"] = d["cm"]["mes"].astype("datetime64[ms]")
    d["dpt"] = pd.read_parquet(p / "dias_por_tramo.parquet",
                               columns=["model", "centro", "mes", "edad_anos_cumplidos", "fotos", "dias_disco", "fallos"])
    d["dpt"]["mes"] = d["dpt"]["mes"].astype("datetime64[ms]")
    rec = pd.read_parquet(p / "recuento_diario_corregido.parquet",
                          columns=["fecha", "model", "datacenter", "discos", "fallos"])
    rec = rec.loc[rec["model"].isin(datos)].copy()
    rec["fecha"] = rec["fecha"].astype("datetime64[ms]")
    rec["datacenter"] = rec["datacenter"].fillna(SIN_DATO)
    d["rec"] = rec
    fd = pd.read_parquet(p / "fallos_detalle.parquet",
                         columns=["serial_number", "dia_fallo", "model", "capacidad_tb", "tipo_disco",
                                  "hay_dia_anterior", "sin_aviso", "datacenter", "vault_id", "pod_slot_num", "tomo",
                                  "plazo_reconstruccion_dias", "coincide_con_anterior", "ultima_foto_anterior"])
    for c in ["dia_fallo", "ultima_foto_anterior"]:
        fd[c] = fd[c].astype("datetime64[ms]")
    d["fd"] = fd.loc[fd["tipo_disco"] == "datos"].sort_values(["dia_fallo", "serial_number"], kind="mergesort").reset_index(drop=True)
    vida = pd.read_parquet(p / "vida_discos.parquet", columns=["serial_number", "ultima_foto", "evento"])
    vida["ultima_foto"] = vida["ultima_foto"].astype("datetime64[ms]")
    d["vida"] = vida.sort_values("serial_number", kind="mergesort").reset_index(drop=True)
    vt = pq.read_table(p / "ventanas_fallo_corregido.parquet",
                       columns=["fecha", "dia_fallo", "serial_number", "pod_slot_num"]
                       + [f"smart_{c}_raw" for c in CONTADORES]).to_pandas()
    for c in ["fecha", "dia_fallo"]:
        vt[c] = vt[c].astype("datetime64[ms]")
    d["ven"] = vt
    # Los centros que constan, del recuento y de las fotos; «sin dato» va aparte
    pf = pq.ParquetFile(p / "fotos_riesgo.parquet")
    centros, periodos = set(rec["datacenter"]) - {SIN_DATO}, set()
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=["datacenter", "periodo"])
        centros |= {x for x in pc.unique(t["datacenter"]).to_pylist() if x is not None}
        periodos |= {x for x in pc.unique(t["periodo"]).to_pylist() if x is not None}
    d["centros"] = sorted(centros)
    d["periodos"] = sorted(periodos)
    d["F"] = leer_fotos(p / "fotos_riesgo.parquet", pd.Index(d["vida"]["serial_number"]), d["modelos"], d["centros"],
                        d["periodos"])
    return d


# =================================================================================================================
# 9. Segundas vías: cada una parte de otra tabla o de otro cálculo (método §5)
# =================================================================================================================
def comparar(nombre, via1, via2, a, b, tolerancia=None):
    """Compara dos series indexadas por la misma clave; exacta o con tolerancia. Una clave en una sola vía no coincide."""
    c = pd.concat([pd.Series(a, dtype="float64").rename("v1"), pd.Series(b, dtype="float64").rename("v2")], axis=1)
    faltan = int(c.isna().any(axis=1).sum())
    c = c.fillna(0)
    dif = (c["v1"] - c["v2"]).abs()
    distintas = int((dif > (tolerancia if tolerancia is not None else 0)).sum())
    return {"nombre": nombre, "via_1": via1, "via_2": via2, "claves": int(len(c)), "claves_en_una_sola_via": faltan,
            "diferentes": distintas, "max_diferencia": r(dif.max() if len(dif) else 0.0, 12),
            "comparacion": "exacta" if tolerancia is None else f"diferencia menor que {tolerancia:g}",
            "coinciden": bool(distintas == 0 and faltan == 0 and len(c) > 0)}


def cifra(nombre, clave, valor, unidad, poblacion, periodo, filas, segunda, de, coinciden):
    """Una cifra del JSON con su población, sus filas, su periodo y su segunda vía."""
    return {"nombre": nombre, "clave": clave, "valor": valor, "unidad": unidad, "poblacion": poblacion,
            "periodo": periodo, "filas": filas, "segunda_via": segunda, "segunda_via_de": de, "coinciden": bool(coinciden)}


# =================================================================================================================
# 10. Cálculo
# =================================================================================================================
def preparar(d):
    """Lo que comparten los bloques: calendario, reparto de los días por las fotos y la foto de cada fallo."""
    F, fd, rec, vida = d["F"], d["fd"], d["rec"], d["vida"]
    b = {}
    cal = d["cal"]
    b["mi_sitio"] = int(mes_indice([INICIO_SITIO])[0])
    b["n_meses"] = int(mes_indice([FECHA_DATOS])[0]) + 1
    b["dia_mes"] = dia_indice([mes_fecha(m) for m in range(b["n_meses"])])
    b["fin"] = int(dia_indice([FECHA_DATOS])[0])
    # Trimestres del calendario, con su marca de incompleto
    q = cal.assign(t=[trimestre_de(x) for x in cal["fecha"]]).groupby("t")["fecha"].agg(["size", "min"])
    b["trimestres"] = {t: {"dias": int(x["size"]), "parcial": int(x["size"]) != sum(
        calendar.monthrange(x["min"].year, m)[1] for m in range(x["min"].month, x["min"].month + 3))}
        for t, x in q.iterrows()}
    meses_cal = cal.assign(mi=mes_indice(cal["fecha"])).groupby("mi").size()
    b["meses_parciales"] = {int(m) for m, n in meses_cal.items()
                            if n != calendar.monthrange(mes_fecha(m).year, mes_fecha(m).month)[1]}
    # Celdas de modelo, centro y mes: «sin dato» es el último código de centro
    nc = len(d["centros"])
    b["nc"] = nc
    dcx = np.where(F["dc"].to_numpy() < 0, nc, F["dc"].to_numpy()).astype(np.int64)
    celda_foto = (F["mo"].to_numpy().astype(np.int64) * (nc + 1) + dcx) * BASE_MES + F["mi"].to_numpy()
    rmo = pd.Categorical(rec["model"], categories=d["modelos"]).codes.astype(np.int64)
    rdc = pd.Categorical(rec["datacenter"], categories=d["centros"] + [SIN_DATO]).codes.astype(np.int64)
    if (rdc < 0).any():
        raise Parada("ERROR", "el recuento trae un centro que no está en la lista de centros")
    rec_celda = (rmo * (nc + 1) + rdc) * BASE_MES + mes_indice(rec["fecha"])
    dias_celda = pd.Series(rec["discos"].to_numpy(dtype=float)).groupby(rec_celda).sum()
    rep = pesos_por_celda(celda_foto, dias_celda)
    b["peso"] = rep["pesos"]
    sin_foto = rep["celdas_sin_foto_lista"]
    fallos_celda = pd.Series(rec["fallos"].to_numpy()).groupby(rec_celda).sum()
    b["reparto"] = {"dias_repartidos": float(rep["pesos"].sum()), "dias_recuento": float(dias_celda.sum()),
                    "dias_sin_foto": rep["dias_sin_foto"], "celdas_sin_foto": rep["celdas_sin_foto"],
                    "fallos_recuento_sin_foto": int(fallos_celda.reindex(sin_foto).sum()),
                    "fotos_sin_dias": rep["fotos_sin_dias"]}
    # Días sin foto por centro desde 07/2023, para la segunda vía de B5
    sf = pd.Series(dias_celda.reindex(sin_foto).to_numpy(), index=sin_foto)
    sf_dc = (sf.index.to_numpy() // BASE_MES) % (nc + 1)
    sf_mi = sf.index.to_numpy() % BASE_MES
    nombres_dc = d["centros"] + [SIN_DATO]
    b["sin_foto_centro"] = (pd.Series(sf.to_numpy()[sf_mi >= b["mi_sitio"]])
                            .groupby([nombres_dc[i] for i in sf_dc[sf_mi >= b["mi_sitio"]]]).sum())
    # La foto de cada fallo: la de su disco con fecha igual a su última foto anterior (criterio 7)
    clave_foto = F["sc"].to_numpy().astype(np.int64) * BASE_MES + F["mi"].to_numpy()
    b["indice_foto"] = pd.Index(clave_foto)
    b["fotos_unicas"] = bool(b["indice_foto"].is_unique)
    if not b["fotos_unicas"]:
        raise Parada("ERROR", "fotos_riesgo trae dos fotos del mismo disco en el mismo mes")
    vida_index = pd.Index(vida["serial_number"])
    fd = fd.assign(sc=vida_index.get_indexer(fd["serial_number"]), dia=dia_indice(fd["dia_fallo"]))
    con_uf = fd["ultima_foto_anterior"].notna().to_numpy()
    idx = np.full(len(fd), -1, dtype=np.int64)
    claves = fd.loc[con_uf, "sc"].to_numpy().astype(np.int64) * BASE_MES + mes_indice(fd.loc[con_uf, "ultima_foto_anterior"])
    idx[con_uf] = np.where(fd.loc[con_uf, "sc"].to_numpy() >= 0, b["indice_foto"].get_indexer(claves), -1)
    b["fd"] = fd.assign(foto=idx)
    b["con_uf"] = int(con_uf.sum())
    b["vida_ultima"] = dia_indice(vida["ultima_foto"].fillna(pd.Timestamp(FECHA_DATOS) + pd.Timedelta(days=BASE_DIA)))
    b["vida_desaparece"] = (vida["evento"] == "desaparece").to_numpy()
    b["cap_mo"] = d["dmd"]["capacidad_tb"].to_numpy()
    b["fab_mo"] = d["dmd"]["fabricante"].to_numpy()
    return b


def calcular_b5(d, b):
    """Bloque 5: si un centro de datos falla más por sí mismo."""
    cm, dpt, rec, F = d["cm"], d["dpt"], d["rec"], d["F"]
    ini = pd.Timestamp(INICIO_SITIO)
    sv = []
    periodo = f"del {iso(INICIO_SITIO)} al {iso(FECHA_DATOS)}"
    # B5.1 · por centro y trimestre, y por centro en los dos años, desde centro_mes
    cm2 = cm.loc[cm["mes"] >= ini].assign(t=lambda x: [trimestre_de(m) for m in x["mes"]])
    tri = []
    for (c, t), x in cm2.loc[cm2["datacenter"] != SIN_DATO].groupby(["datacenter", "t"], sort=True):
        tt, lo, hi = intervalo_poisson(x["fallos"].sum(), x["dias_disco"].sum())
        tri.append({"centro": c, "trimestre": t, "dias_disco": int(x["dias_disco"].sum()), "fallos": int(x["fallos"].sum()),
                    "tasa": tt, "desde": lo, "hasta": hi, "parcial": b["trimestres"][t]["parcial"]})
    por_c = cm2.groupby("datacenter").agg(dias=("dias_disco", "sum"), fallos=("fallos", "sum"))
    # Segunda vía: el recuento, día a día
    r2 = rec.loc[rec["fecha"] >= ini].groupby("datacenter").agg(dias=("discos", "sum"), fallos=("fallos", "sum"))
    sv.append(comparar("días de disco por centro desde 07/2023", "centro_mes", "recuento_diario_corregido",
                       por_c["dias"], r2["dias"]))
    sv.append(comparar("fallos por centro desde 07/2023", "centro_mes", "recuento_diario_corregido",
                       por_c["fallos"], r2["fallos"]))
    # B5.2 · tasa ajustada con dias_por_tramo desde 07/2023, con la mezcla de modelo, edad y trimestre y su φ (petición 19)
    dp = dpt.loc[dpt["mes"] >= ini]
    aj, ph5 = ajustada(dp)
    tasa_todos = float(aj["tasa_todos"].iloc[0])
    sv.append(comparar("días de disco por centro: dias_por_tramo más los días sin foto", "dias_por_tramo + días de "
                       "las celdas del recuento sin foto", "recuento_diario_corregido",
                       aj.set_index("centro")["dias"].add(b["sin_foto_centro"], fill_value=0.0), r2["dias"], TOLERANCIA))
    sv.append(comparar("fallos por centro: dias_por_tramo", "dias_por_tramo", "recuento_diario_corregido",
                       aj.set_index("centro")["observados"], r2["fallos"]))
    # Los esperados suman los observados de las celdas con tasa; los fallos de las celdas sin días van aparte (petición 19)
    sv.append(comparar("suma de los esperados de todos los centros", "esperados (tasa de cada modelo, edad y trimestre)",
                       "observados de las celdas con días", pd.Series({"todos": aj["esperados"].sum()}),
                       pd.Series({"todos": float(aj["observados"].sum() - aj["fallos_sin_tasa"].sum())}), TOLERANCIA))
    centros = []
    for _, x in aj.iterrows():
        c = x["centro"]
        dias_rec, fallos_rec = int(por_c.loc[c, "dias"]), int(por_c.loc[c, "fallos"])
        tb, lo, hi = intervalo_poisson(fallos_rec, dias_rec)
        dias_ano = x["dias"] / ANOS_SITIO
        centros.append({"centro": c, "dias_disco": dias_rec, "fallos": fallos_rec, "tasa_bruta": tb, "desde": lo,
                        "hasta": hi, "dias_tramos": float(x["dias"]), "dias_ano": dias_ano,
                        "observados": int(x["observados"]), "esperados": float(x["esperados"]),
                        "fallos_sin_tasa": int(x["fallos_sin_tasa"]), "razon": x["razon"],
                        "razon_desde": x["razon_desde"], "razon_hasta": x["razon_hasta"],
                        "tasa_bruta_tramos": x["tasa_bruta_tramos"], "tasa_ajustada": x["tasa_ajustada"],
                        "veredicto": veredicto(c, dias_ano, x["observados"], x["razon_desde"], x["razon_hasta"])})
    con_conclusion = [x for x in centros if x["veredicto"] not in ("sin conclusión", "aparte")]
    azar = {"centros_con_conclusion": len(con_conclusion),
            "distintos": sum(1 for x in con_conclusion if x["veredicto"] != "no se distingue"),
            "esperados_por_azar": len(con_conclusion) * (1 - CONFIANZA)}
    # La prueba de quitar cada modelo en sac0 y sac2; cada vez, con su mezcla y su φ
    quitar = []
    base_v = {x["centro"]: x["veredicto"] for x in centros}
    for c in CENTROS_QUITAR:
        if c not in base_v:
            continue
        modelos = sorted(dp.loc[(dp["centro"] == c) & (dp["dias_disco"].fillna(0) > 0), "model"].unique().tolist())
        detalle = []
        for m in modelos:
            a2 = ajustada(dp.loc[dp["model"] != m])[0].set_index("centro").loc[c]
            v = veredicto(c, a2["dias"] / ANOS_SITIO, a2["observados"], a2["razon_desde"], a2["razon_hasta"])
            detalle.append({"model": m, "razon": a2["razon"], "desde": a2["razon_desde"], "hasta": a2["razon_hasta"],
                            "veredicto": v, "cambia": v != base_v[c]})
        quitar.append({"centro": c, "veredicto": base_v[c], "modelos_probados": len(modelos),
                       "cambios": sum(1 for x in detalle if x["cambia"]), "detalle": detalle})
    # Modelos que pasan el mínimo en dos centros o más (lo que pide la tasa ajustada)
    mc_ = dp.loc[dp["centro"] != SIN_DATO].groupby(["model", "centro"])["dias_disco"].sum()
    n_min = int(((mc_ >= MINIMO_DIAS_ANO * ANOS_SITIO).groupby(level="model").sum() >= 2).sum())
    # B5.3 · reparto de cada centro por modelo
    reparto = {}
    for c, x in dp.groupby("centro"):
        dm_ = x.groupby("model")["dias_disco"].sum().sort_values(ascending=False, kind="mergesort")
        tot = float(dm_.sum())
        reparto[c] = {"dias": tot, "modelos": int((dm_ > 0).sum()),
                      "primeros": [{"model": m, "dias": float(v), "pct": 100 * float(v) / tot}
                                   for m, v in dm_.head(N_MODELOS_REPARTO).items()],
                      "resto_pct": 100 * float(dm_.iloc[N_MODELOS_REPARTO:].sum()) / tot}
    # B5.4 · temperatura media por centro y mes, desde 07/2023
    nombres_dc = d["centros"] + [SIN_DATO]
    sel = (F["mi"].to_numpy() >= b["mi_sitio"]) & ~np.isnan(F["t194"].to_numpy())
    dcx = np.where(F["dc"].to_numpy()[sel] < 0, b["nc"], F["dc"].to_numpy()[sel])
    tf = pd.DataFrame({"c": dcx, "mi": F["mi"].to_numpy()[sel], "t": F["t194"].to_numpy()[sel]})
    serie = [{"centro": nombres_dc[c], "mes": iso(mes_fecha(m)), "fotos": int(x["t"].size), "media": float(x["t"].mean())}
             for (c, m), x in tf.groupby(["c", "mi"], sort=True)]
    por_centro = [{"centro": nombres_dc[c], "fotos": int(x["t"].size), "media": float(x["t"].mean())}
                  for c, x in tf.groupby("c", sort=True)]
    # Comprobaciones
    razones = [x["razon"] for x in centros]
    puestos = pd.Series(razones).rank(method="min", ascending=False).astype(int).tolist()
    comp = {"unidad": comp_unidad(zip(cm["datacenter"], cm["mes"])),
            "minimo": comp_minimo([x["veredicto"] not in ("sin conclusión", "aparte") for x in centros],
                                  [x["dias_ano"] for x in centros], [x["observados"] for x in centros],
                                  MINIMO_DIAS_ANO, MINIMO_FALLOS),
            "empates": comp_empates(razones, puestos),
            "referencia": comp_referencia([x["dias_tramos"] for x in centros], float(dp["dias_disco"].fillna(0).sum()))
            and comp_referencia([x["observados"] for x in centros], float(dp["fallos"].sum())),
            "azar_en_grupos": comp_azar(azar["centros_con_conclusion"], azar["esperados_por_azar"],
                                        [(x["razon_desde"], x["razon_hasta"]) for x in con_conclusion]),
            "pesos": None, "hacia_adelante": None,
            "cobertura": comp_cobertura(1 - float(por_c.loc[SIN_DATO, "fallos"]) / float(por_c["fallos"].sum())
                                        if SIN_DATO in por_c.index else 1.0),
            "periodos": comp_periodos(tri, "trimestre", {t for t, x in b["trimestres"].items() if x["parcial"]})}
    tablas = {"centros": centros, "trimestres": tri,
              "ajustada": {"filas": int(len(dp)), "dias": float(dp["dias_disco"].fillna(0).sum()),
                           "fallos": int(dp["fallos"].sum()),
                           "celdas": int(dp.groupby(["model", "edad_anos_cumplidos"]).ngroups),
                           "celdas_modelo_edad_trimestre": int(dp.assign(q=dp["mes"].dt.year * 10 + dp["mes"].dt.quarter)
                                                               .groupby(["model", "edad_anos_cumplidos", "q"]).ngroups),
                           "fallos_sin_tasa": int(aj["fallos_sin_tasa"].sum()), "tasa_todos": tasa_todos},
              "phi": ph5,
              "modelos_minimo_dos_centros": n_min, "azar": azar, "quitar_modelo": quitar, "reparto_por_modelo": reparto,
              "temperatura": {"por_centro": por_centro, "serie": serie},
              "series_grafico_barras": [{"centro": x["centro"], "tasa_bruta": x["tasa_bruta"],
                                         "tasa_ajustada": x["tasa_ajustada"]} for x in centros]}
    pob = POBLACION + "; días y fallos con su centro, del 01/07/2023 al 30/06/2025; «sin dato» aparte"
    ok = {s["nombre"]: s["coinciden"] for s in sv}
    cifras = []
    for x in centros:
        cifras.append(cifra(f"días de disco de {x['centro']}", f"preguntas.B5.tablas.centros[{x['centro']}].dias_disco",
                            x["dias_disco"], "días de disco", pob, periodo, int(len(cm2)), int(r2["dias"].get(x["centro"], 0)),
                            "recuento_diario_corregido", ok["días de disco por centro desde 07/2023"]))
        cifras.append(cifra(f"fallos de {x['centro']}", f"preguntas.B5.tablas.centros[{x['centro']}].fallos",
                            x["fallos"], "fallos", pob, periodo, int(len(cm2)), int(r2["fallos"].get(x["centro"], 0)),
                            "recuento_diario_corregido", ok["fallos por centro desde 07/2023"]
                            and ok["fallos por centro: dias_por_tramo"]))
    cifras.append(cifra("días de disco de la tasa ajustada", "preguntas.B5.tablas.ajustada.dias",
                        tablas["ajustada"]["dias"], "días de disco", pob, periodo, int(len(dp)),
                        float(r2["dias"].sum() - b["sin_foto_centro"].sum()), "recuento menos los días sin foto",
                        ok["días de disco por centro: dias_por_tramo más los días sin foto"]))
    cifras.append(cifra("suma de los esperados", "preguntas.B5.tablas.centros[].esperados",
                        float(aj["esperados"].sum()), "fallos", pob, periodo, int(len(dp)),
                        int(aj["observados"].sum() - aj["fallos_sin_tasa"].sum()),
                        "suma de los observados de las celdas con días", ok["suma de los esperados de todos los centros"]))
    q = {"id": "B5", "pregunta": "Si algún centro de datos tiene más fallos que los demás con los mismos discos",
         "decision": "dónde mirar la operación de un centro: solo si falla más con la misma mezcla de modelos y edades",
         "planteamiento": "config/metodo/plan_de_la_analitica.md, bloque 5; metodo/04_planteamientos.md §1.A",
         "funcion": "comparar_con_total",
         "funcion_adaptada": ("comparar_con_total del 42.6 compara proporciones con Wilson; aquí se compara una tasa por "
                              "días de disco, así que cada centro va con su razón de observados entre esperados por "
                              "estandarización indirecta (5.6) con la mezcla de modelo, año de edad y trimestre, y el "
                              "intervalo exacto de Poisson ensanchado por φ (petición 19); el mínimo es el de las reglas, apartado 7"),
         "poblacion": {"regla": pob, "periodo": periodo, "filas": int(len(dp)), "unidad": "centro de datos",
                       "entidades": int(len(centros))},
         "medida": ("tasa anual = 100 × 365 × fallos / días de disco; razón = observados / esperados con la tasa de cada "
                    "modelo, año de edad y trimestre de todos los centros; tasa ajustada = razón × tasa de todos; "
                    "intervalo de la razón con observados y esperados entre φ, medido en centro × trimestre"),
         "minimo_casos": "50.000 días de disco al año y 20 fallos (reglas, apartado 7; petición, comprobación 1)",
         "que_cambia_la_decision": "un centro cuyo intervalo de la razón queda entero por encima de 1 falla más por sí mismo",
         "cifras": cifras,
         "referencia": {"que_es": "la tasa de todos los centros juntos con las mismas filas de dias_por_tramo; razón 1",
                        "valor": tasa_todos, "filas": int(len(dp))},
         "comprobaciones": comp,
         "motivos_null": {"pesos": "no hay ninguna puntuación con pesos",
                          "hacia_adelante": "los bloques 5 a 8 describen y no predicen"},
         "comprobaciones_extra": {"phi_minimo_uno": comp_phi([ph5]),
                                  "veredicto_del_intervalo": comp_veredicto_centros(centros, ph5["phi"])},
         "sin_conclusion": [{"bloque": "B5", "grupo": x["centro"], "casos": x["observados"],
                             "dias_disco": x["dias_disco"]} for x in centros if x["veredicto"] == "sin conclusión"],
         "tablas": tablas}
    return q, sv


def calcular_b6(d, b):
    """Bloque 6: qué hace Backblaze con los avisos."""
    F, fd, ven = d["F"], b["fd"], d["ven"]
    sv = []
    periodo = f"del {iso(FECHA_INICIO)} al {iso(FECHA_DATOS)}"
    mi, mo, sc = F["mi"].to_numpy(), F["mo"].to_numpy(), F["sc"].to_numpy()
    avisa = F["avisa"].to_numpy()
    # B6.1 · fotos que avisan por mes, modelo y fabricante; segunda vía, el aviso rehecho con los cinco contadores
    por_mes = pd.DataFrame({"mi": mi, "a": avisa}).groupby("mi")["a"].agg(["size", "sum"])
    rehecho = np.zeros(len(F), dtype=bool)
    for c in CONTADORES:
        rehecho |= F[f"f{c}"].to_numpy() == 1
    sv.append(comparar("fotos que avisan por mes", "columna avisa de fotos_riesgo",
                       "los cinco contadores por encima de cero, sin contar los vacíos", por_mes["sum"],
                       pd.Series(rehecho).groupby(mi).sum()))
    avisan_mes = [{"mes": iso(mes_fecha(m)), "fotos": int(x["size"]), "avisan": int(x["sum"]),
                   "pct": 100 * x["sum"] / x["size"]} for m, x in por_mes.iterrows()]
    pm = pd.DataFrame({"mo": mo, "a": avisa}).groupby("mo")["a"].agg(["size", "sum"])
    avisan_modelo = [{"model": d["modelos"][m], "fotos": int(x["size"]), "avisan": int(x["sum"]),
                      "pct": 100 * x["sum"] / x["size"]} for m, x in pm.iterrows()]
    pfab = pm.assign(f=b["fab_mo"][pm.index.to_numpy()]).groupby("f")[["size", "sum"]].sum()
    avisan_fab = [{"fabricante": f, "fotos": int(x["size"]), "avisan": int(x["sum"]), "pct": 100 * x["sum"] / x["size"]}
                  for f, x in pfab.iterrows()]
    # B6.2 · desenlace a 90 días, la foto como unidad (criterio 2)
    dia_foto = b["dia_mes"][mi]
    h = dia_foto + HORIZONTE <= b["fin"]
    sc_h, df_h = sc[h], dia_foto[h]
    f1 = falla_en_90_merge(sc_h, df_h, fd["sc"].to_numpy(), fd["dia"].to_numpy())
    f2 = falla_en_90_busqueda(sc_h, df_h, fd["sc"].to_numpy(), fd["dia"].to_numpy())
    desap = ~f1 & b["vida_desaparece"][sc_h] & (b["vida_ultima"][sc_h] < df_h + HORIZONTE)
    grupos_m = {"sin aviso": ~avisa[h], "con algún aviso": avisa[h]}
    for c in CONTADORES:
        grupos_m[f"contador {c}"] = F[f"f{c}"].to_numpy()[h] == 1
    n_h = int(h.sum())
    # Celdas del φ binomial (petición 19): el trimestre de la foto, como año × 10 + trimestre
    q_h = (FECHA_INICIO.year + mi[h] // 12) * 10 + (mi[h] % 12) // 3 + 1
    grupos, ref = desenlace_por_grupo(grupos_m, f1, f2, desap, sc_h, q_h)
    sv.append(comparar("fotos que fallan en 90 días, por grupo de aviso", "unión de fotos y fallos",
                       "búsqueda en la lista ordenada de fallos", pd.Series({x["grupo"]: x["falla"] for x in grupos}),
                       pd.Series({x["grupo"]: x["falla_busqueda"] for x in grupos})))
    # B6.2 en Seagate (petición 17): el mismo desenlace con el filtro de fabricante, porque solo Seagate trae los cinco
    # contadores; su referencia es «sin aviso» de Seagate
    seag_h = b["fab_mo"][mo[h]] == FABRICANTE_CINCO
    grupos_s, ref_s = desenlace_por_grupo({g: m & seag_h for g, m in grupos_m.items()}, f1, f2, desap, sc_h, q_h)
    sv.append(comparar(f"fotos que fallan en 90 días, por grupo de aviso, {FABRICANTE_CINCO}", "unión de fotos y fallos",
                       "búsqueda en la lista ordenada de fallos", pd.Series({x["grupo"]: x["falla"] for x in grupos_s}),
                       pd.Series({x["grupo"]: x["falla_busqueda"] for x in grupos_s})))
    # Si el 197 y el 198 marcan las mismas fotos en Seagate: por máscaras y, como segunda vía, por índices
    m197, m198 = grupos_m["contador 197"] & seag_h, grupos_m["contador 198"] & seag_h
    las_dos_idx = int(np.intersect1d(np.nonzero(m197)[0], np.nonzero(m198)[0]).size)
    c197_198 = {"fotos_197": int(m197.sum()), "fotos_198": int(m198.sum()), "las_dos": int((m197 & m198).sum()),
                "solo_197": int((m197 & ~m198).sum()), "solo_198": int((m198 & ~m197).sum())}
    c197_198["mismas_fotos"] = c197_198["solo_197"] == 0 and c197_198["solo_198"] == 0
    sv.append(comparar(f"fotos de {FABRICANTE_CINCO} con el 197 y el 198 a la vez", "máscaras de los dos contadores",
                       "intersección de los índices de las fotos", pd.Series({"las_dos": c197_198["las_dos"]}),
                       pd.Series({"las_dos": las_dos_idx})))
    # B6.3 · los fallos: con día anterior, sin aviso y sin día anterior; la ventana antes del fallo
    hay = fd["hay_dia_anterior"].fillna(False).astype(bool)
    fallos = {"datos": int(len(fd)), "con_dia_anterior": int(hay.sum()),
              "sin_aviso": int(fd["sin_aviso"].fillna(False).astype(bool).sum()),
              "sin_dia_anterior": int((~hay).sum())}
    # Por año del fallo (petición 19): sin aviso el día anterior entre los que lo tienen, y sin día anterior entre todos
    sin_av = fd["sin_aviso"].fillna(False).astype(bool) & hay
    ano_f = fd["dia_fallo"].dt.year
    pa_ = (pd.DataFrame({"ano": ano_f.to_numpy(), "hay": hay.to_numpy(), "sa": sin_av.to_numpy()})
           .groupby("ano").agg(fallos=("hay", "size"), con=("hay", "sum"), sa=("sa", "sum")))
    ano_parcial = (FECHA_DATOS.month, FECHA_DATOS.day) != (12, 31)
    por_ano = [{"ano": int(a), "fallos": int(x["fallos"]), "con_dia_anterior": int(x["con"]), "sin_aviso": int(x["sa"]),
                "sin_dia_anterior": int(x["fallos"] - x["con"]),
                "pct_sin_aviso": 100 * x["sa"] / x["con"] if x["con"] else None,
                "pct_sin_dia": 100 * (x["fallos"] - x["con"]) / x["fallos"],
                "parcial": bool(ano_parcial and int(a) == FECHA_DATOS.year)} for a, x in pa_.iterrows()]
    # Segunda vía: el mismo recuento con un bucle sobre las filas
    cuenta = {}
    for a, hh, s in zip(ano_f.tolist(), hay.tolist(), sin_av.tolist()):
        c_ = cuenta.setdefault(a, [0, 0, 0])
        c_[0] += 1
        c_[1] += int(hh)
        c_[2] += int(s)
    sv.append(comparar("fallos sin aviso por año", "agrupación de fallos_detalle por año",
                       "recuento en bucle sobre las filas de fallos_detalle",
                       pd.Series({f"{x['ano']}|{k}": x[c] for x in por_ano
                                  for k, c in (("f", "fallos"), ("c", "con_dia_anterior"), ("s", "sin_aviso"))}),
                       pd.Series({f"{a}|{k}": v[i] for a, v in cuenta.items() for i, k in enumerate(("f", "c", "s"))})))
    clave_fd = pd.MultiIndex.from_arrays([fd["serial_number"], fd["dia_fallo"]])
    v = ven.loc[pd.MultiIndex.from_arrays([ven["serial_number"], ven["dia_fallo"]]).isin(clave_fd)].copy()
    av = np.zeros(len(v), dtype=bool)
    for c in CONTADORES:
        av |= v[f"smart_{c}_raw"].to_numpy(dtype=float, na_value=np.nan) > 0
    v["av"] = av
    v["antes"] = (v["dia_fallo"] - v["fecha"]) // pd.Timedelta(days=1)
    va = v.loc[v["antes"] > 0].sort_values(["serial_number", "dia_fallo", "fecha"], kind="mergesort")
    g = va.groupby(["serial_number", "dia_fallo"], sort=False)
    primero = g["av"].first()
    alguno = g["av"].any()
    primer_aviso = va.loc[va["av"]].groupby(["serial_number", "dia_fallo"])["antes"].max()
    dentro = primer_aviso[(alguno & ~primero).reindex(primer_aviso.index).fillna(False).to_numpy(dtype=bool)]
    qs = dentro.quantile([0.25, 0.5, 0.75]) if len(dentro) else pd.Series([np.nan] * 3, index=[0.25, 0.5, 0.75])
    fallos.update({"con_filas_antes": int(len(primero)), "avisan_algun_dia": int(alguno.sum()),
                   "ya_primer_dia": int(primero.sum()), "empiezan_dentro": int((alguno & ~primero).sum()),
                   "dias_q1": float(qs[0.25]), "dias_mediana": float(qs[0.5]), "dias_q3": float(qs[0.75])})
    # La misma cifra de fallos con día anterior y sin aviso, desde la ventana (comparación que se enseña, no para)
    dia_ant = v.loc[v["antes"] == 1].drop_duplicates(["serial_number", "dia_fallo"])
    comparacion_ventana = {"con_dia_anterior_ventana": int(len(dia_ant)), "sin_aviso_ventana": int((~dia_ant["av"]).sum()),
                           "con_dia_anterior_fallos_detalle": fallos["con_dia_anterior"],
                           "sin_aviso_fallos_detalle": fallos["sin_aviso"]}
    # B6.4 · construcción: fotos con el contador que sube, las que fallan frente a las que no
    per = F["per"].to_numpy()
    cons_cod = [i for i, p in enumerate(d["periodos"]) if str(p).startswith("constru")]
    cons = np.isin(per, cons_cod)
    falla = F["falla"].to_numpy()
    construccion, usadas = [], set()
    for c in CONT_CAMBIO:
        k = F[f"k{c}"].to_numpy()
        m = cons & (k >= 0)
        usadas |= {d["periodos"][i] for i in np.unique(per[m]).tolist()}
        m1, m0 = m & (falla == 1), m & (falla == 0)
        a1, a0 = int((k[m1] == 1).sum()), int((k[m0] == 1).sum())
        construccion.append({"contador": str(c), "fallan_sube": a1, "fallan_filas": int(m1.sum()),
                             "pct_fallan": 100 * a1 / max(int(m1.sum()), 1), "no_fallan_sube": a0,
                             "no_fallan_filas": int(m0.sum()), "pct_no_fallan": 100 * a0 / max(int(m0.sum()), 1)})
    # B6.5 · por cada día antes del fallo, el porcentaje de fallos con cada contador por encima de cero
    serie = []
    for k in range(30, 0, -1):
        x = v.loc[v["antes"] == k]
        cont = {}
        for c in CONTADORES:
            val = x[f"smart_{c}_raw"].to_numpy(dtype=float, na_value=np.nan)
            n = int((~np.isnan(val)).sum())
            enc = int((val > 0).sum())
            cont[str(c)] = {"filas": n, "por_encima": enc, "pct": 100 * enc / n if n else None}
        serie.append({"dia_antes": k, "fallos": int(len(x)), "contadores": cont})
    # Comprobaciones
    ok = {s["nombre"]: s["coinciden"] for s in sv}
    pcts = [x["pct"] for x in avisan_modelo]
    puestos = pd.Series(pcts).rank(method="min", ascending=False).astype(int).tolist()
    otros = [x for x in grupos + grupos_s if x["grupo"] != "sin aviso" and not x["sin_conclusion"]]
    comp = {"unidad": bool(b["fotos_unicas"]) and comp_unidad(zip(fd["serial_number"], fd["dia_fallo"])),
            "minimo": all(x["sin_conclusion"] == (x["fotos"] < MINIMO_CASOS) for x in grupos + grupos_s)
            and all(x["frente_a_sin_aviso"] is None for x in grupos + grupos_s if x["sin_conclusion"]),
            "empates": comp_empates(pcts, puestos),
            "referencia": comp_referencia([grupos[0]["fotos"], grupos[1]["fotos"]], n_h)
            and comp_referencia([grupos_s[0]["fotos"], grupos_s[1]["fotos"]], int(seag_h.sum())),
            "azar_en_grupos": comp_azar(len(otros), len(otros) * (1 - CONFIANZA),
                                        [(x["falla_desde"], x["falla_hasta"]) for x in otros]),
            "pesos": None, "hacia_adelante": None,
            "cobertura": comp_cobertura(n_h / len(F)),
            "periodos": bool((dia_foto[h] + HORIZONTE <= b["fin"]).all()) and not bool(
                (dia_foto[~h] + HORIZONTE <= b["fin"]).any())}
    extra = {"sin_validacion": comp_sin_validacion(sorted(usadas)),
             "phi_minimo_uno": comp_phi([x["phi"] for x in grupos + grupos_s])}
    pob = POBLACION + "; fotos mensuales de fotos_riesgo"
    cifras = [cifra("fotos que avisan", "preguntas.B6.tablas.avisan_por_mes", int(por_mes["sum"].sum()), "fotos", pob,
                    periodo, int(len(F)), int(rehecho.sum()), "los cinco contadores de fotos_riesgo",
                    ok["fotos que avisan por mes"])]
    for x in grupos:
        cifras.append(cifra(f"fotos que fallan en 90 días, {x['grupo']}", f"preguntas.B6.tablas.desenlace[{x['grupo']}].falla",
                            x["falla"], "fotos", pob + "; con 90 días por delante", periodo, x["fotos"],
                            x["falla_busqueda"], "búsqueda en la lista ordenada de fallos de fallos_detalle",
                            ok["fotos que fallan en 90 días, por grupo de aviso"]))
    nombre_s = f"fotos que fallan en 90 días, por grupo de aviso, {FABRICANTE_CINCO}"
    for x in grupos_s:
        cifras.append(cifra(f"fotos de {FABRICANTE_CINCO} que fallan en 90 días, {x['grupo']}",
                            f"preguntas.B6.tablas.desenlace_seagate[{x['grupo']}].falla", x["falla"], "fotos",
                            pob + f"; modelos de {FABRICANTE_CINCO}, con 90 días por delante", periodo, x["fotos"],
                            x["falla_busqueda"], "búsqueda en la lista ordenada de fallos de fallos_detalle", ok[nombre_s]))
    cifras.append(cifra(f"fotos de {FABRICANTE_CINCO} con el 197 y el 198 a la vez",
                        "preguntas.B6.tablas.desenlace_seagate.contadores_197_198.las_dos", c197_198["las_dos"], "fotos",
                        pob + f"; modelos de {FABRICANTE_CINCO}, con 90 días por delante", periodo,
                        int(seag_h.sum()), las_dos_idx, "intersección de los índices de las fotos de cada contador",
                        ok[f"fotos de {FABRICANTE_CINCO} con el 197 y el 198 a la vez"]))
    tablas = {"avisan_por_mes": avisan_mes, "avisan_por_modelo": avisan_modelo, "avisan_por_fabricante": avisan_fab,
              "desenlace": {"fotos": n_h, "grupos": grupos},
              "desenlace_seagate": {"fabricante": FABRICANTE_CINCO, "fotos": int(seag_h.sum()), "grupos": grupos_s,
                                    "referencia_pct_falla": None if ref_s is None else ref_s["pct_falla"],
                                    "contadores_197_198": c197_198},
              "fallos": fallos, "sin_aviso_por_ano": por_ano,
              "comparacion_ventana": comparacion_ventana, "construccion": construccion, "serie_dias_antes": serie}
    q = {"id": "B6", "pregunta": "Cuántos discos avisan, qué aviso anticipa más fallos y cuánto siguen funcionando",
         "decision": "qué aviso merece atención antes y cuánto margen dejan los avisos a los técnicos",
         "planteamiento": "config/metodo/plan_de_la_analitica.md, bloque 6; metodo/04_planteamientos.md §1.A",
         "funcion": "comparar_con_total",
         "funcion_adaptada": ("comparar_con_total del 42.6 frente a las fotos sin aviso y no frente al total, porque el "
                              "aviso es acumulado y la referencia sencilla es no avisar; el intervalo es el exacto de "
                              "Clopper-Pearson con fallan/φ y fotos/φ, con el φ binomial de cada grupo por trimestre de "
                              "la foto (petición 19), y no el de Wilson"),
         "poblacion": {"regla": pob, "periodo": periodo, "filas": int(len(F)), "unidad": "foto mensual de un disco",
                       "entidades": int(np.unique(sc).size)},
         "medida": ("porcentaje de fotos que avisan; desenlace a 90 días de cada foto (falla, desaparece o sigue); "
                    "porcentaje de fotos con el contador que sube entre las que fallan y las que no; fallos sin aviso "
                    "el día anterior por año, entre los que tienen día anterior"),
         "minimo_casos": f"{MINIMO_CASOS} fotos por grupo (método, parametros.md)",
         "que_cambia_la_decision": "un aviso cuyo intervalo de fallo a 90 días queda por encima del de las fotos sin aviso",
         "cifras": cifras,
         "referencia": {"que_es": "las fotos sin aviso, con las mismas fotos de 90 días por delante",
                        "valor": ref["pct_falla"], "filas": ref["fotos"]},
         "comprobaciones": comp,
         "motivos_null": {"pesos": "no hay ninguna puntuación con pesos",
                          "hacia_adelante": "los bloques 5 a 8 describen y no predicen"},
         "comprobaciones_extra": extra,
         "sin_conclusion": ([{"bloque": "B6", "grupo": x["grupo"], "casos": x["fotos"]} for x in grupos if x["sin_conclusion"]]
                            + [{"bloque": "B6", "grupo": f"{FABRICANTE_CINCO}, {x['grupo']}", "casos": x["fotos"]}
                               for x in grupos_s if x["sin_conclusion"]]),
         "tablas": tablas}
    return q, sv


def calcular_b7(d, b):
    """Bloque 7: dónde está el riesgo de perder datos."""
    F, fd = d["F"], b["fd"]
    sv = []
    periodo = f"del {iso(INICIO_SITIO)} al {iso(FECHA_DATOS)}"
    f7 = fd.loc[(fd["dia_fallo"] >= pd.Timestamp(INICIO_SITIO)) & (fd["dia_fallo"] <= pd.Timestamp(FECHA_DATOS))]
    t = f7.loc[f7["tomo"].notna()].copy()
    t["q"] = [trimestre_de(x) for x in t["dia_fallo"]]
    t = t.sort_values(["tomo", "dia", "serial_number"], kind="mergesort").reset_index(drop=True)
    tabla = {"desde_07_2023": int(len(f7)), "sin_centro": int(f7["datacenter"].isna().sum()),
             "sin_tomo": int(f7["tomo"].isna().sum()), "con_tomo": int(len(t)), "tomos": int(t["tomo"].nunique()),
             "coinciden": int(t["coincide_con_anterior"].fillna(False).astype(bool).sum())}
    # Segunda vía: recuento propio en bucle con el tomo armado de centro, vault y ranura
    propio = [None if (pd.isna(c) or pd.isna(v) or pd.isna(s)) else f"{c}|{int(v)}|{int(s)}"
              for c, v, s in zip(f7["datacenter"], f7["vault_id"], f7["pod_slot_num"])]
    n_b, tomos_b, coinc_b = coincidencias_bucle(propio, dia_indice(f7["dia_fallo"]).tolist(),
                                                f7["plazo_reconstruccion_dias"].tolist())
    sv.append(comparar("fallos con tomo, tomos y coincidencias", "columnas tomo y coincide_con_anterior de fallos_detalle",
                       "recuento propio en bucle con centro, vault y ranura",
                       pd.Series({"con_tomo": tabla["con_tomo"], "tomos": tabla["tomos"], "coinciden": tabla["coinciden"]}),
                       pd.Series({"con_tomo": n_b, "tomos": tomos_b, "coinciden": coinc_b})))
    # Tomos con k fallos en d días, en total y por trimestre
    trimestres = sorted({trimestre_de(x) for x in pd.date_range(INICIO_SITIO, FECHA_DATOS, freq="MS")})
    tomo, dia = t["tomo"].to_numpy(), t["dia"].to_numpy()
    kd = []
    for k, dd in K_D:
        res = k_en_d(tomo, dia, k, dd)
        cuenta = pd.Series([t["q"].iloc[i] for i in res.values()], dtype=object).value_counts()
        kd.append({"k": k, "d": dd, "tomos": len(res), "por_trimestre": {q: int(cuenta.get(q, 0)) for q in trimestres}})
    # Frente al azar: los días se barajan dentro de cada centro y trimestre del fallo (petición 19); el azar de solo el
    # centro, el de antes, va al lado con las mismas repeticiones y la misma semilla. El lado frente al p95 es un
    # resultado de cada medida, no una condición para seguir
    def frente_al_azar(az):
        """Observados, media, p95, mínimo, máximo y lado de cada medida frente a sus repeticiones."""
        out = []
        for (k, dd), xs in az.items():
            obs = next(x["tomos"] for x in kd if (x["k"], x["d"]) == (k, dd))
            p95 = float(np.percentile(xs, 95))
            out.append({"k": k, "d": dd, "observados": obs, "media": float(np.mean(xs)), "p95": p95,
                        "minimo": int(min(xs)), "maximo": int(max(xs)), "por_encima_del_p95": obs > p95})
        return out

    estrato = (t["datacenter"].astype(str) + "|" + t["q"]).to_numpy()
    az = azar_tomos(estrato, tomo, dia, AZAR, ITERACIONES, SEMILLA)
    resultados = frente_al_azar(az)
    az_c = azar_tomos(t["datacenter"].to_numpy(), tomo, dia, AZAR, ITERACIONES, SEMILLA)
    resultados_c = frente_al_azar(az_c)
    # Discos a la vez y la paridad supuesta
    alv = a_la_vez(tomo, dia, t["plazo_reconstruccion_dias"].to_numpy())
    t["a_la_vez"] = alv
    t["paridad"] = [paridad(c) for c in t["capacidad_tb"]]
    rep = t["a_la_vez"].value_counts().sort_index()
    por_cap = (t.groupby(["capacidad_tb", "a_la_vez"]).size().reset_index(name="fallos")
               .sort_values(["a_la_vez", "capacidad_tb"], ascending=[False, True], kind="mergesort"))
    alv_tabla = {"reparto": {str(int(k)): int(v) for k, v in rep.items()},
                 "por_capacidad": [{"capacidad_tb": float(x["capacidad_tb"]), "a_la_vez": int(x["a_la_vez"]),
                                    "fallos": int(x["fallos"])} for _, x in por_cap.iterrows()],
                 "llegan_a_paridad": int((t["a_la_vez"] >= t["paridad"]).sum())}
    # Los peores tomos: más coincidencias, luego más fallos, luego más a la vez, luego por nombre
    pt = (t.assign(c=t["coincide_con_anterior"].fillna(False).astype(bool).astype(int)).groupby("tomo")
          .agg(fallos=("dia", "size"), coincidencias=("c", "sum"), max_a_la_vez=("a_la_vez", "max")).reset_index())

    def ordenar(x):
        """Orden de los peores tomos; no depende del orden de las filas."""
        return x.sort_values(["coincidencias", "fallos", "max_a_la_vez", "tomo"], ascending=[False, False, False, True],
                             kind="mergesort")["tomo"].head(N_TOMOS).tolist()

    primeros = ordenar(pt)
    peores = []
    for nombre in primeros:
        x = t.loc[t["tomo"] == nombre]
        f0 = pt.loc[pt["tomo"] == nombre].iloc[0]
        peores.append({"tomo": nombre, "centro": x["datacenter"].iloc[0], "vault": int(x["vault_id"].iloc[0]),
                       "ranura": int(x["pod_slot_num"].iloc[0]), "modelos": sorted(x["model"].unique().tolist()),
                       "fallos": int(f0["fallos"]), "coincidencias": int(f0["coincidencias"]),
                       "max_a_la_vez": int(f0["max_a_la_vez"]),
                       "linea_de_tiempo": [{"dia": iso(y["dia_fallo"]), "model": y["model"],
                                            # Vacío (NA) en el primer fallo de su tomo: no tiene anterior, no coincide
                                            "coincide": bool(pd.notna(y["coincide_con_anterior"])
                                                             and y["coincide_con_anterior"]),
                                            "a_la_vez": int(y["a_la_vez"])}
                                           for _, y in x.iterrows()]})
    tomos_por_fallos = {str(int(k)): int(v) for k, v in pt["fallos"].value_counts().sort_index().items()}
    # Riesgo vivo: cada mes, tomos con 2 o más y 3 o más discos que avisan, frente a la binomial
    sel = ((F["mi"].to_numpy() >= b["mi_sitio"]) & (F["dc"].to_numpy() >= 0) & (F["vault"].to_numpy() >= 0)
           & (F["slot"].to_numpy() >= 0))
    vmax, smax = int(F["vault"].to_numpy()[sel].max()) + 1, int(F["slot"].to_numpy()[sel].max()) + 1
    clave = ((F["dc"].to_numpy()[sel].astype(np.int64) * vmax + F["vault"].to_numpy()[sel]) * smax
             + F["slot"].to_numpy()[sel])
    rv = riesgo_vivo(F["mi"].to_numpy()[sel], clave, F["avisa"].to_numpy()[sel])
    for x in rv:
        x["mes"] = iso(mes_fecha(x["mes"]))
    n = len(rv)
    riesgo = {"meses": rv, "media_dos": sum(x["dos_o_mas"] for x in rv) / n,
              "media_esperados_dos": sum(x["esperados_dos"] for x in rv) / n,
              "media_tres": sum(x["tres_o_mas"] for x in rv) / n,
              "media_esperados_tres": sum(x["esperados_tres"] for x in rv) / n,
              "min_dos": min(x["dos_o_mas"] for x in rv), "max_dos": max(x["dos_o_mas"] for x in rv),
              "ultimo_dos": rv[-1]["dos_o_mas"], "ultimo_tres": rv[-1]["tres_o_mas"]}
    riesgo["razon_dos"] = riesgo["media_dos"] / riesgo["media_esperados_dos"]
    riesgo["razon_tres"] = riesgo["media_tres"] / riesgo["media_esperados_tres"]
    # Comprobaciones
    ok = {s["nombre"]: s["coinciden"] for s in sv}
    barajado = pt.sample(frac=1.0, random_state=SEMILLA)
    comp = {"unidad": comp_unidad(zip(f7["serial_number"], f7["dia_fallo"])),
            "minimo": None,
            "empates": ordenar(barajado) == primeros,
            "referencia": all(len(xs) == ITERACIONES for xs in list(az.values()) + list(az_c.values()))
            and comp_referencia([len(t)], len(tomo)),
            "azar_en_grupos": all(x["media"] is not None and x["p95"] is not None for x in resultados),
            "pesos": None, "hacia_adelante": None,
            "cobertura": comp_cobertura(tabla["con_tomo"] / tabla["desde_07_2023"] if tabla["desde_07_2023"] else None),
            "periodos": comp_periodos([{"t": q, "parcial": b["trimestres"][q]["parcial"]} for q in trimestres], "t",
                                      {q for q in trimestres if b["trimestres"][q]["parcial"]})}
    extra = {"lado_del_azar": comp_lado_azar(resultados + resultados_c)}
    pob = POBLACION + "; fallos del 01/07/2023 al 30/06/2025 con su centro, vault y ranura"
    cifras = [cifra(n_, f"preguntas.B7.tablas.fallos.{c}", tabla[c], u, pob, periodo, int(len(f7)), v,
                    "recuento propio en bucle", ok["fallos con tomo, tomos y coincidencias"])
              for n_, c, u, v in [("fallos con tomo", "con_tomo", "fallos", n_b), ("tomos", "tomos", "tomos", tomos_b),
                                  ("fallos que coinciden con el anterior de su tomo", "coinciden", "fallos", coinc_b)]]
    tablas = {"fallos": tabla, "k_en_d": kd,
              "azar": {"estrato": "centro y trimestre", "iteraciones": ITERACIONES, "semilla": SEMILLA,
                       "resultados": resultados,
                       "solo_centro": {"estrato": "centro", "iteraciones": ITERACIONES, "semilla": SEMILLA,
                                       "resultados": resultados_c}},
              "a_la_vez": alv_tabla, "peores_tomos": peores, "tomos_por_fallos": tomos_por_fallos,
              "riesgo_vivo": riesgo}
    q = {"id": "B7", "pregunta": "Cuántas veces caen varios discos del mismo tomo cerca en el tiempo, y si pasa más que por azar",
         "decision": "si el riesgo de perder datos pide vigilar los tomos donde acaba de fallar un disco",
         "planteamiento": "config/metodo/plan_de_la_analitica.md, bloque 7; metodo/04_planteamientos.md §1.A",
         "funcion": "otra",
         "funcion_adaptada": ("ninguna función del capítulo 42 compara agrupaciones en el tiempo con el azar: se barajan "
                              "los días de los fallos dentro de cada centro y trimestre del fallo (criterio 4, con el "
                              "trimestre de la petición 19; el de solo el centro, al lado) y el riesgo vivo se compara "
                              "con la binomial (criterio 6)"),
         "poblacion": {"regla": pob, "periodo": periodo, "filas": int(len(f7)), "unidad": "tomo (centro, vault y ranura)",
                       "entidades": tabla["tomos"]},
         "medida": ("tomos con k fallos en d días; discos que se rehacen a la vez al llegar cada fallo frente a la "
                    "paridad supuesta; tomos con 2 o más y 3 o más discos que avisan cada mes"),
         "minimo_casos": "no aplica: se cuentan todos los tomos y se comparan con el azar",
         "que_cambia_la_decision": "más tomos con fallos juntos que el percentil 95 del azar dice que los fallos van en grupo",
         "cifras": cifras,
         "referencia": {"que_es": f"los fallos barajados {ITERACIONES} veces dentro de su centro y trimestre, semilla "
                                  f"{SEMILLA}",
                        "valor": next(x["media"] for x in resultados if (x["k"], x["d"]) == (2, 30)),
                        "filas": ITERACIONES},
         "comprobaciones": comp,
         "motivos_null": {"minimo": "el bloque no saca conclusiones de grupos: compara recuentos de todos los tomos con "
                                    "el azar",
                          "pesos": "no hay ninguna puntuación con pesos",
                          "hacia_adelante": "los bloques 5 a 8 describen y no predicen"},
         "comprobaciones_extra": extra, "sin_conclusion": [], "tablas": tablas}
    return q, sv


def calcular_b8(d, b):
    """Bloque 8: temperatura, arranques, datos escritos y datos leídos, dentro de su grupo."""
    F, fd = d["F"], b["fd"]
    sv = []
    periodo = f"del {iso(FECHA_INICIO)} al {iso(FECHA_DATOS)}"
    mo = F["mo"].to_numpy()
    edad = F["edad"].to_numpy()
    ea = np.where(np.isnan(edad), -1, np.floor(np.where(np.isnan(edad), 0, edad))).astype(np.int64)
    peso = b["peso"]
    idx = fd["foto"].to_numpy()
    conf = idx >= 0
    fi = idx[conf]
    fotos_f, veces = np.unique(fi, return_counts=True)
    compartidas = fotos_f[veces > 1]
    # Segundas vías del reparto: fallos con su foto y días repartidos
    sv.append(comparar("fallos con su foto", "unión con fotos_riesgo por disco y mes",
                       "fallos_detalle con ultima_foto_anterior", pd.Series({"fallos": int(conf.sum())}),
                       pd.Series({"fallos": b["con_uf"]})))
    rp = b["reparto"]
    sv.append(comparar("días repartidos por las fotos", "suma de los pesos de las fotos",
                       "recuento menos los días de las celdas sin foto", pd.Series({"dias": rp["dias_repartidos"]}),
                       pd.Series({"dias": rp["dias_recuento"] - rp["dias_sin_foto"]}), TOLERANCIA))
    # Grupos y tramos de cada factor
    ga = np.where(ea >= 0, mo.astype(np.int64) * BASE_MES + ea, -1)
    t194 = F["t194"].to_numpy()
    med_t = pd.Series(t194).groupby(mo).median()
    tramos_t = tramo_temperatura(t194 - med_t.reindex(mo).to_numpy())
    s12 = F["s12"].to_numpy()
    med_a = pd.Series(s12).groupby(ga).median()
    m_a = med_a.reindex(ga).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        razon_a = np.where((m_a > 0) & (ga >= 0), s12 / np.where(m_a > 0, m_a, 1.0), np.nan)
    tramos_a = tramo_arranques(razon_a)
    s9, s241, s242 = F["s9"].to_numpy(), F["s241"].to_numpy(), F["s242"].to_numpy()
    seagate = b["fab_mo"][mo] == "Seagate"
    with np.errstate(invalid="ignore"):
        m_s = seagate & (s241 > 0) & (s9 > 0) & (ga >= 0)
    g_s = np.where(m_s, ga, -1)
    factores_def = {"temperatura": (mo.astype(np.int64), tramos_t, np.ones(len(F), dtype=bool))}
    factores_def["arranques"] = (ga, tramos_a, ga >= 0)
    for nombre, cont in [("escritos", s241), ("leidos", s242)]:
        valor = np.full(len(F), np.nan)
        valor[m_s] = cont[m_s] / (s9[m_s] / H_ANO)
        pct = np.full(len(F), np.nan)
        pct[m_s] = rango_por_grupo(g_s[m_s], valor[m_s])
        factores_def[nombre] = (g_s, tramo_tercio(pct), m_s, valor)
    factores, empates_ok = {}, True
    con_foto = int(conf.sum())
    for nombre, defn in factores_def.items():
        grupo, tramo = defn[0], defn[1]
        poblacion = defn[2]
        gr = grupos_factor(np.where(poblacion, grupo, -1), tramo, peso, np.where(poblacion[fi], grupo[fi], -1), tramo[fi])
        etiquetas = TRAMOS[nombre]
        for x in gr["tramos"]:
            x["nombre"] = etiquetas[x["tramo"]]
        if nombre in ("escritos", "leidos"):
            sel = poblacion & (tramo >= 0)
            empates_ok &= comp_empates(zip(grupo[sel], defn[3][sel]), tramo[sel])
        por_fab = []
        if nombre == "temperatura":
            ti = gr["tabla"].assign(fab=lambda x: b["fab_mo"][x["g"].to_numpy()])
            for (fab, tt), x in ti.groupby(["fab", "t"], sort=True):
                ee = float(x["esp"].sum())
                rz = razon_poisson(int(x["fallos"].sum()), ee) if ee > 0 else (None, None, None)
                tasa = intervalo_poisson(int(x["fallos"].sum()), float(x["dias"].sum())) if x["dias"].sum() > 0 else (None,) * 3
                por_fab.append({"fabricante": fab, "tramo": etiquetas[int(tt)], "dias": float(x["dias"].sum()),
                                "fallos": int(x["fallos"].sum()), "tasa": tasa[0], "esperados": ee, "razon": rz[0],
                                "desde": rz[1], "hasta": rz[2]})
        nombres_g = ({int(g): d["modelos"][int(g)] for g in set(grupo[grupo >= 0].tolist())} if nombre == "temperatura"
                     else {int(g): f"{d['modelos'][int(g) // BASE_MES]}, {int(g) % BASE_MES} años"
                           for g in set(grupo[grupo >= 0].tolist())})
        for x in gr["aparte"]["lista"]:
            x["grupo"] = nombres_g[x["grupo"]]
        factores[nombre] = {k: v for k, v in gr.items() if k not in ("entran", "tasa_grupo", "tabla")}
        factores[nombre]["grupos_que_entran"] = [nombres_g[g] for g in gr["entran"]]
        factores[nombre]["por_fabricante"] = por_fab
        factores[nombre]["partes_suman"] = comp_partes(gr["fallos_entran"], gr["aparte"]["fallos"],
                                                       gr["sin_tramo"]["fallos"], con_foto)
    ok = {s["nombre"]: s["coinciden"] for s in sv}
    # Solo los tramos con razón: un factor sin ningún grupo que entre no compara nada
    tramos_all = [x for f in factores.values() if f["grupos_entran"] > 0 for x in f["tramos"]]
    # La unidad es el fallo: cada uno una vez. Dos fallos de un disco sin foto nueva entre ellos toman la misma foto
    comp = {"unidad": bool(b["fotos_unicas"]) and comp_unidad(zip(fd["serial_number"], fd["dia_fallo"])),
            "minimo": all(all(x["fallos"] >= MINIMO_FALLOS for x in f["tramos"]) or f["grupos_entran"] == 0
                          for f in factores.values())
            and all(all(sum(1 for v in x["fallos_por_tramo"] if v >= MINIMO_FALLOS) < 3 for x in f["aparte"]["lista"])
                    for f in factores.values()),
            "empates": bool(empates_ok),
            "referencia": all(comp_referencia([x["esperados"] for x in f["tramos"]], f["fallos_entran"])
                              for f in factores.values() if f["grupos_entran"] > 0),
            "azar_en_grupos": comp_azar(len(tramos_all), len(tramos_all) * (1 - CONFIANZA),
                                        [(x["desde"], x["hasta"]) for x in tramos_all]),
            "pesos": None, "hacia_adelante": None,
            "cobertura": comp_cobertura(con_foto / len(fd)),
            "periodos": not any(m in b["meses_parciales"] for m in np.unique(F["mi"].to_numpy()).tolist())}
    extra = {"partes_suman_total": all(f["partes_suman"] for f in factores.values())}
    distintos = sum(1 for x in tramos_all if x["desde"] is not None and (x["desde"] > 1 or x["hasta"] < 1))
    pob = POBLACION + "; fotos de fotos_riesgo con los días del recuento repartidos, y fallos con su foto anterior"
    cifras = [cifra("fallos con su foto anterior", "preguntas.B8.tablas.reparto.fallos_con_foto", con_foto, "fallos", pob,
                    periodo, int(len(fd)), b["con_uf"], "fallos_detalle con ultima_foto_anterior", ok["fallos con su foto"]),
              cifra("días repartidos por las fotos", "preguntas.B8.tablas.reparto.dias_repartidos", rp["dias_repartidos"],
                    "días de disco", pob, periodo, int(len(F)), rp["dias_recuento"] - rp["dias_sin_foto"],
                    "recuento menos los días sin foto", ok["días repartidos por las fotos"])]
    tasa_ref = FACTOR_TASA * con_foto / rp["dias_repartidos"]
    tablas = {"reparto": {**rp, "fallos_con_foto": con_foto, "fallos_sin_foto_anterior": int(len(fd)) - b["con_uf"],
                          "fallos_con_fecha_sin_foto": b["con_uf"] - con_foto,
                          "fallos_que_comparten_foto": int(np.isin(fi, compartidas).sum()),
                          "discos_con_fallos_que_comparten_foto": int(np.unique(
                              fd.loc[conf, "serial_number"].to_numpy()[np.isin(fi, compartidas)]).size)},
              "factores": factores, "azar": {"tramos": len(tramos_all), "distintos_de_1": distintos,
                                             "esperados_por_azar": len(tramos_all) * (1 - CONFIANZA)},
              "medianas": {"temperatura_modelos": int(med_t.notna().sum()), "arranques_grupos": int(med_a.notna().sum())}}
    q = {"id": "B8", "pregunta": "Si la temperatura, la carga de trabajo o los arranques acompañan a más fallos",
         "decision": "si alguno de esos factores merece vigilarse dentro de cada modelo",
         "planteamiento": "config/metodo/plan_de_la_analitica.md, bloque 8; metodo/04_planteamientos.md §1.A",
         "funcion": "comparar_con_total",
         "funcion_adaptada": ("comparar_con_total del 42.6 pasado a tasas por días de disco: cada tramo se compara con "
                              "la tasa de su propio grupo (modelo, o modelo y año de edad) por la razón de observados "
                              "entre esperados, con el intervalo de Poisson; el mínimo es de 20 fallos por tramo"),
         "poblacion": {"regla": pob, "periodo": periodo, "filas": int(len(F)), "unidad": "foto mensual de un disco",
                       "entidades": int(np.unique(F["sc"].to_numpy()).size)},
         "medida": ("tasa anual por tramo y razón de observados entre esperados con la tasa de su grupo; los días salen "
                    "del recuento repartidos por las fotos (criterio 7)"),
         "minimo_casos": "20 fallos en cada uno de los tres tramos de un grupo (petición, criterio 8)",
         "que_cambia_la_decision": "un tramo cuyo intervalo de la razón queda entero por encima o por debajo de 1",
         "cifras": cifras,
         "referencia": {"que_es": "la tasa de su grupo, razón 1; al lado, la tasa de todas las fotos con su reparto",
                        "valor": tasa_ref, "filas": int(len(F))},
         "comprobaciones": comp,
         "motivos_null": {"pesos": "no hay ninguna puntuación con pesos",
                          "hacia_adelante": "los bloques 5 a 8 describen y no predicen"},
         "comprobaciones_extra": extra,
         "sin_conclusion": [{"bloque": "B8", "grupo": f"{n}: grupos que no llegan a 20 fallos en sus tres tramos",
                             "casos": f["aparte"]["fallos"]} for n, f in factores.items()],
         "tablas": tablas}
    return q, sv


def calcular_mc(d, b):
    """El minicubo de perfiles y lo que falta en los datos."""
    F, fd, rec, ven = d["F"], b["fd"], d["rec"], d["ven"]
    sv = []
    periodo = f"del {iso(FECHA_INICIO)} al {iso(FECHA_DATOS)}"
    mo, mi = F["mo"].to_numpy(), F["mi"].to_numpy()
    nombres_c = d["centros"] + [SIN_DATO, ANTES]
    cod_c = np.where(mi < b["mi_sitio"], len(d["centros"]) + 1, np.where(F["dc"].to_numpy() < 0, len(d["centros"]),
                                                                         F["dc"].to_numpy()))
    edades = [f"{x:02d}_{x}" for x in range(TOPE_EDAD)] + [f"{TOPE_EDAD:02d}_{TOPE_EDAD}_o_mas"]
    e = F["edad"].to_numpy()
    cod_e = np.clip(np.floor(np.where(np.isnan(e), 0, e)), 0, TOPE_EDAD).astype(np.int64)
    if np.isnan(e).any():
        raise Parada("ERROR", "fotos_riesgo trae fotos sin edad: el minicubo no puede darles tramo")
    fabs = sorted(set(b["fab_mo"].tolist()))
    caps = sorted(set(b["cap_mo"].tolist()))
    dims = {"fabricante": pd.Categorical.from_codes(pd.Categorical(b["fab_mo"], categories=fabs).codes[mo], fabs),
            "capacidad_tb": pd.Categorical.from_codes(pd.Categorical(b["cap_mo"], categories=caps).codes[mo], caps),
            "edad": pd.Categorical.from_codes(cod_e, edades),
            "centro": pd.Categorical.from_codes(cod_c, nombres_c),
            "avisa": pd.Categorical.from_codes(F["avisa"].to_numpy().astype(np.int64), ["no", "sí"])}
    fi = fd["foto"].to_numpy()
    fi = fi[fi >= 0]
    fallo_dims = {k: np.asarray(v)[fi] for k, v in dims.items()}
    # φ de la edad (el de B3 del 09, calculado igual con dias_por_tramo): ensancha cada intervalo del minicubo
    phi_mc = phi_edad(d["dpt"])
    n1, n2 = minicubo(dims, b["peso"], fallo_dims, phi=phi_mc["phi"])
    rp = b["reparto"]
    total = rp["dias_recuento"] - rp["dias_sin_foto"]
    sv.append(comparar("fallos por dimensión del minicubo", "minicubo, con la foto de cada fallo",
                       "fallos_detalle con ultima_foto_anterior",
                       pd.Series({dim: sum(x["fallos"] for x in n1 if x["dimension"] == dim) for dim in DIMENSIONES}),
                       pd.Series({dim: b["con_uf"] for dim in DIMENSIONES})))
    sv.append(comparar("días por dimensión del minicubo", "minicubo, con el reparto de las fotos",
                       "recuento menos los días sin foto",
                       pd.Series({dim: sum(x["dias"] for x in n1 if x["dimension"] == dim) for dim in DIMENSIONES}),
                       pd.Series({dim: total for dim in DIMENSIONES}), TOLERANCIA))
    # Tasa de cada fabricante y capacidad: la del reparto frente a la del recuento (no tiene por qué ser exacta)
    rm = rec.assign(fabricante=rec["model"].map(dict(zip(d["modelos"], b["fab_mo"]))),
                    capacidad_tb=rec["model"].map(dict(zip(d["modelos"], b["cap_mo"]))))
    frente = []
    for dim in ("fabricante", "capacidad_tb"):
        g = rm.groupby(dim).agg(dias=("discos", "sum"), fallos=("fallos", "sum"))
        for v, x in g.iterrows():
            t_rec = FACTOR_TASA * x["fallos"] / x["dias"]
            t_rep = next(y["tasa"] for y in n1 if y["dimension"] == dim and y["valor"] == etiqueta_valor(v))
            frente.append({"dimension": dim, "valor": etiqueta_valor(v), "tasa_reparto": t_rep, "tasa_recuento": t_rec,
                           "diferencia": t_rep - t_rec})
    # Lo que falta en los datos
    trims = ["2024T3", "2024T4", "2025T1", "2025T2"]
    fq = fd.assign(q=[trimestre_de(x) for x in fd["dia_fallo"]])
    vd = ven.loc[ven["fecha"] == ven["dia_fallo"], ["serial_number", "dia_fallo", "pod_slot_num"]].rename(
        columns={"pod_slot_num": "ranura_dia"})
    vd = fq.merge(vd, on=["serial_number", "dia_fallo"], how="left", indicator=True)
    sin_ranura = {q: {"fallos": int((vd["q"] == q).sum()),
                      "sin_fila_del_dia": int(((vd["q"] == q) & (vd["_merge"] == "left_only")).sum()),
                      "sin_ranura": int(((vd["q"] == q) & (vd["_merge"] == "both") & vd["ranura_dia"].isna()).sum())}
                  for q in trims}
    sitio = fq["dia_fallo"] >= pd.Timestamp(INICIO_SITIO)
    sin_tomo = {q: int(((fq["q"] == q) & sitio & fq["tomo"].isna()).sum()) for q in trims}
    falta = {"sin_ranura_dia_fallo": sin_ranura, "sin_tomo_fallos_detalle": sin_tomo,
             "reglas_dicen": "de 20 a 36 fallos sin ranura por trimestre, medido en el reconocimiento con otros datos",
             "coinciden_con_las_reglas": all(20 <= sin_tomo[q] <= 36 for q in trims[1:]),
             "desaparecen_sin_fallo": int(b["vida_desaparece"].sum()),
             "fallos_antes_de_07_2023": int((~sitio).sum()),
             "smart_90_no_vacio": int(F["s90"].to_numpy().sum())}
    # Comprobaciones
    ok = {s["nombre"]: s["coinciden"] for s in sv}
    tasa_todos = FACTOR_TASA * len(fi) / rp["dias_repartidos"]
    con_concl = [x for x in n1 if not x["sin_conclusion"]]
    celdas2 = [c for x in n2 for c in x["primeras"]]
    antes = len(d["centros"]) + 1
    comp = {"unidad": all(sum(x["fotos"] for x in n1 if x["dimension"] == dim) == len(F) for dim in DIMENSIONES),
            "minimo": comp_minimo([True] * len(celdas2), [c["dias"] for c in celdas2], [c["fallos"] for c in celdas2],
                                  MINIMO_DIAS_ANO, MINIMO_FALLOS)
            and comp_minimo([x["frente_al_total"] is not None for x in n1], [x["dias"] for x in n1],
                            [x["fallos"] for x in n1], MINIMO_DIAS_ANO, MINIMO_FALLOS),
            "empates": all(comp_empates([c["tasa"] for c in x["primeras"]],
                                        pd.Series([c["tasa"] for c in x["primeras"]], dtype=float)
                                        .rank(method="min", ascending=False).tolist()) for x in n2),
            "referencia": all(comp_referencia([x["dias"] for x in n1 if x["dimension"] == dim], rp["dias_repartidos"])
                              for dim in DIMENSIONES),
            "azar_en_grupos": comp_azar(len(con_concl), len(con_concl) * (1 - CONFIANZA),
                                        [(x["desde"], x["hasta"]) for x in con_concl]),
            "pesos": None, "hacia_adelante": None,
            "cobertura": comp_cobertura(rp["dias_repartidos"] / rp["dias_recuento"]),
            "periodos": bool((cod_c[mi < b["mi_sitio"]] == antes).all())
            and not bool((cod_c[mi >= b["mi_sitio"]] == antes).any())}
    pob = POBLACION + "; fotos de fotos_riesgo con los días repartidos y fallos con su foto anterior"
    cifras = [cifra(f"fallos por {dim}", f"preguntas.MC.tablas.nivel_1[{dim}].fallos", b["con_uf"], "fallos", pob,
                    periodo, int(len(F)), b["con_uf"], "fallos_detalle con ultima_foto_anterior",
                    ok["fallos por dimensión del minicubo"]) for dim in DIMENSIONES]
    cifras += [cifra(f"días por {dim}", f"preguntas.MC.tablas.nivel_1[{dim}].dias", rp["dias_repartidos"], "días de disco",
                     pob, periodo, int(len(F)), total, "recuento menos los días sin foto",
                     ok["días por dimensión del minicubo"]) for dim in DIMENSIONES]
    tablas = {"tasa_todos": tasa_todos, "phi": phi_mc, "nivel_1": n1, "nivel_2": n2, "segunda_via_recuento": frente,
              "azar": {"valores_con_conclusion": len(con_concl),
                       "distintos": sum(1 for x in con_concl if x["frente_al_total"] != "no se distingue"),
                       "esperados_por_azar": len(con_concl) * (1 - CONFIANZA)},
              "lo_que_falta": falta}
    q = {"id": "MC", "pregunta": "Qué perfiles de disco tienen más riesgo, por fabricante, capacidad, edad, centro y aviso",
         "decision": "dónde mirar primero y qué tasa estimar para una combinación con pocos discos",
         "planteamiento": "config/metodo/plan_de_la_analitica.md, «Cierre del análisis»; assets/23_metodo_minicubo.md",
         "funcion": "minicubo",
         "funcion_adaptada": ("la métrica es la tasa anual con sus días y sus fallos, una razón de sumas y no una "
                              "mediana: una mediana por foto no da una tasa por días de disco (13.13 y 5.5); cada valor "
                              "lleva su recuento de fotos, días y fallos, y su intervalo exacto de Poisson con el φ de "
                              "la edad (petición 19)"),
         "poblacion": {"regla": pob, "periodo": periodo, "filas": int(len(F)), "unidad": "foto mensual de un disco",
                       "entidades": int(np.unique(F["sc"].to_numpy()).size)},
         "medida": ("tasa anual = 100 × 365 × fallos con su foto / días repartidos, por valor y por par de valores; el "
                    "intervalo, con fallos y días entre el φ de la edad"),
         "minimo_casos": "50.000 días de disco y 20 fallos por valor o celda (petición, criterio 9)",
         "que_cambia_la_decision": "un valor o una celda cuyo intervalo queda por encima de la tasa de todos",
         "cifras": cifras,
         "referencia": {"que_es": "la tasa de todas las fotos con el mismo reparto", "valor": tasa_todos,
                        "filas": int(len(F))},
         "comprobaciones": comp,
         "motivos_null": {"pesos": "no hay ninguna puntuación con pesos",
                          "hacia_adelante": "los bloques 5 a 8 describen y no predicen"},
         "comprobaciones_extra": {"phi_minimo_uno": comp_phi([phi_mc])},
         "sin_conclusion": [{"bloque": "MC", "grupo": f"{x['dimension']} {x['valor']}", "casos": x["fallos"],
                             "dias_disco": x["dias"]} for x in n1 if x["sin_conclusion"]],
         "tablas": tablas}
    return q, sv


def calcular(d):
    """Calcula los cinco bloques con sus tablas, cifras, referencias y comprobaciones; no escribe nada."""
    b = preparar(d)
    preguntas, sv = [], []
    for f in (calcular_b5, calcular_b6, calcular_b7, calcular_b8, calcular_mc):
        q, s = f(d, b)
        preguntas.append(q)
        sv += s
    return {"preguntas": preguntas, "segundas_vias": sv}


# =================================================================================================================
# 11. Validaciones (método §7) y búsqueda de resultados escritos
# =================================================================================================================
def buscar_resultados_escritos(texto):
    """Líneas del código con una comprobación o validación puesta a True o con una cifra de cuatro cifras o más.

    Solo pasan el mínimo de días de las reglas (§7), las horas de un año de edad y los años de los datos. Devuelve
    [(línea, texto)].
    """
    claves = "|".join(COMPROBACIONES + VALIDACIONES + EXTRAS + ["coinciden"])
    p_true = re.compile(r"[\"'](" + claves + r")[\"']\s*\]?\s*[:=]\s*True\b|\b(" + claves + r")\s*=\s*True\b")
    p_num = re.compile(r"(?<![\w.])\d[\d_]{3,}(?![\w.])")
    permitidas = {str(MINIMO_DIAS_ANO), str(H_ANO)} | {str(a) for a in range(FECHA_INICIO.year, FECHA_DATOS.year + 2)}
    hallado = []
    for n, linea in enumerate(texto.splitlines(), 1):
        if p_true.search(linea):
            hallado.append((n, linea.strip()))
            continue
        if any(m.replace("_", "") not in permitidas for m in p_num.findall(linea)):
            hallado.append((n, linea.strip()))
    return hallado


def validar(res, fuente, h_antes, h_despues, res2):
    """Las nueve validaciones de el método, cada una calculada sobre el resultado y el código."""
    pregs = res.get("preguntas", [])

    def lleno(x):
        """Cierto si el texto no está vacío."""
        return isinstance(x, str) and x.strip() != ""

    planteamiento = bool(pregs) and all(
        all(lleno(p.get(k)) for k in ["pregunta", "decision", "planteamiento", "funcion", "medida", "minimo_casos",
                                      "que_cambia_la_decision"])
        and all(lleno(p["poblacion"].get(k)) for k in ["regla", "periodo", "unidad"])
        and lleno(p["referencia"].get("que_es")) for p in pregs)
    cifras = [c for p in pregs for c in p.get("cifras", [])]
    con_poblacion = bool(cifras) and all(lleno(c.get("poblacion")) and lleno(c.get("periodo")) and c.get("filas") is not None
                                         for c in cifras)
    segunda = (bool(cifras) and all(c.get("segunda_via") is not None and c.get("coinciden") is True for c in cifras)
               and all(s.get("coinciden") is True for s in res.get("segundas_vias", [])))
    minimo = all(p["comprobaciones"].get("minimo") is not False for p in pregs)
    referencia = all(p["referencia"].get("valor") is not None and p["referencia"].get("filas") is not None for p in pregs)
    calculadas = all(
        set(p["comprobaciones"]) == set(COMPROBACIONES)
        and all(v is True or v is False or (v is None and lleno(p.get("motivos_null", {}).get(k)))
                for k, v in p["comprobaciones"].items()) for p in pregs)
    reproducible = (json.dumps(nativo(res.get("preguntas")), sort_keys=True, ensure_ascii=False)
                    == json.dumps(nativo(res2.get("preguntas")), sort_keys=True, ensure_ascii=False))
    return {"planteamiento_completo": bool(planteamiento), "cifras_con_poblacion": bool(con_poblacion),
            "segunda_via": bool(segunda), "minimo_respetado": bool(minimo), "con_referencia": bool(referencia),
            "comprobaciones_calculadas": bool(calculadas), "reproducible": bool(reproducible),
            "sin_resultados_escritos": buscar_resultados_escritos(fuente) == [],
            "raw_intacto": bool(h_antes) and h_antes == h_despues}


# =================================================================================================================
# 12. Informe para la persona (transmision-conocimiento), generado del mismo diccionario
# =================================================================================================================
def pct(x, d=2):
    """Un porcentaje a la española, o «sin dato»."""
    return "sin dato" if x is None else numero(x, d, " %")


def num(x, d=0):
    """Un número a la española, o «sin dato»."""
    return "sin dato" if x is None else numero(x, d)


def fecha_es(texto_iso):
    """«2025-06-30» -> «30/06/2025»."""
    a, m, d = texto_iso[:10].split("-")
    return f"{d}/{m}/{a}"


def cientifica(x):
    """Un número pequeño en notación científica con coma decimal; el cero, «0»."""
    return "0" if not x else f"{x:.1e}".replace(".", ",")


NOMBRES_FACTOR = {"temperatura": "Temperatura", "arranques": "Arranques", "escritos": "Datos escritos",
                  "leidos": "Datos leídos"}
NOMBRES_COMPROBACION = {"unidad": "La unidad", "minimo": "El mínimo de casos", "empates": "Los empates",
                        "referencia": "La referencia", "azar_en_grupos": "El azar en muchos grupos",
                        "pesos": "Los pesos", "hacia_adelante": "Hacia adelante", "cobertura": "La cobertura",
                        "periodos": "Los periodos"}
NOMBRES_EXTRA = {"sin_validacion": "ninguna cifra cruzada con el fallo a 30 días usa una foto de validación",
                 "partes_suman_total": "en cada factor, los fallos de los tramos, de los grupos aparte y sin tramo suman "
                                       "los fallos con foto",
                 "lado_del_azar": "la marca «por encima del percentil 95» de cada medida del azar sale de comparar sus "
                                  "tomos observados con su percentil 95",
                 "phi_minimo_uno": "cada φ usado es el medido y, si sale menor que 1, vale 1",
                 "veredicto_del_intervalo": "la lectura de cada centro sale de su intervalo con φ",
                 "sin_palabra_vetada": "ni el JSON ni este informe llevan la palabra vetada para el conjunto de discos"}
NOMBRES_VALIDACION = {"planteamiento_completo": "cada pregunta tiene su planteamiento completo",
                      "cifras_con_poblacion": "cada cifra dice su población, sus filas y su periodo",
                      "segunda_via": "cada cifra tiene su segunda vía, y coinciden",
                      "minimo_respetado": "ninguna conclusión sale de un grupo por debajo del mínimo",
                      "con_referencia": "cada resultado lleva su referencia, con las mismas filas",
                      "comprobaciones_calculadas": "las comprobaciones tienen su resultado o su motivo",
                      "reproducible": "dos cálculos seguidos dan las mismas cifras",
                      "sin_resultados_escritos": "el script no lleva ningún resultado escrito a mano",
                      "raw_intacto": "los ficheros de data/raw/ no cambian"}


def seccion_comprobaciones(L, q):
    """Las nueve comprobaciones de una pregunta y las de la petición, con su resultado o su motivo."""
    L.append(f"Las comprobaciones de {q['id']}:")
    L.append("")
    for k, v in q["comprobaciones"].items():
        texto = "sí" if v is True else "no" if v is False else "no aplica, porque " + q["motivos_null"][k]
        L.append(f"- {NOMBRES_COMPROBACION[k]}: {texto}.")
    for k, v in q.get("comprobaciones_extra", {}).items():
        L.append(f"- Del petición, {NOMBRES_EXTRA[k]}: {'sí' if v else 'no'}.")
    L.append("")


def informe(j):
    """Texto Markdown del informe, con los apartados de resultado.md, a partir del JSON."""
    L = []
    est = j["resultado"]
    L.append("# Centros de datos, avisos, tomos, otros factores y perfiles de riesgo")
    L.append("")
    L.append(f"Caso 68, paso 5, bloques 5 a 8 del plan de la analítica, el minicubo y lo que falta en los datos. Datos "
             f"hasta el {fecha_es(j['fecha_datos'])}; ejecutado el {fecha_es(j['fecha_ejecucion'])}. Estado: "
             f"**{est['estado']}**, riesgo {est['riesgo']}.")
    L.append("")
    L.append(est["resumen"])
    L.append("")
    if "preguntas" not in j:
        L.append("## Por qué paró")
        L.append("")
        for s in j.get("segundas_vias", []):
            if not s["coinciden"]:
                L.append(f"- La segunda vía «{s['nombre']}» no coincide: {s['diferentes']} claves distintas y "
                         f"{s['claves_en_una_sola_via']} en una sola vía.")
        for k, v in j.get("validaciones", {}).items():
            if v is False:
                L.append(f"- No se cumple que {NOMBRES_VALIDACION[k]}.")
        return "\n".join(L) + "\n"
    p = {q["id"]: q for q in j["preguntas"]}
    b5, b6, b7, b8, mc = (p[x]["tablas"] for x in ("B5", "B6", "B7", "B8", "MC"))

    # Las preguntas y su planteamiento
    L.append("## Las preguntas y su planteamiento")
    L.append("")
    L.append("Las cinco preguntas salen del plan de la analítica, aprobado por el responsable del caso el 16/11/2026, y del planteamiento "
             "1.A. Entran los discos de datos, sin los de arranque. Lo que va por centro y por tomo cubre del "
             "01/07/2023 al 30/06/2025, porque antes el sitio no consta; lo demás, del 01/01/2020 al 30/06/2025. La "
             "tasa anual de fallo es 100 × 365 × fallos / días de disco. Cuando el corte no está en el recuento, los "
             "días de cada modelo, centro y mes se reparten entre sus fotos.")
    L.append("")
    for q in j["preguntas"]:
        L.append(f"- **{q['id']}.** {q['pregunta']}. Mínimo: {q['minimo_casos']}.")
    L.append("")

    # B5
    L.append("## B5 · Si un centro falla más por sí mismo")
    L.append("")
    cen = b5["centros"]
    mas = [x["centro"] for x in cen if x["veredicto"] == "falla más por sí mismo"]
    menos = [x["centro"] for x in cen if x["veredicto"] == "falla menos"]
    L.append(f"Con la misma mezcla de modelo, año de edad y trimestre, {len(mas)} centros fallan más que los demás "
             f"({', '.join(mas) or 'ninguno'}) y {len(menos)} fallan menos ({', '.join(menos) or 'ninguno'}). Por azar "
             f"saldrían distintos {num(b5['azar']['esperados_por_azar'], 2)} de los "
             f"{b5['azar']['centros_con_conclusion']} centros con conclusión, y salen {b5['azar']['distintos']}. La "
             f"tasa de todos los centros juntos es del {pct(b5['ajustada']['tasa_todos'], 4)} anual.")
    L.append("")
    ph = b5["phi"]
    L.append(f"El intervalo de cada razón lleva φ = {num(ph['phi'], 4)}, lo que varían los fallos de un trimestre a otro "
             f"más de lo que supone Poisson, medido en {num(ph['celdas'])} celdas de centro y trimestre con "
             f"{num(ph['gl'])} grados de libertad (sin «sin dato»). Con φ = 1 no hay variación de más y el intervalo es "
             "el exacto de Poisson.")
    L.append("")
    sin_t = [x for x in cen if x["fallos_sin_tasa"]]
    if sin_t:
        L.append(f"{num(b5['ajustada']['fallos_sin_tasa'])} fallos caen en un modelo, año de edad y trimestre sin ningún "
                 "día de disco, así que no tienen tasa con la que calcular sus esperados. Cuentan en los observados de "
                 "su centro: " + ", ".join(f"{x['centro']}, {num(x['fallos_sin_tasa'])}" for x in sin_t) + ".")
        L.append("")
    L.append("| Centro | Días de disco | Fallos | Tasa bruta | Razón (intervalo) | Tasa ajustada | Lectura |")
    L.append("|---|---:|---:|---:|---|---:|---|")
    for x in cen:
        L.append(f"| {x['centro']} | {num(x['dias_disco'])} | {num(x['fallos'])} | {pct(x['tasa_bruta'], 4)} | "
                 f"{num(x['razon'], 4)} ({num(x['razon_desde'], 4)} a {num(x['razon_hasta'], 4)}) | "
                 f"{pct(x['tasa_ajustada'], 4)} | {x['veredicto']} |")
    L.append("")
    L.append("La tasa bruta usa los días del recuento por centro; la razón y la tasa ajustada usan los días repartidos "
             "por modelo y año de edad, que dejan fuera los días de las celdas sin foto.")
    L.append("")
    for x in b5["quitar_modelo"]:
        L.append(f"- Al quitar uno a uno los modelos de {x['centro']}, la lectura cambia en {x['cambios']} de los "
                 f"{x['modelos_probados']} modelos probados.")
    L.append(f"- {b5['modelos_minimo_dos_centros']} modelos pasan el mínimo de días en dos centros o más.")
    tm = {x["centro"]: x for x in b5["temperatura"]["por_centro"]}
    L.append("- Temperatura media desde 07/2023: " + "; ".join(
        f"{c}, {num(x['media'], 2)} °C" for c, x in tm.items()) + ".")
    L.append("")
    seccion_comprobaciones(L, p["B5"])

    # B6
    L.append("## B6 · Qué hace Backblaze con los avisos")
    L.append("")
    g = {x["grupo"]: x for x in b6["desenlace"]["grupos"]}
    ca, sa = g["con algún aviso"], g["sin aviso"]
    L.append(f"De las fotos con algún aviso, el {pct(ca['pct_falla'])} acaba en fallo antes de 90 días, frente al "
             f"{pct(sa['pct_falla'])} de las fotos sin aviso. El {pct(ca['pct_sigue'])} de las que avisan sigue "
             f"funcionando a los 90 días. La unidad es la foto: un disco que avisa cuenta cada mes, porque el aviso es "
             "acumulado.")
    L.append("")
    L.append("El intervalo de la parte que falla es el exacto de Clopper-Pearson, ensanchado por el φ de cada grupo: lo "
             "que varía de un trimestre a otro la parte de sus fotos que falla, más de lo que supone la binomial.")
    L.append("")
    L.append("| Grupo | Fotos | Discos | Sigue | Falla (intervalo) | φ | Desaparece | Frente a sin aviso |")
    L.append("|---|---:|---:|---:|---|---:|---:|---|")
    for x in b6["desenlace"]["grupos"]:
        L.append(f"| {x['grupo']} | {num(x['fotos'])} | {num(x['discos'])} | {pct(x['pct_sigue'])} | "
                 f"{pct(x['pct_falla'])} ({pct(x['falla_desde'], 3)} a {pct(x['falla_hasta'], 3)}) | "
                 f"{num(x['phi']['phi'], 1)} | {pct(x['pct_desaparece'])} | "
                 f"{'referencia' if x['grupo'] == 'sin aviso' else x['frente_a_sin_aviso'] or 'sin conclusión'} |")
    L.append("")
    # El mismo desenlace solo con Seagate (petición 17): es el único fabricante que trae los cinco contadores, así que
    # ahí cada contador se compara con el «sin aviso» de los mismos modelos
    ds = b6["desenlace_seagate"]
    L.append(f"Solo con las fotos de {ds['fabricante']}, el único fabricante que trae los cinco contadores, "
             f"{num(ds['fotos'])} fotos con 90 días por delante. Cada contador se compara con el «sin aviso» de "
             f"{ds['fabricante']}:")
    L.append("")
    L.append("| Grupo | Fotos | Discos | Sigue | Falla (intervalo) | φ | Desaparece | Frente a sin aviso |")
    L.append("|---|---:|---:|---:|---|---:|---:|---|")
    for x in ds["grupos"]:
        L.append(f"| {x['grupo']} | {num(x['fotos'])} | {num(x['discos'])} | {pct(x['pct_sigue'])} | "
                 f"{pct(x['pct_falla'])} ({pct(x['falla_desde'], 3)} a {pct(x['falla_hasta'], 3)}) | "
                 f"{num(x['phi']['phi'], 1)} | {pct(x['pct_desaparece'])} | "
                 f"{'referencia' if x['grupo'] == 'sin aviso' else x['frente_a_sin_aviso'] or 'sin conclusión'} |")
    L.append("")
    c2 = ds["contadores_197_198"]
    if c2["mismas_fotos"]:
        L.append(f"En {ds['fabricante']}, el 197 y el 198 marcan las mismas fotos: {num(c2['las_dos'])} cada uno, "
                 "así que sus dos filas son la misma medida y no dos avisos distintos.")
    else:
        L.append(f"En {ds['fabricante']}, el 197 marca {num(c2['fotos_197'])} fotos y el 198, "
                 f"{num(c2['fotos_198'])}; {num(c2['las_dos'])} los tienen a la vez, {num(c2['solo_197'])} solo el 197 "
                 f"y {num(c2['solo_198'])} solo el 198.")
    L.append("")
    fv = b6["fallos"]
    L.append(f"De los {num(fv['datos'])} fallos de discos de datos, {num(fv['con_dia_anterior'])} tienen el día anterior "
             f"en su ventana y {num(fv['sin_aviso'])} de ellos llegan sin aviso; {num(fv['sin_dia_anterior'])} no lo "
             "tienen y quedan aparte.")
    L.append("")
    L.append("Por año del fallo, los que llegan sin aviso el día anterior, entre los que tienen ese día, y los que no "
             "tienen día anterior, entre todos:")
    L.append("")
    for x in b6["sin_aviso_por_ano"]:
        L.append(f"- {x['ano']}{' (año incompleto)' if x['parcial'] else ''}: {pct(x['pct_sin_aviso'], 1)} sin aviso "
                 f"({num(x['sin_aviso'])} de {num(x['con_dia_anterior'])}) y {pct(x['pct_sin_dia'], 1)} sin día "
                 f"anterior ({num(x['sin_dia_anterior'])} de {num(x['fallos'])}).")
    L.append("")
    L.append(f"En la ventana de 30 días, {num(fv['avisan_algun_dia'])} de {num(fv['con_filas_antes'])} fallos avisan "
             f"algún día y {num(fv['ya_primer_dia'])} ya avisaban el primero.")
    L.append(f"Los {num(fv['empiezan_dentro'])} que empiezan a avisar dentro lo hacen {num(fv['dias_mediana'], 1)} días "
             f"antes del fallo en la mediana, con cuartiles de {num(fv['dias_q1'], 1)} y {num(fv['dias_q3'], 1)}.")
    L.append("")
    L.append("En la construcción, el porcentaje de fotos con el contador subiendo respecto a la foto anterior, entre "
             "las de discos que fallan en 30 días y las demás:")
    L.append("")
    for x in b6["construccion"]:
        L.append(f"- Contador {x['contador']}: {pct(x['pct_fallan'])} frente a {pct(x['pct_no_fallan'], 3)}.")
    L.append("")
    seccion_comprobaciones(L, p["B6"])

    # B7
    L.append("## B7 · Dónde está el riesgo de perder datos")
    L.append("")
    az = {(x["k"], x["d"]): x for x in b7["azar"]["resultados"]}
    azc = {(x["k"], x["d"]): x for x in b7["azar"]["solo_centro"]["resultados"]}
    a1, a2 = az[(2, 30)], az[(3, 7)]

    def lado(x):
        """«por encima» o «no por encima» del percentil 95 del azar."""
        return "por encima" if x["por_encima_del_p95"] else "no por encima"

    L.append(f"El azar baraja los días de los fallos dentro de cada centro y trimestre del fallo, "
             f"{b7['azar']['iteraciones']} veces. Hay {num(a1['observados'])} tomos con dos fallos o más en 30 días, "
             f"frente a {num(a1['media'], 1)} de media (percentil 95, {num(a1['p95'], 1)}): {lado(a1)} del percentil 95.")
    L.append(f"Con tres fallos o más en 7 días hay {num(a2['observados'])} tomos, frente a {num(a2['media'], 2)} de "
             f"media (percentil 95, {num(a2['p95'], 1)}): {lado(a2)} del percentil 95.")
    if not all(x["por_encima_del_p95"] for x in b7["azar"]["resultados"]):
        L.append("Que una medida no quede por encima del percentil 95 es un resultado del cálculo, no un fallo: con "
                 "ella, esos tomos no se distinguen de lo que da el azar.")
    L.append("")
    L.append("Barajando solo dentro de cada centro, como antes de la petición 19: "
             + "; ".join(f"{k} fallos o más en {d_} días, media {num(x['media'], 2)} y percentil 95 "
                         f"{num(x['p95'], 1)}, {lado(x)}" for (k, d_), x in azc.items()) + ".")
    L.append("")
    t7 = b7["fallos"]
    L.append(f"Desde el 01/07/2023 hay {num(t7['desde_07_2023'])} fallos; {num(t7['con_tomo'])} tienen tomo, en "
             f"{num(t7['tomos'])} tomos, y {num(t7['coinciden'])} llegan antes de que acabe de rehacerse el anterior de "
             f"su tomo. La paridad supuesta se alcanza {b7['a_la_vez']['llegan_a_paridad']} veces.")
    L.append("")
    for x in b7["k_en_d"]:
        L.append(f"- {x['k']} fallos o más en {x['d']} días: {num(x['tomos'])} tomos.")
    L.append("")
    rv = b7["riesgo_vivo"]
    L.append(f"El riesgo vivo cuenta cada mes los tomos con varios discos que avisan a la vez. Con dos o más hay "
             f"{num(rv['media_dos'], 1)} al mes de media, frente a {num(rv['media_esperados_dos'], 1)} por azar. Con "
             f"tres o más hay {num(rv['media_tres'], 1)}, frente a {num(rv['media_esperados_tres'], 1)}.")
    L.append("")
    L.append("Los cinco tomos con más fallos que coinciden:")
    L.append("")
    for x in b7["peores_tomos"]:
        L.append(f"- {x['tomo']} ({', '.join(x['modelos'])}): {x['fallos']} fallos y {x['coincidencias']} "
                 "coincidencias.")
    L.append("")
    seccion_comprobaciones(L, p["B7"])

    # B8
    L.append("## B8 · Otros factores del disco")
    L.append("")
    L.append("Cada factor se mide dentro de su grupo, el modelo en la temperatura y el modelo con su año de edad en los "
             "demás. La razón compara los fallos de un tramo con los que tendría a la tasa de su grupo. Estas cifras "
             "describen una asociación y no dicen por qué ocurre.")
    L.append("")
    for n, f in b8["factores"].items():
        tr = "; ".join(f"{x['nombre']}, razón {num(x['razon'], 4)} ({num(x['desde'], 4)} a {num(x['hasta'], 4)}), "
                       f"{num(x['fallos'])} fallos" for x in f["tramos"])
        L.append(f"- **{NOMBRES_FACTOR[n]}.** Entran {f['grupos_entran']} de {f['grupos']} grupos, con "
                 f"{num(f['fallos_entran'])} fallos: {tr}. Salen aparte {num(f['aparte']['fallos'])} fallos y "
                 f"{num(f['sin_tramo']['fallos'])} no tienen tramo.")
    L.append("")
    rp = b8["reparto"]
    L.append(f"Se reparten {num(rp['dias_repartidos'])} días de disco de {num(rp['dias_recuento'])}; "
             f"{num(rp['fallos_con_foto'])} fallos tienen su foto anterior y {num(rp['fallos_sin_foto_anterior'])} no. "
             f"{num(rp['fallos_que_comparten_foto'])} fallos, de {num(rp['discos_con_fallos_que_comparten_foto'])} "
             "discos que fallan dos veces sin una foto nueva entre los dos fallos, toman la misma foto; cada fallo "
             "cuenta una vez.")
    L.append("")
    seccion_comprobaciones(L, p["B8"])

    # MC
    L.append("## MC · Perfiles de riesgo y lo que falta en los datos")
    L.append("")
    L.append(f"La tasa de todas las fotos, con el reparto de los días, es del {pct(mc['tasa_todos'], 4)} anual. Cada "
             f"intervalo lleva el φ de la edad, {num(mc['phi']['phi'], 4)}, medido en {num(mc['phi']['celdas'])} celdas "
             f"de modelo, año de edad y trimestre con {num(mc['phi']['gl'])} grados de libertad. Por valor de cada "
             "dimensión, con su lectura frente a la tasa de todas:")
    L.append("")
    for dim in DIMENSIONES:
        xs = [x for x in mc["nivel_1"] if x["dimension"] == dim]
        L.append(f"- {dim}: " + "; ".join(f"{x['valor']}, {pct(x['tasa'], 4)}"
                                          + (" (sin conclusión)" if x["sin_conclusion"] else f" ({x['frente_al_total']})")
                                          for x in xs) + ".")
    L.append("")
    L.append("Las celdas de tasa más alta de cada par de dimensiones, con 50.000 días o más y 20 fallos o más:")
    L.append("")
    for x in mc["nivel_2"]:
        if x["primeras"]:
            c = x["primeras"][0]
            L.append(f"- {x['dimensiones'][0]} y {x['dimensiones'][1]}: la primera es {c['valores'][0]} con "
                     f"{c['valores'][1]}, {pct(c['tasa'], 4)} ({num(c['fallos'])} fallos).")
    L.append("")
    lf = mc["lo_que_falta"]
    L.append("Lo que falta en los datos:")
    L.append("")
    for q_, x in lf["sin_ranura_dia_fallo"].items():
        L.append(f"- {q_}: {num(x['sin_ranura'])} de {num(x['fallos'])} fallos sin ranura el día del fallo, y "
                 f"{num(lf['sin_tomo_fallos_detalle'][q_])} sin tomo después de tomarla del día anterior.")
    L.append(f"- Las reglas dicen {lf['reglas_dicen']}; las cifras de los fallos sin tomo "
             f"{'coinciden' if lf['coinciden_con_las_reglas'] else 'no coinciden'} con ese rango.")
    L.append(f"- {num(lf['desaparecen_sin_fallo'])} discos desaparecen sin fallo; {num(lf['fallos_antes_de_07_2023'])} "
             f"fallos son anteriores al 01/07/2023 y no tienen sitio; {num(lf['smart_90_no_vacio'])} fotos traen el "
             "contador 90, cuyo significado no se conoce.")
    L.append("")
    seccion_comprobaciones(L, p["MC"])

    # Lo que no saca conclusión
    L.append("## Lo que no saca conclusión")
    L.append("")
    for q in j["preguntas"]:
        for x in q["sin_conclusion"]:
            L.append(f"- {x['bloque']}, {x['grupo']}: {num(x['casos'])} casos.")
    L.append("")

    # Validaciones
    L.append("## Validaciones")
    L.append("")
    L.append("| Validación | Resultado |")
    L.append("|---|---|")
    for k, v in j["validaciones"].items():
        L.append(f"| {NOMBRES_VALIDACION[k][0].upper() + NOMBRES_VALIDACION[k][1:]} | {'sí' if v else 'no'} |")
    L.append(f"| {NOMBRES_EXTRA['sin_palabra_vetada'][0].upper() + NOMBRES_EXTRA['sin_palabra_vetada'][1:]} | "
             f"{'sí' if j['comprobaciones_salida']['sin_palabra_vetada'] else 'no'} |")
    L.append("")
    L.append("Las segundas vías:")
    L.append("")
    L.append("| Cifra | Primera vía | Segunda vía | Comparación | Coinciden |")
    L.append("|---|---|---|---|---|")
    for s in j["segundas_vias"]:
        L.append(f"| {s['nombre']} | {s['via_1']} | {s['via_2']} | {s['comparacion']}, {s['claves']} claves, "
                 f"diferencia mayor {cientifica(s['max_diferencia'])} | {'sí' if s['coinciden'] else 'no'} |")
    L.append("")

    # Parámetros
    L.append("## Parámetros usados")
    L.append("")
    for x in j["parametros"]:
        L.append(f"- {x['nombre']}: {x['valor']} ({x['origen']}).")
    L.append("")
    L.append("Apartados del manual aplicados:")
    L.append("")
    for x in j["teoria"]:
        L.append(f"- {x['apartado']}: {x['por_que']}.")
    L.append("")

    # Datos personales
    L.append("## Datos personales")
    L.append("")
    for x in j["datos_personales_texto"]:
        L.append(f"- {x}")
    L.append("")

    # Límites
    L.append("## Límites")
    L.append("")
    for x in j["limites"]:
        L.append(f"- {x}")
    L.append("")
    return "\n".join(L) + "\n"


# =================================================================================================================
# 13. Ejecución
# =================================================================================================================
def version_metodo(raiz):
    """La fecha y el código de la última línea de versión del METODO.md (bloque común)."""
    ruta = raiz / METODO_MD
    if not ruta.exists():
        ruta = CASO / METODO_MD
    lineas = [x for x in ruta.read_text(encoding="utf-8").splitlines() if x.startswith("Versión ")]
    m = re.match(r"Versión (\S+) \(([^)]+)\)", lineas[-1]) if lineas else None
    return f"{m.group(1)} ({m.group(2)})" if m else None


def parametros():
    """Los valores con que se ejecutó, cada uno con su origen."""
    return [
        {"nombre": "mínimo de días de disco al año de un centro, un valor o una celda", "valor": numero(MINIMO_DIAS_ANO),
         "origen": "reglas-negocio §7; en un centro, sobre los dos años del sitio (100.000 días)"},
        {"nombre": "mínimo de fallos de un centro, un tramo, un valor o una celda", "valor": str(MINIMO_FALLOS),
         "origen": "petición, criterios 8 y 9 y comprobación 1 (yyz1 sin conclusión); reglas, apartado 7, cuestión 009"},
        {"nombre": "mínimo de fotos de un grupo de aviso", "valor": str(MINIMO_CASOS),
         "origen": "parametros.md de el método"},
        {"nombre": "tasa ajustada por centro", "valor": "estandarización indirecta con la tasa de cada modelo, año de "
                                                        "edad y trimestre de todos los centros, «sin dato» incluido",
         "origen": "criterio técnico 1, en la petición 15; el trimestre, petición 19"},
        {"nombre": "φ de B5", "valor": "chi2 de Pearson / grados de libertad en las celdas centro × trimestre de los "
                                       "centros que constan, con los esperados reescalados para que cada centro sume "
                                       "sus fallos; si sale menor que 1, vale 1",
         "origen": "criterio técnico (reglas, apartado 7), petición 19"},
        {"nombre": "φ de B6", "valor": "binomial por grupo de aviso, en las celdas del trimestre de la foto: suma de "
                                       "(fallan − n·p)² / (n·p·(1 − p)) entre celdas − 1; si sale menor que 1, vale 1",
         "origen": "criterio técnico (reglas, apartado 7), petición 19"},
        {"nombre": "φ del minicubo", "valor": "el de B3 del 09, calculado igual: celdas modelo × año de edad × trimestre "
                                              "de dias_por_tramo con la tasa de su modelo y año de edad",
         "origen": "criterio técnico (reglas, apartado 7), petición 19"},
        {"nombre": "intervalo con φ", "valor": "exacto de Poisson con observados y esperados (o fallos y días) entre φ; "
                                               "Clopper-Pearson con fallan/φ y fotos/φ en el desenlace",
         "origen": "petición 19"},
        {"nombre": "desenlace a 90 días", "valor": "falla, desaparece o sigue, por foto", "origen": "criterio técnico 2"},
        {"nombre": "tomos con k fallos en d días", "valor": "k = 2, 3 y 4; d = 7 y 30", "origen": "criterio técnico 3"},
        {"nombre": "azar de los tomos", "valor": f"{ITERACIONES} repeticiones, semilla {SEMILLA}, días barajados dentro "
                                                 "de cada centro y trimestre del fallo, y al lado dentro de cada centro; "
                                                 "media y percentil 95 (interpolación lineal de numpy)",
         "origen": "criterio técnico 4; el trimestre, petición 19"},
        {"nombre": "discos a la vez", "valor": "fallos anteriores del tomo con día + plazo posterior al día del fallo, "
                                               "más uno; paridad supuesta 3, 4 y 5", "origen": "criterio técnico 5; reglas, apartado 4"},
        {"nombre": "riesgo vivo", "valor": "binomial de 2 o más y de 3 o más con los discos del tomo y la proporción "
                                           "del mes", "origen": "criterio técnico 6"},
        {"nombre": "reparto de los días", "valor": "días de la celda de modelo, mes y centro entre sus fotos",
         "origen": "criterio técnico 7"},
        {"nombre": "tramos del bloque 8", "valor": "temperatura ±3 °C de la mediana del modelo; arranques 1 y 2 veces la "
                                                   "mediana de modelo y edad; escritos y leídos por tercios",
         "origen": "criterio técnico 8, aprobado por el responsable del caso el 18/11/2026"},
        {"nombre": "minicubo", "valor": "cinco dimensiones, tasa por el reparto, diez celdas por par en el nivel 2",
         "origen": "criterio técnico 9; assets/23_metodo_minicubo.md"},
        {"nombre": "confianza de los intervalos", "valor": numero(CONFIANZA, 2),
         "origen": "parametros.md de el método y 42.6 del manual"},
        {"nombre": "tolerancia de las segundas vías en días repartidos", "valor": f"{TOLERANCIA:g}",
         "origen": "petición, «SEGUNDA VÍA»"},
        {"nombre": "semilla", "valor": str(SEMILLA), "origen": "petición, criterio 4"},
    ]


def limites(res):
    """Los límites que salen de este cálculo, con sus cifras."""
    p = {q["id"]: q for q in res["preguntas"]}
    b5, b6, mc = p["B5"]["tablas"], p["B6"]["tablas"], p["MC"]["tablas"]
    cv = b6["comparacion_ventana"]
    return [
        "Las cifras describen el periodo de trabajo. Ninguna dice por qué un centro, un aviso o un tramo falla más: "
        "solo valen verbos de asociación.",
        "El centro y el tomo solo constan desde el 01/07/2023; lo anterior no se rellena. El centro «sin dato» y los "
        "fallos sin tomo van aparte, con su recuento.",
        "Un centro que falla más con la misma mezcla de modelo y edad puede deberse a lo que no está en los datos, "
        "como su operación o sus retiradas: no se puede saber.",
        "El aviso es acumulado y casi nunca vuelve a cero, así que el desenlace a 90 días cuenta fotos, no discos, y el "
        "riesgo vivo se compara con el azar.",
        f"La ventana da {numero(cv['con_dia_anterior_ventana'])} fallos con día anterior y "
        f"{numero(cv['sin_aviso_ventana'])} sin aviso; fallos_detalle da {numero(cv['con_dia_anterior_fallos_detalle'])} "
        f"y {numero(cv['sin_aviso_fallos_detalle'])}. Se dan las de fallos_detalle, que son las de las reglas.",
        "Los contadores 187 y 188 solo los traen los Seagate, y los datos escritos y leídos solo se miden en Seagate: el "
        "porcentaje que avisa no se compara entre fabricantes.",
        "La paridad de cada vault no está en los datos: se usa la supuesta de las reglas, apartado 4. El tiempo de reconstrucción "
        "es la regla de Backblaze, un día por TB más uno.",
        "La tasa del minicubo usa los días repartidos por las fotos, que dejan fuera los días de las celdas sin foto: "
        "la del recuento por fabricante y capacidad va al lado, con su diferencia.",
        f"Las reglas, apartado 5 dicen {mc['lo_que_falta']['reglas_dicen']}; las cifras de fallos_detalle "
        f"{'coinciden' if mc['lo_que_falta']['coinciden_con_las_reglas'] else 'no coinciden'} con ese rango.",
        "Según lo medido al preparar la petición 15, la temperatura de un disco casi no cambia de un mes a otro: el "
        "tramo dice cómo de caliente trabaja ese disco respecto a su modelo, no un mes caluroso.",
        f"La tasa ajustada compara modelos presentes en varios centros: {b5['modelos_minimo_dos_centros']} modelos pasan "
        "el mínimo de días en dos centros o más.",
        f"Los intervalos de B5, B6 y el minicubo llevan φ: {numero(b5['phi']['phi'], 4)} en B5 y "
        f"{numero(mc['phi']['phi'], 4)} en el minicubo; en B6, uno por grupo. φ mide la variación entre trimestres y "
        "no la que pueda haber dentro de un trimestre.",
        f"El último año de los datos, {FECHA_DATOS.year}, llega hasta el {FECHA_DATOS:%d/%m}: su «sin aviso» por año va "
        "marcado como incompleto.",
        "Ninguna cifra se ha medido en la reserva, del 01/07/2025 al 30/06/2026 (reglas, apartado 5).",
        "Pendiente: el auditor sin memoria del cierre del paso (método §8) necesita el sí de el responsable del caso, porque es un agente.",
    ]


def escribir(raiz, texto_json, texto_md):
    """Escribe el JSON y el informe, en UTF-8."""
    (raiz / SALIDA_JSON).write_text(texto_json, encoding="utf-8")
    (raiz / SALIDA_MD).write_text(texto_md, encoding="utf-8")


def textos(j):
    """El JSON y el informe generado de él, sin NaN."""
    tj = json.dumps(nativo(j), ensure_ascii=False, indent=1, allow_nan=False)
    return tj, informe(json.loads(tj))


def principal(raiz):
    """Lee, calcula dos veces, comprueba, valida y escribe; devuelve el código de salida."""
    inicio = time.time()
    j = {"metodo": "indicadores-y-analisis", "version_metodo": version_metodo(raiz), "script": SCRIPT, "peticion": PETICION,
         "fecha_datos": FECHA_DATOS.isoformat(), "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
         "entradas": [], "resultado": {}, "pendientes": []}
    h_antes = huellas_raw(raiz)
    try:
        j["previos"] = comprobar_previos(raiz)
        j["entradas"] = comprobar_huellas(raiz)
        d = leer(raiz)
        res = calcular(d)
        res2 = calcular(d)
        fuente = Path(__file__).read_text(encoding="utf-8")
        h_despues = huellas_raw(raiz)
        val = validar(res, fuente, h_antes, h_despues, res2)
        j["huellas_raw"] = {"antes": h_antes, "despues": h_despues, "iguales": h_antes == h_despues}
        j["validaciones"] = val
        j["segundas_vias"] = res["segundas_vias"]
        comp_falsas = [f"{q['id']}.{k}" for q in res["preguntas"]
                       for k, v in list(q["comprobaciones"].items()) + list(q["comprobaciones_extra"].items())
                       if v is False]
        sv_mal = [s["nombre"] for s in res["segundas_vias"] if not s["coinciden"]]
        cifras_mal = [f"{q['id']}: {c['nombre']}" for q in res["preguntas"] for c in q["cifras"] if c["coinciden"] is not True]
        if sv_mal or cifras_mal or comp_falsas or not all(val.values()):
            motivo = "; ".join(filter(None, [
                ("segundas vías que no coinciden: " + ", ".join(sv_mal)) if sv_mal else "",
                ("cifras sin segunda vía que coincida: " + ", ".join(cifras_mal[:10])) if cifras_mal else "",
                ("comprobaciones en rojo: " + ", ".join(comp_falsas)) if comp_falsas else "",
                ("validaciones en rojo: " + ", ".join(k for k, v in val.items() if not v)) if not all(val.values()) else ""]))
            raise Parada("ERROR", motivo)
        j["preguntas"] = res["preguntas"]
        j["parametros"] = parametros()
        j["teoria"] = [
            {"apartado": "42.1", "por_que": "elegir la función por la pregunta: grupos frente a una referencia en B5, B6 y "
                                            "B8, el minicubo en MC y una comparación con el azar en B7"},
            {"apartado": "38.1", "por_que": "el objetivo de negocio, reducir costes y alargar la vida útil, da la decisión "
                                            "de cada bloque"},
            {"apartado": "42.6", "por_que": "cada grupo con su intervalo y cuántos saldrían distintos solo por azar"},
            {"apartado": "13.13 y assets/23_metodo_minicubo.md", "por_que": "el minicubo de cinco dimensiones, con el "
                                                                            "recuento de cada valor y el nivel 2"},
            {"apartado": "13.6 y 13.7", "por_que": "consultas agrupadas por centro y trimestre, por mes, por modelo y por "
                                                   "tramo"},
            {"apartado": "5.5", "por_que": "cada tasa es suma de fallos entre suma de días, con su base, nunca la media de "
                                           "las tasas"},
            {"apartado": "5.6", "por_que": "la tasa bruta de un centro mezcla modelos y edades; la ajustada compara con la "
                                           "misma mezcla"},
            {"apartado": "4.5 y 4.7", "por_que": "intervalo al 95 %; el mínimo de casos lo fijan las reglas del caso"},
            {"apartado": "4.11 y 4.12", "por_que": "las tasas no se contrastan como dos proporciones: van con el intervalo "
                                                   "exacto de Poisson; el desenlace por aviso, con el exacto de "
                                                   "Clopper-Pearson; los dos, ensanchados por φ (petición 19)"},
        ]
        j["datos_personales_texto"] = [
            ("Existe " + PROTECCION + ": lo que dice va en el informe de la protección." if (raiz / PROTECCION).exists()
             else f"No existe {PROTECCION}: los datos no pasaron por la protección, porque no traen datos de personas."),
            "No hay datos de personas (reglas-negocio §9): el número de serie identifica un disco, no a una persona.",
            "Este cálculo usa el número de serie solo para unir fotos, fallos y ventanas, y no deja ninguno en el JSON "
            "ni en el informe.",
        ]
        j["limites"] = limites(res)
        avisos = [x for q in res["preguntas"] for x in q["sin_conclusion"]]
        n_cifras = sum(len(q["cifras"]) for q in res["preguntas"])
        # Con grupos sin conclusión o aparte, AVISO: el informe final tiene que leerlos
        j["resultado"] = {
            "estado": "AVISO" if avisos else "OK", "riesgo": "medio" if avisos else "bajo",
            "resumen": (f"Cinco preguntas calculadas con {n_cifras} cifras, todas con su segunda vía, y las nueve "
                        f"validaciones en verde. Quedan {len(avisos)} grupos sin conclusión o aparte, y el centro y el "
                        "tomo solo constan desde el 01/07/2023."),
            "artefactos": [SALIDA_JSON, SALIDA_MD],
            "siguiente": ("el borrador de hallazgos (B5, B6, B7, B8 y MC) con este JSON; el informe final y el cuadro de "
                          "mando leen sus series; antes, el auditor sin memoria del paso con el sí de el responsable del caso")}
        j["comprobaciones_salida"] = {"sin_palabra_vetada": None}
        tj, tm = textos(j)
        j["comprobaciones_salida"]["sin_palabra_vetada"] = comp_sin_vetada([tj, tm])
        if not j["comprobaciones_salida"]["sin_palabra_vetada"]:
            raise Parada("ERROR", "el JSON o el informe llevan la palabra vetada para el conjunto de discos")
        codigo = 0
    except Parada as e:
        j = {k: v for k, v in j.items() if k not in ("preguntas", "parametros", "teoria", "limites",
                                                     "datos_personales_texto", "comprobaciones_salida")}
        j["resultado"] = {"estado": e.estado, "riesgo": "alto", "resumen": f"Paró con {e.estado}: {e.motivo}",
                          "artefactos": [SALIDA_JSON, SALIDA_MD], "siguiente": "corregir lo que dice el resumen"}
        codigo = 2
    except Exception as e:  # noqa: BLE001 - un fallo no previsto también deja el JSON con su estado
        j = {k: v for k, v in j.items() if k not in ("preguntas", "parametros", "teoria", "limites",
                                                     "datos_personales_texto", "comprobaciones_salida")}
        j["resultado"] = {"estado": "ERROR", "riesgo": "alto",
                          "resumen": f"Falló: {type(e).__name__}: {e}", "artefactos": [SALIDA_JSON, SALIDA_MD],
                          "siguiente": "corregir el fallo", "traza": traceback.format_exc()[-3 * 10 ** 3:]}
        codigo = 1
    j["ejecucion"] = {"python": sys.executable, "version_python": platform.python_version(), "pandas": pd.__version__,
                      "numpy": np.__version__, "scipy": scipy.__version__, "pyarrow": pa.__version__,
                      "duracion_s": round(time.time() - inicio, 1)}
    tj, tm = textos(j)
    escribir(raiz, tj, tm)
    print(f"{j['resultado']['estado']}: {j['resultado']['resumen']}")
    # Un fallo no previsto enseña también dónde ocurrió; el JSON ya lo guarda en resultado.traza
    if "traza" in j["resultado"]:
        print(j["resultado"]["traza"], file=sys.stderr)
    return codigo


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raiz", default=str(CASO), help="carpeta del caso (por defecto, la de este script)")
    sys.exit(principal(Path(ap.parse_args().raiz).resolve()))
