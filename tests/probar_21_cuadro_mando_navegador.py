"""Prueba de que el navegador dice lo mismo que Python en informes/cuadro_mando.html.

1. En Edge sin ventana, en las mismas combinaciones que la prueba de las pestañas (y en cada tamaño de lista), las cifras
   de arriba de cada pestaña (data-valor) son las que calcula resumen() del script con los datos que lleva el cuadro.
   También el nombre del CSV y su texto, que el navegador monta con su JavaScript y Python con nombre_csv y texto_csv.
2. En Python, resumen() en las 5.040 combinaciones de los cuatro filtros (5 × 12 × 12 × 7): cada pestaña con 3 a 4
   cifras; los discos, los fallos y los días de disco de cada fabricante, capacidad o año de edad suman los de «Todos»
   con los demás filtros iguales; los discos de la lista de cada fabricante suman los de «Todos»; ningún centro que
   falla más o menos de lo esperado sin estar entre los que se ven.
3. Los esperados por fila que usa resumen() suman, centro a centro, lo mismo que ajustada() del script 11 copiada,
   recalculada con cada valor de fabricante, capacidad y año de edad.

La carpeta tests/tmp_cuadro/ se crea y se borra siempre. Sale con 0 si todo pasa y con 1 si algo falla, diciendo qué.

Uso: python -W error tests/probar_21_cuadro_mando_navegador.py
"""

# html deshace los escapes del resultado que deja Edge
import os
import html
# importlib carga el script y la prueba de las pestañas por su ruta
import importlib.util
# itertools recorre las 5.040 combinaciones
import itertools
# json lee el resultado de Edge
import json
# re busca el resultado en el DOM
import re
# shutil borra la carpeta temporal
import shutil
# subprocess lanza Edge
import subprocess
# sys da el código de salida
import sys
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "21_cuadro_mando.py"
PESTANAS_PY = RAIZ / "tests" / "probar_21_cuadro_mando_pestanas.py"
HTML = RAIZ / "informes" / "cuadro_mando.html"
TMP = RAIZ / "tests" / "tmp_cuadro"
EDGE = Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
PESTANAS = ["vision", "centros", "modelos", "edad", "lista"]
TOLERANCIA = 1e-9
FALLOS = []


def caso(nombre, condicion, detalle=""):
    """Apunta un caso y dice si pasa."""
    if not condicion:
        print(f"FALLA {nombre} ({detalle})")
        FALLOS.append(nombre)
    return condicion


def cargar(ruta, nombre):
    """Carga un fichero de Python como módulo, sin ejecutar su principal."""
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


