"""Prueba de las cuatro variables nuevas candidatas (P-04) en el ganador de la competición del caso 68.

Lo decidió el responsable del caso el 19/11/2026: las cuatro variables se prueban aunque el ganador supere a la regla, solo en el ganador,
con sus mismos hiperparámetros y sus mismos cinco pliegues, y se calculan aquí, sin tocar las tablas, la matriz ni los
scripts 05, 12 y 13. Si mejoran, se llevan a la tabla por el guion aprobado; si no, solo se apunta el resultado.

Las cuatro variables (petición 20, segunda parte; definiciones técnicas, 19/11/2026):
  1. contador entre edad: smart_5_raw, smart_187_raw, smart_197_raw y smart_198_raw divididos por edad_anos; vacío si
     falta la edad o es 0;
  2. discos que avisan en el vault: los demás discos de datos del mismo centro y vault en la misma foto con avisa, sin
     contar el propio; vacío sin centro o sin vault;
  3. fallos del vault en los 30 días anteriores: fallos de discos de datos del mismo centro y vault entre 30 días y 1
     día antes de la foto; por vault y no por tomo, porque un tomo tiene muy pocos discos; vacío sin vault o si la
     ventana empieza antes de que conste el sitio (01/07/2023);
  4. tasa del modelo a esa edad: fallos por año de disco del mismo modelo y los mismos años cumplidos, con solo los
     meses anteriores al de la foto (data/processed/dias_por_tramo.parquet, sumando los centros); vacía sin historial.

Lo que compara: el ganador sin sitio (como quedó en informes/modelado.json) en seis brazos: sin las variables, con las
cuatro y con cada una sola. Cada pliegue ajusta el preprocesador del ganador (scripts/13_preparacion.py) una vez y
añade a su salida las columnas del brazo. La medida es la de la competición: la media, en los meses del bloque, de los
fallos en la lista de 100. Las cuatro entran si, pliegue a pliegue, la media de su mejora pasa de su desviación típica
(la regla de empate de la competición); con empate, se queda el modelo más sencillo, sin ellas.

Control: el brazo sin variables tiene que repetir pliegue a pliegue las cifras de la competición; si no, para.

Importa scripts/15_modelado.py y, con él, el 13, con importlib: su trabajo está dentro de `if __name__ == "__main__":` y
al importarlos solo definen sus piezas. Lee data/processed/fotos_riesgo_entrenamiento.parquet, fallos_detalle.parquet,
dias_por_tramo.parquet e informes/modelado.json, que deja el 15; no abre la validación.

Uso: python -W error scripts/16_variables_nuevas.py
Escribe informes/variables_nuevas.json. Sale con 0 si termina, con 2 si para y con 1 si falla.
"""

# =================================================================================================================
# 1. Preparación
# =================================================================================================================
import datetime as dt
import importlib.util
import json
import platform
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import sklearn

CASO = Path(__file__).resolve().parents[1]


