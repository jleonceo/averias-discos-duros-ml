"""Prueba de scripts/14_preseleccion.py (método preseleccion-variables; petición 21, primera parte).

Parte 1, las piezas sueltas. Carga el script como módulo (su trabajo está dentro de `if __name__ == "__main__":`) y
prueba con datos pequeños escritos aquí, cada pieza con un caso que tiene que salir bien y otro que tiene que salir mal:
  - el corte por salto natural, con su cociente y sus dos valores;
  - la variable de origen de cada columna, leída de la matriz aprobada;
  - la votación por variable de origen y las obligatorias, que entran sin votar;
  - la alarma de fuga, con el AUC de cada variable sola y el umbral del caso;
  - las variables del momento;
  - la V de Cramér y Spearman, y de cada par la de más información mutua, salvo que la otra sea obligatoria;
  - el tope, que quita familias enteras de peor ranking y nunca una obligatoria;
  - los meses más recientes de la muestra, enteros, y la muestra entera cuando no llega;
  - los pliegues internos por fecha, que quitan las fotos cuyo horizonte no acabó el primer día de lo que miden;
  - las seis validaciones de el método §8 en verde y en rojo, y que ninguna está escrita con True puesto.
Parte 2, el script entero sobre un caso pequeño en tests/tmp_preseleccion/, que se crea y se borra: una tabla de
entrenamiento con las 144 columnas de la real (tipos tomados con read_schema, sin cargar datos), una copia de la matriz
con su estado escrito en la copia y un informes/preparacion.json en OK con la huella. Sin fichero de validación: el
script no lo necesita. Comprueba:
  - una variable con señal entra; una de ruido sale; una obligatoria que sale abajo entra;
  - de dos que dicen lo mismo sale la que no es obligatoria;
  - los árboles reciben las 64 columnas sin votar;
  - una fuga puesta a propósito salta la alarma y el script para (PARADO);
  - preparacion.json fuera de OK, o la matriz sin aprobar, paran (PARADO).
Parte 3, el JSON real, si la sesión principal ya ejecutó el script: las cifras de control de la petición.

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "14_preseleccion.py"
TMP = CASO / "tests" / "tmp_preseleccion"
MATRIZ = "config/modelo/matriz_transformaciones.md"
ENT = "data/processed/fotos_riesgo_entrenamiento.parquet"
SALIDA = "informes/preseleccion.json"
VALIDACIONES = ["sin_validacion", "origen_en_matriz", "familias_enteras", "tope", "sin_prohibidas", "lista_valida"]
OBLIGATORIAS = ["smart_5_raw", "smart_187_raw", "smart_197_raw", "smart_198_raw"]
LIMITE_S = 150                                      # la petición: si una ejecución pasa de 150 s, se para y se dice
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si no se cumple y lo imprime."""
    print(("ok    " if condicion else "FALLA ") + caso)
    if not condicion:
        FALLOS.append(caso)


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
    spec = importlib.util.spec_from_file_location("preseleccion_14", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["preseleccion_14"] = modulo
    try:
        spec.loader.exec_module(modulo)
    except Exception as e:  # noqa: BLE001 - la prueba dice qué falló al cargar
        comprobar(False, f"el script carga como módulo ({type(e).__name__}: {e})")
        return None
    return modulo


# ---------------------------------------------------------------------------------------------------------------
# 2. Parte 1 · el corte, el origen, la votación, la fuga y el momento
# ---------------------------------------------------------------------------------------------------------------
def probar_corte(m):
    """El salto natural corta donde el cociente entre un valor y el siguiente es mayor."""
    v = pd.Series({"a": 0.50, "b": 0.40, "c": 0.05, "d": 0.04, "e": 0.0, "f": -0.01})
    c = m.corte_salto(v)
    comprobar(sorted(c["pasan"]) == ["a", "b"], f"corte: pasan las de arriba del mayor salto ({c['pasan']})")
    comprobar(abs(c["cociente"] - 8.0) < 1e-9 and c["valor"] == 0.40 and c["valor_abajo"] == 0.05,
              "corte: el JSON lleva el cociente y los dos valores")
    c = m.corte_salto(pd.Series({"a": 0.9, "b": 0.1, "c": 0.09, "d": 0.08}))
    comprobar(c["pasan"] == ["a"], "corte: con el salto arriba, pasa solo la primera (no corta por posición)")
    c = m.corte_salto(pd.Series({"a": 0.0, "b": -0.2}))
    comprobar(c["pasan"] == [] and c["cociente"] is None, "corte: sin valores mayores que cero no pasa ninguna")
    c = m.corte_salto(pd.Series({"a": 0.3, "b": 0.0}))
    comprobar(c["pasan"] == ["a"] and c["cociente"] is None, "corte: con un solo valor mayor que cero, pasa ese")


def probar_origen(m):
    """La variable de origen de cada columna sale de la matriz aprobada, no del nombre."""
    mz = m.P13.leer_matriz((CASO / MATRIZ).read_text(encoding="utf-8"))
    pat = m.patrones_logistica(mz)
    comprobar(len(pat) == 62, f"origen: 62 variables de la logística con su patrón en la matriz ({len(pat)})")
    origen, sin, varias = m.origen_de(["smart_5_raw_disc_cs_3", "smart_5_raw_disc_cs_vacio", "model_ohe_ST4000DM000",
                                       "smart_1_raw_disc_cs_2", "smart_1_normalized_disc_cs_1"], pat)
    comprobar(origen == {"smart_5_raw_disc_cs_3": "smart_5_raw", "smart_5_raw_disc_cs_vacio": "smart_5_raw",
                         "model_ohe_ST4000DM000": "model", "smart_1_raw_disc_cs_2": "smart_1_raw",
                         "smart_1_normalized_disc_cs_1": "smart_1_normalized"} and not sin and not varias,
              "origen: cada columna a su variable")
    _, sin, _ = m.origen_de(["avisa_disc_cs_1", "smart_999_raw_disc_cs_0"], pat)
    comprobar(sorted(sin) == ["avisa_disc_cs_1", "smart_999_raw_disc_cs_0"], "origen: una columna sin variable en la matriz se detecta")


def probar_votacion(m):
    """Una variable recibe el voto de un método si alguna de sus columnas pasa; entran las de dos votos o más."""
    origen = {"a_1": "a", "a_2": "a", "b_1": "b", "c_1": "c", "o_1": "o"}
    votos = m.votos_por_variable({"mi": ["a_1", "b_1"], "rfe": ["a_2", "c_1"], "permutacion": ["b_1"]}, origen)
    comprobar(votos == {"a": 2, "b": 2, "c": 1, "o": 0}, f"votos: por variable de origen ({votos})")
    entran = m.entran_por_votacion(votos, minimo=2, obligatorias=["o"])
    comprobar(entran == ["a", "b", "o"], f"votación: consenso amplio más las obligatorias ({entran})")
    comprobar("c" not in entran, "votación: la de un voto no entra")


def probar_fuga(m):
    """El AUC de cada variable sola, por su distancia a 0,5, y la alarma desde |2·AUC − 1| ≥ 0,90."""
    rng = np.random.default_rng(1)
    y = (rng.random(4000) < 0.3).astype(int)
    Z = pd.DataFrame({"f_1": y.astype(float), "r_1": (rng.random(4000) < 0.5).astype(float),
                      "r_2": (rng.random(4000) < 0.2).astype(float), "i_1": (1 - y).astype(float)})
    cols = {"f": ["f_1"], "r": ["r_1", "r_2"], "i": ["i_1"]}
    auc = m.auc_variable_sola(Z, y, cols)
    alarmas = m.alarmas(auc, m.UMBRAL_FUGA)
    comprobar(sorted(a["columna"] for a in alarmas) == ["f", "i"], f"fuga: salta con la copia y con la copia al revés ({alarmas})")
    comprobar(auc["r"]["diferencia"] < 0.1, "fuga: la de ruido no salta")
    # Una copia del objetivo que los tramos funden en uno solo y no deja columnas: salta por el valor en bruto
    crudas = pd.DataFrame({"smart_242_raw": y.astype(float), "smart_12_raw": rng.integers(0, 6, 4000).astype(float)})
    auc = m.auc_variable_sola(Z, y, {"smart_242_raw": [], "smart_12_raw": []}, crudas)
    comprobar([a["columna"] for a in m.alarmas(auc, m.UMBRAL_FUGA)] == ["smart_242_raw"],
              "fuga: salta en bruto aunque los tramos no dejen columnas")
    comprobar(auc["smart_242_raw"]["auc_tramos"] is None and auc["smart_242_raw"]["de"] == "bruto",
              "fuga: el JSON dice que la alarma salió del valor en bruto")


def probar_momento(m):
    """Una variable con el mismo valor para todas las fotos de una fecha, y distinta entre fechas, es del momento."""
    df = pd.DataFrame({"fecha": ["2024-01"] * 3 + ["2024-02"] * 3, "tipo": [1.0, 1, 1, 2, 2, 2],
                       "disco": [1.0, 2, 3, 1, 2, 3], "fija": [0.0] * 6})
    comprobar(m.del_momento(df, ["tipo", "disco", "fija"], "fecha") == ["tipo"],
              "momento: se marca la de la fecha y no la del disco ni la constante")


def probar_parecidas(m):
    """Cramér y Spearman, y de cada par la de más información mutua, salvo que la otra sea obligatoria."""
    rng = np.random.default_rng(2)
    a = rng.integers(0, 4, 3000)
    comprobar(m.cramer(a, a) > 0.99 and m.cramer(a, rng.integers(0, 4, 3000)) < 0.1, "Cramér: 1 con la misma, cerca de 0 con otra")
    x = rng.normal(size=3000)
    comprobar(m.spearman(x, x * 3 + 1) > 0.99 and abs(m.spearman(x, rng.normal(size=3000))) < 0.1,
              "Spearman: 1 con una monótona, cerca de 0 con otra")
    comprobar(m.spearman(np.ones(10), x[:10]) is None, "Spearman: con una constante no se calcula")
    pares = [{"columna_1": "a", "columna_2": "b", "valor": 0.9}, {"columna_1": "b", "columna_2": "c", "valor": 0.8},
             {"columna_1": "o", "columna_2": "d", "valor": 0.7}, {"columna_1": "o", "columna_2": "p", "valor": 0.6}]
    mi = {"a": 0.5, "b": 0.6, "c": 0.1, "d": 0.9, "o": 0.01, "p": 0.02}
    salen = m.quitar_por_pares(pares, mi, obligatorias=["o", "p"])
    comprobar([p["sale"] for p in salen] == ["a", "c", "d", None],
              f"pares: sale la de menos información mutua; la obligatoria gana; dos obligatorias se quedan ({[p['sale'] for p in salen]})")


def probar_parecido_por_vacio(m):
    """Dos variables que solo coinciden en qué filas no tienen dato no se parecen (método §6, último punto): el vacío
    de un contador SMART lo fija el modelo que lo registra, no la información. Una copia con el mismo vacío sí se parece."""
    rng = np.random.default_rng(3)
    n = 6000
    grupo = np.where(rng.random(n) < 0.5, "A", "B")                      # A no registra los contadores
    x1 = np.where(grupo == "A", np.nan, rng.normal(size=n))
    x2 = np.where(grupo == "A", np.nan, rng.normal(size=n))             # independiente de x1 donde hay dato
    x3 = np.where(grupo == "A", np.nan, x1 + rng.normal(scale=0.05, size=n))   # copia de x1
    df = pd.DataFrame({"x1": x1, "x2": x2, "x3": x3, "grupo": grupo})

    def tramos(x):
        """El vacío como tramo propio (0) y dos tramos por el signo."""
        return np.where(np.isnan(x), 0, np.where(x > 0, 2, 1))

    cod = {"x1": tramos(x1), "x2": tramos(x2), "x3": tramos(x3), "grupo": (grupo == "B").astype(int)}
    pares = {frozenset((p["columna_1"], p["columna_2"])) for p in m.pares_parecidos(df, cod, ["x1", "x2", "x3", "grupo"], 0.5)}
    comprobar(frozenset(("x1", "x2")) not in pares, f"vacío: dos variables que solo comparten el vacío no se parecen ({sorted(map(sorted, pares))})")
    comprobar(frozenset(("grupo", "x2")) not in pares, "vacío: el grupo que decide el vacío no se parece a la variable")
    comprobar(frozenset(("x1", "x3")) in pares, "vacío: una copia con el mismo vacío sí se parece")


def probar_tope(m):
    """Si sobran columnas, salen familias enteras de peor ranking, nunca una obligatoria."""
    cols = {"a": ["a_1", "a_2"], "b": ["b_1", "b_2", "b_3"], "c": ["c_1"], "o": ["o_1", "o_2"]}
    ranking = {"a": 1, "b": 3, "c": 2, "o": 4}
    quedan, salen = m.aplicar_tope(["a", "b", "c", "o"], cols, ranking, maximo=5, obligatorias=["o"])
    comprobar(salen == ["b"] and quedan == ["a", "c", "o"], f"tope: sale la familia de peor ranking que no es obligatoria ({salen})")
    quedan, salen = m.aplicar_tope(["a", "c"], cols, ranking, maximo=5, obligatorias=[])
    comprobar(salen == [] and quedan == ["a", "c"], "tope: si no sobran, no sale ninguna")


def probar_meses(m):
    """Los meses más recientes, enteros, hasta pasar del tamaño; la muestra entera si no llega."""
    df = pd.DataFrame({"fecha": np.repeat(pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]), [40, 30, 50])})
    sub, entera = m.meses_recientes(df, 60, "fecha")
    comprobar(len(sub) == 80 and not entera and sorted(sub["fecha"].dt.month.unique()) == [2, 3],
              f"meses: los dos más recientes, enteros, hasta pasar de 60 ({len(sub)})")
    sub, entera = m.meses_recientes(df, 500, "fecha")
    comprobar(len(sub) == 120 and entera, "meses: si no llega, la muestra entera y se dice")


