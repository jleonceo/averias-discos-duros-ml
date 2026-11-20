"""Medidas, tablas y gráficos técnicos para evaluar un modelo supervisado de sí o no.

Guía de uso: `01_guia_evaluacion.md`, en esta misma carpeta. Banco: `probar_evaluacion_binaria.py`.

Solo vale para modelos supervisados con un objetivo de dos valores (1 = el evento pasa, 0 = no pasa) que dan una
probabilidad por fila. No vale para regresión, agrupación, previsión ni supervivencia.

Todas las funciones reciben el objetivo real y la PROBABILIDAD del «sí» (`predict_proba(x)[:, 1]`), nunca la etiqueta
0/1 de `predict()`: con la etiqueta, el AUC, el Gini, el KS y la ganancia salen con otra cifra. Paran con un
ValueError que dice qué falla si les llega la etiqueta, un objetivo con otro valor, longitudes distintas, vacíos o
probabilidades fuera de 0 a 1.

- medidas_globales: las que no dependen del corte (AUC, Gini, KS, PR-AUC, Brier y la tasa base);
- medidas_en_corte y tabla_cortes: la matriz de confusión y lo que sale de ella en uno o varios cortes;
- tabla_ganancia: qué parte de los «sí» se captura revisando cada tramo de mayor probabilidad, y el lift;
- corte_por_valor: el valor de cada corte con una matriz de impacto que da el negocio;
- comparar_modelos: las medidas globales de varios modelos sobre las mismas filas;
- desarrollo_frente_a_validacion: las medidas en las filas del ajuste y en las nuevas, para ver el sobreajuste;
- calibracion: probabilidad media frente a tasa observada por tramos;
- figura_roc, figura_precision_cobertura, figura_ganancia y figura_umbrales: gráficos técnicos en matplotlib, para
  el análisis del modelado. Los gráficos de un informe para negocio van con `assets/graficos.py`.
"""

# matplotlib dibuja los gráficos técnicos
import matplotlib.pyplot as plt
# numpy hace las cuentas
import numpy as np
# pandas devuelve las tablas
import pandas as pd
# Las medidas de referencia de scikit-learn
from sklearn.metrics import (PrecisionRecallDisplay, RocCurveDisplay, average_precision_score, brier_score_loss,
                             roc_auc_score, roc_curve)

# Cortes que se recorren por defecto: de 0 a 0,99, de centésima en centésima
CORTES = np.round(np.arange(0.0, 1.0, 0.01), 2)


def _comprobar(y, prob):
    """Devuelve objetivo y probabilidad como arrays, o para con un ValueError que dice qué falla."""
    # Objetivo y probabilidad como arrays de numpy
    y = np.asarray(y)
    prob = np.asarray(prob, dtype=float)
    # Mismo número de filas
    if y.shape != prob.shape or y.ndim != 1:
        # Se para
        raise ValueError(f"objetivo y probabilidad con formas distintas: {y.shape} y {prob.shape}")
    # Sin vacíos en ninguno de los dos
    if pd.isna(y).any() or np.isnan(prob).any():
        # Se para
        raise ValueError("hay vacíos en el objetivo o en la probabilidad: se quitan antes, y se dice cuántos")
    # El objetivo solo puede valer 0 o 1
    valores = set(np.unique(y).tolist())
    if not valores <= {0, 1}:
        # Se para
        raise ValueError(f"el objetivo tiene que valer 0 o 1, y trae {sorted(valores)}")
    # Hacen falta las dos clases para medir nada
    if valores != {0, 1}:
        # Se para
        raise ValueError("el objetivo trae una sola clase: con estas filas no se puede evaluar")
    # La probabilidad va de 0 a 1
    if prob.min() < 0 or prob.max() > 1:
        # Se para
        raise ValueError(f"la probabilidad tiene que ir de 0 a 1, y va de {prob.min():.3f} a {prob.max():.3f}")
    # Solo ceros y unos: es la etiqueta de predict(), no la probabilidad
    if set(np.unique(prob).tolist()) <= {0.0, 1.0}:
        # Se para
        raise ValueError("la probabilidad solo trae 0 y 1: parece la etiqueta de predict(); "
                         "pasa predict_proba(x)[:, 1]")
    # Todo en orden
    return y.astype(int), prob


def _cociente(a, b):
    """a / b, o vacío si b es cero."""
    # Sin denominador no hay cociente
    return a / b if b else float("nan")


