"""Preselección de variables del modelo del caso 68 (método preseleccion-variables; petición 21, primera parte).

Solo la regresión logística se preselecciona por votación (reglas, apartado 7, 18/11/2026): modo comparativo, con información
mutua, eliminación recursiva con validación cruzada (RFECV) e importancia por permutación, y escenario de consenso
amplio (entra una variable si la marcan dos o más métodos). smart_5_raw, smart_187_raw, smart_197_raw y smart_198_raw
entran siempre, sin votar. El bosque y el HistGradientBoosting no se preseleccionan: reciben las 64 columnas de la
matriz.

La unidad de voto es la variable de origen de la matriz (columnas «variable» y «salida»): una variable recibe el voto
de un método si alguna de sus columnas pasa el corte de ese método, y entra o sale con todas sus columnas. El JSON
guarda, para la logística, las variables finales y, solo para orientar, los nombres de columna del ajuste con la
muestra: los tramos se aprenden en cada ajuste, así que los nombres cambian de un pliegue a otro. El preprocesador se
monta siempre entero, con la matriz; la selección se aplica después, quedándose con las columnas de salida cuyo origen
está entre las variables finales. Así fabricante sigue leyéndose como clave de los tramos de smart_1_raw y smart_7_raw
aunque pierda la votación (nota de la petición 21, punto 2).

Todo se calcula sobre una muestra de entrenamiento: todas las fotos con fallo y el 2 % de las sanas de cada mes, con
semilla 42, como el script 13, y de ella los meses más recientes hasta pasar de 100.000 filas, enteros. Una segunda
muestra igual con semilla 43 comprueba la lista final: si cambia, se dobla el tamaño y se repite; si al doblar ya no
cabe, se usa la muestra de partida entera.

Importa scripts/13_preparacion.py con importlib para montar el preprocesador de la logística (nota de la petición 21,
punto 1): su trabajo está dentro de `if __name__ == "__main__":` y al importarlo solo define las piezas. No importa
ningún otro script. No abre la validación.

Depende de scripts/13_preparacion.py: lee informes/preparacion.json y para (PARADO) si no está en OK, si la huella de
entrenamiento no es la que dejó o si la matriz no está aprobada.

Deja informes/preseleccion.json y, generado del mismo diccionario, informes/preseleccion.md.

Uso: python -W error scripts/14_preseleccion.py [--raiz CARPETA_DEL_CASO]
Sale con 0 si termina, con 2 si para (PARADO o ERROR) y con 1 si falla por otra causa; en los tres casos escribe el JSON.
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
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
from scipy.stats.contingency import association
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_selection import RFECV, mutual_info_classif
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

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
METODO = "preseleccion-variables"
METODO_MD = CASO / "metodos" / "preseleccion-variables" / "METODO.md"
SCRIPT = "scripts/14_preseleccion.py"
PETICION = "peticiones/21_preseleccion_competicion_y_ganador.md, primera parte, con la nota de respuestas"
FECHA_DATOS = "2025-06-30"                                   # reglas, apartado 5, fecha de referencia
PREPARACION = "informes/preparacion.json"
MATRIZ = "config/modelo/matriz_transformaciones.md"
ENTRENAMIENTO = "data/processed/fotos_riesgo_entrenamiento.parquet"
PROTECCION = "config/fuentes/proteccion-datos.json"
SALIDA_JSON = "informes/preseleccion.json"
SALIDA_MD = "informes/preseleccion.md"
OBJETIVO, FECHA, HORIZONTE = "falla_30d", "fecha", "horizonte_hasta"
LEER = P13.NOMINALES + P13.NUM_ARBOLES + [OBJETIVO, FECHA, HORIZONTE]
ENTRADA_LOGISTICA = P13.NUM_LOGISTICA + P13.NOMINALES          # las 62 variables de origen de la logística
ENTRADA_ARBOLES = P13.NUM_ARBOLES + P13.NOMINALES              # las 64 columnas de los árboles

# La muestra (reglas, apartado 7; parametros.md, «filas para muestrear»)
SEMILLA, SEMILLA_2 = 42, 43
FRACCION_SANAS = P13.FRACCION_SANAS
FILAS_MUESTRA = 100_000
# La votación y lo que entra siempre (reglas, apartado 7, 18/11/2026)
ESCENARIO, VOTOS_MINIMOS = "consenso amplio", 2
OBLIGATORIAS = ["smart_5_raw", "smart_187_raw", "smart_197_raw", "smart_198_raw"]
# Los métodos (parametros.md; petición 21; nota de respuestas, punto 3)
METRICA = "average_precision"
RFE_ARBOLES, RFE_PROFUNDIDAD, RFE_PLIEGUES, RFE_PASO, RFE_MINIMO = 100, 5, 3, 0.05, 1
RESERVA, REPETICIONES = 0.20, 10
# Las que dicen lo mismo, la fuga y el tope
UMBRAL_PARECIDO = 0.5                                        # Spearman y V de Cramér (parametros.md)
UMBRAL_FUGA = 0.90                                           # |2·AUC − 1|, el UMBRAL_FUGA del exploratorio del caso
CASOS_POR_COLUMNA = 10                                       # tope de la logística (método §7)
TROZO = 50_000                                               # filas por trozo al transformar

TEORIA = [
    "36.2 y 36.3: la selección aprende de los datos, así que se hace solo con entrenamiento y sobre una muestra, porque "
    "detectar qué variables predicen pide menos filas que ajustar el modelo final.",
    "36.5: información mutua con semilla y la máscara de discretas, porque todas las columnas de la logística son 0 y 1.",
    "36.6: RFECV con un bosque, que expone importancias, y pliegues por fecha; el paso del 5 % porque con cientos de "
    "columnas quitar de una en una es lento.",
    "36.7: importancia por permutación sobre filas que el modelo auxiliar no vio, la reserva más reciente de entrenamiento.",
    "36.8: votación de los tres métodos, con el corte de los dos que dan un valor por salto natural.",
    "36.9 y 5.2: entre las que pasaron, Spearman y V de Cramér para no dejar dos variables que dicen lo mismo en una "
    "regresión, donde se reparten el efecto y pueden salir con el signo al revés.",
]


class Parada(Exception):
    """Condición que impide seguir; `estado` dice si el método paró a propósito (PARADO) o si falló algo (ERROR)."""

    def __init__(self, mensaje, estado="ERROR"):
        super().__init__(mensaje)
        self.estado = estado


# =================================================================================================================
# 3. Lectura: la muestra de entrenamiento, con dos semillas
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leído por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def leer_muestras(ruta, semillas):
    """Lee entrenamiento grupo a grupo y saca una muestra por semilla: todas las fotos con fallo y, de cada mes, el 2 %
    de las sanas, sorteadas en el orden de los grupos como el script 13. Devuelve las muestras y los recuentos."""
    pf = pq.ParquetFile(ruta)
    rngs = {s: np.random.default_rng(s) for s in semillas}
    trozos = {s: [] for s in semillas}
    total = {"filas": 0, "fallos": 0}
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=LEER)
        y = t[OBJETIVO].to_numpy().astype(np.int64)
        total["filas"] += len(y)
        total["fallos"] += int(y.sum())
        sanas = np.flatnonzero(y == 0)
        k = int(np.floor(FRACCION_SANAS * len(sanas) + 0.5))
        for s in semillas:
            elegidas = rngs[s].choice(sanas, size=k, replace=False) if k else np.array([], dtype=np.int64)
            filas = np.sort(np.concatenate([np.flatnonzero(y == 1), elegidas]))
            trozos[s].append(t.take(pa.array(filas)))
    muestras = {s: pa.concat_tables(trozos[s]).to_pandas() for s in semillas}
    return muestras, total


def meses_recientes(df, filas, col_fecha=FECHA):
    """Los meses más recientes, enteros, hasta pasar de `filas`; si no llega, la muestra entera. Devuelve la tabla y si
    es la muestra entera."""
    cuenta = df[col_fecha].value_counts().sort_index(ascending=False)
    acumulado = cuenta.cumsum()
    pasa = acumulado[acumulado > filas]
    meses = cuenta.index if pasa.empty else cuenta.index[: cuenta.index.get_loc(pasa.index[0]) + 1]
    sub = df[df[col_fecha].isin(meses)]
    return sub, len(sub) == len(df)


# =================================================================================================================
# 4. La variable de origen de cada columna (matriz, columnas «variable» y «salida»)
# =================================================================================================================
def patrones_logistica(mz):
    """El patrón de nombre de las columnas de la logística de cada variable, leído de la columna «salida» de la matriz."""
    patrones = {}
    for fila in mz["filas"]:
        if fila["seccion"] != "entran" or fila["variable"] not in mz["logistica"]:
            continue
        for trozo in fila["salida"].split("<br>"):
            m = re.match(r"\s*L[:]\s*(\S+)\s*$", trozo)
            if m and m.group(1) != "—":
                patrones[fila["variable"]] = m.group(1)
    return patrones


def origen_de(columnas, patrones):
    """Cada columna a su variable de origen. Devuelve el diccionario, las columnas sin origen y las de varios."""
    origen, sin, varias = {}, [], []
    for c in columnas:
        v = [var for var, p in patrones.items() if fnmatch.fnmatchcase(c, p)]
        if len(v) == 1:
            origen[c] = v[0]
        elif not v:
            sin.append(c)
        else:
            varias.append(c)
    return origen, sin, varias


# =================================================================================================================
# 5. Lo que no puede entrar: la fuga y las variables del momento (método §2)
# =================================================================================================================
def codigos(Z, columnas):
    """El tramo o la categoría de cada fila de una variable: 0 en la referencia y k en su columna k."""
    if not columnas:
        return None
    return (Z[columnas].to_numpy(dtype=np.float64) @ np.arange(1, len(columnas) + 1)).astype(np.int64)


def _auc_tasa(y, grupos):
    """AUC de puntuar cada grupo con su tasa de fallo; None si hay un solo grupo."""
    grupos = np.asarray(grupos)
    if len(np.unique(grupos)) < 2:
        return None
    tasa = pd.Series(y).groupby(grupos).mean()
    return float(roc_auc_score(y, tasa.reindex(grupos).to_numpy()))


def auc_variable_sola(Z, y, cols_por_var, crudas=None):
    """El AUC de cada variable sola, leído por |2·AUC − 1|, el mayor de dos:
    - en bruto: una numérica con su valor, en las filas con dato; una nominal, cada categoría con su tasa de fallo;
    - tras el preprocesador: cada tramo o categoría con su tasa de fallo.
    El bruto hace falta porque los tramos piden 20 fallos y 20 sanas: una copia del objetivo se funde en un solo tramo
    y tras el preprocesador no deja ninguna columna."""
    salida = {}
    for v, cols in cols_por_var.items():
        c = codigos(Z, cols)
        auc_tramos = _auc_tasa(y, c) if c is not None else None
        auc_bruto = None
        if crudas is not None and v in crudas:
            x = crudas[v]
            if v in P13.NOMINALES:
                auc_bruto = _auc_tasa(y, x.astype(object).where(x.notna(), P13.SIN_DATO).astype(str).to_numpy())
            else:
                x = pd.to_numeric(x).to_numpy(dtype=float, na_value=np.nan)
                ok = ~np.isnan(x)
                if len(np.unique(y[ok])) == 2 and np.ptp(x[ok]) > 0:
                    auc_bruto = float(roc_auc_score(y[ok], x[ok]))
        dif = {k: abs(2 * a - 1) for k, a in (("bruto", auc_bruto), ("tramos", auc_tramos)) if a is not None}
        mayor = max(dif, key=dif.get) if dif else None
        salida[v] = {"auc": {"bruto": auc_bruto, "tramos": auc_tramos}[mayor] if mayor else None,
                     "auc_bruto": auc_bruto, "auc_tramos": auc_tramos,
                     "diferencia": dif[mayor] if mayor else None, "de": mayor}
    return salida


def alarmas(auc, umbral):
    """Las variables cuyo AUC sola está a |2·AUC − 1| ≥ umbral; la decisión queda vacía hasta que se investigue."""
    return [{"columna": v, "valor": a["diferencia"], "metodo": "AUC de la variable sola, |2·AUC − 1|",
             "que_se_encontro": f"separa el objetivo casi del todo (AUC {a['auc']:.4f}, {a.get('de') or 'tramos'})",
             "decision": ""}
            for v, a in sorted(auc.items()) if a["diferencia"] is not None and a["diferencia"] >= umbral]


def del_momento(df, variables, col_fecha=FECHA):
    """Las variables con el mismo valor para todas las fotos de una fecha y distinto entre fechas."""
    marcadas = []
    for v in variables:
        if df[v].nunique(dropna=False) > 1 and df.groupby(col_fecha)[v].nunique(dropna=False).max() <= 1:
            marcadas.append(v)
    return marcadas


# =================================================================================================================
# 6. Los tres métodos, el corte y la votación (método §3 y §4)
# =================================================================================================================
def pliegues_por_fecha(fechas, horizontes, y, n):
    """TimeSeriesSplit(n) sobre las filas ordenadas por fecha; cada entrenamiento, solo con las fotos cuyo horizonte
    acabó antes del primer día de lo que mide. Devuelve los cortes y lo quitado en cada uno."""
    cortes, detalle = [], []
    for ent, med in TimeSeriesSplit(n).split(np.arange(len(fechas))):
        primero = fechas[med].min()
        ok = horizontes[ent] < primero
        cortes.append((ent[ok], med))
        detalle.append({"primer_dia": str(np.datetime_as_string(primero, unit="D")), "filas_mide": int(len(med)),
                        "filas_entrena": int(ok.sum()), "filas_quitadas": int((~ok).sum()),
                        "fallos_quitados": int(y[ent][~ok].sum())})
    return cortes, detalle


def corte_salto(valores):
    """Corte por salto natural: con los valores mayores que cero de mayor a menor, el corte va donde el cociente entre
    un valor y el siguiente es mayor, y pasan los de arriba. Devuelve lo que pasa, el cociente y los dos valores."""
    pos = valores[valores > 0].sort_values(ascending=False, kind="stable")
    if len(pos) < 2:
        return {"pasan": list(pos.index), "como": "salto", "cociente": None,
                "valor": float(pos.iloc[0]) if len(pos) else None, "valor_abajo": None}
    a = pos.to_numpy()
    cocientes = a[:-1] / a[1:]
    i = int(np.argmax(cocientes))
    return {"pasan": list(pos.index[: i + 1]), "como": "salto", "cociente": float(cocientes[i]),
            "valor": float(a[i]), "valor_abajo": float(a[i + 1])}


def votos_por_variable(marcadas, origen):
    """Los votos de cada variable de origen: uno por método si alguna de sus columnas pasó su corte."""
    votos = {v: 0 for v in origen.values()}
    for columnas in marcadas.values():
        for v in {origen[c] for c in columnas if c in origen}:
            votos[v] += 1
    return votos


def entran_por_votacion(votos, minimo, obligatorias):
    """Las variables con al menos `minimo` votos, más las obligatorias, que entran sin votar."""
    return sorted({v for v, n in votos.items() if n >= minimo} | set(obligatorias))


def puestos(serie):
    """El puesto de cada elemento, de mayor a menor valor y desde 1; los empates, por nombre."""
    orden = sorted(serie.index, key=lambda k: (-serie[k], k))
    return {k: i + 1 for i, k in enumerate(orden)}


# =================================================================================================================
# 7. Las que dicen lo mismo (método §6) y el tope (método §7)
# =================================================================================================================
def cramer(a, b):
    """V de Cramér entre dos variables de tramos o categorías; None si una no varía."""
    tabla = pd.crosstab(np.asarray(a), np.asarray(b)).to_numpy()
    if min(tabla.shape) < 2:
        return None
    return float(association(tabla, method="cramer"))


def spearman(x, y):
    """Spearman entre dos numéricas, con las filas que tienen las dos; None si una no varía o no hay filas."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = ~np.isnan(x) & ~np.isnan(y)
    if ok.sum() < 3 or np.ptp(x[ok]) == 0 or np.ptp(y[ok]) == 0:
        return None
    rx = pd.Series(x[ok]).rank().to_numpy()
    ry = pd.Series(y[ok]).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


