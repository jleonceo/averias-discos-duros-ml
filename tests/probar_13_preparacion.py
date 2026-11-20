"""Prueba de scripts/13_preparacion.py (método preparacion-modelo §4 y §5; petición 20, tercera parte).

Parte 1, las piezas sueltas. Carga el script como módulo (su trabajo está dentro de `if __name__ == "__main__":`) y
prueba con datos pequeños escritos aquí:
  - los tramos de la logística: cada tramo aprendido llega al mínimo; el 0 y un valor dominante van aparte; el vacío
    es tramo propio si llega al mínimo y va a la referencia si no llega o si lo lleva otra variable; un valor por encima
    del máximo cae en el último tramo; smart_1_raw y smart_7_raw aprenden solo con Seagate y los demás fabricantes van a
    la referencia;
  - la agrupación de raras: rara a «otras», nueva a «otras» si existe y, si no, a la referencia, y el vacío a «sin dato»;
  - una columna por categoría menos la de referencia, que es la de más filas;
  - los tres preprocesadores sin ajustar, con remainder="drop" y salida de pandas;
  - las diez validaciones, cada una con un caso que da verde y otro que tiene que dar rojo (error 24);
  - la búsqueda de validaciones escritas con True puesto.
Parte 2, el script entero sobre un caso pequeño, en tests/tmp_preparacion/: las dos partes con las 144 columnas de la
tabla real (tipos tomados con read_schema, sin cargar datos), una copia de la matriz aprobada con su estado escrito en
la copia y un informes/particion.json con las huellas. Comprueba el verde y cinco casos que tienen que parar:
  - la matriz sin aprobar: PARADO;
  - la huella de entrenamiento distinta de la de particion.json: PARADO;
  - una columna de más en la tabla, que no está en la matriz: ERROR, la décima en rojo;
  - las listas del script distintas de la matriz (avisa marcada para la logística en la copia): ERROR, la décima en rojo;
  - «sin dato» como centro real en entrenamiento: ERROR, relleno_sin_choque en rojo.
Parte 3, el JSON real, si la sesión principal ya ejecutó el script: las cifras de control de la petición (la muestra con
todos los fallos, las filas de validación y los 3 modelos nuevos con 19.757 fotos) y las referencias de la matriz.

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
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "13_preparacion.py"
TMP = CASO / "tests" / "tmp_preparacion"
MATRIZ = "config/modelo/matriz_transformaciones.md"
ENT = "data/processed/fotos_riesgo_entrenamiento.parquet"
VAL = "data/processed/fotos_riesgo_validacion.parquet"
SALIDA = "informes/preparacion.json"
VALIDACIONES = ["filas", "sin_objetivo", "sin_intermedias", "sin_vacios", "nombres_unicos", "sin_redundancia",
                "columnas_esperadas", "relleno_sin_choque", "escalado_segun_matriz", "columnas_en_matriz"]
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
    spec = importlib.util.spec_from_file_location("preparacion_13", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["preparacion_13"] = modulo
    try:
        spec.loader.exec_module(modulo)
    except Exception as e:  # noqa: BLE001 - la prueba dice qué falló al cargar
        comprobar(False, f"el script carga como módulo ({type(e).__name__}: {e})")
        return None
    return modulo


# ---------------------------------------------------------------------------------------------------------------
# 2. Parte 1 · los tramos, las categorías y los preprocesadores
# ---------------------------------------------------------------------------------------------------------------
def probar_tramos(m):
    """Los tramos de la logística, con datos que se saben a mano."""
    rng = np.random.default_rng(42)
    n = 3000
    x = np.where(rng.random(n) < 0.4, 0.0, rng.integers(1, 500, n).astype(float))
    x[rng.random(n) < 0.15] = 100.0                      # un valor dominante, distinto de 0
    y = (rng.random(n) < 0.25).astype(int)
    vac = np.zeros(n, bool); vac[:200] = True             # 200 vacíos con unos 50 fallos: llega al mínimo
    x2 = x.copy(); x2[vac] = np.nan
    x3 = x.copy(); x3[:10] = np.nan                       # 10 vacíos: no llega
    fab = np.where(np.arange(n) % 2 == 0, "Seagate", "Toshiba")
    s1 = np.where(fab == "Seagate", rng.integers(100, 200, n), 0).astype(float)
    X = pd.DataFrame({"a": x2, "b": x3, "c": x2.copy(), "smart_1_raw": s1, "fabricante": fab})
    t = m.Tramos(columnas_vacio_a_referencia=("c",), columnas_solo_seagate=("smart_1_raw",)).fit(X, y)
    Z = t.transform(X)
    comprobar(isinstance(Z, pd.DataFrame) and len(Z) == n and list(Z.index) == list(X.index), "tramos: mismas filas e índice")
    comprobar(not Z.isna().any().any(), "tramos: sin vacíos en la salida")
    comprobar("fabricante" not in Z.columns and list(Z.columns) == list(t.get_feature_names_out()), "tramos: fabricante no sale y los nombres son los declarados")
    # Cada tramo aprendido llega al mínimo en los datos del ajuste
    for col in ("a", "b"):
        idx = t.tramo_de(col, X[col].to_numpy(dtype=float))
        validos = ~np.isnan(X[col].to_numpy(dtype=float))
        bien = True
        for i in range(t.n_tramos_[col]):
            s = validos & (idx == i)
            bien &= s.sum() >= 30 and y[s].sum() >= 20 and (s.sum() - y[s].sum()) >= 20
        comprobar(bien, f"tramos: cada tramo de {col} llega a 30 fotos, 20 fallos y 20 sanas")
    tr = t.tramos_["a"]
    comprobar(any(r["desde"] == 0 and r["hasta"] == 0 for r in tr), "tramos: el 0 va aparte")
    comprobar(any(r["desde"] == 100 and r["hasta"] == 100 for r in tr), "tramos: un valor con más del 10 % va aparte")
    comprobar(t.vacio_columna_["a"] and "a_disc_cs_vacio" in Z.columns, "tramos: un vacío que llega al mínimo es su propio tramo")
    comprobar(not t.vacio_columna_["b"] and "b_disc_cs_vacio" not in Z.columns, "tramos: un vacío que no llega va a la referencia")
    comprobar(not t.vacio_columna_["c"] and "c_disc_cs_vacio" not in Z.columns, "tramos: un vacío que lleva otra variable va a la referencia")
    filas_b = Z[[k for k in Z.columns if k.startswith("b_disc_cs_")]]
    comprobar((filas_b.iloc[:10].sum(axis=1) == 0).all(), "tramos: las filas del vacío que va a la referencia salen todo a cero")
    alto = pd.DataFrame({"a": [1e9], "b": [1e9], "c": [1e9], "smart_1_raw": [1e9], "fabricante": ["Seagate"]})
    za = t.transform(alto)
    ult = f"a_disc_cs_{t.n_tramos_['a'] - 1}"
    comprobar((t.referencia_["a"] == t.n_tramos_["a"] - 1 and za.filter(like="a_disc_cs_").sum(axis=1).iloc[0] == 0)
              or (ult in za.columns and za[ult].iloc[0] == 1), "tramos: un valor por encima del máximo cae en el último tramo")
    comprobar(min(r["desde"] for r in t.tramos_["smart_1_raw"]) >= 100, "tramos: smart_1_raw aprende solo con las fotos de Seagate")
    s_cols = [k for k in Z.columns if k.startswith("smart_1_raw_disc_cs_")]
    comprobar((Z.loc[fab != "Seagate", s_cols].sum(axis=1) == 0).all(), "tramos: los demás fabricantes van a la referencia de smart_1_raw")


def probar_categorias(m):
    """Agrupar raras y una columna por categoría menos la de referencia."""
    y = np.array([1] * 25 + [0] * 25 + [1] * 25 + [0] * 75 + [1] * 2 + [0] * 3)
    v = ["A"] * 50 + ["B"] * 100 + ["R"] * 5
    X = pd.DataFrame({"model": v, "datacenter": [None] * 50 + ["phx1"] * 105})
    g = m.AgruparRaras().fit(X, y)
    Z = g.transform(pd.DataFrame({"model": ["A", "R", "NUEVO"], "datacenter": [None, "phx1", "yyz1"]}))
    comprobar(list(Z["model"]) == ["A", "otras", "otras"], "raras: la rara y la nueva van a «otras»")
    comprobar(Z["datacenter"].iloc[0] == "sin dato", "raras: el vacío pasa a «sin dato»")
    comprobar(Z["datacenter"].iloc[2] == g.referencia_["datacenter"], "raras: una nueva sin «otras» va a la referencia")
    comprobar(not g.otras_["datacenter"] and g.otras_["model"], "raras: «otras» solo existe si hubo raras en el ajuste")
    c = m.ColumnasMenosReferencia().fit(g.transform(X))
    W = c.transform(g.transform(X))
    comprobar(c.referencia_["model"] == "B" and list(W.filter(like="model_").columns) == ["model_ohe_A", "model_ohe_otras"],
              "categorías: k − 1 columnas, sin la de más filas")
    comprobar(set(np.unique(W.to_numpy())) <= {0.0, 1.0}, "categorías: solo 0 y 1")


def probar_preprocesadores(m):
    """Los tres, sin ajustar, con remainder drop y salida de pandas."""
    for familia in ("logistica", "bosque", "hgb"):
        p = m.preprocesador(familia)
        ct = p.named_steps["preparacion"]
        comprobar(not hasattr(ct, "transformers_"), f"{familia}: el preprocesador sale sin ajustar")
        comprobar(ct.get_params()["remainder"] == "drop", f"{familia}: remainder drop")
        comprobar(ct._sklearn_output_config.get("transform") == "pandas", f"{familia}: salida de pandas")
    comprobar("avisa" not in m.preprocesador("logistica").named_steps["preparacion"].transformers[0][2],
              "logística: avisa no entra")


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 1 · las diez validaciones, cada una en verde y en rojo
# ---------------------------------------------------------------------------------------------------------------
def probar_validaciones(m):
    """Cada validación con un caso verde y otro que tiene que salir en rojo."""
    comprobar(m.v_filas(10, 10) and not m.v_filas(10, 9), "1 filas: verde y rojo")
    comprobar(m.v_sin_objetivo(["a", "b"]) and not m.v_sin_objetivo(["a", "falla_30d"])
              and not m.v_sin_objetivo(["horizonte_hasta"]), "2 sin objetivo: verde y rojo")
    comprobar(m.v_sin_intermedias("logistica", ["edad_anos_disc_cs_1"]) and not m.v_sin_intermedias("logistica", ["edad_anos"])
              and not m.v_sin_intermedias("bosque", ["model"]) and m.v_sin_intermedias("bosque", ["edad_anos"]),
              "3 sin intermedias: verde y rojo")
    comprobar(m.v_sin_vacios({"edad_anos"}, {"edad_anos"}) and not m.v_sin_vacios({"model_ohe_A"}, {"edad_anos"}),
              "4 sin vacíos: verde y rojo")
    comprobar(m.v_nombres_unicos(["a", "b"]) and not m.v_nombres_unicos(["a", "a"]), "5 nombres únicos: verde y rojo")
    # 6: k − 1 columnas pasa; las k columnas de una variable, o dos columnas idénticas, no
    r = m.Revision("logistica", ["v", "w"])
    r.anadir(pd.DataFrame({"v_disc_cs_1": [0, 1, 0, 0.0], "v_disc_cs_2": [0, 0, 1, 0.0], "w_ohe_X": [1, 0, 0, 1.0]}))
    comprobar(m.v_sin_redundancia(r.grams, r.duplicadas()), "6 sin redundancia: verde con k − 1 columnas")
    r = m.Revision("logistica", ["v"])
    r.anadir(pd.DataFrame({"v_disc_cs_0": [1, 0, 0, 0.0], "v_disc_cs_1": [0, 1, 1, 0.0], "v_disc_cs_2": [0, 0, 0, 1.0]}))
    comprobar(not m.v_sin_redundancia(r.grams, r.duplicadas()), "6 sin redundancia: rojo con las k columnas")
    r = m.Revision("logistica", ["v", "w"])
    r.anadir(pd.DataFrame({"v_disc_cs_1": [0, 1, 0, 1.0], "w_disc_cs_1": [0, 1, 0, 1.0]}))
    comprobar(not m.v_sin_redundancia(r.grams, r.duplicadas()), "6 sin redundancia: rojo con dos columnas idénticas")
    comprobar(m.v_columnas_esperadas(["a", "b"], ["b", "a"]) and not m.v_columnas_esperadas(["a", "b", "c"], ["a", "b"])
              and not m.v_columnas_esperadas(["a"], ["a", "b"]), "7 columnas esperadas: verde y rojo")
    comprobar(m.v_relleno_sin_choque({"datacenter": {"phx1"}, "model": {"A"}})
              and not m.v_relleno_sin_choque({"datacenter": {"sin dato"}})
              and not m.v_relleno_sin_choque({"model": {"otras"}}), "8 relleno sin choque: verde y rojo")
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    comprobar(m.v_escalado(m.preprocesador("bosque"), True) and not m.v_escalado(m.preprocesador("bosque"), False)
              and not m.v_escalado(Pipeline([("escala", StandardScaler())]), True), "9 escalado según la matriz: verde y rojo")
    texto = (CASO / MATRIZ).read_text(encoding="utf-8")
    mz = m.leer_matriz(texto)
    cols = list(pq.read_schema(CASO / ENT).names)
    ok, _ = m.v_columnas_en_matriz(cols, mz)
    comprobar(ok, "10 columnas en la matriz: verde con la tabla y la matriz aprobada")
    ok, det = m.v_columnas_en_matriz(cols + ["smart_999_raw"], mz)
    comprobar(not ok and "smart_999_raw" in json.dumps(det), "10 columnas en la matriz: rojo con una columna que no está")
    mal = m.leer_matriz(texto.replace("| solo bosque, hgb |", "| sí |"))
    ok, det = m.v_columnas_en_matriz(cols, mal)
    comprobar(not ok, "10 columnas en la matriz: rojo si las listas del script no son la matriz aprobada")
    comprobar(mz["aprobada_por"] == "El responsable del caso" and mz["fecha"] == "2026-11-18", "la matriz se lee aprobada por el responsable del caso el 2026-11-18")


def buscar_escritos(texto):
    """Líneas que ponen una validación a True a mano, en vez de calcularla."""
    claves = "|".join(VALIDACIONES)
    patron = re.compile(r"[\"'](" + claves + r")[\"']\s*\]?\s*[:=]\s*True\b|\b(" + claves + r")\s*=\s*True\b")
    return [(n, linea.strip()) for n, linea in enumerate(texto.splitlines(), 1) if patron.search(linea)]


def probar_escritos():
    """Ninguna validación del script lleva True puesto; la búsqueda caza una escrita a propósito."""
    hallado = buscar_escritos(SCRIPT.read_text(encoding="utf-8"))
    comprobar(hallado == [], f"ninguna validación escrita a True en el script ({hallado})")
    comprobar(len(buscar_escritos('v = {"filas": True}\nsin_vacios = True')) == 2, "la búsqueda caza dos validaciones escritas a True")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 2 · el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def columna(campo, n, rng, ctx):
    """Valores para una columna del caso pequeño, con el tipo de la tabla real."""
    nombre, tipo = campo.name, campo.type
    if nombre in ctx:
        return pa.array(ctx[nombre], type=tipo)
    if pa.types.is_string(tipo) or pa.types.is_large_string(tipo):
        return pa.array(["x"] * n, type=tipo)
    if pa.types.is_boolean(tipo):
        return pa.array(rng.random(n) < 0.1, type=tipo)
    if pa.types.is_timestamp(tipo):
        return pa.array([dt.datetime(2024, 1, 1)] * n, type=tipo)
    vals = rng.integers(0, 60, n).astype(float)
    nulo = rng.random(n) < 0.08
    if pa.types.is_integer(tipo):
        return pa.array([None if z else int(v) for v, z in zip(vals, nulo)], type=tipo)
    return pa.array([None if z else float(v) for v, z in zip(vals, nulo)], type=tipo)


def escribir_parte(ruta, esquema, meses, rng, por_mes, fallos_por_mes, modelos, centros, extra=None):
    """Una parte del caso pequeño: un grupo de filas por mes, con las 144 columnas de la tabla real."""
    with pq.ParquetWriter(ruta, esquema) as w:
        for k, mes in enumerate(meses):
            n = por_mes
            y = np.zeros(n, dtype=np.int8); y[:fallos_por_mes] = 1; rng.shuffle(y)
            mod = rng.choice(modelos[0], size=n, p=modelos[1])
            fab = np.where(np.char.startswith(mod.astype(str), "S"), "Seagate", "Toshiba")
            cen = rng.choice(centros[0], size=n, p=centros[1])
            ctx = {"serial_number": [f"S{k}_{i}" for i in range(n)], "fecha": [mes] * n,
                   "horizonte_hasta": [mes + dt.timedelta(days=30)] * n, "falla_30d": y.tolist(),
                   "model": mod.tolist(), "fabricante": fab.tolist(),
                   "datacenter": [None if c == "-" else c for c in cen], "periodo": ["construcción"] * n,
                   "smart_1_raw": np.where(fab == "Seagate", rng.integers(100, 900, n), 0).astype(float).tolist(),
                   "smart_7_raw": np.where(fab == "Seagate", rng.integers(100, 900, n), 0).astype(float).tolist()}
            if extra:
                ctx.update(extra(n))
            t = pa.table({c.name: columna(c, n, rng, ctx) for c in esquema}, schema=esquema)
            w.write_table(t, row_group_size=n)


def montar(estado_matriz="aprobada por el responsable del caso el 18/11/2026 («Sí, siguiente pregunta»)", huella_buena=True,
           columna_de_mas=False, sin_dato_real=False, matriz_cambiada=False):
    """Monta tests/tmp_preparacion/ con las dos partes, la matriz y particion.json."""
    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "data" / "processed").mkdir(parents=True)
    (TMP / "informes").mkdir()
    (TMP / "config" / "modelo").mkdir(parents=True)
    esquema = pq.read_schema(CASO / ENT).remove_metadata()
    if columna_de_mas:
        esquema = esquema.append(pa.field("smart_999_raw", pa.float64()))
    rng = np.random.default_rng(7)
    modelos = (["SA", "TB", "TR"], [0.6, 0.37, 0.03])
    centros = (["phx1", "sac0", "-"], [0.35, 0.35, 0.30]) if not sin_dato_real else (["phx1", "sin dato", "-"], [0.35, 0.35, 0.30])
    meses = [dt.datetime(2024, 4, 1), dt.datetime(2024, 5, 1), dt.datetime(2024, 6, 1)]
    escribir_parte(TMP / ENT, esquema, meses, rng, 6800, 70, modelos, centros)
    mval = (["SA", "TB", "NUEVO"], [0.6, 0.3, 0.1])
    escribir_parte(TMP / VAL, esquema, [dt.datetime(2024, 7, 1), dt.datetime(2024, 8, 1)], rng, 3000, 5, mval,
                   (["phx1", "yyz1", "-"], [0.4, 0.3, 0.3]))
    texto = (CASO / MATRIZ).read_text(encoding="utf-8")
    texto = re.sub(r"^estado: .*$", "estado: " + estado_matriz, texto, count=1, flags=re.M)
    if matriz_cambiada:
        texto = texto.replace("| solo bosque, hgb |", "| sí |")
    (TMP / MATRIZ).write_text(texto, encoding="utf-8")
    partes = []
    for parte, ruta in (("entrenamiento", ENT), ("validacion", VAL)):
        pf = pq.ParquetFile(TMP / ruta)
        partes.append({"parte": parte, "ruta": ruta, "sha256": sha256(TMP / ruta) if (huella_buena or parte != "entrenamiento") else "0" * 64,
                       "filas": pf.metadata.num_rows, "fotos_con_objetivo": None, "tasa_objetivo_pct": None,
                       "fecha_min": None, "fecha_max": None, "discos": None})
    partes.append({"parte": "lote_produccion", "ruta": None, "sha256": None, "filas": None, "motivo": "no hay"})
    (TMP / "informes" / "particion.json").write_text(json.dumps(
        {"resultado": {"estado": "OK"}, "estrategia": "fecha", "por_que": "reglas, apartado 7", "partes": partes,
         "discos_en_las_dos_partes": 0, "diferencia_tasa_puntos": 0.0}, ensure_ascii=False), encoding="utf-8")


def ejecutar():
    """Ejecuta el script sobre la carpeta temporal con -W error; devuelve el código, el JSON y la salida."""
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)], capture_output=True,
                       text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    ruta = TMP / SALIDA
    js = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    if r.returncode not in (0, 2):
        print(r.stdout[-3000:]); print(r.stderr[-4000:])
    return r.returncode, js, r.stdout + r.stderr


def probar_caso_pequeno():
    """El verde del caso pequeño y los cinco casos que tienen que parar."""
    montar()
    codigo, js, salida = ejecutar()
    comprobar(codigo == 0, f"pequeño: el script sale con 0 (salió con {codigo})")
    if js is None:
        comprobar(False, "pequeño: escribe informes/preparacion.json"); print(salida[-3000:])
        return
    comprobar(js["resultado"]["estado"] == "OK", f"pequeño: estado OK ({js['resultado']['estado']}: {js['resultado']['resumen']})")
    for v in VALIDACIONES:
        comprobar(((js.get("validaciones") or {}).get(v) or {}).get("resultado") is True, f"pequeño: validación {v} en verde")
    comprobar(js["matriz"]["aprobada_por"] == "El responsable del caso" and js["matriz"]["fecha"] == "2026-11-18", "pequeño: matriz aprobada por el responsable del caso el 2026-11-18")
    mu = js["muestra"]
    comprobar(mu["fallos"] == 210 and mu["sanas_muestra"] == 3 * round(0.02 * (6800 - 70)) and mu["semilla"] == 42,
              "pequeño: la muestra son todos los fallos y el 2 % de las sanas de cada mes")
    comprobar(all(js["preprocesador"]["familias"][f]["tiempo_ajuste_s"] is not None for f in ("logistica", "bosque", "hgb")),
              "pequeño: el tiempo de ajuste de cada familia está en el JSON")
    comprobar("falla_30d" not in js["preprocesador"]["columnas_leidas_validacion"], "pequeño: la validación se lee sin falla_30d")
    comprobar(js["preprocesador"]["filas_validacion"] == 6000, "pequeño: transforma las 6.000 filas de validación")
    nuevas = js["preprocesador"]["categorias_nuevas_validacion"]["model"]["no_en_entrenamiento"]
    comprobar(nuevas["valores"] == ["NUEVO"] and nuevas["filas"] > 0, "pequeño: el modelo nuevo de validación se cuenta")
    comprobar(js["preprocesador"]["familias"]["hgb"]["categoricas_nativas"] == ["model_oe", "fabricante_oe", "datacenter_oe"],
              "pequeño: las categóricas nativas de HistGradientBoosting")
    md = (TMP / "informes" / "preparacion.md")
    texto = md.read_text(encoding="utf-8") if md.exists() else ""
    for ap in ("Partición", "Desequilibrio de clases", "Matriz de transformaciones", "Variables que no entran",
               "Validaciones", "Parámetros usados", "Datos personales", "Límites"):
        comprobar(f"## {ap}" in texto, f"pequeño: el informe tiene el apartado «{ap}»")
    # Los casos que tienen que parar
    for nombre, montaje, estado, val in (
            ("matriz sin aprobar", {"estado_matriz": "opción, pendiente del responsable del caso"}, "PARADO", None),
            ("huella de entrenamiento distinta", {"huella_buena": False}, "PARADO", None),
            ("una columna de más en la tabla", {"columna_de_mas": True}, "ERROR", "columnas_en_matriz"),
            ("las listas del script no son la matriz", {"matriz_cambiada": True}, "ERROR", "columnas_en_matriz"),
            ("«sin dato» como centro real", {"sin_dato_real": True}, "ERROR", "relleno_sin_choque")):
        montar(**montaje)
        codigo, js, salida = ejecutar()
        comprobar(codigo == 2, f"{nombre}: sale con 2 (salió con {codigo})")
        comprobar(js is not None and js["resultado"]["estado"] == estado, f"{nombre}: estado {estado}")
        if val and js is not None:
            comprobar((js.get("validaciones") or {}).get(val, {}).get("resultado") is False, f"{nombre}: {val} en rojo")


# ---------------------------------------------------------------------------------------------------------------
# 5. Parte 3 · el JSON real
# ---------------------------------------------------------------------------------------------------------------
def probar_real():
    """Si la sesión principal ya ejecutó el script, las cifras de control de la petición."""
    ruta = CASO / SALIDA
    js = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if not isinstance(js.get("validaciones"), dict):
        print("nota  sin informes/preparacion.json de la tercera parte: la parte 3 se ejecuta cuando lo escriba la sesión principal")
        return
    comprobar(js["resultado"]["estado"] == "OK", "real: estado OK")
    comprobar(all(js["validaciones"][v]["resultado"] is True for v in VALIDACIONES), "real: las diez validaciones en verde")
    mu = js["muestra"]
    comprobar(mu["fallos"] == 11962 and abs(mu["sanas_muestra"] - 220282) <= 54, f"real: muestra con 11.962 fallos y unas 220.282 sanas ({mu})")
    comprobar(js["preprocesador"]["filas_validacion"] == 3578809, "real: 3.578.809 filas de validación")
    nuevas = js["preprocesador"]["categorias_nuevas_validacion"]["model"]["no_en_entrenamiento"]
    comprobar(sorted(nuevas["valores"]) == ["ST14000NM002J", "ST24000NM002H", "TOSHIBA MG09ACA16TE"] and nuevas["filas"] == 19757,
              "real: los 3 modelos nuevos de validación, con 19.757 fotos")
    ref = js["preprocesador"]["referencias_logistica"]
    comprobar(ref.get("model") == "TOSHIBA MG07ACA14TA" and ref.get("fabricante") == "Seagate" and ref.get("datacenter") == "sin dato",
              f"real: las referencias de la matriz ({ref})")
    comprobar(js["desequilibrio"]["fotos_con_fallo"] == 11962 and js["desequilibrio"]["filas"] == 11026052, "real: desequilibrio de construcción")


# ---------------------------------------------------------------------------------------------------------------
# 6. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"intérprete: {sys.executable}")
    try:
        m = cargar_modulo()
        if m is not None:
            probar_tramos(m)
            probar_categorias(m)
            probar_preprocesadores(m)
            probar_validaciones(m)
            probar_escritos()
            probar_caso_pequeno()
        probar_real()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos" if FALLOS else "\ntodo en verde")
    sys.exit(1 if FALLOS else 0)
