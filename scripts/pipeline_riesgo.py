"""Módulo de producción del caso 68: el riesgo de fallo de cada disco a 30 días (método preproduccion §2.1).

Trae, según el contrato aprobado (config/modelo/contrato_produccion.md e informes/preproduccion.json):
  - lo que no aprende y lo que necesita otras filas, para pasar una foto mensual en bruto a las columnas del modelo:
    el nombre del modelo, la capacidad del modelo, la capacidad en TB, el tipo de disco, el fabricante, la garantía, la
    edad, los avisos y los cambios contra la foto anterior (P01 a P15 del contrato);
  - la función que construye el Pipeline nuevo cada vez: el preprocesador del HistGradientBoosting (numéricas tal cual,
    el centro vaciado, las categorías raras y el código ordinal), la salida en float32, la columna sin ningún dato fuera
    y el modelo con su recalibración (P20 a P25);
  - guardar el modelo con su ficha y cargarlo solo si la ficha cuadra (manual 39.11);
  - el informe informes/preproduccion.md, generado de informes/preproduccion.json.

Las listas de columnas se leen del contrato, nunca se escriben aquí. Lo que viene del desarrollo (scripts 03, 05, 13 y
15) se ha pasado a este módulo, que no importa ningún script numerado. Importarlo no ejecuta nada.

Uso, solo para recalcular el estado y regenerar el informe: python -W error scripts/pipeline_riesgo.py --informe [--raiz CARPETA_DEL_CASO]
"""

# =================================================================================================================
# 1. Configuración
# =================================================================================================================
import argparse
import hashlib
import json
import platform
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import sklearn
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OrdinalEncoder

CASO = Path(__file__).resolve().parents[1]
CONTRATO_JSON = "informes/preproduccion.json"
INFORME_MD = "informes/preproduccion.md"

# Reglas de negocio §3 y §7 (scripts/05_transformacion_datos.py): arranque hasta este límite, datos por encima
LIMITE_ARRANQUE_BYTES = 2_048_408_248_320
# Convención técnica 1 de las reglas de transformación: el año de edad son 8.766 horas; sin horas, días entre 365,25
HORAS_ANO, DIAS_ANO = 8766.0, 365.25
# Los cinco contadores de avería (reglas, apartado 3) y los cuatro que llevan cambio y suma (sin el 188)
CONTADORES = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]
CONTADORES_SIN_188 = ["smart_5_raw", "smart_187_raw", "smart_197_raw", "smart_198_raw"]
# El fabricante por el nombre del modelo (reglas, apartado 3)
FABRICANTE_EXCEPCIONES = {"Hitachi HDS5C4040ALE630": "HGST", "WUH721816ALE6L4": "WDC"}
FABRICANTE_PREFIJOS = [("TOSHIBA", "Toshiba"), ("WDC", "WDC"), ("HGST", "HGST")]
# Las categorías raras (matriz, P-03; scripts/13_preparacion.py)
ETIQUETA_OTRAS, SIN_DATO = "otras", "sin dato"
MINIMO_FOTOS, MINIMO_FALLOS, MINIMO_SANAS = 30, 20, 20
# Los motivos de una fila que no se puntúa (método §2.3)
MOTIVO_ARRANQUE = "disco de arranque: fuera del modelo (reglas, apartado 3 y §7)"
MOTIVO_DIA_FALLO = "foto del día del fallo: el disco ya está marcado como fallado (reglas de transformación §3)"
MOTIVO_SIN_CAPACIDAD = "modelo sin ninguna capacidad válida hasta la fecha de la foto"
MOTIVO_DOS_CAPACIDADES = "modelo con dos capacidades válidas: la regla, apartado 3 no se puede aplicar"
MOTIVO_EDAD = "edad negativa o vacía"
# Las columnas que no son números en la foto en bruto
TEXTOS = {"serial_number", "model", "datacenter", "date"}


class ErrorDeProduccion(Exception):
    """Una comprobación de producción no pasa: el script para con un mensaje claro."""