def pares_parecidos(df, cod, candidatas, umbral):
    """Los pares de variables de distinto origen que llegan al umbral en V de Cramér (sobre sus tramos o categorías) o
    en Spearman (entre dos numéricas, sobre el valor en bruto). Las dos medidas se calculan solo con las filas que
    tienen dato en las dos variables: muchos contadores SMART solo los registra algún modelo, y con el vacío dentro la
    V de Cramér mide qué modelo registra cada contador, no la información (método §6, último punto)."""
    pares = []
    for i, a in enumerate(candidatas):
        for b in candidatas[i + 1:]:
            comunes = (df[a].notna() & df[b].notna()).to_numpy()
            vc = cramer(cod[a][comunes], cod[b][comunes]) if comunes.any() else None
            vs = spearman(df[a], df[b]) if a in P13.NUM_LOGISTICA and b in P13.NUM_LOGISTICA else None
            medidas = {k: abs(x) for k, x in (("cramer", vc), ("spearman", vs)) if x is not None}
            if medidas and max(medidas.values()) >= umbral:
                medida = max(medidas, key=medidas.get)
                pares.append({"columna_1": a, "columna_2": b, "medida": medida, "valor": medidas[medida],
                              "cramer": vc, "spearman": vs, "filas_comunes": int(comunes.sum())})
    return pares


