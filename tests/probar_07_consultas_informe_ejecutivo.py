"""Prueba de scripts/07_consultas_informe_ejecutivo.py.

Parte 1: monta en tests/tmp_consultas_ejecutivo/ un caso pequeño con modelo_trimestre, inicio_trimestre y
fallos_detalle, escritas con el esquema real de cada parquet (pyarrow.parquet.read_schema, sin cargar los datos), y su
informes/transformacion-datos.json con las huellas. Ejecuta el script con -W error y comprueba:
  - control que no debe disparar: las cifras por año, los trimestres (con una bajada, para que las subidas sean 20 de
    21 y no se den por hechas), las razones, la media al mes, la parte en garantía y los fallos por tipo; los discos de
    arranque de fallos_detalle no entran en la comparación por año;
  - para con ERROR si la huella de una tabla no es la de su salida en transformacion-datos.json;
  - para con ERROR si los fallos de los discos de datos de fallos_detalle no son los de modelo_trimestre;
  - para con ERROR si un coste de fallos_detalle no es el de modelo_trimestre;
  - para con ERROR si falta un trimestre en medio de la serie;
  - y en ninguno de los cuatro escribe el JSON.
Parte 2: con el JSON real, rehace por otro camino (pyarrow y Python, sin pandas) los fallos y los dos costes por año
desde fallos_detalle y los fallos por tipo; compara los discos de cada trimestre con cifras_para_siguiente de
informes/analisis-exploratorio__modelo_trimestre.json; y compara las cifras con los controles del encargo, escritas como
las da el encargo.

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import datetime as dt
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CASO / "assets"))
from graficos import numero  # noqa: E402

SCRIPT = CASO / "scripts" / "07_consultas_informe_ejecutivo.py"
TMP = CASO / "tests" / "tmp_consultas_ejecutivo"
SALIDA = "informes/consultas-informe-ejecutivo.json"
TABLAS = ["modelo_trimestre", "inicio_trimestre", "fallos_detalle"]
FALLOS = []


def comprobar(condicion, caso):
    """Apunta el caso si no se cumple y lo imprime."""
    print(("ok    " if condicion else "FALLA ") + caso)
    if not condicion:
        FALLOS.append(caso)


def sha256(ruta):
    """Huella SHA-256 de un fichero."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------------------------
# 2. El caso pequeño
# ---------------------------------------------------------------------------------------------------------------
# Por año: días de disco, fallos de datos, fallos en garantía, coste y coste con garantía (la verdad del caso pequeño)
ANOS = {
    2020: (36500, 10, 6, 1000.25, 400.0),
    2021: (36500, 12, 7, 1500.5, 500.0),
    2022: (73000, 30, 20, 2600.0, 900.0),
    2023: (73000, 40, 30, 4000.0, 1200.0),
    2024: (100000, 40, 30, 4100.0, 1300.0),
    2025: (50000, 20, 10, 1800.0, 700.0),
}
# Discos del primer día de cada trimestre: 22 trimestres, con una bajada en 2022-T3 (20 subidas de 21)
TRIMESTRES = [(a, t) for a in range(2020, 2026) for t in range(1, 5)][:22]
DISCOS = {}
for i, (a, t) in enumerate(TRIMESTRES):
    DISCOS[(a, t)] = 100 + 10 * i - (25 if (a, t) == (2022, 3) else 0)


