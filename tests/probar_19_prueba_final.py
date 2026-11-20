"""Prueba de scripts/19_prueba_final.py (petición 23, segunda parte; método preproduccion y programacion-del-caso).

Monta en tests/tmp_prueba_final/ un caso pequeño con el de tests/probar_ejecutar.py (contrato, configuración, un modelo
de juguete en uso, fotos en bruto de mayo a julio de 2024 y sus ventanas) y le añade:
  - la foto de agosto de 2024, con dos tomos: T1 (sac0, vault 7, ranura 3), donde un disco de 12 TB falló el 25/07, dentro
    de su plazo de 13 días el 01/08, y T2 (sac0, vault 8, ranura 5), donde uno de 4 TB falló el 20/07, fuera de su plazo
    de 5 días; las ventanas de esos dos fallos, con el sitio en el día anterior y la ranura vacía el día del fallo;
  - la lista de fallos: uno el mismo día de la foto de julio (no cuenta), uno el día 30 (cuenta), uno el día 31 (no
    cuenta en julio y es el día de la foto de agosto), uno en T1 y otro en T2 en agosto;
  - el año guardado de juguete, en data/raw/reserva/: tres fotos (septiembre a noviembre de 2024) con su lista de
    fallos; noviembre tiene el horizonte recortado y no se mide;
  - un modelado.json de juguete que no es el suyo y, después, uno con las cifras que da el ensayo.
Los periodos de los dos modos se cambian en el módulo para el caso pequeño; el resto del script es el de verdad.

Casos:
  1. sin modo, o con los dos, el script no arranca (sin valor por defecto);
  2. las funciones copiadas del script 15 son las mismas, letra a letra, y el reparto de un empate en la lista;
  3. el objetivo: el fallo del mismo día no cuenta, el del día 30 sí y el del 31 no; la comprobación por otro camino
     sale en rojo con un objetivo que cuenta el fallo del mismo día;
  4. las comprobaciones en rojo: una fila de salida sin su fila de la foto; un mes medido con el horizonte recortado; filas
     distintas para el modelo y la regla; la huella de data/raw/ que cambia; una validación con su resultado escrito; el 5 %
     redondeado como Excel;
  5. --reserva sin ensayo en OK: ERROR;
  6. el ensayo con un modelado que no es el suyo: ERROR, y dice qué cifra difiere;
  7. el ensayo con el modelado de sus cifras: OK; julio con 1 fallo y agosto con 2; los tomos de agosto (T1 en peligro con
     10 fotos y 1 fallo, lista de 1; T2 no); la historia del ensayo sin el año guardado; las salidas de los dos meses en
     data/predicciones/<hoy>/;
  8. --reserva: mide septiembre y octubre, no noviembre; escribe prueba_final.json, prueba_final.md y la tabla del año
     guardado con las columnas del contrato, que puntúa igual que la salida; data/raw/ sin cambios;
  9. --reserva por segunda vez: para sin tocar lo medido.
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
SCRIPT = CASO / "scripts" / "19_prueba_final.py"
TMP = CASO / "tests" / "tmp_prueba_final"
HOY = "2026-11-19"
FALLOS = []


def cargar(nombre, ruta):
    """Carga un fichero Python como módulo; su trabajo está bajo __main__ y no se ejecuta."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def comprobar(condicion, caso):
    """Apunta el caso si no se cumple y lo imprime."""
    print(("ok    " if condicion else "FALLA ") + caso)
    if not condicion:
        FALLOS.append(caso)


# El caso pequeño de probar_ejecutar.py, en la carpeta de esta prueba
PE = cargar("probar_ejecutar", CASO / "tests" / "probar_ejecutar.py")
PE.TMP = PE.PR.TMP = TMP
PE.POD = TMP / "data" / "raw" / "podado"
POD, RES = PE.POD, TMP / "data" / "raw" / "reserva"
C4, C12 = PE.C4, PE.C12
BASE = [(f"D{i:03d}", ["ST4000DM000", "ST12000NM0008", "TOSHIBA MG07ACA14TA"][i % 3], [C4, C12, C12][i % 3]) for i in range(150)]


