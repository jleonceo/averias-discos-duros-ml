"""Indicadores de los bloques 1, 2 y 3 del plan de la analítica del caso 68: el conjunto de discos, los modelos y la edad.

Método indicadores-y-analisis (paso 5, parte sin modelo), con la petición peticiones/13_indicadores_discos_modelos_edad.md.
Calcula, comprueba y deja en informes/indicadores__discos_modelos_edad.json (y su informe .md, generado del mismo
diccionario en la misma ejecución):

  - B1, el conjunto de discos: discos y petabytes el día 1 de cada mes (total, por capacidad y por fabricante); altas y bajas por
    trimestre; los diez modelos con más discos de cada año; los días de disco por centro y año desde julio de 2023.
  - B2, los modelos: tasa anual de fallo por modelo con los años que pasan el mínimo, frente al conjunto de discos de las mismas
    celdas; la tabla de modelo por año; la tasa por fabricante y por capacidad con la edad media al lado. Desde el
    petición 17 (peticiones/17_correcciones_del_auditor.md), cada modelo se compara además a igual edad (razón de
    observados entre esperados con la tasa de cada año de edad), el ranking se ordena por esa razón, un modelo con menos
    de 20 fallos sale sin puesto (cuestión 012) y se mide si los veredictos aguantan al quitar cada modelo o el año parcial.
  - B3, la edad: tasa por año de edad (todos los discos, fabricantes y los cinco modelos con más días), con «sube» frente al año
    anterior; la supervivencia por tabla de vida; los discos de 8 años o más.

Cada cifra lleva su segunda vía, que parte de otra tabla (recuento_diario_corregido, fotos y ventanas corregidas,
fallos_detalle o dias_por_tramo). Si una no coincide, para con ERROR. Las comprobaciones y las validaciones de el método
se calculan; ninguna lleva el resultado escrito.

Lee data/processed/ (sin fotos_riesgo) y los JSON de informes/ de la transformación y del exploratorio, que no
modifica. Depende de scripts/05_transformacion_datos.py y de 06_analisis_exploratorio.py: comprueba la huella de cada
tabla contra informes/transformacion-datos.json y el estado de los cuatro exploratorios. No importa ningún script.

Uso: python -W error scripts/09_indicadores_discos_modelos_edad.py [--raiz CARPETA_DEL_CASO]
Sale con 0 si termina, con 2 si para (PARADO o ERROR) y con 1 si falla por otra causa; en los tres casos escribe el JSON.
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
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
import pyarrow.parquet as pq
import scipy
from scipy import stats

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "assets"))
from graficos import numero  # noqa: E402  (pieza común: números a la española, redondeo como Excel)

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SCRIPT = "scripts/09_indicadores_discos_modelos_edad.py"
PETICION = ("peticiones/13_indicadores_discos_modelos_edad.md; B2 cambiado por "
           "peticiones/17_correcciones_del_auditor.md; B2 y B3, por "
           "peticiones/19_correcciones_del_segundo_auditor.md")
SALIDA_JSON = "informes/indicadores__discos_modelos_edad.json"
SALIDA_MD = "informes/indicadores__discos_modelos_edad.md"
TRANSFORMACION = "informes/transformacion-datos.json"
METODO_MD = "metodos/indicadores-y-analisis/METODO.md"
PROTECCION = "config/fuentes/proteccion-datos.json"
# Los cuatro exploratorios de las tablas que lee la petición; si uno está en PARADO o ERROR, no se calcula nada
EXPLORATORIOS = ["modelo_trimestre", "dias_por_tramo", "vida_discos", "centro_mes"]
# Tablas salidas de la transformación y tablas de entrada de la transformación (las corregidas y el calendario)
TABLAS_SALIDA = ["dim_modelo", "modelo_trimestre", "dias_por_tramo", "vida_discos", "fallos_detalle", "centro_mes",
                 "inicio_trimestre"]
TABLAS_ENTRADA = ["recuento_diario_corregido", "fotos_mensuales_corregido", "ventanas_fallo_corregido", "calendario"]

# Fecha de referencia de los datos (reglas, apartado 5) y primer día con centro de datos (reglas, apartado 4)
FECHA_DATOS = dt.date(2025, 6, 30)
PRIMER_DIA_SITIO = pd.Timestamp(2023, 7, 1)
# Mínimo para entrar en un ranking: días de disco del modelo en el año (reglas, apartado 7)
MINIMO_DIAS_ANO = 50_000
# Un año de edad con menos fallos que esto no saca conclusión (reglas, apartado 7, cuestión 009)
MINIMO_FALLOS_EDAD = 20
# Un modelo con menos fallos que esto en sus años que pasan el mínimo sale sin puesto y sin conclusión (reglas, apartado 7, cuestión 012)
MINIMO_FALLOS_MODELO = 20
# Los veredictos a igual edad, en el orden en que se cuentan (petición 17)
VEREDICTOS = ["por encima", "por debajo", "no se distingue", "sin conclusión"]
# Confianza de los intervalos (método, parametros.md; 42.6 del manual)
CONFIANZA = 0.95
# Años de edad de la tasa y de la supervivencia (reglas de transformación §6: de 0 a 10)
EDADES = list(range(11))
# Supervivencia a estos años (plan, bloque 3)
ANOS_S = [1, 3, 5]
# Diferencia máxima entre las dos vías de la supervivencia, en puntos (petición, «SEGUNDA VÍA»)
TOLERANCIA_S_PUNTOS = 0.5
# Cuántos modelos por año en B1 y cuántos modelos en B3 (plan, bloques 1 y 3; petición)
N_TOP = 10
N_MODELOS_EDAD = 5
# Edad desde la que un disco es «de 8 años o más» (plan, bloque 3)
EDAD_VIEJOS = 8
# Días de un año para pasar fallos por día de disco a tasa anual en %: 100 × 365 (reglas, apartado 6)
FACTOR_TASA = 100 * 365

COMPROBACIONES = ["unidad", "minimo", "empates", "referencia", "azar_en_grupos", "pesos", "hacia_adelante",
                  "cobertura", "periodos"]
VALIDACIONES = ["planteamiento_completo", "cifras_con_poblacion", "segunda_via", "minimo_respetado",
                "con_referencia", "comprobaciones_calculadas", "reproducible", "sin_resultados_escritos",
                "raw_intacto"]
# Comprobaciones de la petición 17, aparte de las nueve de el método
EXTRAS = ["veredicto_del_intervalo", "esperados_suman_observados", "phi_minimo_uno"]
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


def etiqueta_trimestre(fechas):
    """«2024T1» para cada fecha de una serie."""
    return fechas.dt.year.astype(str) + "T" + fechas.dt.quarter.astype(str)


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
# 4. Estadística
# =================================================================================================================
def intervalo_poisson(fallos, dias, confianza=CONFIANZA, phi=1.0):
    """Tasa anual en % y su intervalo exacto de Poisson (con chi2), pasados a tasa con los mismos días de disco.

    Inferior chi2.ppf(α/2; 2f)/2, 0 si f = 0; superior chi2.ppf(1 − α/2; 2f + 2)/2 (criterio técnico, petición).
    Con φ (petición 19, reglas, apartado 7), los fallos y los días se dividen entre φ: la tasa no cambia y el intervalo se ensancha.
    """
    a = 1 - confianza
    f = int(fallos)
    fp, dp = f / phi, float(dias) / phi
    lo = 0.0 if f == 0 else stats.chi2.ppf(a / 2, 2 * fp) / 2
    hi = stats.chi2.ppf(1 - a / 2, 2 * fp + 2) / 2
    # Con φ = 1, dp son los mismos días y la cuenta es la de antes, cifra a cifra
    k = FACTOR_TASA / dp
    return f * (FACTOR_TASA / float(dias)), float(lo) * k, float(hi) * k


def razon_poisson(observados, esperados, confianza=CONFIANZA, phi=1.0):
    """Razón observados / esperados y el intervalo exacto de Poisson de los observados dividido por los esperados.

    El mismo método que la tasa ajustada por centro del bloque 5 (petición 15, criterio 1), con el año de edad en lugar
    del modelo (petición 17). Con φ (petición 19), observados y esperados entre φ: la razón no cambia.
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
    φ = chi2 / gl, y si sale menor que 1, vale 1. Devuelve φ, el φ medido, chi2, celdas, grupos, gl y las celdas que
    quedaron fuera por no tener esperados (con sus fallos).
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
    """φ de B3 y del minicubo (petición 19): celdas de modelo × año de edad × trimestre de dias_por_tramo, con el
    esperado de cada una = sus días × la tasa de su modelo y año de edad en todo el periodo; grupo, modelo y año de
    edad. Una fila sin días cuenta 0 días y sus fallos."""
    d = dpt.assign(dias=dpt["dias_disco"].fillna(0.0), q=dpt["mes"].dt.year * 10 + dpt["mes"].dt.quarter)
    g = d.groupby(["model", "edad_anos_cumplidos"])[["dias", "fallos"]].transform("sum")
    tasa = (g["fallos"] / g["dias"].where(g["dias"] > 0)).fillna(0.0)
    grupo = list(zip(d["model"], d["edad_anos_cumplidos"]))
    return phi_poisson(grupo, d["q"].tolist(), d["fallos"], d["dias"] * tasa)


def veredicto_razon(desde, hasta, fallos, minimo=MINIMO_FALLOS_MODELO):
    """Veredicto a igual edad (petición 17): «sin conclusión» con menos de `minimo` fallos (cuestión 012) o sin intervalo;
    «por encima» si el intervalo de la razón queda entero por encima de 1, «por debajo» si queda entero por debajo y «no
    se distingue» en los demás."""
    if fallos < minimo or desde is None or hasta is None:
        return "sin conclusión"
    if desde > 1:
        return "por encima"
    if hasta < 1:
        return "por debajo"
    return "no se distingue"


def spearman(a, b):
    """Correlación de orden de Spearman; None con menos de dos pares o con una lista constante, donde no se define."""
    if len(a) < 2 or len(set(a)) < 2 or len(set(b)) < 2:
        return None
    return float(stats.spearmanr(a, b).statistic)


def tabla_de_vida(edad_entrada, edad_fin, es_evento, edades=EDADES):
    """Exposición en años, eventos y tasa por año de edad, con entrada tardía (petición, B3.2).

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
    """Corta la curva antes del primer año de edad con menos de `minimo` fallos (cuestión 009).

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


def frente_al_anterior(filas, minimo, phi=1.0):
    """Tasa, intervalo y si sube o baja frente al año anterior; sin conclusión si alguno tiene menos de `minimo` fallos.

    «Sube» si el intervalo del año no se solapa con el del anterior por arriba (reglas, apartado 7); «baja», lo mismo por abajo.
    El intervalo lleva el φ de B3 (petición 19).
    """
    out, prev = [], None
    for f in filas:
        g = dict(f)
        if g["dias_disco"] > 0:
            g["tasa"], g["desde"], g["hasta"] = intervalo_poisson(g["fallos"], g["dias_disco"], phi=phi)
        else:
            g["tasa"], g["desde"], g["hasta"] = None, None, None
        g["sin_conclusion"] = bool(g["fallos"] < minimo)
        g["fallos_anterior"] = prev["fallos"] if prev is not None else None
        comparable = (prev is not None and not g["sin_conclusion"] and not prev["sin_conclusion"]
                      and g["tasa"] is not None and prev["tasa"] is not None)
        g["sube"] = bool(g["desde"] > prev["hasta"]) if comparable else None
        g["baja"] = bool(g["hasta"] < prev["desde"]) if comparable else None
        out.append(g)
        prev = g
    return out


# =================================================================================================================
# 5. Comprobaciones (método §4): cada una devuelve True o False calculado con lo ejecutado
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


def comp_minimo_edad(filas, minimo, curvas=None):
    """Ninguna conclusión («sube», «baja») sale de un año con menos de `minimo` fallos, ni ninguna S tras el corte."""
    for f in filas:
        if f.get("sube") is not None or f.get("baja") is not None:
            if f["fallos"] < minimo or f["fallos_anterior"] is None or f["fallos_anterior"] < minimo:
                return False
    for s, eventos in curvas or []:
        for k, v in enumerate(s):
            if v is not None and k >= 1 and any(eventos[i] < minimo for i in range(min(k, len(eventos)))):
                return False
    return True


def comp_referencia(dias_grupos, fallos_grupos, dias_ref, fallos_ref):
    """La referencia se calcula con las mismas filas que los grupos: las sumas coinciden."""
    return (math.isclose(float(sum(dias_grupos)), float(dias_ref), rel_tol=1e-12, abs_tol=1e-6)
            and int(sum(fallos_grupos)) == int(fallos_ref))


def comp_azar(grupos, esperados, confianza):
    """Cada grupo tiene su intervalo y los esperados por azar son la parte de los grupos que da la confianza (42.6)."""
    con_intervalo = all(g.get("desde") is not None and g.get("hasta") is not None for g in grupos)
    return con_intervalo and esperados == round(len(grupos) * (1 - confianza), 1)


def comp_partes_total(partes, totales):
    """Cada lista de partes suma su total."""
    return all(math.isclose(float(sum(p)), float(t), rel_tol=1e-12, abs_tol=1e-6) for p, t in zip(partes, totales))


def comp_cuadre_discos(altas, fallo, desaparece, sigue, discos):
    """Altas = discos, y fallo + desaparece + sigue = discos."""
    return altas == discos and fallo + desaparece + sigue == discos


def comp_periodos(filas, clave, parciales, campo="parcial"):
    """Cada fila de un periodo incompleto lleva su marca, y las de un periodo completo no."""
    return all(bool(f[campo]) == (f[clave] in parciales) for f in filas)


def comp_cobertura(parte):
    """La parte cubierta está calculada y entre 0 y 1."""
    return parte is not None and 0 < parte <= 1 + 1e-12


def comp_puesto_minimo(filas, minimo):
    """Ningún modelo con menos de `minimo` fallos lleva puesto, y los demás sí (reglas, apartado 7, cuestión 012)."""
    return all((f["puesto"] is None) == (f["fallos"] < minimo) for f in filas)


def comp_veredicto_intervalo(filas, minimo, phi=1.0, confianza=CONFIANZA):
    """El veredicto a igual edad de cada modelo es el que dice el intervalo de su razón con φ (peticiones 17 y 19).

    Se rehace aquí con su propia cuenta, con la gamma y sin llamar a razon_poisson ni a veredicto_razon: el intervalo de
    los observados entre φ dividido por los esperados entre φ; entero por encima de 1, «por encima»; entero por debajo,
    «por debajo»; si no, «no se distingue»; con menos de `minimo` fallos o sin intervalo, «sin conclusión». Una fila sin
    observados ni esperados se lee con el intervalo que trae.
    """
    a = 1 - confianza
    for f in filas:
        o, e = f.get("observados"), f.get("esperados")
        if o is not None and e:
            op, ep = o / phi, e / phi
            lo = stats.gamma.ppf(a / 2, op) / ep if o > 0 else 0.0
            hi = stats.gamma.ppf(1 - a / 2, op + 1) / ep
        else:
            lo, hi = f.get("razon_desde"), f.get("razon_hasta")
        if f["fallos"] < minimo or lo is None or hi is None:
            debe = "sin conclusión"
        else:
            debe = "por encima" if lo > 1 else ("por debajo" if hi < 1 else "no se distingue")
        if f.get("veredicto") != debe:
            return False
    return True


def comp_phi(registros):
    """Cada φ usado es el medido, y nunca menor que 1: si el medido sale por debajo de 1, se usa 1 (petición 19)."""
    for x in registros:
        bruto = x.get("phi_bruto")
        debe = 1.0 if bruto is None else max(1.0, bruto)
        if x.get("phi") is None or x["phi"] < 1 or not math.isclose(x["phi"], debe, rel_tol=1e-12):
            return False
    return True


# =================================================================================================================
# 6. Entradas: estado de la fase anterior, huellas y lectura
# =================================================================================================================
def comprobar_exploratorios(raiz):
    """Para con PARADO si falta un exploratorio o su estado es PARADO o ERROR (método, «Al empezar»)."""
    estados = {}
    for t in EXPLORATORIOS:
        ruta = raiz / "informes" / f"analisis-exploratorio__{t}.json"
        if not ruta.exists():
            raise Parada("PARADO", f"falta informes/analisis-exploratorio__{t}.json")
        estado = json.loads(ruta.read_text(encoding="utf-8"))["resultado"]["estado"]
        estados[t] = estado
        if estado in ("PARADO", "ERROR"):
            raise Parada("PARADO", f"el exploratorio de {t} está en {estado}")
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
    return entradas


def leer(raiz):
    """Lee solo las columnas que usan los tres bloques; fechas en milisegundos; discos de datos marcados."""
    p = raiz / "data" / "processed"
    d = {}
    d["dm"] = pd.read_parquet(p / "dim_modelo.parquet", columns=["model", "capacidad_tb", "tipo_disco", "fabricante"])
    d["cal"] = pd.read_parquet(p / "calendario.parquet", columns=["fecha", "ano"])
    d["rec"] = pd.read_parquet(p / "recuento_diario_corregido.parquet",
                               columns=["fecha", "model", "datacenter", "discos", "fallos"])
    d["mt"] = pd.read_parquet(p / "modelo_trimestre.parquet",
                              columns=["model", "ano", "trimestre", "capacidad_tb", "fabricante", "dias_disco",
                                       "fallos", "dias_disco_ano", "pasa_minimo_ano"])
    d["dpt"] = pd.read_parquet(p / "dias_por_tramo.parquet",
                               columns=["model", "centro", "mes", "edad_anos_cumplidos", "fotos", "dias_disco",
                                        "fallos", "desaparecen_avisando"])
    d["vida"] = pd.read_parquet(p / "vida_discos.parquet",
                                columns=["serial_number", "model", "primera_aparicion", "edad_entrada_anos",
                                         "ultima_foto", "evento", "edad_fin_anos", "desaparece_avisando"])
    d["fd"] = pd.read_parquet(p / "fallos_detalle.parquet",
                              columns=["serial_number", "dia_fallo", "model", "tipo_disco", "edad_al_fallar_anos"])
    d["cm"] = pd.read_parquet(p / "centro_mes.parquet", columns=["datacenter", "mes", "dias_disco", "fallos"])
    d["it"] = pd.read_parquet(p / "inicio_trimestre.parquet",
                              columns=["ano", "trimestre", "model", "edad_anos_cumplidos", "discos"])
    d["fo"] = pd.read_parquet(p / "fotos_mensuales_corregido.parquet", columns=["fecha", "serial_number", "model"])
    d["ve"] = pd.read_parquet(p / "ventanas_fallo_corregido.parquet", columns=["fecha", "serial_number", "model"])
    # Fechas, todas en milisegundos (dias_por_tramo llega en microsegundos)
    for t, cols in {"cal": ["fecha"], "rec": ["fecha"], "dpt": ["mes"], "vida": ["primera_aparicion", "ultima_foto"],
                    "fd": ["dia_fallo"], "cm": ["mes"], "fo": ["fecha"], "ve": ["fecha"]}.items():
        for c in cols:
            d[t][c] = a_ms(d[t][c])
    # Discos de datos: la población de todo la petición (reglas, apartado 3 y §7)
    datos = set(d["dm"].loc[d["dm"]["tipo_disco"] == "datos", "model"])
    if not set(d["mt"]["model"]) <= datos or not set(d["dpt"]["model"]) <= datos or not set(d["vida"]["model"]) <= datos:
        raise Parada("ERROR", "modelo_trimestre, dias_por_tramo o vida_discos traen un modelo que no es de datos")
    d["datos"] = datos
    d["rec_d"] = d["rec"].loc[d["rec"]["model"].isin(datos)].copy()
    d["fd_d"] = d["fd"].loc[d["fd"]["tipo_disco"] == "datos"].copy()
    d["dmd"] = d["dm"].loc[d["dm"]["tipo_disco"] == "datos"].copy()
    return d


