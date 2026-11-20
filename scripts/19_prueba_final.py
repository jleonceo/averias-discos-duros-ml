"""Prueba final del modelo de riesgo del caso 68 (petición 23, segunda parte; método preproduccion).

Dos modos, por argumento y sin valor por defecto:
  --ensayo-validacion  las fotos de data/raw/podado/fotos_mensuales/ de 2024-07 a 2025-06, los fallos de
                       data/raw/podado/fallos.parquet y el fin de periodo el 30/06/2025: los 12 meses se miden, con el
                       horizonte recortado como en el modelado. Compara en código con informes/modelado.json (los fallos
                       del modelo en las listas de 20 y de 100 de cada mes, las filas y los fallos de cada mes, el AUC del
                       modelo y el de la regla) y escribe informes/prueba_final_ensayo.json. Si una cifra difiere, ERROR.
  --reserva            el año guardado: las fotos de data/raw/reserva/fotos_mensuales/, los fallos de
                       data/raw/reserva/fallos.parquet y el fin de periodo el 30/06/2026; se miden las 11 fotos cuyo
                       horizonte no se recorta. Para con ERROR si informes/prueba_final_ensayo.json no está en OK con las
                       cifras iguales a modelado.json, y con PARADO, sin tocar nada, si el año guardado ya se midió.
                       Escribe informes/prueba_final.json, informes/prueba_final.md y
                       data/processed/fotos_riesgo_reserva.parquet, lo que lee produccion/reentrenar.py --medir.

En los dos, cada foto pasa por produccion/ejecutar.py (importado, su función principal) con el modelo en uso y la
historia de produccion/configuracion.json; en el ensayo, sin las carpetas del año guardado, que no se mira antes de la
prueba final. La salida de cada mes queda en data/predicciones/<hoy>/. Con la salida, la foto en bruto y la lista de
fallos se calcula el objetivo de cada fila puntuada (reglas de transformación §3), la regla de los cinco contadores y
las medidas: los fallos en las listas de 20, 100, 500 y 1.000 del modelo y de la regla en las mismas filas, el intervalo
de la diferencia en la de 100 (1.000 remuestreos de los meses, semilla 42), el AUC de todas las filas juntas, los fallos
en las marcas de ejecutar.py, la correlación de Matthews de la lista de 100 y los fallos en tomos donde acaba de fallar
un disco. Se da por bueno si el modelo encuentra más que la regla en la de 100, con el intervalo por encima de cero, y
su AUC es de 0,70 o más (guion §2; planteamientos 1.C). Se calcula, nunca se escribe.

No importa ningún script numerado: fallos_en_lista, claves_regla, rango_denso e intervalo_meses son copias de
scripts/15_modelado.py, letra a letra, y la prueba lo comprueba.

  --solo-informe       rehace informes/prueba_final.md, el resumen y los límites del JSON desde lo ya medido en el año
                       guardado, sin medir ni cambiar ninguna cifra (una nota del caso: el texto se corrigió después del examen).

Uso: python -W error scripts/19_prueba_final.py (--ensayo-validacion | --reserva | --solo-informe) [--raiz CARPETA_DEL_CASO] [--hoy AAAA-MM-DD]
Sale con 0 si termina en OK o AVISO, con 1 si da ERROR y con 2 si para (PARADO). Escribe el JSON también si falla,
salvo cuando el año guardado ya se midió: entonces no toca lo medido.
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
import traceback
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import sklearn
from sklearn.metrics import matthews_corrcoef

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "scripts"))
sys.path.insert(0, str(CASO / "assets"))
sys.path.insert(0, str(CASO / "produccion"))
import pipeline_riesgo as pr  # noqa: E402  (módulo de producción del caso)
import evaluacion_binaria as eb  # noqa: E402  (pieza común: el AUC, como lo midió el modelado)
import ejecutar  # noqa: E402  (produccion/ejecutar.py: su trabajo está bajo __main__)
from graficos import numero  # noqa: E402  (pieza común: números a la española, redondeo como Excel)

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
METODO = "preproduccion"
METODO_MD = "metodos/preproduccion/METODO.md"
SCRIPT = "scripts/19_prueba_final.py"
PETICION = "peticiones/23_prueba_final_y_reentreno.md, segunda parte"
CONFIGURACION = "produccion/configuracion.json"
MODELADO = "informes/modelado.json"
PROTECCION = "config/fuentes/proteccion-datos.json"
RAW, RESERVA = "data/raw", "data/raw/reserva"
TABLA_RESERVA = "data/processed/fotos_riesgo_reserva.parquet"
INFORME_MD = "informes/prueba_final.md"
OBJETIVO, FECHA, HORIZONTE = "falla_30d", "fecha", "horizonte_hasta"
CONTADORES, SUMA = "contadores_que_avisan", "suma_contadores_sin_188"

# Los dos modos (petición 23, «Lo que ya está decidido»; guion §2). horizonte_recortado: qué se hace con la foto cuyo
# horizonte pasa del fin del periodo: se mide recortado (ensayo, como el modelado) o no se mide (año guardado)
MODOS = {
    "ensayo": {"argumento": "--ensayo-validacion", "fotos": "data/raw/podado/fotos_mensuales", "fallos": "data/raw/podado/fallos.parquet",
               "fallos_tomos": ["data/raw/podado/fallos.parquet"], "desde": "2024-07", "hasta": "2025-06", "fin": "2025-06-30",
               "medidos": 12, "horizonte_recortado": "se mide recortado", "json": "informes/prueba_final_ensayo.json"},
    "reserva": {"argumento": "--reserva", "fotos": "data/raw/reserva/fotos_mensuales", "fallos": "data/raw/reserva/fallos.parquet",
                "fallos_tomos": ["data/raw/podado/fallos.parquet", "data/raw/reserva/fallos.parquet"], "desde": "2025-07",
                "hasta": "2026-06", "fin": "2026-06-30", "medidos": 11, "horizonte_recortado": "no se mide", "json": "informes/prueba_final.json"},
}
REGLA = "la regla de los cinco avisos SMART"  # el nombre que fijó el responsable del caso (vocabulario del lector, una nota del caso)
HORIZONTE_DIAS = 30            # reglas, apartado 7 y reglas de transformación §3: el objetivo mira 30 días
AUC_MINIMO = 0.70              # guion §2; planteamientos 1.C
SEMILLA, REMUESTREOS = 42, 1000  # el intervalo de la diferencia, remuestreando meses (como el modelado)
PARTE_TOMOS = Decimal("0.05")  # de las fotos en tomos en peligro de cada mes, el 5 % de más riesgo, al menos 1
LISTAS_DEL_MODELADO = (20, 100)
VENTANA_ANTES = 40             # días antes de la primera foto desde los que se buscan fallos para los tomos (plazo máximo 25)


class Parada(Exception):
    """Condición que impide seguir: `estado` es PARADO o ERROR; `escribir` dice si se escribe el JSON."""

    def __init__(self, mensaje, estado="ERROR", escribir=True):
        super().__init__(mensaje)
        self.estado = estado
        self.escribir = escribir


# =================================================================================================================
# 3. Las listas de N, la regla y el intervalo (copias de scripts/15_modelado.py, §3 y §10, letra a letra)
# =================================================================================================================
# Origen: scripts/15_modelado.py, fallos_en_lista (§3)
def fallos_en_lista(claves, y, n):
    """Fallos entre los N primeros, ordenando de mayor a menor por las claves (la primera manda). Si el puesto N cae
    dentro de un grupo empatado, se lleva de ese grupo fallos × plazas que quedan / filas del grupo."""
    claves = [np.asarray(k, dtype=float) for k in claves]
    y = np.asarray(y, dtype=float)
    orden = np.lexsort([-k for k in claves[::-1]])
    ks = [k[orden] for k in claves]
    ys = y[orden]
    cambio = np.ones(len(ys), dtype=bool)
    if len(ys) > 1:
        cambio[1:] = np.any([k[1:] != k[:-1] for k in ks], axis=0)
    inicio = np.flatnonzero(cambio)
    tam = np.diff(np.append(inicio, len(ys)))
    fal = np.add.reduceat(ys, inicio) if len(ys) else np.array([])
    quedan, total = n, 0.0
    for t, f in zip(tam, fal):
        toma = min(quedan, t)
        total += f * toma / t
        quedan -= toma
        if quedan <= 0:
            break
    return float(total)


# Origen: scripts/15_modelado.py, claves_regla (§3)
def claves_regla(df):
    """La regla de los cinco contadores: cuántos contadores avisan y, a igualdad, su suma sin el 188; vacía cuenta 0."""
    return [pd.to_numeric(df[CONTADORES]).to_numpy(dtype=float, na_value=0.0),
            pd.to_numeric(df[SUMA]).to_numpy(dtype=float, na_value=0.0)]


# Origen: scripts/15_modelado.py, rango_denso (§3)
def rango_denso(claves):
    """Una puntuación que ordena como las claves (más alta, más riesgo), para el AUC y el PR-AUC de la regla."""
    claves = [np.asarray(k, dtype=float) for k in claves]
    orden = np.lexsort(claves[::-1])
    ks = [k[orden] for k in claves]
    cambio = np.zeros(len(orden), dtype=float)
    if len(orden) > 1:
        cambio[1:] = np.any([k[1:] != k[:-1] for k in ks], axis=0)
    r = np.empty(len(orden))
    r[orden] = np.cumsum(cambio)
    return r


# Origen: scripts/15_modelado.py, intervalo_meses (§10)
def intervalo_meses(diferencias, remuestreos=REMUESTREOS, semilla=SEMILLA):
    """Intervalo de la media de las diferencias remuestreando meses enteros: percentiles 2,5 y 97,5."""
    d = np.asarray(diferencias, dtype=float)
    rng = np.random.default_rng(semilla)
    medias = d[rng.integers(0, len(d), size=(remuestreos, len(d)))].mean(axis=1)
    return {"medida": "fallos en la lista de 100, diferencia media por mes", "media": float(d.mean()),
            "bajo": float(np.percentile(medias, 2.5)), "alto": float(np.percentile(medias, 97.5)),
            "remuestreos": remuestreos, "semilla": semilla, "unidad": "mes", "unidades": int(len(d))}


# =================================================================================================================
# 4. El objetivo, el tomo y las comprobaciones (cada una calculada; la prueba las pone en rojo)
# =================================================================================================================
def horizonte(fecha, fin):
    """30 días después de la foto, recortado al último día del periodo (reglas de transformación §3)."""
    return min(pd.Timestamp(fecha) + pd.Timedelta(days=HORIZONTE_DIAS), pd.Timestamp(fin))


def objetivo(serial, fecha, hasta, fallos):
    """1 si el disco tiene algún fallo de la lista con dia_fallo del día siguiente a la foto a `hasta`, los dos
    incluidos (reglas de transformación §3); 0 si no. dia_fallo llega en milisegundos, como la fecha."""
    f = fallos.loc[((fallos["dia_fallo"] > fecha) & (fallos["dia_fallo"] <= hasta)).to_numpy()]
    return np.isin(np.asarray(serial, dtype=object), f["serial_number"].unique()).astype(np.int64)


def comprobar_objetivo(serial, fecha, hasta, fallos, y):
    """El objetivo por otro camino: el primer fallo de cada disco posterior a la foto, y si llega a `hasta`. Devuelve
    cuántas filas no coinciden con `y` (un fallo anterior o igual a la foto que cuenta da una)."""
    despues = fallos.loc[(fallos["dia_fallo"] > fecha).to_numpy()].groupby("serial_number")["dia_fallo"].min()
    primero = pd.Series(np.asarray(serial, dtype=object)).map(despues)
    otro = (primero.notna() & (primero <= hasta)).to_numpy().astype(np.int64)
    return int(np.sum(otro != np.asarray(y)))


def alineadas(salida, foto):
    """Cada fila de la salida tiene su fila de la foto: mismas filas, en el mismo orden y con el mismo serial_number."""
    return len(salida) == len(foto) and bool(np.array_equal(salida["serial_number"].astype(str).to_numpy(),
                                                            foto["serial_number"].astype(str).to_numpy()))


def meses_recortados(fechas, fin):
    """Las fotos medidas cuyo horizonte de 30 días pasa del fin del periodo (en el año guardado no se miden)."""
    return [pd.Timestamp(f).date().isoformat() for f in fechas
            if pd.Timestamp(f) + pd.Timedelta(days=HORIZONTE_DIAS) > pd.Timestamp(fin)]


def mismas_filas(filas_modelo, filas_regla):
    """El modelo y la regla se miden en las mismas filas, en el mismo orden."""
    return bool(np.array_equal(np.asarray(filas_modelo, dtype=object), np.asarray(filas_regla, dtype=object)))


def huellas(raiz):
    """La huella SHA-256 de cada fichero de data/raw/, por ruta."""
    salida = {}
    base = Path(raiz) / RAW
    for ruta in sorted(p for p in base.rglob("*") if p.is_file()):
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for trozo in iter(lambda: f.read(1 << 20), b""):
                h.update(trozo)
        salida[ruta.relative_to(base).as_posix()] = h.hexdigest()
    return salida


def sin_resultados_escritos(texto):
    """Error 24: ninguna validación lleva su resultado escrito, ni como clave con su sí o no ni asignada."""
    valor = "|".join(["Tr" + "ue", "Fal" + "se"])
    escrito = re.compile(r"""["'][\w ]+["']\s*:\s*(%s)\b|validaciones\[[^\]]+\]\s*=\s*(%s)\b""" % (valor, valor))
    return not escrito.search(texto)


def parte_de(fotos):
    """El 5 % de las fotos en tomos en peligro, redondeado con el medio hacia arriba y al menos 1; 0 si no hay ninguna."""
    if fotos == 0:
        return 0
    return max(1, int((PARTE_TOMOS * fotos).quantize(Decimal(1), rounding=ROUND_HALF_UP)))


def clave_tomo(centro, vault, ranura):
    """El tomo, centro + vault + ranura (reglas, apartado 4); vacío si falta alguno."""
    centro = pd.Series(centro, dtype=object).reset_index(drop=True)
    vault = pd.to_numeric(pd.Series(vault).reset_index(drop=True)).astype(float)
    ranura = pd.to_numeric(pd.Series(ranura).reset_index(drop=True)).astype(float)
    hay = (centro.notna() & vault.notna() & ranura.notna()).to_numpy()
    clave = np.full(len(centro), None, dtype=object)
    clave[hay] = [f"{c}|{v!r}|{r!r}" for c, v, r in zip(centro[hay], vault[hay], ranura[hay])]
    return clave


# =================================================================================================================
# 5. Lectura
# =================================================================================================================
def ruta_de(raiz, texto):
    """Una ruta absoluta, o relativa a la carpeta del caso."""
    p = Path(texto)
    return p if p.is_absolute() else Path(raiz) / p


def leer_fallos(rutas):
    """La lista de fallos en bruto de uno o varios ficheros, con dia_fallo en milisegundos, como la fecha de la foto."""
    partes = [pd.read_parquet(r, columns=["serial_number", "dia_fallo"]) for r in rutas]
    f = pd.concat(partes, ignore_index=True)
    f["dia_fallo"] = f["dia_fallo"].astype("datetime64[ms]")
    return f


def fotos_del_modo(raiz, m):
    """Las fotos del modo, AAAA-MM.parquet, del primer al último mes, en su orden; para si falta alguna."""
    meses = pd.period_range(m["desde"], m["hasta"], freq="M")
    carpeta = ruta_de(raiz, m["fotos"])
    fotos = [(str(p), carpeta / f"{p}.parquet") for p in meses]
    faltan = [f.name for _, f in fotos if not f.exists()]
    if faltan:
        raise Parada(f"faltan fotos del modo en {m['fotos']}: {faltan}")
    return fotos


def historia_del_modo(raiz, conf, modo):
    """Las carpetas de historia de la configuración; en el ensayo, sin las del año guardado."""
    salida = {}
    for clave in ("historia_fotos", "historia_ventanas"):
        valor = conf[clave]
        carpetas = [ruta_de(raiz, c) for c in ([valor] if isinstance(valor, str) else valor)]
        if modo == "ensayo":
            reserva = ruta_de(raiz, RESERVA).resolve()
            carpetas = [c for c in carpetas if not c.resolve().is_relative_to(reserva)]
        salida[clave] = carpetas
    return salida


def sitios_de_fallos(carpetas_ventanas, fallos, mapeo, minimo, desde, hasta):
    """Los fallos de discos de datos con su tomo y su plazo de reconstrucción, de dia_fallo entre `desde` y el día
    anterior a `hasta`.

    El sitio de un fallo es el de la última fila de su ventana hasta el día del fallo que trae centro, vault y ranura
    (reglas, apartado 5; reglas de transformación §4); la capacidad, la única válida de su modelo (reglas, apartado 3); el plazo, un día
    por TB más uno (reglas, apartado 5 y §7). Devuelve la tabla y lo que se queda fuera, contado.
    """
    columnas = ["serial_number", "fecha", "date", "dia_fallo", "model", "capacity_bytes", "datacenter", "vault_id", "pod_slot_num"]
    partes = []
    for ruta in [r for c in carpetas_ventanas for r in sorted(Path(c).glob("*.parquet"))]:
        v = pr._leer_columnas(ruta, columnas)
        partes.append(v.loc[((v["dia_fallo"] >= desde) & (v["dia_fallo"] < hasta)).to_numpy()])
    if not partes:
        raise Parada("no hay ninguna ventana de fallo en las carpetas de historia: no se puede saber el tomo de ningún fallo")
    v = pd.concat(partes, ignore_index=True)
    # Sin las filas copiadas del día siguiente (R-007): las que trae pr.ventanas_utiles con el día `hasta`
    v = pr.ventanas_utiles(v, hasta).copy()
    v["dia_fallo"] = v["dia_fallo"].astype("datetime64[ms]")
    v["model"] = v["model"].replace(mapeo)
    capacidad, _ = pr.capacidades_del_modelo(v[["model", "capacity_bytes"]], minimo)
    v["tomo"] = clave_tomo(v["datacenter"].to_numpy(), v["vault_id"].to_numpy(), v["pod_slot_num"].to_numpy())
    v = v.loc[(v["fecha"] <= v["dia_fallo"]).to_numpy()].sort_values(["serial_number", "dia_fallo", "fecha"], kind="stable")
    f = fallos.loc[((fallos["dia_fallo"] >= desde) & (fallos["dia_fallo"] < hasta)).to_numpy()].copy()
    # El modelo del fallo: el de la última fila de su ventana; el tomo: el de la última que lo trae
    ultima = v.groupby(["serial_number", "dia_fallo"])["model"].last()
    con_tomo = v.loc[pd.notna(v["tomo"]).to_numpy()].groupby(["serial_number", "dia_fallo"])["tomo"].last()
    claves = pd.MultiIndex.from_frame(f[["serial_number", "dia_fallo"]])
    f["model"] = ultima.reindex(claves).to_numpy()
    f["tomo"] = con_tomo.reindex(claves).to_numpy()
    f["capacidad"] = f["model"].map(capacidad)
    f["datos"] = (f["capacidad"] > pr.LIMITE_ARRANQUE_BYTES).to_numpy()
    f["plazo_dias"] = [pr.capacidad_en_tb(c) + 1 if pd.notna(c) else np.nan for c in f["capacidad"]]
    fuera = {"fallos": int(len(f)), "sin_ventana": int(f["model"].isna().sum()),
             "sin_capacidad": int((f["model"].notna() & f["capacidad"].isna()).sum()),
             "de_arranque": int((f["capacidad"].notna() & ~f["datos"]).sum()),
             "de_datos_sin_tomo": int((f["datos"] & pd.isna(f["tomo"])).sum())}
    utiles = f.loc[(f["datos"] & pd.notna(f["tomo"])).to_numpy(), ["serial_number", "dia_fallo", "tomo", "plazo_dias"]]
    fuera["de_datos_con_tomo"] = int(len(utiles))
    return utiles.reset_index(drop=True), fuera


def tomos_en_peligro(sitios, fecha):
    """Los tomos donde un disco de datos falló antes de la foto y dentro de su plazo; el último día del plazo ya no
    cuenta (reglas, apartado 7, «Fallos que coinciden en un tomo»)."""
    dias = (pd.Timestamp(fecha) - sitios["dia_fallo"]) / pd.Timedelta(days=1)
    return set(sitios.loc[((dias > 0) & (dias < sitios["plazo_dias"])).to_numpy(), "tomo"])


# =================================================================================================================
# 6. Medir un mes
# =================================================================================================================
def marcas_regla(serial, k, n):
    """La lista de N de la regla con el desempate por serial_number, como las marcas de ejecutar.py (para Matthews)."""
    orden = np.lexsort((np.asarray(serial, dtype=object), -k[1], -k[0]))
    m = np.zeros(len(serial), dtype=np.int64)
    m[orden[:n]] = 1
    return m


def medir_mes(foto, salida, sitio, fallos, sitios, fecha, fin, listas, principal):
    """Las cifras de un mes en las filas que ejecutar.py puntúa, y lo que hace falta para las del total."""
    if not alineadas(salida, foto):
        raise Parada(f"{fecha.date()}: la salida de ejecutar.py no tiene una fila por cada fila de la foto, en su orden")
    medida = salida["motivo"].isna().to_numpy()
    sin = salida.loc[~medida, "motivo"].value_counts()
    serial = foto["serial_number"].astype(str).to_numpy()[medida]
    hasta = horizonte(fecha, fin)
    y = objetivo(serial, fecha, hasta, fallos)
    p = salida["probabilidad"].to_numpy(dtype=float)[medida]
    # La regla, con los avisos de la foto en bruto (pr.avisos), en las mismas filas que el modelo
    avisos = pr.avisos(foto)
    filas_regla = avisos.index.to_numpy()[medida]
    k = claves_regla(avisos.loc[filas_regla])
    fila = {"mes": fecha.date().isoformat(), "horizonte_hasta": hasta.date().isoformat(),
            "filas_foto": int(len(foto)), "filas_medidas": int(medida.sum()), "fallos": int(y.sum()),
            "sin_puntuar": [{"motivo": str(m), "filas": int(c)} for m, c in sin.items()],
            "objetivo_distinto_por_otro_camino": comprobar_objetivo(serial, fecha, hasta, fallos, y),
            "mismas_filas": mismas_filas(serial, foto["serial_number"].astype(str).to_numpy()[filas_regla])}
    for n in listas:
        fila[f"modelo_lista_{n}"] = fallos_en_lista([p], y, n)
        fila[f"regla_lista_{n}"] = fallos_en_lista(k, y, n)
        marca = salida[f"en_lista_{n}"].to_numpy(dtype=float, na_value=np.nan)[medida]
        fila[f"modelo_marcas_lista_{n}"] = int(y[marca == 1].sum())
    # Tomos donde acaba de fallar un disco: el 5 % de más riesgo de sus fotos, por el modelo y por la regla
    tomo = clave_tomo(foto["datacenter"].to_numpy(), sitio["vault_id"].to_numpy(), sitio["pod_slot_num"].to_numpy())[medida]
    peligro = tomos_en_peligro(sitios, fecha)
    en = np.array([t is not None and t in peligro for t in tomo], dtype=bool)
    n_tomo = parte_de(int(en.sum()))
    fila["tomos"] = {"tomos_en_peligro": len(peligro), "fotos": int(en.sum()), "fallos": int(y[en].sum()), "lista": n_tomo,
                     "modelo": fallos_en_lista([p[en]], y[en], n_tomo), "regla": fallos_en_lista([k[0][en], k[1][en]], y[en], n_tomo)}
    marca = salida[f"en_lista_{principal}"].to_numpy(dtype=float, na_value=np.nan)[medida]
    datos = {"y": y, "p": p, "k0": k[0], "k1": k[1], "marca_modelo": (marca == 1).astype(np.int64),
             "marca_regla": marcas_regla(serial, k, principal), "medida": medida}
    return fila, datos


def totales(por_mes, listas):
    """Las sumas de los meses medidos."""
    medidos = [r for r in por_mes if r["se_mide"]]
    t = {"meses": len(medidos), "filas_medidas": sum(r["filas_medidas"] for r in medidos), "fallos": sum(r["fallos"] for r in medidos)}
    for n in listas:
        for quien in ("modelo", "regla", "modelo_marcas"):
            t[f"{quien}_lista_{n}"] = float(sum(r[f"{quien}_lista_{n}"] for r in medidos))
    t["tomos"] = {c: float(sum(r["tomos"][c] for r in medidos)) for c in ("fotos", "fallos", "lista", "modelo", "regla")}
    sin = {}
    for r in por_mes:
        for s in r.get("sin_puntuar", []):
            sin[s["motivo"]] = sin.get(s["motivo"], 0) + s["filas"]
    t["sin_puntuar"] = [{"motivo": k, "filas": v} for k, v in sin.items()]
    return t


# =================================================================================================================
# 7. Frente al modelado (ensayo) y la puerta del año guardado
# =================================================================================================================
def frente_al_modelado(res, modelado):
    """Las cifras del ensayo frente a las que guardó el modelado: cada mes (filas, fallos y los fallos del modelo en las
    listas de 20 y de 100) y el AUC del modelo y de la regla. Devuelve si son iguales y cuáles difieren."""
    v = modelado.get("validacion") or {}
    guardado = {r.get("mes"): r for r in v.get("por_mes", [])}
    medidos = [r for r in res["por_mes"] if r["se_mide"]]
    distintos = []
    if sorted(guardado) != [r["mes"] for r in medidos]:
        distintos.append(f"meses: guardados {sorted(guardado)}, medidos {[r['mes'] for r in medidos]}")
    for r in medidos:
        g = guardado.get(r["mes"], {})
        pares = [("filas", "filas_medidas"), ("fallos", "fallos")] + [(f"modelo_lista_{n}", f"modelo_lista_{n}") for n in LISTAS_DEL_MODELADO]
        for clave_g, clave_r in pares:
            if g.get(clave_g) != r[clave_r]:
                distintos.append(f"{r['mes']} {clave_g}: guardado {g.get(clave_g)}, medido {r[clave_r]}")
    auc_g = (v.get("medidas") or {}).get("auc")
    regla_g = ((v.get("referencias") or {}).get("regla") or {}).get("auc")
    if auc_g != res["auc"]["modelo"]["auc"]:
        distintos.append(f"AUC del modelo: guardado {auc_g}, medido {res['auc']['modelo']['auc']}")
    if regla_g != res["auc"]["regla"]["auc"]:
        distintos.append(f"AUC de la regla: guardado {regla_g}, medido {res['auc']['regla']['auc']}")
    return {"iguales": not distintos, "distintos": distintos}


def ensayo_listo(raiz, huella_modelado, huella_modelo):
    """None si informes/prueba_final_ensayo.json está en OK, igual al modelado de hoy y con el mismo modelo en uso;
    si no, el motivo."""
    ruta = ruta_de(raiz, MODOS["ensayo"]["json"])
    if not ruta.exists():
        return f"no existe {MODOS['ensayo']['json']}: primero el ensayo con la validación"
    js = json.loads(ruta.read_text(encoding="utf-8"))
    estado = (js.get("resultado") or {}).get("estado")
    comp = js.get("comparacion") or {}
    if estado != "OK" or comp.get("iguales") is not True:
        return f"el ensayo con la validación no está en OK con las cifras iguales a modelado.json (estado {estado})"
    if comp.get("huella_modelado") != huella_modelado:
        return "informes/modelado.json cambió después del ensayo"
    if (js.get("modelo_en_uso") or {}).get("huella") != huella_modelo:
        return "el modelo en uso no es el del ensayo"
    return None


# =================================================================================================================
# 8. El JSON y el informe
# =================================================================================================================
def a_json(v):
    """Pasa a tipos que JSON acepta, sin NaN."""
    if isinstance(v, dict):
        return {str(k): a_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [a_json(x) for x in v]
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) or np.isinf(v) else float(v)
    return v


def version_metodo(raiz):
    """La fecha y el código de la última línea de versión del METODO.md de el método (bloque común)."""
    texto = ruta_de(raiz, METODO_MD).read_text(encoding="utf-8") if ruta_de(raiz, METODO_MD).exists() else ""
    v = re.findall(r"^Versión (\d{2}/\d{2}/\d{4} \([A-Z]+-\d+\))", texto, flags=re.M)
    return v[-1] if v else None


def datos_personales(raiz):
    """El apartado «Datos personales» (bloque común, regla 6)."""
    if ruta_de(raiz, PROTECCION).exists():
        js = json.loads(ruta_de(raiz, PROTECCION).read_text(encoding="utf-8"))
        return f"Protección de datos según {PROTECCION}: {json.dumps(js, ensure_ascii=False)[:500]}"
    return (f"No existe {PROTECCION}: los datos no pasaron por la protección porque son de discos y no de personas "
            "(reglas, apartado 9). serial_number identifica un disco; esta prueba no usa ni deja ninguna columna de datos personales.")


def base(raiz, modo):
    """El diccionario del resultado, con el bloque común."""
    m = MODOS[modo]
    return {"metodo": METODO, "version_metodo": version_metodo(raiz), "script": SCRIPT, "peticion": PETICION, "modo": m["argumento"],
            "fecha_datos": m["fin"], "fecha_ejecucion": dt.datetime.now().isoformat(timespec="seconds"), "entradas": [],
            "resultado": {"estado": "ERROR", "riesgo": "alto", "resumen": "sin terminar", "artefactos": [m["json"]], "siguiente": ""},
            "pendientes": [], "periodo": {"desde": m["desde"], "hasta": m["hasta"], "fin": m["fin"], "meses_esperados": m["medidos"],
                                          "horizonte_recortado": m["horizonte_recortado"]},
            "por_mes": [], "validaciones": {}, "datos_personales": datos_personales(raiz)}


def escribir_json(raiz, modo, res):
    """Escribe el JSON del modo (bloque común, reglas 1, 2 y 5)."""
    ruta = ruta_de(raiz, MODOS[modo]["json"])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(a_json(res), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]


def mes_texto(iso):
    """«2025-07-01» como «julio de 2025»."""
    d = pd.Timestamp(iso)
    return f"{MESES[d.month - 1]} de {d.year}"


def cifra(x):
    """Un recuento de fallos para el informe: sin decimales si es entero; con dos si un empate repartido lo partió."""
    return numero(x) if float(x).is_integer() else numero(x, 2)


def motivo_texto(motivo):
    """El motivo de ejecutar.py para el lector: sin la cita del párrafo de las reglas y con mayúscula al empezar."""
    t = re.sub(r"\s*\([^)]*§[^)]*\)", "", str(motivo)).strip()
    return t[:1].upper() + t[1:]


def informe_md(res):
    """informes/prueba_final.md, generado del JSON (transmision-conocimiento): el veredicto, lo que lo sostiene, lo de
    al lado, los tomos, lo que no se midió, los datos personales, los límites y lo que se puede hacer ya. Ninguna frase
    lleva más de dos cifras, y la primera dice si el modelo se da por bueno."""
    i, a, t, n100 = res["intervalo"], res["auc"], res["totales"], res["lista_principal"]
    medidos = [r for r in res["por_mes"] if r["se_mide"]]
    fuera = [r for r in res["por_mes"] if not r["se_mide"]]
    if res["se_da_por_bueno"]:
        veredicto = (f"El modelo se da por bueno en el año guardado: en la lista de los {n100} discos de más riesgo de cada mes "
                     f"encuentra de media {numero(i['media'], 2)} fallos más que {REGLA}. "
                     f"El intervalo de esa diferencia va de {numero(i['bajo'], 2)} a {numero(i['alto'], 2)}, por encima de cero.")
    else:
        motivos = []
        if not (i["media"] > 0 and i["bajo"] > 0):
            motivos.append(f"En la lista de {n100}, la diferencia con {REGLA} es de {numero(i['media'], 2)} "
                           f"fallos al mes. Su intervalo, de {numero(i['bajo'], 2)} a {numero(i['alto'], 2)}, no queda por encima de cero.")
        if not a["modelo"]["auc"] >= AUC_MINIMO:
            motivos.append(f"Su AUC es {numero(a['modelo']['auc'], 3)}, por debajo del mínimo de {numero(AUC_MINIMO, 2)}.")
        veredicto = "El modelo no se da por bueno en el año guardado y lo decide el responsable del caso en la puerta 5. " + " ".join(motivos)
    L = ["# Prueba final del modelo de riesgo", "", veredicto, "",
         f"El listón era encontrar más fallos que la regla en la lista de {n100}, con el intervalo por encima de cero, y un AUC "
         f"de {numero(AUC_MINIMO, 2)} o más. Con todas las fotos medidas juntas, el AUC del modelo es "
         f"{numero(a['modelo']['auc'], 3)}. El de la regla es {numero(a['regla']['auc'], 3)}.", "",
         "## Lo que lo sostiene", "",
         f"Se midieron los meses de {mes_texto(medidos[0]['mes'])} a {mes_texto(medidos[-1]['mes'])}, con "
         f"{numero(t['filas_medidas'])} fotos de discos de datos. De ellas, {numero(t['fallos'])} tuvieron un fallo en los 30 "
         "días siguientes a la foto.", "",
         f"Cada mes, el modelo encontró de media {numero(t[f'modelo_lista_{n100}'] / t['meses'], 2)} fallos en su lista y la "
         f"regla, {numero(t[f'regla_lista_{n100}'] / t['meses'], 2)}. Los dos se midieron en las mismas fotos. El intervalo "
         "sale de remuestrear los meses mil veces.", "",
         f"| Mes | Fotos medidas | Fallos | Modelo, lista de {n100} | Regla, lista de {n100} | Modelo, lista de 20 | Regla, lista de 20 |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    L += [f"| {mes_texto(r['mes'])} | {numero(r['filas_medidas'])} | {numero(r['fallos'])} | {cifra(r[f'modelo_lista_{n100}'])} | "
          f"{cifra(r[f'regla_lista_{n100}'])} | {cifra(r['modelo_lista_20'])} | {cifra(r['regla_lista_20'])} |" for r in medidos]
    L += ["", "## Las medidas de al lado", "",
          "No deciden si el modelo se da por bueno. Son los fallos de todos los meses medidos, sumados. La última columna "
          "cuenta las marcas que da la puntuación de cada mes, que deshace los empates por número de serie.", "",
          "| Lista | Modelo | Regla | Marcas del modelo |", "|---:|---:|---:|---:|"]
    L += [f"| {n} | {cifra(t[f'modelo_lista_{n}'])} | {cifra(t[f'regla_lista_{n}'])} | {numero(t[f'modelo_marcas_lista_{n}'])} |"
          for n in res["listas"]]
    L += ["", f"Con todos los meses juntos, la correlación de Matthews de la lista de {n100} es {numero(res['matthews']['modelo'], 3)} "
          f"para el modelo. Para la regla es {numero(res['matthews']['regla'], 3)}.", "",
          "## Tomos donde acaba de fallar un disco", "",
          "Un tomo está en peligro mientras se reconstruye un disco de datos suyo que falló: un día por TB, más uno de espera. "
          f"En los meses medidos hubo {numero(t['tomos']['fotos'])} fotos en tomos en peligro. De ellas, "
          f"{numero(t['tomos']['fallos'])} tuvieron un fallo en sus 30 días.", "",
          f"Cada mes se miró el 5 % de esas fotos con más riesgo, {numero(t['tomos']['lista'])} fotos en total. Entre ellas, el "
          f"modelo encontró {cifra(t['tomos']['modelo'])} fallos y la regla, {cifra(t['tomos']['regla'])}.", "",
          "## Lo que no se midió", ""]
    L += [f"- {motivo_texto(s['motivo'])}. Son {numero(s['filas'])} fotos sin puntuar." for s in t["sin_puntuar"]]
    L += [f"- La foto de {mes_texto(r['mes'])}: su horizonte de 30 días acaba después del "
          f"{pd.Timestamp(res['periodo']['fin']).strftime('%d/%m/%Y')}, fuera del año guardado." for r in fuera]
    L += ["", "## Datos personales", "", res["datos_personales"], "", "## Límites", ""]
    L += [f"- {x}" for x in res["limites"]]
    L += ["", "## Lo que se puede hacer ya", ""]
    if not res["se_da_por_bueno"]:
        L += ["- el responsable del caso decide en la puerta 5 qué se hace con el modelo."]
    L += ["- Medir el reentreno con el año guardado: `produccion/reentrenar.py` con `--medir` sobre la tabla de este año. "
          "El reentreno no sustituye al modelo en uso: eso lo decide el responsable del caso."]
    return "\n".join(L) + "\n"


# =================================================================================================================
# 9. Principal
# =================================================================================================================
def medir(raiz, modo, hoy, res):
    """Ejecuta cada foto del modo con ejecutar.py, la mide y rellena `res`. Devuelve la ruta de la tabla del año
    guardado a medio escribir (solo existe en --reserva): principal() la pone en su sitio si todo pasa y si no la borra."""
    m = MODOS[modo]
    conf = json.loads(ruta_de(raiz, CONFIGURACION).read_text(encoding="utf-8"))
    contrato = pr.leer_contrato(raiz)
    dec = json.loads(ruta_de(raiz, conf["decisiones_correccion"]).read_text(encoding="utf-8"))
    mapeo, minimo = dec["modelos"]["mapeo"], dec["capacidad"]["minimo_valido_bytes"]
    listas, principal = list(conf["listas"]), conf["lista_principal"]
    ruta_modelo = ruta_de(raiz, conf["modelo_en_uso"])
    huella_modelado = pr.huella(ruta_de(raiz, MODELADO)) if ruta_de(raiz, MODELADO).exists() else None
    res["modelo_en_uso"] = {"ruta": conf["modelo_en_uso"], "huella": pr.huella(ruta_modelo)}
    res["listas"], res["lista_principal"] = listas, principal
    # 9.1 La puerta del año guardado: el ensayo en OK, con el mismo modelado y el mismo modelo en uso
    if modo == "reserva":
        motivo = ensayo_listo(raiz, huella_modelado, res["modelo_en_uso"]["huella"])
        if motivo:
            raise Parada(f"el año guardado no se abre: {motivo}")
    fotos = fotos_del_modo(raiz, m)
    historia = historia_del_modo(raiz, conf, modo)
    res["historia"] = {k: [str(c) for c in v] for k, v in historia.items()}
    fallos = leer_fallos([ruta_de(raiz, m["fallos"])])
    fin = pd.Timestamp(m["fin"])
    primera = pd.Timestamp(f"{m['desde']}-01")
    ultima = pd.Timestamp(f"{m['hasta']}-01")
    sitios, fuera = sitios_de_fallos(ejecutar.carpetas_de(raiz, historia["historia_ventanas"]),
                                     leer_fallos([ruta_de(raiz, r) for r in m["fallos_tomos"]]), mapeo, minimo,
                                     primera - pd.Timedelta(days=VENTANA_ANTES), ultima)
    res["tomos_fallos"] = fuera
    res["entradas"] = [{"ruta": m["fallos"], "sha256": pr.huella(ruta_de(raiz, m["fallos"])), "filas": int(len(fallos)), "columnas": 2}]
    pipe = pr.cargar_modelo(ruta_modelo)[0] if modo == "reserva" else None
    tabla_parcial = ruta_de(raiz, TABLA_RESERVA + ".parcial")
    escritor, esquema, tabla_igual, todo = None, None, [], {c: [] for c in ("y", "p", "k0", "k1", "marca_modelo", "marca_regla")}
    try:
        for mes, ruta in fotos:
            fecha = pd.Timestamp(f"{mes}-01")
            res["entradas"].append({"ruta": ruta.relative_to(raiz).as_posix() if ruta.is_relative_to(raiz) else str(ruta),
                                    "sha256": pr.huella(ruta), "filas": pq.read_metadata(ruta).num_rows, "columnas": pq.read_metadata(ruta).num_columns})
            # 9.2 La foto por ejecutar.py, con el modelo en uso y la historia; su salida queda en data/predicciones/<hoy>/
            args = argparse.Namespace(foto=str(ruta), mes=mes, modelo=None, fotos_anteriores=historia["historia_fotos"],
                                      ventanas=historia["historia_ventanas"], raiz=Path(raiz), hoy=hoy)
            resumen = ejecutar.principal(args)
            salida = pd.read_parquet(ruta_de(raiz, resumen["salida"]))
            foto = pr.leer_foto(ruta, contrato["entrada"])
            se_mide = m["horizonte_recortado"] == "se mide recortado" or not meses_recortados([fecha], fin)
            alineada = alineadas(salida, foto)
            if not se_mide:
                res["por_mes"].append({"mes": fecha.date().isoformat(), "se_mide": se_mide, "horizonte_hasta": horizonte(fecha, fin).date().isoformat(),
                                       "motivo": "el horizonte de 30 días pasa del fin del periodo", "filas_foto": int(len(foto)),
                                       "puntuadas": int(salida["probabilidad"].notna().sum()), "salida": resumen["salida"],
                                       "salida_alineada": alineada})
                continue
            # 9.3 El objetivo, la regla y las medidas del mes (medir_mes para si la salida no está alineada con la foto)
            sitio = pr._leer_columnas(ruta, ["vault_id", "pod_slot_num"])
            fila, datos = medir_mes(foto, salida, sitio, fallos, sitios, fecha, fin, listas, principal)
            fila.update({"se_mide": se_mide, "salida_alineada": alineada, "salida": resumen["salida"]})
            res["por_mes"].append(fila)
            for c in todo:
                todo[c].append(datos[c])
            # 9.4 Año guardado: las filas medidas con las columnas del contrato, que puntúan igual que la salida
            if modo == "reserva":
                h = ejecutar.leer_historia(ejecutar.carpetas_de(raiz, historia["historia_fotos"]),
                                           ejecutar.carpetas_de(raiz, historia["historia_ventanas"]), fecha, mapeo, set(foto["serial_number"]))
                df, motivo = pr.preparar_foto(foto, h, mapeo, minimo)
                medida = datos["medida"]
                tabla_igual.append(bool(np.array_equal(motivo == "", medida)) and bool(np.array_equal(
                    pipe.predict_proba(df.loc[medida, contrato["lee"]])[:, 1], salida["probabilidad"].to_numpy(dtype=float)[medida])))
                t = df.loc[medida, ["serial_number", FECHA, *contrato["lee"]]].reset_index(drop=True)
                t[HORIZONTE] = pd.Series([horizonte(fecha, fin)] * len(t), dtype="datetime64[ms]")
                t[OBJETIVO] = datos["y"]
                tt = pa.Table.from_pandas(t, preserve_index=False)
                if escritor is None:
                    esquema = tt.schema
                    tabla_parcial.parent.mkdir(parents=True, exist_ok=True)
                    escritor = pq.ParquetWriter(tabla_parcial, esquema)
                escritor.write_table(tt.cast(esquema), row_group_size=len(t))
    finally:
        if escritor is not None:
            escritor.close()
    # 9.5 Los totales, el intervalo, el AUC, Matthews y si se da por bueno
    medidos = [r for r in res["por_mes"] if r["se_mide"]]
    res["totales"] = totales(res["por_mes"], listas)
    y_all, p_all = np.concatenate(todo["y"]), np.concatenate(todo["p"])
    rr = rango_denso([np.concatenate(todo["k0"]), np.concatenate(todo["k1"])])
    res["auc"] = {"modelo": eb.medidas_globales(y_all, p_all), "regla": eb.medidas_globales(y_all, (rr + 1) / (rr.max() + 2))}
    res["intervalo"] = intervalo_meses([r[f"modelo_lista_{principal}"] - r[f"regla_lista_{principal}"] for r in medidos])
    res["matthews"] = {"lista": principal, "modelo": float(matthews_corrcoef(y_all, np.concatenate(todo["marca_modelo"]))),
                       "regla": float(matthews_corrcoef(y_all, np.concatenate(todo["marca_regla"]))),
                       "como": "las marcas de cada mes, todos los meses juntos; la regla, con el desempate por serial_number"}
    res["tomos"] = {"por_mes": [{"mes": r["mes"], **r["tomos"]} for r in medidos], "total": res["totales"]["tomos"], "fallos_de_la_lista": fuera,
                    "regla": "tomo = centro + vault + ranura; en peligro si un disco de datos suyo falló antes de la foto y hace menos "
                             "días que su plazo, capacidad en TB + 1; el 5 % de más riesgo de sus fotos medidas, redondeado y al menos 1"}
    i = res["intervalo"]
    res["se_da_por_bueno"] = bool(i["media"] > 0 and i["bajo"] > 0 and res["auc"]["modelo"]["auc"] >= AUC_MINIMO)
    res["frente_a"] = {"referencia": f"{REGLA}, en la lista de {principal} de cada mes y en las mismas fotos",
                       "criterio": f"más fallos que la regla con el intervalo de la diferencia por encima de cero y AUC de {AUC_MINIMO} o más",
                       "frente_a_la_regla": "supera" if i["bajo"] > 0 else ("no supera" if i["alto"] < 0 else "no se puede afirmar")}
    # 9.6 Las validaciones, calculadas
    v = res["validaciones"]
    v["filas_de_la_salida_con_su_foto"] = all(r["salida_alineada"] for r in res["por_mes"])
    v["objetivo_sin_fallos_anteriores"] = sum(r["objetivo_distinto_por_otro_camino"] for r in medidos) == 0
    v["sin_meses_recortados"] = (not meses_recortados([r["mes"] for r in medidos], fin)) if m["horizonte_recortado"] == "no se mide" else None
    v["meses_medidos_esperados"] = len(medidos) == m["medidos"]
    v["mismas_filas_modelo_y_regla"] = all(r["mismas_filas"] for r in medidos)
    v["sin_resultados_escritos"] = sin_resultados_escritos(Path(__file__).read_text(encoding="utf-8"))
    if modo == "ensayo":
        modelado = json.loads(ruta_de(raiz, MODELADO).read_text(encoding="utf-8")) if huella_modelado else {}
        res["comparacion"] = {**frente_al_modelado(res, modelado), "modelado": MODELADO, "huella_modelado": huella_modelado}
        v["igual_al_modelado"] = res["comparacion"]["iguales"]
    else:
        v["tabla_puntua_igual_que_la_salida"] = bool(tabla_igual) and all(tabla_igual)
    return tabla_parcial


def limites(res, modo):
    """Los límites del resultado, con sus cifras sacadas del JSON; ninguna frase con más de dos cifras."""
    f = res.get("tomos_fallos") or {}
    medidos_tomo = ((res.get("totales") or {}).get("tomos") or {}).get("fallos", 0)
    fuera = (f"Se quedan fuera de los tomos {numero(f.get('de_datos_sin_tomo', 0))} fallos de discos de datos cuya ventana no "
             "trae centro, vault y ranura.")
    if f.get("sin_ventana", 0):
        fuera += f" Otros {numero(f['sin_ventana'])} fallos de la lista no tienen ventana."
    L = [f"La medida de los tomos se apoya en {numero(medidos_tomo)} fallos en tomos en peligro, pocos para decidir con ellos.",
         fuera,
         "Para la correlación de Matthews, la lista de la regla deshace los empates por número de serie, igual que la del modelo.",
         "Las listas de cada mes reparten en proporción un empate en el último puesto, como en el modelado. Las marcas de la "
         "puntuación de cada mes lo deshacen por número de serie."]
    if modo == "reserva":
        # Auditor antes de entregar (20/11/2026, una nota del caso): decía que el modelo en uso no se volvió a elegir con el año
        # guardado, y el reentreno que se usa hoy se aprobó después de medirlo en él
        L.append("El modelo examinado aquí no se volvió a elegir ni a ajustar con nada del año guardado. El que se usa hoy, "
                 "reentrenado con un año más de datos, se midió en este año antes de aprobarlo: para él no es una prueba "
                 "independiente.")
    return L


def principal(raiz, modo, hoy):
    """Un modo entero; escribe el JSON (y, en el año guardado, el informe y la tabla). Devuelve el código de salida."""
    raiz = Path(raiz).resolve()
    m = MODOS[modo]
    # El año guardado se mide una vez: si ya hay una medida terminada, no se toca
    previo = ruta_de(raiz, m["json"])
    if modo == "reserva" and previo.exists() and (json.loads(previo.read_text(encoding="utf-8")).get("resultado") or {}).get("estado") in ("OK", "AVISO"):
        print(f"PARADO: el año guardado ya se midió ({m['json']}); no se vuelve a medir", file=sys.stderr)
        return 2
    res = base(raiz, modo)
    antes = huellas(raiz)
    tabla_parcial = None
    try:
        tabla_parcial = medir(raiz, modo, hoy, res)
        res["validaciones"]["huella_de_data_raw_igual"] = huellas(raiz) == antes
        res["limites"] = limites(res, modo)
        rojas = [k for k, x in res["validaciones"].items() if x is False]
        if rojas:
            detalle = "; ".join((res.get("comparacion") or {}).get("distintos", [])[:12])
            raise Parada(f"validaciones en rojo: {', '.join(rojas)}" + (f". Difiere: {detalle}" if detalle else ""))
        if modo == "reserva":
            tabla_parcial.replace(ruta_de(raiz, TABLA_RESERVA))
            res["resultado"] = {"estado": "OK" if res["se_da_por_bueno"] else "AVISO", "riesgo": "bajo" if res["se_da_por_bueno"] else "alto",
                                "resumen": informe_md(res).split("\n")[2],
                                "artefactos": [m["json"], INFORME_MD, TABLA_RESERVA, f"data/predicciones/{hoy}/"],
                                "siguiente": "produccion/reentrenar.py --tabla data/processed/fotos_riesgo.parquet --fecha 2025-07-01 "
                                             f"--medir {TABLA_RESERVA}"}
            if not res["se_da_por_bueno"]:
                res["pendientes"] = [{"id": "P-01", "tabla": TABLA_RESERVA, "columna": "",
                                      "pregunta": "El modelo no se da por bueno en el año guardado: qué se hace con él (puerta 5)",
                                      "opciones": ["lo decide el responsable del caso"]}]
            ruta_de(raiz, INFORME_MD).write_text(informe_md(res), encoding="utf-8")
        else:
            res["resultado"] = {"estado": "OK", "riesgo": "bajo",
                                "resumen": (f"El ensayo con la validación da las mismas cifras que modelado.json en los {res['totales']['meses']} "
                                            "meses: el año guardado se puede abrir con --reserva."),
                                "artefactos": [m["json"], f"data/predicciones/{hoy}/"], "siguiente": "scripts/19_prueba_final.py --reserva"}
        codigo = 0
    except (Parada, pr.ErrorDeProduccion) as e:
        estado = getattr(e, "estado", "ERROR")
        res["resultado"] = {"estado": estado, "riesgo": "alto", "resumen": f"El script paró: {e}"[:3000],
                            "artefactos": [m["json"]], "siguiente": "resolver la causa y volver a ejecutar"}
        codigo = 2 if estado == "PARADO" else 1
    except Exception as e:  # noqa: BLE001 - el JSON se escribe también cuando falla (bloque común, regla 5)
        res["resultado"] = {"estado": "ERROR", "riesgo": "alto", "resumen": f"{type(e).__name__}: {e}"[:3000],
                            "artefactos": [m["json"]], "siguiente": "corregir el fallo y volver a ejecutar"}
        res["traza"] = traceback.format_exc()[-3000:]
        codigo = 1
    if codigo != 0 and tabla_parcial is not None and tabla_parcial.exists():
        tabla_parcial.unlink()
    res["parametros"] = [{"nombre": "modo", "valor": m["argumento"], "origen": "argumento"},
                         {"nombre": "periodo", "valor": f"{m['desde']} a {m['hasta']}, fin {m['fin']}", "origen": "petición 23; guion §2"},
                         {"nombre": "horizonte", "valor": HORIZONTE_DIAS, "origen": "reglas, apartado 7; reglas de transformación §3"},
                         {"nombre": "listas", "valor": res.get("listas"), "origen": CONFIGURACION},
                         {"nombre": "AUC mínimo", "valor": AUC_MINIMO, "origen": "guion §2; planteamientos 1.C"},
                         {"nombre": "remuestreos y semilla", "valor": f"{REMUESTREOS}, {SEMILLA}", "origen": "petición 23; scripts/15_modelado.py"},
                         {"nombre": "parte de las fotos en tomos en peligro", "valor": str(PARTE_TOMOS), "origen": "petición 23"}]
    res["ejecucion"] = {"python": platform.python_version(), "ejecutable": sys.executable, "pandas": pd.__version__,
                        "pyarrow": pa.__version__, "scikit_learn": sklearn.__version__}
    escribir_json(raiz, modo, res)
    print(f"{res['resultado']['estado']}: {res['resultado']['resumen']}")
    return codigo


def solo_informe(raiz):
    """Rehace informes/prueba_final.md, el resumen y los límites de prueba_final.json desde lo ya medido, sin volver a
    medir ni tocar ninguna cifra (el año guardado se mira una vez). Devuelve el código de salida."""
    raiz = Path(raiz).resolve()
    ruta = ruta_de(raiz, MODOS["reserva"]["json"])
    res = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if (res.get("resultado") or {}).get("estado") not in ("OK", "AVISO"):
        print(f"PARADO: no hay un año guardado medido en {MODOS['reserva']['json']}", file=sys.stderr)
        return 2
    res["limites"] = limites(res, "reserva")
    res["frente_a"]["referencia"] = f"{REGLA}, en la lista de {res['lista_principal']} de cada mes y en las mismas fotos"
    texto = informe_md(res)
    res["resultado"]["resumen"] = texto.split("\n")[2]
    ruta_de(raiz, INFORME_MD).write_text(texto, encoding="utf-8")
    escribir_json(raiz, "reserva", res)
    print(f"{res['resultado']['estado']}: informe rehecho desde lo medido, sin medir")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Prueba final del modelo de riesgo: el ensayo con la validación o el año guardado")
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--ensayo-validacion", action="store_true", help="ensayo con la validación, comparado con modelado.json")
    modo.add_argument("--reserva", action="store_true", help="el año guardado, una sola vez y con el ensayo en OK")
    modo.add_argument("--solo-informe", action="store_true", help="rehace el informe del año guardado desde su JSON, sin medir")
    ap.add_argument("--raiz", default=str(CASO), help="carpeta del caso (por defecto, la del script)")
    ap.add_argument("--hoy", default=dt.date.today().isoformat(), help="carpeta del día de las predicciones")
    a = ap.parse_args()
    print(f"sys.executable: {sys.executable}")
    if a.solo_informe:
        sys.exit(solo_informe(Path(a.raiz)))
    sys.exit(principal(Path(a.raiz), "reserva" if a.reserva else "ensayo", a.hoy))