def quitar_por_pares(pares, mi, obligatorias):
    """De cada par, del más fuerte al más flojo, sale la de menos información mutua; una obligatoria gana siempre el
    par, y si las dos lo son no sale ninguna. Si una del par ya salió, el par queda resuelto."""
    fuera, salida = set(), []
    for p in sorted(pares, key=lambda q: (-q["valor"], q["columna_1"], q["columna_2"])):
        a, b = p["columna_1"], p["columna_2"]
        if a in fuera or b in fuera:
            sale, motivo = None, "ya resuelto: una del par había salido"
        elif a in obligatorias and b in obligatorias:
            sale, motivo = None, "las dos son obligatorias"
        elif a in obligatorias or b in obligatorias:
            sale = b if a in obligatorias else a
            motivo = "la otra es obligatoria y gana el par"
        else:
            sale = a if (mi[a], b) < (mi[b], a) else b
            motivo = "menos información mutua"
        if sale:
            fuera.add(sale)
        salida.append({**p, "sale": sale, "motivo": motivo})
    return salida


def aplicar_tope(variables, cols, ranking, maximo, obligatorias):
    """Si las columnas pasan del tope, salen familias enteras, de la de peor ranking a la mejor, nunca una obligatoria."""
    quedan, salen = list(variables), []
    while sum(len(cols.get(v, [])) for v in quedan) > maximo:
        candidatas = [v for v in quedan if v not in obligatorias]
        if not candidatas:
            break
        peor = max(candidatas, key=lambda v: (ranking[v], v))
        quedan.remove(peor)
        salen.append(peor)
    return quedan, salen


# =================================================================================================================
# 8. Las seis validaciones (método §8), calculadas con lo que se ejecutó
# =================================================================================================================
def v_sin_validacion(leidos):
    """1. Nada se ajustó con la validación ni con el lote de producción: todo lo que el script leyó es entrenamiento,
    la preparación o la matriz."""
    return bool(leidos) and all(r in (PREPARACION, MATRIZ, ENTRENAMIENTO) for r in leidos)


def v_origen_en_matriz(columnas, origen, variables_matriz):
    """2. Cada columna final tiene su variable de origen en la matriz."""
    return all(c in origen and origen[c] in variables_matriz for c in columnas)


def v_familias_enteras(columnas, variables, cols):
    """3. Ninguna familia quedó a medias: las columnas finales son exactamente las de las variables finales."""
    return set(columnas) == {c for v in variables for c in cols.get(v, [])}


def v_tope(n, maximo):
    """4. En la logística, el número de columnas finales no pasa del tope."""
    return n <= maximo


def v_sin_prohibidas(variables, prohibidas):
    """5. No queda ningún identificador, el objetivo ni una variable que la matriz deja fuera."""
    return not set(variables) & set(prohibidas)


def v_lista_valida(variables, columnas):
    """6. La lista final no está vacía y no tiene nombres repetidos."""
    return bool(variables) and bool(columnas) and len(variables) == len(set(variables)) and len(columnas) == len(set(columnas))


# =================================================================================================================
# 9. Una selección completa sobre una muestra
# =================================================================================================================
def transformar(pre, X):
    """La salida del preprocesador ajustado, por trozos, en float32 para no llenar la memoria."""
    return pd.concat([pre.transform(X.iloc[a:a + TROZO]).astype(np.float32) for a in range(0, len(X), TROZO)])


