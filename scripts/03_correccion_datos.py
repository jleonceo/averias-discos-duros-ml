"""Corrección de los datos del caso 68, averías de discos duros en Backblaze.

Corrige, sin cruzar ni transformar, los cuatro datasets de data/raw/podado/ (fotos mensuales, ventanas de fallo,
recuento diario y lista de fallos) y deja un fichero corregido por dataset en data/processed/. Solo aplica las
correcciones con criterio decidido en la petición 07 (peticiones/07_correccion.md):

1. tipos: el centro como texto, la ranura como entero con vacíos y el texto de la fecha (date) como fecha;
2. el nombre del modelo con dos espacios tras «WDC», con el mapeo cerrado de D1;
3. la capacidad -1 o 0,1 TB, con la única capacidad válida del modelo (reglas, apartado 3), y en el recuento la suma de las
   filas que quedan con la misma clave;
4. fuera de las ventanas las filas cuya fecha no es la de su texto (C-17, P-01);
5. las 66 fotos y las 22 ventanas, cada una en un solo Parquet con todas las columnas.

Lee informes/calidad-datos.json (tiene que existir, no estar PARADO ni en ERROR y describir estos mismos ficheros) y
config/modelo/decisiones-correccion.json, donde viven el mapeo, la regla de la capacidad y los motivos de lo
que no se toca. No rellena ningún vacío: el caso entrena un modelo.

Escribe data/processed/*_corregido.parquet, informes/correccion-datos.json y, a partir de él, informes/correccion-datos.md,
y añade al registro de transformaciones las fichas de las reglas que todavía no tiene.

Uso: python -W error scripts/03_correccion_datos.py [--raiz CARPETA_DEL_CASO]
Método: correccion-datos (versión 06/11/2026, una nota del método), con programacion-del-caso.
"""

# =================================================================================================================
# 1. Configuración
# =================================================================================================================
import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

# -----------------------------------------------------------------------------------------------------------------
# 1.1 Rutas y versión
# -----------------------------------------------------------------------------------------------------------------
CASO = Path(__file__).resolve().parents[1]
METODO = "correccion-datos"
VERSION_METODO = "06/11/2026"
SCRIPT = "scripts/03_correccion_datos.py"
PETICION = "peticiones/07_correccion.md"

# -----------------------------------------------------------------------------------------------------------------
# 1.2 Fechas y cortes de las reglas de negocio
# -----------------------------------------------------------------------------------------------------------------
# Reglas, apartado 5: fecha de referencia de los datos de trabajo
FECHA_DATOS = "2025-06-30"
# Reglas, apartado 3: los discos de datos son los de 4 TB o más; los de arranque, de 0,2 a 2 TB. El corte cae en un hueco.
CAPACIDAD_MAX_ARRANQUE = 3e12
# Reglas, apartado 7 y petición 07: el caso entrena un modelo, así que aquí no se rellena ningún vacío
VA_A_MODELO = True

# -----------------------------------------------------------------------------------------------------------------
# 1.3 Tablas, columnas y orden de la salida
# -----------------------------------------------------------------------------------------------------------------
TABLAS = ["fotos_mensuales", "ventanas_fallo", "recuento_diario", "fallos"]
NOMBRE_TABLA = {"fotos_mensuales": "fotos mensuales", "ventanas_fallo": "ventanas de fallo",
                "recuento_diario": "recuento diario", "fallos": "lista de fallos"}
SALIDA = {t: f"data/processed/{t}_corregido.parquet" for t in TABLAS}
# Las columnas que no son contadores van delante, en este orden; los contadores después, por número y nota antes que bruto
COLUMNAS_DELANTE = ["fecha", "date", "dia_fallo", "serial_number", "model", "capacity_bytes", "failure", "datacenter",
                    "cluster_id", "vault_id", "pod_id", "pod_slot_num"]
PATRON_CONTADOR = re.compile(r"^smart_(\d+)_(normalized|raw)$")
CONTADORES_AVERIA = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]

# -----------------------------------------------------------------------------------------------------------------
# 1.4 Parámetros de el método (parametros.md)
# -----------------------------------------------------------------------------------------------------------------
PARAMETROS = [
    {"nombre": "forma de los nombres de columna", "valor": "minúsculas, sin tildes ni eñes, guion bajo",
     "origen": "por defecto; los nombres ya llegan así y no se cambia ninguno"},
    {"nombre": "etiqueta del vacío en una categórica", "valor": "sin dato",
     "origen": "por defecto; coincide con la del centro que no consta en el recuento (reglas, apartado 4 y §5)"},
    {"nombre": "marca de lo imputado", "valor": "<campo>_faltante, 0 y 1", "origen": "por defecto; no se usa: no se imputa nada"},
    {"nombre": "si los datos van a un modelo", "valor": "no se imputa aquí", "origen": "por defecto; reglas, apartado 7, el caso entrena un modelo"},
    {"nombre": "formato de la tabla corregida", "valor": "Parquet", "origen": "por defecto"},
]

TEORIA = ("Manual 8.1 antes de corregir (cada corrección responde a un problema diagnosticado, con su regla y su recuento); "
          "8.3 para los tipos (la fecha del texto con el patrón explícito %Y-%m-%d, contando los vacíos que crea); "
          "8.7 para el nombre del modelo (mapeo cerrado con replace, que deja como está lo que no encuentra); "
          "8.6 para el recuento (se suman las filas con la misma clave porque la granularidad documentada da una fila por "
          "clave); 8.4 y 33.4 para las filas quitadas de las ventanas (se cuentan, y la regla se puede aplicar siempre); "
          "8.10 para el cierre (filas, vacíos y sumas antes y después). Los apartados 4.5 y 4.6 no se aplican: las filas "
          "quitadas repiten el día siguiente y no tienen datos propios, así que no cambian ninguna comparación entre grupos.")


class ParadaDeRegla(Exception):
    """El script para a propósito por una de sus reglas: el estado es PARADO."""


class ErrorDeRegla(Exception):
    """Una regla no se puede aplicar o una comprobación no pasa: el estado es ERROR."""


