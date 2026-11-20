"""Prueba de scripts/04_modelado_datos.py.

Parte 1: monta en tests/tmp_modelado/ un caso pequeño con las cuatro tablas corregidas escritas aquí (dos fotos
mensuales, tres ventanas de fallo, el recuento diario y la lista de fallos), con su JSON de corrección, una copia del
diseño y una de las cuestiones pendientes, ejecuta el script con -W error y comprueba lo que tiene que salir. Trae
casos que tienen que salir mal: una clave de grano repetida en las fotos, una fila de ventana con date distinta de
fecha, un JSON de corrección parado y una tabla cambiada después de la corrección. Otro caso escribe en la copia del
diseño la línea de aprobación, y solo entonces el script construye el Calendario.
Parte 2: si ya existe informes/modelado-datos.json real, compara sus cifras de control con
tests/cifras_de_referencia.json (clave «cifras_modelado») y rehace cifras por otro camino: los metadatos de los
Parquet, el JSON de la corrección y pandas sobre columnas sueltas, que el script cuenta con pyarrow.

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

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "04_modelado_datos.py"
TMP = CASO / "tests" / "tmp_modelado"
FALLOS = []

APARTADOS = ["Fuente", "Resumen", "Tablas y grano", "Relaciones", "Fechas y calendario", "Registro de exclusiones",
             "Población de la pregunta 4", "Plan de cruces", "Decisiones pendientes", "Datos personales",
             "Teoría aplicada", "Límites"]

ST4, WD14, SSD = "ST4000DM000", "WDC WUH721414ALE6L4", "Seagate SSD"
C4, C14, C025 = 4000787030016, 14000519643136, 250059350016


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


def ms(fechas):
    """Fechas como timestamp[ms], como las fechas de las tablas corregidas."""
    return pa.array(pd.to_datetime(fechas), type=pa.timestamp("ms"))


# ---------------------------------------------------------------------------------------------------------------
# 2. Datos pequeños escritos en la prueba
# ---------------------------------------------------------------------------------------------------------------
def fotos(variante=None):
    """Dos fotos: 01/06/2024 (construcción) y 01/07/2024 (validación).

    A1 y F1 tienen sitio entero; A2 no tiene sitio; B1 es de arranque; F2 falla el 01/07/2024, así que su fila de ese
    día lleva failure = 1. F1 falla el 15/06 y ya no sale en julio. H1 falla sin salir en ninguna foto.
    """
    serie = ["A1", "A2", "B1", "F1", "F2", "A1", "A2", "B1", "F2"]
    fecha = ["2024-06-01"] * 5 + ["2024-07-01"] * 4
    t = {
        "fecha": ms(fecha), "date": ms(fecha), "serial_number": serie,
        "model": [ST4, WD14, SSD, ST4, WD14, ST4, WD14, SSD, WD14],
        "capacity_bytes": pa.array([C4, C14, C025, C4, C14, C4, C14, C025, C14], type=pa.int64()),
        "failure": pa.array([0, 0, 0, 0, 0, 0, 0, 0, 1], type=pa.int64()),
        "datacenter": ["sac0", None, "sac0", "sac0", "phx1", "sac0", None, "sac0", "phx1"],
        "vault_id": pa.array([1000, None, 1000, 1000, 1001, 1000, None, 1000, 1001], type=pa.int64()),
        "pod_id": pa.array([1, None, 1, 1, 2, 1, None, 1, 2], type=pa.int64()),
        "pod_slot_num": pa.array([3, None, None, 4, 5, 3, None, None, 5], type=pa.int64()),
        "smart_9_raw": pa.array([1000.0, 2000.0, 3000.0, 4000.0, 8000.0, 1720.0, 2720.0, 3720.0, 8720.0]),
    }
    tabla = pa.table(t)
    if variante == "clave_repetida":
        # A1 sale dos veces en la foto del 01/06/2024: la clave (serial_number, fecha) deja de ser única
        tabla = pa.concat_tables([tabla, tabla.slice(0, 1)])
    return tabla


def ventanas(variante=None):
    """Ventanas de F1 (15/06), H1 (20/06, sin sitio y sin el día anterior) y F2 (01/07, sin ranura el día del fallo)."""
    fecha = ["2024-06-13", "2024-06-14", "2024-06-15", "2024-06-18", "2024-06-20", "2024-06-29", "2024-06-30",
             "2024-07-01"]
    date = list(fecha)
    if variante == "date_distinta":
        date[1] = "2024-06-15"
    dia_fallo = ["2024-06-15"] * 3 + ["2024-06-20"] * 2 + ["2024-07-01"] * 3
    return pa.table({
        "fecha": ms(fecha), "date": ms(date),
        "dia_fallo": pa.array(pd.to_datetime(dia_fallo), type=pa.timestamp("ns")),
        "serial_number": ["F1", "F1", "F1", "H1", "H1", "F2", "F2", "F2"],
        "model": [ST4, ST4, ST4, ST4, ST4, WD14, WD14, WD14],
        "capacity_bytes": pa.array([C4, C4, C4, C4, C4, C14, C14, C14], type=pa.int64()),
        "failure": pa.array([0, 0, 1, 0, 1, 0, 0, 1], type=pa.int64()),
        "datacenter": ["sac0", "sac0", "sac0", None, None, "phx1", "phx1", "phx1"],
        "vault_id": pa.array([1000, 1000, 1000, None, None, 1001, 1001, 1001], type=pa.int64()),
        "pod_id": pa.array([1, 1, 1, None, None, 2, 2, 2], type=pa.int64()),
        "pod_slot_num": pa.array([4, 4, 4, None, None, 5, 5, None], type=pa.int64()),
        "smart_9_raw": pa.array([4290.0, 4314.0, 4338.0, None, None, 8668.0, 8692.0, 9000.0]),
    })


def recuento():
    """Recuento del 30/05/2024 al 02/07/2024, 34 días sin huecos, con un modelo de arranque y el centro «sin dato»."""
    filas = []
    for dia in pd.date_range("2024-05-30", "2024-07-02", freq="D"):
        filas += [(dia, ST4, C4, "sac0", 2, 0), (dia, WD14, C14, "sin dato", 1, 0), (dia, WD14, C14, "phx1", 1, 0),
                  (dia, SSD, C025, "sac0", 1, 0)]
    df = pd.DataFrame(filas, columns=["fecha", "model", "capacity_bytes", "datacenter", "discos", "fallos"])
    df.loc[(df["fecha"] == "2024-06-15") & (df["model"] == ST4), "fallos"] = 1
    df.loc[(df["fecha"] == "2024-07-01") & (df["model"] == WD14) & (df["datacenter"] == "phx1"), "fallos"] = 1
    df.loc[len(df)] = [pd.Timestamp("2024-06-20"), ST4, C4, "sin dato", 1, 1]
    df["fecha"] = df["fecha"].astype("datetime64[ms]")
    return df


def fallos():
    """Lista de los tres fallos, con el día del fallo en nanosegundos como en la tabla corregida."""
    return pd.DataFrame({"serial_number": ["F1", "H1", "F2"],
                         "dia_fallo": pd.to_datetime(["2024-06-15", "2024-06-20", "2024-07-01"]).astype("datetime64[ns]")})


def diseno(aprobado):
    """Copia mínima del diseño con el estado que se prueba escrito aquí, no heredado del fichero real."""
    linea = "Aprobado: sí · Juan · 2026-11-18" if aprobado else "Pendiente de aprobar."
    return ("# Modelo de datos\n\n## 8. Plan de cruces\n\nAprobado: sí · Otro · 2026-01-01 (fuera de su apartado)\n\n"
            f"## 9. Decisiones de modelado\n\n- una decisión\n\n{linea}\n\n## 10. Observaciones y pendientes\n\n- nada\n")


def cuestiones():
    """Copia mínima de las cuestiones pendientes: una cerrada y una abierta."""
    return ("| Número | Fecha | Petición | Motivo | Lo que haría falta para resolverla | Estado |\n"
            "|---|---|---|---|---|---|\n"
            "| CP-001 | 16/11/2026 | Una cerrada | motivo | nada | cerrada el 17/11/2026 |\n"
            "| CP-011 | 17/11/2026 | Una pregunta abierta | motivo | que la persona responsable elija | abierta |\n")


def montar_caso(variante=None):
    """Crea el caso pequeño en la carpeta temporal; la variante pone un caso que tiene que salir mal o la aprobación."""
    if TMP.exists():
        shutil.rmtree(TMP)
    proc = TMP / "data" / "processed"
    proc.mkdir(parents=True)
    (TMP / "informes").mkdir()
    (TMP / "contexto-proyecto" / "modelo").mkdir(parents=True)
    (TMP / "contexto-proyecto" / "negocio").mkdir(parents=True)
    rutas = {"fotos_mensuales": proc / "fotos_mensuales_corregido.parquet",
             "ventanas_fallo": proc / "ventanas_fallo_corregido.parquet",
             "recuento_diario": proc / "recuento_diario_corregido.parquet",
             "fallos": proc / "fallos_corregido.parquet"}
    pq.write_table(fotos(variante), rutas["fotos_mensuales"])
    pq.write_table(ventanas(variante), rutas["ventanas_fallo"])
    recuento().to_parquet(rutas["recuento_diario"], index=False)
    fallos().to_parquet(rutas["fallos"], index=False)
    salidas = [{"tabla": t, "ruta": f"data/processed/{r.name}", "sha256": sha(r)} for t, r in rutas.items()]
    if variante == "huella_cambiada":
        # La tabla de fallos cambia después de la corrección: su huella ya no es la que dejó la corrección
        fallos().head(2).to_parquet(rutas["fallos"], index=False)
    estado = "PARADO" if variante == "correccion_parada" else "AVISO"
    corr = {"skill": "correccion-datos", "fecha_datos": "2025-06-30", "resultado": {"estado": estado},
            "salidas": salidas, "controles": {"ventanas.filas_quitadas": 228,
                                              "ventanas.fechas_quitadas": ["2022-12-10"]}}
    (TMP / "informes" / "correccion-datos.json").write_text(json.dumps(corr, ensure_ascii=False), encoding="utf-8")
    (TMP / "informes" / "calidad-datos.json").write_text(
        json.dumps({"skill": "calidad-datos", "fecha_datos": "2025-06-30", "resultado": {"estado": "AVISO"}}),
        encoding="utf-8")
    (TMP / "contexto-proyecto" / "modelo" / "modelo-datos.md").write_text(diseno(variante == "aprobado"),
                                                                         encoding="utf-8")
    (TMP / "contexto-proyecto" / "negocio" / "cuestiones-pendientes.md").write_text(cuestiones(), encoding="utf-8")
    return rutas


def ejecutar():
    """Ejecuta el script sobre el caso pequeño con -W error y devuelve el proceso terminado."""
    return subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)],
                          capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})


def leer_json():
    """El JSON que dejó el script en el caso pequeño, o un diccionario vacío si no lo dejó."""
    ruta = TMP / "informes" / "modelado-datos.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 1: el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def parte_1():
    """Ejecuta el script sobre el caso pequeño sin aprobar y comprueba sus salidas."""
    comprobar("existe el script", SCRIPT.exists(), str(SCRIPT))
    if not SCRIPT.exists():
        return
    rutas = montar_caso()
    antes = {k: sha(v) for k, v in rutas.items()}
    p = ejecutar()
    comprobar("el script termina sin error ni aviso", p.returncode == 0, (p.stderr or p.stdout)[-1500:])
    if p.returncode != 0:
        return
    comprobar("las tablas de entrada siguen intactas", {k: sha(v) for k, v in rutas.items()} == antes)
    texto = (TMP / "informes" / "modelado-datos.json").read_text(encoding="utf-8")
    comprobar("JSON sin NaN ni Infinity", "NaN" not in texto and "Infinity" not in texto)
    js = json.loads(texto)
    c = js["cifras_de_control"]

    # Bloque común y aprobación: sin la línea en su apartado, PARADO y aprobado false; la línea de otro apartado no vale
    comprobar("estado PARADO sin aprobar", js["resultado"]["estado"] == "PARADO", js["resultado"]["estado"])
    comprobar("aprobado false", js["aprobado"]["aprobado"] is False, js["aprobado"])
    comprobar("fecha_datos", js.get("fecha_datos") == "2025-06-30")
    comprobar("skill y script", js["skill"] == "modelado-datos" and js["script"] == "scripts/04_modelado_datos.py")
    comprobar("cuatro entradas con huella", len(js["entradas"]) == 4 and all(len(e["sha256"]) == 64 for e in js["entradas"]))
    comprobar("sin Calendario sin aprobar", not (TMP / "data" / "processed" / "calendario.parquet").exists())
    comprobar("calendario sin fichero", js["calendario"]["fichero"] is None)
    comprobar("pendiente abierta leída del fichero", [x["id"] for x in js["pendientes"]] == ["CP-011"], js["pendientes"])

    # Grano: las cuatro claves únicas
    tablas = {t["tabla"]: t for t in js["tablas"]}
    for t in ("hechos_fotos", "hechos_ventanas", "hechos_recuento", "hechos_fallos"):
        comprobar(f"{t}: clave única", tablas[t]["clave_unica"] is True and tablas[t]["filas_repetidas"] == 0,
                  tablas[t])
    comprobar("filas de las cuatro tablas", (c["fotos.filas"], c["ventanas.filas"], c["recuento.filas"],
                                              c["fallos.filas"]) == (9, 8, 137, 3),
              (c["fotos.filas"], c["ventanas.filas"], c["recuento.filas"], c["fallos.filas"]))
    comprobar("date igual a fecha en fotos y ventanas",
              c["fotos.date_distinta_de_fecha"] == 0 and c["ventanas.date_distinta_de_fecha"] == 0)
    comprobar("dimensiones sin fichero", all(t["fichero"] is None for t in js["tablas"] if t["tipo"] != "hechos"))

    # Fechas
    comprobar("recuento: 34 días del 30/05 al 02/07/2024 sin huecos",
              (c["recuento.primer_dia"], c["recuento.ultimo_dia"], c["recuento.dias"], c["recuento.dias_que_faltan"])
              == ("2024-05-30", "2024-07-02", 34, 0))
    comprobar("fotos: dos meses, todas el día 1", c["fotos.meses"] == 2 and c["fotos.fechas_no_dia_1"] == 0
              and c["fotos.meses_que_faltan"] == 0)
    comprobar("ventanas: 8 días con 11 que faltan", c["ventanas.dias"] == 8 and c["ventanas.dias_que_faltan_n"] == 11,
              (c["ventanas.dias"], c["ventanas.dias_que_faltan_n"]))
    rel = {(r["desde"], r["clave_desde"][0], r["hacia"]): r for r in js["relaciones"]}
    comprobar("dia_fallo frente a la fecha del Calendario: tipo distinto, sin corregir",
              rel[("hechos_fallos", "dia_fallo", "Calendario")]["mismo_tipo"] is False,
              rel[("hechos_fallos", "dia_fallo", "Calendario")])
    comprobar("fecha de las fotos frente al Calendario: mismo tipo",
              rel[("hechos_fotos", "fecha", "Calendario")]["mismo_tipo"] is True)
    comprobar("ninguna relación sin procedencia", all(r["procedencia"] for r in js["relaciones"]))

    # Modelos
    comprobar("modelos: 3 en fotos y recuento, los mismos; 2 en ventanas, todos en el recuento",
              (c["modelos.fotos"], c["modelos.recuento"], c["modelos.fotos_igual_recuento"], c["modelos.ventanas"],
               c["modelos.ventanas_fuera_del_recuento"]) == (3, 3, True, 2, 0))
    comprobar("modelos: una capacidad cada uno; 1 de arranque y 2 de datos",
              (c["modelos.con_mas_de_una_capacidad"], c["modelos.arranque"], c["modelos.datos"],
               c["modelos.entre_arranque_y_datos"]) == (0, 1, 2, 0))

    # Fallos
    comprobar("fallos: todos con su ventana y su fila del día", c["fallos.sin_ventana"] == 0
              and c["fallos.sin_fila_del_dia"] == 0, (c["fallos.sin_ventana"], c["fallos.sin_fila_del_dia"]))
    comprobar("fallos: uno de un disco sin foto", c["fallos.discos_sin_foto"] == 1, c["fallos.discos_sin_foto"])
    comprobar("fallos: ningún disco con dos fallos", c["fallos.discos_con_dos_fallos"] == 0)

    # Fotos de discos de datos y pregunta 4
    comprobar("fotos de datos: 7, 4 de construcción y 3 de validación, 1 del día del fallo",
              (c["fotos.filas_datos"], c["fotos.filas_datos_construccion"], c["fotos.filas_datos_validacion"],
               c["fotos.filas_datos_dia_del_fallo"]) == (7, 4, 3, 1),
              (c["fotos.filas_datos"], c["fotos.filas_datos_construccion"], c["fotos.filas_datos_validacion"],
               c["fotos.filas_datos_dia_del_fallo"]))
    p4 = js["pregunta_4"]
    rec = {r["foto"]: r for r in p4["horizonte_recortado"]}
    comprobar("P4: la foto del 01/06/2024 se recorta al 30/06/2024", "2024-06-01" in rec
              and rec["2024-06-01"]["corte"] == "2024-06-30", p4["horizonte_recortado"])
    r6 = rec.get("2024-06-01", {})
    comprobar("P4: el recorte pierde 1 de 2 fallos de discos de la foto",
              r6.get("fallos_disco_en_foto") == 2 and r6.get("fallos_perdidos_disco_en_foto") == 1, r6)
    comprobar("P4: tablón de 6 filas, 4 + 2", (p4["filas_tablon"], p4["filas_tablon_construccion"],
                                               p4["filas_tablon_validacion"]) == (6, 4, 2), p4)

    # Registro de exclusiones: recuentos sacados del código
    ex = {e["clase"]: e["recuentos"] for e in js["exclusiones"]}
    comprobar("exclusión: arranque, 2 fotos y 34 días de disco", ex["discos_de_arranque"]["filas_fotos"] == 2
              and ex["discos_de_arranque"]["dias_de_disco"] == 34, ex["discos_de_arranque"])
    comprobar("exclusión: sitio que no consta, 35 días y 1 fallo desde julio de 2023",
              ex["sitio_no_consta_desde"]["dias_de_disco"] == 35 and ex["sitio_no_consta_desde"]["fallos_recuento"] == 1
              and ex["sitio_no_consta_antes"]["dias_de_disco"] == 0, (ex["sitio_no_consta_antes"], ex["sitio_no_consta_desde"]))
    comprobar("exclusión: 1 fallo sin tomo en su ventana", ex["fallos_sin_ranura"]["fallos_sin_tomo"] == 1
              and ex["fallos_sin_ranura"]["fallos_sin_centro"] == 1, ex["fallos_sin_ranura"])
    comprobar("exclusión: 1 fallo sin el día anterior", ex["fallos_sin_dia_anterior"]["fallos"] == 1,
              ex["fallos_sin_dia_anterior"])
    comprobar("exclusión: en 2024, los 2 modelos de datos bajo el mínimo",
              ex["modelos_bajo_minimo"]["por_ano"].get("2024", {}).get("modelos_bajo_minimo") == 2,
              ex["modelos_bajo_minimo"])
    comprobar("exclusión: 2 años de edad de todos los discos con menos de 20 fallos",
              ex["anos_de_edad_con_menos_de_20_fallos"]["todos_anos"] == 2
              and ex["anos_de_edad_con_menos_de_20_fallos"]["celdas_modelo_edad"] == 2,
              ex["anos_de_edad_con_menos_de_20_fallos"])
    comprobar("exclusión: 1 foto del día del fallo", ex["p4_fotos_del_dia_del_fallo"]["filas"] == 1)
    comprobar("exclusión: las 228 filas, leídas de la corrección", ex["filas_del_10_12_2022"]["filas"] == 228)
    comprobar("cada exclusión dice de qué cálculo sale y si se recupera",
              all(e["sale_de"] and e["recuperable"] for e in js["exclusiones"]))

    # Plan de cruces: ningún cruce fila a fila entre hechos de grano distinto sin agregar o sin fecha
    plan = js["plan_cruces"]
    comprobar("plan de cruces con orden y magnitudes", plan and all(x["orden"] and x["magnitudes_control"] for x in plan))
    granos = {t["tabla"]: tuple(t["clave_grano"]) for t in js["tablas"]}
    hechos = {t["tabla"] for t in js["tablas"] if t["tipo"] == "hechos"}
    malos = [x["orden"] for x in plan if x["partida"] in hechos and x["se_une"] in hechos
             and granos[x["partida"]] != granos[x["se_une"]] and not x["agregar_antes"]]
    comprobar("ningún cruce entre hechos de grano distinto sin agregar o filtrar antes", not malos, malos)
    comprobar("forma de entrega", js["forma_entrega"] == "tablas_separadas")

    # Informe: los apartados en orden
    md = (TMP / "informes" / "modelado-datos.md").read_text(encoding="utf-8")
    pos = [md.find(f"## {a}") for a in APARTADOS]
    comprobar("informe con los apartados en orden", all(x >= 0 for x in pos) and pos == sorted(pos), pos)


def parte_1_casos_que_fallan():
    """Cada variante tiene que salir mal de la forma prevista, sin construir el Calendario."""
    if not SCRIPT.exists():
        return
    # La clave de grano repetida: el script la cuenta, no la arregla, y el grano queda como contradicción
    montar_caso("clave_repetida")
    p = ejecutar()
    js = leer_json()
    t = {x["tabla"]: x for x in js.get("tablas", [])}.get("hechos_fotos", {})
    comprobar("clave repetida: el script la cuenta", p.returncode == 0 and t.get("clave_unica") is False
              and t.get("filas_repetidas") == 1, (p.returncode, t, p.stderr[-800:]))
    comprobar("clave repetida: queda como pendiente", any(x["id"].startswith("GRANO") for x in js.get("pendientes", [])),
              js.get("pendientes"))

    montar_caso("date_distinta")
    ejecutar()
    js = leer_json()
    comprobar("date distinta: se cuenta en ventanas",
              js.get("cifras_de_control", {}).get("ventanas.date_distinta_de_fecha") == 1)

    for variante in ("correccion_parada", "huella_cambiada"):
        montar_caso(variante)
        p = ejecutar()
        js = leer_json()
        comprobar(f"{variante}: el script para", p.returncode != 0, p.returncode)
        comprobar(f"{variante}: estado PARADO", js.get("resultado", {}).get("estado") == "PARADO",
                  js.get("resultado"))
        comprobar(f"{variante}: sin Calendario", not (TMP / "data" / "processed" / "calendario.parquet").exists())


def parte_1_aprobado():
    """Con la línea de aprobación en su apartado, el script la lee y construye el Calendario."""
    if not SCRIPT.exists():
        return
    montar_caso("aprobado")
    p = ejecutar()
    js = leer_json()
    comprobar("aprobado: termina", p.returncode == 0, p.stderr[-800:])
    ap = js.get("aprobado", {})
    comprobar("aprobado: lee quién y cuándo", ap == {"aprobado": True, "fecha": "2026-11-18", "quien": "Juan"}, ap)
    comprobar("aprobado: ya no está PARADO", js.get("resultado", {}).get("estado") in ("OK", "AVISO"),
              js.get("resultado"))
    ruta = TMP / "data" / "processed" / "calendario.parquet"
    comprobar("aprobado: deja el Calendario", ruta.exists())
    if not ruta.exists():
        return
    cal = pd.read_parquet(ruta)
    comprobar("Calendario: 34 días seguidos, uno por fila", len(cal) == 34 and cal["fecha"].is_unique
              and cal["fecha"].diff().dropna().dt.days.eq(1).all())
    comprobar("Calendario: del primer al último día del recuento",
              (str(cal["fecha"].min().date()), str(cal["fecha"].max().date())) == ("2024-05-30", "2024-07-02"))
    comprobar("Calendario: columnas", {"fecha", "ano", "trimestre", "mes", "periodo", "trimestre_completo",
                                       "ano_completo"} <= set(cal.columns), list(cal.columns))
    comprobar("Calendario: 32 días de construcción y 2 de validación",
              cal["periodo"].value_counts().to_dict() == {"construcción": 32, "validación": 2},
              cal["periodo"].value_counts().to_dict())
    comprobar("Calendario: los trimestres y el año, parciales", not cal["trimestre_completo"].any()
              and not cal["ano_completo"].any())
    comprobar("Calendario: la fecha en milisegundos, como las fechas de los hechos",
              str(pq.read_schema(ruta).field("fecha").type) == "timestamp[ms]")


def parte_1_codigo():
    """Ninguna comprobación escrita con su resultado puesto (programacion-del-caso, error 24) ni fechas de datos fijas."""
    if not SCRIPT.exists():
        return
    codigo = SCRIPT.read_text(encoding="utf-8")
    puestas = re.findall(r'"(?:clave_unica|mismo_tipo|coincide|aprobado|pasa)"\s*:\s*True', codigo)
    comprobar("ninguna comprobación con True escrito", not puestas, puestas)
    comprobar("sin filterwarnings", "filterwarnings" not in codigo)
    comprobar("el rango del Calendario no está escrito en el código", "2020-01-01" not in codigo)


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 2: las salidas reales, por otro camino
# ---------------------------------------------------------------------------------------------------------------
def estado_coherente(texto_diseno, js, fechas_calendario):
    """Comprueba que el JSON y el Calendario dicen lo mismo que el diseño sobre la aprobación.

    Con la línea «Aprobado: sí · <nombre> · AAAA-MM-DD» en el diseño, el JSON trae aprobado true y existe el
    Calendario, un día por fila, seguidos y sin repetir, con tantos días como dice el JSON. Sin la línea, el JSON
    trae PARADO y aprobado false, y no hay Calendario. Devuelve una lista de (nombre, ok, detalle).
    """
    aprobado_diseno = re.search(r"^Aprobado: sí · .+ · \d{4}-\d{2}-\d{2}\s*$", texto_diseno, re.MULTILINE) is not None
    aprobado_json = js["aprobado"]["aprobado"] is True
    salida = [("el JSON recoge la aprobación del diseño", aprobado_json == aprobado_diseno,
               f"diseño {aprobado_diseno}, JSON {aprobado_json}")]
    if not aprobado_diseno:
        salida.append(("sin aprobar: PARADO", js["resultado"]["estado"] == "PARADO", js["resultado"]["estado"]))
        salida.append(("sin aprobar: sin Calendario", fechas_calendario is None, "existe el Calendario"))
        return salida
    if fechas_calendario is None:
        salida.append(("aprobado: existe el Calendario", False, "no existe"))
        return salida
    f = pd.Series(fechas_calendario).sort_values().reset_index(drop=True)
    seguidos = bool((f.diff().dropna() == pd.Timedelta(days=1)).all())
    salida.append(("aprobado: Calendario sin días repetidos ni huecos", f.is_unique and seguidos, ""))
    salida.append(("aprobado: Calendario con los días del JSON", len(f) == js["calendario"].get("dias"),
                   f"{len(f)} filas, JSON {js['calendario'].get('dias')}"))
    return salida


def parte_2():
    """Compara las cifras de control reales con las de referencia y rehace varias por otro camino."""
    # La comprobación del estado, con dos casos que tienen que fallar: aprobado sin Calendario y sin aprobar con él
    js_ok = {"aprobado": {"aprobado": True}, "resultado": {"estado": "OK"}, "calendario": {"dias": 3}}
    js_no = {"aprobado": {"aprobado": False}, "resultado": {"estado": "PARADO"}, "calendario": {"dias": 3}}
    tres = pd.Series(pd.date_range("2024-01-01", periods=3))
    aprobado_md = "## 9. Decisiones de modelado\n\nAprobado: sí · Juan · 2026-11-17\n"
    comprobar("estado: aprobado y con Calendario, coherente", all(x[1] for x in estado_coherente(aprobado_md, js_ok, tres)))
    comprobar("estado: aprobado sin Calendario se detecta", not all(x[1] for x in estado_coherente(aprobado_md, js_ok, None)))
    comprobar("estado: sin aprobar con Calendario se detecta",
              not all(x[1] for x in estado_coherente("Pendiente de aprobar.", js_no, tres)))
    comprobar("estado: Calendario con un hueco se detecta",
              not all(x[1] for x in estado_coherente(aprobado_md, js_ok, tres.drop(1).reset_index(drop=True))))
    ruta = CASO / "informes" / "modelado-datos.json"
    if not ruta.exists():
        print("salta  parte 2: no existe informes/modelado-datos.json")
        return
    js = json.loads(ruta.read_text(encoding="utf-8"))
    ref = json.loads((CASO / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8")).get("cifras_modelado", {})
    comprobar("hay cifras de modelado de referencia", bool(ref), "falta la clave cifras_modelado")
    for clave, esperado in ref.items():
        comprobar(f"cifra {clave}", js["cifras_de_control"].get(clave) == esperado,
                  f"sale {js['cifras_de_control'].get(clave)}, referencia {esperado}")
    # El estado real tiene que decir lo mismo que el diseño: aprobado y con Calendario, o sin aprobar y sin él
    ruta_cal = CASO / "data" / "processed" / "calendario.parquet"
    fechas = pd.read_parquet(ruta_cal, columns=["fecha"])["fecha"] if ruta_cal.exists() else None
    texto = (CASO / "contexto-proyecto" / "modelo" / "modelo-datos.md").read_text(encoding="utf-8")
    for nombre, ok, detalle in estado_coherente(texto, js, fechas):
        comprobar(f"real: {nombre}", ok, detalle)

    proc = CASO / "data" / "processed"
    corr = json.loads((CASO / "informes" / "correccion-datos.json").read_text(encoding="utf-8"))
    # Otra fuente: las filas y huellas que dejó la corrección frente a las del script
    por_tabla = {s["ruta"]: s for s in corr["salidas"]}
    for e in js["entradas"]:
        s = por_tabla.get(e["ruta"], {})
        comprobar(f"{e['ruta']}: filas y huella como en la corrección", s.get("filas") == e["filas"]
                  and s.get("sha256") == e["sha256"], (s.get("filas"), e["filas"]))
    # Otro cálculo: las fotos de discos de datos, contando filas por modelo y sumando los modelos cuya capacidad en el
    # recuento (otra tabla) pasa del límite de los de arranque
    cap = pd.read_parquet(proc / "recuento_diario_corregido.parquet", columns=["model", "capacity_bytes"])
    cap = cap.drop_duplicates().set_index("model")["capacity_bytes"]
    por_modelo = pq.read_table(proc / "fotos_mensuales_corregido.parquet", columns=["model"]).column(0).value_counts()
    filas_modelo = {x["values"]: x["counts"] for x in por_modelo.to_pylist()}
    limite = js["parametros"]["limite_arranque_bytes"]
    datos = sum(n for m, n in filas_modelo.items() if cap[m] > limite)
    comprobar("fotos de datos por otro camino", datos == js["cifras_de_control"]["fotos.filas_datos"],
              (datos, js["cifras_de_control"]["fotos.filas_datos"]))
    # Otro cálculo: los discos con dos fallos, con pandas
    fl = pd.read_parquet(proc / "fallos_corregido.parquet")
    dos = int((fl["serial_number"].value_counts() == 2).sum())
    comprobar("discos con dos fallos por otro camino", dos == js["cifras_de_control"]["fallos.discos_con_dos_fallos"],
              dos)
    # Otro cálculo: los días del recuento con pd.date_range sobre las fechas distintas
    f = pd.read_parquet(proc / "recuento_diario_corregido.parquet", columns=["fecha"])["fecha"].drop_duplicates()
    faltan = len(pd.date_range(f.min(), f.max(), freq="D").difference(pd.DatetimeIndex(f)))
    comprobar("días del recuento sin hueco por otro camino", faltan == js["cifras_de_control"]["recuento.dias_que_faltan"])
    # Otra fuente: las 228 filas, frente al registro de transformaciones
    reg = (CASO / "contexto-proyecto" / "modelo" / "registro-transformaciones.md").read_text(encoding="utf-8")
    quitadas = {e["clase"]: e for e in js["exclusiones"]}["filas_del_10_12_2022"]["recuentos"]["filas"]
    comprobar("las filas del 10/12/2022, como en el registro", f"de 536.825 a 536.597 filas" in reg
              and 536825 - 536597 == quitadas, quitadas)


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print("sys.executable:", sys.executable)
    try:
        # Juan, 17/11: la palabra vetada para el conjunto de discos no sale en ningún texto del repositorio (R68-93).
        # Se escribe partida para que esta prueba tampoco la lleve.
        comprobar("el script no lleva la palabra vetada", ("flo" + "ta") not in SCRIPT.read_text(encoding="utf-8").lower())
        parte_1()
        parte_1_casos_que_fallan()
        parte_1_aprobado()
        parte_1_codigo()
        parte_2()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\ntodos los casos pasan")
    sys.exit(1 if FALLOS else 0)
