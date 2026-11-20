"""Prueba de que la reserva del caso 68 está apartada (permiso del responsable del caso, 17/11/2026: «Sí, apártala»).

Uso: python -I probar_reserva.py <poda entera> <trabajo> <reserva>

Comprueba, en las cuatro partes de la poda (fotos, recuento diario, fallos y ventanas):
- que trabajo y reserva suman las filas de la poda entera, sin perder ni repetir ninguna;
- que en el trabajo no hay nada del 01/07/2025 en adelante, y en la reserva nada de antes.
Las fotos y el recuento se parten por su fecha; los fallos y las ventanas, por el día del fallo.
Control que tiene que fallar: una fila de la reserva metida en el trabajo.
Sale con 1 si falla alguna comprobación.
"""
import sys
from pathlib import Path

import pandas as pd

CORTE = pd.Timestamp("2025-07-01")
ENTERA, TRABAJO, RESERVA = (Path(a) for a in sys.argv[1:4])
fallan = 0


def mira(nombre, bien, detalle=""):
    global fallan
    fallan += not bien
    print(f"{'PASA ' if bien else 'FALLA'} · {nombre}: {detalle}")


COLUMNAS = {"fotos_mensuales": ["serial_number"], "ventanas_fallo": ["serial_number", "dia_fallo"]}


def leer(carpeta, parte):
    """Solo las columnas que hacen falta para contar filas y fechas: las 78 fotos enteras no caben en memoria."""
    ruta = carpeta / parte
    cols = COLUMNAS.get(parte)
    if ruta.is_dir():
        ficheros = sorted(ruta.glob("*.parquet"))
        if not ficheros:
            return pd.DataFrame()
        return pd.concat([pd.read_parquet(f, columns=cols).assign(_fichero=f.stem) for f in ficheros], ignore_index=True)
    return pd.read_parquet(ruta) if ruta.exists() else pd.DataFrame()


def fecha_de(parte, d):
    if parte == "fotos_mensuales":
        return pd.to_datetime(d["_fichero"] + "-01")
    if parte == "recuento_diario.parquet":
        return d["fecha"]
    return d["dia_fallo"]


def comprobar(parte, entera, trabajo, reserva):
    mira(f"{parte}, filas", len(trabajo) + len(reserva) == len(entera),
         f"{len(trabajo):,} + {len(reserva):,} frente a {len(entera):,}")
    ft = fecha_de(parte, trabajo) if len(trabajo) else pd.Series(dtype="datetime64[ns]")
    fr = fecha_de(parte, reserva) if len(reserva) else pd.Series(dtype="datetime64[ns]")
    mira(f"{parte}, trabajo antes del corte", len(ft) > 0 and (ft < CORTE).all(), f"último {ft.max()}")
    mira(f"{parte}, reserva desde el corte", len(fr) > 0 and (fr >= CORTE).all(), f"primero {fr.min()}")
    return ft


for parte in ["fotos_mensuales", "recuento_diario.parquet", "fallos.parquet", "ventanas_fallo"]:
    e, t, r = leer(ENTERA, parte), leer(TRABAJO, parte), leer(RESERVA, parte)
    comprobar(parte, e, t, r)
    if parte == "fallos.parquet" and len(r):
        claves = ["serial_number", "dia_fallo"]
        junta = pd.concat([t, r])[claves].drop_duplicates()
        mira("fallos, los mismos que en la entera", len(junta.merge(e[claves])) == len(e) == len(junta),
             f"{len(junta):,} distintos")

# control: una fila de la reserva colada en el trabajo tiene que salir
rec_t = leer(TRABAJO, "recuento_diario.parquet")
rec_r = leer(RESERVA, "recuento_diario.parquet")
if len(rec_t) and len(rec_r):
    colada = pd.concat([rec_t, rec_r.head(1)])
    ft = fecha_de("recuento_diario.parquet", colada)
    mira("control: una fila de la reserva en el trabajo se detecta", not (ft < CORTE).all(), f"último {ft.max()}")
else:
    mira("control: una fila de la reserva en el trabajo se detecta", False, "faltan datos para el control")

print(f"\n{fallan} comprobaciones fallan")
sys.exit(1 if fallan else 0)
