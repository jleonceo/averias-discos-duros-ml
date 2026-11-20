"""Prueba de scripts/17_informe_final.py: el informe final del caso 68.

Comprueba, sin escribir nada en informes/:
1. que el script existe y se importa sin ejecutar nada;
2. que con los JSON reales monta diez páginas antes del anexo, en el orden del texto aprobado, con las cifras clave;
3. que ningún título lleva coma ni dos puntos y que no sale ninguna palabra vetada («flota», «la regla actual»,
   «gastar menos»…);
4. que para si un JSON trae otra fecha de datos;
5. que para si los datos dejan de sostener una frase: el modelo sin ganar a la regla en la lista de 100;
6. que la guardia de palabras vetadas caza «la regla actual» (el caso que tiene que fallar).

Sale con 0 si todo pasa y con 1 si algo falla, diciendo qué.

Uso: python -W error tests/probar_17_informe_final.py
"""

# copy duplica las entradas para estropearlas sin tocar las reales
import copy
# importlib carga el script por su ruta sin ejecutar su main
import importlib.util
# sys da el código de salida
import sys
# Path calcula las rutas desde la carpeta del caso
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "17_informe_final.py"
FALLOS = []


def caso(nombre, condicion):
    """Apunta un caso y dice si pasa."""
    print(("PASA " if condicion else "FALLA ") + nombre)
    if not condicion:
        FALLOS.append(nombre)


def para(funcion, *args):
    """True si la función para con ValueError."""
    try:
        funcion(*args)
    except ValueError:
        return True
    return False


