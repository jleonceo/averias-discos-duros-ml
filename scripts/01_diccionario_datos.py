"""Diccionario de datos del origen del caso 68, averías de discos duros en Backblaze.

Describe, tal como llegan y sin tocarlas, las fuentes que el caso usa ahora:
- los cuatro datasets del caso (data/raw/podado/): fotos mensuales, ventanas de fallo, recuento diario y lista de fallos;
- el esquema de Backblaze, que hace de diccionario de la organización y se compara con las columnas de las fotos mensuales y las ventanas de fallo.

El día a día de los discos que no fallan no está en los cuatro datasets: solo hay una foto al mes de cada disco.

Escribe config/fuentes/diccionario-datos-origen.json y, a partir de él, diccionario-datos-origen.md.

Uso: python scripts/01_diccionario_datos.py
Método: diccionario-datos (versión 05/11/2026, una nota del método), con programacion-del-caso.
"""

# =================================================================================================================
# 1. Configuración
# =================================================================================================================
import datetime as dt
import hashlib
import json
import platform
import re
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

# -----------------------------------------------------------------------------------------------------------------
# 1.1 Rutas, fechas y parámetros
# -----------------------------------------------------------------------------------------------------------------
CASO = Path(__file__).resolve().parents[1]
METODO = "diccionario-datos"
VERSION_METODO = "05/11/2026"
SCRIPT = "scripts/01_diccionario_datos.py"

# Fechas de las reglas de negocio: §5 (fecha de referencia), §7 (partición) y §4 (desde cuándo consta el sitio)
FECHA_DATOS = "2025-06-30"
INICIO_VALIDACION = dt.date(2024, 7, 1)
FIN_DATOS = dt.date(2025, 6, 30)
INICIO_SITIO = dt.date(2023, 7, 1)

# Parámetros de el método (parametros.md de diccionario-datos)
CODIFICACIONES = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]
LIMITE_LISTA = 15
RARA_PCT = 2.5
RARA_MIN = 5

# Límites de este script para contar valores distintos sin llenar la memoria: hasta 1.000 se guardan con su
# frecuencia; hasta 200.000, sin ella; por encima, se dice «más de 200.000». El número de serie se cuenta aparte, exacto.
LIMITE_FRECUENCIAS = 1_000
LIMITE_DISTINTOS = 200_000

# Grupos por capacidad de la fila. Reglas, apartado 3: los discos de arranque son los de 0,2 a 2 TB y los de datos tienen 4 TB
# o más; -1 y 0,1 TB son lecturas malas. Los cortes caen en huecos donde no hay ninguna capacidad.
CAPACIDAD_MIN_VALIDA = 2e11
CAPACIDAD_MAX_ARRANQUE = 3e12

TIPO_DE_CLASE = {"num": pa.float64(), "txt": pa.string(), "fecha": pa.string(), "bool": pa.bool_(), "otro": pa.string()}

# Columnas que no vienen de Backblaze: las añadió quien preparó los cuatro datasets (responsable, 17/11/2026)
COLUMNAS_DEL_DATASET = ("fecha", "dia_fallo", "discos", "fallos")
# Forma de los nombres del esquema: las columnas base y los contadores smart_N_raw y smart_N_normalized
FORMA_NOMBRE = re.compile(r"smart_\d+_(raw|normalized)|date|serial_number|model|capacity_bytes|failure|datacenter|"
                          r"cluster_id|vault_id|pod_id|pod_slot_num|is_legacy_format")

# -----------------------------------------------------------------------------------------------------------------
# 1.2 Descripciones y procedencias (bloque de configuración separado del cálculo, diccionario-datos §4)
# -----------------------------------------------------------------------------------------------------------------
# Columna: (rol, significado, procedencia). Las que se añadieron al preparar los cuatro datasets las describió el responsable el 17/11/2026.
COLUMNAS = {
    "date": ("fecha", "día del registro, como texto AAAA-MM-DD; es la única fecha de los datos", "reglas de negocio §5"),
    "fecha": ("fecha", "día del registro, añadido como fecha al preparar los cuatro datasets", "responsable 17/11/2026"),
    "dia_fallo": ("fecha", "día del fallo: en las ventanas, el fallo al que pertenece la fila; en la lista, el día del fallo",
                  "responsable 17/11/2026"),
    "serial_number": ("identificador", "número de serie: identifica un disco, no a una persona", "reglas de negocio §3 y §9"),
    "model": ("categorica", "número de modelo del disco; del nombre sale el fabricante", "reglas de negocio §3"),
    "capacity_bytes": ("magnitud", "capacidad del disco en bytes; la de un disco es la de su modelo", "reglas de negocio §3"),
    "failure": ("booleana", "1 el día en que Backblaze da el disco por fallado; incluye las retiradas por avisos",
                "reglas de negocio §3"),
    "datacenter": ("categorica", "centro de datos (phx1, sac0, sac2, iad1, ams5, yyz1); consta desde el 01/07/2023",
                   "reglas de negocio §4"),
    "cluster_id": ("codigo", "grupo de servidores dentro del centro, según la ficha de los datos; ninguna regla lo define",
                   "sin_confirmar"),
    "vault_id": ("codigo", "vault: 20 servidores iguales que guardan los datos repartidos", "reglas de negocio §4"),
    "pod_id": ("codigo", "servidor dentro del vault", "reglas de negocio §4"),
    "pod_slot_num": ("codigo", "ranura del disco dentro del servidor", "reglas de negocio §4"),
    "is_legacy_format": ("booleana", "si la fila viene en el formato antiguo, según la ficha de los datos", "sin_confirmar"),
    "discos": ("magnitud", "discos en servicio ese día con ese modelo, capacidad y centro: días de disco",
               "responsable 17/11/2026"),
    "fallos": ("magnitud", "fallos de ese día, modelo, capacidad y centro", "responsable 17/11/2026"),
    "nombre_en_el_esquema": ("identificador", "cada línea del esquema: el nombre de una columna del registro diario",
                             "declarado"),
}

# Contadores SMART con nombre en la ficha de los datos (tomado de la Wikipedia; sin confirmar por Backblaze).
SMART_NOMBRES = {
    1: "Read Error Rate", 2: "Throughput Performance", 3: "Spin-Up Time", 4: "Start/Stop Count",
    5: "Reallocated Sectors Count", 7: "Seek Error Rate", 8: "Seek Time Performance", 9: "Power-On Hours",
    10: "Spin Retry Count", 12: "Power Cycle Count", 22: "Current Helium Level", 23: "Helium Condition Lower",
    24: "Helium Condition Upper", 184: "End-to-End error", 187: "Reported Uncorrectable Errors", 188: "Command Timeout",
    189: "High Fly Writes", 190: "Airflow Temperature", 191: "G-sense Error Rate", 192: "Power-off Retract Count",
    193: "Load Cycle Count", 194: "Temperature", 195: "Hardware ECC Recovered", 196: "Reallocation Event Count",
    197: "Current Pending Sector Count", 198: "Offline Uncorrectable Sector Count", 199: "UltraDMA CRC Error Count",
    200: "Multi-Zone Error Rate", 220: "Disk Shift", 222: "Loaded Hours", 223: "Load/Unload Retry Count",
    224: "Load Friction", 226: "Load 'In'-time", 240: "Head Flying Hours", 241: "Total LBAs Written",
    242: "Total LBAs Read",
}
# Los cinco de avería, con el nombre de las reglas, apartado 3; su número sale de la ficha, por eso van sin confirmar
SMART_AVERIA = {5: "sectores sustituidos", 187: "errores sin corregir", 188: "órdenes abortadas por tiempo",
                197: "sectores pendientes", 198: "sectores ilegibles"}
# Formato propio de cada fabricante (ficha de los datos; reglas, apartado 5: no se comparan entre fabricantes)
SMART_FORMATO_PROPIO = {1, 7, 195}

# Columnas con más de una lectura legítima que las reglas no fijan (diccionario-datos §5)
DECISIONES = {
    "model": ("¿Los nombres de modelo que solo se distinguen por los espacios son el mismo modelo?",
              ["son el mismo modelo escrito de dos formas: se cuentan juntos",
               "son modelos distintos, como los publica Backblaze: se cuentan aparte"]),
    "smart_188_raw": ("¿Cómo se lee el valor en bruto del 188, que pasa de mil millones en una parte de las filas?",
                      ["es un recuento de órdenes abortadas y se usa su valor",
                       "tiene un formato propio del fabricante: solo se usa si es cero o no",
                       "no se usa ni como recuento ni como aviso"]),
    "smart_5_raw": ("¿Los valores más altos del 5, pegados a 65.535, son el tope del contador o un recuento real?",
                    ["es el tope del contador: el valor real es ese o mayor", "es un recuento real del disco"]),
    "smart_187_raw": ("¿El valor 65.535 del 187 es el tope del contador o un recuento real?",
                      ["es el tope de un contador de 16 bits: el valor real es ese o mayor", "es un recuento real del disco"]),
}

# Clase fijada por falta de fuente: lo que ninguna fuente del caso define
CLASE_FIJA = {
    "cluster_id": "qué agrupa un cluster no lo define ninguna regla ni documento de Backblaze del caso",
    "is_legacy_format": "qué es el formato antiguo no lo define ninguna regla ni documento de Backblaze del caso",
}

# Qué significa el cero de una magnitud y la fila que falta (diccionario-datos §3, una nota del método)
CERO = {
    "smart": ("el disco apunta cero en ese contador; no es un vacío, que quiere decir que el modelo no lo apunta",
              "reglas de negocio §5"),
    "smart_averia": ("el contador de avería está a cero; si los cinco están a cero o vacíos, el disco no avisa",
                     "reglas de negocio §3 y §5"),
    "fallos": ("ningún fallo ese día en esa combinación de modelo, capacidad y centro", "reglas de negocio §6"),
}
SIN_FILA = {
    "fotos_mensuales": ("el disco no estaba en servicio el día 1 de ese mes; si vuelve después, no ha desaparecido",
                        "reglas de negocio §3"),
    "ventanas_fallo": ("el disco no estaba en servicio ese día de los 30 anteriores a su fallo", "reglas de negocio §3 y §5"),
    "recuento_diario": ("ningún disco de ese modelo, capacidad y centro estuvo en servicio ese día", "reglas de negocio §5"),
}

