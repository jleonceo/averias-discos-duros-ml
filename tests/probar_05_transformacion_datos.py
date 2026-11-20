"""Prueba de scripts/05_transformacion_datos.py.

Parte 1: monta en tests/tmp_transformacion/ un caso pequeño con las cuatro tablas corregidas y el Calendario escritos
aquí (siete fotos mensuales, de enero a julio de 2024, cada una en su propio bloque del Parquet; las ventanas de 14
fallos; el recuento diario sacado de las fotos y una celda sin ninguna foto), con el JSON de la corrección, el del
diseño con su plan de cruces y una copia corta del registro de transformaciones. Ejecuta el script con -W error y
comprueba los casos que la petición pide, cada uno con su caso que tiene que salir mal:
  - un fallo el día del borde del horizonte entra, y uno al día siguiente no;
  - el horizonte de la foto del 01/06/2024 acaba el 30/06/2024;
  - un fallo que cae en el horizonte de dos fotos da objetivo 1 en las dos;
  - dos fallos del mismo tomo separados por el plazo exacto no coinciden, y con un día menos sí;
  - un disco que falla y después desaparece acaba en «fallo»;
  - una celda del recuento sin foto no entra en dias_por_tramo y se cuenta;
  - un fallo sin día anterior deja sin_aviso vacío, y un contador vacío no cuenta como aviso;
  - una columna de fotos_riesgo sin grupo para el script;
  - el precio de una capacidad sin curva ese día es la media de sus dos vecinas.
Además: una edad negativa para el script, una fila repetida en la ventana para el cruce 1, una segunda ejecución no
añade fichas al registro, y las huellas de la entrada no cambian.
Parte 2: si ya existe informes/transformacion-datos.json real, compara sus cifras de control con
tests/cifras_de_referencia.json (clave «transformacion»).

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import hashlib
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
SCRIPT = CASO / "scripts" / "05_transformacion_datos.py"
TMP = CASO / "tests" / "tmp_transformacion"
FALLOS = []

ST4, HUH10, WD6, SSD = "ST4000DM000", "HGST HUH721010ALE600", "WDC WD60EFRX", "Seagate SSD"
CAP = {ST4: 4000787030016, HUH10: 10000831348736, WD6: 6001175126016, SSD: 250059350016}
MESES = pd.date_range("2024-01-01", "2024-07-01", freq="MS")
CONTADORES = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]
OTRAS_SMART = ["smart_1_raw", "smart_7_raw", "smart_9_normalized", "smart_12_raw", "smart_192_raw", "smart_194_raw",
               "smart_199_raw", "smart_241_raw"]
COMPRA_10TB = pd.Timestamp("2017-09-15")


def comprobar(nombre, condicion, detalle=""):
    """Apunta un caso que falla, con su nombre y lo que se vio."""
    if not condicion:
        FALLOS.append(f"{nombre}: {detalle}")
        print(f"FALLA  {nombre}  {detalle}")
    else:
        print(f"pasa   {nombre}")


def sha(ruta):
    """SHA-256 de un fichero."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------------------------
# 2. Datos pequeños escritos en la prueba
# ---------------------------------------------------------------------------------------------------------------
# Cada disco: modelo, meses con foto, centro, vault, servidor, ranura y horas de la primera foto (None: sin horas)
HORAS_D3 = (pd.Timestamp("2024-02-01") - COMPRA_10TB) / pd.Timedelta(hours=1)
DISCOS = {
    "A1": (ST4, list(range(7)), "sac0", 1000, 1, 3, 10000.0),
    "A2": (ST4, list(range(7)), None, None, None, None, None),
    "B1": (SSD, list(range(7)), "sac0", None, None, None, 5000.0),
    "D1": (ST4, [0], None, None, None, None, 20000.0),
    "D2": (ST4, [0, 1], "sac0", 1000, 2, 4, 21000.0),
    "D3": (HUH10, [1, 2], "sac2", 4000, 1, 1, HORAS_D3 - 720.0),   # en su primera foto (k = 1) lleva HORAS_D3
    "D4": (ST4, [5, 6], "sac0", 1000, 3, 5, 22000.0),
    "D5": (ST4, [0, 1], "sac0", 1000, 4, 6, 23000.0),
    "G1": (ST4, [0, 1, 2], "sac0", 1000, 5, 8, 30000.0),
    "K1": (ST4, [0, 2], "sac0", 1000, 6, 10, 31000.0),
    "E1": (ST4, [1, 2], "sac0", 2000, 1, 7, 12000.0),
    "E2": (ST4, [1, 2], "sac0", 2000, 2, 7, 12500.0),
    "E4": (ST4, [2, 3], "phx1", 3000, 2, 9, 13000.0),
    "H1": (ST4, [3, 4], "sac0", 1000, 7, 11, 14000.0),
    "H2": (ST4, [4], "sac0", 1000, 8, 12, None),
    "W1": (WD6, list(range(7)), "sac0", 1000, 9, 13, 40000.0),
}
# Fallos: disco y día. D1 cae el último día del horizonte de su foto; D2, al día siguiente del de la suya
FALLO = {"D1": "2024-01-31", "D2": "2024-02-01", "D3": "2024-03-02", "D4": "2024-07-01", "D5": "2024-02-10",
         "E1": "2024-03-10", "E2": "2024-03-15", "E3": "2024-04-10", "E4": "2024-04-14", "H1": "2024-05-20",
         "H2": "2024-05-25"}


