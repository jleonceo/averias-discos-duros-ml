"""Indicadores de los bloques 4 y 9 del plan de la analítica del caso 68: el coste por TB y año y la previsión de fallos.

Skill indicadores-y-analisis (paso 5, parte sin modelo), con el encargo prompts/14_encargo_indicadores_coste_prevision.md.
Calcula, comprueba y deja en informes/indicadores__coste_prevision.json (y su informe .md, generado del mismo
diccionario en la misma ejecución):

  - B4, cuánto cuesta cada modelo: el coste por TB y año de los 32 modelos del ranking, con garantía y con el intervalo
    que sale del de la tasa; sin puesto los de menos de 20 fallos (CP-012); el coste a igual edad, con la tasa a igual
    edad del JSON del 09, y la sensibilidad al precio inferido (encargo 17,
    prompts/17_encargo_correcciones_del_auditor.md); la parte de los fallos, la correlación de orden con la tasa y el
    precio inferido; la vida
    real por tabla de vida; el mejor modelo de cada año y capacidad, con la diferencia partida en precio y fallos; el
    ingreso por TB de 2023 y 2024 al lado del coste por TB y año.
  - B9, la previsión de fallos por trimestre y capacidad, de 2021T1 a 2025T2, con lo sabido el primer día, frente a
    repetir los fallos del trimestre anterior; los niveles de tasa, la sensibilidad y los fallos que la cuenta no ve.

La previsión de un trimestre está en `prever_trimestre`, que recibe el trimestre: la usará la prueba final en la
reserva. Cada cifra lleva su segunda vía, que parte de otra tabla o de otro cálculo. Si una no coincide, para con ERROR.
Las comprobaciones y las validaciones de la skill se calculan; ninguna lleva el resultado escrito.

Lee data/processed/ y los JSON de informes/ de la transformación, de dos exploratorios y del encargo 13, que no
modifica, y el doc. 16 del sector. Depende de scripts/05_transformacion_datos.py, de 06_analisis_exploratorio.py y de
09_indicadores_discos_modelos_edad.py: comprueba la huella de cada tabla contra informes/transformacion-datos.json y el
estado de los JSON de los que parte. No importa ningún script.

Uso: python -W error scripts/10_indicadores_coste_prevision.py [--raiz CARPETA_DEL_CASO]
Sale con 0 si termina, con 2 si para (PARADO o ERROR) y con 1 si falla por otra causa; en los tres casos escribe el JSON.
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
SCRIPT = "scripts/10_indicadores_coste_prevision.py"
ENCARGO = ("prompts/14_encargo_indicadores_coste_prevision.md; B4 cambiado por "
           "prompts/17_encargo_correcciones_del_auditor.md y por "
           "prompts/19_encargo_correcciones_del_segundo_auditor.md")
SALIDA_JSON = "informes/indicadores__coste_prevision.json"
SALIDA_MD = "informes/indicadores__coste_prevision.md"
TRANSFORMACION = "informes/transformacion-datos.json"
SKILL_MD = ".claude/skills/indicadores-y-analisis/SKILL.md"
PROTECCION = "contexto-proyecto/fuentes/proteccion-datos.json"
DOC16 = "contexto-proyecto/sector/documentos/16_backblaze_10k_2025_tablas_ingresos.txt"
# JSON de los que parte el encargo; si uno falta o está en PARADO o ERROR, no se calcula nada
PREVIOS = ["analisis-exploratorio__modelo_trimestre", "analisis-exploratorio__dias_por_tramo",
           "indicadores__discos_modelos_edad"]
# Tablas salidas de la transformación y tablas de entrada (las corregidas y el calendario)
TABLAS_SALIDA = ["dim_modelo", "dim_precio_gb", "modelo_trimestre", "inicio_trimestre", "dias_por_tramo",
                 "fallos_detalle", "vida_discos"]
TABLAS_ENTRADA = ["recuento_diario_corregido", "fotos_mensuales_corregido", "ventanas_fallo_corregido", "calendario"]

# Fecha de referencia de los datos (reglas §5)
FECHA_DATOS = dt.date(2025, 6, 30)
# Mínimo para un ranking y para la tasa de una celda de la previsión: días de disco (reglas §7; encargo, criterio 5)
MINIMO_DIAS_ANO = 50_000
# Un año de edad con menos fallos que esto corta la curva de supervivencia (reglas §7, CP-009; encargo 13)
MINIMO_FALLOS_EDAD = 20
# Confianza de los intervalos (skill, parametros.md; 42.6 del manual)
CONFIANZA = 0.95
# Vida contable en años, mano de obra de un cambio en dólares y horas de técnico por cambio (reglas §5 y §6)
VIDA_CONTABLE = 6
COSTE_CAMBIO = 37
HORAS_POR_CAMBIO = 0.74
# Gigabytes por terabyte (reglas §6) y días de un año para pasar días de disco a terabytes-año
GB_POR_TB = 1000
DIAS_ANO = 365
# Factor de la tasa anual en %: 100 × 365 (reglas §6)
FACTOR_TASA = 100 * DIAS_ANO
# Años de edad de la tabla de vida (reglas de transformación §6: de 0 a 10) y nivel de la vida real (encargo)
EDADES = list(range(11))
S_VIDA = 0.5
# Años con ingreso por TB: 2025 necesita la reserva (reglas §6)
ANOS_INGRESO = [2023, 2024]
# Primer trimestre que se prevé: tiene un año de tasas detrás (encargo; reglas §7)
PRIMER_PREVISTO = (2021, 1)
# Niveles de la tasa de la previsión, en su orden (encargo, criterio 5)
NIVELES = ("modelo", "capacidad", "edad")
# Sensibilidad, solo para leer: (nombre, meses de historia o None si toda, mínimo de días, niveles)
MESES_CORTO = 12
VARIANTES = [("12 meses de historia", MESES_CORTO, MINIMO_DIAS_ANO, NIVELES),
             ("mínimo de 1 día, toda la historia", None, 1, NIVELES),
             ("mínimo de 1 día, 12 meses de historia", MESES_CORTO, 1, NIVELES),
             ("solo capacidad y año de edad", None, MINIMO_DIAS_ANO, ("capacidad", "edad"))]
# Diferencia que se admite entre dos vías en importes y en cifras con decimales (encargo, «SEGUNDA VÍA»)
TOLERANCIA = 1e-6
# Primeros del ranking en los que se cuenta el precio inferido (encargo, B4.2)
N_PRIMEROS = 10
# Un modelo con menos fallos que esto en sus años que pasan el mínimo sale sin puesto (reglas §7, CP-012; encargo 17)
MINIMO_FALLOS_MODELO = 20
# Factores sobre el precio inferido en la sensibilidad (encargo 17, B4.3; criterio técnico de Claude)
FACTORES_PRECIO = (0.8, 1.2)
# JSON del 09 del que sale la tasa a igual edad de cada modelo (encargo 17, B4.2)
JSON_09 = "informes/indicadores__discos_modelos_edad.json"
# La palabra vetada para el conjunto de discos (Juan, 17/11; R68-91), partida para que el código no la lleve
VETADA = "flo" + "ta"

COMPROBACIONES = ["unidad", "minimo", "empates", "referencia", "azar_en_grupos", "pesos", "hacia_adelante",
                  "cobertura", "periodos"]
VALIDACIONES = ["planteamiento_completo", "cifras_con_poblacion", "segunda_via", "minimo_respetado",
                "con_referencia", "comprobaciones_calculadas", "reproducible", "sin_resultados_escritos",
                "raw_intacto"]
EXTRAS = ["partes_suman_total", "sin_futuro", "reales_cuadran_recuento", "sin_palabra_vetada", "puesto_dentro_del_grupo"]
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


def etiqueta(ano, t):
    """«2024T1»."""
    return f"{int(ano)}T{int(t)}"


def inicio_trimestre(ano, t):
    """Primer día del trimestre."""
    return pd.Timestamp(int(ano), 3 * int(t) - 2, 1)


def a_ms(serie):
    """Fechas a milisegundos, para que todas las tablas se comparen igual."""
    return serie.astype("datetime64[ms]")


def nativo(x):
    """Convierte tipos de numpy y pandas a tipos de Python para el JSON; NaN pasa a None."""
    if isinstance(x, dict):
        return {str(k): nativo(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [nativo(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return r(x, 10)
    if isinstance(x, pd.Timestamp):
        return iso(x)
    return x


# =================================================================================================================
# 4. Estadística y supervivencia
# =================================================================================================================
def intervalo_poisson(fallos, dias, confianza=CONFIANZA):
    """Tasa anual en % y su intervalo exacto de Poisson (con chi2), pasados a tasa con los mismos días de disco.

    Inferior chi2.ppf(α/2; 2f)/2, 0 si f = 0; superior chi2.ppf(1 − α/2; 2f + 2)/2 (encargo 13, el mismo criterio).
    """
    a = 1 - confianza
    f = int(fallos)
    lo = 0.0 if f == 0 else stats.chi2.ppf(a / 2, 2 * f) / 2
    hi = stats.chi2.ppf(1 - a / 2, 2 * f + 2) / 2
    k = FACTOR_TASA / float(dias)
    return f * k, float(lo) * k, float(hi) * k


def tabla_de_vida(edad_entrada, edad_fin, es_evento, edades=EDADES):
    """Exposición en años, eventos y tasa por año de edad, con entrada tardía (encargo 13, criterio 2 de este encargo).

    Exposición del año j = suma de max(0, min(edad_fin, j + 1) − max(edad_entrada, j)); eventos del año j = discos con
    evento y floor(edad_fin) = j; tasa = eventos / exposición (None si no hay exposición).
    """
    e0 = np.asarray(edad_entrada, dtype=float)
    e1 = np.asarray(edad_fin, dtype=float)
    ev = np.asarray(es_evento, dtype=bool)
    piso = np.floor(e1)
    filas = []
    for j in edades:
        expo = float(np.clip(np.minimum(e1, j + 1) - np.maximum(e0, j), 0, None).sum())
        eventos = int((ev & (piso == j)).sum())
        filas.append({"edad": j, "exposicion_anos": expo, "eventos": eventos,
                      "tasa": eventos / expo if expo > 0 else None})
    return filas


def supervivencia(tasas):
    """S(k) = exp(−(tasa_0 + … + tasa_{k−1})) para k = 0 … len(tasas) − 1; None desde una tasa que falta."""
    s, acum = [1.0], 0.0
    for t in tasas[:-1]:
        if t is None or acum is None:
            acum = None
            s.append(None)
            continue
        acum += t
        s.append(math.exp(-acum))
    return s


def cortar_curva(s, eventos_por_ano, minimo):
    """Corta la curva antes del primer año de edad con menos de `minimo` fallos (CP-009; encargo 13).

    S(k) usa las tasas de los años 0 a k − 1, así que S(j) vale aunque el año j tenga pocos fallos; desde S(j + 1), None.
    Devuelve la curva cortada y el motivo, o None si no hay que cortar.
    """
    j0 = next((j for j, n in enumerate(eventos_por_ano) if n < minimo), None)
    if j0 is None:
        return list(s), None
    curva = [v if k <= j0 else None for k, v in enumerate(s)]
    motivo = (f"el año de edad {j0} tiene {eventos_por_ano[j0]} fallos, menos de {minimo}: "
              f"la curva se corta después de S({j0})")
    return curva, motivo


def vida_real(s, tasas, nivel=S_VIDA):
    """Edad a la que la curva con base baja de `nivel`, dentro del año en que cruza (tasa constante en el año).

    Si S(k) < nivel y S(k − 1) ≥ nivel, la edad es k − 1 + (ln(1/nivel) − H(k − 1)) / tasa_{k−1}, con H = −ln S.
    Devuelve (edad, None) o (None, motivo) si la curva con base no baja de `nivel`.
    """
    validos = [k for k, v in enumerate(s) if v is not None]
    for k in validos[1:]:
        if s[k] < nivel:
            h_prev = -math.log(s[k - 1])
            return (k - 1) + (math.log(1 / nivel) - h_prev) / tasas[k - 1], None
    ultima = validos[-1] if validos else None
    if ultima is None or ultima == 0:
        return None, "ningún año de edad del modelo tiene 20 fallos o más: la curva no tiene base"
    return None, (f"la curva con base no baja de {numero(nivel, 1)}: S vale {numero(s[ultima], 4)} a {ultima} años, "
                  "la última edad con base")


def tabla_de_vida_bucle(modelos, entrada, fin, evento, edades=EDADES):
    """La misma tabla de vida por modelo, disco a disco (segunda vía, otro cálculo): {modelo: (exposición, eventos)}."""
    tope = max(edades)
    out = {}
    for m, e0, e1, ev in zip(modelos, entrada, fin, evento):
        expo, evs = out.setdefault(m, ([0.0] * len(edades), [0] * len(edades)))
        if e1 > e0:
            for j in range(max(0, math.floor(e0)), min(math.floor(e1), tope) + 1):
                trozo = min(e1, j + 1) - max(e0, j)
                if trozo > 0:
                    expo[j] += trozo
        if ev and 0 <= math.floor(e1) <= tope:
            evs[math.floor(e1)] += 1
    return out


# =================================================================================================================
# 5. Comprobaciones (skill §4 y encargo): cada una devuelve True o False calculado con lo ejecutado
# =================================================================================================================
def comp_unidad(claves):
    """La unidad se cuenta una vez: ninguna clave repetida."""
    claves = list(claves)
    return len(set(claves)) == len(claves)


def comp_empates(valores, puestos):
    """Dos entidades con el mismo valor tienen el mismo puesto."""
    por_valor = {}
    for v, p in zip(valores, puestos):
        por_valor.setdefault(v, set()).add(p)
    return all(len(ps) == 1 for ps in por_valor.values())


def comp_minimo_ranking(dias_ano, marcas, minimo):
    """La marca de cada celda dice lo mismo que sus días de disco del año frente al mínimo."""
    return all(bool(m) == (d >= minimo) for d, m in zip(dias_ano, marcas))


def comp_puesto_minimo(filas, minimo=MINIMO_FALLOS_MODELO):
    """Ningún modelo con menos de `minimo` fallos lleva puesto, y todos los demás lo llevan (CP-012; encargo 17)."""
    return all((f["puesto"] is None) == (f["fallos"] < minimo) for f in filas)


def comp_puesto_grupo(filas, minimo=MINIMO_FALLOS_MODELO):
    """Ningún puesto de B4 compara modelos de distinta capacidad o año de compra (encargo 19).

    Rehace los grupos con la capacidad y el año de compra de cada fila y, dentro de cada uno, el puesto de los modelos
    con `minimo` fallos o más por su coste (empates, el mismo puesto); los demás, sin puesto.
    """
    grupos = {}
    for f in filas:
        if f["fallos"] >= minimo:
            grupos.setdefault((f["capacidad_tb"], f.get("ano_compra")), []).append(f["coste_tb_ano"])
    for f in filas:
        if f["fallos"] < minimo:
            debe = None
        else:
            debe = 1 + sum(1 for c in grupos[(f["capacidad_tb"], f.get("ano_compra"))] if c < f["coste_tb_ano"])
        if f.get("puesto") != debe:
            return False
    return True


def comp_minimo_tasas(niveles_y_dias, minimo):
    """Ninguna tasa de nivel modelo o capacidad sale de una celda por debajo del mínimo de días."""
    return all(d >= minimo for n, d in niveles_y_dias if n in ("modelo", "capacidad"))


def comp_referencia(dias_grupos, fallos_grupos, dias_ref, fallos_ref):
    """La referencia se calcula con las mismas filas que los grupos: las sumas coinciden."""
    return (math.isclose(float(sum(dias_grupos)), float(dias_ref), rel_tol=1e-12, abs_tol=1e-6)
            and int(sum(fallos_grupos)) == int(fallos_ref))


def comp_partes_total(partes, totales):
    """Cada lista de partes suma su total."""
    return all(math.isclose(float(sum(p)), float(t), rel_tol=1e-9, abs_tol=1e-6) for p, t in zip(partes, totales))


def comp_sin_futuro(ultimos_meses, inicios):
    """Ninguna tasa de un trimestre usa un mes igual o posterior a su primer día."""
    return all(u is None or pd.Timestamp(u) < pd.Timestamp(i) for u, i in zip(ultimos_meses, inicios))


def comp_referencia_desplazada(pares, reales, anterior):
    """La referencia de cada par es el real del trimestre anterior de la misma capacidad."""
    return all(p["referencia"] == reales.get((anterior[p["trimestre"]], p["capacidad_tb"]), 0) for p in pares)


def comp_periodos(filas, clave, parciales, campo="parcial"):
    """Cada fila de un periodo incompleto lleva su marca, y las de un periodo completo no."""
    return all(bool(f[campo]) == (f[clave] in parciales) for f in filas)


def comp_cobertura(parte):
    """La parte cubierta está calculada y entre 0 y 1."""
    return parte is not None and 0 < parte <= 1 + 1e-12


def comp_sin_vetada(textos):
    """Ningún texto lleva la palabra vetada para el conjunto de discos, en mayúsculas o minúsculas."""
    return not any(VETADA in t.lower() for t in textos)


# =================================================================================================================
# 6. Entradas: estado de la fase anterior, huellas y lectura
# =================================================================================================================
def comprobar_previos(raiz):
    """Para con PARADO si falta un JSON del que parte el encargo o su estado es PARADO o ERROR."""
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
    conocidas = {Path(s["ruta"]).stem: s["sha256"] for s in tj["salidas"]}
    conocidas.update({Path(s["ruta"]).stem: s["sha256"] for s in tj["entradas"]})
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
    doc = raiz / DOC16
    if not doc.exists():
        raise Parada("ERROR", f"falta {DOC16}")
    entradas.append({"ruta": DOC16, "sha256": sha256(doc), "filas": None, "columnas": None,
                     "coincide_con_transformacion": None})
    return entradas


def leer_ingresos(texto):
    """Ingresos totales de cada año, en dólares, de la tabla «Ingresos por producto» del doc. 16 (miles de dólares)."""
    lineas = texto.splitlines()
    i = next(k for k, x in enumerate(lineas) if x.startswith("[Ingresos por producto"))
    anos = [int(x) for x in re.findall(r"\b(20\d\d)\b", lineas[i + 1])]
    total = next(x for x in lineas[i + 2:] if x.startswith("Total revenue"))
    valores = [int(v.strip().replace(",", "")) for v in total.split("|")[1:]]
    return {a: v * 1000 for a, v in zip(anos, valores)}


def leer(raiz):
    """Lee solo las columnas que usan los dos bloques; fechas en milisegundos; discos de datos marcados."""
    p = raiz / "data" / "processed"
    d = {}
    d["dm"] = pd.read_parquet(p / "dim_modelo.parquet",
                              columns=["model", "capacidad_tb", "tipo_disco", "precio_usd", "origen_precio",
                                       "fecha_compra"])
    d["dpg"] = pd.read_parquet(p / "dim_precio_gb.parquet", columns=["capacidad_tb", "ano", "coste_gb"])
    d["mt"] = pd.read_parquet(p / "modelo_trimestre.parquet",
                              columns=["model", "ano", "trimestre", "capacidad_tb", "precio_usd", "origen_precio",
                                       "dias_disco", "fallos", "fallos_en_garantia", "coste_fallos_usd",
                                       "coste_fallos_garantia_usd", "dias_disco_ano", "pasa_minimo_ano"])
    d["it"] = pd.read_parquet(p / "inicio_trimestre.parquet",
                              columns=["ano", "trimestre", "model", "edad_anos_cumplidos", "capacidad_tb", "discos",
                                       "dias_trimestre"])
    d["dpt"] = pd.read_parquet(p / "dias_por_tramo.parquet",
                               columns=["model", "mes", "edad_anos_cumplidos", "dias_disco", "fallos"])
    d["fd"] = pd.read_parquet(p / "fallos_detalle.parquet",
                              columns=["serial_number", "dia_fallo", "model", "capacidad_tb", "tipo_disco"])
    d["vida"] = pd.read_parquet(p / "vida_discos.parquet",
                                columns=["serial_number", "model", "primera_aparicion", "edad_entrada_anos", "evento",
                                         "edad_fin_anos"])
    d["rec"] = pd.read_parquet(p / "recuento_diario_corregido.parquet", columns=["fecha", "model", "discos", "fallos"])
    d["cal"] = pd.read_parquet(p / "calendario.parquet", columns=["fecha", "ano", "trimestre"])
    # Fotos y ventanas: solo la primera fecha de los discos que fallan, para la segunda vía de la primera aparición
    series = pa.array(sorted(set(d["fd"]["serial_number"])))
    primeras = []
    for t in ["fotos_mensuales_corregido", "ventanas_fallo_corregido"]:
        tb = pq.read_table(p / f"{t}.parquet", columns=["fecha", "serial_number"])
        tb = tb.filter(pc.is_in(tb["serial_number"], value_set=series))
        primeras.append(tb.to_pandas())
    d["fv"] = pd.concat(primeras, ignore_index=True)
    # Fechas, todas en milisegundos (dias_por_tramo llega en microsegundos)
    for t, cols in {"dpt": ["mes"], "fd": ["dia_fallo"], "vida": ["primera_aparicion"], "rec": ["fecha"],
                    "cal": ["fecha"], "fv": ["fecha"]}.items():
        for c in cols:
            d[t][c] = a_ms(d[t][c])
    # Discos de datos: la población de todo el encargo (reglas §3 y §7)
    datos = set(d["dm"].loc[d["dm"]["tipo_disco"] == "datos", "model"])
    for t in ["mt", "it", "dpt", "vida"]:
        if not set(d[t]["model"]) <= datos:
            raise Parada("ERROR", f"{t} trae un modelo que no es de datos")
    d["datos"] = datos
    d["dmd"] = d["dm"].loc[d["dm"]["tipo_disco"] == "datos"].copy()
    # El año de compra de cada modelo, del que sale el grupo del puesto de B4 (reglas §6 y §7; encargo 19)
    fc = d["dmd"].loc[d["dmd"]["fecha_compra"].notna()]
    d["ano_compra"] = {m: int(f.year) for m, f in zip(fc["model"], pd.to_datetime(fc["fecha_compra"]))}
    cap = d["dmd"].set_index("model")["capacidad_tb"]
    d["rec_d"] = d["rec"].loc[d["rec"]["model"].isin(datos)].copy()
    d["rec_d"]["capacidad_tb"] = d["rec_d"]["model"].map(cap)
    d["fd_d"] = d["fd"].loc[d["fd"]["tipo_disco"] == "datos"].copy()
    d["dpt"]["capacidad_tb"] = d["dpt"]["model"].map(cap)
    return d


def calendario(cal):
    """Días de cada año y de cada trimestre en los datos, años y trimestres parciales, y los trimestres en orden."""
    dias_ano = cal.groupby("ano")["fecha"].size()
    parciales = {int(a) for a, n in dias_ano.items() if n < (366 if calendar.isleap(int(a)) else DIAS_ANO)}
    q = cal.groupby(["ano", "trimestre"])["fecha"].size()
    trimestres = []
    for (a, t), n in q.sort_index().items():
        completos = sum(calendar.monthrange(int(a), m)[1] for m in range(3 * int(t) - 2, 3 * int(t) + 1))
        trimestres.append({"trimestre": etiqueta(a, t), "ano": int(a), "t": int(t), "inicio": inicio_trimestre(a, t),
                           "dias": int(n), "parcial": int(n) < completos})
    return {"dias_ano": {int(a): int(n) for a, n in dias_ano.items()}, "parciales": parciales,
            "trimestres": trimestres, "dias_total": int(len(cal)),
            "periodo": f"del {iso(cal['fecha'].min())} al {FECHA_DATOS.isoformat()}"}


# =================================================================================================================
# 7. Bloque 4 · Cuánto cuesta cada modelo
# =================================================================================================================
def celdas_desde_mt(mt):
    """Celdas de modelo y año desde modelo_trimestre: días, fallos, coste de los fallos, terabytes-año y mínimo."""
    g = (mt.groupby(["model", "ano"])
         .agg(capacidad_tb=("capacidad_tb", "first"), precio_usd=("precio_usd", "first"),
              origen_precio=("origen_precio", "first"), dias_disco=("dias_disco", "sum"), fallos=("fallos", "sum"),
              coste_f=("coste_fallos_usd", "sum"), coste_fg=("coste_fallos_garantia_usd", "sum"),
              pasa=("pasa_minimo_ano", "first"), dias_ano=("dias_disco_ano", "first"))
         .reset_index().sort_values(["model", "ano"], kind="mergesort").reset_index(drop=True))
    g["tb_ano"] = g["dias_disco"] * g["capacidad_tb"] / DIAS_ANO
    return g


def coste_nuevo(dpg):
    """Lo que cuesta un fallo de cada capacidad y año: disco nuevo al coste por GB del año, más el cambio (reglas §6)."""
    c = dpg.assign(coste=dpg["capacidad_tb"] * GB_POR_TB * dpg["coste_gb"] + COSTE_CAMBIO)
    return {(float(x["capacidad_tb"]), int(x["ano"])): float(x["coste"]) for _, x in c.iterrows()}


def celdas_desde_recuento(rec_d, dmd, dpg):
    """Las mismas celdas desde el recuento, con el coste de los fallos por la fórmula de las reglas §6 (segunda vía)."""
    c = rec_d.assign(ano=rec_d["fecha"].dt.year).groupby(["model", "ano"]).agg(
        dias_disco=("discos", "sum"), fallos=("fallos", "sum")).reset_index()
    c = c.merge(dmd[["model", "capacidad_tb", "precio_usd", "origen_precio"]], on="model", how="left",
                validate="many_to_one")
    nuevo = coste_nuevo(dpg)
    c["coste_f"] = [f * nuevo.get((float(k), int(a)), float("nan")) if f > 0 else 0.0
                    for f, k, a in zip(c["fallos"], c["capacidad_tb"], c["ano"])]
    c["coste_fg"] = float("nan")
    c["pasa"] = c["dias_disco"] >= MINIMO_DIAS_ANO
    c["dias_ano"] = c["dias_disco"]
    c["tb_ano"] = c["dias_disco"] * c["capacidad_tb"] / DIAS_ANO
    return c.sort_values(["model", "ano"], kind="mergesort").reset_index(drop=True)


def spearman(a, b):
    """Correlación de Spearman (Pearson de los rangos medios); None con menos de dos pares o con una lista constante."""
    a, b = pd.Series(a, dtype="float64"), pd.Series(b, dtype="float64")
    if len(a) < 2 or a.nunique() < 2 or b.nunique() < 2:
        return None
    return float(a.rank().corr(b.rank()))


def coste_igual_edad(amort, tasa_ie, por_fallo, dias, tb):
    """Coste por TB y año a igual edad (encargo 17, B4.2): amortización + tasa a igual edad / 100 × coste medio de un
    fallo del modelo × días de disco / 365 / terabytes-año. None si no hay tasa a igual edad."""
    if tasa_ie is None:
        return None
    return amort + tasa_ie / 100 * por_fallo * dias / DIAS_ANO / tb


def salto_de_puesto(a, b):
    """Mayor diferencia de puesto («min») de una misma entidad entre el orden por `a` y el orden por `b`."""
    pa_, pb_ = pd.Series(a, dtype="float64").rank(method="min"), pd.Series(b, dtype="float64").rank(method="min")
    return int((pa_ - pb_).abs().max()) if len(pa_) else 0


def sensibilidad_precio(filas, factores=FACTORES_PRECIO, n=N_PRIMEROS):
    """Si los `n` primeros siguen siéndolo con el precio inferido por cada factor (encargo 17, B4.3).

    Solo cambia la amortización de los modelos con origen_precio «inferido»; la parte de los fallos no se toca (el disco
    nuevo de un fallo sale de dim_precio_gb, no del precio del modelo). `filas` son los modelos con puesto.
    """
    base = sorted(filas, key=lambda f: (f["coste_tb_ano"], f["model"]))
    primeros = {f["model"] for f in base[:n]}
    out = []
    for fac in factores:
        costes = {f["model"]: f["precio_usd"] * (fac if f["origen_precio"] == "inferido" else 1.0) / f["capacidad_tb"]
                  / VIDA_CONTABLE + f["fallos_tb_ano"] for f in filas}
        orden = sorted(costes, key=lambda m: (costes[m], m))
        out.append({"factor": fac, "de": len(primeros), "siguen": len(primeros & set(orden[:n])),
                    "primero": orden[0] if orden else None, "primeros": orden[:n],
                    "salen": sorted(primeros - set(orden[:n])), "entran": sorted(set(orden[:n]) - primeros)})
    return out


def leer_igual_edad(raiz):
    """La tasa a igual edad de cada modelo de B2 en el JSON del 09: {modelo: (días, fallos, tasa a igual edad)}.

    Para con PARADO si el JSON no la trae (es anterior al encargo 17); su estado ya lo mira comprobar_previos.
    """
    j = json.loads((raiz / JSON_09).read_text(encoding="utf-8"))
    b2 = next((p for p in j.get("preguntas", []) if p.get("id") == "B2"), None)
    ranking = (b2 or {}).get("tablas", {}).get("ranking", [])
    if not ranking or any("tasa_igual_edad" not in f for f in ranking):
        raise Parada("PARADO", f"{JSON_09} no trae la tasa a igual edad de cada modelo (encargo 17): hay que ejecutar "
                               "antes el 09")
    # Encargo 19: la tasa a igual edad es la de cada edad y trimestre, con φ; un JSON del 09 sin φ es de antes
    if not isinstance((b2.get("tablas", {}).get("a_igual_edad") or {}).get("phi"), dict):
        raise Parada("PARADO", f"{JSON_09} no trae φ en la comparación a igual edad: es anterior al encargo 19 y hay "
                               "que ejecutar antes el 09")
    return {f["model"]: (f["dias_disco"], f["fallos"], f["tasa_igual_edad"]) for f in ranking}


def poner_igual_edad(ranking, ie):
    """Añade a cada modelo su tasa y su coste a igual edad; para con ERROR si el 09 no tiene sus mismos días y fallos."""
    malos = [f["model"] for f in ranking if f["model"] not in ie
             or (int(ie[f["model"]][0]), int(ie[f["model"]][1])) != (f["dias_disco"], f["fallos"])]
    if malos:
        raise Parada("ERROR", f"la tasa a igual edad de {JSON_09} no es de los mismos días y fallos que el ranking de "
                              f"coste: {', '.join(malos[:5])}")
    for f in ranking:
        tie = ie[f["model"]][2]
        f["tasa_igual_edad"] = tie
        f["coste_tb_ano_igual_edad"] = coste_igual_edad(f["amortizacion_tb_ano"], tie, f["coste_por_fallo"],
                                                        f["dias_disco"], f["tb_ano"])


def resumen_igual_edad(ranking):
    """Spearman entre el coste observado y el de igual edad, y el mayor salto de puesto, con todos los modelos."""
    xs = [f for f in ranking if f["coste_tb_ano_igual_edad"] is not None]
    a, b = [f["coste_tb_ano"] for f in xs], [f["coste_tb_ano_igual_edad"] for f in xs]
    dif = (pd.Series(a, dtype="float64").rank(method="min") - pd.Series(b, dtype="float64").rank(method="min")).abs()
    mayor = salto_de_puesto(a, b)
    return {"modelos": len(xs), "spearman": spearman(a, b), "mayor_salto": mayor,
            "modelos_mayor_salto": sorted(xs[i]["model"] for i in dif.index if dif[i] == mayor) if len(dif) else []}


def b4_ranking(celdas, dias_total, nuevo, minimo=MINIMO_FALLOS_MODELO, ano_compra=None):
    """Coste por TB y año de cada modelo con sus celdas que pasan el mínimo, de menor a mayor, y su referencia.

    Amortización = precio / capacidad / 6; fallos = coste de los fallos / terabytes-año; el intervalo del coste pone en
    la parte de los fallos el intervalo de la tasa (encargo, B4.1 y criterio 1). Un modelo con menos de `minimo` fallos
    sale sin puesto, al final, y el resumen se calcula con los que tienen puesto (CP-012; encargo 17). El puesto se da
    dentro de cada capacidad y año de compra (`ano_compra`, {modelo: año}); el de todos juntos va al lado, en
    `puesto_global`, con su resumen (reglas §7; encargo 19).
    """
    ano_compra = ano_compra or {}
    pasan = celdas.loc[celdas["pasa"] & celdas["precio_usd"].notna()]
    filas = []
    for m, g in pasan.groupby("model"):
        cap, precio = float(g["capacidad_tb"].iloc[0]), float(g["precio_usd"].iloc[0])
        dias, fallos, tb = int(g["dias_disco"].sum()), int(g["fallos"].sum()), float(g["tb_ano"].sum())
        coste_f, coste_fg = float(g["coste_f"].sum()), float(g["coste_fg"].sum(min_count=1))
        t, lo, hi = intervalo_poisson(fallos, dias)
        amort = precio / cap / VIDA_CONTABLE
        fallos_tb = coste_f / tb
        # Coste de un fallo del modelo: el medio de sus fallos; sin fallos, el de sus años ponderado por días
        if fallos > 0:
            por_fallo = coste_f / fallos
        else:
            por_fallo = sum(dd * nuevo[(cap, int(a))] for dd, a in zip(g["dias_disco"], g["ano"])) / dias
        filas.append({"model": m, "capacidad_tb": cap, "ano_compra": ano_compra.get(m), "dias_disco": dias,
                      "fallos": fallos, "tasa": t, "desde": lo,
                      "hasta": hi, "precio_usd": precio, "origen_precio": g["origen_precio"].iloc[0],
                      "tb_ano": tb, "coste_fallos_usd": coste_f, "amortizacion_tb_ano": amort, "fallos_tb_ano": fallos_tb,
                      "coste_tb_ano": amort + fallos_tb,
                      "coste_tb_ano_garantia": (amort + coste_fg / tb) if not math.isnan(coste_fg) else None,
                      "coste_desde": amort + lo / 100 * por_fallo * dias / DIAS_ANO / tb,
                      "coste_hasta": amort + hi / 100 * por_fallo * dias / DIAS_ANO / tb,
                      "parte_fallos_pct": 100 * fallos_tb / (amort + fallos_tb), "coste_por_fallo": por_fallo,
                      "discos_medios": dias / dias_total, "anos_que_pasan": sorted(int(a) for a in g["ano"])})
    # Puesto solo con `minimo` fallos o más (CP-012); los demás, sin puesto y al final, también por coste
    con = sorted((f for f in filas if f["fallos"] >= minimo), key=lambda f: (f["coste_tb_ano"], f["model"]))
    sin = sorted((f for f in filas if f["fallos"] < minimo), key=lambda f: (f["coste_tb_ano"], f["model"]))
    puestos = pd.Series([f["coste_tb_ano"] for f in con], dtype="float64").rank(method="min").astype(int).tolist()
    for f, p in zip(con, puestos):
        f["puesto_global"] = p
    for f in sin:
        f["puesto_global"] = None
        f["puesto"] = None
    # El puesto dentro de cada capacidad y año de compra, donde la tasa de fallo decide (reglas §7; encargo 19)
    grupos = {}
    for f in con:
        grupos.setdefault((f["capacidad_tb"], f["ano_compra"]), []).append(f)
    grupos_compra = []
    for (cap, ano), xs in sorted(grupos.items(), key=lambda kv: (kv[0][0], -1 if kv[0][1] is None else kv[0][1])):
        pg = pd.Series([x["coste_tb_ano"] for x in xs], dtype="float64").rank(method="min").astype(int).tolist()
        for x, p in zip(xs, pg):
            x["puesto"] = p
        grupos_compra.append({"capacidad_tb": cap, "ano_compra": ano, "modelos": [
            {"model": x["model"], "coste_tb_ano": x["coste_tb_ano"], "tasa": x["tasa"], "puesto": x["puesto"]}
            for x in sorted(xs, key=lambda x: (x["puesto"], x["model"]))]})
    filas = con + sin
    tb_ref = float(pasan["tb_ano"].sum())
    amort_ref = float((pasan["tb_ano"] * pasan["precio_usd"] / pasan["capacidad_tb"] / VIDA_CONTABLE).sum())
    referencia = {"dias_disco": int(pasan["dias_disco"].sum()), "fallos": int(pasan["fallos"].sum()), "tb_ano": tb_ref,
                  "coste_tb_ano": (amort_ref + float(pasan["coste_f"].sum())) / tb_ref, "celdas": int(len(pasan))}
    # El resumen del ranking de todos juntos, que se queda al lado como contexto
    primeros = [f for f in con if f["puesto_global"] <= N_PRIMEROS]
    resumen = {"mediana_parte_fallos_pct": float(np.median([f["parte_fallos_pct"] for f in con])) if con else None,
               "spearman_coste_tasa": spearman([f["coste_tb_ano"] for f in con], [f["tasa"] for f in con]),
               "primeros_diez_inferidos": sum(1 for f in primeros if f["origen_precio"] == "inferido"),
               "primeros_diez": len(primeros), "con_puesto": len(con), "sin_puesto": len(sin),
               "minimo_fallos": minimo,
               "grupos_compra": {"grupos_con_puesto": len(grupos_compra),
                                 "grupos_con_dos_o_mas": sum(1 for g in grupos_compra if len(g["modelos"]) >= 2),
                                 "modelos_sin_ano_compra": sorted(f["model"] for f in con if f["ano_compra"] is None),
                                 "grupos": grupos_compra}}
    return filas, referencia, resumen


def b4_fuera(celdas):
    """Lo que no entra en el ranking: celdas bajo el mínimo y modelos sin precio, con su recuento."""
    fuera = celdas.loc[~celdas["pasa"]]
    sp = celdas.loc[celdas["precio_usd"].isna()]
    lista = (sp.groupby("model").agg(dias_disco=("dias_disco", "sum"), fallos=("fallos", "sum")).reset_index()
             .sort_values("model", kind="mergesort"))
    return ({"celdas": int(len(fuera)), "dias_disco": int(fuera["dias_disco"].sum()),
             "fallos": int(fuera["fallos"].sum())},
            {"modelos": int(sp["model"].nunique()), "dias_disco": int(sp["dias_disco"].sum()),
             "fallos": int(sp["fallos"].sum()), "celdas_que_pasan": int(sp["pasa"].sum()),
             "lista": [{"model": x["model"], "dias_disco": int(x["dias_disco"]), "fallos": int(x["fallos"])}
                       for _, x in lista.iterrows()]})


def curva_modelo(tv):
    """Curva cortada, última edad con base y vida real desde la tabla de vida de un modelo."""
    tasas = [f["tasa"] for f in tv]
    eventos = [f["eventos"] for f in tv]
    s = supervivencia(tasas)
    cortada, motivo_corte = cortar_curva(s, eventos, MINIMO_FALLOS_EDAD)
    validos = [k for k, v in enumerate(cortada) if v is not None]
    ultima = validos[-1] if validos and validos[-1] >= 1 else None
    edad, motivo = vida_real(cortada, tasas)
    return {"s": cortada, "eventos_por_ano": eventos, "motivo_corte": motivo_corte, "ultima_edad_con_base": ultima,
            "s_ultima_edad_con_base": cortada[ultima] if ultima is not None else None,
            "vida_real_anos": edad, "motivo": motivo}


def b4_vida(vida, modelos):
    """Vida real de cada modelo de datos por su tabla de vida (encargo, criterio 2)."""
    out = []
    por_modelo = {m: g for m, g in vida.groupby("model")}
    for m in sorted(modelos):
        g = por_modelo.get(m, vida.iloc[0:0])
        tv = tabla_de_vida(g["edad_entrada_anos"], g["edad_fin_anos"], g["evento"] == "fallo")
        c = curva_modelo(tv)
        out.append({"model": m, "discos": int(len(g)), **c,
                    "tabla_de_vida": [{"edad": f["edad"], "exposicion_anos": r(f["exposicion_anos"], 3),
                                       "fallos": f["eventos"]} for f in tv]})
    con_base = [x for x in out if x["ultima_edad_con_base"] is not None]
    mas_baja = min(con_base, key=lambda x: (x["s_ultima_edad_con_base"], x["model"])) if con_base else None
    resumen = {"modelos_datos": len(out), "con_algun_ano_con_base": len(con_base),
               "bajan_de_05": sum(1 for x in out if x["vida_real_anos"] is not None),
               "s_mas_baja": ({"model": mas_baja["model"], "edad": mas_baja["ultima_edad_con_base"],
                               "s": mas_baja["s_ultima_edad_con_base"]} if mas_baja else None)}
    return out, resumen


def b4_vida_bucle(vida, modelos):
    """La vida de cada modelo con la tabla de vida hecha disco a disco (segunda vía, otro cálculo)."""
    tb = tabla_de_vida_bucle(vida["model"].tolist(), vida["edad_entrada_anos"].tolist(), vida["edad_fin_anos"].tolist(),
                             (vida["evento"] == "fallo").tolist())
    out = {}
    for m in sorted(modelos):
        expo, evs = tb.get(m, ([0.0] * len(EDADES), [0] * len(EDADES)))
        tv = [{"edad": j, "exposicion_anos": expo[j], "eventos": evs[j],
               "tasa": evs[j] / expo[j] if expo[j] > 0 else None} for j in EDADES]
        out[m] = curva_modelo(tv) | {"tabla": tv}
    return out


def b4_mejor(celdas, parciales):
    """Mejor modelo de cada capacidad y año, coste real frente al del mejor, y la diferencia en precio y fallos.

    Mejor = el de menor coste por TB y año ese año entre los que pasan el mínimo (empates, por nombre). Coste real de
    todos los modelos con precio de esa capacidad ese año; con el mejor = sus terabytes-año × el coste del mejor
    (encargo, criterio 3).
    """
    c = celdas.loc[celdas["precio_usd"].notna()].copy()
    c["amort"] = c["precio_usd"] / c["capacidad_tb"] / VIDA_CONTABLE
    c["fallos_tb"] = c["coste_f"] / c["tb_ano"]
    c["coste"] = c["amort"] + c["fallos_tb"]
    con, sin = [], []
    for (a, k), g in c.groupby(["ano", "capacidad_tb"], sort=True):
        tb = float(g["tb_ano"].sum())
        real = float((g["tb_ano"] * g["amort"]).sum() + g["coste_f"].sum())
        cand = g.loc[g["pasa"]].sort_values(["coste", "model"], kind="mergesort")
        base = {"ano": int(a), "capacidad_tb": float(k), "parcial": int(a) in parciales,
                "modelos_con_precio": int(len(g)), "modelos_que_pasan": int(len(cand)), "tb_ano": tb,
                "coste_real": real}
        if cand.empty:
            sin.append(base)
            continue
        b = cand.iloc[0]
        parte_precio = float((g["tb_ano"] * (g["amort"] - b["amort"])).sum())
        parte_fallos = float(g["coste_f"].sum() - tb * b["fallos_tb"])
        con.append(base | {"mejor": b["model"], "mejor_pasa": bool(b["pasa"]), "coste_tb_ano_mejor": float(b["coste"]),
                           "coste_con_mejor": tb * float(b["coste"]), "diferencia": real - tb * float(b["coste"]),
                           "parte_precio": parte_precio, "parte_fallos": parte_fallos})
    por_ano = []
    for a in sorted({x["ano"] for x in con} | {x["ano"] for x in sin}):
        xs = [x for x in con if x["ano"] == a]
        por_ano.append({"ano": a, "parcial": a in parciales, "celdas": len(xs),
                        "coste_real": sum(x["coste_real"] for x in xs),
                        "coste_con_mejor": sum(x["coste_con_mejor"] for x in xs),
                        "diferencia": sum(x["diferencia"] for x in xs),
                        "parte_precio": sum(x["parte_precio"] for x in xs),
                        "parte_fallos": sum(x["parte_fallos"] for x in xs),
                        "celdas_sin_mejor": sum(1 for x in sin if x["ano"] == a),
                        "coste_real_sin_mejor": sum(x["coste_real"] for x in sin if x["ano"] == a)})
    return con, sin, por_ano


def b4_ingreso(celdas_todas, celdas, ingresos, dias_ano):
    """Ingreso por TB de 2023 y 2024 y el coste por TB y año de todos los discos con precio (encargo, criterio 4).

    Capacidad media = suma de días × capacidad del año / días del año en los datos, con todos los discos de datos.
    """
    out = []
    c = celdas.loc[celdas["precio_usd"].notna()]
    for a in ANOS_INGRESO:
        cap_media = float((celdas_todas.loc[celdas_todas["ano"] == a, "tb_ano"]).sum()) * DIAS_ANO / dias_ano[a]
        g = c.loc[c["ano"] == a]
        tb = float(g["tb_ano"].sum())
        amort = float((g["tb_ano"] * g["precio_usd"] / g["capacidad_tb"] / VIDA_CONTABLE).sum())
        out.append({"ano": a, "ingresos_usd": ingresos[a], "dias_del_ano": dias_ano[a], "capacidad_media_tb": cap_media,
                    "ingreso_por_tb": ingresos[a] / cap_media, "coste_tb_ano_todos": (amort + float(g["coste_f"].sum())) / tb,
                    "coste_tb_ano_todos_garantia": ((amort + float(g["coste_fg"].sum(min_count=1))) / tb
                                                    if g["coste_fg"].notna().any() else None)})
    return out


# =================================================================================================================
# 8. Bloque 9 · Cuántos discos fallarán el próximo trimestre
# =================================================================================================================
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


def prever_trimestre_bucle(ano, trimestre, it, dpt, meses_historia=None, minimo=MINIMO_DIAS_ANO, niveles=NIVELES):
    """La misma previsión fila a fila, con diccionarios por clave (segunda vía, otro cálculo): {capacidad: previsto}."""
    inicio = inicio_trimestre(ano, trimestre)
    desde = inicio - pd.DateOffset(months=meses_historia) if meses_historia is not None else None
    acum = {"modelo": {}, "capacidad": {}, "edad": {}}
    for x in dpt.itertuples(index=False):
        if not (x.mes < inicio) or (desde is not None and x.mes < desde):
            continue
        # Una fila sin días (solo trae fallos, reglas de transformación §6) cuenta 0 días y sus fallos
        dias = 0.0 if math.isnan(x.dias_disco) else x.dias_disco
        for nivel, k in (("modelo", (x.model, x.edad_anos_cumplidos)), ("capacidad", (x.capacidad_tb,
                                                                                    x.edad_anos_cumplidos)),
                         ("edad", (x.edad_anos_cumplidos,))):
            d, f = acum[nivel].get(k, (0.0, 0))
            acum[nivel][k] = (d + dias, f + x.fallos)
    out = {}
    for x in it.itertuples(index=False):
        if x.ano != ano or x.trimestre != trimestre or x.discos <= 0:
            continue
        claves = {"modelo": (x.model, x.edad_anos_cumplidos), "capacidad": (x.capacidad_tb, x.edad_anos_cumplidos),
                  "edad": (x.edad_anos_cumplidos,)}
        tasa = 0.0
        for nivel in niveles:
            d, f = acum[nivel].get(claves[nivel], (0.0, 0))
            if d > 0 and d >= (minimo if nivel != "edad" else 0):
                tasa = f / d
                break
        out[float(x.capacidad_tb)] = out.get(float(x.capacidad_tb), 0.0) + x.discos * x.dias_trimestre * tasa
    return out


def error_ponderado(previstos, reales):
    """Error absoluto ponderado = suma de |previsto − real| / suma de reales; sesgo, lo mismo con signo (CP-011)."""
    s = float(sum(reales))
    if s == 0:
        return None, None
    return (float(sum(abs(p - x) for p, x in zip(previstos, reales))) / s,
            float(sum(p - x for p, x in zip(previstos, reales))) / s)


def reales_por_trimestre(fd_d):
    """Fallos reales por trimestre y capacidad desde fallos_detalle: {(«2024T1», capacidad): fallos}."""
    q = etiqueta_serie(fd_d["dia_fallo"])
    return {(a, float(k)): int(n) for (a, k), n in fd_d.groupby([q, fd_d["capacidad_tb"]]).size().items()}


def etiqueta_serie(fechas):
    """«2024T1» para cada fecha de una serie."""
    return (fechas.dt.year.astype(str) + "T" + fechas.dt.quarter.astype(str)).rename("trimestre")


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


def correr_prevision(it, dpt, prev_q, reales, anterior, meses=None, minimo=MINIMO_DIAS_ANO, niveles=NIVELES):
    """La previsión de todos los trimestres con una variante: filas por trimestre, pares y error."""
    previsiones, filas, ultimos = {}, {}, {}
    for q in prev_q:
        p = prever_trimestre(q["ano"], q["t"], it, dpt, meses, minimo, niveles)
        previsiones[q["trimestre"]] = p["previsto_por_capacidad"]
        filas[q["trimestre"]] = p["filas"]
        ultimos[q["trimestre"]] = p["ultimo_mes_usado"]
    pares = montar_pares(previsiones, reales, prev_q, anterior)
    return {"previsiones": previsiones, "filas": filas, "ultimos": ultimos, "pares": pares,
            "total": resumen_error(pares)}


# =================================================================================================================
# 9. Segundas vías: cada una parte de otra tabla o de otro cálculo (skill §5)
# =================================================================================================================
def comparar(nombre, via1, via2, a, b, tolerancia=None, recuento=False):
    """Compara dos series indexadas por la misma clave; exacta o con tolerancia. Devuelve la ficha de la segunda vía.

    Con `recuento`, una clave que falta en una vía es un cero; sin él, una clave que falta es una diferencia.
    """
    c = pd.concat([pd.Series(a, dtype="float64").rename("v1"), pd.Series(b, dtype="float64").rename("v2")], axis=1)
    faltan = 0 if recuento else int(c.isna().any(axis=1).sum())
    c = c.fillna(0)
    dif = (c["v1"] - c["v2"]).abs()
    distintas = int((dif > (tolerancia if tolerancia is not None else 0)).sum())
    return {"nombre": nombre, "via_1": via1, "via_2": via2, "claves": int(len(c)), "claves_en_una_sola_via": faltan,
            "diferentes": distintas, "max_diferencia": r(dif.max() if len(dif) else 0.0, 12),
            "comparacion": "exacta" if tolerancia is None else f"diferencia menor que {tolerancia:g}",
            "coinciden": bool(distintas == 0 and faltan == 0 and len(c) > 0)}


# =================================================================================================================
# 10. Cálculo de los dos bloques
# =================================================================================================================
def calcular(d, ingresos):
    """Calcula los dos bloques con sus tablas, cifras, referencias y comprobaciones; no escribe nada."""
    cal_info = calendario(d["cal"])
    mt, dpg, dmd, rec_d, fd_d, vida, it, dpt = (d["mt"], d["dpg"], d["dmd"], d["rec_d"], d["fd_d"], d["vida"], d["it"],
                                                 d["dpt"])
    periodo_todo = cal_info["periodo"]
    nuevo = coste_nuevo(dpg)
    sv = []

    # ---------------------------------------------------------------------------------------------------------
    # B4 · celdas, ranking, vida real, mejor modelo e ingreso
    # ---------------------------------------------------------------------------------------------------------
    celdas = celdas_desde_mt(mt)
    celdas_rec = celdas_desde_recuento(rec_d, dmd, dpg)
    ranking, ref4, resumen = b4_ranking(celdas, cal_info["dias_total"], nuevo, ano_compra=d["ano_compra"])
    ranking_rec, ref4_rec, resumen_rec = b4_ranking(celdas_rec, cal_info["dias_total"], nuevo,
                                                    ano_compra=d["ano_compra"])
    # Encargo 17: coste a igual edad con la tasa del 09, y sensibilidad al precio inferido con los que tienen puesto
    poner_igual_edad(ranking, d["ie"])
    poner_igual_edad(ranking_rec, d["ie"])
    ie_res, ie_res_rec = resumen_igual_edad(ranking), resumen_igual_edad(ranking_rec)
    sens = sensibilidad_precio([f for f in ranking if f["puesto"] is not None])
    sens_rec = sensibilidad_precio([f for f in ranking_rec if f["puesto"] is not None])
    fuera, sin_precio = b4_fuera(celdas)
    fuera_rec, sin_precio_rec = b4_fuera(celdas_rec)
    vida_modelos, vida_res = b4_vida(vida, d["datos"])
    vida_bucle = b4_vida_bucle(vida, d["datos"])
    con, sin, por_ano = b4_mejor(celdas, cal_info["parciales"])
    con_rec, sin_rec, por_ano_rec = b4_mejor(celdas_rec, cal_info["parciales"])
    ingreso = b4_ingreso(celdas, celdas, ingresos, cal_info["dias_ano"])
    ingreso_rec = b4_ingreso(celdas_rec, celdas_rec, ingresos, cal_info["dias_ano"])
    vida_por_modelo = {x["model"]: x for x in vida_modelos}
    for f in ranking:
        f["vida_real_anos"] = vida_por_modelo[f["model"]]["vida_real_anos"]
        f["s_ultima_edad_con_base"] = vida_por_modelo[f["model"]]["s_ultima_edad_con_base"]
        f["ultima_edad_con_base"] = vida_por_modelo[f["model"]]["ultima_edad_con_base"]

    # Segundas vías de B4
    a, b = celdas_rec.set_index(["model", "ano"]), celdas.set_index(["model", "ano"])
    sv.append(comparar("días de disco por modelo y año", "recuento_diario_corregido", "modelo_trimestre",
                       a["dias_disco"], b["dias_disco"]))
    sv.append(comparar("fallos por modelo y año", "recuento_diario_corregido", "modelo_trimestre",
                       a["fallos"], b["fallos"]))
    sv.append(comparar("coste de los fallos por modelo y año, en dólares",
                       "fallos del recuento × (capacidad en GB × coste_gb de dim_precio_gb + 37)",
                       "modelo_trimestre (suma de coste_fallos_usd)", a["coste_f"], b["coste_f"], TOLERANCIA))
    sv.append(comparar("coste por TB y año de cada modelo del ranking, en dólares",
                       "recuento_diario_corregido + dim_precio_gb (fórmula de las reglas §6)", "modelo_trimestre",
                       pd.Series({f["model"]: f["coste_tb_ano"] for f in ranking_rec}),
                       pd.Series({f["model"]: f["coste_tb_ano"] for f in ranking}), TOLERANCIA))
    sv.append(comparar("coste por TB y año a igual edad de cada modelo, en dólares",
                       "recuento_diario_corregido + dim_precio_gb, con la tasa a igual edad del 09",
                       "modelo_trimestre, con la tasa a igual edad del 09",
                       pd.Series({f["model"]: f["coste_tb_ano_igual_edad"] for f in ranking_rec
                                  if f["coste_tb_ano_igual_edad"] is not None}, dtype="float64"),
                       pd.Series({f["model"]: f["coste_tb_ano_igual_edad"] for f in ranking
                                  if f["coste_tb_ano_igual_edad"] is not None}, dtype="float64"),
                       TOLERANCIA))
    ka = pd.Series({(x["ano"], x["capacidad_tb"], x["mejor"]): x["diferencia"] for x in con_rec})
    kb = pd.Series({(x["ano"], x["capacidad_tb"], x["mejor"]): x["diferencia"] for x in con})
    sv.append(comparar("diferencia con el mejor modelo por año y capacidad, en dólares",
                       "recuento_diario_corregido + dim_precio_gb", "modelo_trimestre", ka, kb, TOLERANCIA))
    sv.append(comparar("capacidad media del año, en TB", "recuento_diario_corregido × capacidad de dim_modelo",
                       "modelo_trimestre", pd.Series({x["ano"]: x["capacidad_media_tb"] for x in ingreso_rec}),
                       pd.Series({x["ano"]: x["capacidad_media_tb"] for x in ingreso}), TOLERANCIA))
    eva = pd.Series({(m, j): vida_bucle[m]["tabla"][j]["eventos"] for m in vida_bucle for j in EDADES})
    evb = pd.Series({(x["model"], f["edad"]): f["fallos"] for x in vida_modelos for f in x["tabla_de_vida"]})
    sv.append(comparar("primeros fallos por modelo y año de edad (tabla de vida)", "vida_discos, disco a disco",
                       "vida_discos, vectorizada por año de edad", eva, evb))
    sv.append(comparar("puesto dentro de capacidad y año de compra de cada modelo",
                       "recuento_diario_corregido + dim_precio_gb", "modelo_trimestre",
                       pd.Series({f["model"]: f["puesto"] for f in ranking_rec if f["puesto"] is not None}),
                       pd.Series({f["model"]: f["puesto"] for f in ranking if f["puesto"] is not None})))
    exa = pd.Series({(m, j): vida_bucle[m]["tabla"][j]["exposicion_anos"] for m in vida_bucle for j in EDADES})
    exb = pd.Series({(x["model"], f["edad"]): f["exposicion_anos"] for x in vida_modelos for f in x["tabla_de_vida"]})
    sv.append(comparar("años de exposición por modelo y año de edad (tabla de vida)", "vida_discos, disco a disco",
                       "vida_discos, vectorizada por año de edad", exa, exb, 1e-3))

    # Comprobaciones de B4
    partes_ok = comp_partes_total([[x["parte_precio"], x["parte_fallos"]] for x in con], [x["diferencia"] for x in con])
    total_dias, total_fallos = int(celdas["dias_disco"].sum()), int(celdas["fallos"].sum())
    b4_comp = {
        "unidad": comp_unidad(f["model"] for f in ranking) and comp_unidad(zip(celdas["model"], celdas["ano"])),
        "minimo": (comp_minimo_ranking(celdas["dias_ano"].tolist(), celdas["pasa"].tolist(), MINIMO_DIAS_ANO)
                   and bool((celdas["dias_disco"] == celdas["dias_ano"]).all())
                   and all(x["mejor_pasa"] for x in con)
                   and comp_puesto_minimo(ranking)),
        "empates": comp_empates([(f["capacidad_tb"], f["ano_compra"], f["coste_tb_ano"]) for f in ranking
                                 if f["puesto"] is not None], [f["puesto"] for f in ranking if f["puesto"] is not None])
        and comp_empates([f["coste_tb_ano"] for f in ranking if f["puesto_global"] is not None],
                         [f["puesto_global"] for f in ranking if f["puesto_global"] is not None]),
        "referencia": comp_referencia([f["dias_disco"] for f in ranking], [f["fallos"] for f in ranking],
                                      ref4["dias_disco"], ref4["fallos"]),
        "azar_en_grupos": None, "pesos": None, "hacia_adelante": None,
        "cobertura": (comp_cobertura(ref4["dias_disco"] / total_dias)
                      and ref4["dias_disco"] + fuera["dias_disco"] == total_dias
                      and ref4["fallos"] + fuera["fallos"] == total_fallos),
        "periodos": comp_periodos(por_ano, "ano", cal_info["parciales"]) and comp_periodos(con, "ano",
                                                                                           cal_info["parciales"]),
    }
    motivos_b4 = {"azar_en_grupos": ("B4 ordena los modelos por coste y no compara cada uno con el conjunto de discos; "
                                     "la tasa frente al conjunto, con su intervalo y lo que saldría por azar, está en B2"),
                  "pesos": ("el coste suma dos partes con su fórmula (reglas §6), sin pesos que se puedan mover"),
                  "hacia_adelante": ("B4 describe el coste del periodo; si un modelo barato lo sigue siendo después se "
                                     "mide en la reserva, que no se mira (reglas §5)")}

    # ---------------------------------------------------------------------------------------------------------
    # B9 · previsión trimestre a trimestre, referencia, niveles, sensibilidad y fallos que no se ven
    # ---------------------------------------------------------------------------------------------------------
    trims = cal_info["trimestres"]
    anterior = {q["trimestre"]: trims[i - 1]["trimestre"] for i, q in enumerate(trims) if i > 0}
    prev_q = [q for q in trims if (q["ano"], q["t"]) >= PRIMER_PREVISTO]
    reales = reales_por_trimestre(fd_d)
    principal = correr_prevision(it, dpt, prev_q, reales, anterior)
    pares = principal["pares"]
    tot = principal["total"]
    gana = tot["wape_cuenta"] is not None and tot["wape_cuenta"] < tot["wape_referencia"]
    por_trimestre = resumen_error(pares, "trimestre")
    por_capacidad = sorted(resumen_error(pares, "capacidad_tb"), key=lambda x: x["capacidad_tb"])
    niveles = []
    todas_filas = []
    for q in prev_q:
        f = principal["filas"][q["trimestre"]]
        todas_filas.append(f)
        n = f.groupby("nivel")["discos"].sum()
        niveles.append({"trimestre": q["trimestre"], **{k: int(n.get(k, 0)) for k in list(NIVELES) + ["sin tasa"]},
                        "discos": int(f["discos"].sum()),
                        "ultimo_mes_usado": iso(principal["ultimos"][q["trimestre"]])
                        if principal["ultimos"][q["trimestre"]] is not None else None})
    filas_all = pd.concat(todas_filas, ignore_index=True)
    sensibilidad = []
    for nombre, meses, minimo, nivs in VARIANTES:
        v = correr_prevision(it, dpt, prev_q, reales, anterior, meses, minimo, nivs)
        prev_b = {q["trimestre"]: prever_trimestre_bucle(q["ano"], q["t"], it, dpt, meses, minimo, nivs) for q in prev_q}
        pares_b = montar_pares(prev_b, reales, prev_q, anterior)
        sensibilidad.append({"variante": nombre, "meses_historia": meses, "minimo_dias": minimo, "niveles": list(nivs),
                             "wape": v["total"]["wape_cuenta"], "sesgo": v["total"]["sesgo_cuenta"],
                             "previsto": v["total"]["previsto"],
                             "gana": bool(v["total"]["wape_cuenta"] < v["total"]["wape_referencia"]),
                             "wape_bucle": resumen_error(pares_b)["wape_cuenta"]})

    # Fallos de discos que aparecen después del primer día de su trimestre (vida_discos, primera_aparicion)
    fq = fd_d.assign(trimestre=etiqueta_serie(fd_d["dia_fallo"]))
    fq = fq.loc[fq["trimestre"].isin([q["trimestre"] for q in prev_q])]
    inicio_de = {q["trimestre"]: q["inicio"] for q in prev_q}
    fq = fq.assign(inicio=fq["trimestre"].map(inicio_de))
    pa_vida = vida.drop_duplicates("serial_number").set_index("serial_number")["primera_aparicion"]
    fq = fq.assign(primera=fq["serial_number"].map(pa_vida))
    fq = fq.assign(despues=fq["primera"] > fq["inicio"])
    pa_fv = d["fv"].groupby("serial_number")["fecha"].min()
    fq = fq.assign(despues_fv=fq["serial_number"].map(pa_fv) > fq["inicio"])
    invisibles = {"fallos": int(fq["despues"].sum()), "de": int(len(fq)),
                  "pct": 100 * float(fq["despues"].sum()) / len(fq) if len(fq) else None,
                  "sin_vida": int(fq["primera"].isna().sum()),
                  "por_trimestre": [{"trimestre": q["trimestre"],
                                     "fallos": int(fq.loc[fq["trimestre"] == q["trimestre"], "despues"].sum())}
                                    for q in prev_q]}

    # Segundas vías de B9
    rec_q = rec_d.assign(trimestre=etiqueta_serie(rec_d["fecha"]))
    ra = rec_q.loc[rec_q["fallos"] > 0].groupby(["trimestre", "capacidad_tb"])["fallos"].sum()
    sv.append(comparar("fallos reales por trimestre y capacidad", "recuento_diario_corregido", "fallos_detalle",
                       ra, pd.Series(reales), recuento=True))
    inicios = pd.DatetimeIndex([q["inicio"] for q in trims]).astype("datetime64[ms]")
    r1 = rec_q.loc[rec_q["fecha"].isin(inicios)]
    da = r1.groupby(["trimestre", "capacidad_tb"])["discos"].sum()
    itq = it.assign(trimestre=[etiqueta(a_, t_) for a_, t_ in zip(it["ano"], it["trimestre"])])
    db = itq.groupby(["trimestre", "capacidad_tb"])["discos"].sum()
    sv.append(comparar("discos el primer día de cada trimestre, por capacidad", "recuento_diario_corregido",
                       "inicio_trimestre", da, db))
    prev_bucle = {q["trimestre"]: prever_trimestre_bucle(q["ano"], q["t"], it, dpt) for q in prev_q}
    pb = pd.Series({(q, k): v for q, x in prev_bucle.items() for k, v in x.items()})
    pm = pd.Series({(q, k): v for q, x in principal["previsiones"].items() for k, v in x.items()})
    sv.append(comparar("fallos previstos por trimestre y capacidad", "dias_por_tramo, fila a fila con diccionarios",
                       "dias_por_tramo, agregado y unido por clave", pb, pm, TOLERANCIA))
    sv.append(comparar("error absoluto ponderado de las variantes de sensibilidad", "fila a fila con diccionarios",
                       "agregado y unido por clave", pd.Series({s["variante"]: s["wape_bucle"] for s in sensibilidad}),
                       pd.Series({s["variante"]: s["wape"] for s in sensibilidad}), TOLERANCIA))
    sv.append(comparar("fallos de discos que aparecen después del primer día de su trimestre, por trimestre",
                       "fotos_mensuales_corregido + ventanas_fallo_corregido (primera fecha de cada disco)",
                       "vida_discos (primera_aparicion)",
                       fq.groupby("trimestre")["despues_fv"].sum(), fq.groupby("trimestre")["despues"].sum()))

    # Comprobaciones de B9
    desde_prev = prev_q[0]["inicio"]
    rec_periodo = int(rec_d.loc[rec_d["fecha"] >= desde_prev, "fallos"].sum())
    total_real = sum(p["real"] for p in pares)
    parte_con_tasa = float(filas_all.loc[filas_all["nivel"] != "sin tasa", "discos"].sum()) / float(
        filas_all["discos"].sum())
    sin_futuro = comp_sin_futuro([principal["ultimos"][q["trimestre"]] for q in prev_q], [q["inicio"] for q in prev_q])
    b9_comp = {
        "unidad": (comp_unidad((p["trimestre"], p["capacidad_tb"]) for p in pares)
                   and comp_unidad(zip(fd_d["serial_number"], fd_d["dia_fallo"]))),
        "minimo": comp_minimo_tasas(zip(filas_all["nivel"], filas_all["dias_base"]), MINIMO_DIAS_ANO),
        "empates": None,
        "referencia": comp_referencia_desplazada(pares, reales, anterior),
        "azar_en_grupos": None, "pesos": None,
        "hacia_adelante": sin_futuro,
        "cobertura": comp_cobertura(parte_con_tasa) and comp_cobertura(1 - invisibles["fallos"] / invisibles["de"]),
        "periodos": comp_periodos(prev_q, "trimestre", {q["trimestre"] for q in trims if q["dias"] < (
            sum(calendar.monthrange(q["ano"], m_)[1] for m_ in range(3 * q["t"] - 2, 3 * q["t"] + 1)))}),
    }
    motivos_b9 = {"empates": "B9 no ordena entidades en un ranking",
                  "azar_en_grupos": "B9 compara dos previsiones con el mismo error ponderado, no grupos frente al total",
                  "pesos": "no hay ninguna puntuación con pesos"}

    # ---------------------------------------------------------------------------------------------------------
    # Cifras con su segunda vía
    # ---------------------------------------------------------------------------------------------------------
    ok = {s["nombre"]: s["coinciden"] for s in sv}

    def sv_ok(*nombres):
        """Cierto si todas las segundas vías nombradas coinciden."""
        return all(ok.get(n, False) for n in nombres)

    def cifra(nombre, clave, valor, unidad, poblacion, periodo, filas, segunda, de, coinciden):
        """Una cifra del JSON con su población, sus filas, su periodo y su segunda vía."""
        return {"nombre": nombre, "clave": clave, "valor": valor, "unidad": unidad, "poblacion": poblacion,
                "periodo": periodo, "filas": filas, "segunda_via": segunda, "segunda_via_de": de,
                "coinciden": bool(coinciden)}

    def igual(x, y, tol=TOLERANCIA):
        """Cierto si dos cifras coinciden a menos de `tol`."""
        return x is not None and y is not None and abs(float(x) - float(y)) <= tol

    c4 = []
    pob4 = POBLACION + "; modelos con precio y celdas de modelo y año que pasan el mínimo"
    n_pasan, n_pasan_rec = int(celdas["pasa"].sum()), int(celdas_rec["pasa"].sum())
    c4.append(cifra("celdas de modelo y año que pasan el mínimo", "preguntas.B4.tablas.celdas_que_pasan", n_pasan,
                    "celdas", POBLACION, periodo_todo, int(len(mt)), n_pasan_rec,
                    "recuento_diario_corregido (días del año ≥ mínimo)", n_pasan == n_pasan_rec))
    c4.append(cifra("modelos en el ranking de coste", "preguntas.B4.tablas.ranking", len(ranking), "modelos", pob4,
                    periodo_todo, n_pasan, len(ranking_rec), "recuento_diario_corregido",
                    [f["model"] for f in ranking] == [f["model"] for f in ranking_rec]))
    for nombre, clave in [("días de disco fuera del ranking", "dias_disco"), ("fallos fuera del ranking", "fallos"),
                          ("celdas fuera del ranking", "celdas")]:
        c4.append(cifra(nombre, f"preguntas.B4.tablas.fuera_del_ranking.{clave}", fuera[clave], clave, POBLACION,
                        periodo_todo, int(len(celdas)), fuera_rec[clave], "recuento_diario_corregido",
                        fuera[clave] == fuera_rec[clave]))
    c4.append(cifra("días de disco de los modelos sin precio", "preguntas.B4.tablas.sin_precio.dias_disco",
                    sin_precio["dias_disco"], "días de disco", POBLACION + "; modelos sin precio", periodo_todo,
                    sin_precio["modelos"], sin_precio_rec["dias_disco"], "recuento_diario_corregido",
                    sin_precio["dias_disco"] == sin_precio_rec["dias_disco"]
                    and sin_precio["fallos"] == sin_precio_rec["fallos"]))
    rec_por_modelo = {f["model"]: f for f in ranking_rec}
    # Los tres primeros y los dos últimos con puesto (CP-012: los que no lo tienen van al final, aparte)
    con_puesto = [f for f in ranking if f["puesto"] is not None]
    for f in con_puesto[:3] + con_puesto[-2:]:
        g = rec_por_modelo.get(f["model"], {})
        c4.append(cifra(f"coste por TB y año, puesto {f['puesto_global']} de todos juntos: {f['model']}",
                        f"preguntas.B4.tablas.ranking[model={f['model']}].coste_tb_ano", r(f["coste_tb_ano"], 8),
                        "dólares por TB y año", pob4 + f"; {f['model']}", ", ".join(str(x) for x in f["anos_que_pasan"]),
                        len(f["anos_que_pasan"]), r(g.get("coste_tb_ano"), 8),
                        "recuento_diario_corregido + dim_precio_gb (fórmula de las reglas §6)",
                        igual(g.get("coste_tb_ano"), f["coste_tb_ano"])))
    for nombre, clave in [("mediana de la parte de los fallos en el coste, en %", "mediana_parte_fallos_pct"),
                          ("correlación de Spearman entre el coste y la tasa", "spearman_coste_tasa"),
                          ("modelos con precio inferido entre los diez primeros", "primeros_diez_inferidos")]:
        c4.append(cifra(nombre, f"preguntas.B4.tablas.resumen_ranking.{clave}", r(resumen[clave], 8), clave, pob4,
                        periodo_todo, len(con_puesto), r(resumen_rec[clave], 8),
                        "recuento_diario_corregido + dim_precio_gb", igual(resumen_rec[clave], resumen[clave])))
    # Encargo 19: el puesto dentro de cada capacidad y año de compra
    gc, gc_rec = resumen["grupos_compra"], resumen_rec["grupos_compra"]
    ok_puesto = ok.get("puesto dentro de capacidad y año de compra de cada modelo", False)
    for nombre, clave in [("grupos de capacidad y año de compra con algún modelo con puesto", "grupos_con_puesto"),
                          ("grupos de capacidad y año de compra con dos modelos con puesto o más",
                           "grupos_con_dos_o_mas")]:
        c4.append(cifra(nombre, f"preguntas.B4.tablas.resumen_ranking.grupos_compra.{clave}", gc[clave], "grupos",
                        pob4 + "; modelos con puesto", periodo_todo, resumen["con_puesto"], gc_rec[clave],
                        "recuento_diario_corregido + dim_precio_gb", gc[clave] == gc_rec[clave] and ok_puesto))
    # Encargo 17: modelos con puesto, coste a igual edad y sensibilidad al precio inferido
    c4.append(cifra("modelos con puesto en el ranking de coste (20 fallos o más)",
                    "preguntas.B4.tablas.resumen_ranking.con_puesto", resumen["con_puesto"], "modelos", pob4,
                    periodo_todo, len(ranking), resumen_rec["con_puesto"], "recuento_diario_corregido",
                    resumen["con_puesto"] == resumen_rec["con_puesto"]
                    and [f["model"] for f in ranking if f["puesto"] is None]
                    == [f["model"] for f in ranking_rec if f["puesto"] is None]))
    for nombre, clave in [("correlación de Spearman entre el coste observado y el coste a igual edad", "spearman"),
                          ("mayor salto de puesto entre el coste observado y el coste a igual edad", "mayor_salto")]:
        c4.append(cifra(nombre, f"preguntas.B4.tablas.coste_igual_edad.{clave}", r(ie_res[clave], 8), clave,
                        pob4 + "; con la tasa a igual edad del 09", periodo_todo, ie_res["modelos"],
                        r(ie_res_rec[clave], 8), "recuento_diario_corregido + dim_precio_gb, tasa a igual edad del 09",
                        igual(ie_res_rec[clave], ie_res[clave]) and ie_res["modelos"] == ie_res_rec["modelos"]))
    s_rec = {x["factor"]: x for x in sens_rec}
    for x in sens:
        g = s_rec.get(x["factor"], {})
        c4.append(cifra(f"de los diez primeros, los que siguen con el precio inferido × {numero(x['factor'], 1)}",
                        f"preguntas.B4.tablas.sensibilidad_precio[factor={x['factor']}].siguen", x["siguen"], "modelos",
                        pob4 + "; modelos con puesto", periodo_todo, len(con_puesto), g.get("siguen"),
                        "recuento_diario_corregido + dim_precio_gb",
                        g.get("siguen") == x["siguen"] and g.get("primero") == x["primero"]))
    vb_bajan = sum(1 for x in vida_bucle.values() if x["vida_real_anos"] is not None)
    vb_base = sum(1 for x in vida_bucle.values() if x["ultima_edad_con_base"] is not None)
    vb_s = min((x["s_ultima_edad_con_base"] for x in vida_bucle.values() if x["ultima_edad_con_base"] is not None),
               default=None)
    c4.append(cifra("modelos cuya curva con base baja de 0,5", "preguntas.B4.tablas.vida_real.bajan_de_05",
                    vida_res["bajan_de_05"], "modelos", POBLACION, periodo_todo, int(len(vida)), vb_bajan,
                    "vida_discos, tabla de vida disco a disco", vida_res["bajan_de_05"] == vb_bajan))
    c4.append(cifra("modelos con algún año de edad con base", "preguntas.B4.tablas.vida_real.con_algun_ano_con_base",
                    vida_res["con_algun_ano_con_base"], "modelos", POBLACION, periodo_todo, int(len(vida)), vb_base,
                    "vida_discos, tabla de vida disco a disco", vida_res["con_algun_ano_con_base"] == vb_base))
    if vida_res["s_mas_baja"] is not None:
        c4.append(cifra(f"S más baja en la última edad con base: {vida_res['s_mas_baja']['model']}",
                        "preguntas.B4.tablas.vida_real.s_mas_baja.s", r(vida_res["s_mas_baja"]["s"], 8),
                        "parte que sigue (0 a 1)", POBLACION, periodo_todo, int(len(vida)), r(vb_s, 8),
                        "vida_discos, tabla de vida disco a disco", igual(vb_s, vida_res["s_mas_baja"]["s"])))
    c4.append(cifra("celdas de año y capacidad con mejor modelo", "preguntas.B4.tablas.mejor_modelo.celdas", len(con),
                    "celdas", POBLACION + "; modelos con precio", periodo_todo, int(len(celdas)), len(con_rec),
                    "recuento_diario_corregido + dim_precio_gb", len(con) == len(con_rec)))
    pa_rec = {x["ano"]: x for x in por_ano_rec}
    for x in por_ano:
        g = pa_rec.get(x["ano"], {})
        per = f"año {x['ano']}" + (" (parcial)" if x["parcial"] else "")
        for nombre, clave in [("diferencia con el mejor modelo", "diferencia"), ("parte del precio", "parte_precio"),
                              ("parte de los fallos", "parte_fallos"), ("coste real", "coste_real")]:
            c4.append(cifra(f"{nombre}, {x['ano']}", f"preguntas.B4.tablas.mejor_modelo.por_ano[ano={x['ano']}].{clave}",
                            r(x[clave], 6), "dólares", POBLACION + "; modelos con precio", per, x["celdas"],
                            r(g.get(clave), 6), "recuento_diario_corregido + dim_precio_gb", igual(g.get(clave), x[clave])))
    ing_rec = {x["ano"]: x for x in ingreso_rec}
    for x in ingreso:
        g = ing_rec[x["ano"]]
        for nombre, clave, un in [("capacidad media", "capacidad_media_tb", "TB"),
                                  ("ingreso por TB", "ingreso_por_tb", "dólares por TB"),
                                  ("coste por TB y año de todos los discos con precio", "coste_tb_ano_todos",
                                   "dólares por TB y año")]:
            c4.append(cifra(f"{nombre}, {x['ano']}", f"preguntas.B4.tablas.ingreso_por_tb[ano={x['ano']}].{clave}",
                            r(x[clave], 6), un, POBLACION, f"año {x['ano']}", int((celdas["ano"] == x["ano"]).sum()),
                            r(g[clave], 6), "recuento_diario_corregido (× capacidad de dim_modelo) + dim_precio_gb",
                            igual(g[clave], x[clave])))

    c9 = []
    pob9 = POBLACION + "; todos los modelos (reglas §7, «Población del análisis»)"
    per9 = f"de {prev_q[0]['trimestre']} a {prev_q[-1]['trimestre']}"
    pares_rec = set(da.loc[da > 0].index) | set(ra.index)
    pares_rec |= {(q["trimestre"], k) for q in prev_q for (t_, k) in ra.index if t_ == anterior[q["trimestre"]]}
    pares_rec = {x for x in pares_rec if x[0] in {q["trimestre"] for q in prev_q}}
    c9.append(cifra("pares de trimestre y capacidad", "preguntas.B9.tablas.pares", len(pares), "pares", pob9, per9,
                    len(pares), len(pares_rec), "recuento_diario_corregido (discos del primer día y fallos)",
                    len(pares) == len(pares_rec)))
    c9.append(cifra("fallos reales", "preguntas.B9.tablas.error.real", total_real, "fallos", pob9, per9, len(pares),
                    rec_periodo, "recuento_diario_corregido", total_real == rec_periodo))
    tot_b = float(pb.sum())
    c9.append(cifra("fallos previstos", "preguntas.B9.tablas.error.previsto", r(tot["previsto"], 6), "fallos", pob9,
                    per9, len(pares), r(tot_b, 6), "dias_por_tramo, fila a fila con diccionarios",
                    igual(tot_b, tot["previsto"])))
    pares_b = montar_pares(prev_bucle, {k: int(v) for k, v in ra.items()}, prev_q, anterior)
    tot_bb = resumen_error(pares_b)
    for nombre, clave in [("error absoluto ponderado de la cuenta", "wape_cuenta"), ("sesgo de la cuenta", "sesgo_cuenta"),
                          ("error absoluto ponderado de la referencia", "wape_referencia"),
                          ("sesgo de la referencia", "sesgo_referencia")]:
        c9.append(cifra(nombre, f"preguntas.B9.tablas.error.{clave}", r(tot[clave], 8), "parte de los fallos reales",
                        pob9, per9, len(pares), r(tot_bb[clave], 8),
                        "previsión fila a fila y reales del recuento_diario_corregido", igual(tot_bb[clave], tot[clave])))
    pc_b = {x["capacidad_tb"]: x for x in resumen_error(pares_b, "capacidad_tb")}
    for x in por_capacidad:
        g = pc_b.get(x["capacidad_tb"], {})
        for nombre, clave in [("previstos", "previsto"), ("reales", "real")]:
            c9.append(cifra(f"fallos {nombre} de {numero(x['capacidad_tb'], 0)} TB",
                            f"preguntas.B9.tablas.por_capacidad[capacidad_tb={x['capacidad_tb']}].{clave}",
                            r(x[clave], 6), "fallos", pob9 + f"; {numero(x['capacidad_tb'], 0)} TB", per9, x["pares"],
                            r(g.get(clave), 6), "previsión fila a fila y recuento_diario_corregido",
                            igual(g.get(clave), x[clave])))
    pt_b = {x["trimestre"]: x for x in resumen_error(pares_b, "trimestre")}
    for x in por_trimestre:
        g = pt_b.get(x["trimestre"], {})
        for nombre, clave in [("previstos", "previsto"), ("reales", "real"), ("de la referencia", "referencia")]:
            c9.append(cifra(f"fallos {nombre} de {x['trimestre']}",
                            f"preguntas.B9.tablas.serie_lineas[trimestre={x['trimestre']}].{clave}", r(x[clave], 6),
                            "fallos", pob9, x["trimestre"], x["pares"], r(g.get(clave), 6),
                            "previsión fila a fila y recuento_diario_corregido", igual(g.get(clave), x[clave])))
    for s in sensibilidad:
        c9.append(cifra(f"error absoluto ponderado, sensibilidad: {s['variante']}",
                        f"preguntas.B9.tablas.sensibilidad[variante={s['variante']}].wape", r(s["wape"], 8),
                        "parte de los fallos reales", pob9, per9, len(pares), r(s["wape_bucle"], 8),
                        "previsión fila a fila con diccionarios", igual(s["wape_bucle"], s["wape"])))
    inv_fv = int(fq["despues_fv"].sum())
    c9.append(cifra("fallos de discos que aparecen después del primer día de su trimestre",
                    "preguntas.B9.tablas.invisibles.fallos", invisibles["fallos"], "fallos", pob9, per9,
                    invisibles["de"], inv_fv, "fotos_mensuales_corregido + ventanas_fallo_corregido",
                    invisibles["fallos"] == inv_fv and invisibles["sin_vida"] == 0))

    # ---------------------------------------------------------------------------------------------------------
    # Lo que no saca conclusión, y montaje de las dos preguntas
    # ---------------------------------------------------------------------------------------------------------
    sin4 = ([{"bloque": "B4", "tipo": "celdas", "grupo": "celdas de modelo y año por debajo del mínimo",
              "casos": fuera["celdas"], "dias_disco": fuera["dias_disco"], "fallos": fuera["fallos"]},
             {"bloque": "B4", "tipo": "sin precio", "grupo": "modelos sin precio", "casos": sin_precio["modelos"],
              "dias_disco": sin_precio["dias_disco"], "fallos": sin_precio["fallos"]}]
            + [{"bloque": "B4", "tipo": "sin mejor", "grupo": f"{x['ano']}, {numero(x['capacidad_tb'], 0)} TB",
                "casos": x["modelos_con_precio"], "coste_real": x["coste_real"]} for x in sin]
            + [{"bloque": "B4", "tipo": "vida sin base", "grupo": "modelos sin ningún año de edad con 20 fallos",
                "casos": vida_res["modelos_datos"] - vida_res["con_algun_ano_con_base"]}]
            + [{"bloque": "B4", "tipo": "pocos fallos", "grupo": f["model"], "casos": f["fallos"],
                "dias_disco": f["dias_disco"], "coste_tb_ano": f["coste_tb_ano"]}
               for f in ranking if f["puesto"] is None])
    sin9 = [{"bloque": "B9", "tipo": "sin tasa", "grupo": n["trimestre"], "casos": n["sin tasa"]}
            for n in niveles if n["sin tasa"] > 0]

    serie_dispersion = [{"model": f["model"], "tasa": f["tasa"], "coste_tb_ano": f["coste_tb_ano"],
                         "discos_medios": f["discos_medios"], "origen_precio": f["origen_precio"],
                         "capacidad_tb": f["capacidad_tb"]} for f in ranking]
    q4 = {"id": "B4", "pregunta": "Cuánto cuesta cada modelo de disco por terabyte y año, contando los que se rompen",
          "decision": "qué modelos comprar: un disco barato que falla mucho puede salir más caro (plan, bloque 4)",
          "planteamiento": "contexto-proyecto/metodo/plan_de_la_analitica.md, bloque 4; metodo/04_planteamientos.md §1.A",
          "funcion": "otra",
          "funcion_adaptada": ("ninguna función del capítulo 42 calcula un coste por unidad con averías: se usa la "
                               "fórmula de las reglas §6 con el esquema de consulta agrupada (13.6), el ranking con "
                               "empates «min» (11.10) y la tabla de vida del encargo 13 para la vida real"),
          "poblacion": {"regla": POBLACION + "; en el ranking, modelos con precio y sus años con 50.000 días de disco o más",
                        "periodo": periodo_todo, "filas": int(len(mt)), "unidad": "modelo de disco",
                        "entidades": int(mt["model"].nunique())},
          "medida": ("coste por TB y año = precio / capacidad / 6 + tasa anual × (disco nuevo del año del fallo + 37 "
                     "dólares) / capacidad, que se calcula como suma del coste de los fallos / terabytes-año (reglas §6)"),
          "minimo_casos": "50.000 días de disco del modelo en el año (reglas §7)",
          "que_cambia_la_decision": ("un modelo cuyo coste por TB y año queda por debajo de los demás de su capacidad es "
                                     "candidato a comprarse; la parte de los fallos dice cuánto pesa la fiabilidad"),
          "cifras": c4,
          "referencia": {"que_es": ("el coste por TB y año del conjunto de discos en las mismas celdas del ranking; para "
                                    "el mejor modelo, el coste real de todos los modelos con precio de su capacidad y año"),
                         "valor": r(ref4["coste_tb_ano"], 8), "dias_disco": ref4["dias_disco"], "fallos": ref4["fallos"],
                         "filas": ref4["celdas"]},
          "comprobaciones": b4_comp, "motivos_null": {k: v for k, v in motivos_b4.items() if b4_comp[k] is None},
          "comprobaciones_extra": {"partes_suman_total": partes_ok,
                                   "puesto_dentro_del_grupo": comp_puesto_grupo(ranking)},
          "sin_conclusion": sin4,
          "tablas": {"ranking": ranking, "resumen_ranking": resumen, "serie_dispersion": serie_dispersion,
                     "coste_igual_edad": ie_res, "sensibilidad_precio": sens,
                     "celdas_que_pasan": n_pasan, "celdas_total": int(len(celdas)), "fuera_del_ranking": fuera,
                     "sin_precio": sin_precio,
                     "vida_real": {**vida_res, "modelos": [{k: v for k, v in x.items() if k != "tabla_de_vida"}
                                                           | {"tabla_de_vida": x["tabla_de_vida"]}
                                                           for x in vida_modelos]},
                     "mejor_modelo": {"celdas": con, "sin_mejor": sin, "por_ano": por_ano,
                                      "celdas_con_diferencia_negativa": [f"{x['ano']} con {numero(x['capacidad_tb'], 0)} TB"
                                                                         for x in con if x["diferencia"] < -TOLERANCIA]},
                     "ingreso_por_tb": ingreso,
                     "ingreso_2025": "no se calcula: necesita la capacidad de julio a diciembre de 2025, que es reserva "
                                     "(reglas §6)"}}
    q9 = {"id": "B9", "pregunta": "Cuántos discos fallarán el próximo trimestre, por capacidad",
          "decision": "cuántos discos de repuesto comprar y cuántas horas de técnico hacen falta (plan, bloque 9)",
          "planteamiento": "contexto-proyecto/metodo/plan_de_la_analitica.md, bloque 9; metodo/04_planteamientos.md §1.B",
          "funcion": "otra",
          "funcion_adaptada": ("ninguna función del capítulo 42 prevé un recuento: es una cuenta con las tasas por "
                               "modelo y edad medidas hasta el día anterior, medida con el error absoluto ponderado y "
                               "el sesgo frente a la referencia ingenua (31.9)"),
          "poblacion": {"regla": pob9 + "; los discos del primer día de cada trimestre", "periodo": per9,
                        "filas": int(len(filas_all)), "unidad": "par de trimestre y capacidad",
                        "entidades": len(pares)},
          "medida": ("previstos = suma de discos del primer día × días del trimestre × tasa diaria de su modelo y año "
                     "de edad, con los meses anteriores al primer día; error absoluto ponderado = suma de |previsto − "
                     "real| / suma de reales, y el sesgo con signo (reglas §7, CP-011)"),
          "minimo_casos": "50.000 días de disco en la celda de modelo y edad, o de capacidad y edad (reglas §7; criterio 5)",
          "que_cambia_la_decision": ("si la cuenta gana a repetir el trimestre anterior, se usa para comprar repuestos y "
                                     "planificar horas; si no gana, la cuenta no vale y se usa la referencia (reglas §7)"),
          "cifras": c9,
          "referencia": {"que_es": "repetir los fallos reales del trimestre anterior de la misma capacidad",
                         "valor": r(tot["wape_referencia"], 8), "sesgo": r(tot["sesgo_referencia"], 8),
                         "filas": len(pares)},
          "comprobaciones": b9_comp, "motivos_null": {k: v for k, v in motivos_b9.items() if b9_comp[k] is None},
          "comprobaciones_extra": {"sin_futuro": sin_futuro, "reales_cuadran_recuento": total_real == rec_periodo},
          "sin_conclusion": sin9,
          "tablas": {"pares": pares,
                     "error": {"cuenta": {"wape": tot["wape_cuenta"], "sesgo": tot["sesgo_cuenta"]},
                               "referencia": {"wape": tot["wape_referencia"], "sesgo": tot["sesgo_referencia"]},
                               "previsto": tot["previsto"], "real": tot["real"], "gana_la_cuenta": bool(gana),
                               "veredicto": ("la cuenta gana a la referencia y se usa" if gana else
                                             "la cuenta no gana: no vale y se usa la referencia (reglas §7)")},
                     "serie_lineas": por_trimestre, "por_capacidad": por_capacidad, "niveles": niveles,
                     "parte_de_discos_con_tasa": parte_con_tasa, "sensibilidad": sensibilidad,
                     "filas_sin_dias": {"filas": int(dpt["dias_disco"].isna().sum()),
                                        "fallos": int(dpt.loc[dpt["dias_disco"].isna(), "fallos"].sum()),
                                        "trato": "cuentan 0 días de disco y sus fallos entran en la tasa"},
                     "invisibles": invisibles}}
    return {"preguntas": [q4, q9], "segundas_vias": sv, "periodo": periodo_todo}


# =================================================================================================================
# 11. Validaciones (skill §7) y búsqueda de resultados escritos
# =================================================================================================================
def buscar_resultados_escritos(texto):
    """Líneas del código con una comprobación o validación puesta a True o con una cifra larga escrita.

    Cifras de cinco cifras o más: solo pasa el mínimo de días de las reglas (§7). Devuelve [(línea, texto)].
    """
    claves = "|".join(COMPROBACIONES + VALIDACIONES + EXTRAS + ["coinciden", "gana_la_cuenta"])
    p_true = re.compile(r"[\"'](" + claves + r")[\"']\s*\]?\s*[:=]\s*True\b|\b(" + claves + r")\s*=\s*True\b")
    p_num = re.compile(r"(?<![\w.])\d[\d_]{4,}(?![\w.])")
    permitidas = {str(MINIMO_DIAS_ANO)}
    hallado = []
    for n, linea in enumerate(texto.splitlines(), 1):
        if p_true.search(linea):
            hallado.append((n, linea.strip()))
            continue
        if any(m.replace("_", "") not in permitidas for m in p_num.findall(linea)):
            hallado.append((n, linea.strip()))
    return hallado


def validar(res, fuente, h_antes, h_despues, res2):
    """Las nueve validaciones de la skill, cada una calculada sobre el resultado y el código."""
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
def usd(x, d=0):
    """Dólares a la española, o «sin dato»."""
    return "sin dato" if x is None else numero(x, d) + " dólares"


def pct(x, d=2):
    """Un porcentaje a la española, o «sin dato»."""
    return "sin dato" if x is None else numero(x, d, " %")


def cientifica(x):
    """Un número pequeño en notación científica con coma decimal: 5e-10 -> «5,0e-10»; el cero, «0»."""
    return "0" if not x else f"{x:.1e}".replace(".", ",")


def fecha_es(texto_iso):
    """«2025-06-30» -> «30/06/2025»."""
    a, m, d = texto_iso[:10].split("-")
    return f"{d}/{m}/{a}"


def lista_y(elementos):
    """«1, 4, 7 y 8»."""
    e = [str(x) for x in elementos]
    return e[0] if len(e) == 1 else ", ".join(e[:-1]) + " y " + e[-1]


NOMBRES_COMPROBACION = {"unidad": "La unidad", "minimo": "El mínimo de casos", "empates": "Los empates",
                        "referencia": "La referencia", "azar_en_grupos": "El azar en muchos grupos",
                        "pesos": "Los pesos", "hacia_adelante": "Hacia adelante", "cobertura": "La cobertura",
                        "periodos": "Los periodos"}
NOMBRES_EXTRA = {"partes_suman_total": "las dos partes de la diferencia con el mejor modelo suman el total en cada celda",
                 "puesto_dentro_del_grupo": ("ningún puesto compara modelos de distinta capacidad o año de compra "
                                             "(encargo 19)"),
                 "sin_futuro": "ninguna tasa de la previsión usa un mes igual o posterior al primer día de su trimestre",
                 "reales_cuadran_recuento": "los fallos reales de los trimestres previstos suman lo mismo que el recuento",
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
    """Las nueve comprobaciones de una pregunta y las del encargo, con su resultado o su motivo."""
    L.append(f"Las comprobaciones de {q['id']}:")
    L.append("")
    for k, v in q["comprobaciones"].items():
        texto = "sí" if v is True else "no" if v is False else "no aplica, porque " + q["motivos_null"][k]
        L.append(f"- {NOMBRES_COMPROBACION[k]}: {texto}.")
    for k, v in q.get("comprobaciones_extra", {}).items():
        L.append(f"- Del encargo, {NOMBRES_EXTRA[k]}: {'sí' if v else 'no'}.")
    L.append("")


def informe(j):
    """Texto Markdown del informe, con los apartados de resultado.md, a partir del JSON."""
    L = []
    est = j["resultado"]
    L.append("# Coste por terabyte de cada modelo y previsión de fallos por trimestre")
    L.append("")
    L.append(f"Caso 68, paso 5, bloques 4 y 9 del plan de la analítica. Datos hasta el {fecha_es(j['fecha_datos'])}; "
             f"ejecutado el {fecha_es(j['fecha_ejecucion'])}. Estado: **{est['estado']}**, riesgo {est['riesgo']}.")
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
    b4, b9 = p["B4"]["tablas"], p["B9"]["tablas"]

    # Las preguntas y su planteamiento
    L.append("## Las preguntas y su planteamiento")
    L.append("")
    L.append("Las dos preguntas salen del plan de la analítica, aprobado por Juan el 16/11/2026, y de los "
             "planteamientos 1.A y 1.B. Entran los discos de datos, sin los de arranque, del 01/01/2020 al "
             "30/06/2025. La tasa anual de fallo es 100 × 365 × fallos / días de disco.")
    L.append("")
    for q in j["preguntas"]:
        L.append(f"- **{q['id']}.** {q['pregunta']}.")
        L.append(f"  - Decisión que apoya: {q['decision']}.")
        L.append(f"  - Medida: {q['medida']}.")
        L.append(f"  - Mínimo: {q['minimo_casos']}.")
        L.append(f"  - Referencia: {q['referencia']['que_es']}.")
    L.append("")
    L.append("La teoría del manual que se aplicó:")
    L.append("")
    for x in j["teoria"]:
        L.append(f"- {x['apartado']}: {x['por_que']}.")
    L.append("")

    # B4
    rk = b4["ranking"]
    rr = b4["resumen_ranking"]
    # El más barato y el más caro, entre los que tienen puesto (CP-012: los que no lo tienen van al final)
    rkp = [f for f in rk if f["puesto"] is not None]
    L.append("## B4 · Cuánto cuesta cada modelo")
    L.append("")
    L.append(f"El modelo más barato por terabyte y año es el {rkp[0]['model']}, con {usd(rkp[0]['coste_tb_ano'], 4)}, "
             f"y el más caro el {rkp[-1]['model']}, con {usd(rkp[-1]['coste_tb_ano'], 4)}. Entran {len(rk)} modelos, "
             f"con los {b4['celdas_que_pasan']} años de modelo que pasan el mínimo de 50.000 días de disco. "
             + (f"{len(rkp)} llevan puesto; los {rr['sin_puesto']} con menos de {rr['minimo_fallos']} fallos salen con "
                "su coste, sin puesto y al final de la tabla (reglas §7, CP-012)." if rr["sin_puesto"] else
                f"Todos tienen {rr['minimo_fallos']} fallos o más y llevan puesto (reglas §7, CP-012)."))
    L.append("")
    L.append(f"Los fallos pesan poco en el coste: su parte tiene una mediana del {pct(rr['mediana_parte_fallos_pct'])} "
             f"entre los {len(rkp)} modelos con puesto, y el resto es la amortización del precio de compra. El orden por coste se "
             f"parece poco al orden por tasa de fallo: la correlación de Spearman entre los dos es de "
             f"{numero(rr['spearman_coste_tasa'], 3)}. Además, {rr['primeros_diez_inferidos']} de los "
             f"{rr['primeros_diez']} primeros tienen el precio inferido, así que su puesto vale lo que valga ese precio.")
    L.append("")
    gc = rr["grupos_compra"]
    L.append(f"El puesto se da dentro de cada capacidad y año de compra, que es donde la tasa de fallo decide: entre "
             "años de compra, el orden lo pone el precio de cada año (reglas §7). Hay "
             f"{gc['grupos_con_puesto']} grupos con algún modelo con puesto, y {gc['grupos_con_dos_o_mas']} con dos o "
             "más, que son los únicos donde el puesto compara modelos:")
    L.append("")
    for g in gc["grupos"]:
        if len(g["modelos"]) >= 2:
            L.append(f"- {numero(g['capacidad_tb'], 0)} TB comprados en {g['ano_compra'] or 'año sin dato'}: "
                     + "; ".join(f"{x['puesto']}.º {x['model']}, {usd(x['coste_tb_ano'], 4)}" for x in g["modelos"]) + ".")
    L.append("")
    L.append("El orden de todos juntos va al lado, como contexto, en la columna «De todos» y en el resumen de arriba.")
    L.append("")
    L.append("Cada coste va en dólares por TB y año. El intervalo pone en la parte de los fallos el intervalo al 95 % de "
             "la tasa; con garantía, un fallo dentro de ella cuesta solo los 37 dólares del cambio.")
    L.append("")
    L.append("| En su grupo | De todos | Modelo | TB | Año de compra | Tasa | Precio | Amortización | Fallos | Coste | "
             "Intervalo | Con garantía | A igual edad |")
    L.append("|---:|---:|---|---:|---:|---:|---|---:|---:|---:|---|---:|---:|")
    for f in rk:
        cie = f.get("coste_tb_ano_igual_edad")
        L.append(f"| {f['puesto'] if f['puesto'] is not None else 'sin puesto'} | "
                 f"{f['puesto_global'] if f['puesto_global'] is not None else 'sin puesto'} | {f['model']} | "
                 f"{numero(f['capacidad_tb'], 0)} | {f['ano_compra'] or 'sin dato'} | {pct(f['tasa'])} | "
                 f"{numero(f['precio_usd'], 0)} ({f['origen_precio']}) | {numero(f['amortizacion_tb_ano'], 4)} | "
                 f"{numero(f['fallos_tb_ano'], 4)} | {numero(f['coste_tb_ano'], 4)} | "
                 f"{numero(f['coste_desde'], 4)} a {numero(f['coste_hasta'], 4)} | "
                 f"{numero(f['coste_tb_ano_garantia'], 4) if f['coste_tb_ano_garantia'] is not None else 'sin dato'} | "
                 f"{numero(cie, 4) if cie is not None else 'sin dato'} |")
    L.append("")
    # Encargo 17: el coste con la tasa a igual edad y la sensibilidad al precio inferido
    ce = b4["coste_igual_edad"]
    L.append(f"La última columna pone en la parte de los fallos la tasa a igual edad de cada modelo, la del bloque 2: "
             "la que tendría con la mezcla de edades de todos los discos. Con los "
             f"{ce['modelos']} modelos, la correlación de Spearman entre el coste observado y el de igual edad es de "
             f"{numero(ce['spearman'], 4) if ce['spearman'] is not None else 'sin dato'}, y el mayor salto de puesto es "
             f"de {ce['mayor_salto']}" + (f" ({lista_y(ce['modelos_mayor_salto'])})" if ce["mayor_salto"] else "")
             + ".")
    L.append("")
    L.append("Si los precios inferidos estuvieran un 20 % por debajo o por encima, los diez primeros con puesto "
             "quedarían así:")
    L.append("")
    for x in b4["sensibilidad_precio"]:
        cambio = (f"; salen {lista_y(x['salen'])} y entran {lista_y(x['entran'])}" if x["salen"] else "")
        L.append(f"- Precio inferido × {numero(x['factor'], 1)}: siguen {x['siguen']} de {x['de']}{cambio}. El primero "
                 f"es el {x['primero']}.")
    L.append("")
    ref = p["B4"]["referencia"]
    L.append(f"El conjunto de discos de esas mismas celdas cuesta {usd(ref['valor'], 4)} por TB y año. La serie del "
             "gráfico de dispersión, con la tasa, el coste y los discos medios de cada modelo, está en el JSON.")
    L.append("")
    fu, sp = b4["fuera_del_ranking"], b4["sin_precio"]
    L.append(f"Fuera del ranking quedan {fu['celdas']} años de modelo por debajo del mínimo, con "
             f"{numero(fu['dias_disco'])} días de disco y {numero(fu['fallos'])} fallos. Los {sp['modelos']} modelos sin "
             f"precio suman {numero(sp['dias_disco'])} días de disco y {numero(sp['fallos'])} fallos, y ninguno de sus "
             "años llega al mínimo.")
    L.append("")
    vr = b4["vida_real"]
    if vr["bajan_de_05"] == 0 and vr["s_mas_baja"] is not None:
        L.append(f"La vida real no se puede medir: ningún modelo baja del 50 % de discos vivos en su curva con base. "
                 f"De los {vr['modelos_datos']} modelos de datos, {vr['con_algun_ano_con_base']} tienen algún año de "
                 f"edad con 20 fallos o más. La curva que más baja es la del {vr['s_mas_baja']['model']}, que se queda "
                 f"en el {pct(100 * vr['s_mas_baja']['s'])} a {vr['s_mas_baja']['edad']} años. El coste usa la vida "
                 "contable de 6 años.")
    else:
        L.append(f"{vr['bajan_de_05']} de los {vr['modelos_datos']} modelos de datos bajan del 50 % de discos vivos en su "
                 "curva con base; su vida real va en el JSON, modelo a modelo.")
    L.append("")
    pa_ = b4["mejor_modelo"]["por_ano"]
    L.append("Si cada año se hubieran comprado solo discos del modelo más barato de cada capacidad, el coste habría "
             "bajado en estas cifras, en dólares:")
    L.append("")
    L.append("| Año | Capacidades | Coste real | Con el mejor | Diferencia | Del precio | De los fallos |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for x in pa_:
        L.append(f"| {x['ano']}{' (parcial)' if x['parcial'] else ''} | {x['celdas']} | {numero(x['coste_real'])} | "
                 f"{numero(x['coste_con_mejor'])} | {numero(x['diferencia'])} | {numero(x['parte_precio'])} | "
                 f"{numero(x['parte_fallos'])} |")
    L.append("")
    completos = [x for x in pa_ if not x["parcial"]]
    mayor = max(completos, key=lambda x: x["diferencia"]) if completos else None
    if mayor is not None:
        L.append(f"En {mayor['ano']}, el año con más diferencia, {numero(mayor['parte_precio'])} de los "
                 f"{numero(mayor['diferencia'])} dólares salen del precio de compra y {numero(mayor['parte_fallos'])} de "
                 "los fallos. En la tabla de precios, dos modelos de la misma capacidad solo cambian de precio por su "
                 "año de compra, así que la parte del precio sale de haber comprado en otro año.")
        L.append("")
    neg = b4["mejor_modelo"]["celdas_con_diferencia_negativa"]
    if neg:
        L.append(f"En {len(neg)} combinaciones de año y capacidad la diferencia sale negativa ({lista_y(neg)}): el mejor "
                 "modelo que pasa el mínimo cuesta más por TB y año que algún modelo de su capacidad que no llega a él.")
        L.append("")
    if b4["mejor_modelo"]["sin_mejor"]:
        L.append(f"{len(b4['mejor_modelo']['sin_mejor'])} combinaciones de año y capacidad no tienen ningún modelo que "
                 "pase el mínimo y quedan fuera de esta tabla; van en el JSON con su coste real.")
        L.append("")
    L.append("El ingreso de Backblaze por terabyte de disco es un orden de magnitud: la capacidad incluye la paridad y "
             "el espacio libre, y lo que guardan los clientes no se publica.")
    L.append("")
    for x in b4["ingreso_por_tb"]:
        L.append(f"- {x['ano']}: {usd(x['ingreso_por_tb'], 2)} de ingreso por TB, con {numero(x['capacidad_media_tb'])} "
                 f"TB de media. El coste por TB y año de todos los discos con precio fue de "
                 f"{usd(x['coste_tb_ano_todos'], 3)}, y de {usd(x['coste_tb_ano_todos_garantia'], 3)} con garantía.")
    L.append(f"- 2025: {b4['ingreso_2025']}.")
    L.append("")
    seccion_comprobaciones(L, p["B4"])

    # B9
    e = b9["error"]
    L.append("## B9 · Cuántos discos fallarán el próximo trimestre")
    L.append("")
    if e["gana_la_cuenta"]:
        L.append(f"La cuenta gana a la referencia: su error absoluto ponderado es {numero(e['cuenta']['wape'], 4)}, frente "
                 f"a {numero(e['referencia']['wape'], 4)} de repetir los fallos del trimestre anterior.")
    else:
        L.append(f"La cuenta no gana a la referencia: su error absoluto ponderado es {numero(e['cuenta']['wape'], 4)}, "
                 f"frente a {numero(e['referencia']['wape'], 4)} de repetir los fallos del trimestre anterior. Con la "
                 "regla del caso (reglas §7), la cuenta no vale y se usa la referencia.")
    L.append("")
    L.append(f"La cuenta prevé de más: su sesgo es de {numero(e['cuenta']['sesgo'], 4, con_signo=True)}, y el de la "
             f"referencia, de {numero(e['referencia']['sesgo'], 4, con_signo=True)}. En los "
             f"{len(b9['serie_lineas'])} trimestres prevé {numero(e['previsto'], 1)} fallos, y hubo "
             f"{numero(e['real'])}." if e["cuenta"]["sesgo"] > 0 else
             f"La cuenta prevé de menos: su sesgo es de {numero(e['cuenta']['sesgo'], 4, con_signo=True)}, y el de la "
             f"referencia, de {numero(e['referencia']['sesgo'], 4, con_signo=True)}. En los "
             f"{len(b9['serie_lineas'])} trimestres prevé {numero(e['previsto'], 1)} fallos, y hubo "
             f"{numero(e['real'])}.")
    L.append("")
    L.append("Cada trimestre se prevé con los discos del primer día y las tasas medidas hasta el día anterior. La "
             "serie de las tres líneas del gráfico es esta, en fallos:")
    L.append("")
    L.append("| Trimestre | Previstos | Reales | Referencia | Error de la cuenta | Error de la referencia |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for x in b9["serie_lineas"]:
        L.append(f"| {x['trimestre']} | {numero(x['previsto'], 1)} | {numero(x['real'])} | {numero(x['referencia'])} | "
                 f"{numero(x['wape_cuenta'], 4)} | {numero(x['wape_referencia'], 4)} |")
    L.append("")
    L.append("Por capacidad, en todos los trimestres juntos:")
    L.append("")
    L.append("| Capacidad | Previstos | Reales | Referencia | Error de la cuenta | Error de la referencia |")
    L.append("|---:|---:|---:|---:|---:|---:|")
    for x in b9["por_capacidad"]:
        L.append(f"| {numero(x['capacidad_tb'], 0)} TB | {numero(x['previsto'], 1)} | {numero(x['real'])} | "
                 f"{numero(x['referencia'])} | "
                 f"{numero(x['wape_cuenta'], 4) if x['wape_cuenta'] is not None else 'sin reales'} | "
                 f"{numero(x['wape_referencia'], 4) if x['wape_referencia'] is not None else 'sin reales'} |")
    L.append("")
    L.append(f"Las horas de técnico previstas son 0,74 por fallo previsto; van por trimestre y capacidad en el JSON, "
             f"con los {len(b9['pares'])} pares.")
    L.append("")
    nv = b9["niveles"]
    tot_n = {k: sum(x[k] for x in nv) for k in ["modelo", "capacidad", "edad", "sin tasa", "discos"]}
    L.append(f"La tasa de cada disco del primer día sale de su modelo y año de edad si esa celda tiene 50.000 días de "
             f"disco o más; si no, de su capacidad y edad, y si tampoco, de su edad con todos los discos. Sumando los "
             f"trimestres, el {pct(100 * tot_n['modelo'] / tot_n['discos'], 1)} de los discos usó la de su modelo, "
             f"{pct(100 * tot_n['capacidad'] / tot_n['discos'], 1)} la de su capacidad y "
             f"{pct(100 * tot_n['edad'] / tot_n['discos'], 1)} la de su edad. El reparto por trimestre está en el JSON.")
    L.append("")
    L.append("La sensibilidad, solo para leer, cambia la regla de la tasa. El veredicto lo da la cuenta principal:")
    L.append("")
    for s in b9["sensibilidad"]:
        L.append(f"- {s['variante'][0].upper() + s['variante'][1:]}: error de {numero(s['wape'], 4)}, sesgo de "
                 f"{numero(s['sesgo'], 4, con_signo=True)}; {'gana' if s['gana'] else 'no gana'} a la referencia.")
    L.append("")
    inv = b9["invisibles"]
    L.append(f"La cuenta no puede ver {numero(inv['fallos'])} de los {numero(inv['de'])} fallos reales, el "
             f"{pct(inv['pct'])}: son de discos que aparecen después del primer día de su trimestre, y la regla de la "
             "previsión solo cuenta los discos de ese día (reglas §7). La referencia sí los cuenta.")
    L.append("")
    seccion_comprobaciones(L, p["B9"])

    # Lo que no saca conclusión
    L.append("## Lo que no saca conclusión")
    L.append("")
    for q in j["preguntas"]:
        for x in q["sin_conclusion"]:
            if x["tipo"] == "celdas":
                L.append(f"- B4, {x['casos']} años de modelo por debajo de 50.000 días de disco: {numero(x['fallos'])} "
                         f"fallos en {numero(x['dias_disco'])} días. No entran en el ranking ni pueden ser el mejor modelo.")
            elif x["tipo"] == "sin precio":
                L.append(f"- B4, {x['casos']} modelos sin precio: {numero(x['fallos'])} fallos en "
                         f"{numero(x['dias_disco'])} días de disco. No tienen coste.")
            elif x["tipo"] == "sin mejor":
                L.append(f"- B4, {x['grupo']}: ningún modelo pasa el mínimo; coste real de {usd(x['coste_real'])}.")
            elif x["tipo"] == "pocos fallos":
                L.append(f"- B4, {x['grupo']}: {numero(x['casos'])} fallos en {numero(x['dias_disco'])} días de disco, "
                         f"menos de 20. Sale con su coste, {usd(x['coste_tb_ano'], 4)} por TB y año, pero sin puesto "
                         "(CP-012).")
            elif x["tipo"] == "vida sin base":
                L.append(f"- B4, {x['casos']} modelos sin ningún año de edad con 20 fallos o más: su curva no tiene "
                         "base y no dan vida real.")
            elif x["tipo"] == "sin tasa":
                L.append(f"- B9, {x['grupo']}: {numero(x['casos'])} discos del primer día sin ninguna tasa, porque su "
                         "año de edad no tiene días de disco antes del trimestre; entran con previsto 0.")
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
    L.append("Cada cifra se rehízo por otro camino. Las segundas vías:")
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
def version_skill(raiz):
    """La fecha y el código de la última línea de versión del SKILL.md (bloque común)."""
    ruta = raiz / SKILL_MD
    if not ruta.exists():
        ruta = CASO / SKILL_MD
    lineas = [x for x in ruta.read_text(encoding="utf-8").splitlines() if x.startswith("Versión ")]
    m = re.match(r"Versión (\S+) \(([^)]+)\)", lineas[-1]) if lineas else None
    return f"{m.group(1)} ({m.group(2)})" if m else None


def parametros():
    """Los valores con que se ejecutó, cada uno con su origen."""
    return [
        {"nombre": "mínimo de días de disco en el año para un ranking y para el mejor modelo",
         "valor": numero(MINIMO_DIAS_ANO), "origen": "reglas-negocio §7; sustituye al mínimo de 30 casos de la skill"},
        {"nombre": "mínimo de días de disco de una celda de tasa en la previsión", "valor": numero(MINIMO_DIAS_ANO),
         "origen": "criterio técnico 5 de Claude, con el mínimo de las reglas §7"},
        {"nombre": "vida contable", "valor": f"{VIDA_CONTABLE} años", "origen": "reglas-negocio §3 y §6, CP-001"},
        {"nombre": "coste de un cambio", "valor": f"{COSTE_CAMBIO} dólares", "origen": "reglas-negocio §6, CP-002"},
        {"nombre": "disco nuevo de un fallo", "valor": "misma capacidad al coste por GB del año del fallo (dim_precio_gb)",
         "origen": "reglas-negocio §6"},
        {"nombre": "horas de técnico por cambio", "valor": numero(HORAS_POR_CAMBIO, 2), "origen": "reglas §5, doc. 12b"},
        {"nombre": "coste de un modelo en todo el periodo", "valor": "solo sus celdas de modelo y año que pasan el mínimo",
         "origen": "criterio técnico 1 de Claude, en el encargo"},
        {"nombre": "intervalo del coste", "valor": "la parte de los fallos con el intervalo exacto de Poisson de la tasa",
         "origen": "encargo, B4.1"},
        {"nombre": "vida real", "valor": "edad a la que S baja de 0,5 en la tabla de vida, con la curva cortada antes "
                                         "del primer año de edad con menos de 20 fallos",
         "origen": "criterio técnico 2 de Claude, en el encargo, con el método del encargo 13"},
        {"nombre": "mejor modelo de una capacidad y año", "valor": "el de menor coste por TB y año entre los que pasan "
                                                                   "el mínimo; empates, por nombre",
         "origen": "criterio técnico 3 de Claude, en el encargo"},
        {"nombre": "ingreso por TB", "valor": "«Total revenue» del doc. 16 / capacidad media del año (días × capacidad / "
                                              "días del año en los datos)",
         "origen": "criterio técnico 4 de Claude, en el encargo; reglas §6"},
        {"nombre": "tasa de la previsión", "valor": "modelo y edad, capacidad y edad, o edad, con los meses anteriores al "
                                                    "primer día del trimestre y toda la historia",
         "origen": "criterio técnico 5 de Claude, en el encargo; reglas §7"},
        {"nombre": "filas de dias_por_tramo sin días de disco", "valor": "cuentan 0 días, y sus fallos entran en la tasa",
         "origen": "reglas de transformación §6 (los fallos de una fila sin días están en «fallos»); criterio de "
                   "Claude, el mismo de las sumas por grupo de pandas, que dejan fuera el vacío"},
        {"nombre": "primer trimestre previsto", "valor": etiqueta(*PRIMER_PREVISTO),
         "origen": "plan, bloque 9; encargo: tiene al menos un año de tasas detrás"},
        {"nombre": "medida de la previsión", "valor": "error absoluto ponderado de todos los trimestres y capacidades "
                                                      "a la vez, con el sesgo al lado",
         "origen": "reglas-negocio §7, CP-011"},
        {"nombre": "confianza de los intervalos", "valor": numero(CONFIANZA, 2),
         "origen": "parametros.md de la skill y 42.6 del manual"},
        {"nombre": "tolerancia de las segundas vías en importes y cifras con decimales", "valor": f"{TOLERANCIA:g}",
         "origen": "encargo, «SEGUNDA VÍA»; en los años de exposición de la tabla de vida, 0,001 años, por el redondeo "
                   "de sumar cientos de miles de discos en distinto orden (criterio de Claude)"},
        {"nombre": "mínimo de fallos para tener puesto en el ranking de coste", "valor": str(MINIMO_FALLOS_MODELO),
         "origen": "reglas-negocio §7, CP-012; encargo 17: con menos, el modelo sale con su coste y sin puesto, y el "
                   "resumen del ranking se calcula sin él"},
        {"nombre": "coste a igual edad",
         "valor": "amortización + tasa a igual edad / 100 × coste medio de un fallo del modelo × días de disco / 365 / "
                  "terabytes-año, con la tasa a igual edad del ranking de B2 de " + JSON_09,
         "origen": "encargo 17, B4.2; reglas §7, «Una tasa por modelo se compara a igual edad»"},
        {"nombre": "sensibilidad al precio inferido",
         "valor": "el precio de los modelos con origen «inferido» × " + " y × ".join(numero(x, 1) for x in FACTORES_PRECIO)
                  + "; cambia solo la amortización (el disco nuevo de un fallo sale de dim_precio_gb); con los modelos "
                    f"con puesto, cuántos de los {N_PRIMEROS} primeros siguen y cuál es el primero",
         "origen": "criterio técnico de Claude, en el encargo 17 (B4.3)"},
        {"nombre": "puesto del ranking de coste",
         "valor": ("dentro de cada capacidad y año de compra (el año de fecha_compra de dim_modelo), con CP-012; el "
                   "puesto de todos juntos, al lado, con su resumen"),
         "origen": "reglas-negocio §7 («El coste por TB y año se ordena dentro de cada capacidad y año de compra», Juan, "
                   "18/11/2026); encargo 19"},
        {"nombre": "tasa a igual edad del 09", "valor": "la de cada año de edad y trimestre, con φ (encargo 19)",
         "origen": "encargo 19; el script para si el JSON del 09 no trae φ"},
        {"nombre": "semilla", "valor": "no aplica", "origen": "ningún cálculo usa azar"},
    ]


def limites(res):
    """Los límites que salen de este cálculo, con sus cifras."""
    p = {q["id"]: q for q in res["preguntas"]}
    b4, b9 = p["B4"]["tablas"], p["B9"]["tablas"]
    inv = b9["invisibles"]
    return [
        "Las cifras describen el periodo del 01/01/2020 al 30/06/2025. Ninguna dice por qué un modelo cuesta más o por "
        "qué la previsión falla: solo valen verbos de asociación.",
        "El precio no está en los datos. Sale de la tabla de precios por capacidad y año de compra, inferida desde "
        f"2023, y {b4['resumen_ranking']['primeros_diez_inferidos']} de los diez primeros del ranking lo tienen "
        "inferido. El coste y el mejor modelo valen lo que valgan esos precios.",
        "Dos modelos de la misma capacidad comprados el mismo año tienen el mismo precio, así que entre ellos el orden "
        "lo pone solo la tasa de fallo.",
        f"{b4['resumen_ranking']['sin_puesto']} modelos tienen menos de {MINIMO_FALLOS_MODELO} fallos y salen sin puesto "
        "(CP-012); su coste está en la tabla, pero no se ordena.",
        "El coste a igual edad depende de la tasa a igual edad del 09: si el 09 cambia, este coste cambia con él. La "
        "sensibilidad al precio inferido solo mueve la amortización.",
        "La cifra con garantía usa la garantía de la ficha de cada fabricante y la edad al fallar por horas encendido; "
        "si Backblaze reclama la garantía no consta (CP-005).",
        "2025 tiene seis meses: su fila del mejor modelo no se compara con un año entero.",
        "El ingreso por TB es un orden de magnitud: la capacidad incluye paridad y espacio libre. El de 2025 necesita "
        "la reserva.",
        f"La previsión no ve {numero(inv['fallos'])} fallos de {numero(inv['de'])} ({pct(inv['pct'])}), de discos que "
        "entran después del primer día de su trimestre; es la regla de las reglas §7, y la referencia sí los cuenta.",
        "La sensibilidad es solo para leer: cambiar la regla de la tasa después de ver el resultado sería elegir la "
        "regla para que salga bien.",
        "Ninguna cifra se ha medido en la reserva, del 01/07/2025 al 30/06/2026 (reglas §5). La prueba final de la "
        "previsión usará la misma función, prever_trimestre, en esos cuatro trimestres.",
        "Pendiente: el auditor sin memoria del cierre del paso (skill §8) necesita el sí de Juan, porque es un agente.",
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
    j = {"skill": "indicadores-y-analisis", "version_skill": version_skill(raiz), "script": SCRIPT, "encargo": ENCARGO,
         "fecha_datos": FECHA_DATOS.isoformat(), "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
         "entradas": [], "resultado": {}, "pendientes": []}
    h_antes = huellas_raw(raiz)
    try:
        j["previos"] = comprobar_previos(raiz)
        j["entradas"] = comprobar_huellas(raiz)
        ingresos = leer_ingresos((raiz / DOC16).read_text(encoding="utf-8"))
        ie = leer_igual_edad(raiz)
        d = leer(raiz)
        d["ie"] = ie
        res = calcular(d, ingresos)
        res2 = calcular(d, ingresos)
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
            {"apartado": "42.1", "por_que": "elegir la función por la pregunta: ninguna del capítulo calcula un coste con "
                                            "averías ni prevé un recuento, y se usan la fórmula de las reglas y una cuenta"},
            {"apartado": "38.1", "por_que": "el objetivo de negocio, reducir costes y alargar la vida útil, da la decisión "
                                            "de cada bloque"},
            {"apartado": "11.10", "por_que": "ranking de coste con empates por el método «min»"},
            {"apartado": "13.6 y 13.7", "por_que": "consultas agrupadas por modelo y año, por año y capacidad y por "
                                                   "trimestre y capacidad"},
            {"apartado": "5.5", "por_que": "el coste del conjunto de discos es suma de costes entre suma de terabytes-año, "
                                           "no la media de los costes, y cada cifra va con su base"},
            {"apartado": "5.6", "por_que": "el ranking mezcla capacidades y años de compra; el mejor modelo se busca dentro "
                                           "de cada capacidad y año"},
            {"apartado": "4.5 y 4.7", "por_que": "intervalo al 95 % de la tasa; el mínimo de casos lo fijan las reglas "
                                                 "del caso, no el manual"},
            {"apartado": "4.11 y 4.12", "por_que": "no se contrastan proporciones: el intervalo de la tasa es el exacto "
                                                   "de Poisson, como en el encargo 13"},
            {"apartado": "31.9", "por_que": "la previsión se mide con el error absoluto ponderado y el sesgo aparte, "
                                            "frente a la referencia ingenua de repetir el periodo anterior"},
        ]
        j["datos_personales_texto"] = [
            ("Existe " + PROTECCION + ": lo que dice va en el informe de la protección." if (raiz / PROTECCION).exists()
             else f"No existe {PROTECCION}: los datos no pasaron por la protección, porque no traen datos de personas."),
            "No hay datos de personas (reglas-negocio §9): el número de serie identifica un disco, no a una persona.",
            "Este cálculo usa el número de serie solo para unir los fallos con la primera aparición de su disco y no "
            "deja ninguno en el JSON ni en el informe.",
        ]
        j["limites"] = limites(res)
        b9 = res["preguntas"][1]["tablas"]
        avisos = [x for q in res["preguntas"] for x in q["sin_conclusion"]]
        n_cifras = sum(len(q["cifras"]) for q in res["preguntas"])
        j["resultado"] = {
            "estado": "AVISO", "riesgo": "medio",
            "resumen": (f"Dos bloques calculados con {n_cifras} cifras, todas con su segunda vía, y las nueve "
                        f"validaciones en verde. {b9['error']['veredicto'][0].upper() + b9['error']['veredicto'][1:]}, "
                        f"con un error absoluto ponderado de {numero(b9['error']['cuenta']['wape'], 4)} frente a "
                        f"{numero(b9['error']['referencia']['wape'], 4)}. Quedan {len(avisos)} grupos sin conclusión "
                        "por el mínimo o por falta de precio, y el coste depende de precios inferidos."),
            "artefactos": [SALIDA_JSON, SALIDA_MD],
            "siguiente": ("bloques 5 a 8 del plan; el informe final y el cuadro de mando leen este JSON; antes, el "
                          "auditor sin memoria del paso con el sí de Juan")}
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
                          "siguiente": "corregir el fallo", "traza": traceback.format_exc()[-3000:]}
        codigo = 1
    j["ejecucion"] = {"python": sys.executable, "version_python": platform.python_version(), "pandas": pd.__version__,
                      "numpy": np.__version__, "scipy": scipy.__version__, "pyarrow": pa.__version__,
                      "duracion_s": round(time.time() - inicio, 1)}
    tj, tm = textos(j)
    escribir(raiz, tj, tm)
    print(f"{j['resultado']['estado']}: {j['resultado']['resumen']}")
    return codigo


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raiz", default=str(CASO), help="carpeta del caso (por defecto, la de este script)")
    sys.exit(principal(Path(ap.parse_args().raiz).resolve()))
