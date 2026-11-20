"""Prueba de produccion/ejecutar.py y de tests/comprobar_produccion_por_otro_camino.py (método preproduccion §2.3,
§2.4 y validaciones 2, 3, 5, 6, 7 y 9).

Monta en tests/tmp_produccion/ el caso pequeño de tests/probar_reentrenar.py (contrato, configuración y tabla de
entrenamiento), entrena con reentrenar.py un modelo de juguete y lo pone como modelo en uso de la copia. Escribe datos
en bruto como los de data/raw/podado/: dos fotos mensuales de historia (mayo y junio de 2024, una con el centro sin
tipo, otra con un modelo con dos espacios y una capacidad -1), la foto de julio que se puntúa y un trimestre de
ventanas de fallo. Casos:
  1. verde: una fila de salida por fila de entrada, en el mismo orden y con su serial_number; el disco de arranque y
     la foto del día del fallo salen sin puntuar y con su motivo; un modelo que no estaba en el entrenamiento, un disco
     sin foto anterior y la fila con la capacidad -1 se puntúan; las marcas de las listas, con el desempate por
     serial_number; el resumen y el lote en informes/preproduccion.json;
  2. una segunda ejecución el mismo día archiva la primera;
  3. falta una columna: para;
  4. un número llega como texto: para;
  5. la foto del mes anterior al pedido: para (validación 9);
  6. la ficha del modelo no cuadra (otra versión de scikit-learn): para (validación 7);
  7. sin modelo en uso ni --modelo: para;
  8. el contrato con otra lista de columnas que la del modelo: para (validación 2);
  9. la prueba por otro camino: coincide con la salida y sale en rojo con una probabilidad estropeada y con una marca
     estropeada (validación 5);
 10. ejecutar.py no quita filas: ninguna llamada que tire filas en su código (validación 6);
 11. la historia repartida en dos carpetas (mayo en una; junio y julio en otra) da la misma salida que toda en una, y la
     prueba por otro camino coincide con esas dos carpetas;
 12. dos ventanas con el mismo nombre en carpetas distintas son ficheros distintos y cuentan las dos;
 13. una carpeta de historia que no existe: para;
 14. el archivo por mes: dos meses lanzados el mismo día quedan los dos a la vista, y el mismo mes dos veces deja el
     primero en _archivo/ sin tocar el otro mes;
 15. las validaciones 6 y 7 del lote se calculan: la ficha no cuadra con otra huella, otra versión u otras columnas, y
     una salida con una fila menos, dos filas cambiadas de orden o una fila sin puntuar y sin motivo quita filas; en
     ejecutar.py no queda ninguna validación con su resultado escrito.
Sale con 0 si todo pasa y con 1 si algo falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CASO = Path(__file__).resolve().parents[1]
EJECUTAR = CASO / "produccion" / "ejecutar.py"
REENTRENAR = CASO / "produccion" / "reentrenar.py"
OTRO = CASO / "tests" / "comprobar_produccion_por_otro_camino.py"
spec = importlib.util.spec_from_file_location("probar_reentrenar", CASO / "tests" / "probar_reentrenar.py")
PR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PR)
TMP, HOY = PR.TMP, PR.HOY
POD = TMP / "data" / "raw" / "podado"
FALLOS = []
C4, C12, C025 = 4000787030016, 12000138625024, 250059350016


def comprobar(condicion, caso):
    """Apunta el caso si no se cumple y lo imprime."""
    print(("ok    " if condicion else "FALLA ") + caso)
    if not condicion:
        FALLOS.append(caso)


def correr(script, *args):
    """Ejecuta un script con -W error; devuelve el código y la salida."""
    r = subprocess.run([sys.executable, "-W", "error", str(script), *args], capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=150)
    return r.returncode, r.stdout + r.stderr


# ---------------------------------------------------------------------------------------------------------------
# 2. Los datos en bruto del caso pequeño
# ---------------------------------------------------------------------------------------------------------------
def foto_en_bruto(js, mes, discos, semilla, sin_tipo_el_centro=False):
    """Una foto mensual en bruto, con las columnas de entrada del contrato y sus tipos de origen."""
    rng = np.random.default_rng(semilla)
    n = len(discos)
    entrada = js["entrada_de_ejecutar"]["columnas_que_lee"]
    d = {"serial_number": [s for s, _, _ in discos], "fecha": [mes] * n, "date": [mes.strftime("%Y-%m-%d")] * n,
         "model": [m for _, m, _ in discos], "capacity_bytes": [c for _, _, c in discos], "failure": [0] * n}
    for col in entrada:
        if col.startswith("smart_"):
            x = rng.integers(0, 40, n).astype(float)
            x[rng.random(n) < 0.05] = np.nan
            d[col] = x
    d["smart_9_raw"] = rng.integers(1000, 40000, n).astype(float)
    t = pa.table({k: v for k, v in d.items()})
    t = t.set_column(t.schema.get_field_index("fecha"), "fecha", pa.array(d["fecha"], type=pa.timestamp("ms")))
    t = t.append_column("datacenter", pa.nulls(n) if sin_tipo_el_centro else pa.array(rng.choice(["phx1", "sac0"], n)))
    return t


def montar():
    """El caso pequeño entero: el de reentrenar, un modelo en uso y los datos en bruto."""
    js = PR.montar()
    nueva = TMP / "data" / "nuevos" / "tabla.parquet"
    nueva.parent.mkdir(parents=True)
    shutil.copy(TMP / PR.ENT, nueva)
    codigo, salida = correr(REENTRENAR, "--raiz", str(TMP), "--hoy", HOY, "--tabla", str(nueva), "--fecha", "2024-07-01")
    if codigo != 0:
        print(salida[-1500:])
    modelo = TMP / "modelos" / "reentrenos" / HOY / "modelo_riesgo.joblib"
    (TMP / "produccion" / "configuracion.json").write_text(json.dumps(PR.configuracion(str(modelo)), ensure_ascii=False), encoding="utf-8")
    shutil.copytree(CASO / "config" / "modelo", TMP / "config" / "modelo",
                    ignore=shutil.ignore_patterns("*.md"))
    (POD / "fotos_mensuales").mkdir(parents=True)
    (POD / "ventanas_fallo").mkdir(parents=True)
    base = [(f"D{i:03d}", ["ST4000DM000", "ST12000NM0008", "TOSHIBA MG07ACA14TA"][i % 3], [C4, C12, C12][i % 3]) for i in range(150)]
    # Mayo: el centro sin tipo; junio: un modelo con dos espacios y una capacidad -1
    pq.write_table(foto_en_bruto(js, pd.Timestamp("2024-05-01"), base[:120], 5, sin_tipo_el_centro=True), POD / "fotos_mensuales" / "2024-05.parquet")
    junio = base[:140] + [("W1", "WDC  WUH721414ALE6L4", 14000519643136)]
    junio[0] = ("D000", "ST4000DM000", -1)
    pq.write_table(foto_en_bruto(js, pd.Timestamp("2024-06-01"), junio, 6), POD / "fotos_mensuales" / "2024-06.parquet")
    # Julio, la que se puntúa: los 150, un disco nuevo sin foto anterior, un modelo que no estaba en el entrenamiento,
    # un disco de arranque, la foto del día del fallo y la capacidad -1 otra vez
    julio = base + [("NUEVO_DISCO", "ST4000DM000", C4), ("M1", "ST24000NM002H", 24000476020736), ("B1", "Seagate SSD", C025),
                    ("W1", "WDC  WUH721414ALE6L4", 14000519643136)]
    julio[3] = ("D003", "ST4000DM000", -1)
    t = foto_en_bruto(js, pd.Timestamp("2024-07-01"), julio, 7)
    fallo = np.zeros(len(julio), dtype=np.int64)
    fallo[10] = 1
    t = t.set_column(t.schema.get_field_index("failure"), "failure", pa.array(fallo))
    # Dos discos sin horas: uno con ventana de un fallo anterior y otro con la de un fallo que aún no ha ocurrido
    h = t["smart_9_raw"].to_numpy(zero_copy_only=False).copy()
    h[[20, 21]] = np.nan
    t = t.set_column(t.schema.get_field_index("smart_9_raw"), "smart_9_raw", pa.array(h))
    pq.write_table(t, POD / "fotos_mensuales" / "2024-07.parquet")
    v = pd.DataFrame({"serial_number": ["D020", "D021", "D020"], "fecha": pd.to_datetime(["2024-04-10", "2024-06-20", "2024-04-11"]),
                      "date": ["2024-04-10", "2024-06-20", "2024-04-12"], "dia_fallo": pd.to_datetime(["2024-05-01", "2024-07-15", "2024-05-01"]),
                      "model": ["ST12000NM0008", "ST12000NM0008", "ST12000NM0008"], "capacity_bytes": [C12] * 3, "failure": [0, 0, 0]})
    v["dia_fallo"] = v["dia_fallo"].astype("datetime64[ns]")
    v["fecha"] = v["fecha"].astype("datetime64[ms]")
    pq.write_table(pa.Table.from_pandas(v, preserve_index=False), POD / "ventanas_fallo" / "data_Q2_2024.parquet")
    return js, julio


def ejecutar(*extra, foto=None, mes="2024-07"):
    """ejecutar.py sobre la foto de julio (u otra), con la historia del caso pequeño."""
    return correr(EJECUTAR, "--raiz", str(TMP), "--hoy", HOY, "--foto", str(foto or POD / "fotos_mensuales" / "2024-07.parquet"),
                  "--mes", mes, "--fotos-anteriores", str(POD / "fotos_mensuales"), "--ventanas", str(POD / "ventanas_fallo"), *extra)


# ---------------------------------------------------------------------------------------------------------------
# 3. Los casos
# ---------------------------------------------------------------------------------------------------------------
def casos():
    """Los diez casos del docstring."""
    js, julio = montar()
    carpeta = TMP / "data" / "predicciones" / HOY
    salida_ruta = carpeta / "predicciones_2024-07.parquet"
    # 1. Verde
    codigo, salida = ejecutar()
    comprobar(codigo == 0 and salida_ruta.exists(), f"1 ejecuta y guarda la salida ({codigo}; {salida[-800:]})")
    if not salida_ruta.exists():
        return
    s = pd.read_parquet(salida_ruta)
    comprobar(len(s) == len(julio) and list(s["serial_number"]) == [d for d, _, _ in julio],
              "1 una fila por fila de entrada, en el mismo orden y con su serial_number")
    fila = s.set_index("serial_number")
    comprobar("arranque" in str(fila.loc["B1", "motivo"]) and pd.isna(fila.loc["B1", "probabilidad"]), "1 el disco de arranque sale sin puntuar, con su motivo")
    comprobar("día del fallo" in str(fila.loc["D010", "motivo"]) and pd.isna(fila.loc["D010", "probabilidad"]), "1 la foto del día del fallo sale sin puntuar, con su motivo")
    comprobar(all(pd.notna(fila.loc[x, "probabilidad"]) and pd.isna(fila.loc[x, "motivo"]) for x in ("M1", "NUEVO_DISCO", "D003", "W1", "D020", "D021")),
              "1 se puntúan el modelo nuevo, el disco sin foto anterior, la capacidad -1, el modelo con dos espacios y los discos sin horas")
    puntuadas = s[s["probabilidad"].notna()]
    for n in (20, 100):
        orden = puntuadas.sort_values(["probabilidad", "serial_number"], ascending=[False, True])
        esperada = set(orden["serial_number"].head(n))
        comprobar(set(s.loc[s[f"en_lista_{n}"] == 1, "serial_number"]) == esperada and s.loc[s["probabilidad"].isna(), f"en_lista_{n}"].isna().all(),
                  f"1 la marca de la lista de {n}: los {n} de más riesgo, con el desempate por serial_number; vacía en lo que no se puntúa")
    res = json.loads((carpeta / "resumen_2024-07.json").read_text(encoding="utf-8"))
    comprobar(res["filas_entrada"] == res["filas_salida"] == len(julio) and {x["motivo"][:10] for x in res["sin_puntuar"]} >= {"disco de a", "foto del d"},
              "1 el resumen: filas de entrada y de salida, y lo que no se puntúa por motivo")
    pre = json.loads((TMP / "informes" / "preproduccion.json").read_text(encoding="utf-8"))
    comprobar(pre["lote"]["filas_salida"] == len(julio) and pre["validaciones"]["filas_ejecucion"] is True
              and pre["validaciones"]["ficha_cuadra"] is True and pre["validaciones"]["sin_quitar_filas_al_ejecutar"] is True,
              "1 el lote y sus validaciones en informes/preproduccion.json")
    casos_de_validaciones_calculadas(s, julio)
    hi = pre["lote"]["historial"]
    comprobar(hi["discos_con_foto_anterior"] == 141 and hi["discos_con_ventana_ya_ocurrida"] == 1,
              f"1 el historial: 141 discos con foto anterior y 1 con ventana de un fallo ya ocurrido, no la de D021 ({hi})")
    # 9. La prueba por otro camino, con la salida buena y con dos estropeadas
    argumentos = ["--raiz", str(TMP), "--salida", str(salida_ruta), "--foto", str(POD / "fotos_mensuales" / "2024-07.parquet"), "--mes", "2024-07",
                  "--fotos-anteriores", str(POD / "fotos_mensuales"), "--ventanas", str(POD / "ventanas_fallo"),
                  "--tabla", str(TMP / "data" / "nuevos" / "tabla.parquet"), "--fecha", "2024-07-01"]
    codigo, salida = correr(OTRO, *argumentos)
    comprobar(codigo == 0, f"9 la prueba por otro camino coincide ({codigo}; {salida[-1200:]})")
    for nombre, cambio in (("una probabilidad", lambda d: d.assign(probabilidad=d["probabilidad"].where(d.index != 5, d["probabilidad"] + 1e-9))),
                           ("una marca", lambda d: d.assign(en_lista_20=d["en_lista_20"].where(d.index != 5, 1 - d["en_lista_20"])))):
        mala = TMP / "estropeada.parquet"
        cambio(s.copy()).to_parquet(mala, index=False)
        codigo, salida = correr(OTRO, *[mala.as_posix() if a == str(salida_ruta) else a for a in argumentos])
        comprobar(codigo == 1, f"9 la prueba por otro camino sale en rojo con {nombre} estropeada ({codigo})")
    codigo, _ = correr(OTRO, *argumentos, "--anotar")
    po = json.loads((TMP / "informes" / "preproduccion.json").read_text(encoding="utf-8"))
    comprobar(codigo == 0 and po["prueba_por_otro_camino"]["coincide"] is True and po["prueba_por_otro_camino"]["rojo_con_estropeada"] is True
              and po["validaciones"]["otro_camino"] is True, "9 con --anotar escribe que coincide y que la estropeada sale en rojo")
    # 2. Una segunda ejecución el mismo día archiva la primera
    codigo, _ = ejecutar()
    archivo = list((carpeta / "_archivo").rglob("predicciones_2024-07.parquet")) if (carpeta / "_archivo").exists() else []
    comprobar(codigo == 0 and len(archivo) == 1, "2 la segunda ejecución del día archiva la primera")
    casos_de_varias_carpetas(s, carpeta, argumentos)
    # 3. Falta una columna
    t = pq.read_table(POD / "fotos_mensuales" / "2024-07.parquet")
    mala = TMP / "foto_mala.parquet"
    pq.write_table(t.drop_columns(["smart_5_raw"]), mala)
    codigo, salida = ejecutar(foto=mala)
    comprobar(codigo != 0 and "faltan columnas" in salida and "smart_5_raw" in salida, "3 falta una columna: para y la nombra")
    # 4. Un número llega como texto
    pq.write_table(t.set_column(t.schema.get_field_index("smart_9_raw"), "smart_9_raw", pc_texto(t["smart_9_raw"])), mala)
    codigo, salida = ejecutar(foto=mala)
    comprobar(codigo != 0 and "como texto" in salida and "smart_9_raw" in salida, "4 un número llega como texto: para y lo nombra")
    # 5. La foto del mes anterior al pedido
    codigo, salida = ejecutar(foto=POD / "fotos_mensuales" / "2024-06.parquet", mes="2024-07")
    comprobar(codigo != 0 and "mes" in salida, f"5 la foto del mes anterior al pedido: para ({salida[-300:]})")
    # 8. El contrato con otra lista de columnas
    pre_ruta = TMP / "informes" / "preproduccion.json"
    bueno = pre_ruta.read_text(encoding="utf-8")
    otro = json.loads(bueno)
    otro["finalistas"] = [f for f in otro["finalistas"] if f["variable"] != "smart_242_raw"]
    pre_ruta.write_text(json.dumps(otro, ensure_ascii=False), encoding="utf-8")
    codigo, salida = ejecutar()
    comprobar(codigo != 0 and "columnas" in salida, "8 el contrato con otra lista de columnas que la del modelo: para")
    pre_ruta.write_text(bueno, encoding="utf-8")
    # 6. La ficha no cuadra
    ficha = TMP / "modelos" / "reentrenos" / HOY / "modelo_riesgo_versiones.json"
    texto = ficha.read_text(encoding="utf-8")
    fi = json.loads(texto)
    fi["versiones"]["scikit-learn"] = "0.0.1"
    ficha.write_text(json.dumps(fi), encoding="utf-8")
    codigo, salida = ejecutar()
    comprobar(codigo != 0 and "versiones" in salida, "6 la ficha no cuadra: para al cargar")
    ficha.write_text(texto, encoding="utf-8")
    # 7. Sin modelo en uso
    (TMP / "produccion" / "configuracion.json").write_text(json.dumps(PR.configuracion(None)), encoding="utf-8")
    codigo, salida = ejecutar()
    comprobar(codigo != 0 and "modelo en uso" in salida, "7 sin modelo en uso ni --modelo: para")
    # 10. ejecutar.py no quita filas
    codigo_fuente = EJECUTAR.read_text(encoding="utf-8")
    comprobar(not re.search(r"\.(dropna|drop_duplicates|query)\(|\.loc\[[^\]]*\]\s*=\s*None", codigo_fuente),
              "10 ejecutar.py no tiene ninguna llamada que tire filas")


def casos_de_validaciones_calculadas(s, julio):
    """El caso 15: las validaciones 6 y 7 del lote se calculan y pueden dar «no» (una nota del caso: antes iba un True escrito)."""
    spec_e = importlib.util.spec_from_file_location("ejecutar_68", EJECUTAR)
    e = importlib.util.module_from_spec(spec_e)
    spec_e.loader.exec_module(e)
    if not (hasattr(e, "ficha_cuadra") and hasattr(e, "sin_quitar_filas")):
        comprobar(False, "15 ejecutar.py tiene ficha_cuadra y sin_quitar_filas")
        return
    # Validación 7: la ficha del modelo de juguete cuadra; con otra huella del fichero, del módulo o con otras columnas, no
    modelo = TMP / "modelos" / "reentrenos" / HOY / "modelo_riesgo.joblib"
    ficha = json.loads((TMP / "modelos" / "reentrenos" / HOY / "modelo_riesgo_versiones.json").read_text(encoding="utf-8"))
    lee = ficha["columnas_entrada"]
    comprobar(e.ficha_cuadra(modelo, ficha, lee) is True, "15 la ficha del modelo cuadra")
    for nombre, mala, cols in (("otra huella del fichero", {**ficha, "huella": "0" * 64}, lee),
                               ("otra huella del módulo", {**ficha, "huella_modulo": "0" * 64}, lee),
                               ("otra versión de pandas", {**ficha, "versiones": {**ficha["versiones"], "pandas": "0.0.1"}}, lee),
                               ("otras columnas", ficha, lee[:-1])):
        comprobar(e.ficha_cuadra(modelo, mala, cols) is False, f"15 la ficha no cuadra con {nombre}")
    # Validación 6: los mismos discos en su orden y cada fila puntuada o con su motivo
    foto = pd.DataFrame({"serial_number": [d for d, _, _ in julio]})
    comprobar(e.sin_quitar_filas(foto, s) is True, "15 la salida buena no quita filas")
    sin_una = s.drop(index=7).reset_index(drop=True)
    comprobar(e.sin_quitar_filas(foto, sin_una) is False, "15 una fila menos: quita filas")
    otro_orden = s.iloc[[1, 0, *range(2, len(s))]].reset_index(drop=True)
    comprobar(e.sin_quitar_filas(foto, otro_orden) is False, "15 dos filas cambiadas de orden: no es la misma salida")
    sin_motivo = s.copy()
    i = sin_motivo.index[sin_motivo["probabilidad"].isna()][0]
    sin_motivo.loc[i, "motivo"] = None
    comprobar(e.sin_quitar_filas(foto, sin_motivo) is False, "15 una fila sin puntuar y sin motivo: no cuenta como guardada")
    # Ninguna validación del lote con su resultado escrito
    escritas = re.findall(r'"\w+":\s*(?:True|False)\b', EJECUTAR.read_text(encoding="utf-8"))
    comprobar(not escritas, f"15 ninguna validación con su resultado escrito en ejecutar.py ({escritas})")


def casos_de_varias_carpetas(s, carpeta, argumentos):
    """Los casos 11 a 14: la historia en varias carpetas y el archivo por mes."""
    a, b = TMP / "historia_a", TMP / "historia_b"
    for c in (a / "fotos", b / "fotos", a / "ventanas", b / "ventanas"):
        c.mkdir(parents=True)
    shutil.copy(POD / "fotos_mensuales" / "2024-05.parquet", a / "fotos")
    for m in ("2024-06", "2024-07"):
        shutil.copy(POD / "fotos_mensuales" / f"{m}.parquet", b / "fotos")
    shutil.copy(POD / "ventanas_fallo" / "data_Q2_2024.parquet", a / "ventanas")
    dos = ["--fotos-anteriores", str(a / "fotos"), str(b / "fotos"), "--ventanas", str(a / "ventanas"), str(b / "ventanas")]
    julio = POD / "fotos_mensuales" / "2024-07.parquet"
    base = ["--raiz", str(TMP), "--hoy", HOY, "--foto", str(julio), "--mes", "2024-07"]
    # 11. La historia en dos carpetas da lo mismo que en una, y la prueba por otro camino lo confirma
    codigo, salida = correr(EJECUTAR, *base, *dos)
    ruta = carpeta / "predicciones_2024-07.parquet"
    otra = pd.read_parquet(ruta) if codigo == 0 else None
    comprobar(otra is not None and otra.equals(s), f"11 la historia repartida en dos carpetas da la misma salida que en una ({codigo}; {salida[-300:]})")
    sin_historia = [x for i, x in enumerate(argumentos) if x not in ("--fotos-anteriores", "--ventanas")
                    and argumentos[i - 1] not in ("--fotos-anteriores", "--ventanas")]
    codigo, salida = correr(OTRO, *sin_historia, *dos)
    comprobar(codigo == 0, f"11 la prueba por otro camino coincide con la historia en dos carpetas ({codigo}; {salida[-300:]})")
    # 12. Dos ventanas con el mismo nombre en carpetas distintas: cuentan las dos
    v = pd.DataFrame({"serial_number": ["D022"], "fecha": pd.to_datetime(["2024-05-15"]).astype("datetime64[ms]"), "date": ["2024-05-15"],
                      "dia_fallo": pd.to_datetime(["2024-06-01"]).astype("datetime64[ns]"), "model": ["ST12000NM0008"],
                      "capacity_bytes": [C12], "failure": [0]})
    pq.write_table(pa.Table.from_pandas(v, preserve_index=False), b / "ventanas" / "data_Q2_2024.parquet")
    codigo, salida = correr(EJECUTAR, *base, *dos)
    res = json.loads((carpeta / "resumen_2024-07.json").read_text(encoding="utf-8"))
    comprobar(codigo == 0 and res["historial"]["discos_con_ventana_ya_ocurrida"] == 2,
              f"12 dos ventanas con el mismo nombre en dos carpetas cuentan las dos ({codigo}; {res['historial']})")
    # 13. Una carpeta de historia que no existe
    codigo, salida = correr(EJECUTAR, *base, "--fotos-anteriores", str(a / "fotos"), str(TMP / "no_existe"), "--ventanas", str(a / "ventanas"))
    comprobar(codigo != 0 and "no existe" in salida, f"13 una carpeta de historia que no existe: para ({codigo})")
    # 14. El archivo por mes: junio y julio el mismo día, los dos a la vista; junio otra vez, solo el primer junio al archivo
    def archivados(mes):
        return len(list((carpeta / "_archivo").rglob(f"predicciones_{mes}.parquet"))) if (carpeta / "_archivo").exists() else 0
    julios = archivados("2024-07")
    junio = POD / "fotos_mensuales" / "2024-06.parquet"
    una = ["--fotos-anteriores", str(POD / "fotos_mensuales"), "--ventanas", str(POD / "ventanas_fallo")]
    codigo, _ = correr(EJECUTAR, "--raiz", str(TMP), "--hoy", HOY, "--foto", str(junio), "--mes", "2024-06", *una)
    comprobar(codigo == 0 and ruta.exists() and (carpeta / "resumen_2024-07.json").exists()
              and (carpeta / "predicciones_2024-06.parquet").exists() and archivados("2024-07") == julios,
              f"14 dos meses lanzados el mismo día quedan los dos a la vista ({codigo}; julios archivados {julios} y {archivados('2024-07')})")
    codigo, _ = correr(EJECUTAR, "--raiz", str(TMP), "--hoy", HOY, "--foto", str(junio), "--mes", "2024-06", *una)
    comprobar(codigo == 0 and archivados("2024-06") == 1 and archivados("2024-07") == julios and ruta.exists()
              and len(list((carpeta / "_archivo").rglob("resumen_2024-06.json"))) == 1,
              f"14 el mismo mes dos veces deja el primero en _archivo/ y no toca el otro mes ({archivados('2024-06')}, {archivados('2024-07')})")


def pc_texto(columna):
    """La columna como texto, como llegaría de un CSV mal leído."""
    return pa.array([None if v is None else str(v) for v in columna.to_pylist()], type=pa.string())


# ---------------------------------------------------------------------------------------------------------------
# 4. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"intérprete: {sys.executable}")
    try:
        faltan = [p for p in (EJECUTAR, OTRO) if not p.exists()]
        if faltan:
            for p in faltan:
                comprobar(False, f"existe {p.relative_to(CASO).as_posix()}")
        else:
            casos()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos" if FALLOS else "\ntodo en verde")
    sys.exit(1 if FALLOS else 0)