# ---------------------------------------------------------------------------------------------------------------
# 2. Los datos en bruto que añade esta prueba
# ---------------------------------------------------------------------------------------------------------------
def foto_con_sitio(js, mes, semilla, tomos):
    """Una foto en bruto de los 150 discos con vault y ranura; tomos: {serial: (centro, vault, ranura)}."""
    t = PE.foto_en_bruto(js, pd.Timestamp(mes), BASE, semilla)
    serial = t["serial_number"].to_pylist()
    centro = [tomos[s][0] if s in tomos else c for s, c in zip(serial, t["datacenter"].to_pylist())]
    t = t.set_column(t.schema.get_field_index("datacenter"), "datacenter", pa.array(centro, type=pa.string()))
    t = t.append_column("vault_id", pa.array([tomos[s][1] if s in tomos else None for s in serial], type=pa.int64()))
    return t.append_column("pod_slot_num", pa.array([float(tomos[s][2]) if s in tomos else None for s in serial], type=pa.float64()))


def escribir_fallos(ruta, filas):
    """La lista de fallos en bruto: serial_number y dia_fallo en nanosegundos, como data/raw/."""
    df = pd.DataFrame({"serial_number": [s for s, _ in filas], "dia_fallo": pd.to_datetime([d for _, d in filas]).astype("datetime64[ns]")})
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), ruta)


def ventanas_de_los_tomos(ruta):
    """Las ventanas de los dos fallos de los tomos: el sitio el día anterior y la ranura vacía el día del fallo."""
    filas = [("X1", "2024-07-23", "2024-07-25", "ST12000NM0008", C12, 7, 3.0), ("X1", "2024-07-24", "2024-07-25", "ST12000NM0008", C12, 7, 3.0),
             ("X1", "2024-07-25", "2024-07-25", "ST12000NM0008", C12, 7, None),
             ("X2", "2024-07-19", "2024-07-20", "ST4000DM000", C4, 8, 5.0), ("X2", "2024-07-20", "2024-07-20", "ST4000DM000", C4, 8, None)]
    v = pd.DataFrame(filas, columns=["serial_number", "date", "dia_fallo", "model", "capacity_bytes", "vault_id", "pod_slot_num"])
    v["fecha"] = pd.to_datetime(v["date"]).astype("datetime64[ms]")
    v["dia_fallo"] = pd.to_datetime(v["dia_fallo"]).astype("datetime64[ns]")
    v["datacenter"], v["failure"] = "sac0", (v["date"] == v["dia_fallo"].dt.strftime("%Y-%m-%d")).astype("int64")
    v["vault_id"] = v["vault_id"].astype("int64")
    pq.write_table(pa.Table.from_pandas(v, preserve_index=False), ruta)


def montar():
    """El caso pequeño entero."""
    if TMP.exists():
        shutil.rmtree(TMP)
    js, _ = PE.montar()
    tomos = {**{f"D{i:03d}": ("sac0", 7, 3) for i in range(30, 40)}, **{f"D{i:03d}": ("sac0", 8, 5) for i in range(40, 45)}}
    pq.write_table(foto_con_sitio(js, "2024-08-01", 8, tomos), POD / "fotos_mensuales" / "2024-08.parquet")
    ventanas_de_los_tomos(POD / "ventanas_fallo" / "data_Q3_2024.parquet")
    escribir_fallos(POD / "fallos.parquet", [("D050", "2024-07-01"), ("D051", "2024-07-31"), ("D052", "2024-08-01"),
                                             ("X1", "2024-07-25"), ("X2", "2024-07-20"), ("D033", "2024-08-10"), ("D041", "2024-08-12")])
    (RES / "fotos_mensuales").mkdir(parents=True)
    (RES / "ventanas_fallo").mkdir(parents=True)
    for k, mes in enumerate(("2024-09", "2024-10", "2024-11")):
        pq.write_table(foto_con_sitio(js, f"{mes}-01", 20 + k, {}), RES / "fotos_mensuales" / f"{mes}.parquet")
    escribir_fallos(RES / "fallos.parquet", [("D060", "2024-09-15"), ("D061", "2024-10-31"), ("D062", "2024-11-20")])
    return js


def periodos_de_prueba(M):
    """Los periodos de los dos modos, cambiados para el caso pequeño; lo demás, como en el script."""
    M.MODOS["ensayo"].update({"desde": "2024-07", "hasta": "2024-08", "fin": "2024-08-31", "medidos": 2})
    M.MODOS["reserva"].update({"desde": "2024-09", "hasta": "2024-11", "fin": "2024-11-30", "medidos": 2})


def leer(ruta):
    """Un JSON del caso pequeño, o None si no existe."""
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