def medidas_globales(y, prob):
    """Las medidas que no dependen del corte, sobre la probabilidad.

    - auc: cómo ordena el modelo, de 0,5 (azar) a 1 (perfecto);
    - gini: 2 × AUC − 1, la misma información en escala de 0 a 1, la habitual en riesgo de crédito;
    - ks: la mayor distancia entre la tasa de «sí» capturados y la de «no» señalados por error;
    - pr_auc: el área bajo la curva precisión-cobertura; su azar es la tasa base, y es la que manda cuando los «sí»
      son pocos;
    - brier: el error cuadrático medio de la probabilidad; cuanto más bajo, mejor calibrada y más separada;
    - tasa_base, filas y positivos: con qué se compara todo lo anterior.
    """
    # Entradas comprobadas
    y, prob = _comprobar(y, prob)
    # Curva ROC para el KS
    fpr, tpr, _ = roc_curve(y, prob)
    # AUC sobre la probabilidad
    auc = roc_auc_score(y, prob)
    # Diccionario de medidas
    return {
        "filas": int(len(y)),
        "positivos": int(y.sum()),
        "tasa_base": float(y.mean()),
        "auc": float(auc),
        "gini": float(2 * auc - 1),
        "ks": float(np.max(tpr - fpr)),
        "pr_auc": float(average_precision_score(y, prob)),
        "brier": float(brier_score_loss(y, prob)),
    }


def medidas_en_corte(y, prob, corte):
    """La matriz de confusión y lo que sale de ella cuando se dice «sí» a partir de `corte` (prob >= corte).

    - precision: de los señalados, cuántos son «sí» de verdad;
    - cobertura: de los «sí», cuántos se señalan (recall);
    - f1: la media armónica de las dos;
    - exactitud: aciertos sobre el total; se da al lado de la del modelo trivial, que dice «no» a todos, porque con
      pocos «sí» una exactitud alta no dice nada;
    - senalados: cuántas filas pasan el corte, que es lo que el negocio tendrá que atender.
    """
    # Entradas comprobadas
    y, prob = _comprobar(y, prob)
    # El corte también va de 0 a 1
    if not 0 <= corte <= 1:
        # Se para
        raise ValueError(f"el corte tiene que ir de 0 a 1, y es {corte}")
    # Decisión con el corte
    pred = prob >= corte
    # Las cuatro celdas
    tp = int(np.sum(pred & (y == 1)))
    fp = int(np.sum(pred & (y == 0)))
    fn = int(np.sum(~pred & (y == 1)))
    tn = int(np.sum(~pred & (y == 0)))
    # Precisión y cobertura
    precision = _cociente(tp, tp + fp)
    cobertura = _cociente(tp, tp + fn)
    # Diccionario de medidas
    return {
        "corte": float(corte),
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
        "senalados": tp + fp,
        "precision": precision,
        "cobertura": cobertura,
        "f1": _cociente(2 * precision * cobertura, precision + cobertura) if tp else 0.0,
        "exactitud": (tp + tn) / len(y),
        "exactitud_trivial": float(max(y.mean(), 1 - y.mean())),
    }


def tabla_cortes(y, prob, cortes=CORTES):
    """medidas_en_corte para cada corte, en una tabla con el corte de índice."""
    # Una fila por corte
    filas = [medidas_en_corte(y, prob, c) for c in cortes]
    # Tabla con el corte de índice
    return pd.DataFrame(filas).set_index("corte")