# Qué es una fila y su clave (diccionario-datos §3), comprobado después en los datos
TABLAS = {
    "fotos_mensuales": ("un disco el día 1 de un mes", ["serial_number", "fecha"]),
    "ventanas_fallo": ("un disco en un día de los 30 anteriores a un fallo o el del fallo, con el fallo al que pertenece",
                       ["serial_number", "fecha"]),
    "recuento_diario": ("un día, un modelo, una capacidad y un centro, con sus discos y sus fallos",
                        ["fecha", "model", "capacity_bytes", "datacenter"]),
    "fallos": ("un disco y el día de su fallo", ["serial_number", "dia_fallo"]),
    "esquema_backblaze": ("una línea del esquema de Backblaze", ["nombre_en_el_esquema"]),
}

# Lo que ningún dato ni documento del caso deja saber (reglas, apartado 3 y §6; ficha del caso, «Lo que falta»)
NO_SE_PUEDE_SABER = [
    ("si un fallo es una avería o una retirada por avisos que decide Backblaze", "reglas de negocio §3"),
    ("por qué desaparece un disco sin fallo: migración, retirada sana o disco temporal", "reglas de negocio §3"),
    ("la fecha de compra y de fabricación de cada disco, y si está en garantía", "reglas de negocio §5 y §6"),
    ("la región de cada centro, la paridad de cada vault y cuánto tardó de verdad cada reconstrucción", "reglas de negocio §4"),
    ("el sitio de un disco antes del 01/07/2023", "reglas de negocio §4"),
]


# =================================================================================================================
# 2. Perfil de una tabla lógica, trozo a trozo
# =================================================================================================================
def tramo_de(fecha):
    """Devuelve el tramo de una fecha: construcción antes o después del sitio, validación o fuera de los datos."""
    if fecha > FIN_DATOS:
        return "fuera_de_los_datos"
    if fecha >= INICIO_VALIDACION:
        return "validacion"
    return "construccion_con_sitio" if fecha >= INICIO_SITIO else "construccion_antes_sitio"


def periodo_de(tramo):
    """Pasa un tramo a su periodo de las reglas, apartado 7."""
    return "construccion" if tramo.startswith("construccion") else tramo


def grupo_de_capacidad(capacidad):
    """Grupo de una capacidad leída: datos, arranque o capacidad no válida (reglas, apartado 3)."""
    if capacidad is None:
        return "sin_capacidad"
    if capacidad < CAPACIDAD_MIN_VALIDA:
        return "capacidad_no_valida"
    return "arranque" if capacidad < CAPACIDAD_MAX_ARRANQUE else "datos"


def a_python(valor):
    """Convierte un valor a un tipo que JSON acepta: enteros si no tienen decimales y nada de NaN."""
    if isinstance(valor, float):
        if valor != valor or valor in (float("inf"), float("-inf")):
            return None
        if valor.is_integer() and abs(valor) < 2**53:
            return int(valor)
    if isinstance(valor, (dt.date, dt.datetime)):
        return valor.isoformat()
    return valor


def nuevo_acumulado():
    """Acumulado vacío de una columna."""
    return {"filas_con_columna": 0, "nulos": 0, "nan": 0, "vacios": 0, "espacios": 0, "ceros": 0, "negativos": 0,
            "con_hora": 0, "trozos": 0, "primera_etiqueta": None, "ultima_etiqueta": None,
            "tipos": Counter(), "clases": Counter(), "min": {}, "max": {}, "filas_por_tramo": Counter(),
            "nulos_por_tramo": Counter(), "filas_por_grupo": Counter(), "nulos_por_grupo": Counter(),
            "modo": "frecuencias", "frec": {}, "unicos": {}}


class Perfil:
    """Acumula el perfil de las columnas de una tabla lógica que llega en trozos (un día, un mes, un fichero)."""

    def __init__(self):
        """Empieza el perfil sin filas."""
        self.filas = 0
        self.filas_por_tramo = Counter()
        self.filas_por_grupo_tramo = Counter()
        self.columnas = {}
        self.pares = Counter()
        self.pares_discos = Counter()

    # -------------------------------------------------------------------------------------------------------------
    # 2.1 Un trozo nuevo
    # -------------------------------------------------------------------------------------------------------------
    def anadir(self, tabla, tramo, etiqueta, aparte=("serial_number",)):
        """Suma un trozo de un solo tramo: filas, grupos por capacidad, pares modelo y capacidad, y cada columna."""
        n = tabla.num_rows
        self.filas += n
        self.filas_por_tramo[tramo] += n
        # Los grupos por capacidad se separan filtrando solo los pequeños; los de datos son el resto
        subtablas = {}
        if "capacity_bytes" in tabla.column_names and n and not pa.types.is_null(tabla["capacity_bytes"].type):
            cap = pc.cast(tabla["capacity_bytes"], pa.float64())
            subtablas = {
                "capacidad_no_valida": tabla.filter(pc.less(cap, CAPACIDAD_MIN_VALIDA)),
                "arranque": tabla.filter(pc.and_(pc.greater_equal(cap, CAPACIDAD_MIN_VALIDA), pc.less(cap, CAPACIDAD_MAX_ARRANQUE))),
                "sin_capacidad": tabla.filter(pc.is_null(cap)),
            }
            resto = n - sum(s.num_rows for s in subtablas.values())
            for g, s in subtablas.items():
                self.filas_por_grupo_tramo[(g, tramo)] += s.num_rows
            self.filas_por_grupo_tramo[("datos", tramo)] += resto
            # Pares modelo y capacidad, para saber después la capacidad de cada modelo (reglas, apartado 3)
            if "model" in tabla.column_names:
                agregados = [([], "count_all")] + ([("discos", "sum")] if "discos" in tabla.column_names else [])
                for fila in tabla.select([c for c in ("model", "capacity_bytes", "discos") if c in tabla.column_names]) \
                        .group_by(["model", "capacity_bytes"]).aggregate(agregados).to_pylist():
                    self.pares[(tramo, fila["model"], fila["capacity_bytes"])] += fila["count_all"]
                    if "discos_sum" in fila:
                        self.pares_discos[(tramo, fila["model"], fila["capacity_bytes"])] += fila["discos_sum"]
        else:
            self.filas_por_grupo_tramo[("sin_capacidad", tramo)] += n
        for nombre in tabla.column_names:
            acc = self.columnas.setdefault(nombre, nuevo_acumulado())
            if nombre in aparte:
                acc["modo"] = "aparte"
            nulos_g = {g: (s.num_rows, s[nombre].null_count) for g, s in subtablas.items()}
            perfilar_columna(acc, tabla[nombre], tramo, etiqueta, nulos_g, n)

    # -------------------------------------------------------------------------------------------------------------
    # 2.2 Guardar y juntar perfiles parciales
    # -------------------------------------------------------------------------------------------------------------
    def a_json(self):
        """Devuelve el perfil como diccionario de JSON y una tabla Arrow con los valores distintos guardados."""
        columnas, filas_unicos = {}, {"columna": [], "clase": [], "valor_num": [], "valor_txt": []}
        for nombre, acc in self.columnas.items():
            d = {k: (dict(v) if isinstance(v, Counter) else v) for k, v in acc.items() if k not in ("frec", "unicos")}
            for clave in ("filas_por_tramo", "nulos_por_tramo", "filas_por_grupo", "nulos_por_grupo", "tipos", "clases"):
                d[clave] = dict(acc[clave])
            d["frecuencias"] = [[k, a_python(v), c] for (k, v), c in acc["frec"].items()] if acc["modo"] == "frecuencias" else None
            for clase, arr in acc["unicos"].items():
                valores = arr.to_pylist()
                filas_unicos["columna"] += [nombre] * len(valores)
                filas_unicos["clase"] += [clase] * len(valores)
                filas_unicos["valor_num"] += [v if clase == "num" else None for v in valores]
                filas_unicos["valor_txt"] += [None if clase == "num" else str(v) for v in valores]
            columnas[nombre] = d
        datos = {"filas": self.filas, "filas_por_tramo": dict(self.filas_por_tramo),
                 "filas_por_grupo_tramo": [[g, t, n] for (g, t), n in self.filas_por_grupo_tramo.items()],
                 "pares": [[t, m, c, n, self.pares_discos.get((t, m, c))] for (t, m, c), n in self.pares.items()],
                 "orden": list(self.columnas), "columnas": columnas}
        tabla_unicos = pa.table({"columna": pa.array(filas_unicos["columna"], pa.string()),
                                 "clase": pa.array(filas_unicos["clase"], pa.string()),
                                 "valor_num": pa.array(filas_unicos["valor_num"], pa.float64()),
                                 "valor_txt": pa.array(filas_unicos["valor_txt"], pa.string())})
        return datos, tabla_unicos

    def juntar(self, datos, tabla_unicos):
        """Suma a este perfil uno guardado con a_json, con sus valores distintos."""
        self.filas += datos["filas"]
        self.filas_por_tramo.update(datos["filas_por_tramo"])
        for g, t, n in datos["filas_por_grupo_tramo"]:
            self.filas_por_grupo_tramo[(g, t)] += n
        for t, m, c, n, d in datos["pares"]:
            self.pares[(t, m, c)] += n
            if d is not None:
                self.pares_discos[(t, m, c)] += d
        # Los valores distintos guardados, por columna y clase
        unicos = {}
        if tabla_unicos.num_rows:
            df = tabla_unicos.to_pandas()
            for (col, clase), parte in df.groupby(["columna", "clase"], sort=False):
                if clase == "num":
                    unicos[(col, clase)] = pa.array(parte["valor_num"].to_numpy(), pa.float64())
                elif clase == "bool":
                    unicos[(col, clase)] = pa.array((parte["valor_txt"] == "True").tolist(), pa.bool_())
                else:
                    unicos[(col, clase)] = pa.array(parte["valor_txt"].tolist(), pa.string())
        for nombre in datos["orden"]:
            src = datos["columnas"][nombre]
            acc = self.columnas.setdefault(nombre, nuevo_acumulado())
            for clave in ("filas_con_columna", "nulos", "nan", "vacios", "espacios", "ceros", "negativos", "con_hora", "trozos"):
                acc[clave] += src[clave]
            for clave in ("tipos", "clases", "filas_por_tramo", "nulos_por_tramo", "filas_por_grupo", "nulos_por_grupo"):
                acc[clave].update(src[clave])
            for clase, v in src["min"].items():
                acc["min"][clase] = v if clase not in acc["min"] else min(acc["min"][clase], v)
            for clase, v in src["max"].items():
                acc["max"][clase] = v if clase not in acc["max"] else max(acc["max"][clase], v)
            for clave, elegir in (("primera_etiqueta", min), ("ultima_etiqueta", max)):
                if src[clave] is not None:
                    acc[clave] = src[clave] if acc[clave] is None else elegir(acc[clave], src[clave])
            juntar_valores(acc, src, {cl: arr for (col, cl), arr in unicos.items() if col == nombre})