# =================================================================================================================
# 2. El contrato
# =================================================================================================================
def leer_contrato(raiz):
    """Lee el contrato aprobado de informes/preproduccion.json y saca de él las listas de columnas y la receta.

    Para si el contrato no está aprobado. Las listas salen de la cadena de cada finalista: entran al preprocesador las
    que pasan por P20 (numéricas) o P22 (categorías); se vacían las que pasan por P21.
    """
    ruta = Path(raiz) / CONTRATO_JSON
    if not ruta.exists():
        raise ErrorDeProduccion(f"no existe {CONTRATO_JSON}: falta el contrato")
    js = json.loads(ruta.read_text(encoding="utf-8"))
    if not (js.get("contrato") or {}).get("aprobado_por"):
        raise ErrorDeProduccion("el contrato de producción no está aprobado (contrato.aprobado_por vacío)")

    def pasa(f, paso):
        return any(p["paso"].startswith(paso + " ") for p in f["cadena"])

    fin = js["finalistas"]
    lee = [f["variable"] for f in fin if pasa(f, "P20") or pasa(f, "P22")]
    nominales = [f["variable"] for f in fin if pasa(f, "P22")]
    numericas = [v for v in lee if v not in nominales]
    receta = js["receta"]
    if receta["fijos"]["early_stopping"] is not False:
        raise ErrorDeProduccion("la receta del contrato no trae early_stopping=False")
    return {"lee": lee, "numericas": numericas, "nominales": nominales,
            "vaciar": [f["variable"] for f in fin if pasa(f, "P21")],
            "esperadas": numericas + [f"{v}_oe" for v in nominales],
            "categoricas": list(receta["fijos"]["categorical_features"]),
            "receta": receta, "corte": receta["corte"], "entrada": list(js["entrada_de_ejecutar"]["columnas_que_lee"]),
            "aprobado_por": js["contrato"]["aprobado_por"]}


