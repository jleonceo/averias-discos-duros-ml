"""Prueba de scripts/11_indicadores_centros_avisos_tomos.py.

Parte 1, las piezas sueltas. Carga el script como módulo (su trabajo está dentro de `if __name__ == "__main__":`, así
que cargarlo no lo ejecuta) y prueba cada función con datos pequeños escritos aquí:
  - el intervalo exacto de Poisson de una tasa y de una razón, contra scipy.stats.gamma (otra implementación);
  - la paridad supuesta, los tramos de edad, de temperatura, de arranques y de tercios, y el rango con empates;
  - el reparto de los días por las fotos (criterio 7), con una celda sin foto y una foto sin días;
  - la tasa ajustada por centro, contra una cuenta a mano;
  - los tomos con k fallos en d días, los discos a la vez, el recuento de coincidencias en bucle y el azar;
  - el riesgo vivo de un mes, contra la binomial escrita a mano;
  - el desenlace a 90 días por las dos cuentas, y repetido solo con las fotos de Seagate (petición 17);
  - los grupos de un factor del bloque 8 y el minicubo;
  - cada comprobación con un caso que da verde y otro que tiene que dar rojo (error 24), también la de las fotos de
    validación, la de las partes que suman el total y la de la palabra vetada;
  - cada una de las nueve validaciones con un caso que tiene que dar rojo, y la búsqueda de resultados escritos.
Parte 2, el script entero sobre un caso pequeño. Monta en tests/tmp_indicadores_centros/ las tablas que lee el script,
con el tipo de cada columna tomado del parquet real (pyarrow.parquet.read_schema, sin cargar datos), su
informes/transformacion-datos.json con las huellas, los JSON de las peticiones 13 y 14 y un data/raw/. Ejecuta el script
con -W error y comprueba las cifras contra las calculadas aquí con bucles de Python, sin pandas. Después, cinco casos
que tienen que parar:
  - centro_mes con un fallo de más: la segunda vía de los días y fallos por centro no coincide, ERROR;
  - fallos_detalle con una coincidencia cambiada: el recuento en bucle no coincide con la columna, ERROR;
  - un fallo cuya última foto anterior no está en fotos_riesgo: los fallos con su foto no cuadran, ERROR;
  - la huella de una tabla distinta de la de transformacion-datos.json, ERROR;
  - el JSON de la petición 14 en PARADO: el script no calcula, PARADO.
Parte 3, el JSON real, si existe: las cifras de CONTROLES de la petición (prompts/15_…), escritas como las da la petición, y
dos cifras rehechas con pyarrow, sin pandas: los fallos de discos de datos desde el 01/07/2023 en
recuento_diario_corregido, frente a los fallos de B7, y las fotos con smart_90_raw no vacío.
Además, ni el JSON ni el informe llevan la palabra vetada para el conjunto de discos.

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import calendar
import datetime as dt
import hashlib
import importlib.util
import json
import math
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "11_indicadores_centros_avisos_tomos.py"
TMP = CASO / "tests" / "tmp_indicadores_centros"
SALIDA = "informes/indicadores__centros_avisos_tomos.json"
SALIDA_MD = "informes/indicadores__centros_avisos_tomos.md"
PROCESADOS = CASO / "data" / "processed"
# La palabra vetada para el conjunto de discos (el responsable del caso, 17/11; una nota del caso), partida para que esta prueba no la lleve
VETADA = "flo" + "ta"
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si no se cumple y lo imprime."""
    print(("ok    " if condicion else "FALLA ") + caso)
    if not condicion:
        FALLOS.append(caso)