def perfilar_columna(acc, arr, tramo, etiqueta, nulos_g, n):
    """Suma al acumulado de una columna lo de un trozo: nulos, tipo, mínimo, máximo, ceros, espacios y valores."""
    nulos = arr.null_count
    acc["filas_con_columna"] += n
    acc["nulos"] += nulos
    acc["trozos"] += 1
    acc["primera_etiqueta"] = etiqueta if acc["primera_etiqueta"] is None else min(acc["primera_etiqueta"], etiqueta)
    acc["ultima_etiqueta"] = etiqueta if acc["ultima_etiqueta"] is None else max(acc["ultima_etiqueta"], etiqueta)
    acc["filas_por_tramo"][tramo] += n
    acc["nulos_por_tramo"][tramo] += nulos
    datos_f, datos_n = n, nulos
    for g, (filas_g, nulos_gr) in nulos_g.items():
        acc["filas_por_grupo"][g] += filas_g
        acc["nulos_por_grupo"][g] += nulos_gr
        datos_f -= filas_g
        datos_n -= nulos_gr
    if nulos_g:
        acc["filas_por_grupo"]["datos"] += datos_f
        acc["nulos_por_grupo"]["datos"] += datos_n
    tipo = arr.type
    acc["tipos"][str(tipo)] += n
    if pa.types.is_null(tipo) or nulos == n:
        return
    # Cada tipo se lleva a una clase de valor; las fechas se comparan como texto AAAA-MM-DD
    if pa.types.is_timestamp(tipo) or pa.types.is_date(tipo):
        clase = "fecha"
        marca = arr if pa.types.is_timestamp(tipo) else pc.cast(arr, pa.timestamp("s"))
        acc["con_hora"] += pc.sum(pc.not_equal(pc.floor_temporal(marca, unit="day"), marca)).as_py() or 0
        valores = pc.strftime(marca, format="%Y-%m-%d")
    elif pa.types.is_string(tipo) or pa.types.is_large_string(tipo):
        clase = "txt"
        recortado = pc.utf8_trim_whitespace(arr)
        acc["espacios"] += pc.sum(pc.not_equal(recortado, arr)).as_py() or 0
        acc["vacios"] += pc.sum(pc.equal(recortado, "")).as_py() or 0
        valores = arr
    elif pa.types.is_boolean(tipo):
        clase, valores = "bool", arr
    elif pa.types.is_integer(tipo) or pa.types.is_floating(tipo):
        clase = "num"
        mm = pc.min_max(arr).as_py()
        mn, mx = a_python(mm["min"]), a_python(mm["max"])
        acc["min"]["num"] = mn if "num" not in acc["min"] else min(acc["min"]["num"], mn)
        acc["max"]["num"] = mx if "num" not in acc["max"] else max(acc["max"]["num"], mx)
        if mn is not None and mn <= 0 <= mx:
            acc["ceros"] += pc.sum(pc.equal(arr, 0)).as_py() or 0
        if mn is not None and mn < 0:
            acc["negativos"] += pc.sum(pc.less(arr, 0)).as_py() or 0
        if pa.types.is_floating(tipo):
            acc["nan"] += pc.sum(pc.is_nan(arr)).as_py() or 0
        valores = pc.cast(arr, pa.float64())
    else:
        clase, valores = "otro", pc.cast(arr, pa.string())
    acc["clases"][clase] += n - nulos
    if clase in ("fecha", "txt", "otro"):
        mm = pc.min_max(valores).as_py()
        acc["min"][clase] = mm["min"] if clase not in acc["min"] else min(acc["min"][clase], mm["min"])
        acc["max"][clase] = mm["max"] if clase not in acc["max"] else max(acc["max"][clase], mm["max"])
    sumar_valores(acc, clase, valores.drop_null())


def sumar_valores(acc, clase, valores):
    """Suma los valores de un trozo: con frecuencia hasta 1.000 distintos, sin ella hasta 200.000, y después nada."""
    if acc["modo"] in ("excedido", "aparte"):
        return
    if acc["modo"] == "frecuencias":
        vc = pc.value_counts(valores)
        for v, c in zip(vc.field("values").to_pylist(), vc.field("counts").to_pylist()):
            acc["frec"][(clase, v)] = acc["frec"].get((clase, v), 0) + c
        if len(acc["frec"]) > LIMITE_FRECUENCIAS:
            pasar_a_unicos(acc)
        return
    unir_unicos(acc, clase, pc.unique(valores))


def pasar_a_unicos(acc):
    """Cambia una columna de frecuencias a valores distintos sin frecuencia, porque pasa de 1.000."""
    por_clase = {}
    for (clase, v) in acc["frec"]:
        por_clase.setdefault(clase, []).append(v)
    acc["frec"], acc["modo"] = {}, "unicos"
    for clase, valores in por_clase.items():
        unir_unicos(acc, clase, pa.array(valores, TIPO_DE_CLASE[clase]))


def unir_unicos(acc, clase, nuevos):
    """Une valores distintos nuevos con los guardados; si pasan de 200.000, deja de guardarlos."""
    if acc["modo"] == "excedido":
        return
    if isinstance(nuevos, pa.ChunkedArray):
        nuevos = nuevos.combine_chunks()
    nuevos = nuevos.cast(TIPO_DE_CLASE[clase])
    actual = acc["unicos"].get(clase)
    acc["unicos"][clase] = pc.unique(nuevos if actual is None else pa.concat_arrays([actual, nuevos]))
    if sum(len(a) for a in acc["unicos"].values()) > LIMITE_DISTINTOS:
        acc["modo"], acc["unicos"] = "excedido", {}


def juntar_valores(acc, src, unicos_src):
    """Junta los valores de un perfil guardado con los del acumulado, respetando los dos límites."""
    if src["modo"] == "aparte" or acc["modo"] == "aparte":
        acc["modo"] = "aparte"
        return
    if src["modo"] == "excedido":
        acc["modo"], acc["frec"], acc["unicos"] = "excedido", {}, {}
        return
    if src["modo"] == "frecuencias":
        if acc["modo"] == "frecuencias":
            for clase, v, c in src["frecuencias"]:
                acc["frec"][(clase, v)] = acc["frec"].get((clase, v), 0) + c
            if len(acc["frec"]) > LIMITE_FRECUENCIAS:
                pasar_a_unicos(acc)
        elif acc["modo"] == "unicos":
            por_clase = {}
            for clase, v, _ in src["frecuencias"]:
                por_clase.setdefault(clase, []).append(v)
            for clase, valores in por_clase.items():
                unir_unicos(acc, clase, pa.array(valores, TIPO_DE_CLASE[clase]))
        return
    if acc["modo"] == "frecuencias":
        pasar_a_unicos(acc)
    for clase, arr in unicos_src.items():
        unir_unicos(acc, clase, arr)


# =================================================================================================================
# 3. Huella de un fichero
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leída por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


# =================================================================================================================
# 4. Los Parquet de los cuatro datasets
# =================================================================================================================
def partir_por_tramo(tabla, columna):
    """Parte una tabla en trozos de un solo tramo según una columna de fecha."""
    tipo = tabla[columna].type
    cortes = [(INICIO_SITIO, None), (INICIO_VALIDACION, None), (FIN_DATOS + dt.timedelta(days=1), None)]
    escalares = [pa.scalar(dt.datetime.combine(c, dt.time()), type=tipo) for c, _ in cortes]
    col = tabla[columna]
    mascaras = {
        "construccion_antes_sitio": pc.less(col, escalares[0]),
        "construccion_con_sitio": pc.and_(pc.greater_equal(col, escalares[0]), pc.less(col, escalares[1])),
        "validacion": pc.and_(pc.greater_equal(col, escalares[1]), pc.less(col, escalares[2])),
        "fuera_de_los_datos": pc.greater_equal(col, escalares[2]),
    }
    trozos = {t: tabla.filter(m) for t, m in mascaras.items()}
    sin_fecha = tabla.num_rows - sum(t.num_rows for t in trozos.values())
    if sin_fecha:
        raise ValueError(f"{sin_fecha} filas sin {columna}: no se pueden repartir por periodo")
    return {t: tr for t, tr in trozos.items() if tr.num_rows}


def describir_parquets(ficheros, columna_periodo, perfil=None):
    """Perfila una tabla partida en varios Parquet, fichero a fichero, y devuelve el perfil y lo de cada fichero."""
    perfil = perfil or Perfil()
    por_fichero, seriales = [], {}
    for ruta in ficheros:
        tabla = pq.read_table(ruta)
        trozos = partir_por_tramo(tabla, columna_periodo)
        for tramo, trozo in trozos.items():
            perfil.anadir(trozo, tramo, ruta.stem)
            if "serial_number" in trozo.column_names:
                u = pc.unique(trozo["serial_number"].drop_null())
                u = (u.combine_chunks() if isinstance(u, pa.ChunkedArray) else u).cast(pa.string())
                seriales[tramo] = u if tramo not in seriales else pc.unique(pa.concat_arrays([seriales[tramo], u]))
        fila = {"fichero": ruta.name, "filas": tabla.num_rows, "columnas": tabla.num_columns,
                "tramos": {t: tr.num_rows for t, tr in trozos.items()}}
        # Si el fichero es de una sola fecha, la clave disco y fecha se mira dentro del fichero
        if "fecha" in tabla.column_names and "serial_number" in tabla.column_names:
            fila["fechas_distintas"] = pc.count_distinct(tabla["fecha"]).as_py()
            fila["seriales_repetidos"] = tabla.num_rows - pc.count_distinct(tabla["serial_number"]).as_py()
        por_fichero.append(fila)
        del tabla
    return perfil, por_fichero, seriales


# =================================================================================================================
# 5. Cifras de cada tabla a partir del perfil
# =================================================================================================================
def capacidad_de_cada_modelo(pares):
    """Capacidades válidas que trae cada modelo en la tabla; la regla, apartado 3 dice que la de un disco es la de su modelo."""
    validas = {}
    for (_, modelo, cap), n in pares.items():
        if cap is not None and grupo_de_capacidad(cap) in ("datos", "arranque"):
            validas.setdefault(modelo, set()).add(cap)
    return validas