def calendario(cal):
    """Días de cada año en los datos, años parciales y la lista ordenada de trimestres («2020T1» …)."""
    dias_ano = cal.groupby("ano")["fecha"].size()
    parciales = {int(a) for a, n in dias_ano.items()
                 if n < (dt.date(int(a), 12, 31) - dt.date(int(a), 1, 1)).days + 1}
    trimestres = list(dict.fromkeys(etiqueta_trimestre(cal.sort_values("fecha")["fecha"])))
    meses = sorted(cal.loc[cal["fecha"].dt.day == 1, "fecha"].unique())
    return {"dias_ano": {int(a): int(n) for a, n in dias_ano.items()}, "parciales": parciales,
            "trimestres": trimestres, "meses": [pd.Timestamp(m) for m in meses]}


def periodo_ano(ano, cal_info):
    """El periodo de un año en palabras: el año natural o, si es parcial, sus fechas."""
    if ano in cal_info["parciales"]:
        return f"del {ano}-01-01 al {FECHA_DATOS.isoformat()} ({cal_info['dias_ano'][ano]} días)"
    return f"año {ano}"


# =================================================================================================================
# 7. Bloque 1 · El conjunto de discos
# =================================================================================================================
def b1_serie_mensual(rec_d, dmd, meses):
    """Discos y PB el día 1 de cada mes: total, por capacidad y por fabricante (capacidad del modelo, dim_modelo)."""
    d1 = rec_d.loc[rec_d["fecha"].dt.day == 1].merge(dmd[["model", "capacidad_tb", "fabricante"]], on="model",
                                                     how="left", validate="many_to_one")
    d1 = d1.assign(tb=d1["discos"] * d1["capacidad_tb"])
    total = d1.groupby("fecha").agg(discos=("discos", "sum"), tb=("tb", "sum")).reindex(meses)
    if total["discos"].isna().any():
        raise Parada("ERROR", "falta el día 1 de algún mes en el recuento")
    cap = d1.groupby(["fecha", "capacidad_tb"]).agg(discos=("discos", "sum"), tb=("tb", "sum")).reset_index()
    fab = d1.groupby(["fecha", "fabricante"]).agg(discos=("discos", "sum"), tb=("tb", "sum")).reset_index()
    serie = [{"mes": iso(m), "discos": int(t["discos"]), "pb": r(t["tb"] / 1000)} for m, t in total.iterrows()]
    por_cap = [{"mes": iso(x["fecha"]), "capacidad_tb": r(x["capacidad_tb"], 1), "discos": int(x["discos"]),
                "pb": r(x["tb"] / 1000)} for _, x in cap.iterrows()]
    por_fab = [{"mes": iso(x["fecha"]), "fabricante": x["fabricante"], "discos": int(x["discos"]),
                "pb": r(x["tb"] / 1000)} for _, x in fab.iterrows()]
    # Comprobación: cada mes, las capacidades y los fabricantes suman el total
    partes = ([cap.loc[cap["fecha"] == m, "discos"].tolist() for m in meses]
              + [fab.loc[fab["fecha"] == m, "discos"].tolist() for m in meses])
    totales = [int(total.loc[m, "discos"]) for m in meses] * 2
    return serie, por_cap, por_fab, comp_partes_total(partes, totales)


def b1_altas_bajas(vida, fd_d, trimestres, ultima_foto_datos):
    """Altas por trimestre (sin el primero, que arrastra lo anterior) y bajas: fallos y desaparecen sin fallo."""
    altas = etiqueta_trimestre(vida["primera_aparicion"]).value_counts()
    fallos = etiqueta_trimestre(fd_d["dia_fallo"]).value_counts()
    des = etiqueta_trimestre(vida.loc[vida["evento"] == "desaparece", "ultima_foto"]).value_counts()
    # El trimestre de la última foto de los datos: los que se van en su último mes no se pueden saber
    trim_incompleto = etiqueta_trimestre(pd.Series([ultima_foto_datos])).iloc[0]
    filas_altas = [{"trimestre": q, "altas": int(altas.get(q, 0))} for q in trimestres[1:]]
    filas_bajas = [{"trimestre": q, "fallos": int(fallos.get(q, 0)), "desaparecen": int(des.get(q, 0)),
                    "incompleto": q == trim_incompleto} for q in trimestres]
    eventos = vida["evento"].value_counts()
    cuadre = {"discos": int(len(vida)), "altas_con_el_primer_trimestre": int(altas.sum()),
              "altas_primer_trimestre_con_lo_anterior": int(altas.get(trimestres[0], 0)),
              "acaban_en_fallo": int(eventos.get("fallo", 0)), "desaparecen": int(eventos.get("desaparece", 0)),
              "siguen": int(eventos.get("sigue", 0)), "fallos_de_la_serie": int(fallos.sum()),
              "fallos_que_no_son_el_primero_del_disco": int(fallos.sum() - eventos.get("fallo", 0)),
              "trimestre_incompleto": trim_incompleto, "ultima_foto_de_los_datos": iso(ultima_foto_datos)}
    return filas_altas, filas_bajas, cuadre


def celdas_modelo_ano(dias_fallos):
    """Días y fallos por modelo y año desde una tabla con model, ano, dias y fallos."""
    return (dias_fallos.groupby(["model", "ano"]).agg(dias_disco=("dias", "sum"), fallos=("fallos", "sum"))
            .reset_index().sort_values(["model", "ano"], kind="mergesort").reset_index(drop=True))


def b1_top10(celdas, cal_info, primeros_ultimos):
    """Los diez modelos con más discos medios de cada año (días del año / días del año en los datos).

    Solo entran los modelos que pasan el mínimo de días ese año (reglas, apartado 7; consultas §11, filtrar antes de ordenar).
    """
    c = celdas.loc[celdas["pasa"]]
    c = c.assign(dias_en_datos=c["ano"].map(cal_info["dias_ano"]))
    c = c.assign(discos_medios=c["dias_disco"] / c["dias_en_datos"])
    c["puesto"] = c.groupby("ano")["discos_medios"].rank(method="min", ascending=False).astype(int)
    top = c.loc[c["puesto"] <= N_TOP].sort_values(["ano", "puesto", "model"], kind="mergesort")
    filas = []
    for _, x in top.iterrows():
        pu = primeros_ultimos.get(x["model"], (None, None))
        filas.append({"ano": int(x["ano"]), "puesto": int(x["puesto"]), "model": x["model"],
                      "discos_medios": r(x["discos_medios"]), "dias_disco_ano": int(x["dias_disco"]),
                      "dias_del_ano_en_datos": int(x["dias_en_datos"]), "pasa_minimo": bool(x["pasa"]),
                      "primer_trimestre": pu[0], "ultimo_trimestre": pu[1],
                      "parcial": int(x["ano"]) in cal_info["parciales"]})
    return filas, c


def b1_centros(cm):
    """Días de disco por centro y año desde el 01/07/2023, con «sin dato» aparte y la parte de cada centro."""
    c = cm.loc[cm["mes"] >= PRIMER_DIA_SITIO]
    c = c.assign(ano=c["mes"].dt.year)
    g = c.groupby(["ano", "datacenter"])["dias_disco"].sum().reset_index()
    tot = g.groupby("ano")["dias_disco"].sum()
    meses = c.groupby("ano")["mes"].agg(["min", "max"])
    filas = []
    for _, x in g.sort_values(["ano", "datacenter"], kind="mergesort").iterrows():
        a = int(x["ano"])
        desde, hasta = meses.loc[a, "min"], meses.loc[a, "max"]
        parcial = desde.month != 1 or hasta.month != 12
        fin = dt.date(a, 12, 31) if not parcial else (FECHA_DATOS if a == FECHA_DATOS.year else dt.date(a, 12, 31))
        filas.append({"ano": a, "centro": x["datacenter"], "sin_dato": x["datacenter"] == "sin dato",
                      "dias_disco": int(x["dias_disco"]), "pct_del_ano": r(100 * x["dias_disco"] / tot[a]),
                      "parcial": bool(parcial), "periodo": f"del {iso(desde)} al {fin.isoformat()}"})
    partes = [[f["pct_del_ano"] for f in filas if f["ano"] == a] for a in tot.index]
    suma_100 = all(math.isclose(sum(p), 100.0, abs_tol=1e-3) for p in partes)
    return filas, suma_100


# =================================================================================================================
# 8. Bloque 2 · Qué modelos fallan más
# =================================================================================================================
def b2_ranking(celdas):
    """Tasa por modelo con los años que pasan el mínimo, de menor a mayor, frente al conjunto de discos de las mismas celdas."""
    pasan = celdas.loc[celdas["pasa"]]
    g = pasan.groupby("model").agg(dias_disco=("dias_disco", "sum"), fallos=("fallos", "sum")).reset_index()
    anos = {m: sorted(int(a) for a in s) for m, s in pasan.groupby("model")["ano"]}
    g["anos"] = g["model"].map(anos)
    ref_dias, ref_fallos = int(pasan["dias_disco"].sum()), int(pasan["fallos"].sum())
    ref = intervalo_poisson(ref_fallos, ref_dias)
    filas = []
    for _, x in g.iterrows():
        t, lo, hi = intervalo_poisson(x["fallos"], x["dias_disco"])
        frente = "por encima" if lo > ref[0] else "por debajo" if hi < ref[0] else "no se distingue"
        filas.append({"model": x["model"], "dias_disco": int(x["dias_disco"]), "fallos": int(x["fallos"]),
                      "tasa": t, "desde": lo, "hasta": hi, "anos_que_pasan": x["anos"],
                      "frente_a_todos": frente, "distinto": frente != "no se distingue"})
    filas.sort(key=lambda f: (f["tasa"], f["model"]))
    puestos = pd.Series([f["tasa"] for f in filas]).rank(method="min").astype(int).tolist()
    for f, p in zip(filas, puestos):
        f["puesto"] = p
    fuera = celdas.loc[~celdas["pasa"]]
    en_ranking = set(g["model"])
    modelos_fuera = (celdas.loc[~celdas["model"].isin(en_ranking)].groupby("model")
                     .agg(dias_disco=("dias_disco", "sum"), fallos=("fallos", "sum")).reset_index())
    resumen_fuera = {"celdas": int(len(fuera)), "dias_disco": int(fuera["dias_disco"].sum()),
                     "fallos": int(fuera["fallos"].sum()), "modelos_sin_ningun_ano": int(len(modelos_fuera)),
                     "modelos": [{"model": m["model"], "dias_disco": int(m["dias_disco"]), "fallos": int(m["fallos"])}
                                 for _, m in modelos_fuera.sort_values("model", kind="mergesort").iterrows()]}
    referencia = {"dias_disco": ref_dias, "fallos": ref_fallos, "tasa": ref[0], "desde": ref[1], "hasta": ref[2]}
    return filas, referencia, resumen_fuera


def b2_mapa(celdas, parciales):
    """Tabla de modelo por año: tasa e intervalo en las celdas que pasan; null con su recuento en las demás."""
    filas = []
    for _, x in celdas.iterrows():
        t = intervalo_poisson(x["fallos"], x["dias_disco"]) if x["pasa"] else (None, None, None)
        filas.append({"model": x["model"], "ano": int(x["ano"]), "dias_disco": int(x["dias_disco"]),
                      "fallos": int(x["fallos"]), "pasa_minimo": bool(x["pasa"]), "tasa": t[0], "desde": t[1],
                      "hasta": t[2], "parcial": int(x["ano"]) in parciales})
    return filas


def b2_grupos(dias_fallos, dpt_grupo, clave, ref):
    """Tasa por fabricante o por capacidad con todos sus discos, edad media de sus días de disco y frente al conjunto de discos."""
    g = dias_fallos.groupby(clave).agg(dias_disco=("dias", "sum"), fallos=("fallos", "sum")).reset_index()
    e = dpt_grupo.assign(pond=(dpt_grupo["edad_anos_cumplidos"] + 0.5) * dpt_grupo["dias_disco"])
    e = e.groupby(clave).agg(pond=("pond", "sum"), dias=("dias_disco", "sum"))
    filas = []
    for _, x in g.sort_values(clave, kind="mergesort").iterrows():
        t, lo, hi = intervalo_poisson(x["fallos"], x["dias_disco"])
        frente = "por encima" if lo > ref else "por debajo" if hi < ref else "no se distingue"
        k = x[clave]
        edad = e.loc[k, "pond"] / e.loc[k, "dias"] if k in e.index and e.loc[k, "dias"] > 0 else None
        filas.append({"grupo": k if clave == "fabricante" else r(k, 1), "dias_disco": int(x["dias_disco"]),
                      "fallos": int(x["fallos"]), "tasa": t, "desde": lo, "hasta": hi, "edad_media_anos": edad,
                      "frente_a_todos": frente})
    return filas


# -----------------------------------------------------------------------------------------------------------------
# 8.1 Bloque 2 a igual edad (petición 17; reglas, apartado 7, «Una tasa por modelo se compara a igual edad» y cuestión 012)
# -----------------------------------------------------------------------------------------------------------------
def celdas_que_pasan(dpt, celdas):
    """Filas de dias_por_tramo (modelo, mes, centro y año de edad) cuyo modelo y año de calendario pasan el mínimo.

    La marca es la de las celdas de modelo y año (pasa_minimo_ano de modelo_trimestre, o su segunda vía). Una fila sin
    días (solo trae fallos, reglas de transformación §6) cuenta 0 días y sus fallos.
    """
    pasan = celdas.loc[celdas["pasa"]]
    clave = pd.MultiIndex.from_arrays([pasan["model"], pasan["ano"].astype("int64")])
    # El trimestre de calendario de cada fila, como año × 10 + trimestre, para la tasa de edad y trimestre (petición 19)
    d = dpt.assign(ano=dpt["mes"].dt.year.astype("int64"), dias=dpt["dias_disco"].fillna(0.0),
                   trimestre=(dpt["mes"].dt.year * 10 + dpt["mes"].dt.quarter).astype("int64"))
    return d.loc[pd.MultiIndex.from_arrays([d["model"], d["ano"]]).isin(clave)].copy()


def igual_edad(c, minimo=MINIMO_FALLOS_MODELO, por_trimestre=True, con_phi=True):
    """La razón a igual edad y en el mismo trimestre de cada modelo con las celdas `c` (peticiones 17 y 19).

    Tasa de cada año de edad y trimestre de calendario = fallos / días de las celdas, con todos los modelos juntos;
    esperados de un modelo = suma de sus días × la tasa de su año de edad y su trimestre; razón = observados /
    esperados con el intervalo exacto de Poisson entre φ; tasa a igual edad = razón × tasa de todas las celdas. φ se
    mide en las celdas de modelo × trimestre con esos esperados, con el modelo como grupo (reglas, apartado 7). Con
    `por_trimestre` y `con_phi` en falso, el método de la petición 17 (solo la edad y sin φ), que se da al lado.
    """
    clave = ["edad_anos_cumplidos", "trimestre"] if por_trimestre else ["edad_anos_cumplidos"]
    por_clave = c.groupby(clave).agg(d=("dias", "sum"), f=("fallos", "sum"))
    tasa_dia = (por_clave["f"] / por_clave["d"]).where(por_clave["d"] > 0).rename("tasa_dia")
    esp = (c["dias"] * c.join(tasa_dia, on=clave)["tasa_dia"]).fillna(0.0)
    ph = phi_poisson(c["model"].tolist(), c["trimestre"].tolist(), c["fallos"], esp) if con_phi else None
    phi = ph["phi"] if ph is not None else 1.0
    g = (c.assign(esp=esp, pond=(c["edad_anos_cumplidos"] + 0.5) * c["dias"]).groupby("model")
         .agg(observados=("fallos", "sum"), esperados=("esp", "sum"), dias=("dias", "sum"), pond=("pond", "sum")))
    dias_t, fallos_t = float(c["dias"].sum()), int(c["fallos"].sum())
    tasa_todos = FACTOR_TASA * fallos_t / dias_t if dias_t > 0 else None
    modelos = {}
    for m, x in g.iterrows():
        o, e = int(x["observados"]), float(x["esperados"])
        rz, lo, hi = razon_poisson(o, e, phi=phi) if e > 0 else (None, None, None)
        modelos[m] = {"observados": o, "esperados": e, "dias_igual_edad": float(x["dias"]), "razon": rz,
                      "razon_desde": lo, "razon_hasta": hi,
                      "tasa_igual_edad": rz * tasa_todos if rz is not None and tasa_todos is not None else None,
                      "edad_media_anos": float(x["pond"]) / float(x["dias"]) if x["dias"] > 0 else None,
                      "veredicto": veredicto_razon(lo, hi, o, minimo)}
    # La tasa de cada año de edad, con todos sus trimestres juntos, para leerla en el informe
    por_edad = c.groupby("edad_anos_cumplidos").agg(d=("dias", "sum"), f=("fallos", "sum"))
    tasas = [{"edad": int(e), "dias_disco": float(x["d"]), "fallos": int(x["f"]),
              "tasa": FACTOR_TASA * float(x["f"]) / float(x["d"]) if x["d"] > 0 else None} for e, x in por_edad.iterrows()]
    return {"modelos": modelos, "por_edad": tasas, "dias": dias_t, "fallos": fallos_t, "tasa_todos": tasa_todos,
            "celdas": int(len(c)), "celdas_edad_trimestre": int(len(por_clave)), "phi": ph}


