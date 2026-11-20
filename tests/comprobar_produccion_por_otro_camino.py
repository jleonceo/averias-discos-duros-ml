"""Prueba por otro camino de la salida de produccion/ejecutar.py (método preproduccion §2.4, validación 5).

Rehace la puntuación de una foto mensual sin cargar el modelo y sin importar código de producción (ni
scripts/pipeline_riesgo.py ni nada de produccion/), con su propio código escrito desde las reglas:
  1. de la foto en bruto y su historia (fotos anteriores y ventanas de fallos ya ocurridos), las columnas del modelo:
     el nombre corregido, la capacidad del modelo, el fabricante, la garantía, la edad, los avisos y los cambios;
  2. qué filas no se puntúan: disco de arranque, foto del día del fallo, modelo sin una única capacidad válida, edad
     negativa o vacía;
  3. de la tabla de entrenamiento y la receta del contrato, la muestra (todos los fallos y la fracción de las sanas de
     cada grupo de filas de cada mes, con la semilla, en el orden de los meses), las categorías raras, el código
     ordinal, el HistGradientBoosting y la recalibración;
  4. la probabilidad y las marcas de las listas.
Compara fila a fila con la salida: el mismo número de filas y el mismo orden, las mismas filas sin puntuar, la
probabilidad con la tolerancia de produccion/configuracion.json y las marcas exactas. Con --anotar escribe el resultado
en informes/preproduccion.json, después de comprobar que una copia de la salida con una probabilidad estropeada sale
en rojo.

Uso: python -W error tests/comprobar_produccion_por_otro_camino.py --salida RUTA --foto RUTA --mes AAAA-MM
     --tabla RUTA --fecha AAAA-MM-DD [--fotos-anteriores CARPETA ...] [--ventanas CARPETA ...] [--raiz CARPETA] [--anotar]
La historia puede estar en varias carpetas, como en produccion/configuracion.json; se leen todos sus ficheros.
Sale con 0 si coincide y con 1 si no.
"""

# ---------------------------------------------------------------------------------------------------------------
# 1. Configuración
# ---------------------------------------------------------------------------------------------------------------
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier

CASO = Path(__file__).resolve().parents[1]
# Reglas de negocio §3 y §7, §6 y convención 1 de las reglas de transformación
LIMITE_ARRANQUE = 2_048_408_248_320
HORAS, DIAS = 8766.0, 365.25
CINCO = ["smart_5_raw", "smart_187_raw", "smart_188_raw", "smart_197_raw", "smart_198_raw"]
CUATRO = ["smart_5_raw", "smart_187_raw", "smart_197_raw", "smart_198_raw"]
MINIMOS = (30, 20, 20)


def ruta_de(raiz, texto):
    """Ruta absoluta, o relativa a la carpeta del caso."""
    p = Path(texto)
    return p if p.is_absolute() else raiz / p


# ---------------------------------------------------------------------------------------------------------------
# 2. Las columnas del modelo desde la foto en bruto
# ---------------------------------------------------------------------------------------------------------------
def fab(m):
    """Fabricante por el nombre del modelo (reglas, apartado 3)."""
    excepciones = {"Hitachi HDS5C4040ALE630": "HGST", "WUH721816ALE6L4": "WDC"}
    if m in excepciones:
        return excepciones[m]
    for prefijo, nombre in (("ST", "Seagate"), ("TOSHIBA", "Toshiba"), ("WDC", "WDC"), ("HGST", "HGST")):
        if m.startswith(prefijo):
            return nombre
    return None


def anos_garantia(m, f):
    """Garantía por familia (reglas, apartado 6)."""
    if f == "Seagate":
        if "NM" in m:
            return 5.0
        if "DM" in m:
            return 2.0
    if "HMS5C" in m:
        return 3.0
    if "HUH" in m or "HUS" in m or "WUH" in m or m.startswith("TOSHIBA MG"):
        return 5.0
    return np.nan


def leer(ruta, columnas):
    """Las columnas de un Parquet; las que no trae, vacías."""
    hay = pq.read_schema(ruta).names
    df = pq.read_table(ruta, columns=[c for c in columnas if c in hay]).to_pandas()
    for c in columnas:
        if c not in hay:
            df[c] = np.nan
    return df


def ficheros(carpetas):
    """Los Parquet de una o varias carpetas; dos con el mismo nombre en carpetas distintas son dos ficheros."""
    carpetas = [carpetas] if isinstance(carpetas, (str, Path)) else carpetas
    return [r for c in carpetas for r in sorted(Path(c).glob("*.parquet"))]