# =================================================================================================================
# 3. Lo que no aprende: reglas fijas sobre la propia fila (P03, P07 a P10, P13)
# =================================================================================================================
def capacidad_en_tb(capacity_bytes):
    """capacity_bytes entre 10^12, redondeada a un decimal con el medio hacia arriba, como Excel (P07)."""
    return float((Decimal(int(capacity_bytes)) / Decimal(10**12)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fabricante(modelo):
    """Fabricante por el nombre del modelo, con las dos excepciones de las reglas, apartado 3; None si no sigue ningún patrón (P09)."""
    if modelo in FABRICANTE_EXCEPCIONES:
        return FABRICANTE_EXCEPCIONES[modelo]
    if modelo.startswith("ST"):
        return "Seagate"
    for prefijo, nombre in FABRICANTE_PREFIJOS:
        if modelo.startswith(prefijo):
            return nombre
    return None


def garantia(modelo, fab):
    """Años de garantía por familia (reglas, apartado 6); None sin garantía comprobada (P10)."""
    if fab == "Seagate" and "NM" in modelo:
        return 5
    if fab == "Seagate" and "DM" in modelo:
        return 2
    if "HMS5C" in modelo:
        return 3
    if any(f in modelo for f in ("HUH", "HUS", "WUH")) or modelo.startswith("TOSHIBA MG"):
        return 5
    return None


def avisos(df):
    """avisa, contadores_que_avisan, suma_contadores_sin_188 y smart_188_no_cero; un vacío no cuenta como aviso (P13)."""
    positivos = df[CONTADORES] > 0
    return pd.DataFrame({
        "avisa": positivos.any(axis=1),
        "contadores_que_avisan": positivos.sum(axis=1).astype("int64"),
        "suma_contadores_sin_188": df[CONTADORES_SIN_188].sum(axis=1, min_count=1),
        "smart_188_no_cero": pd.array(np.where(df["smart_188_raw"].isna(), None,
                                               (df["smart_188_raw"] > 0).astype("int64")), dtype="Int8"),
    }, index=df.index)


# =================================================================================================================
# 4. Lo que necesita otras filas: la historia hasta el día de la foto (P04, P06, P12, P14)
# =================================================================================================================
def _fecha_de_texto(serie):
    """El texto date de una ventana como fecha; si ya es fecha, igual."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    return pd.to_datetime(serie, format="%Y-%m-%d")


def ventanas_utiles(ventanas, fecha):
    """Las filas de ventana que cuentan el día de la foto: fallos ya ocurridos (dia_fallo anterior a la foto, el arreglo
    de el responsable del caso del 19/11/2026) y sin las filas cuya fecha no es la de su texto (R-007)."""
    v = ventanas.loc[(ventanas["dia_fallo"] < fecha).to_numpy()]
    return v.loc[(_fecha_de_texto(v["date"]) == v["fecha"]).to_numpy()]


def historia_de(fotos_anteriores, ventanas, fecha, mapeo, pares_fotos=None):
    """Lo que la historia aporta a una foto: los pares (modelo, capacidad), la última foto anterior de cada disco, su
    primera foto y su primer día de ventana. Solo usa filas anteriores a la foto (ventanas: de fallos ya ocurridos).

    pares_fotos: los pares (modelo, capacidad) de todas las fotos anteriores, si fotos_anteriores trae solo algunos
    discos (leer_historia); si no, salen de fotos_anteriores.
    """
    fa = fotos_anteriores.loc[(fotos_anteriores["fecha"] < fecha).to_numpy()].copy()
    v = ventanas_utiles(ventanas, fecha).copy()
    fa["model"] = fa["model"].replace(mapeo)
    v["model"] = v["model"].replace(mapeo)
    pares = pares_fotos if pares_fotos is not None else fa[["model", "capacity_bytes"]]
    pares = pd.concat([pares, v[["model", "capacity_bytes"]]], ignore_index=True).drop_duplicates()
    ordenadas = fa.sort_values(["serial_number", "fecha"], kind="stable")
    ultima = ordenadas.drop_duplicates("serial_number", keep="last").set_index("serial_number")
    anterior = ultima[["fecha", *CONTADORES_SIN_188]].rename(columns={"fecha": "fecha_ant",
                                                                     **{c: f"ant_{c}" for c in CONTADORES_SIN_188}})
    return {"fecha": fecha, "pares": pares, "anterior": anterior,
            "primera_foto": fa.groupby("serial_number")["fecha"].min(),
            "primer_dia_ventana": v.groupby("serial_number")["fecha"].min()}


def _leer_columnas(ruta, columnas):
    """Las columnas de un Parquet que existan en él; las que no trae llegan vacías (R-008)."""
    nombres = pq.read_schema(ruta).names
    t = pq.read_table(ruta, columns=[c for c in columnas if c in nombres])
    df = t.to_pandas()
    for c in columnas:
        if c not in df.columns:
            df[c] = np.nan
    return df[columnas]


def leer_historia(dir_fotos, dir_ventanas, fecha, mapeo, discos):
    """Lee la historia en bruto hasta el día de la foto: las fotos mensuales anteriores y las ventanas de fallo.

    De las fotos guarda los pares (modelo, capacidad) de todos los discos y las filas de los discos de la foto; de las
    ventanas, las de fallos anteriores a la foto.
    """
    fecha = pd.Timestamp(fecha)
    pares, filas = [], []
    for ruta in sorted(Path(dir_fotos).glob("*.parquet")):
        df = _leer_columnas(ruta, ["serial_number", "fecha", "model", "capacity_bytes", *CONTADORES_SIN_188])
        df = df.loc[(df["fecha"] < fecha).to_numpy()]
        if df.empty:
            continue
        pares.append(df[["model", "capacity_bytes"]].drop_duplicates())
        filas.append(df.loc[df["serial_number"].isin(discos).to_numpy()])
    columnas_f = ["serial_number", "fecha", "model", "capacity_bytes", *CONTADORES_SIN_188]
    fotos = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame(columns=columnas_f)
    p = pd.concat(pares, ignore_index=True) if pares else pd.DataFrame(columns=["model", "capacity_bytes"])
    p["model"] = p["model"].replace(mapeo)
    ventanas = []
    for ruta in sorted(Path(dir_ventanas).glob("*.parquet")):
        df = _leer_columnas(ruta, ["serial_number", "fecha", "date", "dia_fallo", "model", "capacity_bytes"])
        ventanas.append(df.loc[(df["dia_fallo"] < fecha).to_numpy()])
    v = (pd.concat(ventanas, ignore_index=True) if ventanas else
         pd.DataFrame(columns=["serial_number", "fecha", "date", "dia_fallo", "model", "capacity_bytes"]))
    return historia_de(fotos, v, fecha, mapeo, pares_fotos=p.drop_duplicates())


def leer_foto(ruta, columnas):
    """Lee la foto en bruto y comprueba las columnas que pide el contrato: que están todas, por nombre, y que ningún
    número llega como texto. Una columna sin tipo (vacía entera) pasa a número o a texto según su papel."""
    esquema = pq.read_schema(ruta)
    faltan = [c for c in columnas if c not in esquema.names]
    if faltan:
        raise ErrorDeProduccion(f"faltan columnas en la foto {Path(ruta).name}: {faltan}")
    texto = [c for c in columnas if c not in TEXTOS and c != "fecha"
             and (pa.types.is_string(esquema.field(c).type) or pa.types.is_large_string(esquema.field(c).type))]
    if texto:
        raise ErrorDeProduccion(f"columnas numéricas que llegan como texto en {Path(ruta).name}: {texto}")
    t = pq.read_table(ruta, columns=columnas)
    for c in columnas:
        if pa.types.is_null(t.schema.field(c).type):
            i = t.schema.get_field_index(c)
            t = t.set_column(i, c, t[c].cast(pa.string() if c in TEXTOS else pa.float64()))
    return t.to_pandas()


def capacidades_del_modelo(pares, minimo):
    """La capacidad válida de cada modelo: la única que trae; None si trae dos (P04, regla, apartado 3)."""
    validas = pares.loc[(pares["capacity_bytes"] >= minimo).to_numpy()].drop_duplicates()
    cuantas = validas.groupby("model")["capacity_bytes"].nunique()
    unica = validas.loc[validas["model"].isin(cuantas.index[cuantas == 1])].set_index("model")["capacity_bytes"]
    return unica.astype("float64").to_dict(), set(cuantas.index[cuantas > 1])


def preparar_foto(foto, historia, mapeo, minimo):
    """Pasa la foto en bruto a las columnas del modelo, sin quitar ninguna fila (P01 a P15).

    Devuelve la tabla, con una fila por fila de la foto y en su orden, y el motivo de cada fila que no se puede
    puntuar (texto vacío si se puede).
    """
    df = foto.reset_index(drop=True).copy()
    fecha = historia["fecha"]
    if not (df["fecha"] == fecha).all():
        raise ErrorDeProduccion(f"la foto trae filas de otra fecha que la de su historia ({fecha.date()})")
    # P02 y P03: el centro como texto y el nombre del modelo con el mapeo cerrado
    df["datacenter"] = df["datacenter"].astype(object).where(df["datacenter"].notna(), None)
    df["model"] = df["model"].replace(mapeo)
    # P04 y P07 a P10: la capacidad del modelo, en TB, el tipo, el fabricante y la garantía
    pares = pd.concat([historia["pares"], df[["model", "capacity_bytes"]]], ignore_index=True)
    capacidad, dobles = capacidades_del_modelo(pares, minimo)
    cap = df["model"].map(capacidad)
    df["capacidad_tb"] = [capacidad_en_tb(c) if pd.notna(c) else np.nan for c in cap]
    tipo = np.where(cap.isna(), None, np.where(cap <= LIMITE_ARRANQUE_BYTES, "arranque", "datos"))
    df["fabricante"] = [fabricante(m) for m in df["model"]]
    df["garantia_anos"] = pd.array([garantia(m, f) if t == "datos" else None
                                    for m, f, t in zip(df["model"], df["fabricante"], tipo)], dtype="Int64")
    # P12: la edad, con horas o desde la primera aparición (primera foto o primer día de una ventana ya ocurrida)
    pf = df["serial_number"].map(historia["primera_foto"]).astype("datetime64[ms]").fillna(fecha)
    pv = df["serial_number"].map(historia["primer_dia_ventana"]).astype("datetime64[ms]")
    primera = pf.where(pv.isna() | (pf <= pv), pv)
    desde = (fecha - primera) / pd.Timedelta(days=1)
    con_horas = df["smart_9_raw"].notna()
    df["edad_anos"] = np.where(con_horas, df["smart_9_raw"] / HORAS_ANO, desde / DIAS_ANO)
    # P13: los avisos
    df = pd.concat([df, avisos(df)], axis=1)
    # P14: los cambios contra la foto anterior del mismo disco
    df = df.merge(historia["anterior"], left_on="serial_number", right_index=True, how="left", validate="many_to_one")
    for c in CONTADORES_SIN_188:
        df[f"cambio_{c.replace('_raw', '')}"] = df[c] - df[f"ant_{c}"]
    fa = df["fecha_ant"]
    df["meses_desde_foto_anterior"] = ((fecha.year - fa.dt.year) * 12 + (fecha.month - fa.dt.month)).astype("Int64")
    df = df.drop(columns=["fecha_ant", *[f"ant_{c}" for c in CONTADORES_SIN_188]])
    # P11: el motivo de lo que no se puntúa; la fila se queda
    motivo = np.full(len(df), "", dtype=object)
    edad_mala = ~(df["edad_anos"] >= 0)
    for mascara, texto in ((edad_mala.to_numpy(), MOTIVO_EDAD), (df["model"].isin(dobles).to_numpy(), MOTIVO_DOS_CAPACIDADES),
                           (cap.isna().to_numpy() & ~df["model"].isin(dobles).to_numpy(), MOTIVO_SIN_CAPACIDAD),
                           ((df["failure"] == 1).to_numpy(), MOTIVO_DIA_FALLO), (tipo == "arranque", MOTIVO_ARRANQUE)):
        motivo[mascara] = texto
    if len(df) != len(foto):
        raise ErrorDeProduccion("preparar la foto cambió el número de filas")
    return df, motivo


# =================================================================================================================
# 5. Las piezas del Pipeline (P20 a P25)
# =================================================================================================================
def _llega(n, f, minimos=(MINIMO_FOTOS, MINIMO_FALLOS, MINIMO_SANAS)):
    """Cierto si un grupo tiene las fotos, los fallos y las sanas mínimos."""
    return n >= minimos[0] and f >= minimos[1] and n - f >= minimos[2]


def vaciar_sitio(X, columnas=("datacenter",)):
    """El centro vaciado: el sitio no entró en el modelo (P21). No aprende nada."""
    X = pd.DataFrame(X).copy()
    for c in columnas:
        if c in X.columns:
            X[c] = pd.Series([None] * len(X), index=X.index, dtype=object)
    return X


def a_float32(X):
    """La salida del preprocesador en float32, como la entrenó el modelado."""
    return pd.DataFrame(X).astype(np.float32)


class AgruparRaras(BaseEstimator, TransformerMixin):
    """Nominales: el vacío a «sin dato» y las categorías raras a «otras», aprendidas en fit con el objetivo (P22).

    Una categoría es rara si en el ajuste tiene menos fotos, fallos o sanas que los mínimos. Una categoría que no se
    vio en el ajuste va a «otras» si existe y, si no, a la referencia, la categoría con más fotos de las que se quedan
    (matriz, P-03). Así el codificador de detrás no ve nunca una categoría nueva. Es la de scripts/13_preparacion.py.
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


class QuitarVacias(BaseEstimator, TransformerMixin):
    """Una columna sin ningún dato en las filas del ajuste sale, como en el modelado (el HistGradientBoosting no puede
    hacer sus tramos); aprende en fit cuáles son."""

    def fit(self, X, y=None):
        """Aprende las columnas vacías enteras."""
        X = pd.DataFrame(X)
        self.columnas_vacias_ = [c for c in X.columns if X[c].isna().all()]
        self.columnas_ = [c for c in X.columns if c not in self.columnas_vacias_]
        return self

    def transform(self, X):
        """Quita las columnas vacías del ajuste."""
        return pd.DataFrame(X).drop(columns=self.columnas_vacias_)

    def get_feature_names_out(self, input_features=None):
        """Las columnas que quedan."""
        return np.asarray(self.columnas_, dtype=object)


def recalibrar(p, tasa_muestra, tasa_real):
    """Corrección del prior sobre el logit: la probabilidad aprendida con la muestra pasa a la escala real (P25)."""
    p = np.clip(np.asarray(p, dtype=float), 1e-15, 1 - 1e-15)
    odds = p / (1 - p) * (tasa_real / (1 - tasa_real)) / (tasa_muestra / (1 - tasa_muestra))
    return odds / (1 + odds)


def hoja_de(filas):
    """La hoja mínima: max(20, 1 % de las filas que entrenan), redondeada al entero (receta del contrato)."""
    return max(20, int(np.floor(0.01 * filas + 0.5)))


class HGBRecalibrado(ClassifierMixin, BaseEstimator):
    """El HistGradientBoosting de la receta con la probabilidad recalibrada (P24 y P25).

    En fit pone la hoja con las filas que entrenan y mide la tasa de la muestra; la tasa real del entrenamiento, que se
    mide antes de la muestra, la pone reentrenar.py en tasa_real.
    """

    def __init__(self, max_iter=500, learning_rate=0.025, max_depth=None, l2_regularization=0.5, min_samples_leaf="hoja",
                 categorical_features=None, random_state=42, tasa_real=None):
        self.max_iter = max_iter
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.l2_regularization = l2_regularization
        self.min_samples_leaf = min_samples_leaf
        self.categorical_features = categorical_features
        self.random_state = random_state
        self.tasa_real = tasa_real

    def fit(self, X, y):
        """Entrena el HistGradientBoosting y mide la tasa de la muestra."""
        if self.tasa_real is None:
            raise ErrorDeProduccion("falta la tasa real del entrenamiento (tasa_real): la pone reentrenar.py")
        y = np.asarray(y).astype(np.int64)
        hoja = hoja_de(len(y)) if self.min_samples_leaf == "hoja" else int(self.min_samples_leaf)
        cat = [c for c in (self.categorical_features or []) if c in X.columns]
        self.modelo_ = HistGradientBoostingClassifier(
            early_stopping=False, random_state=self.random_state, categorical_features=cat, min_samples_leaf=hoja,
            max_iter=self.max_iter, max_depth=self.max_depth, learning_rate=self.learning_rate,
            l2_regularization=self.l2_regularization).fit(X, y)
        self.tasa_muestra_ = float(np.mean(y))
        self.classes_ = self.modelo_.classes_
        return self

    def predict_proba(self, X):
        """La probabilidad recalibrada, en las dos columnas de scikit-learn."""
        p = recalibrar(self.modelo_.predict_proba(X)[:, 1], self.tasa_muestra_, self.tasa_real)
        return np.column_stack([1 - p, p])

    def predict(self, X):
        """No se usa: el caso decide con listas, no con el corte de 0,5 (pipelines.md, regla 9)."""
        raise ErrorDeProduccion("predict no se usa en este caso: el corte son las listas de cada foto mensual")


def construir_pipeline(contrato, tasa_real=None):
    """El Pipeline sin entrenar, construido nuevo en cada llamada, con las listas del contrato (pipelines.md, reglas 1 a 15)."""
    h = contrato["receta"]["hiperparametros"]
    categorias = Pipeline([
        ("sitio", FunctionTransformer(vaciar_sitio, kw_args={"columnas": tuple(contrato["vaciar"])},
                                      feature_names_out="one-to-one")),
        ("raras", AgruparRaras(sufijo="_oe")),
        ("codigo", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan, encoded_missing_value=np.nan)),
    ])
    ct = ColumnTransformer([("numericas", "passthrough", list(contrato["numericas"])),
                            ("categorias", categorias, list(contrato["nominales"]))],
                           remainder="drop", verbose_feature_names_out=False).set_output(transform="pandas")
    modelo = HGBRecalibrado(max_iter=h["max_iter"], learning_rate=h["learning_rate"], max_depth=h["max_depth"],
                            l2_regularization=h["l2_regularization"], min_samples_leaf=h["min_samples_leaf"],
                            categorical_features=list(contrato["categoricas"]),
                            random_state=contrato["receta"]["fijos"]["random_state"], tasa_real=tasa_real)
    return Pipeline([("preparacion", ct), ("float32", FunctionTransformer(a_float32, feature_names_out="one-to-one")),
                     ("sin_vacias", QuitarVacias()), ("modelo", modelo)])


def comprobar_columnas_de_salida(pipe, esperadas):
    """Para si el Pipeline ajustado no da al modelo exactamente las columnas esperadas, menos las vacías del ajuste
    (manual 39.11; remainder="drop" tira en silencio)."""
    vacias = pipe.named_steps["sin_vacias"].columnas_vacias_
    salen = list(pipe[:-1].get_feature_names_out())
    quedan = [c for c in esperadas if c not in vacias]
    if salen != quedan:
        raise ErrorDeProduccion(f"columnas de salida distintas de las del contrato; faltan {[c for c in quedan if c not in salen]}, "
                                f"sobran {[c for c in salen if c not in quedan]}")
    return salen


def estructura(pipe):
    """Lo que hay dentro del Pipeline, para la ficha: pasos, ramas con sus columnas, remainder, columnas de salida,
    columnas vacías del ajuste, categorías aprendidas y el modelo (pipelines.md, regla 8)."""
    ct = pipe.named_steps["preparacion"]
    raras = ct.named_transformers_["categorias"].named_steps["raras"] if hasattr(ct, "named_transformers_") else None
    m = pipe.named_steps["modelo"]
    return {"pasos": list(pipe.named_steps),
            "ramas": [{"nombre": n, "pasos": (list(t.named_steps) if isinstance(t, Pipeline) else str(t)), "columnas": list(c)}
                      for n, t, c in ct.transformers],
            "remainder": ct.remainder,
            "columnas_salida": list(pipe[:-1].get_feature_names_out()) if hasattr(m, "modelo_") else None,
            "columnas_vacias_del_ajuste": getattr(pipe.named_steps["sin_vacias"], "columnas_vacias_", None),
            "categorias": ({c: {"quedan": raras.quedan_[c], "otras": raras.otras_[c], "referencia": raras.referencia_[c]}
                            for c in raras.columnas_} if raras is not None and hasattr(raras, "quedan_") else None),
            "modelo": {"parametros": {k: v for k, v in m.get_params().items()},
                       "iteraciones": int(m.modelo_.n_iter_) if hasattr(m, "modelo_") else None,
                       "tasa_muestra": getattr(m, "tasa_muestra_", None), "tasa_real": m.tasa_real}}


def filas_dentro(objeto, n, ruta="modelo", vistos=None, profundidad=0):
    """Busca en el objeto ajustado matrices con tantas filas como el entrenamiento: si las hay, el modelo guarda
    filas de entrenamiento (método §2.2, paso 5). Devuelve dónde."""
    vistos = set() if vistos is None else vistos
    if id(objeto) in vistos or profundidad > 6:
        return []
    vistos.add(id(objeto))
    hallado = []
    if isinstance(objeto, (np.ndarray, pd.DataFrame, pd.Series)):
        return [ruta] if len(objeto) == n and n > 1 else []
    if isinstance(objeto, dict):
        for k, v in objeto.items():
            hallado += filas_dentro(v, n, f"{ruta}[{k!r}]", vistos, profundidad + 1)
    elif isinstance(objeto, (list, tuple)):
        if len(objeto) == n and n > 1:
            return [ruta]
        for i, v in enumerate(objeto):
            hallado += filas_dentro(v, n, f"{ruta}[{i}]", vistos, profundidad + 1)
    elif hasattr(objeto, "__dict__"):
        for k, v in vars(objeto).items():
            hallado += filas_dentro(v, n, f"{ruta}.{k}", vistos, profundidad + 1)
    return hallado


# =================================================================================================================
# 6. Guardar y cargar el modelo con su ficha (manual 39.7 y 39.11)
# =================================================================================================================
def huella(ruta):
    """SHA-256 de un fichero."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def versiones():
    """Las versiones que deciden si un modelo guardado se puede cargar aquí."""
    return {"python": platform.python_version(), "scikit-learn": sklearn.__version__, "pandas": pd.__version__,
            "numpy": np.__version__, "joblib": joblib.__version__}


def ruta_ficha(ruta):
    """La ficha de un modelo: <nombre>_versiones.json, al lado."""
    ruta = Path(ruta)
    return ruta.with_name(f"{ruta.stem}_versiones.json")


def guardar_modelo(pipe, ruta, **datos):
    """Guarda el Pipeline con joblib y, al lado, su ficha con versiones, huellas del fichero y del módulo, y fecha."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, ruta)
    ficha = {"fecha": datetime.now().isoformat(timespec="seconds"), "fichero": ruta.name, "huella": huella(ruta),
             "modulo": "scripts/pipeline_riesgo.py", "huella_modulo": huella(Path(__file__)), "versiones": versiones()} | datos
    ruta_ficha(ruta).write_text(json.dumps(ficha, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    return ficha


def cargar_modelo(ruta):
    """Carga el Pipeline solo si su ficha cuadra: mismas versiones de scikit-learn y pandas, el mismo fichero y el
    mismo módulo. Un joblib ejecuta código al abrirse: la ficha se lee antes y se para si algo no cuadra."""
    ruta = Path(ruta)
    if not ruta.exists() or not ruta_ficha(ruta).exists():
        raise ErrorDeProduccion(f"no existe el modelo {ruta.name} o su ficha")
    ficha = json.loads(ruta_ficha(ruta).read_text(encoding="utf-8"))
    actuales = versiones()
    distintas = {k: (ficha["versiones"][k], actuales[k]) for k in ("scikit-learn", "pandas") if ficha["versiones"][k] != actuales[k]}
    if distintas:
        raise ErrorDeProduccion(f"el modelo se guardó con otras versiones (guardado, actual): {distintas}")
    if huella(ruta) != ficha["huella"]:
        raise ErrorDeProduccion(f"{ruta.name} no es el fichero que se guardó: su huella no coincide con la de la ficha")
    if huella(Path(__file__)) != ficha["huella_modulo"]:
        raise ErrorDeProduccion("scripts/pipeline_riesgo.py cambió después de guardar el modelo: su huella no es la de la ficha")
    return joblib.load(ruta), ficha


# =================================================================================================================
# 7. El JSON de preproducción y su informe (resultado.md; transmision-conocimiento)
# =================================================================================================================
def actualizar_json(raiz, cambios, validaciones=None):
    """Escribe en informes/preproduccion.json las secciones que deja un script (reentreno, lote, prueba)."""
    ruta = Path(raiz) / CONTRATO_JSON
    js = json.loads(ruta.read_text(encoding="utf-8"))
    js.update(cambios)
    js["validaciones"].update(validaciones or {})
    # El estado sigue a las validaciones: una en rojo es ERROR; alguna sin ejecutar, AVISO; todas en verde, OK
    rojas = [k for k, v in js["validaciones"].items() if v is False]
    faltan = [k for k, v in js["validaciones"].items() if v is None]
    aprobado = f"Contrato aprobado ({js['contrato']['aprobado_por']})"
    if rojas:
        js["resultado"]["estado"] = "ERROR"
        js["resultado"]["resumen"] = f"{aprobado}. Validaciones en rojo: {', '.join(rojas)}."
    elif faltan:
        js["resultado"]["estado"] = "AVISO"
        js["resultado"]["resumen"] = f"{aprobado}. Validaciones sin ejecutar todavía con los datos del caso: {', '.join(faltan)}."
    else:
        js["resultado"]["estado"] = "OK"
        js["resultado"]["resumen"] = f"{aprobado}. Las {len(js['validaciones'])} validaciones, en verde."
    ruta.write_text(json.dumps(js, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    escribir_informe(raiz)
    return js


def _n(x, d=None):
    """Un número a la española; «sin dato» si falta."""
    if x is None:
        return "sin dato"
    if d is None:
        return f"{int(x):,}".replace(",", ".")
    return f"{x:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def informe_md(js):
    """El informe para la persona, generado del JSON, con los apartados de resultado.md."""
    r, rc = js["resultado"], js["receta"]
    L = ["# Preproducción del caso 68", "",
         f"**Estado: {r['estado']}.** {r['resumen']}", "",
         "## Las finalistas y su cadena", "",
         f"El modelo usa {len([f for f in js['finalistas'] if f['columnas_del_modelo']])} columnas y lee "
         f"{len([f for f in js['finalistas'] if any(p['paso'][:3] in ('P20', 'P22') for p in f['cadena'])])} variables, "
         f"porque también lee datacenter y lo vacía. Con el identificador, el objetivo y su horizonte son "
         f"{len(js['finalistas'])} finalistas, todas con su cadena de pasos en el contrato.", "",
         "## El contrato", "",
         f"Aprobación: {js['contrato']['aprobado_por']}. Está en `{js['contrato']['ruta']}`: "
         f"{len(js['pasos'])} pasos, cada uno con su clase, la receta del {rc['algoritmo']} y el corte, las listas de "
         f"{', '.join(map(str, rc['corte']['valores']))} discos de cada foto mensual, con la de {rc['corte']['principal']} como principal.", "",
         "## Qué hace cada script", "",
         f"- `{js['codigo']['modulo']}`: pasa la foto en bruto a las columnas del modelo y construye el Pipeline nuevo cada vez.",
         f"- `{js['codigo']['reentrenar']}`: rehace el modelo con la receta fija y lo deja aparte, con su ficha; no sustituye el modelo en uso.",
         f"- `{js['codigo']['ejecutar']}`: puntúa una foto mensual sin quitar ninguna fila; lo que no puntúa sale con su motivo.",
         f"- `{js['codigo']['prueba']}`: rehace la puntuación por otro camino, sin cargar el modelo, y la compara fila a fila.", "",
         "## El reentreno", ""]
    re_ = js.get("reentreno")
    if re_:
        L += [f"Tabla `{re_['tabla']}`, {_n(re_['filas_entrada'])} fotos. Quitadas: "
              + "; ".join(f"{q['motivo']}, {_n(q['filas'])}" for q in re_["filas_quitadas"]) + ".",
              f"Modelo en uso: {'sí' if re_['modelo_en_uso']['existia'] else 'no'} ({re_['modelo_en_uso']['de_donde']}). "
              f"Igual a lo que guardó el modelado o al modelo en uso: {re_['igual_bit_a_bit']}. Guardado en `{re_['ruta']}`.", ""]
    else:
        L += ["Todavía no se ha ejecutado con los datos del caso: lo hace la sesión principal.", ""]
    L += ["## El lote", ""]
    lo = js.get("lote")
    if lo:
        L += [f"Entrada `{lo['ruta']}`: {_n(lo['filas_entrada'])} filas y {_n(lo['filas_salida'])} de salida. Sin puntuar: "
              + ("; ".join(f"{s['motivo']}, {_n(s['filas'])}" for s in lo["sin_puntuar"]) or "ninguna") + ".", ""]
    else:
        L += ["Todavía no se ha ejecutado con los datos del caso. No hay lote de producción apartado: la prueba final es la "
              "reserva, fuera del caso (R-020).", ""]
    L += ["## La prueba por otro camino", ""]
    pr = js.get("prueba_por_otro_camino")
    L += [(f"Coincide: {pr['coincide']}, con tolerancia {pr['tolerancia']}; con la salida estropeada da rojo: "
           f"{pr['rojo_con_estropeada']}." if pr else "Todavía no se ha ejecutado con los datos del caso."), "",
          "## Validaciones", ""]
    L += [f"- {k}: {'sí' if v is True else 'no' if v is False else 'sin ejecutar'}" for k, v in js["validaciones"].items()]
    L += ["", "## Parámetros usados", ""]
    L += [f"- {p['nombre']}: {p['valor']} ({p['origen']})" for p in js.get("parametros", [])]
    L += ["", "## Datos personales", "", js.get("datos_personales") or "Sin datos personales.", "", "## Límites", ""]
    L += [f"- {x}" for x in js.get("limites", [])]
    return "\n".join(L) + "\n"


def escribir_informe(raiz):
    """Escribe informes/preproduccion.md a partir de informes/preproduccion.json."""
    js = json.loads((Path(raiz) / CONTRATO_JSON).read_text(encoding="utf-8"))
    (Path(raiz) / INFORME_MD).write_text(informe_md(js), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Regenera informes/preproduccion.md del JSON")
    ap.add_argument("--informe", action="store_true")
    ap.add_argument("--raiz", type=Path, default=CASO)
    args = ap.parse_args()
    if args.informe:
        # Recalcula el estado con las validaciones que haya en el JSON (la prueba por otro camino escribe la suya sin
        # importar este módulo) y regenera el informe
        js = actualizar_json(args.raiz.resolve(), {})
        print(f"escrito {INFORME_MD}: {js['resultado']['estado']}")