def probar_pliegues(m):
    """Cada pliegue interno quita del entrenamiento las fotos cuyo horizonte no acabó el primer día de lo que mide."""
    fechas = pd.to_datetime(["2024-01-01"] * 4 + ["2024-02-01"] * 4 + ["2024-03-01"] * 4 + ["2024-04-01"] * 4).to_numpy()
    horiz = fechas + np.timedelta64(30, "D")
    horiz[1] = np.datetime64("2024-03-15")            # una foto de enero cuyo horizonte cruza al pliegue de marzo
    y = np.array([0, 1] * 8)
    cortes, detalle = m.pliegues_por_fecha(fechas, horiz, y, 3)
    comprobar(len(cortes) == 3, "pliegues: tres")
    for (ent, med), d in zip(cortes, detalle):
        primero = fechas[med].min()
        comprobar(bool((horiz[ent] < primero).all()), f"pliegues: ningún horizonte abierto el {str(primero)[:10]}")
    quitadas = [d["filas_quitadas"] for d in detalle]
    comprobar(sum(quitadas) > 0 and any(d["fallos_quitados"] > 0 for d in detalle),
              f"pliegues: el horizonte que cruza se quita y se cuenta ({quitadas})")


def probar_validaciones(m):
    """Las seis de el método §8, cada una en verde y en rojo."""
    comprobar(m.v_sin_validacion(["data/processed/fotos_riesgo_entrenamiento.parquet"])
              and not m.v_sin_validacion(["data/processed/fotos_riesgo_validacion.parquet"]), "1 sin validación: verde y rojo")
    comprobar(m.v_origen_en_matriz(["a_1"], {"a_1": "a"}, ["a"]) and not m.v_origen_en_matriz(["z_1"], {}, ["a"])
              and not m.v_origen_en_matriz(["a_1"], {"a_1": "q"}, ["a"]), "2 origen en la matriz: verde y rojo")
    cols = {"a": ["a_1", "a_2"], "b": ["b_1"]}
    comprobar(m.v_familias_enteras(["a_1", "a_2"], ["a"], cols) and not m.v_familias_enteras(["a_1"], ["a"], cols)
              and not m.v_familias_enteras(["a_1", "a_2", "b_1"], ["a"], cols), "3 familias enteras: verde y rojo")
    comprobar(m.v_tope(10, 10) and not m.v_tope(11, 10), "4 tope: verde y rojo")
    comprobar(m.v_sin_prohibidas(["a"], ["serial_number"]) and not m.v_sin_prohibidas(["falla_30d"], ["falla_30d"]),
              "5 sin prohibidas: verde y rojo")
    comprobar(m.v_lista_valida(["a"], ["a_1"]) and not m.v_lista_valida([], []) and not m.v_lista_valida(["a", "a"], ["a_1"])
              and not m.v_lista_valida(["a"], ["a_1", "a_1"]), "6 lista válida: verde y rojo")