def igual_edad_bucle(modelos, edades, dias, fallos, trimestres=None):
    """La misma cuenta fila a fila, con diccionarios y sin pandas (segunda vía, otro cálculo).

    La tasa es la de cada año de edad y trimestre (petición 19); sin `trimestres`, la de cada año de edad. Devuelve
    {modelo: (observados, esperados)} y, en la clave None, (fallos, días) de todas las celdas.
    """
    trimestres = trimestres if trimestres is not None else [None] * len(modelos)
    por_eq, por_meq = {}, {}
    for m, e, d, f, q in zip(modelos, edades, dias, fallos, trimestres):
        d0, f0 = por_eq.get((e, q), (0.0, 0))
        por_eq[(e, q)] = (d0 + d, f0 + f)
        d1, f1 = por_meq.get((m, e, q), (0.0, 0))
        por_meq[(m, e, q)] = (d1 + d, f1 + f)
    out = {}
    for (m, e, q), (d, f) in por_meq.items():
        de, fe = por_eq[(e, q)]
        o, s = out.get(m, (0, 0.0))
        out[m] = (o + f, s + (d * fe / de if de > 0 else 0.0))
    out[None] = (sum(f for _, f in por_eq.values()), sum(d for d, _ in por_eq.values()))
    return out


def ordenar_ranking(filas, minimo=MINIMO_FALLOS_MODELO):
    """Puesto por la razón, de menor a mayor, entre los modelos con `minimo` fallos o más; los demás, sin puesto y al
    final (cuestión 012). Empates en la razón, mismo puesto («min»); el orden de los empatados, por nombre."""
    con = sorted((f for f in filas if f["fallos"] >= minimo and f.get("razon") is not None),
                 key=lambda f: (f["razon"], f["model"]))
    dentro = {f["model"] for f in con}
    sin = sorted((f for f in filas if f["model"] not in dentro),
                 key=lambda f: (math.inf if f.get("razon") is None else f["razon"], f["model"]))
    puestos = pd.Series([f["razon"] for f in con], dtype="float64").rank(method="min").astype(int).tolist()
    return [dict(f, puesto=p) for f, p in zip(con, puestos)] + [dict(f, puesto=None) for f in sin]


def estabilidad(c, base, parciales, minimo=MINIMO_FALLOS_MODELO):
    """Si los veredictos a igual edad aguantan (directriz 37 del auditor; petición 17, B2.3).

    Quita cada modelo uno a uno, recalcula las tasas por año de edad sin él y cuenta cuántos veredictos de los demás
    cambian. Después repite con todas las celdas sin los años parciales. Un modelo que se queda sin celdas cuenta como
    «sin conclusión».
    """
    def cambian(nuevo, quitado=None):
        """Modelos, sin el quitado, cuyo veredicto no es el de la base."""
        return sorted(m for m in base if m != quitado
                      and nuevo.get(m, {}).get("veredicto", "sin conclusión") != base[m]["veredicto"])

    retiradas = []
    for m in sorted(base):
        cm = cambian(igual_edad(c.loc[c["model"] != m], minimo)["modelos"], m)
        retiradas.append({"model": m, "cambian": len(cm), "modelos": cm})
    mayor = sorted(retiradas, key=lambda x: (-x["cambian"], x["model"]))[0] if retiradas else None
    sp = igual_edad(c.loc[~c["ano"].isin(sorted(parciales))], minimo)["modelos"]
    cp = cambian(sp)
    return {"retiradas": retiradas, "retiradas_que_cambian": sum(1 for x in retiradas if x["cambian"] > 0),
            "max_cambian": mayor["cambian"] if mayor else None,
            "modelo_max": mayor["model"] if mayor and mayor["cambian"] > 0 else None,
            "sin_parciales": {"anos_quitados": sorted(int(a) for a in parciales), "cambian": len(cp), "modelos": cp,
                              "detalle": [{"model": m, "antes": base[m]["veredicto"],
                                           "despues": sp.get(m, {}).get("veredicto", "sin conclusión")} for m in cp]}}


def b2_igual_edad(ranking, celdas, dpt, parciales, minimo=MINIMO_FALLOS_MODELO):
    """El ranking del bloque 2 con la comparación a igual edad, ordenado por la razón (petición 17).

    Cada modelo lleva su razón, su intervalo, su tasa a igual edad, su edad media, el veredicto a igual edad y el
    veredicto bruto con cuestión 012. Devuelve el ranking ordenado, el resumen de la comparación y las celdas usadas.
    """
    c = celdas_que_pasan(dpt, celdas)
    ie = igual_edad(c, minimo)
    filas = []
    for f in ranking:
        x = ie["modelos"].get(f["model"], {})
        g = dict(f)
        for k in ["observados", "esperados", "razon", "razon_desde", "razon_hasta", "tasa_igual_edad", "edad_media_anos"]:
            g[k] = x.get(k)
        g["veredicto"] = veredicto_razon(g["razon_desde"], g["razon_hasta"], g["fallos"], minimo)
        g["veredicto_bruto"] = "sin conclusión" if g["fallos"] < minimo else g["frente_a_todos"]
        filas.append(g)
    orden = ordenar_ranking(filas, minimo)
    con = [f for f in orden if f["puesto"] is not None]
    con_razon = [f for f in orden if f["razon"] is not None]
    cambian = [f for f in orden if f["veredicto"] != f["veredicto_bruto"]]
    # Al lado, el método de la petición 17 (solo la edad y sin φ): qué veredictos cambian y cuánto se parece el orden
    ant = igual_edad(c, minimo, por_trimestre=False, con_phi=False)["modelos"]
    par = [f for f in orden if f["razon"] is not None and ant.get(f["model"], {}).get("razon") is not None]
    frente_anterior = {
        "metodo_anterior": "tasa de cada año de edad, sin trimestre y sin φ (petición 17)",
        "cambian": [{"model": f["model"], "antes": ant.get(f["model"], {}).get("veredicto", "sin conclusión"),
                     "despues": f["veredicto"]} for f in orden
                    if ant.get(f["model"], {}).get("veredicto", "sin conclusión") != f["veredicto"]],
        "spearman_razon": spearman([ant[f["model"]]["razon"] for f in par], [f["razon"] for f in par])}
    resumen = {
        "celdas": ie["celdas"], "dias": ie["dias"], "fallos": ie["fallos"], "tasa_todos": ie["tasa_todos"],
        "celdas_edad_trimestre": ie["celdas_edad_trimestre"], "phi": ie["phi"],
        "frente_al_metodo_anterior": frente_anterior,
        "por_edad": ie["por_edad"], "dias_ranking": int(sum(f["dias_disco"] for f in ranking)),
        "veredictos": {v: sum(1 for f in orden if f["veredicto"] == v) for v in VEREDICTOS},
        "con_conclusion": len(con),
        "sin_conclusion": sorted(f["model"] for f in orden if f["veredicto"] == "sin conclusión"),
        "cambian_frente_al_bruto": {"n": len(cambian), "modelos": [
            {"model": f["model"], "bruto": f["veredicto_bruto"], "igual_edad": f["veredicto"],
             "edad_media_anos": f["edad_media_anos"], "tasa": f["tasa"], "tasa_igual_edad": f["tasa_igual_edad"]}
            for f in cambian]},
        "spearman_tasa_razon": spearman([f["tasa"] for f in con_razon], [f["razon"] for f in con_razon]),
        "spearman_tasa_razon_con_puesto": spearman([f["tasa"] for f in con], [f["razon"] for f in con]),
        "distintos": sum(1 for f in con if f["veredicto"] in ("por encima", "por debajo")),
        "esperados_por_azar": round(len(con) * (1 - CONFIANZA), 1),
        "estabilidad": estabilidad(c, ie["modelos"], parciales, minimo)}
    return orden, resumen, c


# =================================================================================================================
# 9. Bloque 3 · A qué edad empiezan a fallar
# =================================================================================================================
def tasa_por_edad(dpt_grupo, columna_fallos="fallos", phi=1.0):
    """Días, fallos, tasa, intervalo con φ y «sube» por año de edad (0 a 10) de un grupo de dias_por_tramo."""
    a = dpt_grupo.groupby("edad_anos_cumplidos").agg(dias=("dias_disco", "sum"), f=(columna_fallos, "sum"))
    filas = [{"edad": j, "dias_disco": float(a.loc[j, "dias"]) if j in a.index else 0.0,
              "fallos": int(a.loc[j, "f"]) if j in a.index else 0} for j in EDADES]
    return frente_al_anterior(filas, MINIMO_FALLOS_EDAD, phi)


def curva_vida(v, es_evento):
    """Tabla de vida, curva sin cortar, curva cortada por cuestión 009 y S a 1, 3 y 5 años de un grupo de vida_discos."""
    tv = tabla_de_vida(v["edad_entrada_anos"], v["edad_fin_anos"], es_evento)
    s = supervivencia([f["tasa"] for f in tv])
    eventos = [f["eventos"] for f in tv]
    cortada, motivo = cortar_curva(s, eventos, MINIMO_FALLOS_EDAD)
    return {"discos": int(len(v)), "tabla": tv, "s_sin_cortar": s, "s": cortada, "motivo_corte": motivo,
            "eventos_por_ano": eventos, "s_en": {str(k): cortada[k] for k in ANOS_S}}


def curva_dias_por_tramo(dpt_grupo, columnas_evento):
    """La misma curva desde dias_por_tramo: tasa por año de edad = eventos × 365 / días; S(k) = exp(−suma)."""
    a = dpt_grupo.groupby("edad_anos_cumplidos")[["dias_disco"] + columnas_evento].sum().reindex(EDADES, fill_value=0)
    ev = a[columnas_evento].sum(axis=1)
    tasas = [float(ev[j] * 365 / a.loc[j, "dias_disco"]) if a.loc[j, "dias_disco"] > 0 else None for j in EDADES]
    s = supervivencia(tasas)
    return {"tasas": tasas, "s": s, "eventos_por_ano": [int(ev[j]) for j in EDADES]}


# =================================================================================================================
# 10. Segundas vías: cada una parte de otra tabla (método §5)
# =================================================================================================================
def comparar(nombre, via1, via2, a, b, tolerancia=None, recuento=False, texto=None):
    """Compara dos series indexadas por la misma clave; exacta o con tolerancia. Devuelve la ficha de la segunda vía.

    Con `recuento`, una clave que falta en una vía es un cero (un trimestre sin fallos no sale en value_counts); sin
    él, una clave que falta es una diferencia. `texto` dice la comparación cuando la tolerancia no son puntos.
    """
    c = pd.concat([a.rename("v1"), b.rename("v2")], axis=1)
    faltan = 0 if recuento else int(c.isna().any(axis=1).sum())
    c = c.fillna(0)
    dif = (c["v1"] - c["v2"]).abs()
    distintas = int((dif > (tolerancia if tolerancia is not None else 0)).sum())
    return {"nombre": nombre, "via_1": via1, "via_2": via2, "claves": int(len(c)), "claves_en_una_sola_via": faltan,
            "diferentes": distintas, "max_diferencia": r(dif.max() if len(dif) else 0.0),
            "comparacion": texto or ("exacta" if tolerancia is None else f"diferencia menor que {numero(tolerancia, 1)} puntos"),
            "coinciden": bool(distintas == 0 and faltan == 0 and len(c) > 0)}


def segundas_vias(d, t):
    """Las segundas vías de la petición y las que añade este script, todas desde otra tabla."""
    rec_d, mt, dpt, vida, fd_d, it = d["rec_d"], d["mt"], d["dpt"], d["vida"], d["fd_d"], d["it"]
    sv = []
    # SV1: días y fallos por modelo y año, recuento frente a modelo_trimestre
    a = t["celdas_rec"].set_index(["model", "ano"])
    b = t["celdas_mt"].set_index(["model", "ano"])
    sv.append(comparar("días de disco por modelo y año", "recuento_diario_corregido", "modelo_trimestre",
                       a["dias_disco"], b["dias_disco"]))
    sv.append(comparar("fallos por modelo y año", "recuento_diario_corregido", "modelo_trimestre",
                       a["fallos"], b["fallos"]))
    # SV2: altas por trimestre, primera fecha de cada número de serie en fotos y ventanas frente a vida_discos
    u = pd.concat([d["fo"], d["ve"]], ignore_index=True).sort_values(["serial_number", "fecha", "model"],
                                                                     kind="mergesort")
    primera = u.drop_duplicates("serial_number", keep="first")
    primera = primera.loc[primera["model"].isin(d["datos"])]
    sv.append(comparar("altas por trimestre (con el primero)", "fotos_mensuales_corregido + ventanas_fallo_corregido",
                       "vida_discos", etiqueta_trimestre(primera["fecha"]).value_counts(),
                       etiqueta_trimestre(vida["primera_aparicion"]).value_counts(), recuento=True))
    sv.append(comparar("primera aparición de cada disco", "fotos_mensuales_corregido + ventanas_fallo_corregido",
                       "vida_discos", primera.set_index("serial_number")["fecha"].astype("int64"),
                       vida.set_index("serial_number")["primera_aparicion"].astype("int64")))
    # SV3: fallos por trimestre, recuento frente a fallos_detalle
    sv.append(comparar("fallos por trimestre", "recuento_diario_corregido", "fallos_detalle",
                       rec_d.groupby(etiqueta_trimestre(rec_d["fecha"]))["fallos"].sum(),
                       etiqueta_trimestre(fd_d["dia_fallo"]).value_counts(), recuento=True))
    # SV4: discos el primer día de cada trimestre, por modelo, recuento frente a inicio_trimestre
    inicio = rec_d.loc[(rec_d["fecha"].dt.day == 1) & (rec_d["fecha"].dt.month.isin([1, 4, 7, 10]))]
    a4 = inicio.groupby([inicio["fecha"].dt.year.rename("ano"), inicio["fecha"].dt.quarter.rename("trimestre"),
                         "model"])["discos"].sum()
    b4 = it.groupby(["ano", "trimestre", "model"])["discos"].sum()
    sv.append(comparar("discos el primer día de cada trimestre, por modelo", "recuento_diario_corregido",
                       "inicio_trimestre", a4, b4))
    # SV5: supervivencia del conjunto de discos, vida_discos frente a dias_por_tramo, en S a 1, 3 y 5 años (sin cortar)
    s1 = pd.Series({k: 100 * t["sv_todos"]["s_sin_cortar"][k] for k in ANOS_S})
    s2 = pd.Series({k: 100 * t["sv_todos_dpt"]["s"][k] for k in ANOS_S})
    sv.append(comparar("supervivencia del conjunto de discos a 1, 3 y 5 años, en %", "vida_discos (tabla de vida)",
                       "dias_por_tramo (tasas por año de edad)", s1, s2, TOLERANCIA_S_PUNTOS))
    s1 = pd.Series({k: 100 * t["sv_sens"]["s_sin_cortar"][k] for k in ANOS_S})
    s2 = pd.Series({k: 100 * t["sv_sens_dpt"]["s"][k] for k in ANOS_S})
    sv.append(comparar("supervivencia del conjunto de discos contando a los que desaparecen avisando, a 1, 3 y 5 años, en %",
                       "vida_discos (tabla de vida)", "dias_por_tramo (tasas por año de edad)", s1, s2,
                       TOLERANCIA_S_PUNTOS))
    # SV5b: la de los cinco modelos, en los valores que se publican (los que quedan tras el corte)
    a5, b5 = {}, {}
    for m in t["cinco"]:
        for k in ANOS_S:
            if t["sv_modelos"][m]["s"][k] is not None:
                a5[(m, k)] = 100 * t["sv_modelos"][m]["s"][k]
                b5[(m, k)] = 100 * t["sv_modelos_dpt"][m]["s"][k]
    if a5:
        sv.append(comparar("supervivencia de los cinco modelos a 1, 3 y 5 años, en % (valores publicados)",
                           "vida_discos (tabla de vida)", "dias_por_tramo (tasas por año de edad)",
                           pd.Series(a5), pd.Series(b5), TOLERANCIA_S_PUNTOS))
    # SV6: discos el día 1 de cada mes, por modelo, recuento frente a las fotos de dias_por_tramo
    d1 = rec_d.loc[rec_d["fecha"].dt.day == 1].groupby(["fecha", "model"])["discos"].sum()
    f1 = dpt.groupby(["mes", "model"])["fotos"].sum()
    f1.index = f1.index.set_names(["fecha", "model"])
    # Recuento: dias_por_tramo tiene filas de modelo y mes con 0 fotos (las que solo traen fallos), que el recuento
    # del día 1 no tiene; las dos dicen 0 discos
    sv.append(comparar("discos el día 1 de cada mes, por modelo", "recuento_diario_corregido",
                       "dias_por_tramo (fotos)", d1, f1, recuento=True))
    # SV7: días de disco por centro y año desde julio de 2023, recuento frente a centro_mes
    rc = rec_d.loc[rec_d["fecha"] >= PRIMER_DIA_SITIO]
    a7 = rc.groupby([rc["fecha"].dt.year.rename("ano"), "datacenter"])["discos"].sum()
    cc = d["cm"].loc[d["cm"]["mes"] >= PRIMER_DIA_SITIO]
    b7 = cc.groupby([cc["mes"].dt.year.rename("ano"), "datacenter"])["dias_disco"].sum()
    sv.append(comparar("días de disco por centro y año desde el 01/07/2023", "recuento_diario_corregido",
                       "centro_mes", a7, b7))
    # SV8: fallos por modelo y año de edad, fallos_detalle frente a dias_por_tramo
    a8 = fd_d.assign(edad=np.floor(fd_d["edad_al_fallar_anos"]).astype(int)).groupby(["model", "edad"]).size()
    b8 = dpt.groupby(["model", "edad_anos_cumplidos"])["fallos"].sum()
    b8 = b8.loc[b8 > 0]
    b8.index = b8.index.set_names(["model", "edad"])
    sv.append(comparar("fallos por modelo y año de edad", "fallos_detalle (edad al fallar)", "dias_por_tramo",
                       a8, b8, recuento=True))
    # SV9: discos de 8 años o más el primer día del último trimestre, inicio_trimestre frente a dias_por_tramo
    v8 = t["viejos"]
    fq = dpt.loc[dpt["mes"] == pd.Timestamp(v8["fecha"])]
    sv.append(comparar("discos de 8 años o más y discos totales el primer día del último trimestre",
                       "inicio_trimestre", "dias_por_tramo (fotos)",
                       pd.Series({"8_o_mas": v8["discos_8_o_mas"], "total": v8["discos_total"]}),
                       pd.Series({"8_o_mas": int(fq.loc[fq["edad_anos_cumplidos"] >= EDAD_VIEJOS, "fotos"].sum()),
                                  "total": int(fq["fotos"].sum())})))
    # SV10: desaparecen sin fallo por trimestre, desde las fotos y la lista de fallos frente a vida_discos
    fo = d["fo"].sort_values(["serial_number", "fecha"], kind="mergesort")
    pri = fo.drop_duplicates("serial_number", keep="first")
    series_datos = set(pri.loc[pri["model"].isin(d["datos"]), "serial_number"])
    ult = fo.groupby("serial_number")["fecha"].max()
    ult = ult.loc[ult.index.isin(series_datos)]
    con_fallo = set(fd_d["serial_number"])
    des = ult.loc[(ult < fo["fecha"].max()) & ~ult.index.isin(con_fallo)]
    sv.append(comparar("desaparecen sin fallo por trimestre de su última foto",
                       "fotos_mensuales_corregido + fallos_detalle", "vida_discos",
                       etiqueta_trimestre(des).value_counts(),
                       etiqueta_trimestre(vida.loc[vida["evento"] == "desaparece", "ultima_foto"]).value_counts(),
                       recuento=True))
    return sv