def grupos_de_la_tabla(perfil):
    """Filas por grupo y periodo, y las de capacidad no válida repartidas por la capacidad de su modelo."""
    por_grupo, por_grupo_periodo = Counter(), {}
    for (g, t), n in perfil.filas_por_grupo_tramo.items():
        por_grupo[g] += n
        por_grupo_periodo.setdefault(periodo_de(t), Counter())[g] += n
    validas = capacidad_de_cada_modelo(perfil.pares)
    no_valida = Counter({"datos": 0, "arranque": 0, "sin_capacidad_unica": 0})
    no_valida_periodo = {}
    for (t, modelo, cap), n in perfil.pares.items():
        if cap is not None and grupo_de_capacidad(cap) == "capacidad_no_valida":
            caps = validas.get(modelo, set())
            destino = grupo_de_capacidad(next(iter(caps))) if len(caps) == 1 else "sin_capacidad_unica"
            no_valida[destino] += n
            no_valida_periodo.setdefault(periodo_de(t), Counter())[destino] += n
    datos_modelo = por_grupo.get("datos", 0) + no_valida["datos"]
    datos_modelo_periodo = {p: c.get("datos", 0) + no_valida_periodo.get(p, Counter()).get("datos", 0)
                            for p, c in por_grupo_periodo.items()}
    modelos_varias = sorted(m for m, c in validas.items() if len(c) > 1)
    return {"filas_por_grupo": {g: n for g, n in por_grupo.items() if n or g != "sin_capacidad"},
            "filas_por_periodo_y_grupo": {p: dict(c) for p, c in por_grupo_periodo.items()},
            "capacidad_no_valida_por_modelo": dict(no_valida),
            "filas_datos_con_capacidad_del_modelo": datos_modelo,
            "filas_datos_con_capacidad_del_modelo_por_periodo": datos_modelo_periodo,
            "modelos_con_varias_capacidades_validas": modelos_varias}


def periodos(contador_tramos):
    """Pasa un contador por tramo a uno por periodo, con los dos periodos siempre presentes."""
    salida = {"construccion": 0, "validacion": 0}
    for t, n in contador_tramos.items():
        salida[periodo_de(t)] = salida.get(periodo_de(t), 0) + int(n)
    return salida


def normalizar_texto(valor):
    """Nombre normalizado de un valor de texto: minúsculas y un solo espacio entre palabras."""
    return " ".join(str(valor).lower().split())


def ficha_de_columna(tabla_nombre, nombre, acc, filas_tabla):
    """Construye la ficha de una columna: perfil medido, rol, significado, procedencia y clase."""
    # 5.1 Lo medido
    filas_con = acc["filas_con_columna"]
    valores_frec = acc["frec"] if acc["modo"] == "frecuencias" else None
    if acc["modo"] == "frecuencias":
        distintos = len(acc["frec"])
    elif acc["modo"] == "unicos":
        distintos = sum(len(a) for a in acc["unicos"].values())
    else:
        distintos = None
    clases = [c for c, n in acc["clases"].items() if n]
    minimo = maximo = None
    for clase in ("num", "fecha", "txt", "otro"):
        if clase in acc["min"]:
            minimo, maximo = acc["min"][clase], acc["max"][clase]
            break
    tipos = dict(acc["tipos"])
    tipo_leido = max(tipos, key=tipos.get) if tipos else None

    # 5.2 Rol, significado y procedencia, del bloque de configuración
    smart = re.fullmatch(r"smart_(\d+)_(raw|normalized)", nombre)
    observaciones, motivos_nsps, motivos_decision = [], [], []
    if smart:
        num, forma = int(smart.group(1)), smart.group(2)
        nombre_smart = SMART_AVERIA.get(num) or SMART_NOMBRES.get(num)
        rol = "magnitud" if forma == "raw" else "codigo"
        if forma == "raw":
            significado = f"contador SMART {num}, valor en bruto: {nombre_smart}" if nombre_smart else \
                f"contador SMART {num}, valor en bruto; su nombre no está en la ficha de los datos"
        else:
            significado = f"nota normalizada que pone el fabricante al contador SMART {num}" + (f" ({nombre_smart})" if nombre_smart else "")
        procedencia = "sin_confirmar"
        if num in SMART_AVERIA:
            observaciones.append("uno de los cinco contadores de avería de las reglas, apartado 3")
        if not nombre_smart:
            motivos_nsps.append("el contador no tiene nombre en ninguna fuente del caso")
        if num in SMART_FORMATO_PROPIO and forma == "raw":
            motivos_nsps.append("el valor en bruto tiene formato propio de cada fabricante y ninguna fuente lo explica")
    else:
        rol, significado, procedencia = COLUMNAS.get(nombre, ("texto_libre", "sin confirmar", "sin_confirmar"))
        if nombre not in COLUMNAS:
            motivos_nsps.append("columna sin descripción en ninguna fuente del caso")
    if nombre in CLASE_FIJA:
        motivos_nsps.append(CLASE_FIJA[nombre])

    # 5.3 Lo que se puede decir del cero y de la fila que falta en una magnitud
    significado_cero = significado_sin_fila = None
    if rol == "magnitud":
        if smart:
            texto, proc = CERO["smart_averia" if int(smart.group(1)) in SMART_AVERIA else "smart"]
        elif nombre in CERO:
            texto, proc = CERO[nombre]
        else:
            texto, proc = None, None
        if acc["ceros"] == 0:
            significado_cero = {"texto": "no hay ningún cero en la columna", "procedencia": "medido"}
        elif texto:
            significado_cero = {"texto": texto, "procedencia": proc}
        else:
            significado_cero = {"texto": "sin significado documentado", "procedencia": "sin_confirmar"}
            motivos_decision.append(f"tiene {acc['ceros']} ceros y ningún documento dice qué significa su cero")
        if tabla_nombre in SIN_FILA:
            t, p = SIN_FILA[tabla_nombre]
            significado_sin_fila = {"texto": t, "procedencia": p}

    # 5.4 Variantes que colapsan al normalizar, categorías raras y valores con 15 o menos
    variantes, raras, valores = [], [], None
    lista_valores = None
    if valores_frec is not None:
        lista_valores = sorted(((clase, v, c) for (clase, v), c in valores_frec.items()), key=lambda x: (x[0], x[1]))
    elif acc["modo"] == "unicos":
        lista_valores = [(cl, v, None) for cl, arr in acc["unicos"].items() for v in arr.to_pylist()]
    if lista_valores and rol in ("categorica", "codigo", "texto_libre", "identificador"):
        grupos = {}
        for clase, v, _ in lista_valores:
            if clase == "txt":
                grupos.setdefault(normalizar_texto(v), []).append(v)
        variantes = [sorted(vs) for vs in grupos.values() if len(vs) > 1]
        if variantes and nombre != "nombre_en_el_esquema":
            motivos_decision.append(f"{len(variantes)} valores tienen variantes que solo se distinguen por mayúsculas o espacios")
    if valores_frec is not None and rol == "categorica":
        con_valor = filas_con - acc["nulos"]
        raras = [{"categoria": v, "filas": c, "pct": round(100 * c / con_valor, 4)} for (clase, v), c in valores_frec.items()
                 if con_valor and (100 * c / con_valor < RARA_PCT or c < RARA_MIN)]
    if valores_frec is not None and distintos is not None and distintos <= LIMITE_LISTA and rol not in ("magnitud", "fecha", "identificador"):
        valores = [{"valor": a_python(v), "frecuencia": c} for clase, v, c in lista_valores]

    # 5.5 Clase: la manda lo peor que tenga la columna (diccionario-datos §5)
    vacia = filas_con > 0 and acc["nulos"] == filas_con
    if nombre in DECISIONES and not vacia:
        motivos_decision.insert(0, "tiene más de una lectura legítima que las reglas no fijan")
    if vacia:
        clase_campo, motivos = "no_se_puede_saber", ["la columna está vacía en todas las filas que la traen"]
    elif motivos_decision:
        clase_campo, motivos = "decision_de_negocio", motivos_decision + motivos_nsps
    elif motivos_nsps:
        clase_campo, motivos = "no_se_puede_saber", motivos_nsps
    else:
        clase_campo, motivos = "resuelto", []

    if acc["nan"]:
        observaciones.append(f"{acc['nan']} valores NaN leídos como número")
    if len(tipos) > 1:
        observaciones.append("el tipo leído cambia de un trozo a otro: " + ", ".join(f"{k} en {v} filas" for k, v in tipos.items()))
    if acc["con_hora"]:
        observaciones.append(f"{acc['con_hora']} valores con hora distinta de las 00:00")

    return {
        "columna": nombre, "tipo_leido": tipo_leido, "tipos_leidos": tipos, "tipo_declarado": None, "rol": rol,
        "filas_con_columna": filas_con, "filas_sin_columna": filas_tabla - filas_con,
        "nulos": acc["nulos"], "nulos_pct": round(100 * acc["nulos"] / filas_con, 4) if filas_con else None,
        "nulos_por_periodo": periodos(acc["nulos_por_tramo"]),
        "nulos_por_tramo": dict(acc["nulos_por_tramo"]), "filas_por_tramo": dict(acc["filas_por_tramo"]),
        "nulos_por_grupo": dict(acc["nulos_por_grupo"]), "filas_por_grupo": dict(acc["filas_por_grupo"]),
        "vacios": acc["vacios"], "espacios": acc["espacios"], "nan": acc["nan"], "ceros": acc["ceros"],
        "negativos": acc["negativos"], "distintos": distintos,
        "distintos_mas_de": LIMITE_DISTINTOS if acc["modo"] == "excedido" else None,
        "minimo": a_python(minimo), "maximo": a_python(maximo), "valores": valores,
        "primer_trozo": acc["primera_etiqueta"], "ultimo_trozo": acc["ultima_etiqueta"], "trozos_con_columna": acc["trozos"],
        "clase": clase_campo, "motivos_clase": motivos, "significado": significado, "procedencia": procedencia,
        "proteccion": None, "significado_cero": significado_cero, "significado_sin_fila": significado_sin_fila,
        "variantes": variantes, "categorias_raras": raras, "observaciones": observaciones,
    }


def fichas(tabla_nombre, perfil, distintos_exactos=None, orden=None):
    """Fichas de todas las columnas de un perfil, con el número de serie contado aparte y exacto."""
    salida = []
    for nombre in orden or list(perfil.columnas):
        ficha = ficha_de_columna(tabla_nombre, nombre, perfil.columnas[nombre], perfil.filas)
        if distintos_exactos and nombre in distintos_exactos:
            ficha["distintos"], ficha["distintos_mas_de"] = distintos_exactos[nombre], None
        salida.append(ficha)
    return salida


def contar_unicos(seriales_por_tramo):
    """Discos distintos en total y por periodo, a partir de los valores distintos de cada tramo."""
    if not seriales_por_tramo:
        return 0, {}
    # Los números de serie pueden llegar como string o large_string según el fichero: se igualan antes de juntarlos
    arrs_todos = {t: a.cast(pa.string()) for t, a in seriales_por_tramo.items()}
    todos = len(pc.unique(pa.chunked_array(list(arrs_todos.values()), pa.string())))
    por_periodo = {}
    for p in ("construccion", "validacion"):
        arrs = [a for t, a in arrs_todos.items() if periodo_de(t) == p]
        por_periodo[p] = len(pc.unique(pa.chunked_array(arrs, pa.string()))) if arrs else 0
    return todos, por_periodo