def filas_fotos(variante=None):
    """Una fila por disco y foto mensual, con failure = 1 en la foto del día del fallo."""
    filas = []
    for serie, (modelo, meses, dc, vault, pod, ranura, horas0) in DISCOS.items():
        for k in meses:
            mes = MESES[k]
            horas = None if horas0 is None else horas0 + 720.0 * k
            c = {x: 0.0 for x in CONTADORES} if serie != "A2" else {x: None for x in CONTADORES}
            if serie == "A1" and k >= 3:
                c["smart_5_raw"] = 2.0           # A1 empieza a avisar en abril: su cambio es 2
            if serie == "G1" and k == 2:
                c["smart_5_raw"] = 3.0           # G1 avisa en su última foto y desaparece
            if serie == "B1":
                c = {x: None for x in CONTADORES}
            fila = {"fecha": mes, "date": mes, "serial_number": serie, "model": modelo, "capacity_bytes": CAP[modelo],
                    "failure": int(FALLO.get(serie) == mes.strftime("%Y-%m-%d")), "datacenter": dc, "cluster_id": None,
                    "vault_id": vault, "pod_id": pod, "pod_slot_num": ranura, "smart_9_raw": horas, **c}
            for x in OTRAS_SMART:
                fila[x] = 1.0
            filas.append(fila)
    df = pd.DataFrame(filas)
    if variante == "edad_negativa":
        df.loc[(df["serial_number"] == "A1") & (df["fecha"] == MESES[0]), "smart_9_raw"] = -100.0
    if variante == "columna_sin_grupo":
        df["columna_rara"] = 1
    return df


def escribir_fotos(df, ruta):
    """Escribe las fotos con un bloque por mes, como la tabla corregida."""
    esquema = pa.schema([("fecha", pa.timestamp("ms")), ("date", pa.timestamp("ms")), ("serial_number", pa.string()),
                         ("model", pa.string()), ("capacity_bytes", pa.int64()), ("failure", pa.int64()),
                         ("datacenter", pa.string()), ("cluster_id", pa.int64()), ("vault_id", pa.int64()),
                         ("pod_id", pa.int64()), ("pod_slot_num", pa.int64())]
                        + [(x, pa.float64()) for x in sorted(set(CONTADORES + OTRAS_SMART + ["smart_9_raw"]))]
                        + ([("columna_rara", pa.int64())] if "columna_rara" in df.columns else []))
    with pq.ParquetWriter(ruta, esquema) as w:
        for mes in MESES:
            parte = df.loc[df["fecha"] == mes]
            w.write_table(pa.Table.from_pandas(parte, schema=esquema, preserve_index=False))


def filas_ventanas(variante=None):
    """El día anterior y el del fallo de cada ventana; H2 no trae el día anterior y E3 no sale en ninguna foto."""
    sitio = {s: v[2:6] for s, v in DISCOS.items()}
    sitio["E3"] = ("phx1", 3000, 1, 9)
    modelo = {s: v[0] for s, v in DISCOS.items()}
    modelo["E3"] = ST4
    filas = []
    for serie, dia in FALLO.items():
        dia = pd.Timestamp(dia)
        dias = [dia] if serie == "H2" else [dia - pd.Timedelta(days=1), dia]
        for d in dias:
            dc, vault, pod, ranura = sitio[serie]
            if serie.startswith("E") and d == dia:
                ranura = None                    # el día del fallo llega sin ranura: el tomo sale del día anterior
            c = {x: 0.0 for x in CONTADORES}
            if serie == "H1" and d < dia:
                c = {"smart_5_raw": None, "smart_187_raw": 0.0, "smart_188_raw": None, "smart_197_raw": None,
                     "smart_198_raw": None}     # contadores vacíos y un cero: no avisa
            horas = None if serie in ("H2", "E3") else 15000.0
            filas.append({"fecha": d, "date": d, "dia_fallo": dia, "serial_number": serie, "model": modelo[serie],
                          "capacity_bytes": CAP[modelo[serie]], "failure": int(d == dia), "datacenter": dc,
                          "cluster_id": None, "vault_id": vault, "pod_id": pod, "pod_slot_num": ranura,
                          "smart_9_raw": horas, **c})
    df = pd.DataFrame(filas)
    if variante == "ventana_repetida":
        df = pd.concat([df, df.loc[(df["serial_number"] == "D1") & (df["fecha"] == df["dia_fallo"])]], ignore_index=True)
    return df


