"""Prueba de scripts/15_modelado.py (skill aprendizaje-automatico; encargo 21, segunda y tercera parte).

Parte 1, las piezas sueltas. Carga el script como módulo (su trabajo está dentro de `if __name__ == "__main__":`) y
prueba con datos escritos aquí, cada pieza con un caso que tiene que salir bien y otro que tiene que salir mal:
  - los fallos en la lista de N, con un empate en el puesto N repartido en proporción, la regla de los cinco contadores
    con la suma vacía como 0 y el trivial, que encuentra N × la tasa;
  - los cinco bloques de tres meses;
  - el empate pliegue a pliegue, el ganador (con empate, el más estable frente al trivial) y el veredicto;
  - la recalibración por la corrección del prior;
  - el paso 1: OK sigue, AVISO sigue solo si cada pendiente tiene la decisión de Juan escrita en el script;
  - la ampliación de la rejilla por el borde;
  - el canario, la probabilidad media y el intervalo remuestreando meses;
  - la selección de la logística por variable de origen, después del preprocesador entero;
  - que ninguna validación está escrita con True puesto y que solo se carga el script 13.
Parte 2, el script entero sobre un caso pequeño en tests/tmp_modelado/, que se crea y se borra: 21 meses de
construcción con las 144 columnas de la tabla real, un horizonte que cruza el inicio de los bloques 2 y 3, el sitio
solo desde 2023-07, una preseleccion.json en AVISO con P-01 y un fichero de validación roto a propósito. Comprueba:
  - sin --abrir-validacion no abre la validación (si la abriera, el fichero roto lo haría fallar);
  - el horizonte quita lo que tiene que quitar y la muestra no toca lo medido;
  - la regla de cada mes, rehecha aquí por otro camino (ordenando con pandas), coincide con la del JSON;
  - el canario en sus dos sentidos, las validaciones y el JSON en PARADO con aprobado_por vacío;
  - las entradas que no están listas paran: PARADO o ERROR en la preselección, o un pendiente sin decisión.
Parte 3, la validación con un caso pequeño: sin aprobado_por para; con él, la abre una vez, da el intervalo de los 12
meses y una segunda apertura para sin tocar la competición.

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
SCRIPT = CASO / "scripts" / "15_modelado.py"
TMP = CASO / "tests" / "tmp_modelado"
MATRIZ = "contexto-proyecto/modelo/matriz_transformaciones.md"
ENT = "data/processed/fotos_riesgo_entrenamiento.parquet"
VAL = "data/processed/fotos_riesgo_validacion.parquet"
SALIDA = "informes/modelado.json"
LIMITE_S = 150
FALLOS = []
# Las validaciones del skill §9 que el script calcula
VALIDACIONES = ["sin_filas_de_ajuste", "semillas", "validacion_una_vez", "con_probabilidad", "columnas_de_preseleccion",
                "recalibrado_si_hace_falta", "citas_existen", "reproducible", "sin_identificadores_ni_posteriores",
                "sin_resultados_escritos", "canario_objetivo_barajado", "probabilidad_media_cerca_de_la_tasa",
                "objetivo_conocido_al_entrenar"]


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
    spec = importlib.util.spec_from_file_location("modelado_15", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["modelado_15"] = modulo
    try:
        spec.loader.exec_module(modulo)
    except Exception as e:  # noqa: BLE001 - la prueba dice qué falló al cargar
        comprobar(False, f"el script carga como módulo ({type(e).__name__}: {e})")
        return None
    return modulo


# ---------------------------------------------------------------------------------------------------------------
# 2. Parte 1 · las piezas
# ---------------------------------------------------------------------------------------------------------------
def probar_listas(m):
    """Fallos en la lista de N con empates, la regla y el trivial."""
    # Empate en el puesto 3: el grupo de 2 entra entero y del grupo de 3 (2 fallos) se lleva 1 plaza: 1 + 2/3
    f = m.fallos_en_lista([np.array([3, 3, 2, 2, 2, 1.0])], np.array([1, 0, 1, 1, 0, 0]), 3)
    comprobar(abs(f - (1 + 2 / 3)) < 1e-12, f"lista: el empate en el puesto N se reparte en proporción ({f})")
    comprobar(m.fallos_en_lista([np.array([5, 4, 3.0])], np.array([1, 1, 0]), 10) == 2, "lista: con menos filas que N, todos los fallos")
    # La regla: por contadores y, a igualdad, por la suma; una suma vacía cuenta como 0
    claves = m.claves_regla(pd.DataFrame({"contadores_que_avisan": [1, 1, 1, 0], "suma_contadores_sin_188": [5.0, 2, 2, 9]}))
    comprobar(m.fallos_en_lista(claves, np.array([0, 1, 0, 1]), 2) == 0.5, "regla: a igual contador ordena por la suma y reparte el empate")
    claves = m.claves_regla(pd.DataFrame({"contadores_que_avisan": [1, 1], "suma_contadores_sin_188": [np.nan, 3.0]}))
    comprobar(m.fallos_en_lista(claves, np.array([1, 0]), 1) == 0, "regla: la suma vacía cuenta como 0 y no pasa delante")
    comprobar(abs(m.fallos_en_lista([np.full(10, 0.1)], np.array([1, 1] + [0] * 8), 5) - 1.0) < 1e-12, "trivial: N × la tasa del mes")


def probar_bloques(m):
    """Los cinco bloques de tres meses de la skill §3 y del encargo."""
    comprobar([(a, b) for a, b in m.BLOQUES] == [("2023-04-01", "2023-06-30"), ("2023-07-01", "2023-09-30"),
                                                 ("2023-10-01", "2023-12-31"), ("2024-01-01", "2024-03-31"),
                                                 ("2024-04-01", "2024-06-30")], "bloques: los cinco del encargo")


def probar_empate_y_ganador(m):
    """El empate pliegue a pliegue, el ganador y el veredicto frente a la regla."""
    e = m.empate(np.array([10, 11, 12, 13, 14.0]), np.array([9, 10, 11, 12, 13.0]))
    comprobar(not e["empatan"] and e["media"] == 1.0, "empate: siempre 1 por encima no empata")
    e = m.empate(np.array([10, 12, 9, 13, 11.0]), np.array([11, 10, 10, 12, 12.0]))
    comprobar(e["empatan"], "empate: diferencias que cambian de signo empatan")
    triv = np.full(5, 0.1)
    g, _ = m.elegir_ganador({"logistica": np.full(5, 10.0), "hgb": np.full(5, 12.0),
                             "bosque": np.array([11.9, 12.2, 11.8, 12.1, 12.0])}, triv)
    comprobar(g == "hgb", f"ganador: con empate, el más estable frente al trivial ({g})")
    g, _ = m.elegir_ganador({"a": np.array([20, 30, 20, 30, 20.0]), "b": np.full(5, 10.0)}, triv)
    comprobar(g == "a", f"ganador: el mejor gana aunque sea menos estable ({g})")
    comprobar(m.veredicto(np.full(5, 30.0), np.full(5, 20.0)) == "supera"
              and m.veredicto(np.array([30, 10, 30, 10, 20.0]), np.full(5, 20.0)) == "no se puede afirmar"
              and m.veredicto(np.full(5, 10.0), np.full(5, 20.0)) == "no supera", "veredicto: supera, empate y no supera")


def probar_recalibrar(m):
    """La corrección del prior sobre el logit recoloca la probabilidad sin cambiar el orden."""
    p = np.array([0.2, 0.5, 0.9])
    r = m.recalibrar(p, 0.5, 0.001)
    comprobar(abs(r[1] - 0.001) < 1e-6 and np.all(np.diff(r) > 0), f"recalibrar: 0,5 con el prior de la muestra pasa a la tasa real ({r})")
    comprobar(np.allclose(m.recalibrar(p, 0.3, 0.3), p), "recalibrar: con la misma tasa no cambia nada")


def probar_paso_1(m):
    """OK sigue; AVISO sigue si cada pendiente tiene su decisión en el script; lo demás para."""
    ok, _ = m.preseleccion_lista({"resultado": {"estado": "OK"}, "pendientes": []})
    comprobar(ok, "paso 1: OK sigue")
    ok, _ = m.preseleccion_lista({"resultado": {"estado": "AVISO"}, "pendientes": [{"id": "P-01"}]})
    comprobar(ok and "P-01" in m.DECISIONES_DE_JUAN, "paso 1: AVISO con P-01, decidido por Juan, sigue")
    ok, motivo = m.preseleccion_lista({"resultado": {"estado": "AVISO"}, "pendientes": [{"id": "P-01"}, {"id": "P-02"}]})
    comprobar(not ok and "P-02" in motivo, "paso 1: un pendiente sin decisión para")
    for estado in ("PARADO", "ERROR", None):
        ok, _ = m.preseleccion_lista({"resultado": {"estado": estado}, "pendientes": []})
        comprobar(not ok, f"paso 1: {estado} para")


def probar_ampliar(m):
    """Si el mejor valor cae en el borde de su rejilla, se amplía por ese lado (skill §5)."""
    c = m.ESPACIOS["logistica"]["C"]
    nuevo = m.ampliar("logistica", "C", c[-1])
    comprobar(nuevo is not None and nuevo > c[-1], f"ampliar: C en el borde de arriba sube ({nuevo})")
    comprobar(m.ampliar("logistica", "C", c[5]) is None, "ampliar: un valor de dentro no amplía")
    comprobar(m.ampliar("bosque", "max_depth", 15) == 20 and m.ampliar("bosque", "n_estimators", 500) is None,
              "ampliar: la profundidad sube; los árboles no (más árboles solo cuestan tiempo)")
    comprobar(m.ampliar("hgb", "learning_rate", 0.1) == 0.2 and m.ampliar("hgb", "max_iter", 100) == 50
              and m.ampliar("hgb", "max_depth", None) is None, "ampliar: el boosting por los dos lados, sin límite no amplía")


def probar_controles(m):
    """El canario, la probabilidad media y el intervalo de los meses."""
    comprobar(m.v_canario(0.2, 0.13, 96.0, 100.0), "canario: verde si barajado cae al trivial y la fuga sube")
    comprobar(not m.v_canario(20.0, 0.13, 96.0, 100.0), "canario: rojo si con el objetivo barajado sigue encontrando")
    comprobar(not m.v_canario(0.2, 0.13, 40.0, 100.0), "canario: rojo si la fuga no sube")
    comprobar(m.v_prob_media(0.00110, 0.00100) and not m.v_prob_media(0.00130, 0.00100), "probabilidad media: 20 % relativo")
    i = m.intervalo_meses(np.full(12, 5.0))
    comprobar(i["bajo"] == 5.0 and i["alto"] == 5.0 and i["remuestreos"] == 1000 and i["unidades"] == 12, "intervalo: sin variación, un punto")
    d = np.array([5, -3, 8, 2, 0, 4, 6, -1, 3, 7, 1, 2.0])
    a, b = m.intervalo_meses(d), m.intervalo_meses(d)
    comprobar(a["bajo"] < a["alto"] and a == b, "intervalo: con variación tiene anchura y se repite con la semilla")


def probar_seleccion(m):
    """La logística se queda con las columnas cuyo origen está en las variables finales."""
    mz = m.P13.leer_matriz((CASO / MATRIZ).read_text(encoding="utf-8"))
    pat = m.patrones_logistica(mz)
    cols = ["smart_5_raw_disc_cs_1", "smart_5_raw_disc_cs_vacio", "smart_1_raw_disc_cs_2", "fabricante_ohe_HGST", "model_ohe_X"]
    comprobar(m.columnas_de(cols, ["smart_5_raw", "model"], pat) == ["smart_5_raw_disc_cs_1", "smart_5_raw_disc_cs_vacio", "model_ohe_X"],
              "selección: solo las columnas de las variables finales, enteras")
    comprobar(m.columnas_de(cols, ["smart_1_raw"], pat) == ["smart_1_raw_disc_cs_2"], "selección: fabricante no sale si no entra")


def buscar_escritos(texto):
    """Líneas que ponen una validación a True a mano, en vez de calcularla."""
    claves = "|".join(VALIDACIONES)
    patron = re.compile(r"[\"'](" + claves + r")[\"']\s*\]?\s*[:=]\s*True\b|\b(" + claves + r")\s*=\s*True\b")
    return [(n, linea.strip()) for n, linea in enumerate(texto.splitlines(), 1) if patron.search(linea)]


def probar_codigo(m):
    """Ninguna validación con True puesto; el script la busca en sí mismo; solo carga el 13."""
    texto = SCRIPT.read_text(encoding="utf-8")
    comprobar(buscar_escritos(texto) == [], f"ninguna validación escrita a True en el script ({buscar_escritos(texto)})")
    comprobar(m.escritos_en_codigo(texto) == [] and len(m.escritos_en_codigo('v = {"reproducible": True}')) == 1,
              "validación 10: el script caza una validación escrita a True")
    nombrados = set(re.findall(r"scripts\W+(\d\d_\w+)\.py", texto)) | set(re.findall(r'"(\d\d_\w+)\.py"', texto))
    comprobar(nombrados <= {"13_preparacion", "14_preseleccion", "15_modelado"}, f"solo se carga el script 13 ({nombrados})")
    comprobar("14_preseleccion.py\")" not in texto and "spec_from_file_location" in texto, "no se importa el 14")


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 2 · el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
MESES_ENT = [dt.datetime(2022, 10, 1) + pd.DateOffset(months=k) for k in range(21)]          # 2022-10 a 2024-06
MESES_VAL = [dt.datetime(2024, 7, 1) + pd.DateOffset(months=k) for k in range(12)]           # 2024-07 a 2025-06
POR_MES, FALLOS_MES = 3000, 60
FINALES = ["smart_194_raw", "smart_5_raw", "smart_187_raw", "smart_197_raw", "smart_198_raw", "datacenter", "contadores_que_avisan"]


def tabla_mes(esquema, mes, k, rng, n, fallos, fin_de_parte):
    """Un mes con las 144 columnas de la tabla real; las numéricas que no se diseñan valen 0."""
    mes = pd.Timestamp(mes).to_pydatetime()
    y = np.zeros(n, dtype=np.int8); y[:fallos] = 1; rng.shuffle(y)
    cont = ((rng.random(n) < 0.05 + 0.3 * y) * rng.integers(1, 3, n)).astype(np.int64)
    suma = cont * rng.integers(1, 40, n).astype(float)
    suma[rng.random(n) < 0.03] = np.nan
    horizonte = min(mes + dt.timedelta(days=30), fin_de_parte)
    mod = rng.choice(np.array(["SA", "SB", "TA"]), size=n, p=[0.5, 0.2, 0.3])
    sitio = rng.choice(np.array(["phx1", "sac0"]), size=n) if mes >= dt.datetime(2023, 7, 1) else np.full(n, None)
    disenadas = {
        "falla_30d": y, "fecha": np.full(n, np.datetime64(mes, "ms")), "horizonte_hasta": np.full(n, np.datetime64(horizonte, "ms")),
        "serial_number": np.char.add(f"S{k}_", np.arange(n).astype(str)), "model": mod,
        "fabricante": np.where(np.char.startswith(mod, "S"), "Seagate", "Toshiba"), "datacenter": sitio,
        "periodo": np.full(n, "construcción"), "contadores_que_avisan": cont, "suma_contadores_sin_188": suma, "avisa": cont > 0,
        "smart_194_raw": np.clip(np.round(rng.normal(3 + 2.5 * y, 1.2)), 0, 9),
        "smart_5_raw": np.clip(np.round(rng.normal(3 + 2.0 * y, 1.2)), 0, 9),
        "smart_187_raw": rng.integers(0, 4, n).astype(float), "smart_197_raw": rng.integers(0, 4, n).astype(float),
        "smart_198_raw": rng.integers(0, 4, n).astype(float),
        "capacity_bytes": np.full(n, 4_000_000_000_000), "garantia_anos": np.full(n, 5),
        # Como en los datos reales: smart_90_raw no tiene ningún dato antes de mayo de 2023, así que llega vacía entera
        # al entrenamiento del pliegue 1 (el HistGradientBoosting no puede hacer tramos de una columna sin datos)
        "smart_90_raw": np.full(n, np.nan) if mes < dt.datetime(2023, 5, 1) else rng.integers(0, 3, n).astype(float)}
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
        columnas[campo.name] = pa.array(v, from_pandas=True).cast(campo.type)
    return pa.table(columnas, schema=esquema)


def escribir_validacion(rota):
    """El fichero de validación: roto a propósito (si se abre, falla) o un caso pequeño de 12 meses."""
    ruta = TMP / VAL
    if rota:
        ruta.write_bytes(b"esto no es un parquet: si el script lo abre, falla")
        return
    esquema = pq.read_schema(CASO / ENT).remove_metadata()
    rng = np.random.default_rng(11)
    with pq.ParquetWriter(ruta, esquema) as w:
        for k, mes in enumerate(MESES_VAL):
            w.write_table(tabla_mes(esquema, mes, 100 + k, rng, 2000, 30, dt.datetime(2025, 6, 30)), row_group_size=2000)


def montar(estado="AVISO", pendientes=("P-01",)):
    """Monta tests/tmp_modelado/ con entrenamiento, la validación rota, la matriz y preseleccion.json."""
    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "data" / "processed").mkdir(parents=True)
    (TMP / "informes").mkdir()
    (TMP / "contexto-proyecto" / "modelo").mkdir(parents=True)
    esquema = pq.read_schema(CASO / ENT).remove_metadata()
    rng = np.random.default_rng(7)
    with pq.ParquetWriter(TMP / ENT, esquema) as w:
        for k, mes in enumerate(MESES_ENT):
            w.write_table(tabla_mes(esquema, mes, k, rng, POR_MES, FALLOS_MES, dt.datetime(2024, 6, 30)), row_group_size=POR_MES)
    escribir_validacion(rota=True)
    texto = (CASO / MATRIZ).read_text(encoding="utf-8")
    texto = re.sub(r"^estado: .*$", "estado: aprobada por Juan el 18/11/2026 («Sí, siguiente pregunta»)", texto, count=1, flags=re.M)
    (TMP / MATRIZ).write_text(texto, encoding="utf-8")
    m13 = importlib.util.spec_from_file_location("p13_prueba", CASO / "scripts" / "13_preparacion.py")
    p13 = importlib.util.module_from_spec(m13); m13.loader.exec_module(p13)
    pres = {"resultado": {"estado": estado}, "pendientes": [{"id": p} for p in pendientes],
            "entradas": [{"ruta": ENT, "sha256": sha256(TMP / ENT)}],
            "familias": {"logistica": {"se_preselecciona": True, "variables_finales": FINALES},
                         "bosque": {"se_preselecciona": False, "columnas_finales": p13.NUM_ARBOLES + p13.NOMINALES},
                         "hgb": {"se_preselecciona": False, "columnas_finales": p13.NUM_ARBOLES + p13.NOMINALES}}}
    (TMP / "informes" / "preseleccion.json").write_text(json.dumps(pres, ensure_ascii=False), encoding="utf-8")


def ejecutar(*extra):
    """Ejecuta el script sobre la carpeta temporal con -W error; devuelve el código, el JSON y la salida."""
    t0 = time.time()
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP), "--candidatos", "2", *extra],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    segundos = time.time() - t0
    ruta = TMP / SALIDA
    js = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    if r.returncode not in (0, 2):
        print(r.stdout[-3000:]); print(r.stderr[-4000:])
    print(f"nota  ejecución del script en {segundos:.1f} s")
    comprobar(segundos <= LIMITE_S, f"la ejecución no pasa de {LIMITE_S} s ({segundos:.1f} s)")
    return r.returncode, js, r.stdout + r.stderr


def regla_por_otro_camino(n=100):
    """Los fallos de la regla en la lista de N de cada mes medido, ordenando con pandas y sin las funciones del script."""
    df = pq.read_table(TMP / ENT, columns=["fecha", "falla_30d", "contadores_que_avisan", "suma_contadores_sin_188"]).to_pandas()
    df["s"] = df["suma_contadores_sin_188"].fillna(0)
    salida = {}
    for mes, g in df[df["fecha"] >= "2023-04-01"].groupby("fecha"):
        t = g.groupby(["contadores_que_avisan", "s"])["falla_30d"].agg(["size", "sum"]).sort_index(ascending=False)
        quedan, fallos = n, 0.0
        for _, fila in t.iterrows():
            toma = min(quedan, fila["size"])
            fallos += fila["sum"] * toma / fila["size"]
            quedan -= toma
            if quedan == 0:
                break
        salida[str(mes)[:7]] = fallos
    return salida


def probar_caso_pequeno():
    """La competición del caso pequeño, parada antes de la validación, y las entradas que no están listas."""
    montar()
    codigo, js, salida = ejecutar()
    if js is None:
        comprobar(False, "pequeño: escribe informes/modelado.json"); print(salida[-3000:])
        return None
    comprobar(js["resultado"]["estado"] == "PARADO" and js["ganador"]["aprobado_por"] == "",
              f"pequeño: PARADO con aprobado_por vacío ({js['resultado']['estado']}: {js['resultado']['resumen'][:300]})")
    comprobar(all(Path(r).name != "fotos_riesgo_validacion.parquet" for r in js["leidos"]) and js["validacion"]["abierta_una_vez"] is None,
              "pequeño: sin --abrir-validacion no abre la validación (el fichero roto no se tocó)")
    # El horizonte y la muestra
    q = {d["entrenamiento"]: d for d in js["validacion_cruzada"]["objetivo_sin_conocer"]}
    comprobar(q["pliegue que mide 2023-07-01"]["filas_quitadas"] == POR_MES and q["pliegue que mide 2023-10-01"]["filas_quitadas"] == POR_MES
              and q["pliegue que mide 2023-04-01"]["filas_quitadas"] == 0 and q["pliegue que mide 2024-04-01"]["filas_quitadas"] == 0,
              f"pequeño: el horizonte quita junio y septiembre de 2023 en los pliegues 2 y 3 ({[d['filas_quitadas'] for d in q.values()]})")
    comprobar(q["pliegue que mide 2023-07-01"]["eventos_quitados"] == FALLOS_MES, "pequeño: y cuenta sus fallos")
    comprobar(q["ajuste final"]["filas_quitadas"] == 0, "pequeño: el ajuste final no quita nada (junio de 2024 está recortado)")
    pl = js["validacion_cruzada"]["pliegues_detalle"]
    comprobar(all(p["filas_mide"] == 3 * POR_MES and p["fallos_mide"] == 3 * FALLOS_MES for p in pl),
              "pequeño: la muestra no toca lo medido (cada bloque se mide entero)")
    comprobar(all(p["muestra"]["fallos"] == p["fallos_entrena"] for p in pl), "pequeño: la muestra conserva todos los fallos que entrenan")
    # La regla por otro camino
    otra = regla_por_otro_camino()
    del_json = {r["mes"][:7]: r["lista_100"] for r in js["referencias_por_mes"]["regla"]}
    comprobar(set(otra) == set(del_json) and all(abs(otra[k] - del_json[k]) < 1e-9 for k in otra),
              "pequeño: la regla de cada mes coincide con la rehecha por otro camino")
    # Las validaciones calculadas
    for v in VALIDACIONES:
        val = js["validaciones"].get(v)
        if v == "probabilidad_media_cerca_de_la_tasa":
            continue
        comprobar(val is True, f"pequeño: validación {v} en verde ({val})")
    # La validación 12 se calcula; si sale en rojo, para en PARADO, lo dice y conserva el ganador (su verde y su
    # rojo, como pieza, están en probar_controles). Si sale en verde, para en la puerta de Juan con código 0.
    v12 = js["validaciones"].get("probabilidad_media_cerca_de_la_tasa")
    comprobar(v12 in (True, False) and len(js["probabilidad_media_por_bloque"]) == 5, f"pequeño: la validación 12 se calcula por bloque ({v12})")
    if v12 is False:
        comprobar(codigo == 2 and "probabilidad media" in js["resultado"]["resumen"], f"pequeño: la 12 en rojo para y lo dice (código {codigo})")
        print("nota  en el caso pequeño la probabilidad media recalibrada queda lejos de la tasa: " +
              str([(b["bloque"], round(b["probabilidad_media"], 4), b["tasa_real"]) for b in js["probabilidad_media_por_bloque"]]))
    else:
        comprobar(codigo == 0, f"pequeño: sale con 0 en la puerta (salió con {codigo})")
    vacias = js.get("columnas_sin_dato_al_ajustar") or []
    comprobar(any(v["familia"] == "hgb" and "smart_90_raw" in v["columnas"] for v in vacias),
              f"pequeño: la columna sin ningún dato en el pliegue 1 sale de ese ajuste y se apunta ({vacias})")
    can = js.get("canario") or {}
    comprobar(bool(can) and can["barajado"]["lista_100"] is not None and can["fuga"]["lista_100"] is not None,
              f"pequeño: el canario en sus dos sentidos ({can})")
    comprobar(js["ganador"].get("algoritmo") in ("logistica", "bosque", "hgb") and js["ganador"].get("hiperparametros"),
              "pequeño: el ganador con su receta")
    imp = {v["columna"]: v["importancia"] for v in (js.get("importancias") or {}).get("valores", [])}
    # Con max_samples, scikit-learn medía la partida en todo el bloque y la permutada en una parte: todo el ruido salía
    # en −0,095. Ahora el ruido queda cerca de 0 (unos 45 fallos en el trozo dan una holgura de unas centésimas)
    ruido = [imp.get(c, -1.0) for c in ("smart_187_raw", "smart_197_raw", "smart_198_raw")]
    senal = imp.get("smart_194_raw", 0)
    comprobar(senal > 0.05 and max(abs(r) for r in ruido) < senal / 5 and min(ruido) > -0.05,
              f"pequeño: en la permutación pesa la de señal y el ruido queda cerca de 0, sin sesgo negativo (señal {senal}, ruido {ruido})")
    if js["resultado"]["estado"] != "PARADO":
        return None
    comprobar((TMP / "informes" / "modelado_busqueda.csv").exists(), "pequeño: escribe la tabla de lo probado")
    tabla = pd.read_csv(TMP / "informes" / "modelado_busqueda.csv")
    comprobar(set(tabla["algoritmo"]) == {"logistica", "bosque", "hgb"} and {"cv_media", "cv_desviacion", "entrenamiento_media", "posicion"} <= set(tabla.columns),
              "pequeño: una fila por candidato, de los tres algoritmos")
    comprobar(js["sitio"]["meses"] == 12 and js["sitio"]["entra"] in (True, False), "pequeño: el sitio se mide en 12 meses")
    md = (TMP / "informes" / "modelado.md").read_text(encoding="utf-8") if (TMP / "informes" / "modelado.md").exists() else ""
    for ap in ("Lo aprobado antes de entrenar", "Qué se probó y cuánto costó", "El desequilibrio", "Ranking", "El ganador y por qué",
               "Qué variables pesan", "La validación", "¿Se da por bueno?", "Las tres vías de mejora", "Validaciones",
               "Parámetros usados", "Datos personales", "Límites"):
        comprobar(f"## {ap}" in md, f"pequeño: el informe tiene el apartado «{ap}»")
    return js


def probar_validacion(js_competicion):
    """La tercera parte con el caso pequeño: sin aprobar para; aprobada, una vez; la segunda vez para."""
    codigo, js, _ = ejecutar("--abrir-validacion")
    comprobar(codigo == 2 and js["resultado"]["estado"] == "PARADO" and js["validacion"]["abierta_una_vez"] is None,
              f"validación: sin aprobado_por no se abre (código {codigo})")
    comprobar(js["ranking"] == js_competicion["ranking"], "validación: la parada no toca la competición")
    js["ganador"]["aprobado_por"] = "Juan (prueba)"
    (TMP / SALIDA).write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    escribir_validacion(rota=False)
    codigo, js, salida = ejecutar("--abrir-validacion")
    comprobar(codigo == 0, f"validación: con aprobado_por se abre (código {codigo})")
    if js is None or js.get("validacion", {}).get("abierta_una_vez") is not True:
        comprobar(False, "validación: queda abierta una vez"); print(salida[-3000:])
        return
    v = js["validacion"]
    comprobar(v["filas"] == 12 * 2000 and VAL in js["leidos"], "validación: lee las 12 partes del caso pequeño")
    i = v["intervalo"]
    comprobar(i["unidad"] == "mes" and i["unidades"] == 12 and i["remuestreos"] == 1000 and i["bajo"] is not None and i["bajo"] <= i["alto"],
              f"validación: el intervalo remuestrea los 12 meses ({i})")
    comprobar(v["se_da_por_bueno"] in (True, False) and v["frente_al_trivial"] in ("supera", "no supera", "no se puede afirmar"),
              "validación: dice si se da por bueno y el veredicto frente al trivial")
    comprobar(len(v["por_mes"]) == 12 and all("regla_lista_100" in r and "modelo_lista_100" in r for r in v["por_mes"]),
              "validación: el modelo y la regla en las mismas fotos de cada mes")
    comprobar(js["ranking"] == js_competicion["ranking"], "validación: la competición queda igual")
    codigo, js2, _ = ejecutar("--abrir-validacion")
    comprobar(codigo == 2 and js2["resultado"]["estado"] == "PARADO" and js2["validacion"]["abierta_una_vez"] is True
              and js2["validacion"]["por_mes"] == v["por_mes"], "validación: una segunda apertura para y no cambia nada")


def probar_entradas():
    """La preselección que no está lista para el script en PARADO."""
    for nombre, montaje in (("preselección en PARADO", {"estado": "PARADO", "pendientes": ()}),
                            ("preselección en ERROR", {"estado": "ERROR", "pendientes": ()}),
                            ("un pendiente sin decisión de Juan", {"estado": "AVISO", "pendientes": ("P-01", "P-02")})):
        montar(**montaje)
        codigo, js, _ = ejecutar()
        comprobar(codigo == 2 and js is not None and js["resultado"]["estado"] == "PARADO", f"{nombre}: PARADO (código {codigo})")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 4 · el JSON real, si la sesión principal ya ejecutó la competición
# ---------------------------------------------------------------------------------------------------------------
CONTROL_PLIEGUES = [  # fotos y fallos que miden; que entrenan antes de la muestra; que quita el horizonte (encargo 21)
    (717312, 1297, 7103763, 6760, 0, 0), (752057, 905, 7579846, 7749, 241229, 308), (795015, 994, 8316843, 8673, 256289, 289),
    (814408, 906, 9368147, 9956, 0, 0), (843497, 1100, 10182555, 10862, 0, 0)]
CONTROL_REGLA_100 = [20, 28, 34, 17, 26, 18, 30, 24, 19, 19, 20, 10, 12, 15, 15]
CONTROL_REGLA_20 = [7, 9, 12, 8, 7, 5, 12, 4, 7, 7, 6, 4, 4, 5, 6]


def probar_real():
    """Las cifras de control del encargo contra informes/modelado.json real, si existe."""
    ruta = CASO / SALIDA
    js = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if not isinstance(js.get("validacion_cruzada"), dict):
        print("nota  sin informes/modelado.json de la competición: esta parte se ejecuta cuando lo escriba la sesión principal")
        return
    pl = js["validacion_cruzada"]["pliegues_detalle"]
    hallado = [(p["filas_mide"], p["fallos_mide"], p["filas_entrena"], p["fallos_entrena"], p["filas_quitadas"], p["fallos_quitados"]) for p in pl]
    comprobar(hallado == CONTROL_PLIEGUES, f"real: los cinco pliegues, como las cifras de control ({hallado})")
    regla = js["referencias_por_mes"]["regla"]
    comprobar([round(r["lista_100"]) for r in regla] == CONTROL_REGLA_100, f"real: la regla en la lista de 100 ({[r['lista_100'] for r in regla]})")
    comprobar([round(r["lista_20"]) for r in regla] == CONTROL_REGLA_20, f"real: la regla en la lista de 20 ({[r['lista_20'] for r in regla]})")
    comprobar(js["validacion"]["abierta_una_vez"] in (None, True) and VAL not in js["leidos"][:-1], "real: la validación no se abrió en la competición")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"intérprete: {sys.executable}")
    try:
        m = cargar_modulo()
        if m is not None:
            probar_listas(m)
            probar_bloques(m)
            probar_empate_y_ganador(m)
            probar_recalibrar(m)
            probar_paso_1(m)
            probar_ampliar(m)
            probar_controles(m)
            probar_seleccion(m)
            probar_codigo(m)
            js = probar_caso_pequeno()
            if js is not None:
                probar_validacion(js)
            probar_entradas()
        probar_real()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos" if FALLOS else "\ntodo en verde")
    sys.exit(1 if FALLOS else 0)
