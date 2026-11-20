"""Prueba de scripts/22_punto_ciego.py (auditor antes de entregar, R68-153 y R68-155; skill programacion-del-caso).

El script mide el punto ciego de la lista de riesgo: la parte de los fallos a 30 días cuya foto mensual no avisa.
Esta prueba usa datos pequeños escritos aquí, nunca los de data/.

Casos:
  1. cuatro fallos y uno sin aviso dan el 25 %; las fotos sanas no cuentan;
  2. las fotos con el objetivo vacío no cuentan;
  3. sin ningún fallo, la parte es None y no un cero;
  4. un fallo con «avisa» vacío para: no se decide en silencio si avisaba;
  5. los fallos contados cuadran con los del modelo mes a mes, y no cuadran si un mes tiene otro número (en rojo);
  6. ninguna validación con su resultado escrito a mano en el script, y nada de la regla del cambio de contadores.
Sale con 0 si todo pasa y con 1 si algo falla.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import importlib.util
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "22_punto_ciego.py"
FALLOS = []


def caso(nombre, ok, detalle=""):
    """Apunta un caso y lo imprime."""
    print(("PASA  " if ok else "FALLA ") + nombre + (f" · {detalle}" if detalle and not ok else ""))
    if not ok:
        FALLOS.append(nombre)


def cargar():
    """Carga el script como módulo sin ejecutar su main."""
    spec = importlib.util.spec_from_file_location("s22", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fotos(avisa, falla, meses=None):
    """Fotos de juguete: una por fila, con su aviso, su objetivo y su mes."""
    n = len(avisa)
    return pd.DataFrame({"serial_number": [f"S{i}" for i in range(n)],
                         "fecha": pd.to_datetime(meses or ["2025-07-01"] * n),
                         "avisa": pd.array(avisa, dtype="boolean"), "falla_30d": pd.array(falla, dtype="Float64")})


# ---------------------------------------------------------------------------------------------------------------
# 2. Los casos
# ---------------------------------------------------------------------------------------------------------------
def main():
    """Lanza los casos."""
    caso("0. el script existe", SCRIPT.is_file(), "no existe scripts/22_punto_ciego.py")
    if not SCRIPT.is_file():
        print(f"{len(FALLOS)} FALLA")
        return 1
    m = cargar()
    # 1. Cuatro fallos, uno sin aviso; las sanas no cuentan
    r = m.punto_ciego(fotos([True, True, True, False, False, True], [1, 1, 1, 1, 0, 0]))
    caso("1. cuatro fallos y uno sin aviso dan el 25 %", r == {"fallos": 4, "sin_aviso_en_la_foto": 1, "parte": 0.25}, r)
    # 2. El objetivo vacío no cuenta
    r = m.punto_ciego(fotos([False, False, True], [1, None, 1]))
    caso("2. una foto con el objetivo vacío no cuenta", r["fallos"] == 2 and r["sin_aviso_en_la_foto"] == 1, r)
    # 3. Sin fallos, None
    r = m.punto_ciego(fotos([True, False], [0, 0]))
    caso("3. sin fallos la parte es None", r["fallos"] == 0 and r["parte"] is None, r)
    # 4. «avisa» vacío en un fallo: para
    try:
        m.punto_ciego(fotos([True, None], [1, 1]))
        paro = False
    except ValueError:
        paro = True
    caso("4. un fallo con «avisa» vacío para", paro)
    # 5. Cuadra con los fallos del modelo, mes a mes
    t = fotos([True, False, True, True], [1, 1, 0, 1], ["2025-07-01", "2025-07-01", "2025-08-01", "2025-08-01"])
    bueno = [{"mes": "2025-07-01", "fallos": 2}, {"mes": "2025-08-01", "fallos": 1}]
    caso("5. los fallos cuadran con los del modelo", m.cuadra_con_el_modelo(t, bueno) is True)
    malo = [{"mes": "2025-07-01", "fallos": 2}, {"mes": "2025-08-01", "fallos": 2}]
    caso("5. un mes con otro número de fallos no cuadra", m.cuadra_con_el_modelo(t, malo) is False)
    otro_mes = [{"mes": "2025-07-01", "fallos": 2}, {"mes": "2025-09-01", "fallos": 1}]
    caso("5. otro mes no cuadra", m.cuadra_con_el_modelo(t, otro_mes) is False)
    # 6. Ninguna validación escrita y nada de la regla del cambio
    texto = SCRIPT.read_text(encoding="utf-8")
    escritas = re.findall(r'"\w+":\s*(?:True|False)\b', texto)
    caso("6. ninguna validación con su resultado escrito", not escritas, escritas)
    caso("6. nada de la regla del cambio de contadores",
         not re.search(r"cambio_smart_187|regla_cambio|sencilla", texto), "queda algo de la regla")
    print(f"{len(FALLOS)} FALLA" if FALLOS else "TODO PASA")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    np.seterr(all="raise")
    sys.exit(main())