def buscar_escritos(texto):
    """Líneas que ponen una validación a True a mano, en vez de calcularla."""
    claves = "|".join(VALIDACIONES)
    patron = re.compile(r"[\"'](" + claves + r")[\"']\s*\]?\s*[:=]\s*True\b|\b(" + claves + r")\s*=\s*True\b")
    return [(n, linea.strip()) for n, linea in enumerate(texto.splitlines(), 1) if patron.search(linea)]


def probar_escritos():
    """Ninguna validación del script lleva True puesto; la búsqueda caza una escrita a propósito."""
    hallado = buscar_escritos(SCRIPT.read_text(encoding="utf-8"))
    comprobar(hallado == [], f"ninguna validación escrita a True en el script ({hallado})")
    comprobar(len(buscar_escritos('v = {"tope": True}\nlista_valida = True')) == 2, "la búsqueda caza dos validaciones escritas a True")


def probar_importa_solo_13():
    """El script importa solo el 13 (nota de la petición, punto 1) y no abre la validación."""
    texto = SCRIPT.read_text(encoding="utf-8")
    nombrados = set(re.findall(r"scripts\W+(\d\d_\w+)\.py", texto)) | set(re.findall(r'"(\d\d_\w+)\.py"', texto))
    comprobar(nombrados <= {"13_preparacion", "14_preseleccion", "06_analisis_exploratorio"},
              f"solo se carga el script 13 ({nombrados})")
    comprobar("fotos_riesgo_validacion" not in texto, "el script no nombra el fichero de validación")


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 2 · el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
MESES = [dt.datetime(2024, m, 1) for m in range(1, 7)]
POR_MES, FALLOS_MES = 20_000, 300


