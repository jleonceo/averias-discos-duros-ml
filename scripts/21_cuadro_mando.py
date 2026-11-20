"""Cuadro de mando del caso 68 para la dirección de operaciones de los centros de datos.

Un solo HTML que se abre sin internet, con cinco pestañas (visión general, modelos, edad, centros de datos y lista de
riesgo) y cuatro filtros que valen para todas (fabricante, capacidad, años cumplidos y centro de datos). Los gráficos
son SVG dibujados por el JavaScript del propio HTML, porque los filtros los redibujan.

Lee, sin cambiarlos:
- informes/indicadores__discos_modelos_edad.json (scripts/09): B1 (discos el último mes), B2 (intervalo del ranking) y
  B3 (tasa por año de edad y su φ);
- informes/indicadores__coste_prevision.json (scripts/10): B4 (coste por terabyte y año de cada modelo);
- informes/indicadores__centros_avisos_tomos.json (scripts/11): B5 (fallos frente a los esperados por centro);
- informes/consultas-informe-ejecutivo.json (scripts/07): lo que costaron los fallos de 2024;
- informes/prueba_final.json (scripts/19): la lista de 100 frente a la regla de los cinco avisos SMART;
- data/processed/dias_por_tramo.parquet y dim_modelo.parquet: lo que se recalcula con un filtro;
- la última carpeta de data/predicciones/ con predicciones_2026-06.parquet y resumen_2026-06.json, la foto
  data/raw/reserva/fotos_mensuales/2026-06.parquet, data/raw/reserva/fallos.parquet y data/raw/reserva/ventanas_fallo/;
- para preparar la foto como produccion/ejecutar.py: data/raw/podado/ (fotos y ventanas) y las ventanas de la reserva;
  las fotos de la reserva anteriores a junio de 2026 no se leen (alcance de la petición, ver «historia_de_la_foto»).

Deja informes/cuadro_mando.html, informes/cuadro_mando.json e informes/cuadro_mando_lista.csv (la lista de 1.000 sin
filtros).

Orden: los JSON tienen que ser más nuevos que el script que los crea y las predicciones más nuevas que
produccion/ejecutar.py. dias_por_tramo y dim_modelo se comparan por huella con la que usaron los JSON de análisis.

Para sin escribir nada si: una entrada es más vieja que su script; un JSON de análisis no trae la fecha 2025-06-30; una
cifra repetida no es la de su JSON; la huella del modelo en uso no es la del resumen de la lista; una fila puntuada no
tiene foto; los días repartidos de las tasas filtradas no suman los de dias_por_tramo; la segunda vía de los tomos no
da lo mismo; o una validación lleva su resultado escrito. Si cambia la huella de data/, borra el HTML y el CSV y para.

Pruebas: tests/probar_21_cuadro_mando.py, tests/probar_21_cuadro_mando_pestanas.py y
tests/probar_21_cuadro_mando_navegador.py.

No importa ningún script numerado: lo que necesita de ellos va copiado con su origen en un comentario. Importa
scripts/pipeline_riesgo.py y produccion/ejecutar.py (su principal no se ejecuta al importarlo).

Uso, desde cualquier carpeta:
    python -W error scripts/21_cuadro_mando.py
"""

# =====================================================================================================================
# CONFIGURACIÓN
# =====================================================================================================================

# csv no hace falta: el CSV lo monta texto_csv, igual que el JavaScript, para que los dos den el mismo texto
# datetime pone la fecha de ejecución
import datetime as dt
# hashlib calcula las huellas de data/
import hashlib
# json lee las entradas y escribe el JSON del cuadro
import json
# math redondea la edad hacia abajo
import math
# re busca resultados escritos y palabras vetadas
import re
# time mide lo que tarda cada apartado de principal()
import time
# sys añade assets/, scripts/ y produccion/ a la ruta de importación y comprueba el intérprete
import sys
# Decimal redondea el CSV como Excel
from decimal import Decimal, ROUND_HALF_UP
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# Carpeta del caso, calculada desde el propio script para que funcione lo lance quien lo lance
RAIZ = Path(__file__).resolve().parents[1]
# Piezas comunes desde assets/, el módulo de producción desde scripts/ y la lectura de la historia desde produccion/
sys.path.insert(0, str(RAIZ / "assets"))
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "produccion"))

from graficos import numero  # noqa: E402
import pipeline_riesgo as pr  # noqa: E402
import ejecutar  # noqa: E402

# Intérprete del caso
# El entorno del caso, el que crea environment.yml: los scripts se lanzan dentro de él
ENTORNO = "68_averias_discos_duros"
SCRIPT = "scripts/21_cuadro_mando.py"
INFORMES = RAIZ / "informes"
SALIDA_HTML = INFORMES / "cuadro_mando.html"
SALIDA_JSON = INFORMES / "cuadro_mando.json"
SALIDA_CSV = INFORMES / "cuadro_mando_lista.csv"

# Fechas de los datos: las pestañas de análisis y la lista (petición)
FECHA_DATOS = "2025-06-30"
FECHA_LISTA = "2026-06-01"
FECHA_RESERVA = "2026-06-30"
# Los JSON de análisis y el de la prueba final
EDAD = "indicadores__discos_modelos_edad.json"
COSTE = "indicadores__coste_prevision.json"
CENTROS = "indicadores__centros_avisos_tomos.json"
EJECUTIVO = "consultas-informe-ejecutivo.json"
FINAL = "prueba_final.json"
ENTRADAS_ANALISIS = [EDAD, COSTE, CENTROS, EJECUTIVO]
# Tablas y ficheros de datos
DIAS_POR_TRAMO = "data/processed/dias_por_tramo.parquet"
DIM_MODELO = "data/processed/dim_modelo.parquet"
FOTO_LISTA = "data/raw/reserva/fotos_mensuales/2026-06.parquet"
FALLOS_RESERVA = "data/raw/reserva/fallos.parquet"
VENTANAS_RESERVA = "data/raw/reserva/ventanas_fallo"
FOTOS_PODADO = "data/raw/podado/fotos_mensuales"
VENTANAS_PODADO = "data/raw/podado/ventanas_fallo"
DECISIONES = "config/modelo/decisiones-correccion.json"
CONFIGURACION = "produccion/configuracion.json"
EJECUTAR = "produccion/ejecutar.py"
PREDICCIONES = "data/predicciones"
MES_LISTA = "2026-06"

# Periodos: el último año y el anterior (reglas, apartado 5) y el primer día con centro de datos (reglas, apartado 4)
INICIO_ULTIMO = pd.Timestamp("2024-07-01")
FIN_ULTIMO = pd.Timestamp("2025-06-01")
INICIO_ANTERIOR = pd.Timestamp("2023-07-01")
FIN_ANTERIOR = pd.Timestamp("2024-06-01")
INICIO_SITIO = pd.Timestamp("2023-07-01")
INICIO_DATOS = pd.Timestamp("2020-01-01")
# Mínimo para concluir: 50.000 días de disco en el año y 20 fallos (reglas, apartado 7 y cuestión 012)
MINIMO_DIAS_ANO = 50_000
MINIMO_FALLOS = 20
MINIMO_FALLOS_EDAD = 20
# Confianza de los intervalos, días por año de la tasa y años de edad (reglas, apartado 6 y §7; script 09)
CONFIANZA = 0.95
FACTOR_TASA = 100 * 365
EDADES = list(range(11))
# Años del periodo con centro de datos, como el script 11 (ANOS_SITIO)
ANOS_SITIO = 2
SIN_DATO = "sin dato"
# La ciudad de cada centro de datos (reglas de negocio §4, «Centro de datos»: deducida de los códigos de aeropuerto,
# ninguna fuente publica la tabla). La lee el HTML de los datos; la dirección de la página sigue con el código
CIUDADES = {"ams5": "Ámsterdam", "iad1": "Virginia", "phx1": "Phoenix", "sac0": "Sacramento", "sac2": "Sacramento",
            "yyz1": "Toronto"}
# Los cuatro datos de sitio que tiene que traer la fila de la que sale el tomo (scripts/05, SITIO y §7.3)
SITIO = ["datacenter", "vault_id", "pod_id", "pod_slot_num"]
# Tolerancia al comparar con los JSON, que guardan las cifras con diez decimales
TOLERANCIA = 1e-8
# Nombre de la regla, siempre entero (el responsable del caso, 19/11/2026)
REGLA = "regla de los cinco avisos SMART"
# Palabras vetadas en todo el cuadro (las del informe final, scripts/17)
PROHIBIDAS = [r"\bflota\b", r"\bparque\b", r"\bunidades\b", r"regla actual", r"gastar menos", r"\bbajar el coste",
              r"\bimpagad"]
# Las validaciones del JSON, que la prueba busca para que ninguna lleve su resultado escrito
VALIDACIONES = ["entradas_mas_nuevas", "fechas_iguales", "cifras_iguales_a_los_json", "huella_del_modelo",
                "filas_con_foto", "motivos_iguales", "edad_igual_con_toda_la_historia", "dias_repartidos_suman",
                "tomos_segunda_via", "huella_data_igual", "sin_resultados_escritos", "sin_palabras_vetadas"]


def reloj():
    """Una función que imprime los segundos desde la llamada anterior y el total, con el nombre del apartado."""
    inicio = [time.perf_counter()] * 2

    def marca(apartado):
        """Imprime lo que tardó el apartado que acaba."""
        ahora = time.perf_counter()
        print(f"tiempo {apartado}: {ahora - inicio[1]:.1f} s (total {ahora - inicio[0]:.1f} s)", flush=True)
        inicio[1] = ahora
    return marca


class Parada(Exception):
    """El cuadro no se escribe: algo de lo que comprueba no cuadra."""


# =====================================================================================================================
# AYUDAS
# =====================================================================================================================

def sha256(ruta):
    """SHA-256 de un fichero, leído por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def huella_data(raiz):
    """Huella de toda la carpeta data/: una línea por fichero con su huella, y la huella de esas líneas."""
    base = Path(raiz) / "data"
    lineas = [f"{p.relative_to(raiz).as_posix()} {sha256(p)}" for p in sorted(base.rglob("*")) if p.is_file()]
    return {"ficheros": len(lineas), "sha256": hashlib.sha256("\n".join(lineas).encode("utf-8")).hexdigest()}


def leer_json(ruta):
    """Un JSON en UTF-8."""
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def comprobar_orden(pares):
    """Para si alguna entrada es más vieja que el script que la crea. `pares`: [(entrada, script)]."""
    viejas = [str(e) for e, s in pares if Path(e).stat().st_mtime < Path(s).stat().st_mtime]
    if viejas:
        raise Parada(f"orden: estas entradas son más viejas que el script que las crea; relánzalo: {viejas}")
    return True


def pregunta(datos, ident):
    """La pregunta con ese id dentro de un JSON de indicadores (como scripts/17)."""
    encontradas = [p for p in datos["preguntas"] if p["id"] == ident]
    if len(encontradas) != 1:
        raise Parada(f"el JSON no trae la pregunta {ident}")
    return encontradas[0]


def nativo(x):
    """Valores de numpy y pandas a tipos de Python; NaN a None (un JSON no lleva NaN)."""
    if isinstance(x, dict):
        return {str(k): nativo(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [nativo(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if math.isnan(float(x)) else float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if x is pd.NA or x is pd.NaT:
        return None
    return x


def iguales(a, b, tolerancia=TOLERANCIA):
    """Dos cifras iguales con tolerancia relativa; vacío solo con vacío."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    return abs(float(a) - float(b)) <= tolerancia * max(1.0, abs(float(b)))


def concluye(dias_ano, fallos):
    """Cierto si un grupo tiene el mínimo para sacar conclusión: 50.000 días de disco en el año y 20 fallos."""
    return dias_ano >= MINIMO_DIAS_ANO and fallos >= MINIMO_FALLOS


def buscar_resultados_escritos(texto):
    """Líneas del código con una validación puesta a True (como buscar_resultados_escritos de scripts/09).

    Devuelve [(línea, texto)]; la prueba pide que el script no tenga ninguna.
    """
    claves = "|".join(VALIDACIONES)
    patron = re.compile(r"[\"'](" + claves + r")[\"']\s*\]?\s*[:=]\s*True\b|\b(" + claves + r")\s*=\s*True\b")
    return [(n, linea.strip()) for n, linea in enumerate(texto.splitlines(), 1) if patron.search(linea)]


def sin_prohibidas(texto):
    """Las palabras o frases vetadas que lleve un texto."""
    return sorted({m.group(0) for p in PROHIBIDAS for m in re.finditer(p, texto, flags=re.I)})


# =====================================================================================================================
# ESTADÍSTICA, COPIADA DE LOS SCRIPTS DE ANÁLISIS
# =====================================================================================================================

# Copiada letra a letra de scripts/09_indicadores_discos_modelos_edad.py, intervalo_poisson (la de B2.tablas.ranking)
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


# Copiada letra a letra de scripts/09_indicadores_discos_modelos_edad.py, frente_al_anterior
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


# Copiada letra a letra de scripts/09_indicadores_discos_modelos_edad.py, tasa_por_edad
def tasa_por_edad(dpt_grupo, columna_fallos="fallos", phi=1.0):
    """Días, fallos, tasa, intervalo con φ y «sube» por año de edad (0 a 10) de un grupo de dias_por_tramo."""
    a = dpt_grupo.groupby("edad_anos_cumplidos").agg(dias=("dias_disco", "sum"), f=(columna_fallos, "sum"))
    filas = [{"edad": j, "dias_disco": float(a.loc[j, "dias"]) if j in a.index else 0.0,
              "fallos": int(a.loc[j, "f"]) if j in a.index else 0} for j in EDADES]
    return frente_al_anterior(filas, MINIMO_FALLOS_EDAD, phi)


# Copiada letra a letra de scripts/09_indicadores_discos_modelos_edad.py, phi_poisson (igual en scripts/11)
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


# Copiada letra a letra de scripts/09_indicadores_discos_modelos_edad.py, phi_edad (el φ de B3)
def phi_edad(dpt):
    """φ de B3 y del minicubo (petición 19): celdas de modelo × año de edad × trimestre de dias_por_tramo, con el
    esperado de cada una = sus días × la tasa de su modelo y año de edad en todo el periodo; grupo, modelo y año de
    edad. Una fila sin días cuenta 0 días y sus fallos."""
    d = dpt.assign(dias=dpt["dias_disco"].fillna(0.0), q=dpt["mes"].dt.year * 10 + dpt["mes"].dt.quarter)
    g = d.groupby(["model", "edad_anos_cumplidos"])[["dias", "fallos"]].transform("sum")
    tasa = (g["fallos"] / g["dias"].where(g["dias"] > 0)).fillna(0.0)
    grupo = list(zip(d["model"], d["edad_anos_cumplidos"]))
    return phi_poisson(grupo, d["q"].tolist(), d["fallos"], d["dias"] * tasa)


# Copiada letra a letra de scripts/11_indicadores_centros_avisos_tomos.py, razon_poisson
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


# Copiada letra a letra de scripts/11_indicadores_centros_avisos_tomos.py, ajustada
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


# Copiada letra a letra de scripts/11_indicadores_centros_avisos_tomos.py, veredicto
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


def esperados_por_fila(dpt):
    """Los esperados de cada fila de dias_por_tramo: sus días × la tasa de su modelo, año de edad y trimestre con
    todos los centros juntos. Son las primeras líneas de ajustada() del script 11, copiadas, para que el cuadro pueda
    sumarlos con un filtro sin volver a Python. Un filtro de fabricante, capacidad o año de edad quita celdas enteras de
    modelo y año de edad, así que la tasa de las celdas que quedan no cambia (la prueba del navegador lo comprueba)."""
    d = dpt.assign(dias=dpt["dias_disco"].fillna(0.0), q=dpt["mes"].dt.year * 10 + dpt["mes"].dt.quarter)
    claves = ["model", "edad_anos_cumplidos", "q"]
    celda = d.groupby(claves).agg(dc=("dias", "sum"), fc=("fallos", "sum"))
    with np.errstate(divide="ignore", invalid="ignore"):
        celda["tasa"] = np.where(celda["dc"] > 0, celda["fc"] / celda["dc"], np.nan)
    d = d.join(celda["tasa"], on=claves)
    return pd.Series(np.where(d["dias"] > 0, d["dias"] * d["tasa"], 0.0), index=d.index)


# =====================================================================================================================
# LECTURA DE LAS ENTRADAS
# =====================================================================================================================

def leer_entradas(raiz):
    """Los JSON de entrada por nombre; para si falta alguno."""
    faltan = [n for n in ENTRADAS_ANALISIS + [FINAL] if not (Path(raiz) / "informes" / n).is_file()]
    if faltan:
        raise Parada(f"faltan entradas en informes/: {faltan}")
    return {n: leer_json(Path(raiz) / "informes" / n) for n in ENTRADAS_ANALISIS + [FINAL]}