def filas_modelo_trimestre():
    """Dos modelos por año, el segundo con la parte que falta, para que la suma por año no salga de una sola fila."""
    filas = []
    for ano, (dias, fallos, gar, coste, coste_g) in ANOS.items():
        partes = [(dias // 2, fallos // 2, gar // 2, coste / 2, coste_g / 2)]
        partes.append((dias - dias // 2, fallos - fallos // 2, gar - gar // 2, coste - coste / 2,
                       coste_g - coste_g / 2))
        for k, (d, f, g, c, cg) in enumerate(partes):
            filas.append({"model": f"M{k}", "ano": ano, "trimestre": 1 + k, "capacidad_tb": 4.0,
                          "fabricante": "Seagate", "fecha_compra": dt.datetime(ano, 7, 1), "precio_usd": 100.0,
                          "origen_precio": "publicado", "dias_disco": d, "fallos": f, "fallos_en_garantia": g,
                          "coste_fallos_usd": c, "coste_fallos_garantia_usd": cg, "dias_disco_ano": dias,
                          "pasa_minimo_ano": True})
    return filas


def filas_inicio_trimestre():
    """Dos modelos por trimestre que suman los discos del trimestre."""
    filas = []
    for (a, t), n in DISCOS.items():
        for k, parte in enumerate((n // 3, n - n // 3)):
            filas.append({"ano": a, "trimestre": t, "model": f"M{k}", "edad_anos_cumplidos": k,
                          "fecha": dt.datetime(a, 3 * t - 2, 1), "capacidad_tb": 4.0, "discos": parte,
                          "dias_trimestre": 90})
    return filas


def filas_fallos_detalle():
    """Un fallo por fila; el coste del año se reparte a partes iguales. Más dos discos de arranque por año."""
    filas = []
    for ano, (_, fallos, gar, coste, coste_g) in ANOS.items():
        for i in range(fallos):
            filas.append(_fallo(ano, i, "datos", coste / fallos, coste_g / fallos, i < gar))
        for i in range(2):
            filas.append(_fallo(ano, 100 + i, "arranque", 50.0, 50.0, False))
    return filas


def _fallo(ano, i, tipo, coste, coste_g, en_garantia):
    """Un fallo con todas las columnas de fallos_detalle; las que el script no usa, con un valor cualquiera."""
    dia = dt.datetime(ano, 1 + i % 6, 1 + i % 28)
    return {"serial_number": f"S{ano}{i}", "dia_fallo": dia, "model": "M0", "capacidad_tb": 4.0,
            "fabricante": "Seagate", "tipo_disco": tipo, "garantia_anos": 5, "horas_al_fallar": 1000.0,
            "edad_al_fallar_anos": 1.0, "edad_de_horas": True, "en_garantia": en_garantia, "hay_dia_anterior": True,
            "avisa_dia_anterior": False, "sin_aviso": True, "datacenter": "ams5", "vault_id": 1, "pod_id": 1,
            "pod_slot_num": 1, "tomo": "1-1", "plazo_reconstruccion_dias": 1.0, "dias_desde_anterior_del_tomo": None,
            "coincide_con_anterior": None, "precio_nuevo_usd": 100.0, "coste_fallo_usd": coste,
            "coste_fallo_garantia_usd": coste_g, "ultima_foto_anterior": None, "objetivo_de_alguna_foto": False,
            "periodo": "construccion", "ano": ano, "trimestre": 1 + (dia.month - 1) // 3, "mes": dia.month,
            "primer_fallo_del_disco": True}


def montar(fallos_detalle=None, inicio=None, huella_mala=False):
    """Escribe las tres tablas con el esquema real y el JSON de la transformación con sus huellas."""
    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "data" / "processed").mkdir(parents=True)
    (TMP / "informes").mkdir()
    filas = {"modelo_trimestre": filas_modelo_trimestre(),
             "inicio_trimestre": inicio if inicio is not None else filas_inicio_trimestre(),
             "fallos_detalle": fallos_detalle if fallos_detalle is not None else filas_fallos_detalle()}
    salidas = []
    for t in TABLAS:
        # El mismo esquema que el parquet real: mismos tipos de columna (boolean, Int64 y str donde los tiene)
        esquema = pq.read_schema(CASO / "data" / "processed" / f"{t}.parquet")
        ruta = TMP / "data" / "processed" / f"{t}.parquet"
        pq.write_table(pa.Table.from_pylist(filas[t], schema=esquema), ruta)
        huella = sha256(ruta)
        if huella_mala and t == "modelo_trimestre":
            huella = "0" * 64
        salidas.append({"tabla": t, "ruta": f"data/processed/{t}.parquet", "sha256": huella})
    (TMP / "informes" / "transformacion-datos.json").write_text(
        json.dumps({"fecha_datos": "2025-06-30", "salidas": salidas}), encoding="utf-8")


def ejecutar():
    """Ejecuta el script sobre la carpeta temporal con -W error."""
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)], capture_output=True,
                       text=True, encoding="utf-8", env={**__import__("os").environ, "PYTHONUTF8": "1"})
    return r.returncode, r.stdout + r.stderr