# ---------------------------------------------------------------------------------------------------------------
# 3. Las funciones y las comprobaciones, una a una
# ---------------------------------------------------------------------------------------------------------------
def funcion(texto, nombre):
    """El texto de una función de primer nivel, de su def a la línea en blanco que la cierra."""
    m = re.search(rf"^def {nombre}\(.*?(?=^\S|\Z)", texto, flags=re.S | re.M)
    return m.group(0).rstrip() if m else None


def casos_de_funciones(M):
    """Los casos 1 a 4."""
    # 1. Sin modo o con los dos
    for args in ([], ["--ensayo-validacion", "--reserva"]):
        r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP), *args], capture_output=True, text=True,
                           encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, timeout=150)
        comprobar(r.returncode != 0 and "usage" in r.stderr.lower(), f"1 el script no arranca con {args or 'ningún modo'}")
    # 2. Las funciones copiadas del 15, letra a letra, y el empate
    t15, t19 = (CASO / "scripts" / "15_modelado.py").read_text(encoding="utf-8"), SCRIPT.read_text(encoding="utf-8")
    for nombre in ("fallos_en_lista", "claves_regla", "rango_denso", "intervalo_meses"):
        comprobar(funcion(t15, nombre) is not None and funcion(t15, nombre) == funcion(t19, nombre), f"2 {nombre} es la del script 15")
    comprobar(M.fallos_en_lista([[0.9, 0.5, 0.5, 0.1]], [0, 1, 0, 0], 2) == 0.5,
              "2 un empate en el puesto 2 se reparte: medio fallo")
    # 3. El objetivo y su comprobación por otro camino
    fallos = pd.DataFrame({"serial_number": ["A", "B", "C"], "dia_fallo": pd.to_datetime(["2024-07-01", "2024-07-31", "2024-08-01"]).astype("datetime64[ms]")})
    serial, fecha = np.array(["A", "B", "C", "D"], dtype=object), pd.Timestamp("2024-07-01")
    hor = M.horizonte(fecha, pd.Timestamp("2025-06-30"))
    y = M.objetivo(serial, fecha, hor, fallos)
    comprobar(list(y) == [0, 1, 0, 0] and hor == pd.Timestamp("2024-07-31"), f"3 el objetivo: mismo día no, día 30 sí, día 31 no ({list(y)}, {hor})")
    comprobar(M.comprobar_objetivo(serial, fecha, hor, fallos, y) == 0, "3 la comprobación del objetivo por otro camino coincide")
    comprobar(M.comprobar_objetivo(serial, fecha, hor, fallos, np.array([1, 1, 0, 0])) == 1,
              "3 la comprobación del objetivo sale en rojo si cuenta el fallo del mismo día")
    comprobar(M.horizonte(pd.Timestamp("2025-06-01"), pd.Timestamp("2025-06-30")) == pd.Timestamp("2025-06-30"), "3 el horizonte se recorta al fin del periodo")
    # 4. Las comprobaciones en rojo
    foto = pd.DataFrame({"serial_number": ["A", "B", "C"]})
    comprobar(M.alineadas(pd.DataFrame({"serial_number": ["A", "B", "C"]}), foto)
              and not M.alineadas(pd.DataFrame({"serial_number": ["A", "X", "C"]}), foto)
              and not M.alineadas(pd.DataFrame({"serial_number": ["A", "B", "C", "D"]}), foto),
              "4 una fila de la salida sin su fila de la foto: rojo")
    fin = pd.Timestamp("2024-11-30")
    comprobar(M.meses_recortados([pd.Timestamp("2024-10-01")], fin) == [] and M.meses_recortados([pd.Timestamp("2024-11-01")], fin) == ["2024-11-01"],
              "4 un mes medido con el horizonte recortado: rojo")
    comprobar(M.mismas_filas(np.array(["A", "B"]), np.array(["A", "B"])) and not M.mismas_filas(np.array(["A", "B"]), np.array(["A", "C"])),
              "4 filas distintas para el modelo y la regla: rojo")
    d = TMP / "huellas" / "data" / "raw"
    d.mkdir(parents=True)
    (d / "a.txt").write_text("uno", encoding="utf-8")
    antes = M.huellas(TMP / "huellas")
    (d / "a.txt").write_text("dos", encoding="utf-8")
    comprobar(antes != M.huellas(TMP / "huellas") and M.huellas(TMP / "huellas") == M.huellas(TMP / "huellas"),
              "4 la huella de data/raw/ que cambia: rojo")
    shutil.rmtree(TMP / "huellas")
    comprobar(M.sin_resultados_escritos(t19) and not M.sin_resultados_escritos('v = {"iguales": ' + "True}")
              and not M.sin_resultados_escritos("validaciones['x'] = " + "False"),
              "4 ninguna validación del script con su resultado escrito, y la comprobación sabe dar rojo")
    comprobar(M.parte_de(50) == 3 and M.parte_de(10) == 1 and M.parte_de(0) == 0 and M.parte_de(41) == 2,
              "4 el 5 % de las fotos en peligro, redondeado como Excel y al menos 1")