# =================================================================================================================
# 11. Cálculo de los tres bloques
# =================================================================================================================
def calcular(d):
    """Calcula los tres bloques con sus tablas, cifras, referencias y comprobaciones; no escribe nada."""
    cal_info = calendario(d["cal"])
    rec_d, mt, dpt, vida, fd_d, dmd = d["rec_d"], d["mt"], d["dpt"], d["vida"], d["fd_d"], d["dmd"]
    t = {}

    # Recuento de discos de datos: la base de días y fallos de todo la petición
    recuento = {"dias_disco": int(rec_d["discos"].sum()), "fallos": int(rec_d["fallos"].sum()), "filas": int(len(rec_d)),
                "poblacion": POBLACION, "periodo": f"del {iso(d['cal']['fecha'].min())} al {FECHA_DATOS.isoformat()}",
                "tabla": "recuento_diario_corregido"}

    # Celdas de modelo y año: desde modelo_trimestre y, por otra vía, desde el recuento
    mt_ano = mt.assign(dias=mt["dias_disco"])
    t["celdas_mt"] = celdas_modelo_ano(mt_ano)
    marca = mt.groupby(["model", "ano"]).agg(pasa=("pasa_minimo_ano", "first"),
                                             dias_ano=("dias_disco_ano", "first")).reset_index()
    t["celdas_mt"] = t["celdas_mt"].merge(marca, on=["model", "ano"], how="left", validate="one_to_one")
    rec_ano = rec_d.assign(ano=rec_d["fecha"].dt.year, dias=rec_d["discos"])
    t["celdas_rec"] = celdas_modelo_ano(rec_ano)
    t["celdas_rec"]["pasa"] = t["celdas_rec"]["dias_disco"] >= MINIMO_DIAS_ANO

    # ---------------------------------------------------------------------------------------------------------
    # B1
    # ---------------------------------------------------------------------------------------------------------
    serie, por_cap, por_fab, partes_ok = b1_serie_mensual(rec_d, dmd, cal_info["meses"])
    ultima_foto = d["fo"]["fecha"].max()
    altas, bajas, cuadre = b1_altas_bajas(vida, fd_d, cal_info["trimestres"], ultima_foto)
    # Primer y último trimestre con días de disco de cada modelo
    trims = mt["ano"].astype(str) + "T" + mt["trimestre"].astype(str)
    pu = mt.assign(q=trims, orden=mt["ano"] * 10 + mt["trimestre"]).loc[mt["dias_disco"] > 0]
    pu = pu.sort_values(["model", "orden"], kind="mergesort").groupby("model")["q"].agg(["first", "last"])
    primeros_ultimos = {m: (x["first"], x["last"]) for m, x in pu.iterrows()}
    top10, _ = b1_top10(t["celdas_mt"], cal_info, primeros_ultimos)
    top10_rec, _ = b1_top10(t["celdas_rec"], cal_info, primeros_ultimos)
    centros, centros_100 = b1_centros(d["cm"])
    # Segunda vía de la serie mensual en PB: las fotos de dias_por_tramo por la capacidad del modelo
    fotos_mes = dpt.merge(dmd[["model", "capacidad_tb"]], on="model", how="left", validate="many_to_one")
    fotos_mes = fotos_mes.assign(tb=fotos_mes["fotos"] * fotos_mes["capacidad_tb"]).groupby("mes")[["fotos", "tb"]].sum()

    primeros_por_ano = {}
    for f in top10:
        primeros_por_ano.setdefault(f["ano"], f)
    primeros_rec = {}
    for f in top10_rec:
        primeros_rec.setdefault(f["ano"], f)

    sin_dato_desde_sitio = sum(f["dias_disco"] for f in centros if f["sin_dato"])
    dias_desde_sitio = sum(f["dias_disco"] for f in centros)
    b1_comp = {
        "unidad": comp_unidad(vida["serial_number"]) and comp_unidad(zip(fd_d["serial_number"], fd_d["dia_fallo"])),
        "minimo": (comp_minimo_ranking([f["dias_disco_ano"] for f in top10], [f["pasa_minimo"] for f in top10],
                                       MINIMO_DIAS_ANO) and all(f["pasa_minimo"] for f in top10)),
        "empates": all(comp_empates([f["discos_medios"] for f in top10 if f["ano"] == a],
                                    [f["puesto"] for f in top10 if f["ano"] == a]) for a in cal_info["dias_ano"]),
        "referencia": bool(partes_ok and centros_100),
        "azar_en_grupos": None, "pesos": None, "hacia_adelante": None,
        "cobertura": comp_cuadre_discos(cuadre["altas_con_el_primer_trimestre"], cuadre["acaban_en_fallo"],
                                        cuadre["desaparecen"], cuadre["siguen"], cuadre["discos"]),
        "periodos": (comp_periodos(top10, "ano", cal_info["parciales"])
                     and comp_periodos(bajas, "trimestre", {cuadre["trimestre_incompleto"]}, "incompleto")
                     and comp_periodos(centros, "ano", cal_info["parciales"] | {PRIMER_DIA_SITIO.year})),
    }

    # ---------------------------------------------------------------------------------------------------------
    # B2
    # ---------------------------------------------------------------------------------------------------------
    ranking, ref_rk, fuera = b2_ranking(t["celdas_mt"])
    ranking_rec, ref_rk_rec, fuera_rec = b2_ranking(t["celdas_rec"])
    # Lo que se decide con la tasa bruta, antes de pasar a igual edad: se queda en el JSON, al lado (petición 17)
    distintos_bruto = sum(1 for f in ranking if f["distinto"])
    distintos_bruto_rec = sum(1 for f in ranking_rec if f["distinto"])
    esperados_bruto = round(len(ranking) * (1 - CONFIANZA), 1)
    # A igual edad, con las celdas marcadas por modelo_trimestre y, como segunda vía, por el recuento (petición 17)
    ranking, ie_res, celdas_ie = b2_igual_edad(ranking, t["celdas_mt"], dpt, cal_info["parciales"])
    ranking_rec, ie_rec, _ = b2_igual_edad(ranking_rec, t["celdas_rec"], dpt, cal_info["parciales"])
    bucle = igual_edad_bucle(celdas_ie["model"].tolist(), celdas_ie["edad_anos_cumplidos"].tolist(),
                             celdas_ie["dias"].tolist(), celdas_ie["fallos"].tolist(), celdas_ie["trimestre"].tolist())
    razon_bucle = {m: o / s for m, (o, s) in bucle.items() if m is not None and s > 0}
    t["sv_igual_edad"] = [
        comparar("razón a igual edad por modelo", "dias_por_tramo, agregado con pandas",
                 "dias_por_tramo, fila a fila con diccionarios",
                 pd.Series({f["model"]: f["razon"] for f in ranking if f["razon"] is not None}, dtype="float64"),
                 pd.Series(razon_bucle, dtype="float64"), 1e-9, texto="diferencia menor que 1e-9"),
        comparar("fallos por modelo en las celdas que pasan el mínimo", "dias_por_tramo (observados)",
                 "modelo_trimestre (fallos del ranking)", pd.Series({f["model"]: f["observados"] for f in ranking}),
                 pd.Series({f["model"]: f["fallos"] for f in ranking}))]
    sum_esp = sum(f["esperados"] for f in ranking if f["esperados"] is not None)
    sum_obs = sum(f["observados"] for f in ranking if f["observados"] is not None)
    esperados_suman = math.isclose(sum_esp, sum_obs, rel_tol=1e-9, abs_tol=1e-6)
    con_puesto = [f for f in ranking if f["puesto"] is not None]
    mapa = b2_mapa(t["celdas_mt"], cal_info["parciales"])
    esperados = ie_res["esperados_por_azar"]
    total_dias, total_fallos = int(mt["dias_disco"].sum()), int(mt["fallos"].sum())
    tasa_todos = intervalo_poisson(total_fallos, total_dias)
    dpt_f = dpt.merge(dmd[["model", "fabricante", "capacidad_tb"]], on="model", how="left", validate="many_to_one")
    por_fabricante = b2_grupos(mt_ano, dpt_f, "fabricante", tasa_todos[0])
    por_capacidad = b2_grupos(mt_ano, dpt_f, "capacidad_tb", tasa_todos[0])
    rec_g = rec_ano.merge(dmd[["model", "fabricante", "capacidad_tb"]], on="model", how="left",
                          validate="many_to_one")
    por_fabricante_rec = {g["grupo"]: g for g in b2_grupos(rec_g, dpt_f, "fabricante", tasa_todos[0])}
    por_capacidad_rec = {g["grupo"]: g for g in b2_grupos(rec_g, dpt_f, "capacidad_tb", tasa_todos[0])}
    b2_comp = {
        "unidad": (comp_unidad(zip(fd_d["serial_number"], fd_d["dia_fallo"])) and len(fd_d) == total_fallos),
        "minimo": comp_minimo_ranking(t["celdas_mt"]["dias_disco"].tolist(), t["celdas_mt"]["pasa"].tolist(),
                                      MINIMO_DIAS_ANO) and bool((t["celdas_mt"]["dias_disco"]
                                                                 == t["celdas_mt"]["dias_ano"]).all())
        and comp_puesto_minimo(ranking, MINIMO_FALLOS_MODELO),
        "empates": comp_empates([f["razon"] for f in con_puesto], [f["puesto"] for f in con_puesto]),
        "referencia": comp_referencia([f["dias_disco"] for f in ranking], [f["fallos"] for f in ranking],
                                      ref_rk["dias_disco"], ref_rk["fallos"]) and esperados_suman,
        "azar_en_grupos": comp_azar([{"desde": f["razon_desde"], "hasta": f["razon_hasta"]} for f in con_puesto],
                                    esperados, CONFIANZA),
        "pesos": None, "hacia_adelante": None,
        "cobertura": (comp_cobertura(ref_rk["dias_disco"] / total_dias)
                      and ref_rk["dias_disco"] + fuera["dias_disco"] == total_dias
                      and ref_rk["fallos"] + fuera["fallos"] == total_fallos),
        "periodos": comp_periodos(mapa, "ano", cal_info["parciales"]),
    }
    b2_extra = {"veredicto_del_intervalo": comp_veredicto_intervalo(ranking, MINIMO_FALLOS_MODELO, ie_res["phi"]["phi"]),
                "esperados_suman_observados": esperados_suman, "phi_minimo_uno": comp_phi([ie_res["phi"]])}

    # ---------------------------------------------------------------------------------------------------------
    # B3
    # ---------------------------------------------------------------------------------------------------------
    orden_dias = mt.groupby("model")["dias_disco"].sum().reset_index().sort_values(["dias_disco", "model"],
                                                                                   ascending=[False, True],
                                                                                   kind="mergesort")
    cinco = orden_dias["model"].head(N_MODELOS_EDAD).tolist()
    t["cinco"] = cinco
    # φ de B3 (petición 19; reglas, apartado 7): uno para la tasa de cada año de edad de todos los grupos y su «sube»
    phi3 = phi_edad(dpt)
    f3 = phi3["phi"]
    edad_todos = tasa_por_edad(dpt, phi=f3)
    edad_sens = tasa_por_edad(dpt.assign(f_sens=dpt["fallos"] + dpt["desaparecen_avisando"]), "f_sens", phi=f3)
    fabricantes = sorted(dmd["fabricante"].dropna().unique())
    edad_fab = {f: tasa_por_edad(dpt_f.loc[dpt_f["fabricante"] == f], phi=f3) for f in fabricantes}
    edad_mod = {m: tasa_por_edad(dpt.loc[dpt["model"] == m], phi=f3) for m in cinco}
    for grupo in list(edad_fab.values()) + list(edad_mod.values()):
        for f, fl in zip(grupo, edad_todos):
            f["tasa_todos"] = fl["tasa"]
    for f, fl in zip(edad_sens, edad_todos):
        f["tasa_sin_contarlos"] = fl["tasa"]
    sube_distinto = [f["edad"] for f, s in zip(edad_todos, edad_sens) if (f["sube"], f["baja"]) != (s["sube"], s["baja"])]
    fallos_fd = {(m, e): n for (m, e), n in fd_d.assign(e=np.floor(fd_d["edad_al_fallar_anos"]).astype(int))
                 .groupby(["model", "e"]).size().items()}
    fallos_fd_edad = {}
    for (m, e), n in fallos_fd.items():
        fallos_fd_edad[e] = fallos_fd_edad.get(e, 0) + n

    t["sv_todos"] = curva_vida(vida, vida["evento"] == "fallo")
    t["sv_sens"] = curva_vida(vida, (vida["evento"] == "fallo") | vida["desaparece_avisando"].fillna(False).astype(bool))
    t["sv_todos_dpt"] = curva_dias_por_tramo(dpt, ["fallos"])
    t["sv_sens_dpt"] = curva_dias_por_tramo(dpt, ["fallos", "desaparecen_avisando"])
    t["sv_modelos"] = {m: curva_vida(vida.loc[vida["model"] == m], vida.loc[vida["model"] == m, "evento"] == "fallo")
                       for m in cinco}
    t["sv_modelos_dpt"] = {m: curva_dias_por_tramo(dpt.loc[dpt["model"] == m], ["fallos"]) for m in cinco}

    ult_q = d["it"].sort_values(["ano", "trimestre"], kind="mergesort").iloc[-1]
    itq = d["it"].loc[(d["it"]["ano"] == ult_q["ano"]) & (d["it"]["trimestre"] == ult_q["trimestre"])]
    fecha_q = dt.date(int(ult_q["ano"]), 3 * int(ult_q["trimestre"]) - 2, 1)
    viejos = {"fecha": fecha_q.isoformat(), "discos_8_o_mas": int(itq.loc[itq["edad_anos_cumplidos"] >= EDAD_VIEJOS,
                                                                          "discos"].sum()),
              "discos_total": int(itq["discos"].sum())}
    viejos["pct"] = 100 * viejos["discos_8_o_mas"] / viejos["discos_total"]
    a7 = dpt.assign(tramo=np.where(dpt["edad_anos_cumplidos"] >= 9, "9 a 10", dpt["edad_anos_cumplidos"].astype(str)))
    a7 = a7.loc[dpt["edad_anos_cumplidos"] >= 7].groupby("tramo").agg(dias=("dias_disco", "sum"), f=("fallos", "sum"))
    tramos_viejos = frente_al_anterior([{"edad": k, "dias_disco": float(a7.loc[k, "dias"]), "fallos": int(a7.loc[k, "f"])}
                                        for k in ["7", "8", "9 a 10"] if k in a7.index], MINIMO_FALLOS_EDAD, f3)
    viejos["tramos"] = tramos_viejos
    t["viejos"] = viejos

    dias_dpt = float(dpt["dias_disco"].sum())
    filas_edad = (edad_todos + edad_sens + tramos_viejos + [f for g in edad_fab.values() for f in g]
                  + [f for g in edad_mod.values() for f in g])
    curvas = [(c["s"], c["eventos_por_ano"]) for c in [t["sv_todos"], t["sv_sens"]] + list(t["sv_modelos"].values())]
    ref_edad = all(comp_referencia([edad_fab[f][j]["dias_disco"] for f in fabricantes],
                                   [edad_fab[f][j]["fallos"] for f in fabricantes],
                                   edad_todos[j]["dias_disco"], edad_todos[j]["fallos"]) for j in range(len(EDADES)))
    con_exposicion = sum(1 for e0, e1 in zip(vida["edad_entrada_anos"], vida["edad_fin_anos"]) if e1 > e0)
    b3_comp = {
        "unidad": (comp_unidad(vida["serial_number"])
                   and comp_unidad(zip(dpt["model"], dpt["centro"], dpt["mes"], dpt["edad_anos_cumplidos"]))),
        "minimo": comp_minimo_edad(filas_edad, MINIMO_FALLOS_EDAD, curvas),
        "empates": None,
        "referencia": ref_edad,
        "azar_en_grupos": None, "pesos": None, "hacia_adelante": None,
        "cobertura": comp_cobertura(dias_dpt / recuento["dias_disco"]) and comp_cobertura(con_exposicion / len(vida)),
        "periodos": None,
    }

    # ---------------------------------------------------------------------------------------------------------
    # Segundas vías y montaje de las tres preguntas
    # ---------------------------------------------------------------------------------------------------------
    sv = segundas_vias(d, t) + t["sv_igual_edad"]
    ok = {s["nombre"]: s["coinciden"] for s in sv}

    def sv_ok(*nombres):
        """Cierto si todas las segundas vías nombradas coinciden."""
        return all(ok.get(n, False) for n in nombres)

    periodo_todo = recuento["periodo"]
    # Cifras de B1
    c1 = []
    for m in [cal_info["meses"][0], PRIMER_DIA_SITIO, cal_info["meses"][-1]]:
        s = next(x for x in serie if x["mes"] == iso(m))
        fm = fotos_mes.loc[m]
        c1.append({"nombre": f"discos de datos el {iso(m)}", "clave": f"preguntas.B1.tablas.serie_mensual[{iso(m)}].discos",
                   "valor": s["discos"], "unidad": "discos", "poblacion": POBLACION, "periodo": iso(m),
                   "filas": int(((rec_d["fecha"] == m)).sum()), "segunda_via": int(fm["fotos"]),
                   "segunda_via_de": "dias_por_tramo (fotos de ese día)", "coinciden": s["discos"] == int(fm["fotos"])})
        c1.append({"nombre": f"capacidad en PB el {iso(m)}", "clave": f"preguntas.B1.tablas.serie_mensual[{iso(m)}].pb",
                   "valor": s["pb"], "unidad": "PB", "poblacion": POBLACION, "periodo": iso(m),
                   "filas": int(((rec_d["fecha"] == m)).sum()), "segunda_via": r(fm["tb"] / 1000),
                   "segunda_via_de": "dias_por_tramo (fotos de ese día × capacidad del modelo)",
                   "coinciden": math.isclose(s["pb"], fm["tb"] / 1000, abs_tol=1e-6)})
    suma_altas = sum(a["altas"] for a in altas)
    c1.append({"nombre": f"altas de {altas[0]['trimestre']} a {altas[-1]['trimestre']}", "clave": "preguntas.B1.tablas.altas",
               "valor": suma_altas, "unidad": "discos", "poblacion": POBLACION,
               "periodo": f"de {altas[0]['trimestre']} a {altas[-1]['trimestre']}", "filas": int(len(vida)),
               "segunda_via": suma_altas if sv_ok("altas por trimestre (con el primero)") else None,
               "segunda_via_de": "SV «altas por trimestre (con el primero)»",
               "coinciden": sv_ok("altas por trimestre (con el primero)", "primera aparición de cada disco")})
    c1.append({"nombre": "fallos de discos de datos en el periodo", "clave": "preguntas.B1.tablas.bajas[].fallos",
               "valor": cuadre["fallos_de_la_serie"], "unidad": "fallos", "poblacion": POBLACION, "periodo": periodo_todo,
               "filas": int(len(fd_d)), "segunda_via": recuento["fallos"], "segunda_via_de": "recuento_diario_corregido",
               "coinciden": cuadre["fallos_de_la_serie"] == recuento["fallos"] and sv_ok("fallos por trimestre")})
    c1.append({"nombre": "discos que desaparecen sin fallo", "clave": "preguntas.B1.tablas.bajas[].desaparecen",
               "valor": cuadre["desaparecen"], "unidad": "discos", "poblacion": POBLACION, "periodo": periodo_todo,
               "filas": int(len(vida)), "segunda_via": cuadre["desaparecen"] if sv_ok(
                   "desaparecen sin fallo por trimestre de su última foto") else None,
               "segunda_via_de": "SV «desaparecen sin fallo por trimestre de su última foto»",
               "coinciden": sv_ok("desaparecen sin fallo por trimestre de su última foto")})
    for a, f in primeros_por_ano.items():
        g = primeros_rec.get(a, {})
        c1.append({"nombre": f"primero de los diez de {a}: {f['model']}", "clave": f"preguntas.B1.tablas.top10[{a}][0]",
                   "valor": f["discos_medios"], "unidad": "discos medios", "poblacion": POBLACION,
                   "periodo": periodo_ano(a, cal_info), "filas": int((mt["ano"] == a).sum()),
                   "segunda_via": g.get("discos_medios"), "segunda_via_de": "recuento_diario_corregido",
                   "coinciden": g.get("model") == f["model"] and g.get("discos_medios") == f["discos_medios"]})
    for a in sorted({f["ano"] for f in centros}):
        # Parte sin centro del año: 0 si el año no tiene ninguna fila «sin dato»
        del_ano = [f for f in centros if f["ano"] == a]
        parte_sd = sum(f["pct_del_ano"] for f in del_ano if f["sin_dato"])
        c1.append({"nombre": f"parte de los días de disco sin centro en {a}", "clave": f"preguntas.B1.tablas.centros[{a}]",
                   "valor": parte_sd, "unidad": "%", "poblacion": POBLACION, "periodo": del_ano[0]["periodo"],
                   "filas": int(((d["cm"]["mes"] >= PRIMER_DIA_SITIO) & (d["cm"]["mes"].dt.year == a)).sum()),
                   "segunda_via": parte_sd if sv_ok("días de disco por centro y año desde el 01/07/2023") else None,
                   "segunda_via_de": "SV «días de disco por centro y año desde el 01/07/2023»",
                   "coinciden": sv_ok("días de disco por centro y año desde el 01/07/2023")})

    # Cifras de B2
    c2 = []
    pasan_rec = t["celdas_rec"]["pasa"]
    c2.append({"nombre": "celdas de modelo y año que pasan el mínimo", "clave": "preguntas.B2.tablas.celdas_que_pasan",
               "valor": int(t["celdas_mt"]["pasa"].sum()), "unidad": "celdas", "poblacion": POBLACION,
               "periodo": periodo_todo, "filas": int(len(mt)), "segunda_via": int(pasan_rec.sum()),
               "segunda_via_de": "recuento_diario_corregido (días del año ≥ mínimo)",
               "coinciden": int(t["celdas_mt"]["pasa"].sum()) == int(pasan_rec.sum())})
    c2.append({"nombre": "modelos en el ranking", "clave": "preguntas.B2.tablas.ranking", "valor": len(ranking),
               "unidad": "modelos", "poblacion": POBLACION, "periodo": periodo_todo, "filas": int(len(mt)),
               "segunda_via": len(ranking_rec), "segunda_via_de": "recuento_diario_corregido",
               "coinciden": [f["model"] for f in ranking] == [f["model"] for f in ranking_rec]})
    for nombre, clave in [("días de disco fuera del ranking", "dias_disco"), ("fallos fuera del ranking", "fallos")]:
        c2.append({"nombre": nombre, "clave": f"preguntas.B2.tablas.fuera_del_ranking.{clave}", "valor": fuera[clave],
                   "unidad": "días de disco" if clave == "dias_disco" else "fallos", "poblacion": POBLACION,
                   "periodo": periodo_todo, "filas": int(len(mt)), "segunda_via": fuera_rec[clave],
                   "segunda_via_de": "recuento_diario_corregido", "coinciden": fuera[clave] == fuera_rec[clave]})
    c2.append({"nombre": "tasa del conjunto de discos en las celdas del ranking", "clave": "preguntas.B2.tablas.referencia_bruta.valor",
               "valor": r(ref_rk["tasa"]), "unidad": "% anual", "poblacion": POBLACION + ", celdas que pasan el mínimo",
               "periodo": periodo_todo, "filas": int(t["celdas_mt"]["pasa"].sum()), "segunda_via": r(ref_rk_rec["tasa"]),
               "segunda_via_de": "recuento_diario_corregido", "coinciden": r(ref_rk["tasa"]) == r(ref_rk_rec["tasa"])})
    # El ranking va por la razón (petición 17): la tasa bruta más baja y la más alta se buscan entre todos
    def por_tasa(filas, fn):
        """El modelo de tasa bruta más baja o más alta; empates, por nombre."""
        return fn(sorted(filas, key=lambda f: f["model"]), key=lambda f: f["tasa"])

    for etiqueta, fn in [("más baja", min), ("más alta", max)]:
        f, g = por_tasa(ranking, fn), por_tasa(ranking_rec, fn)
        c2.append({"nombre": f"tasa bruta {etiqueta} del ranking: {f['model']}", "clave": f"preguntas.B2.tablas.ranking[{f['model']}]",
                   "valor": r(f["tasa"]), "unidad": "% anual", "poblacion": POBLACION + f", {f['model']}",
                   "periodo": ", ".join(str(a) for a in f["anos_que_pasan"]), "filas": len(f["anos_que_pasan"]),
                   "segunda_via": r(g["tasa"]), "segunda_via_de": "recuento_diario_corregido",
                   "coinciden": g["model"] == f["model"] and r(g["tasa"]) == r(f["tasa"])})
    distintos = ie_res["distintos"]
    c2.append({"nombre": "modelos que se distinguen a igual edad, de los que tienen conclusión",
               "clave": "preguntas.B2.tablas.distintos", "valor": distintos,
               "unidad": "modelos", "poblacion": POBLACION + "; modelos con 20 fallos o más (cuestión 012)", "periodo": periodo_todo,
               "filas": len(con_puesto), "segunda_via": ie_rec["distintos"],
               "segunda_via_de": "celdas marcadas con recuento_diario_corregido", "coinciden": distintos == ie_rec["distintos"]})
    # Cifras de la comparación a igual edad (petición 17)
    pob_ie = POBLACION + "; celdas de dias_por_tramo cuyo modelo y año pasan el mínimo"
    c2.append({"nombre": "fallos de las celdas a igual edad", "clave": "preguntas.B2.tablas.a_igual_edad.fallos",
               "valor": ie_res["fallos"], "unidad": "fallos", "poblacion": pob_ie, "periodo": periodo_todo,
               "filas": ie_res["celdas"], "segunda_via": ref_rk["fallos"], "segunda_via_de": "modelo_trimestre (fallos del ranking)",
               "coinciden": ie_res["fallos"] == ref_rk["fallos"]})
    tasa_bucle = FACTOR_TASA * bucle[None][0] / bucle[None][1] if bucle[None][1] > 0 else None
    c2.append({"nombre": "tasa de todas las celdas a igual edad", "clave": "preguntas.B2.tablas.a_igual_edad.tasa_todos",
               "valor": r(ie_res["tasa_todos"]), "unidad": "% anual", "poblacion": pob_ie, "periodo": periodo_todo,
               "filas": ie_res["celdas"], "segunda_via": r(tasa_bucle), "segunda_via_de": "dias_por_tramo, fila a fila con diccionarios",
               "coinciden": r(tasa_bucle) is not None and r(tasa_bucle) == r(ie_res["tasa_todos"])})
    c2.append({"nombre": "modelos con puesto a igual edad", "clave": "preguntas.B2.tablas.a_igual_edad.con_conclusion",
               "valor": len(con_puesto), "unidad": "modelos", "poblacion": pob_ie, "periodo": periodo_todo,
               "filas": len(ranking), "segunda_via": ie_rec["con_conclusion"],
               "segunda_via_de": "celdas marcadas con recuento_diario_corregido",
               "coinciden": [f["model"] for f in ranking] == [f["model"] for f in ranking_rec]
               and [f["puesto"] for f in ranking] == [f["puesto"] for f in ranking_rec]})
    for v in VEREDICTOS:
        c2.append({"nombre": f"modelos {v} a igual edad", "clave": f"preguntas.B2.tablas.a_igual_edad.veredictos[{v}]",
                   "valor": ie_res["veredictos"][v], "unidad": "modelos", "poblacion": pob_ie, "periodo": periodo_todo,
                   "filas": len(ranking), "segunda_via": ie_rec["veredictos"][v],
                   "segunda_via_de": "celdas marcadas con recuento_diario_corregido",
                   "coinciden": ie_res["veredictos"][v] == ie_rec["veredictos"][v]})
    n_camb, n_camb_rec = ie_res["cambian_frente_al_bruto"]["n"], ie_rec["cambian_frente_al_bruto"]["n"]
    c2.append({"nombre": "modelos que cambian de veredicto entre la tasa bruta y la de igual edad",
               "clave": "preguntas.B2.tablas.a_igual_edad.cambian_frente_al_bruto.n", "valor": n_camb, "unidad": "modelos",
               "poblacion": pob_ie, "periodo": periodo_todo, "filas": len(ranking), "segunda_via": n_camb_rec,
               "segunda_via_de": "recuento_diario_corregido (tasa bruta) y celdas marcadas con él", "coinciden": n_camb == n_camb_rec})
    for etiqueta, f in ([("más baja", con_puesto[0]), ("más alta", con_puesto[-1])] if con_puesto else []):
        c2.append({"nombre": f"razón a igual edad {etiqueta} con puesto: {f['model']}",
                   "clave": f"preguntas.B2.tablas.ranking[{f['model']}].razon", "valor": r(f["razon"]),
                   "unidad": "observados / esperados", "poblacion": pob_ie + f", {f['model']}",
                   "periodo": ", ".join(str(a) for a in f["anos_que_pasan"]), "filas": len(f["anos_que_pasan"]),
                   "segunda_via": r(razon_bucle.get(f["model"])), "segunda_via_de": "dias_por_tramo, fila a fila con diccionarios",
                   "coinciden": sv_ok("razón a igual edad por modelo")})
    for clave in ["spearman_tasa_razon", "spearman_tasa_razon_con_puesto"]:
        if ie_res[clave] is not None:
            c2.append({"nombre": f"correlación de Spearman entre la tasa bruta y la razón ({'con puesto' if clave.endswith('puesto') else 'todos'})",
                       "clave": f"preguntas.B2.tablas.a_igual_edad.{clave}", "valor": r(ie_res[clave]),
                       "unidad": "correlación", "poblacion": pob_ie, "periodo": periodo_todo, "filas": len(ranking),
                       "segunda_via": r(ie_rec[clave]), "segunda_via_de": "recuento_diario_corregido",
                       "coinciden": r(ie_rec[clave]) == r(ie_res[clave])})
    for f in por_fabricante:
        g = por_fabricante_rec.get(f["grupo"], {})
        c2.append({"nombre": f"tasa de {f['grupo']}", "clave": f"preguntas.B2.tablas.por_fabricante[{f['grupo']}]",
                   "valor": r(f["tasa"]), "unidad": "% anual", "poblacion": POBLACION + f", fabricante {f['grupo']}",
                   "periodo": periodo_todo, "filas": int((mt["fabricante"] == f["grupo"]).sum()),
                   "segunda_via": r(g.get("tasa")), "segunda_via_de": "recuento_diario_corregido",
                   "coinciden": r(g.get("tasa")) == r(f["tasa"])})
    for f in por_capacidad:
        g = por_capacidad_rec.get(f["grupo"], {})
        c2.append({"nombre": f"tasa de los discos de {f['grupo']} TB", "clave": f"preguntas.B2.tablas.por_capacidad[{f['grupo']}]",
                   "valor": r(f["tasa"]), "unidad": "% anual", "poblacion": POBLACION + f", {f['grupo']} TB",
                   "periodo": periodo_todo, "filas": int((mt["capacidad_tb"] == f["grupo"]).sum()),
                   "segunda_via": r(g.get("tasa")), "segunda_via_de": "recuento_diario_corregido",
                   "coinciden": r(g.get("tasa")) == r(f["tasa"])})

    # Cifras de B3
    c3 = []
    sv5 = sv_ok("supervivencia del conjunto de discos a 1, 3 y 5 años, en %")
    for f in edad_todos:
        n_fd = fallos_fd_edad.get(f["edad"], 0)
        c3.append({"nombre": f"tasa del conjunto de discos a {f['edad']} años de edad", "clave": f"preguntas.B3.tablas.tasa_por_edad.todos[{f['edad']}]",
                   "valor": r(f["tasa"]), "unidad": "% anual", "poblacion": POBLACION, "periodo": periodo_todo,
                   "filas": int((dpt["edad_anos_cumplidos"] == f["edad"]).sum()), "segunda_via": n_fd,
                   "segunda_via_de": ("fallos de fallos_detalle con ese año de edad al fallar; los días solo los reparte "
                                      "dias_por_tramo, y se contrastan con la supervivencia (SV5)"),
                   "coinciden": n_fd == f["fallos"] and sv5})
    for nombre, cv, cd, svn in [("todos los discos", t["sv_todos"], t["sv_todos_dpt"], "supervivencia del conjunto de discos a 1, 3 y 5 años, en %"),
                                ("todos los discos contando a los que desaparecen avisando", t["sv_sens"], t["sv_sens_dpt"],
                                 "supervivencia del conjunto de discos contando a los que desaparecen avisando, a 1, 3 y 5 años, en %")]:
        for k in ANOS_S:
            if cv["s"][k] is None:
                continue
            c3.append({"nombre": f"supervivencia a {k} años, {nombre}", "clave": f"preguntas.B3.tablas.supervivencia.{'todos' if nombre == 'todos los discos' else 'todos_desaparecen_avisando'}.s[{k}]",
                       "valor": r(cv["s"][k]), "unidad": "parte que sigue (0 a 1)", "poblacion": POBLACION,
                       "periodo": periodo_todo, "filas": int(len(vida)), "segunda_via": r(cd["s"][k]),
                       "segunda_via_de": "dias_por_tramo (tasas por año de edad)",
                       "coinciden": abs(100 * (cv["s"][k] - cd["s"][k])) < TOLERANCIA_S_PUNTOS and sv_ok(svn)})
    for m in cinco:
        for k in ANOS_S:
            v = t["sv_modelos"][m]["s"][k]
            if v is None:
                continue
            w = t["sv_modelos_dpt"][m]["s"][k]
            c3.append({"nombre": f"supervivencia a {k} años, {m}", "clave": f"preguntas.B3.tablas.supervivencia.modelos[{m}].s[{k}]",
                       "valor": r(v), "unidad": "parte que sigue (0 a 1)", "poblacion": POBLACION + f", {m}",
                       "periodo": periodo_todo, "filas": int((vida["model"] == m).sum()), "segunda_via": r(w),
                       "segunda_via_de": "dias_por_tramo (tasas por año de edad)",
                       "coinciden": w is not None and abs(100 * (v - w)) < TOLERANCIA_S_PUNTOS})
    sv9 = sv_ok("discos de 8 años o más y discos totales el primer día del último trimestre")
    c3.append({"nombre": f"discos de 8 años o más el {viejos['fecha']}", "clave": "preguntas.B3.tablas.discos_8_o_mas",
               "valor": viejos["discos_8_o_mas"], "unidad": "discos", "poblacion": POBLACION, "periodo": viejos["fecha"],
               "filas": int(len(itq)), "segunda_via": viejos["discos_8_o_mas"] if sv9 else None,
               "segunda_via_de": "dias_por_tramo (fotos de ese día)", "coinciden": sv9})
    for f in tramos_viejos:
        edades_tramo = [9, 10] if f["edad"] == "9 a 10" else [int(f["edad"])]
        n_fd = sum(fallos_fd_edad.get(e, 0) for e in edades_tramo)
        c3.append({"nombre": f"tasa del conjunto de discos a {f['edad']} años", "clave": f"preguntas.B3.tablas.discos_8_o_mas.tramos[{f['edad']}]",
                   "valor": r(f["tasa"]), "unidad": "% anual", "poblacion": POBLACION, "periodo": periodo_todo,
                   "filas": int(dpt["edad_anos_cumplidos"].isin(edades_tramo).sum()), "segunda_via": n_fd,
                   "segunda_via_de": "fallos de fallos_detalle con esa edad al fallar", "coinciden": n_fd == f["fallos"]})

    # Lo que no saca conclusión: celdas y modelos por debajo del mínimo (B2), años de edad con días de disco y menos de
    # 20 fallos (B3; un año sin ningún día no es un grupo pequeño, es un grupo que no existe, y sale «sin días» en su
    # tabla) y curvas cortadas
    grupos_edad = ([("todos los discos", edad_todos), ("todos los discos contando a los que desaparecen avisando", edad_sens)]
                   + list(edad_fab.items()) + list(edad_mod.items()) + [("tramos de 7 años o más", tramos_viejos)])
    sin_conclusion = (
        [{"bloque": "B2", "tipo": "celdas", "grupo": "años de modelo por debajo del mínimo", "casos": fuera["celdas"],
          "dias_disco": fuera["dias_disco"], "fallos": fuera["fallos"]}]
        + [{"bloque": "B2", "tipo": "modelo", "grupo": m["model"], "casos": None, "dias_disco": m["dias_disco"],
            "fallos": m["fallos"]} for m in fuera["modelos"]]
        + [{"bloque": "B2", "tipo": "pocos fallos", "grupo": f["model"], "casos": f["fallos"], "dias_disco": f["dias_disco"],
            "fallos": f["fallos"], "tasa": f["tasa"]} for f in ranking if f["puesto"] is None]
        + [{"bloque": "B3", "tipo": "edad", "grupo": nombre, "edad": f["edad"], "casos": f["fallos"],
            "dias_disco": r(f["dias_disco"], 1), "fallos": f["fallos"]}
           for nombre, g in grupos_edad for f in g if f["sin_conclusion"] and f["dias_disco"] > 0]
        + [{"bloque": "B3", "tipo": "curva", "grupo": k, "casos": None, "motivo": c["motivo_corte"]}
           for k, c in ([("el conjunto de discos", t["sv_todos"]), ("el conjunto de discos contando a los que desaparecen avisando", t["sv_sens"])]
                        + list(t["sv_modelos"].items())) if c["motivo_corte"]])

    def curva_json(c, cd=None):
        """La curva de un grupo para el JSON: tabla de vida, S cortada y sin cortar, S a 1, 3 y 5 y el corte."""
        out = {"discos": c["discos"], "s": c["s"], "s_sin_cortar": c["s_sin_cortar"], "s_en": c["s_en"],
               "motivo_corte": c["motivo_corte"],
               "tabla_de_vida": [{"edad": f["edad"], "exposicion_anos": r(f["exposicion_anos"], 3),
                                  "fallos": f["eventos"], "tasa": r(f["tasa"], 8)} for f in c["tabla"]]}
        if cd is not None:
            out["s_dias_por_tramo"] = cd["s"]
            out["diferencia_puntos"] = {str(k): (r(100 * (c["s_sin_cortar"][k] - cd["s"][k]), 4)
                                                 if cd["s"][k] is not None and c["s_sin_cortar"][k] is not None else None)
                                        for k in ANOS_S}
        return out

    motivos_b1 = {"azar_en_grupos": "B1 cuenta discos y días de disco; no compara tasas de grupos con el total",
                  "pesos": "no hay ninguna puntuación con pesos",
                  "hacia_adelante": "B1 describe el conjunto de discos; no predice nada que se pueda medir en el periodo siguiente"}
    motivos_b2 = {"pesos": "no hay ninguna puntuación con pesos",
                  "hacia_adelante": ("la tasa describe el periodo; si un modelo malo lo sigue siendo después se mide "
                                     "en la reserva, que no se mira (reglas, apartado 5)")}
    motivos_b3 = {"empates": "B3 no ordena entidades en un ranking", "azar_en_grupos": (
                      "B3 compara cada año de edad con el anterior con el criterio de las reglas, apartado 7 (intervalos que no "
                      "se solapan), no grupos frente al total"),
                  "pesos": "no hay ninguna puntuación con pesos",
                  "hacia_adelante": "la tasa por edad y la supervivencia describen el periodo; la previsión es el bloque 9",
                  "periodos": ("la tasa por edad y la supervivencia juntan todo el periodo, sin comparar años de "
                               "calendario; 2025 aporta sus seis meses de días y fallos")}

    preguntas = [
        {"id": "B1", "pregunta": ("Qué discos de datos tiene Backblaze, cuánta capacidad suman y cómo ha cambiado el conjunto de discos "
                                  "de enero de 2020 a junio de 2025: altas, bajas, modelos principales y centros"),
         "decision": ("ninguna por sí sola; da los discos y los días de disco sobre los que se leen el ranking de B2 y "
                      "la edad de B3, que son los que deciden compras y renovaciones"),
         "planteamiento": "config/metodo/plan_de_la_analitica.md, bloque 1; metodo/04_planteamientos.md §1.A",
         "funcion": "otra", "funcion_adaptada": ("consultas agrupadas, top N y tabla cruzada de assets/18_consultas_"
                                                 "interactivas.md §8, §9 y §13; ninguna función del capítulo 42 cuenta "
                                                 "un conjunto de discos"),
         "poblacion": {"regla": POBLACION, "periodo": periodo_todo, "filas": int(len(rec_d)), "unidad": "disco (número de serie)",
                       "entidades": int(len(vida))},
         "medida": ("discos el día 1 de cada mes y capacidad = discos × capacidad del modelo / 1.000, en PB; altas = discos con "
                    "su primera aparición en el trimestre; bajas = fallos y discos que desaparecen sin fallo; discos medios "
                    "del año = días de disco / días del año en los datos; parte de cada centro en los días del año"),
         "minimo_casos": "50.000 días de disco en el año para entrar entre los diez de cada año (reglas, apartado 7)",
         "que_cambia_la_decision": "nada por sí sola; sitúa las tasas de B2 y B3 en el tamaño y la mezcla del conjunto de discos",
         "cifras": c1,
         "referencia": {"que_es": ("el total del conjunto de discos de cada mes y de cada año, frente al que se leen las partes "
                                   "por capacidad, fabricante y centro"), "valor": recuento["dias_disco"],
                        "filas": recuento["filas"]},
         "comprobaciones": b1_comp, "motivos_null": {k: v for k, v in motivos_b1.items() if b1_comp[k] is None},
         "tablas": {"serie_mensual": serie, "serie_mensual_por_capacidad": por_cap,
                    "serie_mensual_por_fabricante": por_fab, "altas": altas, "bajas": bajas, "cuadre_discos": cuadre,
                    "top10": top10, "centros": centros,
                    "centros_resumen": {"dias_desde_sitio": dias_desde_sitio, "dias_sin_dato": sin_dato_desde_sitio}}},
        {"id": "B2", "pregunta": "Qué modelos de disco fallan más, por tasa anual de fallo, y si el ranking se mantiene de un año a otro",
         "decision": "qué modelos comprar y cuáles evitar, porque es la base de la decisión de compra (plan, bloque 2)",
         "planteamiento": "config/metodo/plan_de_la_analitica.md, bloque 2; metodo/04_planteamientos.md §1.A",
         "funcion": "comparar_con_total",
         "funcion_adaptada": ("42.6 con tres cambios: la medida es una tasa por días de disco y no una proporción, así que "
                              "el intervalo es el exacto de Poisson y no el de Wilson; cada modelo se compara a igual edad, "
                              "con la razón de sus fallos entre los esperados por la tasa de cada año de edad de todos los "
                              "modelos del ranking (estandarización indirecta, 5.6; reglas, apartado 7; petición 17); y la tasa "
                              "bruta frente a la de todos los discos de las mismas celdas queda al lado"),
         "poblacion": {"regla": POBLACION + "; en el ranking, solo los años de cada modelo con 50.000 días de disco o más",
                       "periodo": periodo_todo, "filas": int(len(mt)), "unidad": "modelo de disco",
                       "entidades": int(mt["model"].nunique())},
         "medida": ("tasa anual de fallo = 100 × 365 × fallos / días de disco (reglas, apartado 6), con su intervalo exacto de "
                    "Poisson al 95 %; a igual edad, razón = fallos observados / esperados con la tasa de cada año de "
                    "edad, con el intervalo de Poisson de los observados, y tasa a igual edad = razón × tasa de todas "
                    "las celdas"),
         "minimo_casos": ("50.000 días de disco del modelo en el año, y 20 fallos en sus años que pasan el mínimo para "
                          "llevar puesto y sacar conclusión (reglas, apartado 7, cuestión 012)"),
         "que_cambia_la_decision": ("un modelo cuyo intervalo de la razón queda entero por encima de 1 falla más que lo "
                                    "esperado a su edad y es candidato a no comprarse; uno entero por debajo, a "
                                    "comprarse, siempre a igual capacidad (bloque 4)"),
         "cifras": c2,
         "referencia": {"que_es": ("razón 1: los fallos que tendría el modelo con la tasa de cada año de edad de todos los "
                                   "modelos del ranking juntos, en sus mismas celdas; la tasa de todas esas celdas"),
                        "valor": r(ie_res["tasa_todos"]), "dias_disco": r(ie_res["dias"], 1), "fallos": ie_res["fallos"],
                        "filas": ie_res["celdas"]},
         "comprobaciones": b2_comp, "motivos_null": {k: v for k, v in motivos_b2.items() if b2_comp[k] is None},
         "comprobaciones_extra": b2_extra,
         "tablas": {"ranking": ranking, "distintos": distintos, "esperados_por_azar": esperados,
                    "distintos_bruto": distintos_bruto, "esperados_por_azar_bruto": esperados_bruto,
                    "distintos_bruto_segunda_via": distintos_bruto_rec,
                    "a_igual_edad": ie_res,
                    "referencia_bruta": {"que_es": "la tasa del conjunto de discos en las mismas celdas de modelo y año que pasan el mínimo",
                                         "valor": r(ref_rk["tasa"]), "desde": r(ref_rk["desde"]), "hasta": r(ref_rk["hasta"]),
                                         "dias_disco": ref_rk["dias_disco"], "fallos": ref_rk["fallos"],
                                         "filas": int(t["celdas_mt"]["pasa"].sum())},
                    "celdas_que_pasan": int(t["celdas_mt"]["pasa"].sum()), "celdas_total": int(len(t["celdas_mt"])),
                    "fuera_del_ranking": fuera, "mapa_modelo_ano": mapa, "por_fabricante": por_fabricante,
                    "por_capacidad": por_capacidad,
                    "todos_los_discos": {"dias_disco": total_dias, "fallos": total_fallos, "tasa": tasa_todos[0],
                                               "desde": tasa_todos[1], "hasta": tasa_todos[2]}}},
        {"id": "B3", "pregunta": "A qué edad empiezan a fallar los discos y qué parte sigue funcionando a los 1, 3 y 5 años",
         "decision": "cuándo renovar, por el año de vida en que sube el riesgo de cada modelo (plan, bloque 3)",
         "planteamiento": "config/metodo/plan_de_la_analitica.md, bloque 3; metodo/04_planteamientos.md §1.A",
         "funcion": "otra",
         "funcion_adaptada": ("tasa por año de edad con intervalo exacto de Poisson y supervivencia por tabla de vida con "
                              "entrada tardía, en lugar del kaplan_meier del 42.1: con entrada tardía, a edad 0 hay pocos "
                              "discos en riesgo y la curva de Kaplan-Meier cae de golpe (petición)"),
         "poblacion": {"regla": POBLACION + "; la edad es la de las horas encendido (reglas, apartado 3)", "periodo": periodo_todo,
                       "filas": int(len(dpt)), "unidad": "día de disco por año de edad; disco en la supervivencia",
                       "entidades": int(len(vida))},
         "medida": ("tasa anual por año de edad (0 a 10) desde dias_por_tramo; supervivencia S(k) = exp(−suma de las tasas "
                    "de los años 0 a k − 1), con la tasa de cada año = primeros fallos / años de exposición de vida_discos"),
         "minimo_casos": "20 fallos en el año de edad (reglas, apartado 7, cuestión 009)",
         "que_cambia_la_decision": ("el primer año de edad cuyo intervalo queda por encima del anterior marca cuándo sube "
                                    "el riesgo, y con él cuándo renovar"),
         "cifras": c3,
         "referencia": {"que_es": ("el año de edad anterior del mismo grupo (para «sube») y la tasa del conjunto de discos a la misma "
                                   "edad (para fabricantes y modelos), calculada con las mismas filas de dias_por_tramo"),
                        "valor": r(intervalo_poisson(sum(f["fallos"] for f in edad_todos), dias_dpt)[0]),
                        "dias_disco": r(dias_dpt, 1), "fallos": sum(f["fallos"] for f in edad_todos), "filas": int(len(dpt))},
         "comprobaciones": b3_comp, "motivos_null": {k: v for k, v in motivos_b3.items() if b3_comp[k] is None},
         "comprobaciones_extra": {"phi_minimo_uno": comp_phi([phi3])},
         "tablas": {"cinco_modelos": cinco, "phi": phi3,
                    "tasa_por_edad": {"todos": edad_todos, "todos_desaparecen_avisando": edad_sens,
                                      "fabricantes": edad_fab, "modelos": edad_mod},
                    "sube_distinto_contando_desaparecen": sube_distinto,
                    "supervivencia": {"todos": curva_json(t["sv_todos"], t["sv_todos_dpt"]),
                                      "todos_desaparecen_avisando": curva_json(t["sv_sens"], t["sv_sens_dpt"]),
                                      "todos_dias_por_tramo": {"s": t["sv_todos_dpt"]["s"],
                                                               "tasas": t["sv_todos_dpt"]["tasas"]},
                                      "modelos": {m: curva_json(t["sv_modelos"][m], t["sv_modelos_dpt"][m]) for m in cinco}},
                    "discos_8_o_mas": viejos,
                    "cobertura": {"dias_dias_por_tramo": r(dias_dpt, 1), "dias_recuento": recuento["dias_disco"],
                                  "parte": r(dias_dpt / recuento["dias_disco"]),
                                  "discos_con_exposicion": con_exposicion, "discos": int(len(vida)),
                                  "discos_edad_fin_menor_que_entrada": int((vida["edad_fin_anos"]
                                                                            < vida["edad_entrada_anos"]).sum())}}},
    ]
    return {"recuento_datos": recuento, "preguntas": preguntas, "segundas_vias": sv, "sin_conclusion": sin_conclusion}


