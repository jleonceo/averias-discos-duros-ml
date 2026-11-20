"""Caso 68: poda de los datos de Backblaze. Solo lee los ZIP; escribe en la carpeta de salida que se le da.
El responsable del caso, 16/11/2026: «hazlo» (desde 2020, una foto al mes, los fallos con sus 30 días anteriores y el recuento diario).

Uso: python podar_datos.py <carpeta de salida> <zip> [<zip> ...]

Deja tres cosas:
- `fotos_mensuales/AAAA-MM.parquet`: todos los discos el día 1 de cada mes, con todas sus columnas salvo las 68 que no
  aportan (vacías o con un solo valor en las fotos del 01/07/2024 y del 01/01/2025; lista abajo).
- `ventanas_fallo/<trimestre>.parquet`: cada disco que falla, día a día, desde 30 días antes de su fallo hasta el día
  del fallo, con las mismas columnas. Las ventanas que empiezan en el trimestre anterior salen enteras, porque el día
  de fallo de cada disco se busca antes en todos los ZIP (primera pasada).
- `recuento_diario.parquet`: por día, modelo, capacidad y centro de datos, cuántos discos había y cuántos fallaron.
  Con él las tasas de fallo salen exactas aunque las fotos sean mensuales.
Y `fallos.parquet`: un fallo por fila, con el disco y su día de fallo.

16/11/2026, con permiso del responsable del caso («arreglado, claro»): un disco puede fallar dos veces (43 en los 26 trimestres, de 7 a
30 meses entre uno y otro). La versión anterior guardaba un solo fallo por disco, y además el primero que encontraba en
el orden en que llegaban los ZIP, que no era el de las fechas. Ahora los ZIP se ordenan por año y trimestre, se guardan
todos los fallos y cada fila de ventana lleva `dia_fallo`, el día del fallo al que pertenece (el más cercano por delante).

Las columnas que Backblaze no publicaba un año no aparecen en los ficheros de ese año: las fotos y las ventanas pasan de
101 a 130 columnas entre 2020 y 2024. Solo `datacenter` y `capacity_bytes` se crean vacías cuando faltan, porque el
recuento diario agrupa por ellas (corregido el 17/11/2026, con permiso del responsable del caso: decía que todas quedaban vacías)."""
import re
import sys
import time
import zipfile
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
SALIDA = Path(sys.argv[1])
ZIPS = sorted((Path(z) for z in sys.argv[2:]),
              key=lambda p: tuple(int(x) for x in reversed(re.search(r"Q(\d)_(\d{4})", p.name).groups())))
VENTANA = 30
VACIOS = [15, 160, 161, 163, 164, 176, 178, 250, 251, 252, 255]
CONSTANTES = ["is_legacy_format", "smart_16_normalized", "smart_17_normalized", "smart_18_normalized", "smart_18_raw",
              "smart_23_normalized", "smart_23_raw", "smart_24_raw", "smart_27_normalized", "smart_71_normalized",
              "smart_71_raw", "smart_82_normalized", "smart_82_raw", "smart_90_normalized", "smart_165_normalized",
              "smart_166_normalized", "smart_167_normalized", "smart_168_normalized", "smart_169_normalized",
              "smart_171_normalized", "smart_174_normalized", "smart_175_normalized", "smart_175_raw",
              "smart_179_normalized", "smart_181_normalized", "smart_182_normalized", "smart_182_raw",
              "smart_201_normalized", "smart_206_normalized", "smart_210_normalized", "smart_210_raw",
              "smart_211_normalized", "smart_212_normalized", "smart_218_normalized", "smart_224_normalized",
              "smart_224_raw", "smart_226_normalized", "smart_231_normalized", "smart_232_normalized",
              "smart_233_normalized", "smart_234_normalized", "smart_244_raw", "smart_246_normalized",
              "smart_247_normalized", "smart_248_normalized", "smart_254_raw"]
FUERA = set(CONSTANTES) | {f"smart_{n}_{t}" for n in VACIOS for t in ("raw", "normalized")}
assert len(FUERA) == 68, len(FUERA)
TEXTO = {"serial_number": str, "model": str, "datacenter": str}


def dias(ruta):
    z = zipfile.ZipFile(ruta)
    nombres = sorted(n for n in z.namelist() if n.endswith(".csv") and "__MACOSX" not in n and "/." not in n)
    return z, [(pd.Timestamp(Path(n).stem), n) for n in nombres]


def leer(z, n, columnas=None):
    usar = (lambda c: c in columnas) if columnas else (lambda c: c not in FUERA)
    d = pd.read_csv(z.open(n), usecols=usar, dtype=TEXTO, low_memory=False)
    return d.drop_duplicates("serial_number")


t0 = time.time()
SALIDA.mkdir(parents=True, exist_ok=True)
(SALIDA / "fotos_mensuales").mkdir(exist_ok=True)
(SALIDA / "ventanas_fallo").mkdir(exist_ok=True)

# primera pasada: todos los fallos, cada uno con su disco y su día
eventos = []
for ruta in ZIPS:
    z, lista = dias(ruta)
    for fecha, n in lista:
        d = leer(z, n, {"serial_number", "failure"})
        eventos += [(s, fecha) for s in d.loc[d.failure == 1, "serial_number"]]
    print(f"1.ª pasada {ruta.name}: {len(lista)} días | fallos acumulados {len(eventos):,} | {time.time() - t0:,.0f} s", flush=True)
fallo = (pd.DataFrame(eventos, columns=["serial_number", "dia_fallo"])
         .drop_duplicates().sort_values(["dia_fallo", "serial_number"], ignore_index=True))
fallo.to_parquet(SALIDA / "fallos.parquet", index=False)

# segunda pasada: fotos del día 1 de cada mes, ventanas de fallo y recuento diario
recuentos = []
for ruta in ZIPS:
    z, lista = dias(ruta)
    ventanas = []
    for fecha, n in lista:
        d = leer(z, n)
        d.insert(0, "fecha", fecha)
        for c in ("datacenter", "capacity_bytes"):
            if c not in d.columns:
                d[c] = pd.NA
        r = (d.assign(datacenter=d.datacenter.fillna("sin dato"))
             .groupby(["model", "capacity_bytes", "datacenter"], dropna=False)
             .agg(discos=("serial_number", "size"), fallos=("failure", "sum")).reset_index())
        r.insert(0, "fecha", fecha)
        recuentos.append(r)
        if fecha.day == 1:
            d.to_parquet(SALIDA / "fotos_mensuales" / f"{fecha:%Y-%m}.parquet", index=False)
        v = d.merge(fallo, on="serial_number")
        quedan = (v.dia_fallo - fecha).dt.days
        v = (v[(quedan >= 0) & (quedan <= VENTANA)].sort_values("dia_fallo")
             .drop_duplicates("serial_number"))
        if len(v):
            ventanas.append(v)
    if ventanas:
        pd.concat(ventanas, ignore_index=True).to_parquet(SALIDA / "ventanas_fallo" / f"{ruta.stem}.parquet", index=False)
    print(f"2.ª pasada {ruta.name}: {len(lista)} días | filas de ventanas {sum(len(v) for v in ventanas):,} | {time.time() - t0:,.0f} s", flush=True)

pd.concat(recuentos, ignore_index=True).to_parquet(SALIDA / "recuento_diario.parquet", index=False)
print(f"hecho en {time.time() - t0:,.0f} s")