# =================================================================================================================
# 6. El esquema de Backblaze, diccionario de la organización
# =================================================================================================================
def leer_esquema(ruta):
    """Lee el esquema con la cadena de codificaciones y devuelve sus líneas tal como vienen."""
    contenido = ruta.read_bytes()
    for codificacion in CODIFICACIONES:
        try:
            texto = contenido.decode("utf-8-sig" if contenido.startswith(b"\xef\xbb\xbf") else codificacion)
            break
        except UnicodeDecodeError:
            continue
    lineas = [l for l in texto.splitlines() if l != ""]
    lectura = {"codificacion": "utf-8-sig" if contenido.startswith(b"\xef\xbb\xbf") else codificacion,
               "separador": None, "decimal": None, "hoja": None, "fila_cabecera": None,
               "fin_de_linea": "CRLF" if b"\r\n" in contenido else "LF",
               "avisos": ["el fichero no tiene cabecera: cada línea es un nombre de columna",
                          f"la primera línea, «{lineas[0]}», no es un nombre de columna"]}
    return lineas, lectura


def contradicciones_con_el_esquema(nombres_esquema, columnas_dataset, ficheros_fotos):
    """Compara el esquema con las columnas de las fotos mensuales y las ventanas de fallo; mandan los datos.

    La comparación no es contra el registro diario entero de Backblaze: una columna del esquema que esos datasets no
    traen puede ser una de las que se quitaron al prepararlos, y eso no es una contradicción del esquema. Sí lo son una línea que no es un nombre y un nombre con una forma que no sigue la de los
    demás.
    """
    salida = []
    primera, nombres = nombres_esquema[0], nombres_esquema[1:]
    salida.append({"tabla": "esquema_backblaze", "columna": primera,
                   "que_dice_el_documento": "lo pone como primera línea, en el sitio de un nombre de columna",
                   "que_dicen_los_datos": "ni las fotos mensuales ni las ventanas de fallo traen esa columna, y no tiene la forma de un nombre de columna: es la fecha de actualización del esquema"})
    for n in nombres:
        if n not in columnas_dataset and not FORMA_NOMBRE.fullmatch(n):
            salida.append({"tabla": "esquema_backblaze", "columna": n, "que_dice_el_documento": "existe la columna",
                           "que_dicen_los_datos": "ni las fotos mensuales ni las ventanas de fallo la traen, y su nombre no sigue la forma smart_N_raw o smart_N_normalized de los demás"})
    for c, info in columnas_dataset.items():
        if c not in nombres and c not in COLUMNAS_DEL_DATASET:
            salida.append({"tabla": "fotos_mensuales y ventanas_fallo", "columna": c, "que_dice_el_documento": "no la nombra",
                           "que_dicen_los_datos": f"la traen las fotos mensuales en {info['ficheros']} ficheros de fotos, desde {info['primero']}"})
    for c in nombres:
        info = columnas_dataset.get(c)
        if info and info["ficheros"] < ficheros_fotos:
            salida.append({"tabla": "fotos_mensuales", "columna": c,
                           "que_dice_el_documento": "existe la columna (esquema actual, del 2.º trimestre de 2024)",
                           "que_dicen_los_datos": f"falta en {ficheros_fotos - info['ficheros']} de los {ficheros_fotos} ficheros de fotos: la traen desde {info['primero']}"})
    return salida


# =================================================================================================================
# 7. Validación (diccionario-datos §9, comprobaciones que se pueden hacer en código)
# =================================================================================================================
ROLES = {"identificador", "clave", "categorica", "codigo", "magnitud", "fecha", "booleana", "texto_libre", "dato_personal"}
CLASES = {"resuelto", "no_se_puede_saber", "decision_de_negocio"}


def validar(dic):
    """Devuelve la lista de errores del diccionario; vacía si pasa todas las comprobaciones."""
    errores = []
    for t in dic["tablas"]:
        con_ficha = [c["columna"] for c in t["campos"]]
        for c in t["columnas_fuente"]:
            if c not in con_ficha:
                errores.append(f"{t['tabla']}: columna {c} sin ficha")
        for c in con_ficha:
            if c not in t["columnas_fuente"]:
                errores.append(f"{t['tabla']}: ficha de una columna que no está en la fuente: {c}")
        for c in t["campos"]:
            if not c.get("significado") or not c.get("procedencia"):
                errores.append(f"{t['tabla']}.{c['columna']}: significado sin procedencia")
            if c["rol"] not in ROLES or c["clase"] not in CLASES:
                errores.append(f"{t['tabla']}.{c['columna']}: rol o clase fuera de la lista")
            if c["rol"] == "dato_personal" and c.get("valores") is not None:
                errores.append(f"{t['tabla']}.{c['columna']}: un dato personal muestra valores")
            if c["rol"] == "magnitud" and (c.get("significado_cero") is None or (t["tabla"] in SIN_FILA and c.get("significado_sin_fila") is None)):
                errores.append(f"{t['tabla']}.{c['columna']}: magnitud sin el significado de su cero o de la fila que falta")
            if c["clase"] == "decision_de_negocio" and not any(p["tabla"] == t["tabla"] and p["columna"] == c["columna"] for p in dic["pendientes"]):
                errores.append(f"{t['tabla']}.{c['columna']}: decisión de negocio que no está en pendientes")
    comparacion = dic.get("comparacion_esquema", {})
    listadas = {c["columna"] for c in dic["contradicciones"]}
    for c in comparacion.get("solo_en_esquema_sin_forma_de_columna", []) + comparacion.get("solo_en_datos", []):
        if c not in listadas:
            errores.append(f"contradicción con el esquema sin listar: {c}")
    return errores


# =================================================================================================================
# 8. JSON y Markdown
# =================================================================================================================
def fmt(n):
    """Número con punto de miles y coma decimal, como se escribe en castellano."""
    if n is None:
        return "—"
    if isinstance(n, bool):
        return "sí" if n else "no"
    if isinstance(n, int):
        return f"{n:,}".replace(",", ".")
    if isinstance(n, float):
        return f"{n:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".").rstrip("0").rstrip(",")
    return str(n)


def celda(texto):
    """Texto apto para una celda de tabla Markdown."""
    return str(texto).replace("|", "\\|").replace("\n", " ")


