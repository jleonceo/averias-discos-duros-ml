"""Aparta la reserva del caso 68 (permiso de el responsable del caso, 17/11/2026: «Sí, apártala»).

Uso: python -I apartar_reserva.py <poda entera> <trabajo> <reserva>

La reserva es del 01/07/2025 al 30/06/2026 (El responsable del caso, 16/11/2026) y no se mira hasta la prueba final. Lee la poda entera
sin tocarla y escribe dos carpetas nuevas, que no pueden existir antes:
- fotos mensuales: cada fichero va entero a un lado, por su mes;
- recuento diario: por su fecha;
- fallos y ventanas: por el día del fallo. Las filas de junio de 2025 que preceden a un fallo de julio van a la reserva,
  con su fallo.
Lo lanza el analista una vez, antes de entregar los datos al caso; si la poda se rehace, se vuelve a lanzar.
Su prueba es `probar_reserva.py`.
"""
import shutil
import sys
from pathlib import Path

import pandas as pd

CORTE = pd.Timestamp("2025-07-01")
ENTERA, TRABAJO, RESERVA = (Path(a) for a in sys.argv[1:4])

for carpeta in (TRABAJO, RESERVA):
    carpeta.mkdir()  # falla si ya existe: no se escribe encima de nada
    (carpeta / "fotos_mensuales").mkdir()
    (carpeta / "ventanas_fallo").mkdir()

for f in sorted((ENTERA / "fotos_mensuales").glob("*.parquet")):
    lado = RESERVA if pd.Timestamp(f.stem + "-01") >= CORTE else TRABAJO
    shutil.copy2(f, lado / "fotos_mensuales" / f.name)


def partir(d, columna, nombre):
    reserva = d[columna] >= CORTE
    for lado, filas in ((TRABAJO, d[~reserva]), (RESERVA, d[reserva])):
        if len(filas):
            filas.to_parquet(lado / nombre, index=False)


partir(pd.read_parquet(ENTERA / "recuento_diario.parquet"), "fecha", "recuento_diario.parquet")
partir(pd.read_parquet(ENTERA / "fallos.parquet"), "dia_fallo", "fallos.parquet")
for f in sorted((ENTERA / "ventanas_fallo").glob("*.parquet")):
    partir(pd.read_parquet(f), "dia_fallo", Path("ventanas_fallo") / f.name)

print("hecho")