# =================================================================================================================
# 12. Validaciones (método §7) y búsqueda de resultados escritos
# =================================================================================================================
def buscar_resultados_escritos(texto):
    """Líneas del código con una comprobación o validación puesta a True o con una cifra larga escrita.

    Cifras de cinco cifras o más: solo pasa el mínimo de días de las reglas (§7). Devuelve [(línea, texto)].
    """
    claves = "|".join(COMPROBACIONES + VALIDACIONES + EXTRAS + ["coinciden"])
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
# 13. Informe para la persona (transmision-conocimiento), generado del mismo diccionario
# =================================================================================================================
def pct(x, d=2):
    """Un porcentaje a la española, o «sin dato»."""
    return "sin dato" if x is None else numero(x, d, " %")


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
NOMBRES_VALIDACION = {"planteamiento_completo": "cada pregunta tiene su planteamiento completo",
                      "cifras_con_poblacion": "cada cifra dice su población, sus filas y su periodo",
                      "segunda_via": "cada cifra tiene su segunda vía, y coinciden",
                      "minimo_respetado": "ninguna conclusión sale de un grupo por debajo del mínimo",
                      "con_referencia": "cada resultado lleva su referencia, con las mismas filas",
                      "comprobaciones_calculadas": "las comprobaciones tienen su resultado o su motivo",
                      "reproducible": "dos cálculos seguidos dan las mismas cifras",
                      "sin_resultados_escritos": "el script no lleva ningún resultado escrito a mano",
                      "raw_intacto": "los ficheros de data/raw/ no cambian"}