def comprobar_fechas(entradas):
    """Para si un JSON de análisis no trae fecha_datos 2025-06-30 o el de la prueba final no trae 2026-06-30."""
    esperada = {n: FECHA_RESERVA if n == FINAL else FECHA_DATOS for n in entradas}
    distintas = {n: d.get("fecha_datos") for n, d in entradas.items() if d.get("fecha_datos") != esperada[n]}
    if distintas:
        raise Parada(f"fecha_datos distinta de la esperada ({FECHA_DATOS}; {FECHA_RESERVA} en la prueba final): {distintas}")
    return True


def leer_tramos(raiz):
    """dias_por_tramo con el fabricante y la capacidad de su modelo (dim_modelo, por model); solo discos de datos."""
    dpt = pd.read_parquet(Path(raiz) / DIAS_POR_TRAMO, columns=["model", "centro", "mes", "edad_anos_cumplidos",
                                                                 "fotos", "dias_disco", "fallos"])
    dpt["mes"] = dpt["mes"].astype("datetime64[ms]")
    dm = pd.read_parquet(Path(raiz) / DIM_MODELO, columns=["model", "capacidad_tb", "tipo_disco", "fabricante"])
    dp = dpt.merge(dm, on="model", how="left", validate="many_to_one")
    if dp["tipo_disco"].ne("datos").any() or dp["fabricante"].isna().any():
        raise Parada("dias_por_tramo trae un modelo que no es de datos o sin fabricante en dim_modelo")
    return dp.drop(columns=["tipo_disco"])


def leer_cifras(entradas):
    """Lo que el cuadro repite de los JSON: B1, B2, B3, B4, B5, el coste de 2024 y la prueba final."""
    c = {}
    b1 = pregunta(entradas[EDAD], "B1")["tablas"]
    c["discos_b1"] = {r["mes"]: r["discos"] for r in b1["serie_mensual"]}
    c["b2"] = pregunta(entradas[EDAD], "B2")["tablas"]["ranking"]
    b3 = pregunta(entradas[EDAD], "B3")["tablas"]
    c["b3"], c["b3_phi"] = b3["tasa_por_edad"]["todos"], b3["phi"]["phi"]
    b4 = pregunta(entradas[COSTE], "B4")["tablas"]
    c["b4"], c["b4_resumen"] = b4["ranking"], b4["resumen_ranking"]
    b5 = pregunta(entradas[CENTROS], "B5")["tablas"]
    c["b5"], c["b5_phi"] = b5["centros"], b5["phi"]["phi"]
    cifras = {x["nombre"]: x for x in entradas[EJECUTIVO]["cifras"]}
    for clave in ("coste_fallos_usd_2024", "coste_fallos_garantia_usd_2024"):
        if cifras[clave]["periodo"] != "año 2024":
            raise Parada(f"{clave} no es del año 2024")
    c["coste_2024"] = cifras["coste_fallos_usd_2024"]["valor"]
    c["coste_2024_garantia"] = cifras["coste_fallos_garantia_usd_2024"]["valor"]
    # La prueba final, como la página 8 del informe (scripts/17): media de los meses que se miden
    fin = entradas[FINAL]
    meses = [m for m in fin["por_mes"] if m["se_mide"]]
    c["final"] = {"meses": len(meses), "modelo_100": sum(m["modelo_lista_100"] for m in meses) / len(meses),
                  "regla_100": sum(m["regla_lista_100"] for m in meses) / len(meses),
                  "desde": meses[0]["mes"][:7], "hasta": meses[-1]["mes"][:7]}
    c["final_totales"] = {"modelo_100": fin["totales"]["modelo_lista_100"] / fin["totales"]["meses"],
                          "regla_100": fin["totales"]["regla_lista_100"] / fin["totales"]["meses"]}
    return c


# =====================================================================================================================
# LOS TOMOS EN PELIGRO EL 01/06/2026 (reglas, apartado 7, cuestión 004)
# =====================================================================================================================

def clave_tomo(centro, vault, ranura):
    """El tomo, centro|vault|ranura con números enteros (como la columna tomo de scripts/05, §7.3); None si falta uno."""
    if centro is None or pd.isna(centro) or pd.isna(vault) or pd.isna(ranura):
        return None
    return f"{centro}|{int(vault)}|{int(ranura)}"


def _leer_ventanas(raiz):
    """Las ventanas de fallo de la reserva, con las columnas del sitio, el modelo y la capacidad."""
    columnas = ["fecha", "date", "serial_number", "dia_fallo", "model", "capacity_bytes"] + SITIO
    rutas = sorted((Path(raiz) / VENTANAS_RESERVA).glob("*.parquet"))
    return pd.concat([pr._leer_columnas(r, columnas) for r in rutas], ignore_index=True)


def _filas_utiles(ventanas, mapeo):
    """Las filas de ventana con datos propios (su fecha es la de su texto; decisiones de la corrección, P-01) y el
    nombre del modelo corregido con el mapeo."""
    v = ventanas.copy()
    v["fecha"] = pd.to_datetime(v["fecha"]).astype("datetime64[ms]")
    v["dia_fallo"] = pd.to_datetime(v["dia_fallo"]).astype("datetime64[ms]")
    texto = pd.to_datetime(v["date"].astype(str), format="%Y-%m-%d", errors="coerce").astype("datetime64[ms]")
    v = v.loc[(texto == v["fecha"]).to_numpy()].copy()
    v["model"] = v["model"].replace(mapeo)
    return v


def _recuentos(f, plazo_max):
    """Lo que se cuenta aparte de los fallos que aún podían estar rehaciéndose: los de menos días que el plazo más
    largo de los discos de datos."""
    recientes = f.loc[(f["dias"] > 0) & (f["dias"] < plazo_max)]
    dentro = recientes["dias"] < recientes["plazo_dias"]
    return {"fallos_antes_de_la_fecha": int(len(f)), "plazo_mas_largo_dias": float(plazo_max),
            "recientes": int(len(recientes)),
            "sin_ventana": int(recientes["model"].isna().sum()),
            "sin_capacidad": int((recientes["model"].notna() & recientes["capacidad_tb"].isna()).sum()),
            "de_arranque": int((recientes["capacidad_tb"].notna() & ~recientes["datos"]).sum()),
            "de_datos_sin_tomo": int((recientes["datos"] & recientes["tomo"].isna() & dentro).sum()),
            "de_datos_rehaciendose": int((recientes["datos"] & recientes["tomo"].notna() & dentro).sum())}


def sitios_de_fallos(fallos, ventanas, mapeo, minimo, fecha, pares_extra=None):
    """Cada fallo anterior a `fecha` con su modelo, su capacidad, su plazo y su tomo; y lo que va aparte, contado.

    El tomo, copiado de scripts/05 §7.3: la última fila de su ventana hasta el día del fallo con los cuatro datos de
    SITIO no vacíos (datacenter, vault_id, pod_id y pod_slot_num); su clave es centro|vault|ranura. El modelo, el de la última fila de su
    ventana hasta el día del fallo (en el 05, la del día del fallo, que es esa misma cuando existe). La capacidad, la
    única válida de su modelo (reglas, apartado 3; pipeline_riesgo.capacidades_del_modelo) con las ventanas y la foto. El plazo,
    copiado de scripts/05 §7.7: capacidad_tb + 1.
    """
    fecha = pd.Timestamp(fecha)
    v = _filas_utiles(ventanas, mapeo)
    pares = v[["model", "capacity_bytes"]]
    if pares_extra is not None:
        pares = pd.concat([pares, pares_extra[["model", "capacity_bytes"]]], ignore_index=True)
    capacidad, _ = pr.capacidades_del_modelo(pares, minimo)
    f = fallos.copy()
    f["dia_fallo"] = pd.to_datetime(f["dia_fallo"]).astype("datetime64[ms]")
    f = f.loc[(f["dia_fallo"] < fecha).to_numpy()].drop_duplicates(["serial_number", "dia_fallo"]).copy()
    # 05 §7.3: la última fila hasta el día del fallo, y la última con los tres datos del sitio
    hasta = v.loc[(v["fecha"] <= v["dia_fallo"]).to_numpy()].sort_values(["serial_number", "dia_fallo", "fecha"],
                                                                          kind="mergesort")
    ultima = hasta.groupby(["serial_number", "dia_fallo"], sort=False).tail(1)[["serial_number", "dia_fallo", "model"]]
    con_sitio = hasta.loc[hasta[SITIO].notna().all(axis=1)]
    completa = con_sitio.groupby(["serial_number", "dia_fallo"], sort=False).tail(1).copy()
    completa["tomo"] = [clave_tomo(c, va, ra) for c, va, ra in
                        zip(completa["datacenter"], completa["vault_id"], completa["pod_slot_num"])]
    f = f.merge(ultima, on=["serial_number", "dia_fallo"], how="left", validate="one_to_one")
    f = f.merge(completa[["serial_number", "dia_fallo", "tomo", "datacenter"]], on=["serial_number", "dia_fallo"],
                how="left", validate="one_to_one")
    cap = f["model"].map(capacidad)
    f["capacidad_tb"] = [pr.capacidad_en_tb(x) if pd.notna(x) else np.nan for x in cap]
    f["datos"] = (cap > pr.LIMITE_ARRANQUE_BYTES).astype(bool).to_numpy()
    # 05 §7.7: el plazo de reconstrucción, un día por TB más uno
    f["plazo_dias"] = f["capacidad_tb"] + 1
    f["dias"] = (fecha - f["dia_fallo"]) / pd.Timedelta(days=1)
    datos_cap = [pr.capacidad_en_tb(x) for x in capacidad.values() if x > pr.LIMITE_ARRANQUE_BYTES]
    plazo_max = max(datos_cap) + 1 if datos_cap else 0.0
    return f.reset_index(drop=True), _recuentos(f, plazo_max)


def tomos_en_peligro(sitios, fecha):
    """Los tomos en peligro el día `fecha`: un disco de datos suyo falló antes y los días desde su fallo son menos que
    su plazo; el último día del plazo ya no cuenta (reglas, apartado 7, «Fallos que coinciden en un tomo»; cuestión 004)."""
    dias = (pd.Timestamp(fecha) - sitios["dia_fallo"]) / pd.Timedelta(days=1)
    en = sitios["datos"] & sitios["tomo"].notna() & (dias > 0) & (dias < sitios["plazo_dias"])
    return set(sitios.loc[en.to_numpy(), "tomo"])


def tomos_en_peligro_bucle(fallos, ventanas, mapeo, minimo, fecha, pares_extra=None):
    """Segunda vía de los tomos en peligro: fallo a fallo, en un bucle de Python, sin agrupar ni unir tablas.

    Sigue la misma regla que sitios_de_fallos y tomos_en_peligro; devuelve los tomos y los mismos recuentos aparte.
    """
    fecha = pd.Timestamp(fecha)
    v = _filas_utiles(ventanas, mapeo)
    # La capacidad válida de cada modelo, contada a mano
    validas = {}
    filas_pares = list(zip(v["model"], v["capacity_bytes"]))
    if pares_extra is not None:
        filas_pares += list(zip(pares_extra["model"], pares_extra["capacity_bytes"]))
    for modelo, c in filas_pares:
        if pd.notna(c) and c >= minimo:
            validas.setdefault(modelo, set()).add(float(c))
    unica = {m: next(iter(s)) for m, s in validas.items() if len(s) == 1}
    datos_cap = [pr.capacidad_en_tb(c) for c in unica.values() if c > pr.LIMITE_ARRANQUE_BYTES]
    plazo_max = max(datos_cap) + 1 if datos_cap else 0.0
    # Las filas de cada disco, en su orden
    por_disco = {}
    for fila in v.itertuples(index=False):
        por_disco.setdefault(fila.serial_number, []).append(fila)
    tomos = set()
    cuenta = {"fallos_antes_de_la_fecha": 0, "plazo_mas_largo_dias": float(plazo_max), "recientes": 0,
              "sin_ventana": 0, "sin_capacidad": 0, "de_arranque": 0, "de_datos_sin_tomo": 0,
              "de_datos_rehaciendose": 0}
    vistos = set()
    for serial, dia in zip(fallos["serial_number"], pd.to_datetime(fallos["dia_fallo"])):
        dia = pd.Timestamp(dia)
        if dia >= fecha or (serial, dia) in vistos:
            continue
        vistos.add((serial, dia))
        cuenta["fallos_antes_de_la_fecha"] += 1
        filas = sorted([x for x in por_disco.get(serial, []) if x.dia_fallo == dia and x.fecha <= dia],
                       key=lambda x: x.fecha)
        modelo = filas[-1].model if filas else None
        tomo = None
        for x in filas:
            if all(pd.notna(getattr(x, c)) for c in SITIO):
                tomo = clave_tomo(x.datacenter, x.vault_id, x.pod_slot_num)
        dias = (fecha - dia).days
        if not (0 < dias < plazo_max):
            continue
        cuenta["recientes"] += 1
        if modelo is None:
            cuenta["sin_ventana"] += 1
            continue
        if modelo not in unica:
            cuenta["sin_capacidad"] += 1
            continue
        if unica[modelo] <= pr.LIMITE_ARRANQUE_BYTES:
            cuenta["de_arranque"] += 1
            continue
        plazo = pr.capacidad_en_tb(unica[modelo]) + 1
        if dias < plazo:
            if tomo is None:
                cuenta["de_datos_sin_tomo"] += 1
            else:
                cuenta["de_datos_rehaciendose"] += 1
                tomos.add(tomo)
    return tomos, cuenta


# =====================================================================================================================
# LA LISTA DE RIESGO DEL 01/06/2026
# =====================================================================================================================

def carpeta_de_la_lista(raiz):
    """La última carpeta de data/predicciones/ que trae la predicción y el resumen de junio de 2026."""
    carpetas = [c for c in sorted((Path(raiz) / PREDICCIONES).iterdir()) if c.is_dir()
                and (c / f"predicciones_{MES_LISTA}.parquet").is_file() and (c / f"resumen_{MES_LISTA}.json").is_file()]
    if not carpetas:
        raise Parada(f"no hay ninguna carpeta en {PREDICCIONES} con la predicción y el resumen de {MES_LISTA}")
    return carpetas[-1]


def unir_foto(puntuadas, foto):
    """Une cada fila puntuada con su fila de la foto por serial_number; para si alguna no la encuentra."""
    sin = sorted(set(puntuadas["serial_number"]) - set(foto["serial_number"]))
    if sin:
        raise Parada(f"{len(sin)} filas puntuadas sin su fila en la foto, por ejemplo {sin[:3]}")
    return puntuadas.merge(foto, on="serial_number", how="left", validate="one_to_one")