def tabla_ganancia(y, prob, n_tramos=10, importe=None):
    """Ordena las filas de mayor a menor probabilidad, las parte en tramos del mismo tamaño y acumula.

    Se lee «revisando el 20 % de mayor probabilidad se captura tal parte de los "sí", tantas veces lo que daría elegir
    al azar». Columnas: casos, positivos y tasa del tramo; pct_poblacion y pct_capturado, acumulados; lift, que es
    pct_capturado / pct_poblacion. Con `importe` (uno por fila, por ejemplo la deuda o la venta), además el importe de
    los «sí» del tramo y la parte acumulada del importe total de los «sí». Con empates, manda el orden de las filas.
    """
    # Entradas comprobadas
    y, prob = _comprobar(y, prob)
    # Orden de mayor a menor probabilidad; con empates, por posición
    orden = np.lexsort((np.arange(len(y)), -prob))
    # Tabla ordenada
    d = pd.DataFrame({"y": y[orden], "prob": prob[orden]})
    # Importe de los «sí», si se da
    if importe is not None:
        # Importe como array, del mismo largo
        importe = np.asarray(importe, dtype=float)
        if importe.shape != y.shape or np.isnan(importe).any():
            # Se para
            raise ValueError("el importe tiene que tener un valor por fila y sin vacíos")
        # Solo cuenta el importe de los «sí»
        d["importe_si"] = np.where(y[orden] == 1, importe[orden], 0.0)
    # Tramos del mismo tamaño sobre la posición
    d["tramo"] = pd.qcut(np.arange(len(d)), n_tramos, labels=range(1, n_tramos + 1))
    # Recuento por tramo
    agg = {"casos": ("y", "size"), "positivos": ("y", "sum"), "prob_min": ("prob", "min")}
    if importe is not None:
        agg["importe_si"] = ("importe_si", "sum")
    t = d.groupby("tramo", observed=True).agg(**agg)
    # Tasa del tramo
    t["tasa"] = t["positivos"] / t["casos"]
    # Acumulados
    t["pct_poblacion"] = t["casos"].cumsum() / t["casos"].sum()
    t["pct_capturado"] = t["positivos"].cumsum() / t["positivos"].sum()
    # Veces mejor que al azar
    t["lift"] = t["pct_capturado"] / t["pct_poblacion"]
    # Importe acumulado de los «sí»
    if importe is not None:
        total = t["importe_si"].sum()
        t["pct_importe_capturado"] = t["importe_si"].cumsum() / total if total else float("nan")
    # Tabla por tramo
    return t


def corte_por_valor(y, prob, valor_tp, valor_fp, valor_fn=0.0, valor_tn=0.0, cortes=CORTES):
    """El valor de cada corte: cada celda de la matriz de confusión por su valor, sumado.

    Los cuatro valores los da el negocio, con su fuente, y se escriben frente a una situación de referencia (por
    ejemplo, no actuar), para no contar dos veces el mismo dinero: en una campaña que cuesta 15 por contacto y deja 85
    por venta, acierto «sí» = 85 − 15 = 70, falsa alarma = −15, y el «sí» que se escapa y el «no» acertado = 0.
    Devuelve una fila por corte; el mejor es `tabla.loc[tabla["valor"].idxmax()]`. Se elige con datos de desarrollo y
    se aplica una vez en validación.
    """
    # Entradas comprobadas
    y, prob = _comprobar(y, prob)
    # Una fila por corte
    filas = []
    for c in cortes:
        # Decisión con el corte
        pred = prob >= c
        # Las cuatro celdas
        tp = int(np.sum(pred & (y == 1)))
        fp = int(np.sum(pred & (y == 0)))
        fn = int(np.sum(~pred & (y == 1)))
        tn = int(np.sum(~pred & (y == 0)))
        # Valor del corte
        valor = tp * valor_tp + fp * valor_fp + fn * valor_fn + tn * valor_tn
        filas.append({"corte": float(c), "tp": tp, "fp": fp, "fn": fn, "tn": tn, "valor": float(valor)})
    # Tabla de cortes
    return pd.DataFrame(filas)


def comparar_modelos(y, probs):
    """medidas_globales de cada modelo sobre las mismas filas. `probs` es {nombre: probabilidad}.

    Incluye siempre una referencia sencilla para comparar: un modelo no es bueno por sí mismo, sino si supera a algo
    más simple (el trivial tiene AUC 0,5; la referencia de negocio es la variable sola que más separa).
    """
    # Una fila por modelo, en el orden recibido
    return pd.DataFrame({nombre: medidas_globales(y, p) for nombre, p in probs.items()}).T


def desarrollo_frente_a_validacion(y_des, prob_des, y_val, prob_val):
    """AUC, Gini, KS y PR-AUC en desarrollo y en validación, y validación menos desarrollo, para ver el sobreajuste.

    En desarrollo se mide con el modelo ya ajustado a esas filas; en validación, con filas que no ha visto. Si el Gini
    cae mucho de desarrollo a validación, el modelo memoriza en lugar de aprender (sobreajuste): se corrige con un
    modelo más sencillo o más regularizado. Si los dos son bajos y parecidos, se queda corto (infra ajuste). Cuánto es
    «mucho» no tiene vara fija: se compara entre modelos del mismo caso. En un scorecard, el Gini va además fuera de
    pliegue (`scorecard_de_riesgos/03_`, M19).
    """
    # Medidas de cada lado
    des = medidas_globales(y_des, prob_des)
    val = medidas_globales(y_val, prob_val)
    claves = ["auc", "gini", "ks", "pr_auc"]
    tabla = pd.DataFrame({"desarrollo": {k: des[k] for k in claves}, "validacion": {k: val[k] for k in claves}}).T
    # La caída de desarrollo a validación, en la escala de cada medida
    tabla.loc["validacion_menos_desarrollo"] = tabla.loc["validacion"] - tabla.loc["desarrollo"]
    return tabla