def seleccion(df, fallos_entrenamiento, patrones):
    """Preselección de la logística sobre una muestra: preprocesador, fuga, momento, tres métodos, votación, pares y tope.
    Devuelve un diccionario; si salta una alarma o una variable del momento encabeza un ranking, lleva `parada`."""
    r = {"parada": None}
    t0 = time.time()
    df = df.sort_values(FECHA, kind="stable").reset_index(drop=True)
    y = df[OBJETIVO].to_numpy().astype(np.int64)
    fechas = df[FECHA].to_numpy()
    horiz = df[HORIZONTE].to_numpy()
    r["filas"], r["fallos"] = len(df), int(y.sum())
    r["meses"] = [str(np.datetime_as_string(m, unit="D")) for m in np.unique(fechas)]
    # 9.1 El preprocesador de la logística del script 13, entero y ajustado con la muestra
    pre = P13.preprocesador("logistica").fit(df, y)
    Z = transformar(pre, df)
    Z.index = df.index
    origen, sin, varias = origen_de(list(Z.columns), patrones)
    if sin or varias:
        raise Parada(f"columnas sin una sola variable de origen en la matriz: sin origen {sin}, con varios {varias}")
    cols = {v: [c for c in Z.columns if origen[c] == v] for v in ENTRADA_LOGISTICA}
    r["columnas_preprocesador"] = int(Z.shape[1])
    r["columnas_por_variable"] = cols
    r["columnas_constantes"] = [c for c in Z.columns if Z[c].nunique() <= 1]
    r["sin_columnas"] = [v for v in ENTRADA_LOGISTICA if not [c for c in cols[v] if c not in r["columnas_constantes"]]]
    # 9.2 La fuga: el AUC de cada variable sola; una alarma sin decisión para (resultado.md)
    auc = auc_variable_sola(Z, y, cols, df)
    r["auc_sola"] = auc
    r["alarmas_de_fuga"] = alarmas(auc, UMBRAL_FUGA)
    r["momento"] = del_momento(df, ENTRADA_LOGISTICA)
    if r["alarmas_de_fuga"]:
        r["parada"] = ("alarma de fuga en " + ", ".join(a["columna"] for a in r["alarmas_de_fuga"])
                       + ": se investiga de dónde sale el dato antes de seguir (método §2)")
        return r
    # 9.3 Información mutua, con la máscara de discretas calculada (todas son 0 y 1)
    discretas = np.array([set(np.unique(Z[c].to_numpy())) <= {0.0, 1.0} for c in Z.columns])
    r["discretas"] = int(discretas.sum())
    t = time.time()
    mi = pd.Series(mutual_info_classif(Z, y, discrete_features=discretas, random_state=SEMILLA), index=Z.columns)
    r["segundos_mi"] = round(time.time() - t, 1)
    # 9.4 RFECV con el bosque auxiliar y pliegues por fecha que esperan al objetivo
    cortes_rfe, r["pliegues_rfe"] = pliegues_por_fecha(fechas, horiz, y, RFE_PLIEGUES)
    t = time.time()
    rfe = RFECV(RandomForestClassifier(n_estimators=RFE_ARBOLES, max_depth=RFE_PROFUNDIDAD, random_state=SEMILLA, n_jobs=-1),
                step=RFE_PASO, min_features_to_select=RFE_MINIMO, cv=cortes_rfe, scoring=METRICA).fit(Z, y)
    r["segundos_rfe"] = round(time.time() - t, 1)
    ranking_rfe = pd.Series(rfe.ranking_, index=Z.columns)
    r["rfe_elegidas"] = int(rfe.n_features_)
    # 9.5 Permutación: el boosting auxiliar aprende con el 80 % más antiguo y se mide en el 20 % más reciente
    corte = int(np.floor((1 - RESERVA) * len(df) + 0.5))
    primero = fechas[corte:].min()
    ent = np.flatnonzero(horiz[:corte] < primero)
    r["reserva"] = {"primer_dia": str(np.datetime_as_string(primero, unit="D")), "filas_mide": int(len(df) - corte),
                    "fallos_mide": int(y[corte:].sum()), "filas_entrena": int(len(ent)),
                    "filas_quitadas": int(corte - len(ent)), "fallos_quitados": int(y[:corte].sum() - y[ent].sum())}
    t = time.time()
    aux = HistGradientBoostingClassifier(random_state=SEMILLA, early_stopping=False).fit(Z.iloc[ent], y[ent])
    p = permutation_importance(aux, Z.iloc[corte:], y[corte:], scoring=METRICA, n_repeats=REPETICIONES,
                               random_state=SEMILLA, n_jobs=1)
    r["segundos_permutacion"] = round(time.time() - t, 1)
    per = pd.Series(p.importances_mean, index=Z.columns)
    per_sd = pd.Series(p.importances_std, index=Z.columns)
    # 9.6 Los cortes y la votación por variable de origen
    corte_mi, corte_per = corte_salto(mi), corte_salto(per)
    marcadas = {"mi": corte_mi["pasan"], "rfe": list(ranking_rfe.index[ranking_rfe == 1]), "permutacion": corte_per["pasan"]}
    votos = votos_por_variable(marcadas, origen)
    votos = {v: votos.get(v, 0) for v in ENTRADA_LOGISTICA}
    r["cortes"] = {"mi": {k: v for k, v in corte_mi.items() if k != "pasan"} | {"columnas_que_pasan": len(corte_mi["pasan"])},
                   "permutacion": {k: v for k, v in corte_per.items() if k != "pasan"} | {"columnas_que_pasan": len(corte_per["pasan"])},
                   "rfe": {"como": "ranking 1", "columnas_que_pasan": len(marcadas["rfe"])}}
    r["rankings"] = [{"columna": c, "origen": origen[c], "mi": float(mi[c]), "ranking_rfe": int(ranking_rfe[c]),
                      "permutacion": float(per[c]), "permutacion_desviacion": float(per_sd[c]),
                      "valor_informativo": None, "votos": votos[origen[c]]} for c in Z.columns]
    pm = puestos(mi)
    pp = puestos(per)
    for fila in r["rankings"]:
        fila["ranking_mi"], fila["ranking_per"] = pm[fila["columna"]], pp[fila["columna"]]
    # Por variable: la mejor de sus columnas en cada método
    con = [v for v in ENTRADA_LOGISTICA if cols[v]]
    mi_v = pd.Series({v: float(mi[cols[v]].max()) for v in con})
    per_v = pd.Series({v: float(per[cols[v]].max()) for v in con})
    rfe_v = pd.Series({v: int(ranking_rfe[cols[v]].min()) for v in con})
    pv_mi, pv_per, pv_rfe = puestos(mi_v), puestos(per_v), puestos(-rfe_v)
    tot = pd.Series({v: pv_mi[v] + pv_per[v] + pv_rfe[v] for v in con})
    ranking_tot = {v: i + 1 for i, v in enumerate(sorted(con, key=lambda v: (tot[v], v)))}
    r["rankings_por_variable"] = [{"origen": v, "columnas": len(cols[v]), "mi": mi_v.get(v), "ranking_mi": pv_mi.get(v),
                                   "ranking_rfe": int(rfe_v[v]) if v in rfe_v else None, "permutacion": per_v.get(v),
                                   "ranking_per": pv_per.get(v), "ranking_tot": ranking_tot.get(v), "votos": votos[v],
                                   "obligatoria": v in OBLIGATORIAS, "auc_sola": auc[v]["auc"], "del_momento": v in r["momento"]}
                                  for v in ENTRADA_LOGISTICA]
    # Una variable del momento que encabeza un ranking para y se pregunta (método §2)
    arriba = {min(pv_mi, key=pv_mi.get), min(pv_per, key=pv_per.get)} if con else set()
    if set(r["momento"]) & arriba:
        r["parada"] = (f"la variable del momento {sorted(set(r['momento']) & arriba)} encabeza un ranking: hay que decidir si "
                       "el modelo tiene que funcionar fuera de esa coyuntura (método §2)")
        return r
    votadas = entran_por_votacion(votos, VOTOS_MINIMOS, OBLIGATORIAS)
    r["votadas"] = votadas
    # 9.7 Las que dicen lo mismo, entre variables de distinto origen que pasaron la votación
    candidatas = [v for v in votadas if cols[v]]
    cod = {v: codigos(Z, cols[v]) for v in candidatas}
    pares = pares_parecidos(df, cod, candidatas, UMBRAL_PARECIDO)
    r["pares_parecidos"] = quitar_por_pares(pares, mi_v.to_dict(), OBLIGATORIAS)
    salen_pares = {p["sale"] for p in r["pares_parecidos"] if p["sale"]}
    apariciones = pd.Series([p[k] for p in pares for k in ("columna_1", "columna_2")]).value_counts()
    r["apariciones_en_pares"] = {k: int(n) for k, n in apariciones.items()}
    # 9.8 El tope: una columna por cada 10 fallos de entrenamiento
    tras_pares = [v for v in votadas if v not in salen_pares]
    maximo = fallos_entrenamiento // CASOS_POR_COLUMNA
    rk = {v: ranking_tot.get(v, len(ENTRADA_LOGISTICA) + 1) for v in tras_pares}
    finales, salen_tope = aplicar_tope(tras_pares, cols, rk, maximo, OBLIGATORIAS)
    r["tope"] = {"aplica": True, "casos_clase_pequena": fallos_entrenamiento, "maximo_columnas": maximo,
                 "columnas_antes": sum(len(cols[v]) for v in tras_pares), "salen": salen_tope}
    r["variables_finales"] = finales
    r["columnas_finales"] = [c for c in Z.columns if origen[c] in finales]
    r["tope"]["columnas_finales"] = len(r["columnas_finales"])
    r["origen"] = origen
    r["segundos"] = round(time.time() - t0, 1)
    return r


