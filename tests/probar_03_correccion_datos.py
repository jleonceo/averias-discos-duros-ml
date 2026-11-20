"""Prueba de scripts/03_correccion_datos.py.

Parte 1: monta en tests/tmp_correccion/ un caso pequeño con datos escritos aquí (dos fotos, dos ventanas, el recuento y
la lista de fallos), con su JSON de calidad y su fichero de decisiones, ejecuta la corrección sobre él con -W error y
comprueba lo que tiene que salir. Trae casos que tienen que salir mal y hacer parar al script con ERROR o PARADO: un
modelo con dos capacidades válidas, un modelo sin ninguna, una fila que se quitaría con un fallo dentro y un JSON de
calidad parado.
Parte 2: si ya existe informes/correccion-datos.json real, compara sus cifras de control con
tests/cifras_de_referencia.json (clave «cifras_correccion») y rehace cifras por otro camino: desde data/raw/ con pandas
frente a los Parquet corregidos, que el script no usa para contarlas.

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import hashlib
import json
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
SCRIPT = CASO / "scripts" / "03_correccion_datos.py"
TMP = CASO / "tests" / "tmp_correccion"
FALLOS = []

APARTADOS = ["Fuente", "Correcciones aplicadas", "Decisiones del usuario", "Elementos mantenidos sin cambios",
             "Decisiones pendientes", "Validación", "Datos personales", "Límites"]

ST4, WD14, WD14B, SSD = "ST4000DM000", "WDC WUH721414ALE6L4", "WDC  WUH721414ALE6L4", "Seagate SSD"
C4, C14, C025 = 4000787030016, 14000519643136, 250059350016


def comprobar(nombre, condicion, detalle=""):
    """Apunta un caso que falla, con su nombre y lo que se vio."""
    if not condicion:
        FALLOS.append(f"{nombre}: {detalle}")
        print(f"FALLA  {nombre}  {detalle}")
    else:
        print(f"pasa   {nombre}")


def huella_carpeta(carpeta):
    """SHA-256 de cada fichero de una carpeta, para ver que el script no la toca."""
    return {p.relative_to(carpeta).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(carpeta.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------------------------------------------
# 2. Datos pequeños escritos en la prueba
# ---------------------------------------------------------------------------------------------------------------
def foto_sin_sitio():
    """Foto de enero de 2020: sin columnas de sitio y con el centro sin tipo, como las fotos anteriores a julio de 2023.

    A1 lleva capacidad -1 y ningún contador (C-05); A2 lleva el modelo con dos espacios (C-13); B1 es de arranque.
    """
    return pa.table({
        "fecha": pa.array(pd.to_datetime(["2020-01-01"] * 4), type=pa.timestamp("ms")),
        "date": ["2020-01-01"] * 4,
        "serial_number": ["A1", "A2", "A3", "B1"],
        "model": [ST4, WD14B, WD14, SSD],
        "capacity_bytes": pa.array([-1, C14, C14, C025], type=pa.int64()),
        "failure": pa.array([0, 0, 0, 0], type=pa.int64()),
        "smart_5_raw": pa.array([None, 0.0, 1.0, 0.0], type=pa.float64()),
        "smart_9_raw": pa.array([None, 100.0, 200.0, 300.0], type=pa.float64()),
        "datacenter": pa.nulls(4),
    })


def foto_con_sitio():
    """Foto de julio de 2023: con sitio, la ranura como decimal con un vacío (C-04) y un contador que la otra no trae.

    A1 lleva 0,1 TB (C-05); A2 ya trae el nombre bueno; B1 es de arranque, sin ranura.
    """
    return pa.table({
        "fecha": pa.array(pd.to_datetime(["2023-07-01"] * 4), type=pa.timestamp("ms")),
        "date": ["2023-07-01"] * 4,
        "serial_number": ["A1", "A2", "A3", "B1"],
        "model": [ST4, WD14, WD14, SSD],
        "capacity_bytes": pa.array([100000000000, C14, C14, C025], type=pa.int64()),
        "failure": pa.array([0, 0, 0, 0], type=pa.int64()),
        "smart_5_raw": pa.array([0.0, 0.0, 2.0, 0.0], type=pa.float64()),
        "smart_9_raw": pa.array([1000.0, 1100.0, 1200.0, 1300.0], type=pa.float64()),
        "smart_187_raw": pa.array([0.0, None, None, None], type=pa.float64()),
        "datacenter": ["sac0", "sac0", "phx1", "sac0"],
        "cluster_id": pa.array([0, 0, 1, 0], type=pa.int64()),
        "vault_id": pa.array([1000, 1000, 1001, 1000], type=pa.int64()),
        "pod_id": pa.array([1, 1, 2, 1], type=pa.int64()),
        "pod_slot_num": pa.array([3.0, 4.0, 5.0, None], type=pa.float64()),
    })


def ventana_2022(fallo_en_la_fila_mala=0):
    """Ventana del fallo de F1 el 11/12/2022 y de F2 el 20/12/2022, con el centro sin tipo.

    La fila de F1 del 10/12 dice 11/12 en su texto (C-17): es la que se quita, y F1 se queda sin día anterior.
    F2 lleva capacidad -1 el día antes de su fallo (C-06) y el modelo con dos espacios (C-13).
    """
    return pa.table({
        "fecha": pa.array(pd.to_datetime(["2022-12-09", "2022-12-10", "2022-12-11", "2022-12-19", "2022-12-20"]), type=pa.timestamp("ms")),
        "date": ["2022-12-09", "2022-12-11", "2022-12-11", "2022-12-19", "2022-12-20"],
        "serial_number": ["F1", "F1", "F1", "F2", "F2"],
        "model": [ST4, ST4, ST4, WD14B, WD14],
        "capacity_bytes": pa.array([C4, C4, C4, -1, C14], type=pa.int64()),
        "failure": pa.array([0, fallo_en_la_fila_mala, 1, 0, 1], type=pa.int64()),
        "smart_5_raw": pa.array([0.0, 0.0, 0.0, None, 3.0], type=pa.float64()),
        "smart_9_raw": pa.array([500.0, 524.0, 524.0, None, 900.0], type=pa.float64()),
        "datacenter": pa.nulls(5),
        "dia_fallo": pa.array(pd.to_datetime(["2022-12-11"] * 3 + ["2022-12-20"] * 2), type=pa.timestamp("ns")),
    })


def ventana_2023():
    """Ventana del fallo de F3 el 02/07/2023, con sitio y la ranura como decimal."""
    return pa.table({
        "fecha": pa.array(pd.to_datetime(["2023-07-01", "2023-07-02"]), type=pa.timestamp("ms")),
        "date": ["2023-07-01", "2023-07-02"],
        "serial_number": ["F3", "F3"],
        "model": [WD14, WD14],
        "capacity_bytes": pa.array([C14, C14], type=pa.int64()),
        "failure": pa.array([0, 1], type=pa.int64()),
        "smart_5_raw": pa.array([0.0, 0.0], type=pa.float64()),
        "smart_9_raw": pa.array([700.0, 724.0], type=pa.float64()),
        "datacenter": ["iad1", "iad1"],
        "cluster_id": pa.array([0, 0], type=pa.int64()),
        "vault_id": pa.array([1100, 1100], type=pa.int64()),
        "pod_id": pa.array([3, 3], type=pa.int64()),
        "pod_slot_num": pa.array([7.0, None], type=pa.float64()),
        "dia_fallo": pa.array(pd.to_datetime(["2023-07-02"] * 2), type=pa.timestamp("ns")),
    })


def recuento():
    """Recuento: el 01/01/2020 trae ST4 partido en -1 y su capacidad (C-07) y WD14 partido por los espacios (C-13)."""
    filas = [
        ("2020-01-01", ST4, C4, "sin dato", 10, 0),
        ("2020-01-01", ST4, -1, "sin dato", 2, 1),
        ("2020-01-01", WD14, C14, "sin dato", 5, 0),
        ("2020-01-01", WD14B, C14, "sin dato", 3, 0),
        ("2020-01-01", SSD, C025, "sin dato", 4, 0),
        ("2020-01-02", ST4, C4, "sin dato", 12, 0),
        ("2020-01-02", WD14, C14, "sin dato", 8, 1),
        ("2020-01-02", ST4, 100000000000, "sin dato", 1, 0),
    ]
    df = pd.DataFrame(filas, columns=["fecha", "model", "capacity_bytes", "datacenter", "discos", "fallos"])
    df["fecha"] = pd.to_datetime(df["fecha"]).astype("datetime64[ms]")
    return df


def fallos():
    """Lista de fallos de los tres discos de las ventanas."""
    return pd.DataFrame({"serial_number": ["F1", "F2", "F3"],
                         "dia_fallo": pd.to_datetime(["2022-12-11", "2022-12-20", "2023-07-02"]).astype("datetime64[ns]")})


def decisiones():
    """Fichero de decisiones del caso pequeño: el mapeo de los nombres, la regla de la capacidad y lo que no se toca."""
    real = json.loads((CASO / "contexto-proyecto" / "modelo" / "decisiones-correccion.json").read_text(encoding="utf-8"))
    real["modelos"]["mapeo"] = {WD14B: WD14}
    return real


def calidad(raw, estado="AVISO"):
    """JSON de calidad mínimo: los 30 problemas, la pendiente P-01 y la huella de la entrada del caso pequeño."""
    entradas = [{"ruta": f"data/raw/{k}", "sha256": v} for k, v in huella_carpeta(raw).items()]
    return {"skill": "calidad-datos", "fecha_datos": "2025-06-30", "entradas": entradas,
            "resultado": {"estado": estado}, "problemas": [{"id": f"C-{i:02d}"} for i in range(1, 31)],
            "pendientes": [{"id": "P-01", "problema": "C-17"}]}


def montar_caso(variante=None):
    """Crea el caso pequeño en la carpeta temporal; la variante pone un caso que tiene que salir mal."""
    if TMP.exists():
        shutil.rmtree(TMP)
    raw = TMP / "data" / "raw"
    pod = raw / "podado"
    (pod / "fotos_mensuales").mkdir(parents=True)
    (pod / "ventanas_fallo").mkdir(parents=True)
    (TMP / "informes").mkdir()
    (TMP / "contexto-proyecto" / "modelo").mkdir(parents=True)
    (raw / "Drive_Stats_Schema_Current.csv").write_text("date\r\nserial_number\r\n", encoding="utf-8")
    foto_a, foto_b = foto_sin_sitio(), foto_con_sitio()
    if variante == "dos_capacidades":
        # ST4 trae 4 TB en una foto y 6 TB en otra: no hay una única capacidad del modelo
        foto_b = foto_b.set_column(foto_b.schema.get_field_index("capacity_bytes"), "capacity_bytes",
                                   pa.array([6001175126016, C14, C14, C025], type=pa.int64()))
    pq.write_table(foto_a, pod / "fotos_mensuales" / "2020-01.parquet")
    pq.write_table(foto_b, pod / "fotos_mensuales" / "2023-07.parquet")
    v22 = ventana_2022(fallo_en_la_fila_mala=1 if variante == "fallo_en_fila_quitada" else 0)
    pq.write_table(v22, pod / "ventanas_fallo" / "data_Q4_2022.parquet")
    pq.write_table(ventana_2023(), pod / "ventanas_fallo" / "data_Q3_2023.parquet")
    rec = recuento()
    if variante == "sin_capacidad":
        # Un modelo que solo llega con -1: no hay capacidad del modelo que poner
        rec.loc[len(rec)] = [pd.Timestamp("2020-01-02"), "MODELO_SIN_CAPACIDAD", -1, "sin dato", 1, 0]
    rec.to_parquet(pod / "recuento_diario.parquet", index=False)
    fallos().to_parquet(pod / "fallos.parquet", index=False)
    (TMP / "contexto-proyecto" / "modelo" / "decisiones-correccion.json").write_text(
        json.dumps(decisiones(), ensure_ascii=False, indent=2), encoding="utf-8")
    estado = "PARADO" if variante == "calidad_parada" else "AVISO"
    (TMP / "informes" / "calidad-datos.json").write_text(json.dumps(calidad(raw, estado), ensure_ascii=False), encoding="utf-8")
    return raw


def ejecutar():
    """Ejecuta el script sobre el caso pequeño con -W error y devuelve el proceso terminado."""
    return subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)],
                          capture_output=True, text=True, encoding="utf-8", env={"PYTHONUTF8": "1", **__import__("os").environ})


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 1: el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def parte_1():
    """Ejecuta la corrección sobre el caso pequeño y comprueba sus salidas."""
    comprobar("existe el script", SCRIPT.exists(), str(SCRIPT))
    if not SCRIPT.exists():
        return
    raw = montar_caso()
    antes = huella_carpeta(raw)
    p = ejecutar()
    comprobar("el script termina sin error ni aviso", p.returncode == 0, (p.stderr or p.stdout)[-1500:])
    if p.returncode != 0:
        return
    comprobar("data/raw intacto", huella_carpeta(raw) == antes)
    proc = TMP / "data" / "processed"
    js = json.loads((TMP / "informes" / "correccion-datos.json").read_text(encoding="utf-8"))
    texto_json = (TMP / "informes" / "correccion-datos.json").read_text(encoding="utf-8")
    comprobar("JSON sin NaN ni Infinity", "NaN" not in texto_json and "Infinity" not in texto_json)
    comprobar("estado AVISO", js["resultado"]["estado"] == "AVISO", js["resultado"]["estado"])
    comprobar("fecha_datos", js.get("fecha_datos") == "2025-06-30")
    comprobar("va_a_modelo", js.get("va_a_modelo") is True)

    # Fotos: las mismas filas, sin capacidad no válida, sin dos espacios, centro texto, ranura entera, fecha del texto
    f = pq.read_table(proc / "fotos_mensuales_corregido.parquet")
    df = f.to_pandas()
    comprobar("fotos: mismas filas", len(df) == 8, len(df))
    comprobar("fotos: sin capacidad no válida", int((df["capacity_bytes"] < 2e11).sum()) == 0)
    comprobar("fotos: A1 toma la capacidad de su modelo", set(df.loc[df["serial_number"] == "A1", "capacity_bytes"]) == {C4})
    comprobar("fotos: sin modelos con dos espacios", not df["model"].str.contains("  ").any())
    comprobar("fotos: el centro es texto", pa.types.is_string(f.schema.field("datacenter").type), str(f.schema.field("datacenter").type))
    comprobar("fotos: la ranura es entera", pa.types.is_integer(f.schema.field("pod_slot_num").type), str(f.schema.field("pod_slot_num").type))
    comprobar("fotos: la ranura conserva sus vacíos", int(df["pod_slot_num"].isna().sum()) == 5, int(df["pod_slot_num"].isna().sum()))
    comprobar("fotos: date es fecha", pa.types.is_timestamp(f.schema.field("date").type), str(f.schema.field("date").type))
    comprobar("fotos: date igual a fecha", bool((df["date"] == df["fecha"]).all()))
    comprobar("fotos: la columna que una foto no trae queda vacía", int(df["smart_187_raw"].isna().sum()) == 7)
    comprobar("fotos: ningún vacío rellenado en los contadores", int(df["smart_5_raw"].isna().sum()) == 1 and int(df["smart_9_raw"].isna().sum()) == 1)
    comprobar("fotos: contadores sin tocar", float(df["smart_9_raw"].sum()) == 100 + 200 + 300 + 1000 + 1100 + 1200 + 1300)
    comprobar("fotos: el centro sin dato sigue vacío", int(df["datacenter"].isna().sum()) == 4)

    # Ventanas: sale la fila del 10/12 y F1 se queda sin día anterior
    v = pq.read_table(proc / "ventanas_fallo_corregido.parquet").to_pandas()
    comprobar("ventanas: sale una fila", len(v) == 6, len(v))
    comprobar("ventanas: ya no hay fila del 10/12/2022", not (v["fecha"] == pd.Timestamp("2022-12-10")).any())
    comprobar("ventanas: sin capacidad no válida", int((v["capacity_bytes"] < 2e11).sum()) == 0)
    comprobar("ventanas: sin dos espacios", not v["model"].str.contains("  ").any())
    comprobar("ventanas: los fallos siguen", int(v["failure"].sum()) == 3)
    sd = js["controles"]["ventanas.fallos_datos_sin_dia_anterior"]
    comprobar("ventanas: fallos de datos sin día anterior, 0 antes y 1 después", sd == {"antes": 0, "despues": 1}, sd)

    # Recuento: suma las filas que quedan con la misma clave, y las sumas no cambian
    r = pq.read_table(proc / "recuento_diario_corregido.parquet").to_pandas()
    rr = recuento()
    comprobar("recuento: 8 filas pasan a 5", len(r) == 5, len(r))
    comprobar("recuento: suma de discos igual", int(r["discos"].sum()) == int(rr["discos"].sum()))
    comprobar("recuento: suma de fallos igual", int(r["fallos"].sum()) == int(rr["fallos"].sum()))
    st4 = r.loc[(r["fecha"] == pd.Timestamp("2020-01-01")) & (r["model"] == ST4)]
    comprobar("recuento: ST4 del 01/01 junta 12 discos y 1 fallo", len(st4) == 1 and int(st4["discos"].iloc[0]) == 12 and int(st4["fallos"].iloc[0]) == 1)
    wd = r.loc[(r["fecha"] == pd.Timestamp("2020-01-01")) & (r["model"] == WD14)]
    comprobar("recuento: WD14 del 01/01 junta 8 discos", len(wd) == 1 and int(wd["discos"].iloc[0]) == 8)
    por_dia_a = rr.groupby("fecha")[["discos", "fallos"]].sum()
    por_dia_d = r.groupby("fecha")[["discos", "fallos"]].sum()
    comprobar("recuento: las sumas de cada día no cambian", por_dia_a.equals(por_dia_d))
    comprobar("recuento: la clave queda única", not r.duplicated(["fecha", "model", "capacity_bytes", "datacenter"]).any())

    # Fallos: igual
    fl = pq.read_table(proc / "fallos_corregido.parquet").to_pandas()
    comprobar("fallos: mismas filas", len(fl) == 3)

    # JSON: correcciones solo con cambio, cada problema una vez, sin_cambios del fichero de decisiones
    ids = [c["problema_calidad"] for c in js["correcciones"] if c["problema_calidad"]]
    sin = [s["problema_calidad"] for s in js["sin_cambios"]]
    comprobar("cada problema de calidad, en corregido o en sin_cambios", sorted(set(ids) | set(sin)) == [f"C-{i:02d}" for i in range(1, 31)],
              sorted(set(ids) | set(sin)))
    comprobar("ningún problema en los dos sitios", not (set(ids) & set(sin)), set(ids) & set(sin))
    comprobar("ninguna corrección 0 → 0", all(c["antes"] != c["despues"] for c in js["correcciones"]))
    comprobar("P-01 resuelta en decisiones_usuario", any(d["pendiente"] == "P-01" for d in js["decisiones_usuario"]))
    comprobar("sin pendientes", js["pendientes"] == [])
    comprobar("sumas de control coinciden", all(s["coincide"] for s in js["sumas_control"]) and len(js["sumas_control"]) >= 4)
    comprobar("cuatro salidas con su diccionario", len(js["salidas"]) == 4 and all(s["campos_salida"] for s in js["salidas"]))
    comprobar("nombres: ninguno cambia", js["nombres"] == [])
    c19 = [s for s in js["sin_cambios"] if s["problema_calidad"] == "C-19"][0]["motivo"]
    comprobar("C-19 con su cifra calculada", "{" not in c19 and re.search(r"\d", c19) is not None, c19)

    # Informe: los apartados de la plantilla, en orden
    md = (TMP / "informes" / "correccion-datos.md").read_text(encoding="utf-8")
    pos = [md.find(f"## {a}") for a in APARTADOS]
    comprobar("informe con los apartados en orden", all(x >= 0 for x in pos) and pos == sorted(pos), pos)

    # Registro: una ficha por corrección y una por lo que no se toca; reejecutar no añade fichas
    reg = TMP / "contexto-proyecto" / "modelo" / "registro-transformaciones.md"
    fichas = re.findall(r"^## R-\d{3}", reg.read_text(encoding="utf-8"), re.M)
    comprobar("registro con fichas", len(fichas) >= 8, len(fichas))
    p2 = ejecutar()
    fichas2 = re.findall(r"^## R-\d{3}", reg.read_text(encoding="utf-8"), re.M)
    comprobar("reejecutar no añade fichas", p2.returncode == 0 and len(fichas2) == len(fichas), (len(fichas), len(fichas2)))
    comprobar("data/raw intacto tras dos ejecuciones", huella_carpeta(raw) == antes)


def parte_1_casos_que_fallan():
    """Cada variante tiene que hacer parar al script sin dejar ningún dataset corregido."""
    if not SCRIPT.exists():
        return
    for variante, estado in (("dos_capacidades", "ERROR"), ("sin_capacidad", "ERROR"), ("fallo_en_fila_quitada", "ERROR"),
                             ("calidad_parada", "PARADO")):
        montar_caso(variante)
        p = ejecutar()
        ruta = TMP / "informes" / "correccion-datos.json"
        js = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
        comprobar(f"{variante}: el script para", p.returncode != 0, p.returncode)
        comprobar(f"{variante}: estado {estado}", js.get("resultado", {}).get("estado") == estado, js.get("resultado", {}).get("estado"))
        proc = TMP / "data" / "processed"
        comprobar(f"{variante}: no deja datasets corregidos", not proc.exists() or not any(proc.glob("*.parquet")))


def parte_1_codigo():
    """Ninguna comprobación escrita con su resultado puesto (programacion-del-caso, error 24)."""
    if not SCRIPT.exists():
        return
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestas = re.findall(r'"(?:ok|coincide|pasa)"\s*:\s*True', codigo)
    comprobar("ninguna comprobación con True escrito", not puestas, puestas)
    comprobar("sin filterwarnings", "filterwarnings" not in codigo)


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 2: las salidas reales, por otro camino
# ---------------------------------------------------------------------------------------------------------------
def parte_2():
    """Compara las cifras de control reales con las de referencia y rehace varias desde data/raw/ con pandas."""
    ruta = CASO / "informes" / "correccion-datos.json"
    if not ruta.exists():
        print("salta  parte 2: no existe informes/correccion-datos.json")
        return
    js = json.loads(ruta.read_text(encoding="utf-8"))
    ref = json.loads((CASO / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8")).get("cifras_correccion", {})
    comprobar("hay cifras de corrección de referencia", bool(ref), "falta la clave cifras_correccion")
    plano = {}
    for clave, valor in js["controles"].items():
        if isinstance(valor, dict):
            for k, x in valor.items():
                plano[f"{clave}.{k}"] = x
        else:
            plano[clave] = valor
    for clave, esperado in ref.items():
        comprobar(f"cifra {clave}", plano.get(clave) == esperado, f"sale {plano.get(clave)}, referencia {esperado}")

    raw = CASO / "data" / "raw" / "podado"
    proc = CASO / "data" / "processed"
    # Vía independiente 1: el recuento en bruto con pandas, sumado por día, frente al corregido
    rec_a = pd.read_parquet(raw / "recuento_diario.parquet")
    rec_d = pd.read_parquet(proc / "recuento_diario_corregido.parquet")
    comprobar("recuento: discos por día iguales (pandas, bruto frente a corregido)",
              rec_a.groupby("fecha")["discos"].sum().equals(rec_d.groupby("fecha")["discos"].sum()))
    comprobar("recuento: fallos por día iguales", rec_a.groupby("fecha")["fallos"].sum().equals(rec_d.groupby("fecha")["fallos"].sum()))
    comprobar("recuento: fallos totales iguales a la lista de fallos",
              int(rec_d["fallos"].sum()) == len(pd.read_parquet(raw / "fallos.parquet")))
    # Vía independiente 2: las ventanas en bruto con pandas, quitando las filas cuya fecha no es su texto
    piezas = [pd.read_parquet(p, columns=["fecha", "date", "failure"]) for p in sorted((raw / "ventanas_fallo").glob("*.parquet"))]
    ven = pd.concat(piezas, ignore_index=True)
    distinta = ven["fecha"].dt.strftime("%Y-%m-%d") != ven["date"]
    filas_v = pq.ParquetFile(proc / "ventanas_fallo_corregido.parquet").metadata.num_rows
    comprobar("ventanas: filas en bruto menos fecha distinta del texto", len(ven) - int(distinta.sum()) == filas_v, (len(ven), int(distinta.sum()), filas_v))
    comprobar("ventanas: las filas quitadas no traen ningún fallo", int(ven.loc[distinta, "failure"].sum()) == 0)
    comprobar("ventanas: los fallos se conservan", int(ven["failure"].sum()) == int(pq.read_table(proc / "ventanas_fallo_corregido.parquet", columns=["failure"]).column(0).to_pandas().sum()))
    # Vía independiente 3: filas de las fotos desde los metadatos de cada fichero en bruto, y capacidades corregidas
    filas_f = sum(pq.ParquetFile(p).metadata.num_rows for p in (raw / "fotos_mensuales").glob("*.parquet"))
    cap = pq.read_table(proc / "fotos_mensuales_corregido.parquet", columns=["capacity_bytes", "model"]).to_pandas()
    comprobar("fotos: filas iguales que en bruto", len(cap) == filas_f, (len(cap), filas_f))
    comprobar("fotos: ninguna capacidad no válida", int((cap["capacity_bytes"] < 2e11).sum()) == 0)
    comprobar("fotos: una sola capacidad por modelo", int(cap.groupby("model")["capacity_bytes"].nunique().max()) == 1)
    comprobar("fotos: ningún modelo con dos espacios", not cap["model"].drop_duplicates().str.contains("  ").any())


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print("sys.executable:", sys.executable)
    try:
        parte_1()
        parte_1_casos_que_fallan()
        parte_1_codigo()
        parte_2()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\ntodos los casos pasan")
    sys.exit(1 if FALLOS else 0)