def cargar():
    """Carga el script como módulo, sin ejecutar su main."""
    spec = importlib.util.spec_from_file_location("informe_final_68", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def main():
    """Lanza los casos."""
    # 1. El script existe y se importa
    caso("1. el script existe", SCRIPT.is_file())
    if not SCRIPT.is_file():
        print(f"{len(FALLOS)} FALLA")
        sys.exit(1)
    m = cargar()
    caso("1. se importa sin ejecutar nada (tiene main)", hasattr(m, "main") and hasattr(m, "construir"))

    # 2. Con los JSON reales
    entradas = m.leer_entradas(m.INFORMES)
    texto, filas, inf = m.construir(entradas)
    antes = [p for p in inf.paginas if p.tipo != "anexo"]
    caso("2. diez páginas antes del anexo", len(antes) == 10)
    caso("2. orden: resumen, siete de resultado, límites y decisión",
         [p.tipo for p in antes] == ["resumen"] + ["resultado"] * 7 + ["limites", "decision"])
    # «15,8» (la regla en la prueba anterior) sale desde el 19/11/2026: la página 8 da la prueba final
    for cifra in ("32,2", "6,44 %", "2,58 %", "489", "1,10", "2.546", "832.698", "T4 2024"):
        caso(f"2. la cifra {cifra} está en el informe", cifra in texto)
    caso("2. el CSV de los gráficos lleva cifras", len(filas) > 20)
    # Auditor y lector simulado del 19/11/2026
    caso("2. orden: los repuestos van en la página 4, junto a la compra", antes[3].panel == "Los repuestos")
    caso("2. no da los 2.044.860 $ como ahorro: mezclan años de compra", "2.044.860" not in texto)
    caso("2. la lista se llama siempre «lista de riesgo»", "lista de riesgo" in texto and "Regla de avisos" not in texto
         and "lista del modelo" not in texto)
    caso("2. los trimestres se escriben para el lector, sin «2024T4»", "2024T4" not in texto)
    for palabra in ("trozos", "instalación", "máximo probable", "pendiente de la puesta"):
        caso(f"2. no sale «{palabra}»", palabra not in texto.lower())
    # Segunda revisión externa del 19/11/2026, sobre el resumen: sus cifras clave hablan del precio de compra, que es lo
    # que dice su título, y el próximo paso nombra las cuatro decisiones
    p1 = antes[0]
    caso("2. resumen: la primera cifra clave es la parte del precio de compra", p1.cifras[0][0] == "93,56 %"
         and "precio de compra" in p1.cifras[0][1])
    caso("2. resumen: ninguna cifra clave de la tasa por edad", not any("edad" in e for _, e, _ in p1.cifras))
    caso("2. resumen: el próximo paso nombra las cuatro decisiones",
         all(x in p1.bloques[-1]["html"] for x in ("comprar en cada capacidad", "lista de riesgo", "sac2", "repuestos")))
    # Revisión externa del 19/11/2026: en el resumen «sac2» solo no dice qué es
    caso("2. resumen: sac2 se nombra como centro de datos", "centro de datos sac2" in p1.bloques[-1]["html"])
    # Revisión externa de las páginas 2 a 4 y pasada propia de la 5 a la 10 (19/11/2026, Juan: «todo»)
    caso("2. página 4: el año guardado compara los dos errores", "31,8 %" in
         "".join(b["html"] for b in antes[3].bloques))
    caso("2. página 3: el título dice que son siete grupos", antes[2].titulo.startswith("En los siete grupos"))
    caso("2. página 3: el próximo paso no repite «en cada compra»", "En cada compra" not in antes[2].bloques[-1]["html"])
    caso("2. página 2: no repite el coste de 2024 del resumen",
         not any("832.698" in x for f in antes[1].cifras for x in f))
    caso("2. página 2: dice cuántas veces se llegó al límite de la redundancia",
         any("límite de la redundancia" in f[1] for f in antes[1].cifras))
    caso("2. no sale «cumpleaños»", "cumpleaños" not in texto)
    # Revisión externa de la página 10 (19/11/2026): la entrada no da por hecha la aprobación y sac2 se nombra como
    # centro de datos
    html10 = "".join(b["html"] for b in antes[9].bloques)
    caso("2. página 10: propone, no da por aprobado", "aprueba estas" not in html10 and "Se proponen" in html10)
    caso("2. página 10: el equipo del centro de datos sac2", "equipo del centro de datos sac2" in html10)
    caso("2. la página 3 dice cuánto pesan los fallos en el coste", "6,44 %" in "".join(b["html"] for b in antes[2].bloques))
    # Revisión externa de la página 4 (19/11/2026): tres líneas cruzadas no se leen; el gráfico lleva dos, los reales y
    # la previsión por modelo y edad, y sin expresiones coloquiales
    p4 = antes[3]
    svg4 = "".join(b["html"] for b in p4.bloques if "<svg" in b["html"])
    caso("2. página 4: el gráfico lleva dos líneas, sin la del trimestre anterior",
         "Reales" in svg4 and "Por modelo y edad" in svg4 and "Trimestre anterior" not in svg4)
    for coloquial in ("se equivoca", "se queda", "deja un margen"):
        caso(f"2. no sale «{coloquial}»", coloquial not in texto.lower())
    # Lista de control 08 con sus cuatro lectores ajenos (19/11/2026): la garantía arriba, la regla de los cinco avisos
    # SMART es la referencia del análisis y no consta que Backblaze la use (no se «sustituye»), la recomendación de los
    # tomos tiene su decisión, y la tabla de la página 8 cuadra con su diferencia
    caso("2. resumen: lleva el coste de los fallos con garantía", "305.124" in "".join(x for f in p1.cifras for x in f))
    caso("2. resumen: dice que el ahorro en dólares no se puede calcular", "no se puede calcular el ahorro" in
         "".join(b["html"] for b in p1.bloques))
    caso("2. no dice que se sustituya la regla", "sustitu" not in texto.lower())
    caso("2. la tabla de la página 8 lleva dos decimales y cuadra con la diferencia", "22,64" in texto)
    # Prueba final del 19/11/2026: el año guardado, de julio de 2025 a junio de 2026, ya se midió. La página 8 da su
    # cifra, la 9 dice que bajó frente a la prueba anterior y la 4 dice el error de los repuestos en ese año
    p8, p9 = antes[7], antes[8]
    html8 = "".join(b["html"] for b in p8.bloques)
    caso("2. página 8: la tabla es la de la prueba final", "22,64" in html8 and "14,91" in html8
         and "prueba final" in html8)
    caso("2. página 8: el intervalo es el de la prueba final", "4,82" in html8 and "11,45" in html8)
    caso("2. página 8: el título dice un 52 % más y no el doble", "52 %" in p8.titulo and "doble" not in p8.titulo)
    caso("2. no dice «el doble» en ninguna página", "el doble" not in texto.lower())
    caso("2. página 8: tres de cada cuatro discos de la lista no fallan", "tres de cada cuatro" in html8)
    html9 = "".join(b["html"] for b in p9.bloques)
    caso("2. página 9: ya no dice que falte la prueba final", "Ninguna cifra se ha medido" not in html9)
    caso("2. página 9: dice que la lista bajó de 32,2 a 22,6", "32,2" in html9 and "22,6" in html9)
    caso("2. página 4: dice el error de los repuestos en el último año", "30,6 %" in
         "".join(b["html"] for b in antes[3].bloques))
    caso("2. página 10: la lista se justifica con la prueba final", "22,6" in "".join(b["html"] for b in antes[9].bloques))
    caso("2. el anexo nombra los dos JSON de la prueba final", all(n in texto for n in ("prueba_final.json",
                                                                                       "prueba_final_prevision.json")))
    p10 = antes[9]
    caso("2. cinco decisiones, con la del tomo", p10.titulo.startswith("Cinco decisiones")
         and "revisar el tomo" in "".join(b["html"] for b in p10.bloques))
    caso("2. la página 3 enseña la tasa de fallo de cada modelo", "Tasa de fallo" in
         "".join(b["html"] for b in antes[2].bloques))
    # Revisión externa del 19/11/2026: la página 2 dimensiona el problema con cifras y un esquema, y las definiciones
    # van al anexo
    p2 = antes[1]
    caso("2. la página 2 lleva tres cifras clave", len(p2.cifras) == 3)
    caso("2. la página 2 lleva el esquema del tomo", any("<svg" in b["html"] for b in p2.bloques))
    caso("2. la página 2 no lleva la tabla de definiciones", not any("Qué quiere decir" in b["html"] for b in p2.bloques))
    anexo = [p for p in inf.paginas if p.tipo == "anexo"]
    caso("2. las definiciones del caso están en el anexo",
         any("Aviso SMART" in b["html"] for p in anexo for b in p.bloques))
    caso("2. la cifra 832.698 está en el informe", "832.698" in texto)
    # Juan, 19/11/2026: «pones métricas clave, lo dejas vacío y luego pones la tabla a la derecha». Una página con un
    # rótulo sin texto tiene que ir de arriba abajo, para que la tabla quede debajo de su rótulo
    for p in antes:
        vacios = [b for b in p.bloques if b["clase"] == "apartado" and not b["parrafos"]]
        caso(f"2. página «{p.panel}»: ningún rótulo vacío con la tabla al lado", not vacios or not p.columnas)

    # 3. Títulos y palabras vetadas
    titulos = [m.TITULO] + [p.titulo for p in antes]
    caso("3. ningún título con coma ni dos puntos", all("," not in t and ":" not in t for t in titulos))
    bajo = texto.lower()
    for vetada in ("flota", "parque", "regla actual", "gastar menos", "unidades"):
        caso(f"3. no sale «{vetada}»", vetada not in bajo)

    # 4. Fecha de datos distinta
    otra = copy.deepcopy(entradas)
    otra["modelado.json"]["fecha_datos"] = "2025-05-31"
    caso("4. para con otra fecha de datos", para(m.comprobar_fechas, otra))
    # Los JSON de la prueba final llevan la fecha del año guardado, no la del análisis
    reserva = copy.deepcopy(entradas)
    caso("4. con sus dos fechas, no para", not para(m.comprobar_fechas, reserva))
    reserva["prueba_final.json"]["fecha_datos"] = "2025-06-30"
    caso("4. para si la prueba final trae la fecha del análisis", para(m.comprobar_fechas, reserva))

    # 5. Datos que ya no sostienen la frase de la lista de riesgo
    rota = copy.deepcopy(entradas)
    for mes in rota["modelado.json"]["validacion"]["por_mes"]:
        mes["modelo_lista_100"] = mes["regla_lista_100"]
    caso("5. para si el modelo no gana a la regla en la lista de 100", para(m.construir, rota))
    # La prueba final: si un mes la regla iguala a la lista, o si la previsión pasa a ganar, la frase ya no vale
    rota_final = copy.deepcopy(entradas)
    medido = [x for x in rota_final["prueba_final.json"]["por_mes"] if x["se_mide"]][0]
    medido["modelo_lista_100"] = medido["regla_lista_100"]
    caso("5. para si en la prueba final la regla iguala a la lista un mes", para(m.construir, rota_final))
    rota_prev = copy.deepcopy(entradas)
    rota_prev["prueba_final_prevision.json"]["total"]["wape_cuenta"] = 0.1
    caso("5. para si en el último año la previsión prevé mejor", para(m.construir, rota_prev))

    # 6. La guardia de palabras vetadas caza «la regla actual»
    caso("6. la guardia caza «la regla actual»",
         para(m.sin_prohibidas, '<section id="p1"><p>Mejora a la regla actual.</p></section>'))

    # 7. Auditor sin memoria antes de entregar (20/11/2026, R68-153): el punto ciego medido igual que el modelo, el
    # intervalo bien definido y el año guardado dicho como se usó. La regla sencilla que propuso no se usa (Juan,
    # 20/11/2026, R68-155): la referencia es solo la regla de los cinco avisos SMART
    anexo_html = "".join(b["html"] for p in anexo for b in p.bloques)
    caso("7. no queda nada de la regla sencilla", "sencilla" not in texto.lower() and "24,55" not in texto
         and "referencia_cambio_contadores" not in texto)
    caso("7. el anexo nombra el JSON del punto ciego", "punto_ciego.json" in texto)
    caso("7. página 9: ya no da el 25 % «sin ningún aviso»", "sin ningún aviso" not in html9)
    caso("7. página 9: da el punto ciego del último año, 32 %", "32 %" in html9)
    caso("7. el intervalo no se define como «con un 95 % de seguridad»", "95 % de seguridad" not in anexo_html)
    caso("7. el modelo de riesgo no se define como una probabilidad", "estima cada mes la probabilidad" not in anexo_html)
    caso("7. el año guardado no se da como medido «una sola vez»",
         "se midieron una sola vez con el último año" not in anexo_html)
    caso("7. el anexo dice que el modelo en uso también se midió en el año guardado", "23,73" in anexo_html)
    ciego = copy.deepcopy(entradas)
    ciego["punto_ciego.json"]["validaciones"]["fallos_del_ano_guardado_como_el_modelo"] = False
    caso("7. para si el punto ciego no cuadra con los fallos del modelo", para(m.construir, ciego))

    print(f"{len(FALLOS)} FALLA" if FALLOS else "Todo en verde")
    sys.exit(1 if FALLOS else 0)


if __name__ == "__main__":
    main()
