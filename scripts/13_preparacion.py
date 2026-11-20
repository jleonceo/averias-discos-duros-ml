"""Preprocesador del modelo del caso 68 (método preparacion-modelo §4 y §5; petición 20, tercera parte).

Construye, con la matriz de transformaciones aprobada por el responsable del caso (config/modelo/matriz_transformaciones.md),
un preprocesador por familia de algoritmos, cada uno un ColumnTransformer dentro de un Pipeline y sin ajustar:

  - logística: las numéricas por tramos (columnas 0/1, el vacío como tramo propio o en la referencia) y las nominales
    con las raras en «otras» y una columna por categoría menos la de referencia; nada se escala;
  - bosque: las numéricas tal cual, con su vacío, y las nominales con las raras en «otras» y una columna por categoría;
  - HistGradientBoosting: las numéricas tal cual y las nominales como código para categorías nativas.

Las listas de columnas están escritas a mano, copiadas de la matriz; la décima validación comprueba que son las de la
matriz aprobada y que cada una de las columnas de la tabla está en ella o en la lista de fuera.

Después, solo para comprobar, ajusta cada preprocesador una vez con la muestra de partida de entrenamiento (todas las
fotos con fallo y el 2 % de las sanas de cada mes, reglas, apartado 7, semilla 42), aplica transform a la validación sin leer
su falla_30d y calcula las nueve validaciones de el método (§5). No guarda ninguna tabla transformada ni el preprocesador
ajustado: lo ajusta aprendizaje-automatico, con el modelo. Lee las dos partes grupo a grupo, sin cargar la tabla entera.

Depende de scripts/12_particion.py: lee informes/particion.json y para (PARADO) si no está en OK o si la huella de una
parte no es la que dejó; para también si la matriz no está aprobada. No importa ningún script.

Deja informes/preparacion.json y, generado del mismo diccionario, informes/preparacion.md.

Uso: python -W error scripts/13_preparacion.py [--raiz CARPETA_DEL_CASO]
Sale con 0 si termina, con 2 si para (PARADO o ERROR) y con 1 si falla por otra causa; en los tres casos escribe el JSON.
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
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import sklearn
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (MaxAbsScaler, MinMaxScaler, OneHotEncoder, OrdinalEncoder, PowerTransformer,
                                   QuantileTransformer, RobustScaler, StandardScaler)

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "assets"))
from graficos import numero  # noqa: E402  (pieza común: números a la española, redondeo como Excel)

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
METODO = "preparacion-modelo"
METODO_MD = CASO / "metodos" / "preparacion-modelo" / "METODO.md"
SCRIPT = "scripts/13_preparacion.py"
PETICION = "peticiones/20_particion_y_preparacion.md, tercera parte"
FECHA_DATOS = "2025-06-30"                                   # reglas, apartado 5, fecha de referencia
PARTICION = "informes/particion.json"
MATRIZ = "config/modelo/matriz_transformaciones.md"
SALIDA_JSON = "informes/preparacion.json"
SALIDA_MD = "informes/preparacion.md"
OBJETIVO = "falla_30d"
OBJETIVO_Y_HORIZONTE = ["falla_30d", "horizonte_hasta"]
COLUMNA_FECHA = "fecha"

# La muestra de partida (reglas, apartado 7, una nota del caso) y la semilla (preparacion-modelo/parametros.md)
FRACCION_SANAS = 0.02
SEMILLA = 42
# Mínimos de un tramo y de una categoría que no va a «otras» (parametros.md; ficha de la logística §4.2 y §4.3)
MINIMO_FOTOS, MINIMO_FALLOS, MINIMO_SANAS = 30, 20, 20
# Tramos: el 0 y cada valor con al menos esta parte de las fotos con dato van aparte; los trozos de en medio, por
# cuantiles, hasta 3 por debajo de 0 y hasta 10 por encima (matriz, criterio «tramos»)
CUOTA_APARTE, K_NEGATIVOS, K_POSITIVOS = 0.10, 3, 10
ETIQUETA_OTRAS = "otras"
SIN_DATO = "sin dato"
TROZO = 50_000                                               # filas por trozo al transformar, para no llenar la memoria

# ---------------------------------------------------------------------------------------------------------------
# 2.1 Las columnas, copiadas a mano de la matriz aprobada (la décima validación comprueba que son las suyas)
# ---------------------------------------------------------------------------------------------------------------
NOMINALES = ["model", "fabricante", "datacenter"]
NUM_LOGISTICA = [
    "capacidad_tb", "garantia_anos", "smart_5_raw", "smart_187_raw", "smart_197_raw", "smart_198_raw",
    "smart_194_raw", "smart_199_raw", "smart_12_raw", "smart_192_raw", "smart_1_raw", "smart_7_raw", "edad_anos",
    "contadores_que_avisan", "suma_contadores_sin_188", "smart_188_no_cero", "cambio_smart_5", "cambio_smart_187",
    "cambio_smart_197", "cambio_smart_198", "meses_desde_foto_anterior", "smart_1_normalized", "smart_2_normalized",
    "smart_2_raw", "smart_3_normalized", "smart_3_raw", "smart_4_raw", "smart_5_normalized", "smart_7_normalized",
    "smart_8_normalized", "smart_8_raw", "smart_9_normalized", "smart_22_normalized", "smart_22_raw",
    "smart_24_normalized", "smart_90_raw", "smart_183_raw", "smart_184_raw", "smart_189_raw",
    "smart_191_normalized", "smart_191_raw", "smart_192_normalized", "smart_193_normalized", "smart_193_raw",
    "smart_194_normalized", "smart_195_normalized", "smart_195_raw", "smart_196_normalized", "smart_196_raw",
    "smart_198_normalized", "smart_199_normalized", "smart_200_normalized", "smart_220_raw",
    "smart_222_raw", "smart_223_raw", "smart_226_raw", "smart_240_raw", "smart_241_raw",
    "smart_242_raw"]
# Los árboles llevan además avisa, que en la logística es la suma de los tramos de contadores_que_avisan, y
# smart_197_normalized, que en la logística no deja ningún tramo con la muestra de partida (matriz, P-05)
NUM_ARBOLES = NUM_LOGISTICA[:13] + ["avisa"] + NUM_LOGISTICA[13:] + ["smart_197_normalized"]
# Las seis copias que quitó la corrección de la matriz (P-05, una nota del caso) van al final de las que no entran
NO_ENTRAN = [
    "smart_188_raw", "edad_de_horas", "smart_4_normalized", "smart_9_raw", "smart_10_normalized", "smart_10_raw",
    "smart_11_normalized", "smart_11_raw", "smart_12_normalized", "smart_13_normalized", "smart_13_raw",
    "smart_16_raw", "smart_17_raw", "smart_27_raw", "smart_165_raw", "smart_166_raw", "smart_167_raw",
    "smart_168_raw", "smart_169_raw", "smart_170_normalized", "smart_170_raw", "smart_171_raw",
    "smart_172_normalized", "smart_172_raw", "smart_173_normalized", "smart_173_raw", "smart_174_raw",
    "smart_177_normalized", "smart_177_raw", "smart_179_raw", "smart_180_normalized", "smart_180_raw",
    "smart_181_raw", "smart_188_normalized", "smart_190_normalized", "smart_200_raw", "smart_201_raw",
    "smart_202_normalized", "smart_202_raw", "smart_206_raw", "smart_211_raw", "smart_212_raw", "smart_218_raw",
    "smart_220_normalized", "smart_223_normalized", "smart_225_normalized", "smart_225_raw", "smart_230_normalized",
    "smart_230_raw", "smart_231_raw", "smart_232_raw", "smart_233_raw", "smart_234_raw", "smart_235_normalized",
    "smart_235_raw", "smart_240_normalized", "smart_241_normalized", "smart_242_normalized", "smart_244_normalized",
    "smart_245_normalized", "smart_245_raw", "smart_246_raw", "smart_247_raw", "smart_248_raw",
    "smart_254_normalized", "smart_190_raw", "smart_183_normalized", "smart_184_normalized", "smart_187_normalized",
    "smart_189_normalized", "smart_222_normalized"]
FUERA = ["serial_number", "fecha", "periodo", "horizonte_hasta", "falla_30d", "capacity_bytes", "vault_id", "pod_id",
         "pod_slot_num"]
# En la logística, el vacío idéntico, fila a fila, lo lleva una sola variable; estas lo mandan a su referencia
VACIO_COMPARTIDO = {
    "cambio_smart_198": "cambio_smart_5", "smart_2_raw": "smart_2_normalized", "smart_8_normalized": "smart_2_normalized",
    "smart_8_raw": "smart_2_normalized", "smart_22_raw": "smart_22_normalized",
    "smart_191_raw": "smart_191_normalized", "smart_195_raw": "smart_195_normalized",
    "smart_196_raw": "smart_196_normalized", "smart_222_raw": "smart_220_raw",
    "smart_226_raw": "smart_220_raw", "smart_242_raw": "smart_241_raw"}
# Formato propio de cada fabricante (reglas, apartado 5): en la logística, tramos aprendidos solo con Seagate
SOLO_SEAGATE = ["smart_1_raw", "smart_7_raw"]
FAMILIAS = ["logistica", "bosque", "hgb"]
ESCALADORES = (StandardScaler, MinMaxScaler, RobustScaler, MaxAbsScaler, PowerTransformer, QuantileTransformer)

TEORIA = [
    "39.3 a 39.5, pipelines: cada preprocesador es un ColumnTransformer dentro de un Pipeline, sin ajustar; lo ajusta "
    "aprendizaje-automatico con el modelo, dentro de cada pliegue.",
    "35.7, discretización: los tramos se aprenden en el ajuste con el mínimo de casos, y lo que queda fuera del rango del "
    "entrenamiento cae en el tramo del borde.",
    "35.2 y 35.3: una columna por categoría menos la de referencia en la logística, todas en el bosque y código "
    "ordinal para las categóricas nativas de HistGradientBoosting.",
    "35.12: ningún escalador, porque la logística solo recibe columnas 0 y 1 y los árboles cortan por orden.",
    "20.8, fugas: el ajuste usa solo entrenamiento y la validación se transforma sin leer su objetivo.",
]


class Parada(Exception):
    """Condición que impide seguir; `estado` dice si el método paró a propósito (PARADO) o si falló algo (ERROR)."""

    def __init__(self, mensaje, estado="ERROR"):
        super().__init__(mensaje)
        self.estado = estado


# =================================================================================================================
# 3. Las piezas propias del preprocesador (no tocan filas; aprenden solo en fit)
# =================================================================================================================
def _a_float(serie):
    """Una columna como número decimal, con el vacío como NaN (las enteras con vacíos llegan como decimales)."""
    return pd.to_numeric(serie).to_numpy(dtype=float, na_value=np.nan)


def _llega(n, f, minimos=(MINIMO_FOTOS, MINIMO_FALLOS, MINIMO_SANAS)):
    """Cierto si un grupo tiene las fotos, los fallos y las sanas mínimos."""
    return n >= minimos[0] and f >= minimos[1] and n - f >= minimos[2]


def _cuantiles(u, c, f, k):
    """Junta valores consecutivos en hasta k trozos de fotos parecidas; un valor nunca se parte."""
    if len(u) <= k:
        return [[u[i], u[i], int(c[i]), int(f[i])] for i in range(len(u))]
    cum = np.cumsum(c) - c
    b = np.minimum((cum / c.sum() * k).astype(int), k - 1)
    salida = []
    for q in np.unique(b):
        s = b == q
        salida.append([u[s][0], u[s][-1], int(c[s].sum()), int(f[s].sum())])
    return salida


def _fundir(g, minimos):
    """Junta cada tramo que no llega al mínimo con el vecino de menos fotos, hasta que todos llegan."""
    g = [list(t) for t in g]
    while len(g) > 1:
        malos = [i for i, t in enumerate(g) if not _llega(t[2], t[3], minimos)]
        if not malos:
            break
        i = malos[0]
        j = 1 if i == 0 else (i - 1 if i == len(g) - 1 else (i - 1 if g[i - 1][2] <= g[i + 1][2] else i + 1))
        a, b = sorted((i, j))
        g[a] = [g[a][0], g[b][1], g[a][2] + g[b][2], g[a][3] + g[b][3]]
        del g[b]
    return g


class Tramos(BaseEstimator, TransformerMixin):
    """Numéricas de la logística por tramos: una columna 0/1 por tramo menos el de más fotos (la referencia).

    En fit aprende, con el objetivo, los tramos de cada columna: el 0 y cada valor con al menos `cuota_aparte` de las
    fotos con dato van aparte; los trozos de en medio van por cuantiles (hasta `k_negativos` por debajo de 0 y hasta
    `k_positivos` por encima) y después se funden con el vecino hasta tener los mínimos. El vacío es su propio tramo
    si llega a los mínimos y no está en `columnas_vacio_a_referencia`; si no, va a la referencia. Las columnas de
    `columnas_solo_seagate` aprenden solo con las fotos de Seagate, y las demás van a la referencia. La columna de
    fabricante se lee como clave y no sale.
    """

    def __init__(self, columnas_vacio_a_referencia=(), columnas_solo_seagate=(), columna_fabricante="fabricante",
                 minimo_fotos=MINIMO_FOTOS, minimo_fallos=MINIMO_FALLOS, minimo_sanas=MINIMO_SANAS,
                 cuota_aparte=CUOTA_APARTE, k_negativos=K_NEGATIVOS, k_positivos=K_POSITIVOS):
        self.columnas_vacio_a_referencia = columnas_vacio_a_referencia
        self.columnas_solo_seagate = columnas_solo_seagate
        self.columna_fabricante = columna_fabricante
        self.minimo_fotos = minimo_fotos
        self.minimo_fallos = minimo_fallos
        self.minimo_sanas = minimo_sanas
        self.cuota_aparte = cuota_aparte
        self.k_negativos = k_negativos
        self.k_positivos = k_positivos

    def _seagate(self, X):
        """Máscara de las fotos de Seagate."""
        return (X[self.columna_fabricante].astype(object) == "Seagate").to_numpy()

    def fit(self, X, y):
        """Aprende los tramos, la referencia y si el vacío es tramo propio, columna a columna."""
        X = pd.DataFrame(X)
        y = np.asarray(y).astype(np.int64)
        minimos = (self.minimo_fotos, self.minimo_fallos, self.minimo_sanas)
        self.columnas_ = [c for c in X.columns if c != self.columna_fabricante]
        self.tramos_, self.cortes_, self.n_tramos_, self.referencia_, self.vacio_columna_ = {}, {}, {}, {}, {}
        seagate = self._seagate(X) if self.columnas_solo_seagate else None
        for c in self.columnas_:
            x = _a_float(X[c])
            vac = np.isnan(x)
            usar = ~vac & (seagate if c in self.columnas_solo_seagate else True)
            u, inv, n = np.unique(x[usar], return_inverse=True, return_counts=True)
            f = np.bincount(inv, weights=y[usar], minlength=len(u)).astype(np.int64)
            g = []
            if len(u):
                aparte = (u == 0) | (n >= self.cuota_aparte * n.sum())
                i = 0
                while i < len(u):
                    if aparte[i]:
                        g.append([u[i], u[i], int(n[i]), int(f[i])]); i += 1; continue
                    j = i
                    while j < len(u) and not aparte[j]:
                        j += 1
                    g += _cuantiles(u[i:j], n[i:j], f[i:j], self.k_negativos if u[j - 1] < 0 else self.k_positivos)
                    i = j
                g = _fundir(g, minimos)
            self.tramos_[c] = [{"desde": float(t[0]), "hasta": float(t[1]), "fotos": t[2], "fallos": t[3]} for t in g]
            self.cortes_[c] = np.array([t[0] for t in g[1:]], dtype=float)
            self.n_tramos_[c] = len(g)
            self.referencia_[c] = int(np.argmax([t[2] for t in g])) if g else -1
            self.vacio_columna_[c] = bool(c not in self.columnas_vacio_a_referencia
                                          and _llega(int(vac.sum()), int(y[vac].sum()), minimos))
        self.nombres_ = []
        for c in self.columnas_:
            self.nombres_ += [f"{c}_disc_cs_{i}" for i in range(self.n_tramos_[c]) if i != self.referencia_[c]]
            if self.vacio_columna_[c]:
                self.nombres_.append(f"{c}_disc_cs_vacio")
        return self

    def tramo_de(self, columna, x):
        """El tramo de cada valor (−1 si es vacío); lo que queda fuera del rango cae en el tramo del borde."""
        idx = np.searchsorted(self.cortes_[columna], x, side="right")
        return np.where(np.isnan(x), -1, idx)

    def transform(self, X):
        """Las columnas 0/1 de cada tramo y, si lo es, la del vacío; mismas filas y mismo índice."""
        X = pd.DataFrame(X)
        seagate = self._seagate(X) if self.columnas_solo_seagate else None
        salida = {}
        for c in self.columnas_:
            x = _a_float(X[c])
            idx = self.tramo_de(c, x)
            if c in self.columnas_solo_seagate:
                idx = np.where(seagate | np.isnan(x), idx, self.referencia_[c])
            for i in range(self.n_tramos_[c]):
                if i != self.referencia_[c]:
                    salida[f"{c}_disc_cs_{i}"] = (idx == i).astype(float)
            if self.vacio_columna_[c]:
                salida[f"{c}_disc_cs_vacio"] = (idx == -1).astype(float)
        return pd.DataFrame(salida, index=X.index, columns=self.nombres_)

    def get_feature_names_out(self, input_features=None):
        """Los nombres de salida, con el sufijo de su rama."""
        return np.asarray(self.nombres_, dtype=object)


class AgruparRaras(BaseEstimator, TransformerMixin):
    """Nominales: el vacío a «sin dato» y las categorías raras a «otras», aprendidas en fit con el objetivo.

    Una categoría es rara si en el ajuste tiene menos fotos, fallos o sanas que los mínimos. Una categoría que no se
    vio en el ajuste va a «otras» si existe y, si no, a la referencia, la categoría con más fotos de las que se quedan
    (matriz, P-03). Así el codificador de detrás no ve nunca una categoría nueva. Conserva índice y filas.
    """

    def __init__(self, etiqueta=ETIQUETA_OTRAS, relleno=SIN_DATO, sufijo="", minimo_fotos=MINIMO_FOTOS,
                 minimo_fallos=MINIMO_FALLOS, minimo_sanas=MINIMO_SANAS):
        self.etiqueta = etiqueta
        self.relleno = relleno
        self.sufijo = sufijo
        self.minimo_fotos = minimo_fotos
        self.minimo_fallos = minimo_fallos
        self.minimo_sanas = minimo_sanas

    def _texto(self, s):
        """La columna como texto, con el vacío como «sin dato»."""
        s = s.astype(object)
        return s.where(s.notna(), self.relleno)

    def fit(self, X, y):
        """Aprende las categorías que se quedan, si hay «otras» y la referencia de cada columna."""
        X = pd.DataFrame(X)
        y = np.asarray(y).astype(np.int64)
        minimos = (self.minimo_fotos, self.minimo_fallos, self.minimo_sanas)
        self.columnas_ = list(X.columns)
        self.quedan_, self.otras_, self.referencia_, self.vistas_ = {}, {}, {}, {}
        for c in self.columnas_:
            t = pd.DataFrame({"v": self._texto(X[c]).to_numpy(), "y": y}).groupby("v")["y"].agg(["size", "sum"])
            quedan = sorted(k for k, r in t.iterrows() if _llega(int(r["size"]), int(r["sum"]), minimos))
            self.vistas_[c] = sorted(t.index)
            self.quedan_[c] = quedan
            self.otras_[c] = len(quedan) < len(t)
            orden = t.loc[quedan].sort_values("size", ascending=False) if quedan else t.sort_values("size", ascending=False)
            self.referencia_[c] = str(orden.index[0]) if quedan else self.etiqueta
        return self

    def transform(self, X):
        """Cada valor a su categoría, a «otras» o a la referencia."""
        X = pd.DataFrame(X)
        salida = {}
        for c in self.columnas_:
            s = self._texto(X[c])
            destino = self.etiqueta if self.otras_[c] else self.referencia_[c]
            salida[c + self.sufijo] = s.where(s.isin(self.quedan_[c]), destino).to_numpy(dtype=object)
        return pd.DataFrame(salida, index=X.index)

    def get_feature_names_out(self, input_features=None):
        """Los nombres de entrada con el sufijo."""
        return np.asarray([c + self.sufijo for c in self.columnas_], dtype=object)


class ColumnasMenosReferencia(BaseEstimator, TransformerMixin):
    """Una columna 0/1 por categoría menos la de más fotos en el ajuste, que hace de referencia (ficha §4.3)."""

    def fit(self, X, y=None):
        """Aprende las categorías y la referencia de cada columna."""
        X = pd.DataFrame(X)
        self.columnas_ = list(X.columns)
        self.categorias_, self.referencia_ = {}, {}
        for c in self.columnas_:
            cuenta = X[c].astype(object).value_counts()
            cuenta = cuenta.sort_index().sort_values(ascending=False, kind="stable")
            self.categorias_[c] = sorted(str(k) for k in cuenta.index)
            self.referencia_[c] = str(cuenta.index[0])
        self.nombres_ = [f"{c}_ohe_{k}" for c in self.columnas_ for k in self.categorias_[c] if k != self.referencia_[c]]
        return self

    def transform(self, X):
        """Las columnas 0/1; la referencia sale con todas a cero."""
        X = pd.DataFrame(X)
        salida = {}
        for c in self.columnas_:
            s = X[c].astype(object).to_numpy()
            for k in self.categorias_[c]:
                if k != self.referencia_[c]:
                    salida[f"{c}_ohe_{k}"] = (s == k).astype(float)
        return pd.DataFrame(salida, index=X.index, columns=self.nombres_)

    def get_feature_names_out(self, input_features=None):
        """Los nombres de salida."""
        return np.asarray(self.nombres_, dtype=object)


def nombre_ohe(variable, categoria):
    """Nombre de una columna de categoría del bosque: <variable>_ohe_<categoría> (función de módulo, se puede guardar)."""
    return f"{variable}_ohe_{categoria}"


# =================================================================================================================
# 4. Los preprocesadores, sin ajustar
# =================================================================================================================
def preprocesador(familia):
    """El Pipeline sin ajustar de una familia: logistica, bosque o hgb."""
    if familia == "logistica":
        partes = [("tramos", Tramos(columnas_vacio_a_referencia=tuple(VACIO_COMPARTIDO), columnas_solo_seagate=tuple(SOLO_SEAGATE)),
                   NUM_LOGISTICA + ["fabricante"]),
                  ("categorias", Pipeline([("raras", AgruparRaras()), ("columnas", ColumnasMenosReferencia())]), NOMINALES)]
    elif familia == "bosque":
        partes = [("numericas", "passthrough", NUM_ARBOLES),
                  ("categorias", Pipeline([("raras", AgruparRaras()),
                                           ("columnas", OneHotEncoder(handle_unknown="ignore", sparse_output=False,
                                                                      feature_name_combiner=nombre_ohe))]), NOMINALES)]
    elif familia == "hgb":
        partes = [("numericas", "passthrough", NUM_ARBOLES),
                  ("categorias", Pipeline([("raras", AgruparRaras(sufijo="_oe")),
                                           ("codigo", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan,
                                                                     encoded_missing_value=np.nan))]), NOMINALES)]
    else:
        raise ValueError(f"familia desconocida: {familia}")
    ct = ColumnTransformer(partes, remainder="drop", verbose_feature_names_out=False).set_output(transform="pandas")
    return Pipeline([("preparacion", ct)])


# =================================================================================================================
# 5. La matriz aprobada
# =================================================================================================================
def leer_matriz(texto):
    """Lee la matriz aprobada: su estado, quién la aprobó y cuándo, y sus tres listas con lo que dice cada fila."""
    m = re.search(r"^estado: (.*)$", texto, flags=re.M)
    estado = m.group(1).strip() if m else ""
    a = re.search(r"aprobada por (\w+) el (\d{2})/(\d{2})/(\d{4})", estado)
    mz = {"estado": estado, "aprobada_por": a.group(1) if a else "", "fecha": f"{a.group(4)}-{a.group(3)}-{a.group(2)}" if a else "",
          "entran": [], "no_entran": [], "fuera": [], "logistica": [], "compartido": {}, "solo_seagate": [], "filas": [],
          "decisiones": re.findall(r"^- \*\*(P-0\d):\*\* (.*)$", texto, flags=re.M)}
    seccion = None
    for linea in texto.splitlines():
        if linea.startswith("## Columnas que entran"):
            seccion = "entran"
        elif linea.startswith("## Columnas que no entran"):
            seccion = "no_entran"
        elif linea.startswith("## Columnas fuera de la matriz"):
            seccion = "fuera"
        elif linea.startswith("## "):
            seccion = None
        elif seccion and linea.startswith("| `"):
            celdas = [x.strip() for x in linea.strip().strip("|").split("|")]
            variable = celdas[0].strip("`")
            mz[seccion].append(variable)
            if seccion == "fuera":
                mz["filas"].append({"variable": variable, "seccion": seccion, "motivo": celdas[1], "detalle": celdas[2]})
                continue
            fila = dict(zip(["variable", "tipo", "rama", "escalado", "relleno", "salida", "entra"], [variable] + celdas[1:7]))
            fila["porque"] = "|".join(celdas[7:])
            fila["seccion"] = seccion
            mz["filas"].append(fila)
            if seccion == "entran" and fila["entra"] == "sí":
                mz["logistica"].append(variable)
            r = re.search(r"el de (\w+), que ya lleva esa columna", fila["relleno"])
            if r:
                mz["compartido"][variable] = r.group(1)
            if "solo con las fotos de Seagate" in fila["rama"]:
                mz["solo_seagate"].append(variable)
    return mz


# =================================================================================================================
# 6. Las validaciones (método §5, más la décima de la petición), calculadas con lo que se ejecutó
# =================================================================================================================
def v_filas(entrada, salida):
    """1. Las filas de entrada y de salida coinciden."""
    return entrada == salida


def v_sin_objetivo(columnas):
    """2. Ni el objetivo ni su horizonte están entre las columnas de salida."""
    return not any(c in OBJETIVO_Y_HORIZONTE for c in columnas)


def v_sin_intermedias(familia, columnas):
    """3. No queda la original de una variable transformada ni un nombre con prefijo de transformador."""
    transformadas = set(NUM_LOGISTICA + NOMINALES) if familia == "logistica" else set(NOMINALES)
    return not any(c in transformadas or "__" in c for c in columnas)


def v_sin_vacios(columnas_con_vacio, permitidas):
    """4. Solo tienen vacíos las columnas en que la matriz los deja entrar."""
    return set(columnas_con_vacio) <= set(permitidas)


def v_nombres_unicos(columnas):
    """5. Los nombres de salida son únicos."""
    return len(columnas) == len(set(columnas))


def v_sin_redundancia(grams, duplicadas):
    """6. En la logística, ninguna columna de una variable es combinación de las demás con el término independiente,
    y no hay dos columnas idénticas."""
    rangos = all(np.linalg.matrix_rank(g, hermitian=True) == g.shape[0] for g in grams.values())
    return rangos and not duplicadas


def v_columnas_esperadas(columnas, esperadas):
    """7. Las columnas de salida son exactamente las esperadas, en número y en nombre."""
    return len(columnas) == len(esperadas) and set(columnas) == set(esperadas)


def v_relleno_sin_choque(valores):
    """8. Ni «sin dato» ni «otras», los valores fijos que pone el preprocesador, existen ya en entrenamiento."""
    return not any((SIN_DATO in v) or (ETIQUETA_OTRAS in v) for v in valores.values())


def _piezas(objeto):
    """Todos los pasos de un Pipeline o un ColumnTransformer, sin ajustar, de forma recursiva."""
    if isinstance(objeto, Pipeline):
        return [p for _, paso in objeto.steps for p in _piezas(paso)]
    if isinstance(objeto, ColumnTransformer):
        return [p for _, t, _ in objeto.transformers for p in _piezas(t)]
    return [objeto]


def v_escalado(pipeline, cero_uno):
    """9. La matriz no escala nada: ningún escalador en el preprocesador, y las columnas 0/1 salen en 0 y 1."""
    return not any(isinstance(p, ESCALADORES) for p in _piezas(pipeline)) and bool(cero_uno)


def v_columnas_en_matriz(columnas_tabla, mz):
    """10. Cada columna de la tabla está una sola vez en la matriz o en la lista de fuera, y las listas del script son
    las de la matriz aprobada. Devuelve el resultado y el detalle de lo que no cuadra."""
    todas = mz["entran"] + mz["no_entran"] + mz["fuera"]
    detalle = {
        "fuera_de_la_matriz": [c for c in columnas_tabla if c not in todas],
        "repetidas_en_la_matriz": sorted({c for c in todas if todas.count(c) > 1}),
        "en_la_matriz_y_no_en_la_tabla": [c for c in todas if c not in columnas_tabla],
        "listas_distintas": [n for n, a, b in (
            ("entran", set(NOMINALES + NUM_ARBOLES), set(mz["entran"])),
            ("logistica", set(NOMINALES + NUM_LOGISTICA), set(mz["logistica"])),
            ("no_entran", set(NO_ENTRAN), set(mz["no_entran"])),
            ("fuera", set(FUERA), set(mz["fuera"])),
            ("vacio_compartido", set(VACIO_COMPARTIDO.items()), set(mz["compartido"].items())),
            ("solo_seagate", set(SOLO_SEAGATE), set(mz["solo_seagate"]))) if a != b]}
    return not any(detalle.values()), detalle


class Revision:
    """Lo que hay que mirar de la salida de una familia, trozo a trozo: filas, vacíos, 0 y 1, columnas idénticas y,
    en la logística, la matriz de productos de cada variable con el término independiente."""

    def __init__(self, familia, variables):
        self.familia = familia
        self.variables = variables
        self.filas = 0
        self.columnas = None
        self.columnas_con_vacio = set()
        self.cero_uno = True
        self.grams = {}
        self._huellas = {}

    def anadir(self, df):
        """Suma un trozo de salida."""
        if self.columnas is None:
            self.columnas = list(df.columns)
        elif list(df.columns) != self.columnas:
            raise Parada(f"{self.familia}: las columnas de salida cambian de un trozo a otro")
        self.filas += len(df)
        self.columnas_con_vacio |= set(df.columns[df.isna().any().to_numpy()])
        binarias = list(df.columns) if self.familia == "logistica" else [c for c in df.columns if "_ohe_" in c]
        if binarias:
            v = df[binarias].to_numpy(dtype=float, na_value=np.nan)
            self.cero_uno &= bool(np.isin(v, (0.0, 1.0)).all())
        if self.familia != "logistica":
            return
        for c in df.columns:
            h = self._huellas.setdefault(c, hashlib.sha1())
            h.update(df[c].to_numpy(dtype=float).tobytes())
        for var in self.variables:
            cols = [c for c in df.columns if c.startswith(var + "_disc_cs_") or c.startswith(var + "_ohe_")]
            if not cols:
                continue
            z = np.column_stack([np.ones(len(df))] + [df[c].to_numpy(dtype=float) for c in cols])
            self.grams[var] = self.grams.get(var, 0) + z.T @ z

    def duplicadas(self):
        """Grupos de columnas idénticas fila a fila (solo en la logística)."""
        grupos = {}
        for c, h in self._huellas.items():
            grupos.setdefault(h.hexdigest(), []).append(c)
        return [g for g in grupos.values() if len(g) > 1]


def esperadas(familia, ajustado):
    """Las columnas que la matriz espera de una familia ya ajustada, calculadas con lo que aprendió cada pieza.

    Una variable de la matriz que no deja ninguna columna añade un nombre imposible, para que la validación 7 caiga.
    """
    ct = ajustado.named_steps["preparacion"]
    salida = []
    if familia == "logistica":
        t = ct.named_transformers_["tramos"]
        for c in NUM_LOGISTICA:
            propias = [f"{c}_disc_cs_{i}" for i in range(t.n_tramos_[c]) if i != t.referencia_[c]]
            propias += [f"{c}_disc_cs_vacio"] if t.vacio_columna_[c] else []
            salida += propias or [f"{c}<sin columnas>"]
        cm = ct.named_transformers_["categorias"].named_steps["columnas"]
        for c in NOMINALES:
            propias = [f"{c}_ohe_{k}" for k in cm.categorias_[c] if k != cm.referencia_[c]]
            salida += propias or [f"{c}<sin columnas>"]
    elif familia == "bosque":
        ohe = ct.named_transformers_["categorias"].named_steps["columnas"]
        salida = list(NUM_ARBOLES) + [f"{c}_ohe_{k}" for c, cats in zip(NOMINALES, ohe.categories_) for k in cats]
    else:
        salida = list(NUM_ARBOLES) + [f"{c}_oe" for c in NOMINALES]
    return salida


# =================================================================================================================
# 7. Lectura: el entrenamiento con su muestra y la validación sin el objetivo
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leído por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def leer_entrenamiento(ruta):
    """Lee entrenamiento grupo a grupo: el desequilibrio, los valores de las nominales y la muestra de partida.

    La muestra son todas las fotos con fallo y, de cada mes, el 2 % de las sanas, sorteadas con la semilla 42 en el
    orden de los grupos (reglas, apartado 7). Devuelve la muestra (sin objetivo ni fecha), su objetivo y los recuentos.
    """
    pf = pq.ParquetFile(ruta)
    columnas = NOMINALES + NUM_ARBOLES + [OBJETIVO, COLUMNA_FECHA]
    rng = np.random.default_rng(SEMILLA)
    trozos = []
    r = {"filas": 0, "fallos": 0, "sanas_muestra": 0, "fallos_muestra": 0, "por_fabricante": {}, "por_mes": [],
         "valores": {c: set() for c in NOMINALES}}
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=columnas)
        y = t[OBJETIVO].to_numpy().astype(np.int64)
        r["filas"] += len(y)
        r["fallos"] += int(y.sum())
        fecha = pc.unique(t[COLUMNA_FECHA]).to_pylist()
        r["por_mes"].append({"mes": fecha[0].date().isoformat() if len(fecha) == 1 else None, "fotos": len(y), "fallos": int(y.sum())})
        fab = t["fabricante"].to_numpy(zero_copy_only=False)
        for f in np.unique(fab.astype(str)):
            a = r["por_fabricante"].setdefault(f, {"fotos": 0, "fallos": 0})
            s = fab.astype(str) == f
            a["fotos"] += int(s.sum()); a["fallos"] += int(y[s].sum())
        for c in NOMINALES:
            r["valores"][c].update(v for v in pc.unique(t[c]).to_pylist() if v is not None)
        # La muestra de partida: todos los fallos y el 2 % de las sanas de este mes (redondeo al entero más cercano)
        sanas = np.flatnonzero(y == 0)
        k = int(np.floor(FRACCION_SANAS * len(sanas) + 0.5))
        elegidas = rng.choice(sanas, size=k, replace=False) if k else np.array([], dtype=np.int64)
        filas = np.sort(np.concatenate([np.flatnonzero(y == 1), elegidas]))
        trozos.append(t.take(pa.array(filas)))
        r["sanas_muestra"] += k
        r["fallos_muestra"] += int(y.sum())
    muestra = pa.concat_tables(trozos).to_pandas()
    y = muestra.pop(OBJETIVO).to_numpy().astype(np.int64)
    muestra = muestra.drop(columns=[COLUMNA_FECHA])
    return muestra, y, r


# =================================================================================================================
# 8. El JSON y el informe
# =================================================================================================================
def version_metodo():
    """La fecha y el código de la última línea de versión del METODO.md (bloque común de resultado.md)."""
    if not METODO_MD.exists():
        return None
    lineas = [x for x in METODO_MD.read_text(encoding="utf-8").splitlines() if x.startswith("Versión ")]
    m = re.match(r"Versión (\S+) \(([^),]+)", lineas[-1]) if lineas else None
    return f"{m.group(1)} ({m.group(2)})" if m else None


def desequilibrio(r):
    """El desequilibrio de clases de entrenamiento, solo descrito (método §2)."""
    meses = [m for m in r["por_mes"] if m["mes"]]
    fallos_mes = [m["fallos"] for m in meses]
    minimo = min(meses, key=lambda m: m["fallos"]) if meses else None
    maximo = max(meses, key=lambda m: m["fallos"]) if meses else None
    return {"filas": r["filas"], "fotos_con_fallo": r["fallos"], "fotos_sanas": r["filas"] - r["fallos"],
            "proporcion_positiva": r["fallos"] / r["filas"] if r["filas"] else None,
            "razon": (r["filas"] - r["fallos"]) / r["fallos"] if r["fallos"] else None,
            "casos_clase_pequena_entrenamiento": r["fallos"],
            "por_fabricante": [{"fabricante": f, **v, "tasa_pct": 100 * v["fallos"] / v["fotos"]}
                               for f, v in sorted(r["por_fabricante"].items(), key=lambda kv: -kv[1]["fotos"])],
            "por_mes": {"meses": len(meses), "fallos_min": minimo["fallos"] if minimo else None, "mes_min": minimo["mes"] if minimo else None,
                        "fallos_max": maximo["fallos"] if maximo else None, "mes_max": maximo["mes"] if maximo else None,
                        "fallos_mediana": float(np.median(fallos_mes)) if fallos_mes else None}}


NOMBRES_VALIDACION = {
    "filas": "las filas de entrada y de salida coinciden en cada parte",
    "sin_objetivo": "ni el objetivo ni su horizonte salen",
    "sin_intermedias": "no queda la original de ninguna variable transformada",
    "sin_vacios": "solo tienen vacíos las columnas en que la matriz los deja",
    "nombres_unicos": "los nombres de salida son únicos",
    "sin_redundancia": "en la logística, ninguna columna de una variable es combinación de las demás y no hay dos iguales",
    "columnas_esperadas": "las columnas de salida son las que espera la matriz, en número y en nombre",
    "relleno_sin_choque": "«sin dato» y «otras» no existen ya en entrenamiento",
    "escalado_segun_matriz": "no hay ningún escalador y las columnas 0/1 salen en 0 y 1",
    "columnas_en_matriz": "cada columna de la tabla está en la matriz o fuera, y las listas del script son las de la matriz",
}
NOMBRE_FAMILIA = {"logistica": "regresión logística", "bosque": "bosque aleatorio", "hgb": "HistGradientBoosting"}


def informe(res):
    """El informe para el responsable del caso, con los apartados de resultado.md y solo las cifras del diccionario."""
    L = []
    w = L.append
    estado = res["resultado"]["estado"]
    w("# Preparación para el modelo · el preprocesador")
    w("")
    pre = res.get("preprocesador") or {}
    fam = pre.get("familias") or {}
    mu = res.get("muestra") or {}
    if estado == "OK":
        w("Los tres preprocesadores de la matriz aprobada están construidos y pasan las diez validaciones. Se ajustaron una "
          "sola vez, solo para comprobarlos, con la muestra de partida de entrenamiento, y la validación se transformó sin "
          "leer su objetivo.")
    else:
        w(f"El script paró en estado {estado}: {res['resultado']['resumen']}")
    w("")
    if mu:
        w(f"La muestra de ajuste tiene {numero(mu['filas'])} filas: los {numero(mu['fallos'])} fallos y "
          f"{numero(mu['sanas_muestra'])} sanas, el {numero(100 * mu['fraccion_sanas'])} % de cada mes.")
        w("")
    if fam:
        w("Lo que tarda y lo que deja cada familia:")
        w("")
        for f in FAMILIAS:
            d = fam.get(f) or {}
            if d.get("tiempo_ajuste_s") is not None:
                w(f"- **{NOMBRE_FAMILIA[f][0].upper() + NOMBRE_FAMILIA[f][1:]}:** ajuste en {numero(d['tiempo_ajuste_s'], 1)} s y "
                  f"{numero(d['n_salida'])} columnas de salida; transformar la validación, {numero(d['tiempo_transformar_validacion_s'], 1)} s.")
        w("")
    w("## Partición")
    w("")
    pa_ = res.get("particion") or {}
    w(f"Partición por {pa_.get('estrategia', 'fecha')}, la de informes/particion.json: {pa_.get('por_que', '')}")
    w("")
    for p in pa_.get("partes", []):
        if p.get("filas") is not None:
            tasa = f", con un {numero(p['tasa_objetivo_pct'], 4)} % que falla en 30 días" if p.get("tasa_objetivo_pct") is not None else ""
            w(f"- **{p['parte'].capitalize()}:** {numero(p['filas'])} fotos{tasa}.")
    w("")
    w("## Desequilibrio de clases")
    w("")
    d = res.get("desequilibrio")
    if d and d.get("filas"):
        w(f"En entrenamiento fallan en 30 días {numero(d['fotos_con_fallo'])} de las {numero(d['filas'])} fotos. Por cada "
          f"foto de fallo hay {numero(d['razon'], 2)} sanas.")
        w("")
        for x in d["por_fabricante"]:
            w(f"- **{x['fabricante']}:** {numero(x['fallos'])} fallos en {numero(x['fotos'])} fotos, el {numero(x['tasa_pct'], 4)} %.")
        w("")
        pm = d["por_mes"]
        if pm["meses"]:
            w(f"En las {pm['meses']} fotos mensuales, el mes con menos fallos fue el {pm['mes_min']}, con {pm['fallos_min']}. "
              f"El que más, el {pm['mes_max']}, con {pm['fallos_max']}; la mediana es {numero(pm['fallos_mediana'], 1)}.")
            w("")
        w("Se trata solo al entrenar, con la muestra de partida, y la probabilidad se recalibra después (reglas, apartado 7).")
    else:
        w("No se calculó: el script paró antes de leer entrenamiento.")
    w("")
    w("## Matriz de transformaciones")
    w("")
    mz = res.get("matriz") or {}
    w(f"La matriz la aprobó {mz.get('aprobada_por') or 'nadie todavía'}"
      f"{' el ' + mz['fecha'] if mz.get('fecha') else ''}. Sus decisiones:")
    w("")
    for codigo, texto in mz.get("decisiones", []):
        w(f"- **{codigo}:** {texto}")
    w("")
    tl = pre.get("tramos_logistica") or {}
    if tl:
        w("Cómo quedó cada numérica en la logística tras el ajuste:")
        w("")
        w("| Variable | Tramos | Columnas | Vacío |")
        w("|---|---|---|---|")
        for c, t in tl.items():
            w(f"| {c} | {t['n_tramos']} | {t['columnas']} | {'tramo propio' if t['vacio_columna'] else 'en la referencia'} |")
        w("")
        ref = pre.get("referencias_logistica") or {}
        w("Las referencias de las nominales en la logística: " + "; ".join(f"{k}, {v}" for k, v in ref.items()) + ".")
        w("")
    w("## Variables que no entran")
    w("")
    rc = res.get("recuento") or {}
    if rc:
        w(f"De las {rc['columnas_tabla']} columnas de la tabla entran {rc['entran']}; no entran {rc['no_entran']}, cada una "
          f"con su motivo en la matriz, y {rc['fuera']} quedan fuera desde el principio.")
        w("")
        w("- **No entran:** " + ", ".join(NO_ENTRAN) + ".")
        w("- **Fuera:** " + ", ".join(FUERA) + ".")
        w("- **Solo en los árboles:** avisa, porque en la logística es la suma de los tramos de contadores_que_avisan.")
    w("")
    w("## Validaciones")
    w("")
    val = res.get("validaciones") or {}
    if val:
        for k, nombre in NOMBRES_VALIDACION.items():
            v = val.get(k)
            if v is None:
                w(f"- **{nombre[0].upper() + nombre[1:]}:** no se calculó.")
                continue
            por = [f"{NOMBRE_FAMILIA[f]}, {'sí' if v[f] else 'no'}" for f in FAMILIAS if v.get(f) is not None]
            w(f"- **{nombre[0].upper() + nombre[1:]}:** {'en verde' if v['resultado'] else 'EN ROJO'}"
              + (f" ({'; '.join(por)})" if por else "") + ".")
    else:
        w("No se calcularon: el script paró antes.")
    w("")
    cn = pre.get("categorias_nuevas_validacion") or {}
    if cn.get("model"):
        n = cn["model"]["no_en_entrenamiento"]
        w(f"En validación hay {len(n['valores'])} modelos de disco que no salen en entrenamiento, con {numero(n['filas'])} "
          "fotos: van a «otras», como fija la matriz.")
        w("")
    w("## Parámetros usados")
    w("")
    for p in res.get("parametros", []):
        w(f"- **{p['nombre'][0].upper() + p['nombre'][1:]}:** {p['valor']}. Origen: {p['origen']}.")
    w("")
    w("Los apartados del manual aplicados:")
    w("")
    for t in TEORIA:
        w(f"- {t}")
    w("")
    w("## Datos personales")
    w("")
    w(res["datos_personales"])
    w("")
    w("## Límites")
    w("")
    for x in res.get("limites", []):
        w(f"- {x}")
    w("")
    return "\n".join(L)


def escribir(raiz, res):
    """Escribe el JSON (UTF-8, sin NaN) y el informe, del mismo diccionario."""
    (raiz / SALIDA_JSON).parent.mkdir(parents=True, exist_ok=True)
    (raiz / SALIDA_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    (raiz / SALIDA_MD).write_text(informe(res), encoding="utf-8")


# =================================================================================================================
# 9. Principal
# =================================================================================================================
def base(raiz):
    """El bloque común y lo fijo, antes de saber el resultado."""
    return {
        "metodo": METODO, "version_metodo": version_metodo(), "script": SCRIPT, "peticion": PETICION,
        "fecha_datos": FECHA_DATOS, "fecha_ejecucion": dt.datetime.now().replace(microsecond=0).isoformat(),
        "entradas": [], "resultado": {"estado": None, "riesgo": None, "resumen": None, "artefactos": [SALIDA_JSON, SALIDA_MD], "siguiente": None},
        "pendientes": [],
        "objetivo": {"columna": OBJETIVO, "tipo": "si_no", "clase_positiva": 1},
        "algoritmo_previsto": ["regresión logística regularizada", "bosque aleatorio", "HistGradientBoosting"],
        "particion": None, "desequilibrio": None, "muestra": None, "matriz": None, "fuera": None, "recuento": None,
        "preprocesador": None, "validaciones": None,
        "parametros": [
            {"nombre": "semilla", "valor": SEMILLA, "origen": "parametros.md; sortea la muestra de partida"},
            {"nombre": "muestra de partida", "valor": f"todos los fallos y el {numero(100 * FRACCION_SANAS)} % de las sanas de cada mes", "origen": "reglas, apartado 7"},
            {"nombre": "mínimo por tramo y por categoría", "valor": f"{MINIMO_FOTOS} fotos, {MINIMO_FALLOS} fallos y {MINIMO_SANAS} sanas", "origen": "parametros.md; ficha de la logística §4.2 y §4.3"},
            {"nombre": "tramos", "valor": f"el 0 y cada valor con al menos el {numero(100 * CUOTA_APARTE)} % aparte; hasta {K_NEGATIVOS} trozos por debajo de 0 y {K_POSITIVOS} por encima", "origen": "matriz aprobada, criterio «tramos»"},
            {"nombre": "relleno categórico", "valor": SIN_DATO, "origen": "parametros.md y matriz (datacenter)"},
            {"nombre": "etiqueta de las raras", "valor": ETIQUETA_OTRAS, "origen": "ficha de la logística §4.3"},
            {"nombre": "escalado", "valor": "ninguno", "origen": "matriz aprobada, en las tres familias"},
            {"nombre": "sobrante del ColumnTransformer", "valor": "drop", "origen": "parametros.md"}],
        "teoria": TEORIA,
        "datos_personales": ("Ninguno: los datos son de discos y serial_number identifica un disco, no a una persona "
                             "(reglas, apartado 9); el preprocesador no lo usa. No existe config/fuentes/"
                             "proteccion-datos.json: los datos no pasaron por la protección porque no hacía falta."),
        "limites": [
            "El ajuste de este script es solo para comprobar: no se guarda. Lo ajusta aprendizaje-automatico con el modelo, "
            "dentro de cada pliegue, y los tramos y las categorías pueden cambiar con cada muestra.",
            "Las piezas propias (Tramos, AgruparRaras, ColumnasMenosReferencia) viven en este script: quien guarde el "
            "Pipeline con joblib tiene que poder importarlas al cargarlo.",
            "En la logística, fabricante entra en dos piezas: como nominal y como clave de los tramos de smart_1_raw y "
            "smart_7_raw, que solo se aprenden con Seagate. No sale dos veces.",
            "capacidad_tb, fabricante y garantia_anos salen del modelo de disco: en la logística pueden ser en parte "
            "combinación de las columnas de model; la validación 6 mira cada variable por separado y la preselección "
            "elige entre ellas (matriz)."],
    }


def principal(raiz):
    """Lee, construye, ajusta para comprobar, valida y escribe. Devuelve el código de salida."""
    inicio = time.time()
    res = base(raiz)
    try:
        # 9.1 La partición y sus huellas
        if not (raiz / PARTICION).exists():
            raise Parada(f"falta {PARTICION}", "PARADO")
        part = json.loads((raiz / PARTICION).read_text(encoding="utf-8"))
        if part.get("resultado", {}).get("estado") != "OK":
            raise Parada(f"{PARTICION} no está en OK", "PARADO")
        partes = {p["parte"]: p for p in part["partes"]}
        res["particion"] = {"estrategia": part.get("estrategia"), "por_que": part.get("por_que"),
                            "partes": [{k: p.get(k) for k in ("parte", "filas", "fotos_con_objetivo", "tasa_objetivo_pct", "fecha_min", "fecha_max")}
                                       for p in part["partes"]]}
        for nombre in ("entrenamiento", "validacion"):
            ruta = raiz / partes[nombre]["ruta"]
            huella = sha256(ruta) if ruta.exists() else None
            res["entradas"].append({"ruta": partes[nombre]["ruta"], "sha256": huella, "filas": pq.ParquetFile(ruta).metadata.num_rows if huella else None,
                                    "columnas": len(pq.read_schema(ruta).names) if huella else None})
            if huella != partes[nombre]["sha256"]:
                raise Parada(f"la huella de {partes[nombre]['ruta']} no es la de {PARTICION}", "PARADO")
        # 9.2 La matriz aprobada
        if not (raiz / MATRIZ).exists():
            raise Parada(f"falta {MATRIZ}: sin matriz aprobada no hay preprocesador", "PARADO")
        mz = leer_matriz((raiz / MATRIZ).read_text(encoding="utf-8"))
        res["entradas"].append({"ruta": MATRIZ, "sha256": sha256(raiz / MATRIZ), "estado": mz["estado"]})
        res["matriz"] = {"ruta": MATRIZ, "aprobada_por": mz["aprobada_por"], "fecha": mz["fecha"], "estado": mz["estado"],
                         "decisiones": mz["decisiones"], "variables": [f for f in mz["filas"] if f["seccion"] != "fuera"]}
        res["fuera"] = [f for f in mz["filas"] if f["seccion"] == "fuera"]
        if not mz["aprobada_por"]:
            raise Parada("la matriz no está aprobada: el método no monta el preprocesador sin aprobación", "PARADO")
        # 9.3 La décima: cada columna de la tabla en la matriz o fuera, y las listas del script son las de la matriz
        ent_ruta, val_ruta = raiz / partes["entrenamiento"]["ruta"], raiz / partes["validacion"]["ruta"]
        cols_tabla = list(pq.read_schema(ent_ruta).names)
        ok10, det10 = v_columnas_en_matriz(cols_tabla, mz)
        res["validaciones"] = {k: None for k in NOMBRES_VALIDACION}
        res["validaciones"]["columnas_en_matriz"] = {"resultado": ok10, "detalle": det10}
        res["recuento"] = {"columnas_tabla": len(cols_tabla), "entran": len(mz["entran"]), "no_entran": len(mz["no_entran"]),
                           "fuera": len(mz["fuera"]), "entran_en_logistica": len(mz["logistica"])}
        if not ok10:
            raise Parada("validación 10 en rojo: " + json.dumps(det10, ensure_ascii=False))
        if list(pq.read_schema(val_ruta).names) != cols_tabla:
            raise Parada("la validación no tiene las mismas columnas que el entrenamiento")
        # 9.4 Entrenamiento: desequilibrio, valores de las nominales y muestra de partida
        X, y, r = leer_entrenamiento(ent_ruta)
        res["desequilibrio"] = desequilibrio(r)
        res["muestra"] = {"filas": len(X), "fallos": r["fallos_muestra"], "sanas_muestra": r["sanas_muestra"],
                          "sanas_total": r["filas"] - r["fallos"], "fraccion_sanas": FRACCION_SANAS, "semilla": SEMILLA,
                          "como": "todas las fotos con fallo y, de cada mes, el 2 % de las sanas, sorteadas con la semilla en el orden de los meses"}
        valores = {c: sorted(str(v) for v in r["valores"][c]) for c in NOMINALES}
        ok8 = v_relleno_sin_choque({c: set(v) for c, v in valores.items()})
        res["validaciones"]["relleno_sin_choque"] = {"resultado": ok8, "detalle": {c: [v for v in vs if v in (SIN_DATO, ETIQUETA_OTRAS)] for c, vs in valores.items()}}
        # 9.5 Ajustar cada familia una vez, con la muestra, y revisar su salida sobre la misma muestra
        ajustados, revisiones, tiempos = {}, {}, {}
        variables = {"logistica": NUM_LOGISTICA + NOMINALES, "bosque": NUM_ARBOLES + NOMINALES, "hgb": NUM_ARBOLES + NOMINALES}
        for f in FAMILIAS:
            t0 = time.time()
            ajustados[f] = preprocesador(f).fit(X, y)
            tiempos[f] = {"tiempo_ajuste_s": round(time.time() - t0, 2)}
            revisiones[f] = {"entrenamiento": Revision(f, variables[f]), "validacion": Revision(f, variables[f])}
            for a in range(0, len(X), TROZO):
                revisiones[f]["entrenamiento"].anadir(ajustados[f].transform(X.iloc[a:a + TROZO]))
        # 9.6 La validación, por trozos y sin leer su objetivo
        leidas = NOMINALES + NUM_ARBOLES
        filas_val = 0
        nuevas = {c: {"no_en_entrenamiento": {}, "no_vistas_en_el_ajuste": {}} for c in NOMINALES}
        raras = ajustados["logistica"].named_steps["preparacion"].named_transformers_["categorias"].named_steps["raras"]
        for f in FAMILIAS:
            tiempos[f]["tiempo_transformar_validacion_s"] = 0.0
        for lote in pq.ParquetFile(val_ruta).iter_batches(batch_size=TROZO, columns=leidas):
            df = lote.to_pandas()
            filas_val += len(df)
            for c in NOMINALES:
                s = df[c].astype(object)
                s = s.where(s.notna(), SIN_DATO)
                for clave, conocidos in (("no_en_entrenamiento", set(valores[c]) | {SIN_DATO}), ("no_vistas_en_el_ajuste", set(raras.vistas_[c]))):
                    for v, n in s[~s.isin(conocidos)].value_counts().items():
                        nuevas[c][clave][str(v)] = nuevas[c][clave].get(str(v), 0) + int(n)
            for f in FAMILIAS:
                t0 = time.time()
                salida = ajustados[f].transform(df)
                tiempos[f]["tiempo_transformar_validacion_s"] += time.time() - t0
                revisiones[f]["validacion"].anadir(salida)
        # 9.7 Las nueve validaciones de el método, por familia
        val = res["validaciones"]
        por = {k: {} for k in ("filas", "sin_objetivo", "sin_intermedias", "sin_vacios", "nombres_unicos", "sin_redundancia",
                               "columnas_esperadas", "escalado_segun_matriz")}
        detalle = {k: {} for k in por}
        for f in FAMILIAS:
            re_, rv = revisiones[f]["entrenamiento"], revisiones[f]["validacion"]
            cols = re_.columnas
            permitidas = set(NUM_ARBOLES) if f != "logistica" else set()
            por["filas"][f] = v_filas(len(X), re_.filas) and v_filas(filas_val, rv.filas) and rv.columnas == cols
            por["sin_objetivo"][f] = v_sin_objetivo(cols)
            por["sin_intermedias"][f] = v_sin_intermedias(f, cols)
            con_vacio = re_.columnas_con_vacio | rv.columnas_con_vacio
            por["sin_vacios"][f] = v_sin_vacios(con_vacio, permitidas)
            detalle["sin_vacios"][f] = sorted(con_vacio - permitidas)
            por["nombres_unicos"][f] = v_nombres_unicos(cols)
            if f == "logistica":
                dup = re_.duplicadas()
                por["sin_redundancia"][f] = v_sin_redundancia(re_.grams, dup)
                detalle["sin_redundancia"][f] = {"duplicadas": dup, "variables_con_combinacion": [v for v, g in re_.grams.items()
                                                                                                if np.linalg.matrix_rank(g, hermitian=True) < g.shape[0]]}
            else:
                por["sin_redundancia"][f] = None
                detalle["sin_redundancia"][f] = "no aplica: los árboles admiten las k columnas de una categoría (matriz)"
            esp = esperadas(f, ajustados[f])
            por["columnas_esperadas"][f] = v_columnas_esperadas(cols, esp)
            detalle["columnas_esperadas"][f] = {"sobran": sorted(set(cols) - set(esp)), "faltan": sorted(set(esp) - set(cols))}
            por["escalado_segun_matriz"][f] = v_escalado(ajustados[f], re_.cero_uno and rv.cero_uno)
        for k, d in por.items():
            val[k] = {**d, "resultado": all(x for x in d.values() if x is not None), "detalle": detalle[k]}
        # 9.8 Lo que deja el preprocesador
        ctl = ajustados["logistica"].named_steps["preparacion"]
        t = ctl.named_transformers_["tramos"]
        cm = ctl.named_transformers_["categorias"].named_steps["columnas"]
        res["preprocesador"] = {
            "script": SCRIPT, "remainder": "drop", "columnas_leidas_validacion": leidas, "filas_validacion": filas_val,
            "familias": {f: {"columnas_entrada": (NUM_LOGISTICA + NOMINALES) if f == "logistica" else (NUM_ARBOLES + NOMINALES),
                             "columnas_salida": revisiones[f]["entrenamiento"].columnas, "n_salida": len(revisiones[f]["entrenamiento"].columnas),
                             "tiempo_ajuste_s": tiempos[f]["tiempo_ajuste_s"],
                             "tiempo_transformar_validacion_s": round(tiempos[f]["tiempo_transformar_validacion_s"], 2),
                             "categoricas_nativas": [f"{c}_oe" for c in NOMINALES] if f == "hgb" else None} for f in FAMILIAS},
            "referencias_logistica": dict(cm.referencia_),
            "categorias_logistica": {c: {"quedan": raras.quedan_[c], "otras": raras.otras_[c]} for c in NOMINALES},
            "tramos_logistica": {c: {"n_tramos": t.n_tramos_[c], "referencia": t.referencia_[c], "vacio_columna": t.vacio_columna_[c],
                                     "columnas": sum(1 for n in t.nombres_ if n.startswith(c + "_disc_cs_")), "tramos": t.tramos_[c]}
                                 for c in NUM_LOGISTICA},
            "categorias_nuevas_validacion": {c: {k: {"valores": sorted(v), "filas": sum(v.values())} for k, v in d.items()}
                                             for c, d in nuevas.items()},
        }
        rojas = [k for k, v in val.items() if v is not None and v["resultado"] is False]
        if rojas:
            raise Parada("validaciones en rojo: " + ", ".join(rojas))
        n = {f: res["preprocesador"]["familias"][f]["n_salida"] for f in FAMILIAS}
        res["resultado"] = {"estado": "OK", "riesgo": "bajo", "artefactos": [SALIDA_JSON, SALIDA_MD],
                            "resumen": (f"Tres preprocesadores sin ajustar, con la matriz aprobada por {mz['aprobada_por']}; "
                                        f"ajustados una vez para comprobar con {numero(len(X))} filas, dan {numero(n['logistica'])}, "
                                        f"{numero(n['bosque'])} y {numero(n['hgb'])} columnas, y pasan las diez validaciones."),
                            "siguiente": "preseleccion-variables con entrenamiento; después aprendizaje-automatico, que ajusta cada preprocesador con su modelo"}
        codigo = 0
    except Parada as p:
        res["resultado"] = {"estado": p.estado, "riesgo": "alto", "resumen": str(p)[:2000], "artefactos": [SALIDA_JSON, SALIDA_MD],
                            "siguiente": "corregir la causa y volver a ejecutar; la fase siguiente no empieza"}
        codigo = 2
    except Exception as e:  # noqa: BLE001 - el JSON se escribe también cuando falla (bloque común, regla 5)
        res["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(e).__name__}: {e}"[:2000],
                            "artefactos": [SALIDA_JSON, SALIDA_MD], "siguiente": "corregir el fallo y volver a ejecutar"}
        res["traza"] = traceback.format_exc()[-3000:]
        codigo = 1
    res["ejecucion"] = {"python": platform.python_version(), "ejecutable": sys.executable, "pandas": pd.__version__,
                        "pyarrow": pa.__version__, "scikit_learn": sklearn.__version__, "segundos": round(time.time() - inicio, 1)}
    escribir(raiz, res)
    print(f"{res['resultado']['estado']}: {res['resultado']['resumen']}")
    return codigo


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso (por defecto, la del script)")
    sys.exit(principal(Path(argumentos.parse_args().raiz).resolve()))