def tabla_mes(esquema, mes, k, rng, fuga):
    """Un mes del caso pequeño con las 144 columnas de la tabla real; las numéricas que no se diseñan valen 0."""
    n = POR_MES
    y = np.zeros(n, dtype=np.int8); y[:FALLOS_MES] = 1; rng.shuffle(y)
    senal = np.clip(np.round(rng.normal(3 + 1.6 * y, 1.4)), 0, 9)                 # entra: separa los fallos
    oblig = np.clip(np.round(rng.normal(3 + 1.2 * y, 1.4)), 0, 9)                 # obligatoria con señal
    copia = np.where(rng.random(n) < 0.9, oblig, np.clip(oblig + rng.integers(-1, 2, n), 0, 9))   # dice lo mismo
    mod = rng.choice(np.array(["SA", "SB", "TA"]), size=n, p=[0.5, 0.2, 0.3])
    fab = np.where(np.char.startswith(mod, "S"), "Seagate", "Toshiba")
    disenadas = {
        "falla_30d": y, "fecha": np.full(n, np.datetime64(mes, "ms")),
        "horizonte_hasta": np.full(n, np.datetime64(mes + dt.timedelta(days=30), "ms")),
        "serial_number": np.char.add(f"S{k}_", np.arange(n).astype(str)), "model": mod, "fabricante": fab,
        "datacenter": rng.choice(np.array(["phx1", "sac0"]), size=n), "periodo": np.full(n, "construcción"),
        "smart_194_raw": senal, "smart_5_raw": oblig, "smart_183_raw": copia,
        "smart_12_raw": rng.integers(0, 6, n).astype(float),                          # ruido: sale
        "smart_197_raw": rng.integers(0, 6, n).astype(float),                         # obligatoria sin señal: entra
        "capacity_bytes": np.full(n, 4_000_000_000_000), "garantia_anos": np.full(n, 5)}
    if fuga:
        disenadas["smart_242_raw"] = y.astype(float)                                 # la fuga puesta a propósito
    columnas = {}
    for campo in esquema:
        v = disenadas.get(campo.name)
        if v is None:
            if pa.types.is_string(campo.type) or pa.types.is_large_string(campo.type):
                v = np.full(n, "x")
            elif pa.types.is_boolean(campo.type):
                v = np.zeros(n, dtype=bool)
            elif pa.types.is_timestamp(campo.type):
                v = np.full(n, np.datetime64(mes, "ms"))
            else:
                v = np.zeros(n)
        columnas[campo.name] = pa.array(v).cast(campo.type)
    return pa.table(columnas, schema=esquema)


