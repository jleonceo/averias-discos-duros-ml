"""Prueba de las pestañas de informes/cuadro_mando.html, abierto en Edge sin ventana.

Edge abre una página de prueba en tests/tmp_cuadro/ con el cuadro dentro de un marco de 1366 × 650. Esa página pone
cada combinación de filtros y cada pestaña con la función del propio cuadro que lee la dirección (CUADRO.irA) y mide la
pestaña montada: cuántas cifras tiene arriba y su ancho, cuántos gráficos, cuántas palabras, sus títulos y si la página
se sale a lo ancho. Edge deja el resultado en el DOM y la prueba lo lee con --dump-dom.

Combinaciones: «Todos»; cada valor de cada filtro solo (4 + 11 + 11 + 6); diez al azar con la semilla 21; y la más
estrecha que tiene datos (los cuatro filtros puestos y la que menos días de disco tiene de julio de 2024 a junio de
2025, con desempate por el orden de los filtros).

En cada pestaña y combinación comprueba: de 3 a 4 cifras arriba, todas del mismo ancho; como mucho 2 gráficos; como
mucho LIMITE_PALABRAS palabras (unas 60; no cuentan el número grande, la etiqueta de las cifras, lo que va dentro de
los gráficos y las tablas, los mandos ni lo que sale al pasar el ratón); ningún título con coma o dos puntos; ningún
título que concluya (sube, baja, más, menos, no se distingue, el de menor coste) sin marcar su grupo, ni que concluya
sobre un grupo sin conclusión (menos de 50.000 días de disco en el año o de 20 fallos); toda barra o punto gris con
«sin conclusión» en su etiqueta y con algo de alto aunque su cifra sea cero; ninguna palabra vetada; nada
más ancho que 1366 px. Y que las cifras sin filtros son las de tests/cifras_de_referencia.json («cifras_cuadro»).

La carpeta tests/tmp_cuadro/ se crea y se borra siempre. Sale con 0 si todo pasa y con 1 si algo falla, diciendo qué.

Uso: python -W error tests/probar_21_cuadro_mando_pestanas.py
"""

# html deshace los escapes del resultado que deja Edge
import html
# importlib carga el script por su ruta sin ejecutar su principal
import importlib.util
# json lee los datos del cuadro, el resultado de Edge y las cifras de referencia
import json
# random elige las diez combinaciones al azar
import random
# re busca el resultado en el DOM y las palabras de los títulos
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
HTML = RAIZ / "informes" / "cuadro_mando.html"
TMP = RAIZ / "tests" / "tmp_cuadro"
EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
PESTANAS = ["vision", "centros", "modelos", "edad", "lista"]
# Los órdenes de lo general a lo particular (Juan, 20/11/2026; reglas §4 «La instalación»)
ORDEN_FILTROS = ["f-centro", "f-fabricante", "f-capacidad", "f-edad"]
ORDEN_COLUMNAS = ["Puesto", "Centro de datos", "Tomo en peligro", "Fabricante", "Modelo", "TB", "Años cumplidos",
                  "Número de serie", "Puntuación de riesgo, 0 a 100"]
SEMILLA = 21
LIMITE_PALABRAS = 66
MINIMO_DIAS_ANO = 50_000
MINIMO_FALLOS = 20
# Un título que dice uno de estos verbos o comparaciones concluye sobre un grupo
CONCLUYE = re.compile(r"\b(sube|suben|baja|bajan|más|menos|no se distingue|no se distinguen|menor coste)\b", re.I)
VETADAS = re.compile(r"\b(flota|parque|unidades)\b|regla actual|gastar menos", re.I)
# La ciudad de cada centro, copiada de contexto-proyecto/negocio/reglas-negocio.md §4 («Centro de datos»)
CIUDADES = {"ams5": "Ámsterdam", "iad1": "Virginia", "phx1": "Phoenix", "sac0": "Sacramento", "sac2": "Sacramento",
            "yyz1": "Toronto"}
FALLOS = []


def caso(nombre, condicion, detalle=""):
    """Apunta un caso y dice si pasa."""
    if not condicion:
        print(f"FALLA {nombre} ({detalle})")
        FALLOS.append(nombre)
    return condicion