# ---------------------------------------------------------------------------------------------------------------
# 4. Los modos, de principio a fin
# ---------------------------------------------------------------------------------------------------------------
def modelado_de(ensayo):
    """Un modelado.json de juguete con las cifras que dio el ensayo."""
    por_mes = [{"mes": r["mes"], "filas": r["filas_medidas"], "fallos": r["fallos"], "modelo_lista_20": r["modelo_lista_20"],
                "modelo_lista_100": r["modelo_lista_100"]} for r in ensayo["por_mes"]]
    js = {"resultado": {"estado": "OK"}, "validacion": {"por_mes": por_mes, "medidas": {"auc": ensayo["auc"]["modelo"]["auc"]},
                                                         "referencias": {"regla": {"auc": ensayo["auc"]["regla"]["auc"]}}}}
    (TMP / "informes" / "modelado.json").write_text(json.dumps(js), encoding="utf-8")


def casos_de_modos(M):
    """Los casos 5 a 9."""
    j_ens, j_res = TMP / "informes" / "prueba_final_ensayo.json", TMP / "informes" / "prueba_final.json"
    tabla = TMP / "data" / "processed" / "fotos_riesgo_reserva.parquet"
    raw_antes = M.huellas(TMP)
    # 5. --reserva sin ensayo
    codigo = M.principal(TMP, "reserva", HOY)
    r = leer(j_res)
    comprobar(codigo != 0 and r is not None and r["resultado"]["estado"] == "ERROR" and "ensayo" in r["resultado"]["resumen"]
              and not tabla.exists(), f"5 --reserva sin el ensayo en OK: ERROR ({codigo}; {(r or {}).get('resultado')})")
    j_res.unlink(missing_ok=True)
    # 6. El ensayo con un modelado que no es el suyo
    codigo = M.principal(TMP, "ensayo", HOY)
    e = leer(j_ens)
    comprobar(codigo != 0 and e is not None and e["resultado"]["estado"] == "ERROR" and e["comparacion"]["iguales"] is False
              and any("modelo_lista_100" in x or "filas" in x for x in e["comparacion"]["distintos"]),
              f"6 el ensayo con otro modelado: ERROR y dice qué difiere ({codigo}; {(e or {}).get('comparacion', {}).get('distintos', [])[:3]})")
    if e is None or not e.get("por_mes"):
        return
    # 7. El ensayo con el modelado de sus cifras
    modelado_de(e)
    codigo = M.principal(TMP, "ensayo", HOY)
    e = leer(j_ens)
    comprobar(codigo == 0 and e["resultado"]["estado"] == "OK" and e["comparacion"]["iguales"] is True,
              f"7 el ensayo con el modelado de sus cifras: OK ({codigo}; {e['resultado']['resumen'][:300]})")
    mes = {r["mes"]: r for r in e["por_mes"]}
    comprobar([mes["2024-07-01"]["fallos"], mes["2024-08-01"]["fallos"]] == [1, 2],
              f"7 julio con 1 fallo (el del día 30) y agosto con 2 ({[r['fallos'] for r in e['por_mes']]})")
    t = mes["2024-08-01"]["tomos"]
    comprobar(t["tomos_en_peligro"] == 1 and t["fotos"] == 10 and t["fallos"] == 1 and t["lista"] == 1 and mes["2024-07-01"]["tomos"]["fotos"] == 0,
              f"7 los tomos: T1 en peligro (10 fotos, 1 fallo, lista de 1), T2 fuera de plazo ({t})")
    resumenes = [leer(TMP / "data" / "predicciones" / HOY / f"resumen_{m}.json") for m in ("2024-07", "2024-08")]
    comprobar(all(r is not None for r in resumenes) and all("reserva" not in c for r in resumenes for c in r["historial"]["ruta"]["fotos"] + r["historial"]["ruta"]["ventanas"]),
              "7 las salidas de los dos meses quedan en data/predicciones/<hoy>/ y la historia del ensayo no lee el año guardado")
    comprobar(e["validaciones"]["huella_de_data_raw_igual"] is True and e["validaciones"]["objetivo_sin_fallos_anteriores"] is True,
              "7 el ensayo escribe sus validaciones calculadas")
    # 8. --reserva
    codigo = M.principal(TMP, "reserva", HOY)
    r = leer(j_res)
    comprobar(codigo == 0 and r is not None and r["resultado"]["estado"] in ("OK", "AVISO"),
              f"8 --reserva termina ({codigo}; {(r or {}).get('resultado')})")
    if r is None or not r.get("por_mes"):
        return
    medidos = [x["mes"] for x in r["por_mes"] if x["se_mide"]]
    nov = [x for x in r["por_mes"] if x["mes"] == "2024-11-01"]
    comprobar(medidos == ["2024-09-01", "2024-10-01"] and nov and nov[0]["se_mide"] is False,
              f"8 mide septiembre y octubre; noviembre, con el horizonte recortado, no ({medidos})")
    comprobar([x["fallos"] for x in r["por_mes"] if x["se_mide"]] == [1, 1], "8 un fallo en septiembre y otro el día 30 de octubre")
    comprobar(all(k in r for k in ("intervalo", "auc", "matthews", "tomos", "se_da_por_bueno", "frente_a", "totales")),
              "8 prueba_final.json trae el intervalo, el AUC, Matthews, los tomos, si se da por bueno y frente a qué")
    md = TMP / "informes" / "prueba_final.md"
    texto = md.read_text(encoding="utf-8") if md.exists() else ""
    primera = next((x for x in texto.splitlines() if x and not x.startswith("#")), "")
    comprobar("## Datos personales" in texto and ("no se da por bueno" in primera) == (not r["se_da_por_bueno"])
              and ("responsable del caso" in primera) == (not r["se_da_por_bueno"]), f"8 prueba_final.md abre con el veredicto ({primera[:200]})")
    bueno = {**r, "se_da_por_bueno": not r["se_da_por_bueno"], "intervalo": {**r["intervalo"], "media": 2.0, "bajo": 1.0, "alto": 3.0},
             "auc": {**r["auc"], "modelo": {**r["auc"]["modelo"], "auc": 0.9}}}
    otra = M.informe_md(bueno).splitlines()[2]
    comprobar(otra.startswith("El modelo se da por bueno") and "responsable del caso" not in otra if bueno["se_da_por_bueno"] else "no se da por bueno" in otra,
              f"8 el informe abre con el veredicto contrario cuando cambian las cifras ({otra[:120]})")
    print("\n--- informe del caso pequeño ---\n" + texto + "--- fin ---\n")
    t = pd.read_parquet(tabla) if tabla.exists() else None
    contrato = M.pr.leer_contrato(TMP)
    comprobar(t is not None and list(t.columns) == ["serial_number", "fecha", *contrato["lee"], "horizonte_hasta", "falla_30d"]
              and len(t) == r["totales"]["filas_medidas"] and int(t["falla_30d"].sum()) == 2,
              f"8 la tabla del año guardado: las filas medidas con las columnas del contrato ({None if t is None else len(t)})")
    comprobar(r["validaciones"]["tabla_puntua_igual_que_la_salida"] is True, "8 la tabla del año guardado puntúa igual que la salida de ejecutar.py")
    comprobar(M.huellas(TMP) == raw_antes, "8 data/raw/ sin cambios después de los dos modos")
    # 9. --reserva otra vez
    antes = j_res.read_text(encoding="utf-8")
    codigo = M.principal(TMP, "reserva", HOY)
    comprobar(codigo != 0 and j_res.read_text(encoding="utf-8") == antes, "9 --reserva otra vez: para y no toca lo medido")
    casos_del_texto(M, j_res, md)


