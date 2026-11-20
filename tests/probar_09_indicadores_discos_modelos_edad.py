"""Prueba de scripts/09_indicadores_discos_modelos_edad.py.

Parte 1, las piezas sueltas. Carga el script como módulo (su trabajo está dentro de `if __name__ == "__main__":`, así
que cargarlo no lo ejecuta) y prueba cada función con datos pequeños escritos aquí:
  - el intervalo exacto de Poisson, contra tres valores de la tabla de Garwood y contra scipy.stats.gamma, que es otra
    implementación del mismo intervalo (error 30);
  - la tabla de vida y la supervivencia, contra una cuenta hecha a mano; el corte de la curva por el mínimo de fallos;
  - «sube» frente al año anterior: sube, no se distingue y sin conclusión por pocos fallos;
  - cada comprobación con un caso que da verde y otro que tiene que dar rojo (error 24);
  - cada una de las nueve validaciones con un caso que tiene que dar rojo;
  - la búsqueda de resultados escritos a mano, que encuentra un «True» puesto en una comprobación y una cifra larga.
Parte 2, el script entero sobre un caso pequeño. Monta en tests/tmp_indicadores_discos/ las tablas que lee el script con
el tipo de cada columna tomado del parquet real (pyarrow.parquet.read_schema, sin cargar datos), su
informes/transformacion-datos.json con las huellas, los cuatro exploratorios y un data/raw/. Ejecuta el script con -W
error y comprueba las cifras contra las que se saben del caso pequeño. Después, cinco casos que tienen que parar:
  - modelo_trimestre con un fallo de más: la segunda vía de días y fallos por modelo y año no coincide, ERROR;
  - vida_discos con una primera aparición cambiada: la de las altas no coincide, ERROR;
  - inicio_trimestre con un disco de más: la de los discos del primer día del trimestre no coincide, ERROR;
  - vida_discos con fallos a edad cero: la supervivencia se aleja más de 0,5 puntos de la de dias_por_tramo, ERROR;
  - la huella de una tabla distinta de la de transformacion-datos.json, ERROR;
  - un exploratorio en PARADO: el script no calcula, PARADO.
Parte 3, el JSON real, si existe: las cifras de control de la petición (prompts/13_…, «CONTROLES»), escritas como las da
la petición, y dos cifras rehechas por otro camino, con pyarrow y sin pandas:
  - días de disco y fallos de los discos de datos desde recuento_diario_corregido, frente al JSON (que los toma de
    modelo_trimestre);
  - discos del 01/04/2025 desde recuento_diario_corregido, frente al JSON (que los toma de inicio_trimestre).

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
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
SCRIPT = CASO / "scripts" / "09_indicadores_discos_modelos_edad.py"
TMP = CASO / "tests" / "tmp_indicadores_discos"
SALIDA = "informes/indicadores__discos_modelos_edad.json"
PROCESADOS = CASO / "data" / "processed"
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
    spec = importlib.util.spec_from_file_location("indicadores_09", SCRIPT)
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
    from scipy import stats

    # 2.1 Intervalo exacto de Poisson: tabla de Garwood (fallos 0, 1 y 10) y la misma cuenta con la gamma
    dias = 36500  # con 36.500 días, la tasa en % es el recuento
    t, lo, hi = m.intervalo_poisson(0, dias)
    comprobar(t == 0 and lo == 0 and cerca(hi, 3.689, 1e-3), "Poisson con 0 fallos: 0 a 3,689")
    t, lo, hi = m.intervalo_poisson(1, dias)
    comprobar(cerca(lo, 0.0253, 1e-2) and cerca(hi, 5.572, 1e-3), "Poisson con 1 fallo: 0,0253 a 5,572")
    t, lo, hi = m.intervalo_poisson(10, dias)
    comprobar(cerca(lo, 4.795, 1e-3) and cerca(hi, 18.39, 1e-3), "Poisson con 10 fallos: 4,795 a 18,39")
    t, lo, hi = m.intervalo_poisson(193, 21590966)
    g_lo = stats.gamma.ppf(0.025, 193) * 100 * 365 / 21590966
    g_hi = stats.gamma.ppf(0.975, 194) * 100 * 365 / 21590966
    comprobar(cerca(lo, g_lo, 1e-9) and cerca(hi, g_hi, 1e-9), "Poisson con chi2 igual que con la gamma (otra vía)")

    # 2.2 Tabla de vida a mano: tres discos; uno de 0 a 2 años, uno de 0,5 a 1,5 que falla, uno de 1 a 3
    e0 = [0.0, 0.5, 1.0]
    e1 = [2.0, 1.5, 3.0]
    ev = [False, True, False]
    tv = m.tabla_de_vida(e0, e1, ev, edades=range(3))
    comprobar(cerca(tv[0]["exposicion_anos"], 1.5) and cerca(tv[1]["exposicion_anos"], 2.5)
              and cerca(tv[2]["exposicion_anos"], 1.0), "tabla de vida: exposición 1,5; 2,5; 1,0")
    comprobar(tv[1]["eventos"] == 1 and tv[0]["eventos"] == 0, "tabla de vida: el fallo cae en el año 1")
    comprobar(cerca(tv[1]["tasa"], 1 / 2.5), "tabla de vida: tasa del año 1 = 1 / 2,5")
    s = m.supervivencia([0.0, 0.4, 0.0])
    comprobar(cerca(s[0], 1.0) and cerca(s[1], 1.0) and cerca(s[2], math.exp(-0.4)), "S(k) = exp(−suma de tasas)")
    # Disco con la edad final por debajo de la de entrada: no aporta exposición
    tv2 = m.tabla_de_vida([2.0], [1.5], [False], edades=range(3))
    comprobar(all(f["exposicion_anos"] == 0 for f in tv2), "edad final menor que la de entrada: exposición 0")

    # 2.3 Corte de la curva: el año 1 tiene 5 fallos, menos de 20; S(0) y S(1) valen, S(2) en adelante no
    curva, motivo = m.cortar_curva([1.0, 0.99, 0.98, 0.97], [30, 5, 40], 20)
    comprobar(curva[:2] == [1.0, 0.99] and curva[2] is None and curva[3] is None and motivo,
              "la curva se corta antes del primer año con menos de 20 fallos")
    curva, motivo = m.cortar_curva([1.0, 0.99, 0.98], [30, 40], 20)
    comprobar(curva == [1.0, 0.99, 0.98] and motivo is None, "sin años por debajo, la curva entera")

    # 2.4 «Sube» frente al año anterior: los intervalos no se solapan; con menos de 20 fallos, sin conclusión
    filas = [{"edad": 0, "fallos": 100, "dias_disco": 3650000.0},
             {"edad": 1, "fallos": 300, "dias_disco": 3650000.0},
             {"edad": 2, "fallos": 310, "dias_disco": 3650000.0},
             {"edad": 3, "fallos": 10, "dias_disco": 36500.0}]
    out = m.frente_al_anterior(filas, 20)
    comprobar(out[0]["sube"] is None and out[1]["sube"] is True and out[2]["sube"] is False
              and out[3]["sube"] is None and out[3]["sin_conclusion"] is True,
              "sube: null el primero, sí con intervalos separados, no si se solapan, null con < 20 fallos")

    # 2.5 Comprobaciones, cada una en verde y en rojo
    comprobar(m.comp_unidad(["a", "b", "c"]) is True and m.comp_unidad(["a", "a", "c"]) is False,
              "unidad: claves únicas sí; una repetida, rojo")
    comprobar(m.comp_empates([1.0, 1.0, 2.0], [1, 1, 3]) is True
              and m.comp_empates([1.0, 1.0, 2.0], [1, 2, 3]) is False,
              "empates: el mismo valor con el mismo puesto; con puestos distintos, rojo")
    comprobar(m.comp_minimo_ranking([60000, 50000], [True, True], 50000) is True
              and m.comp_minimo_ranking([60000, 49999], [True, True], 50000) is False
              and m.comp_minimo_ranking([60000, 70000], [True, False], 50000) is False,
              "mínimo del ranking: una celda por debajo o con la marca que no cuadra, rojo")
    ok_edad = [{"fallos": 30, "sube": True, "fallos_anterior": 25}, {"fallos": 10, "sube": None, "fallos_anterior": 30}]
    mal_edad = [{"fallos": 10, "sube": True, "fallos_anterior": 30}]
    comprobar(m.comp_minimo_edad(ok_edad, 20) is True and m.comp_minimo_edad(mal_edad, 20) is False,
              "mínimo por edad: una conclusión con menos de 20 fallos, rojo")
    comprobar(m.comp_minimo_edad([], 20, curvas=[([1.0, 0.9, None], [30, 5])]) is True
              and m.comp_minimo_edad([], 20, curvas=[([1.0, 0.9, 0.8], [30, 5])]) is False,
              "mínimo por edad: una S después de un año con menos de 20 fallos, rojo")
    comprobar(m.comp_referencia([100, 200], [1, 2], 300, 3) is True
              and m.comp_referencia([100, 200], [1, 2], 301, 3) is False,
              "referencia: con las mismas filas sí; con otros días, rojo")
    grupos = [{"desde": 0.1, "hasta": 0.3}, {"desde": 0.2, "hasta": 0.5}]
    comprobar(m.comp_azar(grupos, 0.1, 0.95) is True and m.comp_azar(grupos, 0.2, 0.95) is False
              and m.comp_azar([{"desde": None, "hasta": 0.3}], 0.05, 0.95) is False,
              "azar: los esperados son el 5 % de los grupos y todos con intervalo; si no, rojo")
    comprobar(m.comp_partes_total([[1, 2], [3, 4]], [3, 7]) is True
              and m.comp_partes_total([[1, 2], [3, 4]], [3, 8]) is False,
              "partes que suman el total: sí; una que no, rojo")
    comprobar(m.comp_cuadre_discos(100, 10, 20, 70, 100) is True and m.comp_cuadre_discos(100, 10, 20, 69, 100) is False,
              "altas = fallos + desaparecen + siguen = discos: sí; uno de menos, rojo")
    per_ok = [{"ano": 2024, "parcial": False}, {"ano": 2025, "parcial": True}]
    per_mal = [{"ano": 2024, "parcial": False}, {"ano": 2025, "parcial": False}]
    comprobar(m.comp_periodos(per_ok, "ano", {2025}) is True and m.comp_periodos(per_mal, "ano", {2025}) is False,
              "periodos: 2025 marcado parcial; sin la marca, rojo")
    comprobar(m.comp_cobertura(0.98) is True and m.comp_cobertura(1.2) is False and m.comp_cobertura(None) is False,
              "cobertura: entre 0 y 1; fuera o sin calcular, rojo")

    # 2.6 Validaciones: un resultado mínimo que pasa las nueve, y un rojo para cada una
    base = resultado_minimo()
    v = m.validar(base, "x = 1\n", {"a": "1"}, {"a": "1"}, json.loads(json.dumps(base)))
    comprobar(all(v[k] is True for k in v) and len(v) == 9, "las nueve validaciones en verde con un resultado bueno")
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
    v = m.validar(base, "x = 1\n", {"a": "1"}, {"a": "1"}, r2)
    comprobar(v["reproducible"] is False, "validación reproducible: rojo si la segunda cuenta da otra cifra")
    v = m.validar(base, 'c = {"unidad": True}\n', {"a": "1"}, {"a": "1"}, json.loads(json.dumps(base)))
    comprobar(v["sin_resultados_escritos"] is False, "validación sin_resultados_escritos: rojo con un True escrito")
    v = m.validar(base, "x = 1\n", {"a": "1"}, {"a": "2"}, json.loads(json.dumps(base)))
    comprobar(v["raw_intacto"] is False, "validación raw_intacto: rojo si cambia una huella de data/raw/")

    # 2.7 La búsqueda de resultados escritos encuentra un sí puesto y una cifra larga, y deja pasar el mínimo fijo
    comprobar(len(m.buscar_resultados_escritos('val["reproducible"] = True\n')) == 1,
              "búsqueda: encuentra una validación puesta a True")
    comprobar(len(m.buscar_resultados_escritos("total = 446108683\n")) == 1, "búsqueda: encuentra una cifra larga")
    comprobar(len(m.buscar_resultados_escritos("MINIMO = 50_000\n")) == 0, "búsqueda: el mínimo de las reglas pasa")
    texto = SCRIPT.read_text(encoding="utf-8")
    comprobar(m.buscar_resultados_escritos(texto) == [], "el script no lleva ningún resultado escrito")


def probar_igual_edad(m):
    """Petición 17: la razón a igual edad, cuestión 012, el veredicto por el intervalo y la estabilidad, con datos escritos aquí."""
    import pandas as pd
    from scipy import stats

    faltan = [f for f in ("razon_poisson", "celdas_que_pasan", "igual_edad", "igual_edad_bucle", "veredicto_razon",
                          "ordenar_ranking", "comp_puesto_minimo", "comp_veredicto_intervalo", "estabilidad")
              if not hasattr(m, f)]
    comprobar(not faltan, f"petición 17: el script tiene las funciones de la comparación a igual edad (faltan {faltan})")
    if faltan:
        return

    # Razón con su intervalo exacto de Poisson, contra la gamma (otra implementación)
    rz, lo, hi = m.razon_poisson(30, 20.0)
    comprobar(cerca(rz, 1.5) and cerca(lo, stats.gamma.ppf(0.025, 30) / 20) and cerca(hi, stats.gamma.ppf(0.975, 31) / 20),
              "igual edad: razón = observados / esperados, intervalo de Poisson igual que con la gamma")

    # Celdas que pasan: el año de calendario del mes con la marca de su modelo y año
    dpt = pd.DataFrame({"model": ["A", "A", "B"], "centro": ["x", "x", "x"],
                        "mes": pd.to_datetime(["2021-05-01", "2022-05-01", "2021-05-01"]).astype("datetime64[ms]"),
                        "edad_anos_cumplidos": [0, 1, 0], "dias_disco": [10.0, float("nan"), 5.0], "fallos": [1, 2, 0]})
    celdas = pd.DataFrame({"model": ["A", "A", "B"], "ano": [2021, 2022, 2021], "pasa": [True, True, False]})
    c = m.celdas_que_pasan(dpt, celdas)
    comprobar(len(c) == 2 and set(c["model"]) == {"A"} and float(c["dias"].sum()) == 10.0 and int(c["fallos"].sum()) == 3,
              "igual edad: solo las celdas cuyo modelo y año pasan; una fila sin días cuenta 0 días y sus fallos")

    # A mano: A, edad 0 con 1.000 días y 1 fallo, edad 1 con 1.000 y 4; B, edad 0 con 3.000 y 3, edad 1 con 1.000 y 1.
    # Tasa por día: edad 0, 4/4.000; edad 1, 5/2.000. Esperados: A 1 + 2,5 = 3,5; B 3 + 2,5 = 5,5. Todo en un mismo
    # trimestre (petición 19: la tasa es la de cada año de edad y trimestre; con uno solo, la cuenta de la petición 17)
    c = pd.DataFrame({"model": ["A", "A", "B", "B"], "edad_anos_cumplidos": [0, 1, 0, 1],
                      "dias": [1000.0, 1000.0, 3000.0, 1000.0], "fallos": [1, 4, 3, 1], "ano": [2021] * 4,
                      "trimestre": [20211] * 4})
    r = m.igual_edad(c, 2)
    a, b = r["modelos"]["A"], r["modelos"]["B"]
    todos = 36500 * 9 / 6000
    comprobar(cerca(a["esperados"], 3.5) and cerca(b["esperados"], 5.5) and a["observados"] == 5 and b["observados"] == 4,
              "igual edad: esperados por la tasa de cada año de edad, a mano")
    comprobar(cerca(a["razon"], 5 / 3.5) and cerca(b["razon"], 4 / 5.5) and cerca(r["tasa_todos"], todos)
              and cerca(a["tasa_igual_edad"], 5 / 3.5 * todos), "igual edad: razón y tasa a igual edad = razón × tasa de todas")
    comprobar(cerca(a["edad_media_anos"], 1.0) and cerca(b["edad_media_anos"], 0.75),
              "igual edad: edad media ponderada por días (años cumplidos + 0,5)")
    # Suma de esperados = suma de observados: es así por construcción, no es una segunda vía de la cifra
    comprobar(cerca(a["esperados"] + b["esperados"], a["observados"] + b["observados"]),
              "igual edad: los esperados suman los observados (por construcción; no es segunda vía)")
    bu = m.igual_edad_bucle(c["model"].tolist(), c["edad_anos_cumplidos"].tolist(), c["dias"].tolist(),
                            c["fallos"].tolist())
    comprobar(bu["A"][0] == 5 and cerca(bu["A"][1], 3.5) and cerca(bu["B"][1], 5.5),
              "igual edad en bucle: los mismos observados y esperados")

    # Veredicto a igual edad: del intervalo de la razón, y sin conclusión con menos de 20 fallos
    comprobar(m.veredicto_razon(1.1, 1.5, 25) == "por encima" and m.veredicto_razon(0.5, 0.9, 25) == "por debajo"
              and m.veredicto_razon(0.9, 2.1, 25) == "no se distingue" and m.veredicto_razon(1.1, 1.5, 19) == "sin conclusión",
              "veredicto a igual edad: por encima, por debajo, no se distingue y sin conclusión con 19 fallos")
    bien = [{"model": "X", "fallos": 25, "razon": 1.5, "razon_desde": 0.9, "razon_hasta": 2.1, "veredicto": "no se distingue"}]
    mal = [{"model": "X", "fallos": 25, "razon": 1.5, "razon_desde": 0.9, "razon_hasta": 2.1, "veredicto": "por encima"}]
    comprobar(m.comp_veredicto_intervalo(bien, 20) is True and m.comp_veredicto_intervalo(mal, 20) is False,
              "comprobación del veredicto: una razón 1,5 de 0,9 a 2,1 que dice «por encima», rojo")

    # cuestión 012: puesto por la razón entre los de 20 fallos o más; los demás, sin puesto y al final
    filas = [{"model": "P", "fallos": 30, "razon": 1.2}, {"model": "Q", "fallos": 19, "razon": 0.1},
             {"model": "R", "fallos": 40, "razon": 0.8}]
    orden = m.ordenar_ranking(filas, 20)
    comprobar([f["model"] for f in orden] == ["R", "P", "Q"] and [f["puesto"] for f in orden] == [1, 2, None],
              "cuestión 012: puesto por la razón; el de 19 fallos sin puesto, al final")
    comprobar(m.comp_puesto_minimo(orden, 20) is True
              and m.comp_puesto_minimo([{"model": "Q", "fallos": 19, "puesto": 3}], 20) is False,
              "comprobación de cuestión 012: un modelo con 19 fallos y puesto, rojo")

    # Estabilidad: A en 2021 y 2025, B solo en 2025 (parcial). Sin 2025, B se queda sin días: pasa a sin conclusión
    c = pd.DataFrame({"model": ["A", "A", "B"], "edad_anos_cumplidos": [0, 0, 0], "dias": [10000.0, 10000.0, 1000.0],
                      "fallos": [30, 30, 25], "ano": [2021, 2025, 2025], "trimestre": [20211, 20251, 20251]})
    base = m.igual_edad(c, 20)["modelos"]
    est = m.estabilidad(c, base, {2025}, 20)
    comprobar(len(est["retiradas"]) == 2 and est["sin_parciales"]["cambian"] >= 1
              and "B" in est["sin_parciales"]["modelos"], "estabilidad: una retirada por modelo; sin el año parcial, B cambia")


def phi_a_mano(filas):
    """φ con un bucle propio y sin pandas (segunda vía de la petición 19): filas (grupo, celda, observados, esperados).

    Se suman por grupo y celda; fuera las celdas sin esperados; los esperados de cada grupo se reescalan para que sumen
    sus observados; chi2 de Pearson entre grados de libertad (celdas − grupos); por debajo de 1, vale 1.
    """
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


def probar_peticion19(m):
    """Petición 19: φ, los intervalos con φ, la tasa de cada año de edad y trimestre y sus comprobaciones en rojo."""
    import pandas as pd
    from scipy import stats

    faltan = [f for f in ("phi_poisson", "comp_phi") if not hasattr(m, f)]
    comprobar(not faltan, f"petición 19: el script tiene φ y su comprobación (faltan {faltan})")
    if faltan:
        return

    # φ a mano: A con 10 y 0 fallos frente a 5 y 5 esperados (chi2 10); B con 5 y 5 frente a 5 y 5 (chi2 0); 4 celdas,
    # 2 grupos, 2 grados de libertad: φ = 5. Con el bucle de la prueba, lo mismo
    filas = [("A", 1, 10, 5.0), ("A", 2, 0, 5.0), ("B", 1, 5, 5.0), ("B", 2, 5, 5.0)]
    p = m.phi_poisson([f[0] for f in filas], [f[1] for f in filas], [f[2] for f in filas], [f[3] for f in filas])
    pm = phi_a_mano(filas)
    comprobar(cerca(p["phi"], 5.0) and p["celdas"] == 4 and p["gl"] == 2 and cerca(pm["phi"], 5.0),
              f"petición 19: φ = 5 a mano, con 4 celdas y 2 grados de libertad (da {p})")
    # Los esperados se reescalan por grupo: A con 12 y 8 esperados para 10 y 10 observados sale igual que con 10 y 10
    p2 = m.phi_poisson(["A", "A", "B", "B"], [1, 2, 1, 2], [10, 10, 4, 16], [12.0, 8.0, 10.0, 10.0])
    pm2 = phi_a_mano([("A", 1, 10, 12.0), ("A", 2, 10, 8.0), ("B", 1, 4, 10.0), ("B", 2, 16, 10.0)])
    comprobar(cerca(p2["phi"], pm2["phi"]) and cerca(p2["phi_bruto"], pm2["phi_bruto"]),
              "petición 19: φ con los esperados reescalados por grupo, igual que el bucle de la prueba")
    # φ por debajo de 1 vale 1: sin ninguna variación de más, chi2 0
    p3 = m.phi_poisson(["A", "A"], [1, 2], [5, 5], [5.0, 5.0])
    comprobar(p3["phi"] == 1.0 and cerca(p3["phi_bruto"], 0.0, 1e-12), "petición 19: φ bruto 0 se usa como 1")
    comprobar(m.comp_phi([{"phi": 0.8, "phi_bruto": 0.8}]) is False
              and m.comp_phi([{"phi": 1.0, "phi_bruto": 0.8}]) is True
              and m.comp_phi([{"phi": 5.0, "phi_bruto": 5.0}]) is True
              and m.comp_phi([{"phi": 4.0, "phi_bruto": 5.0}]) is False,
              "petición 19, comprobación: un φ de 0,8 usado sin subir a 1, rojo; uno que no es el medido, rojo")

    # El intervalo con φ: los observados y los esperados entre φ; la razón no cambia
    rz, lo, hi = m.razon_poisson(200, 200 / 1.2, phi=4.0)
    e4 = 200 / 1.2 / 4
    comprobar(cerca(rz, 1.2) and cerca(lo, stats.gamma.ppf(0.025, 50) / e4) and cerca(hi, stats.gamma.ppf(0.975, 51) / e4),
              "petición 19: razón con φ = 4, intervalo igual que con la gamma de 50 observados")
    rz1, lo1, _ = m.razon_poisson(200, 200 / 1.2)
    comprobar(lo1 > 1 and lo < 1, "petición 19: la razón 1,2 queda por encima sin φ y cruza 1 con φ = 4")
    fila = {"model": "X", "fallos": 200, "observados": 200, "esperados": 200 / 1.2, "razon": 1.2,
            "razon_desde": lo1, "razon_hasta": 1.4}
    comprobar(m.comp_veredicto_intervalo([dict(fila, veredicto="por encima")], 20, 4.0) is False
              and m.comp_veredicto_intervalo([dict(fila, veredicto="no se distingue")], 20, 4.0) is True
              and m.comp_veredicto_intervalo([dict(fila, veredicto="por encima")], 20, 1.0) is True,
              "petición 19, comprobación: razón 1,2 con φ = 4 que dice «por encima», rojo")
    t, lo, hi = m.intervalo_poisson(100, 36500, phi=4.0)
    comprobar(cerca(t, 100.0) and cerca(lo, stats.gamma.ppf(0.025, 25) * 4) and cerca(hi, stats.gamma.ppf(0.975, 26) * 4),
              "petición 19: tasa con φ = 4, la misma tasa con el intervalo de 25 fallos en un cuarto de los días")
    filas_e = [{"edad": 0, "fallos": 100, "dias_disco": 3650000.0}, {"edad": 1, "fallos": 300, "dias_disco": 3650000.0}]
    sube1 = m.frente_al_anterior(filas_e, 20)[1]["sube"]
    sube50 = m.frente_al_anterior(filas_e, 20, 50.0)[1]["sube"]
    comprobar(sube1 is True and sube50 is False, "petición 19: «sube» con φ = 50 deja de salir")

    # La tasa de cada año de edad y trimestre: A y B con la misma edad, en dos trimestres con tasas distintas.
    # Trimestre 1: A 1.000 días y 1 fallo, B 1.000 y 9 (tasa 10/2.000); trimestre 2: A 3.000 y 3, B 1.000 y 1
    # (4/4.000). Esperados: A 5 + 3 = 8; B 5 + 1 = 6. Con la tasa de solo la edad (14/6.000): A 9,33; B 4,67
    c = pd.DataFrame({"model": ["A", "B", "A", "B"], "edad_anos_cumplidos": [0, 0, 0, 0],
                      "dias": [1000.0, 1000.0, 3000.0, 1000.0], "fallos": [1, 9, 3, 1], "ano": [2021] * 4,
                      "trimestre": [20211, 20211, 20212, 20212]})
    r = m.igual_edad(c, 2)
    comprobar(cerca(r["modelos"]["A"]["esperados"], 8.0) and cerca(r["modelos"]["B"]["esperados"], 6.0)
              and r.get("celdas_edad_trimestre") == 2,
              "petición 19: esperados con la tasa de cada año de edad y trimestre, a mano")
    bu = m.igual_edad_bucle(c["model"].tolist(), c["edad_anos_cumplidos"].tolist(), c["dias"].tolist(),
                            c["fallos"].tolist(), c["trimestre"].tolist())
    comprobar(cerca(bu["A"][1], 8.0) and cerca(bu["B"][1], 6.0), "petición 19: la misma cuenta en bucle")
    # φ de B2: celdas modelo × trimestre con esperados A (5, 3) y B (5, 1), observados A (1, 3) y B (9, 1)
    pm = phi_a_mano([("A", 20211, 1, 5.0), ("A", 20212, 3, 3.0), ("B", 20211, 9, 5.0), ("B", 20212, 1, 1.0)])
    comprobar(cerca(r["phi"]["phi"], pm["phi"]) and r["phi"]["celdas"] == pm["celdas"] and r["phi"]["gl"] == pm["gl"],
              f"petición 19: φ de B2 igual que el bucle de la prueba (da {r['phi']}, prueba {pm})")
    rv = r["modelos"]["B"]
    eb = 6.0 / r["phi"]["phi"]
    comprobar(cerca(rv["razon"], 10 / 6) and cerca(rv["razon_desde"], stats.gamma.ppf(0.025, 10 / r["phi"]["phi"]) / eb),
              "petición 19: razón de B con su intervalo con φ, a mano")
    # φ de B3: celdas modelo × año de edad × trimestre con la tasa de su modelo y edad en todo el periodo
    dpt = pd.DataFrame({"model": ["A", "A", "B", "B"], "centro": ["x"] * 4, "edad_anos_cumplidos": [0, 0, 1, 1],
                        "mes": pd.to_datetime(["2021-01-01", "2021-04-01", "2021-01-01", "2021-04-01"]).astype("datetime64[ms]"),
                        "dias_disco": [1000.0, 1000.0, 2000.0, float("nan")], "fallos": [10, 0, 4, 2]})
    p_e = m.phi_edad(dpt)
    pm_e = phi_a_mano([(("A", 0), 1, 10, 5.0), (("A", 0), 2, 0, 5.0), (("B", 1), 1, 4, 6.0), (("B", 1), 2, 2, 0.0)])
    comprobar(cerca(p_e["phi"], pm_e["phi"]) and p_e["celdas"] == pm_e["celdas"] == 3 and p_e["gl"] == pm_e["gl"] == 1,
              f"petición 19: φ de B3 por modelo, edad y trimestre, igual que el bucle de la prueba (da {p_e})")


def resultado_minimo():
    """Un JSON pequeño con una pregunta completa, que pasa las nueve validaciones."""
    comp = {k: None for k in ["unidad", "minimo", "empates", "referencia", "azar_en_grupos", "pesos",
                              "hacia_adelante", "cobertura", "periodos"]}
    comp.update({"unidad": True, "minimo": True})
    motivos = {k: "no toca" for k, v in comp.items() if v is None}
    return {"preguntas": [{
        "id": "B1", "pregunta": "p", "decision": "d", "planteamiento": "x §1", "funcion": "otra",
        "poblacion": {"regla": "r", "periodo": "p", "filas": 3, "unidad": "disco", "entidades": 3},
        "medida": "m", "minimo_casos": "50.000", "que_cambia_la_decision": "q",
        "cifras": [{"nombre": "n", "valor": 1, "poblacion": "p", "filas": 3, "periodo": "p",
                    "segunda_via": 1, "coinciden": True}],
        "referencia": {"que_es": "total", "valor": 1, "filas": 3},
        "comprobaciones": comp, "motivos_null": motivos}]}


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 2 · el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
MESES = [dt.datetime(2020 + i // 12, i % 12 + 1, 1) for i in range(66)]
# Modelo: (fabricante, capacidad en TB, tipo, discos el día 1, edad del primer mes)
MODELOS = {
    "ST4000X": ("Seagate", 4.0, "datos", 10000, 0),
    "TOSHIBA T8": ("Toshiba", 8.0, "datos", 3000, 2),
    "WDC W12": ("WDC", 12.0, "datos", 5000, 4),
    "BOOT1": (None, 0.2, "arranque", 100, 0),
}
# Fallos: (modelo, índice del mes, cuántos, serie del disco o None). Todos a 5 años o más: la supervivencia a 1, 3 y 5
# años sale 1 por las dos vías, y la prueba se centra en que el script llegue al final y en sus cifras.
FALLOS_PEQ = [("ST4000X", 61, 1, None), ("ST4000X", 64, 2, None),
              ("TOSHIBA T8", 40, 1, None), ("TOSHIBA T8", 50, 2, None), ("TOSHIBA T8", 58, 1, None),
              ("WDC W12", 14, 1, "D21"), ("WDC W12", 30, 1, "D20"), ("WDC W12", 45, 2, None),
              ("WDC W12", 62, 1, "D29"), ("BOOT1", 20, 1, None)]


def edad(modelo, i):
    """Años de edad cumplidos del modelo en el mes i del caso pequeño."""
    return MODELOS[modelo][4] + i // 12


def centros(modelo, i):
    """Reparto de los discos del modelo por centro en el mes i: sin centro antes de julio de 2023."""
    n = MODELOS[modelo][3]
    if i < 42:
        return {"sin dato": n}
    if modelo == "ST4000X":
        return {"phx1": n - 1000, "sin dato": 1000}
    return {"sac0": n}


def esquema(tabla, columnas):
    """Esquema con el tipo real de cada columna, leído del parquet del caso sin cargar sus datos."""
    s = pq.read_schema(PROCESADOS / f"{tabla}.parquet")
    return pa.schema([s.field(c) for c in columnas])


def escribir(raiz, tabla, filas, columnas):
    """Escribe una tabla del caso pequeño con los tipos del parquet real."""
    datos = {c: [f[c] for f in filas] for c in columnas}
    pq.write_table(pa.Table.from_pydict(datos, schema=esquema(tabla, columnas)),
                   raiz / "data" / "processed" / f"{tabla}.parquet")


def poblacion():
    """Los 30 discos de vida_discos del caso pequeño, con sus fotos y sus ventanas."""
    vida, fotos, ventanas = [], [], []
    for k in range(30):
        s = f"D{k:02d}"
        modelo = "ST4000X" if k < 20 else "WDC W12"
        p = 0 if k < 10 else 3 if k < 15 else 27 if k < 20 else 0 if k < 25 else 63
        e0 = 4.0 if 20 <= k < 25 else 0.0
        ultima, evento, fallo, avisa = 65, "sigue", None, False
        # D05 desaparece avisando a los 5 años (no mueve la supervivencia a 1, 3 y 5); D06 desaparece sin avisar
        if k in (5, 6):
            ultima, evento = (61 if k == 5 else 30), "desaparece"
            avisa = k == 5
        if s == "D21":
            ultima, evento, fallo = 13, "fallo", 14
        if s == "D20":
            ultima, evento, fallo = 29, "fallo", 30
        if s == "D29":
            continue
        fin = MESES[fallo] if fallo is not None else MESES[ultima]
        e1 = e0 + ((fallo if fallo is not None else ultima) - p) / 12
        vida.append({"serial_number": s, "model": modelo, "primera_aparicion": MESES[p], "edad_entrada_anos": e0,
                     "ultima_foto": MESES[ultima], "primer_fallo": MESES[fallo] if fallo is not None else None,
                     "evento": evento, "fecha_fin": fin, "edad_fin_anos": e1, "avisa_ultima_foto": avisa,
                     "desaparece_avisando": evento == "desaparece" and avisa})
        fotos.append({"fecha": MESES[p], "serial_number": s, "model": modelo})
        if ultima != p:
            fotos.append({"fecha": MESES[ultima], "serial_number": s, "model": modelo})
        if fallo is not None:
            ventanas.append({"fecha": MESES[fallo] - dt.timedelta(days=30), "serial_number": s, "model": modelo})
    # D29 solo sale en la ventana de su fallo: primera aparición, el primer día de la ventana
    inicio = MESES[62] - dt.timedelta(days=30)
    vida.append({"serial_number": "D29", "model": "WDC W12", "primera_aparicion": inicio, "edad_entrada_anos": 5.2,
                 "ultima_foto": None, "primer_fallo": MESES[62], "evento": "fallo", "fecha_fin": MESES[62],
                 "edad_fin_anos": 5.28, "avisa_ultima_foto": None, "desaparece_avisando": False})
    ventanas.append({"fecha": inicio, "serial_number": "D29", "model": "WDC W12"})
    # Un disco de arranque en las fotos, que no entra en las altas
    fotos.append({"fecha": MESES[10], "serial_number": "B01", "model": "BOOT1"})
    return vida, fotos, ventanas


def fallos_por_mes(lista):
    """Fallos por modelo e índice de mes de una lista de fallos del caso pequeño."""
    fallos_mes = {}
    for modelo, i, n, _ in lista:
        fallos_mes[(modelo, i)] = fallos_mes.get((modelo, i), 0) + n
    return fallos_mes


def filas_dpt(fallos_mes):
    """dias_por_tramo del caso pequeño: una fila por modelo de datos y mes, con la edad del modelo ese mes."""
    dpt = []
    for modelo in [k for k, v in MODELOS.items() if v[2] == "datos"]:
        for i, mes in enumerate(MESES):
            n = MODELOS[modelo][3]
            dpt.append({"model": modelo, "centro": next(iter(centros(modelo, i))), "mes": mes,
                        "edad_anos_cumplidos": edad(modelo, i), "fotos": n, "dias_disco": float(n),
                        "fallos": fallos_mes.get((modelo, i), 0),
                        "desaparecen_avisando": 1 if (modelo == "ST4000X" and i == 61) else 0})
    return dpt


def igual_edad_a_mano(lista):
    """La razón a igual edad del caso pequeño con bucles de Python y sin pandas (otra cuenta que la del script).

    Celdas: las filas de dias_por_tramo cuyo modelo y año pasan los 50.000 días; tasa de cada año de edad con todas ellas;
    esperados = días × tasa de su edad; intervalo con la gamma, otra implementación que la chi2 del script.
    """
    from scipy import stats
    dias_ano = {}
    for modelo, v in MODELOS.items():
        if v[2] == "datos":
            for i in range(66):
                dias_ano[(modelo, MESES[i].year)] = dias_ano.get((modelo, MESES[i].year), 0) + v[3]
    celdas = [f for f in filas_dpt(fallos_por_mes(lista)) if dias_ano[(f["model"], f["mes"].year)] >= 50000]
    # Petición 19: la tasa es la de cada año de edad y trimestre de calendario, con todos los modelos juntos
    por_eq, por_meq = {}, {}
    for f in celdas:
        q = (f["mes"].year, (f["mes"].month - 1) // 3 + 1)
        k = (f["edad_anos_cumplidos"], q)
        d0, f0 = por_eq.get(k, (0.0, 0))
        por_eq[k] = (d0 + f["dias_disco"], f0 + f["fallos"])
        k2 = (f["model"], f["edad_anos_cumplidos"], q)
        d1, f1 = por_meq.get(k2, (0.0, 0))
        por_meq[k2] = (d1 + f["dias_disco"], f1 + f["fallos"])
    dias_t = sum(d for d, _ in por_eq.values())
    fallos_t = sum(f for _, f in por_eq.values())
    out, filas_phi = {}, []
    for (mo, e, q), (d, f) in por_meq.items():
        x = out.setdefault(mo, {"observados": 0, "esperados": 0.0, "dias": 0.0, "pond": 0.0})
        esp = d * por_eq[(e, q)][1] / por_eq[(e, q)][0]
        x["observados"] += f
        x["esperados"] += esp
        x["dias"] += d
        x["pond"] += (e + 0.5) * d
        filas_phi.append((mo, q, f, esp))
    phi = phi_a_mano(filas_phi)
    for x in out.values():
        o, s = x["observados"], x["esperados"]
        op, sp = o / phi["phi"], s / phi["phi"]
        x["razon"] = o / s
        x["desde"] = stats.gamma.ppf(0.025, op) / sp if o > 0 else 0.0
        x["hasta"] = stats.gamma.ppf(0.975, op + 1) / sp
        x["tasa_igual_edad"] = x["razon"] * 36500 * fallos_t / dias_t
        x["edad_media"] = x["pond"] / x["dias"]
        x["veredicto"] = ("sin conclusión" if o < 20 else "por encima" if x["desde"] > 1
                          else "por debajo" if x["hasta"] < 1 else "no se distingue")
    return out, dias_t, fallos_t, phi


# Fallos de más para que los dos modelos del ranking pasen de 20 fallos: ST4000X en 2025-01 (edad 5) y WDC W12 en
# 2022-03 (edad 6), los dos en años que pasan el mínimo. A 5 años o más, para no mover la supervivencia a 1, 3 y 5
# años, que S(5) saca de las tasas de las edades 0 a 4
FALLOS_VEINTE = [("ST4000X", 60, 30, None), ("WDC W12", 26, 25, None)]


def montar_caso(raiz, estropear=None, extra=()):
    """Escribe el caso pequeño en `raiz`; `estropear` cambia una tabla para un caso que tiene que parar; `extra` añade
    fallos a FALLOS_PEQ en todas las tablas a la vez."""
    if raiz.exists():
        shutil.rmtree(raiz)
    for c in ["data/processed", "data/raw", "informes", "config/fuentes"]:
        (raiz / c).mkdir(parents=True)
    (raiz / "data" / "raw" / "origen.csv").write_text("a\n1\n", encoding="utf-8")
    lista = FALLOS_PEQ + list(extra)

    # dim_modelo y calendario
    dm = [{"model": k, "capacidad_tb": v[1], "tipo_disco": v[2], "fabricante": v[0]} for k, v in MODELOS.items()]
    escribir(raiz, "dim_modelo", dm, ["model", "capacidad_tb", "tipo_disco", "fabricante"])
    dias, d = [], dt.datetime(2020, 1, 1)
    while d <= dt.datetime(2025, 6, 30):
        dias.append({"fecha": d, "ano": d.year})
        d += dt.timedelta(days=1)
    escribir(raiz, "calendario", dias, ["fecha", "ano"])

    # Fallos por modelo y mes, y los de cada fila del recuento
    fallos_mes = fallos_por_mes(lista)

    # recuento: una fila por día 1, modelo y centro; los fallos van al primer centro del reparto
    rec = []
    for i, mes in enumerate(MESES):
        for modelo in MODELOS:
            reparto = centros(modelo, i)
            for j, (centro, n) in enumerate(reparto.items()):
                rec.append({"fecha": mes, "model": modelo, "datacenter": centro, "discos": n,
                            "fallos": fallos_mes.get((modelo, i), 0) if j == 0 else 0})
    escribir(raiz, "recuento_diario_corregido", rec, ["fecha", "model", "datacenter", "discos", "fallos"])

    # modelo_trimestre: días y fallos por modelo de datos y trimestre, con el mínimo del año
    datos = [k for k, v in MODELOS.items() if v[2] == "datos"]
    mt = []
    for modelo in datos:
        dias_ano = {}
        for i in range(66):
            dias_ano[MESES[i].year] = dias_ano.get(MESES[i].year, 0) + MODELOS[modelo][3]
        for q in range(22):
            ano, trim = 2020 + q // 4, q % 4 + 1
            meses_q = range(q * 3, q * 3 + 3)
            mt.append({"model": modelo, "ano": ano, "trimestre": trim, "capacidad_tb": MODELOS[modelo][1],
                       "fabricante": MODELOS[modelo][0], "dias_disco": 3 * MODELOS[modelo][3],
                       "fallos": sum(fallos_mes.get((modelo, i), 0) for i in meses_q),
                       "dias_disco_ano": dias_ano[ano], "pasa_minimo_ano": dias_ano[ano] >= 50000})
    if estropear == "modelo_trimestre":
        mt[0]["fallos"] += 1
    escribir(raiz, "modelo_trimestre", mt, ["model", "ano", "trimestre", "capacidad_tb", "fabricante", "dias_disco",
                                            "fallos", "dias_disco_ano", "pasa_minimo_ano"])

    # centro_mes: discos de datos por centro y mes
    cm = {}
    for f in rec:
        if MODELOS[f["model"]][2] != "datos":
            continue
        k = (f["datacenter"], f["fecha"])
        a = cm.setdefault(k, {"datacenter": k[0], "mes": k[1], "dias_disco": 0, "fallos": 0})
        a["dias_disco"] += f["discos"]
        a["fallos"] += f["fallos"]
    escribir(raiz, "centro_mes", list(cm.values()), ["datacenter", "mes", "dias_disco", "fallos"])

    # dias_por_tramo: una fila por modelo y mes, con la edad del modelo ese mes
    dpt = filas_dpt(fallos_mes)
    escribir(raiz, "dias_por_tramo", dpt, ["model", "centro", "mes", "edad_anos_cumplidos", "fotos", "dias_disco",
                                           "fallos", "desaparecen_avisando"])

    # inicio_trimestre: los discos del primer día de cada trimestre, por modelo y edad
    it = []
    for q in range(22):
        for modelo in datos:
            it.append({"ano": 2020 + q // 4, "trimestre": q % 4 + 1, "model": modelo,
                       "edad_anos_cumplidos": edad(modelo, q * 3), "discos": MODELOS[modelo][3]})
    if estropear == "inicio_trimestre":
        it[-1]["discos"] += 1
    escribir(raiz, "inicio_trimestre", it, ["ano", "trimestre", "model", "edad_anos_cumplidos", "discos"])

    # fallos_detalle: una fila por fallo, con la edad del modelo ese mes más medio año
    fd, n = [], 0
    for modelo, i, k, serie in lista:
        for _ in range(k):
            n += 1
            fd.append({"serial_number": serie or f"F{n:03d}", "dia_fallo": MESES[i], "model": modelo,
                       "tipo_disco": MODELOS[modelo][2], "edad_al_fallar_anos": edad(modelo, i) + 0.5})
    escribir(raiz, "fallos_detalle", fd, ["serial_number", "dia_fallo", "model", "tipo_disco", "edad_al_fallar_anos"])

    # vida_discos, fotos y ventanas
    vida, fotos, ventanas = poblacion()
    if estropear == "vida_discos":
        vida[12]["primera_aparicion"] = MESES[4]
    if estropear == "supervivencia":
        for k in (0, 1, 2, 3, 4, 7, 8, 9):
            vida[k].update({"evento": "fallo", "edad_fin_anos": 0.5, "primer_fallo": MESES[6]})
    escribir(raiz, "vida_discos", vida, ["serial_number", "model", "primera_aparicion", "edad_entrada_anos",
                                         "ultima_foto", "evento", "edad_fin_anos", "desaparece_avisando"])
    escribir(raiz, "fotos_mensuales_corregido", fotos, ["fecha", "serial_number", "model"])
    escribir(raiz, "ventanas_fallo_corregido", ventanas, ["fecha", "serial_number", "model"])

    # transformacion-datos.json con las huellas, y los cuatro exploratorios
    p = raiz / "data" / "processed"
    salidas = [{"tabla": t, "ruta": f"data/processed/{t}.parquet", "sha256": sha256(p / f"{t}.parquet")}
               for t in ["dim_modelo", "modelo_trimestre", "dias_por_tramo", "vida_discos", "fallos_detalle",
                         "centro_mes", "inicio_trimestre"]]
    entradas = [{"ruta": f"data/processed/{t}.parquet", "sha256": sha256(p / f"{t}.parquet")}
                for t in ["recuento_diario_corregido", "fotos_mensuales_corregido", "ventanas_fallo_corregido",
                          "calendario"]]
    if estropear == "huella":
        salidas[1]["sha256"] = "0" * 64
    (raiz / "informes" / "transformacion-datos.json").write_text(
        json.dumps({"salidas": salidas, "entradas": entradas}), encoding="utf-8")
    for t in ["modelo_trimestre", "dias_por_tramo", "vida_discos", "centro_mes"]:
        estado = "PARADO" if (estropear == "exploratorio" and t == "vida_discos") else "AVISO"
        (raiz / "informes" / f"analisis-exploratorio__{t}.json").write_text(
            json.dumps({"resultado": {"estado": estado}}), encoding="utf-8")


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


def probar_caso_pequeno():
    """El script entero sobre el caso pequeño, y los casos que tienen que parar."""
    montar_caso(TMP)
    codigo, j = ejecutar(TMP)
    comprobar(codigo == 0 and j is not None and j["resultado"]["estado"] in ("OK", "AVISO"),
              f"caso pequeño: termina sin parar (código {codigo}, estado {j and j['resultado']['estado']})")
    if j is None or j["resultado"]["estado"] not in ("OK", "AVISO"):
        if j is not None:
            print(json.dumps(j["resultado"], ensure_ascii=False)[:2000])
        return
    comprobar((TMP / "informes" / "indicadores__discos_modelos_edad.md").exists(), "caso pequeño: deja el MD")
    # el responsable del caso, 17/11: la palabra vetada para el conjunto de discos no sale en ningún informe ni texto del repositorio
    #. Se escribe partida para que esta prueba tampoco la lleve.
    vetada = "flo" + "ta"
    textos = [(TMP / "informes" / n).read_text(encoding="utf-8").lower()
              for n in ("indicadores__discos_modelos_edad.json", "indicadores__discos_modelos_edad.md")
              if (TMP / "informes" / n).exists()]
    comprobar(len(textos) == 2 and not any(vetada in t for t in textos),
              "caso pequeño: ni el JSON ni el MD dicen la palabra vetada")
    comprobar(all(v is True for v in j["validaciones"].values()), "caso pequeño: las nueve validaciones en verde")

    b1, b2, b3 = pregunta(j, "B1"), pregunta(j, "B2"), pregunta(j, "B3")
    t1 = b1["tablas"]
    # Días y fallos del recuento de discos de datos: 18.000 discos × 66 días; 12 fallos
    comprobar(j["recuento_datos"]["dias_disco"] == 18000 * 66 and j["recuento_datos"]["fallos"] == 12,
              "caso pequeño: días y fallos de los discos de datos del recuento")
    # Serie mensual: 66 meses; el primero con 18.000 discos y 124 PB (10.000 × 4 + 3.000 × 8 + 5.000 × 12)
    serie = t1["serie_mensual"]
    comprobar(len(serie) == 66 and serie[0]["discos"] == 18000 and cerca(serie[0]["pb"], 124.0),
              "caso pequeño: serie mensual de 66 meses, 18.000 discos y 124 PB")
    # Altas: 21 trimestres; 5 en 2020T2, 5 en 2022T2, 1 en 2025T1 (D29, solo en su ventana), 4 en 2025T2
    altas = {a["trimestre"]: a["altas"] for a in t1["altas"]}
    comprobar(len(altas) == 21 and "2020T1" not in altas and altas["2020T2"] == 5 and altas["2022T2"] == 5
              and altas["2025T1"] == 1 and altas["2025T2"] == 4, "caso pequeño: altas por trimestre")
    bajas = {b["trimestre"]: b for b in t1["bajas"]}
    comprobar(len(bajas) == 22 and bajas["2022T3"]["desaparecen"] == 1 and bajas["2025T1"]["desaparecen"] == 1
              and bajas["2025T2"]["incompleto"] is True
              and bajas["2025T1"]["incompleto"] is False, "caso pequeño: bajas sin fallo y la marca de 2025T2")
    comprobar(bajas["2021T1"]["fallos"] == 1 and bajas["2025T1"]["fallos"] == 2,
              "caso pequeño: fallos por trimestre (el de arranque no entra)")
    # Diez modelos de 2020: ST4000X primero, 120.000 días entre 366
    top = [t for t in t1["top10"] if t["ano"] == 2020]
    comprobar(top[0]["model"] == "ST4000X" and cerca(top[0]["discos_medios"], 120000 / 366, 1e-6),
              "caso pequeño: primero de 2020 y sus discos medios")
    comprobar([t["model"] for t in top] == ["ST4000X", "WDC W12"],
              "caso pequeño: TOSHIBA T8, con 36.000 días en 2020, no entra entre los diez (mínimo)")
    # Ranking: dos modelos; ST4000X 3 fallos en 660.000 días; WDC W12 4 en 300.000 (2025 no pasa)
    rk = {r["model"]: r for r in b2["tablas"]["ranking"]}
    comprobar(set(rk) == {"ST4000X", "WDC W12"} and rk["ST4000X"]["fallos"] == 3
              and rk["ST4000X"]["dias_disco"] == 660000 and rk["WDC W12"]["fallos"] == 4
              and rk["WDC W12"]["dias_disco"] == 300000, "caso pequeño: ranking con los años que pasan el mínimo")
    fuera = b2["tablas"]["fuera_del_ranking"]
    comprobar(fuera["dias_disco"] == 228000 and fuera["fallos"] == 5 and fuera["celdas"] == 7,
              "caso pequeño: lo que no llega al mínimo, aparte con su recuento")
    # El JSON guarda las tasas con seis decimales
    comprobar(cerca(b2["referencia"]["valor"], 100 * 365 * 7 / 960000, 1e-5), "caso pequeño: tasa del conjunto de discos del ranking")
    # Por fabricante: Toshiba 4 fallos en 198.000 días
    fab = {f["grupo"]: f for f in b2["tablas"]["por_fabricante"]}
    comprobar(fab["Toshiba"]["fallos"] == 4 and fab["Toshiba"]["dias_disco"] == 198000,
              "caso pequeño: tasa por fabricante con todos sus discos")
    # Edad 5 del conjunto de discos: 156.000 días y 5 fallos
    e5 = next(f for f in b3["tablas"]["tasa_por_edad"]["todos"] if f["edad"] == 5)
    comprobar(cerca(e5["dias_disco"], 156000.0) and e5["fallos"] == 5, "caso pequeño: año de edad 5 del conjunto de discos")
    # Discos de 8 años o más el 01/04/2025: los 5.000 WDC (9 años) de 18.000
    v8 = b3["tablas"]["discos_8_o_mas"]
    comprobar(v8["discos_8_o_mas"] == 5000 and v8["discos_total"] == 18000, "caso pequeño: discos de 8 años o más")
    comprobar(all(s["coinciden"] is True for s in j["segundas_vias"]), "caso pequeño: todas las segundas vías coinciden")

    # Petición 17, cuestión 012: los dos modelos tienen 3 y 4 fallos, menos de 20: sin puesto y «sin conclusión»
    comprobar(all(rk[mo].get("puesto", 0) is None and rk[mo].get("veredicto") == "sin conclusión" for mo in rk),
              "petición 17, caso pequeño: con menos de 20 fallos, sin puesto y «sin conclusión» (cuestión 012)")
    sc_b2 = {x["grupo"] for x in j["sin_conclusion"] if x["bloque"] == "B2" and x["tipo"] == "pocos fallos"}
    comprobar(sc_b2 == {"ST4000X", "WDC W12"}, "petición 17, caso pequeño: los dos, en lo que no saca conclusión")
    a_mano, _, _, _ = igual_edad_a_mano(FALLOS_PEQ)
    comprobar(all(cerca(rk[mo].get("razon"), a_mano[mo]["razon"]) for mo in rk),
              "petición 17, caso pequeño: la razón de cada modelo, igual que el bucle de la prueba")
    probar_caso_veinte()

    # Casos que tienen que parar
    for estropear, estado, motivo in [
            ("modelo_trimestre", "ERROR", "fallos por modelo y año"),
            ("vida_discos", "ERROR", "primera aparición de cada disco"),
            ("inicio_trimestre", "ERROR", "discos el primer día de cada trimestre"),
            ("supervivencia", "ERROR", "supervivencia del conjunto de discos a 1, 3 y 5 años"),
            ("huella", "ERROR", "huella"),
            ("exploratorio", "PARADO", "exploratorio de vida_discos")]:
        montar_caso(TMP, estropear)
        codigo, j = ejecutar(TMP)
        comprobar(codigo != 0 and j is not None and j["resultado"]["estado"] == estado
                  and motivo in j["resultado"]["resumen"] and "preguntas" not in j,
                  f"caso pequeño estropeado en {estropear}: para con {estado} por «{motivo}», sin cifras en el JSON")


def probar_caso_veinte():
    """Petición 17: el caso pequeño con 30 y 25 fallos de más, para que los dos modelos del ranking lleven puesto.

    La razón, su intervalo, la tasa a igual edad, la edad media, el veredicto y el puesto se comparan con el bucle de la
    prueba (igual_edad_a_mano), que no usa pandas y saca el intervalo de la gamma.
    """
    montar_caso(TMP, extra=FALLOS_VEINTE)
    codigo, j = ejecutar(TMP)
    comprobar(codigo == 0 and j is not None and j["resultado"]["estado"] in ("OK", "AVISO"),
              f"petición 17, caso con 20 fallos: termina sin parar (código {codigo})")
    if j is None or "preguntas" not in j:
        if j is not None:
            print(json.dumps(j["resultado"], ensure_ascii=False)[:2000])
        return
    b2 = pregunta(j, "B2")["tablas"]
    rk = {r["model"]: r for r in b2["ranking"]}
    esp, dias_t, fallos_t, phi = igual_edad_a_mano(FALLOS_PEQ + FALLOS_VEINTE)
    ie0 = b2.get("a_igual_edad", {})
    ph = ie0.get("phi") or {}
    # En el caso pequeño cada año de edad y trimestre tiene un solo modelo: los esperados son los observados y φ vale 1.
    # El φ mayor que 1 lo prueban las piezas (probar_peticion19)
    comprobar(phi["phi"] >= 1 and cerca(ph.get("phi"), phi["phi"], 1e-9) and ph.get("celdas") == phi["celdas"]
              and ph.get("gl") == phi["gl"],
              f"petición 19, caso con 20 fallos: φ de B2 con sus celdas y grados de libertad, igual que el bucle de la "
              f"prueba ({phi}; da {ph})")
    b3 = pregunta(j, "B3")["tablas"]
    comprobar(isinstance(b3.get("phi"), dict) and b3["phi"].get("phi", 0) >= 1 and "celdas" in b3["phi"]
              and "gl" in b3["phi"], "petición 19, caso con 20 fallos: φ de B3 en el JSON, con celdas y grados de libertad")
    comprobar(all(v is True for v in pregunta(j, "B3").get("comprobaciones_extra", {"falta": False}).values()),
              "petición 19, caso con 20 fallos: las comprobaciones de la petición en B3, en verde")
    comprobar(rk["ST4000X"]["fallos"] == 33 and rk["WDC W12"]["fallos"] == 29 and all(
        rk[mo]["fallos"] == esp[mo]["observados"] for mo in rk), "petición 17, caso con 20 fallos: 33 y 29 fallos")
    comprobar(all(cerca(rk[mo].get("razon"), esp[mo]["razon"]) and cerca(rk[mo].get("razon_desde"), esp[mo]["desde"])
                  and cerca(rk[mo].get("razon_hasta"), esp[mo]["hasta"]) for mo in rk),
              "petición 17, caso con 20 fallos: razón e intervalo de cada modelo, igual que el bucle de la prueba")
    comprobar(all(cerca(rk[mo].get("tasa_igual_edad"), esp[mo]["tasa_igual_edad"], 1e-6)
                  and cerca(rk[mo].get("edad_media_anos"), esp[mo]["edad_media"], 1e-6) for mo in rk),
              "petición 17, caso con 20 fallos: tasa a igual edad y edad media, a mano")
    comprobar(all(rk[mo].get("veredicto") == esp[mo]["veredicto"] for mo in rk),
              "petición 17, caso con 20 fallos: el veredicto a igual edad sale del intervalo")
    # Petición 19: con la tasa de cada edad y trimestre, en el caso pequeño las dos razones valen 1 (cada edad y trimestre
    # tiene un solo modelo), y su orden lo pone el redondeo. El orden se mira con las razones del JSON, que la
    # comprobación de arriba compara con el bucle
    rz = [r["razon"] for r in b2["ranking"]]
    comprobar(all(a <= b + 1e-9 for a, b in zip(rz, rz[1:]))
              and sorted(r.get("puesto") for r in b2["ranking"]) in ([1, 1], [1, 2]),
              "petición 17, caso con 20 fallos: ranking y puestos por la razón")
    ie = b2.get("a_igual_edad", {})
    comprobar(cerca(ie.get("dias"), dias_t) and ie.get("fallos") == fallos_t
              and cerca(ie.get("tasa_todos"), 36500 * fallos_t / dias_t, 1e-6),
              "petición 17, caso con 20 fallos: días, fallos y tasa de todas las celdas que pasan")
    # Por construcción del método, no como segunda vía de la cifra
    comprobar(cerca(sum(r.get("esperados", math.nan) for r in b2["ranking"]), sum(r["fallos"] for r in b2["ranking"]), 1e-9),
              "petición 17, caso con 20 fallos: los esperados suman los observados (por construcción, no es segunda vía)")
    est = ie.get("estabilidad", {})
    comprobar(len(est.get("retiradas", [])) == 2 and "sin_parciales" in est,
              "petición 17, caso con 20 fallos: la estabilidad, con una retirada por modelo y sin 2025")
    comprobar(all(v is True for v in j["validaciones"].values())
              and all(v is True for v in pregunta(j, "B2").get("comprobaciones_extra", {"falta": False}).values()),
              "petición 17, caso con 20 fallos: las validaciones y las comprobaciones de la petición en verde")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 3 · el JSON real, contra los controles de la petición y por otro camino
# ---------------------------------------------------------------------------------------------------------------
def probar_json_real():
    """Controles de la petición y dos cifras rehechas con pyarrow desde el recuento."""
    ruta = CASO / SALIDA
    if not ruta.exists():
        print("aviso  no hay JSON real todavía: la parte 3 no se prueba")
        return
    j = json.loads(ruta.read_text(encoding="utf-8"))
    comprobar(j["resultado"]["estado"] in ("OK", "AVISO"), f"JSON real: estado {j['resultado']['estado']}")
    b1, b2, b3 = pregunta(j, "B1"), pregunta(j, "B2"), pregunta(j, "B3")

    def pct(x, d=2):
        """Redondeo a d decimales como se escribe en la petición."""
        return round(x + 1e-12, d)

    # Recuento de discos de datos
    comprobar(j["recuento_datos"]["dias_disco"] == 446108683 and j["recuento_datos"]["fallos"] == 16996,
              "control: 446.108.683 días de disco y 16.996 fallos")
    # Día 1 de mes
    serie = {s["mes"]: s for s in b1["tablas"]["serie_mensual"]}
    for mes, discos, pb in [("2020-01-01", 122696, 1090.9), ("2023-07-01", 241297, 2881.1),
                            ("2025-06-01", 314758, 4790.1)]:
        comprobar(serie[mes]["discos"] == discos and pct(serie[mes]["pb"], 1) == pb,
                  f"control: {mes}, {discos} discos y {pb} PB (da {serie[mes]['discos']} y {serie[mes]['pb']:.2f})")
    # Altas, bajas y fallos por trimestre
    altas = {a["trimestre"]: a["altas"] for a in b1["tablas"]["altas"]}
    for q, n in [("2020T2", 11418), ("2022T1", 12371), ("2024T1", 11768), ("2025T2", 11310)]:
        comprobar(altas.get(q) == n, f"control: altas {q} = {n} (da {altas.get(q)})")
    bajas = {b["trimestre"]: b for b in b1["tablas"]["bajas"]}
    comprobar(sum(b["desaparecen"] for b in bajas.values()) == 71328, "control: 71.328 desaparecen sin fallo")
    for q, n in [("2020T2", 2092), ("2022T1", 9), ("2024T1", 6230), ("2025T1", 4206)]:
        comprobar(bajas[q]["desaparecen"] == n, f"control: desaparecen {q} = {n} (da {bajas[q]['desaparecen']})")
    for q, n in [("2020T2", 272), ("2024T1", 949), ("2025T1", 1067)]:
        comprobar(bajas[q]["fallos"] == n, f"control: fallos {q} = {n} (da {bajas[q]['fallos']})")
    # Primero de los diez de cada año
    for ano, modelo, n in [(2020, "ST12000NM0007", 32643), (2024, "TOSHIBA MG08ACA16TA", 38497)]:
        top = [t for t in b1["tablas"]["top10"] if t["ano"] == ano][0]
        comprobar(top["model"] == modelo and round(top["discos_medios"]) == n,
                  f"control: primero de {ano}, {modelo} con {n} discos medios (da {top['model']}, "
                  f"{top['discos_medios']:.1f})")
    # Ranking
    t2 = b2["tablas"]
    fuera = t2["fuera_del_ranking"]
    comprobar(t2["celdas_que_pasan"] == 152 and t2["celdas_total"] == 299 and len(t2["ranking"]) == 32,
              "control: 152 celdas de 299 pasan el mínimo, de 32 modelos")
    comprobar(fuera["dias_disco"] == 1282168 and fuera["fallos"] == 101, "control: fuera, 1.282.168 días y 101 fallos")
    rk = t2["ranking"]
    # Desde la petición 17 el ranking se ordena por la razón a igual edad: la tasa más baja y la más alta se buscan
    lo, hi = min(rk, key=lambda f: f["tasa"]), max(rk, key=lambda f: f["tasa"])
    comprobar(lo["model"] == "HGST HMS5C4040BLE640" and pct(lo["tasa"]) == 0.33 and lo["fallos"] == 193
              and lo["dias_disco"] == 21590966 and pct(lo["desde"]) == 0.28 and pct(lo["hasta"]) == 0.38,
              "control: el más bajo, HGST HMS5C4040BLE640, 0,33 % (0,28 a 0,38)")
    comprobar(hi["model"] == "ST14000NM0138" and pct(hi["tasa"]) == 5.90 and hi["fallos"] == 391
              and hi["dias_disco"] == 2417642 and pct(hi["desde"]) == 5.33 and pct(hi["hasta"]) == 6.52,
              "control: el más alto, ST14000NM0138, 5,90 % (5,33 a 6,52)")
    fab = {f["grupo"]: f for f in t2["por_fabricante"]}
    for g, t, n in [("HGST", 1.30, 2702), ("Seagate", 1.78, 10284), ("Toshiba", 1.09, 3279), ("WDC", 0.53, 731)]:
        comprobar(pct(fab[g]["tasa"]) == t and fab[g]["fallos"] == n, f"control: {g} {t} % ({n} fallos)")
    controles_igual_edad(t2, pct)
    controles_peticion19(t2, b3["tablas"], pct)
    # Tasa por edad del conjunto de discos
    edad = {f["edad"]: f for f in b3["tablas"]["tasa_por_edad"]["todos"]}
    for e, t in zip(range(6), [0.79, 0.86, 1.20, 1.59, 1.92, 2.58]):
        comprobar(pct(edad[e]["tasa"]) == t, f"control: tasa a {e} años, {t} % (da {edad[e]['tasa']:.4f})")
    comprobar(edad[7]["fallos"] == 1207 and round(edad[7]["dias_disco"]) == 18269950,
              "control: año 7, 1.207 fallos en 18.269.950 días")
    comprobar(edad[8]["fallos"] == 334 and round(edad[8]["dias_disco"]) == 6421014,
              "control: año 8, 334 fallos en 6.421.014 días")
    comprobar(edad[9]["fallos"] == 0 and edad[10]["fallos"] == 0, "control: años 9 y 10 sin fallos")
    # Supervivencia del conjunto de discos
    sv = b3["tablas"]["supervivencia"]["todos"]
    for k, ref in zip((1, 3, 5), (99.16, 97.11, 93.68)):
        comprobar(abs(100 * sv["s"][k] - ref) < 0.2,
                  f"control: S a {k} años desde vida_discos a menos de 0,2 puntos de {ref} (da {100 * sv['s'][k]:.2f})")
    sd = b3["tablas"]["supervivencia"]["todos_dias_por_tramo"]
    for k, ref in zip((1, 3, 5), (99.21, 97.19, 93.83)):
        comprobar(pct(100 * sd["s"][k]) == ref, f"control: S a {k} años con dias_por_tramo, {ref}")
    # Los cinco modelos con más días y los discos de 8 años o más
    comprobar(b3["tablas"]["cinco_modelos"] == ["TOSHIBA MG07ACA14TA", "ST12000NM0008", "ST16000NM001G",
                                                 "ST8000NM0055", "ST4000DM000"], "control: los cinco modelos con más días")
    v8 = b3["tablas"]["discos_8_o_mas"]
    comprobar(v8["discos_8_o_mas"] == 11038 and v8["discos_total"] == 308836, "control: 11.038 de 308.836 discos")

    # Otro camino, con pyarrow y sin pandas: el recuento de los discos de datos
    dm = pq.read_table(PROCESADOS / "dim_modelo.parquet", columns=["model", "tipo_disco"]).to_pylist()
    datos = {f["model"] for f in dm if f["tipo_disco"] == "datos"}
    rec = pq.read_table(PROCESADOS / "recuento_diario_corregido.parquet", columns=["fecha", "model", "discos", "fallos"])
    mascara = pc.is_in(rec["model"], value_set=pa.array(sorted(datos)))
    rd = rec.filter(mascara)
    comprobar(pc.sum(rd["discos"]).as_py() == j["recuento_datos"]["dias_disco"]
              and pc.sum(rd["fallos"]).as_py() == j["recuento_datos"]["fallos"],
              "otra vía (pyarrow, recuento): días y fallos de los discos de datos")
    abril = rd.filter(pc.equal(rd["fecha"], pa.scalar(dt.datetime(2025, 4, 1), type=rd.schema.field("fecha").type)))
    comprobar(pc.sum(abril["discos"]).as_py() == v8["discos_total"],
              "otra vía (pyarrow, recuento): discos del 01/04/2025 = los de inicio_trimestre")
    # Las cifras aprobadas de pasos anteriores: los fallos de discos de datos por periodo
    ref = json.loads((CASO / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8"))["cifras"]
    comprobar(ref["fallos.datos_construccion"] + ref["fallos.datos_validacion"] == j["recuento_datos"]["fallos"],
              "cifras de referencia: los fallos de discos de datos de los pasos anteriores")


def controles_igual_edad(t2, pct):
    """Controles de la petición 17 (prompts/17_…, «CONTROLES», B2), escritos como los da la petición.

    Un JSON real de antes de la petición 17 no trae la comparación a igual edad: se avisa y no se prueba, porque lo escribe la
    ejecución real de la sesión principal.
    """
    ie = t2.get("a_igual_edad")
    if ie is None:
        print("aviso  el JSON real es de antes de la petición 17: sus controles de B2 se prueban tras la ejecución real")
        return
    # Desde la petición 19 la tasa es la de cada edad y trimestre y el intervalo lleva φ: las razones, los veredictos y
    # la estabilidad de la petición 17 cambian por diseño, y mandan los controles del 19 (controles_peticion19)
    if "phi" in ie:
        return
    rk = {f["model"]: f for f in t2["ranking"]}
    comprobar(round(ie["dias"]) == 443929499 and ie["fallos"] == 16895 and pct(ie["tasa_todos"], 4) == 1.3891
              and ie["dias_ranking"] == 444826515,
              "control 17: celdas que pasan, 443.929.499 días y 16.895 fallos; tasa 1,3891; el ranking, 444.826.515 días")
    v = ie["veredictos"]
    comprobar((v.get("por encima"), v.get("por debajo"), v.get("no se distingue"), v.get("sin conclusión")) == (13, 11, 3, 5),
              f"control 17: 13 por encima, 11 por debajo, 3 no se distinguen y 5 sin conclusión (da {v})")
    comprobar(ie["cambian_frente_al_bruto"]["n"] == 9, "control 17: cambian 9 frente al bruto con cuestión 012")
    # La edad media de la petición (0,75 y 5,37) se midió con los años cumplidos; el script usa años cumplidos + 0,5, el
    # punto medio del año, como desde la petición 13 (sus parámetros lo dicen). El control se corrige al +0,5
    for mo, f, rz, lo, hi, ed, ver, bru in [
            ("TOSHIBA MG08ACA16TA", 852, 1.3145, 1.2277, 1.4058, 1.25, "por encima", "por debajo"),
            ("ST8000DM002", 937, 0.8388, 0.7860, 0.8943, 5.87, "por debajo", "por encima")]:
        x = rk[mo]
        comprobar(x["fallos"] == f and pct(x["razon"], 4) == rz and pct(x["razon_desde"], 4) == lo
                  and pct(x["razon_hasta"], 4) == hi and pct(x["edad_media_anos"], 2) == ed and x["veredicto"] == ver
                  and x["veredicto_bruto"] == bru,
                  f"control 17: {mo}, {f} fallos, razón {rz} ({lo} a {hi}), edad media {ed}, {ver} (bruto: {bru}) "
                  f"(da {x['razon']:.4f}, edad {x['edad_media_anos']:.2f}, {x['veredicto']})")
    comprobar(pct(rk["HGST HMS5C4040BLE640"]["razon"], 4) == 0.1526 and pct(rk["ST14000NM0138"]["razon"], 4) == 5.0203,
              "control 17: razón del HGST HMS5C4040BLE640, 0,1526, y del ST14000NM0138, 5,0203")
    sp = (ie["spearman_tasa_razon"], ie["spearman_tasa_razon_con_puesto"])
    comprobar(0.859 in [pct(x, 3) for x in sp if x is not None],
              f"control 17: Spearman entre tasa bruta y razón, 0,859 (da {sp[0]} con los 32 y {sp[1]} con los de puesto)")
    comprobar(set(ie["sin_conclusion"]) == {"ST12000NM000J", "ST14000NM000J", "ST16000NM002J", "ST6000DX000",
                                            "ST8000NM000A"}
              and all(rk[mo]["puesto"] is None for mo in ie["sin_conclusion"]), "control 17: los cinco sin conclusión, sin puesto")
    es = ie["estabilidad"]
    comprobar(es["retiradas_que_cambian"] == 5 and es["max_cambian"] == 2 and es["modelo_max"] == "HGST HMS5C4040BLE640",
              f"control 17: estabilidad, 5 retiradas cambian algo y como mucho 2, la del HGST HMS5C4040BLE640 "
              f"(da {es['retiradas_que_cambian']}, {es['max_cambian']}, {es['modelo_max']})")
    # La petición daba 3 porque su medida dejó fuera el ST24000NM002H, que solo tiene 2025: sin ese año se queda sin
    # días y pasa a «sin conclusión», un cambio más
    comprobar(es["sin_parciales"]["cambian"] == 4 and set(es["sin_parciales"]["modelos"]) == {
        "ST24000NM002H", "TOSHIBA MG08ACA16TEY", "TOSHIBA MG10ACA20TE", "WDC WUH722222ALE6L4"},
        f"control 17: sin 2025 cambian 4 (da {es['sin_parciales']['modelos']})")


def controles_peticion19(t2, t3, pct):
    """Controles de la petición 19 (prompts/19_…, «CONTROLES», B2 y B3), escritos como los da la petición.

    Un JSON real de antes de la petición 19 no trae φ: se avisa y no se prueba, porque lo escribe la ejecución real de la
    sesión principal.
    """
    ie = t2.get("a_igual_edad") or {}
    if "phi" not in ie:
        print("aviso  el JSON real es de antes de la petición 19: sus controles de B2 y B3 se prueban tras la ejecución real")
        return
    rk = {f["model"]: f for f in t2["ranking"]}
    comprobar(ie["celdas"] == 10039 and round(ie["dias"]) == 443929499 and ie["fallos"] == 16895
              and ie.get("celdas_edad_trimestre") == 188
              and abs(sum(f["esperados"] for f in t2["ranking"] if f["esperados"] is not None) - 16895) < 1e-6,
              f"control 19: 10.039 celdas, 443.929.499 días y 16.895 fallos; 188 celdas de edad y trimestre; "
              f"esperados 16.895 (da {ie['celdas']}, {ie['dias']:.0f}, {ie['fallos']}, {ie.get('celdas_edad_trimestre')})")
    ph = ie["phi"]
    comprobar(pct(ph["phi"], 4) == 3.3668 and ph["celdas"] == 536 and ph["gl"] == 504,
              f"control 19: φ de B2 3,3668 con 536 celdas y 504 gl (da {ph})")
    v = ie["veredictos"]
    comprobar((v.get("por encima"), v.get("por debajo"), v.get("no se distingue"), v.get("sin conclusión")) == (13, 9, 5, 5),
              f"control 19: 13 por encima, 9 por debajo, 5 no se distinguen y 5 sin conclusión (da {v})")
    for mo, f, rz, lo, hi, ver in [
            ("WDC WUH721816ALE6L0", 78, 0.8074, 0.5128, 1.2098, "no se distingue"),
            ("HGST HUH721212ALN604", 1367, 0.9666, 0.8748, 1.0653, "no se distingue"),
            ("ST8000DM002", 937, 1.1514, 1.0201, 1.2949, "por encima"),
            ("TOSHIBA MG08ACA16TA", None, 1.3860, 1.2205, 1.5677, "por encima")]:
        x = rk[mo]
        comprobar((f is None or x["fallos"] == f) and pct(x["razon"], 4) == rz and pct(x["razon_desde"], 4) == lo
                  and pct(x["razon_hasta"], 4) == hi and x["veredicto"] == ver,
                  f"control 19: {mo}, razón {rz} ({lo} a {hi}), {ver} (da {x['razon']:.4f}, {x['razon_desde']:.4f} a "
                  f"{x['razon_hasta']:.4f}, {x['veredicto']})")
    for mo, rz, lo, hi in [("HGST HMS5C4040BLE640", 0.2034, 0.1542, 0.2634), ("ST14000NM0138", 5.1950, 4.2932, 6.2302)]:
        x = rk[mo]
        comprobar(pct(x["razon"], 4) == rz and pct(x["razon_desde"], 4) == lo and pct(x["razon_hasta"], 4) == hi,
                  f"control 19: {mo}, razón {rz} ({lo} a {hi}) (da {x['razon']:.4f}, {x['razon_desde']:.4f} a "
                  f"{x['razon_hasta']:.4f})")
    fa = ie.get("frente_al_metodo_anterior", {})
    cambian = {x["model"]: (x["antes"], x["despues"]) for x in fa.get("cambian", [])}
    comprobar(cambian == {"WDC WUH721816ALE6L0": ("por debajo", "no se distingue"),
                          "HGST HUH721212ALN604": ("por encima", "no se distingue"),
                          "ST8000DM002": ("por debajo", "por encima")}
              and pct(fa.get("spearman_razon", 0), 4) == 0.9516,
              f"control 19: frente al método anterior cambian 3 y Spearman 0,9516 (da {cambian}, {fa.get('spearman_razon')})")
    pe = t3.get("phi") or {}
    comprobar(pct(pe.get("phi", 0), 2) == 5.02 and pe.get("celdas") == 2543 and pe.get("gl") == 2338,
              f"control 19: φ de B3 5,02 con 2.543 celdas y 2.338 gl (da {pe})")
    sube = [f["edad"] for f in t3["tasa_por_edad"]["todos"] if f["sube"]]
    comprobar(sube == [2, 3, 4, 5], f"control 19: con φ, la tasa sube en los años de edad 2, 3, 4 y 5 (da {sube})")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        modulo = cargar_modulo()
        if modulo is not None:
            probar_piezas(modulo)
            probar_igual_edad(modulo)
            probar_peticion19(modulo)
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