def leer_lista(raiz, mapeo, minimo):
    """La lista de riesgo con el modelo, la capacidad, el fabricante, el centro y la edad de su foto preparada.

    La foto se prepara con pipeline_riesgo.preparar_foto como en produccion/ejecutar.py, con la historia de
    data/raw/podado/ (fotos y ventanas) y las ventanas de la reserva. Devuelve la tabla de las filas puntuadas y lo que
    se comprobó.
    """
    carpeta = carpeta_de_la_lista(raiz)
    resumen = leer_json(carpeta / f"resumen_{MES_LISTA}.json")
    pred = pd.read_parquet(carpeta / f"predicciones_{MES_LISTA}.parquet")
    info = {"carpeta": carpeta.relative_to(raiz).as_posix(), "huella_modelo_resumen": resumen["huella_modelo"],
            "huella_modelo_en_uso": pr.huella(Path(raiz) / leer_json(Path(raiz) / CONFIGURACION)["modelo_en_uso"]),
            "fecha_entrenamiento": resumen.get("fecha_entrenamiento")}
    if info["huella_modelo_resumen"] != info["huella_modelo_en_uso"]:
        raise Parada("la huella del modelo del resumen de la lista no es la del modelo en uso")
    columnas = ["fecha", "serial_number", "model", "capacity_bytes", "failure", "datacenter", "vault_id",
                "pod_slot_num", "smart_9_raw"] + pr.CONTADORES
    foto = pr.leer_foto(Path(raiz) / FOTO_LISTA, columnas)
    fecha = pd.Timestamp(FECHA_LISTA)
    # La historia guarda las filas anteriores solo de los discos sin horas: es lo único que el cuadro toma de ellas (su
    # primera foto da la edad). Las capacidades salen de todas las fotos igual. Con los 350.000 discos tardaba 160 s
    historia = ejecutar.leer_historia([Path(raiz) / FOTOS_PODADO],
                                      [Path(raiz) / VENTANAS_PODADO, Path(raiz) / VENTANAS_RESERVA],
                                      fecha, mapeo, set(foto.loc[foto["smart_9_raw"].isna(), "serial_number"]))
    df, motivo = pr.preparar_foto(foto, historia, mapeo, minimo)
    df = df.assign(motivo_cuadro=motivo)
    # Las filas puntuadas de la predicción (motivo vacío), cada una con su foto
    puntuadas = pred.loc[pred["motivo"].isna(), ["serial_number", "probabilidad", "en_lista_20", "en_lista_100",
                                                 "en_lista_500", "en_lista_1000"]]
    unida = unir_foto(puntuadas, df[["serial_number", "model", "capacidad_tb", "fabricante", "datacenter", "vault_id",
                                     "pod_slot_num", "edad_anos", "smart_9_raw", "motivo_cuadro"]])
    # Mismos motivos que la predicción, fila a fila por serial_number
    mot_pred = pred.set_index("serial_number")["motivo"].fillna("")
    mot_cuadro = df.set_index("serial_number")["motivo_cuadro"]
    info["motivos_iguales"] = bool(mot_pred.reindex(mot_cuadro.index).eq(mot_cuadro).all()
                                   and len(mot_pred) == len(mot_cuadro))
    info["filas"], info["puntuadas"] = int(len(pred)), int(len(puntuadas))
    info["sin_puntuar"] = {k: int(v) for k, v in pred["motivo"].value_counts().items()}
    info["filas_con_foto"] = bool(unida["model"].notna().all() and len(unida) == len(puntuadas))
    # La edad: sin horas y sin primera foto en la historia que se lee, el disco apareció después del 01/07/2025 y su año
    # cumplido es 0 con la historia entera también
    sin_horas = unida["smart_9_raw"].isna()
    con_primera = unida["serial_number"].isin(historia["primera_foto"].index)
    unida["edad"] = np.floor(unida["edad_anos"]).astype("int64")
    dudosas = sin_horas & ~con_primera
    info["sin_horas"] = int(sin_horas.sum())
    info["sin_horas_ni_primera_foto"] = int(dudosas.sum())
    info["edad_igual_con_toda_la_historia"] = bool((unida.loc[dudosas, "edad"] == 0).all())
    info["historia_de_la_foto"] = ("fotos de data/raw/podado/ (hasta junio de 2025) y ventanas de data/raw/podado/ y de "
                                   "la reserva; las fotos de la reserva de julio de 2025 a mayo de 2026 no se leen por el "
                                   "alcance de la petición. Solo cambian la edad de los discos sin horas que no salen en "
                                   "ninguna foto hasta junio de 2025: los dos casos tienen 0 años cumplidos")
    unida["tomo"] = [clave_tomo(c, v, r) for c, v, r in zip(unida["datacenter"], unida["vault_id"], unida["pod_slot_num"])]
    # El puesto en la foto entera: probabilidad de mayor a menor y empate por serial_number (como ejecutar.marcas)
    unida = unida.sort_values(["probabilidad", "serial_number"], ascending=[False, True], kind="mergesort")
    unida["puesto"] = np.arange(1, len(unida) + 1)
    info["listas_iguales_a_los_primeros"] = bool(all(
        unida[f"en_lista_{n}"].astype(int).to_numpy().tolist() == [1] * n + [0] * (len(unida) - n)
        for n in (20, 100, 500, 1000)))
    return unida.reset_index(drop=True), foto, info


# =====================================================================================================================
# DATOS DEL HTML
# =====================================================================================================================

def preparar_datos(dp, cifras, unida, peligro_tabla, aparte, conf):
    """Todo lo que el navegador necesita para filtrar sin volver a Python, como listas (sin NaN)."""
    modelos = sorted(set(dp["model"]) | {r["model"] for r in cifras["b4"]})
    dm = dp.drop_duplicates("model").set_index("model")
    filas_modelo = []
    for m in modelos:
        if m in dm.index:
            filas_modelo.append({"model": m, "fabricante": dm.loc[m, "fabricante"],
                                 "capacidad_tb": float(dm.loc[m, "capacidad_tb"])})
        else:
            raise Parada(f"el modelo {m} de B4 no está en dias_por_tramo: no se sabe su fabricante")
    indice_modelo = {m: i for i, m in enumerate(modelos)}
    centros = sorted(set(dp["centro"]) - {SIN_DATO})
    if set(centros) != set(CIUDADES):
        raise Parada(f"los centros de los datos no son los de la tabla de ciudades: {centros}")
    indice_centro = {c: i for i, c in enumerate(centros)}
    meses = sorted(dp["mes"].unique())
    indice_mes = {m: i for i, m in enumerate(meses)}
    sitio = dp["mes"] >= INICIO_SITIO
    esp = pd.Series(0.0, index=dp.index)
    esp.loc[sitio] = esperados_por_fila(dp.loc[sitio])
    tramos = {"modelo": [indice_modelo[m] for m in dp["model"]],
              "centro": [indice_centro.get(c, -1) for c in dp["centro"]],
              "mes": [indice_mes[m] for m in dp["mes"]],
              "edad": dp["edad_anos_cumplidos"].astype(int).tolist(),
              "fotos": dp["fotos"].astype(int).tolist(),
              "dias": dp["dias_disco"].fillna(0.0).astype(float).tolist(),
              "fallos": dp["fallos"].astype(int).tolist(),
              "esp": esp.astype(float).tolist()}
    b4 = [{k: r[k] for k in ("model", "capacidad_tb", "ano_compra", "dias_disco", "fallos", "tasa", "coste_tb_ano",
                             "coste_desde", "coste_hasta", "parte_fallos_pct", "puesto", "anos_que_pasan")}
          for r in sorted(cifras["b4"], key=lambda r: (r["coste_tb_ano"], r["model"]))]
    b5 = [{"centro": r["centro"], "observados": r["observados"], "esperados": r["esperados"], "dias": r["dias_tramos"],
           "razon": r["razon"], "razon_desde": r["razon_desde"], "razon_hasta": r["razon_hasta"],
           "veredicto": r["veredicto"]} for r in cifras["b5"]]
    b3 = [{k: r[k] for k in ("edad", "dias_disco", "fallos", "tasa", "desde", "hasta", "sin_conclusion", "sube",
                             "baja")} for r in cifras["b3"]]
    # La lista de 1.000, una fila por disco como lista; col dice la posición de cada campo
    col = ["puesto", "serial_number", "model", "fabricante", "capacidad_tb", "centro", "vault", "ranura", "edad",
           "tomo_en_peligro", "probabilidad", "en_20", "en_100", "en_500"]
    mil = unida.loc[unida["en_lista_1000"] == 1]
    filas = []
    for x in mil.itertuples(index=False):
        estado = "Sin tomo" if x.tomo is None else ("Sí" if x.tomo in peligro_tabla["tomos"] else "No")
        filas.append([int(x.puesto), x.serial_number, x.model, x.fabricante, float(x.capacidad_tb), x.datacenter,
                      None if pd.isna(x.vault_id) else int(x.vault_id),
                      None if pd.isna(x.pod_slot_num) else int(x.pod_slot_num), int(x.edad), estado,
                      float(x.probabilidad), int(x.en_lista_20), int(x.en_lista_100), int(x.en_lista_500)])
    # Los discos puntuados de la foto por fabricante, capacidad, año cumplido y centro, para la línea «Viendo»
    rec = unida.groupby(["fabricante", "capacidad_tb", "edad", "datacenter"]).size().reset_index(name="n")
    recuento = [[x.fabricante, float(x.capacidad_tb), int(x.edad), x.datacenter, int(x.n)] for x in rec.itertuples()]
    q = [int(pd.Timestamp(m).year * 10 + pd.Timestamp(m).quarter) for m in meses]
    return nativo({
        "fecha_datos": FECHA_DATOS, "fecha_lista": FECHA_LISTA,
        "minimo_dias_ano": MINIMO_DIAS_ANO, "minimo_fallos": MINIMO_FALLOS, "anos_sitio": ANOS_SITIO,
        "modelos": filas_modelo, "fabricantes": sorted({r["fabricante"] for r in filas_modelo}),
        "capacidades": sorted({r["capacidad_tb"] for r in filas_modelo}), "edades": EDADES, "centros": centros,
        "ciudades": CIUDADES,
        "meses": [pd.Timestamp(m).strftime("%Y-%m-%d") for m in meses], "trimestres_de_mes": q,
        "i_ultimo": [indice_mes[INICIO_ULTIMO], indice_mes[FIN_ULTIMO]],
        "i_anterior": [indice_mes[INICIO_ANTERIOR], indice_mes[FIN_ANTERIOR]],
        "i_sitio": indice_mes[INICIO_SITIO],
        "dias_periodo": int((pd.Timestamp(FECHA_DATOS) - INICIO_DATOS).days + 1),
        "dias_periodo_sitio": int((pd.Timestamp(FECHA_DATOS) - INICIO_SITIO).days + 1),
        "tramos": tramos, "coste_2024": cifras["coste_2024"], "coste_2024_garantia": cifras["coste_2024_garantia"],
        "b4": b4, "b3": b3, "b3_phi": cifras["b3_phi"], "b5": b5, "b5_phi": cifras["b5_phi"],
        "lista": {"col": col, "filas": filas, "listas": conf["listas"], "principal": conf["lista_principal"],
                  "recuento": recuento},
        "tomos": {"en_peligro": peligro_tabla["por_tomo"], "fallos": peligro_tabla["fallos"], "aparte": aparte},
        "final": cifras["final"]})


# =====================================================================================================================
# RESUMEN EN PYTHON: LAS CIFRAS DE ARRIBA PARA CUALQUIER FILTRO (lo que compara la prueba del navegador)
# =====================================================================================================================

def _arrays(datos):
    """Las columnas de los tramos como arrays de numpy, guardadas en los datos para no rehacerlas."""
    if "_np" not in datos:
        t = datos["tramos"]
        mod = datos["modelos"]
        fab = np.array([m["fabricante"] for m in mod], dtype=object)
        cap = np.array([m["capacidad_tb"] for m in mod], dtype=float)
        im = np.asarray(t["modelo"], dtype=np.int64)
        datos["_np"] = {"fab": fab[im], "cap": cap[im], "centro": np.asarray(t["centro"], dtype=np.int64),
                        "mes": np.asarray(t["mes"], dtype=np.int64), "edad": np.asarray(t["edad"], dtype=np.int64),
                        "fotos": np.asarray(t["fotos"], dtype=np.int64), "dias": np.asarray(t["dias"], dtype=float),
                        "fallos": np.asarray(t["fallos"], dtype=np.int64), "esp": np.asarray(t["esp"], dtype=float),
                        "q": np.asarray(datos["trimestres_de_mes"], dtype=np.int64)[np.asarray(t["mes"])]}
    return datos["_np"]


def mascara(datos, f, con_centro=True):
    """Las filas de los tramos que pasan los filtros; sin el de centro si `con_centro` es falso."""
    a = _arrays(datos)
    m = np.ones(len(a["mes"]), dtype=bool)
    if f.get("fabricante") is not None:
        m &= a["fab"] == f["fabricante"]
    if f.get("capacidad") is not None:
        m &= a["cap"] == float(f["capacidad"])
    if f.get("edad") is not None:
        m &= a["edad"] == int(f["edad"])
    if con_centro and f.get("centro") is not None:
        c = datos["centros"].index(f["centro"]) if f["centro"] in datos["centros"] else -2
        m &= a["centro"] == c
    return m


def dias_de(datos, f):
    """Días de disco de los tramos que pasan los filtros, en todo el periodo."""
    return float(_arrays(datos)["dias"][mascara(datos, f)].sum())


def filas_edad(datos, f):
    """La tasa por año de edad: la de B3 sin filtros; con un filtro, recalculada con frente_al_anterior y el φ de B3."""
    if not any(f.get(k) is not None for k in ("fabricante", "capacidad", "edad", "centro")):
        return [dict(r) for r in datos["b3"]]
    a = _arrays(datos)
    m = mascara(datos, f)
    filas = [{"edad": j, "dias_disco": float(a["dias"][m & (a["edad"] == j)].sum()),
              "fallos": int(a["fallos"][m & (a["edad"] == j)].sum())} for j in EDADES]
    return frente_al_anterior(filas, MINIMO_FALLOS_EDAD, datos["b3_phi"])


def gris_edad(datos, f, fila):
    """Cierto si un año de edad va sin conclusión: menos de 20 fallos o de 50.000 días de disco al año."""
    dias_periodo = datos["dias_periodo_sitio"] if f.get("centro") is not None else datos["dias_periodo"]
    return fila["sin_conclusion"] or fila["dias_disco"] / (dias_periodo / 365) < MINIMO_DIAS_ANO


def centros_por_fila(datos, f):
    """Fallos observados frente a los esperados de cada centro con un filtro de fabricante, capacidad o año de edad.

    Suma los esperados por fila (esperados_por_fila) y mide φ con phi_poisson en las celdas centro × trimestre; el
    intervalo y el veredicto, con razon_poisson y veredicto copiadas del script 11.
    """
    a = _arrays(datos)
    m = mascara(datos, f, con_centro=False) & (a["mes"] >= datos["i_sitio"])
    constan = m & (a["centro"] >= 0)
    ph = phi_poisson(a["centro"][constan].tolist(), a["q"][constan].tolist(), a["fallos"][constan], a["esp"][constan])
    salida = {}
    for i, c in enumerate(datos["centros"] + [SIN_DATO]):
        en = m & (a["centro"] == (i if c != SIN_DATO else -1))
        obs, esp, dias = int(a["fallos"][en].sum()), float(a["esp"][en].sum()), float(a["dias"][en].sum())
        rz, lo, hi = razon_poisson(obs, esp, phi=ph["phi"]) if esp > 0 else (None, None, None)
        v = (veredicto(c, dias / ANOS_SITIO, obs, lo, hi) if lo is not None
             else ("aparte" if c == SIN_DATO else "sin conclusión"))
        salida[c] = {"centro": c, "observados": obs, "esperados": esp, "dias": dias, "razon": rz, "razon_desde": lo,
                     "razon_hasta": hi, "veredicto": v}
    salida["_phi"] = ph["phi"]
    return salida


def filas_centros(datos, f):
    """Los centros que se ven: los de B5 sin filtros de fabricante, capacidad ni edad; si no, recalculados."""
    if any(f.get(k) is not None for k in ("fabricante", "capacidad", "edad")):
        por = centros_por_fila(datos, f)
        filas = [por[c] for c in datos["centros"]]
    else:
        filas = [dict(r) for r in datos["b5"] if r["centro"] != SIN_DATO]
    if f.get("centro") is not None:
        filas = [r for r in filas if r["centro"] == f["centro"]]
    return filas


def filas_lista(datos, f):
    """Los discos de la lista elegida que pasan los filtros, por puesto, como diccionarios."""
    col = datos["lista"]["col"]
    n = int(f.get("lista") or datos["lista"]["principal"])
    salida = []
    for fila in datos["lista"]["filas"]:
        x = dict(zip(col, fila))
        en = {20: x["en_20"], 100: x["en_100"], 500: x["en_500"], 1000: 1}[n]
        if not en:
            continue
        if f.get("fabricante") is not None and x["fabricante"] != f["fabricante"]:
            continue
        if f.get("capacidad") is not None and x["capacidad_tb"] != float(f["capacidad"]):
            continue
        if f.get("edad") is not None and x["edad"] != int(f["edad"]):
            continue
        if f.get("centro") is not None and x["centro"] != f["centro"]:
            continue
        salida.append(x)
    return sorted(salida, key=lambda x: x["puesto"])