# =================================================================================================================
# 2. Utilidades
# =================================================================================================================
def sha256(ruta):
    """Huella SHA-256 de un fichero, leída por bloques."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


def huellas(carpeta):
    """Huella de cada fichero de una carpeta, por su ruta relativa."""
    return {p.relative_to(carpeta).as_posix(): sha256(p) for p in sorted(carpeta.rglob("*")) if p.is_file()}


def a_json(valor):
    """Pasa a tipos que JSON acepta: enteros, decimales sin NaN, listas y diccionarios."""
    if isinstance(valor, dict):
        return {str(k): a_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [a_json(v) for v in valor]
    if isinstance(valor, (np.bool_, bool)):
        return bool(valor)
    if isinstance(valor, np.integer):
        return int(valor)
    if isinstance(valor, (np.floating, float)):
        v = float(valor)
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return int(v) if v.is_integer() and abs(v) < 2**53 else round(v, 6)
    if isinstance(valor, (dt.datetime, dt.date)):
        return valor.isoformat()
    return valor


def fmt(n):
    """Número con punto de miles, como se escribe en español."""
    if n is None:
        return "sin dato"
    if isinstance(n, float) and not n.is_integer():
        return f"{n:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{int(n):,}".replace(",", ".")


def es_contador(nombre):
    """Si el nombre es el de un contador SMART (smart_N_normalized o smart_N_raw)."""
    return PATRON_CONTADOR.match(nombre) is not None


def orden_columnas(nombres):
    """Orden de la salida: las columnas fijas delante; los contadores por número, nota antes que bruto; lo demás al final."""
    delante = [c for c in COLUMNAS_DELANTE if c in nombres]
    contadores = sorted((c for c in nombres if es_contador(c)),
                        key=lambda c: (int(PATRON_CONTADOR.match(c).group(1)), PATRON_CONTADOR.match(c).group(2) == "raw"))
    resto = [c for c in nombres if c not in delante and c not in contadores]
    return delante + contadores + resto


# =================================================================================================================
# 3. Entradas: el diagnóstico de calidad y el fichero de decisiones
# =================================================================================================================
def leer_calidad(raiz, huella_raw):
    """Lee informes/calidad-datos.json y comprueba que se puede corregir con él (resultado.md, «Al empezar»)."""
    ruta = raiz / "informes" / "calidad-datos.json"
    if not ruta.exists():
        raise ParadaDeRegla("no existe informes/calidad-datos.json: falta el diagnóstico")
    cal = json.loads(ruta.read_text(encoding="utf-8"))
    estado = cal.get("resultado", {}).get("estado")
    if estado in ("PARADO", "ERROR", None):
        raise ParadaDeRegla(f"el JSON de calidad está en {estado}: falta el diagnóstico y no se corrige")
    suyas = {e["ruta"].removeprefix("data/raw/"): e["sha256"] for e in cal.get("entradas", [])}
    if suyas != huella_raw:
        raise ParadaDeRegla("la huella de las entradas del JSON de calidad no es la de data/raw/: hay que repetir la calidad")
    return cal


def leer_decisiones(raiz):
    """Lee el fichero de decisiones del caso y comprueba que su mapeo de modelos es cerrado y tiene sentido."""
    ruta = raiz / "config" / "modelo" / "decisiones-correccion.json"
    if not ruta.exists():
        raise ParadaDeRegla("no existe config/modelo/decisiones-correccion.json")
    dec = json.loads(ruta.read_text(encoding="utf-8"))
    for antes, despues in dec["modelos"]["mapeo"].items():
        if "  " not in antes or "  " in despues or " ".join(antes.split()) != despues:
            raise ErrorDeRegla(f"el mapeo de modelos no es solo quitar el espacio repetido: {antes!r} → {despues!r}")
    return dec


def comprobar_decisiones_contra_calidad(dec, cal):
    """Cada problema de calidad va una vez, corregido o sin cambios, y cada pendiente tiene su decisión (método, apartado 2)."""
    problemas = [p["id"] for p in cal["problemas"]]
    corregidos = set(dec["capacidad"]["problemas_calidad"]) | {dec["modelos"]["problema_calidad"], dec["fecha_y_texto"]["problema_calidad"]}
    corregidos |= {v["problema_calidad"] for v in dec["tipos"].values() if v.get("problema_calidad")}
    sin = [s["problema_calidad"] for s in dec["sin_cambios"]]
    repetidos = sorted(corregidos & set(sin)) + sorted({x for x in sin if sin.count(x) > 1})
    sueltos = sorted(set(problemas) - corregidos - set(sin))
    ajenos = sorted((corregidos | set(sin)) - set(problemas))
    pendientes = {p["id"] for p in cal.get("pendientes", [])}
    sin_decision = sorted(pendientes - {dec["fecha_y_texto"]["pendiente"]})
    if repetidos or sueltos or ajenos or sin_decision:
        raise ErrorDeRegla(f"decisiones que no casan con la calidad: repetidos {repetidos}, sin decidir {sueltos}, "
                           f"que no existen {ajenos}, pendientes sin decisión {sin_decision}")
    return sorted(corregidos)


# =================================================================================================================
# 4. Las reglas de corrección, sobre un DataFrame df
# =================================================================================================================
def normalizar_modelo(df, mapeo):
    """Cambia cada variante del mapeo cerrado por su nombre (D1); lo que no está en el mapeo se queda como está."""
    antes = df["model"].copy()
    df["model"] = df["model"].replace(mapeo)
    return int((antes != df["model"]).sum())


def capacidad_no_valida(serie, minimo):
    """Máscara de las capacidades que no son válidas: -1 y 0,1 TB (reglas, apartado 3)."""
    return serie < minimo


def poner_capacidad_del_modelo(df, capacidad_modelo, minimo):
    """Pone en cada fila con capacidad no válida la única capacidad válida de su modelo (reglas, apartado 3)."""
    mala = capacidad_no_valida(df["capacity_bytes"], minimo)
    sin_capacidad = sorted(set(df.loc[mala, "model"]) - set(capacidad_modelo))
    if sin_capacidad:
        raise ErrorDeRegla(f"modelos con capacidad no válida y sin ninguna capacidad válida: {sin_capacidad}")
    df.loc[mala, "capacity_bytes"] = df.loc[mala, "model"].map(capacidad_modelo).astype("int64")
    return int(mala.sum())


def sumar_misma_clave(df, clave, magnitudes):
    """Suma en una las filas que comparten clave, en el orden en que aparece cada clave por primera vez."""
    return df.groupby(clave, sort=False, dropna=False, as_index=False)[magnitudes].sum()


def fecha_del_texto(df):
    """La fecha que dice el texto date, leída con su patrón ISO; falla si algún texto no es una fecha."""
    fecha = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    nuevos_vacios = int(fecha.isna().sum() - df["date"].isna().sum())
    if nuevos_vacios:
        raise ErrorDeRegla(f"{nuevos_vacios} textos de date no son una fecha AAAA-MM-DD")
    return fecha


def capacidades_validas(modelos_y_capacidades, minimo):
    """Capacidades válidas de cada modelo, a partir de pares (modelo, capacidad) ya con el nombre corregido."""
    validas = {}
    for modelo, capacidad in modelos_y_capacidades:
        if capacidad >= minimo:
            validas.setdefault(modelo, set()).add(int(capacidad))
    return validas


def fallos_sin_dia_anterior(df, capacidad_modelo):
    """Fallos de discos de datos cuya ventana no trae el día anterior al fallo (el día que mira el aviso, reglas, apartado 6)."""
    claves = df[["serial_number", "dia_fallo"]].drop_duplicates()
    con_antes = df.loc[(df["dia_fallo"] - df["fecha"]).dt.days.eq(1), ["serial_number", "dia_fallo"]].drop_duplicates()
    sin = claves.merge(con_antes, how="left", indicator=True).query("_merge == 'left_only'").drop(columns="_merge")
    # El grupo del fallo sale del modelo de su ventana (la fila del día del fallo, o cualquiera si falta)
    modelo = df.sort_values("fecha").drop_duplicates(["serial_number", "dia_fallo"], keep="last")[["serial_number", "dia_fallo", "model"]]
    sin = sin.merge(modelo, how="left")
    datos = sin["model"].map(capacidad_modelo).ge(CAPACIDAD_MAX_ARRANQUE)
    return int(datos.sum()), int(len(sin))


# =================================================================================================================
# 5. Datos personales en claro (método, apartado 1)
# =================================================================================================================
PATRON_CORREO = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")
PATRON_DNI = re.compile(r"^([XYZ]?)(\d{7,8})([A-Z])$")
PATRON_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
PATRON_TELEFONO = re.compile(r"^\+\d{9,15}$|^(\+34|0034)?[6789]\d{8}$")
LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"


def parece_dato_personal(texto):
    """Qué dato personal parece un texto: correo, DNI o NIE con su letra buena, IBAN con su control bueno o teléfono."""
    t = str(texto).strip().upper()
    if PATRON_CORREO.search(str(texto)):
        return "correo"
    m = PATRON_DNI.match(t)
    if m:
        numero = int(str("XYZ".index(m.group(1))) + m.group(2) if m.group(1) else m.group(2))
        if LETRAS_DNI[numero % 23] == m.group(3):
            return "documento de identidad"
    if PATRON_IBAN.match(t):
        reordenado = t[4:] + t[:4]
        if int("".join(str(int(c, 36)) for c in reordenado)) % 97 == 1:
            return "cuenta bancaria"
    if PATRON_TELEFONO.match(t):
        return "teléfono"
    return None


def buscar_datos_personales(textos_por_columna):
    """Cuenta, por columna, los valores distintos con forma de dato personal; nunca guarda el valor."""
    hallazgos = []
    for (tabla, columna), valores in sorted(textos_por_columna.items()):
        tipos = {}
        for v in valores:
            tipo = parece_dato_personal(v)
            if tipo:
                tipos[tipo] = tipos.get(tipo, 0) + 1
        for tipo, n in tipos.items():
            hallazgos.append({"tabla": tabla, "columna": columna, "tipo": tipo, "valores_distintos": n})
    return hallazgos


# =================================================================================================================
# 6. Primera pasada: lo que hay antes de corregir y la capacidad de cada modelo
# =================================================================================================================
def ficheros_de(raiz, tabla):
    """Ficheros Parquet de una tabla en data/raw/podado/, en orden."""
    pod = raiz / "data" / "raw" / "podado"
    if tabla in ("fotos_mensuales", "ventanas_fallo"):
        return sorted((pod / tabla).glob("*.parquet"))
    return [pod / f"{tabla}.parquet"]


def esquema_comun(ficheros):
    """Esquema de salida con todas las columnas de las piezas y el tipo de su rol: centro texto, ranura entera, date fecha."""
    tipos = {}
    for f in ficheros:
        for campo in pq.read_schema(f):
            if not pa.types.is_null(campo.type):
                tipos.setdefault(campo.name, set()).add(campo.type)
            else:
                tipos.setdefault(campo.name, set())
    dobles = {c: sorted(map(str, t)) for c, t in tipos.items() if len(t) > 1}
    if dobles:
        raise ErrorDeRegla(f"columnas con dos tipos según la pieza: {dobles}")
    objetivo = {c: (next(iter(t)) if t else pa.string()) for c, t in tipos.items()}
    objetivo["datacenter"] = pa.string()
    if "pod_slot_num" in objetivo:
        objetivo["pod_slot_num"] = pa.int64()
    if "date" in objetivo:
        objetivo["date"] = pa.timestamp("ms")
    return pa.schema([pa.field(c, objetivo[c]) for c in orden_columnas(list(objetivo))])


def primera_pasada(raiz, mapeo, minimo):
    """Lee lo justo de las cuatro tablas para medir el antes y sacar la capacidad válida de cada modelo."""
    pares = set()
    textos = {}
    antes = {"fotos_mensuales": {}, "ventanas_fallo": {}}
    piezas_cambio = []
    for tabla in ("fotos_mensuales", "ventanas_fallo"):
        a = {"ficheros": 0, "filas": 0, "capacidad_no_valida": 0, "modelos_dos_espacios": set(), "filas_modelo_en_mapeo": 0,
             "ficheros_centro_sin_tipo": 0, "filas_ranura_decimal": 0, "filas_date_texto": 0, "fecha_distinta_del_texto": 0,
             "failure": 0, "variantes_fuera_del_mapeo": set()}
        for f in ficheros_de(raiz, tabla):
            esquema = pq.read_schema(f)
            cols = ["serial_number", "model", "capacity_bytes", "fecha", "date", "failure"]
            t = pq.read_table(f, columns=cols)
            a["ficheros"] += 1
            a["filas"] += t.num_rows
            cap = t["capacity_bytes"].to_numpy()
            a["capacidad_no_valida"] += int((cap < minimo).sum())
            a["failure"] += int(pc.sum(t["failure"]).as_py() or 0)
            modelos = pc.value_counts(t["model"]).to_pylist()
            for par in modelos:
                m = par["values"]
                if "  " in m:
                    a["modelos_dos_espacios"].add(m)
                    if m in mapeo:
                        a["filas_modelo_en_mapeo"] += par["counts"]
                    else:
                        a["variantes_fuera_del_mapeo"].add(m)
            # Pares distintos de modelo y capacidad, con el nombre ya corregido, para la capacidad de cada modelo
            pares_t = pa.table({"m": t["model"], "c": t["capacity_bytes"]}).group_by(["m", "c"]).aggregate([]).to_pylist()
            pares |= {(mapeo.get(p["m"], p["m"]), p["c"]) for p in pares_t}
            if pa.types.is_null(esquema.field("datacenter").type):
                a["ficheros_centro_sin_tipo"] += 1
            if "pod_slot_num" in esquema.names and pa.types.is_floating(esquema.field("pod_slot_num").type):
                a["filas_ranura_decimal"] += t.num_rows
            if pa.types.is_string(esquema.field("date").type):
                a["filas_date_texto"] += t.num_rows
            # El texto se lee como fecha ISO (la conversión falla si alguno no lo es) y se compara con la fecha
            fecha_texto = pc.cast(t["date"], pa.timestamp("ms"))
            a["fecha_distinta_del_texto"] += int(pc.sum(pc.not_equal(fecha_texto, t["fecha"])).as_py() or 0)
            textos.setdefault((tabla, "serial_number"), set()).update(pc.unique(t["serial_number"]).to_pylist())
            textos.setdefault((tabla, "model"), set()).update(m["values"] for m in modelos)
            if tabla == "fotos_mensuales":
                piezas_cambio.append(t.select(["serial_number", "fecha", "model", "capacity_bytes"]))
        antes[tabla] = a
    # El recuento y la lista de fallos son pequeños: se leen enteros
    rec = pd.read_parquet(ficheros_de(raiz, "recuento_diario")[0])
    pares |= {(mapeo.get(m, m), int(c)) for m, c in rec[["model", "capacity_bytes"]].drop_duplicates().itertuples(index=False)}
    textos[("recuento_diario", "model")] = set(rec["model"].unique())
    textos[("recuento_diario", "datacenter")] = set(rec["datacenter"].unique())
    fal = pd.read_parquet(ficheros_de(raiz, "fallos")[0])
    textos[("fallos", "serial_number")] = set(fal["serial_number"].unique())
    validas = capacidades_validas(pares, minimo)
    cambios_antes = cambios_entre_fotos(pa.concat_tables(piezas_cambio), minimo)
    return antes, validas, textos, rec, fal, cambios_antes


def cambios_entre_fotos(t, minimo):
    """Veces que el modelo o la capacidad de un disco cambian entre dos fotos seguidas suyas (RC-02)."""
    serie = pc.dictionary_encode(t["serial_number"].combine_chunks()).indices.to_numpy()
    modelo = pc.dictionary_encode(t["model"].combine_chunks()).indices.to_numpy()
    fecha = t["fecha"].combine_chunks().cast(pa.int64()).to_numpy()
    cap = t["capacity_bytes"].combine_chunks().to_numpy()
    orden = np.lexsort((fecha, serie))
    s, m, c = serie[orden], modelo[orden], cap[orden]
    mismo = s[1:] == s[:-1]
    validas = (c[1:] >= minimo) & (c[:-1] >= minimo)
    return {"modelo": int((mismo & (m[1:] != m[:-1])).sum()), "capacidad": int((mismo & (c[1:] != c[:-1])).sum()),
            "capacidad_entre_validas": int((mismo & validas & (c[1:] != c[:-1])).sum())}


# =================================================================================================================
# 7. Fotos y ventanas: corregir pieza a pieza y juntar en un Parquet
# =================================================================================================================
def corregir_pieza(t, esquema, mapeo, capacidad_modelo, minimo, quitar_fecha_distinta):
    """Corrige una pieza (un fichero) y la devuelve con el esquema común, más lo que hizo con ella."""
    n = t.num_rows
    # El df de trabajo lleva solo las columnas que se corrigen; los contadores siguen en Arrow sin tocarse
    df = t.select(["fecha", "date", "model", "capacity_bytes", "failure"]).to_pandas()
    hecho = {"modelo": normalizar_modelo(df, mapeo)}
    hecho["capacidad"] = poner_capacidad_del_modelo(df, capacidad_modelo, minimo)
    fecha_texto = fecha_del_texto(df)
    distinta = (fecha_texto != df["fecha"]).to_numpy()
    hecho["fecha_distinta"] = int(distinta.sum())
    conservar = ~distinta if quitar_fecha_distinta else np.ones(n, dtype=bool)
    quitadas = df.loc[~conservar, ["fecha", "date", "failure"]].copy()
    if int(quitadas["failure"].sum()):
        raise ErrorDeRegla(f"{int(quitadas['failure'].sum())} filas que se quitarían traen un fallo: no se quita ninguna")
    # Se ponen en la tabla las columnas corregidas y se añaden vacías las que la pieza no trae
    columnas = {}
    for campo in esquema:
        c = campo.name
        if c == "model":
            columnas[c] = pa.array(df["model"], type=pa.string())
        elif c == "capacity_bytes":
            columnas[c] = pa.array(df["capacity_bytes"], type=pa.int64())
        elif c == "date":
            columnas[c] = pa.array(fecha_texto, type=pa.timestamp("ms"))
        elif c in t.column_names:
            columnas[c] = t[c].cast(campo.type, safe=True)
        else:
            columnas[c] = pa.nulls(n, type=campo.type)
    salida = pa.table(columnas, schema=esquema)
    # Ningún vacío nuevo: cada columna que trae la pieza tiene en la salida los mismos vacíos que en bruto
    vacios = {c: (t[c].null_count if not pa.types.is_null(t.schema.field(c).type) else n, salida[c].null_count)
              for c in t.column_names}
    hecho["vacios_cambiados"] = sorted(c for c, (a, d) in vacios.items() if a != d)
    filtro = pa.array(conservar)
    raw_mag = [c for c in t.column_names if c.endswith("_raw") or c == "failure"]
    hecho["sumas_antes"] = {c: pc.sum(t.filter(filtro)[c]).as_py() or 0 for c in raw_mag}
    salida = salida.filter(filtro)
    hecho["sumas_despues"] = {c: pc.sum(salida[c]).as_py() or 0 for c in raw_mag}
    hecho["quitadas"] = quitadas
    return salida, hecho


def corregir_troceada(raiz, tabla, destino, mapeo, capacidad_modelo, minimo, quitar_fecha_distinta):
    """Corrige las piezas de una tabla una a una y las escribe en un único Parquet, sin cargarla entera en memoria."""
    ficheros = ficheros_de(raiz, tabla)
    esquema = esquema_comun(ficheros)
    total = {"modelo": 0, "capacidad": 0, "fecha_distinta": 0, "filas_salida": 0, "vacios_cambiados": set(),
             "sumas_antes": {}, "sumas_despues": {}, "quitadas": [], "ventana": []}
    with pq.ParquetWriter(destino, esquema) as escritor:
        for f in ficheros:
            t = pq.read_table(f)
            salida, hecho = corregir_pieza(t, esquema, mapeo, capacidad_modelo, minimo, quitar_fecha_distinta)
            escritor.write_table(salida)
            for k in ("modelo", "capacidad", "fecha_distinta"):
                total[k] += hecho[k]
            total["filas_salida"] += salida.num_rows
            total["vacios_cambiados"] |= set(hecho["vacios_cambiados"])
            for clave in ("sumas_antes", "sumas_despues"):
                for c, v in hecho[clave].items():
                    total[clave][c] = total[clave].get(c, 0) + v
            total["quitadas"].append(hecho["quitadas"])
            if tabla == "ventanas_fallo":
                # Para contar los fallos sin día anterior antes y después: el bruto con el nombre corregido, y la salida
                bruto = t.select(["serial_number", "fecha", "dia_fallo", "model"]).to_pandas()
                bruto["model"] = bruto["model"].replace(mapeo)
                total["ventana"].append((bruto, salida.select(["serial_number", "fecha", "dia_fallo", "model"]).to_pandas()))
    total["quitadas"] = pd.concat(total["quitadas"], ignore_index=True)
    return esquema, total


# =================================================================================================================
# 8. Comprobaciones sobre los ficheros escritos
# =================================================================================================================
def diccionario_salida(ruta, reglas_por_columna):
    """Tipo, vacíos y valores distintos de cada columna de un Parquet escrito, leída columna a columna."""
    pf = pq.ParquetFile(ruta)
    campos = []
    for campo in pf.schema_arrow:
        col = pf.read(columns=[campo.name])[campo.name]
        campos.append({"columna": campo.name, "tipo": str(campo.type), "nulos": col.null_count,
                       "distintos": pc.count_distinct(col).as_py(), "regla_aplicada": reglas_por_columna.get(campo.name)})
    return campos


def medir_salida_troceada(ruta, minimo):
    """Lo que se cuenta en la salida de fotos o ventanas: filas, capacidades, modelos y tipos."""
    pf = pq.ParquetFile(ruta)
    t = pf.read(columns=["model", "capacity_bytes", "failure"])
    modelos = pc.unique(t["model"]).to_pylist()
    esquema = pf.schema_arrow
    return {"filas": pf.metadata.num_rows, "capacidad_no_valida": int(pc.sum(pc.less(t["capacity_bytes"], minimo)).as_py() or 0),
            "modelos_dos_espacios": sorted(m for m in modelos if "  " in m), "failure": int(pc.sum(t["failure"]).as_py() or 0),
            "tipo_datacenter": str(esquema.field("datacenter").type), "tipo_pod_slot_num": str(esquema.field("pod_slot_num").type),
            "tipo_date": str(esquema.field("date").type), "columnas": len(esquema.names)}


# =================================================================================================================
# 9. Registro de transformaciones
# =================================================================================================================
CABECERA_REGISTRO = """---
titulo: Registro de transformaciones del caso 68 · cada regla que cambia los datos de trabajo, con su ficha
estado: vivo; solo acumula. Lo escribe scripts/03_correccion_datos.py la primera vez que aplica cada regla
fecha_documento: {fecha}
dueno: El responsable del caso (decide)
---