def cifras(ruta):
    """Lee el JSON de consultas y devuelve sus cifras por nombre."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return datos, {c["nombre"]: c for c in datos["cifras"]}


def sin_nan(objeto):
    """True si el JSON no lleva NaN ni infinitos."""
    if isinstance(objeto, float):
        return math.isfinite(objeto)
    if isinstance(objeto, dict):
        return all(sin_nan(v) for v in objeto.values())
    if isinstance(objeto, list):
        return all(sin_nan(v) for v in objeto)
    return True


# ---------------------------------------------------------------------------------------------------------------
# 3. Parte 1: el caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def parte_1():
    """Control que no debe disparar y los cuatro casos de parada."""
    # Control: todo coherente, con discos de arranque en fallos_detalle y una bajada de trimestre
    montar()
    codigo, salida = ejecutar()
    comprobar(codigo == 0, f"control: el script acaba bien (salida: {salida[-600:]})")
    ruta = TMP / SALIDA
    comprobar(ruta.exists(), "control: deja el JSON de consultas")
    if ruta.exists():
        datos, c = cifras(ruta)
        comprobar(datos.get("fecha_datos") == "2025-06-30", "control: fecha_datos 2025-06-30")
        comprobar(set(datos.get("versiones", {})) >= {"python", "pandas", "numpy", "pyarrow"},
                  "control: versiones de Python, pandas, numpy y pyarrow")
        comprobar(sin_nan(datos), "control: el JSON no lleva NaN")
        comprobar(all({"nombre", "valor", "poblacion", "periodo"} <= set(x) for x in datos["cifras"]),
                  "control: cada cifra lleva nombre, valor, población y periodo")
        for ano, (dias, fallos, gar, coste, coste_g) in ANOS.items():
            comprobar(c[f"dias_disco_{ano}"]["valor"] == dias, f"control: días de disco {ano}")
            comprobar(c[f"fallos_{ano}"]["valor"] == fallos, f"control: fallos {ano}")
            comprobar(c[f"fallos_en_garantia_{ano}"]["valor"] == gar, f"control: fallos en garantía {ano}")
            comprobar(abs(c[f"tasa_anual_pct_{ano}"]["valor"] - fallos / dias * 365 * 100) < 1e-9,
                      f"control: tasa anual {ano}")
            comprobar(abs(c[f"coste_fallos_usd_{ano}"]["valor"] - coste) < 1e-6, f"control: coste {ano}")
            comprobar(abs(c[f"coste_fallos_garantia_usd_{ano}"]["valor"] - coste_g) < 1e-6,
                      f"control: coste con garantía {ano}")
            comprobar(c[f"ano_completo_{ano}"]["valor"] is (ano < 2025), f"control: año completo {ano}")
        comprobar(c["trimestres"]["valor"] == 22, "control: 22 trimestres")
        comprobar(c["subidas_trimestre"]["valor"] == 20, "control: 20 subidas (hay una bajada a propósito)")
        comprobar(c["pasos_trimestre"]["valor"] == 21, "control: 21 pasos de un trimestre al siguiente")
        comprobar(c["discos_inicio_2020_T1"]["valor"] == DISCOS[(2020, 1)], "control: discos 2020-T1")
        comprobar(c["discos_inicio_2025_T2"]["valor"] == DISCOS[(2025, 2)], "control: discos 2025-T2")
        comprobar(abs(c["razon_discos_ultimo_primero"]["valor"] - DISCOS[(2025, 2)] / DISCOS[(2020, 1)]) < 1e-12,
                  "control: razón de discos último / primero")
        comprobar(abs(c["razon_coste_2024_2020"]["valor"] - 4100.0 / 1000.25) < 1e-12, "control: razón de coste")
        comprobar(abs(c["media_fallos_mes_2024"]["valor"] - 40 / 12) < 1e-12, "control: media de fallos al mes")
        comprobar(abs(c["parte_fallos_garantia_pct_2024"]["valor"] - 30 / 40 * 100) < 1e-12,
                  "control: parte en garantía 2024")
        comprobar(c["fallos_tipo_datos"]["valor"] == sum(v[1] for v in ANOS.values()), "control: fallos de datos")
        comprobar(c["fallos_tipo_arranque"]["valor"] == 12, "control: fallos de arranque")

    # Parada: la huella de modelo_trimestre no es la de su salida
    montar(huella_mala=True)
    codigo, salida = ejecutar()
    comprobar(codigo != 0 and "ERROR" in salida and not (TMP / SALIDA).exists(),
              "huella distinta: para con ERROR y no escribe el JSON")

    # Parada: un fallo de datos de más en 2022 en fallos_detalle
    filas = filas_fallos_detalle()
    filas.append(_fallo(2022, 999, "datos", 0.0, 0.0, False))
    montar(fallos_detalle=filas)
    codigo, salida = ejecutar()
    comprobar(codigo != 0 and "ERROR" in salida and not (TMP / SALIDA).exists(),
              "fallos de fallos_detalle distintos: para con ERROR y no escribe el JSON")

    # Parada: el mismo número de fallos, pero un coste distinto en 2023
    filas = filas_fallos_detalle()
    for f in filas:
        if f["ano"] == 2023 and f["tipo_disco"] == "datos":
            f["coste_fallo_garantia_usd"] += 10.0
            break
    montar(fallos_detalle=filas)
    codigo, salida = ejecutar()
    comprobar(codigo != 0 and "ERROR" in salida and not (TMP / SALIDA).exists(),
              "coste con garantía de fallos_detalle distinto: para con ERROR y no escribe el JSON")

    # Parada: falta un trimestre en medio de la serie (sin él, la subida se mediría entre dos no seguidos)
    inicio = [f for f in filas_inicio_trimestre() if (f["ano"], f["trimestre"]) != (2023, 2)]
    montar(inicio=inicio)
    codigo, salida = ejecutar()
    comprobar(codigo != 0 and "ERROR" in salida and not (TMP / SALIDA).exists(),
              "trimestre que falta en medio: para con ERROR y no escribe el JSON")


# ---------------------------------------------------------------------------------------------------------------
# 4. Parte 2: el JSON real, por otro camino y frente a los controles del encargo
# ---------------------------------------------------------------------------------------------------------------
# Controles del encargo, tal como los escribe: días de disco, fallos, tasa, coste y coste con garantía
CONTROLES_ANO = {
    2020: ("51.345.918", "1.307", "0,9", "250.485", "80.209"),
    2021: ("66.072.034", "1.823", "1,0", "352.674", "109.169"),
    2022: ("78.890.669", "2.999", "1,4", "565.844", "200.888"),
    2023: ("90.077.756", "4.201", "1,7", "755.879", "284.507"),
    2024: ("103.839.696", "4.538", "1,6", "832.698", "305.124"),
    2025: ("55.882.610", "2.128", "1,4", "366.916", "170.296"),
}


def parte_2():
    """Compara el JSON real con un cálculo por otro camino y con los controles del encargo."""
    ruta = CASO / SALIDA
    comprobar(ruta.exists(), "real: existe informes/consultas-informe-ejecutivo.json")
    if not ruta.exists():
        return
    datos, c = cifras(ruta)
    comprobar(datos.get("fecha_datos") == "2025-06-30", "real: fecha_datos 2025-06-30")
    comprobar(sin_nan(datos), "real: el JSON no lleva NaN")

    # Otro camino: fallos_detalle con pyarrow, recorrido fila a fila en Python, el año sacado de dia_fallo
    t = pq.read_table(CASO / "data/processed/fallos_detalle.parquet",
                      columns=["tipo_disco", "dia_fallo", "coste_fallo_usd", "coste_fallo_garantia_usd"]).to_pydict()
    por_ano, por_tipo = {}, {}
    for tipo, dia, coste, coste_g in zip(t["tipo_disco"], t["dia_fallo"], t["coste_fallo_usd"],
                                         t["coste_fallo_garantia_usd"]):
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
        if tipo != "datos":
            continue
        n, s, sg = por_ano.get(dia.year, (0, 0.0, 0.0))
        por_ano[dia.year] = (n + 1, s + coste, sg + coste_g)
    for ano in range(2020, 2026):
        n, s, sg = por_ano.get(ano, (0, 0.0, 0.0))
        comprobar(c[f"fallos_{ano}"]["valor"] == n, f"real, otro camino: fallos {ano} = {n}")
        comprobar(abs(c[f"coste_fallos_usd_{ano}"]["valor"] - s) < 0.005, f"real, otro camino: coste {ano}")
        comprobar(abs(c[f"coste_fallos_garantia_usd_{ano}"]["valor"] - sg) < 0.005,
                  f"real, otro camino: coste con garantía {ano}")
    comprobar(c["fallos_tipo_datos"]["valor"] == por_tipo.get("datos"), "real, otro camino: fallos de datos")
    comprobar(c["fallos_tipo_arranque"]["valor"] == por_tipo.get("arranque"), "real, otro camino: fallos de arranque")

    # Otro camino: los discos de cada trimestre frente a los del análisis exploratorio
    eda = json.loads((CASO / "informes/analisis-exploratorio__modelo_trimestre.json").read_text(encoding="utf-8"))
    serie = eda["cifras_para_siguiente"]["inicio_trimestre"]
    comprobar(c["trimestres"]["valor"] == len(serie), f"real, exploratorio: {len(serie)} trimestres")
    for fila in serie:
        nombre = f"discos_inicio_{fila['ano']}_T{fila['trimestre']}"
        comprobar(nombre in c and c[nombre]["valor"] == fila["discos"], f"real, exploratorio: {nombre}")

    # Controles del encargo, escritos como los escribe
    for ano, (dias, fallos, tasa, coste, coste_g) in CONTROLES_ANO.items():
        obtenido = (numero(c[f"dias_disco_{ano}"]["valor"]), numero(c[f"fallos_{ano}"]["valor"]),
                    numero(c[f"tasa_anual_pct_{ano}"]["valor"], 1), numero(c[f"coste_fallos_usd_{ano}"]["valor"]),
                    numero(c[f"coste_fallos_garantia_usd_{ano}"]["valor"]))
        comprobar(obtenido == (dias, fallos, tasa, coste, coste_g), f"control del encargo {ano}: {obtenido}")
    comprobar(c["ano_completo_2025"]["valor"] is False and c["ano_completo_2024"]["valor"] is True,
              "control del encargo: 2025 no está completo y 2024 sí")
    comprobar(numero(c["fallos_en_garantia_2024"]["valor"]) == "3.258", "control del encargo: 3.258 en garantía")
    comprobar(numero(c["parte_fallos_garantia_pct_2024"]["valor"], 1) == "71,8", "control del encargo: 71,8 %")
    comprobar(numero(c["media_fallos_mes_2024"]["valor"]) == "378", "control del encargo: 378 al mes")
    comprobar(numero(c["dias_disco_2024"]["valor"] / 1e6, 1) == "103,8", "control del encargo: 103,8 millones")
    comprobar(numero(c["discos_inicio_2020_T1"]["valor"]) == "122.696", "control del encargo: 122.696")
    comprobar(numero(c["discos_inicio_2025_T2"]["valor"]) == "308.836", "control del encargo: 308.836")
    comprobar(c["subidas_trimestre"]["valor"] == 21 and c["pasos_trimestre"]["valor"] == 21,
              "control del encargo: 21 subidas de 21")
    comprobar(numero(c["razon_discos_ultimo_primero"]["valor"], 2) == "2,52", "control del encargo: razón 2,52")
    comprobar(numero(c["razon_coste_2024_2020"]["valor"], 2) == "3,32", "control del encargo: razón 3,32")
    comprobar(numero(c["fallos_tipo_datos"]["valor"]) == "16.996", "control del encargo: 16.996 de datos")
    comprobar(numero(c["fallos_tipo_arranque"]["valor"]) == "964", "control del encargo: 964 de arranque")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        if not SCRIPT.exists():
            comprobar(False, "existe scripts/07_consultas_informe_ejecutivo.py")
        else:
            parte_1()
        parte_2()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} casos fallan" if FALLOS else "\nTodos los casos pasan")
    sys.exit(1 if FALLOS else 0)