def resumen(datos, f):
    """Las cifras de arriba de las cinco pestañas para unos filtros, calculadas en Python: {pestaña: [{id, valor}]}."""
    a = _arrays(datos)
    m = mascara(datos, f)
    # Visión general
    iu0, iu1 = datos["i_ultimo"]
    ia0, ia1 = datos["i_anterior"]
    u = m & (a["mes"] >= iu0) & (a["mes"] <= iu1)
    fallos_u, dias_u = int(a["fallos"][u].sum()), float(a["dias"][u].sum())
    tasa_u = intervalo_poisson(fallos_u, dias_u)[0] if dias_u > 0 else None
    vision = [{"id": "discos", "valor": int(a["fotos"][m & (a["mes"] == iu1)].sum())},
              {"id": "fallos", "valor": fallos_u}, {"id": "tasa", "valor": tasa_u},
              {"id": "coste", "valor": datos["coste_2024"]}]
    # Modelos: B4, con los filtros de fabricante y capacidad
    fab = {r["model"]: r["fabricante"] for r in datos["modelos"]}
    filas4 = [r for r in datos["b4"] if (f.get("fabricante") is None or fab[r["model"]] == f["fabricante"])
              and (f.get("capacidad") is None or r["capacidad_tb"] == float(f["capacidad"]))]
    con = [r for r in filas4 if r["puesto"] is not None]
    modelos = [{"id": "modelos", "valor": len(filas4)},
               {"id": "coste_min", "valor": min(r["coste_tb_ano"] for r in con) if con else None},
               {"id": "mediana_fallos", "valor": float(np.median([r["parte_fallos_pct"] for r in con])) if con else None}]
    # Edad
    fe = filas_edad(datos, f)
    gris = [gris_edad(datos, f, r) for r in fe]
    sube = [j for j in range(1, len(fe)) if fe[j]["sube"] and not gris[j] and not gris[j - 1]]
    edad = [{"id": "tasa_0", "valor": fe[0]["tasa"]}, {"id": "tasa_5", "valor": fe[5]["tasa"]},
            {"id": "anos_sube", "valor": len(sube)}]
    # Centros de datos
    fc = filas_centros(datos, f)
    centros = [{"id": "centros_mas", "valor": sum(r["veredicto"] == "falla más por sí mismo" for r in fc)},
               {"id": "centros_menos", "valor": sum(r["veredicto"] == "falla menos" for r in fc)},
               {"id": "fallos_centros", "valor": int(sum(r["observados"] for r in fc))}]
    # Lista de riesgo
    tomos = [t for t in datos["tomos"]["en_peligro"] if f.get("centro") is None or t["centro"] == f["centro"]]
    lista = [{"id": "discos_lista", "valor": len(filas_lista(datos, f))}, {"id": "tomos_peligro", "valor": len(tomos)},
             {"id": "final_100", "valor": datos["final"]["modelo_100"]}]
    return {"vision": vision, "modelos": modelos, "edad": edad, "centros": centros, "lista": lista}


def combinacion_mas_estrecha(datos):
    """La combinación con los cuatro filtros puestos que menos días de disco tiene de julio de 2024 a junio de 2025,
    con alguno; a igualdad, la primera en el orden de los filtros."""
    a = _arrays(datos)
    iu0, iu1 = datos["i_ultimo"]
    u = (a["mes"] >= iu0) & (a["mes"] <= iu1) & (a["centro"] >= 0)
    t = pd.DataFrame({"fabricante": a["fab"][u], "capacidad": a["cap"][u], "edad": a["edad"][u],
                      "centro": [datos["centros"][i] for i in a["centro"][u]], "dias": a["dias"][u]})
    g = t.groupby(["fabricante", "capacidad", "edad", "centro"], sort=True)["dias"].sum()
    g = g[g > 0]
    orden = g.reset_index().sort_values(["dias", "fabricante", "capacidad", "edad", "centro"], kind="mergesort")
    x = orden.iloc[0]
    return {"fabricante": x["fabricante"], "capacidad": float(x["capacidad"]), "edad": int(x["edad"]),
            "centro": x["centro"]}


# =====================================================================================================================
# CSV
# =====================================================================================================================

def decimal_csv(x, decimales):
    """Un número con coma decimal y sin punto de miles, redondeado como Excel sobre su texto (como numero de assets)."""
    paso = Decimal(1).scaleb(-decimales)
    return str(Decimal(repr(float(x))).quantize(paso, rounding=ROUND_HALF_UP)).replace(".", ",")


def _capacidad_texto(c):
    """La capacidad en TB: entera sin decimales; si no, con un decimal."""
    return str(int(c)) if float(c).is_integer() else decimal_csv(c, 1)


def _seleccion(f):
    """Los filtros puestos, en palabras, en el orden de los filtros."""
    partes = []
    if f.get("centro") is not None:
        partes.append(f"{CIUDADES[f['centro']]} · {f['centro']}")
    if f.get("fabricante") is not None:
        partes.append(f["fabricante"])
    if f.get("capacidad") is not None:
        partes.append(_capacidad_texto(f["capacidad"]) + " TB")
    if f.get("edad") is not None:
        partes.append("1 año cumplido" if int(f["edad"]) == 1 else f"{int(f['edad'])} años cumplidos")
    return partes


def nombre_csv(lista, f, fecha):
    """El nombre del CSV: lista_100_sac2_seagate_16tb_edad-3_datos-2026-06-01.csv, con los filtros que haya."""
    partes = [f"lista_{int(lista)}"]
    if f.get("centro") is not None:
        partes.append(str(f["centro"]).lower())
    if f.get("fabricante") is not None:
        partes.append(str(f["fabricante"]).lower())
    if f.get("capacidad") is not None:
        partes.append(_capacidad_texto(f["capacidad"]).replace(",", "-") + "tb")
    if f.get("edad") is not None:
        partes.append(f"edad-{int(f['edad'])}")
    return "_".join(partes) + f"_datos-{fecha}.csv"


# Columnas de lo general a lo particular (centro, tomo con su vault y su ranura, modelo, edad y disco); la puntuación de
# riesgo, que ordena la lista, la última. Es la salida del modelo por 100: no está calibrado y no es una probabilidad
CABECERA_CSV = ["Puesto", "Centro de datos", "Ciudad", "Tomo en peligro", "Vault", "Ranura", "Fabricante", "Modelo",
                "Capacidad (TB)", "Años cumplidos", "Número de serie", "Puntuación de riesgo (0 a 100)"]


def texto_csv(filas, lista, f, fecha):
    """El CSV de la lista: la selección en la primera línea, punto y coma, coma decimal y la puntuación de 0 a 100."""
    dia = pd.Timestamp(fecha).strftime("%d/%m/%Y")
    lineas = [" · ".join([f"Lista de {int(lista)}"] + _seleccion(f) + [f"datos a {dia}"]), ";".join(CABECERA_CSV)]
    for x in filas:
        lineas.append(";".join([str(int(x["puesto"])), x["centro"] or "", CIUDADES.get(x["centro"], ""),
                                x["tomo_en_peligro"], "" if x["vault"] is None else str(int(x["vault"])),
                                "" if x["ranura"] is None else str(int(x["ranura"])), x["fabricante"], x["model"],
                                _capacidad_texto(x["capacidad_tb"]), str(int(x["edad"])), x["serial_number"],
                                decimal_csv(x["probabilidad"] * 100, 2)]))
    return "\r\n".join(lineas) + "\r\n"


# =====================================================================================================================
# HTML: estilos, esqueleto y JavaScript
# =====================================================================================================================

CSS = """
html, body { margin: 0; background: #ffffff; color: #0b0b0b; }
body { font-family: "Segoe UI", system-ui, sans-serif; font-size: 15px; line-height: 1.4; font-variant-numeric: tabular-nums; }
* { box-sizing: border-box; }
.barra { display: flex; align-items: baseline; gap: 28px; padding: 10px 40px 6px; border-bottom: 1px solid #e1e0d9; }
.barra .nombre { font-weight: 700; font-size: 16px; white-space: nowrap; }
.barra [role=tablist] { display: flex; gap: 22px; }
.barra [role=tab] { font: 15px "Segoe UI", system-ui, sans-serif; background: #ffffff; color: #0b0b0b; border: 0; padding: 2px 0; cursor: pointer; }
.barra [role=tab][aria-selected=true] { font-weight: 700; text-decoration: underline; }
.filtros { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; padding: 8px 40px 0; font-size: 14px; }
.filtros label { color: #52514e; }
.filtros select { font: 14px "Segoe UI", system-ui, sans-serif; margin-left: 4px; padding: 1px 2px; }
.filtros button { font: 14px "Segoe UI", system-ui, sans-serif; background: #ffffff; border: 1px solid #898781; border-radius: 3px; padding: 1px 8px; cursor: pointer; }
.filtros button:disabled { color: #898781; border-color: #e1e0d9; cursor: default; }
.viendo { margin: 4px 40px 0; font-size: 13px; color: #52514e; }
main { padding: 6px 40px 0; }
.pestana h2 { font-size: 28px; font-weight: 700; line-height: 1.2; margin: 0 0 8px; }
.cifras { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 24px; margin: 0 0 10px; }
.cifra { min-width: 0; outline-offset: 2px; }
.cifra > div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cifra .num { font-size: 28px; font-weight: 700; line-height: 1.15; }
.cifra .etq { font-size: 14px; }
.cifra .ctx { font-size: 13px; color: #52514e; }
.grafico .gtit { font-size: 20px; font-weight: 700; line-height: 1.25; }
.grafico svg { display: block; margin-top: 4px; }
.grafico svg text { font-family: "Segoe UI", system-ui, sans-serif; }
.texto { margin: 8px 0 0; max-width: 110ch; }
.pie { margin: 6px 0 0; font-size: 13px; color: #52514e; max-width: 160ch; }
.dos { display: grid; grid-template-columns: 600px minmax(0, 1fr); gap: 32px; align-items: start; }
.tabla { overflow-y: auto; border-bottom: 1px solid #e1e0d9; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { position: sticky; top: 0; background: #ffffff; text-align: left; font-weight: 600; border-bottom: 1px solid #0b0b0b; padding: 3px 6px; vertical-align: bottom; }
td { padding: 2px 6px; white-space: nowrap; }
th.n, td.n { text-align: right; }
tr.gris td { color: #52514e; }
.mandos { display: flex; align-items: center; gap: 18px; margin: 0 0 6px; font-size: 14px; }
.mandos select, .mandos button { font: 14px "Segoe UI", system-ui, sans-serif; }
.mandos button { background: #ffffff; border: 1px solid #898781; border-radius: 3px; padding: 1px 8px; cursor: pointer; }
#tip { position: fixed; z-index: 10; max-width: 360px; background: #ffffff; color: #0b0b0b; border: 1px solid #898781; border-radius: 3px; padding: 6px 8px; font-size: 13px; line-height: 1.35; pointer-events: none; }
[data-tip]:focus { outline: 2px solid #2a78d6; }
"""

CUERPO = """
<div class="barra">
  <span class="nombre">Fallos y coste de los discos</span>
  <div role="tablist" aria-label="Pestañas">
    <button role="tab" id="b-vision" data-p="vision">Visión general</button>
    <button role="tab" id="b-centros" data-p="centros">Centros de datos</button>
    <button role="tab" id="b-modelos" data-p="modelos">Modelos</button>
    <button role="tab" id="b-edad" data-p="edad">Edad</button>
    <button role="tab" id="b-lista" data-p="lista">Lista de riesgo</button>
  </div>
</div>
<div class="filtros">
  <label>Centro de datos<select id="f-centro"></select></label>
  <label>Fabricante<select id="f-fabricante"></select></label>
  <label>Capacidad<select id="f-capacidad"></select></label>
  <label>Años cumplidos<select id="f-edad"></select></label>
  <button id="quitar" type="button">Quitar filtros</button>
</div>
<p class="viendo" id="viendo"></p>
<main>
  <section class="pestana" id="p-vision" role="tabpanel" hidden>
    <h2 data-titulo id="t-vision"></h2><div class="cifras" id="c-vision"></div>
    <div class="grafico" id="g-vision"></div><p class="texto" id="x-vision"></p><p class="pie" id="pie-vision"></p>
  </section>
  <section class="pestana" id="p-modelos" role="tabpanel" hidden>
    <h2 data-titulo id="t-modelos"></h2><div class="cifras" id="c-modelos"></div>
    <div class="dos"><div class="grafico" id="g-modelos"></div><div class="tabla" id="d-modelos" style="max-height:300px"></div></div>
    <p class="texto" id="x-modelos"></p><p class="pie" id="pie-modelos"></p>
  </section>
  <section class="pestana" id="p-edad" role="tabpanel" hidden>
    <h2 data-titulo id="t-edad"></h2><div class="cifras" id="c-edad"></div>
    <div class="grafico" id="g-edad"></div><p class="texto" id="x-edad"></p><p class="pie" id="pie-edad"></p>
  </section>
  <section class="pestana" id="p-centros" role="tabpanel" hidden>
    <h2 data-titulo id="t-centros"></h2><div class="cifras" id="c-centros"></div>
    <div class="grafico" id="g-centros"></div><p class="texto" id="x-centros"></p><p class="pie" id="pie-centros"></p>
  </section>
  <section class="pestana" id="p-lista" role="tabpanel" hidden>
    <h2 data-titulo id="t-lista"></h2><div class="cifras" id="c-lista"></div>
    <div class="mandos"><label>Lista de <select id="f-lista"></select> discos</label>
      <button id="descargar" type="button">Descargar CSV</button></div>
    <div class="tabla" id="d-lista" style="max-height:226px"></div><p class="pie" id="pie-lista"></p>
  </section>
</main>
<div id="tip" role="tooltip" hidden></div>
"""

