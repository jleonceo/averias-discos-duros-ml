"""Prueba de scripts/16_variables_nuevas.py: las cuatro variables nuevas candidatas (P-04) y la decisión.

Datos pequeños escritos aquí, nunca los de data/. Comprueba:
  1. contador entre edad: divide por la edad en años y queda vacío si la edad falta o es 0;
  2. discos que avisan en el vault: cuenta los demás discos del mismo centro, vault y foto, sin el propio, y queda vacío
     sin vault;
  3. fallos del vault en los 30 días anteriores: entra el fallo de hace 30 días y no el de hace 31 ni el del mismo día;
     solo cuenta su vault y los discos de datos; vacío sin vault o si la ventana empieza antes de que conste el sitio;
  4. tasa del modelo a esa edad: solo los meses anteriores al de la foto, con la edad en años cumplidos; vacía sin
     historial;
  5. la decisión pliegue a pliegue: entran si mejoran por encima de la desviación, no si empatan o empeoran;
  6. si ya existe informes/variables_nuevas.json, el brazo sin variables repite pliegue a pliegue las cifras de la
     competición, leídas de informes/modelado.json (otra salida, de otro script).

Sale con 0 si todo pasa y con 1 si algo falla; imprime cada caso.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CASO = Path(__file__).resolve().parents[1]
FALLOS = []


def comprobar(nombre, condicion, detalle=""):
    """Apunta un caso: ok o FALLA con su detalle."""
    print(("ok    " if condicion else "FALLA ") + nombre + (f" ({detalle})" if detalle and not condicion else ""))
    if not condicion:
        FALLOS.append(nombre)


def cargar():
    """Carga el script 16 como módulo; su trabajo está bajo __main__."""
    spec = importlib.util.spec_from_file_location("variables_16", CASO / "scripts" / "16_variables_nuevas.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["variables_16"] = m
    spec.loader.exec_module(m)
    return m


def igual(a, b):
    """Iguales contando el vacío como igual al vacío."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


