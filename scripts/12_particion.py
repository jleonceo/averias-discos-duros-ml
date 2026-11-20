"""Partición por fecha de fotos_riesgo del caso 68 (skill preparacion-modelo §1; encargo 20, primera parte).

La transformación ya escribió en cada foto su periodo (construcción o validación), con el Calendario. Este script no
vuelve a partir: separa las fotos por la columna periodo, comprueba fila a fila que coincide con las fechas de las
reglas de negocio §7 y guarda las dos partes:

  - data/processed/fotos_riesgo_entrenamiento.parquet, la construcción, del 01/01/2020 al 30/06/2024;
  - data/processed/fotos_riesgo_validacion.parquet, la validación, del 01/07/2024 al 30/06/2025.

Las dos con las mismas columnas que la entrada, en el mismo orden y con los mismos tipos, y un grupo de filas por fecha.
No hay lote de producción: la prueba final es la reserva, del 01/07/2025 al 30/06/2026, fuera del caso (reglas §5 y §7).

Lee fotos_riesgo grupo a grupo (cada grupo es una foto mensual), sin cargar la tabla entera, y escribe cada parte en un
fichero «.parcial». Solo si pasan las seis comprobaciones y las validaciones de la salida, los «.parcial» pasan a ser
las partes; si no, se borran y el JSON queda en ERROR con la comprobación que falló. Nada de esto usa azar: la semilla
se escribe en el JSON porque la skill lo pide, no porque se use.

Depende de scripts/05_transformacion_datos.py: lee informes/transformacion-datos.json, para si su estado es PARADO o
ERROR, si la huella de fotos_riesgo no es la que dejó la transformación o si sus fechas de partición no son las de las
reglas. No importa ningún script.

Deja informes/particion.json, con el bloque común y lo propio de resultado.md. No escribe informe para la persona: el
de la fase es informes/preparacion.md, de la segunda y la tercera parte del encargo. La ficha de la partición en el
registro de transformaciones la escribe Claude con las cifras de la ejecución real (encargo 20).

Uso: python -W error scripts/12_particion.py [--raiz CARPETA_DEL_CASO]
Sale con 0 si termina, con 2 si para (PARADO o ERROR) y con 1 si falla por otra causa; en los tres casos escribe el JSON.
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import sys
import time
import traceback
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "assets"))
from graficos import numero  # noqa: E402  (pieza común: números a la española, redondeo como Excel)

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SKILL = "preparacion-modelo"
SKILL_MD = CASO / ".claude" / "skills" / "preparacion-modelo" / "SKILL.md"
SCRIPT = "scripts/12_particion.py"
ENCARGO = "prompts/20_encargo_particion_y_preparacion.md, primera parte"
FECHA_DATOS = "2025-06-30"                                   # reglas §5, fecha de referencia

ENTRADA = "data/processed/fotos_riesgo.parquet"
TRANSFORMACION = "informes/transformacion-datos.json"
SALIDA_JSON = "informes/particion.json"
COLUMNA_FECHA = "fecha"
COLUMNA_PERIODO = "periodo"
COLUMNA_HORIZONTE = "horizonte_hasta"
COLUMNA_OBJETIVO = "falla_30d"
COLUMNA_DISCO = "serial_number"

# Las dos partes, con las fechas de las reglas §7 (Juan, 17/11/2026: «Sí, apruebo»). Cada una: el valor de la columna
# periodo, el primer y el último día de la regla, y el fichero de salida.
PARTES = [
    {"parte": "entrenamiento", "periodo": "construcción", "desde": dt.date(2020, 1, 1), "hasta": dt.date(2024, 6, 30),
     "ruta": "data/processed/fotos_riesgo_entrenamiento.parquet"},
    {"parte": "validacion", "periodo": "validación", "desde": dt.date(2024, 7, 1), "hasta": dt.date(2025, 6, 30),
     "ruta": "data/processed/fotos_riesgo_validacion.parquet"},
]
# Nombre de cada parte en partición de transformacion-datos.json, para comparar sus fechas con las de las reglas
CLAVE_EN_TRANSFORMACION = {"entrenamiento": "desarrollo", "validacion": "validacion"}

# Parámetros de la skill (preparacion-modelo/parametros.md)
SEMILLA = 42                                                 # no se usa: la partición por fecha no sortea nada
TOLERANCIA_PUNTOS = 2.0                                      # diferencia máxima de la tasa del objetivo entre partes

POR_QUE = ("Por fecha, como manda reglas-negocio §7 (Juan, 17/11/2026): el modelo se usará hacia adelante, cada mes con "
           "las fotos nuevas, así que la validación es el periodo más reciente, del 01/07/2024 al 30/06/2025, y la "
           "construcción va del 01/01/2020 al 30/06/2024. Un disco sigue en servicio de una parte a la otra, como "
           "seguirá en producción: no se parte por disco.")
MOTIVO_LOTE = ("No hay lote de producción en el caso: la prueba final es la reserva, del 01/07/2025 al 30/06/2026, "
               "que está fuera de los datos de trabajo y no se mira hasta entonces (reglas-negocio §5 y §7).")
TEORIA = [
    "20.2, entrenamiento, validación y prueba: la validación se aparta y se mira una sola vez, al medir el modelo; la "
    "prueba final es la reserva, fuera del caso.",
    "20.8, las fugas: datos con fecha no se parten al azar. Un mismo disco a los dos lados es lo que pasará en "
    "producción, porque el modelo puntúa cada mes los discos que ya vio; se cuenta y se dice, y el horizonte de "
    "construcción no pasa del 30/06/2024, para que ninguna foto de construcción sepa nada de la validación.",
]


class Parada(Exception):
    """Condición que impide seguir; `estado` dice si la skill paró a propósito (PARADO) o si falló algo (ERROR)."""

    def __init__(self, mensaje, estado="ERROR"):
        super().__init__(mensaje)
        self.estado = estado


# =================================================================================================================
# 3. Utilidades
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leído por trozos."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def version_skill():
    """La fecha y el código de la última línea de versión del SKILL.md (bloque común de resultado.md)."""
    if not SKILL_MD.exists():
        return None
    lineas = [x for x in SKILL_MD.read_text(encoding="utf-8").splitlines() if x.startswith("Versión ")]
    if not lineas:
        return None
    m = re.match(r"Versión (\S+) \(([^),]+)", lineas[-1])
    return f"{m.group(1)} ({m.group(2)})" if m else lineas[-1][:40]


def dia(valor):
    """Una fecha de pyarrow (datetime) en ISO, AAAA-MM-DD; None si falta."""
    return valor.date().isoformat() if valor is not None else None


def parte_por_regla(fecha):
    """La parte que dan las reglas §7 a una fecha, o None si la fecha no cae en ninguna."""
    for p in PARTES:
        if p["desde"] <= fecha <= p["hasta"]:
            return p
    return None


# =================================================================================================================
# 4. Antes de partir: el estado de la transformación y la huella de la entrada
# =================================================================================================================
def leer_transformacion(raiz, huella_entrada):
    """Lee el JSON de la transformación y para si no se puede partir con él (resultado.md, «Al empezar»).

    PARADO si su estado es PARADO o ERROR, si la huella de fotos_riesgo no es la que dejó o si sus fechas de partición
    no son las de las reglas §7. Devuelve su estado.
    """
    ruta = raiz / TRANSFORMACION
    if not ruta.exists():
        raise Parada(f"falta {TRANSFORMACION}: sin transformación no se parte", "PARADO")
    tr = json.loads(ruta.read_text(encoding="utf-8"))
    estado = tr.get("resultado", {}).get("estado")
    if estado in ("PARADO", "ERROR") or estado is None:
        raise Parada(f"la transformación está en {estado}: no se parte", "PARADO")
    salida = [s for s in tr.get("salidas", []) if s.get("ruta") == ENTRADA]
    if not salida or salida[0].get("sha256") != huella_entrada:
        raise Parada(f"la huella de {ENTRADA} no es la que dejó la transformación: no se reutiliza (bloque común, "
                     "regla 7)", "PARADO")
    particion = tr.get("particion") or {}
    for p in PARTES:
        fechas = particion.get(CLAVE_EN_TRANSFORMACION[p["parte"]], {})
        if (fechas.get("desde"), fechas.get("hasta")) != (p["desde"].isoformat(), p["hasta"].isoformat()):
            raise Parada(f"las fechas de {p['parte']} en {TRANSFORMACION} ({fechas}) no son las de las reglas §7",
                         "PARADO")
    return estado


# =================================================================================================================
# 5. La pasada: separar por periodo, comprobar contra las reglas y escribir los «.parcial»
# =================================================================================================================
def nuevo_acumulador():
    """Lo que se cuenta de cada parte mientras se lee la entrada."""
    return {"filas": 0, "objetivo": 0, "fechas": set(), "discos": set(), "horizonte_max": None,
            "horizonte_vacio": 0}


def pasada(raiz, parciales):
    """Lee la entrada grupo a grupo, separa cada grupo por periodo y escribe cada parte en su «.parcial».

    Cada grupo de la entrada tiene que ser una sola fecha, y cada fecha estar en un solo grupo: así cada parte sale con
    un grupo de filas por fecha y una clave serial_number y fecha solo se puede repetir dentro de su grupo. Si no, ERROR.
    Devuelve los recuentos de la entrada y de cada parte.
    """
    pf = pq.ParquetFile(raiz / ENTRADA)
    esquema = pf.schema_arrow
    # La misma compresión que la entrada, para que las partes pesen lo mismo que su trozo de la tabla
    compresion = pf.metadata.row_group(0).column(0).compression.lower() if pf.num_row_groups else "snappy"
    compresion = "none" if compresion == "uncompressed" else compresion
    acu = {p["parte"]: nuevo_acumulador() for p in PARTES}
    r = {"filas_entrada": 0, "grupos": pf.num_row_groups, "columnas": len(esquema.names), "objetivo_entrada": 0,
         "fechas_vistas": [], "claves_compartidas": 0, "claves_repetidas": 0, "filas_que_no_coinciden_con_periodo": 0,
         "filas_sin_parte": 0, "filas_fuera_de_las_reglas": 0}
    escritores = {}
    try:
        for p in PARTES:
            escritores[p["parte"]] = pq.ParquetWriter(parciales[p["parte"]], esquema, compression=compresion)
        for i in range(pf.num_row_groups):
            t = pf.read_row_group(i)
            r["filas_entrada"] += t.num_rows
            r["objetivo_entrada"] += int(pc.sum(t[COLUMNA_OBJETIVO]).as_py() or 0)
            # 5.1 La forma de la entrada: una fecha por grupo y cada fecha en un solo grupo
            fechas = pc.unique(t[COLUMNA_FECHA]).to_pylist()
            if len(fechas) != 1 or fechas[0] is None:
                raise Parada(f"el grupo de filas {i} tiene {len(fechas)} fechas: se espera una por grupo")
            fecha = fechas[0].date()
            if fecha in r["fechas_vistas"]:
                raise Parada(f"la fecha {fecha} está en más de un grupo de filas")
            r["fechas_vistas"].append(fecha)
            # 5.2 Claves repetidas dentro de la fecha (la clave es serial_number y fecha)
            discos_grupo = t[COLUMNA_DISCO]
            r["claves_repetidas"] += t.num_rows - len(pc.unique(discos_grupo))
            # 5.3 Cada fila contra la regla: la parte que dan las reglas §7 a esta fecha frente a su periodo
            regla = parte_por_regla(fecha)
            periodo = t[COLUMNA_PERIODO]
            if regla is None:
                r["filas_fuera_de_las_reglas"] += t.num_rows
                r["filas_que_no_coinciden_con_periodo"] += t.num_rows
            else:
                iguales = pc.sum(pc.fill_null(pc.equal(periodo, regla["periodo"]), False)).as_py() or 0
                r["filas_que_no_coinciden_con_periodo"] += t.num_rows - int(iguales)
            # 5.4 Separar por periodo y escribir cada trozo como un grupo de filas de su parte
            asignadas = 0
            discos_por_parte = {}
            for p in PARTES:
                mascara = pc.fill_null(pc.equal(periodo, p["periodo"]), False)
                trozo = t.filter(mascara)
                asignadas += trozo.num_rows
                if trozo.num_rows == 0:
                    continue
                a = acu[p["parte"]]
                a["filas"] += trozo.num_rows
                a["objetivo"] += int(pc.sum(trozo[COLUMNA_OBJETIVO]).as_py() or 0)
                a["fechas"].add(fecha)
                unicos = set(pc.unique(trozo[COLUMNA_DISCO]).to_pylist())
                discos_por_parte[p["parte"]] = unicos
                a["discos"].update(unicos)
                h = trozo[COLUMNA_HORIZONTE]
                a["horizonte_vacio"] += h.null_count
                m = pc.max(h).as_py()
                if m is not None and (a["horizonte_max"] is None or m > a["horizonte_max"]):
                    a["horizonte_max"] = m
                escritores[p["parte"]].write_table(trozo, row_group_size=trozo.num_rows)
            r["filas_sin_parte"] += t.num_rows - asignadas
            # 5.5 Claves en las dos partes: el mismo disco en la misma fecha con los dos periodos
            if len(discos_por_parte) == len(PARTES):
                r["claves_compartidas"] += len(set.intersection(*discos_por_parte.values()))
    finally:
        for w in escritores.values():
            w.close()
    r["partes"] = acu
    r["esquema"] = esquema
    return r


# =================================================================================================================
# 6. Las comprobaciones (skill §1 y encargo), calculadas con lo que se ejecutó
# =================================================================================================================
def tasa(a):
    """Parte de las fotos de una parte con el objetivo en 1; None si la parte no tiene fotos."""
    return a["objetivo"] / a["filas"] if a["filas"] else None


def comprobar(r):
    """Las seis comprobaciones que paran con ERROR, y sin_entidades_compartidas en null (partición por fecha)."""
    e, v = r["partes"]["entrenamiento"], r["partes"]["validacion"]
    te, tv = tasa(e), tasa(v)
    r["diferencia_tasa_puntos"] = abs(te - tv) * 100 if te is not None and tv is not None else None
    r["discos_en_las_dos_partes"] = len(e["discos"] & v["discos"])
    ultimo_dia_construccion = PARTES[1]["desde"] - dt.timedelta(days=1)
    return {
        "sin_filas_compartidas": r["claves_compartidas"] == 0,
        # Partición por fecha: un disco sigue en servicio de una parte a la otra; el recuento va en
        # discos_en_las_dos_partes
        "sin_entidades_compartidas": None,
        "suman_la_entrada": e["filas"] + v["filas"] == r["filas_entrada"],
        "tasa_dentro_de_tolerancia": (r["diferencia_tasa_puntos"] is not None
                                      and r["diferencia_tasa_puntos"] <= TOLERANCIA_PUNTOS),
        "fechas_sin_solape": bool(e["fechas"]) and bool(v["fechas"]) and max(e["fechas"]) < min(v["fechas"]),
        "horizonte_cerrado": (e["horizonte_max"] is not None and e["horizonte_vacio"] == 0
                              and e["horizonte_max"].date() <= ultimo_dia_construccion),
        "coincide_con_periodo": r["filas_que_no_coinciden_con_periodo"] == 0,
    }


def validar_salida(r, parciales):
    """Las partes escritas: mismas columnas, en el mismo orden y con los mismos tipos; un grupo por fecha; sus filas."""
    v = {"mismas_columnas_y_tipos": [], "un_grupo_por_fecha": [], "filas_escritas": []}
    for p in PARTES:
        pf = pq.ParquetFile(parciales[p["parte"]])
        a = r["partes"][p["parte"]]
        v["mismas_columnas_y_tipos"].append(pf.schema_arrow.equals(r["esquema"]))
        fechas = []
        for i in range(pf.num_row_groups):
            unicas = pc.unique(pf.read_row_group(i, columns=[COLUMNA_FECHA])[COLUMNA_FECHA]).to_pylist()
            fechas.append(unicas[0].date() if len(unicas) == 1 else None)
        v["un_grupo_por_fecha"].append(None not in fechas and len(set(fechas)) == len(fechas) == len(a["fechas"]))
        v["filas_escritas"].append(pf.metadata.num_rows == a["filas"])
    return {k: all(x) for k, x in v.items()}


# =================================================================================================================
# 7. El JSON
# =================================================================================================================
def bloque_parte(p, a, huella):
    """Lo propio de una parte en particion.json (resultado.md)."""
    t = tasa(a)
    return {"parte": p["parte"], "periodo": p["periodo"], "regla": {"desde": p["desde"].isoformat(),
                                                                    "hasta": p["hasta"].isoformat()},
            "ruta": p["ruta"], "sha256": huella, "filas": a["filas"], "fotos_con_objetivo": a["objetivo"],
            "tasa_objetivo": t, "tasa_objetivo_pct": t * 100 if t is not None else None,
            "fecha_min": min(a["fechas"]).isoformat() if a["fechas"] else None,
            "fecha_max": max(a["fechas"]).isoformat() if a["fechas"] else None,
            "fotos_mensuales": len(a["fechas"]), "horizonte_hasta_max": dia(a["horizonte_max"]),
            "horizonte_vacio": a["horizonte_vacio"], "discos": len(a["discos"])}


def resumen(res):
    """Una o dos frases con las cifras del propio JSON."""
    e, v = res["partes"][0], res["partes"][1]
    return (f"Construcción: {numero(e['filas'])} fotos y {numero(e['fotos_con_objetivo'])} con fallo a 30 días "
            f"({numero(e['tasa_objetivo_pct'], 4)} %), del {e['fecha_min']} al {e['fecha_max']}. Validación: "
            f"{numero(v['filas'])} fotos y {numero(v['fotos_con_objetivo'])} con fallo "
            f"({numero(v['tasa_objetivo_pct'], 4)} %), del {v['fecha_min']} al {v['fecha_max']}; "
            f"{numero(res['discos_en_las_dos_partes'])} discos están en las dos partes.")


def escribir_json(raiz, res):
    """Escribe particion.json en UTF-8, sin NaN."""
    ruta = raiz / SALIDA_JSON
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(res, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def base_json(huella_entrada, filas, columnas, grupos, estado_tr):
    """El bloque común y lo fijo de lo propio, antes de saber el resultado."""
    return {
        "skill": SKILL,
        "version_skill": version_skill(),
        "script": SCRIPT,
        "encargo": ENCARGO,
        "fecha_datos": FECHA_DATOS,
        "fecha_ejecucion": dt.datetime.now().replace(microsecond=0).isoformat(),
        "entradas": [{"ruta": ENTRADA, "sha256": huella_entrada, "filas": filas, "columnas": columnas,
                      "grupos_de_filas": grupos},
                     {"ruta": TRANSFORMACION, "estado": estado_tr}],
        "resultado": {"estado": None, "riesgo": None, "resumen": None, "artefactos": [], "siguiente": None},
        "pendientes": [],
        "estrategia": "fecha",
        "por_que": POR_QUE,
        "semilla": SEMILLA,
        "columna_fecha": COLUMNA_FECHA,
        "columna_grupo": None,
        "columna_periodo": COLUMNA_PERIODO,
        "partes": [],
        "parametros": [
            {"nombre": "semilla", "valor": SEMILLA, "origen": "parametros.md; no se usa, la partición por fecha no sortea"},
            {"nombre": "tolerancia de la tasa del objetivo entre partes", "valor": TOLERANCIA_PUNTOS,
             "origen": "parametros.md, 2 puntos porcentuales"},
            {"nombre": "proporción de validación", "valor": None,
             "origen": "parametros.md da 30 %; no aplica: las fechas de la regla §7 fijan las partes"},
        ],
        "teoria": TEORIA,
        "datos_personales": ("Ninguno: los datos son de discos y no traen nada de personas; serial_number identifica un "
                             "disco (reglas-negocio §9). No existe contexto-proyecto/fuentes/proteccion-datos.json: "
                             "los datos no pasaron por la protección porque no hacía falta."),
    }


# =================================================================================================================
# 8. Principal
# =================================================================================================================
def principal(raiz):
    """Comprueba la entrada, parte, comprueba, valida, guarda y escribe el JSON. Devuelve el código de salida."""
    inicio = time.time()
    entrada = raiz / ENTRADA
    proc = entrada.parent
    parciales = {p["parte"]: proc / (Path(p["ruta"]).name + ".parcial") for p in PARTES}
    finales = {p["parte"]: raiz / p["ruta"] for p in PARTES}
    res = base_json(None, None, None, None, None)
    try:
        # 8.1 La entrada y la transformación
        if not entrada.exists():
            raise Parada(f"falta {ENTRADA}", "PARADO")
        huella = sha256(entrada)
        meta = pq.ParquetFile(entrada).metadata
        estado_tr = leer_transformacion(raiz, huella)
        res = base_json(huella, meta.num_rows, meta.num_columns, meta.num_row_groups, estado_tr)
        # 8.2 Un «.parcial» que quedara de una ejecución cortada se quita; las partes ya guardadas no se tocan hasta
        # que esta ejecución pase todo (si para, el JSON en ERROR o PARADO dice que no valen)
        for ruta in parciales.values():
            if ruta.exists():
                ruta.unlink()
        # 8.3 La pasada y las comprobaciones
        r = pasada(raiz, parciales)
        comprobaciones = comprobar(r)
        res.update({
            "partes": [bloque_parte(p, r["partes"][p["parte"]], None) for p in PARTES]
                      + [{"parte": "lote_produccion", "ruta": None, "sha256": None, "filas": None,
                          "tasa_objetivo": None, "fecha_min": None, "fecha_max": None, "motivo": MOTIVO_LOTE}],
            "objetivo_entrada": r["objetivo_entrada"],
            "claves_compartidas": r["claves_compartidas"],
            "claves_repetidas": r["claves_repetidas"],
            "filas_que_no_coinciden_con_periodo": r["filas_que_no_coinciden_con_periodo"],
            "filas_fuera_de_las_reglas": r["filas_fuera_de_las_reglas"],
            "filas_sin_parte": r["filas_sin_parte"],
            "discos_en_las_dos_partes": r["discos_en_las_dos_partes"],
            "diferencia_tasa_puntos": r["diferencia_tasa_puntos"],
            "tolerancia_puntos": TOLERANCIA_PUNTOS,
            "comprobaciones": comprobaciones,
        })
        rojas = [k for k, x in comprobaciones.items() if x is False]
        if rojas:
            raise Parada("comprobaciones en rojo: " + ", ".join(rojas))
        # 8.4 Las validaciones de lo escrito, antes de darlo por bueno
        validaciones = validar_salida(r, parciales)
        res["validaciones_salida"] = validaciones
        rojas = [k for k, x in validaciones.items() if not x]
        if rojas:
            raise Parada("validaciones de la salida en rojo: " + ", ".join(rojas))
        # 8.5 Guardar: los «.parcial» pasan a ser las partes, con su huella
        for p, bloque in zip(PARTES, res["partes"]):
            parciales[p["parte"]].replace(finales[p["parte"]])
            bloque["sha256"] = sha256(finales[p["parte"]])
        avisos = []
        if r["discos_en_las_dos_partes"]:
            avisos.append(f"{numero(r['discos_en_las_dos_partes'])} discos tienen fotos en las dos partes: es lo "
                          "esperado en una partición por fecha, y la validación cruzada de construcción irá por fecha.")
        res["avisos"] = avisos
        res["resultado"] = {"estado": "OK", "riesgo": "bajo", "resumen": resumen(res),
                            "artefactos": [p["ruta"] for p in PARTES] + [SALIDA_JSON],
                            "siguiente": ("preparacion-modelo §2 y §3: el desequilibrio descrito y la matriz de "
                                          "transformaciones propuesta, con la tabla de entrenamiento (encargo 20, "
                                          "segunda parte)")}
        codigo = 0
    except Parada as p:
        for ruta in parciales.values():
            if ruta.exists():
                ruta.unlink()
        res["resultado"] = {"estado": p.estado, "riesgo": "alto", "resumen": str(p), "artefactos": [SALIDA_JSON],
                            "siguiente": "corregir la causa y volver a ejecutar; la fase siguiente no empieza"}
        codigo = 2
    except Exception as e:  # noqa: BLE001 - el JSON se escribe también cuando falla (bloque común, regla 5)
        for ruta in parciales.values():
            if ruta.exists():
                ruta.unlink()
        res["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(e).__name__}: {e}",
                            "artefactos": [SALIDA_JSON], "siguiente": "corregir el fallo y volver a ejecutar"}
        res["traza"] = traceback.format_exc()[-3000:]
        codigo = 1
    res["ejecucion"] = {"python": platform.python_version(), "ejecutable": sys.executable,
                        "pyarrow": pa.__version__, "segundos": round(time.time() - inicio, 1)}
    escribir_json(raiz, res)
    print(f"{res['resultado']['estado']}: {res['resultado']['resumen']}")
    return codigo


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--raiz", default=str(CASO), help="carpeta del caso (por defecto, la del script)")
    sys.exit(principal(Path(argumentos.parse_args().raiz).resolve()))