def informe(j):
    """Texto Markdown del informe, con los apartados de resultado.md, a partir del JSON."""
    L = []
    est = j["resultado"]
    L.append("# Indicadores del conjunto de discos, los modelos y la edad de los discos")
    L.append("")
    L.append(f"Caso 68, paso 5, bloques 1 a 3 del plan de la analítica. Datos hasta el {fecha_es(j['fecha_datos'])}; "
             f"ejecutado el {fecha_es(j['fecha_ejecucion'])}. Estado: **{est['estado']}**, riesgo {est['riesgo']}.")
    L.append("")
    L.append(est["resumen"])
    L.append("")
    if "preguntas" not in j:
        L.append("## Por qué paró")
        L.append("")
        L.append(est["resumen"])
        for s in j.get("segundas_vias", []):
            if not s["coinciden"]:
                L.append(f"- La segunda vía «{s['nombre']}» no coincide: {s['diferentes']} claves distintas y "
                         f"{s['claves_en_una_sola_via']} en una sola vía.")
        for k, v in j.get("validaciones", {}).items():
            if v is False:
                L.append(f"- No se cumple que {NOMBRES_VALIDACION[k]}.")
        return "\n".join(L) + "\n"

    p = {q["id"]: q for q in j["preguntas"]}
    b1, b2, b3 = p["B1"]["tablas"], p["B2"]["tablas"], p["B3"]["tablas"]

    # Las preguntas y su planteamiento
    L.append("## Las preguntas y su planteamiento")
    L.append("")
    L.append("Las tres preguntas salen del plan de la analítica, aprobado por el responsable del caso el 16/11/2026, y del planteamiento "
             "1.A. La población es la misma en las tres: los discos de datos, sin los de arranque, del 01/01/2020 al "
             "30/06/2025. La tasa anual de fallo es 100 × 365 × fallos / días de disco, siempre con sus fallos y sus días.")
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

    # B1
    serie = b1["serie_mensual"]
    L.append("## B1 · Cómo es y cómo ha cambiado el conjunto de discos")
    L.append("")
    L.append(f"El conjunto de discos de datos pasó de {numero(serie[0]['discos'])} discos y {numero(serie[0]['pb'], 1)} PB "
             f"el {fecha_es(serie[0]['mes'])} a {numero(serie[-1]['discos'])} discos y {numero(serie[-1]['pb'], 1)} PB "
             f"el {fecha_es(serie[-1]['mes'])}. La serie de los {len(serie)} meses, por capacidad y por fabricante, está "
             "en el JSON para el gráfico de áreas.")
    L.append("")
    cu = b1["cuadre_discos"]
    L.append(f"Entre los {numero(cu['discos'])} discos que salen en los datos, {numero(cu['acaban_en_fallo'])} acaban "
             f"en un fallo, {numero(cu['desaparecen'])} desaparecen sin fallo y {numero(cu['siguen'])} siguen en la "
             f"última foto. El primer trimestre de 2020 no da altas: sus {numero(cu['altas_primer_trimestre_con_lo_anterior'])} "
             "discos incluyen todos los que ya estaban antes.")
    L.append("")
    L.append("| Trimestre | Altas | Fallos | Desaparecen sin fallo |")
    L.append("|---|---:|---:|---:|")
    altas = {a["trimestre"]: a["altas"] for a in b1["altas"]}
    for b in b1["bajas"]:
        nota = " (incompleto)" if b["incompleto"] else ""
        L.append(f"| {b['trimestre']} | {numero(altas[b['trimestre']]) if b['trimestre'] in altas else 'no se da'} | "
                 f"{numero(b['fallos'])} | {numero(b['desaparecen'])}{nota} |")
    L.append("")
    L.append(f"Los fallos de la tabla son todos los fallos ({numero(cu['fallos_de_la_serie'])}); "
             f"{numero(cu['fallos_que_no_son_el_primero_del_disco'])} son el segundo fallo de un disco que volvió.")
    L.append("")
    L.append("El modelo con más discos de cada año, en discos medios (días de disco del año entre los días del año en "
             "los datos):")
    L.append("")
    primeros = {}
    for f in b1["top10"]:
        primeros.setdefault(f["ano"], f)
    for a, f in primeros.items():
        nota = f", con {f['dias_del_ano_en_datos']} días" if f["parcial"] else ""
        L.append(f"- {a}{nota}: {f['model']}, {numero(f['discos_medios'])} discos medios; con días de disco de "
                 f"{f['primer_trimestre']} a {f['ultimo_trimestre']}.")
    L.append("")
    L.append("Los diez de cada año, con su primer y su último trimestre, están en el JSON. Un primer trimestre 2020T1 "
             "quiere decir que el modelo ya estaba antes de los datos, y un último 2025T2, que sigue.")
    L.append("")
    L.append("Reparto de los días de disco por centro desde julio de 2023, cuando el centro empieza a constar:")
    L.append("")
    anos_c = sorted({f["ano"] for f in b1["centros"]})
    centros = sorted({f["centro"] for f in b1["centros"]}, key=lambda c: (c == "sin dato", c))
    L.append("| Centro | " + " | ".join(f"{a}{' (parcial)' if any(f['parcial'] for f in b1['centros'] if f['ano'] == a) else ''}"
                                         for a in anos_c) + " |")
    L.append("|---|" + "---:|" * len(anos_c))
    for c in centros:
        celdas = []
        for a in anos_c:
            f = next((x for x in b1["centros"] if x["ano"] == a and x["centro"] == c), None)
            celdas.append(f"{numero(f['dias_disco'])} ({pct(f['pct_del_ano'], 1)})" if f else "sin días")
        L.append(f"| {c} | " + " | ".join(celdas) + " |")
    L.append("")
    seccion_comprobaciones(L, p["B1"])

    # B2
    rk = b2["ranking"]
    ref = b2["referencia_bruta"]
    ie = b2["a_igual_edad"]
    ve = ie["veredictos"]
    baja, alta = min(rk, key=lambda f: f["tasa"]), max(rk, key=lambda f: f["tasa"])
    L.append("## B2 · Qué modelos fallan más")
    L.append("")
    L.append(f"De los {b2['celdas_total']} años de modelo con días de disco, {b2['celdas_que_pasan']} pasan el mínimo de "
             f"50.000 días, de {len(rk)} modelos. Con esos años, la tasa bruta va del {pct(baja['tasa'])} del "
             f"{baja['model']} al {pct(alta['tasa'])} del {alta['model']}.")
    L.append("")
    L.append("Cada modelo se compara a igual edad y en los mismos trimestres (reglas, apartado 7): sus fallos frente a los que "
             "tendría con la tasa de cada año de edad y trimestre de todos los modelos del ranking juntos. La razón entre "
             "los dos dice cuánto falla por encima o por debajo de lo esperado a su edad, y el ranking se ordena por ella. "
             f"{ie['con_conclusion']} modelos tienen 20 fallos o más y llevan puesto; "
             f"{len(ie['sin_conclusion'])} no llegan y salen con su tasa, sin puesto y sin conclusión (cuestión 012).")
    L.append("")
    ph = ie["phi"]
    L.append(f"Los fallos de un modelo varían de un trimestre a otro más de lo que supone el intervalo de Poisson. Esa "
             f"variación de más, φ, vale {numero(ph['phi'], 4)} (medida en {numero(ph['celdas'])} celdas de modelo y "
             f"trimestre, con {numero(ph['gl'])} grados de libertad), y cada intervalo de la razón la lleva dentro: "
             "observados y esperados entre φ. La razón no cambia; el intervalo se ensancha.")
    L.append("")
    fa = ie["frente_al_metodo_anterior"]
    L.append(f"Frente a la comparación de antes, solo a igual edad y sin φ, cambian de veredicto {len(fa['cambian'])} "
             "modelos" + (": " + lista_y([f"{x['model']} (de {x['antes']} a {x['despues']})" for x in fa["cambian"]])
                          if fa["cambian"] else "") + ". La correlación de orden de Spearman entre las dos razones es de "
             f"{'sin dato' if fa['spearman_razon'] is None else numero(fa['spearman_razon'], 4)}.")
    L.append("")
    L.append(f"La comparación usa {numero(ie['dias'])} días de disco y {numero(ie['fallos'])} fallos, con una tasa del "
             f"{pct(ie['tasa_todos'], 4)}. Son {numero(ie['dias_ranking'] - ie['dias'])} días menos que los del ranking "
             f"({numero(ie['dias_ranking'])}), porque la tabla por año de edad deja fuera los días sin foto.")
    L.append("")
    L.append(f"A igual edad, {ve['por encima']} modelos fallan por encima de lo esperado, {ve['por debajo']} por debajo y "
             f"{ve['no se distingue']} no se distinguen. Solo por azar saldrían distintos unos "
             f"{numero(b2['esperados_por_azar'], 1)} de los {ie['con_conclusion']}, y salen {b2['distintos']}.")
    L.append("")
    cb = ie["cambian_frente_al_bruto"]
    L.append(f"Con la tasa bruta, el conjunto de discos de las mismas celdas falla al {pct(ref['valor'])} "
             f"({numero(ref['fallos'])} fallos en {numero(ref['dias_disco'])} días de disco). {cb['n']} modelos cambian de "
             "lectura entre esa comparación y la de igual edad. Las dos difieren por la edad media de cada modelo: la "
             "tasa bruta de un modelo joven se compara con discos más viejos, que fallan más, y la de uno viejo con "
             "discos más jóvenes.")
    L.append("")
    for x in cb["modelos"]:
        edad = "sin dato" if x["edad_media_anos"] is None else numero(x["edad_media_anos"], 2) + " años"
        L.append(f"- {x['model']}: edad media {edad}; con la tasa bruta, {x['bruto']}; a igual edad, {x['igual_edad']}.")
    if cb["modelos"]:
        L.append("")
    L.append("| Puesto | Modelo | Días de disco | Fallos | Edad media | Tasa bruta | Razón (intervalo al 95 %) | "
             "Tasa a igual edad | A igual edad | Bruta frente al conjunto |")
    L.append("|---:|---|---:|---:|---:|---:|---|---:|---|---|")
    for f in rk:
        edad = "sin dato" if f["edad_media_anos"] is None else numero(f["edad_media_anos"], 2)
        razon = ("sin dato" if f["razon"] is None else
                 f"{numero(f['razon'], 4)} ({numero(f['razon_desde'], 4)} a {numero(f['razon_hasta'], 4)})")
        L.append(f"| {f['puesto'] if f['puesto'] is not None else 'sin puesto'} | {f['model']} | "
                 f"{numero(f['dias_disco'])} | {numero(f['fallos'])} | {edad} | {pct(f['tasa'])} | {razon} | "
                 f"{pct(f['tasa_igual_edad'])} | {f['veredicto']} | {f['frente_a_todos']} |")
    L.append("")
    sp, spp = ie["spearman_tasa_razon"], ie["spearman_tasa_razon_con_puesto"]
    if sp is not None or spp is not None:
        L.append(f"La correlación de orden de Spearman entre la tasa bruta y la razón es de "
                 f"{'sin dato' if sp is None else numero(sp, 3)} con todos los modelos y de "
                 f"{'sin dato' if spp is None else numero(spp, 3)} con los que llevan puesto.")
        L.append("")
    es = ie["estabilidad"]
    sp_ = es["sin_parciales"]
    L.append(f"Si se quita cada modelo uno a uno y se rehacen las tasas por año de edad sin él, {es['retiradas_que_cambian']} "
             f"de las {len(es['retiradas'])} retiradas cambian el veredicto de algún otro modelo"
             + (f", como mucho {es['max_cambian']} (al quitar el {es['modelo_max']})." if es["modelo_max"] else ".")
             + (f" Sin {lista_y(sp_['anos_quitados'])}, el año parcial, cambian {sp_['cambian']}"
                + (f": {lista_y(sp_['modelos'])}." if sp_["modelos"] else ".") if sp_["anos_quitados"] else ""))
    L.append("")
    fu = b2["fuera_del_ranking"]
    L.append(f"Lo que no llega al mínimo se da aparte: {fu['celdas']} años de modelo con {numero(fu['dias_disco'])} días "
             f"de disco y {numero(fu['fallos'])} fallos; {fu['modelos_sin_ningun_ano']} modelos no llegan ningún año. "
             "La tabla de modelo por año, con la tasa de cada celda que pasa y el recuento de las que no, está en el "
             "JSON para el mapa de calor.")
    L.append("")
    fl = b2["todos_los_discos"]
    L.append(f"Por fabricante y por capacidad entran todos los discos de datos, y todos los discos juntos fallan al "
             f"{pct(fl['tasa'])} ({numero(fl['fallos'])} fallos en {numero(fl['dias_disco'])} días de disco). Cada grupo "
             "mezcla modelos de edades distintas, y por eso va con la edad media de sus días de disco al lado.")
    L.append("")
    for titulo, filas, suf in [("Fabricante", b2["por_fabricante"], ""), ("Capacidad", b2["por_capacidad"], " TB")]:
        L.append(f"| {titulo} | Días de disco | Fallos | Tasa | Intervalo al 95 % | Edad media | Frente al conjunto de discos |")
        L.append("|---|---:|---:|---:|---|---:|---|")
        for f in filas:
            g = f["grupo"] if isinstance(f["grupo"], str) else numero(f["grupo"], 0)
            edad = "sin dato" if f["edad_media_anos"] is None else numero(f["edad_media_anos"], 1) + " años"
            L.append(f"| {g}{suf} | {numero(f['dias_disco'])} | {numero(f['fallos'])} | {pct(f['tasa'])} | "
                     f"{pct(f['desde'])} a {pct(f['hasta'])} | {edad} | {f['frente_a_todos']} |")
        L.append("")
    seccion_comprobaciones(L, p["B2"])

    # B3
    ef = b3["tasa_por_edad"]["todos"]
    es = b3["tasa_por_edad"]["todos_desaparecen_avisando"]
    L.append("## B3 · A qué edad empiezan a fallar")
    L.append("")
    sube = [f["edad"] for f in ef if f["sube"]]
    L.append(f"La tasa del conjunto de discos va del {pct(ef[0]['tasa'])} con 0 años cumplidos al {pct(ef[5]['tasa'])} con 5. "
             + (f"Sube frente al año anterior, con intervalos que no se solapan, en los años de edad {lista_y(sube)}."
                if sube else "No sube en ningún año de edad con intervalos que no se solapen."))
    L.append("")
    p3 = b3["phi"]
    L.append(f"Cada intervalo de esta parte lleva φ = {numero(p3['phi'], 2)}, lo que varían los fallos de un modelo y año "
             f"de edad de un trimestre a otro más de lo que supone Poisson (medido en {numero(p3['celdas'])} celdas, con "
             f"{numero(p3['gl'])} grados de libertad). Fallos y días se dividen entre φ: la tasa no cambia y el intervalo "
             "se ensancha.")
    L.append("")
    L.append("Al lado va la misma tasa contando como fallo a los discos que desaparecen avisando, porque desaparecen "
             "más viejos y avisando más que el conjunto de discos (reglas, apartado 3).")
    L.append("")
    L.append("| Edad | Días de disco | Fallos | Tasa | Intervalo al 95 % | Frente al año anterior | Contando los que desaparecen avisando |")
    L.append("|---:|---:|---:|---:|---|---|---:|")
    for f, s in zip(ef, es):
        L.append(f"| {f['edad']} | {numero(f['dias_disco'])} | {numero(f['fallos'])} | {pct(f['tasa'])} | "
                 f"{pct(f['desde'])} a {pct(f['hasta'])} | {lectura(f)} | {pct(s['tasa'])} ({lectura(s)}) |")
    L.append("")
    if b3["sube_distinto_contando_desaparecen"]:
        L.append(f"Las dos cuentas dan una lectura distinta frente al año anterior en los años de edad "
                 f"{lista_y(b3['sube_distinto_contando_desaparecen'])}.")
        L.append("")
    for titulo, grupos in [("Por fabricante", b3["tasa_por_edad"]["fabricantes"]),
                           ("Los cinco modelos con más días de disco", b3["tasa_por_edad"]["modelos"])]:
        L.append(f"{titulo}, tasa por año de edad («s. c.»: menos de 20 fallos, sin conclusión; «↑»: sube frente al "
                 "año anterior):")
        L.append("")
        nombres = list(grupos)
        L.append("| Edad | " + " | ".join(nombres) + " |")
        L.append("|---:|" + "---:|" * len(nombres))
        for j_ in range(len(ef)):
            celdas = []
            for n in nombres:
                f = grupos[n][j_]
                if f["tasa"] is None:
                    celdas.append("sin días")
                else:
                    marca = " s. c." if f["sin_conclusion"] else (" ↑" if f["sube"] else "")
                    celdas.append(pct(f["tasa"]) + marca)
            L.append(f"| {j_} | " + " | ".join(celdas) + " |")
        L.append("")
    sv = b3["supervivencia"]
    L.append("La supervivencia sale de una tabla de vida: cada disco cuenta desde la edad que tenía al aparecer, los "
             "que desaparecen sin fallo quedan censurados y la vida acaba en el primer fallo.")
    L.append("")
    L.append("| Grupo | Discos | A 1 año | A 3 años | A 5 años | Corte |")
    L.append("|---|---:|---:|---:|---:|---|")
    grupos_sv = [("Todos los discos", sv["todos"]), ("Todos los discos, contando a los que desaparecen avisando", sv["todos_desaparecen_avisando"])]
    grupos_sv += list(sv["modelos"].items())
    for n, c in grupos_sv:
        vals = " | ".join(pct(None if c["s_en"][str(k)] is None else 100 * c["s_en"][str(k)]) for k in ANOS_S)
        L.append(f"| {n} | {numero(c['discos'])} | {vals} | {c['motivo_corte'] or 'sin corte hasta los 10 años'} |")
    L.append("")
    sd = sv["todos_dias_por_tramo"]["s"]
    L.append(f"Por la otra vía, con las tasas por edad de los días de disco, el conjunto de discos da {pct(100 * sd[1])}, "
             f"{pct(100 * sd[3])} y {pct(100 * sd[5])} a 1, 3 y 5 años. La diferencia con la tabla de vida queda por "
             "debajo de 0,5 puntos: una cuenta usa los días de las fotos y el primer fallo, y la otra los días del "
             "recuento y todos los fallos.")
    L.append("")
    v8 = b3["discos_8_o_mas"]
    L.append(f"El {fecha_es(v8['fecha'])} había {numero(v8['discos_8_o_mas'])} discos de 8 años o más, el "
             f"{pct(v8['pct'], 1)} de {numero(v8['discos_total'])}. La tasa del conjunto de discos en esas edades:")
    L.append("")
    for f in v8["tramos"]:
        L.append(f"- {f['edad']} años: {pct(f['tasa'])}, {numero(f['fallos'])} fallos en {numero(f['dias_disco'])} "
                 f"días de disco ({lectura(f)}).")
    L.append("")
    seccion_comprobaciones(L, p["B3"])

    # Lo que no saca conclusión
    L.append("## Lo que no saca conclusión")
    L.append("")
    L.append("Estos grupos se enseñan con su recuento y no se comparan. Los años de edad sin ningún día de disco no "
             "están aquí: salen como «sin días» en su tabla.")
    L.append("")
    sc = j["sin_conclusion"]
    for x in sc:
        if x["tipo"] == "celdas":
            L.append(f"- B2, {x['casos']} años de modelo por debajo de 50.000 días de disco: {numero(x['fallos'])} fallos "
                     f"en {numero(x['dias_disco'])} días de disco.")
    modelos_fuera = [x for x in sc if x["tipo"] == "modelo"]
    if modelos_fuera:
        L.append(f"- B2, {len(modelos_fuera)} modelos sin ningún año que llegue al mínimo: "
                 f"{numero(sum(x['fallos'] for x in modelos_fuera))} fallos en "
                 f"{numero(sum(x['dias_disco'] for x in modelos_fuera))} días de disco. La lista, modelo a modelo, está "
                 "en el JSON.")
    for x in sc:
        if x["tipo"] == "pocos fallos":
            L.append(f"- B2, {x['grupo']}: {numero(x['fallos'])} fallos en {numero(x['dias_disco'])} días de disco, tasa "
                     f"bruta del {pct(x['tasa'])}; menos de 20 fallos, sin puesto y sin conclusión (cuestión 012).")
    por_grupo = {}
    for x in sc:
        if x["tipo"] == "edad":
            por_grupo.setdefault(x["grupo"], []).append(x)
    for g, xs in por_grupo.items():
        partes = [f"{x['edad']} ({numero(x['fallos'])} en {numero(x['dias_disco'])} días)" for x in xs]
        L.append(f"- B3, {g}, años de edad con menos de 20 fallos: {lista_y(partes)}.")
    for x in sc:
        if x["tipo"] == "curva":
            L.append(f"- B3, supervivencia de {x['grupo']}: {x['motivo']}.")
    L.append("")

    # Validaciones
    L.append("## Validaciones")
    L.append("")
    L.append("| Validación | Resultado |")
    L.append("|---|---|")
    for k, v in j["validaciones"].items():
        L.append(f"| {NOMBRES_VALIDACION[k][0].upper() + NOMBRES_VALIDACION[k][1:]} | {'sí' if v else 'no'} |")
    L.append("")
    L.append("Cada cifra se rehízo desde otra tabla. Las segundas vías:")
    L.append("")
    L.append("| Cifra | Primera vía | Segunda vía | Comparación | Coinciden |")
    L.append("|---|---|---|---|---|")
    for s in j["segundas_vias"]:
        L.append(f"| {s['nombre']} | {s['via_1']} | {s['via_2']} | {s['comparacion']}, {s['claves']} claves, "
                 f"diferencia mayor {numero(s['max_diferencia'], 4)} | {'sí' if s['coinciden'] else 'no'} |")
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