def casos_del_texto(M, j_res, md):
    """Los casos 10 y 11: el texto del informe y rehacerlo desde el JSON sin volver a medir."""
    r = leer(j_res)
    # 10. El texto: la regla con su nombre, recuentos sin decimales, lo no medido legible y los límites con su cifra
    texto = M.informe_md(r)
    comprobar("cinco contadores" not in texto and "cinco avisos SMART" in texto, "10 la regla se llama «de los cinco avisos SMART»")
    comprobar(getattr(M, "cifra", None) is not None and M.cifra(27.0) == "27" and M.cifra(1157.0) == "1.157" and M.cifra(0.5) == "0,50",
              "10 un recuento entero sale sin decimales y un empate repartido, con dos")
    # Los dos motivos que deja ejecutar.py en el año real (el caso pequeño no tiene filas sin puntuar)
    sin = [{"motivo": "disco de arranque: fuera del modelo (reglas, apartado 3 y §7)", "filas": 43512},
           {"motivo": "foto del día del fallo: el disco ya está marcado como fallado (reglas de transformación §3)", "filas": 123}]
    texto = M.informe_md({**r, "totales": {**r["totales"], "sin_puntuar": sin}})
    no_medido = texto.split("## Lo que no se midió")[1].split("##")[0]
    vinetas = [x for x in no_medido.splitlines() if x.startswith("- ")]
    comprobar(vinetas and all(x[2].isupper() for x in vinetas) and "§" not in no_medido,
              f"10 lo que no se midió empieza en mayúscula y sin citar párrafos de las reglas ({vinetas[:2]})")
    falso = {**r, "tomos_fallos": {**r["tomos_fallos"], "de_datos_con_tomo": 4750, "sin_ventana": 0},
             "totales": {**r["totales"], "tomos": {**r["totales"]["tomos"], "fallos": 113.0}}}
    lim = " ".join(M.limites(falso, "reserva"))
    comprobar("113" in lim and "4.750" not in lim and "Otros 0" not in lim,
              f"10 el límite de los tomos cita los fallos que mide, y un cero no se escribe ({lim[:200]})")
    falso["tomos_fallos"]["sin_ventana"] = 3
    comprobar("3 fallos" in " ".join(M.limites(falso, "reserva")), "10 los fallos sin ventana se dicen si los hay")
    # 12. Auditor antes de entregar (20/11/2026, una nota del caso): el modelo en uso se aprobó después de medirlo en el año
    # guardado, así que el límite no puede decir que no se eligió con él. La regla sencilla no se usa (El responsable del caso, una nota del caso)
    lim = " ".join(M.limites(r, "reserva"))
    comprobar("El modelo en uso no se volvió a elegir" not in lim and "antes de aprobarlo" in lim,
              f"12 el límite dice que el modelo en uso se midió en el año guardado antes de aprobarlo ({lim[-300:]})")
    comprobar("referencia_cambio_contadores" not in lim and "187 y" not in lim, "12 el límite no nombra la regla sencilla")
    # 11. --solo-informe: rehace el informe y el texto del JSON desde lo medido, sin medir
    solo = getattr(M, "solo_informe", None)
    if solo is None:
        comprobar(False, "11 existe solo_informe")
        return
    md.unlink()
    antes = leer(j_res)
    codigo = solo(TMP)
    despues = leer(j_res)
    comprobar(codigo == 0 and md.exists() and "cinco avisos SMART" in md.read_text(encoding="utf-8"),
              f"11 --solo-informe escribe el informe con el texto nuevo ({codigo})")
    comprobar(all(despues[k] == antes[k] for k in ("por_mes", "totales", "intervalo", "auc", "matthews", "se_da_por_bueno", "validaciones")),
              "11 --solo-informe no cambia ninguna cifra ni validación")
    comprobar("cinco avisos SMART" in despues["resultado"]["resumen"] and despues["limites"] == M.limites(despues, "reserva"),
              "11 --solo-informe pone al día el resumen y los límites del JSON")
    j_res.unlink()
    comprobar(solo(TMP) != 0, "11 --solo-informe sin el año guardado medido: para")


# ---------------------------------------------------------------------------------------------------------------
# 5. Ejecución
# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"intérprete: {sys.executable}")
    try:
        if not SCRIPT.exists():
            comprobar(False, f"existe {SCRIPT.relative_to(CASO).as_posix()}")
        else:
            montar()
            M = cargar("prueba_final_19", SCRIPT)
            periodos_de_prueba(M)
            casos_de_funciones(M)
            casos_de_modos(M)
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} fallos" if FALLOS else "\ntodo en verde")
    sys.exit(1 if FALLOS else 0)
