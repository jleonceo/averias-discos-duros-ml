"""Prueba de scripts/12_particion.py (skill preparacion-modelo §1, encargo 20, primera parte).

Parte 1, el script entero sobre un caso pequeño. Monta en tests/tmp_particion/ una fotos_riesgo de 16 fotos en cuatro
fechas (dos de construcción y dos de validación, un grupo de filas por fecha), con los tipos de la tabla real (texto,
fecha en milisegundos, int8), y su informes/transformacion-datos.json con la huella. Ejecuta el script con -W error y
comprueba lo que se sabe a mano del caso pequeño: 8 fotos y 1 fallo en cada parte, 2 discos en las dos partes, las
columnas en el mismo orden, un grupo de filas por fecha, la huella de cada parte y el lote de producción en null con su
motivo. Después, los casos que tienen que parar, cada uno con la comprobación que lo caza en rojo:
  - una fila en las dos partes (la misma clave serial_number y fecha con los dos periodos): sin_filas_compartidas;
  - una fecha que solapa (una foto de julio marcada como construcción): fechas_sin_solape;
  - un horizonte que cruza (una foto de construcción con horizonte en julio): horizonte_cerrado;
  - un periodo que no coincide con su fecha (todo el 01/07 marcado como construcción): coincide_con_periodo;
  - una tasa fuera de tolerancia (fallan casi todas las fotos de agosto): tasa_dentro_de_tolerancia;
  - una fila que se pierde (una foto sin periodo): suman_la_entrada;
  - un grupo de filas con dos fechas: la entrada no tiene la forma que el script necesita, ERROR;
  - la transformación en PARADO y la huella de la entrada distinta de la de la transformación: PARADO.
En todos, el JSON se escribe con su estado y no queda ninguna de las dos partes en disco.
Parte 2, la búsqueda de resultados escritos a mano (error 24): ninguna comprobación del script lleva True puesto, y la
búsqueda caza uno escrito a propósito.
Parte 3, el JSON real, si existe (lo escribe la ejecución de la sesión principal): las cifras de control del encargo,
escritas como las da el encargo, y las cifras rehechas por otro camino: contadas en las dos partes ya escritas (otra
tabla, leída con pyarrow grupo a grupo) frente a lo que el script contó al leer la entrada, y frente a las cifras de
control de informes/transformacion-datos.json, que salen de la ejecución de la transformación. La misma función se
prueba antes sobre el caso pequeño, en verde y con un JSON alterado que tiene que dar rojo.

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "12_particion.py"
TMP = CASO / "tests" / "tmp_particion"
ENTRADA = "data/processed/fotos_riesgo.parquet"
SAL_ENT = "data/processed/fotos_riesgo_entrenamiento.parquet"
SAL_VAL = "data/processed/fotos_riesgo_validacion.parquet"
SAL_JSON = "informes/particion.json"
TRANSFORMACION = "informes/transformacion-datos.json"
COMPROBACIONES = ["sin_filas_compartidas", "suman_la_entrada", "tasa_dentro_de_tolerancia", "fechas_sin_solape",
                  "horizonte_cerrado", "coincide_con_periodo"]
CONSTRUCCION, VALIDACION = "construcción", "validación"
FALLOS = []

# Las cifras de control del encargo 20 (CIFRAS DE CONTROL), escritas como las da el encargo
ESPERADAS_REALES = {
    "entrada_filas": 14604861, "entrada_columnas": 144, "entrada_grupos": 66, "objetivo_total": 16266,
    "entrenamiento": {"filas": 11026052, "objetivo": 11962, "tasa_pct": 0.108489, "fecha_min": "2020-01-01",
                      "fecha_max": "2024-06-01", "fechas": 54, "horizonte_max": "2024-06-30", "discos": 352642},
    "validacion": {"filas": 3578809, "objetivo": 4304, "tasa_pct": 0.120263, "fecha_min": "2024-07-01",
                   "fecha_max": "2025-06-01", "fechas": 12, "discos": 332218},
    "diferencia_puntos": 0.0118, "discos_en_las_dos_partes": 282422,
}


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


# ---------------------------------------------------------------------------------------------------------------
# 2. El caso pequeño
# ---------------------------------------------------------------------------------------------------------------
# Tipos de la tabla real (medidos con read_schema el 18/11/2026): texto, fecha en ms, float64 e int8
ESQUEMA = pa.schema([("serial_number", pa.string()), ("fecha", pa.timestamp("ms")), ("model", pa.string()),
                     ("smart_5_raw", pa.float64()), ("periodo", pa.string()), ("horizonte_hasta", pa.timestamp("ms")),
                     ("falla_30d", pa.int8())])


def d(texto):
    """Fecha ISO a datetime."""
    return dt.datetime.fromisoformat(texto)


def fila(serie, fecha, periodo, horizonte, falla=0, smart5=0.0):
    """Una foto del caso pequeño."""
    return {"serial_number": serie, "fecha": d(fecha), "model": "M1", "smart_5_raw": smart5, "periodo": periodo,
            "horizonte_hasta": d(horizonte) if horizonte else None, "falla_30d": falla}


def filas_limpias():
    """16 fotos: 05/2024 y 06/2024 de construcción, 07/2024 y 08/2024 de validación; un fallo en cada parte.

    Discos en construcción: A, B, C, D, E; en validación: A, B, F, G, H; en las dos, A y B.
    """
    c, v = CONSTRUCCION, VALIDACION
    return [
        fila("A", "2024-05-01", c, "2024-05-31"), fila("B", "2024-05-01", c, "2024-05-31"),
        fila("C", "2024-05-01", c, "2024-05-31", smart5=None), fila("D", "2024-05-01", c, "2024-05-31"),
        fila("A", "2024-06-01", c, "2024-06-30"), fila("B", "2024-06-01", c, "2024-06-30"),
        fila("C", "2024-06-01", c, "2024-06-30"), fila("E", "2024-06-01", c, "2024-06-30", falla=1),
        fila("A", "2024-07-01", v, "2024-07-31"), fila("B", "2024-07-01", v, "2024-07-31"),
        fila("F", "2024-07-01", v, "2024-07-31"), fila("G", "2024-07-01", v, "2024-07-31"),
        fila("A", "2024-08-01", v, "2024-08-31"), fila("F", "2024-08-01", v, "2024-08-31"),
        fila("G", "2024-08-01", v, "2024-08-31"), fila("H", "2024-08-01", v, "2024-08-31", falla=1),
    ]


def montar(filas, estado_transformacion="OK", huella_buena=True, grupos=None):
    """Monta tests/tmp_particion/ con la entrada y el JSON de la transformación.

    Cada fecha va en su grupo de filas, en el orden en que aparece; `grupos` permite fijar los grupos a mano (lista de
    listas de filas) para el caso de un grupo con dos fechas.
    """
    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "data" / "processed").mkdir(parents=True)
    (TMP / "informes").mkdir()
    if grupos is None:
        orden = []
        por_fecha = {}
        for f in filas:
            if f["fecha"] not in por_fecha:
                orden.append(f["fecha"])
                por_fecha[f["fecha"]] = []
            por_fecha[f["fecha"]].append(f)
        grupos = [por_fecha[k] for k in orden]
    ruta = TMP / ENTRADA
    with pq.ParquetWriter(ruta, ESQUEMA) as w:
        for g in grupos:
            t = pa.Table.from_pylist(g, schema=ESQUEMA)
            w.write_table(t, row_group_size=len(g))
    n = sum(len(g) for g in grupos)
    construccion = sum(1 for g in grupos for f in g if f["periodo"] == CONSTRUCCION)
    validacion = sum(1 for g in grupos for f in g if f["periodo"] == VALIDACION)
    tr = {
        "fecha_datos": "2025-06-30",
        "resultado": {"estado": estado_transformacion},
        "particion": {"columna_fecha": "fecha", "desarrollo": {"desde": "2020-01-01", "hasta": "2024-06-30"},
                      "validacion": {"desde": "2024-07-01", "hasta": "2025-06-30"}, "fuente": "reglas-negocio §7"},
        "salidas": [{"tabla": "fotos_riesgo", "ruta": ENTRADA, "sha256": sha256(ruta) if huella_buena else "0" * 64,
                     "filas": n, "columnas": len(ESQUEMA)}],
        "cifras_de_control": {"fotos_riesgo.filas": n, "fotos_riesgo.construccion": construccion,
                              "fotos_riesgo.validacion": validacion,
                              "fotos_riesgo.objetivo_construccion": sum(f["falla_30d"] for g in grupos for f in g
                                                                        if f["periodo"] == CONSTRUCCION),
                              "fotos_riesgo.objetivo_validacion": sum(f["falla_30d"] for g in grupos for f in g
                                                                      if f["periodo"] == VALIDACION)},
    }
    (TMP / TRANSFORMACION).write_text(json.dumps(tr, ensure_ascii=False, indent=2), encoding="utf-8")


def ejecutar():
    """Ejecuta el script sobre la carpeta temporal con -W error; devuelve el código de salida y el JSON (o None)."""
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)], capture_output=True,
                       text=True, encoding="utf-8", env={**__import__("os").environ, "PYTHONUTF8": "1"})
    ruta = TMP / SAL_JSON
    js = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    if r.returncode not in (0, 2):
        print(r.stdout[-2000:])
        print(r.stderr[-3000:])
    return r.returncode, js


def sin_partes():
    """Cierto si no quedó en disco ninguna de las dos partes ni un fichero a medio escribir."""
    proc = TMP / "data" / "processed"
    return not (TMP / SAL_ENT).exists() and not (TMP / SAL_VAL).exists() and not list(proc.glob("*.parcial"))


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 1 · el caso limpio
# ---------------------------------------------------------------------------------------------------------------
def probar_limpio():
    """El caso que no tiene que disparar nada: cada cifra, contada a mano en filas_limpias()."""
    montar(filas_limpias())
    codigo, js = ejecutar()
    comprobar(codigo == 0, f"limpio: el script sale con 0 (salió con {codigo})")
    if js is None:
        comprobar(False, "limpio: escribe informes/particion.json")
        return
    comprobar(js["resultado"]["estado"] == "OK", "limpio: estado OK")
    for c in COMPROBACIONES:
        comprobar(js["comprobaciones"].get(c) is True, f"limpio: {c} en verde")
    comprobar("sin_entidades_compartidas" in js["comprobaciones"]
              and js["comprobaciones"]["sin_entidades_compartidas"] is None, "limpio: sin_entidades_compartidas null")
    comprobar(js.get("discos_en_las_dos_partes") == 2, "limpio: 2 discos en las dos partes (A y B)")
    comprobar(js.get("estrategia") == "fecha" and js.get("semilla") == 42 and js.get("columna_fecha") == "fecha",
              "limpio: estrategia fecha, semilla 42, columna fecha")
    comprobar(js.get("fecha_datos") == "2025-06-30", "limpio: fecha_datos 2025-06-30")
    comprobar(bool(js.get("por_que")) and "§7" in js["por_que"], "limpio: por_que cita la regla §7")
    partes = {p["parte"]: p for p in js.get("partes", [])}
    e, v, lp = partes.get("entrenamiento"), partes.get("validacion"), partes.get("lote_produccion")
    comprobar(e is not None and v is not None and lp is not None, "limpio: las tres partes en el JSON")
    if e is None or v is None or lp is None:
        return
    comprobar(e["filas"] == 8 and v["filas"] == 8, "limpio: 8 fotos en cada parte")
    comprobar(e["fotos_con_objetivo"] == 1 and v["fotos_con_objetivo"] == 1, "limpio: 1 fallo en cada parte")
    comprobar(abs(e["tasa_objetivo"] - 0.125) < 1e-12 and abs(v["tasa_objetivo"] - 0.125) < 1e-12,
              "limpio: tasa 0,125 en las dos partes")
    comprobar(abs(js["diferencia_tasa_puntos"]) < 1e-12, "limpio: diferencia de tasa 0 puntos")
    comprobar((e["fecha_min"], e["fecha_max"], v["fecha_min"], v["fecha_max"])
              == ("2024-05-01", "2024-06-01", "2024-07-01", "2024-08-01"), "limpio: fechas mínima y máxima de cada parte")
    comprobar(e["horizonte_hasta_max"] == "2024-06-30", "limpio: horizonte máximo de construcción 2024-06-30")
    comprobar(e["discos"] == 5 and v["discos"] == 5, "limpio: 5 discos en cada parte")
    comprobar(e["ruta"] == SAL_ENT and v["ruta"] == SAL_VAL, "limpio: rutas de las dos partes")
    comprobar(all(lp[k] is None for k in ("ruta", "sha256", "filas", "tasa_objetivo", "fecha_min", "fecha_max"))
              and bool(lp.get("motivo")), "limpio: lote_produccion en null y con su motivo")
    entrada = pq.ParquetFile(TMP / ENTRADA)
    for nombre, ruta, p, fechas in (("entrenamiento", SAL_ENT, e, ["2024-05-01", "2024-06-01"]),
                                    ("validación", SAL_VAL, v, ["2024-07-01", "2024-08-01"])):
        existe = (TMP / ruta).exists()
        comprobar(existe, f"limpio: {nombre} escrita")
        if not existe:
            continue
        pf = pq.ParquetFile(TMP / ruta)
        comprobar(pf.schema_arrow.names == entrada.schema_arrow.names, f"limpio: {nombre} con las columnas en el orden de la entrada")
        comprobar(pf.schema_arrow.equals(entrada.schema_arrow), f"limpio: {nombre} con los tipos de la entrada")
        grupos = [pc.unique(pf.read_row_group(i, columns=["fecha"])["fecha"]).to_pylist() for i in range(pf.num_row_groups)]
        comprobar([len(g) for g in grupos] == [1] * len(fechas)
                  and [g[0].date().isoformat() for g in grupos] == fechas, f"limpio: {nombre}, un grupo de filas por fecha")
        comprobar(sha256(TMP / ruta) == p["sha256"], f"limpio: {nombre}, la huella del JSON es la del fichero")
    comprobar(js["entradas"][0]["sha256"] == sha256(TMP / ENTRADA), "limpio: la huella de la entrada en el JSON")
    comprobar(not list((TMP / "data" / "processed").glob("*.parcial")), "limpio: no queda ningún fichero a medio escribir")
    # La misma función de la parte 3, en verde sobre el caso pequeño y en rojo con un JSON alterado
    esperadas = {"entrada_filas": 16, "entrada_columnas": 7, "entrada_grupos": 4, "objetivo_total": 2,
                 "entrenamiento": {"filas": 8, "objetivo": 1, "tasa_pct": 12.5, "fecha_min": "2024-05-01",
                                   "fecha_max": "2024-06-01", "fechas": 2, "horizonte_max": "2024-06-30", "discos": 5},
                 "validacion": {"filas": 8, "objetivo": 1, "tasa_pct": 12.5, "fecha_min": "2024-07-01",
                                "fecha_max": "2024-08-01", "fechas": 2, "discos": 5},
                 "diferencia_puntos": 0.0, "discos_en_las_dos_partes": 2}
    fallos = comprobar_json_real(TMP, esperadas)
    comprobar(fallos == [], f"parte 3 sobre el caso pequeño, en verde ({fallos})")
    alterado = json.loads((TMP / SAL_JSON).read_text(encoding="utf-8"))
    alterado["partes"][0]["filas"] += 1
    alterado["discos_en_las_dos_partes"] += 1
    (TMP / SAL_JSON).write_text(json.dumps(alterado, ensure_ascii=False), encoding="utf-8")
    fallos = comprobar_json_real(TMP, esperadas)
    comprobar(any("filas" in f for f in fallos) and any("dos partes" in f for f in fallos),
              "parte 3 sobre un JSON alterado, en rojo")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 1 · los casos que tienen que parar
# ---------------------------------------------------------------------------------------------------------------
def probar_rojo(nombre, filas, comprobacion, **montaje):
    """Un caso que tiene que parar con ERROR: la comprobación nombrada en rojo y ninguna parte en disco."""
    montar(filas, **montaje)
    codigo, js = ejecutar()
    comprobar(codigo == 2, f"{nombre}: sale con 2 (salió con {codigo})")
    if js is None:
        comprobar(False, f"{nombre}: escribe el JSON aunque pare")
        return None
    comprobar(js["resultado"]["estado"] == "ERROR", f"{nombre}: estado ERROR (es {js['resultado']['estado']})")
    if comprobacion:
        comprobar(js["comprobaciones"].get(comprobacion) is False, f"{nombre}: {comprobacion} en rojo")
    comprobar(sin_partes(), f"{nombre}: no deja ninguna parte en disco")
    return js


def probar_rojos():
    """Una fila en las dos partes, una fecha que solapa, un horizonte que cruza, un periodo que no coincide, una tasa
    fuera de tolerancia, una fila que se pierde y un grupo con dos fechas."""
    c, v = CONSTRUCCION, VALIDACION
    # Una fila en las dos partes: la foto de A del 01/06 sale dos veces, una con cada periodo
    probar_rojo("una fila en las dos partes", filas_limpias() + [fila("A", "2024-06-01", v, "2024-06-30")],
                "sin_filas_compartidas")
    # Una fecha que solapa: una foto del 01/07 marcada como construcción
    probar_rojo("una fecha que solapa", filas_limpias() + [fila("Z", "2024-07-01", c, "2024-06-30")],
                "fechas_sin_solape")
    # Un horizonte que cruza: una foto de construcción del 01/06 con el horizonte el 01/07
    f = filas_limpias()
    f[5]["horizonte_hasta"] = d("2024-07-01")
    js = probar_rojo("un horizonte que cruza", f, "horizonte_cerrado")
    if js:
        otras = [k for k in COMPROBACIONES if k != "horizonte_cerrado" and js["comprobaciones"].get(k) is not True]
        comprobar(otras == [], f"un horizonte que cruza: solo cae horizonte_cerrado ({otras})")
    # Un periodo que no coincide con su fecha: el 01/07 entero marcado como construcción, con el horizonte cerrado
    f = filas_limpias()
    for x in f:
        if x["fecha"] == d("2024-07-01"):
            x["periodo"], x["horizonte_hasta"] = c, d("2024-06-30")
    js = probar_rojo("un periodo que no coincide con su fecha", f, "coincide_con_periodo")
    if js:
        comprobar(js.get("filas_que_no_coinciden_con_periodo") == 4, "un periodo que no coincide: 4 filas contadas")
    # Una tasa fuera de tolerancia: fallan tres de las cuatro fotos del 01/08 (4 de 8 en validación, 1 de 8 en construcción)
    f = filas_limpias()
    for x in f[12:15]:
        x["falla_30d"] = 1
    js = probar_rojo("una tasa fuera de tolerancia", f, "tasa_dentro_de_tolerancia")
    if js:
        comprobar(abs(js["diferencia_tasa_puntos"] - 37.5) < 1e-9, "una tasa fuera de tolerancia: 37,5 puntos")
    # Una fila que se pierde: una foto sin periodo no va a ninguna parte
    js = probar_rojo("una fila que se pierde", filas_limpias() + [fila("Y", "2024-08-01", None, "2024-08-31")],
                     "suman_la_entrada")
    if js:
        comprobar(js.get("filas_sin_parte") == 1, "una fila que se pierde: 1 fila sin parte")
    # Un grupo con dos fechas: el script necesita un grupo de filas por fecha para comparar las claves fecha a fecha
    f = filas_limpias()
    probar_rojo("un grupo con dos fechas", f, None, grupos=[f[0:8], f[8:16]])


def probar_parados():
    """La transformación en PARADO y la huella de la entrada distinta: PARADO, sin partes en disco."""
    for nombre, montaje in (("transformación en PARADO", {"estado_transformacion": "PARADO"}),
                            ("huella de la entrada distinta", {"huella_buena": False})):
        montar(filas_limpias(), **montaje)
        codigo, js = ejecutar()
        comprobar(codigo == 2, f"{nombre}: sale con 2 (salió con {codigo})")
        comprobar(js is not None and js["resultado"]["estado"] == "PARADO", f"{nombre}: estado PARADO")
        comprobar(sin_partes(), f"{nombre}: no deja ninguna parte en disco")


# ---------------------------------------------------------------------------------------------------------------
# 5. Parte 2 · ningún resultado escrito a mano (error 24)
# ---------------------------------------------------------------------------------------------------------------
def buscar_escritos(texto):
    """Líneas que ponen una comprobación a True a mano, en vez de calcularla."""
    claves = "|".join(COMPROBACIONES + ["sin_entidades_compartidas"])
    patron = re.compile(r"[\"'](" + claves + r")[\"']\s*\]?\s*[:=]\s*True\b|\b(" + claves + r")\s*=\s*True\b")
    return [(n, linea.strip()) for n, linea in enumerate(texto.splitlines(), 1) if patron.search(linea)]


def probar_escritos():
    """El script no escribe ninguna comprobación a True; la búsqueda caza una escrita a propósito."""
    if not SCRIPT.exists():
        comprobar(False, f"existe {SCRIPT.relative_to(CASO)}")
        return
    hallado = buscar_escritos(SCRIPT.read_text(encoding="utf-8"))
    comprobar(hallado == [], f"ninguna comprobación escrita a True en el script ({hallado})")
    comprobar(len(buscar_escritos('c = {"suman_la_entrada": True}\nhorizonte_cerrado = True')) == 2,
              "la búsqueda caza dos comprobaciones escritas a True")


# ---------------------------------------------------------------------------------------------------------------
# 6. Parte 3 · el JSON real, con sus cifras por otro camino
# ---------------------------------------------------------------------------------------------------------------
def recontar(ruta):
    """Cuenta una parte ya escrita, grupo a grupo y con pyarrow: fotos, fallos, fechas, horizonte y discos."""
    pf = pq.ParquetFile(ruta)
    filas, objetivo, fechas, discos, hmax = 0, 0, set(), set(), None
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=["serial_number", "fecha", "horizonte_hasta", "falla_30d"])
        filas += t.num_rows
        objetivo += int(pc.sum(t["falla_30d"]).as_py() or 0)
        fechas.update(x.date().isoformat() for x in pc.unique(t["fecha"]).to_pylist())
        discos.update(pc.unique(t["serial_number"]).to_pylist())
        m = pc.max(t["horizonte_hasta"]).as_py()
        hmax = m if hmax is None or (m is not None and m > hmax) else hmax
    return {"filas": filas, "objetivo": objetivo, "fechas": sorted(fechas), "discos": discos,
            "horizonte_max": hmax.date().isoformat() if hmax else None}


def comprobar_json_real(raiz, esperadas):
    """Lista de diferencias entre el JSON de la partición, las cifras esperadas y el recuento de las dos partes."""
    fallos = []
    js = json.loads((raiz / SAL_JSON).read_text(encoding="utf-8"))
    tr = json.loads((raiz / TRANSFORMACION).read_text(encoding="utf-8"))
    if js["resultado"]["estado"] != "OK":
        return [f"estado {js['resultado']['estado']}"]
    ent = js["entradas"][0]
    for clave, campo in (("entrada_filas", "filas"), ("entrada_columnas", "columnas"), ("entrada_grupos", "grupos_de_filas")):
        if ent.get(campo) != esperadas[clave]:
            fallos.append(f"entrada {campo}: {ent.get(campo)} frente a {esperadas[clave]}")
    partes = {p["parte"]: p for p in js["partes"]}
    recuentos = {}
    for parte, prefijo in (("entrenamiento", "construccion"), ("validacion", "validacion")):
        p, e = partes[parte], esperadas[parte]
        r = recontar(raiz / p["ruta"])
        recuentos[parte] = r
        # Las cifras de control del encargo
        if (p["filas"], p["fotos_con_objetivo"], p["fecha_min"], p["fecha_max"], p["fotos_mensuales"], p["discos"]) != \
                (e["filas"], e["objetivo"], e["fecha_min"], e["fecha_max"], e["fechas"], e["discos"]):
            fallos.append(f"{parte}: filas, fallos, fechas o discos distintos de los del encargo")
        if round(p["tasa_objetivo_pct"], 6) != e["tasa_pct"]:
            fallos.append(f"{parte}: tasa {p['tasa_objetivo_pct']} frente a {e['tasa_pct']}")
        if "horizonte_max" in e and p["horizonte_hasta_max"] != e["horizonte_max"]:
            fallos.append(f"{parte}: horizonte máximo {p['horizonte_hasta_max']}")
        # Otro camino 1: la parte escrita, contada de nuevo
        if (r["filas"], r["objetivo"], r["fechas"][0], r["fechas"][-1], len(r["fechas"]), len(r["discos"])) != \
                (p["filas"], p["fotos_con_objetivo"], p["fecha_min"], p["fecha_max"], p["fotos_mensuales"], p["discos"]):
            fallos.append(f"{parte}: el recuento del fichero escrito no da las filas, fallos, fechas o discos del JSON")
        if r["horizonte_max"] != p["horizonte_hasta_max"]:
            fallos.append(f"{parte}: el horizonte máximo del fichero no es el del JSON")
        if sha256(raiz / p["ruta"]) != p["sha256"]:
            fallos.append(f"{parte}: la huella del fichero no es la del JSON")
        # Otro camino 2: las cifras de control de la transformación, de su propia ejecución
        cc = tr.get("cifras_de_control", {})
        if (cc.get(f"fotos_riesgo.{prefijo}"), cc.get(f"fotos_riesgo.objetivo_{prefijo}")) != (r["filas"], r["objetivo"]):
            fallos.append(f"{parte}: filas o fallos distintos de los de la transformación")
    if round(js["diferencia_tasa_puntos"], 4) != esperadas["diferencia_puntos"]:
        fallos.append(f"diferencia de tasa {js['diferencia_tasa_puntos']}")
    if js["discos_en_las_dos_partes"] != esperadas["discos_en_las_dos_partes"]:
        fallos.append(f"discos en las dos partes del JSON: {js['discos_en_las_dos_partes']}")
    comunes = len(recuentos["entrenamiento"]["discos"] & recuentos["validacion"]["discos"])
    if comunes != js["discos_en_las_dos_partes"]:
        fallos.append(f"discos en las dos partes recontados: {comunes} frente a {js['discos_en_las_dos_partes']}")
    total = recuentos["entrenamiento"]["objetivo"] + recuentos["validacion"]["objetivo"]
    if total != esperadas["objetivo_total"]:
        fallos.append(f"fallos de las dos partes: {total} frente a {esperadas['objetivo_total']}")
    return fallos


def probar_real():
    """Si la sesión principal ya ejecutó el script, sus cifras de control y su recuento por otro camino."""
    if not (CASO / SAL_JSON).exists():
        print("nota  sin informes/particion.json real: la parte 3 se ejecuta cuando lo escriba la sesión principal")
        return
    fallos = comprobar_json_real(CASO, ESPERADAS_REALES)
    comprobar(fallos == [], f"real: cifras de control y recuento de las dos partes ({fallos})")


# ---------------------------------------------------------------------------------------------------------------
# 7. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"intérprete: {sys.executable}")
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe {SCRIPT.relative_to(CASO)}")
        else:
            probar_limpio()
            probar_rojos()
            probar_parados()
        probar_escritos()
        probar_real()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos" if FALLOS else "\ntodo en verde")
    sys.exit(1 if FALLOS else 0)