def lectura(f):
    """Lectura de un año de edad frente al anterior, en palabras."""
    if f["sin_conclusion"]:
        return "sin conclusión"
    if f["sube"] is None:
        return "primer año" if f["fallos_anterior"] is None else "sin conclusión"
    return "sube" if f["sube"] else "baja" if f["baja"] else "no se distingue"


NOMBRES_EXTRA = {"veredicto_del_intervalo": "el veredicto a igual edad de cada modelo es el que dice el intervalo de "
                                           "su razón",
                 "esperados_suman_observados": ("los fallos esperados de todos los modelos suman los observados, como "
                                                "tiene que pasar por cómo se calculan (no es una segunda vía)"),
                 "phi_minimo_uno": "el φ usado es el medido y nunca menor que 1"}


def seccion_comprobaciones(L, q):
    """Las nueve comprobaciones de una pregunta y las de las peticiones 17 y 19, con su resultado o su motivo."""
    L.append(f"Las comprobaciones de {q['id']}:")
    L.append("")
    for k, v in q["comprobaciones"].items():
        texto = "sí" if v is True else "no" if v is False else "no aplica, porque " + q["motivos_null"][k]
        L.append(f"- {NOMBRES_COMPROBACION[k]}: {texto}.")
    for k, v in q.get("comprobaciones_extra", {}).items():
        L.append(f"- Del petición, {NOMBRES_EXTRA[k]}: {'sí' if v else 'no'}.")
    L.append("")