# Registro de transformaciones

Cada ficha lleva nueve campos: tabla y columna; cómo estaba; problema; decisión; qué se hizo; quién y con qué permiso;
comprobación; cómo quedó; cómo deshacer. Una ficha no se borra ni se reescribe: si una regla se retira o se corrige, se
añade otra que lo dice. Las cifras de cada ficha son las de la ejecución que la escribió.
"""


def ficha(numero, tabla_columna, como_estaba, problema, decision, codigo, comprobacion, como_quedo, deshacer, fecha):
    """Texto de una ficha del registro, con sus nueve campos."""
    return (f"\n## {numero} · {tabla_columna}\n\n"
            f"Escrita el {fecha} por {SCRIPT}.\n\n"
            f"1. **Tabla y columna:** {tabla_columna}.\n"
            f"2. **Cómo estaba:** {como_estaba}\n"
            f"3. **Problema:** {problema}\n"
            f"4. **Decisión:** {decision}\n"
            f"5. **Qué se hizo:**\n\n```python\n{codigo}\n```\n\n"
            f"6. **Quién y con qué permiso:** el analista, con la petición {PETICION}, lanzado por "
            f"El responsable del caso el 17/11/2026 («Sí, lánzalo»).\n"
            f"7. **Comprobación:** {comprobacion}\n"
            f"8. **Cómo quedó:** {como_quedo}\n"
            f"9. **Cómo deshacer:** {deshacer} data/raw/ no se toca, así que basta con volver a ejecutar el script sin la regla.\n")


def escribir_registro(raiz, fichas):
    """Añade al registro las fichas cuyo número todavía no está; si no cambia ninguna regla, no añade nada."""
    ruta = raiz / "config" / "modelo" / "registro-transformaciones.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = ruta.read_text(encoding="utf-8") if ruta.exists() else CABECERA_REGISTRO.format(fecha=dt.date.today().isoformat())
    nuevas = [(n, f) for n, f in fichas if not re.search(rf"^## {n} ", texto, re.M)]
    if nuevas or not ruta.exists():
        ruta.write_text(texto + "".join(f for _, f in nuevas), encoding="utf-8")
    return [n for n, _ in nuevas]


# =================================================================================================================
# 10. Informe para la persona, generado del JSON
# =================================================================================================================
def informe_md(r):
    """Genera informes/correccion-datos.md a partir del diccionario del JSON, con la plantilla de el método."""
    L = ["# Informe de corrección de datos", "",
         f"**Estado: {r['resultado']['estado']}.** {r['resultado']['resumen']}", ""]
    L += ["## Fuente", ""]
    if r.get("ejecucion"):
        e = r["ejecucion"]
        L += [f"- **Datasets de entrada:** los cuatro de `data/raw/podado/`: {fmt(r['controles'].get('fotos.ficheros'))} fotos "
              f"mensuales, {fmt(r['controles'].get('ventanas.ficheros'))} ventanas de fallo por trimestre, el recuento diario y la "
              f"lista de fallos ({len(r['entradas'])} ficheros en `data/raw/` con el esquema).",
              f"- **Diagnóstico usado:** `informes/calidad-datos.json`, en estado {r['calidad_usada']['estado']}, ejecutado el "
              f"{r['calidad_usada']['fecha_ejecucion'] or 'sin fecha'}, con la misma huella de entrada que estos datos.",
              f"- **Decisiones leídas:** `config/modelo/decisiones-correccion.json`.",
              "- **Datasets de salida:** " + "; ".join(f"`{s['ruta']}`" for s in r["salidas"]) + ".",
              f"- **Ejecución:** {r['fecha_ejecucion']}, con Python {e['python']}, pandas {e['pandas']}, pyarrow {e['pyarrow']} "
              f"y numpy {e['numpy']}.",
              f"- **Huellas:** las de los {len(r['entradas'])} ficheros de entrada y las de las cuatro salidas están en el JSON "
              f"(`entradas` y `salidas`). data/raw/ tiene la misma huella al empezar y al terminar.",
              f"- **Teoría aplicada:** {r['teoria']}", ""]
    else:
        L += [f"- La ejecución paró antes de corregir: {r['resultado']['resumen']}", ""]

    L += ["## Correcciones aplicadas", ""]
    if r["correcciones"]:
        for c in r["correcciones"]:
            origen = f"Viene del problema {c['problema_calidad']}" if c["problema_calidad"] else "No viene de ningún problema de calidad"
            L.append(f"- **{c['id']} · {NOMBRE_TABLA.get(c['tabla'], c['tabla'])}, `{c['columna']}`.** {c['correccion']} "
                     f"{origen}; criterio: {c['criterio_texto']}. Pasa de {fmt(c['antes'])} a {fmt(c['despues'])} "
                     f"{c['unidad']}. Ficha {c['ficha']} del registro.")
    else:
        L.append("- No se aplicó ninguna corrección.")
    L.append("")

    L += ["## Decisiones del responsable", ""]
    if r["decisiones_responsable"]:
        L += [f"- **{d['pendiente']}:** {d['decision']} ({d['quien']}, {d['fecha']}; {d['fuente']})." for d in r["decisiones_responsable"]]
    else:
        L.append("- No hay instrucciones de tratamiento de la persona responsable en esta ejecución.")
    L.append("")

    L += ["## Elementos mantenidos sin cambios", "",
          "Estos problemas del diagnóstico se dejan como están, cada uno con su motivo. Ninguno rellena un vacío: el caso "
          "entrena un modelo.", ""]
    L += [f"- **{s['problema_calidad']}** ({s['resultado_calidad']}): {s['motivo']}." for s in r["sin_cambios"]]
    if r.get("variantes_fuera_del_mapeo"):
        L.append(f"- Variantes de modelo con dos espacios que no están en el mapeo y se dejan como están: {len(r['variantes_fuera_del_mapeo'])}.")
    if r.get("tipos_sin_cambiar"):
        L.append(f"- {r['tipos_sin_cambiar']}")
    L.append("")

    L += ["## Decisiones pendientes", ""]
    if r["pendientes"]:
        L += [f"- **{p['id']}** ({p['tabla']}, `{p['columna']}`): {p['pregunta']} Opciones: {'; '.join(p['opciones'])}." for p in r["pendientes"]]
    else:
        L.append("- No queda ninguna. La única cuestión que dejó la calidad, P-01, la resuelve la petición 07 y está en «Decisiones del responsable».")
    L.append("")

    L += ["## Validación", ""]
    if r.get("metricas"):
        L += ["| Tabla | Filas antes | Filas después | Capacidad -1 o 0,1 TB antes | Después | Modelos con dos espacios antes | Después |",
              "|---|---:|---:|---:|---:|---:|---:|"]
        for m in r["metricas"]:
            L.append(f"| {NOMBRE_TABLA[m['tabla']]} | {fmt(m['filas_antes'])} | {fmt(m['filas_despues'])} | "
                     f"{fmt(m['capacidad_no_valida_antes'])} | {fmt(m['capacidad_no_valida_despues'])} | "
                     f"{fmt(m['modelos_dos_espacios_antes'])} | {fmt(m['modelos_dos_espacios_despues'])} |")
        ctl = r["controles"]
        L += ["", f"Las ventanas pierden {fmt(ctl['ventanas.filas_quitadas'])} filas, todas del "
              f"{', '.join(ctl['ventanas.fechas_quitadas'])}, ninguna con un fallo. Por eso los fallos de discos de datos sin el "
              f"día anterior en su ventana pasan de {fmt(ctl['ventanas.fallos_datos_sin_dia_anterior']['antes'])} a "
              f"{fmt(ctl['ventanas.fallos_datos_sin_dia_anterior']['despues'])}. El recuento pasa de "
              f"{fmt(ctl['recuento.filas']['antes'])} a {fmt(ctl['recuento.filas']['despues'])} filas al sumar las que quedan con la "
              f"misma clave. En las fotos, tras las dos correcciones, un disco cambia de modelo "
              f"{fmt(ctl['fotos.cambios_de_modelo']['despues'])} vez entre dos fotos seguidas, frente a "
              f"{fmt(ctl['fotos.cambios_de_modelo']['antes'])} antes.", ""]
        L += ["**Sumas de control.** Cada magnitud que no debía cambiar da lo mismo antes y después:", ""]
        for s in r["sumas_control"]:
            L.append(f"- {NOMBRE_TABLA.get(s['tabla'], s['tabla'])}, `{s['columna']}` ({s['via']}): {fmt(s['antes'])} y "
                     f"{fmt(s['despues'])}; {'coincide' if s['coincide'] else 'NO coincide'}.")
        L += ["", "**Las cuatro comprobaciones del dataset procesado:**", ""]
        L += [f"- {k}: {v}." for k, v in r["comprobaciones"].items()]
        L += ["", "**Comprobaciones de la ejecución:**", ""]
        L += [f"- {v['comprobacion']}: {'pasa' if v['ok'] else 'NO pasa'}." for v in r["validacion"]]
        L += ["", f"Estado final: {r['resultado']['estado']}. Los datasets corregidos están en `data/processed/`, uno por tabla.", ""]
    else:
        L += ["- No se llegó a validar: la ejecución paró antes.", ""]

    L += ["## Datos personales", ""]
    L += [f"- {t}" for t in r["datos_personales_texto"]]
    L.append("")
    L += ["## Límites", ""]
    L += [f"- {t}" for t in r["limites"]]
    L.append("")
    return "\n".join(L)


# =================================================================================================================
# 11. Ejecución
# =================================================================================================================
def escribir_salidas_de_informe(raiz, r):
    """Escribe el JSON y, del mismo diccionario, el informe Markdown."""
    (raiz / "informes").mkdir(exist_ok=True)
    (raiz / "informes" / "correccion-datos.json").write_text(json.dumps(a_json(r), ensure_ascii=False, indent=2, allow_nan=False),
                                                            encoding="utf-8")
    (raiz / "informes" / "correccion-datos.md").write_text(informe_md(a_json(r)), encoding="utf-8")


def base_resultado(fecha_ejecucion):
    """El bloque común del JSON, vacío, para escribirlo también si el script para o falla."""
    return {"metodo": METODO, "version_metodo": VERSION_METODO, "script": SCRIPT, "fecha_datos": FECHA_DATOS,
            "fecha_ejecucion": fecha_ejecucion, "entradas": [], "resultado": {}, "pendientes": [], "salidas": [],
            "correcciones": [], "sin_cambios": [], "decisiones_responsable": [], "sumas_control": [], "comprobaciones": {},
            "nombres": [], "va_a_modelo": VA_A_MODELO, "parametros": PARAMETROS, "controles": {}, "validacion": [],
            "teoria": TEORIA,
            "datos_personales_texto": ["No existe config/fuentes/proteccion-datos.json: los datos no pasaron por la protección.",
                                       "No hay datos de personas (reglas, apartado 9): el paso de protección se saltó el 17/11/2026 con el sí del responsable del caso."],
            "limites": ["La corrección mira una tabla cada vez. Una clave huérfana o repetida al otro lado de un cruce no se ve ni se corrige aquí."]}


def corregir(raiz):
    """Corrige los cuatro datasets del caso que está en raiz y devuelve el diccionario del JSON."""
    tiempos, t0 = {}, time.time()
    fecha_ejecucion = dt.datetime.now().replace(microsecond=0).isoformat()
    r = base_resultado(fecha_ejecucion)
    proc = raiz / "data" / "processed"
    parciales = {t: raiz / (SALIDA[t] + ".parcial") for t in TABLAS}
    try:
        # 11.1 Huella de data/raw/ al empezar, diagnóstico y decisiones
        raw = raiz / "data" / "raw"
        huella_inicio = huellas(raw)
        r["entradas"] = []
        for k, v in huella_inicio.items():
            ruta = raw / k
            if ruta.suffix == ".parquet":
                md = pq.ParquetFile(ruta).metadata
                filas, columnas = md.num_rows, md.num_columns
            else:
                lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
                filas, columnas = len(lineas), 1
            r["entradas"].append({"ruta": f"data/raw/{k}", "sha256": v, "filas": filas, "columnas": columnas})
        cal = leer_calidad(raiz, huella_inicio)
        r["calidad_usada"] = {"ruta": "informes/calidad-datos.json", "estado": cal["resultado"]["estado"],
                              "fecha_ejecucion": cal.get("fecha_ejecucion")}
        dec = leer_decisiones(raiz)
        comprobar_decisiones_contra_calidad(dec, cal)
        mapeo = dec["modelos"]["mapeo"]
        minimo = dec["capacidad"]["minimo_valido_bytes"]
        tiempos["huellas, diagnóstico y decisiones"] = round(time.time() - t0, 1)

        # 11.2 Primera pasada: el antes, la capacidad de cada modelo y los datos personales
        t1 = time.time()
        antes, validas, textos, rec_raw, fal_raw, cambios_antes = primera_pasada(raiz, mapeo, minimo)
        varias = {m: sorted(c) for m, c in validas.items() if len(c) > 1}
        if varias:
            raise ErrorDeRegla(f"modelos con más de una capacidad válida, la regla, apartado 3 no se puede aplicar: {varias}")
        capacidad_modelo = {m: next(iter(c)) for m, c in validas.items()}
        personales = buscar_datos_personales(textos)
        if personales:
            r["datos_personales_hallados"] = personales
            raise ParadaDeRegla("hay columnas con valores con forma de dato personal en claro: " +
                                "; ".join(f"{h['tabla']}.{h['columna']}, {h['valores_distintos']} valores ({h['tipo']})" for h in personales))
        tiempos["primera pasada"] = round(time.time() - t1, 1)

        # 11.3 Fotos y ventanas, pieza a pieza
        proc.mkdir(parents=True, exist_ok=True)
        t2 = time.time()
        esq_f, tot_f = corregir_troceada(raiz, "fotos_mensuales", parciales["fotos_mensuales"], mapeo, capacidad_modelo, minimo, False)
        tiempos["fotos: corregir y escribir"] = round(time.time() - t2, 1)
        t3 = time.time()
        esq_v, tot_v = corregir_troceada(raiz, "ventanas_fallo", parciales["ventanas_fallo"], mapeo, capacidad_modelo, minimo,
                                         dec["fecha_y_texto"]["tabla"] == "ventanas_fallo")
        tiempos["ventanas: corregir y escribir"] = round(time.time() - t3, 1)

        # 11.4 Recuento: nombre, capacidad y suma de las filas con la misma clave, por este orden
        t4 = time.time()
        df = rec_raw.copy()
        clave, magnitudes = dec["capacidad"]["recuento_clave"], dec["capacidad"]["recuento_magnitudes"]
        r_modelo = normalizar_modelo(df, mapeo)
        r_capacidad = poner_capacidad_del_modelo(df, capacidad_modelo, minimo)
        df = sumar_misma_clave(df, clave, magnitudes)
        esquema_rec = pq.read_schema(ficheros_de(raiz, "recuento_diario")[0]).remove_metadata()
        pq.write_table(pa.Table.from_pandas(df[esquema_rec.names], preserve_index=False).cast(esquema_rec), parciales["recuento_diario"])
        # La lista de fallos no tiene nada que corregir: se escribe igual
        pq.write_table(pq.read_table(ficheros_de(raiz, "fallos")[0]), parciales["fallos"])
        tiempos["recuento y lista de fallos"] = round(time.time() - t4, 1)

        # 11.5 Lo que se mide sobre los ficheros escritos, antes de darlos por buenos
        t5 = time.time()
        sal_f = medir_salida_troceada(parciales["fotos_mensuales"], minimo)
        sal_v = medir_salida_troceada(parciales["ventanas_fallo"], minimo)
        cambios_despues = cambios_entre_fotos(pq.read_table(parciales["fotos_mensuales"],
                                                            columns=["serial_number", "fecha", "model", "capacity_bytes"]), minimo)
        # Los fallos sin día anterior se cuentan con todas las ventanas juntas: una ventana puede caer en dos trimestres
        bruto_v = pd.concat([a for a, _ in tot_v["ventana"]], ignore_index=True)
        sal_v_df = pd.concat([d for _, d in tot_v["ventana"]], ignore_index=True)
        sin_dia = {"antes": fallos_sin_dia_anterior(bruto_v, capacidad_modelo)[0], "despues": fallos_sin_dia_anterior(sal_v_df, capacidad_modelo)[0]}
        rec_d = pq.read_table(parciales["recuento_diario"])
        rec_a = pq.read_table(ficheros_de(raiz, "recuento_diario")[0])
        fal_d = pq.ParquetFile(parciales["fallos"]).metadata.num_rows
        # Dos vías para las sumas del recuento: pandas en memoria y pyarrow sobre los ficheros en disco
        via1 = {m: (int(rec_raw[m].sum()), int(df[m].sum())) for m in magnitudes}
        via2 = {m: (int(pc.sum(rec_a[m]).as_py()), int(pc.sum(rec_d[m]).as_py())) for m in magnitudes}
        por_dia_a = rec_raw.groupby("fecha")[magnitudes].sum()
        por_dia_d = df.groupby("fecha")[magnitudes].sum()
        rec_d_df = rec_d.to_pandas()
        rec_modelos_d = sorted(m for m in rec_d_df["model"].unique() if "  " in m)
        tiempos["comprobar las salidas"] = round(time.time() - t5, 1)

        # 11.6 Las comprobaciones, calculadas con lo que se ejecutó
        quitadas = tot_v["quitadas"]
        contadores_iguales = {t: all(tot["sumas_antes"][c] == tot["sumas_despues"][c] for c in tot["sumas_antes"])
                              for t, tot in (("fotos_mensuales", tot_f), ("ventanas_fallo", tot_v))}
        modelos_antes = antes["fotos_mensuales"]["modelos_dos_espacios"] | antes["ventanas_fallo"]["modelos_dos_espacios"] | \
            {m for m in rec_raw["model"].unique() if "  " in m}
        modelos_despues = set(sal_f["modelos_dos_espacios"]) | set(sal_v["modelos_dos_espacios"]) | set(rec_modelos_d)
        fuera_mapeo = sorted(m for m in modelos_antes if m not in mapeo)
        validacion = [
            {"comprobacion": "fotos: las mismas filas a la entrada y a la salida", "ok": sal_f["filas"] == antes["fotos_mensuales"]["filas"]},
            {"comprobacion": "ventanas: salen solo las filas cuya fecha no es la de su texto, ninguna con un fallo",
             "ok": sal_v["filas"] == antes["ventanas_fallo"]["filas"] - len(quitadas) and int(quitadas["failure"].sum()) == 0
             and len(quitadas) == antes["ventanas_fallo"]["fecha_distinta_del_texto"]},
            {"comprobacion": "fotos: ninguna fila con la fecha distinta de su texto, que no se quita",
             "ok": antes["fotos_mensuales"]["fecha_distinta_del_texto"] == 0},
            {"comprobacion": "recuento: discos y fallos suman lo mismo por las dos vías",
             "ok": all(a == d for a, d in via1.values()) and all(a == d for a, d in via2.values())},
            {"comprobacion": "recuento: discos y fallos de cada día suman lo mismo", "ok": bool(por_dia_a.equals(por_dia_d))},
            {"comprobacion": "recuento: la clave queda única", "ok": not bool(df.duplicated(clave).any())},
            {"comprobacion": "lista de fallos: las mismas filas", "ok": fal_d == len(fal_raw)},
            {"comprobacion": "ninguna capacidad -1 o 0,1 TB después",
             "ok": sal_f["capacidad_no_valida"] == 0 and sal_v["capacidad_no_valida"] == 0 and int((df["capacity_bytes"] < minimo).sum()) == 0},
            {"comprobacion": "ningún modelo del mapeo queda con dos espacios", "ok": not (modelos_despues & set(mapeo))},
            {"comprobacion": "ningún vacío nuevo ni rellenado en fotos y ventanas",
             "ok": not tot_f["vacios_cambiados"] and not tot_v["vacios_cambiados"]},
            {"comprobacion": "los fallos de fotos y ventanas se conservan",
             "ok": sal_f["failure"] == antes["fotos_mensuales"]["failure"] and sal_v["failure"] == antes["ventanas_fallo"]["failure"]},
            {"comprobacion": "los contadores en bruto suman lo mismo en las filas que se quedan",
             "ok": contadores_iguales["fotos_mensuales"] and contadores_iguales["ventanas_fallo"]},
            {"comprobacion": "tipos de salida: centro texto, ranura entera y date fecha",
             "ok": all(s["tipo_datacenter"] == "string" and s["tipo_pod_slot_num"] == "int64" and s["tipo_date"].startswith("timestamp")
                       for s in (sal_f, sal_v))},
            {"comprobacion": "ningún modelo con dos capacidades válidas", "ok": not varias},
        ]

        # 11.7 Las correcciones que cambiaron algo, con su ficha
        C = []
        reglas_por_columna = {}

        def corr(problema, tabla, columna, texto, criterio, criterio_texto, ficha_n, antes_, despues_, unidad, motivo=None):
            """Apunta una corrección solo si cambió algo (una regla 0 → 0 no es una corrección)."""
            if antes_ != despues_:
                C.append({"id": f"K-{len(C) + 1:02d}", "problema_calidad": problema, "tabla": tabla, "columna": columna,
                          "correccion": texto, "criterio": criterio, "criterio_texto": criterio_texto, "motivo": motivo,
                          "ficha": ficha_n, "antes": antes_, "despues": despues_, "unidad": unidad})
                reglas_por_columna.setdefault(tabla, {}).setdefault(columna, ficha_n)

        af, av = antes["fotos_mensuales"], antes["ventanas_fallo"]
        tip = dec["tipos"]
        corr(tip["texto"]["problema_calidad"], "fotos_mensuales", "datacenter", "El centro se lee como texto en todas las fotos.",
             "tecnicamente_inequivoca", "técnicamente inequívoca: el rol del diccionario es categórica y el tipo nulo es la forma de un centro vacío entero",
             "R-001", af["ficheros_centro_sin_tipo"], 0, "ficheros sin tipo")
        corr(tip["texto"]["problema_calidad"], "ventanas_fallo", "datacenter", "El centro se lee como texto en todas las ventanas.",
             "tecnicamente_inequivoca", "técnicamente inequívoca, como en las fotos", "R-001", av["ficheros_centro_sin_tipo"], 0, "ficheros sin tipo")
        corr(tip["entero_con_vacio"]["problema_calidad"], "fotos_mensuales", "pod_slot_num", "La ranura pasa de decimal a entero, y sus vacíos se quedan vacíos.",
             "tecnicamente_inequivoca", "técnicamente inequívoca: todos sus valores con dato son enteros (la conversión segura falla si alguno no lo es)",
             "R-002", af["filas_ranura_decimal"], 0, "filas leídas como decimal")
        corr(tip["entero_con_vacio"]["problema_calidad"], "ventanas_fallo", "pod_slot_num", "La ranura pasa de decimal a entero, y sus vacíos se quedan vacíos.",
             "tecnicamente_inequivoca", "técnicamente inequívoca, como en las fotos", "R-002", av["filas_ranura_decimal"], 0, "filas leídas como decimal")
        corr(None, "fotos_mensuales", "date", "El texto de la fecha pasa a fecha, leído con el patrón %Y-%m-%d.", "responsable",
             "responsable: la petición 07 pide las fechas como fecha, que es el rol de date en el diccionario", "R-003",
             af["filas_date_texto"], 0, "filas con la fecha como texto", motivo=tip["fecha_desde_texto"]["motivo"])
        corr(None, "ventanas_fallo", "date", "El texto de la fecha pasa a fecha, leído con el patrón %Y-%m-%d.", "responsable",
             "responsable: la petición 07 pide las fechas como fecha", "R-003", av["filas_date_texto"] - len(quitadas), 0,
             "filas con la fecha como texto", motivo=tip["fecha_desde_texto"]["motivo"])
        for tabla, filas_mapeo, modelos_a, modelos_d in (
                ("fotos_mensuales", tot_f["modelo"], af["modelos_dos_espacios"] & set(mapeo), set(sal_f["modelos_dos_espacios"]) & set(mapeo)),
                ("ventanas_fallo", tot_v["modelo"], av["modelos_dos_espacios"] & set(mapeo), set(sal_v["modelos_dos_espacios"]) & set(mapeo)),
                ("recuento_diario", r_modelo, {m for m in rec_raw["model"].unique() if m in mapeo}, set(rec_modelos_d) & set(mapeo))):
            corr(dec["modelos"]["problema_calidad"], tabla, "model",
                 f"Los modelos escritos con dos espacios tras «WDC» pasan a su nombre con uno, con el mapeo cerrado de D1 "
                 f"({fmt(filas_mapeo)} filas cambiadas).", "responsable", "responsable: D1, cerrada por el responsable del caso el 17/11/2026 en el plan de calidad",
                 "R-004", len(modelos_a), len(modelos_d), "nombres con dos espacios")
        for tabla, problema, n_antes, n_despues in (("fotos_mensuales", "C-05", af["capacidad_no_valida"], sal_f["capacidad_no_valida"]),
                                                    ("ventanas_fallo", "C-06", av["capacidad_no_valida"], sal_v["capacidad_no_valida"]),
                                                    ("recuento_diario", "C-07", r_capacidad, int((df["capacity_bytes"] < minimo).sum()))):
            corr(problema, tabla, "capacity_bytes", "Las filas con capacidad -1 o 0,1 TB toman la única capacidad válida de su modelo.",
                 "regla_documentada", "regla documentada: reglas de negocio §3", "R-005", n_antes, n_despues, "filas con capacidad -1 o 0,1 TB")
        corr("C-07", "recuento_diario", "(fila)", "Las filas que quedan con la misma clave (fecha, modelo, capacidad y centro) se suman en una: discos y fallos.",
             "regla_documentada", "regla documentada: reglas de negocio §3, con el orden de la petición 07 (nombre, capacidad y suma)",
             "R-006", len(rec_raw), len(df), "filas")
        corr(dec["fecha_y_texto"]["problema_calidad"], "ventanas_fallo", "(fila)",
             "Salen las filas cuya fecha no es la de su texto: traen las horas encendido del día siguiente y no tienen datos propios.",
             "responsable", "responsable: la petición 07 resuelve P-01; quitarlas no cambia ninguna respuesta (las instrucciones del caso, «Datos que no sirven o están mal»; criterios.md §2)",
             "R-007", antes["ventanas_fallo"]["filas"], sal_v["filas"], "filas")
        corr(None, "fotos_mensuales", "(fichero)", f"Las {fmt(af['ficheros'])} fotos mensuales se juntan en un solo Parquet con las "
             f"{fmt(sal_f['columnas'])} columnas que trae alguna; donde una pieza no trae una columna, queda vacía.",
             "responsable", "responsable: la petición 07 y metodo/como_estan_organizados_los_datos.md (las filas son las mismas: solo cambia el fichero)",
             "R-008", af["ficheros"], 1, "ficheros")
        corr(None, "ventanas_fallo", "(fichero)", f"Las {fmt(av['ficheros'])} ventanas se juntan en un solo Parquet con las "
             f"{fmt(sal_v['columnas'])} columnas que trae alguna; donde una pieza no trae una columna, queda vacía.",
             "responsable", "responsable: la petición 07 y metodo/como_estan_organizados_los_datos.md", "R-008", av["ficheros"], 1, "ficheros")
        r["correcciones"] = C

        # 11.8 Lo que se deja sin cambios, con su motivo, y lo que decidió el responsable
        valores_motivo = {"cambios_modelo": fmt(cambios_despues["modelo"]), "cambios_capacidad": fmt(cambios_despues["capacidad"]),
                          "sin_dia_antes": fmt(sin_dia["antes"]), "sin_dia_despues": fmt(sin_dia["despues"])}
        resultado_calidad = {p["id"]: p.get("resultado", "") for p in cal["problemas"]}
        r["sin_cambios"] = [{"problema_calidad": s["problema_calidad"], "resultado_calidad": resultado_calidad.get(s["problema_calidad"], ""),
                             "motivo": s["motivo"].format(**valores_motivo)} for s in dec["sin_cambios"]]
        r["variantes_fuera_del_mapeo"] = fuera_mapeo
        r["tipos_sin_cambiar"] = ("Los contadores (smart_N_raw y smart_N_normalized) siguen como decimales: la petición 07 nombra como "
                                  "correcciones de tipo solo el centro, la ranura y las fechas, y un decimal es un tipo válido para una "
                                  "magnitud. La calidad los marcó como «toca entero» sin abrir ningún problema; si se quieren enteros, "
                                  "es una decisión para el paso siguiente.")
        fy = dec["fecha_y_texto"]
        r["decisiones_responsable"] = [
            {"pendiente": fy["pendiente"], "decision": fy["decision"], "quien": "El responsable del caso, con la petición 07", "fecha": fecha_ejecucion[:10], "fuente": fy["fuente"]},
            {"pendiente": dec["modelos"]["decision"], "decision": dec["modelos"]["texto"], "quien": "El responsable del caso", "fecha": "2026-11-17",
             "fuente": "informes/plan_calidad_datos.md, «Lo aprobado»"},
            {"pendiente": "tipos de fecha", "decision": "las fechas como fecha: el texto date pasa a fecha", "quien": "El responsable del caso, con la petición 07",
             "fecha": "2026-11-17", "fuente": PETICION},
            {"pendiente": "juntar las piezas", "decision": "las 66 fotos en un Parquet y las 22 ventanas en otro, con todas las columnas",
             "quien": "El responsable del caso, con la petición 07", "fecha": "2026-11-17", "fuente": f"{PETICION}; config/metodo/como_estan_organizados_los_datos.md"},
        ]

        # 11.9 Sumas de control, métricas y controles
        r["sumas_control"] = []
        for m in magnitudes:
            r["sumas_control"].append({"tabla": "recuento_diario", "columna": m, "via": "pandas, en memoria", "antes": via1[m][0],
                                       "despues": via1[m][1], "coincide": via1[m][0] == via1[m][1]})
            r["sumas_control"].append({"tabla": "recuento_diario", "columna": m, "via": "pyarrow, sobre los ficheros en disco", "antes": via2[m][0],
                                       "despues": via2[m][1], "coincide": via2[m][0] == via2[m][1]})
        for tabla, tot in (("fotos_mensuales", tot_f), ("ventanas_fallo", tot_v)):
            for c in ("failure", "smart_9_raw"):
                r["sumas_control"].append({"tabla": tabla, "columna": c, "via": "pyarrow, pieza a pieza, en las filas que se quedan",
                                           "antes": tot["sumas_antes"][c], "despues": tot["sumas_despues"][c],
                                           "coincide": tot["sumas_antes"][c] == tot["sumas_despues"][c]})
        r["metricas"] = [
            {"tabla": "fotos_mensuales", "filas_antes": af["filas"], "filas_despues": sal_f["filas"], "capacidad_no_valida_antes": af["capacidad_no_valida"],
             "capacidad_no_valida_despues": sal_f["capacidad_no_valida"], "modelos_dos_espacios_antes": len(af["modelos_dos_espacios"]),
             "modelos_dos_espacios_despues": len(sal_f["modelos_dos_espacios"])},
            {"tabla": "ventanas_fallo", "filas_antes": av["filas"], "filas_despues": sal_v["filas"], "capacidad_no_valida_antes": av["capacidad_no_valida"],
             "capacidad_no_valida_despues": sal_v["capacidad_no_valida"], "modelos_dos_espacios_antes": len(av["modelos_dos_espacios"]),
             "modelos_dos_espacios_despues": len(sal_v["modelos_dos_espacios"])},
            {"tabla": "recuento_diario", "filas_antes": len(rec_raw), "filas_despues": len(df),
             "capacidad_no_valida_antes": int((rec_raw["capacity_bytes"] < minimo).sum()), "capacidad_no_valida_despues": int((df["capacity_bytes"] < minimo).sum()),
             "modelos_dos_espacios_antes": len({m for m in rec_raw["model"].unique() if "  " in m}), "modelos_dos_espacios_despues": len(rec_modelos_d)},
            {"tabla": "fallos", "filas_antes": len(fal_raw), "filas_despues": fal_d, "capacidad_no_valida_antes": None,
             "capacidad_no_valida_despues": None, "modelos_dos_espacios_antes": None, "modelos_dos_espacios_despues": None},
        ]
        r["controles"] = {
            "fotos.ficheros": af["ficheros"], "ventanas.ficheros": av["ficheros"],
            "fotos.filas": {"antes": af["filas"], "despues": sal_f["filas"]},
            "ventanas.filas": {"antes": av["filas"], "despues": sal_v["filas"]},
            "recuento.filas": {"antes": len(rec_raw), "despues": len(df)},
            "fallos.filas": {"antes": len(fal_raw), "despues": fal_d},
            "fotos.capacidad_no_valida": {"antes": af["capacidad_no_valida"], "despues": sal_f["capacidad_no_valida"]},
            "ventanas.capacidad_no_valida": {"antes": av["capacidad_no_valida"], "despues": sal_v["capacidad_no_valida"]},
            "recuento.capacidad_no_valida": {"antes": int((rec_raw["capacity_bytes"] < minimo).sum()), "despues": int((df["capacity_bytes"] < minimo).sum())},
            "recuento.discos": {"antes": via1["discos"][0], "despues": via1["discos"][1]},
            "recuento.fallos": {"antes": via1["fallos"][0], "despues": via1["fallos"][1]},
            "modelos_dos_espacios": {"antes": len(modelos_antes), "despues": len(modelos_despues)},
            "fotos.modelos_dos_espacios": {"antes": len(af["modelos_dos_espacios"]), "despues": len(sal_f["modelos_dos_espacios"])},
            "ventanas.modelos_dos_espacios": {"antes": len(av["modelos_dos_espacios"]), "despues": len(sal_v["modelos_dos_espacios"])},
            "recuento.modelos_dos_espacios": {"antes": len({m for m in rec_raw["model"].unique() if "  " in m}), "despues": len(rec_modelos_d)},
            "ventanas.fallos_datos_sin_dia_anterior": sin_dia,
            "ventanas.filas_quitadas": len(quitadas),
            "ventanas.fechas_quitadas": sorted({f.date().isoformat() for f in quitadas["fecha"]}),
            "ventanas.textos_de_las_quitadas": sorted(set(quitadas["date"])),
            "fotos.cambios_de_modelo": {"antes": cambios_antes["modelo"], "despues": cambios_despues["modelo"]},
            "fotos.cambios_de_capacidad": {"antes": cambios_antes["capacidad"], "despues": cambios_despues["capacidad"]},
            "modelos_con_dos_capacidades_validas": len(varias),
            "modelos_con_capacidad": len(capacidad_modelo),
            "filas_modelo_cambiadas": {"fotos": tot_f["modelo"], "ventanas": tot_v["modelo"], "recuento": r_modelo},
        }

        # 11.10 Las cuatro comprobaciones del dataset procesado (método, apartado 4.4)
        ok = {v["comprobacion"]: v["ok"] for v in validacion}
        completitud = ok["fotos: las mismas filas a la entrada y a la salida"] and ok["ventanas: salen solo las filas cuya fecha no es la de su texto, ninguna con un fallo"] \
            and ok["lista de fallos: las mismas filas"] and ok["recuento: discos y fallos suman lo mismo por las dos vías"]
        consistencia = ok["ninguna capacidad -1 o 0,1 TB después"] and ok["ningún modelo del mapeo queda con dos espacios"] \
            and ok["tipos de salida: centro texto, ranura entera y date fecha"] and ok["recuento: la clave queda única"]
        utilidad = ok["recuento: discos y fallos de cada día suman lo mismo"] and ok["los fallos de fotos y ventanas se conservan"] \
            and ok["ningún vacío nuevo ni rellenado en fotos y ventanas"]
        r["comprobaciones"] = {"completitud": "pasa" if completitud else "no pasa", "consistencia": "pasa" if consistencia else "no pasa",
                               "utilidad": "pasa" if utilidad else "no pasa", "datos_personales": "pasa" if not personales else "no pasa"}

        # 11.11 Diccionario de cada salida y huella de data/raw/ al terminar
        t6 = time.time()
        nombres_salida = {"fotos_mensuales": (sal_f["filas"], sal_f["columnas"]), "ventanas_fallo": (sal_v["filas"], sal_v["columnas"]),
                          "recuento_diario": (len(df), len(esquema_rec.names)), "fallos": (fal_d, 2)}
        for tabla in TABLAS:
            r["salidas"].append({"tabla": tabla, "ruta": SALIDA[tabla], "sha256": sha256(parciales[tabla]), "filas": nombres_salida[tabla][0],
                                 "columnas": nombres_salida[tabla][1],
                                 "campos_salida": diccionario_salida(parciales[tabla], reglas_por_columna.get(tabla, {}))})
        for s in r["salidas"]:
            for c in s["campos_salida"]:
                if s["tabla"] == "recuento_diario" and c["columna"] == "datacenter":
                    c["nota"] = (f"«{dec['etiqueta_sin_dato']['valor']}» quiere decir que el centro no consta (reglas, apartado 4 y §5); "
                                 "es la etiqueta del vacío en una categórica de correccion-datos")
        tiempos["diccionario de las salidas"] = round(time.time() - t6, 1)
        huella_fin = huellas(raw)
        validacion.append({"comprobacion": "data/raw intacto: la misma huella al empezar y al terminar", "ok": huella_fin == huella_inicio})
        r["validacion"] = validacion

        # 11.12 Estado: solo se publican los datasets si todas las comprobaciones pasan
        fallan = [v["comprobacion"] for v in validacion if not v["ok"]]
        if fallan:
            raise ErrorDeRegla("no pasan estas comprobaciones: " + "; ".join(fallan))
        for tabla in TABLAS:
            parciales[tabla].replace(raiz / SALIDA[tabla])
        r["huella_raw"] = {"ficheros": len(huella_fin), "iguales_al_empezar_y_al_terminar": huella_fin == huella_inicio}
        r["datos_personales_texto"] += [
            "Ninguna columna de los datos tiene el papel de dato personal en el diccionario del origen. El número de serie identifica un disco, no a una persona.",
            f"Antes de corregir se buscaron correos, documentos de identidad, cuentas bancarias y teléfonos en los textos (número de serie, "
            f"modelo y centro): {len(personales)} columnas con alguno.",
            "Este método no usa ni deja ninguna columna de datos personales."]
        r["limites"] += [
            "No se repite aquí el diagnóstico completo sobre las tablas corregidas (manual 8.10, paso 1); se comprueban las cifras de "
            "cada corrección, los vacíos y las sumas.",
            "Las cifras de los motivos de C-18 y C-26 son las de la petición 07 y no se vuelven a medir en esta ejecución.",
            "Los contadores siguen como decimales (ver «Elementos mantenidos sin cambios»).",
            "Las fechas fecha y dia_fallo ya llegan como fecha y no se cambian; date pasa a fecha con la misma precisión que fecha.",
        ]
        r["ejecucion"] = {"python": platform.python_version(), "pandas": pd.__version__, "pyarrow": pa.__version__, "numpy": np.__version__,
                          "segundos_por_parte": tiempos}
        estado = "AVISO" if r["sin_cambios"] or r["pendientes"] else "OK"
        r["resultado"] = {"estado": estado, "riesgo": "medio" if estado == "AVISO" else "bajo",
                          "resumen": (f"Los cuatro datasets corregidos, uno por tabla en data/processed/: {len(C)} correcciones con cambio y "
                                      f"{len(r['sin_cambios'])} problemas que se dejan como están, con su motivo, para que los lea el método "
                                      f"siguiente. Ningún vacío rellenado y ninguna fila perdida sin explicar."),
                          "artefactos": [SALIDA[t] for t in TABLAS] + ["informes/correccion-datos.json", "informes/correccion-datos.md",
                                                                       "config/modelo/registro-transformaciones.md"],
                          "siguiente": "modelado-datos: el diseño del modelo de datos, que aprueba el responsable del caso"}

        # 11.13 Registro de transformaciones: una ficha por regla que cambió algo y una por lo que no se toca
        r["fichas_nuevas"] = escribir_registro(raiz, fichas_del_registro(r, dec, fecha_ejecucion[:10]))
        tiempos["total"] = round(time.time() - t0, 1)
        return r
    except (ParadaDeRegla, ErrorDeRegla) as e:
        for p in parciales.values():
            if p.exists():
                p.unlink()
        r["resultado"] = {"estado": "PARADO" if isinstance(e, ParadaDeRegla) else "ERROR", "riesgo": "alto", "resumen": str(e),
                          "artefactos": ["informes/correccion-datos.json", "informes/correccion-datos.md"],
                          "siguiente": "resolver lo que dice el resumen y volver a ejecutar la corrección"}
        r["correcciones"], r["salidas"] = [], []
        return r


def fichas_del_registro(r, dec, fecha):
    """Las fichas del registro, con las cifras de esta ejecución; solo de las reglas que cambiaron algo."""
    ctl = r["controles"]
    por_ficha = {}
    for c in r["correcciones"]:
        por_ficha.setdefault(c["ficha"], []).append(c)
    resumen = lambda n: "; ".join(f"{NOMBRE_TABLA[c['tabla']]}, de {fmt(c['antes'])} a {fmt(c['despues'])} {c['unidad']}" for c in por_ficha[n])
    F = []
    if "R-001" in por_ficha:
        F.append(("R-001", ficha("R-001", "fotos mensuales y ventanas de fallo · datacenter", "en las piezas anteriores a julio de 2023 el centro "
                  "llega sin tipo (columna nula entera) y en las demás como texto.", "C-03: al juntar las piezas, el centro tiene que tener un solo tipo.",
                  "el centro es una categórica (diccionario del origen); técnicamente inequívoca.",
                  'columnas["datacenter"] = t["datacenter"].cast(pa.string(), safe=True)',
                  f"{resumen('R-001')}; los vacíos de la columna son los mismos antes y después.",
                  "datacenter es texto en las dos tablas; donde no consta, sigue vacío.", "volver a leer la columna con el tipo de cada pieza.", fecha)))
    if "R-002" in por_ficha:
        F.append(("R-002", ficha("R-002", "fotos mensuales y ventanas de fallo · pod_slot_num", "la ranura llega como decimal (38.0) porque trae vacíos.",
                  "C-04: un código de ranura no es un decimal.", "entero que admite vacío (petición 07): sus valores con dato son todos enteros.",
                  'columnas["pod_slot_num"] = t["pod_slot_num"].cast(pa.int64(), safe=True)  # falla si un valor no es entero',
                  f"{resumen('R-002')}; los vacíos son los mismos antes y después.", "pod_slot_num es int64 con vacíos.",
                  "volver a leerla como decimal.", fecha)))
    if "R-003" in por_ficha:
        F.append(("R-003", ficha("R-003", "fotos mensuales y ventanas de fallo · date", "date llega como texto AAAA-MM-DD; la columna fecha ya es fecha.",
                  "el rol de date en el diccionario es fecha.", "las fechas como fecha (petición 07).",
                  'fecha = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")  # para si algún texto no convierte\n'
                  'columnas["date"] = pa.array(fecha, type=pa.timestamp("ms"))',
                  f"{resumen('R-003')}; ningún texto quedó sin convertir.", "date es fecha, con la precisión de fecha.",
                  "volver a escribir la fecha como texto ISO.", fecha)))
    if "R-004" in por_ficha:
        mapeo = "; ".join(f"«{a}» → «{d}»" for a, d in dec["modelos"]["mapeo"].items())
        F.append(("R-004", ficha("R-004", "fotos mensuales, ventanas de fallo y recuento diario · model", f"cuatro modelos llegan también con dos espacios tras «WDC»: {mapeo}.",
                  "C-13: el mismo modelo escrito de dos formas parte en dos sus discos, sus días de disco y sus fallos.",
                  dec["modelos"]["texto"] + ".", 'df["model"] = df["model"].replace(mapeo)  # mapeo cerrado de decisiones-correccion.json',
                  f"{resumen('R-004')}. Filas cambiadas: fotos {fmt(ctl['filas_modelo_cambiadas']['fotos'])}, ventanas "
                  f"{fmt(ctl['filas_modelo_cambiadas']['ventanas'])}, recuento {fmt(ctl['filas_modelo_cambiadas']['recuento'])}.",
                  "ningún modelo del mapeo queda con dos espacios.", "aplicar el mapeo al revés en las filas que cambiaron, que se ven en data/raw/.", fecha)))
    if "R-005" in por_ficha:
        F.append(("R-005", ficha("R-005", "fotos mensuales, ventanas de fallo y recuento diario · capacity_bytes", "algunas filas traen -1 o 0,1 TB.",
                  "C-05, C-06 y C-07: son lecturas malas, y en el recuento parten una clave en dos.", dec["capacidad"]["regla"] + ".",
                  'mala = df["capacity_bytes"] < minimo  # 2e11 bytes, de decisiones-correccion.json\n'
                  'df.loc[mala, "capacity_bytes"] = df.loc[mala, "model"].map(capacidad_modelo)  # la única válida del modelo',
                  f"{resumen('R-005')}; {fmt(ctl['modelos_con_capacidad'])} modelos con capacidad y "
                  f"{fmt(ctl['modelos_con_dos_capacidades_validas'])} con dos capacidades válidas. No es un relleno: es la regla, apartado 3 para un valor que no es válido.",
                  "ninguna fila con -1 o 0,1 TB.", "poner -1 o 0,1 TB en las filas que cambiaron, que se ven en data/raw/.", fecha)))
    if "R-006" in por_ficha:
        F.append(("R-006", ficha("R-006", "recuento diario · fila", "tras corregir el nombre y la capacidad, varias filas comparten fecha, modelo, capacidad y centro.",
                  "C-07: la granularidad del recuento es una fila por clave.", dec["capacidad"]["recuento_regla"] + ".",
                  'df = df.groupby(["fecha", "model", "capacity_bytes", "datacenter"], sort=False, dropna=False, as_index=False)[["discos", "fallos"]].sum()',
                  f"{resumen('R-006')}. Discos {fmt(ctl['recuento.discos']['antes'])} y {fmt(ctl['recuento.discos']['despues'])}; fallos "
                  f"{fmt(ctl['recuento.fallos']['antes'])} y {fmt(ctl['recuento.fallos']['despues'])}, por dos vías y día a día.",
                  "la clave es única y las sumas no cambian.", "volver a leer el recuento de data/raw/ y aplicar solo R-004 y R-005.", fecha)))
    if "R-007" in por_ficha:
        F.append(("R-007", ficha("R-007", "ventanas de fallo · fila", f"{fmt(ctl['ventanas.filas_quitadas'])} filas con fecha "
                  f"{', '.join(ctl['ventanas.fechas_quitadas'])} dicen {', '.join(ctl['ventanas.textos_de_las_quitadas'])} en su texto y traen "
                  "las horas encendido de ese día.", "C-17 y P-01: no son datos de su fecha.", dec["fecha_y_texto"]["decision"] + ".",
                  'distinta = pd.to_datetime(df["date"], format="%Y-%m-%d") != df["fecha"]\nsalida = salida.filter(pa.array(~distinta))  # para si alguna trae un fallo',
                  f"{resumen('R-007')}, el {fmt(100 * ctl['ventanas.filas_quitadas'] / ctl['ventanas.filas']['antes'])} % de las filas, ninguna con un "
                  f"fallo. Los fallos de discos de datos sin el día anterior en su ventana pasan de "
                  f"{fmt(ctl['ventanas.fallos_datos_sin_dia_anterior']['antes'])} a {fmt(ctl['ventanas.fallos_datos_sin_dia_anterior']['despues'])}. "
                  "No cambian ninguna respuesta: el recuento de ese día se queda como está y no hay comparación entre grupos que dependa de ellas.",
                  "ninguna fila de las ventanas tiene la fecha distinta de su texto.", "volver a ejecutar sin la regla; las filas siguen en data/raw/.", fecha)))
    if "R-008" in por_ficha:
        F.append(("R-008", ficha("R-008", "fotos mensuales y ventanas de fallo · fichero", "cada tabla llega partida en piezas por tamaño, y las "
                  "piezas no traen todas las columnas.", "la petición 07 pide un fichero corregido por dataset.",
                  "juntar las piezas sin cambiar las filas (metodo/como_estan_organizados_los_datos.md).",
                  "with pq.ParquetWriter(destino, esquema_comun) as escritor:\n    for f in piezas:\n        escritor.write_table(corregir_pieza(pq.read_table(f), ...))",
                  f"{resumen('R-008')}. Las columnas que una pieza no trae quedan vacías en sus filas; no se rellena ninguna.",
                  "un Parquet por tabla en data/processed/.", "leer las piezas de data/raw/podado/.", fecha)))
    sin = "; ".join(f"{s['problema_calidad']}: {s['motivo']}" for s in r["sin_cambios"])
    F.append(("R-009", ficha("R-009", "las cuatro tablas · lo que se deja sin cambios", "el diagnóstico de calidad dejó 30 problemas.",
              f"{len(r['sin_cambios'])} de ellos no se corrigen.", sin + ".", "# ninguna regla: estos datos no se tocan",
              "las comprobaciones de vacíos y sumas de esta ejecución confirman que no cambian.", "como llegaron.",
              "no hay nada que deshacer.", fecha)))
    return F


def main():
    """Ejecuta la corrección, escribe el JSON y el informe, y sale con 1 si para o falla."""
    parser = argparse.ArgumentParser(description="Corrección de los cuatro datasets del caso 68")
    parser.add_argument("--raiz", type=Path, default=CASO, help="carpeta del caso (por defecto, la de este script)")
    raiz = parser.parse_args().raiz.resolve()
    print("sys.executable:", sys.executable)
    r = corregir(raiz)
    escribir_salidas_de_informe(raiz, r)
    print(f"estado: {r['resultado']['estado']} · {r['resultado']['resumen']}")
    if r.get("ejecucion"):
        print("segundos por parte:", json.dumps(r["ejecucion"]["segundos_por_parte"], ensure_ascii=False))
    sys.exit(0 if r["resultado"]["estado"] in ("OK", "AVISO") else 1)


if __name__ == "__main__":
    main()
