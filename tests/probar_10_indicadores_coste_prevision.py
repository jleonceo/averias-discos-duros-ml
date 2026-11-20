"""Prueba de scripts/10_indicadores_coste_prevision.py, con lo que añade el encargo 17 en B4: sin puesto con menos de
20 fallos (CP-012), el coste a igual edad con la tasa del JSON del 09 y la sensibilidad al precio inferido.

Parte 1, las piezas sueltas. Carga el script como módulo (su trabajo está dentro de `if __name__ == "__main__":`, así
que cargarlo no lo ejecuta) y prueba cada función con datos pequeños escritos aquí:
  - el intervalo exacto de Poisson, contra scipy.stats.gamma, otra implementación del mismo intervalo (error 30);
  - la tabla de vida, la supervivencia, el corte por el mínimo de fallos y la vida real (la edad a la que S baja de 0,5),
    contra cuentas hechas a mano; sin cruce, la vida real queda vacía con su motivo;
  - la previsión de un trimestre: los tres niveles de tasa, el mínimo de días y que un mes del propio trimestre no
    cambia nada; la segunda cuenta, en bucle, da lo mismo;
  - el error absoluto ponderado y el sesgo, contra una cuenta a mano;
  - la lectura de los ingresos del doc. 16;
  - cada comprobación con un caso que da verde y otro que tiene que dar rojo (error 24), también la que busca un mes
    igual o posterior al primer día del trimestre y la de la palabra vetada;
  - cada una de las nueve validaciones con un caso que tiene que dar rojo;
  - la búsqueda de resultados escritos a mano.
Parte 2, el script entero sobre un caso pequeño. Monta en tests/tmp_indicadores_coste/ las tablas que lee el script,
con el tipo de cada columna tomado del parquet real (pyarrow.parquet.read_schema, sin cargar datos), su
informes/transformacion-datos.json con las huellas, los dos exploratorios, el JSON del encargo 13, el doc. 16 y un
data/raw/. Ejecuta el script con -W error y comprueba las cifras contra las calculadas aquí a mano. Después, cinco casos
que tienen que parar:
  - modelo_trimestre con el coste de un fallo cambiado: la segunda vía del coste de los fallos no coincide, ERROR;
  - inicio_trimestre con un disco de más: la de los discos del primer día no coincide, ERROR;
  - fallos_detalle con un fallo de más: la de los fallos reales por trimestre y capacidad no coincide, ERROR;
  - la huella de una tabla distinta de la de transformacion-datos.json, ERROR;
  - el JSON del encargo 13 en PARADO: el script no calcula, PARADO;
  - el JSON del 09 sin la tasa a igual edad (anterior al encargo 17): PARADO;
  - el JSON del 09 con otros días de disco que el ranking de coste: ERROR.
Parte 3, el JSON real, si existe: las cifras de control del encargo (prompts/14_…, «CONTROLES»), escritas como las da
el encargo, y dos cifras rehechas por otro camino, con pyarrow y sin pandas:
  - los fallos de los discos de datos de 2021 a junio de 2025 desde recuento_diario_corregido, frente a los reales de la
    previsión (que salen de fallos_detalle);
  - los discos de inicio_trimestre (3.117 filas, 22 trimestres).
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
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "10_indicadores_coste_prevision.py"
TMP = CASO / "tests" / "tmp_indicadores_coste"
SALIDA = "informes/indicadores__coste_prevision.json"
SALIDA_MD = "informes/indicadores__coste_prevision.md"
PROCESADOS = CASO / "data" / "processed"
# La palabra vetada para el conjunto de discos (Juan, 17/11; R68-91), partida para que esta prueba no la lleve
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
    spec = importlib.util.spec_from_file_location("indicadores_10", SCRIPT)
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
    import pandas as pd
    from scipy import stats

    # 2.1 Intervalo exacto de Poisson, contra la misma cuenta con la gamma
    t, lo, hi = m.intervalo_poisson(391, 2417642)
    g_lo = stats.gamma.ppf(0.025, 391) * 100 * 365 / 2417642
    g_hi = stats.gamma.ppf(0.975, 392) * 100 * 365 / 2417642
    comprobar(cerca(t, 100 * 365 * 391 / 2417642) and cerca(lo, g_lo) and cerca(hi, g_hi),
              "Poisson con chi2 igual que con la gamma (otra vía)")
    t, lo, hi = m.intervalo_poisson(0, 36500)
    comprobar(t == 0 and lo == 0 and cerca(hi, 3.689, 1e-3), "Poisson con 0 fallos: 0 a 3,689")

    # 2.2 Tabla de vida, supervivencia, corte y vida real, a mano
    tv = m.tabla_de_vida([0.0, 0.5, 1.0], [2.0, 1.5, 3.0], [False, True, False], edades=range(3))
    comprobar(cerca(tv[0]["exposicion_anos"], 1.5) and cerca(tv[1]["exposicion_anos"], 2.5)
              and tv[1]["eventos"] == 1 and cerca(tv[1]["tasa"], 0.4), "tabla de vida: exposición y eventos a mano")
    s = m.supervivencia([0.2, 0.9, 0.1])
    comprobar(cerca(s[1], math.exp(-0.2)) and cerca(s[2], math.exp(-1.1)), "S(k) = exp(−suma de tasas)")
    curva, motivo = m.cortar_curva([1.0, 0.9, 0.8, 0.7], [30, 5, 40], 20)
    comprobar(curva[:2] == [1.0, 0.9] and curva[2] is None and motivo, "la curva se corta tras el primer año con < 20")
    # S cruza 0,5 entre 1 y 2 años: H(1) = 0,2 y tasa del año 1 = 0,9; edad = 1 + (ln 2 − 0,2) / 0,9
    v, motivo = m.vida_real([1.0, math.exp(-0.2), math.exp(-1.1), None], [0.2, 0.9, 0.1])
    comprobar(cerca(v, 1 + (math.log(2) - 0.2) / 0.9) and motivo is None, "vida real: cruce de 0,5 dentro del año 1")
    v, motivo = m.vida_real([1.0, 0.9, 0.8, None], [0.105, 0.118, 0.1])
    comprobar(v is None and motivo, "vida real: sin cruce de 0,5, vacía con su motivo")
    v, motivo = m.vida_real([1.0, 0.9, 0.8, 0.4], [0.105, 0.118, 0.69])
    comprobar(v is not None and 2 < v < 3, "vida real: el cruce cae en el último año con base")

    # 2.3 Previsión de un trimestre: tres niveles, el mínimo y un mes del propio trimestre que no cuenta
    inicio = pd.Timestamp(2021, 1, 1)
    dpt = pd.DataFrame([
        # A, 8 TB, edad 2: 60.000 días y 6 fallos antes del trimestre (nivel modelo)
        {"model": "A", "capacidad_tb": 8.0, "mes": pd.Timestamp(2020, 11, 1), "edad_anos_cumplidos": 2,
         "dias_disco": 60000.0, "fallos": 6},
        # B, 8 TB, edad 2: 10.000 días y 4 fallos (no llega: nivel capacidad, 70.000 días y 10 fallos)
        {"model": "B", "capacidad_tb": 8.0, "mes": pd.Timestamp(2020, 12, 1), "edad_anos_cumplidos": 2,
         "dias_disco": 10000.0, "fallos": 4},
        # C, 6 TB, edad 2: 1.000 días y 0 fallos (ni modelo ni capacidad: nivel edad, 71.000 días y 10 fallos)
        {"model": "C", "capacidad_tb": 6.0, "mes": pd.Timestamp(2020, 12, 1), "edad_anos_cumplidos": 2,
         "dias_disco": 1000.0, "fallos": 0},
        # El propio mes del trimestre, con muchos fallos: no tiene que contar
        {"model": "A", "capacidad_tb": 8.0, "mes": pd.Timestamp(2021, 1, 1), "edad_anos_cumplidos": 2,
         "dias_disco": 30000.0, "fallos": 900},
    ])
    it = pd.DataFrame([
        {"ano": 2021, "trimestre": 1, "model": "A", "edad_anos_cumplidos": 2, "capacidad_tb": 8.0, "discos": 100,
         "dias_trimestre": 90},
        {"ano": 2021, "trimestre": 1, "model": "B", "edad_anos_cumplidos": 2, "capacidad_tb": 8.0, "discos": 10,
         "dias_trimestre": 90},
        {"ano": 2021, "trimestre": 1, "model": "C", "edad_anos_cumplidos": 2, "capacidad_tb": 6.0, "discos": 5,
         "dias_trimestre": 90},
    ])
    p = m.prever_trimestre(2021, 1, it, dpt)
    f = p["filas"].set_index("model")
    comprobar(list(f.loc[["A", "B", "C"], "nivel"]) == ["modelo", "capacidad", "edad"],
              "previsión: niveles modelo, capacidad y edad")
    comprobar(cerca(f.loc["A", "previsto"], 100 * 90 * 6 / 60000) and cerca(f.loc["B", "previsto"], 10 * 90 * 10 / 70000)
              and cerca(f.loc["C", "previsto"], 5 * 90 * 10 / 71000), "previsión: discos × días × tasa de su nivel")
    comprobar(p["ultimo_mes_usado"] < inicio, "previsión: el mes del propio trimestre no se usa")
    comprobar(cerca(p["previsto_por_capacidad"][8.0], 100 * 90 * 6 / 60000 + 10 * 90 * 10 / 70000),
              "previsión: suma por capacidad")
    b = m.prever_trimestre_bucle(2021, 1, it, dpt)
    comprobar(all(cerca(b[c], p["previsto_por_capacidad"][c]) for c in (6.0, 8.0)), "previsión en bucle: lo mismo")
    # Con mínimo de 1 día, B y C usan su propio modelo
    p1 = m.prever_trimestre(2021, 1, it, dpt, minimo=1)
    f1 = p1["filas"].set_index("model")
    comprobar(list(f1.loc[["A", "B", "C"], "nivel"]) == ["modelo"] * 3 and f1.loc["C", "previsto"] == 0,
              "previsión con mínimo de 1 día: todos en su modelo")
    # Solo capacidad y edad: A y B toman la de su capacidad
    pc_ = m.prever_trimestre(2021, 1, it, dpt, niveles=("capacidad", "edad"))
    comprobar(list(pc_["filas"].set_index("model").loc[["A", "B"], "nivel"]) == ["capacidad"] * 2,
              "previsión sin el nivel modelo: capacidad")
    # Una fila sin días (vacío) y con 2 fallos: cuenta 0 días y sus fallos, igual en las dos cuentas
    dpt_v = pd.concat([dpt, pd.DataFrame([{"model": "B", "capacidad_tb": 8.0, "mes": pd.Timestamp(2020, 12, 1),
                                           "edad_anos_cumplidos": 2, "dias_disco": float("nan"), "fallos": 2}])],
                      ignore_index=True)
    pv = m.prever_trimestre(2021, 1, it, dpt_v)
    bv = m.prever_trimestre_bucle(2021, 1, it, dpt_v)
    comprobar(cerca(pv["filas"].set_index("model").loc["B", "previsto"], 10 * 90 * 12 / 70000)
              and all(cerca(bv[c], pv["previsto_por_capacidad"][c]) for c in (6.0, 8.0)),
              "previsión: una fila sin días cuenta 0 días y sus fallos, en las dos cuentas")
    # Con 1 mes de historia, el de diciembre: A no llega y toma la de su capacidad (10.000 días, no llega) y la edad
    p12 = m.prever_trimestre(2021, 1, it, dpt, meses_historia=1)
    comprobar(p12["filas"].set_index("model").loc["A", "nivel"] == "edad", "previsión con historia corta: solo diciembre")

    # 2.4 Error absoluto ponderado y sesgo, a mano
    w, s_ = m.error_ponderado([10, 5, 0], [8, 6, 2])
    comprobar(cerca(w, (2 + 1 + 2) / 16) and cerca(s_, (2 - 1 - 2) / 16), "error ponderado y sesgo a mano")
    comprobar(m.error_ponderado([1], [0]) == (None, None), "error ponderado sin reales: vacío, sin dividir por cero")

    # 2.5 Ingresos del doc. 16
    texto = ("[Ingresos por producto, años cerrados a 31 de diciembre, miles de $]\n"
             "                         | 2025    | 2024    | 2023\n"
             "B2 Cloud Storage         | 79,897  | 63,335  | 46,427\n"
             "Total revenue            | 145,835 | 127,628 | 102,019\n")
    ing = m.leer_ingresos(texto)
    comprobar(ing == {2025: 145835000, 2024: 127628000, 2023: 102019000}, "ingresos del doc. 16, en dólares")

    # 2.6 Comprobaciones, cada una en verde y en rojo
    comprobar(m.comp_unidad(["a", "b"]) is True and m.comp_unidad(["a", "a"]) is False, "unidad: repetida, rojo")
    comprobar(m.comp_empates([1.0, 1.0, 2.0], [1, 1, 3]) is True and m.comp_empates([1.0, 1.0], [1, 2]) is False,
              "empates: el mismo valor con distinto puesto, rojo")
    comprobar(m.comp_minimo_ranking([60000, 50000], [True, True], 50000) is True
              and m.comp_minimo_ranking([49999], [True], 50000) is False, "mínimo del ranking: rojo bajo el mínimo")
    comprobar(m.comp_minimo_tasas([("modelo", 60000), ("capacidad", 50000), ("edad", 3)], 50000) is True
              and m.comp_minimo_tasas([("modelo", 49999)], 50000) is False,
              "mínimo de las tasas: un nivel modelo o capacidad bajo el mínimo, rojo")
    comprobar(m.comp_referencia([100, 200], [1, 2], 300, 3) is True
              and m.comp_referencia([100, 200], [1, 2], 301, 3) is False, "referencia con otras filas, rojo")
    comprobar(m.comp_partes_total([[1, 2], [3, 4]], [3, 7]) is True
              and m.comp_partes_total([[1, 2]], [4]) is False, "partes que no suman el total, rojo")
    ini = [pd.Timestamp(2021, 1, 1), pd.Timestamp(2021, 4, 1)]
    comprobar(m.comp_sin_futuro([pd.Timestamp(2020, 12, 1), pd.Timestamp(2021, 3, 1)], ini) is True
              and m.comp_sin_futuro([pd.Timestamp(2020, 12, 1), pd.Timestamp(2021, 4, 1)], ini) is False,
              "sin futuro: un mes del propio trimestre, rojo")
    pares = [{"trimestre": "2021T2", "capacidad_tb": 8.0, "referencia": 3}]
    comprobar(m.comp_referencia_desplazada(pares, {("2021T1", 8.0): 3}, {"2021T2": "2021T1"}) is True
              and m.comp_referencia_desplazada(pares, {("2021T1", 8.0): 4}, {"2021T2": "2021T1"}) is False,
              "referencia del trimestre anterior: otra cifra, rojo")
    comprobar(m.comp_periodos([{"ano": 2025, "parcial": True}], "ano", {2025}) is True
              and m.comp_periodos([{"ano": 2025, "parcial": False}], "ano", {2025}) is False, "periodos: rojo")
    comprobar(m.comp_cobertura(0.9) is True and m.comp_cobertura(None) is False and m.comp_cobertura(1.3) is False,
              "cobertura: fuera de 0 a 1, rojo")
    comprobar(m.comp_sin_vetada(["todos los discos"]) is True and m.comp_sin_vetada(["la " + VETADA.upper()]) is False,
              "palabra vetada: rojo si sale")

    # 2.7 Validaciones: un resultado mínimo que pasa las nueve, y un rojo para cada una
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

    # 2.8 La búsqueda de resultados escritos
    comprobar(len(m.buscar_resultados_escritos('x["sin_futuro"] = True\n')) == 1,
              "búsqueda: encuentra una comprobación extra puesta a True")
    comprobar(len(m.buscar_resultados_escritos("total = 15689\n")) == 1, "búsqueda: encuentra una cifra larga")
    comprobar(len(m.buscar_resultados_escritos("MINIMO = 50_000\n")) == 0, "búsqueda: el mínimo de las reglas pasa")
    comprobar(m.buscar_resultados_escritos(SCRIPT.read_text(encoding="utf-8")) == [],
              "el script no lleva ningún resultado escrito")

    # 2.9 Encargo 17: CP-012, coste a igual edad, salto de puesto y sensibilidad al precio inferido
    probar_piezas_encargo17(m)
    # 2.10 Encargo 19: el puesto dentro de cada capacidad y año de compra
    probar_piezas_encargo19(m)


def puestos_a_mano(filas, minimo=20):
    """El puesto dentro de cada capacidad y año de compra, rehecho aquí (segunda vía del encargo 19): por grupo, los de
    `minimo` fallos o más ordenados por coste; empates en el coste, el mismo puesto («min»)."""
    grupos = {}
    for f in filas:
        if f["fallos"] >= minimo:
            grupos.setdefault((f["capacidad_tb"], f.get("ano_compra")), []).append(f)
    out = {}
    for xs in grupos.values():
        costes = sorted(x["coste_tb_ano"] for x in xs)
        for x in xs:
            out[x["model"]] = 1 + costes.index(x["coste_tb_ano"])
    return out


def probar_piezas_encargo19(m):
    """El puesto de B4 dentro de cada capacidad y año de compra (encargo 19), con su caso en rojo."""
    import pandas as pd

    f = getattr(m, "comp_puesto_grupo", None)
    comprobar(f is not None, "encargo 19: el script tiene la comprobación del puesto dentro del grupo")
    if f is None:
        return
    # Caso en rojo: dos modelos de 12 y 16 TB con puestos 1 y 2, como si fueran del mismo grupo
    mal = [{"model": "A", "capacidad_tb": 12.0, "ano_compra": 2021, "fallos": 30, "coste_tb_ano": 2.0, "puesto": 1},
           {"model": "B", "capacidad_tb": 16.0, "ano_compra": 2021, "fallos": 30, "coste_tb_ano": 2.5, "puesto": 2}]
    bien = [dict(mal[0]), dict(mal[1], puesto=1)]
    otro_ano = [dict(mal[0]), dict(mal[0], model="C", ano_compra=2020, coste_tb_ano=1.0, puesto=2)]
    comprobar(f(mal) is False and f(bien) is True and f(otro_ano) is False,
              "encargo 19, comprobación: 12 y 16 TB con puestos 1 y 2 del mismo grupo, rojo; dos años de compra, rojo")
    # b4_ranking con el año de compra: Q40 y R30 de 1 TB de 2020, S25 de 2 TB de 2021, P19 con 19 fallos
    celdas = pd.DataFrame([
        {"model": "P19", "ano": 2021, "capacidad_tb": 1.0, "precio_usd": 6.0, "origen_precio": "curva",
         "dias_disco": 365000, "fallos": 19, "coste_f": 190.0, "coste_fg": 190.0, "pasa": True, "dias_ano": 365000},
        {"model": "Q40", "ano": 2021, "capacidad_tb": 1.0, "precio_usd": 12.0, "origen_precio": "inferido",
         "dias_disco": 365000, "fallos": 40, "coste_f": 400.0, "coste_fg": 400.0, "pasa": True, "dias_ano": 365000},
        {"model": "R30", "ano": 2021, "capacidad_tb": 1.0, "precio_usd": 18.0, "origen_precio": "curva",
         "dias_disco": 365000, "fallos": 30, "coste_f": 300.0, "coste_fg": 300.0, "pasa": True, "dias_ano": 365000},
        {"model": "S25", "ano": 2021, "capacidad_tb": 2.0, "precio_usd": 6.0, "origen_precio": "curva",
         "dias_disco": 365000, "fallos": 25, "coste_f": 250.0, "coste_fg": 250.0, "pasa": True, "dias_ano": 365000}])
    celdas["tb_ano"] = celdas["dias_disco"] * celdas["capacidad_tb"] / 365
    try:
        filas, _, resumen = m.b4_ranking(celdas, 365, {(1.0, 2021): 10.0, (2.0, 2021): 10.0},
                                         ano_compra={"P19": 2020, "Q40": 2020, "R30": 2020, "S25": 2021})
    except Exception as e:  # noqa: BLE001 - el script de antes no lo admite
        filas, resumen = [], {}
        print(f"       (b4_ranking con año de compra: {type(e).__name__}: {e})")
    rk = {x["model"]: x for x in filas}
    esp = puestos_a_mano(filas)
    comprobar(bool(filas) and {mo: rk[mo].get("puesto") for mo in esp} == esp == {"Q40": 1, "R30": 2, "S25": 1}
              and rk["P19"].get("puesto") is None,
              f"encargo 19: puesto dentro de capacidad y año de compra, rehecho aquí (da "
              f"{ {mo: x.get('puesto') for mo, x in rk.items()} })")
    # El orden de todos juntos se queda al lado: S25 cuesta 0,5 + 0,25 = 0,75, Q40 2,4 y R30 3,3
    comprobar({mo: x.get("puesto_global") for mo, x in rk.items()} == {"S25": 1, "Q40": 2, "R30": 3, "P19": None},
              "encargo 19: el puesto de todos juntos, al lado")
    rg = resumen.get("grupos_compra", {})
    comprobar(rg.get("grupos_con_puesto") == 2 and rg.get("grupos_con_dos_o_mas") == 1 and f(filas) is True,
              "encargo 19: dos grupos con puesto, uno con dos modelos o más; la comprobación en verde")


def probar_piezas_encargo17(m):
    """Las piezas nuevas del encargo 17, cada una contra una cuenta a mano y con su caso en rojo."""
    import pandas as pd

    # Ningún modelo con menos de 20 fallos lleva puesto (caso en rojo: uno con 19 y puesto)
    f = getattr(m, "comp_puesto_minimo", None)
    comprobar(f is not None and f([{"fallos": 20, "puesto": 1}, {"fallos": 19, "puesto": None}]) is True
              and f([{"fallos": 19, "puesto": 2}]) is False and f([{"fallos": 25, "puesto": None}]) is False,
              "encargo 17, CP-012: un modelo con 19 fallos y puesto, rojo; uno con 20 sin puesto, rojo")

    # El ranking de coste deja sin puesto, al final, al modelo con 19 fallos aunque sea el más barato
    celdas = pd.DataFrame([
        {"model": "P19", "ano": 2021, "capacidad_tb": 1.0, "precio_usd": 6.0, "origen_precio": "curva",
         "dias_disco": 365000, "fallos": 19, "coste_f": 190.0, "coste_fg": 190.0, "pasa": True, "dias_ano": 365000},
        {"model": "Q40", "ano": 2021, "capacidad_tb": 1.0, "precio_usd": 12.0, "origen_precio": "inferido",
         "dias_disco": 365000, "fallos": 40, "coste_f": 400.0, "coste_fg": 400.0, "pasa": True, "dias_ano": 365000},
        {"model": "R30", "ano": 2021, "capacidad_tb": 1.0, "precio_usd": 18.0, "origen_precio": "curva",
         "dias_disco": 365000, "fallos": 30, "coste_f": 300.0, "coste_fg": 300.0, "pasa": True, "dias_ano": 365000}])
    celdas["tb_ano"] = celdas["dias_disco"] * celdas["capacidad_tb"] / 365
    try:
        filas, _, resumen = m.b4_ranking(celdas, 365, {(1.0, 2021): 10.0})
    except Exception as e:  # noqa: BLE001 - el script de antes puede no admitirlo
        filas, resumen = [], {}
        print(f"       (b4_ranking: {type(e).__name__}: {e})")
    orden = [(x["model"], x.get("puesto")) for x in filas]
    comprobar(orden == [("Q40", 1), ("R30", 2), ("P19", None)],
              f"encargo 17, CP-012: P19 (19 fallos) sin puesto y al final del ranking de coste (da {orden})")
    # Resumen solo con los de puesto: Q40 cuesta 2 + 400/1000 = 2,4 y R30, 3 + 0,3 = 3,3
    comprobar(resumen.get("primeros_diez") == 2 and resumen.get("primeros_diez_inferidos") == 1
              and cerca(resumen.get("mediana_parte_fallos_pct"), (100 * 0.4 / 2.4 + 100 * 0.3 / 3.3) / 2),
              "encargo 17, CP-012: el resumen de B4 solo con los dos modelos con puesto")

    # Coste a igual edad = amortización + tasa a igual edad / 100 × coste de un fallo × días / 365 / terabytes-año
    f = getattr(m, "coste_igual_edad", None)
    comprobar(f is not None and cerca(f(2.0, 5.0, 300.0, 730000, 4000.0), 2.0 + 5.0 / 100 * 300.0 * 730000 / 365 / 4000.0)
              and f(2.0, None, 300.0, 730000, 4000.0) is None,
              "encargo 17: coste a igual edad con la fórmula del encargo; sin tasa, vacío")

    # Mayor salto de puesto entre dos órdenes: 1, 2, 3 frente a 3, 2, 1 salta 2
    f = getattr(m, "salto_de_puesto", None)
    comprobar(f is not None and f([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == 2 and f([1.0, 2.0], [5.0, 6.0]) == 0,
              "encargo 17: mayor salto de puesto a mano")

    # Sensibilidad al precio inferido: B inferido. Base B 1,3, A 1,5, C 1,52; × 1,2: A, C, B; × 0,8: B, A, C
    f = getattr(m, "sensibilidad_precio", None)
    filas_s = [{"model": "B", "precio_usd": 7.2, "capacidad_tb": 1.0, "origen_precio": "inferido", "fallos_tb_ano": 0.1},
               {"model": "A", "precio_usd": 6.0, "capacidad_tb": 1.0, "origen_precio": "curva", "fallos_tb_ano": 0.5},
               {"model": "C", "precio_usd": 8.52, "capacidad_tb": 1.0, "origen_precio": "curva", "fallos_tb_ano": 0.1}]
    for x in filas_s:
        x["coste_tb_ano"] = x["precio_usd"] / x["capacidad_tb"] / 6 + x["fallos_tb_ano"]
    s = {x["factor"]: x for x in f(filas_s, (0.8, 1.2), 2)} if f is not None else {}
    comprobar(s.get(1.2, {}).get("siguen") == 1 and s.get(1.2, {}).get("primero") == "A"
              and s.get(0.8, {}).get("siguen") == 2 and s.get(0.8, {}).get("primero") == "B"
              and s.get(1.2, {}).get("de") == 2,
              "encargo 17: sensibilidad al precio inferido a mano (× 1,2 sigue 1 de 2 y el primero es A)")


def resultado_minimo():
    """Un JSON pequeño con una pregunta completa, que pasa las nueve validaciones."""
    comp = {k: None for k in ["unidad", "minimo", "empates", "referencia", "azar_en_grupos", "pesos",
                              "hacia_adelante", "cobertura", "periodos"]}
    comp.update({"unidad": True, "minimo": True})
    return {"preguntas": [{
        "id": "B4", "pregunta": "p", "decision": "d", "planteamiento": "x §1", "funcion": "otra",
        "poblacion": {"regla": "r", "periodo": "p", "filas": 3, "unidad": "modelo", "entidades": 3},
        "medida": "m", "minimo_casos": "50.000", "que_cambia_la_decision": "q",
        "cifras": [{"nombre": "n", "valor": 1, "poblacion": "p", "filas": 3, "periodo": "p",
                    "segunda_via": 1, "coinciden": True}],
        "referencia": {"que_es": "total", "valor": 1, "filas": 3},
        "comprobaciones": comp, "motivos_null": {k: "no toca" for k, v in comp.items() if v is None}}]}


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 2 · el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
# Modelo: (tipo, capacidad en TB, precio, origen del precio, discos cada día, edad fija)
MODELOS = {
    "M8A": ("datos", 8.0, 200.0, "curva", 1000, 2),
    "M8B": ("datos", 8.0, 160.0, "curva", 100, 2),
    "M12": ("datos", 12.0, 240.0, "inferido", 2000, 1),
    "M6X": ("datos", 6.0, None, None, 20, 2),
    "BOOT": ("arranque", 0.2, None, None, 50, 0),
}
# Coste por GB del disco nuevo, el mismo en todas las capacidades
COSTE_GB = {2020: 0.02, 2021: 0.018, 2022: 0.016, 2023: 0.0132, 2024: 0.0115, 2025: 0.01}
# Ingresos del doc. 16 del caso pequeño, en miles de dólares
INGRESOS = {2023: 1000, 2024: 1200, 2025: 1500}
TRIMESTRES = [(2020 + q // 4, q % 4 + 1) for q in range(22)]
# Fecha de compra de cada modelo (encargo 19): M8A y M8B de 2019, M12 de 2021; los demás sin ella
COMPRA = {"M8A": dt.datetime(2019, 6, 1), "M8B": dt.datetime(2019, 6, 1), "M12": dt.datetime(2021, 3, 1)}


def inicio_q(ano, t):
    """Primer día del trimestre."""
    return dt.datetime(ano, 3 * t - 2, 1)


def dias_q(ano, t):
    """Días del trimestre."""
    return sum(calendar.monthrange(ano, mm)[1] for mm in range(3 * t - 2, 3 * t + 1))


def fallos_peq():
    """Los fallos del caso pequeño: (modelo, día, serie, primera aparición del disco)."""
    out = []
    for ano, t in TRIMESTRES:
        m1 = 3 * t - 2
        out.append(("M8A", dt.datetime(ano, m1, 10), f"A{ano}{t}a", dt.datetime(2020, 1, 1)))
        out.append(("M8A", dt.datetime(ano, m1 + 1, 20), f"A{ano}{t}b", dt.datetime(2020, 1, 1)))
        # El fallo de M12 de 2023T2 es de un disco que aparece el 01/05/2023, después del primer día del trimestre
        pa_ = dt.datetime(2023, 5, 1) if (ano, t) == (2023, 2) else dt.datetime(2020, 1, 1)
        out.append(("M12", dt.datetime(ano, m1 + 2, 5), f"C{ano}{t}", pa_))
    out.append(("M8B", dt.datetime(2022, 5, 10), "B2022", dt.datetime(2020, 1, 1)))
    out.append(("BOOT", dt.datetime(2021, 3, 3), "BOOT1", dt.datetime(2020, 1, 1)))
    return out


def esquema(tabla, columnas):
    """Esquema con el tipo real de cada columna, leído del parquet del caso sin cargar sus datos."""
    s = pq.read_schema(PROCESADOS / f"{tabla}.parquet")
    return pa.schema([s.field(c) for c in columnas])


def escribir(raiz, tabla, filas, columnas):
    """Escribe una tabla del caso pequeño con los tipos del parquet real."""
    datos = {c: [f[c] for f in filas] for c in columnas}
    pq.write_table(pa.Table.from_pydict(datos, schema=esquema(tabla, columnas)),
                   raiz / "data" / "processed" / f"{tabla}.parquet")


def coste_fallo(modelo, ano):
    """Disco nuevo de la misma capacidad al coste por GB del año del fallo, más 37 dólares (reglas §6)."""
    return MODELOS[modelo][1] * 1000 * COSTE_GB[ano] + 37


def montar_caso(raiz, estropear=None):
    """Escribe el caso pequeño en `raiz`; `estropear` cambia una tabla para un caso que tiene que parar."""
    if raiz.exists():
        shutil.rmtree(raiz)
    for c in ["data/processed", "data/raw", "informes", "contexto-proyecto/sector/documentos"]:
        (raiz / c).mkdir(parents=True)
    (raiz / "data" / "raw" / "origen.csv").write_text("a\n1\n", encoding="utf-8")
    datos = [k for k, v in MODELOS.items() if v[0] == "datos"]
    fallos = fallos_peq()

    # Calendario y dimensiones
    dias, d = [], dt.datetime(2020, 1, 1)
    while d <= dt.datetime(2025, 6, 30):
        dias.append({"fecha": d, "ano": d.year, "trimestre": (d.month - 1) // 3 + 1})
        d += dt.timedelta(days=1)
    escribir(raiz, "calendario", dias, ["fecha", "ano", "trimestre"])
    # Encargo 19: la fecha de compra de cada modelo, de la que sale el año de compra del puesto de B4
    dm = [{"model": k, "capacidad_tb": v[1], "tipo_disco": v[0], "precio_usd": v[2], "origen_precio": v[3],
           "fecha_compra": COMPRA.get(k)} for k, v in MODELOS.items()]
    escribir(raiz, "dim_modelo", dm, ["model", "capacidad_tb", "tipo_disco", "precio_usd", "origen_precio",
                                      "fecha_compra"])
    dpg = [{"capacidad_tb": c, "ano": a, "coste_gb": g} for c in (6.0, 8.0, 12.0) for a, g in COSTE_GB.items()]
    escribir(raiz, "dim_precio_gb", dpg, ["capacidad_tb", "ano", "coste_gb"])

    # Recuento: una fila por día y modelo, con los fallos de ese día
    por_dia = {}
    for mo, dia, _, _ in fallos:
        por_dia[(mo, dia)] = por_dia.get((mo, dia), 0) + 1
    rec = [{"fecha": x["fecha"], "model": mo, "discos": MODELOS[mo][4], "fallos": por_dia.get((mo, x["fecha"]), 0)}
           for x in dias for mo in MODELOS]
    escribir(raiz, "recuento_diario_corregido", rec, ["fecha", "model", "discos", "fallos"])

    # modelo_trimestre: días, fallos y coste de los fallos por modelo de datos y trimestre
    mt = []
    for mo in datos:
        for ano, t in TRIMESTRES:
            fq = [f for f in fallos if f[0] == mo and (f[1].year, (f[1].month - 1) // 3 + 1) == (ano, t)]
            dias_ano = MODELOS[mo][4] * (181 if ano == 2025 else (366 if ano in (2020, 2024) else 365))
            garantia = mo == "M8A"
            mt.append({"model": mo, "ano": ano, "trimestre": t, "capacidad_tb": MODELOS[mo][1],
                       "precio_usd": MODELOS[mo][2], "origen_precio": MODELOS[mo][3],
                       "dias_disco": MODELOS[mo][4] * dias_q(ano, t), "fallos": len(fq),
                       "fallos_en_garantia": len(fq) if garantia else 0,
                       "coste_fallos_usd": len(fq) * coste_fallo(mo, ano),
                       "coste_fallos_garantia_usd": len(fq) * (37 if garantia else coste_fallo(mo, ano)),
                       "dias_disco_ano": dias_ano, "pasa_minimo_ano": dias_ano >= 50000})
    if estropear == "coste":
        mt[5]["coste_fallos_usd"] += 1.0
    escribir(raiz, "modelo_trimestre", mt, ["model", "ano", "trimestre", "capacidad_tb", "precio_usd", "origen_precio",
                                            "dias_disco", "fallos", "fallos_en_garantia", "coste_fallos_usd",
                                            "coste_fallos_garantia_usd", "dias_disco_ano", "pasa_minimo_ano"])

    # inicio_trimestre: los discos del primer día, con su edad fija
    it = [{"ano": a, "trimestre": t, "model": mo, "edad_anos_cumplidos": MODELOS[mo][5], "fecha": inicio_q(a, t),
           "capacidad_tb": MODELOS[mo][1], "discos": MODELOS[mo][4], "dias_trimestre": dias_q(a, t)}
          for a, t in TRIMESTRES for mo in datos]
    if estropear == "inicio_trimestre":
        it[-1]["discos"] += 1
    escribir(raiz, "inicio_trimestre", it, ["ano", "trimestre", "model", "edad_anos_cumplidos", "fecha", "capacidad_tb",
                                            "discos", "dias_trimestre"])

    # dias_por_tramo: una fila por modelo y mes, con su edad fija
    dpt = []
    for mo in datos:
        for a in range(2020, 2026):
            for mm in range(1, 13 if a < 2025 else 7):
                n = sum(1 for f in fallos if f[0] == mo and f[1].year == a and f[1].month == mm)
                dpt.append({"model": mo, "centro": "sin dato", "mes": dt.datetime(a, mm, 1),
                            "edad_anos_cumplidos": MODELOS[mo][5], "fotos": MODELOS[mo][4],
                            "dias_disco": float(MODELOS[mo][4] * calendar.monthrange(a, mm)[1]), "fallos": n,
                            "desaparecen_avisando": 0})
    escribir(raiz, "dias_por_tramo", dpt, ["model", "centro", "mes", "edad_anos_cumplidos", "fotos", "dias_disco",
                                           "fallos", "desaparecen_avisando"])

    # fallos_detalle, vida_discos, fotos y ventanas
    fd = [{"serial_number": s, "dia_fallo": dia, "model": mo, "capacidad_tb": MODELOS[mo][1],
           "tipo_disco": MODELOS[mo][0]} for mo, dia, s, _ in fallos]
    if estropear == "fallos_detalle":
        fd.append({"serial_number": "EXTRA", "dia_fallo": dt.datetime(2022, 2, 2), "model": "M12",
                   "capacidad_tb": 12.0, "tipo_disco": "datos"})
    escribir(raiz, "fallos_detalle", fd, ["serial_number", "dia_fallo", "model", "capacidad_tb", "tipo_disco"])
    vida, fotos, ventanas = [], [], []
    for mo, dia, s, p_ in fallos:
        if MODELOS[mo][0] != "datos":
            continue
        vida.append({"serial_number": s, "model": mo, "primera_aparicion": p_, "edad_entrada_anos": 3.0,
                     "evento": "fallo", "edad_fin_anos": 3.5})
        fotos.append({"fecha": p_, "serial_number": s, "model": mo})
        ventanas.append({"fecha": max(dia - dt.timedelta(days=30), p_), "serial_number": s, "model": mo})
    # 30 discos de M12 que entran nuevos: 25 fallan a medio año y 5 siguen hasta el año y medio
    for k in range(30):
        vida.append({"serial_number": f"V{k:02d}", "model": "M12", "primera_aparicion": dt.datetime(2020, 1, 1),
                     "edad_entrada_anos": 0.0, "evento": "fallo" if k < 25 else "sigue",
                     "edad_fin_anos": 0.5 if k < 25 else 1.5})
    escribir(raiz, "vida_discos", vida, ["serial_number", "model", "primera_aparicion", "edad_entrada_anos", "evento",
                                         "edad_fin_anos"])
    escribir(raiz, "fotos_mensuales_corregido", fotos, ["fecha", "serial_number", "model"])
    escribir(raiz, "ventanas_fallo_corregido", ventanas, ["fecha", "serial_number", "model"])

    # El doc. 16 con su tabla de ingresos
    (raiz / "contexto-proyecto/sector/documentos/16_backblaze_10k_2025_tablas_ingresos.txt").write_text(
        "[Ingresos por producto, años cerrados a 31 de diciembre, miles de $]\n"
        "                         | 2025    | 2024    | 2023\n"
        f"Total revenue            | {INGRESOS[2025]:,} | {INGRESOS[2024]:,} | {INGRESOS[2023]:,}\n",
        encoding="utf-8")

    # transformacion-datos.json con las huellas; los dos exploratorios y el JSON del encargo 13
    p = raiz / "data" / "processed"
    salidas = [{"ruta": f"data/processed/{t}.parquet", "sha256": sha256(p / f"{t}.parquet")}
               for t in ["dim_modelo", "dim_precio_gb", "modelo_trimestre", "inicio_trimestre", "dias_por_tramo",
                         "fallos_detalle", "vida_discos"]]
    entradas = [{"ruta": f"data/processed/{t}.parquet", "sha256": sha256(p / f"{t}.parquet")}
                for t in ["recuento_diario_corregido", "fotos_mensuales_corregido", "ventanas_fallo_corregido",
                          "calendario"]]
    if estropear == "huella":
        salidas[2]["sha256"] = "0" * 64
    (raiz / "informes" / "transformacion-datos.json").write_text(
        json.dumps({"salidas": salidas, "entradas": entradas}), encoding="utf-8")
    for n in ["analisis-exploratorio__modelo_trimestre", "analisis-exploratorio__dias_por_tramo",
              "indicadores__discos_modelos_edad"]:
        estado = "PARADO" if (estropear == "encargo13" and n == "indicadores__discos_modelos_edad") else "AVISO"
        contenido = {"resultado": {"estado": estado}}
        if n == "indicadores__discos_modelos_edad":
            contenido["preguntas"] = [{"id": "B2", "tablas": {"ranking": ranking_09(estropear)}}]
            # Encargo 19: el JSON nuevo del 09 trae φ en la comparación a igual edad; el de antes, no
            if estropear != "sin_phi":
                contenido["preguntas"][0]["tablas"]["a_igual_edad"] = {
                    "phi": {"phi": 1.5, "phi_bruto": 1.5, "celdas": 10, "gl": 8}}
        (raiz / "informes" / f"{n}.json").write_text(json.dumps(contenido), encoding="utf-8")


# Tasa a igual edad del JSON del 09 en el caso pequeño: la tasa bruta por este factor (encargo 17)
FACTOR_IGUAL_EDAD = {"M8A": 1.25, "M12": 0.8}


def ranking_09(estropear=None):
    """El ranking de B2 del JSON del 09 del caso pequeño, con su tasa a igual edad; `estropear` la quita o cambia días."""
    out = []
    for mo, x in esperado_b4().items():
        tasa = 100 * 365 * x["fallos"] / x["dias"]
        f = {"model": mo, "dias_disco": x["dias"], "fallos": x["fallos"], "tasa": tasa, "puesto": 1,
             "tasa_igual_edad": tasa * FACTOR_IGUAL_EDAD[mo]}
        if estropear == "sin_igual_edad":
            del f["tasa_igual_edad"]
        if estropear == "igual_edad_dias" and mo == "M12":
            f["dias_disco"] += 1
        out.append(f)
    return out


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


def esperado_b4():
    """El ranking del caso pequeño calculado aquí: M8A y M12 pasan el mínimo todos los años."""
    out = {}
    for mo in ("M8A", "M12"):
        cap, precio, n = MODELOS[mo][1], MODELOS[mo][2], MODELOS[mo][4]
        f = [x for x in fallos_peq() if x[0] == mo]
        dias = n * 2008
        coste_f = sum(coste_fallo(mo, x[1].year) for x in f)
        tb = dias * cap / 365
        out[mo] = {"dias": dias, "fallos": len(f), "amort": precio / cap / 6, "fallos_tb": coste_f / tb,
                   "coste": precio / cap / 6 + coste_f / tb}
    return out


def probar_caso_pequeno():
    """El script entero sobre el caso pequeño, y los casos que tienen que parar."""
    montar_caso(TMP)
    codigo, j = ejecutar(TMP)
    comprobar(codigo == 0 and j is not None and j["resultado"]["estado"] in ("OK", "AVISO"),
              f"caso pequeño: termina sin parar (código {codigo}, estado {j and j['resultado']['estado']})")
    if j is None or j["resultado"]["estado"] not in ("OK", "AVISO"):
        if j is not None:
            print(json.dumps(j["resultado"], ensure_ascii=False)[:3000])
        return
    textos = [(TMP / n).read_text(encoding="utf-8").lower() for n in (SALIDA, SALIDA_MD) if (TMP / n).exists()]
    comprobar(len(textos) == 2 and not any(VETADA in t for t in textos),
              "caso pequeño: deja el JSON y el MD, sin la palabra vetada")
    comprobar(all(v is True for v in j["validaciones"].values()), "caso pequeño: las nueve validaciones en verde")
    comprobar(all(s["coinciden"] is True for s in j["segundas_vias"]), "caso pequeño: todas las segundas vías coinciden")
    b4, b9 = pregunta(j, "B4")["tablas"], pregunta(j, "B9")["tablas"]

    # B4: ranking de dos modelos, con el coste calculado aquí
    esp = esperado_b4()
    rk = {f["model"]: f for f in b4["ranking"]}
    comprobar(set(rk) == {"M8A", "M12"} and b4["celdas_que_pasan"] == 12 and b4["celdas_total"] == 24,
              "caso pequeño: 12 de 24 celdas pasan, de 2 modelos")
    comprobar(all(rk[mo]["dias_disco"] == esp[mo]["dias"] and rk[mo]["fallos"] == esp[mo]["fallos"]
                  and cerca(rk[mo]["coste_tb_ano"], esp[mo]["coste"], 1e-9)
                  and cerca(rk[mo]["amortizacion_tb_ano"], esp[mo]["amort"]) for mo in rk),
              "caso pequeño: días, fallos, amortización y coste por TB y año de cada modelo")
    orden = sorted(esp, key=lambda mo: esp[mo]["coste"])
    comprobar([f["model"] for f in b4["ranking"]] == orden, "caso pequeño: ordenado de menor a mayor coste")
    a8 = rk["M8A"]
    comprobar(cerca(a8["coste_tb_ano_garantia"], esp["M8A"]["amort"] + 44 * 37 / (esp["M8A"]["dias"] * 8 / 365)),
              "caso pequeño: coste con garantía (todos los fallos de M8A dentro)")
    comprobar(a8["coste_desde"] < a8["coste_tb_ano"] < a8["coste_hasta"]
              and cerca(a8["coste_hasta"] - a8["amortizacion_tb_ano"],
                        a8["fallos_tb_ano"] * a8["hasta"] / a8["tasa"]),
              "caso pequeño: intervalo del coste con el de la tasa en la parte de los fallos")
    comprobar(cerca(a8["discos_medios"], 1000.0), "caso pequeño: discos medios = días / 2.008")
    sp = b4["sin_precio"]
    comprobar(sp["modelos"] == 1 and sp["dias_disco"] == 20 * 2008 and sp["celdas_que_pasan"] == 0,
              "caso pequeño: el modelo sin precio, aparte")
    # Vida real: M12 cruza 0,5 en el año 0 (25 fallos en 17,5 años de exposición)
    vr = {f["model"]: f for f in b4["vida_real"]["modelos"]}
    comprobar(cerca(vr["M12"]["vida_real_anos"], math.log(2) / (25 / 17.5), 1e-9)
              and vr["M8A"]["vida_real_anos"] is None and b4["vida_real"]["con_algun_ano_con_base"] == 1,
              "caso pequeño: vida real de M12 a mano; M8A sin base")
    # Mejor modelo: en 8 TB, M8A frente a M8A + M8B; la parte del precio es la de M8B, más barato
    c8 = next(c for c in b4["mejor_modelo"]["celdas"] if c["ano"] == 2022 and c["capacidad_tb"] == 8.0)
    tb_b = 100 * 365 * 8 / 365
    comprobar(c8["mejor"] == "M8A" and cerca(c8["parte_precio"], tb_b * (160 / 8 / 6 - 200 / 8 / 6))
              and cerca(c8["parte_precio"] + c8["parte_fallos"], c8["diferencia"]),
              "caso pequeño: mejor modelo de 8 TB en 2022 y sus dos partes")
    comprobar(len(b4["mejor_modelo"]["celdas"]) == 12 and next(
        x for x in b4["mejor_modelo"]["por_ano"] if x["ano"] == 2025)["parcial"] is True,
        "caso pequeño: 12 celdas de año y capacidad; 2025 parcial")
    ing = {x["ano"]: x for x in b4["ingreso_por_tb"]}
    tb23 = (1000 * 8 + 100 * 8 + 2000 * 12 + 20 * 6)
    comprobar(cerca(ing[2023]["capacidad_media_tb"], tb23) and cerca(ing[2023]["ingreso_por_tb"], 1e6 / tb23)
              and 2025 not in ing, "caso pequeño: ingreso por TB de 2023; 2025 no se calcula")

    # Encargo 17: los dos tienen 20 fallos o más y llevan puesto; coste a igual edad rehecho con la fórmula del encargo
    comprobar(all(f.get("puesto") is not None for f in b4["ranking"])
              and b4["resumen_ranking"].get("con_puesto") == 2 and b4["resumen_ranking"].get("sin_puesto") == 0,
              "encargo 17, caso pequeño: M8A (44 fallos) y M12 (22) con puesto; ninguno sin él")
    cie = {}
    for mo, x in esp.items():
        tb = x["dias"] * MODELOS[mo][1] / 365
        tasa_ie = 100 * 365 * x["fallos"] / x["dias"] * FACTOR_IGUAL_EDAD[mo]
        cie[mo] = x["amort"] + tasa_ie / 100 * (x["fallos_tb"] * tb / x["fallos"]) * x["dias"] / 365 / tb
    comprobar(all(cerca(rk[mo].get("coste_tb_ano_igual_edad"), cie[mo]) for mo in cie),
              "encargo 17, caso pequeño: coste a igual edad de cada modelo, rehecho con la fórmula del encargo")
    ce = b4.get("coste_igual_edad", {})
    comprobar(ce.get("modelos") == 2 and cerca(ce.get("spearman"), 1.0) and ce.get("mayor_salto") == 0,
              "encargo 17, caso pequeño: los dos costes ordenan igual (Spearman 1, salto 0)")
    # Sensibilidad: solo M12 tiene el precio inferido; el orden, rehecho aquí en bucle
    sp_ = {x["factor"]: x for x in b4.get("sensibilidad_precio", [])}
    ok_s = set(sp_) == {0.8, 1.2}
    for fac in (0.8, 1.2):
        costes = {mo: (MODELOS[mo][2] * (fac if MODELOS[mo][3] == "inferido" else 1)) / MODELOS[mo][1] / 6
                  + esp[mo]["fallos_tb"] for mo in esp}
        primero = min(costes, key=lambda mo: (costes[mo], mo))
        ok_s = ok_s and sp_.get(fac, {}).get("siguen") == 2 and sp_.get(fac, {}).get("primero") == primero
    comprobar(ok_s, "encargo 17, caso pequeño: precio inferido × 0,8 y × 1,2, siguen 2 de 2 y el primero rehecho aquí")
    # Encargo 19: M8A (8 TB, 2019) y M12 (12 TB, 2021) en grupos distintos, puesto 1 cada uno; el global, al lado
    esp19 = puestos_a_mano(b4["ranking"])
    comprobar(esp19 == {"M8A": 1, "M12": 1} and all(rk[mo].get("puesto") == esp19[mo] for mo in esp19)
              and rk["M8A"].get("ano_compra") == 2019 and rk["M12"].get("ano_compra") == 2021
              and sorted(rk[mo].get("puesto_global") for mo in rk) == [1, 2],
              "encargo 19, caso pequeño: puesto dentro de capacidad y año de compra, rehecho aquí; el global al lado")
    rg = b4.get("resumen_ranking", {}).get("grupos_compra", {})
    comprobar(rg.get("grupos_con_puesto") == 2 and rg.get("grupos_con_dos_o_mas") == 0
              and pregunta(j, "B4").get("comprobaciones_extra", {}).get("puesto_dentro_del_grupo") is True,
              "encargo 19, caso pequeño: dos grupos con puesto, ninguno con dos; la comprobación en verde")

    # B9: 18 trimestres y 3 capacidades; 2021T1 a mano
    pares = b9["pares"]
    comprobar(len(pares) == 54 and len({p["trimestre"] for p in pares}) == 18, "caso pequeño: 54 pares, 18 trimestres")
    p8 = next(p for p in pares if p["trimestre"] == "2021T1" and p["capacidad_tb"] == 8.0)
    prev8 = 1000 * 90 * 8 / 366000 + 100 * 90 * 8 / 402600
    comprobar(cerca(p8["previsto"], prev8) and p8["real"] == 2 and p8["referencia"] == 2
              and cerca(p8["horas_tecnico"], 0.74 * prev8), "caso pequeño: 2021T1, 8 TB, previsto a mano")
    p6 = next(p for p in pares if p["trimestre"] == "2021T1" and p["capacidad_tb"] == 6.0)
    comprobar(cerca(p6["previsto"], 20 * 90 * 8 / 409920) and p6["real"] == 0, "caso pequeño: 6 TB, nivel edad")
    niv = next(x for x in b9["niveles"] if x["trimestre"] == "2021T1")
    comprobar(niv["modelo"] == 3000 and niv["capacidad"] == 100 and niv["edad"] == 20,
              "caso pequeño: discos por nivel de tasa en 2021T1")
    comprobar(sum(p["real"] for p in pares) == 18 * 3 + 1, "caso pequeño: 55 fallos reales")
    w = sum(abs(p["previsto"] - p["real"]) for p in pares) / sum(p["real"] for p in pares)
    comprobar(cerca(b9["error"]["cuenta"]["wape"], w), "caso pequeño: error ponderado de la cuenta")
    comprobar(b9["invisibles"]["fallos"] == 1, "caso pequeño: un fallo de un disco que aparece después del primer día")
    comprobar(len(b9["sensibilidad"]) == 4, "caso pequeño: cuatro variantes de sensibilidad")

    # Casos que tienen que parar
    for estropear, estado, motivo in [
            ("coste", "ERROR", "coste de los fallos"),
            ("inicio_trimestre", "ERROR", "discos el primer día"),
            ("fallos_detalle", "ERROR", "fallos reales por trimestre y capacidad"),
            ("huella", "ERROR", "huella"),
            ("encargo13", "PARADO", "indicadores__discos_modelos_edad"),
            ("sin_igual_edad", "PARADO", "tasa a igual edad"),
            ("sin_phi", "PARADO", "φ"),
            ("igual_edad_dias", "ERROR", "igual edad")]:
        montar_caso(TMP, estropear)
        codigo, j = ejecutar(TMP)
        comprobar(codigo != 0 and j is not None and j["resultado"]["estado"] == estado
                  and motivo in j["resultado"]["resumen"] and "preguntas" not in j,
                  f"caso pequeño estropeado en {estropear}: para con {estado} por «{motivo}», sin cifras en el JSON")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 3 · el JSON real, contra los controles del encargo y por otro camino
# ---------------------------------------------------------------------------------------------------------------
def probar_json_real():
    """Controles del encargo 14 y dos cifras rehechas con pyarrow."""
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
    b4, b9 = pregunta(j, "B4")["tablas"], pregunta(j, "B9")["tablas"]

    def rd(x, d):
        """Redondeo como lo escribe el encargo."""
        return round(x + 1e-12, d)

    # Celdas y lo que queda fuera
    comprobar(b4["celdas_que_pasan"] == 152 and b4["celdas_total"] == 299 and len(b4["ranking"]) == 32,
              "control: 152 de 299 celdas pasan, de 32 modelos")
    fu, sp = b4["fuera_del_ranking"], b4["sin_precio"]
    comprobar(fu["celdas"] == 147 and fu["dias_disco"] == 1282168 and fu["fallos"] == 101,
              "control: fuera, 147 celdas con 1.282.168 días y 101 fallos")
    comprobar(sp["modelos"] == 4 and sp["dias_disco"] == 18840 and sp["fallos"] == 0 and sp["celdas_que_pasan"] == 0,
              "control: sin precio, 4 modelos con 18.840 días y 0 fallos")
    # Ranking de coste
    rk = b4["ranking"]
    rkm = {f["model"]: f for f in rk}
    p0 = rk[0]
    comprobar(p0["model"] == "TOSHIBA MG10ACA20TE" and rd(p0["coste_tb_ano"], 4) == 1.8758
              and rd(p0["amortizacion_tb_ano"], 4) == 1.7919 and rd(p0["fallos_tb_ano"], 4) == 0.0839
              and rd(p0["coste_tb_ano_garantia"], 4) == 1.8045 and rd(p0["tasa"], 2) == 0.68,
              f"control: el más barato, TOSHIBA MG10ACA20TE, 1,8758 (da {p0['model']} {p0['coste_tb_ano']:.4f})")
    comprobar([f["model"] for f in rk[1:3]] == ["WDC WUH722222ALE6L4", "ST24000NM002H"]
              and rd(rk[1]["coste_tb_ano"], 4) == 1.9854 and rd(rk[2]["coste_tb_ano"], 4) == 1.9865,
              "control: después WDC WUH722222ALE6L4, 1,9854, y ST24000NM002H, 1,9865")
    # El más caro, entre los que tienen puesto: con CP-012 (encargo 17) los que no lo tienen van al final
    rkp = [f for f in rk if f.get("puesto") is not None]
    comprobar(rkp[-1]["model"] == "ST8000DM002" and rd(rkp[-1]["coste_tb_ano"], 4) == 6.0234
              and rkp[-2]["model"] == "ST4000DM000" and rd(rkp[-2]["coste_tb_ano"], 4) == 5.8469
              and rd(rkp[-2]["coste_tb_ano_garantia"], 4) == 5.8469,
              "control: el más caro ST8000DM002, 6,0234; antes ST4000DM000, 5,8469, igual con garantía")
    s138 = rkm.get("ST14000NM0138", {})
    comprobar(rd(s138.get("tasa", 0), 2) == 5.90 and rd(s138.get("coste_tb_ano", 0), 4) == 3.5818
              and rd(s138.get("coste_tb_ano_garantia", 0), 4) == 2.7893,
              "control: ST14000NM0138, tasa 5,90 %, coste 3,5818, con garantía 2,7893")
    rr = b4["resumen_ranking"]
    if "coste_igual_edad" not in b4:
        print("aviso  el JSON real es de antes del encargo 17: sus controles de B4 se prueban tras la ejecución real")
        comprobar(rd(rr["mediana_parte_fallos_pct"], 2) == 6.14 and rd(rr["spearman_coste_tasa"], 3) == 0.323
                  and rr["primeros_diez_inferidos"] == 8,
                  "control: mediana de la parte de los fallos 6,14 %; Spearman 0,323; 8 de los diez primeros inferidos")
    else:
        controles_encargo17(b4, rd)
    controles_encargo19(b4, rd)
    # Vida real
    vr = b4["vida_real"]
    comprobar(vr["bajan_de_05"] == 0 and vr["con_algun_ano_con_base"] == 19 and vr["modelos_datos"] == 61
              and vr["s_mas_baja"]["model"] == "ST14000NM0138" and rd(vr["s_mas_baja"]["s"], 4) == 0.7372
              and vr["s_mas_baja"]["edad"] == 5,
              "control: vida real, ninguno baja de 0,5; 19 de 61 con base; ST14000NM0138, 0,7372 a 5 años")
    # Mejor modelo por año
    pa_ = {x["ano"]: x for x in b4["mejor_modelo"]["por_ano"]}
    for ano, dif in [(2020, 1019887), (2021, 801451), (2022, 990544), (2023, 1446478), (2024, 2044860),
                     (2025, 691776)]:
        comprobar(round(pa_[ano]["diferencia"]) == dif, f"control: mejor modelo, diferencia {ano} = {dif} "
                                                         f"(da {pa_[ano]['diferencia']:.0f})")
    comprobar(round(pa_[2023]["parte_precio"]) == 936501 and round(pa_[2023]["parte_fallos"]) == 509977
              and round(pa_[2024]["parte_precio"]) == 1892334 and round(pa_[2024]["parte_fallos"]) == 152527,
              "control: partes de 2023 (936.501 y 509.977) y 2024 (1.892.334 y 152.527)")
    comprobar(round(pa_[2024]["coste_real"]) == 11107178 and len(b4["mejor_modelo"]["celdas"]) == 46,
              "control: coste real de 2024, 11.107.178; 46 celdas de año y capacidad")
    # Ingreso por TB
    ing = {x["ano"]: x for x in b4["ingreso_por_tb"]}
    comprobar(rd(ing[2023]["ingreso_por_tb"], 2) == 34.05 and round(ing[2023]["capacidad_media_tb"]) == 2995811
              and rd(ing[2024]["ingreso_por_tb"], 2) == 32.66 and round(ing[2024]["capacidad_media_tb"]) == 3907527,
              "control: ingreso por TB, 34,05 (2.995.811 TB) y 32,66 (3.907.527 TB)")
    comprobar(rd(ing[2023]["coste_tb_ano_todos"], 3) == 3.097 and rd(ing[2023]["coste_tb_ano_todos_garantia"], 3) == 2.940
              and rd(ing[2024]["coste_tb_ano_todos"], 3) == 2.836
              and rd(ing[2024]["coste_tb_ano_todos_garantia"], 3) == 2.701,
              "control: coste por TB y año de todos los discos, 3,097 (2,940) y 2,836 (2,701)")
    # Previsión
    pares = b9["pares"]
    comprobar(len(pares) == 157 and len({p["trimestre"] for p in pares}) == 18, "control: 18 trimestres y 157 pares")
    comprobar(sum(p["real"] for p in pares) == 15689 and rd(sum(p["previsto"] for p in pares), 1) == 16484.0,
              "control: 15.689 reales y 16.484,0 previstos")
    e = b9["error"]
    comprobar(rd(e["cuenta"]["wape"], 4) == 0.2670 and rd(e["referencia"]["wape"], 4) == 0.2504
              and rd(e["cuenta"]["sesgo"], 4) == 0.0507 and rd(e["referencia"]["sesgo"], 4) == -0.0439
              and e["gana_la_cuenta"] is False,
              "control: error ponderado 0,2670 frente a 0,2504; sesgo +0,0507 frente a −0,0439; la cuenta no gana")
    pt = {x["trimestre"]: x for x in b9["serie_lineas"]}
    for q, pv, re_, rf in [("2021T1", 418.4, 350, 372), ("2023T2", 977.0, 1341, 892), ("2025T2", 1340.4, 1061, 1067)]:
        comprobar(rd(pt[q]["previsto"], 1) == pv and pt[q]["real"] == re_ and pt[q]["referencia"] == rf,
                  f"control: {q}, previsto {pv}, real {re_}, referencia {rf}")
    pcap = {x["capacidad_tb"]: x for x in b9["por_capacidad"]}
    comprobar(rd(pcap[12.0]["previsto"], 1) == 5307.4 and pcap[12.0]["real"] == 5239
              and rd(pcap[14.0]["previsto"], 1) == 3796.6 and pcap[14.0]["real"] == 3000,
              "control: 12 TB, 5.307,4 y 5.239; 14 TB, 3.796,6 y 3.000")
    sens = {x["variante"]: x for x in b9["sensibilidad"]}
    comprobar([rd(x["wape"], 4) for x in b9["sensibilidad"]] == [0.2528, 0.3264, 0.3313, 0.2774]
              and not any(x["gana"] for x in sens.values()),
              "control: sensibilidad 0,2528; 0,3264; 0,3313; 0,2774; ninguna gana")
    inv = b9["invisibles"]
    comprobar(inv["fallos"] == 413 and inv["de"] == 15689 and rd(inv["pct"], 2) == 2.63,
              "control: 413 de 15.689 fallos de discos que aparecen después del primer día (2,63 %)")

    # Otro camino, con pyarrow y sin pandas
    dm = pq.read_table(PROCESADOS / "dim_modelo.parquet", columns=["model", "tipo_disco"]).to_pylist()
    datos = sorted({f["model"] for f in dm if f["tipo_disco"] == "datos"})
    rec = pq.read_table(PROCESADOS / "recuento_diario_corregido.parquet", columns=["fecha", "model", "fallos"])
    rec = rec.filter(pc.is_in(rec["model"], value_set=pa.array(datos)))
    tipo = rec.schema.field("fecha").type
    desde = pc.greater_equal(rec["fecha"], pa.scalar(dt.datetime(2021, 1, 1), type=tipo))
    comprobar(pc.sum(rec.filter(desde)["fallos"]).as_py() == sum(p["real"] for p in pares),
              "otra vía (pyarrow, recuento): fallos de 2021 a junio de 2025 = los reales de la previsión")
    it = pq.read_table(PROCESADOS / "inicio_trimestre.parquet", columns=["ano", "trimestre", "discos"])
    trims = {(a, t) for a, t in zip(it["ano"].to_pylist(), it["trimestre"].to_pylist())}
    comprobar(it.num_rows == 3117 and len(trims) == 22 and pc.sum(it["discos"]).as_py() == 4805590,
              "control: inicio_trimestre, 3.117 filas, 22 trimestres y 4.805.590 discos")


def controles_encargo17(b4, rd):
    """Los CONTROLES de B4 del encargo 17 (prompts/17_…), escritos como los da el encargo."""
    rk, rr = b4["ranking"], b4["resumen_ranking"]
    sin = sorted(f["model"] for f in rk if f.get("puesto") is None)
    comprobar(rr["con_puesto"] == 27 and sin == ["ST12000NM000J", "ST14000NM000J", "ST16000NM002J", "ST6000DX000",
                                                 "ST8000NM000A"],
              f"control 17: 27 modelos con puesto y 5 sin él (da {rr['con_puesto']} y {sin})")
    diez = [("TOSHIBA MG10ACA20TE", 1.8758), ("WDC WUH722222ALE6L4", 1.9854), ("ST24000NM002H", 1.9865),
            ("WDC WUH721816ALE6L4", 2.3437), ("TOSHIBA MG08ACA16TA", 2.3881), ("ST16000NM001G", 2.6050),
            ("WDC WUH721414ALE6L4", 2.6526), ("WDC WUH721816ALE6L0", 2.7186), ("TOSHIBA MG07ACA14TEY", 2.7482),
            ("ST12000NM001G", 2.7922)]
    da = [(f["model"], rd(f["coste_tb_ano"], 4)) for f in rk[:10]]
    comprobar(da == diez, f"control 17: los diez primeros con su coste (da {da})")
    comprobar(rr["primeros_diez_inferidos"] == 5 and rd(rr["spearman_coste_tasa"], 4) == 0.4951
              and rd(rr["mediana_parte_fallos_pct"], 2) == 6.44,
              f"control 17: 5 inferidos entre los diez; Spearman 0,4951; mediana 6,44 % (da "
              f"{rr['primeros_diez_inferidos']}, {rr['spearman_coste_tasa']:.4f}, {rr['mediana_parte_fallos_pct']:.2f})")
    ce = b4["coste_igual_edad"]
    # Desde el encargo 19 la tasa a igual edad del 09 es la de cada edad y trimestre: este control del 17 ya no aplica
    if "grupos_compra" in rr:
        print("aviso  control 17 del coste a igual edad (Spearman 0,9974, salto 2): no aplica con la tasa del encargo 19")
    else:
        comprobar(ce["modelos"] == 32 and rd(ce["spearman"], 4) == 0.9974 and ce["mayor_salto"] == 2,
                  f"control 17: coste a igual edad con los 32, Spearman 0,9974 y mayor salto 2 (da {ce['modelos']}, "
                  f"{ce['spearman']:.4f}, {ce['mayor_salto']})")
    sp = {x["factor"]: x for x in b4["sensibilidad_precio"]}
    comprobar(sp[0.8]["siguen"] == 10 and sp[1.2]["siguen"] == 8 and sp[0.8]["de"] == 10
              and sp[0.8]["primero"] == sp[1.2]["primero"] == "TOSHIBA MG10ACA20TE",
              f"control 17: precio inferido × 0,8 siguen 10 y × 1,2 siguen 8; el primero, TOSHIBA MG10ACA20TE (da "
              f"{sp[0.8]['siguen']}, {sp[1.2]['siguen']}, {sp[0.8]['primero']}, {sp[1.2]['primero']})")


def controles_encargo19(b4, rd):
    """Los CONTROLES de B4 del encargo 19 (prompts/19_…), escritos como los da el encargo; con un JSON de antes, aviso."""
    rg = b4["resumen_ranking"].get("grupos_compra")
    if rg is None:
        print("aviso  el JSON real es de antes del encargo 19: sus controles de B4 se prueban tras la ejecución real")
        return
    comprobar(rg["grupos_con_puesto"] == 19 and rg["grupos_con_dos_o_mas"] == 7,
              f"control 19: 19 grupos de capacidad y año de compra con puesto, 7 con dos o más (da "
              f"{rg['grupos_con_puesto']} y {rg['grupos_con_dos_o_mas']})")
    grupos = {(g["capacidad_tb"], g["ano_compra"]): [(x["model"], rd(x["coste_tb_ano"], 4), x["puesto"])
                                                     for x in g["modelos"]] for g in rg["grupos"]}
    for clave, esperado in [
            ((4.0, 2016), [("HGST HMS5C4040BLE640", 4.0303, 1), ("HGST HMS5C4040ALE640", 4.3286, 2)]),
            ((12.0, 2019), [("HGST HUH721212ALE600", 3.0510, 1), ("HGST HUH721212ALN604", 3.6937, 2)]),
            ((12.0, 2021), [("ST12000NM001G", 2.7922, 1), ("HGST HUH721212ALE604", 2.8399, 2)]),
            ((14.0, 2020), [("TOSHIBA MG07ACA14TA", 2.7967, 1), ("ST14000NM0138", 3.5818, 2)]),
            ((14.0, 2021), [("WDC WUH721414ALE6L4", 2.6526, 1), ("ST14000NM001G", 2.7931, 2)]),
            ((16.0, 2021), [("WDC WUH721816ALE6L0", 2.7186, 1), ("TOSHIBA MG08ACA16TEY", 2.8029, 2),
                            ("TOSHIBA MG08ACA16TE", 2.8279, 3)]),
            ((16.0, 2023), [("WDC WUH721816ALE6L4", 2.3437, 1), ("TOSHIBA MG08ACA16TA", 2.3881, 2)])]:
        comprobar(grupos.get(clave) == esperado,
                  f"control 19: {clave[0]:.0f} TB de {clave[1]}, {esperado} (da {grupos.get(clave)})")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        modulo = cargar_modulo()
        if modulo is not None:
            probar_piezas(modulo)
            probar_caso_pequeno()
        probar_json_real()
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