def escribir_markdown(dic, ruta):
    """Genera el diccionario para la persona a partir del JSON, sin añadir cifras que no estén en él."""
    L = []
    L.append("# Diccionario de datos del origen · caso 68, averías de discos duros\n")
    L.append(f"Generado por `{dic['script']}` el {dic['fecha_ejecucion']} a partir de `config/fuentes/diccionario-datos-origen.json`. "
             "No se edita a mano: se cambia el script y se vuelve a lanzar.\n")
    L.append(f"**Estado:** {dic['resultado']['estado']}. {dic['resultado']['resumen']}\n")
    # 1. Cabecera
    L.append("## 1. Cabecera\n")
    c = dic["cabecera"]
    L.append(f"- Fecha de comprobación: {dic['fecha_ejecucion']}; fecha de los datos: {dic['fecha_datos']}.")
    L.append(f"- Python {c['python']}, pandas {c['pandas']}, pyarrow {c['pyarrow']}.")
    L.append(f"- Fuentes: {fmt(len(dic['entradas']))} ficheros de `data/raw/`, {fmt(c['bytes_data_raw'])} bytes en total.")
    L.append("- Contexto usado: " + "; ".join(c["contexto"]) + ".")
    L.append("- Teoría aplicada: " + c["teoria"] + "\n")
    L.append("**Parámetros**\n")
    for p in dic["parametros"]:
        L.append(f"- {p['nombre']}: {fmt(p['valor'])} ({p['origen']}).")
    L.append("")
    # 2. Lectura
    L.append("## 2. Lectura\n")
    for t in dic["tablas"]:
        lec = t["lectura"]
        # Solo se escribe lo que la lectura decidió; un Parquet trae sus tipos y no tiene codificación ni separador
        decisiones = [f"{k} {lec[c]}" for c, k in (("codificacion", "codificación"), ("fin_de_linea", "fin de línea"),
                                                   ("separador", "separador"), ("decimal", "decimal")) if lec.get(c)]
        L.append(f"**{t['tabla']}** (`{t['fichero']}`): " + (", ".join(decisiones) if decisiones else "Parquet") + ".")
        for a in lec.get("avisos", []):
            L.append(f"- Aviso: {a}")
        L.append("")
    # 3. Resumen
    L.append("## 3. Resumen\n")
    L.append("| tabla | filas | columnas | clave | clave única |")
    L.append("|---|---:|---:|---|---|")
    for t in dic["tablas"]:
        L.append(f"| {t['tabla']} | {fmt(t['filas'])} | {fmt(t['columnas'])} | {', '.join(t['clave'])} | {fmt(t['clave_unica'])} |")
    L.append("")
    # 4. Una sección por tabla
    L.append("## 4. Las tablas\n")
    for t in dic["tablas"]:
        L.append(f"### {t['tabla']}\n")
        L.append(f"- Una fila es {t['que_es_una_fila']}.")
        L.append(f"- Clave: {', '.join(t['clave'])}; única: {fmt(t['clave_unica'])}" +
                 (f" ({fmt(t['filas_clave_repetida'])} filas repetidas)." if t.get("filas_clave_repetida") is not None else "."))
        for clave, texto in (("ficheros", "Ficheros"), ("dias", "Días"), ("discos_distintos", "Discos distintos"),
                             ("ventanas", "Ventanas"), ("suma_discos", "Suma de días de disco"), ("suma_fallos", "Suma de fallos"),
                             ("suma_failure", "Suma de la columna failure"), ("dias_que_faltan", "Días que faltan entre el primero y el último")):
            if t.get(clave) is not None:
                L.append(f"- {texto}: {fmt(t[clave])}.")
        if t.get("columnas_por_fichero"):
            L.append(f"- Columnas por fichero: de {fmt(t['columnas_por_fichero']['min'])} a {fmt(t['columnas_por_fichero']['max'])}.")
        if t.get("dias_por_columnas"):
            L.append("- Días por número de columnas: " + ", ".join(f"{fmt(v)} días con {k}" for k, v in t["dias_por_columnas"].items()) + ".")
        if t.get("filas_por_periodo"):
            L.append("- Filas por periodo: " + ", ".join(f"{k} {fmt(v)}" for k, v in t["filas_por_periodo"].items()) + ".")
        if t.get("filas_por_grupo"):
            L.append("- Filas por grupo según la capacidad de la fila: " + ", ".join(f"{k} {fmt(v)}" for k, v in t["filas_por_grupo"].items()) + ".")
        if t.get("capacidad_no_valida_por_modelo"):
            L.append("- Filas con capacidad no válida, por la capacidad que su modelo trae en el resto de la tabla: " +
                     ", ".join(f"{k} {fmt(v)}" for k, v in t["capacidad_no_valida_por_modelo"].items()) + ".")
        if t.get("filas_datos_con_capacidad_del_modelo") is not None:
            L.append(f"- Filas de discos de datos con la capacidad del modelo (reglas, apartado 3): {fmt(t['filas_datos_con_capacidad_del_modelo'])}" +
                     " (" + ", ".join(f"{k} {fmt(v)}" for k, v in t.get("filas_datos_con_capacidad_del_modelo_por_periodo", {}).items()) + ").")
        for clave, texto in t.get("medidas", {}).items():
            L.append(f"- {clave}: {fmt(texto)}.")
        L.append("")
        L.append("| columna | tipo leído | rol | filas con la columna | nulos | % nulos | distintos | mínimo | máximo | clase | significado | procedencia |")
        L.append("|---|---|---|---:|---:|---:|---:|---|---|---|---|---|")
        for f in t["campos"]:
            dist = fmt(f["distintos"]) if f["distintos"] is not None else f"más de {fmt(f['distintos_mas_de'])}"
            L.append(f"| {celda(f['columna'])} | {celda(f['tipo_leido'])} | {f['rol']} | {fmt(f['filas_con_columna'])} | {fmt(f['nulos'])} | "
                     f"{fmt(f['nulos_pct'])} | {dist} | {celda(fmt(f['minimo']))} | {celda(fmt(f['maximo']))} | {f['clase']} | "
                     f"{celda(f['significado'])} | {f['procedencia']} |")
        L.append("")
        con_valores = [f for f in t["campos"] if f["valores"]]
        if con_valores:
            L.append("**Valores de las columnas con 15 o menos**\n")
            for f in con_valores:
                L.append(f"- {f['columna']}: " + ", ".join(f"«{celda(v['valor'])}» {fmt(v['frecuencia'])}" for v in f["valores"]) + ".")
            L.append("")
        detalles = [f for f in t["campos"] if f["observaciones"] or f["motivos_clase"] or f["variantes"] or
                    f["vacios"] or f["espacios"] or f["negativos"]]
        if detalles:
            L.append("**Observaciones medidas y motivo de la clase**\n")
            for f in detalles:
                partes = list(f["motivos_clase"]) + list(f["observaciones"])
                if f["variantes"]:
                    partes.append("variantes: " + "; ".join(" / ".join(f"«{v}»" for v in vs) for vs in f["variantes"]))
                for clave, texto in (("vacios", "vacíos o solo espacios"), ("espacios", "con espacios al principio o al final"), ("negativos", "negativos")):
                    if f[clave]:
                        partes.append(f"{fmt(f[clave])} {texto}")
                L.append(f"- {f['columna']} ({f['clase']}): " + "; ".join(partes) + ".")
            L.append("")
        magn = [f for f in t["campos"] if f["rol"] == "magnitud"]
        if magn:
            L.append("**El cero y la fila que falta en las magnitudes**\n")
            vistos = {}
            for f in magn:
                clave = (f["significado_cero"]["texto"], (f["significado_sin_fila"] or {}).get("texto"))
                vistos.setdefault(clave, []).append(f)
            for (cero, sin_fila), fs in vistos.items():
                nombres = ", ".join(x["columna"] for x in fs) if len(fs) <= 6 else f"{len(fs)} columnas ({fs[0]['columna']}, …, {fs[-1]['columna']})"
                L.append(f"- {nombres}: el cero, {cero} ({fs[0]['significado_cero']['procedencia']})" +
                         (f"; la fila que falta, {sin_fila} ({fs[0]['significado_sin_fila']['procedencia']})." if sin_fila else "."))
            L.append("")
    # 5 a 11
    L.append("## 5. Contradicciones con el diccionario de la organización\n")
    L.append(f"El diccionario de la organización es `{dic['diccionario_organizacion']}`. Mandan los datos; ninguna se corrige.\n")
    L.append("| tabla | columna | qué dice el documento | qué dicen los datos |")
    L.append("|---|---|---|---|")
    for x in dic["contradicciones"]:
        L.append(f"| {x['tabla']} | {celda(x['columna'])} | {celda(x['que_dice_el_documento'])} | {celda(x['que_dicen_los_datos'])} |")
    L.append("")
    L.append("## 6. Columnas que no llegan al análisis\n")
    L.append("| tabla | columna | motivo |")
    L.append("|---|---|---|")
    for x in dic["columnas_que_no_llegan"]:
        L.append(f"| {x['tabla']} | {celda(x['columna'])} | {celda(x['motivo'])} |")
    L.append("")
    L.append("## 7. Filtros de negocio\n")
    for x in dic["filtros_de_negocio"]:
        L.append(f"- {x['regla']}: {fmt(x['filas_afectadas'])} filas.")
    L.append("")
    L.append("## 8. Decisiones de negocio pendientes\n")
    for p in dic["pendientes"]:
        L.append(f"- **{p['id']}** · {p['tabla']}.{p['columna']}: {p['pregunta']} Lecturas: " + "; ".join(p["opciones"]) + ".")
    L.append("")
    L.append("## 9. Lo que no se puede saber\n")
    for x in dic["no_se_puede_saber"]:
        L.append(f"- {x['que']} ({x['procedencia']}).")
    L.append("")
    L.append("## 10. Datos personales\n")
    for x in dic["datos_personales"]:
        L.append(f"- {x}")
    L.append("")
    L.append("## 11. Límites\n")
    for x in dic["limites"]:
        L.append(f"- {x}")
    L.append("")
    ruta.write_text("\n".join(L), encoding="utf-8")


