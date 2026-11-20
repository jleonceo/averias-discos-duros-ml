"""Prueba de las piezas de Python de scripts/21_cuadro_mando.py, con datos pequeños escritos aquí.

Casos:
1. el script existe y se importa sin ejecutar nada (no escribe el cuadro);
2. una tasa con su intervalo: 10 fallos en 365.000 días de disco dan un 1 % entre 0,4795 y 1,8390 (intervalo exacto de
   Poisson de 10 sucesos, de 4,7954 a 18,3904, en las tablas de Garwood);
3. un grupo por debajo del mínimo (50.000 días de disco en el año o 20 fallos) sale sin conclusión;
4. el tomo en peligro el último día de su plazo y el día siguiente: un disco de 4 TB que falló hace 4 días lo pone en
   peligro y uno que falló hace 5 no; el tomo sale de la última fila con centro, vault y ranura, y la fila cuya fecha no
   es la de su texto no cuenta;
5. un fallo sin tomo, uno sin capacidad y uno de arranque se cuentan aparte;
6. la segunda vía de los tomos, en bucle fallo a fallo, da lo mismo que la tabla; con los datos de arriba y con 300
   fallos al azar (semilla fija);
7. una fila puntuada sin foto para;
8. una entrada más vieja que su script para, y una más nueva pasa;
9. el CSV: su nombre con la lista, los filtros y la fecha; punto y coma, coma decimal y la selección en la primera
   línea; se escribe en tests/tmp_cuadro/ y se lee de vuelta;
10. el buscador de validaciones con su resultado escrito caza «"huella_data_igual": True» y no encuentra ninguna en el
    script.

La carpeta tests/tmp_cuadro/ se crea y se borra siempre. Sale con 0 si todo pasa y con 1 si algo falla, diciendo qué.

Uso: python -W error tests/probar_21_cuadro_mando.py
"""

# csv lee de vuelta el CSV escrito
import csv
# importlib carga el script por su ruta sin ejecutar su principal
import importlib.util
# os cambia la fecha de modificación de los ficheros de prueba
import os
# shutil borra la carpeta temporal
import shutil
# sys da el código de salida
import sys
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "21_cuadro_mando.py"
TMP = RAIZ / "tests" / "tmp_cuadro"
# La cabecera del CSV: centro, tomo (con su vault y su ranura), modelo, edad, disco y, al final, la puntuación de
# riesgo (ordena los discos; el modelo no está calibrado y no es una probabilidad, una nota del caso)
CABECERA = ["Puesto", "Centro de datos", "Ciudad", "Tomo en peligro", "Vault", "Ranura", "Fabricante", "Modelo",
            "Capacidad (TB)", "Años cumplidos", "Número de serie", "Puntuación de riesgo (0 a 100)"]
FALLOS = []
FECHA = pd.Timestamp("2026-06-01")
# La ciudad de cada centro, copiada de config/negocio/reglas-negocio.md §4 («Centro de datos»)
CIUDADES = {"ams5": "Ámsterdam", "iad1": "Virginia", "phx1": "Phoenix", "sac0": "Sacramento", "sac2": "Sacramento",
            "yyz1": "Toronto"}


def caso(nombre, condicion, detalle=""):
    """Apunta un caso y dice si pasa."""
    print(("PASA  " if condicion else "FALLA ") + nombre + ("" if condicion else f" ({detalle})"))
    if not condicion:
        FALLOS.append(nombre)


def para(m, funcion, *args):
    """Cierto si la función para con la Parada del script."""
    try:
        funcion(*args)
    except m.Parada:
        return True
    return False