JS = r"""
'use strict';
const D = JSON.parse(document.getElementById('datos').textContent);
const AZUL = '#2a78d6', NARANJA = '#eb6834', GRIS = '#898781', REJILLA = '#e1e0d9', TEXTO2 = '#52514e', NEGRO = '#0b0b0b';
const PESTANAS = ['vision', 'centros', 'modelos', 'edad', 'lista'];
const FACTOR = 100 * 365, CONF = 0.95, MIN_DIAS = D.minimo_dias_ano, MIN_FALLOS = D.minimo_fallos;
const REGLA = 'regla de los cinco avisos SMART';
const SIN_DATO = 'sin dato';
const E = {pestana: 'vision', fabricante: null, capacidad: null, edad: null, centro: null, lista: D.lista.principal};

// ---------------------------------------------------------------- números y textos a la española
function redondeo(x, d) {
  // Como Excel y como numero() de assets/graficos.py: el medio se aleja del cero, sobre el texto del número
  let s = String(Math.abs(x));
  if (s.includes('e')) s = Math.abs(x).toFixed(20);
  let [ent, dec = ''] = s.split('.');
  dec = dec.padEnd(d + 1, '0');
  let base = BigInt(ent + dec.slice(0, d));
  if (Number(dec[d]) >= 5) base += 1n;
  const t = base.toString().padStart(d + 1, '0');
  return [x < 0 && base !== 0n, d > 0 ? t.slice(0, t.length - d) : t, d > 0 ? t.slice(t.length - d) : ''];
}
function num(x, d = 0) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const [neg, e, f] = redondeo(x, d);
  return (neg ? '−' : '') + e.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (d > 0 ? ',' + f : '');
}
function decCsv(x, d) { const [neg, e, f] = redondeo(x, d); return (neg ? '-' : '') + e + (d > 0 ? ',' + f : ''); }
function pct(x, d = 2) { return x === null ? '—' : num(x, d) + ' %'; }
function usd(x, d = 0) { return num(x, d) + ' $'; }
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function millones(x) { return x >= 1e6 ? num(x / 1e6, 1) + ' millones de' : num(x); }
function listaY(xs) { return xs.length <= 1 ? xs.join('') : xs.slice(0, -1).join(', ') + ' y ' + xs[xs.length - 1]; }
function trimestre(q) { return 'T' + (q % 10) + ' ' + Math.floor(q / 10); }
function capTexto(c) { return Number.isInteger(c) ? String(c) : decCsv(c, 1); }

// ---------------------------------------------------------------- estadística: la misma cuenta que scipy en Python
function lgamma(x) {
  let s = 0;
  while (x < 15) { s -= Math.log(x); x += 1; }
  const x2 = x * x;
  return s + (x - 0.5) * Math.log(x) - x + 0.9189385332046728 + 1 / (12 * x) - 1 / (360 * x * x2)
    + 1 / (1260 * x2 * x2 * x) - 1 / (1680 * x2 * x2 * x2 * x);
}
function gammaP(a, x) {
  // Función gamma incompleta regularizada: serie por debajo de a + 1 y fracción continua por encima
  if (x <= 0) return 0;
  const lf = a * Math.log(x) - x - lgamma(a);
  if (x < a + 1) {
    let ap = a, del = 1 / a, sum = del;
    for (let n = 0; n < 1e5; n++) { ap += 1; del *= x / ap; sum += del; if (Math.abs(del) < Math.abs(sum) * 1e-17) break; }
    return sum * Math.exp(lf);
  }
  let b = x + 1 - a, c = 1e300, d = 1 / b, h = d;
  for (let i = 1; i < 1e5; i++) {
    const an = -i * (i - a); b += 2;
    d = an * d + b; if (Math.abs(d) < 1e-300) d = 1e-300;
    c = b + an / c; if (Math.abs(c) < 1e-300) c = 1e-300;
    d = 1 / d; const del = d * c; h *= del;
    if (Math.abs(del - 1) < 1e-17) break;
  }
  return 1 - Math.exp(lf) * h;
}
function gammaInv(p, a) {
  // Cuantil de la gamma de forma a: Newton con salvaguarda de bisección
  let lo = 0, hi = Math.max(1, a + 10 * Math.sqrt(a) + 10);
  while (gammaP(a, hi) < p) hi *= 2;
  let x = a > 1 ? a : hi / 2;
  for (let it = 0; it < 400; it++) {
    const F = gammaP(a, x) - p;
    if (F < 0) lo = x; else hi = x;
    const pdf = Math.exp((a - 1) * Math.log(x) - x - lgamma(a));
    let nx = x - F / pdf;
    if (!(nx > lo && nx < hi) || !Number.isFinite(nx)) nx = 0.5 * (lo + hi);
    if (Math.abs(nx - x) <= 1e-16 * Math.abs(nx) || hi - lo <= 1e-16 * hi) return nx;
    x = nx;
  }
  return x;
}
// intervalo_poisson del script 09: chi2.ppf(q; 2f)/2 es el cuantil de la gamma de forma f
function intervaloPoisson(fallos, dias, phi = 1) {
  const a = 1 - CONF, f = Math.trunc(fallos), fp = f / phi, dp = dias / phi;
  const lo = f === 0 ? 0 : gammaInv(a / 2, fp), hi = gammaInv(1 - a / 2, fp + 1), k = FACTOR / dp;
  return [f * (FACTOR / dias), lo * k, hi * k];
}
// razon_poisson del script 11
function razonPoisson(o, esp, phi = 1) {
  const a = 1 - CONF, op = o / phi, e = esp / phi;
  const lo = o === 0 ? 0 : gammaInv(a / 2, op), hi = gammaInv(1 - a / 2, op + 1);
  return [o / esp, lo / e, hi / e];
}
// frente_al_anterior del script 09
function frenteAlAnterior(filas, minimo, phi) {
  const out = []; let prev = null;
  for (const f of filas) {
    const g = Object.assign({}, f);
    if (g.dias_disco > 0) [g.tasa, g.desde, g.hasta] = intervaloPoisson(g.fallos, g.dias_disco, phi);
    else { g.tasa = null; g.desde = null; g.hasta = null; }
    g.sin_conclusion = g.fallos < minimo;
    const comparable = prev !== null && !g.sin_conclusion && !prev.sin_conclusion && g.tasa !== null && prev.tasa !== null;
    g.sube = comparable ? g.desde > prev.hasta : null;
    g.baja = comparable ? g.hasta < prev.desde : null;
    out.push(g); prev = g;
  }
  return out;
}
// phi_poisson del script 09
function phiPoisson(grupos, celdas, obs, esp) {
  const t = new Map();
  for (let i = 0; i < grupos.length; i++) {
    const k = grupos[i] + '|' + celdas[i];
    if (!t.has(k)) t.set(k, {g: grupos[i], o: 0, e: 0});
    const c = t.get(k); c.o += obs[i]; c.e += esp[i];
  }
  const filas = [...t.values()].filter(c => c.e > 0), tot = new Map();
  for (const c of filas) { if (!tot.has(c.g)) tot.set(c.g, {o: 0, e: 0}); const s = tot.get(c.g); s.o += c.o; s.e += c.e; }
  let chi2 = 0, n = 0; const gs = new Set();
  for (const c of filas) {
    const s = tot.get(c.g), ee = c.e * s.o / s.e;
    if (!(ee > 0)) continue;
    chi2 += (c.o - ee) ** 2 / ee; n += 1; gs.add(c.g);
  }
  const gl = n - gs.size;
  return gl > 0 ? Math.max(1, chi2 / gl) : 1;
}
function veredicto(centro, diasAno, fallos, desde, hasta) {
  if (centro === SIN_DATO) return 'aparte';
  if (diasAno < MIN_DIAS || fallos < MIN_FALLOS) return 'sin conclusión';
  if (desde > 1) return 'falla más por sí mismo';
  if (hasta < 1) return 'falla menos';
  return 'no se distingue';
}
function nombreCentro(c) { return D.ciudades[c] ? D.ciudades[c] + ' · ' + c : c; }
function concluye(diasAno, fallos) { return diasAno >= MIN_DIAS && fallos >= MIN_FALLOS; }

// ---------------------------------------------------------------- la selección
const T = D.tramos, N = T.mes.length;
const FAB = T.modelo.map(i => D.modelos[i].fabricante), CAP = T.modelo.map(i => D.modelos[i].capacidad_tb);
const FAB_MODELO = Object.fromEntries(D.modelos.map(m => [m.model, m.fabricante]));
function hayFiltro(claves = ['fabricante', 'capacidad', 'edad', 'centro']) { return claves.some(k => E[k] !== null); }
function pasa(i, conCentro = true) {
  if (E.fabricante !== null && FAB[i] !== E.fabricante) return false;
  if (E.capacidad !== null && CAP[i] !== E.capacidad) return false;
  if (E.edad !== null && T.edad[i] !== E.edad) return false;
  if (conCentro && E.centro !== null && (T.centro[i] < 0 || D.centros[T.centro[i]] !== E.centro)) return false;
  return true;
}
function seleccionTexto() {
  // Los filtros en su orden, de lo general a lo particular: centro, fabricante, capacidad y edad
  if (!hayFiltro()) return 'todos los discos de datos';
  const p = [];
  if (E.centro !== null) p.push('en ' + nombreCentro(E.centro));
  if (E.fabricante !== null) p.push(E.fabricante);
  if (E.capacidad !== null) p.push('de ' + capTexto(E.capacidad) + ' TB');
  if (E.edad !== null) p.push('con ' + E.edad + (E.edad === 1 ? ' año cumplido' : ' años cumplidos'));
  return 'discos ' + p.join(', ');
}

// ---------------------------------------------------------------- cálculo de cada pestaña (la misma cuenta que resumen() en Python)
function calcVision() {
  const [u0, u1] = D.i_ultimo, [a0, a1] = D.i_anterior;
  let discos = 0, discosA = 0, fu = 0, du = 0, fa = 0, da = 0;
  const porQ = new Map(), porAno = new Map();
  const desde = E.centro !== null ? D.i_sitio : 0;
  for (let i = 0; i < N; i++) {
    if (!pasa(i)) continue;
    const m = T.mes[i];
    if (m === u1) discos += T.fotos[i];
    if (m === a1) discosA += T.fotos[i];
    if (m >= u0 && m <= u1) { fu += T.fallos[i]; du += T.dias[i]; }
    if (m >= a0 && m <= a1) { fa += T.fallos[i]; da += T.dias[i]; }
    if (m < desde) continue;
    const q = D.trimestres_de_mes[m], ano = Math.floor(q / 10);
    if (!porQ.has(q)) porQ.set(q, {q: q, fallos: 0, dias: 0});
    const s = porQ.get(q); s.fallos += T.fallos[i]; s.dias += T.dias[i];
    porAno.set(ano, (porAno.get(ano) || 0) + T.dias[i]);
  }
  const serie = [...new Set(D.trimestres_de_mes.slice(desde))].map(q => porQ.get(q) || {q: q, fallos: 0, dias: 0});
  for (const s of serie) {
    s.diasAno = porAno.get(Math.floor(s.q / 10)) || 0;
    s.gris = !concluye(s.diasAno, s.fallos);
    if (s.dias > 0) [s.tasa, s.desde, s.hasta] = intervaloPoisson(s.fallos, s.dias); else { s.tasa = null; }
  }
  const iu = du > 0 ? intervaloPoisson(fu, du) : [null, null, null], ia = da > 0 ? intervaloPoisson(fa, da) : [null, null, null];
  return {discos, discosA, fu, du, fa, da, iu, ia, serie};
}
function calcModelos() {
  const filas = D.b4.filter(r => (E.fabricante === null || FAB_MODELO[r.model] === E.fabricante)
    && (E.capacidad === null || r.capacidad_tb === E.capacidad));
  const con = filas.filter(r => r.puesto !== null);
  let coste = null, mejor = null;
  for (const r of con) if (coste === null || r.coste_tb_ano < coste) { coste = r.coste_tb_ano; mejor = r; }
  let med = null;
  if (con.length) {
    const v = con.map(r => r.parte_fallos_pct).sort((a, b) => a - b), k = v.length;
    med = k % 2 ? v[(k - 1) / 2] : (v[k / 2 - 1] + v[k / 2]) / 2;
  }
  return {filas, con, coste, mejor, med};
}
function calcEdad() {
  let filas;
  if (!hayFiltro()) filas = D.b3.map(r => Object.assign({}, r));
  else {
    const dias = new Array(11).fill(0), fallos = new Array(11).fill(0);
    for (let i = 0; i < N; i++) { if (!pasa(i)) continue; const e = T.edad[i]; if (e >= 0 && e <= 10) { dias[e] += T.dias[i]; fallos[e] += T.fallos[i]; } }
    filas = frenteAlAnterior(dias.map((d, j) => ({edad: j, dias_disco: d, fallos: fallos[j]})), MIN_FALLOS, D.b3_phi);
  }
  const anos = (E.centro !== null ? D.dias_periodo_sitio : D.dias_periodo) / 365;
  for (const r of filas) { r.diasAno = r.dias_disco / anos; r.gris = r.sin_conclusion || r.diasAno < MIN_DIAS; }
  const sube = [];
  for (let j = 1; j < filas.length; j++) if (filas[j].sube && !filas[j].gris && !filas[j - 1].gris) sube.push(j);
  return {filas, sube};
}
function calcCentros() {
  let filas;
  if (hayFiltro(['fabricante', 'capacidad', 'edad'])) {
    const nc = D.centros.length, obs = new Array(nc + 1).fill(0), esp = new Array(nc + 1).fill(0), dias = new Array(nc + 1).fill(0);
    const g = [], q = [], o = [], e = [];
    for (let i = 0; i < N; i++) {
      if (T.mes[i] < D.i_sitio || !pasa(i, false)) continue;
      const c = T.centro[i] >= 0 ? T.centro[i] : nc;
      obs[c] += T.fallos[i]; esp[c] += T.esp[i]; dias[c] += T.dias[i];
      if (T.centro[i] >= 0) { g.push(T.centro[i]); q.push(D.trimestres_de_mes[T.mes[i]]); o.push(T.fallos[i]); e.push(T.esp[i]); }
    }
    const phi = phiPoisson(g, q, o, e);
    filas = D.centros.map((c, j) => {
      const r = {centro: c, observados: obs[j], esperados: esp[j], dias: dias[j], razon: null, razon_desde: null, razon_hasta: null};
      if (esp[j] > 0) [r.razon, r.razon_desde, r.razon_hasta] = razonPoisson(obs[j], esp[j], phi);
      r.veredicto = r.razon_desde !== null ? veredicto(c, dias[j] / D.anos_sitio, obs[j], r.razon_desde, r.razon_hasta) : 'sin conclusión';
      return r;
    });
  } else filas = D.b5.filter(r => r.centro !== SIN_DATO).map(r => Object.assign({}, r));
  if (E.centro !== null) filas = filas.filter(r => r.centro === E.centro);
  const sinCentro = D.b5.find(r => r.centro === SIN_DATO);
  return {filas, sinCentro};
}
function filasLista() {
  const col = D.lista.col, n = E.lista, out = [];
  for (const fila of D.lista.filas) {
    const x = {}; col.forEach((k, j) => { x[k] = fila[j]; });
    const en = n === 20 ? x.en_20 : n === 100 ? x.en_100 : n === 500 ? x.en_500 : 1;
    if (!en) continue;
    if (E.fabricante !== null && x.fabricante !== E.fabricante) continue;
    if (E.capacidad !== null && x.capacidad_tb !== E.capacidad) continue;
    if (E.edad !== null && x.edad !== E.edad) continue;
    if (E.centro !== null && x.centro !== E.centro) continue;
    out.push(x);
  }
  return out.sort((a, b) => a.puesto - b.puesto);
}
function calcLista() {
  const filas = filasLista();
  const tomos = D.tomos.en_peligro.filter(t => E.centro === null || t.centro === E.centro);
  return {filas, tomos, fallos: tomos.reduce((s, t) => s + t.fallos, 0)};
}

// ---------------------------------------------------------------- piezas: cifras, títulos, etiquetas
function cifra(id, valor, numero, etiqueta, contexto, tip) {
  return `<div class="cifra" tabindex="0" data-id="${id}" data-valor="${valor === null ? '' : String(valor)}" data-tip="${esc(tip)}">`
    + `<div class="num">${esc(numero)}</div><div class="etq">${esc(etiqueta)}</div><div class="ctx">${esc(contexto)}</div></div>`;
}
function titulo(el, texto, grupo) {
  el.textContent = texto;
  el.dataset.concluye = grupo ? 'si' : 'no';
  if (grupo) { el.dataset.diasAno = String(grupo.diasAno); el.dataset.fallos = String(grupo.fallos); }
  else { delete el.dataset.diasAno; delete el.dataset.fallos; }
}
function grafico(id, texto, svg, grupo) {
  const g = document.getElementById(id);
  g.innerHTML = `<div class="gtit" data-titulo></div>` + svg;
  titulo(g.querySelector('.gtit'), texto, grupo);
}
function marcaGris(x, y, texto = 'Gris: sin conclusión, por menos de 50.000 días de disco en el año o de 20 fallos') {
  return `<text x="${x}" y="${y}" font-size="12" fill="${TEXTO2}"><tspan fill="${GRIS}">■</tspan> ${texto}</text>`;
}
function maxDe(xs) { return Math.max(...xs.filter(r => r.v !== null).map(r => r.gris ? r.v : r.hasta)); }
function escala(max) {
  const paso = [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100].find(p => max / p <= 6) || 200;
  return {paso, tope: Math.ceil(max / paso) * paso || paso};
}

// ---------------------------------------------------------------- pestaña 1: visión general
function dibujarVision() {
  const v = calcVision(), sel = seleccionTexto(), filtro = hayFiltro();
  const [tu, lu, hu] = v.iu, [ta, la, ha] = v.ia;
  const okU = concluye(v.du, v.fu), okA = concluye(v.da, v.fa);
  let t = 'Fallos y tasa anual de fallo de esta selección', grupo = null;
  if (okU && okA) {
    grupo = {diasAno: Math.min(v.du, v.da), fallos: Math.min(v.fu, v.fa)};
    t = lu > ha ? 'La tasa anual de fallo sube frente al año anterior' : hu < la ? 'La tasa anual de fallo baja frente al año anterior'
      : 'La tasa anual de fallo no se distingue de la del año anterior';
  }
  titulo(document.getElementById('t-vision'), t, grupo);
  const cambio = v.discosA > 0 ? (v.discos / v.discosA - 1) * 100 : null;
  document.getElementById('c-vision').innerHTML = [
    cifra('discos', v.discos, num(v.discos), 'Discos de datos el 01/06/2025',
      cambio === null ? 'Ninguno el 01/06/2024' : (cambio > 0 ? '+' : '') + num(cambio, 1) + ' % frente al 01/06/2024',
      `Discos de datos de ${sel} el 01/06/2025: ${num(v.discos)}. Se cuentan con el estado de cada disco el primer día del mes. El 01/06/2024 eran ${num(v.discosA)}.`),
    cifra('fallos', v.fu, num(v.fu), 'Fallos de julio de 2024 a junio de 2025', num(v.fa) + ' el año anterior',
      `Fallos de ${sel} de julio de 2024 a junio de 2025: ${num(v.fu)}, en ${millones(v.du)} días de disco. De julio de 2023 a junio de 2024 fueron ${num(v.fa)}.`),
    cifra('tasa', tu, pct(tu), 'Tasa anual de fallo del último año', ta === null ? 'Sin datos el año anterior' : pct(ta) + ' el año anterior',
      tu === null ? `Sin días de disco de ${sel} en el último año.` :
      `Tasa anual de fallo de ${sel} de julio de 2024 a junio de 2025: ${pct(tu, 4)}, con un intervalo de confianza del 95 % de ${pct(lu, 4)} a ${pct(hu, 4)}. Es 100 × 365 × fallos / días de disco.` + (ta === null ? '' : ` El año anterior, ${pct(ta, 4)}, de ${pct(la, 4)} a ${pct(ha, 4)}.`)
      + (okU && okA ? '' : ' Sin conclusión: uno de los dos años no llega a 50.000 días de disco o a 20 fallos.')),
    cifra('coste', D.coste_2024, usd(D.coste_2024), 'Lo que costaron los fallos en 2024', filtro ? 'Del total, sin filtro' : usd(D.coste_2024_garantia) + ' con garantía',
      `Lo que costaron los fallos de los discos de datos en 2024: ${usd(D.coste_2024)}. Cada fallo cuesta un disco nuevo de la misma capacidad y 37 $ del cambio. Si la garantía pagara los discos, ${usd(D.coste_2024_garantia)}.` + (filtro ? ' Es la cifra del total: no cambia con los filtros.' : ''))
  ].join('');
  // Gráfico: tasa anual de fallo por trimestre con su intervalo
  const W = 1286, H = 236, ml = 56, mr = 16, mt = 12, mb = 44, s = v.serie, k = s.length;
  const max = Math.max(0.5, maxDe(s.map(p => ({v: p.tasa, gris: p.gris, hasta: p.hasta}))));
  const {paso, tope} = escala(max), X = j => ml + (j + 0.5) * (W - ml - mr) / k, Y = y => mt + (H - mt - mb) * (1 - y / tope);
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Tasa anual de fallo por trimestre">`;
  for (let y = 0; y <= tope + 1e-9; y += paso) svg += `<line x1="${ml}" x2="${W - mr}" y1="${Y(y)}" y2="${Y(y)}" stroke="${REJILLA}"/><text x="${ml - 6}" y="${Y(y) + 4}" font-size="12" text-anchor="end" fill="${TEXTO2}">${num(y, paso < 1 ? 1 : 0)} %</text>`;
  let camino = '';
  s.forEach((p, j) => { if (p.tasa !== null) camino += (camino ? 'L' : 'M') + X(j) + ' ' + Y(p.tasa); });
  svg += `<path d="${camino}" fill="none" stroke="${AZUL}" stroke-width="1.5"/>`;
  s.forEach((p, j) => {
    const etiqueta = trimestre(p.q);
    if (p.q % 10 === 1 || j === 0) svg += `<text x="${X(j)}" y="${H - mb + 16}" font-size="12" text-anchor="middle" fill="${TEXTO2}">${p.q % 10 === 1 ? Math.floor(p.q / 10) : etiqueta}</text>`;
    if (p.tasa === null) return;
    const color = p.gris ? GRIS : AZUL;
    const tip = `${etiqueta}: tasa anual de fallo de ${pct(p.tasa)}, de ${pct(p.desde)} a ${pct(p.hasta)} con un 95 % de confianza; ${num(p.fallos)} fallos en ${millones(p.dias)} días de disco.` + (p.gris ? ' Sin conclusión: menos de 50.000 días de disco en el año o de 20 fallos.' : '');
    svg += `<g tabindex="0" data-tip="${esc(tip)}">` + (p.gris ? '' : `<line x1="${X(j)}" x2="${X(j)}" y1="${Y(p.desde)}" y2="${Y(Math.min(p.hasta, tope))}" stroke="${color}" stroke-width="1.5"/>`)
      + `<circle cx="${X(j)}" cy="${Y(p.tasa)}" r="4" fill="${color}"/><rect x="${X(j) - 12}" y="${mt}" width="24" height="${H - mt - mb}" fill="transparent"/></g>`;
  });
  svg += `<text x="${ml}" y="${H - 6}" font-size="12" fill="${TEXTO2}">Raya vertical: intervalo de confianza del 95 %. Tasa anual de fallo en %.</text>`;
  if (s.some(p => p.gris && p.tasa !== null)) svg += marcaGris(ml + 470, H - 6);
  svg += '</svg>';
  grafico('g-vision', 'Tasa anual de fallo por trimestre' + (E.centro !== null ? ' desde julio de 2023' : ''), svg, null);
  document.getElementById('x-vision').textContent = 'La primera de las cinco decisiones del informe final es comprar en cada capacidad el modelo de menor coste por terabyte y año.';
  document.getElementById('pie-vision').textContent = 'Fuente: registro diario de Backblaze, datos a 30/06/2025';
}

// ---------------------------------------------------------------- pestaña 2: modelos
function dibujarModelos() {
  const m = calcModelos(), sel = seleccionTexto(), filas = m.filas;
  let t = 'Coste por terabyte y año de cada modelo', grupo = null;
  const best = filas[0];
  if (filas.length >= 2 && best.puesto !== null) {
    const diasAno = best.dias_disco / best.anos_que_pasan.length;
    if (concluye(diasAno, best.fallos) && filas.slice(1).every(r => r.coste_desde > best.coste_hasta)) {
      t = `El ${best.model} es el modelo de menor coste por terabyte y año`; grupo = {diasAno, fallos: best.fallos};
    }
  }
  titulo(document.getElementById('t-modelos'), t, grupo);
  const sin = filas.length - m.con.length;
  document.getElementById('c-modelos').innerHTML = [
    cifra('modelos', filas.length, num(filas.length), 'Modelos con coste por terabyte', sin === 1 ? '1 sin conclusión' : num(sin) + ' sin conclusión',
      `Modelos de disco de datos de ${sel} con coste por terabyte y año: ${num(filas.length)}. Sin conclusión, ${num(sin)}: tienen menos de 20 fallos en sus años con 50.000 días de disco o más.`),
    cifra('coste_min', m.coste, m.coste === null ? '—' : usd(m.coste, 2), 'Menor coste por terabyte y año', m.mejor ? m.mejor.model : 'Ningún modelo con conclusión',
      m.mejor ? `Menor coste por terabyte y año entre los modelos con conclusión de ${sel}: ${usd(m.coste, 4)} del ${m.mejor.model}, de ${usd(m.mejor.coste_desde, 4)} a ${usd(m.mejor.coste_hasta, 4)} con un 95 % de confianza. Es el precio del disco repartido en 6 años y en su capacidad, más lo que cuestan sus fallos.` : `Ningún modelo de ${sel} tiene 20 fallos.`),
    cifra('mediana_fallos', m.med, m.med === null ? '—' : pct(m.med, 1), 'Parte de los fallos en el coste', m.con.length ? 'Mediana de ' + num(m.con.length) + ' modelos' : 'Sin modelos con conclusión',
      m.med === null ? `Ningún modelo de ${sel} tiene 20 fallos.` : `Parte del coste por terabyte y año que se va en fallos, mediana de los ${num(m.con.length)} modelos con conclusión de ${sel}: ${pct(m.med, 2)}. El resto es el precio del disco.`)
  ].join('');
  // Gráfico: los diez primeros por coste, barras desde cero con su intervalo
  const top = filas.slice(0, 10), W = 600, fila = 23, ml = 178, mr = 130, mt = 6, mb = 58, H = mt + mb + Math.max(top.length, 1) * fila;
  const max = Math.max(...top.map(r => r.coste_hasta), 1), {paso, tope} = escala(max), X = x => ml + (W - ml - mr) * x / tope;
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Coste por terabyte y año">`;
  for (let x = 0; x <= tope + 1e-9; x += paso) svg += `<line x1="${X(x)}" x2="${X(x)}" y1="${mt}" y2="${H - mb}" stroke="${REJILLA}"/><text x="${X(x)}" y="${H - mb + 14}" font-size="12" text-anchor="middle" fill="${TEXTO2}">${num(x, paso < 1 ? 1 : 0)}</text>`;
  top.forEach((r, j) => {
    const y = mt + j * fila, gris = r.puesto === null, color = gris ? GRIS : AZUL;
    const tip = `${r.model}, ${capTexto(r.capacidad_tb)} TB comprado en ${r.ano_compra}: ${usd(r.coste_tb_ano, 4)} por terabyte y año, de ${usd(r.coste_desde, 4)} a ${usd(r.coste_hasta, 4)} con un 95 % de confianza. Tasa anual de fallo ${pct(r.tasa)}, ${num(r.fallos)} fallos.` + (gris ? ' Sin conclusión: menos de 20 fallos.' : '');
    svg += `<g tabindex="0" data-tip="${esc(tip)}"><text x="${ml - 6}" y="${y + 15}" font-size="12" text-anchor="end" fill="${NEGRO}">${esc(r.model)}</text>`
      + `<rect x="${ml}" y="${y + 4}" width="${X(r.coste_tb_ano) - ml}" height="${fila - 8}" fill="${color}"/>`
      + (gris ? '' : `<line x1="${X(r.coste_desde)}" x2="${X(r.coste_hasta)}" y1="${y + fila / 2}" y2="${y + fila / 2}" stroke="${NEGRO}" stroke-width="1.5"/>`)
      + `<text x="${X(gris ? r.coste_tb_ano : r.coste_hasta) + 6}" y="${y + 15}" font-size="12" fill="${NEGRO}">${usd(r.coste_tb_ano, 2)}${gris ? ', sin conclusión' : ''}</text></g>`;
  });
  svg += `<text x="${ml}" y="${H - 6}" font-size="12" fill="${TEXTO2}">Dólares por terabyte y año; raya negra: intervalo de confianza del 95 %</text>`;
  if (top.some(r => r.puesto === null)) svg += marcaGris(ml, H - 22, 'Gris: sin conclusión, por menos de 20 fallos');
  svg += '</svg>';
  grafico('g-modelos', 'Coste por terabyte y año de los diez primeros modelos', svg, null);
  // Tabla de todos los modelos de la selección
  let h = '<table><thead><tr><th>Modelo</th><th class="n">TB</th><th class="n">Año de compra</th><th class="n">Dólares por TB y año</th><th class="n">Tasa anual de fallo, %</th><th class="n">Fallos</th></tr></thead><tbody>';
  for (const r of filas) h += `<tr${r.puesto === null ? ' class="gris"' : ''}><td>${esc(r.model)}${r.puesto === null ? ' (sin conclusión)' : ''}</td><td class="n">${capTexto(r.capacidad_tb)}</td><td class="n">${r.ano_compra}</td><td class="n">${num(r.coste_tb_ano, 2)}</td><td class="n">${num(r.tasa, 2)}</td><td class="n">${num(r.fallos)}</td></tr>`;
  document.getElementById('d-modelos').innerHTML = h + '</tbody></table>';
  document.getElementById('x-modelos').textContent = hayFiltro(['edad', 'centro'])
    ? 'Con un filtro de edad o de centro de datos el coste por terabyte no se puede recalcular y no cambia.'
    : 'Compara cada modelo con los de su capacidad y año de compra, porque cada año el terabyte sale más barato.';
  document.getElementById('pie-modelos').textContent = 'Fuente: registro diario de Backblaze y precios de compra estimados desde 2023, datos a 30/06/2025';
}

// ---------------------------------------------------------------- pestaña 3: edad
function dibujarEdad() {
  const e = calcEdad(), f = e.filas, sel = seleccionTexto();
  let t = 'Tasa anual de fallo por años cumplidos', grupo = null;
  const comparables = [];
  for (let j = 1; j < f.length; j++) if (f[j].sube !== null && !f[j].gris && !f[j - 1].gris) comparables.push(j);
  if (e.sube.length) {
    const edades = [...new Set(e.sube.flatMap(j => [j - 1, j]))];
    t = 'La tasa anual de fallo sube con la edad';
    grupo = {diasAno: Math.min(...edades.map(j => f[j].diasAno)), fallos: Math.min(...edades.map(j => f[j].fallos))};
  } else if (comparables.length) {
    const edades = [...new Set(comparables.flatMap(j => [j - 1, j]))];
    t = 'La tasa anual de fallo no se distingue de un año de edad al siguiente';
    grupo = {diasAno: Math.min(...edades.map(j => f[j].diasAno)), fallos: Math.min(...edades.map(j => f[j].fallos))};
  }
  titulo(document.getElementById('t-edad'), t, grupo);
  const r0 = f[0], r5 = f[5];
  const tipEdad = (r, nombre) => r.tasa === null ? `Sin días de disco de ${sel} ${nombre}.` :
    `Tasa anual de fallo de ${sel} ${nombre}: ${pct(r.tasa, 4)}, de ${pct(r.desde, 4)} a ${pct(r.hasta, 4)} con un 95 % de confianza; ${num(r.fallos)} fallos en ${millones(r.dias_disco)} días de disco.` + (r.gris ? ' Sin conclusión: menos de 20 fallos o de 50.000 días de disco al año.' : '');
  document.getElementById('c-edad').innerHTML = [
    cifra('tasa_0', r0.tasa, pct(r0.tasa), 'Tasa anual de fallo el primer año', num(r0.fallos) + ' fallos', tipEdad(r0, 'con 0 años cumplidos')),
    cifra('tasa_5', r5.tasa, pct(r5.tasa), 'Tasa anual de fallo a los 5 años cumplidos', num(r5.fallos) + ' fallos', tipEdad(r5, 'con 5 años cumplidos')),
    cifra('anos_sube', e.sube.length, num(e.sube.length), 'Años de edad en que la tasa sube', e.sube.length ? listaY(e.sube.map(String)) + ' años' : 'Ninguno',
      'Años cumplidos en que la tasa anual de fallo sube frente al año anterior: su intervalo de confianza del 95 % no se solapa con el del año anterior. Solo cuentan los años con conclusión.')
  ].join('');
  const W = 1286, H = 252, ml = 56, mr = 16, mt = 22, mb = 46, k = f.length;
  const max = Math.max(0.5, maxDe(f.map(r => ({v: r.tasa, gris: r.gris, hasta: r.hasta}))));
  const {paso, tope} = escala(max), X = j => ml + (j + 0.5) * (W - ml - mr) / k, Y = y => mt + (H - mt - mb) * (1 - y / tope), bw = (W - ml - mr) / k * 0.6;
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Tasa anual de fallo por años cumplidos">`;
  for (let y = 0; y <= tope + 1e-9; y += paso) svg += `<line x1="${ml}" x2="${W - mr}" y1="${Y(y)}" y2="${Y(y)}" stroke="${REJILLA}"/><text x="${ml - 6}" y="${Y(y) + 4}" font-size="12" text-anchor="end" fill="${TEXTO2}">${num(y, paso < 1 ? 1 : 0)} %</text>`;
  f.forEach((r, j) => {
    svg += `<text x="${X(j)}" y="${H - mb + 16}" font-size="12" text-anchor="middle" fill="${TEXTO2}">${j}</text>`;
    if (r.tasa === null) return;
    const color = r.gris ? GRIS : AZUL;
    const alto = Math.max(Y(0) - Y(r.tasa), r.gris ? 2 : 0), arriba = Y(0) - alto;
    svg += `<g tabindex="0" data-tip="${esc(tipEdad(r, j === 1 ? 'con 1 año cumplido' : 'con ' + j + ' años cumplidos'))}"><rect x="${X(j) - bw / 2}" y="${arriba}" width="${bw}" height="${alto}" fill="${color}"/>`
      + (r.gris ? '' : `<line x1="${X(j)}" x2="${X(j)}" y1="${Y(r.desde)}" y2="${Y(Math.min(r.hasta, tope))}" stroke="${NEGRO}" stroke-width="1.5"/>`)
      + (r.gris ? `<text x="${X(j)}" y="${arriba - 19}" font-size="12" text-anchor="middle" fill="${NEGRO}">${pct(r.tasa)}<tspan x="${X(j)}" dy="14">sin conclusión</tspan></text></g>`
        : `<text x="${X(j)}" y="${Y(Math.min(r.hasta, tope)) - 5}" font-size="12" text-anchor="middle" fill="${NEGRO}">${pct(r.tasa)}</text></g>`);
  });
  svg += `<text x="${ml}" y="${H - 6}" font-size="12" fill="${TEXTO2}">Años cumplidos. Raya negra: intervalo de confianza del 95 %.</text>`;
  if (f.some(r => r.gris && r.tasa !== null)) svg += marcaGris(ml + 380, H - 6);
  svg += '</svg>';
  grafico('g-edad', 'Tasa anual de fallo por años cumplidos' + (E.centro !== null ? ' desde julio de 2023' : ''), svg, null);
  document.getElementById('x-edad').textContent = 'Compara los modelos siempre a la misma edad: uno joven parece fallar poco solo por su edad.';
  document.getElementById('pie-edad').textContent = 'Fuente: registro diario de Backblaze, datos a 30/06/2025';
}

// ---------------------------------------------------------------- pestaña 4: centros de datos
const VEREDICTO = {'falla más por sí mismo': 'falla más de lo esperado', 'falla menos': 'falla menos de lo esperado',
  'no se distingue': 'no se distingue de lo esperado', 'sin conclusión': 'sin conclusión'};
function dibujarCentros() {
  const c = calcCentros(), f = c.filas, sel = seleccionTexto();
  const mas = f.filter(r => r.veredicto === 'falla más por sí mismo'), menos = f.filter(r => r.veredicto === 'falla menos');
  const con = f.filter(r => r.veredicto !== 'sin conclusión' && r.veredicto !== 'aparte');
  let t = 'Fallos de cada centro de datos frente a los esperados', grupo = null;
  const g = rs => ({diasAno: Math.min(...rs.map(r => r.dias / D.anos_sitio)), fallos: Math.min(...rs.map(r => r.observados))});
  if (mas.length === 1) { t = `El centro de datos ${nombreCentro(mas[0].centro)} falla más de lo esperado`; grupo = g(mas); }
  else if (mas.length > 1) { t = `Los centros de datos ${listaY(mas.map(r => nombreCentro(r.centro)))} fallan más de lo esperado`; grupo = g(mas); }
  else if (con.length) { t = con.length === 1 ? `El centro de datos ${nombreCentro(con[0].centro)} no falla más de lo esperado` : 'Ningún centro de datos falla más de lo esperado'; grupo = g(con); }
  titulo(document.getElementById('t-centros'), t, grupo);
  const obs = f.reduce((s, r) => s + r.observados, 0), esp = f.reduce((s, r) => s + r.esperados, 0);
  document.getElementById('c-centros').innerHTML = [
    cifra('centros_mas', mas.length, num(mas.length), 'Centros que fallan más de lo esperado', mas.length ? listaY(mas.map(r => nombreCentro(r.centro))) : 'Ninguno',
      'Centros de datos cuyos fallos superan los esperados con su mezcla de modelos, años de edad y trimestres: el intervalo de confianza del 95 % de la razón entre los dos queda entero por encima de 1.'),
    cifra('centros_menos', menos.length, num(menos.length), 'Centros que fallan menos de lo esperado', menos.length ? listaY(menos.map(r => nombreCentro(r.centro))) : 'Ninguno',
      'Centros de datos cuyos fallos quedan por debajo de los esperados con su mezcla de modelos, años de edad y trimestres: el intervalo de confianza del 95 % de la razón queda entero por debajo de 1.'),
    cifra('fallos_centros', obs, num(obs), 'Fallos en los centros de datos', num(esp) + ' esperados',
      `Fallos de ${sel} con su centro de datos de julio de 2023 a junio de 2025: ${num(obs)}. Si cada centro fallara como la media con sus mismos discos, se esperaban ${num(esp, 1)}.`)
  ].join('');
  const W = 1286, fila = 30, ml = 140, mr = 120, mt = 22, mb = 42, H = mt + mb + Math.max(f.length, 1) * fila;
  const max = Math.max(1.25, maxDe(f.map(r => ({v: r.razon, gris: r.veredicto === 'sin conclusión', hasta: r.razon_hasta}))));
  const {paso, tope} = escala(max), X = x => ml + (W - ml - mr) * x / tope;
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Fallos frente a los esperados">`;
  for (let x = 0; x <= tope + 1e-9; x += paso) svg += `<line x1="${X(x)}" x2="${X(x)}" y1="${mt}" y2="${H - mb}" stroke="${REJILLA}"/><text x="${X(x)}" y="${H - mb + 14}" font-size="12" text-anchor="middle" fill="${TEXTO2}">${num(x, 2)}</text>`;
  f.forEach((r, j) => {
    const y = mt + j * fila, gris = r.veredicto === 'sin conclusión', color = gris ? GRIS : r.veredicto === 'falla más por sí mismo' ? NARANJA : AZUL;
    const tip = r.razon === null ? `${nombreCentro(r.centro)}: sin días de disco en esta selección.` :
      `${nombreCentro(r.centro)}: ${num(r.observados)} fallos frente a ${num(r.esperados, 1)} esperados; ${num(r.razon, 2)} veces lo esperado, de ${num(r.razon_desde, 2)} a ${num(r.razon_hasta, 2)} con un 95 % de confianza. ${VEREDICTO[r.veredicto][0].toUpperCase() + VEREDICTO[r.veredicto].slice(1)}.`;
    svg += `<g tabindex="0" data-tip="${esc(tip)}"><text x="${ml - 8}" y="${y + 19}" font-size="13" text-anchor="end" fill="${NEGRO}">${esc(nombreCentro(r.centro))}</text>`;
    if (r.razon !== null) svg += `<rect x="${ml}" y="${y + 6}" width="${X(r.razon) - ml}" height="${fila - 12}" fill="${color}"/>`
      + (gris ? '' : `<line x1="${X(r.razon_desde)}" x2="${X(Math.min(r.razon_hasta, tope))}" y1="${y + fila / 2}" y2="${y + fila / 2}" stroke="${NEGRO}" stroke-width="1.5"/>`)
      + `<text x="${X(gris ? r.razon : Math.min(r.razon_hasta, tope)) + 6}" y="${y + 19}" font-size="12" fill="${NEGRO}">${num(r.razon, 2)}${gris ? ', sin conclusión' : ''}</text>`;
    svg += '</g>';
  });
  svg += `<line x1="${X(1)}" x2="${X(1)}" y1="${mt}" y2="${H - mb}" stroke="${NEGRO}" stroke-dasharray="4 3"/><text x="${X(1) + 4}" y="${mt - 8}" font-size="12" fill="${NEGRO}">1 = lo esperado</text>`;
  svg += `<text x="${ml}" y="${H - 6}" font-size="12" fill="${TEXTO2}">Veces lo esperado. Raya negra: intervalo de confianza del 95 %. Naranja: falla más de lo esperado.</text>`;
  if (f.some(r => r.veredicto === 'sin conclusión' && r.razon !== null)) svg += marcaGris(ml + 560, H - 6);
  svg += '</svg>';
  grafico('g-centros', 'Fallos frente a los esperados', svg, null);
  document.getElementById('x-centros').textContent = 'Lo esperado: los fallos con sus modelos, edades y trimestres si fallara como la media.';
  document.getElementById('pie-centros').textContent = `Fuente: registro diario de Backblaze desde julio de 2023; ${num(c.sinCentro.observados)} fallos sin centro aparte; datos a 30/06/2025. La ciudad se deduce del código de aeropuerto: ninguna fuente publica la tabla.`;
}

// ---------------------------------------------------------------- pestaña 5: lista de riesgo
function dibujarLista() {
  const l = calcLista(), sel = seleccionTexto(), filtro = hayFiltro(), otros = hayFiltro(['fabricante', 'capacidad', 'edad']);
  titulo(document.getElementById('t-lista'), `La lista de ${num(E.lista)} discos de mayor riesgo de junio de 2026`, null);
  const fin = D.final;
  document.getElementById('c-lista').innerHTML = [
    cifra('discos_lista', l.filas.length, num(l.filas.length), 'Discos de la lista en la selección', filtro ? `De los ${num(E.lista)} de la lista` : 'La lista entera',
      `Discos de ${sel} en la lista de los ${num(E.lista)} de mayor riesgo de fallar en los 30 días siguientes al 01/06/2026: ${num(l.filas.length)}.`),
    cifra('tomos_peligro', l.tomos.length, num(l.tomos.length), 'Tomos en peligro el 01/06/2026', otros ? 'De todos los discos' + (E.centro !== null ? ' del centro' : '') : num(l.fallos) + ' fallos rehaciéndose',
      `Tomos${E.centro !== null ? ' de ' + nombreCentro(E.centro) : ''} en peligro el 01/06/2026: ${num(l.tomos.length)}, con ${num(l.fallos)} fallos de discos de datos que aún se están rehaciendo. Un tomo está en peligro mientras se rehace un disco suyo que falló: un día por terabyte más uno. ${num(D.tomos.aparte.de_datos_sin_tomo)} fallos sin tomo y ${num(D.tomos.aparte.sin_capacidad + D.tomos.aparte.sin_ventana)} sin capacidad van aparte.` + (otros ? ' No cambia con el fabricante, la capacidad ni la edad.' : '')),
    cifra('final_100', fin.modelo_100, num(fin.modelo_100, 2), 'Fallos al mes en la lista de 100 en la prueba final', filtro ? `Del total. ${REGLA[0].toUpperCase() + REGLA.slice(1)}: ${num(fin.regla_100, 2)}` : `${num(fin.regla_100, 2)} con la ${REGLA}`,
      `En la prueba final, de julio de 2025 a mayo de 2026, los 100 discos de la lista del modelo examinado tuvieron ${num(fin.modelo_100, 2)} fallos al mes de media en sus 30 días siguientes, frente a ${num(fin.regla_100, 2)} con la ${REGLA}.` + (filtro ? ' Es la cifra del total: no cambia con los filtros.' : ''))
  ].join('');
  // Columnas de lo general a lo particular (centro, tomo, modelo, edad, disco); la puntuación de riesgo, que ordena, la última
  let h = '<table><thead><tr><th class="n">Puesto</th><th>Centro de datos</th><th>Tomo en peligro</th><th>Fabricante</th><th>Modelo</th><th class="n">TB</th><th class="n">Años cumplidos</th><th>Número de serie</th><th class="n">Puntuación de riesgo, 0 a 100</th></tr></thead><tbody>';
  for (const x of l.filas) h += `<tr><td class="n">${x.puesto}</td><td>${esc(x.centro ? nombreCentro(x.centro) : '')}</td><td>${x.tomo_en_peligro}</td><td>${esc(x.fabricante)}</td><td>${esc(x.model)}</td><td class="n">${capTexto(x.capacidad_tb)}</td><td class="n">${x.edad}</td><td>${esc(x.serial_number)}</td><td class="n">${num(x.probabilidad * 100, 2)}</td></tr>`;
  if (!l.filas.length) h += '<tr><td colspan="9">Ningún disco de esta selección está en la lista.</td></tr>';
  document.getElementById('d-lista').innerHTML = h + '</tbody></table>';
  document.getElementById('pie-lista').textContent = 'Puntuación del modelo en uso, reentrenado hasta junio de 2025: ordena los discos y no es una probabilidad. Sus fallos aún no se miden: sus 30 días pasan del final de los datos. Fuente: estado de los discos a 01/06/2026';
}

// ---------------------------------------------------------------- CSV
function seleccionCsv() {
  const p = [];
  if (E.centro !== null) p.push(nombreCentro(E.centro));
  if (E.fabricante !== null) p.push(E.fabricante);
  if (E.capacidad !== null) p.push(capTexto(E.capacidad) + ' TB');
  if (E.edad !== null) p.push(E.edad === 1 ? '1 año cumplido' : E.edad + ' años cumplidos');
  return p;
}
function nombreCsv() {
  const p = ['lista_' + E.lista];
  if (E.centro !== null) p.push(E.centro.toLowerCase());
  if (E.fabricante !== null) p.push(E.fabricante.toLowerCase());
  if (E.capacidad !== null) p.push(capTexto(E.capacidad).replace(',', '-') + 'tb');
  if (E.edad !== null) p.push('edad-' + E.edad);
  return p.join('_') + '_datos-' + D.fecha_lista + '.csv';
}
function textoCsv() {
  const [a, m, d] = D.fecha_lista.split('-');
  const lineas = [[`Lista de ${E.lista}`, ...seleccionCsv(), `datos a ${d}/${m}/${a}`].join(' · '),
    'Puesto;Centro de datos;Ciudad;Tomo en peligro;Vault;Ranura;Fabricante;Modelo;Capacidad (TB);Años cumplidos;Número de serie;Puntuación de riesgo (0 a 100)'];
  for (const x of filasLista()) lineas.push([String(x.puesto), x.centro || '', D.ciudades[x.centro] || '', x.tomo_en_peligro,
    x.vault === null ? '' : String(x.vault), x.ranura === null ? '' : String(x.ranura), x.fabricante, x.model, capTexto(x.capacidad_tb),
    String(x.edad), x.serial_number, decCsv(x.probabilidad * 100, 2)].join(';'));
  return lineas.join('\r\n') + '\r\n';
}
function descargar() {
  const url = URL.createObjectURL(new Blob(['\ufeff' + textoCsv()], {type: 'text/csv;charset=utf-8'}));
  const a = document.createElement('a'); a.href = url; a.download = nombreCsv(); document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------- dirección de la página, filtros y pestañas
function leerDireccion(hash) {
  const p = new URLSearchParams(String(hash || '').replace(/^#/, ''));
  E.pestana = PESTANAS.includes(p.get('pestana')) ? p.get('pestana') : 'vision';
  E.fabricante = D.fabricantes.includes(p.get('fabricante')) ? p.get('fabricante') : null;
  const c = p.has('capacidad') ? Number(p.get('capacidad')) : null; E.capacidad = D.capacidades.includes(c) ? c : null;
  const e = p.has('edad') ? Number(p.get('edad')) : null; E.edad = D.edades.includes(e) ? e : null;
  E.centro = D.centros.includes(p.get('centro')) ? p.get('centro') : null;
  const n = p.has('lista') ? Number(p.get('lista')) : D.lista.principal; E.lista = D.lista.listas.includes(n) ? n : D.lista.principal;
}
function escribirDireccion() {
  const p = ['pestana=' + E.pestana];
  for (const k of ['centro', 'fabricante', 'capacidad', 'edad']) if (E[k] !== null) p.push(k + '=' + encodeURIComponent(E[k]));
  if (E.lista !== D.lista.principal) p.push('lista=' + E.lista);
  history.replaceState(null, '', '#' + p.join('&'));
}
function opciones(id, valores, texto) {
  document.getElementById(id).innerHTML = '<option value="">Todos</option>' + valores.map(v => `<option value="${esc(v)}">${esc(texto(v))}</option>`).join('');
}
function dibujar() {
  for (const p of PESTANAS) {
    document.getElementById('p-' + p).hidden = p !== E.pestana;
    const b = document.getElementById('b-' + p); b.setAttribute('aria-selected', String(p === E.pestana)); b.tabIndex = p === E.pestana ? 0 : -1;
  }
  document.getElementById('f-fabricante').value = E.fabricante === null ? '' : E.fabricante;
  document.getElementById('f-capacidad').value = E.capacidad === null ? '' : String(E.capacidad);
  document.getElementById('f-edad').value = E.edad === null ? '' : String(E.edad);
  document.getElementById('f-centro').value = E.centro === null ? '' : E.centro;
  document.getElementById('f-lista').value = String(E.lista);
  document.getElementById('quitar').disabled = !hayFiltro();
  let viendo;
  if (E.pestana === 'lista') {
    const n = D.lista.recuento.filter(r => (E.fabricante === null || r[0] === E.fabricante) && (E.capacidad === null || r[1] === E.capacidad)
      && (E.edad === null || r[2] === E.edad) && (E.centro === null || r[3] === E.centro)).reduce((s, r) => s + r[4], 0);
    viendo = `Viendo: ${seleccionTexto()} · ${num(n)} ${n === 1 ? 'disco' : 'discos'} con riesgo calculado el 01/06/2026`;
  } else {
    let n = 0; for (let i = 0; i < N; i++) if (T.mes[i] === D.i_ultimo[1] && pasa(i)) n += T.fotos[i];
    viendo = `Viendo: ${seleccionTexto()} · ${num(n)} ${n === 1 ? 'disco' : 'discos'} de datos el 01/06/2025`;
  }
  document.getElementById('viendo').textContent = viendo;
  ({vision: dibujarVision, modelos: dibujarModelos, edad: dibujarEdad, centros: dibujarCentros, lista: dibujarLista})[E.pestana]();
  ocultarTip();
}
function cambiar() { escribirDireccion(); dibujar(); }

// ---------------------------------------------------------------- etiquetas al pasar el ratón y con el tabulador
const TIP = document.getElementById('tip');
function mostrarTip(el) {
  TIP.textContent = el.dataset.tip; TIP.hidden = false;
  const r = el.getBoundingClientRect(), w = TIP.offsetWidth, h = TIP.offsetHeight;
  let x = r.left + r.width / 2 - w / 2, y = r.bottom + 8;
  if (y + h > window.innerHeight) y = r.top - h - 8;
  x = Math.max(8, Math.min(x, window.innerWidth - w - 8)); y = Math.max(8, y);
  TIP.style.left = x + 'px'; TIP.style.top = y + 'px';
}
function ocultarTip() { TIP.hidden = true; }
document.addEventListener('mouseover', ev => { const el = ev.target.closest('[data-tip]'); if (el) mostrarTip(el); else ocultarTip(); });
document.addEventListener('focusin', ev => { const el = ev.target.closest('[data-tip]'); if (el) mostrarTip(el); });
document.addEventListener('focusout', ocultarTip);
document.addEventListener('keydown', ev => { if (ev.key === 'Escape') ocultarTip(); });
document.addEventListener('mouseleave', ocultarTip);

// ---------------------------------------------------------------- arranque
opciones('f-fabricante', D.fabricantes, v => v);
opciones('f-capacidad', D.capacidades, v => capTexto(v) + ' TB');
opciones('f-edad', D.edades, v => v === 1 ? '1 año' : v + ' años');
opciones('f-centro', D.centros, v => nombreCentro(v));
document.getElementById('f-lista').innerHTML = D.lista.listas.map(n => `<option value="${n}">${num(n)}</option>`).join('');
document.getElementById('f-fabricante').addEventListener('change', ev => { E.fabricante = ev.target.value || null; cambiar(); });
document.getElementById('f-capacidad').addEventListener('change', ev => { E.capacidad = ev.target.value === '' ? null : Number(ev.target.value); cambiar(); });
document.getElementById('f-edad').addEventListener('change', ev => { E.edad = ev.target.value === '' ? null : Number(ev.target.value); cambiar(); });
document.getElementById('f-centro').addEventListener('change', ev => { E.centro = ev.target.value || null; cambiar(); });
document.getElementById('f-lista').addEventListener('change', ev => { E.lista = Number(ev.target.value); cambiar(); });
document.getElementById('quitar').addEventListener('click', () => { E.fabricante = E.capacidad = E.edad = E.centro = null; cambiar(); });
document.getElementById('descargar').addEventListener('click', descargar);
document.querySelectorAll('[role=tab]').forEach(b => {
  b.addEventListener('click', () => { E.pestana = b.dataset.p; cambiar(); });
  b.addEventListener('keydown', ev => {
    const i = PESTANAS.indexOf(E.pestana), d = ev.key === 'ArrowRight' ? 1 : ev.key === 'ArrowLeft' ? -1 : 0;
    if (!d) return;
    E.pestana = PESTANAS[(i + d + PESTANAS.length) % PESTANAS.length]; cambiar(); document.getElementById('b-' + E.pestana).focus();
  });
});
window.addEventListener('hashchange', () => { leerDireccion(location.hash); dibujar(); });
window.CUADRO = {irA: h => { leerDireccion(h); dibujar(); }, nombreCsv, textoCsv};
leerDireccion(location.hash); dibujar();
"""