def tabla_ventanas(df):
    """Las ventanas con los tipos de la tabla corregida: dia_fallo en nanosegundos y fecha en milisegundos."""
    esquema = pa.schema([("fecha", pa.timestamp("ms")), ("date", pa.timestamp("ms")), ("dia_fallo", pa.timestamp("ns")),
                         ("serial_number", pa.string()), ("model", pa.string()), ("capacity_bytes", pa.int64()),
                         ("failure", pa.int64()), ("datacenter", pa.string()), ("cluster_id", pa.int64()),
                         ("vault_id", pa.int64()), ("pod_id", pa.int64()), ("pod_slot_num", pa.int64()),
                         ("smart_9_raw", pa.float64())] + [(x, pa.float64()) for x in CONTADORES])
    return pa.Table.from_pandas(df, schema=esquema, preserve_index=False)


def tabla_recuento(fotos):
    """Recuento diario sacado de las fotos (cada día del mes, los discos de su foto) y una celda sin ninguna foto."""
    fotos = fotos.assign(centro=fotos["datacenter"].fillna("sin dato"))
    filas = []
    for mes, g in fotos.groupby("fecha"):
        cuenta = g.groupby(["model", "centro"]).size()
        for dia in pd.date_range(mes, mes + pd.offsets.MonthEnd(0), freq="D"):
            for (modelo, centro), n in cuenta.items():
                filas.append({"fecha": dia, "model": modelo, "capacity_bytes": CAP[modelo], "datacenter": centro,
                              "discos": int(n), "fallos": 0})
    # La celda sin foto: el modelo de 6 TB en iad1 todo marzo, sin ninguna foto ahí
    for dia in pd.date_range("2024-03-01", "2024-03-31", freq="D"):
        filas.append({"fecha": dia, "model": WD6, "capacity_bytes": CAP[WD6], "datacenter": "iad1", "discos": 2,
                      "fallos": 0})
    rec = pd.DataFrame(filas)
    centro = {s: (v[2] or "sin dato") for s, v in DISCOS.items()}
    centro["E3"] = "phx1"
    for serie, dia in FALLO.items():
        modelo = DISCOS[serie][0] if serie in DISCOS else ST4
        sel = (rec["fecha"] == pd.Timestamp(dia)) & (rec["model"] == modelo) & (rec["datacenter"] == centro[serie])
        if sel.any():
            rec.loc[sel.idxmax(), "fallos"] += 1
        else:
            rec = pd.concat([rec, pd.DataFrame([{"fecha": pd.Timestamp(dia), "model": modelo, "capacity_bytes": CAP[modelo],
                                                 "datacenter": centro[serie], "discos": 1, "fallos": 1}])],
                            ignore_index=True)
    esquema = pa.schema([("fecha", pa.timestamp("ms")), ("model", pa.string()), ("capacity_bytes", pa.int64()),
                         ("datacenter", pa.string()), ("discos", pa.int64()), ("fallos", pa.int64())])
    return pa.Table.from_pandas(rec, schema=esquema, preserve_index=False)


def tabla_calendario():
    """El Calendario del caso, del 01/01/2020 al 30/06/2025, con su periodo."""
    f = pd.date_range("2020-01-01", "2025-06-30", freq="D")
    cal = pd.DataFrame({"fecha": f, "ano": f.year.astype("int64"), "trimestre": f.quarter.astype("int64"),
                        "mes": f.month.astype("int64")})
    cal["periodo"] = np.where(cal["fecha"] <= pd.Timestamp("2024-06-30"), "construcción", "validación")
    cal["trimestre_completo"] = True
    cal["ano_completo"] = cal["ano"] < 2025
    esquema = pa.schema([("fecha", pa.timestamp("ms")), ("ano", pa.int64()), ("trimestre", pa.int64()),
                         ("mes", pa.int64()), ("periodo", pa.string()), ("trimestre_completo", pa.bool_()),
                         ("ano_completo", pa.bool_())])
    return pa.Table.from_pandas(cal, schema=esquema, preserve_index=False)


