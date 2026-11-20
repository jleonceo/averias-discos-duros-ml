"""Prueba de scripts/18_contrato_produccion.py (skill preproduccion, parte 1; encargo del caso 68, primera parte).

Monta en tests/tmp_contrato/ un caso de juguete con lo único que lee el script: informes/modelado.json, el registro de
transformaciones, las reglas de transformación y la matriz. El ganador de juguete es un HistGradientBoosting con ocho
columnas y su preprocesador lee nueve, con datacenter. Los documentos se escriben aquí, con el estado que se prueba
escrito en la copia (programacion-del-caso §2 y error 31), y no se heredan de los del caso.

Casos:
  1. verde: el contrato se escribe aprobado (Juan, 19/11/2026), el JSON queda en AVISO con la aprobación y el arreglo
     de la historia de ventanas (fallos anteriores a la foto, con dia_fallo); cada finalista tiene su
     cadena con fichas que existen y cada paso una de las cuatro clases;
  2. modelado sin aprobar (ganador.aprobado_por vacío): PARADO y sin contrato;
  3. modelado en ERROR: PARADO y sin contrato;
  4. validación que no da el modelo por bueno: PARADO y sin contrato;
  5. finalista sin cadena (el registro no trae R-013, la ficha que la produce): ERROR y sin contrato;
  6. paso sin clase (el registro trae una ficha R-025 sobre fotos_riesgo que el contrato no clasifica): ERROR;
  7. paso que aprende ajustado antes de la partición (R-020 escrita después de R-021): ERROR;
  8. contrato con un campo vacío (la muestra del ganador vacía en modelado.json): ERROR;
  9. una columna del ganador que no sale de ninguna finalista (no está en la matriz): ERROR;
 10. una finalista sin definición en el registro ni en las reglas (las reglas no nombran edad_anos): ERROR.
Y la búsqueda de comprobaciones escritas con su resultado puesto (error 24) en el código del script, que tiene que
cazar una escrita a propósito.

Sale con 0 si todo pasa y con 1 si algo falla, e imprime qué caso falla. La carpeta temporal se borra siempre.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Preparación
# ---------------------------------------------------------------------------------------------------------------
import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

CASO = Path(__file__).resolve().parents[1]
SCRIPT = CASO / "scripts" / "18_contrato_produccion.py"
TMP = CASO / "tests" / "tmp_contrato"
CONTRATO = "contexto-proyecto/modelo/contrato_produccion.md"
SAL_JSON = "informes/preproduccion.json"
CLASES = {"quita filas", "no aprende", "necesita otras filas", "aprende"}
FALLOS = []

# El ganador de juguete: ocho columnas; el preprocesador lee además datacenter
COLUMNAS = ["capacidad_tb", "garantia_anos", "smart_5_raw", "edad_anos", "avisa", "cambio_smart_5", "model",
            "fabricante"]
LEE = COLUMNAS + ["datacenter"]


def fallo(caso, mensaje):
    """Apunta un caso que falla y lo imprime."""
    FALLOS.append(f"{caso}: {mensaje}")
    print(f"  ROJO  {caso}: {mensaje}")


def bien(caso):
    """Imprime un caso que pasa."""
    print(f"  verde {caso}")


# ---------------------------------------------------------------------------------------------------------------
# 2. Los documentos de juguete
# ---------------------------------------------------------------------------------------------------------------
FICHAS = [
    ("R-001", "fotos mensuales y ventanas de fallo · datacenter", "El centro pasa a texto."),
    ("R-002", "fotos mensuales y ventanas de fallo · pod_slot_num", "La ranura pasa a entero."),
    ("R-003", "fotos mensuales y ventanas de fallo · date", "date pasa a fecha."),
    ("R-004", "fotos mensuales, ventanas de fallo y recuento diario · model", "Mapeo cerrado de modelos."),
    ("R-005", "fotos mensuales, ventanas de fallo y recuento diario · capacity_bytes", "Capacidad del modelo."),
    ("R-006", "recuento diario · fila", "Suma de filas con la misma clave."),
    ("R-007", "ventanas de fallo · fila", "Fuera las filas con la fecha distinta de su texto."),
    ("R-008", "fotos mensuales y ventanas de fallo · fichero", "Un Parquet por tabla."),
    ("R-009", "las cuatro tablas · lo que se deja sin cambios", "Un contador vacío no se rellena."),
    ("R-010", "igualación antes de cruzar · dia_fallo y centro vacío", "dia_fallo a milisegundos."),
    ("R-011", "dim_modelo · tabla nueva", "Capacidad, tipo, fabricante y garantía del modelo."),
    ("R-012", "dim_precio_gb · tabla nueva", "Precio por GB."),
    ("R-013", "fotos_riesgo · tabla nueva", "Una fila por disco de datos y foto."),
    ("R-014", "fallos_detalle · tabla nueva", "Una fila por fallo."),
    ("R-015", "vida_discos · tabla nueva", "Una fila por disco."),
    ("R-016", "dias_por_tramo · tabla nueva", "Días por tramo."),
    ("R-017", "inicio_trimestre · tabla nueva", "Discos al empezar el trimestre."),
    ("R-018", "modelo_trimestre · tabla nueva", "Modelo y trimestre."),
    ("R-019", "centro_mes · tabla nueva", "Centro y mes."),
    ("R-020", "fotos_riesgo · partición en entrenamiento y validación", "Partición por fecha."),
    ("R-021", "fotos_riesgo_entrenamiento · matriz de transformaciones aprobada", "La matriz."),
    ("R-022", "fotos_riesgo_entrenamiento · matriz corregida: seis copias fuera", "Seis copias fuera."),
    ("R-023", "fotos_riesgo_entrenamiento · preselección de variables de la logística", "Solo la logística."),
    ("R-024", "producción · contrato de producción aprobado", "El contrato aprobado; no cambia ningún dato."),
]
# La aprobación que el script lleva en su configuración (Juan, 19/11/2026)
APROBADO_POR = "Juan, 19/11/2026: «Sí, con el arreglo»"
FECHA_APROBACION = "2026-11-19"


def registro(fichas):
    """El texto del registro de juguete con las fichas dadas, en su orden."""
    partes = ["# Registro de transformaciones", ""]
    for numero, titulo, cuerpo in fichas:
        partes += [f"## {numero} · {titulo}", "", cuerpo, ""]
    return "\n".join(partes)


REGLAS_DE_QUE_SE_PARTE = ("**La edad**, que usan cuatro tablas, se calcula siempre igual: las horas encendido de la "
                          "fila, pasadas a años; si no las trae, los días desde la primera aparición del disco.")
REGLAS_DIM = ("- `capacidad_tb`: capacity_bytes entre 10^12.\n- `tipo_disco`: arranque o datos.\n"
              "- `fabricante`: del nombre.\n- `garantia_anos`: del nombre.")
REGLAS_FOTOS = ("Entran las fotos de discos de datos, salvo las del día del fallo.\n- `serial_number`, `fecha`, `model`: "
                "los de la fila.\n- `capacidad_tb`, `fabricante`, `garantia_anos`: de `dim_modelo`.\n- `edad_anos`: con la "
                "regla de la edad.\n- `avisa`, `contadores_que_avisan`, `suma_contadores_sin_188`, `smart_188_no_cero`.\n"
                "- `cambio_smart_5`, `cambio_smart_187`, `cambio_smart_197`, `cambio_smart_198` y "
                "`meses_desde_foto_anterior`: contra la foto anterior.\n- `datacenter`: el de la fila.\n"
                "- `horizonte_hasta` y `falla_30d`: el objetivo.\nLas demás columnas, todas `smart_*`, pasan sin cambios.")


def reglas(de_que_se_parte=REGLAS_DE_QUE_SE_PARTE, fotos=REGLAS_FOTOS):
    """El texto de las reglas de transformación de juguete, con los apartados que cita el contrato."""
    return "\n".join(["# Reglas de transformación", "", "### De qué se parte", "", de_que_se_parte, "",
                      "### 1. Las dos dimensiones", "", "#### `dim_modelo`: una fila por modelo", "", REGLAS_DIM, "",
                      "### 3. `fotos_riesgo`: una fila por disco de datos y foto mensual", "", fotos, "",
                      "### 4. `fallos_detalle`: una fila por fallo", "", "Nada.", ""])


def matriz(variables):
    """La matriz de juguete: las variables que entran, todas en las tres familias salvo avisa (solo árboles)."""
    filas = ["# Matriz de transformaciones", "", f"## Columnas que entran ({len(variables)})", "",
             "| Variable | Tipo | Rama | Escalado | Relleno | Salida | Entra | Porqué |",
             "|---|---|---|---|---|---|---|---|"]
    for v in variables:
        entra = "solo bosque, hgb" if v == "avisa" else "sí"
        filas.append(f"| `{v}` | continua | H: tal cual | ninguno | ninguno | H: {v} | {entra} | prueba |")
    filas += ["", "## Columnas que no entran (1)", "", "| Variable | Tipo | Rama | Escalado | Relleno | Salida | Entra | Porqué |",
              "|---|---|---|---|---|---|---|---|", "| `smart_9_raw` | continua | — | — | — | — | no | prueba |", ""]
    return "\n".join(filas)


MODELADO = {
    "skill": "aprendizaje-automatico", "fecha_datos": "2025-06-30",
    "entradas": [{"ruta": "data/processed/fotos_riesgo_entrenamiento.parquet", "sha256": "abc", "filas": 1000}],
    "resultado": {"estado": "OK", "riesgo": "bajo", "resumen": "prueba"},
    "aprobado_antes": {"medida_principal": "los fallos encontrados entre los 100 discos de más riesgo de cada mes"},
    "validacion_cruzada": {"objetivo_sin_conocer": [{"entrenamiento": "ajuste final", "conocido_desde": "2024-07-01",
                                                     "filas_quitadas": 0, "eventos_quitados": 0}]},
    "desequilibrio": {"recalibracion": {"metodo": "corrección del prior sobre el logit", "tasa_muestra": 0.05,
                                        "tasa_real": 0.001}},
    "ganador": {"algoritmo": "hgb", "hiperparametros": {"min_samples_leaf": "hoja", "max_iter": 500, "max_depth": None,
                                                         "learning_rate": 0.025, "l2_regularization": 0.5},
                "semilla": 42, "columnas": COLUMNAS, "columnas_que_lee_el_preprocesador": LEE,
                "datacenter": "se vacía (sin sitio)",
                "muestra": "todas las fotos con fallo y el 2 % de las sanas de cada mes, semilla 42",
                "recalibracion": {"metodo": "corrección del prior sobre el logit", "tasa_muestra": 0.05,
                                  "tasa_real": 0.001},
                "aprobado_por": "Juan, prueba"},
    "ajuste_final": {"filas_entrena": 1000, "fallos_entrena": 1, "muestra": {"filas": 2500, "fallos": 50, "sanas": 2450},
                     "hoja": 25, "horizonte_max": "2024-06-30"},
    "validacion": {"se_da_por_bueno": True, "medidas": {"auc": 0.9},
                   "por_mes": [{"mes": "2024-07-01", "modelo_lista_20": 1.0, "modelo_lista_100": 2.0,
                                "modelo_lista_500": 3.0, "modelo_lista_1000": 4.0}]},
    "corte": {"valor": None, "como": "capacidad", "por_que": "el tamaño de la lista lo elige Backblaze (CP-010)"},
    "parametros": [{"nombre": "hoja", "valor": "max(20, 1 % de las filas que entrenan en el pliegue)", "origen": "x"},
                   {"nombre": "HistGradientBoosting", "valor": "early_stopping=False, categóricas nativas", "origen": "x"}],
}


def montar(modelado=None, fichas=None, texto_reglas=None, variables=None):
    """Monta tests/tmp_contrato/ con los cuatro documentos; cada argumento cambia el suyo."""
    if TMP.exists():
        shutil.rmtree(TMP)
    (TMP / "informes").mkdir(parents=True)
    (TMP / "contexto-proyecto" / "modelo").mkdir(parents=True)
    (TMP / "contexto-proyecto" / "negocio").mkdir(parents=True)
    (TMP / "informes" / "modelado.json").write_text(json.dumps(modelado or MODELADO, ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
    (TMP / "contexto-proyecto" / "modelo" / "registro-transformaciones.md").write_text(registro(fichas or FICHAS),
                                                                                       encoding="utf-8")
    (TMP / "contexto-proyecto" / "negocio" / "reglas-transformacion.md").write_text(texto_reglas or reglas(),
                                                                                    encoding="utf-8")
    (TMP / "contexto-proyecto" / "modelo" / "matriz_transformaciones.md").write_text(matriz(variables or LEE),
                                                                                     encoding="utf-8")


def ejecutar():
    """Ejecuta el script con -W error sobre la carpeta de juguete; devuelve el código, la salida y el JSON."""
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--raiz", str(TMP)], capture_output=True,
                       text=True, encoding="utf-8", timeout=120)
    ruta = TMP / SAL_JSON
    js = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
    return r.returncode, r.stdout + r.stderr, js


# ---------------------------------------------------------------------------------------------------------------
# 3. Los casos
# ---------------------------------------------------------------------------------------------------------------
def caso_verde():
    """El caso bueno: contrato escrito, PARADO a la espera de Juan, cadenas completas y cada paso con su clase."""
    nombre = "1 verde"
    montar()
    codigo, salida, js = ejecutar()
    if js is None:
        return fallo(nombre, f"no escribió el JSON (código {codigo}): {salida[-800:]}")
    errores = []
    if js["resultado"]["estado"] != "AVISO":
        errores.append(f"estado {js['resultado']['estado']}, se esperaba AVISO (contrato aprobado, parte 2 por hacer): "
                       f"{js['resultado'].get('resumen')}")
    if not (TMP / CONTRATO).exists():
        errores.append("no escribió el contrato")
    if js.get("contrato", {}).get("aprobado_por") != APROBADO_POR:
        errores.append(f"contrato.aprobado_por es {js.get('contrato', {}).get('aprobado_por')!r}")
    if js.get("contrato", {}).get("fecha") != FECHA_APROBACION:
        errores.append(f"contrato.fecha es {js.get('contrato', {}).get('fecha')!r}")
    # El arreglo: la historia de ventanas solo lleva fallos anteriores a la foto, y lo dice con dia_fallo
    ventanas = [h for h in js.get("historia_de_ejecutar", []) if "ventanas" in h["tabla"]]
    if not ventanas or "dia_fallo" not in ventanas[0]["columnas"] or "antes del día de la foto" not in ventanas[0]["hasta"]:
        errores.append(f"la historia de ventanas no lleva el arreglo: {ventanas}")
    pasos = {p["id"]: p for p in js.get("pasos", [])}
    for i in ("P06", "P12"):
        if "dia_fallo" not in pasos.get(i, {}).get("que", "") + pasos.get(i, {}).get("por_que", ""):
            errores.append(f"{i} no escribe el arreglo")
    variables = [f["variable"] for f in js.get("finalistas", [])]
    esperadas = set(LEE) | {"serial_number", "fecha", "falla_30d", "horizonte_hasta"}
    if set(variables) != esperadas:
        errores.append(f"finalistas {sorted(variables)}, se esperaban {sorted(esperadas)}")
    fichas = {f[0] for f in FICHAS}
    for f in js.get("finalistas", []):
        if not f.get("cadena"):
            errores.append(f"{f['variable']} sin cadena")
        for p in f.get("cadena", []):
            if p.get("clase") not in CLASES:
                errores.append(f"{f['variable']}: paso {p.get('paso')} con clase {p.get('clase')}")
            citadas = re.findall(r"R-\d{3}", p.get("ficha", ""))
            if any(c not in fichas for c in citadas):
                errores.append(f"{f['variable']}: cita una ficha que no existe: {p.get('ficha')}")
    # Las columnas del modelo de cada finalista: datacenter no saca ninguna (se vacía) y avisa saca la suya
    porvar = {f["variable"]: f.get("columnas_del_modelo") for f in js.get("finalistas", [])}
    if porvar.get("avisa") != ["avisa"]:
        errores.append(f"columnas_del_modelo de avisa: {porvar.get('avisa')}")
    v = js.get("validaciones", {})
    for k in ("cadenas_completas", "aprende_tras_la_particion", "contrato_sin_vacios", "pasos_con_clase"):
        if v.get(k) is not True:
            errores.append(f"validaciones.{k} = {v.get(k)}")
    # La receta y el corte salen del JSON del modelado
    receta = js.get("receta") or {}
    if receta.get("hiperparametros", {}).get("max_iter") != 500 or receta.get("semilla") != 42:
        errores.append(f"receta mal leída: {receta.get('hiperparametros')}")
    if receta.get("corte", {}).get("valores") != [20, 100, 500, 1000] or receta.get("corte", {}).get("principal") != 100:
        errores.append(f"corte mal leído: {receta.get('corte')}")
    if receta.get("hoja", {}).get("valor") != 25:
        errores.append(f"hoja {receta.get('hoja')}, se esperaba 25 (1 % de 2.500 filas)")
    texto = (TMP / CONTRATO).read_text(encoding="utf-8") if (TMP / CONTRATO).exists() else ""
    if f"estado: aprobado por {APROBADO_POR}" not in texto:
        errores.append("el estado del contrato no dice la aprobación")
    for apartado in ("## El identificador y el objetivo", "## Las finalistas y su cadena", "## Los pasos",
                     "## La receta del modelo", "## El corte", "## La historia que pide ejecutar"):
        if apartado not in texto:
            errores.append(f"el contrato no trae «{apartado}»")
    if errores:
        return fallo(nombre, "; ".join(errores))
    bien(nombre)


def caso_parado(nombre, cambiar):
    """Un modelado que no deja empezar: PARADO, sin contrato y con el JSON escrito."""
    m = copy.deepcopy(MODELADO)
    cambiar(m)
    montar(modelado=m)
    codigo, salida, js = ejecutar()
    if js is None:
        return fallo(nombre, f"no escribió el JSON (código {codigo}): {salida[-500:]}")
    if js["resultado"]["estado"] != "PARADO" or (TMP / CONTRATO).exists() or js.get("finalistas"):
        return fallo(nombre, f"estado {js['resultado']['estado']}, contrato escrito {(TMP / CONTRATO).exists()}")
    bien(nombre)


def caso_error(nombre, debe_decir, **cambios):
    """Un caso que tiene que parar con ERROR, sin contrato, y decir por qué."""
    montar(**cambios)
    codigo, salida, js = ejecutar()
    if js is None:
        return fallo(nombre, f"no escribió el JSON (código {codigo}): {salida[-500:]}")
    if js["resultado"]["estado"] != "ERROR":
        return fallo(nombre, f"estado {js['resultado']['estado']}, se esperaba ERROR")
    if (TMP / CONTRATO).exists():
        return fallo(nombre, "escribió el contrato aunque paró")
    if debe_decir not in js["resultado"]["resumen"]:
        return fallo(nombre, f"el resumen no dice «{debe_decir}»: {js['resultado']['resumen']}")
    bien(nombre)


def busqueda_de_resultados_puestos():
    """Error 24: ninguna validación del script lleva su resultado escrito; la búsqueda caza uno puesto a propósito."""
    nombre = "11 sin resultados puestos"
    patron = re.compile(r"""["'](cadenas_completas|aprende_tras_la_particion|contrato_sin_vacios|pasos_con_clase)["']\s*:\s*True""")
    if not SCRIPT.exists():
        return fallo(nombre, "no existe el script")
    if patron.search(SCRIPT.read_text(encoding="utf-8")):
        return fallo(nombre, "el script escribe una validación con True puesto")
    if not patron.search('{"cadenas_completas": True}'):
        return fallo(nombre, "la búsqueda no caza un True puesto a propósito")
    bien(nombre)


# ---------------------------------------------------------------------------------------------------------------
# 4. Ejecución
# ---------------------------------------------------------------------------------------------------------------
def main():
    """Ejecuta todos los casos y borra la carpeta temporal."""
    print(f"Intérprete: {sys.executable}")
    try:
        if not SCRIPT.exists():
            fallo("0 script", f"no existe {SCRIPT.relative_to(CASO).as_posix()}")
        else:
            caso_verde()
            caso_parado("2 modelado sin aprobar", lambda m: m["ganador"].update(aprobado_por=""))
            caso_parado("3 modelado en ERROR", lambda m: m["resultado"].update(estado="ERROR"))
            caso_parado("4 validación que no lo da por bueno", lambda m: m["validacion"].update(se_da_por_bueno=False))
            caso_error("5 finalista sin cadena", "sin cadena", fichas=[f for f in FICHAS if f[0] != "R-013"])
            caso_error("6 paso sin clase", "sin clase",
                       fichas=FICHAS + [("R-025", "fotos_riesgo · una columna nueva", "Algo que nadie clasificó.")])
            orden = [f for f in FICHAS if f[0] != "R-020"]
            orden.insert(next(i for i, f in enumerate(orden) if f[0] == "R-022") + 1,
                         next(f for f in FICHAS if f[0] == "R-020"))
            caso_error("7 aprende antes de la partición", "antes de la partición", fichas=orden)
            m = copy.deepcopy(MODELADO)
            m["ganador"]["muestra"] = ""
            caso_error("8 contrato con un campo vacío", "vacío", modelado=m)
            caso_error("9 columna sin finalista", "ninguna finalista",
                       variables=[v for v in LEE if v != "cambio_smart_5"])
            caso_error("10 finalista sin definición", "sin definición",
                       texto_reglas=reglas(de_que_se_parte="La edad sale de las horas.",
                                           fotos=REGLAS_FOTOS.replace("`edad_anos`", "la edad")))
        busqueda_de_resultados_puestos()
    finally:
        if TMP.exists():
            shutil.rmtree(TMP)
    print(f"\n{len(FALLOS)} casos en rojo" if FALLOS else "\nTodos los casos en verde")
    sys.exit(1 if FALLOS else 0)


if __name__ == "__main__":
    main()