def montar(fuga=False, estado_preparacion="OK", estado_matriz="aprobada por el responsable del caso el 18/11/2026 («Sí, siguiente pregunta»)"):
    """Monta tests/tmp_preseleccion/ con la tabla de entrenamiento, la matriz y preparacion.json."""
    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "data" / "processed").mkdir(parents=True)
    (TMP / "informes").mkdir()
    (TMP / "config" / "modelo").mkdir(parents=True)
    esquema = pq.read_schema(CASO / ENT).remove_metadata()
    rng = np.random.default_rng(7)
    with pq.ParquetWriter(TMP / ENT, esquema) as w:
        for k, mes in enumerate(MESES):
            w.write_table(tabla_mes(esquema, mes, k, rng, fuga), row_group_size=POR_MES)
    texto = (CASO / MATRIZ).read_text(encoding="utf-8")
    texto = re.sub(r"^estado: .*$", "estado: " + estado_matriz, texto, count=1, flags=re.M)
    (TMP / MATRIZ).write_text(texto, encoding="utf-8")
    (TMP / "informes" / "preparacion.json").write_text(json.dumps(
        {"resultado": {"estado": estado_preparacion},
         "entradas": [{"ruta": ENT, "sha256": sha256(TMP / ENT)}],
         "matriz": {"aprobada_por": "El responsable del caso", "fecha": "2026-11-18"}}, ensure_ascii=False), encoding="utf-8")