PLAN = {1: "1:1", 2: "1:1", 3: "1:1", 4: "N:1", 5: "N:1", 6: "N:1", 7: "N:1", 8: "N:1", 9: "N:1", 10: "N:1",
        11: "N:1", 12: "N:1", 13: "N:1", 14: "N:1", 15: "1:1"}


def montar(variante=None):
    """Monta el caso pequeño en TMP."""
    if TMP.exists():
        shutil.rmtree(TMP)
    proc = TMP / "data" / "processed"
    proc.mkdir(parents=True)
    (TMP / "informes").mkdir()
    (TMP / "config" / "modelo").mkdir(parents=True)
    fotos = filas_fotos(variante)
    escribir_fotos(fotos, proc / "fotos_mensuales_corregido.parquet")
    pq.write_table(tabla_ventanas(filas_ventanas(variante)), proc / "ventanas_fallo_corregido.parquet")
    pq.write_table(tabla_recuento(filas_fotos()), proc / "recuento_diario_corregido.parquet")
    fl = pd.DataFrame({"serial_number": list(FALLO), "dia_fallo": pd.to_datetime(list(FALLO.values()))})
    pq.write_table(pa.Table.from_pandas(fl, schema=pa.schema([("serial_number", pa.string()),
                                                              ("dia_fallo", pa.timestamp("ns"))]),
                                        preserve_index=False), proc / "fallos_corregido.parquet")
    pq.write_table(tabla_calendario(), proc / "calendario.parquet")
    salidas = [{"tabla": t, "ruta": f"data/processed/{f}", "sha256": sha(proc / f)}
               for t, f in (("fotos_mensuales", "fotos_mensuales_corregido.parquet"),
                            ("ventanas_fallo", "ventanas_fallo_corregido.parquet"),
                            ("recuento_diario", "recuento_diario_corregido.parquet"),
                            ("fallos", "fallos_corregido.parquet"))]
    (TMP / "informes" / "correccion-datos.json").write_text(json.dumps(
        {"resultado": {"estado": "AVISO"}, "salidas": salidas}, ensure_ascii=False), encoding="utf-8")
    plan = [{"orden": o, "partida": "p", "se_une": "u", "cardinalidad": c} for o, c in PLAN.items()]
    (TMP / "informes" / "modelado-datos.json").write_text(json.dumps(
        {"resultado": {"estado": "OK"}, "aprobado": {"aprobado": True}, "plan_cruces": plan}, ensure_ascii=False),
        encoding="utf-8")
    (TMP / "config" / "modelo" / "registro-transformaciones.md").write_text(
        "---\ntitulo: registro de prueba\n---\n\n# Registro de transformaciones\n\n## R-009 · prueba · nada\n\n"
        "Ficha de prueba.\n", encoding="utf-8")
    return fotos


def ejecutar():
    """Ejecuta el script sobre el caso pequeño con -W error."""
    return subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)],
                          capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})


def leer_json():
    """El JSON que deja el script, o None si no existe."""
    ruta = TMP / "informes" / "transformacion-datos.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def leer(tabla):
    """Una tabla de salida del caso pequeño, o None si no existe."""
    ruta = TMP / "data" / "processed" / f"{tabla}.parquet"
    return pd.read_parquet(ruta) if ruta.exists() else None


def recta(puntos, dia):
    """Valor en un día de una curva de puntos (fecha, dólares por GB), recta entre puntos; cálculo propio de la prueba."""
    x = [(pd.Timestamp(f) - pd.Timestamp("2000-01-01")) / pd.Timedelta(days=1) for f, _ in puntos]
    return float(np.interp((pd.Timestamp(dia) - pd.Timestamp("2000-01-01")) / pd.Timedelta(days=1), x,
                           [v for _, v in puntos]))


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 1: el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def fila(df, **clave):
    """La única fila de df con esos valores, o None."""
    sel = np.ones(len(df), dtype=bool)
    for k, v in clave.items():
        sel &= (df[k] == (pd.Timestamp(v) if k in ("fecha", "dia_fallo", "mes") else v)).to_numpy()
    return df.loc[sel].iloc[0] if sel.sum() == 1 else None


