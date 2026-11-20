"""Competición, ganador y validación del modelo del caso 68 (skill aprendizaje-automatico; encargo 21, partes 2 y 3).

Sin argumentos, solo con construcción (del 01/01/2020 al 30/06/2024):
  - cinco pliegues por fecha, bloques de tres meses de 2023-04 a 2024-06; cada uno entrena con los meses anteriores, solo
    con las fotos cuyo horizonte acabó antes del primer día del bloque y con la muestra del desequilibrio (todas las
    fotos con fallo y el 2 % de las sanas de cada mes, semilla 42), y mide en todas las fotos del bloque, mes a mes;
  - una búsqueda por algoritmo con los mismos pliegues: la logística en los 12 valores de C (ParameterGrid) y el bosque
    y el HistGradientBoosting con 15 candidatos (ParameterSampler, random_state=42). No usa RandomizedSearchCV: la
    muestra se toma solo en la parte que entrena de cada pliegue y cada bloque se puntúa por trozos de 50.000 filas,
    sin guardar la tabla transformada. Es el mismo método; lo dice el informe;
  - cada candidato es el Pipeline entero: el preprocesador de su familia (scripts/13_preparacion.py), las columnas de
    informes/preseleccion.json y el algoritmo. El preprocesador no depende de los hiperparámetros, así que se ajusta una
    vez por pliegue y familia y lo comparten los candidatos: es el mismo ajuste que haría cada Pipeline. En la logística
    se monta entero y después se quedan las columnas cuyo origen está en variables_finales;
  - la medida de la búsqueda: la media, en los meses del bloque, de los fallos en la lista de 100; al lado, las listas
    de 20, 500 y 1.000, el AUC y el PR-AUC de cada mes, con la regla de los cinco contadores y el trivial en las mismas
    fotos;
  - el ranking y el ganador pliegue a pliegue (skill §6), el sitio (guion §3), el reajuste con toda la construcción y
    su recalibración, la importancia por permutación en el último bloque con el modelo del pliegue 5, el canario y las
    validaciones del skill §9.
  Escribe informes/modelado.json en PARADO, con ganador.aprobado_por vacío: es la puerta de Juan antes de abrir la
  validación. Si el ganador no supera a la regla pliegue a pliegue, para también y lo dice en la primera frase.

Con --abrir-validacion (tercera parte): comprueba que ganador.aprobado_por está escrito y que la validación no se abrió
antes, reajusta la receta del ganador con construcción, lee data/processed/fotos_riesgo_validacion.parquet mes a mes,
mide el ganador, la regla y el trivial en las mismas fotos con assets/evaluacion_binaria.py y da el intervalo de la
diferencia en la lista de 100 remuestreando los 12 meses (1.000 veces, semilla 42). No vuelve a hacer la competición.

Importa scripts/13_preparacion.py con importlib para montar los preprocesadores: su trabajo está dentro de
`if __name__ == "__main__":` y al importarlo solo define las piezas. No importa ningún otro script.

Uso: python -W error scripts/15_modelado.py [--raiz CARPETA_DEL_CASO] [--abrir-validacion] [--candidatos N]
(--candidatos limita los candidatos de cada búsqueda; solo lo usa la prueba con su caso pequeño.)
Sale con 0 si termina o si para en una puerta de Juan, con 2 si para por otra causa y con 1 si falla; siempre escribe
el JSON (en la tercera parte, si para, deja la competición como estaba y solo cambia el resultado).
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import copy
import csv
import datetime as dt
import fnmatch
import hashlib
import importlib.util
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
import pyarrow.parquet as pq
import sklearn
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import ParameterGrid, ParameterSampler

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "assets"))
from graficos import numero  # noqa: E402  (pieza común: números a la española, redondeo como Excel)


def cargar_13():
    """Carga scripts/13_preparacion.py como módulo; solo define sus piezas, porque su trabajo está bajo __main__."""
    spec = importlib.util.spec_from_file_location("preparacion_13", CASO / "scripts" / "13_preparacion.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["preparacion_13"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


P13 = cargar_13()

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SKILL = "aprendizaje-automatico"
SKILL_MD = CASO / ".claude" / "skills" / "aprendizaje-automatico" / "SKILL.md"
SCRIPT = "scripts/15_modelado.py"
ENCARGO = "prompts/21_encargo_preseleccion_competicion_y_ganador.md, segunda y tercera parte, con sus dos notas"
FECHA_DATOS = "2025-06-30"                                   # reglas §5, fecha de referencia
PRESELECCION = "informes/preseleccion.json"
MATRIZ = "contexto-proyecto/modelo/matriz_transformaciones.md"
ENTRENAMIENTO = "data/processed/fotos_riesgo_entrenamiento.parquet"
VALIDACION = "data/processed/fotos_riesgo_validacion.parquet"
PIEZA = "assets/evaluacion_binaria.py"
PROTECCION = "contexto-proyecto/fuentes/proteccion-datos.json"
SALIDA_JSON = "informes/modelado.json"
SALIDA_CSV = "informes/modelado_busqueda.csv"
SALIDA_MD = "informes/modelado.md"
OBJETIVO, FECHA, HORIZONTE = "falla_30d", "fecha", "horizonte_hasta"
CONTADORES, SUMA = "contadores_que_avisan", "suma_contadores_sin_188"
LEER = P13.NOMINALES + P13.NUM_ARBOLES + [OBJETIVO, FECHA, HORIZONTE]
FAMILIAS = ["logistica", "bosque", "hgb"]
ORDEN_SENCILLEZ = ["logistica", "hgb", "bosque"]             # con empate, el más sencillo (skill §6)
FICHAS = {"logistica": "regresion_logistica", "bosque": "bosque_aleatorio", "hgb": "histgradientboosting"}
NOMBRE = {"logistica": "regresión logística", "bosque": "bosque aleatorio", "hgb": "HistGradientBoosting"}
CATEGORICAS_HGB = [f"{c}_oe" for c in P13.NOMINALES]

# Lo que Juan ya decidió de los pendientes de la preselección (segunda nota del encargo 21)
DECISIONES_DE_JUAN = {"P-01": "seguir con la lista de la semilla 42 (Juan, 18/11/2026, R-023)"}

# La partición y los pliegues (reglas §7; encargo 21)
INICIO_VALIDACION = "2024-07-01"
BLOQUES = [("2023-04-01", "2023-06-30"), ("2023-07-01", "2023-09-30"), ("2023-10-01", "2023-12-31"),
           ("2024-01-01", "2024-03-31"), ("2024-04-01", "2024-06-30")]
SITIO_DESDE = "2023-07-01"                                   # el sitio consta desde esa fecha (guion §3)
SEMILLA = 42
FRACCION_SANAS = P13.FRACCION_SANAS                          # reglas §7: todas las fotos con fallo y el 2 % de las sanas
LISTAS, LISTA = [20, 100, 500, 1000], 100                    # reglas §7, CP-010; la de 100 es la medida principal
TROZO = 50_000
# La búsqueda (reglas §7; algoritmos.md para sí o no, con early_stopping=False por la fecha)
CANDIDATOS = 15
MAX_RONDAS = 2                                               # rondas de ampliación por el borde (skill §5)
ESPACIOS = {
    "logistica": {"C": [float(c) for c in np.logspace(-3, 2, 12)]},
    "bosque": {"max_depth": [5, 10, 15], "n_estimators": [100, 300, 500], "min_samples_leaf": ["hoja", "2xhoja"],
               "max_features": ["sqrt", 0.3, 0.5]},
    "hgb": {"learning_rate": [0.025, 0.05, 0.1], "max_depth": [3, 5, None], "max_iter": [100, 200, 500],
            "min_samples_leaf": ["hoja"], "l2_regularization": [0.0, 0.5, 1.0]},
}
PASO_C = 10 ** (5 / 11)                                      # el paso de logspace(-3, 2, 12)
# Los controles
METRICA_PERMUTACION, REPETICIONES, MUESTRA_PERMUTACION = "average_precision", 10, 0.25
TOLERANCIA_PROBABILIDAD = 0.20                               # validación 12 (encargo 21)
CANARIO_FUGA = 0.90                                          # la fuga encuentra al menos el 90 % de lo que cabe
REMUESTREOS = 1000
VALIDACIONES = ["sin_filas_de_ajuste", "semillas", "validacion_una_vez", "con_probabilidad", "columnas_de_preseleccion",
                "recalibrado_si_hace_falta", "citas_existen", "reproducible", "sin_identificadores_ni_posteriores",
                "sin_resultados_escritos", "canario_objetivo_barajado", "probabilidad_media_cerca_de_la_tasa",
                "objetivo_conocido_al_entrenar"]

TEORIA = [
    "20.3 y 31.6: validación cruzada temporal, con bloques de meses enteros y sin barajar, porque el modelo se usa hacia "
    "adelante y barajar mezclaría meses.",
    "32.6 y 32.7: rejilla en la logística, que solo busca C, y búsqueda aleatoria en los árboles, una por algoritmo.",
    "37.4 y 37.8: submuestreo de las sanas solo al entrenar y recalibración por la corrección del prior, porque la "
    "probabilidad se usa para esperar fallos.",
    "21.1 y 21.8: todo con la probabilidad; AUC y PR-AUC del mes al lado de la lista de 100, que es la medida del negocio.",
    "19.3: la distancia entre entrenamiento y fuera de pliegue, en AUC, para ver el sobreajuste.",
    "5.1: las tres vías de mejora si el modelo no supera a la regla.",
    "4.6 y 5.3: el intervalo de la diferencia remuestreando meses, que es la unidad de la medida.",
]


class Parada(Exception):
    """Condición que impide seguir; `estado` dice si la skill paró a propósito (PARADO) o si falló algo (ERROR)."""

    def __init__(self, mensaje, estado="ERROR", codigo=2):
        super().__init__(mensaje)
        self.estado = estado
        self.codigo = codigo


# =================================================================================================================
# 3. Las listas de N, la regla y las medidas de cada mes
# =================================================================================================================
def fallos_en_lista(claves, y, n):
    """Fallos entre los N primeros, ordenando de mayor a menor por las claves (la primera manda). Si el puesto N cae
    dentro de un grupo empatado, se lleva de ese grupo fallos × plazas que quedan / filas del grupo."""
    claves = [np.asarray(k, dtype=float) for k in claves]
    y = np.asarray(y, dtype=float)
    orden = np.lexsort([-k for k in claves[::-1]])
    ks = [k[orden] for k in claves]
    ys = y[orden]
    cambio = np.ones(len(ys), dtype=bool)
    if len(ys) > 1:
        cambio[1:] = np.any([k[1:] != k[:-1] for k in ks], axis=0)
    inicio = np.flatnonzero(cambio)
    tam = np.diff(np.append(inicio, len(ys)))
    fal = np.add.reduceat(ys, inicio) if len(ys) else np.array([])
    quedan, total = n, 0.0
    for t, f in zip(tam, fal):
        toma = min(quedan, t)
        total += f * toma / t
        quedan -= toma
        if quedan <= 0:
            break
    return float(total)


def claves_regla(df):
    """La regla de los cinco contadores: cuántos contadores avisan y, a igualdad, su suma sin el 188; vacía cuenta 0."""
    return [pd.to_numeric(df[CONTADORES]).to_numpy(dtype=float, na_value=0.0),
            pd.to_numeric(df[SUMA]).to_numpy(dtype=float, na_value=0.0)]


def rango_denso(claves):
    """Una puntuación que ordena como las claves (más alta, más riesgo), para el AUC y el PR-AUC de la regla."""
    claves = [np.asarray(k, dtype=float) for k in claves]
    orden = np.lexsort(claves[::-1])
    ks = [k[orden] for k in claves]
    cambio = np.zeros(len(orden), dtype=float)
    if len(orden) > 1:
        cambio[1:] = np.any([k[1:] != k[:-1] for k in ks], axis=0)
    r = np.empty(len(orden))
    r[orden] = np.cumsum(cambio)
    return r


def medidas_mes(y, claves, puntuacion):
    """Las cifras de un mes: los fallos en las listas de 20, 100, 500 y 1.000, el AUC y el PR-AUC."""
    y = np.asarray(y).astype(int)
    m = {"filas": int(len(y)), "fallos": int(y.sum())}
    for n in LISTAS:
        m[f"lista_{n}"] = fallos_en_lista(claves, y, n)
    dos = 0 < y.sum() < len(y)
    m["auc"] = float(roc_auc_score(y, puntuacion)) if dos else None
    m["pr_auc"] = float(average_precision_score(y, puntuacion)) if dos else None
    return m


def recalibrar(p, tasa_muestra, tasa_real):
    """Corrección del prior sobre el logit: la probabilidad aprendida con la muestra pasa a la escala real."""
    p = np.clip(np.asarray(p, dtype=float), 1e-15, 1 - 1e-15)
    odds = p / (1 - p) * (tasa_real / (1 - tasa_real)) / (tasa_muestra / (1 - tasa_muestra))
    return odds / (1 + odds)


# =================================================================================================================
# 4. El empate, el ganador y el veredicto (skill §6 y §8)
# =================================================================================================================
def empate(a, b):
    """Pliegue a pliegue: la media de a − b frente a su desviación típica; empatan si la media no la pasa."""
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    media = float(d.mean())
    sd = float(d.std(ddof=1)) if len(d) > 1 else 0.0
    return {"media": media, "desviacion": sd, "empatan": abs(media) <= sd, "por_pliegue": [float(x) for x in d]}


def elegir_ganador(cv, trivial):
    """El de mejor media; si empata con otros, el más estable frente al trivial (menor desviación de su mejora) y, si
    siguen igualados, el más sencillo."""
    orden = [a for a in ORDEN_SENCILLEZ if a in cv] + [a for a in cv if a not in ORDEN_SENCILLEZ]
    mejor = max(orden, key=lambda a: (float(np.mean(cv[a])), -orden.index(a)))
    empatados = [a for a in orden if a == mejor or empate(cv[mejor], cv[a])["empatan"]]
    estab = {a: float(np.std(np.asarray(cv[a]) - np.asarray(trivial), ddof=1)) for a in empatados}
    ganador = min(empatados, key=lambda a: (estab[a], orden.index(a))) if len(empatados) > 1 else mejor
    return ganador, {"mejor_media": mejor, "empatados_con_el_mejor": empatados, "estabilidad_frente_al_trivial": estab,
                     "comparaciones": {a: empate(cv[ganador], cv[a]) for a in orden if a != ganador}}


def veredicto(modelo, referencia):
    """Supera, no supera o no se puede afirmar, pliegue a pliegue."""
    e = empate(modelo, referencia)
    if e["empatan"]:
        return "no se puede afirmar"
    return "supera" if e["media"] > 0 else "no supera"


def preseleccion_lista(js):
    """Paso 1: OK sigue; AVISO sigue si cada pendiente tiene la decisión de Juan escrita aquí; lo demás para."""
    estado = (js.get("resultado") or {}).get("estado")
    if estado == "OK":
        return True, "en OK"
    if estado == "AVISO":
        sin = [p.get("id") for p in js.get("pendientes", []) if p.get("id") not in DECISIONES_DE_JUAN]
        if sin:
            return False, f"en AVISO con pendientes sin decisión de Juan: {sin}"
        return True, "en AVISO, con cada pendiente decidido por Juan: " + "; ".join(
            f"{p['id']}, {DECISIONES_DE_JUAN[p['id']]}" for p in js.get("pendientes", []))
    return False, f"en estado {estado}"


# =================================================================================================================
# 5. Los candidatos y la ampliación por el borde (skill §5)
# =================================================================================================================
def _orden(valor):
    """Orden de un valor de la rejilla: None (sin límite) arriba; «sqrt» abajo; «k×hoja» por su factor."""
    if valor is None:
        return float("inf")
    if valor == "sqrt":
        return -1.0
    if isinstance(valor, str) and valor.endswith("hoja"):
        return 1.0 if valor == "hoja" else float(valor.split("x")[0])
    return float(valor)


AMPLIAR = {
    ("logistica", "C"): (lambda v: v / PASO_C, lambda v: v * PASO_C),
    ("bosque", "max_depth"): (lambda v: v - 2 if v > 2 else None, lambda v: None if v is None else v + 5),
    ("bosque", "n_estimators"): (lambda v: None, lambda v: None),       # más árboles solo cuestan (algoritmos.md)
    ("bosque", "min_samples_leaf"): (lambda v: None, lambda v: f"{2 * int(_orden(v))}xhoja"),
    ("bosque", "max_features"): (lambda v: None, lambda v: round(min(1.0, float(v) + 0.2), 2) if v != "sqrt" else None),
    ("hgb", "learning_rate"): (lambda v: v / 2, lambda v: v * 2),
    ("hgb", "max_depth"): (lambda v: v - 1 if v is not None and v > 2 else None, lambda v: None),
    ("hgb", "max_iter"): (lambda v: v // 2, lambda v: v * 2),
    ("hgb", "l2_regularization"): (lambda v: None, lambda v: v * 2),
}


def ampliar(familia, param, valor, valores=None):
    """El valor que amplía la rejilla por el borde en que cae `valor`; None si no está en un borde o no se amplía."""
    valores = ESPACIOS[familia][param] if valores is None else valores
    if len(valores) < 2 or (familia, param) not in AMPLIAR:
        return None
    k = _orden(valor)
    claves = [_orden(v) for v in valores]
    abajo, arriba = AMPLIAR[(familia, param)]
    if k == max(claves):
        return arriba(valor)
    if k == min(claves):
        return abajo(valor)
    return None


def candidatos_iniciales(familia, n):
    """Los candidatos de la primera búsqueda: la rejilla de C en la logística y n sorteados en los árboles."""
    espacio = ESPACIOS[familia]
    if familia == "logistica":
        todos = list(ParameterGrid(espacio))
        if n < len(todos):
            todos = [todos[i] for i in np.unique(np.round(np.linspace(0, len(todos) - 1, n)).astype(int))]
        return [dict(c) for c in todos]
    total = int(np.prod([len(v) for v in espacio.values()]))
    return [dict(c) for c in ParameterSampler(espacio, n_iter=min(n, total), random_state=SEMILLA)]


def hoja_de(filas):
    """La hoja mínima: max(20, 1 % de las filas que entrenan), redondeada al entero (parametros.md)."""
    return max(20, int(np.floor(0.01 * filas + 0.5)))


def resolver(params, hoja):
    """Los hiperparámetros con la hoja del pliegue puesta en número."""
    p = dict(params)
    if isinstance(p.get("min_samples_leaf"), str):
        p["min_samples_leaf"] = int(_orden(p["min_samples_leaf"])) * hoja
    return p


def construir(familia, params, hoja, con_fuga=False):
    """El algoritmo de una familia con sus hiperparámetros y la semilla."""
    p = resolver(params, hoja)
    if familia == "logistica":
        return LogisticRegression(solver="lbfgs", l1_ratio=0, max_iter=5000, random_state=SEMILLA, C=p["C"])
    if familia == "bosque":
        return RandomForestClassifier(n_jobs=-1, random_state=SEMILLA, **p)
    return HistGradientBoostingClassifier(early_stopping=False, random_state=SEMILLA, categorical_features=CATEGORICAS_HGB, **p)


def clave(params):
    """Un texto que identifica un candidato."""
    return json.dumps(params, sort_keys=True, default=str)


# =================================================================================================================
# 6. Las columnas de la logística por variable de origen (matriz, columnas «variable» y «salida»)
# =================================================================================================================
def patrones_logistica(mz):
    """El patrón de nombre de las columnas de la logística de cada variable, leído de la columna «salida» de la matriz."""
    patrones = {}
    for fila in mz["filas"]:
        if fila["seccion"] != "entran" or fila["variable"] not in mz["logistica"]:
            continue
        for trozo in fila["salida"].split("<br>"):
            m = re.match(r"\s*L:\s*(\S+)\s*$", trozo)
            if m and m.group(1) != "—":
                patrones[fila["variable"]] = m.group(1)
    return patrones


def columnas_de(columnas, variables, patrones):
    """Las columnas de salida cuyo origen está en `variables`, en su orden."""
    return [c for c in columnas if any(fnmatch.fnmatchcase(c, patrones[v]) for v in variables if v in patrones)]


# =================================================================================================================
# 7. Lectura: los meses medidos y la muestra de cada entrenamiento
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leído por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


class Datos:
    """Una tabla de fotos leída grupo a grupo: los meses que tiene, un mes entero y la muestra de un entrenamiento."""

    def __init__(self, ruta):
        self.ruta = ruta
        self.pf = pq.ParquetFile(ruta)
        self.grupos = {}
        for i in range(self.pf.num_row_groups):
            for f in np.unique(self.pf.read_row_group(i, columns=[FECHA])[FECHA].to_numpy()):
                self.grupos.setdefault(pd.Timestamp(f), []).append(i)
        self.meses = sorted(self.grupos)

    def mes(self, m):
        """Todas las fotos de un mes, con las columnas que se usan."""
        partes = []
        for i in self.grupos[pd.Timestamp(m)]:
            t = self.pf.read_row_group(i, columns=LEER)
            fe = t[FECHA].to_numpy()
            partes.append(t.take(pa.array(np.flatnonzero(fe == np.datetime64(pd.Timestamp(m), "ms")))))
        return pa.concat_tables(partes).to_pandas()

    def muestra(self, inicio):
        """Las fotos anteriores a `inicio` cuyo horizonte acabó antes de ese día; de ellas, todas las de fallo y el 2 %
        de las sanas de cada mes, sorteadas con la semilla en el orden de los meses. Devuelve la muestra y lo contado."""
        corte = np.datetime64(pd.Timestamp(inicio), "ms")
        rng = np.random.default_rng(SEMILLA)
        trozos = []
        c = {"filas_antes": 0, "filas_entrena": 0, "fallos_entrena": 0, "filas_quitadas": 0, "fallos_quitados": 0,
             "horizonte_max": None}
        hmax = None
        for m in self.meses:
            if m >= pd.Timestamp(inicio):
                continue
            for i in self.grupos[m]:
                t = self.pf.read_row_group(i, columns=LEER)
                fe, ho = t[FECHA].to_numpy(), t[HORIZONTE].to_numpy()
                y = t[OBJETIVO].to_numpy().astype(np.int64)
                antes = fe == np.datetime64(m, "ms")
                ok = antes & (ho < corte)
                c["filas_antes"] += int(antes.sum())
                c["filas_entrena"] += int(ok.sum())
                c["fallos_entrena"] += int(y[ok].sum())
                c["filas_quitadas"] += int((antes & ~ok).sum())
                c["fallos_quitados"] += int(y[antes & ~ok].sum())
                sanas = np.flatnonzero(ok & (y == 0))
                k = int(np.floor(FRACCION_SANAS * len(sanas) + 0.5))
                elegidas = rng.choice(sanas, size=k, replace=False) if k else np.array([], dtype=np.int64)
                filas = np.sort(np.concatenate([np.flatnonzero(ok & (y == 1)), elegidas]))
                if len(filas):
                    trozos.append(t.take(pa.array(filas)))
                    h = ho[filas].max()
                    hmax = h if hmax is None or h > hmax else hmax
        df = pa.concat_tables(trozos).to_pandas()
        y = df[OBJETIVO].to_numpy().astype(np.int64)
        c["horizonte_max"] = str(np.datetime_as_string(hmax, unit="D")) if hmax is not None else None
        c["muestra"] = {"filas": int(len(df)), "fallos": int(y.sum()), "sanas": int(len(df) - y.sum())}
        c["tasa_muestra"] = float(y.mean())
        c["tasa_real"] = c["fallos_entrena"] / c["filas_entrena"]
        c["hoja"] = hoja_de(len(df))
        c["horizonte_cerrado"] = bool(hmax is None or hmax < corte)
        return df, y, c


def sin_sitio(df):
    """La misma tabla con el centro de datos vaciado: el modelo sin sitio."""
    df = df.copy()
    df["datacenter"] = pd.Series([None] * len(df), index=df.index, dtype=object)
    return df


# =================================================================================================================
# 8. Ajustar y medir
# =================================================================================================================
class Contexto:
    """Lo que comparten las búsquedas: los datos, la preselección, los entrenamientos de cada pliegue y lo usado."""

    def __init__(self, datos, finales, patrones):
        self.datos = datos
        self.finales = finales
        self.patrones = patrones
        self.cache = {}
        self.semillas = set()
        self.segundos_ajuste = []
        self.columnas_vacias = []

    def entrenamiento(self, f):
        """La muestra del pliegue f (0 a 4), leída una vez."""
        if f not in self.cache:
            self.cache[f] = self.datos.muestra(BLOQUES[f][0])
        return self.cache[f]

    def meses_bloque(self, f):
        """Los meses del bloque f."""
        a, b = pd.Timestamp(BLOQUES[f][0]), pd.Timestamp(BLOQUES[f][1])
        return [m for m in self.datos.meses if a <= m <= b]


def transformar(pre, df, familia, ctx):
    """La salida del preprocesador ajustado, con la selección de la logística, por trozos y en float32."""
    partes = []
    for a in range(0, len(df), TROZO):
        out = pre.transform(df.iloc[a:a + TROZO])
        if familia == "logistica":
            out = out[columnas_de(list(out.columns), ctx.finales, ctx.patrones)]
        out = out.drop(columns=getattr(pre, "columnas_vacias_", []))
        partes.append(out.astype(np.float32))
    return pd.concat(partes)


def ajustar(familia, candidatos, df, y, hoja, ctx, sitio=True, y_ajuste=None, fuga=False):
    """Ajusta el preprocesador una vez y cada candidato encima; devuelve el preprocesador, los modelos y el AUC de
    cada uno en sus propias filas (entrenamiento)."""
    df = df if sitio else sin_sitio(df)
    yy = y if y_ajuste is None else y_ajuste
    pre = P13.preprocesador(familia).fit(df, yy)
    Xt = transformar(pre, df, familia, ctx)
    # Una columna sin ningún dato en las filas del ajuste no aporta nada y el HistGradientBoosting no puede hacer sus
    # tramos: sale de este ajuste y de su puntuación (smart_90_raw no tiene datos antes de mayo de 2023)
    pre.columnas_vacias_ = [c for c in Xt.columns if Xt[c].isna().all()]
    if pre.columnas_vacias_:
        Xt = Xt.drop(columns=pre.columnas_vacias_)
        ctx.columnas_vacias.append({"familia": familia, "columnas": pre.columnas_vacias_, "filas_del_ajuste": int(len(Xt))})
    if fuga:
        Xt["canario_fuga"] = yy.astype(np.float32)
    modelos, auc_ent = [], []
    for c in candidatos:
        t0 = time.time()
        mdl = construir(familia, c, hoja).fit(Xt, yy)
        ctx.segundos_ajuste.append(time.time() - t0)
        ctx.semillas.add(mdl.get_params()["random_state"])
        modelos.append(mdl)
        p = mdl.predict_proba(Xt)[:, 1]
        auc_ent.append(float(roc_auc_score(yy, p)) if 0 < yy.sum() < len(yy) else None)
    return pre, modelos, auc_ent, list(Xt.columns)


def puntuar(pre, modelos, df, familia, ctx, sitio=True, fuga=False):
    """La probabilidad de cada modelo en las fotos de `df`, por trozos de 50.000 filas."""
    df = df if sitio else sin_sitio(df)
    probs = [[] for _ in modelos]
    for a in range(0, len(df), TROZO):
        trozo = df.iloc[a:a + TROZO]
        X = transformar(pre, trozo, familia, ctx)
        if fuga:
            X["canario_fuga"] = trozo[OBJETIVO].to_numpy().astype(np.float32)
        for j, mdl in enumerate(modelos):
            probs[j].append(mdl.predict_proba(X)[:, 1])
    return [np.concatenate(p) for p in probs]


def evaluar(familia, candidatos, ctx, pliegues=range(5), sitio=True):
    """Cada candidato en cada pliegue: las cifras de cada mes medido, la probabilidad media recalibrada y el AUC en sus
    filas de ajuste. Devuelve una lista, un elemento por candidato, con un diccionario por pliegue."""
    salida = [{} for _ in candidatos]
    for f in pliegues:
        df, y, c = ctx.entrenamiento(f)
        pre, modelos, auc_ent, _ = ajustar(familia, candidatos, df, y, c["hoja"], ctx, sitio=sitio)
        meses = {j: [] for j in range(len(candidatos))}
        for mes in ctx.meses_bloque(f):
            dm = ctx.datos.mes(mes)
            ym = dm[OBJETIVO].to_numpy().astype(int)
            for j, p in enumerate(puntuar(pre, modelos, dm, familia, ctx, sitio=sitio)):
                r = medidas_mes(ym, [p], p)
                r["mes"] = mes.date().isoformat()
                r["prob_media_recalibrada"] = float(recalibrar(p, c["tasa_muestra"], c["tasa_real"]).mean())
                r["prob_unicas"] = int(min(len(np.unique(p)), 3))
                meses[j].append(r)
        for j in range(len(candidatos)):
            salida[j][f] = {"meses": meses[j], "auc_entrenamiento": auc_ent[j],
                            "lista_100": float(np.mean([r["lista_100"] for r in meses[j]]))}
    return salida


def cv(resultado, pliegues=range(5)):
    """La medida de la búsqueda de un candidato en cada pliegue."""
    return np.array([resultado[f]["lista_100"] for f in pliegues])


# =================================================================================================================
# 9. La búsqueda de un algoritmo, con su ampliación por el borde
# =================================================================================================================
def buscar(familia, ctx, n):
    """Primera búsqueda y, si el mejor cae en el borde de un hiperparámetro, hasta MAX_RONDAS rondas que lo amplían."""
    espacio = copy.deepcopy(ESPACIOS[familia])
    cands = candidatos_iniciales(familia, n)
    resultados = evaluar(familia, cands, ctx)
    rondas = [0] * len(cands)
    mejor = int(np.argmax([cv(r).mean() for r in resultados]))
    segundas, ampliadas = [], []
    for ronda in range(1, MAX_RONDAS + 1):
        vistos = {clave(c) for c in cands}
        nuevos = []
        for param, valor in cands[mejor].items():
            nv = ampliar(familia, param, valor, espacio[param])
            if nv is None:
                continue
            c = dict(cands[mejor]); c[param] = nv
            if clave(c) not in vistos:
                nuevos.append((param, nv, c))
        if not nuevos:
            break
        res_nuevos = evaluar(familia, [c for _, _, c in nuevos], ctx)
        adoptados = []
        base = cv(resultados[mejor])
        for (param, nv, c), r in zip(nuevos, res_nuevos):
            espacio[param].append(nv)
            ampliadas.append(f"{NOMBRE[familia]}, {param} hasta {numero(nv, 4) if isinstance(nv, float) else nv}")
            cands.append(c); resultados.append(r); rondas.append(ronda)
            e = empate(cv(r), base)
            adopta = (not e["empatan"]) and e["media"] > 0
            segundas.append({"algoritmo": familia, "que_contesta": f"{param} en el borde ({cands[mejor][param]}); se prueba {nv}",
                             "mejora": e["media"], "desviacion": e["desviacion"], "se_queda": adopta, "ronda": ronda})
            if adopta:
                adoptados.append(len(cands) - 1)
        if not adoptados:
            break
        mejor = max(adoptados, key=lambda j: cv(resultados[j]).mean())
    return {"candidatos": cands, "resultados": resultados, "rondas": rondas, "mejor": mejor, "segundas": segundas,
            "ampliadas": ampliadas, "espacio": espacio}


# =================================================================================================================
# 10. Las validaciones del skill §9 y sus piezas
# =================================================================================================================
def escritos_en_codigo(texto):
    """Líneas que ponen una validación a True a mano (validación 10)."""
    claves = "|".join(VALIDACIONES)
    patron = re.compile(r"[\"'](" + claves + r")[\"']\s*\]?\s*[:=]\s*True\b|\b(" + claves + r")\s*=\s*True\b")
    return [(n, linea.strip()) for n, linea in enumerate(texto.splitlines(), 1) if patron.search(linea)]


def v_canario(barajado, trivial, fuga, techo):
    """11. Con el objetivo barajado la lista de 100 cae a lo del trivial (como mucho, el trivial más tres desviaciones
    de Poisson y un fallo); con la fuga sube a casi todo lo que cabe (el 90 % o más)."""
    return bool(barajado <= trivial + 3 * np.sqrt(max(trivial, 0.0)) + 1 and fuga >= CANARIO_FUGA * techo)


def v_prob_media(media, tasa, tolerancia=TOLERANCIA_PROBABILIDAD):
    """12. La probabilidad media recalibrada de un bloque no se aparta de su tasa real más del 20 % relativo."""
    return bool(tasa > 0 and abs(media - tasa) / tasa <= tolerancia)


def intervalo_meses(diferencias, remuestreos=REMUESTREOS, semilla=SEMILLA):
    """Intervalo de la media de las diferencias remuestreando meses enteros: percentiles 2,5 y 97,5."""
    d = np.asarray(diferencias, dtype=float)
    rng = np.random.default_rng(semilla)
    medias = d[rng.integers(0, len(d), size=(remuestreos, len(d)))].mean(axis=1)
    return {"medida": "fallos en la lista de 100, diferencia media por mes", "media": float(d.mean()),
            "bajo": float(np.percentile(medias, 2.5)), "alto": float(np.percentile(medias, 97.5)),
            "remuestreos": remuestreos, "semilla": semilla, "unidad": "mes", "unidades": int(len(d))}


def filas_etiquetadas(res):
    """1. Cada cifra de comparación dice sobre qué filas se calculó, y ninguna de fuera de pliegue sale del ajuste."""
    bloques = list(res["ranking"]) + list(res["referencias_cv"])
    return bool(bloques) and all(b.get("filas") == "fuera de pliegue" for b in bloques) and all(
        b.get("filas_entrenamiento") == "entrenamiento" for b in res["ranking"])


class ConElResto(ClassifierMixin, BaseEstimator):
    """El Pipeline del ganador, que recibe solo las variables que se permutan y añade el resto por índice; así la
    permutación (sklearn) baraja solo las variables del modelo."""

    def __init__(self, pre=None, modelo=None, resto=None, familia=None, ctx=None, sitio=True):
        self.pre, self.modelo, self.resto, self.familia, self.ctx, self.sitio = pre, modelo, resto, familia, ctx, sitio
        self.classes_ = np.array([0, 1])

    def fit(self, X, y=None):
        """Ya está ajustado: no hace nada."""
        return self

    def predict_proba(self, X):
        """La probabilidad con las variables de X y el resto de la tabla en las mismas filas."""
        df = pd.concat([X, self.resto.loc[X.index]], axis=1)
        p = puntuar(self.pre, [self.modelo], df, self.familia, self.ctx, sitio=self.sitio)[0]
        return np.column_stack([1 - p, p])


# =================================================================================================================
# 11. El JSON, la tabla de lo probado y el informe
# =================================================================================================================
def version_skill():
    """La fecha y el código de la última línea de versión del SKILL.md (bloque común de resultado.md)."""
    if not SKILL_MD.exists():
        return None
    lineas = [x for x in SKILL_MD.read_text(encoding="utf-8").splitlines() if x.startswith("Versión ")]
    m = re.match(r"Versión (\S+) \(([^),]+)", lineas[-1]) if lineas else None
    return f"{m.group(1)} ({m.group(2)})" if m else None


NOMBRES_VALIDACION = {
    "sin_filas_de_ajuste": "ninguna cifra de comparación sale de las filas del ajuste",
    "semillas": "cada modelo y cada muestra llevan la semilla 42",
    "validacion_una_vez": "la validación no se abrió o se abrió una sola vez, con el ganador aprobado",
    "con_probabilidad": "las medidas se calcularon con la probabilidad",
    "columnas_de_preseleccion": "las columnas del ganador son las de la preselección",
    "recalibrado_si_hace_falta": "la probabilidad se recalibró, porque se entrenó con una muestra",
    "citas_existen": "lo que cita el JSON existe",
    "reproducible": "el mismo ajuste, repetido, da las mismas cifras",
    "sin_identificadores_ni_posteriores": "ningún identificador ni variable posterior a la decisión entra",
    "sin_resultados_escritos": "el script no lleva ninguna validación escrita con un sí",
    "canario_objetivo_barajado": "el canario: con el objetivo barajado cae al trivial y con la fuga sube a casi todo",
    "probabilidad_media_cerca_de_la_tasa": "la probabilidad media recalibrada de cada bloque queda cerca de su tasa",
    "objetivo_conocido_al_entrenar": "ningún entrenamiento usa una foto con el horizonte abierto el día que empieza lo que mide",
}


def escribir_csv(raiz, filas):
    """La tabla de todo lo probado, una fila por candidato."""
    with open(raiz / SALIDA_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["algoritmo", "hiperparametros", "ronda", "cv_media", "cv_desviacion",
                                          "entrenamiento_media", "cv_auc_media", "posicion"])
        w.writeheader()
        for fila in filas:
            w.writerow(fila)


def _n(x, d=1):
    """Un número para el informe, o «no se calculó»."""
    return "no se calculó" if x is None else numero(x, d)


def informe(res):
    """El informe interno del modelado, con los apartados de resultado.md y solo las cifras del diccionario."""
    L = []
    w = L.append
    w("# Modelado · competición y ganador")
    w("")
    w(res["resultado"]["resumen"])
    w("")
    w("## Lo aprobado antes de entrenar")
    w("")
    ap = res.get("aprobado_antes") or {}
    w(f"La medida principal son {ap.get('medida_principal', '')}. {ap.get('por_que', '')} Se da por bueno si "
      f"{ap.get('se_da_por_bueno', '')}")
    w("")
    w(f"Las referencias son {', '.join(ap.get('referencias', []))}. La preselección llegó así: {res.get('preseleccion_estado', '')}.")
    w("")
    w("## Qué se probó y cuánto costó")
    w("")
    b = res.get("busqueda") or {}
    if b.get("espacio"):
        w(f"Una búsqueda por algoritmo con los mismos cinco pliegues por fecha. {b.get('como', '')}")
        w("")
        for e in b["espacio"]:
            w(f"- {NOMBRE[e['algoritmo']]}: {e['probadas']} candidatos de {e['combinaciones']} combinaciones posibles.")
        w("")
        if b.get("rejillas_ampliadas"):
            w("La rejilla se amplió por el borde en: " + "; ".join(b["rejillas_ampliadas"]) + ".")
            w("")
        w(f"La búsqueda tardó {_n(res.get('ejecucion', {}).get('segundos_busqueda'), 0)} segundos.")
    else:
        w("No se llegó a buscar: el script paró antes.")
    w("")
    w("## El desequilibrio")
    w("")
    d = res.get("desequilibrio") or {}
    w(d.get("por_que", ""))
    rc = d.get("recalibracion") or {}
    if rc.get("tasa_muestra") is not None:
        w(f"En el reajuste final, la muestra tiene una tasa de fallo de {numero(100 * rc['tasa_muestra'], 2)} % y la "
          f"construcción, de {numero(100 * rc['tasa_real'], 4)} %; la recalibración devuelve la probabilidad a la escala real.")
    w("")
    w("## Ranking")
    w("")
    if res.get("ranking"):
        w("Fallos encontrados en la lista de 100 de cada mes, media de los meses medidos, fuera de pliegue. El AUC de "
          "entrenamiento va al lado para ver el sobreajuste frente al AUC fuera de pliegue.")
        w("")
        w("| Algoritmo | Lista de 100, media | Desviación entre pliegues | AUC fuera de pliegue | AUC en entrenamiento |")
        w("|---|---|---|---|---|")
        for r in res["ranking"]:
            w(f"| {NOMBRE[r['algoritmo']]} | {_n(r['cv_media'], 2)} | {_n(r['cv_desviacion'], 2)} | {_n(r['cv_auc_media'], 3)} | {_n(r['entrenamiento_media'], 3)} |")
        for r in res["referencias_cv"]:
            w(f"| {r['nombre']} | {_n(r['valor'], 2)} | {_n(r['desviacion'], 2)} | {_n(r.get('auc'), 3)} | — |")
        w("")
    else:
        w("No hay ranking: el script paró antes.")
        w("")
    w("## El ganador y por qué")
    w("")
    g = res.get("ganador") or {}
    if g.get("algoritmo"):
        w(f"Gana {NOMBRE[g['algoritmo']]}. {g['por_que']}")
        w("")
        w(f"Hiperparámetros: {json.dumps(g['hiperparametros'], ensure_ascii=False)}. El centro de datos {g['datacenter']}: {res['sitio']['por_que']}")
        w("")
        fr = res.get("frente_a_la_regla_cv") or {}
        if fr:
            w(f"Frente a la regla de los cinco contadores, pliegue a pliegue, {fr['veredicto']}: encuentra de media "
              f"{numero(fr['media'], 2)} fallos más por mes en la lista de 100, con una desviación entre pliegues de "
              f"{numero(fr['desviacion'], 2)}.")
        w("")
        w(f"Falta que Juan apruebe el ganador: aprobado_por está {'vacío' if not g.get('aprobado_por') else 'escrito: ' + g['aprobado_por']}.")
    else:
        w("No hay ganador: el script paró antes.")
    w("")
    w("## Qué variables pesan")
    w("")
    imp = res.get("importancias") or {}
    if imp.get("valores"):
        w(f"Importancia por permutación en el último bloque, con el modelo del pliegue 5, que no lo vio; métrica PR-AUC, "
          f"{REPETICIONES} repeticiones sobre el {numero(100 * MUESTRA_PERMUTACION)} % de las fotos del bloque, sorteado una vez "
          f"({numero(imp['filas_usadas'])} fotos, {numero(imp['fallos_usados'])} con fallo).")
        w("")
        for v in imp["valores"][:10]:
            w(f"- {v['columna']}: {numero(v['importancia'], 5)} (desviación {numero(v['desviacion'], 5)}).")
        w("")
        w("El peso de una variable dice que el modelo la usa para acertar, no que cause el fallo.")
    else:
        w("No se calculó: el script paró antes.")
    w("")
    w("## La validación")
    w("")
    v = res.get("validacion") or {}
    if v.get("abierta_una_vez"):
        i = v["intervalo"]
        w(f"La validación se abrió una vez, con el ganador aprobado por {g.get('aprobado_por')}. En sus 12 meses el modelo "
          f"encuentra de media {numero(i['media'], 2)} fallos más que la regla en la lista de 100, con un intervalo del "
          f"95 % de {numero(i['bajo'], 2)} a {numero(i['alto'], 2)}. Su AUC es {numero(v['medidas']['auc'], 3)}.")
    else:
        w("La validación sigue cerrada: se abre una sola vez, con el ganador aprobado (tercera parte).")
    w("")
    w("## El corte")
    w("")
    w("El modelo no lleva un corte fijo: da una lista de los discos de más riesgo de cada mes, y su tamaño lo elige "
      "Backblaze según lo que puedan atender sus técnicos, que no consta (reglas §7, CP-010). Por eso se dan las listas "
      "de 20, 100, 500 y 1.000. El tamaño se puede cambiar sin reentrenar.")
    w("")
    w("## ¿Se da por bueno?")
    w("")
    if v.get("abierta_una_vez"):
        w(("Sí" if v["se_da_por_bueno"] else "No") + f": frente a la regla, el intervalo va de {numero(v['intervalo']['bajo'], 2)} "
          f"a {numero(v['intervalo']['alto'], 2)}, y el AUC es {numero(v['medidas']['auc'], 3)} frente al mínimo de 0,70. "
          f"Frente al trivial, {v['frente_al_trivial']}.")
    else:
        w("No se sabe hasta abrir la validación. En la competición, " + (
            f"frente a la regla, {res['frente_a_la_regla_cv']['veredicto']}." if res.get("frente_a_la_regla_cv") else "no se llegó a medir."))
    w("")
    w("## Las tres vías de mejora")
    w("")
    vm = res.get("vias_de_mejora") or {}
    if vm:
        w(f"1. Mejor modelo: {vm['mejor_modelo']}")
        w("2. Crear variables con los datos que ya hay: " + "; ".join(f"{x['variable']}, {x['motivo']}" for x in vm["variables_nuevas"]) + ".")
        w("3. Pedir más información: " + "; ".join(f"{x['dato']}, {x['para_que']} (lo tiene {x['quien_lo_tiene']})" for x in vm["informacion_nueva"]) + ".")
    w("")
    w("## Validaciones")
    w("")
    for k, nombre in NOMBRES_VALIDACION.items():
        x = (res.get("validaciones") or {}).get(k)
        w(f"- {nombre[0].upper() + nombre[1:]}: " + ("no se calculó." if x is None else ("en verde." if x else "EN ROJO.")))
    w("")
    w("## Parámetros usados")
    w("")
    for p in res["parametros"]:
        w(f"- {p['nombre'][0].upper() + p['nombre'][1:]}: {p['valor']}. Origen: {p['origen']}.")
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
    for x in res["limites"]:
        w(f"- {x}")
    w("")
    return "\n".join(L)


def escribir(raiz, res):
    """Escribe el JSON (UTF-8, sin NaN) y el informe, del mismo diccionario."""
    (raiz / SALIDA_JSON).parent.mkdir(parents=True, exist_ok=True)
    (raiz / SALIDA_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, allow_nan=False, default=str), encoding="utf-8")
    (raiz / SALIDA_MD).write_text(informe(res), encoding="utf-8")


# =================================================================================================================
# 12. La competición (segunda parte)
# =================================================================================================================
def base(raiz):
    """El bloque común y lo fijo, antes de saber el resultado."""
    return {
        "skill": SKILL, "version_skill": version_skill(), "script": SCRIPT, "encargo": ENCARGO, "fecha_datos": FECHA_DATOS,
        "fecha_ejecucion": dt.datetime.now().replace(microsecond=0).isoformat(), "entradas": [],
        "resultado": {"estado": None, "riesgo": None, "resumen": None, "artefactos": [SALIDA_JSON, SALIDA_CSV, SALIDA_MD], "siguiente": None},
        "pendientes": [], "leidos": [], "rama": "si_no",
        "hace_falta_modelar": {"respuesta": True, "por_que": "la pregunta 4 pide ordenar cada disco por su riesgo (planteamientos, 2)"},
        "puerta_contestable": {"aplica": False, "por_que": "la decisión es sobre discos y no afecta a personas (planteamientos 1.C)"},
        "aprobado_antes": {"medida_principal": "los fallos encontrados entre los 100 discos de más riesgo de cada mes",
                           "por_que": "Es lo que mide el negocio: de los N discos de más riesgo, cuántos fallan (reglas §7).",
                           "referencias": ["la regla de los cinco contadores (CP-010)", "el trivial, DummyClassifier(strategy=\"prior\")"],
                           "se_da_por_bueno": "en la validación el modelo encuentra en esa lista más fallos que la regla, con el "
                                              "intervalo de la diferencia por encima de cero, y su AUC es 0,70 o más.",
                           "minimo_de_casos": 20, "fuente": "contexto-proyecto/metodo/04_planteamientos.md, 1.C"},
        "preseleccion_estado": None, "validacion_cruzada": None,
        "desequilibrio": {"regla": "equilibrado", "por_que": (
            "La regla del caso (reglas §7) entrena con todas las fotos con fallo y el 2 % de las sanas de cada mes, solo al "
            "ajustar cada pliegue; lo medido conserva la proporción real. La probabilidad del ganador se recalibra con la "
            "corrección del prior sobre el logit."), "metodo": "submuestreo de las sanas, semilla 42",
            "recalibracion": None},
        "busqueda": None, "ranking": [], "referencias_cv": [], "referencias_por_mes": None, "ganador": {"aprobado_por": ""},
        "frente_a_la_regla_cv": None, "sitio": None, "importancias": None, "canario": None, "ajuste_final": None,
        "validacion": {"abierta_una_vez": None, "pieza": PIEZA, "filas": None, "medidas": {}, "referencias": {},
                       "desarrollo_frente_a_validacion": {}, "intervalo": None, "se_da_por_bueno": None,
                       "frente_al_trivial": None, "errores_por_segmento": []},
        "corte": {"valor": None, "como": "capacidad", "filas_para_elegir": "fuera de pliegue", "valor_en_validacion": None,
                  "tipo_de_decision": "estrategica", "preferencia": None, "minimo": None, "escenarios": [],
                  "por_que": "el tamaño de la lista lo elige Backblaze según lo que puedan atender sus técnicos, que no consta "
                             "(reglas §7, CP-010): se dan las listas de 20, 100, 500 y 1.000", "se_puede_cambiar_sin_reentrenar": True},
        "vias_de_mejora": None,
        "validaciones": {k: None for k in VALIDACIONES} | {"intervalo_por_entidad": None},
        "validaciones_no_aplican": {"14": "no es una previsión de una serie", "15": "los pliegues van por fecha, no por entidad; el intervalo remuestrea meses"},
        "parametros": [
            {"nombre": "semilla", "valor": SEMILLA, "origen": "parametros.md de las dos skills"},
            {"nombre": "pliegues", "valor": "cinco bloques de tres meses, de 2023-04 a 2024-06, por fecha y sin barajar", "origen": "skill §3; encargo 21"},
            {"nombre": "muestra de cada entrenamiento", "valor": f"todas las fotos con fallo y el {numero(100 * FRACCION_SANAS)} % de las sanas de cada mes, solo con el horizonte cerrado", "origen": "reglas §7"},
            {"nombre": "medida de la búsqueda", "valor": "media de los fallos en la lista de 100 de los meses del bloque", "origen": "planteamientos 1.C; encargo 21"},
            {"nombre": "logística", "valor": "LogisticRegression(solver=\"lbfgs\", l1_ratio=0, max_iter=5000, random_state=42), C en logspace(-3, 2, 12)", "origen": "reglas §7, Juan, 18/11/2026"},
            {"nombre": "bosque", "valor": "RandomForestClassifier(n_jobs=-1, random_state=42), 15 candidatos de ParameterSampler(random_state=42)", "origen": "algoritmos.md; reglas §7"},
            {"nombre": "HistGradientBoosting", "valor": "early_stopping=False, max_iter en 100, 200 y 500, categóricas nativas, 15 candidatos", "origen": "algoritmos.md, con fecha; reglas §7"},
            {"nombre": "hoja", "valor": "max(20, 1 % de las filas que entrenan en el pliegue)", "origen": "parametros.md"},
            {"nombre": "ampliación por el borde", "valor": f"hasta {MAX_RONDAS} rondas; se queda el valor nuevo si mejora pliegue a pliegue", "origen": "skill §5"},
            {"nombre": "empate", "valor": "la media de las diferencias en los cinco pliegues no pasa de su desviación típica (con n − 1)", "origen": "skill §6"},
            {"nombre": "sitio", "valor": "datacenter entra solo si con él la lista de 100 encuentra más fallos en cada uno de los 12 meses de 2023-07 a 2024-06", "origen": "guion §3; encargo 21"},
            {"nombre": "permutación", "valor": f"{METRICA_PERMUTACION}, {REPETICIONES} repeticiones sobre el {numero(100 * MUESTRA_PERMUTACION)} % de las fotos del bloque 5, sorteado una vez con la semilla 42", "origen": "skill §7; parametros.md; la fracción, criterio del script por el tiempo"},
            {"nombre": "canario", "valor": f"barajado: como mucho el trivial más tres desviaciones de Poisson y un fallo; fuga: el {numero(100 * CANARIO_FUGA)} % de lo que cabe en la lista", "origen": "skill §9, validación 11; los márgenes, criterio del script"},
            {"nombre": "tolerancia de la probabilidad media", "valor": f"{numero(100 * TOLERANCIA_PROBABILIDAD)} % relativo", "origen": "encargo 21, validación 12"},
            {"nombre": "intervalo", "valor": f"{REMUESTREOS} remuestreos de los 12 meses, semilla 42, percentiles 2,5 y 97,5", "origen": "skill §8; encargo 21"},
        ],
        "teoria": TEORIA,
        "datos_personales": ("Los datos son de discos: serial_number identifica un disco, no a una persona (reglas §9), y el "
                             "modelo no lo lee. No usa ni deja ninguna columna de datos personales. "
                             + ("" if (raiz / PROTECCION).exists() else
                                f"No existe {PROTECCION}: los datos no pasaron por la protección porque no hacía falta.")),
        "limites": [
            "El modelo vale para los discos de datos de Backblaze, con una foto al mes, en los periodos de construcción y "
            "validación; si cambian los modelos de disco o los centros, su rendimiento puede caer (deriva).",
            "Detecta asociaciones, no causas: que un contador pese no dice que cause el fallo.",
            "No ve los fallos que llegan sin aviso en la última foto mensual (reglas §7).",
            "La preselección de la logística se hizo una vez y entra fija en cada pliegue: su validación cruzada sale algo "
            "optimista; cuánto, NO SE PUEDE SABER sin medirlo.",
            "Las cuatro variables nuevas candidatas de la matriz (P-04) no se crearon en este encargo.",
        ],
    }


def vias(res, ctx_busquedas):
    """Las tres vías de mejora, con lo que se probó y lo que queda (skill §8)."""
    probado = "; ".join(f"{NOMBRE[a]}, {len(b['candidatos'])} candidatos" for a, b in ctx_busquedas.items())
    return {"mejor_modelo": f"se probaron tres algoritmos con su búsqueda ({probado}); quedan sin probar XGBoost y los "
                            "castigos L1 y mezcla de la logística, que Juan dejó fuera (reglas §7).",
            "variables_nuevas": [{"variable": "las cuatro variables nuevas candidatas de la matriz (P-04)", "probada": False,
                                  "motivo": "no se crean en este encargo; se crean si el modelo no supera a la regla, con la "
                                            "decisión de Juan y antes de abrir la validación (reglas §7)"}],
            "informacion_nueva": [{"dato": "las lecturas SMART diarias, no solo la foto mensual",
                                   "para_que": "ver los fallos que avisan entre una foto y la siguiente", "quien_lo_tiene": "Backblaze"}]}


def competicion(raiz, res, n_candidatos):
    """La segunda parte entera. Devuelve el código de salida."""
    t_inicio = time.time()
    # 12.1 La preselección (paso 1, con la segunda nota)
    if not (raiz / PRESELECCION).exists():
        raise Parada(f"falta {PRESELECCION}", "PARADO")
    pres = json.loads((raiz / PRESELECCION).read_text(encoding="utf-8"))
    res["leidos"].append(PRESELECCION)
    ok, motivo = preseleccion_lista(pres)
    res["preseleccion_estado"] = motivo
    res["entradas"].append({"ruta": PRESELECCION, "estado": (pres.get("resultado") or {}).get("estado"), "motivo": motivo})
    if not ok:
        raise Parada(f"{PRESELECCION} {motivo}", "PARADO")
    mz = P13.leer_matriz((raiz / MATRIZ).read_text(encoding="utf-8"))
    res["leidos"].append(MATRIZ)
    if not mz["aprobada_por"]:
        raise Parada("la matriz no está aprobada", "PARADO")
    ruta = raiz / ENTRENAMIENTO
    huella = sha256(ruta)
    esperada = next((e.get("sha256") for e in pres.get("entradas", []) if e.get("ruta") == ENTRENAMIENTO), None)
    res["entradas"].append({"ruta": ENTRENAMIENTO, "sha256": huella, "filas": pq.ParquetFile(ruta).metadata.num_rows})
    if huella != esperada:
        raise Parada(f"la huella de {ENTRENAMIENTO} no es la de {PRESELECCION}", "PARADO")
    finales = pres["familias"]["logistica"]["variables_finales"]
    entradas = {"logistica": finales, "bosque": pres["familias"]["bosque"]["columnas_finales"],
                "hgb": pres["familias"]["hgb"]["columnas_finales"]}
    datos = Datos(ruta)
    res["leidos"].append(ENTRENAMIENTO)
    ctx = Contexto(datos, finales, patrones_logistica(mz))
    # 12.2 Los pliegues, la regla y el trivial en las mismas fotos
    detalle, sin_conocer = [], []
    reglas, triviales, mes_regla, mes_trivial = [], [], [], []
    for f, (a, b) in enumerate(BLOQUES):
        _, y, c = ctx.entrenamiento(f)
        triv = DummyClassifier(strategy="prior").fit(np.zeros((len(y), 1)), y)
        p_triv = float(triv.predict_proba(np.zeros((1, 1)))[0, 1])
        r_f, t_f, filas, fallos = [], [], 0, 0
        for mes in ctx.meses_bloque(f):
            dm = datos.mes(mes)
            ym = dm[OBJETIVO].to_numpy().astype(int)
            k = claves_regla(dm)
            r = medidas_mes(ym, k, rango_denso(k)); r["mes"] = mes.date().isoformat()
            pt = np.full(len(ym), p_triv)
            t = medidas_mes(ym, [pt], pt); t["mes"] = mes.date().isoformat()
            r_f.append(r); t_f.append(t)
            filas += len(ym); fallos += int(ym.sum())
        mes_regla += r_f; mes_trivial += t_f
        reglas.append(float(np.mean([r["lista_100"] for r in r_f])))
        triviales.append(float(np.mean([t["lista_100"] for t in t_f])))
        detalle.append({"bloque": f + 1, "desde": a, "hasta": b, "filas_mide": filas, "fallos_mide": fallos,
                        "filas_entrena": c["filas_entrena"], "fallos_entrena": c["fallos_entrena"],
                        "filas_quitadas": c["filas_quitadas"], "fallos_quitados": c["fallos_quitados"], "muestra": c["muestra"],
                        "hoja": c["hoja"], "tasa_muestra": c["tasa_muestra"], "tasa_real": c["tasa_real"],
                        "horizonte_max": c["horizonte_max"], "horizonte_cerrado": c["horizonte_cerrado"],
                        "fallos_por_pliegue_minimo": 20})
        sin_conocer.append({"entrenamiento": f"pliegue que mide {a}", "conocido_desde": a, "filas_quitadas": c["filas_quitadas"],
                            "eventos_quitados": c["fallos_quitados"]})
    if any(d["fallos_mide"] < 20 or d["fallos_entrena"] < 20 for d in detalle):
        raise Parada("un pliegue no llega a 20 fallos (parametros.md)", "PARADO")
    reglas, triviales = np.array(reglas), np.array(triviales)
    res["referencias_por_mes"] = {"regla": mes_regla, "trivial": mes_trivial, "filas": "fuera de pliegue"}
    # 12.3 Una búsqueda por algoritmo
    t_busqueda = time.time()
    busquedas = {fam: buscar(fam, ctx, n_candidatos) for fam in FAMILIAS}
    filas_csv, ranking, cv_mejor = [], [], {}
    for fam, bq in busquedas.items():
        medias = [cv(r).mean() for r in bq["resultados"]]
        puesto = {j: i + 1 for i, j in enumerate(sorted(range(len(medias)), key=lambda j: -medias[j]))}
        for j, (c, r) in enumerate(zip(bq["candidatos"], bq["resultados"])):
            filas_csv.append({"algoritmo": fam, "hiperparametros": json.dumps(c, ensure_ascii=False), "ronda": bq["rondas"][j],
                              "cv_media": float(cv(r).mean()), "cv_desviacion": float(cv(r).std(ddof=1)),
                              "entrenamiento_media": float(np.mean([r[f]["auc_entrenamiento"] for f in r])),
                              "cv_auc_media": float(np.mean([m["auc"] for f in r for m in r[f]["meses"] if m["auc"] is not None])),
                              "posicion": puesto[j]})
        r = bq["resultados"][bq["mejor"]]
        cv_mejor[fam] = cv(r)
        ranking.append({"algoritmo": fam, "hiperparametros": bq["candidatos"][bq["mejor"]], "cv_media": float(cv(r).mean()),
                        "cv_desviacion": float(cv(r).std(ddof=1)), "cv_por_pliegue": [float(x) for x in cv(r)],
                        "listas": {str(n): float(np.mean([m[f"lista_{n}"] for f in r for m in r[f]["meses"]])) for n in LISTAS},
                        "cv_auc_media": float(np.mean([m["auc"] for f in r for m in r[f]["meses"] if m["auc"] is not None])),
                        "cv_pr_auc_media": float(np.mean([m["pr_auc"] for f in r for m in r[f]["meses"] if m["pr_auc"] is not None])),
                        "filas": "fuera de pliegue", "entrenamiento_media": float(np.mean([r[f]["auc_entrenamiento"] for f in r])),
                        "entrenamiento_medida": "AUC en las filas del ajuste de cada pliegue", "filas_entrenamiento": "entrenamiento"})
    escribir_csv(raiz, filas_csv)
    res["ranking"] = sorted(ranking, key=lambda r: -r["cv_media"])
    res["referencias_cv"] = [
        {"nombre": "regla de los cinco contadores", "valor": float(reglas.mean()), "desviacion": float(reglas.std(ddof=1)),
         "por_pliegue": [float(x) for x in reglas], "auc": float(np.mean([m["auc"] for m in mes_regla if m["auc"] is not None])),
         "filas": "fuera de pliegue"},
        {"nombre": "trivial", "valor": float(triviales.mean()), "desviacion": float(triviales.std(ddof=1)),
         "por_pliegue": [float(x) for x in triviales], "auc": 0.5, "filas": "fuera de pliegue"}]
    total = {fam: int(np.prod([len(v) for v in ESPACIOS[fam].values()])) for fam in FAMILIAS}
    res["busqueda"] = {"nivel": "equilibrado", "tipo": "rejilla en la logística; aleatoria en el bosque y el HistGradientBoosting",
                       "como": ("Cada búsqueda usa ParameterGrid o ParameterSampler de scikit-learn y los cinco pliegues por "
                                "fecha, y puntúa cada bloque por trozos; no usa RandomizedSearchCV porque la muestra se toma "
                                "solo en la parte que entrena de cada pliegue y el bloque medido no cabe en memoria transformado."),
                       "modelos_estimados": int(sum(len(b["candidatos"]) for b in busquedas.values()) * len(BLOQUES)),
                       "medida": "media de los fallos en la lista de 100 de los meses del bloque", "tabla": SALIDA_CSV,
                       "rejillas_ampliadas": [x for b in busquedas.values() for x in b["ampliadas"]],
                       "espacio": [{"algoritmo": fam, "combinaciones": total[fam], "probadas": len(busquedas[fam]["candidatos"])} for fam in FAMILIAS],
                       "segundas_busquedas": [x for b in busquedas.values() for x in b["segundas"]]}
    res["ejecucion_parcial"] = {"segundos_busqueda": round(time.time() - t_busqueda, 1)}
    # 12.4 El ganador, pliegue a pliegue, y frente a la regla
    ganador, por_que = elegir_ganador(cv_mejor, triviales)
    bq = busquedas[ganador]
    receta = bq["candidatos"][bq["mejor"]]
    r_gan = bq["resultados"][bq["mejor"]]
    e_regla = empate(cv_mejor[ganador], reglas)
    res["frente_a_la_regla_cv"] = {"veredicto": veredicto(cv_mejor[ganador], reglas), **e_regla, "filas": "fuera de pliegue"}
    # 12.5 El sitio: con y sin datacenter en los 12 meses que lo tienen
    pliegues_sitio = [f for f in range(len(BLOQUES)) if pd.Timestamp(BLOQUES[f][0]) >= pd.Timestamp(SITIO_DESDE)]
    sin = evaluar(ganador, [receta], ctx, pliegues=pliegues_sitio, sitio=False)[0]
    con_m = [m["lista_100"] for f in pliegues_sitio for m in r_gan[f]["meses"]]
    sin_m = [m["lista_100"] for f in pliegues_sitio for m in sin[f]["meses"]]
    entra = bool(len(con_m) > 0 and all(a > b for a, b in zip(con_m, sin_m)))
    res["sitio"] = {"meses": len(con_m), "con": con_m, "sin": sin_m, "entra": entra, "filas": "fuera de pliegue",
                    "por_que": ("con él encuentra más fallos en la lista de 100 en cada uno de los "
                                f"{len(con_m)} meses con sitio, así que entra." if entra else
                                f"con él no encuentra más fallos en los {len(con_m)} meses con sitio, así que se vacía.")}
    sitio = entra
    if not sitio:
        r_final = {**r_gan, **sin}
    else:
        r_final = r_gan
    # 12.6 El reajuste con toda la construcción, recalibrado
    df_fin, y_fin, c_fin = datos.muestra(INICIO_VALIDACION)
    pre_fin, mod_fin, auc_fin, _ = ajustar(ganador, [receta], df_fin, y_fin, c_fin["hoja"], ctx, sitio=sitio)
    sin_conocer.append({"entrenamiento": "ajuste final", "conocido_desde": INICIO_VALIDACION,
                        "filas_quitadas": c_fin["filas_quitadas"], "eventos_quitados": c_fin["fallos_quitados"]})
    res["ajuste_final"] = {"filas_entrena": c_fin["filas_entrena"], "fallos_entrena": c_fin["fallos_entrena"],
                           "muestra": c_fin["muestra"], "hoja": c_fin["hoja"], "auc_entrenamiento": auc_fin[0],
                           "filas": "entrenamiento", "horizonte_max": c_fin["horizonte_max"]}
    res["desequilibrio"]["recalibracion"] = {"metodo": "corrección del prior sobre el logit (desequilibrio.md, «Recalibrar»)",
                                             "tasa_muestra": c_fin["tasa_muestra"], "tasa_real": c_fin["tasa_real"]}
    res["validacion_cruzada"] = {"tipo": "por fecha, bloques de tres meses, sin barajar", "pliegues": len(BLOQUES),
                                 "semilla": SEMILLA, "grupo": None, "test_size": None, "gap": None,
                                 "objetivo_sin_conocer": sin_conocer, "pliegues_detalle": detalle}
    # 12.7 El modelo del pliegue 5: reproducible, importancia por permutación y canario
    f5 = len(BLOQUES) - 1
    df5, y5, c5 = ctx.entrenamiento(f5)
    pre5, mod5, _, cols5 = ajustar(ganador, [receta], df5, y5, c5["hoja"], ctx, sitio=sitio)
    bloque = pd.concat([datos.mes(m) for m in ctx.meses_bloque(f5)], ignore_index=True)
    yb = bloque[OBJETIVO].to_numpy().astype(int)
    p5 = puntuar(pre5, mod5, bloque, ganador, ctx, sitio=sitio)[0]
    repetido = []
    for mes in ctx.meses_bloque(f5):
        s = (bloque[FECHA] == mes).to_numpy()
        repetido.append(fallos_en_lista([p5[s]], yb[s], LISTA))
    original = [m["lista_100"] for m in r_final[f5]["meses"]]
    reproducible = bool(np.allclose(repetido, original, rtol=0, atol=1e-9))
    variables = [v for v in (finales if ganador == "logistica" else entradas[ganador]) if sitio or v != "datacenter"]
    entrada_familia = (P13.NUM_LOGISTICA + P13.NOMINALES) if ganador == "logistica" else (P13.NUM_ARBOLES + P13.NOMINALES)
    # Un trozo fijo del bloque, sorteado una vez con la semilla: la puntuación de partida y las permutadas se miden en
    # las mismas filas (con max_samples, scikit-learn mide la de partida en todas y las permutadas en una parte)
    filas_pi = np.sort(np.random.default_rng(SEMILLA).choice(len(bloque), size=int(np.floor(MUESTRA_PERMUTACION * len(bloque) + 0.5)), replace=False))
    sub = bloque.iloc[filas_pi]
    resto = sub[[c for c in sub.columns if c not in variables]]
    envoltorio = ConElResto(pre5, mod5[0], resto, ganador, ctx, sitio)
    t0 = time.time()
    pi = permutation_importance(envoltorio, sub[variables], yb[filas_pi], scoring=METRICA_PERMUTACION, n_repeats=REPETICIONES,
                                random_state=SEMILLA, n_jobs=1)
    res["importancias"] = {"metodo": "permutacion", "filas": "fuera de pliegue: el bloque 5, con el modelo del pliegue 5",
                           "metrica": METRICA_PERMUTACION, "repeticiones": REPETICIONES, "fraccion_del_bloque": MUESTRA_PERMUTACION,
                           "filas_usadas": int(len(filas_pi)), "fallos_usados": int(yb[filas_pi].sum()),
                           "segundos": round(time.time() - t0, 1),
                           "valores": sorted([{"columna": v, "importancia": float(m), "desviacion": float(s)}
                                              for v, m, s in zip(variables, pi.importances_mean, pi.importances_std)],
                                             key=lambda x: -x["importancia"])}
    # El canario en sus dos sentidos, con el entrenamiento del pliegue 5
    barajado = np.random.default_rng(SEMILLA).permutation(y5)
    preb, modb, _, _ = ajustar(ganador, [receta], df5, y5, c5["hoja"], ctx, sitio=sitio, y_ajuste=barajado)
    pb = puntuar(preb, modb, bloque, ganador, ctx, sitio=sitio)[0]
    prf, modf, _, _ = ajustar(ganador, [receta], df5, y5, c5["hoja"], ctx, sitio=sitio, fuga=True)
    pf_ = puntuar(prf, modf, bloque, ganador, ctx, sitio=sitio, fuga=True)[0]
    lb, lf, lt, techo = [], [], [], []
    for mes in ctx.meses_bloque(f5):
        s = (bloque[FECHA] == mes).to_numpy()
        lb.append(fallos_en_lista([pb[s]], yb[s], LISTA)); lf.append(fallos_en_lista([pf_[s]], yb[s], LISTA))
        lt.append(LISTA * yb[s].mean()); techo.append(min(LISTA, int(yb[s].sum())))
    res["canario"] = {"barajado": {"lista_100": float(np.mean(lb)), "filas": "bloque 5"},
                      "fuga": {"lista_100": float(np.mean(lf)), "filas": "bloque 5"},
                      "trivial_lista_100": float(np.mean(lt)), "techo_lista_100": float(np.mean(techo))}
    # 12.8 Lo que queda del ganador
    res["ganador"] = {"algoritmo": ganador, "ficha": f"assets/fichas_de_algoritmos/{FICHAS[ganador]}/01_ficha.md",
                      "hiperparametros": receta, "semilla": SEMILLA, "columnas": variables,
                      "columnas_que_lee_el_preprocesador": entrada_familia,
                      "columnas_tras_el_preprocesador_pliegue_5": len(cols5),
                      "datacenter": "entra" if sitio else "se vacía (sin sitio)",
                      "por_que": (f"Tiene la mejor media en la lista de 100 fuera de pliegue ({numero(cv_mejor[ganador].mean(), 2)} "
                                  "fallos por mes)" if por_que["mejor_media"] == ganador else
                                  "Empata pliegue a pliegue con el de mejor media y es el más estable frente al trivial")
                                 + "; la comparación pliegue a pliegue con los otros va en «ganador_detalle».",
                      "muestra": "todas las fotos con fallo y el 2 % de las sanas de cada mes, semilla 42",
                      "recalibracion": res["desequilibrio"]["recalibracion"], "aprobado_por": ""}
    res["ganador_detalle"] = por_que
    res["vias_de_mejora"] = vias(res, busquedas)
    # 12.9 Las validaciones del skill §9, calculadas
    prob_bloques = []
    for f in range(len(BLOQUES)):
        _, _, c = ctx.entrenamiento(f)
        meses = r_final[f]["meses"]
        filas = sum(m["filas"] for m in meses)
        media = sum(m["prob_media_recalibrada"] * m["filas"] for m in meses) / filas
        tasa = sum(m["fallos"] for m in meses) / filas
        prob_bloques.append({"bloque": f + 1, "probabilidad_media": media, "tasa_real": tasa, "cerca": v_prob_media(media, tasa)})
    res["probabilidad_media_por_bloque"] = prob_bloques
    escribir_csv(raiz, filas_csv)
    citas = [PRESELECCION, res["ganador"]["ficha"], SALIDA_CSV, PIEZA]
    prohibidas = set(P13.FUERA) | set(P13.NO_ENTRAN) | {OBJETIVO, HORIZONTE}
    if ganador == "logistica":
        usadas = {v for v in finales if columnas_de(cols5, [v], ctx.patrones)}
        cols_ok = usadas <= set(finales) and all(v in finales for v in variables)
    else:
        cols_ok = sorted(entradas[ganador]) == sorted(entrada_familia)
    texto = Path(__file__).read_text(encoding="utf-8")
    res["validaciones"].update({
        "sin_filas_de_ajuste": filas_etiquetadas(res),
        "semillas": ctx.semillas == {SEMILLA},
        "validacion_una_vez": VALIDACION not in res["leidos"],
        "con_probabilidad": bool(len(np.unique(p5)) > 2 and p5.min() >= 0 and p5.max() <= 1),
        "columnas_de_preseleccion": bool(cols_ok),
        "recalibrado_si_hace_falta": bool(c_fin["tasa_muestra"] > c_fin["tasa_real"] and res["desequilibrio"]["recalibracion"]),
        "citas_existen": all((raiz / c).exists() or (CASO / c).exists() for c in citas),
        "reproducible": reproducible,
        "sin_identificadores_ni_posteriores": not (set(variables) & prohibidas),
        "sin_resultados_escritos": escritos_en_codigo(texto) == [],
        "canario_objetivo_barajado": v_canario(res["canario"]["barajado"]["lista_100"], res["canario"]["trivial_lista_100"],
                                               res["canario"]["fuga"]["lista_100"], res["canario"]["techo_lista_100"]),
        "probabilidad_media_cerca_de_la_tasa": all(b["cerca"] for b in prob_bloques),
        "objetivo_conocido_al_entrenar": all(d["horizonte_cerrado"] for d in detalle) and bool(c_fin["horizonte_cerrado"]),
    })
    # Las columnas sin ningún dato en las filas de algún ajuste, que salieron de ese ajuste (una entrada por ajuste)
    res["columnas_sin_dato_al_ajustar"] = ctx.columnas_vacias
    res["ejecucion_parcial"]["segundos_competicion"] = round(time.time() - t_inicio, 1)
    rojas = [k for k in VALIDACIONES if res["validaciones"][k] is False and k != "probabilidad_media_cerca_de_la_tasa"]
    if rojas:
        raise Parada("validaciones en rojo: " + ", ".join(rojas))
    if not res["validaciones"]["probabilidad_media_cerca_de_la_tasa"]:
        lejos = [b["bloque"] for b in prob_bloques if not b["cerca"]]
        raise Parada(f"la probabilidad media recalibrada se aparta más de un 20 % de la tasa real en los bloques {lejos}", "PARADO")
    # 12.10 La puerta: el ganador frente a la regla y la aprobación de Juan
    vr = res["frente_a_la_regla_cv"]
    if vr["veredicto"] != "supera":
        resumen = (f"El ganador, {NOMBRE[ganador]}, {'no supera' if vr['veredicto'] == 'no supera' else 'no se puede afirmar que supere'} "
                   f"a la regla de los cinco contadores pliegue a pliegue ({numero(vr['media'], 2)} fallos de diferencia media en la "
                   f"lista de 100, desviación {numero(vr['desviacion'], 2)}). Para en la puerta 4: Juan decide si se crean las cuatro "
                   "variables nuevas; las tres vías de mejora van en el informe.")
        siguiente = "decisión de Juan sobre las variables nuevas (reglas §7), antes de abrir la validación"
    else:
        resumen = (f"Gana {NOMBRE[ganador]}, que supera a la regla pliegue a pliegue: {numero(vr['media'], 2)} fallos más de media en "
                   f"la lista de 100 de cada mes. Para antes de abrir la validación: falta que Juan apruebe el ganador.")
        siguiente = "Juan aprueba el ganador; se escribe ganador.aprobado_por y se ejecuta con --abrir-validacion"
    res["resultado"] = {"estado": "PARADO", "riesgo": "medio", "resumen": resumen,
                        "artefactos": [SALIDA_JSON, SALIDA_CSV, SALIDA_MD], "siguiente": siguiente}
    return 0


# =================================================================================================================
# 13. La validación, una vez (tercera parte)
# =================================================================================================================
def abrir_validacion(raiz, res):
    """La tercera parte: con el ganador aprobado y la validación sin abrir, la mide una vez. Devuelve el código."""
    import evaluacion_binaria as eb  # pieza común de assets/, solo hace falta aquí
    g = res.get("ganador") or {}
    if not g.get("aprobado_por"):
        raise Parada("ganador.aprobado_por está vacío: la validación no se abre sin el sí de Juan", "PARADO")
    if (res.get("validacion") or {}).get("abierta_una_vez"):
        raise Parada("la validación ya se abrió una vez: no se vuelve a abrir", "PARADO")
    pres = json.loads((raiz / PRESELECCION).read_text(encoding="utf-8"))
    ok, motivo = preseleccion_lista(pres)
    if not ok:
        raise Parada(f"{PRESELECCION} {motivo}", "PARADO")
    mz = P13.leer_matriz((raiz / MATRIZ).read_text(encoding="utf-8"))
    finales = pres["familias"]["logistica"]["variables_finales"]
    datos = Datos(raiz / ENTRENAMIENTO)
    ctx = Contexto(datos, finales, patrones_logistica(mz))
    fam, receta, sitio = g["algoritmo"], g["hiperparametros"], g["datacenter"] == "entra"
    # 13.1 El reajuste con construcción, la misma receta, y su recalibración
    df_fin, y_fin, c_fin = datos.muestra(INICIO_VALIDACION)
    pre, mods, _, _ = ajustar(fam, [receta], df_fin, y_fin, c_fin["hoja"], ctx, sitio=sitio)
    p_des = recalibrar(puntuar(pre, mods, df_fin, fam, ctx, sitio=sitio)[0], c_fin["tasa_muestra"], c_fin["tasa_real"])
    p_triv = c_fin["tasa_real"]
    # 13.2 La validación mes a mes: el ganador, la regla y el trivial en las mismas fotos
    val = Datos(raiz / VALIDACION)
    res["leidos"].append(VALIDACION)
    por_mes, ys, ps, ks = [], [], [], [[], []]
    for mes in val.meses:
        dm = val.mes(mes)
        ym = dm[OBJETIVO].to_numpy().astype(int)
        p = recalibrar(puntuar(pre, mods, dm, fam, ctx, sitio=sitio)[0], c_fin["tasa_muestra"], c_fin["tasa_real"])
        k = claves_regla(dm)
        fila = {"mes": mes.date().isoformat(), "filas": int(len(ym)), "fallos": int(ym.sum())}
        for n in LISTAS:
            fila[f"modelo_lista_{n}"] = fallos_en_lista([p], ym, n)
            fila[f"regla_lista_{n}"] = fallos_en_lista(k, ym, n)
            fila[f"trivial_lista_{n}"] = n * float(ym.mean())
        por_mes.append(fila)
        ys.append(ym); ps.append(p); ks[0].append(k[0]); ks[1].append(k[1])
    y_all, p_all = np.concatenate(ys), np.concatenate(ps)
    rr = rango_denso([np.concatenate(ks[0]), np.concatenate(ks[1])])
    regla_p = (rr + 1) / (rr.max() + 2)
    dif_regla = [m["modelo_lista_100"] - m["regla_lista_100"] for m in por_mes]
    dif_triv = [m["modelo_lista_100"] - m["trivial_lista_100"] for m in por_mes]
    i_regla, i_triv = intervalo_meses(dif_regla), intervalo_meses(dif_triv)
    medidas = eb.medidas_globales(y_all, p_all)
    bueno = bool(i_regla["media"] > 0 and i_regla["bajo"] > 0 and medidas["auc"] >= 0.70)
    res["validacion"] = {
        "abierta_una_vez": True, "pieza": PIEZA, "filas": int(len(y_all)), "medidas": medidas,
        "referencias": {"regla": eb.medidas_globales(y_all, regla_p), "trivial": eb.medidas_globales(y_all, np.full(len(y_all), p_triv))},
        "desarrollo_frente_a_validacion": eb.desarrollo_frente_a_validacion(y_fin, p_des, y_all, p_all).to_dict(orient="index"),
        "desarrollo_filas": "desarrollo: la muestra del reajuste final; validación: todas sus fotos",
        "calibracion": eb.calibracion(y_all, p_all).to_dict(orient="records"),
        "por_mes": por_mes, "intervalo": i_regla, "intervalo_frente_al_trivial": i_triv,
        "se_da_por_bueno": bueno,
        "frente_al_trivial": "supera" if i_triv["bajo"] > 0 else ("no supera" if i_triv["alto"] < 0 else "no se puede afirmar"),
        "frente_a_la_regla": "supera" if i_regla["bajo"] > 0 else ("no supera" if i_regla["alto"] < 0 else "no se puede afirmar"),
        "filas_de_cada_cifra": "validacion", "errores_por_segmento": []}
    res["validaciones"]["validacion_una_vez"] = res["leidos"].count(VALIDACION) == 1
    res["resultado"] = {"estado": "OK", "riesgo": "bajo" if bueno else "medio",
                        "resumen": (f"La validación, abierta una vez, {'da' if bueno else 'no da'} por bueno el modelo: en la lista de 100 "
                                    f"encuentra de media {numero(i_regla['media'], 2)} fallos más que la regla por mes (intervalo "
                                    f"{numero(i_regla['bajo'], 2)} a {numero(i_regla['alto'], 2)}) y su AUC es {numero(medidas['auc'], 3)}."),
                        "artefactos": [SALIDA_JSON, SALIDA_CSV, SALIDA_MD],
                        "siguiente": "preproduccion, con la receta del ganador" if bueno else "las tres vías de mejora, con Juan"}
    return 0


# =================================================================================================================
# 14. Principal
# =================================================================================================================
def principal(raiz, abrir, n_candidatos):
    """La segunda parte, o la tercera con --abrir-validacion. Devuelve el código de salida."""
    inicio = time.time()
    previo = None
    if abrir and (raiz / SALIDA_JSON).exists():
        previo = json.loads((raiz / SALIDA_JSON).read_text(encoding="utf-8"))
        res = copy.deepcopy(previo)
        res["leidos"] = [r for r in res.get("leidos", []) if r != VALIDACION] + ([VALIDACION] if (res.get("validacion") or {}).get("abierta_una_vez") else [])
    else:
        res = base(raiz)
    try:
        if abrir:
            if previo is None:
                raise Parada(f"falta {SALIDA_JSON}: primero la competición", "PARADO")
            codigo = abrir_validacion(raiz, res)
        else:
            codigo = competicion(raiz, res, n_candidatos)
    except Parada as p:
        if abrir and previo is not None:
            res = copy.deepcopy(previo)
        res["resultado"] = {"estado": p.estado, "riesgo": "alto", "resumen": f"El script paró: {p}"[:2000],
                            "artefactos": [SALIDA_JSON, SALIDA_CSV, SALIDA_MD], "siguiente": "resolver la causa y volver a ejecutar"}
        codigo = p.codigo
    except Exception as e:  # noqa: BLE001 - el JSON se escribe también cuando falla (bloque común, regla 5)
        if abrir and previo is not None:
            res = copy.deepcopy(previo)
        res["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(e).__name__}: {e}"[:2000],
                            "artefactos": [SALIDA_JSON, SALIDA_CSV, SALIDA_MD], "siguiente": "corregir el fallo y volver a ejecutar"}
        res["traza"] = traceback.format_exc()[-3000:]
        codigo = 1
    res["ejecucion"] = {**res.get("ejecucion_parcial", {}), "python": platform.python_version(), "ejecutable": sys.executable,
                        "pandas": pd.__version__, "pyarrow": pa.__version__, "scikit_learn": sklearn.__version__,
                        "segundos": round(time.time() - inicio, 1)}
    escribir(raiz, res)
    print(f"{res['resultado']['estado']}: {res['resultado']['resumen']}")
    return codigo


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso (por defecto, la del script)")
    argumentos.add_argument("--abrir-validacion", action="store_true", help="tercera parte: abre la validación una vez")
    argumentos.add_argument("--candidatos", type=int, default=CANDIDATOS, help="candidatos por búsqueda (solo la prueba lo baja)")
    a = argumentos.parse_args()
    sys.exit(principal(Path(a.raiz).resolve(), a.abrir_validacion, a.candidatos))
