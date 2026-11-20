"""Prueba de scripts/pipeline_riesgo.py, el módulo de producción del caso 68 (skill preproduccion §2.1).

Parte 1, el módulo, con datos pequeños escritos aquí:
  - importarlo no ejecuta nada (un proceso aparte lo importa y no escribe ni imprime nada);
  - el contrato se lee de informes/preproduccion.json: 61 numéricas, 3 nominales, 64 que lee el preprocesador, y para si
    el contrato no está aprobado (copia con aprobado_por vacío);
  - el Pipeline: nombres, remainder «drop», columnas por nombre del contrato, un objeto nuevo en cada llamada;
  - el preprocesador del módulo da las mismas columnas y los mismos valores que el de scripts/13_preparacion.py para
    la familia hgb, con el centro vaciado como en el modelado (el 13 se carga con importlib solo para comparar);
  - el modelo entero da la misma probabilidad, bit a bit, que el camino del modelado: el preprocesador del 13, la
    salida en float32, el HistGradientBoosting con la receta y la corrección del prior escrita aquí;
  - las columnas que salen se comprueban: una lista esperada distinta da rojo;
  - las funciones de la foto, cada una con su caso que tiene que salir mal: el modelo con dos espacios, la capacidad no
    válida, un modelo sin ninguna capacidad válida, el fabricante y la garantía, el disco de arranque, la foto del día
    del fallo, la edad con y sin horas, la ventana de un fallo anterior (cuenta) y la de un fallo que aún no ha
    ocurrido (no cuenta: el arreglo de Juan), la fila de ventana con la fecha distinta de su texto (no cuenta), los
    cambios contra la foto anterior de dos meses antes, el disco sin foto anterior y los avisos con un vacío.
Parte 2, la medida que pidió la sesión principal (no decide nada): en data/raw/, cuántos modelos tienen una fila con
capacidad no válida y su capacidad válida solo en el recuento diario, y cuántas filas de fotos con capacidad no válida
no tienen ninguna capacidad válida de su modelo en fotos y ventanas hasta su fecha. Se imprime; no falla.
Parte 3, solo con --real: la transformación del módulo sobre las fotos en bruto del 01/06/2025 y del 01/06/2024,
frente a fotos_riesgo, columna a columna, con las cifras de control del encargo; la foto del arreglo se cuenta aparte.

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier

CASO = Path(__file__).resolve().parents[1]
MODULO = CASO / "scripts" / "pipeline_riesgo.py"
TMP = CASO / "tests" / "tmp_produccion"
FALLOS = []
F = pd.Timestamp("2024-04-01")


def comprobar(condicion, caso):
    """Apunta el caso si no se cumple y lo imprime."""
    print(("ok    " if condicion else "FALLA ") + caso)
    if not condicion:
        FALLOS.append(caso)


def cargar(ruta, nombre):
    """Carga un fichero .py como módulo; None si no existe o no carga."""
    if not ruta.exists():
        comprobar(False, f"existe {ruta.relative_to(CASO).as_posix()}")
        return None
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = m
    try:
        spec.loader.exec_module(m)
    except Exception as e:  # noqa: BLE001 - la prueba dice qué falló al cargar
        comprobar(False, f"{ruta.name} carga como módulo ({type(e).__name__}: {e})")
        return None
    return m


# ---------------------------------------------------------------------------------------------------------------
# 2. Parte 1 · el módulo
# ---------------------------------------------------------------------------------------------------------------
def probar_import():
    """Importar el módulo en otro proceso no imprime ni escribe nada."""
    antes = sorted(p.as_posix() for p in CASO.rglob("*") if p.is_file() and "tests" not in p.parts and ".claude" not in p.parts)
    r = subprocess.run([sys.executable, "-W", "error", "-c", f"import sys; sys.path.insert(0, r'{MODULO.parent}'); import pipeline_riesgo"],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    despues = sorted(p.as_posix() for p in CASO.rglob("*") if p.is_file() and "tests" not in p.parts and ".claude" not in p.parts)
    comprobar(r.returncode == 0 and r.stdout == "" and r.stderr == "", f"importar el módulo no imprime nada ({r.stderr[-300:]})")
    comprobar(antes == despues, "importar el módulo no escribe ningún fichero")


def tabla_de_juguete(c, n=6000, semilla=3):
    """Una tabla con las 64 columnas que lee el preprocesador, con vacíos, una categoría rara y fallos suficientes."""
    rng = np.random.default_rng(semilla)
    y = (rng.random(n) < 0.08).astype(np.int64)
    df = pd.DataFrame({v: np.where(rng.random(n) < 0.1, np.nan, rng.integers(0, 50, n) + 30 * y * (rng.random(n) < 0.5))
                       for v in c["numericas"]})
    df["avisa"] = rng.random(n) < 0.1
    df["model"] = rng.choice(["ST4000DM000", "ST12000NM0008", "TOSHIBA MG07ACA14TA", "RARO1"], n, p=[0.4, 0.3, 0.297, 0.003])
    df["fabricante"] = np.where(df["model"].str.startswith("ST"), "Seagate", "Toshiba")
    df["datacenter"] = rng.choice(np.array(["phx1", "sac0", None], dtype=object), n)
    return df, y


def probar_contrato_y_pipeline(m, p13):
    """El contrato, el Pipeline y la comparación con el preprocesador del 13 y con el camino del modelado."""
    c = m.leer_contrato(CASO)
    comprobar(len(c["numericas"]) == 61 and c["nominales"] == ["model", "fabricante", "datacenter"] and len(c["lee"]) == 64,
              f"contrato: 61 numéricas, 3 nominales y 64 que lee ({len(c['numericas'])}, {c['nominales']}, {len(c['lee'])})")
    comprobar(c["vaciar"] == ["datacenter"] and c["esperadas"] == c["numericas"] + ["model_oe", "fabricante_oe", "datacenter_oe"],
              "contrato: el centro se vacía y las columnas esperadas son las numéricas y los tres códigos")
    # Un contrato sin aprobar para
    js = json.loads((CASO / "informes" / "preproduccion.json").read_text(encoding="utf-8"))
    js["contrato"]["aprobado_por"] = ""
    (TMP / "informes").mkdir(parents=True, exist_ok=True)
    (TMP / "informes" / "preproduccion.json").write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    try:
        m.leer_contrato(TMP)
        comprobar(False, "contrato: sin aprobar tiene que parar")
    except m.ErrorDeProduccion as e:
        comprobar("aprobado" in str(e), f"contrato: sin aprobar para ({e})")
    # El Pipeline
    a, b = m.construir_pipeline(c, tasa_real=0.001), m.construir_pipeline(c, tasa_real=0.001)
    comprobar(list(a.named_steps) == ["preparacion", "float32", "sin_vacias", "modelo"], f"pipeline: pasos con nombre ({list(a.named_steps)})")
    ct = a.named_steps["preparacion"]
    comprobar(ct.remainder == "drop" and [t[0] for t in ct.transformers] == ["numericas", "categorias"]
              and ct.transformers[0][2] == c["numericas"] and ct.transformers[1][2] == c["nominales"],
              "pipeline: remainder drop y columnas por nombre del contrato")
    comprobar(a.named_steps["preparacion"] is not b.named_steps["preparacion"]
              and a.named_steps["modelo"] is not b.named_steps["modelo"], "pipeline: un objeto nuevo en cada llamada")
    # El preprocesador frente al del 13, con el centro vaciado como en el modelado (sin_sitio)
    df, y = tabla_de_juguete(c)
    sin_sitio = df.copy()
    sin_sitio["datacenter"] = pd.Series([None] * len(df), index=df.index, dtype=object)
    x13 = p13.preprocesador("hgb").fit(sin_sitio, y).transform(sin_sitio)
    xm = m.construir_pipeline(c, tasa_real=0.001).named_steps["preparacion"].fit(df, y).transform(df)
    comprobar(list(xm.columns) == list(x13.columns), "preprocesador: las mismas columnas que el del 13")
    try:
        pd.testing.assert_frame_equal(xm, x13)
        iguales = True
    except AssertionError as e:
        iguales = False
        print(str(e)[:500])
    comprobar(iguales, "preprocesador: los mismos valores que el del 13")
    # El modelo entero frente al camino del modelado (13 + float32 + HistGradientBoosting + corrección del prior)
    pipe = m.construir_pipeline(c, tasa_real=0.002).set_params(modelo__max_iter=40)
    p_mod = pipe.fit(df, y).predict_proba(df)[:, 1]
    pre = p13.preprocesador("hgb").fit(sin_sitio, y)
    xt = pre.transform(sin_sitio).astype(np.float32)
    hoja = max(20, int(np.floor(0.01 * len(df) + 0.5)))
    h = c["receta"]["hiperparametros"]
    hgb = HistGradientBoostingClassifier(early_stopping=False, random_state=42, categorical_features=c["categoricas"],
                                         min_samples_leaf=hoja, max_iter=40, max_depth=h["max_depth"],
                                         learning_rate=h["learning_rate"], l2_regularization=h["l2_regularization"]).fit(xt, y)
    p = np.clip(hgb.predict_proba(xt)[:, 1], 1e-15, 1 - 1e-15)
    tm, tr = float(np.mean(y)), 0.002
    odds = p / (1 - p) * (tr / (1 - tr)) / (tm / (1 - tm))
    comprobar(np.array_equal(p_mod, odds / (1 + odds)), "modelo: la misma probabilidad, bit a bit, que el camino del modelado")
    comprobar(pipe.named_steps["modelo"].modelo_.min_samples_leaf == hoja, f"modelo: la hoja es max(20, 1 % de las filas) ({hoja})")
    # Las columnas de salida comprobadas
    comprobar(m.comprobar_columnas_de_salida(pipe, c["esperadas"]) == c["esperadas"], "columnas: verde con la lista del contrato")
    try:
        m.comprobar_columnas_de_salida(pipe, c["esperadas"][:-1])
        comprobar(False, "columnas: una lista distinta tiene que dar rojo")
    except m.ErrorDeProduccion:
        comprobar(True, "columnas: una lista distinta da rojo")


def probar_foto(m):
    """Las funciones de la foto, con un caso pequeño escrito aquí."""
    mapeo = {"WDC  WUH721414ALE6L4": "WDC WUH721414ALE6L4"}
    minimo = 200_000_000_000
    C4, C14, C025 = 4000787030016, 14000519643136, 250059350016
    foto = pd.DataFrame({
        "serial_number": ["A", "B", "C", "D", "E", "G", "H", "K"],
        "fecha": [F] * 8,
        "model": ["ST4000DM000", "WDC  WUH721414ALE6L4", "ST4000DM000", "Seagate SSD", "ST4000DM000", "NUEVO1", "ST4000DM000", "ST4000DM000"],
        "capacity_bytes": [-1, C14, C4, C025, C4, -1, C4, C4],
        "failure": [0, 0, 0, 0, 1, 0, 0, 0],
        "datacenter": [None, "sac0", None, None, None, None, None, None],
        "smart_9_raw": [8766.0, 17532.0, np.nan, 100.0, 1.0, 1.0, np.nan, np.nan],
        "smart_5_raw": [3.0, np.nan, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "smart_187_raw": [0.0, np.nan, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "smart_188_raw": [0.0, np.nan, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "smart_197_raw": [0.0, np.nan, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "smart_198_raw": [0.0, np.nan, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    })
    # La historia: A tiene foto en febrero (dos meses antes); C, primera foto en enero; H, solo ventana de un fallo
    # anterior; K, ventana de un fallo que aún no ha ocurrido; C, además, una fila de ventana con la fecha distinta de su texto
    fotos_ant = pd.DataFrame({"serial_number": ["A", "C", "C"], "fecha": pd.to_datetime(["2024-02-01", "2024-01-01", "2024-03-01"]),
                              "model": ["ST4000DM000"] * 3, "capacity_bytes": [C4, C4, C4],
                              "smart_5_raw": [1.0, 0.0, 0.0], "smart_187_raw": [0.0, 0.0, np.nan],
                              "smart_197_raw": [0.0, 0.0, 0.0], "smart_198_raw": [0.0, 0.0, 0.0]})
    ventanas = pd.DataFrame({"serial_number": ["H", "K", "C"],
                             "fecha": pd.to_datetime(["2023-12-15", "2024-03-20", "2023-11-01"]),
                             "date": ["2023-12-15", "2024-03-20", "2023-11-02"],
                             "dia_fallo": pd.to_datetime(["2024-01-10", "2024-04-10", "2023-11-20"]),
                             "model": ["ST4000DM000"] * 3, "capacity_bytes": [C4, C4, C4]})
    h = m.historia_de(fotos_ant, ventanas, F, mapeo)
    x, motivo = m.preparar_foto(foto, h, mapeo, minimo)
    fila = x.set_index("serial_number")
    mot = pd.Series(list(motivo), index=foto["serial_number"])
    comprobar(len(x) == len(foto) and list(x["serial_number"]) == list(foto["serial_number"]), "foto: una fila por fila, en el mismo orden")
    comprobar(fila.loc["B", "model"] == "WDC WUH721414ALE6L4", "foto: el modelo con dos espacios pasa a su nombre")
    comprobar(fila.loc["A", "capacidad_tb"] == 4.0, "foto: la capacidad no válida toma la de su modelo")
    comprobar(pd.isna(fila.loc["G", "capacidad_tb"]) and "capacidad" in mot["G"], f"foto: un modelo sin capacidad válida sale con su motivo ({mot['G']})")
    comprobar(fila.loc["A", "fabricante"] == "Seagate" and fila.loc["B", "fabricante"] == "WDC" and fila.loc["A", "garantia_anos"] == 2
              and fila.loc["B", "garantia_anos"] == 5, "foto: fabricante y garantía del nombre del modelo")
    comprobar("arranque" in mot["D"] and "día del fallo" in mot["E"] and mot["A"] == "" and mot["C"] == "",
              f"foto: el disco de arranque y la foto del día del fallo salen con su motivo ({mot['D']}; {mot['E']})")
    comprobar(fila.loc["A", "edad_anos"] == 1.0 and fila.loc["B", "edad_anos"] == 2.0, "foto: con horas, horas entre 8.766")
    comprobar(fila.loc["C", "edad_anos"] == ((F - pd.Timestamp("2024-01-01")) / pd.Timedelta(days=1)) / 365.25,
              "foto: sin horas, desde su primera foto (la ventana con la fecha distinta de su texto no cuenta)")
    comprobar(fila.loc["H", "edad_anos"] == ((F - pd.Timestamp("2023-12-15")) / pd.Timedelta(days=1)) / 365.25,
              "foto: sin horas ni foto anterior, desde la ventana de un fallo ya ocurrido")
    comprobar(fila.loc["K", "edad_anos"] == 0.0, "foto: la ventana de un fallo que aún no ha ocurrido no cuenta (el arreglo)")
    comprobar(fila.loc["A", "cambio_smart_5"] == 2.0 and fila.loc["A", "meses_desde_foto_anterior"] == 2,
              "foto: el cambio contra la foto anterior de dos meses antes")
    comprobar(pd.isna(fila.loc["C", "cambio_smart_187"]) and fila.loc["C", "cambio_smart_5"] == 0.0,
              "foto: el cambio con uno de los dos valores vacío queda vacío")
    comprobar(pd.isna(fila.loc["H", "cambio_smart_5"]) and pd.isna(fila.loc["H", "meses_desde_foto_anterior"]),
              "foto: un disco sin foto anterior deja los cambios vacíos")
    comprobar(fila.loc["C", "contadores_que_avisan"] == 2 and bool(fila.loc["C", "avisa"]) and fila.loc["C", "suma_contadores_sin_188"] == 2.0
              and fila.loc["C", "smart_188_no_cero"] == 1, "foto: los avisos de los cinco contadores")
    comprobar(not bool(fila.loc["B", "avisa"]) and pd.isna(fila.loc["B", "suma_contadores_sin_188"]) and pd.isna(fila.loc["B", "smart_188_no_cero"]),
              "foto: un contador vacío no cuenta como aviso")


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 2 · la medida de la capacidad que solo estaría en el recuento diario
# ---------------------------------------------------------------------------------------------------------------
def medir_capacidad_solo_en_recuento(m):
    """Mide, en data/raw/, lo que la sesión principal pidió: no decide nada, lo imprime."""
    pod = CASO / "data" / "raw" / "podado"
    if not pod.exists():
        print("nota  sin data/raw/podado: la medida no se hace")
        return
    t0 = time.time()
    dec = json.loads((CASO / "contexto-proyecto" / "modelo" / "decisiones-correccion.json").read_text(encoding="utf-8"))
    mapeo, minimo = dec["modelos"]["mapeo"], dec["capacidad"]["minimo_valido_bytes"]
    partes = []
    for tabla in ("fotos_mensuales", "ventanas_fallo"):
        for f in sorted((pod / tabla).glob("*.parquet")):
            t = pq.read_table(f, columns=["fecha", "model", "capacity_bytes"])
            g = t.group_by(["model", "capacity_bytes"]).aggregate([("fecha", "min")]).to_pandas()
            partes.append(g.assign(tabla=tabla))
    fv = pd.concat(partes, ignore_index=True)
    fv["model"] = fv["model"].replace(mapeo)
    rec = pd.read_parquet(pod / "recuento_diario.parquet", columns=["model", "capacity_bytes"]).drop_duplicates()
    rec["model"] = rec["model"].replace(mapeo)
    validas_fv = set(fv.loc[fv["capacity_bytes"] >= minimo, "model"])
    malas = set(fv.loc[fv["capacity_bytes"] < minimo, "model"])
    solo_rec = sorted((malas - validas_fv) & set(rec.loc[rec["capacity_bytes"] >= minimo, "model"]))
    print(f"medida: modelos con una fila de capacidad no válida en fotos o ventanas y su capacidad válida solo en el recuento: "
          f"{len(solo_rec)} {solo_rec}")
    # Por fecha: la primera capacidad válida de cada modelo en fotos y ventanas frente a la primera no válida
    primera_valida = fv[fv["capacity_bytes"] >= minimo].groupby("model")["fecha_min"].min()
    primera_mala = fv[fv["capacity_bytes"] < minimo].groupby("model")["fecha_min"].min()
    antes = sorted(k for k, v in primera_mala.items() if k not in primera_valida or v < primera_valida[k])
    print(f"medida: modelos cuya primera fila no válida llega antes que su primera capacidad válida en fotos y ventanas: "
          f"{len(antes)} {antes} ({time.time() - t0:.0f} s)")
    comprobar(True, "medida de la capacidad hecha (se lee arriba; no decide nada)")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 3 · con --real, la transformación del módulo frente a fotos_riesgo
# ---------------------------------------------------------------------------------------------------------------
CONTROL_REAL = {"2025-06-01": {"filas": 318737, "columnas": 130, "arranque": 3979, "dia_fallo": 7, "datos": 314751, "sin_anterior": 3913},
                "2024-06-01": {"filas": 286791, "arranque": 4220, "dia_fallo": 11, "datos": 282560, "capacidad_mala": 101}}


def probar_real(m):
    """La transformación del módulo sobre la foto en bruto frente a fotos_riesgo, con las cifras de control."""
    c = m.leer_contrato(CASO)
    dec = json.loads((CASO / "contexto-proyecto" / "modelo" / "decisiones-correccion.json").read_text(encoding="utf-8"))
    mapeo, minimo = dec["modelos"]["mapeo"], dec["capacidad"]["minimo_valido_bytes"]
    pod = CASO / "data" / "raw" / "podado"
    for dia, ctl in CONTROL_REAL.items():
        t0 = time.time()
        fecha = pd.Timestamp(dia)
        ruta = pod / "fotos_mensuales" / f"{dia[:7]}.parquet"
        foto = m.leer_foto(ruta, c["entrada"])
        h = m.leer_historia(pod / "fotos_mensuales", pod / "ventanas_fallo", fecha, mapeo, set(foto["serial_number"]))
        x, motivo = m.preparar_foto(foto, h, mapeo, minimo)
        mot = pd.Series(list(motivo))
        comprobar(len(foto) == ctl["filas"], f"real {dia}: {len(foto)} filas en bruto (control {ctl['filas']})")
        if "columnas" in ctl:
            comprobar(pq.ParquetFile(ruta).metadata.num_columns == ctl["columnas"], f"real {dia}: 130 columnas en bruto")
        if "capacidad_mala" in ctl:
            comprobar(int((foto["capacity_bytes"] < minimo).sum()) == ctl["capacidad_mala"], f"real {dia}: {ctl['capacidad_mala']} capacidades no válidas antes de corregir")
        n_arr, n_fal = int(mot.str.contains("arranque").sum()), int(mot.str.contains("día del fallo").sum())
        datos = (mot == "").to_numpy()
        comprobar((n_arr, n_fal, int(datos.sum())) == (ctl["arranque"], ctl["dia_fallo"], ctl["datos"]),
                  f"real {dia}: arranque, día del fallo y datos ({n_arr}, {n_fal}, {int(datos.sum())})")
        if "sin_anterior" in ctl:
            comprobar(int(x.loc[datos, "meses_desde_foto_anterior"].isna().sum()) == ctl["sin_anterior"],
                      f"real {dia}: {int(x.loc[datos, 'meses_desde_foto_anterior'].isna().sum())} sin foto anterior (control 3.913)")
        # Columna a columna frente a fotos_riesgo de esa fecha, unidas por serial_number
        ruta_fr = CASO / "data" / "processed" / ("fotos_riesgo_validacion.parquet" if fecha >= pd.Timestamp("2024-07-01") else "fotos_riesgo_entrenamiento.parquet")
        fr = pq.read_table(ruta_fr, columns=["serial_number", "fecha", "edad_de_horas"] + c["lee"],
                           filters=[("fecha", "==", fecha)]).to_pandas().set_index("serial_number")
        mio = x.loc[datos].set_index("serial_number")
        comprobar(sorted(mio.index) == sorted(fr.index), f"real {dia}: las mismas fotos que fotos_riesgo")
        mio = mio.loc[fr.index]
        distintas = {}
        for col in c["lee"]:
            a, b = mio[col], fr[col]
            if col in c["nominales"]:
                ig = (a.astype(object).where(a.notna(), None) == b.astype(object).where(b.notna(), None)) | (a.isna() & b.isna())
            else:
                av, bv = pd.to_numeric(a).to_numpy(dtype=float, na_value=np.nan), pd.to_numeric(b).to_numpy(dtype=float, na_value=np.nan)
                ig = pd.Series((av == bv) | (np.isnan(av) & np.isnan(bv)), index=a.index)
            if not ig.all():
                distintas[col] = list(ig.index[~ig.to_numpy()])
        # La foto del arreglo: sin horas y con la edad distinta, se cuenta aparte
        arreglo = [s for s in distintas.get("edad_anos", []) if not fr.loc[s, "edad_de_horas"]]
        resto = {k: v for k, v in distintas.items() if not (k == "edad_anos" and set(v) == set(arreglo))}
        print(f"nota  real {dia}: fotos con la edad distinta por el arreglo (sin horas): {len(arreglo)}; en {time.time() - t0:.0f} s")
        comprobar(not resto and len(arreglo) <= 1, f"real {dia}: iguales a fotos_riesgo salvo la foto del arreglo "
                  f"({ {k: len(v) for k, v in resto.items()} }, arreglo {len(arreglo)})")


def probar_estado(m):
    """El estado del JSON sigue a las validaciones: AVISO y cuáles faltan mientras alguna está sin ejecutar, OK con
    todas en verde y ERROR con una en rojo; el informe se regenera con él."""
    js = json.loads((CASO / "informes" / "preproduccion.json").read_text(encoding="utf-8"))
    # La copia lleva el estado que se prueba, todas sin ejecutar; no lo hereda del JSON real, que cambia con el caso
    # (programacion-del-caso §2 y error 31: desde el reentreno con datos nuevos, el real ya no tiene ninguna sin ejecutar)
    js["validaciones"] = {k: None for k in js["validaciones"]}
    (TMP / "informes").mkdir(parents=True, exist_ok=True)
    (TMP / "informes" / "preproduccion.json").write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    claves = list(js["validaciones"])
    r = m.actualizar_json(TMP, {}, {"filas_ejecucion": True})
    faltan = [k for k, v in r["validaciones"].items() if v is None]
    comprobar(r["resultado"]["estado"] == "AVISO" and all(k in r["resultado"]["resumen"] for k in faltan)
              and "Falta la parte 2" not in r["resultado"]["resumen"],
              f"estado: con validaciones sin ejecutar, AVISO y las nombra ({r['resultado']['resumen'][:160]})")
    r = m.actualizar_json(TMP, {}, {k: True for k in claves})
    md = (TMP / "informes" / "preproduccion.md").read_text(encoding="utf-8")
    comprobar(r["resultado"]["estado"] == "OK" and "**Estado: OK.**" in md, f"estado: con todas en verde, OK, también en el informe ({r['resultado']['resumen'][:160]})")
    r = m.actualizar_json(TMP, {}, {"otro_camino": False})
    comprobar(r["resultado"]["estado"] == "ERROR" and "otro_camino" in r["resultado"]["resumen"], "estado: con una en rojo, ERROR y la nombra")
    # La prueba por otro camino escribe su validación en el JSON sin importar el módulo: --informe recalcula el estado
    ruta = TMP / "informes" / "preproduccion.json"
    js = json.loads(ruta.read_text(encoding="utf-8"))
    js["validaciones"]["otro_camino"] = True
    ruta.write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    subprocess.run([sys.executable, "-W", "error", str(MODULO), "--informe", "--raiz", str(TMP)], capture_output=True,
                   env={**os.environ, "PYTHONUTF8": "1"}, timeout=150)
    js = json.loads(ruta.read_text(encoding="utf-8"))
    comprobar(js["resultado"]["estado"] == "OK", "estado: --informe lo recalcula tras la validación que escribe la prueba por otro camino")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"intérprete: {sys.executable}")
    try:
        TMP.mkdir(parents=True, exist_ok=True)
        m = cargar(MODULO, "pipeline_riesgo")
        p13 = cargar(CASO / "scripts" / "13_preparacion.py", "preparacion_13_para_comparar")
        if m is not None and p13 is not None:
            probar_import()
            probar_contrato_y_pipeline(m, p13)
            probar_foto(m)
            probar_estado(m)
            medir_capacidad_solo_en_recuento(m)
            if "--real" in sys.argv:
                probar_real(m)
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos" if FALLOS else "\ntodo en verde")
    sys.exit(1 if FALLOS else 0)