def fotos():
    """Seis fotos: dos meses, dos vaults de un centro y una sin sitio."""
    return pd.DataFrame({
        "fecha": pd.to_datetime(["2023-09-01", "2023-09-01", "2023-09-01", "2023-09-01", "2023-09-01", "2023-07-01"]),
        "datacenter": ["ams1", "ams1", "ams1", "ams1", None, "ams1"],
        "vault_id": pd.array([1, 1, 1, 2, None, 1], dtype="Int64"),
        "avisa": [True, True, False, True, True, False],
        "model": ["A", "A", "B", "A", "A", "A"],
        "edad_anos": [2.0, 0.0, np.nan, 2.9, 1.5, 3.0],
        "smart_5_raw": [10.0, 4.0, 6.0, np.nan, 3.0, 0.0],
        "smart_187_raw": [2.0, 0.0, 0.0, 1.0, 0.0, 0.0],
        "smart_197_raw": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "smart_198_raw": [4.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    })


def probar_por_ano(m):
    """1. Contador entre edad."""
    v = m.por_ano(fotos())
    comprobar("1: cuatro columnas, una por contador de avería", list(v.columns) == [f"smart_{k}_raw_por_ano" for k in (5, 187, 197, 198)], list(v.columns))
    comprobar("1: 10 averías a los 2 años son 5 por año", v["smart_5_raw_por_ano"].iloc[0] == 5.0, v["smart_5_raw_por_ano"].iloc[0])
    comprobar("1: edad 0, vacío", np.isnan(v["smart_5_raw_por_ano"].iloc[1]))
    comprobar("1: edad vacía, vacío", np.isnan(v["smart_5_raw_por_ano"].iloc[2]))
    comprobar("1: contador vacío, vacío", np.isnan(v["smart_5_raw_por_ano"].iloc[3]))


def probar_avisan(m):
    """2. Discos que avisan en el mismo vault esa foto, sin el propio."""
    f = fotos()
    v = m.avisan_en_vault(f, m.cuenta_avisos(f))
    comprobar("2: el que avisa no se cuenta a sí mismo", v.iloc[0] == 1.0, v.iloc[0])
    comprobar("2: el que no avisa ve a los dos que avisan", v.iloc[2] == 2.0, v.iloc[2])
    comprobar("2: otro vault no se mezcla", v.iloc[3] == 0.0, v.iloc[3])
    comprobar("2: sin sitio, vacío", np.isnan(v.iloc[4]))
    comprobar("2: otra foto del mismo vault no se mezcla", v.iloc[5] == 0.0, v.iloc[5])


def probar_fallos_vault(m):
    """3. Fallos del mismo vault en los 30 días anteriores."""
    fallos = pd.DataFrame({
        "dia_fallo": pd.to_datetime(["2023-08-02", "2023-08-01", "2023-09-01", "2023-08-31", "2023-08-20", "2023-08-20"]),
        "datacenter": ["ams1", "ams1", "ams1", "ams1", "ams1", "ams1"],
        "vault_id": pd.array([1, 1, 1, 1, 2, 1], dtype="Int64"),
        "tipo_disco": ["datos", "datos", "datos", "datos", "datos", "arranque"],
    })
    v = m.fallos_vault_30d(fotos(), fallos)
    # Foto del 01/09: ventana del 02/08 al 31/08. Entran el 02/08 y el 31/08; no el 01/08 (31 días), ni el 01/09 (mismo
    # día), ni el de otro vault, ni el disco de arranque.
    comprobar("3: dos fallos en la ventana del vault 1", v.iloc[0] == 2.0, v.iloc[0])
    comprobar("3: el vault 2 ve solo el suyo", v.iloc[3] == 1.0, v.iloc[3])
    comprobar("3: sin sitio, vacío", np.isnan(v.iloc[4]))
    comprobar("3: ventana que empieza antes de que conste el sitio, vacío", np.isnan(v.iloc[5]))


def probar_tasa(m):
    """4. Tasa del modelo a esa edad con solo los meses anteriores."""
    dias = pd.DataFrame({
        "model": ["A", "A", "A", "A", "B", "A"],
        "centro": ["x", "y", "x", "x", "x", "x"],
        "mes": pd.to_datetime(["2023-07-01", "2023-07-01", "2023-08-01", "2023-09-01", "2023-08-01", "2023-08-01"]),
        "edad_anos_cumplidos": [2, 2, 2, 2, 0, 1],
        "fallos": [1, 1, 2, 50, 3, 0],
        "dias_disco": [365.25, 365.25, 730.5, 365.25, 365.25, 0.0],
    })
    v = m.tasa_modelo_edad(fotos(), dias)
    # Modelo A, 2 años (2,0 y 2,9) en septiembre: julio y agosto, 4 fallos en 1.461 días = 1 por año de disco; el mes de
    # la foto (50 fallos) no entra.
    comprobar("4: julio y agosto, sin el mes de la foto", abs(v.iloc[0] - 1.0) < 1e-12, v.iloc[0])
    comprobar("4: 2,9 años son 2 años cumplidos", abs(v.iloc[3] - 1.0) < 1e-12, v.iloc[3])
    comprobar("4: edad vacía, vacío", np.isnan(v.iloc[2]))
    comprobar("4: historial con 0 días de disco, vacío y sin dividir por 0", np.isnan(v.iloc[4]))
    comprobar("4: sin meses anteriores, vacío", np.isnan(v.iloc[5]))


def probar_decision(m):
    """5. La decisión pliegue a pliegue."""
    base = [30, 31, 29, 30, 30]
    comprobar("5: mejoran en todos los pliegues, entran", m.decision(base, [33, 34, 32, 33, 34])["entran"] is True)
    comprobar("5: empatan, no entran", m.decision(base, [32, 29, 31, 28, 31])["entran"] is False)
    comprobar("5: empeoran, no entran", m.decision(base, [27, 28, 26, 27, 27])["entran"] is False)


def probar_real():
    """6. Con la salida real: el brazo sin variables repite la competición pliegue a pliegue."""
    ruta, comp = CASO / "informes" / "variables_nuevas.json", CASO / "informes" / "modelado.json"
    if not ruta.exists():
        print("nota  sin informes/variables_nuevas.json: la parte real no se comprueba")
        return
    r = json.loads(ruta.read_text(encoding="utf-8"))
    md = json.loads(comp.read_text(encoding="utf-8"))
    hgb = [x for x in md["ranking"] if x["algoritmo"] == md["ganador"]["algoritmo"]][0]
    # El pliegue 1 no tiene sitio, así que con y sin sitio es lo mismo; los pliegues 2 a 5, del «sin» de modelado.json
    sin = md["sitio"]["sin"]
    esperado = [hgb["cv_por_pliegue"][0]] + [float(np.mean(sin[3 * i:3 * i + 3])) for i in range(4)]
    base = r["brazos"]["sin_variables"]["por_pliegue"]
    comprobar("6: el brazo sin variables repite la competición", igual(np.round(base, 9), np.round(esperado, 9)), f"{base} frente a {esperado}")
    comprobar("6: la decisión sale del cálculo", r["decision"]["entran"] == m_decision_real(r), r["decision"])


def m_decision_real(r):
    """La decisión rehecha a mano con las cifras del JSON: media de las diferencias por encima de su desviación."""
    d = np.asarray(r["brazos"]["las_cuatro"]["por_pliegue"]) - np.asarray(r["brazos"]["sin_variables"]["por_pliegue"])
    return bool(d.mean() > d.std(ddof=1))


if __name__ == "__main__":
    try:
        modulo = cargar()
    except Exception as e:  # noqa: BLE001 - sin script no hay nada que probar
        print(f"FALLA no se puede cargar scripts/16_variables_nuevas.py ({type(e).__name__}: {e})")
        sys.exit(1)
    probar_por_ano(modulo)
    probar_avisan(modulo)
    probar_fallos_vault(modulo)
    probar_tasa(modulo)
    probar_decision(modulo)
    probar_real()
    print("todo en verde" if not FALLOS else f"{len(FALLOS)} casos fallan")
    sys.exit(1 if FALLOS else 0)