def cargar():
    """Carga el script como módulo, sin ejecutar su principal."""
    spec = importlib.util.spec_from_file_location("cuadro_mando_68", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def fila_ventana(serial, dia_fallo, fecha, modelo, capacidad, centro, vault, ranura, texto=None, pod=1):
    """Una fila de ventana de fallo en bruto, con su fecha, su texto y su servidor (pod_id)."""
    fecha = pd.Timestamp(fecha)
    return {"fecha": fecha, "date": texto or fecha.strftime("%Y-%m-%d"), "serial_number": serial,
            "dia_fallo": pd.Timestamp(dia_fallo), "model": modelo, "capacity_bytes": capacidad, "datacenter": centro,
            "vault_id": vault, "pod_id": pod, "pod_slot_num": ranura}


def datos_tomos():
    """Cinco fallos de mayo de 2026 con sus ventanas, escritos a mano.

    - A: 4 TB, falla el 28/05 (4 días antes del 01/06, plazo 5): en peligro, último día del plazo. Su fila del día del
      fallo viene sin ranura y el día antes la trae: el tomo es el del día antes (ams5|10|3). Una fila del 27/05 con el
      texto de otro día trae otro sitio y no cuenta.
    - B: 4 TB, falla el 27/05 (5 días antes): ya no está en peligro, el día siguiente al plazo. Tomo sac0|20|1.
    - C: 4 TB, falla el 30/05 sin ranura en ninguna fila: sin tomo.
    - D: un modelo cuya única capacidad es −1: sin capacidad.
    - E: un disco de arranque de 0,25 TB: no es de datos.
    """
    tb4, mala, arranque = 4_000_787_030_016, -1, 250_059_350_016
    filas = [
        fila_ventana("A", "2026-05-28", "2026-05-26", "MOD4", tb4, "ams5", 10, 3),
        fila_ventana("A", "2026-05-28", "2026-05-27", "MOD4", tb4, "phx1", 99, 9, texto="2026-05-28"),
        fila_ventana("A", "2026-05-28", "2026-05-27", "MOD4", tb4, "ams5", 10, 3),
        fila_ventana("A", "2026-05-28", "2026-05-28", "MOD4", tb4, "ams5", 10, np.nan),
        fila_ventana("B", "2026-05-27", "2026-05-27", "MOD4", tb4, "sac0", 20, 1),
        fila_ventana("C", "2026-05-30", "2026-05-30", "MOD4", tb4, "sac2", 30, np.nan),
        fila_ventana("D", "2026-05-29", "2026-05-29", "MALO", mala, "iad1", 40, 2),
        fila_ventana("E", "2026-05-29", "2026-05-29", "ARR", arranque, "iad1", 41, 2),
    ]
    ventanas = pd.DataFrame(filas)
    fallos = pd.DataFrame({"serial_number": list("ABCDE"),
                           "dia_fallo": pd.to_datetime(["2026-05-28", "2026-05-27", "2026-05-30", "2026-05-29",
                                                        "2026-05-29"])})
    return fallos, ventanas


def al_azar(semilla=68, n=300):
    """Fallos y ventanas al azar: 300 fallos de mayo de 2026, de 4 a 24 TB, con huecos de sitio."""
    rng = np.random.default_rng(semilla)
    capacidades = {f"M{c}": c * 10**12 for c in (4, 8, 12, 16, 20, 24)}
    filas, fallos = [], []
    for i in range(n):
        modelo = rng.choice(list(capacidades))
        dia = FECHA - pd.Timedelta(days=int(rng.integers(1, 30)))
        fallos.append({"serial_number": f"S{i}", "dia_fallo": dia})
        centro = rng.choice(["ams5", "sac0", "sac2"])
        vault, ranura = int(rng.integers(1, 6)), int(rng.integers(1, 4))
        for k in range(int(rng.integers(1, 5)), -1, -1):
            sin_ranura = rng.random() < 0.3
            filas.append(fila_ventana(f"S{i}", dia, dia - pd.Timedelta(days=k), modelo, capacidades[modelo], centro,
                                      vault, np.nan if sin_ranura else ranura))
    return pd.DataFrame(fallos), pd.DataFrame(filas)


def main():
    """Lanza los casos."""
    # 1. El script existe y se importa sin escribir el cuadro
    caso("1. el script existe", SCRIPT.is_file(), "no existe scripts/21_cuadro_mando.py")
    if not SCRIPT.is_file():
        print(f"{len(FALLOS)} FALLA")
        return 1
    html = RAIZ / "informes" / "cuadro_mando.html"
    antes = html.stat().st_mtime if html.exists() else None
    m = cargar()
    despues = html.stat().st_mtime if html.exists() else None
    caso("1. importarlo no escribe el cuadro", antes == despues)

    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    try:
        # 2. Una tasa con su intervalo
        t, lo, hi = m.intervalo_poisson(10, 365_000)
        caso("2. tasa de 10 fallos en 365.000 días", abs(t - 1.0) < 1e-12, t)
        caso("2. su intervalo es el exacto de Poisson", abs(lo - 0.479539) < 1e-5 and abs(hi - 1.839036) < 1e-5,
             (lo, hi))
        t0, lo0, hi0 = m.intervalo_poisson(0, 365_000)
        caso("2. sin fallos el intervalo empieza en cero", t0 == 0 and lo0 == 0 and hi0 > 0, (t0, lo0, hi0))

        # 3. El mínimo
        caso("3. con 49.999 días de disco en el año no hay conclusión", not m.concluye(49_999, 25))
        caso("3. con 19 fallos no hay conclusión", not m.concluye(80_000, 19))
        caso("3. con 50.000 días y 20 fallos hay conclusión", m.concluye(50_000, 20))

        # 4 y 5. Los tomos en peligro y lo que va aparte
        fallos, ventanas = datos_tomos()
        sitios, aparte = m.sitios_de_fallos(fallos, ventanas, {}, 200_000_000_000, FECHA)
        caso("4. el tomo del fallo A es el del día antes, con ranura",
             sitios.set_index("serial_number").loc["A", "tomo"] == "ams5|10|3",
             sitios.set_index("serial_number")["tomo"].to_dict())
        peligro = m.tomos_en_peligro(sitios, FECHA)
        caso("4. el último día de su plazo el tomo está en peligro", "ams5|10|3" in peligro, peligro)
        caso("4. el día siguiente al plazo ya no", "sac0|20|1" not in peligro, peligro)
        caso("4. solo un tomo en peligro", len(peligro) == 1, peligro)
        caso("5. un fallo sin tomo", aparte["de_datos_sin_tomo"] == 1, aparte)
        caso("5. un fallo sin capacidad", aparte["sin_capacidad"] == 1, aparte)
        caso("5. un fallo de arranque", aparte["de_arranque"] == 1, aparte)

        # 6. La segunda vía, en bucle fallo a fallo
        bucle, aparte_b = m.tomos_en_peligro_bucle(fallos, ventanas, {}, 200_000_000_000, FECHA)
        caso("6. el bucle da los mismos tomos", bucle == peligro, (bucle, peligro))
        caso("6. el bucle cuenta lo mismo aparte", aparte_b == aparte, (aparte_b, aparte))
        fa, va = al_azar()
        s2, ap2 = m.sitios_de_fallos(fa, va, {}, 200_000_000_000, FECHA)
        p2 = m.tomos_en_peligro(s2, FECHA)
        b2, apb2 = m.tomos_en_peligro_bucle(fa, va, {}, 200_000_000_000, FECHA)
        caso("6. con 300 fallos al azar el bucle da lo mismo", b2 == p2 and apb2 == ap2 and len(p2) > 10,
             (len(b2), len(p2), apb2, ap2))

        # 6b. El tomo como scripts/05 §7.3: la última fila con los cuatro datos de sitio (pod_id incluido)
        tb4 = 4_000_787_030_016
        vf = pd.DataFrame([fila_ventana("F", "2026-05-29", "2026-05-28", "MOD4", tb4, "sac2", 50, 4, pod=1),
                           fila_ventana("F", "2026-05-29", "2026-05-29", "MOD4", tb4, "sac2", 50, 7, pod=np.nan)])
        ff = pd.DataFrame({"serial_number": ["F"], "dia_fallo": pd.to_datetime(["2026-05-29"])})
        sf, _ = m.sitios_de_fallos(ff, vf, {}, 200_000_000_000, FECHA)
        caso("6b. sin pod_id la última fila no da el tomo: es el de la anterior completa",
             sf.loc[0, "tomo"] == "sac2|50|4", sf.loc[0, "tomo"])
        bf, _ = m.tomos_en_peligro_bucle(ff, vf, {}, 200_000_000_000, FECHA)
        caso("6b. la segunda vía también", bf == {"sac2|50|4"}, bf)

        # 7. Una fila puntuada sin foto para
        puntuadas = pd.DataFrame({"serial_number": ["X1", "X2"], "probabilidad": [0.2, 0.1]})
        foto = pd.DataFrame({"serial_number": ["X1"], "model": ["M"]})
        caso("7. una fila puntuada sin foto para", para(m, m.unir_foto, puntuadas, foto))
        foto2 = pd.DataFrame({"serial_number": ["X1", "X2"], "model": ["M", "N"]})
        caso("7. con su foto, la une por serial_number",
             m.unir_foto(puntuadas, foto2).set_index("serial_number").loc["X2", "model"] == "N")

        # 8. Una entrada más vieja que su script para
        entrada, script = TMP / "entrada.json", TMP / "script.py"
        entrada.write_text("{}", encoding="utf-8")
        script.write_text("# script", encoding="utf-8")
        os.utime(entrada, (1_000_000_000, 1_000_000_000))
        os.utime(script, (1_000_000_100, 1_000_000_100))
        caso("8. una entrada más vieja que su script para", para(m, m.comprobar_orden, [(entrada, script)]))
        os.utime(entrada, (1_000_000_200, 1_000_000_200))
        caso("8. una entrada más nueva pasa", not para(m, m.comprobar_orden, [(entrada, script)]))

        # 9. El CSV
        caso("9. nombre con la lista, un filtro y la fecha",
             m.nombre_csv(100, {"fabricante": "Seagate"}, "2026-06-01") == "lista_100_seagate_datos-2026-06-01.csv",
             m.nombre_csv(100, {"fabricante": "Seagate"}, "2026-06-01"))
        todos = {"fabricante": "HGST", "capacidad": 12.0, "edad": 3, "centro": "sac2"}
        caso("9. nombre con los cuatro filtros, de lo general a lo particular", m.nombre_csv(20, todos, "2026-06-01")
             == "lista_20_sac2_hgst_12tb_edad-3_datos-2026-06-01.csv", m.nombre_csv(20, todos, "2026-06-01"))
        caso("9. la selección del CSV, en el mismo orden", m.texto_csv([], 20, todos, "2026-06-01").split("\r\n")[0]
             == "Lista de 20 · Sacramento · sac2 · HGST · 12 TB · 3 años cumplidos · datos a 01/06/2026",
             m.texto_csv([], 20, todos, "2026-06-01").split("\r\n")[0])
        caso("9. nombre sin filtros", m.nombre_csv(1000, {}, "2026-06-01") == "lista_1000_datos-2026-06-01.csv")
        filas = [{"puesto": 1, "serial_number": "ZA1", "model": "ST16000NM001G", "fabricante": "Seagate",
                  "capacidad_tb": 16.0, "centro": "sac2", "vault": 1031, "ranura": 7, "edad": 3,
                  "tomo_en_peligro": "Sí", "probabilidad": 0.123456},
                 {"puesto": 2, "serial_number": "ZA2", "model": "ST16000NM001G", "fabricante": "Seagate",
                  "capacidad_tb": 16.0, "centro": "sac2", "vault": None, "ranura": None, "edad": 3,
                  "tomo_en_peligro": "Sin tomo", "probabilidad": 0.0012345}]
        texto = m.texto_csv(filas, 100, {"fabricante": "Seagate"}, "2026-06-01")
        ruta = TMP / m.nombre_csv(100, {"fabricante": "Seagate"}, "2026-06-01")
        ruta.write_text(texto, encoding="utf-8", newline="")
        with open(ruta, encoding="utf-8", newline="") as f:
            leido = list(csv.reader(f, delimiter=";"))
        caso("9. la primera línea dice la selección", leido[0][0].startswith("Lista de 100") and "Seagate" in leido[0][0],
             leido[0])
        caso("9. la cabecera, de lo general a lo particular y la puntuación la última", leido[1] == CABECERA, leido[1])
        caso("9. al lado del centro, su ciudad", leido[2][1:3] == ["sac2", "Sacramento"], leido[2][1:3])
        caso("9. la puntuación de 0 a 100, con coma decimal y redondeo como Excel", leido[2][11] == "12,35"
             and leido[3][11] == "0,12", (leido[2][11], leido[3][11]))
        caso("9. un sitio vacío queda vacío", leido[3][4] == "" and leido[3][5] == "", leido[3])
        caso("9. la capacidad sin decimales si es entera", leido[2][8] == "16", leido[2][8])
        caso("9. el número de serie, antes de la puntuación", leido[2][10] == "ZA1", leido[2][10])
        caso("9. la ciudad de cada centro, la de las reglas, apartado 4", m.CIUDADES == CIUDADES, m.CIUDADES)

        # 10. Ninguna validación con su resultado escrito
        caso("10. el buscador caza un resultado escrito",
             m.buscar_resultados_escritos('    v = {"huella_data_igual": True}') != [])
        hallado = m.buscar_resultados_escritos(SCRIPT.read_text(encoding="utf-8"))
        caso("10. el script no tiene ninguno", hallado == [], hallado)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    caso("la carpeta temporal se ha borrado", not TMP.exists())
    print(f"{len(FALLOS)} FALLA" if FALLOS else "TODO PASA")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