PAGINA = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<iframe id="cuadro" src="__SRC__" style="width:1366px;height:650px;border:0"></iframe>
<pre id="resultado"></pre>
<script>
const PRUEBAS = __PRUEBAS__;
const marco = document.getElementById('cuadro');
marco.addEventListener('load', () => {
  const salida = [];
  try {
    const win = marco.contentWindow, doc = marco.contentDocument;
    for (const p of PRUEBAS) {
      win.CUADRO.irA(p.hash);
      const sec = doc.querySelector('section.pestana:not([hidden])');
      const r = {hash: p.hash, valores: [...sec.querySelectorAll('.cifra')].map(c => ({id: c.dataset.id, valor: c.dataset.valor}))};
      if (sec.id === 'p-lista') { r.nombre = win.CUADRO.nombreCsv(); r.csv = win.CUADRO.textoCsv(); }
      salida.push(r);
    }
  } catch (e) { salida.push({error: String(e) + ' ' + (e.stack || '')}); }
  document.getElementById('resultado').textContent = JSON.stringify(salida);
});
</script></body></html>"""


def medir_en_edge(pruebas):
    """Abre la página de prueba en Edge sin ventana y devuelve lo que leyó."""
    pagina = TMP / "pagina_de_prueba.html"
    pagina.write_text(PAGINA.replace("__SRC__", HTML.resolve().as_uri())
                      .replace("__PRUEBAS__", json.dumps(pruebas, ensure_ascii=False)), encoding="utf-8")
    orden = [str(EDGE), "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--window-size=1400,800",
             "--virtual-time-budget=120000", f"--user-data-dir={TMP / 'perfil_edge'}", "--dump-dom",
             pagina.resolve().as_uri()]
    salida = subprocess.run(orden, capture_output=True, timeout=140).stdout.decode("utf-8", errors="replace")
    m = re.search(r'<pre id="resultado">(.*?)</pre>', salida, flags=re.S)
    if not m or not m.group(1).strip():
        raise RuntimeError("Edge no dejó el resultado de la página de prueba")
    return json.loads(html.unescape(m.group(1)))


def iguales(a, b):
    """Dos cifras iguales con la tolerancia de la prueba; vacío con vacío."""
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= TOLERANCIA * max(1.0, abs(float(b)))


def filtros_de(hash_):
    """Los filtros y la lista de una dirección de la página."""
    partes = dict(p.split("=", 1) for p in hash_.lstrip("#").split("&"))
    f = {}
    if "fabricante" in partes:
        f["fabricante"] = partes["fabricante"]
    if "capacidad" in partes:
        f["capacidad"] = float(partes["capacidad"])
    if "edad" in partes:
        f["edad"] = int(partes["edad"])
    if "centro" in partes:
        f["centro"] = partes["centro"]
    lista = int(partes["lista"]) if "lista" in partes else None
    return partes["pestana"], f, lista


def parte_navegador(m, datos, combos):
    """Las cifras, el nombre y el texto del CSV del navegador frente a los de Python."""
    pruebas = [{"hash": pe.direccion(p, c)} for c in combos for p in PESTANAS]
    pruebas += [{"hash": pe.direccion("lista", c, n)} for c in combos for n in datos["lista"]["listas"]]
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    try:
        resultado = medir_en_edge(pruebas)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    errores = [r for r in resultado if "error" in r]
    caso("la página de prueba no da error", not errores, errores[:1])
    comparadas = 0
    for r in [x for x in resultado if "error" not in x]:
        pestana, f, lista = filtros_de(r["hash"])
        f_con_lista = dict(f, lista=lista or datos["lista"]["principal"])
        esperado = {c["id"]: c["valor"] for c in m.resumen(datos, f_con_lista)[pestana]}
        sale = {v["id"]: (None if v["valor"] in (None, "") else float(v["valor"])) for v in r["valores"]}
        caso(f"{r['hash']}: las mismas cifras", set(sale) == set(esperado), (set(sale), set(esperado)))
        for k in esperado:
            comparadas += 1
            caso(f"{r['hash']}: {k}", iguales(sale.get(k), esperado[k]), f"navegador {sale.get(k)}, Python {esperado[k]}")
        if pestana == "lista":
            n = f_con_lista["lista"]
            caso(f"{r['hash']}: nombre del CSV", r["nombre"] == m.nombre_csv(n, f, datos["fecha_lista"]),
                 (r["nombre"], m.nombre_csv(n, f, datos["fecha_lista"])))
            texto = m.texto_csv(m.filas_lista(datos, f_con_lista), n, f, datos["fecha_lista"])
            caso(f"{r['hash']}: texto del CSV", r["csv"] == texto, (r["csv"][:200], texto[:200]))
    print(f"navegador: {comparadas} cifras comparadas en {len(resultado)} pestañas")


def parte_python(m, datos):
    """resumen() en las 5.040 combinaciones de los cuatro filtros."""
    fab = [None] + datos["fabricantes"]
    cap = [None] + datos["capacidades"]
    eda = [None] + datos["edades"]
    cen = [None] + datos["centros"]
    res = {}
    for combo in itertools.product(fab, cap, eda, cen):
        f = {k: v for k, v in zip(("fabricante", "capacidad", "edad", "centro"), combo) if v is not None}
        f["lista"] = datos["lista"]["principal"]
        r = m.resumen(datos, f)
        res[combo] = r
        for p in PESTANAS:
            caso(f"{combo} {p}: de 3 a 4 cifras", 3 <= len(r[p]) <= 4, len(r[p]))
        centros_vistos = 1 if combo[3] is not None else len(datos["centros"])
        mas = {c["id"]: c["valor"] for c in r["centros"]}
        caso(f"{combo}: centros que fallan más o menos, entre los que se ven",
             (mas["centros_mas"] or 0) + (mas["centros_menos"] or 0) <= centros_vistos, mas)
    caso("son 5.040 combinaciones", len(res) == 5040, len(res))

    def valor(r, pestana, ident):
        """Una cifra de un resumen por su id."""
        return {c["id"]: c["valor"] for c in r[pestana]}[ident]

    sumas = 0
    for i, opciones in enumerate((fab, cap, eda)):
        for combo in res:
            if combo[i] is not None:
                continue
            partes = [res[combo[:i] + (v,) + combo[i + 1:]] for v in opciones[1:]]
            for pestana, ident in (("vision", "discos"), ("vision", "fallos"), ("lista", "discos_lista")):
                total = valor(res[combo], pestana, ident) or 0
                suma = sum(valor(p, pestana, ident) or 0 for p in partes)
                sumas += 1
                caso(f"{combo} {ident}: las partes suman el total", abs(total - suma) < 1e-6, (total, suma))
            dias_total = m.dias_de(datos, dict(zip(("fabricante", "capacidad", "edad", "centro"), combo)))
            dias_suma = sum(m.dias_de(datos, dict(zip(("fabricante", "capacidad", "edad", "centro"),
                                                      combo[:i] + (v,) + combo[i + 1:]))) for v in opciones[1:])
            caso(f"{combo}: los días de disco repartidos suman el total", abs(dias_total - dias_suma) < 1e-3,
                 (dias_total, dias_suma))
    print(f"python: 5.040 combinaciones y {sumas} sumas de partes comprobadas")


def parte_esperados(m, datos):
    """Los esperados por fila frente a ajustada() copiada del script 11, con cada valor de los tres filtros."""
    dp = m.leer_tramos(RAIZ)
    dp = dp.loc[dp["mes"] >= m.INICIO_SITIO]
    for clave, columna, valores in (("fabricante", "fabricante", datos["fabricantes"]),
                                    ("capacidad", "capacidad_tb", datos["capacidades"]),
                                    ("edad", "edad_anos_cumplidos", datos["edades"])):
        for v in valores:
            parte = dp.loc[dp[columna] == v]
            if parte["fallos"].sum() == 0:
                continue
            por_fila = m.centros_por_fila(datos, {clave: v})
            # ajustada() del 11 divide por cero si un centro con filas no tiene esperados; el cuadro lo deja sin
            # razón y sin conclusión. Esos valores se cuentan y se saltan
            if any(por_fila[c]["esperados"] == 0 for c in parte["centro"].unique()):
                print(f"salta {clave}={v}: un centro sin esperados, que ajustada() no puede dividir")
                continue
            aj, _ = m.ajustada(parte)
            for _, x in aj.iterrows():
                otra = por_fila[x["centro"]]
                caso(f"{clave}={v} {x['centro']}: esperados", abs(x["esperados"] - otra["esperados"]) < 1e-6,
                     (x["esperados"], otra["esperados"]))
                caso(f"{clave}={v} {x['centro']}: observados", x["observados"] == otra["observados"])
                caso(f"{clave}={v} {x['centro']}: razón e intervalo",
                     all(iguales(otra[k], x[k]) for k in ("razon", "razon_desde", "razon_hasta")),
                     (otra, dict(x)))


def main():
    """Lanza las tres partes."""
    if not caso("existe informes/cuadro_mando.html", HTML.is_file(), "lanza antes scripts/21_cuadro_mando.py"):
        print(f"{len(FALLOS)} FALLA")
        return 1
    m = cargar(SCRIPT, "cuadro_mando_68")
    global pe
    pe = cargar(PESTANAS_PY, "probar_pestanas_68")
    datos = pe.datos_del_html()
    combos = pe.combinaciones(datos, m)
    parte_navegador(m, datos, combos)
    parte_python(m, datos)
    parte_esperados(m, datos)
    print(f"{len(FALLOS)} FALLA" if FALLOS else "TODO PASA")
    return 1 if FALLOS else 0


pe = None

if __name__ == "__main__":
    sys.exit(main())