# =================================================================================================================
# 9. Principal
# =================================================================================================================
def escribir_json(dic, ruta):
    """Escribe el JSON sin NaN, que no es JSON válido."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(dic, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")


def base_comun(raiz):
    """Bloque común de la cadena, sin el resultado todavía."""
    return {"metodo": METODO, "version_metodo": VERSION_METODO, "script": SCRIPT, "fecha_datos": FECHA_DATOS,
            "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"), "entradas": [],
            "resultado": None, "pendientes": []}


def main(raiz=CASO):
    """Describe los cuatro datasets y el esquema y escribe el diccionario; devuelve el diccionario escrito."""
    inicio = time.time()
    raw = raiz / "data" / "raw"
    pod = raw / "podado"
    fuentes = raiz / "config" / "fuentes"
    ruta_json, ruta_md = fuentes / "diccionario-datos-origen.json", fuentes / "diccionario-datos-origen.md"
    dic = base_comun(raiz)
    try:
        # 9.1 Al empezar: protección de datos (resultado.md, «Al empezar»)
        ruta_proteccion = fuentes / "proteccion-datos.json"
        proteccion = json.loads(ruta_proteccion.read_text(encoding="utf-8")) if ruta_proteccion.exists() else None
        if proteccion and proteccion.get("resultado", {}).get("estado") in ("PARADO", "ERROR"):
            raise RuntimeError("proteccion-datos.json está PARADO o en ERROR: los datos no están protegidos")

        # 9.2 Huella de cada fichero de data/raw/
        entradas = {}
        for p in sorted(raw.rglob("*")):
            if p.is_file():
                entradas[p] = {"ruta": p.relative_to(raiz).as_posix(), "sha256": sha256(p), "filas": None, "columnas": None}
        bytes_raw = sum(p.stat().st_size for p in entradas)

        # 9.3 Las fotos mensuales y las ventanas de fallo, fichero a fichero
        ruta_esq = raw / "Drive_Stats_Schema_Current.csv"
        lineas, lectura_esq = leer_esquema(ruta_esq)
        orden_esquema = lineas[1:]
        tablas_pod, perfiles_pod = [], {}
        for nombre, col_periodo in (("fotos_mensuales", "fecha"), ("ventanas_fallo", "dia_fallo")):
            ficheros = sorted((pod / nombre).glob("*.parquet"))
            if not ficheros:
                raise FileNotFoundError(f"no hay ningún Parquet en data/raw/podado/{nombre}/")
            perfil, por_fichero, seriales = describir_parquets(ficheros, col_periodo)
            perfiles_pod[nombre] = perfil
            discos, discos_periodo = contar_unicos(seriales)
            for f, info in zip(ficheros, por_fichero):
                entradas[f]["filas"], entradas[f]["columnas"] = info["filas"], info["columnas"]
            # Primero las columnas que se añadieron al preparar los datasets y después las de Backblaze, en el orden del esquema
            orden = ([c for c in perfil.columnas if c in COLUMNAS_DEL_DATASET] + [c for c in orden_esquema if c in perfil.columnas]
                     + [c for c in perfil.columnas if c not in COLUMNAS_DEL_DATASET and c not in orden_esquema])
            t = {"tabla": nombre, "fichero": f"data/raw/podado/{nombre}/*.parquet",
                 "lectura": {"codificacion": None, "separador": None, "decimal": None, "hoja": None, "fila_cabecera": None,
                             "avisos": ["Parquet con los tipos declarados en el propio fichero; se lee fichero a fichero"]},
                 "que_es_una_fila": TABLAS[nombre][0], "ficheros": len(ficheros), "filas": perfil.filas, "columnas": len(orden),
                 "columnas_por_fichero": {"min": min(i["columnas"] for i in por_fichero), "max": max(i["columnas"] for i in por_fichero)},
                 "clave": TABLAS[nombre][1], "filas_por_periodo": periodos(perfil.filas_por_tramo),
                 "ficheros_por_periodo": periodos(Counter(max(i["tramos"], key=i["tramos"].get) for i in por_fichero)),
                 "discos_distintos": discos, "discos_distintos_por_periodo": discos_periodo,
                 "columnas_fuente": orden, **grupos_de_la_tabla(perfil)}
            if nombre == "fotos_mensuales":
                t["filas_clave_repetida"] = sum(i["seriales_repetidos"] for i in por_fichero)
                t["medidas"] = {"ficheros con más de una fecha": sum(1 for i in por_fichero if i["fechas_distintas"] != 1),
                                "filas anteriores al 01/07/2023, sin sitio por las reglas, apartado 4": perfil.filas_por_tramo.get("construccion_antes_sitio", 0)}
            else:
                clave_v = pd.concat([pd.read_parquet(f, columns=["serial_number", "fecha", "dia_fallo", "model", "capacity_bytes"]) for f in ficheros],
                                    ignore_index=True)
                t["filas_clave_repetida"] = int(clave_v.duplicated(["serial_number", "fecha"]).sum())
                tam = clave_v.groupby(["serial_number", "dia_fallo"]).size()
                distancia = (clave_v["dia_fallo"] - clave_v["fecha"]).dt.days
                t["ventanas"] = int(len(tam))
                t["medidas"] = {"ventanas con menos de 31 filas": int((tam < 31).sum()),
                                "filas fuera de los 30 días anteriores al fallo": int((distancia.lt(0) | distancia.gt(30)).sum()),
                                "ventanas sin la fila del día del fallo": int(len(tam) - clave_v.loc[distancia.eq(0)].groupby(["serial_number", "dia_fallo"]).ngroups)}
                dia_del_fallo = clave_v.loc[distancia.eq(0), ["serial_number", "dia_fallo", "model", "capacity_bytes"]]
            t["clave_unica"] = t["filas_clave_repetida"] == 0
            t["campos"] = fichas(nombre, perfil, {"serial_number": discos}, orden)
            tablas_pod.append(t)

        # 9.4 El recuento diario
        ruta_rec = pod / "recuento_diario.parquet"
        perfil_rec, _, _ = describir_parquets([ruta_rec], "fecha")
        rec = pd.read_parquet(ruta_rec)
        entradas[ruta_rec]["filas"], entradas[ruta_rec]["columnas"] = len(rec), rec.shape[1]
        columnas_rec = list(rec.columns)
        rec["tramo"] = rec["fecha"].dt.date.map(tramo_de)
        dias_rec = rec["fecha"].dt.normalize().drop_duplicates()
        calendario = pd.date_range(dias_rec.min(), dias_rec.max(), freq="D")
        clave_rec = TABLAS["recuento_diario"][1]
        repetidas_rec = int(rec.duplicated(clave_rec).sum())
        sin_dato = rec["datacenter"].eq("sin dato")
        t_rec = {"tabla": "recuento_diario", "fichero": "data/raw/podado/recuento_diario.parquet",
                 "lectura": {"codificacion": None, "separador": None, "decimal": None, "hoja": None, "fila_cabecera": None,
                             "avisos": ["Parquet con los tipos declarados en el propio fichero"]},
                 "que_es_una_fila": TABLAS["recuento_diario"][0], "ficheros": 1, "filas": len(rec), "columnas": len(columnas_rec),
                 "clave": clave_rec, "filas_clave_repetida": repetidas_rec, "clave_unica": repetidas_rec == 0,
                 "dias": int(len(dias_rec)), "primer_dia": dias_rec.min().date().isoformat(), "ultimo_dia": dias_rec.max().date().isoformat(),
                 "dias_que_faltan": int(len(calendario) - len(dias_rec)),
                 "filas_por_periodo": periodos(Counter(rec["tramo"].value_counts().to_dict())),
                 "suma_discos": int(rec["discos"].sum()), "suma_fallos": int(rec["fallos"].sum()),
                 "suma_discos_por_periodo": periodos(Counter(rec.groupby("tramo")["discos"].sum().to_dict())),
                 "suma_fallos_por_periodo": periodos(Counter(rec.groupby("tramo")["fallos"].sum().to_dict())),
                 "medidas": {"filas con centro «sin dato»": int(sin_dato.sum()),
                             "filas con centro «sin dato» desde el 01/07/2023": int((sin_dato & rec["fecha"].dt.date.ge(INICIO_SITIO)).sum()),
                             "días de disco con centro «sin dato»": int(rec.loc[sin_dato, "discos"].sum()),
                             "filas con capacidad no válida (-1 o 0,1 TB)": int(rec["capacity_bytes"].lt(CAPACIDAD_MIN_VALIDA).sum()),
                             "claves repetidas si se quita la capacidad": int(rec.duplicated(["fecha", "model", "datacenter"]).sum())},
                 "columnas_fuente": columnas_rec, **grupos_de_la_tabla(perfil_rec)}
        dd = Counter()
        for (_, _, cap), d in perfil_rec.pares_discos.items():
            dd[grupo_de_capacidad(cap)] += int(d)
        t_rec["dias_de_disco_por_grupo"] = dict(dd)
        t_rec["campos"] = fichas("recuento_diario", perfil_rec, None, columnas_rec)
        del rec

        # 9.5 La lista de fallos; el grupo de cada fallo sale de la fila del día del fallo en su ventana, sin guardar el cruce
        ruta_fal = pod / "fallos.parquet"
        perfil_fal, _, _ = describir_parquets([ruta_fal], "dia_fallo")
        fal = pd.read_parquet(ruta_fal)
        entradas[ruta_fal]["filas"], entradas[ruta_fal]["columnas"] = len(fal), fal.shape[1]
        columnas_fal = list(fal.columns)
        fal["periodo"] = fal["dia_fallo"].dt.date.map(tramo_de).map(periodo_de)
        cruce = fal.merge(dia_del_fallo, on=["serial_number", "dia_fallo"], how="left", validate="one_to_one")
        validas_v = {}
        for m, c in dia_del_fallo[["model", "capacity_bytes"]].drop_duplicates().itertuples(index=False):
            if grupo_de_capacidad(c) in ("datos", "arranque"):
                validas_v.setdefault(m, set()).add(c)
        cruce["grupo_fila"] = cruce["capacity_bytes"].map(lambda c: "sin_fila_del_dia_del_fallo" if pd.isna(c) else grupo_de_capacidad(c))
        cruce["grupo_modelo"] = [g if g != "capacidad_no_valida" else
                                 (grupo_de_capacidad(next(iter(validas_v[m]))) if len(validas_v.get(m, ())) == 1 else "sin_capacidad_unica")
                                 for g, m in zip(cruce["grupo_fila"], cruce["model"])]
        veces = fal.groupby("serial_number").size()
        repetidas_fal = int(fal.duplicated(["serial_number", "dia_fallo"]).sum())
        datos_periodo = {p: int(((cruce["grupo_modelo"] == "datos") & (cruce["periodo"] == p)).sum()) for p in ("construccion", "validacion")}
        t_fal = {"tabla": "fallos", "fichero": "data/raw/podado/fallos.parquet",
                 "lectura": {"codificacion": None, "separador": None, "decimal": None, "hoja": None, "fila_cabecera": None,
                             "avisos": ["Parquet con los tipos declarados en el propio fichero",
                                        "la tabla no trae capacidad: el grupo de cada fallo se toma de la fila del día del fallo en ventanas_fallo, sin guardar ningún cruce"]},
                 "que_es_una_fila": TABLAS["fallos"][0], "ficheros": 1, "filas": len(fal), "columnas": len(columnas_fal),
                 "clave": TABLAS["fallos"][1], "filas_clave_repetida": repetidas_fal, "clave_unica": repetidas_fal == 0,
                 "discos_distintos": int(fal["serial_number"].nunique()), "discos_con_mas_de_un_fallo": int((veces > 1).sum()),
                 "filas_por_periodo": periodos(Counter(fal["dia_fallo"].dt.date.map(tramo_de).value_counts().to_dict())),
                 "filas_por_grupo": {k: int(v) for k, v in cruce["grupo_fila"].value_counts().items()},
                 "capacidad_no_valida_por_modelo": {k: int(v) for k, v in cruce.loc[cruce["grupo_fila"] == "capacidad_no_valida", "grupo_modelo"].value_counts().items()},
                 "filas_datos_con_capacidad_del_modelo": sum(datos_periodo.values()),
                 "filas_datos_con_capacidad_del_modelo_por_periodo": datos_periodo,
                 "arranque_con_capacidad_del_modelo_por_periodo": {p: int(((cruce["grupo_modelo"] == "arranque") & (cruce["periodo"] == p)).sum())
                                                                   for p in ("construccion", "validacion")},
                 "columnas_fuente": columnas_fal}
        t_fal["campos"] = fichas("fallos", perfil_fal, {"serial_number": t_fal["discos_distintos"]}, columnas_fal)

        # 9.6 El esquema de Backblaze, descrito como tabla y comparado con las columnas de las fotos y las ventanas
        entradas[ruta_esq]["filas"], entradas[ruta_esq]["columnas"] = len(lineas), 1
        perfil_esq = Perfil()
        perfil_esq.anadir(pa.table({"nombre_en_el_esquema": pa.array(lineas, pa.string())}), "fuera_de_los_datos", "esquema", aparte=())
        repetidos_esq = len(lineas) - len(set(lineas))
        t_esq = {"tabla": "esquema_backblaze", "fichero": "data/raw/Drive_Stats_Schema_Current.csv", "lectura": lectura_esq,
                 "que_es_una_fila": TABLAS["esquema_backblaze"][0], "filas": len(lineas), "columnas": 1,
                 "clave": TABLAS["esquema_backblaze"][1], "filas_clave_repetida": repetidos_esq, "clave_unica": repetidos_esq == 0,
                 "primera_linea": lineas[0], "nombres_de_columna": len(lineas) - 1, "columnas_fuente": ["nombre_en_el_esquema"]}
        t_esq["campos"] = fichas("esquema_backblaze", perfil_esq, None)
        fotos_cols = perfiles_pod["fotos_mensuales"].columnas
        columnas_dataset = {}
        for nombre_t in ("fotos_mensuales", "ventanas_fallo"):
            for c, acc in perfiles_pod[nombre_t].columnas.items():
                columnas_dataset.setdefault(c, {"ficheros": fotos_cols[c]["trozos"] if c in fotos_cols else 0,
                                                "primero": fotos_cols[c]["primera_etiqueta"] if c in fotos_cols else acc["primera_etiqueta"]})
        ficheros_fotos = tablas_pod[0]["ficheros"]
        contradicciones = contradicciones_con_el_esquema(lineas, columnas_dataset, ficheros_fotos)

        # 9.7 Columnas que no llegan, filtros de negocio y pendientes
        tablas = tablas_pod + [t_rec, t_fal, t_esq]
        listadas = {x["columna"] for x in contradicciones}
        no_llegan = [{"tabla": "fotos_mensuales y ventanas_fallo", "columna": n,
                      "motivo": "la nombra el esquema y ni las fotos mensuales ni las ventanas de fallo la traen: se quitó al preparar los cuatro datasets, por vacía o constante (responsable, 17/11/2026); no se puede comprobar con ellos"}
                     for n in orden_esquema if n not in columnas_dataset and n not in listadas]
        for t in tablas_pod + [t_rec]:
            for c in t["columnas_fuente"]:
                if c in COLUMNAS_DEL_DATASET:
                    no_llegan.append({"tabla": t["tabla"], "columna": c, "motivo": "no viene de Backblaze: se añadió al preparar los cuatro datasets (responsable, 17/11/2026)"})
        no_llegan.append({"tabla": "recuento_diario", "columna": "(todas las del esquema salvo model, capacity_bytes y datacenter)",
                          "motivo": "el recuento agrega por día, modelo, capacidad y centro (responsable, 17/11/2026)"})
        filtros = []
        for t in tablas[:-1]:
            arr = t.get("capacidad_no_valida_por_modelo", {}).get("arranque", 0) + t.get("filas_por_grupo", {}).get("arranque", 0)
            filtros.append({"regla": f"discos de arranque fuera de tasas, coste y modelo (reglas, apartado 3), en {t['tabla']}, contando las capacidades no válidas por su modelo",
                            "filas_afectadas": arr})
        for t in tablas[:-1]:
            filtros.append({"regla": f"validación del 01/07/2024 al 30/06/2025, que no se mira contra el fallo hasta medir el modelo (reglas, apartado 7), en {t['tabla']}",
                            "filas_afectadas": t["filas_por_periodo"].get("validacion", 0)})
        for t in tablas[:-1]:
            filtros.append({"regla": f"reserva, después del 30/06/2025, fuera del caso (reglas, apartado 5), en {t['tabla']}",
                            "filas_afectadas": t["filas_por_periodo"].get("fuera_de_los_datos", 0)})
        filtros.append({"regla": "el sitio solo consta desde el 01/07/2023 y no se rellena hacia atrás (reglas, apartado 4): filas de fotos anteriores",
                        "filas_afectadas": perfiles_pod["fotos_mensuales"].filas_por_tramo.get("construccion_antes_sitio", 0)})
        pendientes = []
        for t in tablas:
            for f in t["campos"]:
                if f["clase"] == "decision_de_negocio":
                    pregunta, opciones = DECISIONES.get(f["columna"], (
                        "¿Cómo se lee esta columna? " + "; ".join(f["motivos_clase"]),
                        ["los valores que difieren solo en mayúsculas o espacios son el mismo", "son valores distintos"]))
                    pendientes.append({"id": f"P-{len(pendientes) + 1:02d}", "tabla": t["tabla"], "columna": f["columna"],
                                       "pregunta": pregunta, "opciones": opciones, "motivo": "; ".join(f["motivos_clase"])})

        # 9.8 El diccionario entero, validado antes de escribirlo
        resumen = (f"Los cuatro datasets (fotos mensuales, ventanas de fallo, recuento diario y lista de fallos) y el esquema descritos enteros, sin muestra: {fmt(sum(t['filas'] for t in tablas_pod))} filas de fotos y ventanas, "
                   f"{fmt(t_rec['filas'])} del recuento y {fmt(t_fal['filas'])} fallos. {len(pendientes)} columnas quedan como decisión de negocio "
                   f"y hay {len(contradicciones)} contradicciones con el esquema. "
                   + ("No existe proteccion-datos.json: no hubo paso de protección (paso 2a saltado el 17/11/2026 con el sí del responsable del caso, porque no hay datos personales)."
                      if proteccion is None else "Los datos pasaron por la protección de proteccion-datos.json."))
        dic.update({
            "entradas": list(entradas.values()),
            "resultado": {"estado": "AVISO" if pendientes else "OK", "riesgo": "medio", "resumen": resumen,
                          "artefactos": [ruta_json.relative_to(raiz).as_posix(), ruta_md.relative_to(raiz).as_posix()],
                          "siguiente": "calidad-datos: el plan de calidad espera el visto bueno de la persona responsable antes del script"},
            "pendientes": pendientes,
            "cabecera": {"python": platform.python_version(), "pandas": pd.__version__, "pyarrow": pa.__version__,
                         "bytes_data_raw": bytes_raw,
                         "contexto": ["las instrucciones del caso", "negocio/reglas-negocio.md", "negocio/01_ficha_del_caso.md",
                                      "negocio/cuestiones-pendientes.md", "fuentes/ficha_de_los_datos.md (nombres de los contadores, sin confirmar)",
                                      "fuentes/proteccion-datos.md", "petición del responsable del 17/11/2026"],
                         "teoria": ("manual 6.5 y 6.6 para la lectura (se mira la fuente en bruto y se declara cada decisión); "
                                    "3.3 para el rol (un código numérico no es una magnitud: las notas normalizadas y los identificadores de sitio van como código); "
                                    "7.3 para los códigos de ausencia (-1 de capacidad y «sin dato» del centro se cuentan, no se convierten).")},
            "parametros": [
                {"nombre": "orden de codificaciones", "valor": ", ".join(CODIFICACIONES), "origen": "por defecto; solo lo usa el esquema, que es texto"},
                {"nombre": "filas donde buscar la cabecera de un Excel", "valor": "no aplica: no hay Excel", "origen": "por defecto"},
                {"nombre": "lista completa de valores de un texto", "valor": LIMITE_LISTA, "origen": "por defecto"},
                {"nombre": "categoría rara", "valor": f"menos del {fmt(RARA_PCT)} % de las filas o menos de {RARA_MIN} apariciones", "origen": "por defecto"},
                {"nombre": "apertura de bases de datos", "valor": "no aplica: no hay bases de datos", "origen": "por defecto"},
                {"nombre": "ficheros de un ZIP que no se abren", "valor": "no aplica: el caso no tiene ZIP", "origen": "por defecto"},
                {"nombre": "valores distintos guardados con su frecuencia", "valor": LIMITE_FRECUENCIAS, "origen": "este script, por memoria"},
                {"nombre": "valores distintos contados exactos", "valor": LIMITE_DISTINTOS, "origen": "este script, por memoria; el número de serie se cuenta exacto aparte"},
                {"nombre": "cortes de capacidad", "valor": f"no válida por debajo de {fmt(int(CAPACIDAD_MIN_VALIDA))} bytes (0,2 TB); arranque por debajo de {fmt(int(CAPACIDAD_MAX_ARRANQUE))} (3 TB); datos desde ahí",
                 "origen": "reglas de negocio §3"},
            ],
            "diccionario_organizacion": ruta_esq.relative_to(raiz).as_posix(),
            "tablas": tablas,
            "comparacion_esquema": {"contra": "las columnas de fotos_mensuales y ventanas_fallo",
                                    "solo_en_esquema_sin_forma_de_columna": [n for n in lineas if n not in columnas_dataset and not FORMA_NOMBRE.fullmatch(n)],
                                    "solo_en_esquema_quitadas": [n for n in orden_esquema if n not in columnas_dataset and FORMA_NOMBRE.fullmatch(n)],
                                    "solo_en_datos": [c for c in columnas_dataset if c not in lineas and c not in COLUMNAS_DEL_DATASET]},
            "contradicciones": contradicciones,
            "columnas_que_no_llegan": no_llegan,
            "filtros_de_negocio": filtros,
            "no_se_puede_saber": [{"que": q, "procedencia": p} for q, p in NO_SE_PUEDE_SABER] +
                                 [{"que": f"{t['tabla']}.{f['columna']}: " + "; ".join(f["motivos_clase"]), "procedencia": "medido"}
                                  for t in tablas for f in t["campos"] if f["clase"] == "no_se_puede_saber"],
            "datos_personales": [
                "No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección." if proteccion is None
                else "Los datos pasaron por la protección de proteccion-datos.json.",
                "El paso 2a se saltó el 17/11/2026 con el sí del responsable del caso porque no hay datos de personas (reglas, apartado 9; proteccion-datos.md).",
                "Ninguna columna lleva rol dato_personal. El número de serie identifica un disco, no a una persona: su rol es identificador.",
                "Este método no usa ni deja columnas de datos personales.",
            ],
            "limites": [
                "El diccionario describe una tabla cada vez; las claves huérfanas o repetidas entre tablas se ven primero en el apartado «Cruces entre tablas» de calidad-datos y se controlan al cruzarlas con integracion-datos. La única excepción es el grupo de cada fallo, que la lista no trae y se toma de la fila del día del fallo en su ventana, sin guardar el cruce.",
                "La detección de datos personales mira columnas enteras; un nombre dentro de texto libre no lo caza.",
                "Las descripciones «sin confirmar» son deducciones y no se usan como regla: los nombres de los contadores SMART salen de la ficha de los datos, que los tomó de la Wikipedia.",
                "El esquema se compara con las columnas de las fotos mensuales y las ventanas de fallo, no con el registro diario de Backblaze entero: una columna del esquema que esos datasets no traen se quitó al preparar los cuatro datasets, y desde aquí no se puede comprobar si estaba vacía o era constante.",
                "El día a día de los discos que no fallan no está en los cuatro datasets: de cada disco hay una foto al mes, y día a día solo los 30 días anteriores a cada fallo.",
                f"Los valores distintos se cuentan exactos hasta {fmt(LIMITE_DISTINTOS)}; por encima, el diccionario dice «más de {fmt(LIMITE_DISTINTOS)}». El número de serie se cuenta exacto aparte. Ninguna cifra sale de una muestra: se leen todas las filas.",
                "Los números se comparan como decimales de 64 bits para contar distintos; un entero por encima de 2^53 podría juntarse con su vecino al contarlo.",
                "Los grupos de discos de datos y de arranque se dan por la capacidad de cada fila y, aparte, las filas con capacidad no válida repartidas por la capacidad que su modelo trae en el resto de la tabla (reglas, apartado 3). No se corrige ninguna fila.",
            ],
        })
        errores = validar(dic)
        if errores:
            raise RuntimeError("la validación del diccionario falla: " + " | ".join(errores[:20]))
        escribir_json(dic, ruta_json)
        escribir_markdown(json.loads(ruta_json.read_text(encoding="utf-8")), ruta_md)
        print(f"diccionario escrito: {ruta_json.relative_to(raiz).as_posix()} y .md; estado {dic['resultado']['estado']}; "
              f"{time.time() - inicio:.0f} s", flush=True)
        return dic
    except Exception as error:
        # 9.9 Si algo falla, el JSON se escribe igual con su estado (resultado.md, regla 5)
        dic["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(error).__name__}: {error}",
                            "artefactos": [ruta_json.relative_to(raiz).as_posix()], "siguiente": "arreglar el fallo y volver a lanzar el script"}
        dic.pop("tablas", None)
        escribir_json(dic, ruta_json)
        raise


if __name__ == "__main__":
    print("intérprete:", sys.executable, flush=True)
    main(CASO)
