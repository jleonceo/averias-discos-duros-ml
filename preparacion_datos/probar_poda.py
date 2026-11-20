"""Prueba de `podar_datos.py` con los dos trimestres ya medidos (3.º de 2024 y 1.º de 2025). Solo lee.
Las cifras de referencia salen de los scripts anteriores del estudio previo:
- foto del 01/01/2025: 304.957 discos; foto del 01/07/2024: 289.096;
- discos distintos que fallan: 1.067 en el 1.er trimestre de 2025 y 1.423 en el 3.º de 2024 (1.424 filas de fallo);
- 197 columnas de origen, menos 68 que no aportan, más `fecha`: 130.
Cada comprobación imprime PASA o FALLA, y la prueba sale con código 1 si alguna falla.
16/11/2026, con permiso de Juan («arreglado, claro»): un disco puede fallar más de una vez; se comprueba que la poda
guarda cada fallo, que cada fila de ventana lleva el día de su fallo y, con los 26 trimestres, los 22.711 fallos.
Uso: python probar_poda.py <carpeta de salida de la poda>"""
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
S = Path(sys.argv[1])
malas = 0


def comprobar(nombre, ok, detalle):
    global malas
    malas += not ok
    print(("PASA " if ok else "FALLA") + f" · {nombre}: {detalle}")


f25 = pd.read_parquet(S / "fotos_mensuales" / "2025-01.parquet")
f24 = pd.read_parquet(S / "fotos_mensuales" / "2024-07.parquet")
comprobar("discos el 01/01/2025", len(f25) == 304_957, len(f25))
comprobar("discos el 01/07/2024", len(f24) == 289_096, len(f24))
comprobar("columnas de una foto", f25.shape[1] == 130, f25.shape[1])
comprobar("ninguna columna de las 68 quitadas", not {"is_legacy_format", "smart_15_raw", "smart_224_raw"} & set(f25.columns), "")
fallos = pd.read_parquet(S / "fallos.parquet")
q1 = fallos.loc[fallos.dia_fallo.between("2025-01-01", "2025-03-31"), "serial_number"].nunique()
q3 = fallos.loc[fallos.dia_fallo.between("2024-07-01", "2024-09-30"), "serial_number"].nunique()
comprobar("discos que fallan en el 1.er trimestre de 2025", q1 == 1_067, q1)
comprobar("discos que fallan en el 3.er trimestre de 2024", q3 == 1_423, q3)
# Con los 26 trimestres (16/11/2026, comprobar_orden_fallos_salida.txt): 22.711 días con failure = 1, de 22.668
# discos; 43 discos fallan dos veces. Se guarda cada fallo, no uno por disco. Solo se comprueba si la poda tiene los 26.
if len(list((S / "ventanas_fallo").glob("*.parquet"))) == 26:
    comprobar("todos los fallos de los 26 trimestres, también el segundo de un disco", len(fallos) == 22_711, len(fallos))
    comprobar("discos con dos fallos", (fallos.serial_number.value_counts() == 2).sum() == 43,
              (fallos.serial_number.value_counts() == 2).sum())
rec = pd.read_parquet(S / "recuento_diario.parquet")
r25 = rec.loc[rec.fecha == "2025-01-01", "discos"].sum()
comprobar("recuento diario del 01/01/2025 igual a la foto", r25 == 304_957, r25)
comprobar("fallos del recuento diario del 1.er trimestre de 2025", rec.loc[rec.fecha.between("2025-01-01", "2025-03-31"), "fallos"].sum() == 1_067,
          rec.loc[rec.fecha.between("2025-01-01", "2025-03-31"), "fallos"].sum())
v = pd.concat(pd.read_parquet(p) for p in (S / "ventanas_fallo").glob("*.parquet"))
dias = v.loc[v.failure == 1, ["serial_number", "fecha"]].drop_duplicates()
comprobar("cada fallo tiene su día de fallo en las ventanas", len(dias) == len(fallos), f"{len(dias)} de {len(fallos)}")
comprobar("cada fila de ventana dice a qué fallo pertenece", "dia_fallo" in v.columns, "")
if "dia_fallo" in v.columns:
    d = (v.dia_fallo - v.fecha).dt.days
    comprobar("ninguna fila de ventana fuera de los 30 días", d.between(0, 30).all(), f"de {d.min()} a {d.max()} días")
# CASOS QUE TIENEN QUE FALLAR (17/11/2026, con permiso de Juan; el control anterior comparaba una cifra consigo misma
# más uno y no podía fallar). Se estropea una copia de los datos y las mismas comprobaciones de arriba tienen que cazarlo.
fallos_rotos = fallos.iloc[1:]
comprobar("control: si falta un fallo, «cada fallo tiene su día» lo caza", len(dias) != len(fallos_rotos),
          f"{len(dias)} días frente a {len(fallos_rotos)} fallos")
if "dia_fallo" in v.columns:
    v_roto = v[["fecha", "dia_fallo"]].copy()
    v_roto.iloc[0, 1] = v_roto.iloc[0, 0] + pd.Timedelta(days=40)
    d_roto = (v_roto.dia_fallo - v_roto.fecha).dt.days
    comprobar("control: una fila a 40 días de su fallo, «fuera de los 30 días» la caza", not d_roto.between(0, 30).all(),
              f"máximo {d_roto.max()} días")
print(f"\n{malas} comprobaciones fallan")
sys.exit(1 if malas else 0)