def cargar_15():
    """Carga scripts/15_modelado.py como módulo; solo define sus piezas, porque su trabajo está bajo __main__."""
    spec = importlib.util.spec_from_file_location("modelado_15", CASO / "scripts" / "15_modelado.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["modelado_15"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


M15 = cargar_15()

# =================================================================================================================
# 2. Configuración
# =================================================================================================================
SCRIPT = "scripts/16_variables_nuevas.py"
FECHA_DATOS = M15.FECHA_DATOS
MODELADO = "informes/modelado.json"
ENTRENAMIENTO = M15.ENTRENAMIENTO
FALLOS = "data/processed/fallos_detalle.parquet"
DIAS = "data/processed/dias_por_tramo.parquet"
SALIDA = "informes/variables_nuevas.json"
CONTADORES_AVERIA = [5, 187, 197, 198]                       # los cuatro contadores de avería (reglas, apartado 7)
VENTANA_DIAS = 30                                            # fallos del vault en los 30 días anteriores
SITIO_DESDE = pd.Timestamp(M15.SITIO_DESDE)                  # el sitio consta desde el 01/07/2023
DIAS_ANO = 365.25
# La foto también necesita el vault, que el 15 no lee
EXTRA = ["vault_id"]

V1 = [f"smart_{k}_raw_por_ano" for k in CONTADORES_AVERIA]
V2, V3, V4 = ["avisan_en_vault"], ["fallos_vault_30d"], ["tasa_modelo_edad"]
BRAZOS = {"sin_variables": [], "las_cuatro": V1 + V2 + V3 + V4, "solo_contador_entre_edad": V1,
          "solo_avisan_en_vault": V2, "solo_fallos_vault_30d": V3, "solo_tasa_modelo_edad": V4}


class Parada(Exception):
    """Condición que impide seguir."""


# =================================================================================================================
# 3. Las cuatro variables
# =================================================================================================================
def por_ano(df):
    """1. Cada contador de avería dividido por la edad en años; vacío si falta la edad o es 0."""
    edad = pd.to_numeric(df["edad_anos"]).to_numpy(dtype=float, na_value=np.nan)
    edad = np.where(edad > 0, edad, np.nan)
    salida = {}
    for k in CONTADORES_AVERIA:
        valor = pd.to_numeric(df[f"smart_{k}_raw"]).to_numpy(dtype=float, na_value=np.nan)
        salida[f"smart_{k}_raw_por_ano"] = valor / edad
    return pd.DataFrame(salida, index=df.index)


def _claves_vault(df):
    """Las claves de centro, vault y foto, con el vault como entero; vacías si falta el centro o el vault."""
    return pd.DataFrame({"fecha": pd.to_datetime(df["fecha"]).to_numpy(), "datacenter": df["datacenter"].astype(object).to_numpy(),
                         "vault_id": pd.array(df["vault_id"], dtype="Int64")}, index=df.index)


def cuenta_avisos(tabla):
    """Cuántos discos avisan en cada centro, vault y foto, contados sobre la tabla entera de fotos."""
    k = _claves_vault(tabla)
    k["avisa"] = np.asarray(pd.array(tabla["avisa"], dtype="boolean").fillna(False), dtype=int)
    k = k[k["datacenter"].notna() & k["vault_id"].notna()]
    return k.groupby(["fecha", "datacenter", "vault_id"], as_index=False)["avisa"].sum().rename(columns={"avisa": "avisan"})


def avisan_en_vault(df, cuenta):
    """2. Los demás discos que avisan en el mismo centro, vault y foto, sin el propio; vacío sin centro o sin vault."""
    k = _claves_vault(df)
    propio = np.asarray(pd.array(df["avisa"], dtype="boolean").fillna(False), dtype=int)
    unido = k.reset_index(drop=True).merge(cuenta, on=["fecha", "datacenter", "vault_id"], how="left", validate="m:1")
    v = unido["avisan"].to_numpy(dtype=float, na_value=np.nan) - propio
    con_sitio = (k["datacenter"].notna() & k["vault_id"].notna()).to_numpy()
    v = np.where(con_sitio, np.where(np.isnan(v), 0.0, v), np.nan)
    return pd.Series(v, index=df.index, name="avisan_en_vault")


def fallos_vault_30d(df, fallos):
    """3. Fallos de discos de datos del mismo centro y vault entre 30 días y 1 día antes de la foto; vacío sin vault o
    si la ventana empieza antes de que conste el sitio."""
    f = fallos[(fallos["tipo_disco"] == "datos") & fallos["datacenter"].notna() & fallos["vault_id"].notna()]
    dias_fallo = {}
    for (dc, va), g in f.groupby(["datacenter", "vault_id"]):
        dias_fallo[(dc, int(va))] = np.sort(pd.to_datetime(g["dia_fallo"]).to_numpy(dtype="datetime64[ms]"))
    k = _claves_vault(df)
    salida = np.full(len(k), np.nan)
    for (fe, dc, va), pos in k.groupby(["fecha", "datacenter", "vault_id"]).indices.items():
        desde = pd.Timestamp(fe) - pd.Timedelta(days=VENTANA_DIAS)
        if desde < SITIO_DESDE:
            continue
        d = dias_fallo.get((dc, int(va)), np.array([], dtype="datetime64[ms]"))
        a = np.searchsorted(d, np.datetime64(desde, "ms"), side="left")
        b = np.searchsorted(d, np.datetime64(pd.Timestamp(fe), "ms"), side="left")
        salida[pos] = float(b - a)
    return pd.Series(salida, index=df.index, name="fallos_vault_30d")


def tasa_modelo_edad(df, dias):
    """4. Fallos por año de disco del mismo modelo y los mismos años cumplidos, con solo los meses anteriores al de la
    foto, sumando los centros; vacía sin historial o sin edad."""
    d = dias.groupby(["model", "edad_anos_cumplidos", "mes"], as_index=False)[["fallos", "dias_disco"]].sum()
    d = d.sort_values(["model", "edad_anos_cumplidos", "mes"])
    d[["fallos_acum", "dias_acum"]] = d.groupby(["model", "edad_anos_cumplidos"])[["fallos", "dias_disco"]].cumsum()
    edad = pd.to_numeric(df["edad_anos"]).to_numpy(dtype=float, na_value=np.nan)
    q = pd.DataFrame({"pos": np.arange(len(df)), "model": df["model"].astype(object).to_numpy(),
                      "edad_anos_cumplidos": np.floor(edad), "mes": pd.to_datetime(df["fecha"]).to_numpy(dtype="datetime64[ns]")})
    salida = np.full(len(df), np.nan)
    q = q[~np.isnan(q["edad_anos_cumplidos"])].copy()
    q["edad_anos_cumplidos"] = q["edad_anos_cumplidos"].astype(np.int64)
    d["mes"] = pd.to_datetime(d["mes"]).astype("datetime64[ns]")
    d["edad_anos_cumplidos"] = d["edad_anos_cumplidos"].astype(np.int64)
    d["model"] = d["model"].astype("str")
    q["model"] = q["model"].astype("str")
    if len(q):
        # El último mes acumulado estrictamente anterior al de la foto, del mismo modelo y la misma edad
        u = pd.merge_asof(q.sort_values("mes", kind="stable"),
                          d[["model", "edad_anos_cumplidos", "mes", "fallos_acum", "dias_acum"]].sort_values("mes", kind="stable"),
                          on="mes", by=["model", "edad_anos_cumplidos"], allow_exact_matches=False, direction="backward")
        # Solo se divide donde hay días de disco: con 0 días no hay tasa y queda vacía
        dias_acum = u["dias_acum"].to_numpy(dtype=float, na_value=np.nan)
        ok = dias_acum > 0
        tasa = u["fallos_acum"].to_numpy(dtype=float, na_value=np.nan)[ok] / dias_acum[ok] * DIAS_ANO
        salida[u["pos"].to_numpy()[ok]] = tasa
    return pd.Series(salida, index=df.index, name="tasa_modelo_edad")


def variables(df, tablas):
    """Las cuatro variables, siete columnas, en las filas de `df` y en su orden."""
    v = por_ano(df)
    v["avisan_en_vault"] = avisan_en_vault(df, tablas["avisos"])
    v["fallos_vault_30d"] = fallos_vault_30d(df, tablas["fallos"])
    v["tasa_modelo_edad"] = tasa_modelo_edad(df, tablas["dias"])
    return v.astype(np.float32)


# =================================================================================================================
# 4. La decisión pliegue a pliegue (regla de empate de la competición)
# =================================================================================================================
def decision(base, con):
    """Entran si la media de la mejora pliegue a pliegue pasa de su desviación típica y es positiva."""
    e = M15.empate(con, base)
    entran = bool((not e["empatan"]) and e["media"] > 0)
    return {**e, "entran": entran,
            "veredicto": "mejoran" if entran else ("empatan" if e["empatan"] else "empeoran")}


# =================================================================================================================
# 5. Ajustar y medir los seis brazos en un pliegue
# =================================================================================================================
def pliegue(f, receta, datos, ctx, tablas, cobertura, vacias):
    """Un pliegue: el preprocesador del ganador sin sitio, una vez; cada brazo, su modelo con sus columnas; las cifras
    de cada mes del bloque."""
    df, y, c = ctx.entrenamiento(f)
    nuevas = variables(df, tablas)
    cobertura[f] = {col: float(nuevas[col].notna().mean()) for col in nuevas.columns}
    base_df = M15.sin_sitio(df)
    pre = M15.P13.preprocesador("hgb").fit(base_df, y)
    Xt = M15.transformar(pre, base_df, "hgb", ctx)
    # Lo mismo que hace el 15: una columna sin ningún dato en el ajuste sale de él
    pre.columnas_vacias_ = [col for col in Xt.columns if Xt[col].isna().all()]
    Xt = Xt.drop(columns=pre.columnas_vacias_)
    modelos = {}
    for brazo, cols in BRAZOS.items():
        usar = [col for col in cols if nuevas[col].notna().any()]
        vacias[f"{f}:{brazo}"] = [col for col in cols if col not in usar]
        X = pd.concat([Xt, nuevas[usar].set_axis(Xt.index)], axis=1) if usar else Xt
        mdl = M15.construir("hgb", receta, c["hoja"]).fit(X, y)
        modelos[brazo] = (mdl, usar)
    meses = {b: [] for b in BRAZOS}
    for mes in ctx.meses_bloque(f):
        dm = datos.mes(mes)
        ym = dm[M15.OBJETIVO].to_numpy().astype(int)
        nm = variables(dm, tablas)
        Xm = M15.transformar(pre, M15.sin_sitio(dm), "hgb", ctx)
        for brazo, (mdl, usar) in modelos.items():
            X = pd.concat([Xm, nm[usar].set_axis(Xm.index)], axis=1) if usar else Xm
            p = np.concatenate([mdl.predict_proba(X.iloc[a:a + M15.TROZO])[:, 1] for a in range(0, len(X), M15.TROZO)])
            r = M15.medidas_mes(ym, [p], p)
            r["mes"] = mes.date().isoformat()
            meses[brazo].append(r)
    return meses, {"filas": int(len(df)), "fallos": int(y.sum()), "hoja": c["hoja"]}


# =================================================================================================================
# 6. Principal
# =================================================================================================================
def principal():
    """Lee lo necesario, mide los seis brazos en los cinco pliegues, comprueba el control y escribe el JSON."""
    inicio = time.time()
    res = {"script": SCRIPT, "fecha_datos": FECHA_DATOS, "fecha_ejecucion": dt.date.today().isoformat(),
           "decidido_por": "El responsable del caso, 19/11/2026: probar las cuatro variables solo en el ganador, calculadas en este script"}
    try:
        md = json.loads((CASO / MODELADO).read_text(encoding="utf-8"))
        g = md["ganador"]
        if g["algoritmo"] != "hgb" or g["datacenter"] != "se vacía (sin sitio)":
            raise Parada(f"el ganador de {MODELADO} no es el HistGradientBoosting sin sitio que se prueba aquí")
        receta = g["hiperparametros"]
        M15.LEER = M15.LEER + EXTRA                          # el 15 lee sus columnas de LEER; aquí, también el vault
        datos = M15.Datos(CASO / ENTRENAMIENTO)
        ctx = M15.Contexto(datos, [], {})
        t0 = time.time()
        avisos = cuenta_avisos(pq.read_table(CASO / ENTRENAMIENTO, columns=["fecha", "datacenter", "vault_id", "avisa"]).to_pandas())
        tablas = {"avisos": avisos, "fallos": pd.read_parquet(CASO / FALLOS), "dias": pd.read_parquet(CASO / DIAS)}
        res["segundos_tablas"] = round(time.time() - t0, 1)
        cobertura, vacias, por_brazo, muestras = {}, {}, {b: {} for b in BRAZOS}, {}
        for f in range(len(M15.BLOQUES)):
            t1 = time.time()
            meses, muestras[f] = pliegue(f, receta, datos, ctx, tablas, cobertura, vacias)
            for b in BRAZOS:
                por_brazo[b][f] = meses[b]
            print(f"pliegue {f + 1}: {round(time.time() - t1)} s, lista de 100 sin variables "
                  f"{np.mean([m['lista_100'] for m in meses['sin_variables']]):.2f}, con las cuatro "
                  f"{np.mean([m['lista_100'] for m in meses['las_cuatro']]):.2f}", flush=True)
            ctx.cache.pop(f, None)
        brazos = {}
        for b, pl in por_brazo.items():
            v = [float(np.mean([m["lista_100"] for m in pl[f]])) for f in sorted(pl)]
            aucs = [m["auc"] for f in sorted(pl) for m in pl[f] if m["auc"] is not None]
            brazos[b] = {"columnas": BRAZOS[b], "por_pliegue": v, "media": float(np.mean(v)),
                         "auc_media": float(np.mean(aucs)), "meses": {str(f + 1): pl[f] for f in sorted(pl)}}
        res["brazos"] = brazos
        res["comparaciones"] = {b: decision(brazos["sin_variables"]["por_pliegue"], brazos[b]["por_pliegue"])
                                for b in BRAZOS if b != "sin_variables"}
        res["decision"] = res["comparaciones"]["las_cuatro"]
        res["cobertura_en_la_muestra"] = {str(f + 1): c for f, c in cobertura.items()}
        res["columnas_sin_dato_en_el_ajuste"] = {k: v for k, v in vacias.items() if v}
        res["muestras"] = {str(f + 1): m for f, m in muestras.items()}
        # Control: el brazo sin variables repite la competición (pliegue 1 del ranking; 2 a 5, del «sin» del sitio)
        hgb = [x for x in md["ranking"] if x["algoritmo"] == "hgb"][0]
        sin = md["sitio"]["sin"]
        esperado = [hgb["cv_por_pliegue"][0]] + [float(np.mean(sin[3 * i:3 * i + 3])) for i in range(4)]
        dif = float(np.max(np.abs(np.asarray(brazos["sin_variables"]["por_pliegue"]) - np.asarray(esperado))))
        res["control"] = {"esperado": esperado, "obtenido": brazos["sin_variables"]["por_pliegue"], "diferencia_maxima": dif,
                          "igual": bool(dif < 1e-9), "de_donde": f"{MODELADO}: ranking (pliegue 1) y sitio.sin (pliegues 2 a 5)"}
        if not res["control"]["igual"]:
            raise Parada(f"el brazo sin variables no repite la competición: {res['control']['obtenido']} frente a {esperado}")
        d = res["decision"]
        res["resultado"] = {"estado": "OK", "resumen": (
            f"Las cuatro variables {d['veredicto']}: con ellas, la lista de 100 encuentra de media "
            f"{d['media']:.2f} fallos más por mes que sin ellas, con una desviación entre pliegues de {d['desviacion']:.2f}.")}
        codigo = 0
    except Parada as p:
        res["resultado"] = {"estado": "PARADO", "resumen": f"El script paró: {p}"}
        codigo = 2
    except Exception as e:  # noqa: BLE001 - el JSON se escribe también cuando falla
        res["resultado"] = {"estado": "ERROR", "resumen": f"{type(e).__name__}: {e}"[:2000]}
        res["traza"] = traceback.format_exc()[-3000:]
        codigo = 1
    res["ejecucion"] = {"segundos": round(time.time() - inicio, 1), "python": platform.python_version(),
                        "ejecutable": sys.executable, "pandas": pd.__version__, "scikit_learn": sklearn.__version__}
    (CASO / SALIDA).write_text(json.dumps(res, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    print(f"{res['resultado']['estado']}: {res['resultado']['resumen']}")
    return codigo


if __name__ == "__main__":
    sys.exit(principal())