def calibracion(y, prob, n_tramos=5):
    """Probabilidad media frente a tasa observada, por tramos de probabilidad con el mismo número de filas.

    Si la probabilidad se va a usar como probabilidad (una pérdida esperada, un corte por fórmula), las dos columnas
    tienen que parecerse. Con pocos «sí», cada tramo necesita bastantes filas: el caso fija el mínimo.
    """
    # Entradas comprobadas
    y, prob = _comprobar(y, prob)
    # Tramos por cuantiles de la probabilidad, sin tramos repetidos
    tramo = pd.qcut(prob, n_tramos, duplicates="drop")
    d = pd.DataFrame({"y": y, "prob": prob, "tramo": tramo})
    # Recuento por tramo
    t = d.groupby("tramo", observed=True).agg(casos=("y", "size"), prob_media=("prob", "mean"),
                                              tasa_observada=("y", "mean"))
    return t


def figura_roc(y, probs):
    """Curva ROC de uno o varios modelos, con la diagonal del azar. Para lectores técnicos."""
    # Figura y ejes
    fig, ax = plt.subplots(figsize=(6, 5))
    # Una curva por modelo
    for i, (nombre, p) in enumerate(probs.items()):
        y_, p_ = _comprobar(y, p)
        RocCurveDisplay.from_predictions(y_, p_, name=nombre, ax=ax, plot_chance_level=(i == 0))
    # Rótulos en castellano
    ax.set_xlabel("Tasa de «no» señalados por error")
    ax.set_ylabel("Tasa de «sí» capturados")
    return fig


def figura_precision_cobertura(y, probs):
    """Curva precisión-cobertura de uno o varios modelos, con la línea del azar (la tasa base)."""
    # Figura y ejes
    fig, ax = plt.subplots(figsize=(6, 5))
    # Una curva por modelo
    for i, (nombre, p) in enumerate(probs.items()):
        y_, p_ = _comprobar(y, p)
        PrecisionRecallDisplay.from_predictions(y_, p_, name=nombre, ax=ax, plot_chance_level=(i == 0))
    # Rótulos en castellano
    ax.set_xlabel("Cobertura")
    ax.set_ylabel("Precisión")
    return fig


def figura_ganancia(y, probs, n_tramos=10):
    """Curva de ganancia de uno o varios modelos, con la diagonal del azar. Versión técnica de la de negocio."""
    # Figura y ejes
    fig, ax = plt.subplots(figsize=(6, 5))
    # Una curva por modelo, desde el origen
    for nombre, p in probs.items():
        t = tabla_ganancia(y, p, n_tramos=n_tramos)
        ax.plot([0] + list(t["pct_poblacion"] * 100), [0] + list(t["pct_capturado"] * 100), marker="o", label=nombre)
    # Azar
    ax.plot([0, 100], [0, 100], linestyle="--", color="grey", label="al azar")
    # Rótulos en castellano
    ax.set_xlabel("% de filas revisadas, de mayor a menor probabilidad")
    ax.set_ylabel("% de «sí» capturados")
    ax.legend()
    return fig


def figura_umbrales(y, prob, cortes=CORTES):
    """Precisión, cobertura y F1 en cada corte. Sirve para ver el equilibrio antes de elegir el corte por valor."""
    # Medidas en cada corte
    t = tabla_cortes(y, prob, cortes)
    # Figura y ejes
    fig, ax = plt.subplots(figsize=(6, 5))
    # Las tres líneas
    ax.plot(t.index, t["precision"], label="precisión")
    ax.plot(t.index, t["cobertura"], label="cobertura")
    ax.plot(t.index, t["f1"], label="F1")
    # Rótulos en castellano
    ax.set_xlabel("Corte")
    ax.set_ylabel("Valor")
    ax.legend()
    return fig