def cargar():
    """Carga el script como módulo, sin ejecutar su principal."""
    spec = importlib.util.spec_from_file_location("cuadro_mando_68", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def datos_del_html():
    """Los datos que el cuadro lleva dentro, en su bloque JSON."""
    texto = HTML.read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="datos">(.*?)</script>', texto, flags=re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def combinaciones(datos, m):
    """«Todos», cada valor solo, diez al azar y la más estrecha con datos (ver la cabecera)."""
    opciones = {"fabricante": datos["fabricantes"], "capacidad": datos["capacidades"], "edad": datos["edades"],
                "centro": datos["centros"]}
    combos = [{}]
    for clave, valores in opciones.items():
        combos += [{clave: v} for v in valores]
    rng = random.Random(SEMILLA)
    for _ in range(10):
        combos.append({k: v for k, v in ((k, rng.choice([None] + list(vs))) for k, vs in opciones.items())
                       if v is not None})
    combos.append(m.combinacion_mas_estrecha(datos))
    return combos


def direccion(pestana, filtros, lista=None):
    """La dirección de la página para una pestaña y unos filtros, como la escribe el cuadro."""
    partes = [f"pestana={pestana}"] + [f"{k}={v}" for k, v in filtros.items()]
    if lista is not None:
        partes.append(f"lista={lista}")
    return "#" + "&".join(partes)


PAGINA = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<iframe id="cuadro" src="__SRC__" style="width:1366px;height:650px;border:0"></iframe>
<pre id="resultado"></pre>
<script>
const PRUEBAS = __PRUEBAS__;
const marco = document.getElementById('cuadro');
function palabras(sec) {
  const copia = sec.cloneNode(true);
  copia.querySelectorAll('svg, table, .num, .etq, button, select, label, [data-no-cuenta]').forEach(e => e.remove());
  const texto = copia.textContent.replace(/\\s+/g, ' ');
  return texto.split(' ').filter(p => /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(p)).length;
}
marco.addEventListener('load', () => {
  const salida = [];
  try {
    const win = marco.contentWindow, doc = marco.contentDocument;
    for (const p of PRUEBAS) {
      win.CUADRO.irA(p.hash);
      const sec = doc.querySelector('section.pestana:not([hidden])');
      const cifras = [...sec.querySelectorAll('.cifra')];
      const titulos = [...sec.querySelectorAll('[data-titulo]')].map(t => ({texto: t.textContent.trim(),
        concluye: t.dataset.concluye, dias: t.dataset.diasAno, fallos: t.dataset.fallos}));
      const ids = [...doc.querySelectorAll('[id]')].map(e => e.id);
      const grises = [...sec.querySelectorAll('.grafico g[data-tip]')].filter(g => g.querySelector('[fill="#898781"]'))
        .map(g => ({texto: g.textContent.trim(), tip: g.dataset.tip,
          alto: Math.min(...[...g.querySelectorAll('rect[fill="#898781"], circle[fill="#898781"]')].map(e => e.getBBox().height))}));
      salida.push({hash: p.hash, pestana: sec.id, cifras: cifras.length,
        filtros: [...doc.querySelectorAll('.filtros select')].map(s => s.id),
        pestanas: [...doc.querySelectorAll('[role=tab]')].map(b => b.dataset.p),
        columnas: [...sec.querySelectorAll('thead th')].map(th => th.textContent),
        grises: grises, viendo: doc.getElementById('viendo').textContent,
        opciones_centro: [...doc.querySelectorAll('#f-centro option')].filter(o => o.value).map(o => [o.value, o.textContent]),
        etiquetas_centro: sec.id === 'p-centros' ? [...sec.querySelectorAll('.grafico g[data-tip]')].map(g =>
          ({texto: g.querySelector('text').textContent, tip: g.dataset.tip})) : [],
        cifras_centro: sec.id === 'p-centros' ? [...sec.querySelectorAll('.cifra .ctx')].map(c => c.textContent) : [],
        titulo_texto: sec.querySelector('h2').textContent,
        ids_repetidos: ids.filter((x, i) => ids.indexOf(x) !== i), pie: (sec.querySelector('.pie') || {}).textContent || '',
        selects_vacios: [...doc.querySelectorAll('select')].filter(s => s.options.length === 0).map(s => s.id),
        anchos: cifras.map(c => Math.round(c.getBoundingClientRect().width * 10) / 10),
        valores: cifras.map(c => ({id: c.dataset.id, valor: c.dataset.valor})),
        graficos: sec.querySelectorAll('.grafico').length, palabras: palabras(sec), titulos: titulos,
        ancho: doc.documentElement.scrollWidth, texto: sec.innerText});
    }
  } catch (e) { salida.push({error: String(e) + ' ' + (e.stack || '')}); }
  try {
    // La dirección que escribe el cuadro al cambiar un filtro, con los cuatro puestos
    const win = marco.contentWindow, doc = marco.contentDocument;
    win.CUADRO.irA('#pestana=vision&edad=5&capacidad=8&fabricante=Toshiba&centro=sac2');
    const s = doc.getElementById('f-edad'); s.value = '5'; s.dispatchEvent(new Event('change'));
    salida.push({direccion: win.location.hash});
  } catch (e) { salida.push({error: String(e)}); }
  document.getElementById('resultado').textContent = JSON.stringify(salida);
});
</script></body></html>"""


def medir_en_edge(pruebas):
    """Abre la página de prueba en Edge sin ventana y devuelve lo que midió."""
    src = HTML.resolve().as_uri()
    pagina = TMP / "pagina_de_prueba.html"
    pagina.write_text(PAGINA.replace("__SRC__", src).replace("__PRUEBAS__", json.dumps(pruebas, ensure_ascii=False)),
                      encoding="utf-8")
    perfil = TMP / "perfil_edge"
    orden = [str(EDGE), "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--window-size=1400,800",
             "--virtual-time-budget=120000", f"--user-data-dir={perfil}", "--dump-dom", pagina.resolve().as_uri()]
    salida = subprocess.run(orden, capture_output=True, timeout=140).stdout.decode("utf-8", errors="replace")
    m = re.search(r'<pre id="resultado">(.*?)</pre>', salida, flags=re.S)
    if not m or not m.group(1).strip():
        raise RuntimeError("Edge no dejó el resultado de la página de prueba")
    return json.loads(html.unescape(m.group(1)))


def orden_viendo(hash_):
    """Lo que la línea «Viendo» tiene que nombrar, en el orden de los filtros: centro, fabricante, capacidad y edad."""
    partes = dict(x.split("=", 1) for x in hash_.lstrip("#").split("&"))
    orden = []
    if "centro" in partes:
        orden.append(f"{CIUDADES[partes['centro']]} · {partes['centro']}")
    if "fabricante" in partes:
        orden.append(partes["fabricante"])
    if "capacidad" in partes:
        c = float(partes["capacidad"])
        orden.append(f"{int(c) if c.is_integer() else c} TB")
    if "edad" in partes:
        orden.append("cumplido")
    return orden


def comprobar_pestana(r):
    """Los casos de una pestaña en una combinación."""
    nombre = f"{r['hash']}"
    caso(f"{nombre}: de 3 a 4 cifras", 3 <= r["cifras"] <= 4, r["cifras"])
    caso(f"{nombre}: cifras del mismo ancho", r["anchos"] and max(r["anchos"]) - min(r["anchos"]) <= 1, r["anchos"])
    caso(f"{nombre}: como mucho 2 gráficos", r["graficos"] <= 2, r["graficos"])
    caso(f"{nombre}: unas 60 palabras", r["palabras"] <= LIMITE_PALABRAS, r["palabras"])
    caso(f"{nombre}: nada más ancho que la pantalla", r["ancho"] <= 1366, r["ancho"])
    caso(f"{nombre}: ninguna palabra vetada", not VETADAS.search(r["texto"]), VETADAS.search(r["texto"]))
    caso(f"{nombre}: tiene título", len(r["titulos"]) >= 1, r["titulos"])
    caso(f"{nombre}: ningún id repetido en la página", not r["ids_repetidos"], r["ids_repetidos"])
    caso(f"{nombre}: los filtros, de lo general a lo particular", r["filtros"] == ORDEN_FILTROS, r["filtros"])
    caso(f"{nombre}: las pestañas, en su orden", r["pestanas"] == PESTANAS, r["pestanas"])
    if r["pestana"] == "p-lista":
        caso(f"{nombre}: las columnas de la lista, en su orden", r["columnas"] == ORDEN_COLUMNAS, r["columnas"])
        # La puntuación ordena los discos; el modelo no está calibrado y no se presenta como probabilidad (R68-153)
        caso(f"{nombre}: el pie dice que la puntuación no es una probabilidad", "no es una probabilidad" in r["pie"],
             r["pie"])
        caso(f"{nombre}: la lista no habla de probabilidad de fallar",
             "probabilidad de fallar" not in r["texto"].lower(), r["texto"][:200])
    puestos = [r["viendo"].find(x) for x in orden_viendo(r["hash"])]
    caso(f"{nombre}: la línea «Viendo» nombra los filtros en su orden", puestos == sorted(puestos) and -1 not in puestos,
         (r["viendo"], orden_viendo(r["hash"])))
    for valor, texto in r["opciones_centro"]:
        caso(f"{nombre}: la opción del centro {valor} lleva su ciudad", texto == f"{CIUDADES[valor]} · {valor}", texto)
    for e in r["etiquetas_centro"]:
        codigo = e["texto"].split(" · ")[-1]
        caso(f"{nombre}: la etiqueta del centro lleva su ciudad «{e['texto']}»",
             codigo in CIUDADES and e["texto"] == f"{CIUDADES[codigo]} · {codigo}" and e["tip"].startswith(e["texto"]), e)
    centro = re.search(r"centro=(\w+)", r["hash"])
    if centro:
        c = centro.group(1)
        caso(f"{nombre}: la línea «Viendo» nombra el centro con su ciudad", f"{CIUDADES[c]} · {c}" in r["viendo"],
             r["viendo"])
    if r["pestana"] == "p-centros":
        sueltos = [x for x in r["cifras_centro"] + [r["titulo_texto"]]
                   for c in CIUDADES if re.search(rf"(?<!· ){c}\b", x)]
        caso(f"{nombre}: el título y las cifras de centros no nombran un centro sin su ciudad", not sueltos, sueltos)
    for g in r["grises"]:
        # Una barra o punto gris dice «sin conclusión» en su etiqueta: la que se ve, o, si no lleva texto, la del ratón
        etiqueta = g["texto"] if re.search(r"[0-9A-Za-z]", g["texto"]) else g["tip"]
        caso(f"{nombre}: lo gris lleva «sin conclusión» en su etiqueta «{g['texto'][:60]}»",
             "sin conclusión" in etiqueta.lower(), g)
        caso(f"{nombre}: lo gris se ve, aunque su cifra sea cero «{g['texto'][:60]}»", g["alto"] >= 1, g)
    caso(f"{nombre}: el pie dice la fuente", r["pie"].strip() != "" and "Fuente" in r["pie"], r["pie"])
    caso(f"{nombre}: ningún selector sin opciones", not r["selects_vacios"], r["selects_vacios"])
    for t in r["titulos"]:
        caso(f"{nombre}: título sin coma ni dos puntos «{t['texto']}»", "," not in t["texto"] and ":" not in t["texto"])
        if CONCLUYE.search(t["texto"]):
            caso(f"{nombre}: el título que concluye marca su grupo «{t['texto']}»", t["concluye"] == "si", t)
        if t["concluye"] == "si":
            dias = float(t["dias"]) if t["dias"] not in (None, "") else -1
            fallos = float(t["fallos"]) if t["fallos"] not in (None, "") else -1
            caso(f"{nombre}: el título concluye sobre un grupo con conclusión «{t['texto']}»",
                 dias >= MINIMO_DIAS_ANO and fallos >= MINIMO_FALLOS, t)


def main():
    """Lanza los casos."""
    if not caso("existe informes/cuadro_mando.html", HTML.is_file(), "lanza antes scripts/21_cuadro_mando.py"):
        print(f"{len(FALLOS)} FALLA")
        return 1
    m = cargar()
    datos = datos_del_html()
    combos = combinaciones(datos, m)
    caso("son 44 combinaciones", len(combos) == 44, len(combos))
    print("la más estrecha:", combos[-1])
    pruebas = [{"hash": direccion(p, c)} for c in combos for p in PESTANAS]
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    try:
        resultado = medir_en_edge(pruebas)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    direcciones = [r["direccion"] for r in resultado if "direccion" in r]
    caso("la dirección pone los filtros de lo general a lo particular",
         direcciones == ["#pestana=vision&centro=sac2&fabricante=Toshiba&capacidad=8&edad=5"], direcciones)
    resultado = [r for r in resultado if "direccion" not in r]
    errores = [r for r in resultado if "error" in r]
    caso("la página de prueba no da error", not errores, errores[:1])
    medidas = [r for r in resultado if "error" not in r]
    caso("se midieron todas las pestañas", len(medidas) == len(pruebas), (len(medidas), len(pruebas)))
    for r in medidas:
        comprobar_pestana(r)
    print("palabras como mucho por pestaña:",
          {p: max(r["palabras"] for r in medidas if r["pestana"] == f"p-{p}") for p in PESTANAS})
    # Las cifras sin filtros, contra las de referencia
    ref = json.loads((RAIZ / "tests" / "cifras_de_referencia.json").read_text(encoding="utf-8")).get("cifras_cuadro", {})
    caso("hay cifras del cuadro de referencia", bool(ref), "falta la clave cifras_cuadro")
    sin_filtros = {v["id"]: v["valor"] for r in medidas if r["hash"].count("&") == 0 for v in r["valores"]}
    for clave, esperado in ref.items():
        sale = sin_filtros.get(clave)
        igual = (sale not in (None, "") and abs(float(sale) - esperado) <= 1e-9 * max(1.0, abs(esperado)))
        caso(f"referencia {clave}", igual, f"sale {sale}, referencia {esperado}")
    caso("toda cifra sin filtros tiene referencia", set(sin_filtros) == set(ref), set(sin_filtros) ^ set(ref))
    print(f"{len(medidas)} pestañas medidas; " + (f"{len(FALLOS)} FALLA" if FALLOS else "TODO PASA"))
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