def montar_html(datos):
    """El HTML entero, con los datos dentro de un bloque JSON (los «</» escapados para no cerrar el script)."""
    publicos = {k: v for k, v in datos.items() if not k.startswith("_")}
    js_datos = json.dumps(publicos, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    return ("<!doctype html>\n<html lang=\"es\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>Fallos y coste de los discos</title>\n<style>" + CSS + "</style>\n</head>\n<body>\n" + CUERPO
            + "\n<script type=\"application/json\" id=\"datos\">" + js_datos + "</script>\n<script>" + JS
            + "</script>\n</body>\n</html>\n")


# =====================================================================================================================
# COMPROBACIONES
# =====================================================================================================================

def comparar_con_json(dp, cifras, datos):
    """Cada cifra que el cuadro repite, sin filtros, frente a su JSON; las de B3 y B5 recalculadas con las funciones
    copiadas desde dias_por_tramo. Devuelve una lista de {nombre, cuadro, json, coinciden}."""
    filas = []

    def apunta(nombre, cuadro, del_json):
        """Una comparación."""
        filas.append({"nombre": nombre, "cuadro": cuadro, "json": del_json, "coinciden": iguales(cuadro, del_json)})

    sin = resumen(datos, {"lista": datos["lista"]["principal"]})
    v = {c["id"]: c["valor"] for c in sin["vision"]}
    apunta("discos de datos el 01/06/2025 (B1.tablas.serie_mensual)", v["discos"], cifras["discos_b1"]["2025-06-01"])
    apunta("coste de los fallos de 2024 (coste_fallos_usd_2024)", v["coste"], cifras["coste_2024"])
    apunta("coste de los fallos de 2024 con garantía", datos["coste_2024_garantia"], cifras["coste_2024_garantia"])
    # B2: el intervalo copiado del 09 da el de cada modelo del ranking
    for r in cifras["b2"]:
        t, lo, hi = intervalo_poisson(r["fallos"], r["dias_disco"])
        apunta(f"B2 {r['model']} tasa", t, r["tasa"])
        apunta(f"B2 {r['model']} desde", lo, r["desde"])
        apunta(f"B2 {r['model']} hasta", hi, r["hasta"])
    # B4: lo que lleva el cuadro de cada modelo, y la mediana de la parte de los fallos
    b4 = {r["model"]: r for r in datos["b4"]}
    for r in cifras["b4"]:
        for k in ("coste_tb_ano", "coste_desde", "coste_hasta", "tasa", "fallos"):
            apunta(f"B4 {r['model']} {k}", b4[r["model"]][k], r[k])
    m = {c["id"]: c["valor"] for c in sin["modelos"]}
    apunta("B4 mediana de la parte de los fallos", m["mediana_fallos"], cifras["b4_resumen"]["mediana_parte_fallos_pct"])
    apunta("B4 modelos con puesto", sum(r["puesto"] is not None for r in datos["b4"]), cifras["b4_resumen"]["con_puesto"])
    # B3: recalculada con tasa_por_edad y phi_edad copiadas, desde dias_por_tramo
    ph3 = phi_edad(dp)
    apunta("B3 φ", ph3["phi"], cifras["b3_phi"])
    for mia, js in zip(tasa_por_edad(dp, phi=ph3["phi"]), cifras["b3"]):
        for k in ("dias_disco", "fallos", "tasa", "desde", "hasta", "sube", "sin_conclusion"):
            apunta(f"B3 edad {js['edad']} {k}", mia[k], js[k])
    # B5: recalculada con ajustada copiada, desde dias_por_tramo
    aj, ph5 = ajustada(dp.loc[dp["mes"] >= INICIO_SITIO])
    apunta("B5 φ", ph5["phi"], cifras["b5_phi"])
    js5 = {r["centro"]: r for r in cifras["b5"]}
    for _, x in aj.iterrows():
        for k in ("observados", "esperados", "razon", "razon_desde", "razon_hasta"):
            apunta(f"B5 {x['centro']} {k}", x[k], js5[x["centro"]][k])
        mio = veredicto(x["centro"], x["dias"] / ANOS_SITIO, x["observados"], x["razon_desde"], x["razon_hasta"])
        filas.append({"nombre": f"B5 {x['centro']} veredicto", "cuadro": mio, "json": js5[x["centro"]]["veredicto"],
                      "coinciden": mio == js5[x["centro"]]["veredicto"]})
    # Los esperados por fila suman los de ajustada en cada centro
    por = centros_por_fila(datos, {})
    for _, x in aj.iterrows():
        apunta(f"B5 {x['centro']} esperados por fila", por[x["centro"]]["esperados"], x["esperados"])
    # La prueba final: la media de los meses medidos y la de los totales
    apunta("prueba final, lista de 100, modelo (media de los meses)", datos["final"]["modelo_100"],
           cifras["final_totales"]["modelo_100"])
    apunta("prueba final, lista de 100, regla (media de los meses)", datos["final"]["regla_100"],
           cifras["final_totales"]["regla_100"])
    return filas


def control_anos(datos):
    """Días de disco, fallos y tasa del último año y del anterior, sin filtros, para compararlos con la petición."""
    a = _arrays(datos)
    salida = {}
    for nombre, (i0, i1) in (("ultimo_ano", datos["i_ultimo"]), ("ano_anterior", datos["i_anterior"])):
        en = (a["mes"] >= i0) & (a["mes"] <= i1)
        dias, fallos = float(a["dias"][en].sum()), int(a["fallos"][en].sum())
        t, lo, hi = intervalo_poisson(fallos, dias)
        salida[nombre] = {"dias_disco": dias, "fallos": fallos, "tasa": t, "desde": lo, "hasta": hi}
    return salida


def dias_repartidos(datos):
    """Para cada filtro, los días de disco de sus valores suman los de dias_por_tramo sin filtro (salvo el centro, cuyos
    días sin dato van aparte: sus valores más «sin dato» suman el total)."""
    total = dias_de(datos, {})
    a = _arrays(datos)
    sin_dato = float(a["dias"][a["centro"] < 0].sum())
    salida = {}
    for clave, valores in (("fabricante", datos["fabricantes"]), ("capacidad", datos["capacidades"]),
                           ("edad", datos["edades"]), ("centro", datos["centros"])):
        suma = sum(dias_de(datos, {clave: v}) for v in valores) + (sin_dato if clave == "centro" else 0.0)
        salida[clave] = {"suma": suma, "total": total, "coinciden": abs(suma - total) <= 1e-6 * total}
    return salida


# =====================================================================================================================
# PRINCIPAL
# =====================================================================================================================

def principal(raiz=RAIZ):
    """Comprueba, calcula, comprueba otra vez y escribe el HTML, el CSV y el JSON del cuadro."""
    if Path(sys.prefix).name != ENTORNO:
        raise Parada(f"este no es el intérprete del caso: {sys.executable}")
    marca = reloj()
    huella_antes = huella_data(raiz)
    marca("huella de data/ al empezar")
    validaciones = {}
    # Entradas: existen, traen su fecha y son más nuevas que su script
    entradas = leer_entradas(raiz)
    validaciones["fechas_iguales"] = comprobar_fechas(entradas)
    carpeta = carpeta_de_la_lista(raiz)
    pares = [(Path(raiz) / "informes" / n, Path(raiz) / d["script"]) for n, d in entradas.items()]
    pares += [(carpeta / f"predicciones_{MES_LISTA}.parquet", Path(raiz) / EJECUTAR),
              (carpeta / f"resumen_{MES_LISTA}.json", Path(raiz) / EJECUTAR)]
    validaciones["entradas_mas_nuevas"] = comprobar_orden(pares)
    # Las tablas de trabajo son las que usaron los JSON de análisis (sus huellas)
    usadas = {e["ruta"]: e["sha256"] for e in entradas[EDAD]["entradas"]}
    tablas_iguales = {r: sha256(Path(raiz) / r) == usadas.get(r) for r in (DIAS_POR_TRAMO, DIM_MODELO)}
    if not all(tablas_iguales.values()):
        raise Parada(f"dias_por_tramo o dim_modelo no son los que usaron los JSON de análisis: {tablas_iguales}")
    marca("entradas, fechas y orden")
    cifras = leer_cifras(entradas)
    dp = leer_tramos(raiz)
    conf = leer_json(Path(raiz) / CONFIGURACION)
    dec = leer_json(Path(raiz) / DECISIONES)
    mapeo, minimo = dec["modelos"]["mapeo"], dec["capacidad"]["minimo_valido_bytes"]
    # La lista y su foto
    marca("cifras y tramos")
    unida, foto, info = leer_lista(raiz, mapeo, minimo)
    marca("lista y foto preparada")
    validaciones["huella_del_modelo"] = info["huella_modelo_resumen"] == info["huella_modelo_en_uso"]
    validaciones["filas_con_foto"] = info["filas_con_foto"]
    validaciones["motivos_iguales"] = info["motivos_iguales"] and info["listas_iguales_a_los_primeros"]
    validaciones["edad_igual_con_toda_la_historia"] = info["edad_igual_con_toda_la_historia"]
    # Los tomos en peligro el 01/06/2026, y su segunda vía
    fallos = pd.read_parquet(Path(raiz) / FALLOS_RESERVA)
    ventanas = _leer_ventanas(raiz)
    pares_foto = foto[["model", "capacity_bytes"]].assign(model=foto["model"].replace(mapeo))
    sitios, aparte = sitios_de_fallos(fallos, ventanas, mapeo, minimo, FECHA_LISTA, pares_foto)
    peligro = tomos_en_peligro(sitios, FECHA_LISTA)
    marca("tomos en peligro")
    bucle, aparte_bucle = tomos_en_peligro_bucle(fallos, ventanas, mapeo, minimo, FECHA_LISTA, pares_foto)
    validaciones["tomos_segunda_via"] = (bucle == peligro and aparte_bucle == aparte)
    marca("segunda vía de los tomos")
    dias = (pd.Timestamp(FECHA_LISTA) - sitios["dia_fallo"]) / pd.Timedelta(days=1)
    en = sitios["datos"] & sitios["tomo"].notna() & (dias > 0) & (dias < sitios["plazo_dias"])
    por_tomo = sitios.loc[en.to_numpy()].groupby("tomo").size()
    peligro_tabla = {"tomos": peligro, "fallos": int(en.sum()),
                     "por_tomo": [{"tomo": t, "centro": t.split("|")[0], "fallos": int(n)} for t, n in por_tomo.items()]}
    # Los datos del HTML y las comprobaciones con ellos
    datos = preparar_datos(dp, cifras, unida, peligro_tabla, aparte, conf)
    marca("datos del HTML")
    comparadas = comparar_con_json(dp, cifras, datos)
    validaciones["cifras_iguales_a_los_json"] = all(c["coinciden"] for c in comparadas)
    marca("comparación con los JSON")
    repartidos = dias_repartidos(datos)
    validaciones["dias_repartidos_suman"] = (all(x["coinciden"] for x in repartidos.values())
                                            and abs(dias_de(datos, {}) - float(dp["dias_disco"].sum())) <= 1e-3)
    validaciones["sin_resultados_escritos"] = buscar_resultados_escritos(Path(__file__).read_text(encoding="utf-8")) == []
    html_texto = montar_html(datos)
    vetadas = sin_prohibidas(html_texto)
    validaciones["sin_palabras_vetadas"] = vetadas == []
    fallan = [k for k, v in validaciones.items() if v is not True]
    if fallan:
        malas = [c for c in comparadas if not c["coinciden"]][:10]
        raise Parada(f"no pasan estas comprobaciones: {fallan}; cifras distintas: {malas}; vetadas: {vetadas}")
    # Se escribe el HTML y el CSV; después se mira que data/ no ha cambiado
    marca("días repartidos, montaje del HTML y validaciones")
    SALIDA_HTML.write_text(html_texto, encoding="utf-8")
    lista_mil = filas_lista(datos, {"lista": 1000})
    SALIDA_CSV.write_text(texto_csv(lista_mil, 1000, {}, FECHA_LISTA), encoding="utf-8-sig", newline="")
    huella_despues = huella_data(raiz)
    marca("HTML, CSV y huella de data/ al acabar")
    validaciones["huella_data_igual"] = huella_antes == huella_despues
    if not validaciones["huella_data_igual"]:
        SALIDA_HTML.unlink(missing_ok=True)
        SALIDA_CSV.unlink(missing_ok=True)
        raise Parada("la huella de data/ cambió entre el principio y el final: se borran el HTML y el CSV")
    sin_filtros = resumen(datos, {"lista": datos["lista"]["principal"]})
    js = {"script": SCRIPT, "fecha_datos": FECHA_DATOS, "fecha_lista": FECHA_LISTA,
          "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"),
          "entradas": [{"ruta": Path(e).relative_to(raiz).as_posix(), "script": Path(s).relative_to(raiz).as_posix(),
                        "sha256": sha256(e)} for e, s in pares]
                      + [{"ruta": r, "sha256": sha256(Path(raiz) / r), "igual_a_la_de_los_json": tablas_iguales[r]}
                         for r in (DIAS_POR_TRAMO, DIM_MODELO)],
          "cifras_sin_filtros": sin_filtros,
          "cifras_de_control": control_anos(datos),
          "comparadas_con_los_json": comparadas,
          "tomos_en_peligro": {"fecha": FECHA_LISTA, "tomos": len(peligro), "fallos_rehaciendose": peligro_tabla["fallos"],
                               "aparte": aparte, "segunda_via": {"tomos": len(bucle), "aparte": aparte_bucle,
                                                                 "de": "bucle fallo a fallo sobre las ventanas en bruto"}},
          "lista": {k: v for k, v in info.items()} | {"en_la_lista_1000": len(lista_mil)},
          "dias_repartidos": repartidos,
          "combinacion_mas_estrecha": combinacion_mas_estrecha(datos),
          "huella_data": {"antes": huella_antes, "despues": huella_despues},
          "validaciones": validaciones,
          "decisiones": [
              "Con un filtro, la tasa por edad lleva el φ de B3 (5,02), como hace el script 09 con los fabricantes y "
              "los modelos; los centros miden su φ con la selección, como ajustada() del 11.",
              "Un trimestre va en gris si su año natural no llega a 50.000 días de disco o el trimestre a 20 fallos; un "
              "año de edad, si tiene menos de 20 fallos o de 50.000 días de disco por año del periodo.",
              "Las entradas de tablas (dias_por_tramo y dim_modelo) se comparan por huella con la que usaron los JSON de "
              "análisis: son más viejas que scripts/05, que se editó después sin volver a lanzarse.",
              "El modelo de un fallo de la reserva es el de la última fila de su ventana hasta el día del fallo; su "
              "capacidad, la única válida de su modelo en las ventanas y la foto de junio de 2026.",
              "Los fallos sin tomo, sin capacidad o de arranque se cuentan entre los de menos días que el plazo más "
              "largo de los discos de datos (los que aún podían estar rehaciéndose)."]}
    SALIDA_JSON.write_text(json.dumps(nativo(js), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    marca("JSON del cuadro")
    return js


if __name__ == "__main__":
    try:
        r = principal()
    except Parada as e:
        print(f"PARADO: {e}")
        sys.exit(1)
    s = r["cifras_sin_filtros"]
    print("OK: informes/cuadro_mando.html, informes/cuadro_mando.json e informes/cuadro_mando_lista.csv")
    for p, cs in s.items():
        print(p, {c["id"]: c["valor"] for c in cs})
    print("tomos en peligro:", r["tomos_en_peligro"]["tomos"], "fallos rehaciéndose:",
          r["tomos_en_peligro"]["fallos_rehaciendose"], "aparte:", r["tomos_en_peligro"]["aparte"])