def parte_1():
    """Ejecución normal: los nueve casos de la petición y las salidas."""
    if not SCRIPT.exists():
        comprobar("existe scripts/05_transformacion_datos.py", False, "no existe")
        return
    fotos = montar()
    huellas_antes = {p.name: sha(p) for p in (TMP / "data" / "processed").glob("*.parquet")}
    p = ejecutar()
    js = leer_json()
    comprobar("el script termina con 0", p.returncode == 0, p.stderr[-3000:] + p.stdout[-1500:])
    if js is None:
        comprobar("deja el JSON", False, "no existe")
        return
    comprobar("estado OK o AVISO", js["resultado"]["estado"] in ("OK", "AVISO"), js["resultado"])
    comprobar("fecha_datos 2025-06-30", js.get("fecha_datos") == "2025-06-30", js.get("fecha_datos"))
    comprobar("deja el informe Markdown", (TMP / "informes" / "transformacion-datos.md").exists())
    comprobar("nueve salidas", len(js.get("salidas", [])) == 9, [s["tabla"] for s in js.get("salidas", [])])
    for p_ in (TMP / "data" / "processed").glob("*.parquet"):
        if p_.name in huellas_antes:
            comprobar(f"huella de {p_.name} sin cambiar", sha(p_) == huellas_antes[p_.name])
    comprobar("ningún fichero parcial queda", not list((TMP / "data" / "processed").glob("*.parcial")))

    fr, fd, vd = leer("fotos_riesgo"), leer("fallos_detalle"), leer("vida_discos")
    dpt, dm, dpg = leer("dias_por_tramo"), leer("dim_modelo"), leer("dim_precio_gb")
    if any(x is None for x in (fr, fd, vd, dpt, dm, dpg)):
        comprobar("existen las tablas de salida", False, "falta alguna")
        return

    # fotos_riesgo: sin arranque ni foto del día del fallo; sin failure, date ni cluster_id
    esperadas = int(((fotos["model"] != SSD) & (fotos["failure"] == 0)).sum())
    comprobar("fotos_riesgo: filas de datos sin la foto del día del fallo", len(fr) == esperadas, (len(fr), esperadas))
    comprobar("fotos_riesgo: sin failure, date ni cluster_id", not {"failure", "date", "cluster_id"} & set(fr.columns))
    comprobar("fotos_riesgo: ninguna foto del día del fallo", fila(fr, serial_number="D2", fecha="2024-02-01") is None)

    # Caso 1: el borde del horizonte
    d1, d2 = fila(fr, serial_number="D1", fecha="2024-01-01"), fila(fr, serial_number="D2", fecha="2024-01-01")
    comprobar("borde: el fallo del último día del horizonte entra", d1 is not None and d1["falla_30d"] == 1,
              None if d1 is None else d1["falla_30d"])
    comprobar("borde: el fallo del día siguiente no entra", d2 is not None and d2["falla_30d"] == 0,
              None if d2 is None else d2["falla_30d"])

    # Caso 2: el recorte del horizonte el 30/06/2024
    d4 = fila(fr, serial_number="D4", fecha="2024-06-01")
    comprobar("recorte: la foto del 01/06/2024 mira hasta el 30/06/2024",
              d4 is not None and d4["horizonte_hasta"] == pd.Timestamp("2024-06-30") and d4["falla_30d"] == 0,
              None if d4 is None else (d4["horizonte_hasta"], d4["falla_30d"]))
    a1 = fila(fr, serial_number="A1", fecha="2024-07-01")
    comprobar("validación: la foto del 01/07/2024 mira 30 días", a1 is not None
              and a1["horizonte_hasta"] == pd.Timestamp("2024-07-31") and a1["periodo"] == "validación")

    # Caso 3: un fallo en el horizonte de dos fotos
    f2, f3 = fila(fr, serial_number="D3", fecha="2024-02-01"), fila(fr, serial_number="D3", fecha="2024-03-01")
    comprobar("dos fotos: objetivo 1 en las dos", f2 is not None and f3 is not None and f2["falla_30d"] == 1
              and f3["falla_30d"] == 1, None if f2 is None or f3 is None else (f2["falla_30d"], f3["falla_30d"]))
    comprobar("dos fotos: el fallo se cuenta una vez",
              js["cifras_de_control"].get("fotos_riesgo.fallos_objetivo") == int(fr["falla_30d"].sum()) - 1,
              (js["cifras_de_control"].get("fotos_riesgo.fallos_objetivo"), int(fr["falla_30d"].sum())))

    # Caso 4: dos fallos del mismo tomo, con el plazo exacto y con un día menos
    e1, e2, e4 = (fila(fd, serial_number=s) for s in ("E1", "E2", "E4"))
    comprobar("tomo: el tomo sale del último día con ranura", e1 is not None and e1["tomo"] == "sac0|2000|7",
              None if e1 is None else e1["tomo"])
    comprobar("tomo: el primero de su tomo no tiene días", e1 is not None and pd.isna(e1["dias_desde_anterior_del_tomo"]))
    comprobar("tomo: con el plazo exacto no coincide", e2 is not None and e2["dias_desde_anterior_del_tomo"] == 5
              and e2["coincide_con_anterior"] == False,  # noqa: E712
              None if e2 is None else (e2["dias_desde_anterior_del_tomo"], e2["coincide_con_anterior"]))
    comprobar("tomo: con un día menos coincide", e4 is not None and e4["dias_desde_anterior_del_tomo"] == 4
              and e4["coincide_con_anterior"] == True,  # noqa: E712
              None if e4 is None else (e4["dias_desde_anterior_del_tomo"], e4["coincide_con_anterior"]))

    # Caso 5: un disco que falla y después desaparece acaba en «fallo»
    v = {s: fila(vd, serial_number=s) for s in ("D5", "G1", "K1", "A1", "E3")}
    comprobar("vida: falla y desaparece, acaba en fallo", v["D5"] is not None and v["D5"]["evento"] == "fallo",
              None if v["D5"] is None else v["D5"]["evento"])
    comprobar("vida: desaparece avisando", v["G1"] is not None and v["G1"]["evento"] == "desaparece"
              and v["G1"]["desaparece_avisando"] == True)  # noqa: E712
    comprobar("vida: desaparece sin avisar", v["K1"] is not None and v["K1"]["evento"] == "desaparece"
              and v["K1"]["desaparece_avisando"] == False)  # noqa: E712
    comprobar("vida: sigue", v["A1"] is not None and v["A1"]["evento"] == "sigue")
    comprobar("vida: el disco que solo sale en su ventana", v["E3"] is not None and pd.isna(v["E3"]["ultima_foto"])
              and v["E3"]["primera_aparicion"] == pd.Timestamp("2024-04-09"))
    comprobar("vida: sin discos de arranque", "B1" not in set(vd["serial_number"]))

    # Caso 6: una celda del recuento sin foto
    sin = dpt.loc[(dpt["model"] == WD6) & (dpt["centro"] == "iad1")]
    comprobar("tramo: la celda sin foto no entra", sin.empty, len(sin))
    exc = {e["clase"]: e for e in js.get("exclusiones", [])}
    dsf = exc.get("dias_sin_foto", {}).get("recuentos", {})
    comprobar("tramo: sus días se cuentan", dsf.get("dias_de_disco") == 62 and dsf.get("celdas") == 1, dsf)
    comprobar("tramo: G1 desaparece avisando en el mes y la edad de su última foto",
              int(dpt.loc[(dpt["mes"] == pd.Timestamp("2024-03-01")) & (dpt["model"] == ST4)
                          & (dpt["centro"] == "sac0"), "desaparecen_avisando"].sum()) == 1)

    # Caso 7: sin día anterior y contador vacío
    h1, h2 = fila(fd, serial_number="H1"), fila(fd, serial_number="H2")
    comprobar("aviso: sin día anterior, sin_aviso vacío", h2 is not None and h2["hay_dia_anterior"] == False  # noqa: E712
              and pd.isna(h2["sin_aviso"]) and pd.isna(h2["avisa_dia_anterior"]),
              None if h2 is None else (h2["hay_dia_anterior"], h2["sin_aviso"]))
    comprobar("aviso: un contador vacío no cuenta como aviso", h1 is not None and h1["avisa_dia_anterior"] == False  # noqa: E712
              and h1["sin_aviso"] == True, None if h1 is None else (h1["avisa_dia_anterior"], h1["sin_aviso"]))  # noqa: E712
    a2 = fila(fr, serial_number="A2", fecha="2024-02-01")
    comprobar("aviso: en la foto, los contadores vacíos no avisan", a2 is not None and a2["avisa"] == False  # noqa: E712
              and a2["contadores_que_avisan"] == 0 and pd.isna(a2["suma_contadores_sin_188"])
              and pd.isna(a2["smart_188_no_cero"]))
    comprobar("edad: sin horas, desde la primera aparición", a2 is not None and a2["edad_de_horas"] == False  # noqa: E712
              and abs(a2["edad_anos"] - 31 / 365.25) < 1e-9, None if a2 is None else a2["edad_anos"])
    comprobar("edad: sin horas el día ni el anterior en un fallo", h2 is not None and h2["edad_de_horas"] == False  # noqa: E712
              and abs(h2["edad_al_fallar_anos"] - 24 / 365.25) < 1e-9, None if h2 is None else h2["edad_al_fallar_anos"])

    # Los cambios y la foto anterior
    a1_4, a1_1, k1 = (fila(fr, serial_number="A1", fecha="2024-04-01"), fila(fr, serial_number="A1", fecha="2024-01-01"),
                      fila(fr, serial_number="K1", fecha="2024-03-01"))
    comprobar("cambio: contra la foto anterior", a1_4 is not None and a1_4["cambio_smart_5"] == 2
              and a1_4["meses_desde_foto_anterior"] == 1)
    comprobar("cambio: la primera foto no tiene anterior", a1_1 is not None and pd.isna(a1_1["cambio_smart_5"])
              and pd.isna(a1_1["meses_desde_foto_anterior"]))
    comprobar("cambio: foto anterior dos meses antes", k1 is not None and k1["meses_desde_foto_anterior"] == 2)

    # Caso 9: el precio con las capacidades vecinas
    d = COMPRA_10TB
    c8 = recta([("2016-01-01", 0.051), ("2016-12-31", 0.030), ("2017-01-01", 0.033), ("2017-12-31", 0.025)], d)
    c12 = recta([("2017-01-01", 0.0245), ("2017-12-31", 0.024), ("2018-01-01", 0.024), ("2018-12-31", 0.0225)], d)
    m10 = fila(dm, model=HUH10)
    comprobar("precio: la capacidad sin curva toma la media de sus dos vecinas", m10 is not None
              and abs(m10["coste_gb_compra"] - (c8 + c12) / 2) < 1e-6 and m10["origen_precio"] == "vecinas",
              None if m10 is None else (m10["coste_gb_compra"], (c8 + c12) / 2, m10["origen_precio"]))
    comprobar("precio: precio_usd es coste por GB por la capacidad", m10 is not None
              and abs(m10["precio_usd"] - m10["coste_gb_compra"] * 10.0 * 1000) < 1e-6)
    m6 = fila(dm, model=WD6)
    comprobar("precio: los modelos de 6 TB de la lista no llevan precio", m6 is not None and pd.isna(m6["precio_usd"]))
    p10 = fila(dpg, capacidad_tb=10.0, ano=2020)
    comprobar("precio por año: 10 TB en 2020, media de 12 y 14", p10 is not None
              and abs(p10["coste_gb"] - (0.0167 + 0.0158) / 2) < 1e-9 and p10["origen"] == "vecinas",
              None if p10 is None else (p10["coste_gb"], p10["origen"]))
    p4 = fila(dpg, capacidad_tb=4.0, ano=2022)
    c16 = recta([("2022-01-01", 0.0157), ("2022-12-31", 0.0145)], "2022-07-01")
    comprobar("precio por año: con una sola capacidad con curva, esa", p4 is not None
              and abs(p4["coste_gb"] - c16) < 1e-9, None if p4 is None else (p4["coste_gb"], c16))
    p23 = fila(dpg, capacidad_tb=4.0, ano=2023)
    comprobar("precio por año: desde 2023, lo inferido", p23 is not None and abs(p23["coste_gb"] - 0.0132) < 1e-12
              and p23["origen"] == "inferido")
    comprobar("dim_precio_gb: capacidades de datos por años del Calendario", len(dpg) == 3 * 6, len(dpg))
    comprobar("dim_modelo: garantía de las familias", fila(dm, model=ST4)["garantia_anos"] == 2
              and fila(dm, model=HUH10)["garantia_anos"] == 5 and pd.isna(fila(dm, model=WD6)["garantia_anos"])
              and pd.isna(fila(dm, model=SSD)["garantia_anos"]))
    comprobar("dim_modelo: arranque sin fecha de compra", fila(dm, model=SSD)["tipo_disco"] == "arranque"
              and pd.isna(fila(dm, model=SSD)["fecha_compra"]))

    # Los grupos de fotos_riesgo, la partición y el registro
    grupos = js.get("grupos_fotos_riesgo", {})
    todas = [c for cols in grupos.values() for c in cols]
    comprobar("grupos: cada columna en un solo grupo", sorted(todas) == sorted(fr.columns), set(todas) ^ set(fr.columns))
    part = js.get("particion") or {}
    comprobar("partición del Calendario", part.get("desarrollo") == {"desde": "2020-01-01", "hasta": "2024-06-30"}
              and part.get("validacion") == {"desde": "2024-07-01", "hasta": "2025-06-30"}, part)
    marcas = {v["columna"]: v for v in js.get("variables_generadas", [])}
    comprobar("marcas: falla_30d, horizonte_hasta, precio_usd y fecha_compra son información posterior",
              all(marcas.get(c, {}).get("informacion_posterior") is True
                  for c in ("falla_30d", "horizonte_hasta", "precio_usd", "fecha_compra")))
    comprobar("validaciones: ninguna falla", all(v["resultado"] == "pasa" for v in js.get("validaciones", [])),
              [v for v in js.get("validaciones", []) if v["resultado"] != "pasa"])
    reg = (TMP / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
    numeros = re.findall(r"^## (R-\d+) ", reg, re.M)
    comprobar("registro: fichas nuevas desde R-010", numeros[:2] == ["R-009", "R-010"] and len(numeros) > 2, numeros)
    comprobar("registro: nueve campos por ficha", reg.count("9. **Cómo deshacer:**") == len(numeros) - 1)
    comprobar("fallos_detalle: todos los fallos", len(fd) == len(FALLO), len(fd))

    # Una segunda ejecución no añade fichas
    p2 = ejecutar()
    reg2 = (TMP / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
    comprobar("segunda ejecución: termina con 0", p2.returncode == 0, p2.stderr[-1500:])
    comprobar("segunda ejecución: no añade fichas", re.findall(r"^## (R-\d+) ", reg2, re.M) == numeros)


def parte_1_casos_que_paran():
    """Variantes que tienen que parar el script sin dejar ninguna tabla."""
    if not SCRIPT.exists():
        return
    for variante, texto in (("columna_sin_grupo", "columna_rara"), ("edad_negativa", "edad"),
                            ("ventana_repetida", "cruce 1")):
        montar(variante)
        p = ejecutar()
        js = leer_json()
        estado = None if js is None else js["resultado"]["estado"]
        comprobar(f"{variante}: PARADO", estado == "PARADO", (estado, p.stderr[-800:]))
        comprobar(f"{variante}: sale con 1", p.returncode == 1, p.returncode)
        comprobar(f"{variante}: dice por qué", js is not None and texto in json.dumps(js, ensure_ascii=False),
                  None if js is None else js["resultado"].get("resumen"))
        nuevas = [x.name for x in (TMP / "data" / "processed").iterdir()
                  if not x.name.endswith("_corregido.parquet") and x.name != "calendario.parquet"]
        comprobar(f"{variante}: no deja ninguna tabla", not nuevas, nuevas)
        reg = (TMP / "config" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
        comprobar(f"{variante}: no escribe fichas", re.findall(r"^## (R-\d+) ", reg, re.M) == ["R-009"])
    js = leer_json()
    cruce1 = [c for c in (js or {}).get("cruces", []) if c.get("orden") == 1]
    comprobar("ventana_repetida: el cruce 1 queda sin hacer", bool(cruce1) and cruce1[-1]["hecho"] is False, cruce1)


def parte_1_codigo():
    """Ninguna comprobación escrita con su resultado puesto, sin filterwarnings y las fotos leídas por bloques."""
    if not SCRIPT.exists():
        return
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestas = re.findall(r'"(?:coincide|pasa|hecho|resultado|ok)"\s*:\s*(?:True|"pasa")\s*[,}]', codigo)
    comprobar("ninguna comprobación con su resultado escrito", not puestas, puestas)
    comprobar("sin filterwarnings", "filterwarnings" not in codigo)
    comprobar("las fotos se leen bloque a bloque", "read_row_group" in codigo
              and not re.search(r"read_(?:table|parquet)\([^)]*FOTOS", codigo))
    comprobar("fotos_riesgo se escribe con ParquetWriter", "ParquetWriter" in codigo)
    comprobar("el rango de los datos no está escrito en el código", "2020-01-01" not in codigo
              and "2025-06-01" not in codigo)


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 2: las cifras reales frente a las de referencia
# ---------------------------------------------------------------------------------------------------------------
def parte_2():
    """Si existe el JSON real, compara sus cifras de control con tests/cifras_de_referencia.json."""
    ruta = CASO / "informes" / "transformacion-datos.json"
    if not ruta.exists():
        print("salta  parte 2: no existe informes/transformacion-datos.json")
        return
    js = json.loads(ruta.read_text(encoding="utf-8"))
    ref = json.loads((CASO / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8")).get("transformacion", {})
    cifras = ref.get("cifras", {})
    comprobar("hay cifras de transformación de referencia", bool(cifras), "falta la clave transformacion")
    for clave, esperado in cifras.items():
        sale = js.get("cifras_de_control", {}).get(clave)
        comprobar(f"cifra {clave}", sale == esperado, f"sale {sale}, referencia {esperado}")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print("sys.executable:", sys.executable)
    try:
        # el responsable del caso, 17/11: la palabra vetada para el conjunto de discos no sale en ningún texto del repositorio.
        # Se escribe partida para que esta prueba tampoco la lleve.
        comprobar("el script no lleva la palabra vetada", ("flo" + "ta") not in SCRIPT.read_text(encoding="utf-8").lower())
        parte_1()
        parte_1_casos_que_paran()
        parte_1_codigo()
        parte_2()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\ntodos los casos pasan")
    sys.exit(1 if FALLOS else 0)