# =================================================================================================================
# 10. El JSON y el informe
# =================================================================================================================
def version_metodo():
    """La fecha y el código de la última línea de versión del METODO.md (bloque común de resultado.md)."""
    if not METODO_MD.exists():
        return None
    lineas = [x for x in METODO_MD.read_text(encoding="utf-8").splitlines() if x.startswith("Versión ")]
    m = re.match(r"Versión (\S+) \(([^),]+)", lineas[-1]) if lineas else None
    return f"{m.group(1)} ({m.group(2)})" if m else None


NOMBRES_VALIDACION = {
    "sin_validacion": "nada se ajustó con la validación, que el script no abrió",
    "origen_en_matriz": "cada columna final tiene su variable de origen en la matriz",
    "familias_enteras": "ninguna familia quedó a medias",
    "tope": "las columnas finales no pasan del tope",
    "sin_prohibidas": "no queda ningún identificador, el objetivo ni una variable que la matriz deja fuera",
    "lista_valida": "la lista final no está vacía ni tiene nombres repetidos",
}


def _p(x, d=4):
    """Un número para el informe, o «no se calculó»."""
    return "no se calculó" if x is None else numero(x, d)


def informe(res):
    """El informe para el responsable del caso, con los apartados de resultado.md y solo las cifras del diccionario."""
    L = []
    w = L.append
    lo = res["familias"]["logistica"]
    estado = res["resultado"]["estado"]
    w("# Preselección de variables")
    w("")
    w(res["resultado"]["resumen"])
    w("")
    w("## ¿Hacía falta?")
    w("")
    w(f"En la regresión logística sí. {lo['por_que']} El bosque y el HistGradientBoosting no se preseleccionan por "
      f"votación y reciben las {len(res['familias']['bosque']['columnas_finales'])} columnas de la matriz.")
    w("")
    mu = lo.get("muestra") or {}
    if mu.get("partida"):
        pa_ = mu["partida"]
        w(f"La muestra de partida tiene {numero(pa_['filas'])} fotos: las {numero(pa_['fallos'])} con fallo y "
          f"{numero(pa_['sanas'])} sanas, el {numero(100 * FRACCION_SANAS)} % de cada mes.")
        if mu.get("filas") is not None:
            w(f"La preselección usó {numero(mu['filas'])} de ellas, de {mu['meses'][0]} a {mu['meses'][-1]}"
              + (", la muestra entera." if mu.get("entera") else ", los meses más recientes enteros hasta pasar de "
                 f"{numero(mu['filas_objetivo'])} filas."))
        if mu.get("misma_lista") is not None:
            w("Con la segunda muestra, sorteada con semilla 43, la lista final " +
              ("sale igual." if mu["misma_lista"] else "cambia; el detalle de cada intento está en el JSON."))
        w("")
    w("## Lo que no podía entrar")
    w("")
    rc = lo.get("recuento") or {}
    if rc:
        w(f"Entran a la logística {rc['variables_entrada']} variables de la matriz, que el preprocesador del script 13 "
          f"convierte en {numero(rc['columnas_preprocesador'])} columnas con la muestra de partida. Ninguna es un "
          "identificador, el objetivo ni una de las que la matriz deja fuera: la validación 5 lo comprueba.")
    sc = lo.get("sin_columnas") or []
    if sc:
        w(f"No dejan ninguna columna que varíe con la muestra usada, y por eso no pueden recibir votos: {', '.join(sc)}.")
    mo = lo.get("del_momento")
    if mo is not None:
        w("Ninguna variable vale lo mismo para todas las fotos de una fecha." if not mo else
          f"Valen lo mismo para todas las fotos de una fecha: {', '.join(mo)}. Ninguna encabeza un ranking.")
    w("")
    w("## Alarmas de fuga")
    w("")
    al = lo.get("alarmas_de_fuga")
    if al is None:
        w("No se calcularon: el script paró antes.")
    elif not al:
        aucs = [r for r in lo.get("rankings_por_variable") or [] if r.get("auc_sola") is not None]
        top = max(aucs, key=lambda r: abs(2 * r["auc_sola"] - 1)) if aucs else None
        w(f"Ninguna variable sola llega a |2·AUC − 1| de {numero(UMBRAL_FUGA, 2)}, el umbral de posible fuga del "
          "exploratorio del caso." + (f" La que más separa es {top['origen']}, con un AUC de {numero(top['auc_sola'], 3)}."
                                       if top else ""))
    else:
        for a in al:
            w(f"- {a['columna']}: {a['que_se_encontro']}. Queda sin decisión y el script para hasta que se investigue de "
              "dónde sale el dato.")
    w("")
    w("## Cómo se votó")
    w("")
    w(f"Modo comparativo y escenario de {lo['escenario']}, fijado por el responsable del caso antes de ver el resultado: entra una variable "
      "si la marcan dos o más de los tres métodos. La unidad de voto es la variable de origen: recibe el voto de un "
      "método si alguna de sus columnas pasa su corte, y entra o sale con todas.")
    w("")
    w(f"Entran siempre, sin votar: {', '.join(OBLIGATORIAS)}, para poder explicar la lista a los técnicos con lo que ya vigilan.")
    w("")
    ct = lo.get("cortes")
    if ct:
        for nombre, k in (("información mutua", "mi"), ("importancia por permutación", "permutacion")):
            c = ct[k]
            if c["cociente"] is None:
                w(f"- En {nombre} no hubo salto que medir: pasan las {c['columnas_que_pasan']} columnas con valor mayor que cero.")
            else:
                w(f"- En {nombre}, el mayor salto va de {_p(c['valor'], 5)} a {_p(c['valor_abajo'], 5)}, un cociente de "
                  f"{numero(c['cociente'], 2)}; pasan {c['columnas_que_pasan']} " + ("columna." if c['columnas_que_pasan'] == 1 else "columnas."))
        w(f"- En RFECV pasan las {ct['rfe']['columnas_que_pasan']} columnas de ranking 1.")
        w("")
        rv = sorted([r for r in lo["rankings_por_variable"] if r["ranking_tot"] is not None], key=lambda r: (r["ranking_tot"], r["origen"]))
        w("| Variable | Votos | Puesto combinado | Información mutua | Permutación | Ranking RFECV | Obligatoria |")
        w("|---|---|---|---|---|---|---|")
        for r in rv:
            w(f"| {r['origen']} | {r['votos']} | {r['ranking_tot'] if r['ranking_tot'] is not None else '—'} | "
              f"{_p(r['mi'], 5)} | {_p(r['permutacion'], 5)} | {r['ranking_rfe'] if r['ranking_rfe'] is not None else '—'} | "
              f"{'sí' if r['obligatoria'] else 'no'} |")
        w("")
        w("Las cifras de los modelos auxiliares solo ordenan: no se citan como rendimiento.")
    else:
        w("No se votó: el script paró antes.")
    w("")
    w("## Una variante por variable")
    w("")
    w("En la logística cada variable tiene una sola rama: sus tramos, con el vacío cuando es tramo propio, o una columna "
      "por categoría. Cada variable es una familia y entra o sale entera; no hay alternativas entre las que elegir.")
    w("")
    w("## Las que dicen lo mismo")
    w("")
    pr = lo.get("pares_parecidos")
    if pr is None:
        w("No se calcularon: el script paró antes.")
    elif not pr:
        w(f"Ningún par de variables que pasaron la votación llega a {numero(UMBRAL_PARECIDO, 1)} en Spearman ni en V de Cramér.")
    else:
        w(f"Estos pares llegan a {numero(UMBRAL_PARECIDO, 1)}. De cada uno sale la de menos información mutua, salvo que "
          "la otra sea obligatoria, que gana el par:")
        w("")
        for p in pr:
            w(f"- {p['columna_1']} y {p['columna_2']}, {'Spearman' if p['medida'] == 'spearman' else 'V de Cramér'} {numero(p['valor'], 3)}"
              f" con las {numero(p['filas_comunes'])} fotos que tienen dato en las dos: "
              + (f"sale {p['sale']} ({p['motivo']})." if p["sale"] else f"no sale ninguna ({p['motivo']})."))
    w("")
    w("## El tope")
    w("")
    tp = lo.get("tope")
    if tp:
        w(f"Con {numero(tp['casos_clase_pequena'])} fotos con fallo en entrenamiento, la logística admite como mucho "
          f"{numero(tp['maximo_columnas'])} columnas. Tras los pares quedaban {numero(tp['columnas_antes'])}"
          + (f", y salieron por familias enteras: {', '.join(tp['salen'])}." if tp["salen"] else ", así que no sale ninguna."))
    else:
        w("No se calculó: el script paró antes.")
    w("")
    w("## Las columnas que entran")
    w("")
    if lo.get("variables_finales"):
        w(f"Entran {len(lo['variables_finales'])} variables, con {len(lo['columnas_finales'])} columnas en el ajuste con la "
          f"muestra: {', '.join(lo['variables_finales'])}.")
        w("")
        w("El modelado guarda la lista de variables, no la de columnas: los tramos se aprenden en cada ajuste y sus nombres "
          "cambian de un pliegue a otro. El preprocesador se monta entero y después se quedan las columnas cuyo origen "
          "está en la lista. Por eso fabricante sigue sirviendo de clave a los tramos de smart_1_raw y smart_7_raw "
          "aunque no entre, y sus columnas propias solo salen si entra.")
    else:
        w("No hay lista final: el script paró antes.")
    w("")
    w("## Validaciones")
    w("")
    val = lo.get("validaciones") or {}
    for k, nombre in NOMBRES_VALIDACION.items():
        v = val.get(k)
        w(f"- {nombre[0].upper() + nombre[1:]}: " + ("no se calculó." if v is None else ("en verde." if v else "EN ROJO.")))
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
    if estado != "OK":
        w(f"Estado de esta ejecución: {estado}.")
        w("")
    return "\n".join(L)