# =================================================================================================================
# 14. Ejecución
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
        {"nombre": "mínimo de días de disco en el año para un ranking", "valor": numero(MINIMO_DIAS_ANO),
         "origen": "reglas-negocio §7; sustituye al mínimo de 30 casos de el método, que cambian las reglas del caso"},
        {"nombre": "mínimo de fallos en un año de edad para sacar conclusión", "valor": numero(MINIMO_FALLOS_EDAD),
         "origen": "reglas-negocio §7, cuestión 009"},
        {"nombre": "mínimo de fallos de un modelo, en sus años que pasan el mínimo, para llevar puesto y sacar conclusión",
         "valor": numero(MINIMO_FALLOS_MODELO), "origen": "reglas-negocio §7, cuestión 012 (El responsable del caso, 18/11/2026)"},
        {"nombre": "comparación a igual edad y en el mismo trimestre",
         "valor": ("razón = fallos observados / esperados con la tasa de cada año de edad y trimestre de calendario de "
                   "las celdas de dias_por_tramo cuyo modelo y año pasan el mínimo, con todos los modelos juntos; "
                   "intervalo exacto de Poisson con observados y esperados entre φ; tasa a igual edad = razón × tasa de "
                   "todas las celdas"),
         "origen": ("reglas-negocio §7 («Una tasa por modelo se compara a igual edad y en el mismo trimestre», el responsable del caso, "
                    "18/11/2026); peticiones 17 y 19")},
        {"nombre": "φ de B2",
         "valor": ("chi2 de Pearson / grados de libertad en las celdas de modelo × trimestre, con los esperados de arriba "
                   "reescalados para que cada modelo sume sus fallos; gl = celdas − modelos; si sale menor que 1, vale 1"),
         "origen": "criterio técnico (reglas, apartado 7, una nota del caso y una nota del caso); petición 19"},
        {"nombre": "φ de B3",
         "valor": ("el mismo cálculo en las celdas de modelo × año de edad × trimestre de dias_por_tramo, con el esperado "
                   "= días × la tasa de su modelo y año de edad en todo el periodo; un solo φ para la tasa de cada año de "
                   "edad de todos los grupos y su «sube»"),
         "origen": "criterio técnico (reglas, apartado 7, una nota del caso y una nota del caso); petición 19"},
        {"nombre": "veredicto a igual edad",
         "valor": ("por encima o por debajo si el intervalo de la razón con φ queda entero a un lado de 1; si no, no se "
                   "distingue"),
         "origen": "peticiones 17 y 19"},
        {"nombre": "comparación con el método anterior",
         "valor": "la razón solo a igual edad y sin φ, al lado: los veredictos que cambian y la Spearman de las razones",
         "origen": "criterio, para que se vea qué mueve la petición 19"},
        {"nombre": "edad media de un modelo", "valor": "años cumplidos + 0,5, ponderados por días de disco, en sus celdas",
         "origen": "criterio: la misma edad media de fabricantes y capacidades de la petición 13"},
        {"nombre": "estabilidad de los veredictos a igual edad",
         "valor": "quitando cada modelo uno a uno, con las tasas por edad rehechas sin él, y sin el año parcial",
         "origen": "directriz 37 del auditor del cierre analítico; petición 17"},
        {"nombre": "correlación de Spearman entre la tasa bruta y la razón",
         "valor": "con todos los modelos que tienen razón y con los que llevan puesto",
         "origen": "criterio: la petición 17 no dice con cuáles, y se dan las dos"},
        {"nombre": "confianza de los intervalos", "valor": numero(CONFIANZA, 2),
         "origen": "parametros.md de el método y 42.6 del manual"},
        {"nombre": "intervalo de una tasa", "valor": "exacto de Poisson con scipy.stats.chi2",
         "origen": "criterio técnico, fijado en la petición"},
        {"nombre": "supervivencia", "valor": "tabla de vida con entrada tardía, años de edad 0 a 10",
         "origen": "criterio técnico, fijado en la petición"},
        {"nombre": "diferencia máxima entre las dos vías de la supervivencia",
         "valor": numero(TOLERANCIA_S_PUNTOS, 1) + " puntos",
         "origen": "la petición la fija para el conjunto de discos; el script aplica la misma a los cinco modelos y a la cifra que "
                   "cuenta a los que desaparecen avisando, por criterio"},
        {"nombre": "«baja» frente al año anterior", "valor": "el intervalo del año queda por debajo del anterior",
         "origen": "criterio, simétrico al «sube» de las reglas, apartado 7"},
        {"nombre": "días del año en los datos", "valor": "los del calendario, con 2025 del 01/01 al 30/06",
         "origen": "calendario.parquet; petición"},
        {"nombre": "modelos de cada año en B1 y modelos en B3", "valor": f"{N_TOP} y {N_MODELOS_EDAD}",
         "origen": "plan, bloques 1 y 3; petición"},
        {"nombre": "parte de cada centro en su año", "valor": "sobre todos los días del año, con «sin dato» dentro",
         "origen": "criterio: así las partes suman 100 y «sin dato» se ve con su peso"},
        {"nombre": "semilla", "valor": "no aplica", "origen": "ningún cálculo usa azar"},
    ]


def limites(res):
    """Los límites que salen de este cálculo, con sus cifras."""
    p = {q["id"]: q for q in res["preguntas"]}
    cu = p["B1"]["tablas"]["cuadre_discos"]
    cob = p["B3"]["tablas"]["cobertura"]
    sv = p["B3"]["tablas"]["supervivencia"]["todos"]["s_en"]
    sens = p["B3"]["tablas"]["supervivencia"]["todos_desaparecen_avisando"]["s_en"]
    cen = p["B1"]["tablas"]["centros_resumen"]
    dif = p["B3"]["tablas"]["sube_distinto_contando_desaparecen"]
    ie = p["B2"]["tablas"]["a_igual_edad"]
    return [
        "La comparación a igual edad corrige la edad de cada modelo y el trimestre de calendario, no su centro. Usa las "
        f"celdas por año de edad, que dejan fuera {numero(ie['dias_ranking'] - ie['dias'])} días de disco sin foto de "
        "los años que pasan el mínimo.",
        "Los intervalos de B2 y B3 llevan φ, medido con la variación entre trimestres; es un criterio técnico "
        "y no cambia ninguna razón ni ninguna tasa, solo lo ancho del intervalo.",
        f"{len(ie['sin_conclusion'])} modelos tienen menos de 20 fallos en sus años que pasan el mínimo: salen con su "
        "tasa, sus fallos y sus días, pero sin puesto y sin conclusión (cuestión 012).",
        "Las cifras describen el periodo del 01/01/2020 al 30/06/2025. Ninguna dice por qué un modelo, un fabricante o "
        "una edad falla más: solo valen verbos de asociación.",
        "2025 tiene seis meses. Sus discos medios, su columna del mapa y sus días por centro no se comparan con un año "
        "entero.",
        f"Las bajas sin fallo de {cu['trimestre_incompleto']} están incompletas: la última foto de los datos es del "
        f"{fecha_es(cu['ultima_foto_de_los_datos'])}, y un disco que la tiene cuenta como que sigue aunque se vaya en "
        "junio.",
        "Comparar fabricantes o capacidades mezcla modelos de edades distintas (reglas, apartado 7). La edad media al lado lo "
        "deja ver, pero no lo corrige.",
        f"El centro solo consta desde el 01/07/2023. Desde entonces, {numero(cen['dias_sin_dato'])} días de disco de "
        f"{numero(cen['dias_desde_sitio'])} vienen sin centro y se cuentan aparte.",
        f"La tasa por edad sale de dias_por_tramo, que reparte los días del recuento con las fotos de cada mes: deja "
        f"fuera {numero(cob['dias_recuento'] - cob['dias_dias_por_tramo'])} días de disco sin foto, "
        f"el {pct(100 * (1 - cob['parte']), 2)} del recuento. Los días por año de edad no tienen otra fuente exacta: se "
        "contrastan a través de la supervivencia.",
        f"En la supervivencia, {numero(cob['discos_edad_fin_menor_que_entrada'])} discos tienen la edad final por debajo "
        "de la de entrada (horas encendido que bajan, R-009) y no aportan exposición.",
        "Un disco que desaparece se cuenta como censurado: se sabe que llegó vivo a su última foto, no si se migró, se "
        "retiró sano o falló fuera de los datos, y eso no se puede saber. Contándolos como fallo cuando avisaban, la "
        f"supervivencia a 5 años pasa del {pct(None if sv['5'] is None else 100 * sv['5'])} al "
        f"{pct(None if sens['5'] is None else 100 * sens['5'])}"
        + (f", y la lectura frente al año anterior cambia en los años de edad {lista_y(dif)}." if dif else "."),
        "Si la tasa de los discos más viejos baja porque son los que han aguantado no se puede saber con estos datos: "
        "la tasa describe a los que quedan, y los datos no dicen por qué salieron los demás.",
        "Ninguna cifra se ha medido hacia adelante: la reserva, del 01/07/2025 al 30/06/2026, no se mira (reglas, apartado 5).",
        "Pendiente: el auditor sin memoria del cierre del paso (método §8) necesita el sí de el responsable del caso, porque es un agente.",
    ]


def escribir(raiz, j):
    """Escribe el JSON y el informe generado de él, en UTF-8 y sin NaN."""
    texto = json.dumps(nativo(j), ensure_ascii=False, indent=1, allow_nan=False)
    (raiz / SALIDA_JSON).write_text(texto, encoding="utf-8")
    (raiz / SALIDA_MD).write_text(informe(json.loads(texto)), encoding="utf-8")


def principal(raiz):
    """Lee, calcula dos veces, comprueba, valida y escribe; devuelve el código de salida."""
    inicio = time.time()
    j = {"metodo": "indicadores-y-analisis", "version_metodo": version_metodo(raiz), "script": SCRIPT, "peticion": PETICION,
         "fecha_datos": FECHA_DATOS.isoformat(), "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
         "entradas": [], "resultado": {}, "pendientes": []}
    h_antes = huellas_raw(raiz)
    try:
        j["exploratorios"] = comprobar_exploratorios(raiz)
        j["entradas"] = comprobar_huellas(raiz)
        d = leer(raiz)
        res = calcular(d)
        res2 = calcular(d)
        fuente = Path(__file__).read_text(encoding="utf-8")
        h_despues = huellas_raw(raiz)
        val = validar(res, fuente, h_antes, h_despues, res2)
        comp_falsas = [f"{q['id']}.{k}" for q in res["preguntas"]
                       for k, v in list(q["comprobaciones"].items()) + list(q.get("comprobaciones_extra", {}).items())
                       if v is False]
        sv_mal = [s["nombre"] for s in res["segundas_vias"] if not s["coinciden"]]
        cifras_mal = [f"{q['id']}: {c['nombre']}" for q in res["preguntas"] for c in q["cifras"] if c["coinciden"] is not True]
        j["huellas_raw"] = {"antes": h_antes, "despues": h_despues, "iguales": h_antes == h_despues}
        j["validaciones"] = val
        j["segundas_vias"] = res["segundas_vias"]
        if sv_mal or cifras_mal or comp_falsas or not all(val.values()):
            motivo = "; ".join(filter(None, [
                ("segundas vías que no coinciden: " + ", ".join(sv_mal)) if sv_mal else "",
                ("cifras sin segunda vía que coincida: " + ", ".join(cifras_mal[:10])) if cifras_mal else "",
                ("comprobaciones en rojo: " + ", ".join(comp_falsas)) if comp_falsas else "",
                ("validaciones en rojo: " + ", ".join(k for k, v in val.items() if not v)) if not all(val.values()) else ""]))
            raise Parada("ERROR", motivo)
        j.update({"recuento_datos": res["recuento_datos"], "preguntas": res["preguntas"],
                  "sin_conclusion": res["sin_conclusion"]})
        j["parametros"] = parametros()
        j["teoria"] = [
            {"apartado": "42.1", "por_que": "elegir la función por la pregunta; B1 no tiene función y va con consultas"},
            {"apartado": "38.1", "por_que": "el objetivo de negocio: reducir costes y alargar la vida útil"},
            {"apartado": "42.6", "por_que": "grupos frente al conjunto de discos con intervalo y cuántos saldrían por azar (B2)"},
            {"apartado": "4.2", "por_que": "los fallos por días de disco siguen una Poisson: de ahí el intervalo exacto"},
            {"apartado": "4.5", "por_que": "confianza del 95 % de todos los intervalos"},
            {"apartado": "4.7", "por_que": "el mínimo de casos no lo fija el manual: lo fijan las reglas del caso"},
            {"apartado": "4.11 y 4.12", "por_que": "se compara una tasa con otra por intervalos, no con una z de proporciones"},
            {"apartado": "11.10", "por_que": "ranking con empates por el método «min»"},
            {"apartado": "13.6 y 13.7", "por_que": "consultas agrupadas y conteos de B1"},
            {"apartado": "5.5", "por_que": "tasa de un grupo = suma de fallos / suma de días; cada tasa con su base"},
            {"apartado": "5.6", "por_que": ("Simpson: fabricante y capacidad mezclan edades, con la edad media al lado; "
                                            "cada modelo se compara a igual edad por estandarización indirecta")},
            {"apartado": "assets/18_consultas_interactivas.md §8, §9, §11, §13, §14 y §18",
             "por_que": "top N, framework agrupado, filtro por mínimo, tabla cruzada, tabla dinámica y el grano"},
        ]
        proteccion = (raiz / PROTECCION).exists()
        j["datos_personales_texto"] = [
            (f"{PROTECCION} existe: lo que dice va en el informe de la protección." if proteccion else
             f"No existe {PROTECCION}: los datos no pasaron por la protección."),
            "No hay datos de personas (reglas-negocio §9): el número de serie identifica un disco, no a una persona.",
            "Este cálculo usa el número de serie solo para contar discos y no deja ninguno en el JSON ni en el informe.",
        ]
        j["limites"] = limites(res)
        avisos = res["sin_conclusion"]
        sens = next(q for q in res["preguntas"] if q["id"] == "B3")["tablas"]["sube_distinto_contando_desaparecen"]
        n_cifras = sum(len(q["cifras"]) for q in res["preguntas"])
        cuenta = {k: sum(1 for x in avisos if x["tipo"] == k) for k in ["celdas", "modelo", "pocos fallos", "edad", "curva"]}
        celdas_fuera = sum(x["casos"] for x in avisos if x["tipo"] == "celdas")
        j["resultado"] = {
            "estado": "AVISO" if (avisos or sens) else "OK", "riesgo": "medio" if (avisos or sens) else "bajo",
            "resumen": (f"Tres bloques calculados con {n_cifras} cifras, todas con su segunda vía, y las nueve validaciones "
                        f"en verde. B2 compara cada modelo a igual edad y en los mismos trimestres, con φ en el "
                        f"intervalo, y ordena el ranking por la razón (peticiones 17 y 19). "
                        f"Sin conclusión por el mínimo: {celdas_fuera} años de modelo ({cuenta['modelo']} "
                        f"modelos sin ningún año en el ranking), {cuenta['pocos fallos']} modelos con menos de 20 fallos "
                        f"sin puesto (cuestión 012), {cuenta['edad']} años de edad de algún grupo con menos "
                        f"de 20 fallos y {cuenta['curva']} curvas de supervivencia cortadas"
                        + (f"; contar a los que desaparecen avisando cambia la lectura en los años de edad "
                           f"{lista_y(sens)}." if sens else ".")),
            "artefactos": [SALIDA_JSON, SALIDA_MD],
            "siguiente": ("bloques 4 a 9 del plan (coste, centros, avisos, tomos, otros factores y previsión), que leen "
                          "este JSON; antes, el auditor sin memoria del paso con el sí de el responsable del caso")}
        codigo = 0
    except Parada as e:
        j["resultado"] = {"estado": e.estado, "riesgo": "alto", "resumen": f"Paró con {e.estado}: {e.motivo}",
                          "artefactos": [SALIDA_JSON, SALIDA_MD], "siguiente": "corregir lo que dice el resumen"}
        codigo = 2
    except Exception as e:  # noqa: BLE001 - un fallo no previsto también deja el JSON con su estado
        j["resultado"] = {"estado": "ERROR", "riesgo": "alto",
                          "resumen": f"Falló: {type(e).__name__}: {e}", "artefactos": [SALIDA_JSON, SALIDA_MD],
                          "siguiente": "corregir el fallo", "traza": traceback.format_exc()[-3000:]}
        codigo = 1
    j["ejecucion"] = {"python": sys.executable, "version_python": platform.python_version(), "pandas": pd.__version__,
                      "numpy": np.__version__, "scipy": scipy.__version__,
                      "duracion_s": round(time.time() - inicio, 1)}
    escribir(raiz, j)
    print(f"{j['resultado']['estado']}: {j['resultado']['resumen']}")
    return codigo


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raiz", default=str(CASO), help="carpeta del caso (por defecto, la de este script)")
    sys.exit(principal(Path(ap.parse_args().raiz).resolve()))
