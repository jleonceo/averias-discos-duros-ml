"""Punto ciego de la lista de riesgo: la parte de los fallos a 30 días cuya foto mensual no avisa (R68-153 y R68-155).

Por qué existe. El informe final daba un 25 % de fallos «sin ningún aviso» medido con otra definición (sin aviso el
día anterior al fallo). La lista de riesgo trabaja con la foto del día 1 de cada mes, así que su punto ciego se mide en
esa foto: de los fallos a 30 días de cada mes, cuántos llegan con la foto sin ningún aviso de los cinco contadores.
Se mide en los mismos meses en que se midió el modelo:
  - la validación (de 2024-07 a 2025-06), los meses de modelado.json;
  - el año guardado (de 2025-07 a 2026-05), los meses que se miden en prueba_final.json.
Segunda vía: los fallos que cuenta este script, mes a mes, tienen que ser los que contó el modelo en esos JSON.

Entradas (solo lectura): data/processed/fotos_riesgo_validacion.parquet y _reserva.parquet; informes/modelado.json e
informes/prueba_final.json, que tienen que existir y ser más nuevos que sus scripts (15 y 19).
Salida: informes/punto_ciego.json.
Ejecución: python -W error scripts/22_punto_ciego.py
"""

# =================================================================================================================
# 1. Configuración
# =================================================================================================================
import hashlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

CASO = Path(__file__).resolve().parents[1]
PROC = CASO / "data" / "processed"
INF = CASO / "informes"
SALIDA = INF / "punto_ciego.json"

TABLAS = {"validacion": PROC / "fotos_riesgo_validacion.parquet",
          "ano_guardado": PROC / "fotos_riesgo_reserva.parquet"}
JSON_MODELO = {"modelado": (INF / "modelado.json", CASO / "scripts" / "15_modelado.py"),
               "prueba_final": (INF / "prueba_final.json", CASO / "scripts" / "19_prueba_final.py")}
COLUMNAS = ["serial_number", "fecha", "avisa", "falla_30d"]
FECHA_DATOS = "2026-06-30"  # fin del año guardado, la fecha más nueva que se lee


# =================================================================================================================
# 2. La medida
# =================================================================================================================
def fallos_de(df):
    """Las fotos con fallo a 30 días; fuera las que tienen el objetivo vacío."""
    return df[df["falla_30d"].notna() & (df["falla_30d"] == 1)]


def punto_ciego(df):
    """Parte de los fallos a 30 días cuya foto mensual no avisa. Para si algún fallo trae «avisa» vacío."""
    f = fallos_de(df)
    if f["avisa"].isna().any():
        raise ValueError(f"{int(f['avisa'].isna().sum())} fallos con «avisa» vacío: no se puede decir si avisaban")
    sin = int((~f["avisa"].astype(bool)).sum())
    return {"fallos": int(len(f)), "sin_aviso_en_la_foto": sin, "parte": sin / len(f) if len(f) else None}


def cuadra_con_el_modelo(df, modelo_por_mes):
    """Segunda vía: los fallos de cada mes son los que contó el modelo en su JSON, y los meses son los mismos."""
    f = fallos_de(df)
    mios = {pd.Timestamp(m).strftime("%Y-%m-%d"): int(n) for m, n in f.groupby("fecha").size().items()}
    suyos = {str(r["mes"])[:10]: int(r["fallos"]) for r in modelo_por_mes}
    return mios == suyos


# =================================================================================================================
# 3. Lectura y huellas
# =================================================================================================================
def huella(ruta):
    """SHA-256 de un fichero."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def leer_json(ruta, script):
    """Lee un JSON del caso; para si no existe o es más viejo que el script que lo escribe."""
    if not ruta.is_file():
        raise SystemExit(f"Falta {ruta}")
    if ruta.stat().st_mtime < script.stat().st_mtime:
        raise SystemExit(f"{ruta.name} es más viejo que {script.name}: ejecuta antes ese script")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def leer_tabla(ruta, meses):
    """Lee las columnas necesarias, con la fecha como fecha, solo en los meses que se piden."""
    d = pd.read_parquet(ruta, columns=COLUMNAS)
    d["fecha"] = pd.to_datetime(d["fecha"])
    return d[d["fecha"].dt.strftime("%Y-%m-%d").isin(meses)]


# =================================================================================================================
# 4. Principal
# =================================================================================================================
def main():
    """Mide el punto ciego en la validación y en el año guardado, lo cuadra con el modelo y escribe el JSON."""
    inicio = datetime.now()
    huellas_antes = {k: huella(v) for k, v in TABLAS.items()}
    modelado = leer_json(*JSON_MODELO["modelado"])
    prueba = leer_json(*JSON_MODELO["prueba_final"])
    por_mes = {"validacion": modelado["validacion"]["por_mes"],
               "ano_guardado": [r for r in prueba["por_mes"] if r.get("se_mide")]}

    # 4.1 El punto ciego de cada periodo y su segunda vía
    resultados, cuadran = {}, {}
    for clave, tabla in TABLAS.items():
        meses = {str(r["mes"])[:10] for r in por_mes[clave]}
        t = leer_tabla(tabla, meses)
        resultados[clave] = {"meses": sorted(meses), **punto_ciego(t)}
        cuadran[clave] = cuadra_con_el_modelo(t, por_mes[clave])

    # 4.2 Comprobaciones, cada una calculada
    validaciones = {
        "entradas_sin_cambios": huellas_antes == {k: huella(v) for k, v in TABLAS.items()},
        "fallos_de_validacion_como_el_modelo": cuadran["validacion"],
        "fallos_del_ano_guardado_como_el_modelo": cuadran["ano_guardado"],
        "ano_guardado_con_sus_meses": len(resultados["ano_guardado"]["meses"]) == prueba["periodo"]["meses_esperados"],
    }
    estado = "OK" if all(validaciones.values()) else "ERROR"
    salida = {
        "script": "scripts/22_punto_ciego.py", "origen": "auditor sin memoria antes de entregar (R68-153)",
        "fecha_datos": FECHA_DATOS, "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
        "estado": estado,
        "definicion": ("Parte de los fallos a 30 días cuya foto mensual, la del día 1 del mes, no tiene ningún aviso de "
                       "los cinco contadores de la regla de los cinco avisos SMART."),
        **resultados,
        "validaciones": validaciones,
        "entradas": {k: {"ruta": str(v.relative_to(CASO)), "huella": huellas_antes[k]} for k, v in TABLAS.items()},
        "ejecucion": {"python": platform.python_version(), "ejecutable": sys.executable, "pandas": pd.__version__,
                      "segundos": round((datetime.now() - inicio).total_seconds(), 1)},
    }
    if estado != "OK":
        print(json.dumps(validaciones, ensure_ascii=False, indent=1))
        raise SystemExit(f"ERROR: validaciones en rojo; no se escribe {SALIDA.name}")
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    for k in TABLAS:
        r = salida[k]
        print(f"{k}: {r['sin_aviso_en_la_foto']} de {r['fallos']} fallos sin aviso, {r['parte']:.4f}")
    print(f"{estado}, {salida['ejecucion']['segundos']} s → {SALIDA.relative_to(CASO)}")


if __name__ == "__main__":
    main()