def escribir(raiz, res):
    """Escribe el JSON (UTF-8, sin NaN) y el informe, del mismo diccionario."""
    (raiz / SALIDA_JSON).parent.mkdir(parents=True, exist_ok=True)
    (raiz / SALIDA_JSON).write_text(json.dumps(res, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    (raiz / SALIDA_MD).write_text(informe(res), encoding="utf-8")


# =================================================================================================================
# 11. Principal
# =================================================================================================================
def base(raiz):
    """El bloque común y lo fijo, antes de saber el resultado."""
    proteccion = (raiz / PROTECCION).exists()
    return {
        "metodo": METODO, "version_metodo": version_metodo(), "script": SCRIPT, "peticion": PETICION,
        "fecha_datos": FECHA_DATOS, "fecha_ejecucion": dt.datetime.now().replace(microsecond=0).isoformat(),
        "entradas": [], "resultado": {"estado": None, "riesgo": None, "resumen": None, "artefactos": [SALIDA_JSON, SALIDA_MD], "siguiente": None},
        "pendientes": [], "leidos": [],
        "familias": {
            "logistica": {"se_preselecciona": True,
                          "por_que": ("Es un modelo lineal: scikit-learn no da la significación de cada coeficiente y el "
                                      "tope de columnas obliga (método §1), y el responsable del caso lo fijó en las reglas, apartado 7 el 18/11/2026."),
                          "algoritmo_previsto": "regresión logística regularizada", "modo": "comparativo",
                          "escenario": ESCENARIO, "escenario_fijado_en": "config/negocio/reglas-negocio.md §7",
                          "obligatorias": OBLIGATORIAS, "muestra": None, "recuento": None, "fuera_de_entrada": None,
                          "alarmas_de_fuga": None, "del_momento": None, "sin_columnas": None, "rankings": None,
                          "rankings_por_variable": None, "cortes": None, "una_variante_por_variable": None,
                          "pares_parecidos": None, "tope": None, "variables_finales": None, "columnas_finales": None,
                          "columnas_por_variable": None, "pliegues_rfe": None, "reserva_permutacion": None,
                          "validaciones": {k: None for k in NOMBRES_VALIDACION}, "intentos": []},
            **{f: {"se_preselecciona": False,
                   "por_que": ("los árboles manejan bien muchas variables y el responsable del caso fijó en las reglas, apartado 7 (18/11/2026) que no "
                               "se preseleccionan por votación: reciben las columnas de la matriz."),
                   "algoritmo_previsto": nombre, "fuera_de_entrada": None, "columnas_finales": ENTRADA_ARBOLES,
                   "muestra": None, "alarmas_de_fuga": None, "modo": None, "escenario": None, "rankings": None,
                   "cortes": None, "una_variante_por_variable": None, "pares_parecidos": None, "tope": None,
                   "validaciones": None}
               for f, nombre in (("bosque", "bosque aleatorio"), ("hgb", "HistGradientBoosting"))}},
        "parametros": [
            {"nombre": "semillas", "valor": f"{SEMILLA} en la muestra y en los tres métodos; {SEMILLA_2} en la segunda muestra", "origen": "parametros.md y petición 21"},
            {"nombre": "muestra", "valor": f"todas las fotos con fallo y el {numero(100 * FRACCION_SANAS)} % de las sanas de cada mes; de ella, los meses más recientes enteros hasta pasar de {numero(FILAS_MUESTRA)} filas; si la lista cambia con la segunda muestra se dobla; si no cabe, se usa entera", "origen": "reglas, apartado 7; parametros.md, «filas para muestrear»; nota de la petición 21, punto 5"},
            {"nombre": "escenario de votación", "valor": f"{ESCENARIO}, {VOTOS_MINIMOS} votos o más", "origen": "reglas, apartado 7, el responsable del caso, 18/11/2026"},
            {"nombre": "obligatorias", "valor": ", ".join(OBLIGATORIAS), "origen": "reglas, apartado 7, el responsable del caso, 18/11/2026"},
            {"nombre": "información mutua", "valor": f"mutual_info_classif con random_state={SEMILLA} y la máscara de discretas", "origen": "metodos.md; petición 21"},
            {"nombre": "RFECV", "valor": f"RandomForestClassifier({RFE_ARBOLES} árboles, profundidad {RFE_PROFUNDIDAD}, semilla {SEMILLA}), TimeSeriesSplit({RFE_PLIEGUES}) por fecha con el horizonte cerrado, step={RFE_PASO}, min_features_to_select={RFE_MINIMO}, {METRICA}", "origen": "parametros.md; petición 21; nota de la petición 21, punto 3"},
            {"nombre": "importancia por permutación", "valor": f"HistGradientBoostingClassifier por defecto con semilla {SEMILLA} y early_stopping=False; el {numero(100 * (1 - RESERVA))} % más antiguo entrena y el {numero(100 * RESERVA)} % más reciente mide; {REPETICIONES} repeticiones; {METRICA}", "origen": "parametros.md; petición 21; early_stopping escrito por aprendizaje-automatico §5 y algoritmos.md"},
            {"nombre": "corte de información mutua y permutación", "valor": "salto natural: el mayor cociente entre un valor y el siguiente", "origen": "metodos.md, «El corte»; petición 21"},
            {"nombre": "umbral de las que dicen lo mismo", "valor": f"Spearman o V de Cramér de {numero(UMBRAL_PARECIDO, 1)} o más", "origen": "parametros.md"},
            {"nombre": "alarma de fuga", "valor": f"|2·AUC − 1| de {numero(UMBRAL_FUGA, 2)} o más, con el AUC de la variable sola", "origen": "UMBRAL_FUGA de scripts/06_analisis_exploratorio.py, línea 88; nota de la petición 21, punto 4"},
            {"nombre": "tope", "valor": f"una columna por cada {CASOS_POR_COLUMNA} fotos con fallo de entrenamiento", "origen": "método §7"},
        ],
        "teoria": TEORIA,
        "datos_personales": (
            ("Los datos son de discos: serial_number identifica un disco, no a una persona (reglas, apartado 9), y esta preselección no "
             "lo lee. No usa ni deja ninguna columna de datos personales. ")
            + ("" if proteccion else f"No existe {PROTECCION}: los datos no pasaron por la protección porque no hacía falta.")),
        "limites": [
            "La preselección se hizo una vez, sobre una muestra de entrenamiento, y su lista entra fija en cada pliegue del "
            "modelado: la validación cruzada del modelado sale algo optimista (método §9). Cuánto, NO SE PUEDE SABER sin medirlo.",
            "Los modelos auxiliares van sin búsqueda y solo ordenan; sus cifras no son rendimiento.",
            "El AUC de cada variable sola se mide en la misma muestra, con el valor en bruto y con cada tramo puntuado por su tasa de fallo: sirve para la alarma, no "
            "como medida del modelo.",
            "El parecido entre dos variables se mide solo con las fotos que tienen dato en las dos, para que el vacío de "
            "los contadores que solo registra algún modelo no fabrique parecidos; cada par dice con cuántas filas se midió.",
        ],
    }


def principal(raiz):
    """Lee, comprueba, selecciona con dos muestras, valida y escribe. Devuelve el código de salida."""
    inicio = time.time()
    res = base(raiz)
    lo = res["familias"]["logistica"]
    try:
        # 11.1 La fase anterior y la matriz aprobada (resultado.md, «Al empezar»)
        if not (raiz / PREPARACION).exists():
            raise Parada(f"falta {PREPARACION}", "PARADO")
        prep = json.loads((raiz / PREPARACION).read_text(encoding="utf-8"))
        res["leidos"].append(PREPARACION)
        res["entradas"].append({"ruta": PREPARACION, "estado": prep.get("resultado", {}).get("estado")})
        if prep.get("resultado", {}).get("estado") != "OK":
            raise Parada(f"{PREPARACION} no está en OK", "PARADO")
        if not (raiz / MATRIZ).exists():
            raise Parada(f"falta {MATRIZ}", "PARADO")
        mz = P13.leer_matriz((raiz / MATRIZ).read_text(encoding="utf-8"))
        res["leidos"].append(MATRIZ)
        res["entradas"].append({"ruta": MATRIZ, "sha256": sha256(raiz / MATRIZ), "estado": mz["estado"]})
        if not mz["aprobada_por"]:
            raise Parada("la matriz no está aprobada", "PARADO")
        # 11.2 La huella de entrenamiento, la que dejó la preparación
        ruta = raiz / ENTRENAMIENTO
        huella = sha256(ruta) if ruta.exists() else None
        esperada = next((e.get("sha256") for e in prep.get("entradas", []) if e.get("ruta") == ENTRENAMIENTO), None)
        res["entradas"].append({"ruta": ENTRENAMIENTO, "sha256": huella, "filas": pq.ParquetFile(ruta).metadata.num_rows if huella else None,
                                "columnas": len(pq.read_schema(ruta).names) if huella else None})
        if huella is None or huella != esperada:
            raise Parada(f"la huella de {ENTRENAMIENTO} no es la de {PREPARACION}", "PARADO")
        # 11.3 Lo que no puede entrar: la lista de la logística frente a la matriz (método §2)
        patrones = patrones_logistica(mz)
        prohibidas = sorted(set(mz["fuera"]) | set(mz["no_entran"]) | {OBJETIVO, HORIZONTE})
        solo_arboles = [f["variable"] for f in mz["filas"] if f["seccion"] == "entran" and f["variable"] not in mz["logistica"]]
        if sorted(patrones) != sorted(ENTRADA_LOGISTICA) or sorted(mz["logistica"]) != sorted(ENTRADA_LOGISTICA):
            raise Parada("las variables de la logística del script 13 no son las de la matriz aprobada")
        lo["fuera_de_entrada"] = ([{"columna": f["variable"], "motivo": f["motivo"]} for f in mz["filas"] if f["seccion"] == "fuera"]
                                  + [{"columna": v, "motivo": "no entra en la matriz"} for v in mz["no_entran"]]
                                  + [{"columna": v, "motivo": "solo en los árboles (matriz)"} for v in solo_arboles])
        for f in ("bosque", "hgb"):
            res["familias"][f]["fuera_de_entrada"] = lo["fuera_de_entrada"][: len(mz["fuera"]) + len(mz["no_entran"])]
        # 11.4 Las dos muestras de partida y el preprocesador ajustado con la de semilla 42 (cifra de control)
        muestras, total = leer_muestras(ruta, (SEMILLA, SEMILLA_2))
        res["leidos"].append(ENTRENAMIENTO)
        m42 = muestras[SEMILLA]
        y42 = m42[OBJETIVO].to_numpy().astype(np.int64)
        prueba = P13.preprocesador("logistica").fit(m42, y42)
        lo["recuento"] = {"variables_entrada": len(ENTRADA_LOGISTICA),
                          "columnas_preprocesador": int(prueba.transform(m42.iloc[:10]).shape[1]),
                          "fotos_entrenamiento": total["filas"], "fallos_entrenamiento": total["fallos"]}
        lo["muestra"] = {"usada": True, "partida": {"filas": len(m42), "fallos": int(y42.sum()), "sanas": int(len(m42) - y42.sum())},
                         "segunda_semilla": SEMILLA_2, "misma_lista": None, "filas": None, "entera": None, "meses": None,
                         "filas_objetivo": None}
        # 11.5 La selección con las dos muestras; si la lista cambia, se dobla, hasta la muestra entera
        tamano, r42 = FILAS_MUESTRA, None
        while True:
            s42, entera = meses_recientes(m42, tamano)
            s43, _ = meses_recientes(muestras[SEMILLA_2], tamano)
            r42 = seleccion(s42, total["fallos"], patrones)
            r43 = None if r42["parada"] else seleccion(s43, total["fallos"], patrones)
            intento = {"filas_objetivo": tamano, "entera": entera, "filas_semilla_42": r42["filas"],
                       "filas_semilla_43": r43["filas"] if r43 else None,
                       "variables_semilla_42": r42.get("variables_finales"), "variables_semilla_43": r43.get("variables_finales") if r43 else None,
                       "parada_semilla_43": r43["parada"] if r43 else None}
            intento["misma_lista"] = (None if r43 is None or r43["parada"] or r42["parada"]
                                      else sorted(r42["variables_finales"]) == sorted(r43["variables_finales"]))
            lo["intentos"].append(intento)
            lo["muestra"].update({"filas": r42["filas"], "entera": entera, "meses": r42["meses"], "filas_objetivo": tamano,
                                  "misma_lista": intento["misma_lista"]})
            if r42["parada"] or (r43 and r43["parada"]) or intento["misma_lista"] or entera:
                break
            tamano *= 2
        # 11.6 Lo que deja la selección con la muestra de semilla 42
        lo["alarmas_de_fuga"] = r42["alarmas_de_fuga"]
        lo["del_momento"] = r42["momento"]
        lo["sin_columnas"] = r42["sin_columnas"]
        lo["columnas_por_variable"] = r42["columnas_por_variable"]
        lo["muestra"]["columnas_preprocesador_muestra_usada"] = r42["columnas_preprocesador"]
        parada = r42["parada"] or (r43["parada"] if r43 else None)
        if parada:
            if r42["alarmas_de_fuga"]:
                res["pendientes"] = [{"id": "P-01", "tabla": ENTRENAMIENTO, "columna": a["columna"],
                                      "pregunta": "¿De dónde sale el dato y se conoce el día de la foto?",
                                      "opciones": ["se conoce a tiempo: entra", "se conoce después: sale de la matriz"]}
                                     for a in r42["alarmas_de_fuga"]]
            raise Parada(parada, "PARADO")
        for k in ("rankings", "rankings_por_variable", "cortes", "pares_parecidos", "tope", "variables_finales",
                  "columnas_finales", "pliegues_rfe", "apariciones_en_pares"):
            lo[k] = r42[k]
        lo["reserva_permutacion"] = r42["reserva"]
        lo["filas_de_cada_cifra"] = "entrenamiento: la muestra usada; la permutación, la reserva interna más reciente"
        lo["segundos"] = {k: r42[k] for k in ("segundos_mi", "segundos_rfe", "segundos_permutacion", "segundos")}
        lo["una_variante_por_variable"] = [{"origen": v, "clase": "familia", "columnas": r42["columnas_por_variable"][v],
                                            "se_queda": r42["columnas_por_variable"][v] if v in r42["variables_finales"] else [],
                                            "decidio": "regla"} for v in ENTRADA_LOGISTICA]
        # 11.7 Las seis validaciones de el método §8
        cols = r42["columnas_por_variable"]
        lo["validaciones"] = {
            "sin_validacion": v_sin_validacion(res["leidos"]),
            "origen_en_matriz": v_origen_en_matriz(r42["columnas_finales"], r42["origen"], mz["logistica"]),
            "familias_enteras": v_familias_enteras(r42["columnas_finales"], r42["variables_finales"], cols),
            "tope": v_tope(len(r42["columnas_finales"]), r42["tope"]["maximo_columnas"]),
            "sin_prohibidas": v_sin_prohibidas(r42["variables_finales"], prohibidas),
            "lista_valida": v_lista_valida(r42["variables_finales"], r42["columnas_finales"]),
        }
        rojas = [k for k, v in lo["validaciones"].items() if not v]
        if rojas:
            raise Parada("validaciones en rojo: " + ", ".join(rojas))
        estable = lo["muestra"]["misma_lista"]
        n_v, n_c = len(r42["variables_finales"]), len(r42["columnas_finales"])
        resumen = (f"La logística queda con {n_v} de sus {len(ENTRADA_LOGISTICA)} variables ({n_c} columnas en el ajuste con la "
                   f"muestra), por consenso amplio y con las cuatro obligatorias; los árboles reciben sus "
                   f"{len(ENTRADA_ARBOLES)} columnas sin votar.")
        if estable:
            res["resultado"] = {"estado": "OK", "riesgo": "bajo", "resumen": resumen + " La segunda muestra da la misma lista.",
                                "artefactos": [SALIDA_JSON, SALIDA_MD], "siguiente": "aprendizaje-automatico (petición 21, segunda parte)"}
        else:
            res["pendientes"] = [{"id": "P-01", "tabla": ENTRENAMIENTO, "columna": "",
                                  "pregunta": "La lista cambia con la segunda muestra aun con la muestra de partida entera: ¿se sigue con la de semilla 42?",
                                  "opciones": ["seguir con la de semilla 42", "otro criterio"]}]
            res["resultado"] = {"estado": "AVISO", "riesgo": "medio",
                                "resumen": resumen + " La segunda muestra da otra lista aun con la muestra entera: el detalle está en «intentos».",
                                "artefactos": [SALIDA_JSON, SALIDA_MD], "siguiente": "decidir P-01 antes de aprendizaje-automatico"}
        codigo = 0
    except Parada as p:
        res["resultado"] = {"estado": p.estado, "riesgo": "alto", "resumen": f"El script paró: {p}"[:2000],
                            "artefactos": [SALIDA_JSON, SALIDA_MD], "siguiente": "resolver la causa y volver a ejecutar; el modelado no empieza"}
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