def columnas_de_la_foto(foto, dir_fotos, dir_ventanas, fecha, mapeo, minimo):
    """Las columnas del modelo y la máscara de lo que se puntúa, escritas aquí desde las reglas."""
    f = foto.reset_index(drop=True).copy()
    f["model"] = [mapeo.get(m, m) for m in f["model"]]
    discos = set(f["serial_number"])
    # La historia: fotos anteriores y ventanas de fallos ya ocurridos con su fecha bien escrita
    fotos, pares = [], []
    for r in ficheros(dir_fotos):
        d = leer(r, ["serial_number", "fecha", "model", "capacity_bytes", *CUATRO])
        d = d[d["fecha"] < fecha]
        d["model"] = [mapeo.get(m, m) for m in d["model"]]
        pares.append(d[["model", "capacity_bytes"]])
        fotos.append(d[d["serial_number"].isin(discos)])
    ventanas = []
    for r in ficheros(dir_ventanas):
        d = leer(r, ["serial_number", "fecha", "date", "dia_fallo", "model", "capacity_bytes"])
        d = d[(d["dia_fallo"] < fecha)]
        d = d[pd.to_datetime(d["date"].astype(str)).to_numpy() == d["fecha"].to_numpy()]
        d["model"] = [mapeo.get(m, m) for m in d["model"]]
        ventanas.append(d)
    h = pd.concat(fotos, ignore_index=True)
    v = pd.concat(ventanas, ignore_index=True)
    # La capacidad del modelo: la única válida en historia, ventanas y la propia foto
    todos = pd.concat([*pares, v[["model", "capacity_bytes"]], f[["model", "capacity_bytes"]]], ignore_index=True)
    validas = todos[todos["capacity_bytes"] >= minimo].groupby("model")["capacity_bytes"].agg(lambda s: sorted(set(s)))
    cap_modelo = {m: (c[0] if len(c) == 1 else None) for m, c in validas.items()}
    dobles = {m for m, c in validas.items() if len(c) > 1}
    cap = np.array([cap_modelo.get(m) if cap_modelo.get(m) is not None else np.nan for m in f["model"]], dtype=float)
    f["capacidad_tb"] = [np.nan if np.isnan(c) else ((int(c) * 10 + 5 * 10**11) // 10**12) / 10 for c in cap]
    f["fabricante"] = [fab(m) for m in f["model"]]
    datos = cap > LIMITE_ARRANQUE
    f["garantia_anos"] = [anos_garantia(m, x) if d else np.nan for m, x, d in zip(f["model"], f["fabricante"], datos)]
    # La edad: horas entre 8.766; sin horas, días desde la primera aparición entre 365,25
    primera = pd.concat([h[["serial_number", "fecha"]], v[["serial_number", "fecha"]]]).groupby("serial_number")["fecha"].min()
    desde = pd.Series([primera.get(s, fecha) for s in f["serial_number"]]).astype("datetime64[ms]")
    dias = (fecha - desde) / pd.Timedelta(days=1)
    f["edad_anos"] = np.where(f["smart_9_raw"].notna(), f["smart_9_raw"] / HORAS, dias / DIAS)
    # Los avisos
    pos = pd.DataFrame({c: f[c] > 0 for c in CINCO})
    f["avisa"] = pos.any(axis=1).astype(float)
    f["contadores_que_avisan"] = pos.sum(axis=1).astype(float)
    f["suma_contadores_sin_188"] = f[CUATRO].sum(axis=1, min_count=1)
    f["smart_188_no_cero"] = np.where(f["smart_188_raw"].isna(), np.nan, (f["smart_188_raw"] > 0).astype(float))
    # Los cambios contra la última foto anterior del mismo disco
    ultima = h.sort_values("fecha", kind="stable").groupby("serial_number").tail(1).set_index("serial_number")
    for c in CUATRO:
        f[f"cambio_{c[:-4]}"] = f[c] - f["serial_number"].map(ultima[c])
    fa = f["serial_number"].map(ultima["fecha"])
    f["meses_desde_foto_anterior"] = (fecha.year - fa.dt.year) * 12 + (fecha.month - fa.dt.month)
    # Lo que se puntúa
    puntua = (datos & (f["failure"] != 1).to_numpy() & (f["edad_anos"] >= 0).to_numpy()
              & ~f["model"].isin(dobles).to_numpy())
    return f, puntua


# ---------------------------------------------------------------------------------------------------------------
# 3. El modelo rehecho desde la tabla de entrenamiento y la receta
# ---------------------------------------------------------------------------------------------------------------
def la_muestra(ruta, fecha, columnas, semilla, fraccion):
    """Fotos anteriores a la fecha con el horizonte cerrado y sin discos de arranque; todos los fallos y la fracción de
    las sanas de cada grupo de filas, mes a mes, con la semilla. Devuelve la muestra y la tasa real."""
    pf = pq.ParquetFile(ruta)
    meses = {}
    for i in range(pf.num_row_groups):
        for m in pd.unique(pf.read_row_group(i, columns=["fecha"]).to_pandas()["fecha"]):
            meses.setdefault(pd.Timestamp(m), []).append(i)
    rng = np.random.default_rng(semilla)
    trozos, filas, fallos = [], 0, 0
    for m in sorted(meses):
        if m >= fecha:
            continue
        for i in meses[m]:
            d = pf.read_row_group(i, columns=columnas).to_pandas()
            ok = ((d["fecha"] == m) & (d["capacidad_tb"] * 1e12 > LIMITE_ARRANQUE) & (d["horizonte_hasta"] < fecha)).to_numpy()
            y = d["falla_30d"].to_numpy().astype(int)
            filas += int(ok.sum())
            fallos += int(y[ok].sum())
            sanas = np.flatnonzero(ok & (y == 0))
            k = int(np.floor(fraccion * len(sanas) + 0.5))
            sorteo = rng.choice(sanas, size=k, replace=False) if k else np.array([], dtype=int)
            trozos.append(d.iloc[np.sort(np.concatenate([np.flatnonzero(ok & (y == 1)), sorteo]))])
    return pd.concat(trozos, ignore_index=True), fallos / filas


def texto(s, vaciar):
    """La columna como texto con «sin dato» en el vacío; vaciada entera si es el centro."""
    if vaciar:
        return pd.Series(["sin dato"] * len(s), index=s.index, dtype=object)
    s = s.astype(object)
    return s.where(s.notna(), "sin dato")


def rehacer(raiz, args, foto_cols, puntua):
    """Entrena el modelo de la receta y devuelve la probabilidad de cada fila (vacía en lo que no se puntúa)."""
    js = json.loads((raiz / "informes" / "preproduccion.json").read_text(encoding="utf-8"))
    pasa = lambda f, p: any(x["paso"].startswith(p + " ") for x in f["cadena"])  # noqa: E731
    nominales = [f["variable"] for f in js["finalistas"] if pasa(f, "P22")]
    numericas = [f["variable"] for f in js["finalistas"] if pasa(f, "P20") and f["variable"] not in nominales]
    vaciar = {f["variable"] for f in js["finalistas"] if pasa(f, "P21")}
    rc = js["receta"]
    muestra, tasa_real = la_muestra(args.tabla, pd.Timestamp(args.fecha), numericas + nominales + ["fecha", "horizonte_hasta", "falla_30d"],
                                    rc["semilla"], rc["muestra"]["fraccion_sanas"])
    y = muestra["falla_30d"].to_numpy().astype(int)
    Xe = muestra[numericas].astype(np.float32)
    Xf = foto_cols.loc[puntua, numericas].astype(np.float32)
    for c in nominales:
        # Las categorías raras: menos de 30 fotos, 20 fallos o 20 sanas van a «otras»; lo no visto, a «otras» o a la
        # categoría con más fotos; y el código, el orden alfabético de lo que queda
        te = texto(muestra[c], c in vaciar)
        g = pd.DataFrame({"v": te.to_numpy(), "y": y}).groupby("v")["y"].agg(["size", "sum"])
        quedan = sorted(k for k, r in g.iterrows() if r["size"] >= MINIMOS[0] and r["sum"] >= MINIMOS[1] and r["size"] - r["sum"] >= MINIMOS[2])
        hay_otras = len(quedan) < len(g)
        referencia = "otras" if hay_otras or not quedan else g.loc[quedan].sort_values("size", ascending=False, kind="stable").index[0]
        a_cat = lambda s: s.where(s.isin(quedan), referencia)  # noqa: E731
        ce, cf = a_cat(te), a_cat(texto(foto_cols.loc[puntua, c], c in vaciar))
        codigo = {k: float(i) for i, k in enumerate(sorted(set(ce)))}
        Xe[f"{c}_oe"] = np.float32(ce.map(codigo).to_numpy(dtype=float))
        Xf[f"{c}_oe"] = np.float32(cf.map(codigo).to_numpy(dtype=float))
    vacias = [c for c in Xe.columns if Xe[c].isna().all()]
    Xe, Xf = Xe.drop(columns=vacias), Xf.drop(columns=vacias)
    h = rc["hiperparametros"]
    cat = [c for c in rc["fijos"]["categorical_features"] if c in Xe.columns]
    hgb = HistGradientBoostingClassifier(early_stopping=False, random_state=rc["fijos"]["random_state"], categorical_features=cat,
                                         min_samples_leaf=max(20, int(np.floor(0.01 * len(y) + 0.5))), max_iter=h["max_iter"],
                                         max_depth=h["max_depth"], learning_rate=h["learning_rate"],
                                         l2_regularization=h["l2_regularization"]).fit(Xe, y)
    p = np.clip(hgb.predict_proba(Xf)[:, 1], 1e-15, 1 - 1e-15)
    tm = float(np.mean(y))
    odds = p / (1 - p) * (tasa_real / (1 - tasa_real)) / (tm / (1 - tm))
    salida = np.full(len(foto_cols), np.nan)
    salida[puntua] = odds / (1 + odds)
    return salida


# ---------------------------------------------------------------------------------------------------------------
# 4. La comparación fila a fila
# ---------------------------------------------------------------------------------------------------------------
def comparar(salida, serial, prob, listas, tolerancia):
    """Las diferencias entre la salida de ejecutar.py y lo rehecho aquí; lista vacía si coincide."""
    dif = []
    if len(salida) != len(serial) or list(salida["serial_number"].astype(str)) != list(serial):
        return [f"filas u orden distintos: salida {len(salida)}, foto {len(serial)}"]
    ps = salida["probabilidad"].to_numpy(dtype=float)
    if not np.array_equal(np.isnan(ps), np.isnan(prob)):
        dif.append(f"filas sin puntuar distintas: {int((np.isnan(ps) != np.isnan(prob)).sum())}")
        return dif
    d = np.abs(ps - prob)[~np.isnan(prob)]
    if d.size and d.max() > tolerancia:
        dif.append(f"probabilidad: {int((d > tolerancia).sum())} filas por encima de {tolerancia}, máximo {d.max():.3e}")
    validas = np.flatnonzero(~np.isnan(prob))
    orden = validas[np.lexsort((serial[validas], -prob[validas]))]
    for n in listas:
        esperada = np.zeros(len(serial))
        esperada[orden[:n]] = 1
        esperada[np.isnan(prob)] = np.nan
        dada = salida[f"en_lista_{n}"].astype("Float64").to_numpy(dtype=float, na_value=np.nan)
        malas = int(np.sum(~((dada == esperada) | (np.isnan(dada) & np.isnan(esperada)))))
        if malas:
            dif.append(f"lista de {n}: {malas} marcas distintas")
    return dif


def main():
    """Rehace, compara y, con --anotar, lo escribe en informes/preproduccion.json."""
    ap = argparse.ArgumentParser(description="Prueba por otro camino de la salida de ejecutar.py")
    for a in ("--salida", "--foto", "--mes", "--tabla", "--fecha"):
        ap.add_argument(a, required=True)
    ap.add_argument("--fotos-anteriores", nargs="+")
    ap.add_argument("--ventanas", nargs="+")
    ap.add_argument("--raiz", type=Path, default=CASO)
    ap.add_argument("--anotar", action="store_true")
    args = ap.parse_args()
    print(f"sys.executable: {sys.executable}")
    raiz = args.raiz.resolve()
    conf = json.loads((raiz / "produccion" / "configuracion.json").read_text(encoding="utf-8"))
    dec = json.loads(ruta_de(raiz, conf["decisiones_correccion"]).read_text(encoding="utf-8"))
    fecha = pd.Timestamp(f"{args.mes}-01")
    foto = pq.read_table(args.foto).to_pandas()
    def carpetas(valor):
        return [ruta_de(raiz, c) for c in ([valor] if isinstance(valor, str) else valor)]

    cols, puntua = columnas_de_la_foto(foto, carpetas(args.fotos_anteriores or conf["historia_fotos"]),
                                       carpetas(args.ventanas or conf["historia_ventanas"]), fecha,
                                       dec["modelos"]["mapeo"], dec["capacidad"]["minimo_valido_bytes"])
    prob = rehacer(raiz, args, cols, puntua)
    salida = pd.read_parquet(args.salida)
    serial = foto["serial_number"].astype(str).to_numpy()
    tol = conf["tolerancia_otro_camino"]
    dif = comparar(salida, serial, prob, conf["listas"], tol)
    for d in dif:
        print(f"distinto: {d}")
    if args.anotar:
        # La comparación tiene que saber salir en rojo: una probabilidad estropeada en una copia
        mala = salida.copy()
        i = int(np.flatnonzero(mala["probabilidad"].notna().to_numpy())[0])
        mala.loc[i, "probabilidad"] += 1e-9
        rojo = bool(comparar(mala, serial, prob, conf["listas"], tol))
        ruta = raiz / "informes" / "preproduccion.json"
        js = json.loads(ruta.read_text(encoding="utf-8"))
        js["prueba_por_otro_camino"] = {"salida": args.salida, "coincide": not dif, "tolerancia": tol, "rojo_con_estropeada": rojo,
                                        "filas": int(len(salida)), "puntuadas": int(np.sum(~np.isnan(prob))), "distintos": dif}
        js["validaciones"]["otro_camino"] = (not dif) and rojo
        if js["validaciones"]["otro_camino"] is False:
            js["resultado"]["estado"] = "ERROR"
        ruta.write_text(json.dumps(js, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    print("coincide" if not dif else "NO coincide")
    sys.exit(0 if not dif else 1)


if __name__ == "__main__":
    main()