def ejecutar():
    """Ejecuta el script sobre la carpeta temporal con -W error; devuelve el código, el JSON, la salida y los segundos."""
    t0 = time.time()
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)], capture_output=True,
                       text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    segundos = time.time() - t0
    ruta = TMP / SALIDA
    js = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    if r.returncode not in (0, 2):
        print(r.stdout[-3000:]); print(r.stderr[-4000:])
    print(f"nota  ejecución del script en {segundos:.1f} s")
    comprobar(segundos <= LIMITE_S, f"la ejecución no pasa de {LIMITE_S} s ({segundos:.1f} s)")
    return r.returncode, js, r.stdout + r.stderr


def probar_caso_pequeno():
    """El verde del caso pequeño y los casos que tienen que parar."""
    montar()
    codigo, js, salida = ejecutar()
    comprobar(codigo == 0, f"pequeño: el script sale con 0 (salió con {codigo})")
    if js is None:
        comprobar(False, "pequeño: escribe informes/preseleccion.json"); print(salida[-3000:])
        return
    comprobar(js["resultado"]["estado"] in ("OK", "AVISO"), f"pequeño: estado OK o AVISO ({js['resultado']['estado']}: {js['resultado']['resumen']})")
    lo = js["familias"]["logistica"]
    fin = lo.get("variables_finales") or []
    comprobar("smart_194_raw" in fin, f"pequeño: la variable con señal entra ({fin})")
    comprobar("smart_12_raw" not in fin, "pequeño: la de ruido sale")
    comprobar("smart_197_raw" in fin and all(o in fin for o in OBLIGATORIAS), "pequeño: las obligatorias entran, también la que sale abajo")
    votos_197 = next((r["votos"] for r in lo["rankings_por_variable"] if r["origen"] == "smart_197_raw"), None)
    comprobar(votos_197 is not None and votos_197 < 2, f"pequeño: la obligatoria de ruido no llegaba por votos ({votos_197})")
    par = [p for p in lo["pares_parecidos"] if {p["columna_1"], p["columna_2"]} == {"smart_5_raw", "smart_183_raw"}]
    comprobar(len(par) == 1 and par[0]["sale"] == "smart_183_raw" and "smart_183_raw" not in fin,
              f"pequeño: de las dos que dicen lo mismo sale la que no es obligatoria ({par})")
    origen = {c: o for o in fin for c in lo["columnas_por_variable"].get(o, [])}
    comprobar(sorted(lo["columnas_finales"]) == sorted(origen), "pequeño: las columnas finales son las de las variables finales, enteras")
    for v in VALIDACIONES:
        comprobar(lo["validaciones"].get(v) is True, f"pequeño: validación {v} en verde")
    comprobar(lo["muestra"]["entera"] is True and lo["muestra"]["usada"] is True, "pequeño: la muestra no llega a 100.000 filas y se usa entera")
    comprobar(lo["muestra"]["segunda_semilla"] == 43 and lo["muestra"]["misma_lista"] in (True, False), "pequeño: la segunda muestra, con semilla 43")
    for f in ("bosque", "hgb"):
        d = js["familias"][f]
        comprobar(d["se_preselecciona"] is False and len(d["columnas_finales"]) == 64, f"pequeño: {f} sin votación y con sus 64 columnas")
    comprobar(lo["tope"]["maximo_columnas"] == 6 * FALLOS_MES // 10, "pequeño: el tope, una columna por cada 10 fallos de entrenamiento")
    comprobar(all(Path(r).name != "fotos_riesgo_validacion.parquet" for r in js["leidos"]), "pequeño: no se lee la validación")
    md = TMP / "informes" / "preseleccion.md"
    texto = md.read_text(encoding="utf-8") if md.exists() else ""
    for ap in ("¿Hacía falta?", "Lo que no podía entrar", "Alarmas de fuga", "Cómo se votó", "Una variante por variable",
               "Las que dicen lo mismo", "El tope", "Las columnas que entran", "Validaciones", "Parámetros usados",
               "Datos personales", "Límites"):
        comprobar(f"## {ap}" in texto, f"pequeño: el informe tiene el apartado «{ap}»")
    # La fuga puesta a propósito: salta la alarma y para
    montar(fuga=True)
    codigo, js, _ = ejecutar()
    comprobar(codigo == 2 and js is not None and js["resultado"]["estado"] == "PARADO", f"fuga: el script para (PARADO, código {codigo})")
    if js is not None:
        al = (js["familias"]["logistica"] or {}).get("alarmas_de_fuga") or []
        comprobar([a["columna"] for a in al] == ["smart_242_raw"] and al[0]["decision"] == "",
                  f"fuga: la alarma salta con smart_242_raw y queda sin decisión ({al})")
    # Las entradas que no están listas
    for nombre, montaje in (("preparacion.json sin OK", {"estado_preparacion": "PARADO"}),
                            ("matriz sin aprobar", {"estado_matriz": "opción, pendiente del responsable del caso"})):
        montar(**montaje)
        codigo, js, _ = ejecutar()
        comprobar(codigo == 2 and js is not None and js["resultado"]["estado"] == "PARADO", f"{nombre}: PARADO (código {codigo})")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 3 · el JSON real
# ---------------------------------------------------------------------------------------------------------------
def probar_real():
    """Si la sesión principal ya ejecutó el script, las cifras de control de la petición."""
    ruta = CASO / SALIDA
    js = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if not isinstance(js.get("familias"), dict):
        print("nota  sin informes/preseleccion.json: la parte 3 se ejecuta cuando lo escriba la sesión principal")
        return
    lo = js["familias"]["logistica"]
    comprobar(lo["muestra"]["partida"] == {"filas": 232243, "fallos": 11962, "sanas": 220281},
              f"real: muestra de partida de 232.243 fotos, 11.962 con fallo ({lo['muestra']['partida']})")
    comprobar(lo["recuento"]["variables_entrada"] == 62 and lo["recuento"]["columnas_preprocesador"] == 496,
              f"real: 62 variables y 496 columnas en la logística ({lo['recuento']})")
    comprobar(lo["tope"]["maximo_columnas"] == 1196, "real: tope de 1.196 columnas")
    comprobar(all(o in lo["variables_finales"] for o in OBLIGATORIAS), "real: las cuatro obligatorias entran")
    comprobar(all(len(js["familias"][f]["columnas_finales"]) == 64 for f in ("bosque", "hgb")), "real: árboles con 64 columnas")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"intérprete: {sys.executable}")
    try:
        m = cargar_modulo()
        if m is not None:
            probar_corte(m)
            probar_origen(m)
            probar_votacion(m)
            probar_fuga(m)
            probar_momento(m)
            probar_parecidas(m)
            probar_parecido_por_vacio(m)
            probar_tope(m)
            probar_meses(m)
            probar_pliegues(m)
            probar_validaciones(m)
            probar_escritos()
            probar_importa_solo_13()
            probar_caso_pequeno()
        probar_real()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos" if FALLOS else "\ntodo en verde")
    sys.exit(1 if FALLOS else 0)
