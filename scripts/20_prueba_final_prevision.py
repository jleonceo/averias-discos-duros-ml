"""Prueba final de la previsión de fallos del caso 68 en el año guardado (encargo 24; guion de la preproducción, paso 6).

La previsión es la del bloque 9 (reglas §7, CP-011): para cada modelo y año de edad del primer día del trimestre,
previsto = discos × días del trimestre × fallos / días de disco de su nivel de tasa, con los meses anteriores al primer
día; frente a repetir los fallos reales del trimestre anterior, por capacidad. Gana la cuenta si su error absoluto
ponderado de los cuatro trimestres juntos es menor que el de la referencia. Se calcula, nunca se escribe.

Las tres piezas de cada trimestre (los discos del primer día, los días de disco y los fallos de cada mes, y los fallos
reales) se rehacen desde los datos en bruto con el módulo de producción (scripts/pipeline_riesgo.py) y la historia de
varias carpetas de produccion/configuracion.json, como el script 19. Para los meses anteriores al periodo, la historia es
data/processed/dias_por_tramo.parquet tal cual. Ninguna tabla del análisis se toca.

Dos modos, por argumento y sin valor por defecto:
  --ensayo-validacion  rehace los 12 meses de 2024-07 a 2025-06 y los cuatro primeros días de trimestre de
                       data/raw/podado/, sin las carpetas del año guardado. Compara en código las piezas con
                       inicio_trimestre y dias_por_tramo y los pares con B9.tablas.pares de
                       informes/indicadores__coste_prevision.json; si algo difiere, ERROR y dice qué. Solo se admite la
                       foto de un disco sin horas cuya edad sale distinta por el arreglo del contrato (R-024: la edad sin
                       horas solo mira ventanas de fallos ya ocurridos), contada aparte, y como mucho una. Escribe
                       informes/prueba_final_prevision_ensayo.json.
  --reserva            el año guardado, una sola vez: rehace los 12 meses de 2025-07 a 2026-06 y los primeros días de
                       2025T3 a 2026T2 con la historia de data/raw/podado y data/raw/reserva; la referencia de 2025T3 son
                       los fallos reales de 2025T2 de B9.tablas.pares. Para con ERROR si el ensayo no está en OK con las
                       mismas entradas y el mismo script, y con PARADO, sin tocar nada, si el año guardado ya se midió.
                       Escribe informes/prueba_final_prevision.json e informes/prueba_final_prevision.md.

No importa ningún script numerado: inicio_trimestre, prever_trimestre, error_ponderado, montar_pares y resumen_error son
copias de scripts/10_indicadores_coste_prevision.py, letra a letra, y sin_resultados_escritos, de
scripts/19_prueba_final.py; la prueba lo comprueba. Importa scripts/pipeline_riesgo.py y produccion/ejecutar.py.

Uso: python -W error scripts/20_prueba_final_prevision.py (--ensayo-validacion | --reserva) [--raiz CARPETA_DEL_CASO]
Sale con 0 si termina en OK o AVISO, con 1 si da ERROR y con 2 si para (PARADO). Escribe el JSON también si falla,
salvo cuando el año guardado ya se midió: entonces no toca lo medido.
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import calendar
import datetime as dt
import hashlib
import json
import math
import platform
import re
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
sys.path.insert(0, str(CASO / "assets"))
sys.path.insert(0, str(CASO / "produccion"))
import pipeline_riesgo as pr  # noqa: E402  (módulo de producción del caso)
import ejecutar  # noqa: E402  (produccion/ejecutar.py: su trabajo está bajo __main__)
from graficos import numero  # noqa: E402  (pieza común: números a la española, redondeo como Excel)

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SCRIPT = "scripts/20_prueba_final_prevision.py"
ENCARGO = "prompts/24_encargo_prevision_en_el_ano_guardado.md"
SKILL = "indicadores-y-analisis (método del bloque 9, copiado del script 10)"
CONFIGURACION = "produccion/configuracion.json"
INDICADORES = "informes/indicadores__coste_prevision.json"
DPT = "data/processed/dias_por_tramo.parquet"
INICIO = "data/processed/inicio_trimestre.parquet"
DIM_MODELO = "data/processed/dim_modelo.parquet"
RAW, RESERVA = "data/raw", "data/raw/reserva"
INFORME_MD = "informes/prueba_final_prevision.md"
FOTOS, RECUENTO, LISTA = "fotos_mensuales", "recuento_diario.parquet", "fallos.parquet"

# Los dos modos (encargo 24; guion de la preproducción, paso 6): de dónde salen los datos del periodo y qué se escribe
MODOS = {
    "ensayo": {"argumento": "--ensayo-validacion", "datos": "data/raw/podado", "desde": "2024-07", "hasta": "2025-06",
               "fin": "2025-06-30", "json": "informes/prueba_final_prevision_ensayo.json"},
    "reserva": {"argumento": "--reserva", "datos": "data/raw/reserva", "desde": "2025-07", "hasta": "2026-06",
                "fin": "2026-06-30", "json": "informes/prueba_final_prevision.json"},
}
# Mínimo de días de disco de un nivel de tasa, niveles en su orden y horas de técnico por cambio (reglas §5 y §7; los
# del script 10, que usan las funciones copiadas)
MINIMO_DIAS_ANO = 50_000
NIVELES = ("modelo", "capacidad", "edad")
HORAS_POR_CAMBIO = 0.74
# Diferencia que se admite en días y previstos, cifras con decimales (encargo 24)
TOLERANCIA = 1e-6
# El centro que no consta (reglas de transformación §6) y el año de edad (convención técnica 1)
SIN_DATO = pr.SIN_DATO
HORAS_ANO, DIAS_ANO = pr.HORAS_ANO, pr.DIAS_ANO
# Columnas que se leen de la foto en bruto y de las ventanas
COLUMNAS_FOTO = ["serial_number", "fecha", "model", "capacity_bytes", "failure", "datacenter", "smart_9_raw", *pr.CONTADORES]
COLUMNAS_VENTANA = ["serial_number", "fecha", "date", "dia_fallo", "model", "capacity_bytes", "smart_9_raw"]
# Diferencias que se escriben en el resumen de un ERROR
MAX_DIFERENCIAS = 12


class Parada(Exception):
    """Condición que impide seguir: `estado` es PARADO o ERROR."""

    def __init__(self, mensaje, estado="ERROR"):
        super().__init__(mensaje)
        self.estado = estado


# =================================================================================================================
# 3. La previsión del bloque 9 (copias de scripts/10_indicadores_coste_prevision.py, letra a letra)
# =================================================================================================================
# Origen: scripts/10_indicadores_coste_prevision.py, inicio_trimestre
def inicio_trimestre(ano, t):
    """Primer día del trimestre."""
    return pd.Timestamp(int(ano), 3 * int(t) - 2, 1)


# Origen: scripts/10_indicadores_coste_prevision.py, prever_trimestre
def prever_trimestre(ano, trimestre, it, dpt, meses_historia=None, minimo=MINIMO_DIAS_ANO, niveles=NIVELES):
    """Fallos previstos de un trimestre con lo sabido hasta el día anterior a su primer día (reglas §7, CP-011).

    Para cada fila de inicio_trimestre del trimestre (modelo y año de edad del primer día): previsto = discos ×
    días del trimestre × fallos / días de disco de su nivel de tasa, con los meses de dias_por_tramo anteriores al
    primer día (toda la historia o los últimos `meses_historia`). El nivel es el primero de `niveles` cuya celda tiene
    `minimo` días o más; el de edad, con cualquier día. `dpt` lleva la capacidad de cada modelo. Devuelve las filas,
    el último mes usado y el previsto por capacidad.
    """
    inicio = inicio_trimestre(ano, trimestre)
    # Una fila sin días (solo trae fallos, reglas de transformación §6) cuenta 0 días y sus fallos
    h = dpt.loc[dpt["mes"] < inicio].assign(dias_disco=lambda x: x["dias_disco"].fillna(0.0))
    if meses_historia is not None:
        h = h.loc[h["mes"] >= inicio - pd.DateOffset(months=meses_historia)]
    filas = it.loc[(it["ano"] == ano) & (it["trimestre"] == trimestre) & (it["discos"] > 0),
                   ["model", "edad_anos_cumplidos", "capacidad_tb", "discos", "dias_trimestre"]].copy()
    claves = {"modelo": ["model", "edad_anos_cumplidos"], "capacidad": ["capacidad_tb", "edad_anos_cumplidos"],
              "edad": ["edad_anos_cumplidos"]}
    filas["nivel"] = "sin tasa"
    filas["dias_base"] = 0.0
    filas["fallos_base"] = 0.0
    for nivel in niveles:
        t = (h.groupby(claves[nivel]).agg(d=("dias_disco", "sum"), f=("fallos", "sum")).reset_index()
             .rename(columns={"d": f"d_{nivel}", "f": f"f_{nivel}"}))
        filas = filas.merge(t, on=claves[nivel], how="left", validate="many_to_one")
        umbral = minimo if nivel != "edad" else 0
        elegir = (filas["nivel"] == "sin tasa") & (filas[f"d_{nivel}"].fillna(0) > 0) & (
            filas[f"d_{nivel}"].fillna(0) >= umbral)
        filas.loc[elegir, "nivel"] = nivel
        filas.loc[elegir, "dias_base"] = filas.loc[elegir, f"d_{nivel}"]
        filas.loc[elegir, "fallos_base"] = filas.loc[elegir, f"f_{nivel}"].astype(float)
    con_tasa = filas["dias_base"] > 0
    filas["tasa_dia"] = np.where(con_tasa, filas["fallos_base"] / filas["dias_base"].where(con_tasa, 1.0), 0.0)
    filas["previsto"] = filas["discos"] * filas["dias_trimestre"] * filas["tasa_dia"]
    filas = filas[["model", "edad_anos_cumplidos", "capacidad_tb", "discos", "dias_trimestre", "nivel", "dias_base",
                   "fallos_base", "tasa_dia", "previsto"]].sort_values(["model", "edad_anos_cumplidos"],
                                                                         kind="mergesort").reset_index(drop=True)
    por_cap = filas.groupby("capacidad_tb")["previsto"].sum()
    return {"inicio": inicio, "filas": filas, "ultimo_mes_usado": h["mes"].max() if len(h) else None,
            "previsto_por_capacidad": {float(k): float(v) for k, v in por_cap.items()}}


# Origen: scripts/10_indicadores_coste_prevision.py, error_ponderado
def error_ponderado(previstos, reales):
    """Error absoluto ponderado = suma de |previsto − real| / suma de reales; sesgo, lo mismo con signo (CP-011)."""
    s = float(sum(reales))
    if s == 0:
        return None, None
    return (float(sum(abs(p - x) for p, x in zip(previstos, reales))) / s,
            float(sum(p - x for p, x in zip(previstos, reales))) / s)


# Origen: scripts/10_indicadores_coste_prevision.py, montar_pares
def montar_pares(previsiones, reales, prev_q, anterior):
    """Pares de trimestre y capacidad: los que tienen discos el primer día, reales o referencia (encargo, B9.1)."""
    pares = []
    for q in prev_q:
        p = previsiones[q["trimestre"]]
        caps = (set(p) | {k for (t, k) in reales if t == q["trimestre"]}
                | {k for (t, k) in reales if t == anterior[q["trimestre"]]})
        for k in sorted(caps):
            prev = float(p.get(k, 0.0))
            real = reales.get((q["trimestre"], k), 0)
            ref = reales.get((anterior[q["trimestre"]], k), 0)
            pares.append({"trimestre": q["trimestre"], "capacidad_tb": k, "previsto": prev, "real": real,
                          "referencia": ref, "previsto_entre_real": prev / real if real > 0 else None,
                          "horas_tecnico": prev * HORAS_POR_CAMBIO})
    return pares


# Origen: scripts/10_indicadores_coste_prevision.py, resumen_error
def resumen_error(pares, clave=None):
    """Error ponderado y sesgo de la cuenta y de la referencia, en total o por `clave`."""
    grupos = {None: pares} if clave is None else {}
    if clave is not None:
        for p in pares:
            grupos.setdefault(p[clave], []).append(p)
    out = []
    for g, xs in grupos.items():
        wc, sc = error_ponderado([x["previsto"] for x in xs], [x["real"] for x in xs])
        wr, sr = error_ponderado([x["referencia"] for x in xs], [x["real"] for x in xs])
        fila = {"previsto": sum(x["previsto"] for x in xs), "real": sum(x["real"] for x in xs),
                "referencia": sum(x["referencia"] for x in xs), "wape_cuenta": wc, "sesgo_cuenta": sc,
                "wape_referencia": wr, "sesgo_referencia": sr, "pares": len(xs)}
        out.append(fila if clave is None else {clave: g} | fila)
    return out[0] if clave is None else out


# =================================================================================================================
# 4. Comprobaciones: cada una calculada con lo ejecutado; la prueba las pone en rojo
# =================================================================================================================
def comp_sin_futuro(ultimos_meses, inicios):
    """Ninguna previsión usa un mes igual o posterior al primer día de su trimestre (directriz 20)."""
    return all(u is None or pd.Timestamp(u) < pd.Timestamp(i) for u, i in zip(ultimos_meses, inicios))


def comp_totales(total, por_trimestre):
    """El previsto, el real y la referencia del total son la suma de los de cada trimestre."""
    return all(math.isclose(float(total[c]), float(sum(t[c] for t in por_trimestre)), rel_tol=1e-12, abs_tol=1e-9)
               for c in ("previsto", "real", "referencia"))


def comp_cuadre(partes, totales):
    """Cada parte cuadra con su total: días repartidos con los del recuento de sus celdas con foto, o fallos de la
    historia rehecha con los de la lista de discos de datos, mes a mes."""
    return len(partes) == len(totales) and all(
        math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=TOLERANCIA) for a, b in zip(partes, totales))


def comp_huellas(antes, despues):
    """La huella de cada fichero de data/raw/ es la misma antes y después."""
    return antes == despues


def admitidas_ok(admitidas):
    """Solo se admite como diferencia la foto de un disco sin horas, y como mucho una (encargo 24)."""
    return len(admitidas) <= 1 and all(a["tipo"] == "foto" for a in admitidas)


# Origen: scripts/19_prueba_final.py, sin_resultados_escritos
def sin_resultados_escritos(texto):
    """Error 24: ninguna validación lleva su resultado escrito, ni como clave con su sí o no ni asignada."""
    valor = "|".join(["Tr" + "ue", "Fal" + "se"])
    escrito = re.compile(r"""["'][\w ]+["']\s*:\s*(%s)\b|validaciones\[[^\]]+\]\s*=\s*(%s)\b""" % (valor, valor))
    return not escrito.search(texto)


def diferencias(nombre, a, b, tolerancia=None, faltan_son_cero=True):
    """Compara dos series indexadas por la misma clave y devuelve las claves que difieren, con su texto.

    Con `faltan_son_cero`, una clave que falta en un lado vale 0; sin él, una clave que falta es una diferencia.
    """
    c = pd.concat([pd.Series(a, dtype="float64").rename("rehecho"), pd.Series(b, dtype="float64").rename("analisis")],
                  axis=1)
    falta = c.isna().any(axis=1).to_numpy()
    c = c.fillna(0.0)
    dif = (c["rehecho"] - c["analisis"]).abs().to_numpy()
    malas = dif > (tolerancia if tolerancia is not None else 0)
    if not faltan_son_cero:
        malas = malas | falta
    return [f"{nombre} {k}: rehecho {x:.10g}, análisis {y:.10g}" + (" (la clave falta en un lado)" if fa else "")
            for k, x, y, fa in zip(c.index[malas], c["rehecho"].to_numpy()[malas], c["analisis"].to_numpy()[malas],
                                   falta[malas])]


# =================================================================================================================
# 5. Lectura
# =================================================================================================================
def ruta_de(raiz, texto):
    """Una ruta absoluta, o relativa a la carpeta del caso."""
    p = Path(texto)
    return p if p.is_absolute() else Path(raiz) / p


def sha256(ruta):
    """Huella SHA-256 de un fichero, leído por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def huellas_raw(raiz):
    """La huella de cada fichero de data/raw/, por ruta."""
    base = Path(raiz) / RAW
    return {p.relative_to(base).as_posix(): sha256(p) for p in sorted(base.rglob("*")) if p.is_file()}


def huellas_de_entrada(raiz):
    """Las huellas de lo que el año guardado tiene que leer igual que el ensayo: las tablas del análisis, el JSON de B9,
    el módulo, la configuración y este script."""
    rutas = [INDICADORES, DPT, INICIO, DIM_MODELO, "scripts/pipeline_riesgo.py", "produccion/ejecutar.py", SCRIPT]
    return {r: sha256(ruta_de(raiz, r)) for r in rutas if ruta_de(raiz, r).exists()}


def leer_configuracion(raiz):
    """La configuración de producción, el mapeo de modelos y la capacidad mínima válida."""
    conf = json.loads(ruta_de(raiz, CONFIGURACION).read_text(encoding="utf-8"))
    dec = json.loads(ruta_de(raiz, conf["decisiones_correccion"]).read_text(encoding="utf-8"))
    return conf, dec["modelos"]["mapeo"], dec["capacidad"]["minimo_valido_bytes"]


def historia_del_modo(raiz, conf, modo):
    """Las carpetas de historia de la configuración; en el ensayo, sin las del año guardado (como el script 19)."""
    salida = {}
    for clave in ("historia_fotos", "historia_ventanas"):
        valor = conf[clave]
        carpetas = [ruta_de(raiz, c) for c in ([valor] if isinstance(valor, str) else valor)]
        if modo == "ensayo":
            reserva = ruta_de(raiz, RESERVA).resolve()
            carpetas = [c for c in carpetas if not c.resolve().is_relative_to(reserva)]
        salida[clave] = ejecutar.carpetas_de(Path(raiz), carpetas)
    return salida


def meses_y_trimestres(m):
    """Los meses del periodo (primer día) y sus trimestres, con su primer día y sus días naturales."""
    meses = [p.start_time for p in pd.period_range(m["desde"], m["hasta"], freq="M")]
    trims = []
    for f in meses:
        if f.month in (1, 4, 7, 10):
            t = (f.month - 1) // 3 + 1
            dias = sum(calendar.monthrange(f.year, x)[1] for x in range(f.month, f.month + 3))
            trims.append({"trimestre": f"{f.year}T{t}", "ano": f.year, "t": t, "inicio": f, "dias": dias})
    return meses, trims


def etiqueta_anterior(trimestre):
    """«2025T2» para «2025T3»; «2024T4» para «2025T1»."""
    a, t = int(trimestre[:4]), int(trimestre[5])
    return f"{a - 1}T4" if t == 1 else f"{a}T{t - 1}"


def leer_lista(ruta, desde, hasta):
    """La lista de fallos en bruto con dia_fallo en milisegundos, del primer día `desde` al día anterior a `hasta`."""
    f = pd.read_parquet(ruta, columns=["serial_number", "dia_fallo"])
    f["dia_fallo"] = f["dia_fallo"].astype("datetime64[ms]")
    if f.duplicated(["serial_number", "dia_fallo"]).any():
        raise Parada(f"la lista de fallos {ruta.name} tiene la clave (serial_number, dia_fallo) repetida")
    return f.loc[((f["dia_fallo"] >= desde) & (f["dia_fallo"] < hasta)).to_numpy()].reset_index(drop=True)


def leer_recuento(ruta, desde, hasta, mapeo):
    """El recuento diario del periodo, con el nombre del modelo corregido, el centro («sin dato» si falta) y el mes."""
    r = pd.read_parquet(ruta, columns=["fecha", "model", "datacenter", "discos", "fallos"])
    r["fecha"] = r["fecha"].astype("datetime64[ms]")
    r = r.loc[((r["fecha"] >= desde) & (r["fecha"] < hasta)).to_numpy()].copy()
    r["model"] = r["model"].replace(mapeo)
    r["centro"] = r["datacenter"].astype(object).where(r["datacenter"].notna(), SIN_DATO)
    r["mes"] = r["fecha"].dt.to_period("M").dt.start_time.astype("datetime64[ms]")
    return r


def leer_ventanas(carpetas):
    """Todas las ventanas de fallo de las carpetas de historia, sin las filas cuya fecha no es la de su texto (R-007),
    con el nombre del modelo sin corregir todavía."""
    partes = [pr._leer_columnas(ruta, COLUMNAS_VENTANA) for c in carpetas for ruta in sorted(Path(c).glob("*.parquet"))]
    if not partes:
        raise Parada("no hay ninguna ventana de fallo en las carpetas de historia")
    v = pd.concat(partes, ignore_index=True)
    v["fecha"] = v["fecha"].astype("datetime64[ms]")
    v["dia_fallo"] = v["dia_fallo"].astype("datetime64[ms]")
    v = v.loc[(pr._fecha_de_texto(v["date"]) == v["fecha"]).to_numpy()]
    return v.drop(columns=["date"]).reset_index(drop=True)


def fotos_de(carpetas, seriales):
    """La fecha de cada foto de unos discos, en todas las fotos de las carpetas de historia."""
    valores = pa.array(sorted(seriales), type=pa.string())
    partes = []
    for ruta in [r for c in carpetas for r in sorted(Path(c).glob("*.parquet"))]:
        t = pq.read_table(ruta, columns=["serial_number", "fecha"])
        partes.append(t.filter(pc.is_in(t["serial_number"], value_set=valores)).to_pandas())
    f = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["serial_number", "fecha"])
    f["fecha"] = f["fecha"].astype("datetime64[ms]")
    return f


def leer_analisis(raiz):
    """Las tablas del análisis que se usan o se comparan, y los pares de B9."""
    dpt = pd.read_parquet(ruta_de(raiz, DPT), columns=["model", "mes", "edad_anos_cumplidos", "dias_disco", "fallos"])
    dpt["mes"] = dpt["mes"].astype("datetime64[ms]")
    it = pd.read_parquet(ruta_de(raiz, INICIO), columns=["ano", "trimestre", "model", "edad_anos_cumplidos",
                                                         "capacidad_tb", "discos", "dias_trimestre"])
    dm = pd.read_parquet(ruta_de(raiz, DIM_MODELO), columns=["model", "capacidad_tb", "tipo_disco"])
    js = json.loads(ruta_de(raiz, INDICADORES).read_text(encoding="utf-8"))
    b9 = next((p for p in js["preguntas"] if p.get("id") == "B9"), None)
    if b9 is None or not b9.get("tablas", {}).get("pares"):
        raise Parada(f"{INDICADORES} no trae B9.tablas.pares")
    return {"dpt": dpt, "it": it, "dm": dm, "pares": b9["tablas"]["pares"]}


# =================================================================================================================
# 6. Rehacer un mes desde los datos en bruto
# =================================================================================================================
def rehacer_foto(ruta, fecha, carpetas, mapeo, minimo, primer_dia_ventana_todas=None):
    """La foto del primer día de un mes por el módulo de producción: sus filas de discos de datos (todas menos las de
    arranque; las del día del fallo, dentro) con modelo, centro, capacidad y año de edad.

    Con `primer_dia_ventana_todas` (solo en el ensayo) calcula al lado la edad como el análisis, con la primera aparición
    en cualquier ventana, para contar las fotos cuya edad cambia por el arreglo del contrato (R-024). Devuelve las filas,
    los pares (modelo, capacidad) conocidos hasta la foto y las filas de discos de arranque.
    """
    foto = pr.leer_foto(ruta, COLUMNAS_FOTO)
    if not (foto["fecha"] == fecha).all():
        raise Parada(f"la foto {Path(ruta).name} trae filas de otra fecha que el {fecha.date()}")
    historia = ejecutar.leer_historia(carpetas["historia_fotos"], carpetas["historia_ventanas"], fecha, mapeo,
                                      set(foto["serial_number"]))
    df, motivo = pr.preparar_foto(foto, historia, mapeo, minimo)
    # Discos de datos: los de capacidad conocida que no son de arranque (el día del fallo cuenta)
    datos = (df["capacidad_tb"].notna() & (motivo != pr.MOTIVO_ARRANQUE)).to_numpy()
    d = df.loc[datos, ["serial_number", "model", "datacenter", "capacidad_tb", "smart_9_raw", "edad_anos"]].copy()
    if not (d["edad_anos"] >= 0).all():
        raise Parada(f"la foto del {fecha.date()} trae {int((~(d['edad_anos'] >= 0)).sum())} discos de datos con edad "
                     "vacía o negativa")
    d["centro"] = d["datacenter"].astype(object).where(d["datacenter"].notna(), SIN_DATO)
    d["edad_anos_cumplidos"] = np.floor(d["edad_anos"]).astype("int64")
    d["edad_analisis"] = d["edad_anos_cumplidos"]
    if primer_dia_ventana_todas is not None:
        # La edad como el análisis: sin horas, desde la primera foto o el primer día de cualquier ventana
        pf = d["serial_number"].map(historia["primera_foto"]).astype("datetime64[ms]").fillna(fecha)
        pv = d["serial_number"].map(primer_dia_ventana_todas).astype("datetime64[ms]")
        primera = pf.where(pv.isna() | (pf <= pv), pv)
        desde = (fecha - primera) / pd.Timedelta(days=1)
        edad = np.where(d["smart_9_raw"].notna(), d["smart_9_raw"] / HORAS_ANO, desde / DIAS_ANO)
        d["edad_analisis"] = np.floor(edad).astype("int64")
    pares = pd.concat([historia["pares"], df[["model", "capacity_bytes"]]], ignore_index=True)
    return d.reset_index(drop=True), pares, int((motivo == pr.MOTIVO_ARRANQUE).sum())


def repartir_dias(d, rec_mes, capacidad, columna_edad):
    """Los días del recuento de cada modelo y centro del mes, repartidos entre sus años de edad en proporción a las fotos
    (reglas de transformación §6). Una celda sin ninguna foto no se reparte: se cuenta aparte, si es de un modelo de
    datos. Devuelve los días por modelo, centro y año de edad, y lo contado."""
    claves = ["model", "centro"]
    F = d.groupby(claves + [columna_edad]).size().rename("fotos").reset_index()
    F["parte"] = F["fotos"] / F.groupby(claves)["fotos"].transform("sum")
    R = rec_mes.groupby(claves).agg(dias_recuento=("discos", "sum"), fallos_recuento=("fallos", "sum")).reset_index()
    m = F.merge(R, on=claves, how="left", validate="many_to_one")
    m["dias_disco"] = m["parte"] * m["dias_recuento"]
    con = R.merge(F[claves].drop_duplicates(), on=claves, how="left", validate="one_to_one", indicator=True)
    sin = con.loc[(con["_merge"] == "left_only").to_numpy()]
    cap = sin["model"].map(capacidad)
    sin_datos = sin.loc[(cap > pr.LIMITE_ARRANQUE_BYTES).to_numpy()]
    info = {"dias_recuento_con_foto": float(con.loc[(con["_merge"] == "both").to_numpy(), "dias_recuento"].sum()),
            "dias_repartidos": float(m["dias_disco"].sum()),
            "celdas_sin_foto": int(len(sin_datos)), "dias_sin_foto": float(sin_datos["dias_recuento"].sum()),
            "fallos_recuento_sin_foto": int(sin_datos["fallos_recuento"].sum()),
            "dias_de_modelos_sin_capacidad": float(sin.loc[cap.isna().to_numpy(), "dias_recuento"].sum()),
            "celdas_con_foto_sin_recuento": int(m["dias_recuento"].isna().sum())}
    return m.rename(columns={columna_edad: "edad_anos_cumplidos"}), info


def edad_al_fallar(f, fotos, ventanas, solo_lo_ocurrido):
    """Años de edad al fallar: horas del día del fallo o, si faltan, del día anterior, entre 8.766; sin horas, días desde
    la primera aparición en fotos o ventanas entre 365,25 (reglas de transformación §4 y §6).

    Con `solo_lo_ocurrido`, la primera aparición solo mira fotos hasta el día del fallo y ventanas de fallos ya ocurridos
    hasta ese día (directriz 20); sin él, todas, como el análisis.
    """
    claves = f[["serial_number", "dia_fallo"]]
    fo = claves.merge(fotos, on="serial_number", how="inner")
    ve = claves.merge(ventanas[["serial_number", "fecha", "dia_fallo"]].rename(columns={"dia_fallo": "dia_v"}),
                      on="serial_number", how="inner")
    if solo_lo_ocurrido:
        fo = fo.loc[(fo["fecha"] <= fo["dia_fallo"]).to_numpy()]
        ve = ve.loc[(ve["dia_v"] <= ve["dia_fallo"]).to_numpy()]
    primera = (pd.concat([fo[["serial_number", "dia_fallo", "fecha"]], ve[["serial_number", "dia_fallo", "fecha"]]],
                         ignore_index=True).groupby(["serial_number", "dia_fallo"], as_index=False)["fecha"].min())
    p = claves.merge(primera, on=["serial_number", "dia_fallo"], how="left", validate="one_to_one")["fecha"]
    p = pd.Series(p.to_numpy(), index=f.index).astype("datetime64[ms]")
    desde = (f["dia_fallo"] - p) / pd.Timedelta(days=1)
    return np.where(f["horas"].notna(), f["horas"] / HORAS_ANO, desde / DIAS_ANO)


def rehacer_fallos(lista_mes, ventanas, fotos, capacidad, ensayo):
    """Los fallos de la lista de un mes con el modelo de su ventana el día del fallo, su capacidad y su año de edad.
    Devuelve los de discos de datos y lo que queda fuera, contado."""
    v = ventanas.loc[ventanas.set_index(["serial_number", "dia_fallo"]).index.isin(
        pd.MultiIndex.from_frame(lista_mes[["serial_number", "dia_fallo"]]))]
    dia = v.loc[(v["fecha"] == v["dia_fallo"]).to_numpy(), ["serial_number", "dia_fallo", "model", "smart_9_raw"]]
    ant = v.loc[(v["fecha"] == v["dia_fallo"] - pd.Timedelta(days=1)).to_numpy(), ["serial_number", "dia_fallo", "smart_9_raw"]]
    f = (lista_mes.merge(dia.rename(columns={"smart_9_raw": "horas_dia"}), on=["serial_number", "dia_fallo"], how="left",
                         validate="one_to_one")
         .merge(ant.rename(columns={"smart_9_raw": "horas_ant"}), on=["serial_number", "dia_fallo"], how="left",
                validate="one_to_one"))
    f["horas"] = f["horas_dia"].astype("float64").combine_first(f["horas_ant"].astype("float64"))
    cap = f["model"].map(capacidad)
    datos = (cap > pr.LIMITE_ARRANQUE_BYTES).to_numpy()
    fuera = {"sin_ventana_del_dia": int(f["model"].isna().sum()),
             "sin_capacidad": int((f["model"].notna() & cap.isna()).sum()),
             "de_arranque": int((cap.notna() & ~datos).sum())}
    f = f.loc[datos].copy()
    f["capacidad_tb"] = [pr.capacidad_en_tb(c) for c in cap[datos]]
    edad = edad_al_fallar(f, fotos, ventanas, solo_lo_ocurrido=True)
    edad_analisis = edad_al_fallar(f, fotos, ventanas, solo_lo_ocurrido=False) if ensayo else edad
    if not (edad >= 0).all() or not (edad_analisis >= 0).all():
        raise Parada(f"{int((~(edad >= 0)).sum())} fallos de discos de datos con edad vacía o negativa")
    f["edad_anos_cumplidos"] = np.floor(edad).astype("int64")
    f["edad_analisis"] = np.floor(edad_analisis).astype("int64")
    return f[["serial_number", "dia_fallo", "model", "capacidad_tb", "horas", "edad_anos_cumplidos",
              "edad_analisis"]].reset_index(drop=True), fuera


def tramo_del_mes(dias, fallos, mes):
    """Días de disco y fallos del mes por modelo y año de edad, la forma de dias_por_tramo que usa la previsión."""
    a = dias.groupby(["model", "edad_anos_cumplidos"])["dias_disco"].sum()
    b = fallos.groupby(["model", "edad_anos_cumplidos"]).size()
    t = pd.concat([a.rename("dias_disco"), b.rename("fallos")], axis=1).reset_index()
    t["dias_disco"] = t["dias_disco"].fillna(0.0)
    t["fallos"] = t["fallos"].fillna(0).astype("int64")
    t["mes"] = pd.Series([mes] * len(t), dtype="datetime64[ms]")
    return t[["model", "mes", "edad_anos_cumplidos", "dias_disco", "fallos"]]


# =================================================================================================================
# 7. Las piezas del periodo y la previsión
# =================================================================================================================
def rehacer_periodo(raiz, m, modo, carpetas, mapeo, minimo):
    """Las tres piezas del periodo desde los datos en bruto: inicio de cada trimestre, días y fallos de cada mes. En el
    ensayo, también como el análisis (`*_analisis`) y las fotos y fallos cuya edad cambia entre las dos."""
    meses, trims = meses_y_trimestres(m)
    desde, hasta = meses[0], meses[-1] + pd.DateOffset(months=1)
    base = ruta_de(raiz, m["datos"])
    fotos_ruta = {f: base / FOTOS / f"{f.strftime('%Y-%m')}.parquet" for f in meses}
    faltan = [p.name for p in fotos_ruta.values() if not p.exists()] + [
        n for n in (RECUENTO, LISTA) if not (base / n).exists()]
    if faltan:
        raise Parada(f"faltan datos del periodo en {m['datos']}: {faltan}")
    lista = leer_lista(base / LISTA, desde, hasta)
    rec = leer_recuento(base / RECUENTO, desde, hasta, mapeo)
    ventanas = leer_ventanas(carpetas["historia_ventanas"])
    ventanas_mapeadas = ventanas.assign(model=ventanas["model"].replace(mapeo))
    fotos_fallos = fotos_de(carpetas["historia_fotos"], set(lista["serial_number"]))
    primer_dia_todas = ventanas.groupby("serial_number")["fecha"].min() if modo == "ensayo" else None
    piezas = {"inicio": [], "inicio_analisis": [], "tramos": [], "tramos_analisis": [], "fallos": [], "capacidades": [],
              "meses": [], "admitidas": [], "fallos_edad_distinta": []}
    for f in meses:
        siguiente = f + pd.DateOffset(months=1)
        d, pares, arranque = rehacer_foto(fotos_ruta[f], f, carpetas, mapeo, minimo, primer_dia_todas)
        # La capacidad de cada modelo con lo conocido hasta el final del mes: fotos, ventanas y la foto del mes
        v_mes = ventanas_mapeadas.loc[(ventanas_mapeadas["dia_fallo"] < siguiente).to_numpy(), ["model", "capacity_bytes"]]
        capacidad, dobles = pr.capacidades_del_modelo(pd.concat([pares, v_mes], ignore_index=True), minimo)
        rec_mes = rec.loc[(rec["mes"] == f).to_numpy()]
        dias, info = repartir_dias(d, rec_mes, capacidad, "edad_anos_cumplidos")
        lista_mes = lista.loc[((lista["dia_fallo"] >= f) & (lista["dia_fallo"] < siguiente)).to_numpy()]
        fallos, fuera = rehacer_fallos(lista_mes, ventanas_mapeadas, fotos_fallos, capacidad, modo == "ensayo")
        tramo = tramo_del_mes(dias, fallos, f)
        piezas["tramos"].append(tramo)
        piezas["fallos"].append(fallos.assign(mes=f))
        # La capacidad de cada modelo de las fotos del mes: un modelo nuevo puede entrar a mitad de trimestre, sin salir
        # en la foto del primer día ni entre los fallos (R68-145)
        piezas["capacidades"].append(d[["model", "capacidad_tb"]].drop_duplicates())
        # Las fotos y los fallos de discos sin horas cuya edad cambia entre la regla del contrato y la del análisis
        for _, x in d.loc[(d["edad_anos_cumplidos"] != d["edad_analisis"]).to_numpy()].iterrows():
            piezas["admitidas"].append({"tipo": "foto", "serial_number": x["serial_number"], "fecha": f.date().isoformat(),
                                        "model": x["model"], "edad": int(x["edad_anos_cumplidos"]),
                                        "edad_analisis": int(x["edad_analisis"])})
        for _, x in fallos.loc[(fallos["edad_anos_cumplidos"] != fallos["edad_analisis"]).to_numpy()].iterrows():
            piezas["admitidas"].append({"tipo": "fallo", "serial_number": x["serial_number"],
                                        "fecha": x["dia_fallo"].date().isoformat(), "model": x["model"],
                                        "edad": int(x["edad_anos_cumplidos"]), "edad_analisis": int(x["edad_analisis"])})
        if modo == "ensayo":
            dias_a, _ = repartir_dias(d.drop(columns=["edad_anos_cumplidos"]), rec_mes, capacidad, "edad_analisis")
            piezas["tramos_analisis"].append(tramo_del_mes(
                dias_a, fallos.drop(columns=["edad_anos_cumplidos"]).rename(columns={"edad_analisis": "edad_anos_cumplidos"}), f))
        piezas["meses"].append({"mes": f.date().isoformat(), "filas_foto_datos": int(len(d)), "filas_foto_arranque": arranque,
                                "dias_disco": float(tramo["dias_disco"].sum()), "fallos": int(tramo["fallos"].sum()),
                                "fallos_lista_datos": int(len(fallos)), "fallos_sin_horas": int(fallos["horas"].isna().sum()),
                                "fallos_fuera": fuera, "modelos_con_dos_capacidades": sorted(dobles), **info})
        # El primer día de un trimestre: los discos de la foto por modelo, capacidad y año de edad
        q = next((x for x in trims if x["inicio"] == f), None)
        if q is not None:
            for col, destino in (("edad_anos_cumplidos", "inicio"), ("edad_analisis", "inicio_analisis")):
                i = d.groupby(["model", "capacidad_tb", col]).size().rename("discos").reset_index()
                i = i.rename(columns={col: "edad_anos_cumplidos"}).assign(ano=q["ano"], trimestre=q["t"],
                                                                          dias_trimestre=q["dias"])
                piezas[destino].append(i)
    for k in ("inicio", "inicio_analisis", "tramos", "tramos_analisis", "fallos", "capacidades"):
        piezas[k] = pd.concat(piezas[k], ignore_index=True) if piezas[k] else None
    piezas["trimestres"], piezas["meses_periodo"], piezas["desde"] = trims, meses, desde
    piezas["lista_por_mes"] = lista.assign(mes=lista["dia_fallo"].dt.to_period("M").dt.start_time).groupby("mes").size()
    return piezas


def mapa_de_capacidad(dm, piezas):
    """La capacidad en TB de cada modelo de datos: la de dim_modelo y, para un modelo nuevo, la de sus fotos (las del
    primer día y las de cada mes) y sus fallos; para con ERROR si un modelo trae dos capacidades."""
    mapa = dm.loc[dm["tipo_disco"] == "datos"].set_index("model")["capacidad_tb"].astype(float).to_dict()
    nuevas = pd.concat([piezas[k][["model", "capacidad_tb"]] for k in ("inicio", "fallos", "capacidades")
                        if piezas.get(k) is not None], ignore_index=True).drop_duplicates()
    for modelo, g in nuevas.groupby("model"):
        caps = set(g["capacidad_tb"].astype(float))
        if modelo in mapa:
            caps.add(mapa[modelo])
        if len(caps) > 1:
            raise Parada(f"el modelo {modelo} sale con dos capacidades: {sorted(caps)}")
        mapa[modelo] = caps.pop()
    return mapa


def correr(piezas, dpt, mapa, reales_anterior, tramos="tramos", inicio="inicio"):
    """La previsión de los trimestres del periodo con unas piezas: historia, previsiones, pares y error."""
    trims, desde = piezas["trimestres"], piezas["desde"]
    hist = pd.concat([dpt.loc[(dpt["mes"] < desde).to_numpy()], piezas[tramos]], ignore_index=True)
    hist["capacidad_tb"] = hist["model"].map(mapa)
    if hist["capacidad_tb"].isna().any():
        raise Parada(f"modelos de la historia sin capacidad: {sorted(set(hist.loc[hist['capacidad_tb'].isna(), 'model']))}")
    it = piezas[inicio]
    f = piezas["fallos"]
    etiquetas = [f"{d.year}T{(d.month - 1) // 3 + 1}" for d in f["dia_fallo"]]
    reales = {(t, float(k)): int(n) for (t, k), n in f.groupby([pd.Series(etiquetas, index=f.index), f["capacidad_tb"]]).size().items()}
    reales.update(reales_anterior)
    anterior = {q["trimestre"]: etiqueta_anterior(q["trimestre"]) for q in trims}
    previsiones, ultimos, niveles = {}, {}, []
    for q in trims:
        p = prever_trimestre(q["ano"], q["t"], it, hist)
        previsiones[q["trimestre"]] = p["previsto_por_capacidad"]
        ultimos[q["trimestre"]] = p["ultimo_mes_usado"]
        n = p["filas"].groupby("nivel")["discos"].sum()
        niveles.append({"trimestre": q["trimestre"], **{k: int(n.get(k, 0)) for k in list(NIVELES) + ["sin tasa"]},
                        "discos": int(p["filas"]["discos"].sum()),
                        "ultimo_mes_usado": p["ultimo_mes_usado"].date().isoformat() if p["ultimo_mes_usado"] is not None else None})
    pares = montar_pares(previsiones, reales, trims, anterior)
    return {"pares": pares, "total": resumen_error(pares), "por_trimestre": resumen_error(pares, "trimestre"),
            "ultimos": ultimos, "niveles": niveles, "hist": hist}


def reales_del_anterior(pares_b9, trimestre):
    """Los fallos reales del trimestre anterior al periodo, por capacidad, de B9.tablas.pares: solo los que tienen
    fallos, como los reales del script 10."""
    xs = [p for p in pares_b9 if p["trimestre"] == trimestre]
    if not xs:
        raise Parada(f"B9.tablas.pares no trae el trimestre {trimestre}, la referencia del primero del periodo")
    return {(trimestre, float(p["capacidad_tb"])): int(p["real"]) for p in xs if int(p["real"]) > 0}


# =================================================================================================================
# 8. El ensayo frente al análisis
# =================================================================================================================
def frente_al_analisis(piezas, an, res_analisis):
    """Las piezas rehechas como el análisis frente a inicio_trimestre y dias_por_tramo, y los pares frente a
    B9.tablas.pares. Devuelve la lista de diferencias, con su texto."""
    trims = piezas["trimestres"]
    dist = []
    # (a) inicio_trimestre, por trimestre, modelo y año de edad; y los días de cada trimestre
    i = piezas["inicio_analisis"]
    del_periodo = {(q["ano"], q["t"]) for q in trims}
    it = an["it"]
    it = it.loc[np.array([(a, t) in del_periodo for a, t in zip(it["ano"], it["trimestre"])], dtype=bool)]
    clave = ["ano", "trimestre", "model", "edad_anos_cumplidos"]
    dist += diferencias("discos del primer día", i.set_index(clave)["discos"], it.set_index(clave)["discos"])
    dist += diferencias("días del trimestre", i.groupby(["ano", "trimestre"])["dias_trimestre"].first(),
                        it.groupby(["ano", "trimestre"])["dias_trimestre"].first(), faltan_son_cero=False)
    # (a) dias_por_tramo de los meses del periodo, por modelo, mes y año de edad: el centro solo reparte los días
    t = piezas["tramos_analisis"]
    d = an["dpt"].loc[an["dpt"]["mes"].isin(pd.DatetimeIndex(piezas["meses_periodo"]).astype("datetime64[ms]")).to_numpy()]
    clave = ["model", "mes", "edad_anos_cumplidos"]
    a, b = t.groupby(clave)[["dias_disco", "fallos"]].sum(), d.groupby(clave)[["dias_disco", "fallos"]].sum()
    dist += diferencias("días de disco", a["dias_disco"], b["dias_disco"], TOLERANCIA)
    dist += diferencias("fallos", a["fallos"], b["fallos"])
    # (b) los pares, frente a B9.tablas.pares: previsto con tolerancia, real y referencia exactos
    nombres = {q["trimestre"] for q in trims}
    p_r = {(p["trimestre"], float(p["capacidad_tb"])): p for p in res_analisis["pares"]}
    p_a = {(p["trimestre"], float(p["capacidad_tb"])): p for p in an["pares"] if p["trimestre"] in nombres}
    for campo, tol in (("previsto", TOLERANCIA), ("real", None), ("referencia", None)):
        dist += diferencias(f"par {campo}", pd.Series({k: v[campo] for k, v in p_r.items()}, dtype="float64"),
                            pd.Series({k: v[campo] for k, v in p_a.items()}, dtype="float64"), tol, faltan_son_cero=False)
    return dist


def ensayo_listo(raiz):
    """None si informes/prueba_final_prevision_ensayo.json está en OK, igual al análisis y con las mismas entradas y el
    mismo script; si no, el motivo."""
    ruta = ruta_de(raiz, MODOS["ensayo"]["json"])
    if not ruta.exists():
        return f"no existe {MODOS['ensayo']['json']}: primero el ensayo con la validación"
    js = json.loads(ruta.read_text(encoding="utf-8"))
    estado = (js.get("resultado") or {}).get("estado")
    if estado != "OK" or (js.get("comparacion") or {}).get("iguales") is not True:
        return f"el ensayo con la validación no está en OK e igual al análisis (estado {estado})"
    if js.get("huellas_de_entrada") != huellas_de_entrada(raiz):
        return "las tablas del análisis, el JSON de B9, el módulo o este script cambiaron después del ensayo"
    return None


# =================================================================================================================
# 9. El JSON y el informe
# =================================================================================================================
def a_json(v):
    """Pasa a tipos que JSON acepta, sin NaN."""
    if isinstance(v, dict):
        return {str(k): a_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [a_json(x) for x in v]
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) or np.isinf(v) else float(v)
    if isinstance(v, pd.Timestamp):
        return v.date().isoformat()
    return v


def base(modo):
    """El diccionario del resultado, con el bloque común."""
    m = MODOS[modo]
    return {"skill": SKILL, "script": SCRIPT, "encargo": ENCARGO, "modo": m["argumento"], "fecha_datos": m["fin"],
            "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
            "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": "sin terminar", "artefactos": [m["json"]],
                          "siguiente": ""},
            "periodo": {"desde": m["desde"], "hasta": m["hasta"], "fin": m["fin"], "datos": m["datos"]},
            "validaciones": {}}


def escribir_json(raiz, modo, res):
    """Escribe el JSON del modo."""
    ruta = ruta_de(raiz, MODOS[modo]["json"])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(a_json(res), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")


def error(x):
    """Un error absoluto ponderado con cuatro decimales, a la española."""
    return numero(x, 4)


def pct(x):
    """Un sesgo como porcentaje con un decimal y su signo en palabras."""
    return f"{numero(abs(x) * 100, 1)} %"


def informe_md(res):
    """informes/prueba_final_prevision.md, generado del JSON (transmision-conocimiento). Ninguna frase lleva más de dos
    cifras, y la primera dice si la cuenta gana."""
    t, gana = res["total"], res["gana_la_cuenta"]
    trims = [q["trimestre"] for q in res["por_trimestre"]]
    cifras = (f"Se equivoca en {error(t['wape_cuenta'])} fallos por cada fallo real, frente a "
              f"{error(t['wape_referencia'])} de la referencia.")
    if gana:
        veredicto = ("La cuenta por modelo y edad gana a repetir los fallos del trimestre anterior en el año guardado. "
                     f"{cifras}")
    else:
        veredicto = ("La cuenta por modelo y edad no gana a repetir los fallos del trimestre anterior en el año guardado. "
                     f"{cifras} Se sigue usando la referencia, como fija la regla de la previsión.")

    def sesgo(s):
        """El sesgo en palabras: cuánto prevé de más o de menos frente a los fallos reales."""
        return "acierta el total" if s == 0 else (f"prevé un {pct(s)} más" if s > 0 else f"prevé un {pct(s)} menos")

    L = ["# Prueba final de la previsión de fallos", "", veredicto, "",
         "## Lo que lo sostiene", "",
         f"El año guardado va de {trims[0]} a {trims[-1]}. En esos trimestres hubo {numero(t['real'])} fallos de discos "
         f"de datos. La cuenta previó {numero(t['previsto'], 1)}.",
         f"Repetir el trimestre anterior daba {numero(t['referencia'])}. Frente a los fallos reales, la cuenta "
         f"{sesgo(t['sesgo_cuenta'])} y la referencia {sesgo(t['sesgo_referencia'])}.", "",
         "El error de un trimestre es la suma de lo que se equivoca la previsión en cada capacidad, sin signo, entre "
         "sus fallos reales.", "",
         "| Trimestre | Fallos reales | Previstos por la cuenta | Referencia | Error de la cuenta | Error de la referencia |",
         "|---|---:|---:|---:|---:|---:|"]
    for q in res["por_trimestre"]:
        L.append(f"| {q['trimestre']} | {numero(q['real'])} | {numero(q['previsto'], 1)} | {numero(q['referencia'])} | "
                 f"{error(q['wape_cuenta']) if q['wape_cuenta'] is not None else 'sin fallos'} | "
                 f"{error(q['wape_referencia']) if q['wape_referencia'] is not None else 'sin fallos'} |")
    L += ["", "## Cada trimestre y capacidad", "",
          "Entran las capacidades con discos el primer día del trimestre, con fallos en él o con fallos en el trimestre "
          "anterior.", "",
          "| Trimestre | Capacidad (TB) | Previstos | Reales | Referencia |", "|---|---:|---:|---:|---:|"]
    L += [f"| {p['trimestre']} | {numero(p['capacidad_tb'], 0 if float(p['capacidad_tb']).is_integer() else 1)} | "
          f"{numero(p['previsto'], 1)} | {numero(p['real'])} | {numero(p['referencia'])} |" for p in res["pares"]]
    L += ["", "## Límites", ""]
    L += [f"- {x}" for x in res["limites"]]
    L += ["", "## Lo que se puede hacer ya", "",
          "- Llevar el resultado al informe final, al cuadro de mando y al README."]
    if gana:
        L.append("- Juan decide si la cuenta sustituye a la referencia: el resultado no lo cambia por sí solo.")
    return "\n".join(L) + "\n"


def limites(res):
    """Los límites del resultado, con sus cifras sacadas de lo medido; ninguna frase con más de dos cifras."""
    meses = res["piezas"]["meses"]
    sin_foto = sum(x["dias_sin_foto"] for x in meses)
    fuera = {k: sum(x["fallos_fuera"][k] for x in meses) for k in meses[0]["fallos_fuera"]}
    L = ["El error se da sin intervalo, como en el análisis: es una sola medida de todos los trimestres juntos.",
         f"La referencia del primer trimestre son los fallos reales de {res['trimestre_anterior']} del análisis.",
         f"Quedan sin repartir {numero(sin_foto)} días de disco de celdas de modelo, centro y mes sin ninguna foto. "
         "No cuentan en las tasas de los trimestres siguientes."]
    if fuera["de_arranque"]:
        L.append(f"Los fallos de discos de arranque no entran, como en el análisis: son {numero(fuera['de_arranque'])}.")
    otros = fuera["sin_ventana_del_dia"] + fuera["sin_capacidad"]
    if otros:
        L.append("Los fallos de la lista sin modelo o capacidad conocidos el día del fallo no entran en ninguna capacidad: "
                 f"son {numero(otros)}.")
    L.append("El año guardado se midió una sola vez, después del ensayo con la validación.")
    return L


# =================================================================================================================
# 10. Principal
# =================================================================================================================
def medir(raiz, modo, res):
    """Rehace las piezas del modo, prevé cada trimestre y rellena `res` con las cifras y las validaciones calculadas."""
    m = MODOS[modo]
    if modo == "reserva":
        motivo = ensayo_listo(raiz)
        if motivo:
            raise Parada(f"el año guardado no se abre: {motivo}")
    res["huellas_de_entrada"] = huellas_de_entrada(raiz)
    conf, mapeo, minimo = leer_configuracion(raiz)
    carpetas = historia_del_modo(raiz, conf, modo)
    res["historia"] = {k: [Path(c).relative_to(Path(raiz)).as_posix() if Path(c).is_relative_to(Path(raiz)) else str(c)
                           for c in v] for k, v in carpetas.items()}
    an = leer_analisis(raiz)
    piezas = rehacer_periodo(raiz, m, modo, carpetas, mapeo, minimo)
    trims = piezas["trimestres"]
    res["trimestre_anterior"] = etiqueta_anterior(trims[0]["trimestre"])
    reales_ant = reales_del_anterior(an["pares"], res["trimestre_anterior"])
    mapa = mapa_de_capacidad(an["dm"], piezas)
    r = correr(piezas, an["dpt"], mapa, reales_ant)

    # 10.1 Las cifras: piezas, pares, error y si gana la cuenta
    ini = piezas["inicio"]
    res["piezas"] = {
        "inicio": [{"trimestre": q["trimestre"], "fecha": q["inicio"].date().isoformat(), "dias_trimestre": q["dias"],
                    "filas": int(((ini["ano"] == q["ano"]) & (ini["trimestre"] == q["t"])).sum()),
                    "discos": int(ini.loc[(ini["ano"] == q["ano"]) & (ini["trimestre"] == q["t"]), "discos"].sum())}
                   for q in trims],
        "meses": piezas["meses"],
        "historia_rehecha": piezas["tramos"].assign(mes=piezas["tramos"]["mes"].dt.date.astype(str)).to_dict("records"),
        "totales": {"filas_historia_rehecha": int(len(piezas["tramos"])), "dias_disco": float(piezas["tramos"]["dias_disco"].sum()),
                    "fallos": int(piezas["tramos"]["fallos"].sum())}}
    res["pares"], res["total"], res["por_trimestre"], res["niveles"] = r["pares"], r["total"], r["por_trimestre"], r["niveles"]
    tot = r["total"]
    res["gana_la_cuenta"] = bool(tot["wape_cuenta"] is not None and tot["wape_cuenta"] < tot["wape_referencia"])
    res["veredicto"] = ("la cuenta gana; que pase a usarse lo decide Juan" if res["gana_la_cuenta"]
                        else "la cuenta no gana: no vale y se usa la referencia (reglas §7)")
    res["diferencias_admitidas"] = piezas["admitidas"]

    # 10.2 Las validaciones, calculadas
    v = res["validaciones"]
    v["sin_futuro"] = comp_sin_futuro([r["ultimos"][q["trimestre"]] for q in trims], [q["inicio"] for q in trims])
    v["totales_suman_los_trimestres"] = comp_totales(r["total"], r["por_trimestre"])
    v["dias_repartidos_cuadran_con_el_recuento"] = comp_cuadre([x["dias_repartidos"] for x in piezas["meses"]],
                                                               [x["dias_recuento_con_foto"] for x in piezas["meses"]])
    lista_mes = piezas["lista_por_mes"]
    v["fallos_cuadran_con_la_lista"] = comp_cuadre(
        [x["fallos"] for x in piezas["meses"]],
        [int(lista_mes.get(pd.Timestamp(x["mes"]), 0)) - sum(x["fallos_fuera"].values()) for x in piezas["meses"]])
    v["trimestres_medidos"] = sorted({p["trimestre"] for p in r["pares"]}) == sorted(q["trimestre"] for q in trims)
    v["sin_resultados_escritos"] = sin_resultados_escritos(Path(__file__).read_text(encoding="utf-8"))
    if modo == "ensayo":
        ra = correr(piezas, an["dpt"], mapa, reales_ant, "tramos_analisis", "inicio_analisis")
        distintos = frente_al_analisis(piezas, an, ra)
        p_b9 = {(p["trimestre"], float(p["capacidad_tb"])): p["previsto"] for p in an["pares"]}
        res["comparacion"] = {"iguales": not distintos, "distintos": distintos[:200], "n_distintos": len(distintos),
                              "contra": [INICIO, DPT, f"{INDICADORES} (B9.tablas.pares)"],
                              "max_diferencia_previsto_con_la_regla_del_contrato": max(
                                  [abs(p["previsto"] - p_b9.get((p["trimestre"], float(p["capacidad_tb"])), 0.0))
                                   for p in r["pares"]], default=0.0)}
        v["igual_al_analisis"] = not distintos
        v["diferencias_admitidas"] = admitidas_ok(piezas["admitidas"])
    return r


def principal(raiz, modo):
    """Un modo entero; escribe el JSON (y, en el año guardado, el informe). Devuelve el código de salida."""
    raiz = Path(raiz).resolve()
    m = MODOS[modo]
    # El año guardado se mide una vez: si ya hay una medida terminada, no se toca
    previo = ruta_de(raiz, m["json"])
    if modo == "reserva" and previo.exists() and (json.loads(previo.read_text(encoding="utf-8")).get("resultado") or {}).get(
            "estado") in ("OK", "AVISO"):
        print(f"PARADO: el año guardado ya se midió ({m['json']}); no se vuelve a medir", file=sys.stderr)
        return 2
    res = base(modo)
    antes = huellas_raw(raiz)
    try:
        medir(raiz, modo, res)
        res["validaciones"]["huella_de_data_raw_igual"] = comp_huellas(antes, huellas_raw(raiz))
        res["limites"] = limites(res)
        rojas = [k for k, x in res["validaciones"].items() if x is False]
        if rojas:
            detalle = "; ".join((res.get("comparacion") or {}).get("distintos", [])[:MAX_DIFERENCIAS])
            adm = [f"{a['tipo']} {a['serial_number']} {a['fecha']}" for a in res.get("diferencias_admitidas", [])]
            raise Parada(f"validaciones en rojo: {', '.join(rojas)}" + (f". Difiere: {detalle}" if detalle else "")
                         + (f". Edad distinta: {', '.join(adm[:MAX_DIFERENCIAS])}" if adm else ""))
        if modo == "reserva":
            texto = informe_md(res)
            res["resultado"] = {"estado": "OK" if res["gana_la_cuenta"] else "AVISO",
                                "riesgo": "bajo" if res["gana_la_cuenta"] else "medio",
                                "resumen": texto.split("\n")[2], "artefactos": [m["json"], INFORME_MD],
                                "siguiente": "el informe final, el cuadro de mando y el README dicen el resultado"}
            ruta_de(raiz, INFORME_MD).write_text(texto, encoding="utf-8")
        else:
            res["resultado"] = {"estado": "OK", "riesgo": "bajo",
                                "resumen": (f"El ensayo rehace desde los datos en bruto las piezas de los {len(res['por_trimestre'])} "
                                            "trimestres y da lo mismo que el análisis: el año guardado se puede abrir con --reserva."),
                                "artefactos": [m["json"]], "siguiente": "scripts/20_prueba_final_prevision.py --reserva"}
        codigo = 0
    except (Parada, pr.ErrorDeProduccion) as e:
        estado = getattr(e, "estado", "ERROR")
        res["resultado"] = {"estado": estado, "riesgo": "alto", "resumen": f"El script paró: {e}"[:4000],
                            "artefactos": [m["json"]], "siguiente": "resolver la causa y volver a ejecutar"}
        codigo = 2 if estado == "PARADO" else 1
    except Exception as e:  # noqa: BLE001 - el JSON se escribe también cuando falla
        res["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(e).__name__}: {e}"[:4000],
                            "artefactos": [m["json"]], "siguiente": "corregir el fallo y volver a ejecutar"}
        res["traza"] = traceback.format_exc()[-3000:]
        codigo = 1
    res["parametros"] = [{"nombre": "modo", "valor": m["argumento"], "origen": "argumento"},
                         {"nombre": "periodo", "valor": f"{m['desde']} a {m['hasta']}", "origen": "encargo 24; guion, paso 6"},
                         {"nombre": "mínimo de días de un nivel de tasa", "valor": MINIMO_DIAS_ANO, "origen": "reglas §7; script 10"},
                         {"nombre": "niveles de tasa", "valor": list(NIVELES), "origen": "reglas §7; script 10"},
                         {"nombre": "tolerancia en días y previstos", "valor": TOLERANCIA, "origen": "encargo 24"}]
    res["ejecucion"] = {"python": platform.python_version(), "ejecutable": sys.executable, "pandas": pd.__version__,
                        "pyarrow": pa.__version__}
    escribir_json(raiz, modo, res)
    print(f"{res['resultado']['estado']}: {res['resultado']['resumen'][:2000]}")
    return codigo


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Prueba final de la previsión de fallos: el ensayo con la validación o el año guardado")
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--ensayo-validacion", action="store_true", help="ensayo con la validación, comparado con el análisis")
    modo.add_argument("--reserva", action="store_true", help="el año guardado, una sola vez y con el ensayo en OK")
    ap.add_argument("--raiz", default=str(CASO), help="carpeta del caso (por defecto, la del script)")
    a = ap.parse_args()
    print(f"sys.executable: {sys.executable}")
    sys.exit(principal(Path(a.raiz), "reserva" if a.reserva else "ensayo"))