def cerca(a, b, tol=1e-9):
    """Cierto si dos números están a menos de `tol` (relativo o absoluto)."""
    if a is None or b is None:
        return False
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def sha256(ruta):
    """Huella SHA-256 de un fichero."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def cargar_modulo():
    """Carga el script como módulo, sin ejecutar su trabajo; None si no existe o no carga."""
    if not SCRIPT.exists():
        comprobar(False, f"existe {SCRIPT.relative_to(CASO)}")
        return None
    spec = importlib.util.spec_from_file_location("indicadores_11", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(modulo)
    except Exception as e:  # noqa: BLE001 - la prueba dice qué falló al cargar
        comprobar(False, f"el script carga como módulo ({type(e).__name__}: {e})")
        return None
    return modulo


# ---------------------------------------------------------------------------------------------------------------
# 2. Parte 1 · las piezas sueltas
# ---------------------------------------------------------------------------------------------------------------
def probar_piezas(m):
    """Cada función con datos escritos aquí; cada comprobación y validación con su caso en rojo."""
    import numpy as np
    import pandas as pd
    from scipy import stats

    # 2.1 Intervalos exactos de Poisson, contra la gamma
    t, lo, hi = m.intervalo_poisson(476, 12111055)
    comprobar(cerca(t, 100 * 365 * 476 / 12111055)
              and cerca(lo, stats.gamma.ppf(0.025, 476) * 36500 / 12111055)
              and cerca(hi, stats.gamma.ppf(0.975, 477) * 36500 / 12111055), "Poisson de una tasa igual que con la gamma")
    rz, lo, hi = m.razon_poisson(30, 20.0)
    comprobar(cerca(rz, 1.5) and cerca(lo, stats.gamma.ppf(0.025, 30) / 20) and cerca(hi, stats.gamma.ppf(0.975, 31) / 20),
              "Poisson de una razón: observados / esperados, con la gamma")
    rz, lo, hi = m.razon_poisson(0, 5.0)
    comprobar(rz == 0 and lo == 0 and hi > 0, "razón con 0 observados: desde 0")

    # 2.2 Paridad y tramos
    comprobar([m.paridad(c) for c in (4, 8, 10, 12, 14, 16, 22)] == [3, 3, 4, 4, 4, 5, 5], "paridad supuesta por capacidad")
    comprobar(list(m.tramo_edad(np.array([0.2, 1.0, 7.99, 8.0, 12.5]))) == ["00_0", "01_1", "07_7", "08_8_o_mas",
                                                                              "08_8_o_mas"], "tramos de edad")
    comprobar(list(m.tramo_temperatura(np.array([-3.01, -3.0, 2.99, 3.0, np.nan]))) == [0, 1, 1, 2, -1],
              "temperatura: frío < −3, medio de −3 a < 3, caliente ≥ 3, vacío sin tramo")
    comprobar(list(m.tramo_arranques(np.array([1.0, 1.0001, 2.0, 2.01, np.nan]))) == [0, 1, 1, 2, -1],
              "arranques: ≤ 1, de 1 a 2, más de 2, vacío sin tramo")
    comprobar(list(m.tramo_tercio(np.array([1 / 3, 0.34, 2 / 3, 0.67, np.nan]))) == [0, 1, 1, 2, -1],
              "tercios: ≤ 1/3, ≤ 2/3, el resto, vacío sin tramo")
    pct = m.rango_por_grupo(np.array([1, 1, 1, 2, 2]), np.array([5.0, 5.0, 9.0, 1.0, np.nan]))
    comprobar(cerca(pct[0], 0.5) and cerca(pct[1], 0.5) and cerca(pct[2], 1.0) and cerca(pct[3], 1.0)
              and np.isnan(pct[4]), "rango por grupo con empates en la media y el vacío fuera")

    # 2.3 Reparto de los días por las fotos: celda 1 con dos fotos, celda 2 sin foto, celda 3 sin días
    rep = m.pesos_por_celda(np.array([1, 1, 3]), pd.Series({1: 100.0, 2: 40.0}))
    comprobar(list(rep["pesos"]) == [50.0, 50.0, 0.0] and rep["dias_sin_foto"] == 40.0 and rep["celdas_sin_foto"] == 1
              and rep["fotos_sin_dias"] == 1, "reparto: cada foto pesa los días de su celda entre sus fotos")

    # 2.4 Tasa ajustada, a mano: modelo A edad 1 en dos centros, modelo B edad 1 solo en el centro y
    # Petición 19: la mezcla lleva el trimestre; todo en un mes, la cuenta es la de antes. ajustada devuelve también φ
    dpt = pd.DataFrame({"model": ["A", "A", "B"], "centro": ["x", "y", "y"], "edad_anos_cumplidos": [1, 1, 1],
                        "mes": pd.to_datetime(["2024-01-01"] * 3).astype("datetime64[ms]"),
                        "dias_disco": [1000.0, 3000.0, 2000.0], "fallos": [4, 4, 8]})
    aj = m.ajustada(dpt)
    aj = (aj[0] if isinstance(aj, tuple) else aj).set_index("centro")
    # tasa de A = 8/4000; esperados de x = 1000 × 8/4000 = 2; de y = 3000 × 8/4000 + 2000 × 8/2000 = 14
    comprobar(cerca(aj.loc["x", "esperados"], 2.0) and cerca(aj.loc["y", "esperados"], 14.0)
              and cerca(aj.loc["x", "razon"], 2.0) and cerca(aj.loc["y", "razon"], 12 / 14), "ajustada: esperados y razón a mano")
    todos = 36500 * 16 / 6000
    comprobar(cerca(aj.loc["x", "tasa_ajustada"], 2.0 * todos), "ajustada: razón × tasa de todos")
    comprobar(m.veredicto("x", 60000, 25, 1.1, 1.5) == "falla más por sí mismo"
              and m.veredicto("x", 60000, 25, 0.5, 0.9) == "falla menos"
              and m.veredicto("x", 60000, 25, 0.9, 1.2) == "no se distingue"
              and m.veredicto("x", 60000, 19, 1.1, 1.5) == "sin conclusión"
              and m.veredicto("x", 49999, 25, 1.1, 1.5) == "sin conclusión"
              and m.veredicto("sin dato", 60000, 25, 1.1, 1.5) == "aparte", "veredicto de un centro")

    # 2.5 Tomos: k en d días, a la vez, bucle y azar
    tomo = np.array(["a", "a", "a", "b", "b", "c"])
    dia = np.array([0, 3, 9, 100, 140, 5])
    plazo = np.array([9.0, 9.0, 9.0, 13.0, 13.0, 9.0])
    k2 = m.k_en_d(tomo, dia, 2, 7)
    comprobar(set(k2) == {"a"} and k2["a"] == 1, "dos fallos en 7 días: el tomo a, completado por su 2.º fallo")
    comprobar(set(m.k_en_d(tomo, dia, 3, 30)) == {"a"} and set(m.k_en_d(tomo, dia, 2, 40)) == {"a", "b"},
              "tres en 30 días y dos en 40 días")
    comprobar(list(m.a_la_vez(tomo, dia, plazo)) == [1, 2, 2, 1, 1, 1],
              "a la vez: el 3.º de a llega cuando el 1.º ya se rehízo (día 9 = 0 + 9)")
    comprobar(m.coincidencias_bucle(["a", "a", "a", None], [0, 3, 9, 4], [9, 9, 9, 9]) == (3, 1, 2),
              "bucle: 3 fallos con tomo, 1 tomo, 2 coincidencias")
    az = m.azar_tomos(np.array(["p"] * 4 + ["q"] * 2), np.array(["a", "a", "b", "b", "c", "c"]),
                      np.array([0, 50, 100, 150, 0, 3]), [(2, 7)], 20, 68)
    comprobar(len(az[(2, 7)]) == 20 and min(az[(2, 7)]) >= 1, "azar: 20 repeticiones; el tomo c siempre cuenta")
    az2 = m.azar_tomos(np.array(["p"] * 4 + ["q"] * 2), np.array(["a", "a", "b", "b", "c", "c"]),
                       np.array([0, 50, 100, 150, 0, 3]), [(2, 7)], 20, 68)
    comprobar(az == az2, "azar: con la misma semilla, la misma cifra")

    # 2.6 Riesgo vivo de un mes: tomo t1 con 3 discos (2 avisan), t2 con 2 (0 avisan)
    rv = m.riesgo_vivo(np.array([5, 5, 5, 5, 5]), np.array(["t1", "t1", "t1", "t2", "t2"]),
                       np.array([True, True, False, False, False]))
    p = 2 / 5
    e2 = (1 - stats.binom.cdf(1, 3, p)) + (1 - stats.binom.cdf(1, 2, p))
    comprobar(rv[0]["dos_o_mas"] == 1 and rv[0]["tres_o_mas"] == 0 and cerca(rv[0]["esperados_dos"], e2)
              and cerca(rv[0]["esperados_tres"], p ** 3), "riesgo vivo: observados y binomial a mano")

    # 2.7 Desenlace: foto del día 0; fallo del disco 1 el día 90 (cuenta), del disco 2 el 91 (no), del 3 el 0 (no)
    sc = np.array([1, 2, 3, 4])
    fd = np.array([0, 0, 0, 0])
    sf, df_ = np.array([1, 2, 3]), np.array([90, 91, 0])
    a, b = m.falla_en_90_merge(sc, fd, sf, df_), m.falla_en_90_busqueda(sc, fd, sf, df_)
    comprobar(list(a) == [True, False, False, False] and list(b) == list(a), "desenlace: falla del día 1 al 90, dos cuentas")

    # 2.8 Grupos de un factor: g1 entra (20, 20, 20), g2 no (20, 5, 20); una foto sin tramo
    fg = np.array([1, 1, 1, 2, 2, 2, 1])
    ft = np.array([0, 1, 2, 0, 1, 2, -1])
    peso = np.array([1000.0, 2000.0, 1000.0, 500.0, 500.0, 500.0, 77.0])
    lg = np.repeat([1, 1, 1, 2, 2, 2, 1], [20, 20, 20, 20, 5, 20, 3])
    lt = np.repeat([0, 1, 2, 0, 1, 2, -1], [20, 20, 20, 20, 5, 20, 3])
    gr = m.grupos_factor(fg, ft, peso, lg, lt, 20)
    comprobar(gr["grupos"] == 2 and gr["grupos_entran"] == 1 and gr["fallos_entran"] == 60
              and gr["aparte"]["fallos"] == 45 and gr["sin_tramo"]["fallos"] == 3, "factor: entra uno, aparte otro")
    tr = {x["tramo"]: x for x in gr["tramos"]}
    # tasa del grupo 1 = 60 / 4000; esperados del tramo 1 = 2000 × 60/4000 = 30; razón = 20/30
    comprobar(cerca(tr[1]["esperados"], 30.0) and cerca(tr[1]["razon"], 20 / 30) and cerca(tr[0]["razon"], 20 / 15),
              "factor: esperados por la tasa de su grupo y razón a mano")

    # 2.9 Minicubo: dos dimensiones, cuatro fotos
    dims = {"d1": np.array(["a", "a", "b", "b"]), "d2": np.array(["x", "y", "x", "y"])}
    fallo_dims = {"d1": np.array(["a"] * 30 + ["b"] * 10), "d2": np.array(["x"] * 25 + ["y"] * 15)}
    n1, n2 = m.minicubo(dims, np.array([40000.0, 30000.0, 20000.0, 10000.0]), fallo_dims, 50000, 20)
    v = {(x["dimension"], x["valor"]): x for x in n1}
    comprobar(v[("d1", "a")]["dias"] == 70000 and v[("d1", "a")]["fallos"] == 30
              and cerca(v[("d1", "a")]["tasa"], 36500 * 30 / 70000) and v[("d1", "b")]["sin_conclusion"] is True,
              "minicubo nivel 1: días, fallos, tasa y sin conclusión bajo el mínimo")
    comprobar(len(n2) == 1 and n2[0]["dimensiones"] == ["d1", "d2"] and n2[0]["celdas"] == 4,
              "minicubo nivel 2: un par de dimensiones, cuatro celdas")
    # Un peso grande y 20.000 pesos diminutos: una suma uno detrás de otro pierde los pequeños (6e-4 días); los días
    # de cada valor tienen que sumar lo mismo que la suma exacta de los pesos, a menos de 1e-6 (petición)
    pesos = np.array([1e9] + [3e-8] * 20000)
    n1, _ = m.minicubo({"d1": np.array(["a"] * len(pesos))}, pesos, {"d1": np.array(["a"])}, 1, 1)
    comprobar(abs(n1[0]["dias"] - math.fsum(pesos)) < 1e-6,
              f"minicubo: los días de un valor, sin perder decimales al sumar (error {abs(n1[0]['dias'] - math.fsum(pesos)):.1e})")

    # 2.10 Comprobaciones, cada una en verde y en rojo
    comprobar(m.comp_unidad(["a", "b"]) is True and m.comp_unidad(["a", "a"]) is False, "unidad: repetida, rojo")
    comprobar(m.comp_empates([1.0, 1.0, 2.0], [1, 1, 3]) is True and m.comp_empates([1.0, 1.0], [1, 2]) is False,
              "empates: el mismo valor con distinto puesto, rojo")
    comprobar(m.comp_minimo([True, False], [60000, 40000], [25, 30], 50000, 20) is True
              and m.comp_minimo([True], [60000], [19], 50000, 20) is False, "mínimo: conclusión con 19 fallos, rojo")
    comprobar(m.comp_referencia([100.0, 200.0], 300.0) is True and m.comp_referencia([100.0, 200.0], 301.0) is False,
              "referencia con otras filas, rojo")
    comprobar(m.comp_azar(5, 0.25, [(1, 2)] * 5) is True and m.comp_azar(5, 0.3, [(1, 2)] * 5) is False
              and m.comp_azar(5, 0.25, [(1, None)] * 5) is False, "azar en grupos: esperado mal o sin intervalo, rojo")
    comprobar(m.comp_cobertura(0.9) is True and m.comp_cobertura(None) is False and m.comp_cobertura(1.3) is False,
              "cobertura: fuera de 0 a 1, rojo")
    comprobar(m.comp_periodos([{"t": "a", "parcial": True}], "t", {"a"}) is True
              and m.comp_periodos([{"t": "a", "parcial": False}], "t", {"a"}) is False, "periodos: rojo")
    comprobar(m.comp_sin_validacion(["construcción", "construcción"]) is True
              and m.comp_sin_validacion(["construcción", "validación"]) is False,
              "ninguna foto de validación cruzada con falla_30d: rojo con una de validación")
    comprobar(m.comp_partes(3, 4, 5, 12) is True and m.comp_partes(3, 4, 5, 13) is False,
              "tramos + aparte + sin tramo = fallos con foto: rojo si no suman")
    comprobar(m.comp_sin_vetada(["todos los discos"]) is True and m.comp_sin_vetada(["la " + VETADA.upper()]) is False,
              "palabra vetada: rojo si sale")

    # 2.11 Validaciones: un resultado mínimo que pasa las nueve, y un rojo para cada una
    base = resultado_minimo()
    v = m.validar(base, "x = 1\n", {"a": "1"}, {"a": "1"}, json.loads(json.dumps(base)))
    comprobar(len(v) == 9 and all(x is True for x in v.values()), "las nueve validaciones en verde con un resultado bueno")
    rojos = {
        "planteamiento_completo": lambda r: r["preguntas"][0].update({"decision": ""}),
        "cifras_con_poblacion": lambda r: r["preguntas"][0]["cifras"][0].update({"periodo": ""}),
        "segunda_via": lambda r: r["preguntas"][0]["cifras"][0].update({"coinciden": False}),
        "minimo_respetado": lambda r: r["preguntas"][0]["comprobaciones"].update({"minimo": False}),
        "con_referencia": lambda r: r["preguntas"][0]["referencia"].update({"valor": None}),
        "comprobaciones_calculadas": lambda r: r["preguntas"][0]["comprobaciones"].update({"pesos": "sí"}),
    }
    for clave, estropear in rojos.items():
        r = json.loads(json.dumps(base))
        estropear(r)
        v = m.validar(r, "x = 1\n", {"a": "1"}, {"a": "1"}, json.loads(json.dumps(r)))
        comprobar(v[clave] is False, f"validación {clave}: rojo con el caso estropeado")
    r2 = json.loads(json.dumps(base))
    r2["preguntas"][0]["cifras"][0]["valor"] = 99
    comprobar(m.validar(base, "x = 1\n", {"a": "1"}, {"a": "1"}, r2)["reproducible"] is False,
              "validación reproducible: rojo si la segunda cuenta da otra cifra")
    comprobar(m.validar(base, 'c = {"hacia_adelante": True}\n', {"a": "1"}, {"a": "1"}, base)
              ["sin_resultados_escritos"] is False, "validación sin_resultados_escritos: rojo con un True escrito")
    comprobar(m.validar(base, "x = 1\n", {"a": "1"}, {"a": "2"}, base)["raw_intacto"] is False,
              "validación raw_intacto: rojo si cambia una huella de data/raw/")
    comprobar(len(m.buscar_resultados_escritos('x["sin_validacion"] = True\n')) == 1,
              "búsqueda: encuentra una comprobación de la petición puesta a True")
    comprobar(len(m.buscar_resultados_escritos("total = 8634\n")) == 1, "búsqueda: encuentra una cifra de cuatro cifras")
    comprobar(len(m.buscar_resultados_escritos("MINIMO = 50_000\nANO = 2023\nH = 8766\n")) == 0,
              "búsqueda: el mínimo, un año y las horas del año pasan")
    comprobar(m.buscar_resultados_escritos(SCRIPT.read_text(encoding="utf-8")) == [],
              "el script no lleva ningún resultado escrito")


def phi_a_mano(filas):
    """φ de Poisson con un bucle propio y sin pandas (segunda vía de la petición 19): filas (grupo, celda, observados,
    esperados); fuera las celdas sin esperados; reescalado por grupo; chi2 / (celdas − grupos); por debajo de 1, 1."""
    celdas = {}
    for g, c, o, e in filas:
        o0, e0 = celdas.get((g, c), (0, 0.0))
        celdas[(g, c)] = (o0 + o, e0 + e)
    celdas = {k: v for k, v in celdas.items() if v[1] > 0}
    por_g = {}
    for (g, _), (o, e) in celdas.items():
        o0, e0 = por_g.get(g, (0, 0.0))
        por_g[g] = (o0 + o, e0 + e)
    chi2, n, grupos = 0.0, 0, set()
    for (g, _), (o, e) in celdas.items():
        og, eg = por_g[g]
        if og <= 0:
            continue
        ee = e * og / eg
        chi2 += (o - ee) ** 2 / ee
        n += 1
        grupos.add(g)
    gl = n - len(grupos)
    bruto = chi2 / gl if gl > 0 else None
    return {"phi": max(1.0, bruto) if bruto is not None else 1.0, "phi_bruto": bruto, "celdas": n, "gl": gl}


def phi_bin_a_mano(celdas, exitos):
    """φ binomial con un bucle propio: por celda, fotos y fallos; p de todo el grupo; chi2 = suma de (x − n·p)² /
    (n·p·(1 − p)); gl = celdas − 1; por debajo de 1, 1."""
    por = {}
    for c, x in zip(celdas, exitos):
        n0, x0 = por.get(c, (0, 0))
        por[c] = (n0 + 1, x0 + int(x))
    n_t, x_t = sum(v[0] for v in por.values()), sum(v[1] for v in por.values())
    if n_t == 0 or x_t in (0, n_t) or len(por) < 2:
        return {"phi": 1.0, "celdas": len(por), "gl": len(por) - 1}
    p = x_t / n_t
    chi2 = sum((x - n * p) ** 2 / (n * p * (1 - p)) for n, x in por.values())
    gl = len(por) - 1
    return {"phi": max(1.0, chi2 / gl), "celdas": len(por), "gl": gl}


def probar_peticion19(m):
    """Petición 19: φ de Poisson y binomial, los intervalos con φ, la mezcla con el trimestre en B5, el azar y sus
    comprobaciones, cada una con su caso en rojo."""
    import numpy as np
    import pandas as pd
    from scipy import stats

    faltan = [f for f in ("phi_poisson", "phi_binomial", "phi_edad", "intervalo_cp", "comp_phi",
                          "comp_veredicto_centros", "comp_lado_azar") if not hasattr(m, f)]
    comprobar(not faltan, f"petición 19: el script tiene φ, Clopper-Pearson y sus comprobaciones (faltan {faltan})")
    if faltan:
        return
    filas = [("A", 1, 10, 5.0), ("A", 2, 0, 5.0), ("B", 1, 5, 5.0), ("B", 2, 5, 5.0)]
    p = m.phi_poisson([f[0] for f in filas], [f[1] for f in filas], [f[2] for f in filas], [f[3] for f in filas])
    comprobar(cerca(p["phi"], 5.0) and cerca(p["phi"], phi_a_mano(filas)["phi"]) and p["gl"] == 2,
              f"petición 19: φ de Poisson a mano, 5 con 2 grados de libertad (da {p})")
    comprobar(m.comp_phi([{"phi": 0.8, "phi_bruto": 0.8}]) is False and m.comp_phi([{"phi": 1.0, "phi_bruto": 0.8}]) is True,
              "petición 19, comprobación: un φ de 0,8 usado sin subir a 1, rojo")
    # φ binomial: 100 fotos con 10 fallos y 100 con 0; p = 0,05; chi2 = 2 × 25 / 4,75; un grado de libertad
    cel = np.array([1] * 100 + [2] * 100)
    exi = np.array([1] * 10 + [0] * 90 + [0] * 100)
    pb = m.phi_binomial(cel, exi)
    comprobar(cerca(pb["phi"], 50 / 4.75) and cerca(pb["phi"], phi_bin_a_mano(cel, exi)["phi"]) and pb["gl"] == 1,
              f"petición 19: φ binomial a mano, 10,53 con 1 grado de libertad (da {pb})")
    comprobar(m.phi_binomial(np.array([1, 1, 2, 2]), np.array([1, 0, 1, 0]))["phi"] == 1.0,
              "petición 19: φ binomial sin variación de más, 1")
    # Clopper-Pearson: con φ = 1, el exacto de scipy (otra implementación); con φ = 4, el de 2,5 en 50
    lo, hi = m.intervalo_cp(10, 200)
    ci = stats.binomtest(10, 200).proportion_ci(confidence_level=0.95, method="exact")
    comprobar(cerca(lo, ci.low) and cerca(hi, ci.high), "petición 19: Clopper-Pearson igual que binomtest de scipy")
    lo4, hi4 = m.intervalo_cp(10, 200, 4.0)
    comprobar(cerca(lo4, stats.beta.ppf(0.025, 2.5, 48.5)) and cerca(hi4, stats.beta.ppf(0.975, 3.5, 47.5))
              and lo4 < lo and hi4 > hi, "petición 19: Clopper-Pearson con fallan/φ y fotos/φ, más ancho")
    # Intervalos de Poisson con φ, contra la gamma
    t, lo, hi = m.intervalo_poisson(100, 36500, phi=4.0)
    comprobar(cerca(t, 100.0) and cerca(lo, stats.gamma.ppf(0.025, 25) * 4) and cerca(hi, stats.gamma.ppf(0.975, 26) * 4),
              "petición 19: tasa con φ = 4, igual que la gamma de 25 fallos en un cuarto de los días")
    rz, lo, hi = m.razon_poisson(200, 200 / 1.2, phi=4.0)
    comprobar(cerca(rz, 1.2) and lo < 1 < hi and cerca(lo, stats.gamma.ppf(0.025, 50) / (200 / 1.2 / 4)),
              "petición 19: razón 1,2 con φ = 4 cruza 1")
    # El veredicto de un centro sale del intervalo con φ (caso en rojo: razón 1,2 que con φ = 4 cruza 1 y dice «más»)
    c = {"centro": "x", "dias_ano": 60000, "observados": 200, "esperados": 200 / 1.2}
    comprobar(m.comp_veredicto_centros([dict(c, veredicto="falla más por sí mismo")], 4.0) is False
              and m.comp_veredicto_centros([dict(c, veredicto="no se distingue")], 4.0) is True
              and m.comp_veredicto_centros([dict(c, veredicto="falla más por sí mismo")], 1.0) is True,
              "petición 19, comprobación: razón 1,2 con φ = 4 que dice «falla más por sí mismo», rojo")
    # El lado frente al azar es un resultado, no una parada: la comprobación mira que cada marca sale de su cifra
    comprobar(m.comp_lado_azar([{"observados": 8, "p95": 5.0, "por_encima_del_p95": True},
                                {"observados": 3, "p95": 5.0, "por_encima_del_p95": False}]) is True
              and m.comp_lado_azar([{"observados": 3, "p95": 5.0, "por_encima_del_p95": True}]) is False,
              "petición 19, comprobación: un tomo por debajo del p95 marcado «por encima», rojo")
    # B5 con la mezcla de modelo, edad y trimestre: A edad 1 en x e y, dos trimestres con tasas distintas.
    # 2024T1: x 1.000 días y 1 fallo, y 1.000 y 9 (tasa 10/2.000); 2024T2: x 3.000 y 3, y 1.000 y 1 (4/4.000).
    # Esperados: x 5 + 3 = 8, y 5 + 1 = 6; con solo modelo y edad (14/6.000), x 9,33 e y 4,67
    dpt = pd.DataFrame({"model": ["A"] * 4, "centro": ["x", "y", "x", "y"], "edad_anos_cumplidos": [1] * 4,
                        "mes": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-04-01", "2024-04-01"]).astype("datetime64[ms]"),
                        "dias_disco": [1000.0, 1000.0, 3000.0, 1000.0], "fallos": [1, 9, 3, 1]})
    aj, ph = m.ajustada(dpt)
    aj = aj.set_index("centro")
    pm = phi_a_mano([("x", 1, 1, 5.0), ("x", 2, 3, 3.0), ("y", 1, 9, 5.0), ("y", 2, 1, 1.0)])
    comprobar(cerca(aj.loc["x", "esperados"], 8.0) and cerca(aj.loc["y", "esperados"], 6.0)
              and cerca(ph["phi"], pm["phi"]) and ph["celdas"] == pm["celdas"],
              f"petición 19: B5 con la tasa de cada modelo, edad y trimestre, y su φ, a mano (da {ph}, prueba {pm})")
    comprobar(cerca(aj.loc["y", "razon_desde"], stats.gamma.ppf(0.025, 10 / ph["phi"]) / (6.0 / ph["phi"])),
              "petición 19: el intervalo de la razón de un centro, con φ")
    # Una celda de modelo, edad y trimestre con fallos y sin días no tiene tasa: sus fallos cuentan en los observados de
    # su centro y no pueden tener esperados; se cuentan aparte para que la suma de esperados se compare con lo demás
    d2 = pd.concat([dpt, pd.DataFrame({"model": ["A"], "centro": ["x"], "edad_anos_cumplidos": [1],
                                       "mes": pd.to_datetime(["2024-07-01"]).astype("datetime64[ms]"),
                                       "dias_disco": [float("nan")], "fallos": [2]})], ignore_index=True)
    a2, _ = m.ajustada(d2)
    a2 = a2.set_index("centro")
    comprobar("fallos_sin_tasa" in a2.columns and a2.loc["x", "fallos_sin_tasa"] == 2 and a2.loc["y", "fallos_sin_tasa"] == 0
              and a2.loc["x", "observados"] == 6 and cerca(a2["esperados"].sum(), (a2["observados"] - a2["fallos_sin_tasa"]).sum()),
              "petición 19: los fallos de una celda sin días, en sus observados y contados aparte; los esperados suman el resto")
    # φ de la edad (el de B3 del 09, calculado igual): celdas modelo × edad × trimestre
    d3 = pd.DataFrame({"model": ["A", "A", "B", "B"], "centro": ["x"] * 4, "edad_anos_cumplidos": [0, 0, 1, 1],
                       "mes": pd.to_datetime(["2021-01-01", "2021-04-01", "2021-01-01", "2021-04-01"]).astype("datetime64[ms]"),
                       "dias_disco": [1000.0, 1000.0, 2000.0, float("nan")], "fallos": [10, 0, 4, 2]})
    pe = m.phi_edad(d3)
    pm_e = phi_a_mano([(("A", 0), 1, 10, 5.0), (("A", 0), 2, 0, 5.0), (("B", 1), 1, 4, 6.0), (("B", 1), 2, 2, 0.0)])
    comprobar(cerca(pe["phi"], pm_e["phi"]) and pe["celdas"] == pm_e["celdas"], "petición 19: φ de la edad, a mano")
    # Minicubo con φ: el intervalo de cada valor con fallos y días entre φ
    dims = {"d1": np.array(["a", "a", "b", "b"])}
    n1, _ = m.minicubo(dims, np.array([40000.0, 30000.0, 20000.0, 10000.0]), {"d1": np.array(["a"] * 30)}, 50000, 20,
                       phi=4.0)
    va = next(x for x in n1 if x["valor"] == "a")
    comprobar(cerca(va["desde"], stats.gamma.ppf(0.025, 7.5) * 36500 / (70000 / 4)),
              "petición 19: minicubo, el intervalo de cada valor con φ")


def resultado_minimo():
    """Un JSON pequeño con una pregunta completa, que pasa las nueve validaciones."""
    comp = {k: None for k in ["unidad", "minimo", "empates", "referencia", "azar_en_grupos", "pesos",
                              "hacia_adelante", "cobertura", "periodos"]}
    comp.update({"unidad": True, "minimo": True})
    return {"preguntas": [{
        "id": "B5", "pregunta": "p", "decision": "d", "planteamiento": "x §1", "funcion": "otra",
        "poblacion": {"regla": "r", "periodo": "p", "filas": 3, "unidad": "centro", "entidades": 3},
        "medida": "m", "minimo_casos": "50.000", "que_cambia_la_decision": "q",
        "cifras": [{"nombre": "n", "valor": 1, "poblacion": "p", "filas": 3, "periodo": "p",
                    "segunda_via": 1, "coinciden": True}],
        "referencia": {"que_es": "total", "valor": 1, "filas": 3},
        "comprobaciones": comp, "motivos_null": {k: "no toca" for k, v in comp.items() if v is None}}]}


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 2 · el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
# Modelos: (tipo, capacidad, fabricante, temperatura de los sanos)
MODELOS = {"ST8A": ("datos", 8.0, "Seagate", 30.0), "HG12": ("datos", 12.0, "HGST", 40.0),
           "BOOT": ("arranque", 0.2, None, None)}
CENTROS = ["sac0", "sac2", "phx1", "yyz1"]
# Discos de cada día en el recuento desde 07/2023, por modelo y centro; antes, todos «sin dato»
DISCOS = {"ST8A": {"sac0": 400, "sac2": 300, "phx1": 300, "yyz1": 150, "sin dato": 20},
          "HG12": {"sac0": 200, "sac2": 300, "phx1": 100, "yyz1": 150, "sin dato": 20}}
DISCOS_ANTES = {"ST8A": 1000, "HG12": 600}
# Centros con discos sanos en las fotos (HG12 no tiene en yyz1: sus días van sin foto salvo el mes de un fallo)
SANOS = {"ST8A": CENTROS, "HG12": ["sac0", "sac2", "phx1"]}
MESES = [(2023 + (m - 1) // 12, (m - 1) % 12 + 1) for m in range(1, 31)]
MESES_SITIO = MESES[6:28]
H_ANO = 8766
INICIO_SITIO = dt.datetime(2023, 7, 1)
FIN = dt.datetime(2025, 6, 30)


def dia(a, mm, d=1):
    """Un día."""
    return dt.datetime(a, mm, d)


def plan_fallos():
    """Los fallos del caso pequeño, cada uno con lo que dice la foto de su disco el mes del fallo."""
    out = []
    for i in range(60):
        a, mm = MESES_SITIO[i % 22]
        c = "sac0" if i < 30 else "sac2" if i < 50 else "phx1"
        f = {"serial": f"F{i:02d}", "model": "ST8A", "dia": dia(a, mm, 15), "dc": c, "vault": 100 + i, "slot": 2,
             "temp": [25.0, 30.0, 35.0][i % 3], "s12": [80.0, 150.0, 300.0][i % 3], "s241": 1000.0 * (i % 7 + 1),
             "s242": 500.0 * (i % 5 + 1), "s5": 2.0 if i % 4 == 0 else 0.0, "inicio_aviso": i % 4, "foto": True,
             "ranura_dia": True}
        out.append(f)
    # El tomo A: tres fallos en cinco días; el tomo B: dos fallos a 19 días
    for i, d_ in zip((0, 1, 2), (10, 12, 14)):
        out[i].update({"dia": dia(2024, 2, d_), "dc": "sac0", "vault": 900, "slot": 5})
    for i, d_ in zip((30, 31), (5, 24)):
        out[i].update({"dia": dia(2024, 8, d_), "dc": "sac2", "vault": 901, "slot": 5})
    out[59].update({"slot": None, "ranura_dia": False})            # sin tomo
    out[18]["ranura_dia"] = False                                  # 2025T1: sin ranura el día, la trae el anterior
    for j in range(10):
        a, mm = MESES_SITIO[j * 2]
        out.append({"serial": f"G{j}", "model": "HG12", "dia": dia(a, mm, 15), "dc": "sac2", "vault": 200 + j,
                    "slot": 2, "temp": 40.0, "s12": 100.0, "s241": None, "s242": None, "s5": 0.0,
                    "inicio_aviso": j % 4, "foto": True, "ranura_dia": True})
    for j, (a, mm) in enumerate([(2024, 4), (2024, 9)]):
        out.append({"serial": f"Y{j}", "model": "HG12", "dia": dia(a, mm, 15), "dc": "yyz1", "vault": 300 + j,
                    "slot": 2, "temp": 40.0, "s12": 100.0, "s241": None, "s242": None, "s5": 0.0, "inicio_aviso": 2,
                    "foto": True, "ranura_dia": True})
    out.append({"serial": "SD0", "model": "HG12", "dia": dia(2024, 6, 15), "dc": None, "vault": None, "slot": None,
                "temp": 40.0, "s12": 100.0, "s241": None, "s242": None, "s5": 0.0, "inicio_aviso": 2, "foto": True,
                "ranura_dia": False})
    for j in range(5):
        out.append({"serial": f"P{j}", "model": "ST8A", "dia": dia(2023, 2 + j, 15), "dc": None, "vault": None,
                    "slot": None, "temp": 30.0, "s12": 100.0, "s241": 2000.0, "s242": 900.0, "s5": 0.0,
                    "inicio_aviso": 2, "foto": True, "ranura_dia": False})
    # Como en los datos reales (dos discos): P0 vuelve a fallar sin foto nueva y su 2.º fallo toma la misma foto
    out.append({"serial": "P0", "model": "ST8A", "dia": dia(2023, 2, 25), "dc": None, "vault": None, "slot": None,
                "temp": 30.0, "s12": 100.0, "s241": 2000.0, "s242": 900.0, "s5": 0.0, "inicio_aviso": 2, "foto": True,
                "ranura_dia": False})
    for j, d_ in enumerate((20, 22)):
        out.append({"serial": f"N{j}", "model": "HG12", "dia": dia(2024, 3, d_), "dc": "sac0", "vault": 400 + j,
                    "slot": 2, "temp": None, "s12": None, "s241": None, "s242": None, "s5": 0.0, "inicio_aviso": 2,
                    "foto": False, "ranura_dia": True})
    out.append({"serial": "B0", "model": "BOOT", "dia": dia(2024, 5, 5), "dc": None, "vault": None, "slot": None,
                "temp": None, "s12": None, "s241": None, "s242": None, "s5": 0.0, "inicio_aviso": 2, "foto": False,
                "ranura_dia": False})
    for f in out:
        f["tomo"] = f"{f['dc']}|{f['vault']}|{f['slot']}" if f["dc"] and f["slot"] is not None else None
        f["foto_fecha"] = dia(f["dia"].year, f["dia"].month) if f["foto"] else None
    return out


def plan_fotos(fallos):
    """Las fotos del caso pequeño: los discos sanos, los «sin dato» y la foto de cada disco que falla."""
    fotos = []
    for mo in ("ST8A", "HG12"):
        cap, fab, temp = MODELOS[mo][1], MODELOS[mo][2], MODELOS[mo][3]
        discos = [(f"H-{mo}-{c}-{k}", c, 10 + CENTROS.index(c) + (0 if mo == "ST8A" else 5), 1, k)
                  for c in SANOS[mo] for k in range(4)] + [(f"S-{mo}-{k}", None, None, None, k) for k in range(2)]
        for s, c, vault, slot, k in discos:
            hasta = (2024, 5) if s == "H-ST8A-sac2-3" else (2025, 6)
            for a, mm in MESES:
                if (a, mm) > hasta:
                    break
                sitio = dia(a, mm) >= INICIO_SITIO
                aviso = c == "sac0" and k in (0, 1) and (a, mm) >= (2024, 1)
                # Petición 17: en phx1, el 197 avisa en un disco de Seagate y el 198 en dos, desde 2024-01; en sac2, el 197
                # de un disco de HGST, que el filtro de Seagate tiene que dejar fuera
                desde24 = (a, mm) >= (2024, 1)
                v197 = 1.0 if desde24 and ((mo == "ST8A" and c == "phx1" and k == 0)
                                           or (mo == "HG12" and c == "sac2" and k == 0)) else 0.0
                v198 = 1.0 if desde24 and mo == "ST8A" and c == "phx1" and k in (0, 1) else 0.0
                fotos.append({"serial_number": s, "fecha": dia(a, mm), "model": mo, "edad_anos": 2.5,
                              "smart_197_raw": v197, "smart_198_raw": v198,
                              "smart_194_raw": temp, "smart_12_raw": 100.0,
                              "smart_241_raw": 1000.0 * (k + 1) if fab == "Seagate" else None,
                              "smart_242_raw": 500.0 * (k + 1) if fab == "Seagate" else None,
                              "smart_9_raw": 2.5 * H_ANO, "smart_90_raw": 1.0 if s == "S-ST8A-0" else None,
                              "smart_5_raw": 3.0 if aviso else 0.0,
                              "datacenter": c if sitio else None, "vault_id": vault if sitio else None,
                              "pod_slot_num": slot if sitio else None})
    hechas = set()
    for f in fallos:
        # Un disco que falla dos veces sin foto nueva tiene una sola foto
        if not f["foto"] or (f["serial"], f["foto_fecha"]) in hechas:
            continue
        hechas.add((f["serial"], f["foto_fecha"]))
        fotos.append({"serial_number": f["serial"], "fecha": f["foto_fecha"], "model": f["model"], "edad_anos": 2.5,
                      "smart_197_raw": 0.0, "smart_198_raw": 0.0,
                      "smart_194_raw": f["temp"], "smart_12_raw": f["s12"], "smart_241_raw": f["s241"],
                      "smart_242_raw": f["s242"], "smart_9_raw": 2.5 * H_ANO, "smart_90_raw": None,
                      "smart_5_raw": f["s5"], "datacenter": f["dc"], "vault_id": f["vault"], "pod_slot_num": f["slot"]})
    dias_fallo = {}
    for f in fallos:
        dias_fallo.setdefault(f["serial"], []).append(f["dia"])
    fotos.sort(key=lambda x: (x["serial_number"], x["fecha"]))
    previa = {}
    for x in fotos:
        seagate = MODELOS[x["model"]][2] == "Seagate"
        x["smart_187_raw"] = 0.0 if seagate else None
        x["smart_188_raw"] = 0.0 if seagate else None
        cnt = [x[f"smart_{n}_raw"] for n in (5, 187, 188, 197, 198)]
        x["avisa"] = any(v is not None and v > 0 for v in cnt)
        ant = previa.get(x["serial_number"])
        for n in (5, 187, 197, 198):
            v, w = x[f"smart_{n}_raw"], (ant or {}).get(f"smart_{n}_raw")
            x[f"cambio_smart_{n}"] = v - w if ant is not None and v is not None and w is not None else None
        corte = dia(2024, 6, 30) if x["fecha"] <= dia(2024, 6, 30) else FIN
        hasta = min(x["fecha"] + dt.timedelta(days=30), corte)
        x["periodo"] = "construcción" if x["fecha"] <= dia(2024, 6, 30) else "validación"
        x["falla_30d"] = int(any(x["fecha"] < d_ <= hasta for d_ in dias_fallo.get(x["serial_number"], [])))
        previa[x["serial_number"]] = x
    return fotos


def esquema(tabla, columnas):
    """Esquema con el tipo real de cada columna, leído del parquet del caso sin cargar sus datos."""
    s = pq.read_schema(PROCESADOS / f"{tabla}.parquet")
    return pa.schema([s.field(c) for c in columnas])


def escribir(raiz, tabla, filas, columnas, anulables=()):
    """Escribe una tabla del caso pequeño con los tipos del parquet real.

    Las columnas de `anulables` se escriben desde pandas como booleano anulable («boolean»), con sus metadatos, para que
    se lean con pd.NA como las del parquet real (fallos_detalle las guarda así).
    """
    datos = {c: [f[c] for f in filas] for c in columnas}
    if anulables:
        import pandas as pd
        df = pd.DataFrame(datos)
        for c in anulables:
            df[c] = df[c].astype("boolean")
        t = pa.Table.from_pandas(df, schema=esquema(tabla, columnas), preserve_index=False)
    else:
        t = pa.Table.from_pydict(datos, schema=esquema(tabla, columnas))
    pq.write_table(t, raiz / "data" / "processed" / f"{tabla}.parquet", row_group_size=500)


COL_FOTOS = ["serial_number", "fecha", "model", "edad_anos", "avisa", "smart_5_raw", "smart_187_raw", "smart_188_raw",
             "smart_197_raw", "smart_198_raw", "smart_194_raw", "smart_12_raw", "smart_241_raw", "smart_242_raw",
             "smart_9_raw", "smart_90_raw", "cambio_smart_5", "cambio_smart_187", "cambio_smart_197",
             "cambio_smart_198", "datacenter", "vault_id", "pod_slot_num", "periodo", "falla_30d"]
COL_FD = ["serial_number", "dia_fallo", "model", "capacidad_tb", "tipo_disco", "hay_dia_anterior", "sin_aviso",
          "datacenter", "vault_id", "pod_slot_num", "tomo", "plazo_reconstruccion_dias", "coincide_con_anterior",
          "ultima_foto_anterior"]


def filas_ventana(f):
    """Las 31 filas de la ventana de un fallo: los 30 días anteriores y el del fallo."""
    seagate = MODELOS[f["model"]][2] == "Seagate"
    out = []
    for k in range(30, -1, -1):
        d_ = f["dia"] - dt.timedelta(days=k)
        if f["inicio_aviso"] == 0:
            s5 = 2.0
        elif f["inicio_aviso"] == 1:
            s5 = 1.0 if k <= 10 and k > 0 else 0.0
        else:
            s5 = 0.0
        out.append({"fecha": d_, "dia_fallo": f["dia"], "serial_number": f["serial"],
                    "pod_slot_num": f["slot"] if (k > 0 or f["ranura_dia"]) else None, "smart_5_raw": s5,
                    "smart_187_raw": 0.0 if seagate else None, "smart_188_raw": 0.0 if seagate else None,
                    "smart_197_raw": 0.0, "smart_198_raw": 0.0})
    return out


def montar_caso(raiz, estropear=None):
    """Escribe el caso pequeño en `raiz`; `estropear` cambia una tabla para un caso que tiene que parar."""
    if raiz.exists():
        shutil.rmtree(raiz)
    for c in ["data/processed", "data/raw", "informes"]:
        (raiz / c).mkdir(parents=True)
    (raiz / "data" / "raw" / "origen.csv").write_text("a\n1\n", encoding="utf-8")
    fallos = plan_fallos()
    fotos = plan_fotos(fallos)

    # Calendario y dim_modelo
    dias, d_ = [], dia(2020, 1, 1)
    while d_ <= FIN:
        dias.append({"fecha": d_, "ano": d_.year, "trimestre": (d_.month - 1) // 3 + 1})
        d_ += dt.timedelta(days=1)
    escribir(raiz, "calendario", dias, ["fecha", "ano", "trimestre"])
    escribir(raiz, "dim_modelo", [{"model": k, "capacidad_tb": v[1], "tipo_disco": v[0], "fabricante": v[2]}
                                  for k, v in MODELOS.items()], ["model", "capacidad_tb", "tipo_disco", "fabricante"])

    # Recuento: un día por modelo y centro, con los fallos de ese día
    por_dia = {}
    for f in fallos:
        por_dia[(f["dia"], f["model"], f["dc"] or "sin dato")] = por_dia.get((f["dia"], f["model"], f["dc"] or "sin dato"), 0) + 1
    rec, d_ = [], dia(2023, 1, 1)
    while d_ <= FIN:
        celdas = ([(mo, c, n) for mo in DISCOS for c, n in DISCOS[mo].items()] if d_ >= INICIO_SITIO
                  else [(mo, "sin dato", n) for mo, n in DISCOS_ANTES.items()]) + [("BOOT", "sin dato", 50)]
        for mo, c, n in celdas:
            rec.append({"fecha": d_, "model": mo, "datacenter": c, "discos": n, "fallos": por_dia.get((d_, mo, c), 0)})
        d_ += dt.timedelta(days=1)
    escribir(raiz, "recuento_diario_corregido", rec, ["fecha", "model", "datacenter", "discos", "fallos"])

    # centro_mes: el recuento de discos de datos por centro y mes
    cm = {}
    for x in rec:
        if x["model"] == "BOOT":
            continue
        k = (x["datacenter"], dia(x["fecha"].year, x["fecha"].month))
        a = cm.setdefault(k, [0, 0])
        a[0] += x["discos"]
        a[1] += x["fallos"]
    if estropear == "centro_mes":
        cm[("sac0", dia(2024, 1))][1] += 1
    escribir(raiz, "centro_mes", [{"datacenter": k[0], "mes": k[1], "dias_disco": v[0], "fallos": v[1]}
                                  for k, v in sorted(cm.items())], ["datacenter", "mes", "dias_disco", "fallos"])

    # dias_por_tramo: los días de cada celda con foto (todas con edad 2) y los fallos por su centro y mes
    fotos_celda, dias_celda = {}, {}
    for x in fotos:
        k = (x["model"], x["datacenter"] or "sin dato", x["fecha"])
        fotos_celda[k] = fotos_celda.get(k, 0) + 1
    for x in rec:
        if x["model"] != "BOOT":
            k = (x["model"], x["datacenter"], dia(x["fecha"].year, x["fecha"].month))
            dias_celda[k] = dias_celda.get(k, 0) + x["discos"]
    fallos_celda = {}
    for f in fallos:
        if f["model"] != "BOOT":
            k = (f["model"], f["dc"] or "sin dato", dia(f["dia"].year, f["dia"].month))
            fallos_celda[k] = fallos_celda.get(k, 0) + 1
    dpt = []
    for k in sorted(set(fotos_celda) | set(fallos_celda)):
        n = fotos_celda.get(k, 0)
        dpt.append({"model": k[0], "centro": k[1], "mes": k[2], "edad_anos_cumplidos": 2, "fotos": n,
                    "dias_disco": float(dias_celda[k]) if n > 0 else None, "fallos": fallos_celda.get(k, 0)})
    escribir(raiz, "dias_por_tramo", dpt, ["model", "centro", "mes", "edad_anos_cumplidos", "fotos", "dias_disco",
                                           "fallos"])

    # fotos_riesgo, ventanas, fallos_detalle y vida_discos
    escribir(raiz, "fotos_riesgo", fotos, COL_FOTOS)
    ven = [x for f in fallos for x in filas_ventana(f)]
    escribir(raiz, "ventanas_fallo_corregido", ven, ["fecha", "dia_fallo", "serial_number", "pod_slot_num",
                                                     "smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw",
                                                     "smart_198_raw"])
    fd = []
    ultimo = {}
    for f in sorted(fallos, key=lambda x: (x["tomo"] or "~", x["dia"], x["serial"])):
        ant = next(x for x in filas_ventana(f) if x["fecha"] == f["dia"] - dt.timedelta(days=1))
        avisa = ant["smart_5_raw"] > 0
        cap = MODELOS[f["model"]][1]
        prev = ultimo.get(f["tomo"]) if f["tomo"] else None
        # Como en los datos reales: vacío (NA) si el fallo no tiene un anterior en su tomo o no tiene tomo
        coincide = None if prev is None else (f["dia"] - prev[0]).days < prev[1]
        if f["tomo"]:
            ultimo[f["tomo"]] = (f["dia"], cap + 1)
        fd.append({"serial_number": f["serial"], "dia_fallo": f["dia"], "model": f["model"], "capacidad_tb": cap,
                   "tipo_disco": MODELOS[f["model"]][0], "hay_dia_anterior": True, "sin_aviso": not avisa,
                   "datacenter": f["dc"], "vault_id": f["vault"], "pod_slot_num": f["slot"], "tomo": f["tomo"],
                   "plazo_reconstruccion_dias": cap + 1, "coincide_con_anterior": coincide,
                   "ultima_foto_anterior": f["foto_fecha"]})
    if estropear == "coincide":
        x = next(x for x in fd if x["serial_number"] == "F31")
        x["coincide_con_anterior"] = True
    if estropear == "foto":
        x = next(x for x in fd if x["serial_number"] == "F10")
        x["ultima_foto_anterior"] = dia(2022, 1)
    escribir(raiz, "fallos_detalle", fd, COL_FD, anulables=("coincide_con_anterior", "sin_aviso"))
    vida = {}
    for x in fotos:
        vida[x["serial_number"]] = x["fecha"]
    vd = []
    for s, u in sorted(vida.items()):
        ev = "fallo" if s[0] in "FGYSPN" and not s.startswith("S-") else ("desaparece" if u < dia(2025, 6) else "sigue")
        vd.append({"serial_number": s, "ultima_foto": u, "evento": ev})
    for f in fallos:
        if not f["foto"] and f["model"] != "BOOT":
            vd.append({"serial_number": f["serial"], "ultima_foto": None, "evento": "fallo"})
    escribir(raiz, "vida_discos", vd, ["serial_number", "ultima_foto", "evento"])

    # transformacion-datos.json con las huellas, y los JSON de las peticiones 13 y 14
    p = raiz / "data" / "processed"
    salidas = [{"ruta": f"data/processed/{t}.parquet", "sha256": sha256(p / f"{t}.parquet")}
               for t in ["dim_modelo", "fotos_riesgo", "fallos_detalle", "vida_discos", "dias_por_tramo", "centro_mes"]]
    entradas = [{"ruta": f"data/processed/{t}.parquet", "sha256": sha256(p / f"{t}.parquet")}
                for t in ["ventanas_fallo_corregido", "recuento_diario_corregido", "calendario"]]
    if estropear == "huella":
        salidas[1]["sha256"] = "0" * 64
    (raiz / "informes" / "transformacion-datos.json").write_text(
        json.dumps({"salidas": salidas, "entradas": entradas}), encoding="utf-8")
    for n in ["indicadores__discos_modelos_edad", "indicadores__coste_prevision"]:
        estado = "PARADO" if (estropear == "peticion14" and n == "indicadores__coste_prevision") else "AVISO"
        (raiz / "informes" / f"{n}.json").write_text(json.dumps({"resultado": {"estado": estado}}), encoding="utf-8")
    return fallos, fotos, rec


def ejecutar(raiz):
    """Ejecuta el script con -W error sobre `raiz`; devuelve el código de salida y el JSON, si lo escribió."""
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(raiz)],
                       capture_output=True, text=True, encoding="utf-8")
    ruta = raiz / SALIDA
    j = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    if r.returncode not in (0, 2):
        print(r.stdout[-3000:], r.stderr[-3000:])
    return r.returncode, j


def pregunta(j, ident):
    """La pregunta `ident` del JSON."""
    return next(p for p in j["preguntas"] if p["id"] == ident)


def esperado(fallos, fotos, rec):
    """Las cifras del caso pequeño, con bucles de Python y sin pandas (otra cuenta que la del script)."""
    e = {}
    datos = [f for f in fallos if f["model"] != "BOOT"]
    desde = [f for f in datos if f["dia"] >= INICIO_SITIO]
    # B5: días y fallos por centro desde 07/2023, del recuento
    dc = {}
    for x in rec:
        if x["model"] != "BOOT" and x["fecha"] >= INICIO_SITIO:
            a = dc.setdefault(x["datacenter"], [0, 0])
            a[0] += x["discos"]
            a[1] += x["fallos"]
    e["centros"] = dc
    # B6: desenlace de las fotos con 90 días por delante
    fd_por_disco = {}
    for f in datos:
        fd_por_disco.setdefault(f["serial"], []).append(f["dia"])
    ultima = {}
    for x in fotos:
        ultima[x["serial_number"]] = max(ultima.get(x["serial_number"], x["fecha"]), x["fecha"])
    fallados = {f["serial"] for f in datos}
    grupos = {"con algún aviso": [0, 0, 0], "sin aviso": [0, 0, 0]}
    for x in fotos:
        h = x["fecha"] + dt.timedelta(days=90)
        if h > FIN:
            continue
        if any(x["fecha"] < d_ <= h for d_ in fd_por_disco.get(x["serial_number"], [])):
            k = 1
        elif x["serial_number"] not in fallados and ultima[x["serial_number"]] < dia(2025, 6) and ultima[x["serial_number"]] < h:
            k = 2
        else:
            k = 0
        grupos["con algún aviso" if x["avisa"] else "sin aviso"][k] += 1
    e["desenlace"] = grupos
    # B6: la ventana antes del fallo
    con, alguno, primero, dentro, dias_ = 0, 0, 0, 0, []
    for f in datos:
        filas = [x for x in filas_ventana(f) if x["fecha"] < f["dia"]]
        con += 1
        avis = [x for x in filas if x["smart_5_raw"] > 0]
        if avis:
            alguno += 1
            if filas[0]["smart_5_raw"] > 0:
                primero += 1
            else:
                dentro += 1
                dias_.append((f["dia"] - avis[0]["fecha"]).days)
    e["ventana"] = (con, alguno, primero, dentro, statistics.median(dias_))
    e["sin_aviso"] = sum(1 for f in datos if not filas_ventana(f)[-2]["smart_5_raw"] > 0)
    # B7: tomos
    ct = [f for f in desde if f["tomo"]]
    e["b7"] = (len(desde), sum(1 for f in desde if not f["dc"]), len(desde) - len(ct), len(ct), len({f["tomo"] for f in ct}))
    # B8: temperatura de ST8A (mediana 30): frío 20, medio 25, caliente 20
    pesos = {}
    fotos_celda = {}
    for x in fotos:
        k = (x["model"], x["datacenter"] or "sin dato", x["fecha"])
        fotos_celda[k] = fotos_celda.get(k, 0) + 1
    dias_celda = {}
    for x in rec:
        if x["model"] != "BOOT":
            k = (x["model"], x["datacenter"], dia(x["fecha"].year, x["fecha"].month))
            dias_celda[k] = dias_celda.get(k, 0) + x["discos"]
    for x in fotos:
        k = (x["model"], x["datacenter"] or "sin dato", x["fecha"])
        pesos[(x["serial_number"], x["fecha"])] = dias_celda.get(k, 0) / fotos_celda[k]
    e["dias_repartidos"] = sum(pesos.values())
    e["dias_recuento"] = sum(dias_celda.values())
    med = statistics.median([x["smart_194_raw"] for x in fotos if x["model"] == "ST8A"])
    dias_t, fallos_t = [0.0, 0.0, 0.0], [0, 0, 0]
    for x in fotos:
        if x["model"] == "ST8A" and x["smart_194_raw"] is not None:
            dif = x["smart_194_raw"] - med
            dias_t[0 if dif < -3 else 1 if dif < 3 else 2] += pesos[(x["serial_number"], x["fecha"])]
    for f in datos:
        if f["model"] == "ST8A" and f["foto"]:
            dif = f["temp"] - med
            fallos_t[0 if dif < -3 else 1 if dif < 3 else 2] += 1
    tasa = sum(fallos_t) / sum(dias_t)
    e["temp_razones"] = [fallos_t[i] / (dias_t[i] * tasa) for i in range(3)]
    e["temp_fallos"] = fallos_t
    e["con_foto"] = sum(1 for f in datos if f["foto"])
    # Minicubo: tasa por fabricante del reparto
    fab = {}
    for x in fotos:
        a = fab.setdefault(MODELOS[x["model"]][2], [0.0, 0])
        a[0] += pesos[(x["serial_number"], x["fecha"])]
    for f in datos:
        if f["foto"]:
            fab[MODELOS[f["model"]][2]][1] += 1
    e["fabricante"] = {k: 36500 * v[1] / v[0] for k, v in fab.items()}
    return e


def esperado_seagate(fallos, fotos):
    """Petición 17: el desenlace a 90 días solo con las fotos de Seagate, con bucles y sin pandas, y las fotos con el 197,
    con el 198 y con los dos."""
    datos = [f for f in fallos if f["model"] != "BOOT"]
    fd_por_disco = {}
    for f in datos:
        fd_por_disco.setdefault(f["serial"], []).append(f["dia"])
    ultima = {}
    for x in fotos:
        ultima[x["serial_number"]] = max(ultima.get(x["serial_number"], x["fecha"]), x["fecha"])
    fallados = {f["serial"] for f in datos}
    grupos = {"sin aviso": [0, 0, 0], "contador 197": [0, 0, 0], "contador 198": [0, 0, 0]}
    n, n197, n198, dos = 0, 0, 0, 0
    for x in fotos:
        h = x["fecha"] + dt.timedelta(days=90)
        if h > FIN or MODELOS[x["model"]][2] != "Seagate":
            continue
        n += 1
        if any(x["fecha"] < d_ <= h for d_ in fd_por_disco.get(x["serial_number"], [])):
            k = 1
        elif x["serial_number"] not in fallados and ultima[x["serial_number"]] < dia(2025, 6) and ultima[x["serial_number"]] < h:
            k = 2
        else:
            k = 0
        a197, a198 = x["smart_197_raw"] > 0, x["smart_198_raw"] > 0
        if not x["avisa"]:
            grupos["sin aviso"][k] += 1
        if a197:
            grupos["contador 197"][k] += 1
        if a198:
            grupos["contador 198"][k] += 1
        n197, n198, dos = n197 + a197, n198 + a198, dos + (a197 and a198)
    return {"grupos": grupos, "fotos": n, "197_198": (n197, n198, dos)}


def trimestre_num(fecha):
    """Año × 10 + trimestre: 2024-05 da 20242."""
    return fecha.year * 10 + (fecha.month - 1) // 3 + 1


def esperado_peticion19(fallos, fotos):
    """Petición 19, con bucles propios y sin pandas: φ binomial del desenlace por trimestre de la foto, «sin aviso» por
    año, esperados y φ de B5 con la mezcla de modelo, edad y trimestre, y φ de la edad del minicubo."""
    e = {}
    datos = [f for f in fallos if f["model"] != "BOOT"]
    fd_por_disco = {}
    for f in datos:
        fd_por_disco.setdefault(f["serial"], []).append(f["dia"])
    # B6: por grupo, la celda (trimestre de la foto) y si falla en 90 días, de las fotos con 90 días por delante
    cel = {"con algún aviso": ([], []), "sin aviso": ([], [])}
    for x in fotos:
        h = x["fecha"] + dt.timedelta(days=90)
        if h > FIN:
            continue
        falla = any(x["fecha"] < d_ <= h for d_ in fd_por_disco.get(x["serial_number"], []))
        g = cel["con algún aviso" if x["avisa"] else "sin aviso"]
        g[0].append(trimestre_num(x["fecha"]))
        g[1].append(falla)
    e["phi_desenlace"] = {g: phi_bin_a_mano(c, x) for g, (c, x) in cel.items()}
    # B6: «sin aviso» por año del fallo (en el caso pequeño todos tienen día anterior)
    por_ano = {}
    for f in datos:
        a = por_ano.setdefault(f["dia"].year, [0, 0])
        a[0] += 1
        a[1] += int(not filas_ventana(f)[-2]["smart_5_raw"] > 0)
    e["sin_aviso_por_ano"] = por_ano
    dpt = pq.read_table(TMP / "data" / "processed" / "dias_por_tramo.parquet").to_pylist()
    # B5: tasa de cada modelo, edad y trimestre desde 07/2023, con «sin dato»; φ en centro × trimestre sin «sin dato»
    sitio = [x for x in dpt if x["mes"] >= INICIO_SITIO]
    tasa = {}
    for x in sitio:
        a = tasa.setdefault((x["model"], x["edad_anos_cumplidos"], trimestre_num(x["mes"])), [0.0, 0])
        a[0] += x["dias_disco"] or 0.0
        a[1] += x["fallos"]
    esperados, filas = {}, []
    for x in sitio:
        dd, fc = tasa[(x["model"], x["edad_anos_cumplidos"], trimestre_num(x["mes"]))]
        d_ = x["dias_disco"] or 0.0
        esp = d_ * fc / dd if d_ > 0 and dd > 0 else 0.0
        esperados[x["centro"]] = esperados.get(x["centro"], 0.0) + esp
        if x["centro"] != "sin dato":
            filas.append((x["centro"], trimestre_num(x["mes"]), x["fallos"], esp))
    e["esperados_b5"] = esperados
    e["phi_b5"] = phi_a_mano(filas)
    # Minicubo: φ de la edad, celdas modelo × edad × trimestre de todo el periodo
    te = {}
    for x in dpt:
        a = te.setdefault((x["model"], x["edad_anos_cumplidos"]), [0.0, 0])
        a[0] += x["dias_disco"] or 0.0
        a[1] += x["fallos"]
    filas = []
    for x in dpt:
        dd, fc = te[(x["model"], x["edad_anos_cumplidos"])]
        filas.append(((x["model"], x["edad_anos_cumplidos"]), trimestre_num(x["mes"]), x["fallos"],
                      (x["dias_disco"] or 0.0) * fc / dd if dd > 0 else 0.0))
    e["phi_mc"] = phi_a_mano(filas)
    return e


def probar_caso_pequeno_peticion19(j, fallos, fotos):
    """Petición 19 sobre el caso pequeño: cada φ y cada intervalo contra la cuenta propia de la prueba."""
    from scipy import stats
    e = esperado_peticion19(fallos, fotos)
    b5, b6, b7, mc = (pregunta(j, x)["tablas"] for x in ("B5", "B6", "B7", "MC"))
    ex = {x: pregunta(j, x)["comprobaciones_extra"] for x in ("B5", "B6", "B7", "MC")}
    # B5
    ph = b5.get("phi") or {}
    pm = e["phi_b5"]
    comprobar(cerca(ph.get("phi"), pm["phi"], 1e-8) and ph.get("celdas") == pm["celdas"] and ph.get("gl") == pm["gl"],
              f"petición 19, B5: φ en centro × trimestre, a mano (da {ph}, prueba {pm})")
    cen = {x["centro"]: x for x in b5["centros"]}
    comprobar(all(cerca(cen[c]["esperados"], v, 1e-8) for c, v in e["esperados_b5"].items()),
              "petición 19, B5: esperados de cada centro con la tasa de cada modelo, edad y trimestre (bucle propio)")
    f = ph.get("phi", 0.0)
    comprobar(f >= 1 and all(cerca(x["razon_desde"], stats.gamma.ppf(0.025, x["observados"] / f) / (x["esperados"] / f), 1e-8)
                             for x in b5["centros"] if x["observados"] > 0 and x["esperados"] > 0),
              "petición 19, B5: el intervalo de la razón de cada centro, con φ")
    comprobar(ex["B5"].get("phi_minimo_uno") is True and ex["B5"].get("veredicto_del_intervalo") is True,
              "petición 19, B5: comprobaciones de φ y del veredicto, en verde")
    # B6
    des = {x["grupo"]: x for x in b6["desenlace"]["grupos"]}
    for g, pb in e["phi_desenlace"].items():
        x = des[g]
        ph = x.get("phi") or {}
        f = ph.get("phi", 0.0)
        lo = stats.beta.ppf(0.025, x["falla"] / f, (x["fotos"] - x["falla"]) / f + 1) if x["falla"] and f else 0.0
        comprobar(cerca(f, pb["phi"], 1e-8) and ph.get("celdas") == pb["celdas"] and ph.get("gl") == pb["gl"]
                  and cerca(x["falla_desde"], 100 * lo, 1e-8),
                  f"petición 19, B6: φ binomial de «{g}» por trimestre de la foto y su Clopper-Pearson (da {ph}, prueba {pb})")
    comprobar(all("phi" in x for x in b6["desenlace"]["grupos"] + b6["desenlace_seagate"]["grupos"]),
              "petición 19, B6: cada grupo, también los de Seagate, con su φ")
    sa = b6.get("sin_aviso_por_ano") or []
    comprobar({x["ano"]: [x["fallos"], x["sin_aviso"]] for x in sa} == e["sin_aviso_por_ano"]
              and all(x["sin_dia_anterior"] == 0 and x["con_dia_anterior"] == x["fallos"]
                      and cerca(x["pct_sin_aviso"], 100 * x["sin_aviso"] / x["con_dia_anterior"], 1e-8) for x in sa),
              "petición 19, B6: «sin aviso» por año, recuento propio")
    comprobar(ex["B6"].get("phi_minimo_uno") is True, "petición 19, B6: φ nunca menor que 1, en verde")
    # B7
    az = b7["azar"]
    sc = az.get("solo_centro") or {}
    comprobar(az.get("estrato") == "centro y trimestre" and sc.get("estrato") == "centro"
              and sc.get("iteraciones") == az["iteraciones"] and len(sc.get("resultados", [])) == len(az["resultados"]),
              "petición 19, B7: el azar dentro de centro y trimestre, y el de solo centro al lado")
    comprobar(all(x["por_encima_del_p95"] == (x["observados"] > x["p95"]) for x in az["resultados"] + sc.get("resultados", []))
              and ex["B7"].get("lado_del_azar") is True and "por_encima_del_p95" not in ex["B7"],
              "petición 19, B7: el lado frente al azar es un resultado calculado, no una parada")
    # MC
    ph = mc.get("phi") or {}
    f = ph.get("phi", 0.0)
    comprobar(cerca(f, e["phi_mc"]["phi"], 1e-8) and ph.get("celdas") == e["phi_mc"]["celdas"],
              f"petición 19, MC: φ de la edad, a mano (da {ph}, prueba {e['phi_mc']})")
    comprobar(f >= 1 and all(cerca(x["desde"], stats.gamma.ppf(0.025, x["fallos"] / f) * 36500 / (x["dias"] / f), 1e-8)
                             for x in mc["nivel_1"] if x["fallos"] > 0 and x["dias"] > 0)
              and ex["MC"].get("phi_minimo_uno") is True, "petición 19, MC: el intervalo de cada valor, con φ")


def probar_caso_pequeno():
    """El script entero sobre el caso pequeño, y los casos que tienen que parar."""
    fallos, fotos, rec = montar_caso(TMP)
    codigo, j = ejecutar(TMP)
    comprobar(codigo == 0 and j is not None and j["resultado"]["estado"] in ("OK", "AVISO"),
              f"caso pequeño: termina sin parar (código {codigo}, estado {j and j['resultado']['estado']})")
    if j is None or j["resultado"]["estado"] not in ("OK", "AVISO"):
        if j is not None:
            print(json.dumps(j["resultado"], ensure_ascii=False)[:3000])
        return
    e = esperado(fallos, fotos, rec)
    textos = [(TMP / n).read_text(encoding="utf-8").lower() for n in (SALIDA, SALIDA_MD) if (TMP / n).exists()]
    comprobar(len(textos) == 2 and not any(VETADA in t for t in textos),
              "caso pequeño: deja el JSON y el MD, sin la palabra vetada")
    comprobar(all(v is True for v in j["validaciones"].values()), "caso pequeño: las nueve validaciones en verde")
    comprobar(all(s["coinciden"] is True for s in j["segundas_vias"]), "caso pequeño: todas las segundas vías coinciden")
    comprobar([q["id"] for q in j["preguntas"]] == ["B5", "B6", "B7", "B8", "MC"], "caso pequeño: cinco preguntas")
    comprobar(all(isinstance(j["ejecucion"].get(k), str) for k in ("pandas", "numpy", "scipy")),
              "caso pequeño: versiones de pandas, numpy y scipy en el JSON")
    b5, b6, b7, b8, mc = (pregunta(j, x)["tablas"] for x in ("B5", "B6", "B7", "B8", "MC"))

    # B5
    cen = {x["centro"]: x for x in b5["centros"]}
    comprobar(all(cen[c]["dias_disco"] == e["centros"][c][0] and cen[c]["fallos"] == e["centros"][c][1]
                  for c in e["centros"]), "B5: días y fallos por centro, los del recuento")
    comprobar(cen["yyz1"]["veredicto"] == "sin conclusión" and cen["sin dato"]["veredicto"] == "aparte",
              "B5: yyz1 sin conclusión (2 fallos); «sin dato», aparte")
    comprobar(cerca(sum(x["esperados"] for x in b5["centros"]), sum(x["observados"] for x in b5["centros"]), 1e-9),
              "B5: los esperados suman los observados")
    comprobar(len(b5["trimestres"]) == 32 and len({x["trimestre"] for x in b5["trimestres"]}) == 8,
              "B5: 4 centros por 8 trimestres")
    comprobar(len(b5["quitar_modelo"]) == 2, "B5: la prueba de quitar cada modelo, en sac0 y sac2")
    comprobar(cerca(next(x for x in b5["temperatura"]["por_centro"] if x["centro"] == "yyz1")["media"],
                    (4 * 24 * 30.0 + 2 * 40.0) / (4 * 24 + 2)), "B5: temperatura media de yyz1")

    # B6
    des = {x["grupo"]: x for x in b6["desenlace"]["grupos"]}
    comprobar(all([des[g]["sigue"], des[g]["falla"], des[g]["desaparece"]] == e["desenlace"][g]
                  for g in ("con algún aviso", "sin aviso")), "B6: desenlace a 90 días contado a mano")
    fv = b6["fallos"]
    comprobar((fv["con_filas_antes"], fv["avisan_algun_dia"], fv["ya_primer_dia"], fv["empiezan_dentro"],
               fv["dias_mediana"]) == e["ventana"], "B6: la ventana antes del fallo, contada a mano")
    comprobar(fv["sin_aviso"] == e["sin_aviso"] and fv["sin_dia_anterior"] == 0, "B6: fallos sin aviso")
    comprobar(len(b6["serie_dias_antes"]) == 30, "B6: la serie de los 30 días antes del fallo")
    # Petición 17: el desenlace por contador, solo con las fotos de Seagate, frente al recuento propio de la prueba
    ds = b6.get("desenlace_seagate")
    comprobar(ds is not None, "petición 17, B6: el desenlace a 90 días repetido con las fotos de Seagate")
    if ds is not None:
        gs = {x["grupo"]: x for x in ds["grupos"]}
        es = esperado_seagate(fallos, fotos)
        comprobar(all(g in gs and [gs[g]["sigue"], gs[g]["falla"], gs[g]["desaparece"]] == es["grupos"][g]
                      for g in ("sin aviso", "contador 197", "contador 198")),
                  "petición 17, B6 Seagate: sin aviso, 197 y 198, contados a mano (el HGST con el 197 queda fuera)")
        comprobar(ds["fotos"] == es["fotos"], "petición 17, B6 Seagate: fotos de Seagate con 90 días por delante")
        c = ds["contadores_197_198"]
        comprobar((c["fotos_197"], c["fotos_198"], c["las_dos"]) == es["197_198"] and c["mismas_fotos"] is False,
                  "petición 17, B6 Seagate: el 197 y el 198 no marcan las mismas fotos en el caso pequeño, con su recuento")

    # B7
    t7 = b7["fallos"]
    comprobar((t7["desde_07_2023"], t7["sin_centro"], t7["sin_tomo"], t7["con_tomo"], t7["tomos"]) == e["b7"],
              "B7: fallos, sin centro, sin tomo, con tomo y tomos")
    comprobar(t7["coinciden"] == 2, "B7: dos coincidencias, las del tomo A")
    kd = {(x["k"], x["d"]): x["tomos"] for x in b7["k_en_d"]}
    comprobar(kd[(2, 7)] == 1 and kd[(3, 7)] == 1 and kd[(2, 30)] == 2 and kd[(4, 30)] == 0,
              "B7: tomos con k fallos en d días")
    lv = b7["a_la_vez"]
    comprobar(lv["reparto"] == {"1": e["b7"][3] - 2, "2": 1, "3": 1} and lv["llegan_a_paridad"] == 1,
              "B7: discos a la vez y una vez la paridad (tres en 8 TB)")
    comprobar(b7["peores_tomos"][0]["tomo"] == "sac0|900|5"
              and [x["coincide"] for x in b7["peores_tomos"][0]["linea_de_tiempo"]] == [False, True, True],
              "B7: el peor tomo y su línea de tiempo; el primero, con coincide vacío (NA), no coincide")
    comprobar(len(b7["riesgo_vivo"]["meses"]) == 24 and b7["azar"]["iteraciones"] == 200,
              "B7: 24 meses de riesgo vivo y 200 repeticiones del azar")
    probar_caso_pequeno_peticion19(j, fallos, fotos)

    # B8
    rp = b8["reparto"]
    comprobar(cerca(rp["dias_repartidos"], e["dias_repartidos"], 1e-9) and rp["fallos_con_foto"] == e["con_foto"]
              and rp["fallos_sin_foto_anterior"] == 2, "B8: días repartidos y fallos con su foto")
    tp = b8["factores"]["temperatura"]
    comprobar(tp["grupos_entran"] == 1 and [x["fallos"] for x in tp["tramos"]] == e["temp_fallos"]
              and all(cerca(x["razon"], y, 1e-9) for x, y in zip(tp["tramos"], e["temp_razones"])),
              "B8: temperatura, ST8A entra y sus razones a mano")
    comprobar(all(f["fallos_entran"] + f["aparte"]["fallos"] + f["sin_tramo"]["fallos"] == e["con_foto"]
                  for f in b8["factores"].values()), "B8: tramos + aparte + sin tramo = fallos con foto, en los cuatro")

    # Minicubo y lo que falta
    n1 = {(x["dimension"], x["valor"]): x for x in mc["nivel_1"]}
    comprobar(all(cerca(n1[("fabricante", k)]["tasa"], v, 1e-9) for k, v in e["fabricante"].items()),
              "MC: tasa por fabricante del reparto")
    comprobar(sum(x["fallos"] for x in mc["nivel_1"] if x["dimension"] == "centro") == e["con_foto"]
              and n1[("centro", "antes_de_07_2023")]["fallos"] == 6,
              "MC: fallos por centro, con «antes» (6: P0 falla dos veces con la misma foto)")
    comprobar(rp["fallos_que_comparten_foto"] == 2 and rp["discos_con_fallos_que_comparten_foto"] == 1,
              "B8: dos fallos de un mismo disco toman la misma foto, contados y dichos")
    comprobar(len(mc["nivel_2"]) == 10, "MC: diez pares de dimensiones")
    lf = mc["lo_que_falta"]
    comprobar(lf["sin_ranura_dia_fallo"]["2025T1"]["sin_ranura"] == 1
              and lf["sin_ranura_dia_fallo"]["2024T4"]["sin_ranura"] == 1 and lf["smart_90_no_vacio"] == 30,
              "lo que falta: sin ranura el día del fallo y smart_90")

    # Casos que tienen que parar
    for estropear, estado, motivo in [
            ("centro_mes", "ERROR", "por centro"),
            ("coincide", "ERROR", "coincidencias"),
            ("foto", "ERROR", "con su foto"),
            ("huella", "ERROR", "huella"),
            ("peticion14", "PARADO", "indicadores__coste_prevision")]:
        montar_caso(TMP, estropear)
        codigo, j = ejecutar(TMP)
        comprobar(codigo != 0 and j is not None and j["resultado"]["estado"] == estado
                  and motivo in j["resultado"]["resumen"] and "preguntas" not in j,
                  f"caso pequeño estropeado en {estropear}: para con {estado} por «{motivo}», sin cifras en el JSON")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 3 · el JSON real, contra los controles de la petición y por otro camino
# ---------------------------------------------------------------------------------------------------------------
def probar_json_real_peticion19(b5, b6, b7, mc, rd, m=None):
    """Los CONTROLES de la petición 19 sobre el JSON real.

    B5: el control se midió con los centros que constan, sin «sin dato» en la mezcla; el script la calcula con «sin
    dato» dentro (criterio técnico 1 de la petición 15). Las cifras del control se comprueban exactas con la función del
    script sobre esas mismas celdas, y el JSON, con los mismos lados y a menos de una centésima, como permite la petición
    («pueden moverse en el tercer decimal; los lados tienen que salir iguales»).
    """
    controles = [("sac2", 1.099, 1.057, 1.143, "falla más por sí mismo"), ("sac0", 0.900, 0.867, 0.934, "falla menos"),
                 ("phx1", 1.034, 0.990, 1.078, "no se distingue"), ("ams5", 1.061, None, None, "no se distingue"),
                 ("iad1", 0.990, None, None, "no se distingue"), ("yyz1", None, None, None, "sin conclusión")]
    if m is not None:
        import pandas as pd
        d = pq.read_table(PROCESADOS / "dias_por_tramo.parquet").to_pandas()
        d["mes"] = d["mes"].astype("datetime64[ms]")
        d = d.loc[(d["mes"] >= INICIO_SITIO) & (d["centro"] != "sin dato")]
        aj, ph = m.ajustada(d)
        aj = aj.set_index("centro")
        comprobar(rd(ph["phi"], 2) == 1.01 and ph["celdas"] == 42 and ph["gl"] == 36,
                  f"control 19, B5 con las celdas del control: φ 1,01 con 42 celdas y 36 gl (da {ph['phi']:.4f})")
        for c, rz, lo, hi, v in controles:
            x = aj.loc[c]
            ok = rz is None or rd(x["razon"], 3) == rz
            ok = ok and (lo is None or (rd(x["razon_desde"], 3) == lo and rd(x["razon_hasta"], 3) == hi))
            comprobar(ok, f"control 19, B5 con las celdas del control: {c}, {rz} ({lo} a {hi}) (da {x['razon']:.4f} "
                          f"({x['razon_desde']:.4f} a {x['razon_hasta']:.4f}))")
    ph = b5["phi"]
    comprobar(abs(ph["phi"] - 1.01) < 0.01 and ph["celdas"] == 42 and ph["gl"] == 36,
              f"control 19, B5 del JSON: φ 1,01 a menos de una centésima, 42 celdas y 36 gl (da {ph['phi']:.4f})")
    cen = {x["centro"]: x for x in b5["centros"]}
    for c, rz, lo, hi, v in controles:
        x = cen[c]
        ok = x["veredicto"] == v and (rz is None or abs(x["razon"] - rz) < 0.01)
        ok = ok and (lo is None or (abs(x["razon_desde"] - lo) < 0.01 and abs(x["razon_hasta"] - hi) < 0.01))
        comprobar(ok, f"control 19, B5 del JSON: {c}, {rz} ({lo} a {hi}), {v}, el lado igual y a menos de una "
                      f"centésima (da {x['razon']:.4f} ({x['razon_desde']:.4f} a {x['razon_hasta']:.4f}), {x['veredicto']})")
    g = {x["grupo"]: x for x in b6["desenlace"]["grupos"]}
    for grupo, f in [("contador 5", 54.1), ("contador 187", 41.6), ("contador 188", 13.4), ("contador 197", 68.2),
                     ("contador 198", 62.0), ("sin aviso", 23.3)]:
        comprobar(rd(g[grupo]["phi"]["phi"], 1) == f, f"control 19, B6: φ de {grupo} {f} (da {g[grupo]['phi']['phi']:.3f})")
    comprobar(all(g[f"contador {c}"]["frente_a_sin_aviso"] == "por encima" for c in (5, 187, 188, 197, 198)),
              "control 19, B6: con φ, todos los contadores siguen por encima de las fotos sin aviso")
    c8, sa = g["contador 188"], g["sin aviso"]
    comprobar([rd(c8["falla_desde"], 3), rd(c8["falla_hasta"], 3), rd(sa["falla_desde"], 3), rd(sa["falla_hasta"], 3)]
              == [1.148, 1.467, 0.139, 0.159],
              f"control 19, B6: 188 de 1,148 a 1,467 % frente a 0,139 a 0,159 % (da {c8['falla_desde']:.4f} a "
              f"{c8['falla_hasta']:.4f} y {sa['falla_desde']:.4f} a {sa['falla_hasta']:.4f})")
    pa_ = {x["ano"]: x for x in b6["sin_aviso_por_ano"]}
    comprobar([rd(pa_[a]["pct_sin_aviso"], 1) for a in range(2020, 2026)] == [40.3, 36.8, 26.6, 22.5, 20.5, 17.9],
              f"control 19, B6: sin aviso el día anterior por año (da {[round(pa_[a]['pct_sin_aviso'], 2) for a in sorted(pa_)]})")
    comprobar([rd(pa_[a]["pct_sin_dia"], 1) for a in range(2020, 2026)] == [2.1, 2.1, 4.5, 5.8, 5.3, 10.3],
              f"control 19, B6: sin día anterior por año (da {[round(pa_[a]['pct_sin_dia'], 2) for a in sorted(pa_)]})")
    az = {(x["k"], x["d"]): x for x in b7["azar"]["resultados"]}
    a = az[(2, 30)]
    comprobar(430 <= a["media"] <= 445 and a["observados"] == 489 and a["por_encima_del_p95"] is True,
              f"control 19, B7: media entre 430 y 445 y los 489 por encima del p95 (da media {a['media']:.2f}, "
              f"p95 {a['p95']:.1f})")
    comprobar(rd(mc["phi"]["phi"], 2) == 5.02, f"control 19, MC: φ 5,02 (da {mc['phi']['phi']:.4f})")
    n1 = {(x["dimension"], x["valor"]): x for x in mc["nivel_1"]}
    comprobar(all(n1[k]["frente_al_total"] == "no se distingue"
                  for k in [("fabricante", "HGST"), ("capacidad_tb", "4"), ("capacidad_tb", "24")]),
              "control 19, MC: HGST, 4 TB y 24 TB dejan de distinguirse")


def probar_json_real(m=None):
    """Controles de la petición 15 y dos cifras rehechas con pyarrow; con el JSON de la petición 19, sus controles."""
    ruta = CASO / SALIDA
    if not ruta.exists():
        print("aviso  no hay JSON real todavía: la parte 3 no se prueba")
        return
    j = json.loads(ruta.read_text(encoding="utf-8"))
    comprobar(j["resultado"]["estado"] in ("OK", "AVISO"), f"JSON real: estado {j['resultado']['estado']}")
    if "preguntas" not in j:
        return
    textos = [(CASO / n).read_text(encoding="utf-8").lower() for n in (SALIDA, SALIDA_MD)]
    comprobar(not any(VETADA in t for t in textos), "JSON real y su informe: sin la palabra vetada")
    b5, b6, b7, b8, mc = (pregunta(j, x)["tablas"] for x in ("B5", "B6", "B7", "B8", "MC"))

    def rd(x, d):
        """Redondeo como lo escribe la petición."""
        return round(x + 1e-12, d)

    # B5
    cen = {x["centro"]: x for x in b5["centros"]}
    for c, dd, ff, tt in [("ams5", 12111055, 476, 1.4346), ("iad1", 18007479, 512, 1.0378),
                          ("phx1", 65723705, 2160, 1.1996), ("sac0", 59117752, 2806, 1.7325),
                          ("sac2", 45064768, 2546, 2.0621), ("yyz1", 651306, 6, 0.3362),
                          ("sin dato", 6621213, 128, 0.7056)]:
        x = cen[c]
        comprobar(x["dias_disco"] == dd and x["fallos"] == ff and rd(x["tasa_bruta"], 4) == tt,
                  f"control B5: {c}, {dd} días, {ff} fallos, tasa {tt} (da {x['dias_disco']}, {x['fallos']}, "
                  f"{x['tasa_bruta']:.4f})")
    tri = b5["trimestres"]
    # 42 = cinco centros por 8 trimestres y yyz1 en 2; «sin dato» no es un centro y no lleva filas por trimestre
    comprobar(len(tri) == 42 and len({x["trimestre"] for x in tri}) == 8
              and sum(x["centro"] == "yyz1" for x in tri) == 2 and not any(x["centro"] == "sin dato" for x in tri),
              "control B5: 42 filas de centro y trimestre, yyz1 en 2 y ninguna «sin dato»")
    t2 = {(x["centro"], x["trimestre"]): x for x in tri}
    comprobar(rd(t2[("sac2", "2024T2")]["tasa"], 3) == 2.461 and rd(t2[("sac2", "2025T2")]["tasa"], 3) == 1.882,
              "control B5: sac2 2,461 en 2024T2 y 1,882 en 2025T2")
    aj = b5["ajustada"]
    comprobar(aj["filas"] == 8298 and round(aj["dias"]) == 206490290 and aj["fallos"] == 8634 and aj["celdas"] == 278
              and rd(aj["tasa_todos"], 4) == 1.5262, "control B5: 8.298 filas, 206.490.290 días, 8.634 fallos, 278 celdas")
    if "phi" not in b5:
        for c, rz, lo, hi in [("ams5", 1.0842, 0.9890, 1.1862), ("iad1", 1.0379, 0.9500, 1.1318),
                              ("phx1", 1.0527, 1.0087, 1.0980), ("sac0", 0.8934, 0.8607, 0.9271),
                              ("sac2", 1.0826, 1.0409, 1.1255), ("yyz1", 0.3990, 0.1464, 0.8684),
                              ("sin dato", 0.9001, 0.7510, 1.0703)]:
            x = cen[c]
            comprobar(rd(x["razon"], 4) == rz and rd(x["razon_desde"], 4) == lo and rd(x["razon_hasta"], 4) == hi,
                      f"control B5: razón de {c} {rz} ({lo} a {hi}) (da {x['razon']:.4f})")
        comprobar(rd(cen["sac0"]["tasa_ajustada"], 4) == 1.3635 and rd(cen["sac2"]["tasa_ajustada"], 4) == 1.6522,
                  "control B5: tasa ajustada de sac0 1,3635 y de sac2 1,6522")
    else:
        # La mezcla de B5 lleva el trimestre desde la petición 19: la razón y la tasa ajustada del 15 ya no valen
        print("aviso  B5 con la mezcla de la petición 19: los controles de la razón de la petición 15 no se aplican")
        probar_json_real_peticion19(b5, b6, b7, mc, rd, m)
    comprobar(b5["modelos_minimo_dos_centros"] == 21, "control B5: 21 modelos con el mínimo en dos centros o más")
    tm = {x["centro"]: x["media"] for x in b5["temperatura"]["por_centro"]}
    comprobar(all(rd(tm[c], 2) == v for c, v in [("ams5", 34.50), ("iad1", 33.73), ("phx1", 33.44), ("sac0", 30.02),
                                                 ("sac2", 35.87), ("yyz1", 30.88)]),
              "control B5: temperatura media por centro")

    # B6
    pm = {x["mes"]: x for x in b6["avisan_por_mes"]}
    comprobar(rd(pm["2020-01-01"]["pct"], 2) == 4.28 and rd(pm["2025-06-01"]["pct"], 2) == 7.42,
              "control B6: avisan 4,28 % en 2020-01 y 7,42 % en 2025-06")
    pf = {x["fabricante"]: x["pct"] for x in b6["avisan_por_fabricante"]}
    comprobar([rd(pf[k], 2) for k in ("HGST", "Seagate", "Toshiba", "WDC")] == [2.99, 10.52, 2.26, 0.85],
              "control B6: por fabricante 2,99, 10,52, 2,26 y 0,85 %")
    des = b6["desenlace"]
    g = {x["grupo"]: x for x in des["grupos"]}
    comprobar(des["fotos"] == 13978734, "control B6: 13.978.734 fotos con 90 días por delante")
    sa, ca = g["sin aviso"], g["con algún aviso"]
    comprobar(sa["fotos"] == 13126654 and rd(sa["pct_sigue"], 2) == 98.34 and rd(sa["pct_desaparece"], 2) == 1.51
              and rd(sa["pct_falla"], 2) == 0.15, "control B6: sin aviso, 13.126.654 fotos; 98,34, 1,51 y 0,15 %")
    comprobar(ca["fotos"] == 852080 and ca["discos"] == 40925 and rd(ca["pct_sigue"], 2) == 94.48
              and rd(ca["pct_falla"], 2) == 3.25 and rd(ca["pct_desaparece"], 2) == 2.27,
              "control B6: con algún aviso, 852.080 fotos de 40.925 discos; 94,48, 3,25 y 2,27 %")
    for c, n, pf_ in [("197", 149959, 9.58), ("198", 113845, 9.90), ("187", 218789, 6.46), ("5", 440582, 4.34),
                      ("188", 267618, 1.30)]:
        x = g[f"contador {c}"]
        comprobar(x["fotos"] == n and rd(x["pct_falla"], 2) == pf_, f"control B6: contador {c}, {n} fotos, falla {pf_} %")
    fv = b6["fallos"]
    comprobar(fv["con_dia_anterior"] == 16093 and fv["sin_aviso"] == 4046, "control B6: 16.093 con día anterior, 4.046 sin aviso")
    comprobar((fv["con_filas_antes"], fv["avisan_algun_dia"], fv["ya_primer_dia"], fv["empiezan_dentro"])
              == (16917, 12900, 10171, 2729) and (fv["dias_mediana"], fv["dias_q1"], fv["dias_q3"]) == (10, 4, 19),
              "control B6: 16.917, 12.900, 10.171 y 2.729; 10 días (4 y 19)")
    # Petición 17: el desenlace en Seagate; un JSON real de antes de la petición no lo trae y se avisa
    ds = b6.get("desenlace_seagate")
    if ds is None:
        print("aviso  el JSON real es de antes de la petición 17: el desenlace en Seagate se prueba tras la ejecución real")
    else:
        gs = {x["grupo"]: x for x in ds["grupos"]}
        for g, n, pf_ in [("contador 5", 344356, 4.05), ("contador 187", 218789, 6.46), ("contador 188", 267606, 1.30),
                          ("contador 197", 75992, 9.71), ("contador 198", 75992, 9.71)]:
            comprobar(gs[g]["fotos"] == n and rd(gs[g]["pct_falla"], 2) == pf_,
                      f"control 17, B6 Seagate: {g}, {n} fotos, falla {pf_} % (da {gs[g]['fotos']}, {gs[g]['pct_falla']:.2f})")
        comprobar(gs["sin aviso"]["fotos"] == 6015625 and rd(gs["sin aviso"]["pct_falla"], 3) == 0.166,
                  "control 17, B6 Seagate: sin aviso, 6.015.625 fotos, falla 0,166 %")
        c = ds["contadores_197_198"]
        comprobar(c["fotos_197"] == 75992 and c["fotos_198"] == 75992,
                  f"control 17, B6 Seagate: el 197 y el 198, 75.992 fotos cada uno (los dos a la vez: {c['las_dos']}; "
                  f"mismas fotos: {c['mismas_fotos']})")
    co = {x["contador"]: x for x in b6["construccion"]}
    for c, a1, n1, a0, n0 in [("5", 3779, 11641, 58975, 10658403), ("187", 3205, 7971, 22540, 5476340),
                              ("197", 2482, 11503, 24092, 10485315), ("198", 1936, 11641, 16097, 10658403)]:
        x = co[c]
        comprobar((x["fallan_sube"], x["fallan_filas"], x["no_fallan_sube"], x["no_fallan_filas"]) == (a1, n1, a0, n0),
                  f"control B6: contador {c}, {a1} de {n1} frente a {a0} de {n0}")

    # B7
    t7 = b7["fallos"]
    comprobar((t7["desde_07_2023"], t7["sin_centro"], t7["sin_tomo"], t7["con_tomo"], t7["tomos"], t7["coinciden"])
              == (8634, 128, 141, 8493, 5404, 262), "control B7: 8.634, 128, 141, 8.493 en 5.404 tomos, 262")
    kd = {(x["k"], x["d"]): x for x in b7["k_en_d"]}
    comprobar([kd[(k, d)]["tomos"] for k, d in [(2, 7), (2, 30), (3, 7), (3, 30), (4, 7), (4, 30)]]
              == [151, 489, 8, 28, 0, 8], "control B7: 151, 489, 8, 28, 0 y 8 tomos")
    comprobar(list(kd[(2, 30)]["por_trimestre"].values()) == [48, 50, 56, 117, 83, 46, 53, 36],
              "control B7: 2 o más en 30 días por trimestre")
    lv = b7["a_la_vez"]
    comprobar(lv["reparto"] == {"1": 8231, "2": 250, "3": 12} and lv["llegan_a_paridad"] == 2,
              "control B7: 8.231 solos, 250 con dos y 12 con tres; la paridad, 2 veces")
    tres = {x["capacidad_tb"]: x["fallos"] for x in lv["por_capacidad"] if x["a_la_vez"] == 3}
    comprobar(tres == {12.0: 6, 8.0: 2, 14.0: 2, 16.0: 2}, "control B7: los de tres, 6 en 12 TB y 2 en 8, 14 y 16")
    pt = b7["peores_tomos"][0]
    comprobar(pt["tomo"] == "phx1|1063|59" and sorted(pt["modelos"]) == ["TOSHIBA MG07ACA14TA", "TOSHIBA MG08ACA16TA"]
              and pt["fallos"] == 9 and pt["coincidencias"] == 3,
              "control B7: el peor tomo, phx1|1063|59, dos modelos, 9 fallos y 3 coincidencias")
    az = {(x["k"], x["d"]): x for x in b7["azar"]["resultados"]}
    if "estrato" not in b7["azar"]:
        comprobar(az[(2, 30)]["observados"] == 489 and az[(2, 30)]["por_encima_del_p95"] is True
                  and az[(3, 7)]["observados"] == 8 and az[(3, 7)]["por_encima_del_p95"] is True,
                  "control B7: los dos, por encima del percentil 95 del azar (el lado)")
    else:
        # Desde la petición 19 el lado es un resultado; los de 3 en 7 días se dicen, sin control escrito
        print(f"info   B7, 3 fallos en 7 días: {az[(3, 7)]['observados']} observados, media {az[(3, 7)]['media']:.2f}, "
              f"p95 {az[(3, 7)]['p95']:.1f}, por encima: {az[(3, 7)]['por_encima_del_p95']}")
    rv = b7["riesgo_vivo"]
    comprobar(len(rv["meses"]) == 24 and rd(rv["media_dos"], 1) == 4327.9 and rd(rv["media_esperados_dos"], 1) == 5720.6
              and rd(rv["razon_dos"], 3) == 0.757 and rv["min_dos"] == 3618 and rv["max_dos"] == 5165
              and rv["ultimo_dos"] == 5165, "control B7: riesgo vivo de 2 o más, 4.327,9 frente a 5.720,6")
    comprobar(rd(rv["media_tres"], 1) == 2769.5 and rd(rv["media_esperados_tres"], 1) == 2260.8
              and rd(rv["razon_tres"], 3) == 1.225 and rv["ultimo_tres"] == 3353,
              "control B7: riesgo vivo de 3 o más, 2.769,5 frente a 2.260,8")

    # B8
    rp = b8["reparto"]
    comprobar(round(rp["dias_repartidos"]) == 445189491 and rp["dias_recuento"] == 446108683
              and rp["fallos_con_foto"] == 16725 and rp["fallos_sin_foto_anterior"] == 271,
              "control B8: 445.189.491 de 446.108.683 días; 16.725 fallos con foto y 271 sin ella")
    for f, ge, gt, fe, rz in [("temperatura", 20, 61, 16200, [0.7737, 0.8983, 1.2958]),
                              ("arranques", 41, 332, 11723, [0.7779, 1.1956, 1.5359]),
                              ("escritos", 41, 155, 9242, [0.9307, 1.0927, 0.9764]),
                              ("leidos", 37, 155, 8860, [0.8372, 1.0221, 1.1408])]:
        x = b8["factores"][f]
        comprobar(x["grupos_entran"] == ge and x["grupos"] == gt and x["fallos_entran"] == fe
                  and [rd(t["razon"], 4) for t in x["tramos"]] == rz,
                  f"control B8: {f}, {ge} de {gt} grupos, {fe} fallos, razones {rz}")

    # Minicubo y lo que falta
    n1 = {(x["dimension"], x["valor"]): x for x in mc["nivel_1"]}
    for k, v in [(("fabricante", "HGST"), 1.2758), (("fabricante", "Seagate"), 1.7615), (("fabricante", "Toshiba"), 1.0719),
                 (("fabricante", "WDC"), 0.5179), (("capacidad_tb", "12"), 1.7200), (("capacidad_tb", "8"), 2.0770),
                 (("capacidad_tb", "16"), 0.8154), (("edad", "00_0"), 0.7305), (("edad", "05_5"), 2.5409),
                 (("centro", "sac2"), 2.0522), (("centro", "antes_de_07_2023"), 1.2566), (("avisa", "sí"), 14.9095),
                 (("avisa", "no"), 0.4891)]:
        comprobar(rd(n1[k]["tasa"], 4) == v, f"control MC: {k[0]} {k[1]}, tasa {v} (da {n1[k]['tasa']:.4f})")
    comprobar(n1[("capacidad_tb", "12")]["fallos"] == 5769 and n1[("centro", "sac2")]["fallos"] == 2524
              and n1[("centro", "antes_de_07_2023")]["fallos"] == 8218 and n1[("avisa", "sí")]["fallos"] == 11124
              and n1[("avisa", "no")]["fallos"] == 5601, "control MC: fallos de 12 TB, sac2, antes, avisa sí y no")
    lf = mc["lo_que_falta"]
    sr = lf["sin_ranura_dia_fallo"]
    comprobar([(sr[q]["sin_ranura"], sr[q]["fallos"]) for q in ("2024T3", "2024T4", "2025T1", "2025T2")]
              == [(60, 1389), (67, 1001), (861, 1067), (840, 1061)], "control: sin ranura el día del fallo")
    comprobar([lf["sin_tomo_fallos_detalle"][q] for q in ("2024T4", "2025T1", "2025T2")] == [40, 2, 2]
              and lf["smart_90_no_vacio"] == 344969, "control: sin tomo 40, 2 y 2; smart_90 en 344.969 fotos")

    # Otro camino, con pyarrow y sin pandas
    dm = pq.read_table(PROCESADOS / "dim_modelo.parquet", columns=["model", "tipo_disco"]).to_pylist()
    datos = sorted({f["model"] for f in dm if f["tipo_disco"] == "datos"})
    rec = pq.read_table(PROCESADOS / "recuento_diario_corregido.parquet", columns=["fecha", "model", "fallos"])
    rec = rec.filter(pc.is_in(rec["model"], value_set=pa.array(datos)))
    tipo = rec.schema.field("fecha").type
    desde = pc.greater_equal(rec["fecha"], pa.scalar(dt.datetime(2023, 7, 1), type=tipo))
    comprobar(pc.sum(rec.filter(desde)["fallos"]).as_py() == t7["desde_07_2023"],
              "otra vía (pyarrow, recuento): fallos desde 07/2023 = los de B7")
    f90 = pq.read_table(PROCESADOS / "fotos_riesgo.parquet", columns=["smart_90_raw"])
    comprobar(f90.num_rows - f90["smart_90_raw"].null_count == lf["smart_90_no_vacio"],
              "otra vía (pyarrow): fotos con smart_90_raw no vacío")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        modulo = cargar_modulo()
        if modulo is not None:
            probar_piezas(modulo)
            probar_peticion19(modulo)
            probar_caso_pequeno()
        probar_json_real(modulo)
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print()
    if FALLOS:
        print(f"{len(FALLOS)} casos fallan:")
        for f in FALLOS:
            print("  - " + f)
        sys.exit(1)
    print("todos los casos pasan")
    sys.exit(0)
