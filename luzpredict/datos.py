"""Descarga y preparación de datos reales.

Fuente de los precios: REData, la API pública de Red Eléctrica de España
(https://www.ree.es/es/apidatos). No necesita clave.
Fuente del tiempo: Open-Meteo.

Qué se ha comprobado y qué no:
- La forma del JSON de REData SÍ está en su documentación oficial.
- Los NOMBRES de las series de "precios-mercados-tiempo-real" (que contengan
  "spot" y "pvpc") hay que confirmarlos la primera vez que se ejecuta. Si no
  coinciden, el programa se para y enseña los nombres que ha encontrado.
"""
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ZONA = "Europe/Madrid"
URL_REDATA = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
URL_TIEMPO = "https://api.open-meteo.com/v1/forecast"
CABECERAS = {"Accept": "application/json", "User-Agent": "LuzPredict (proyecto universitario)"}

RUTA_CSV = "data/precios.csv"
COLUMNA_SPOT = "spot_eur_mwh"
COLUMNA_PVPC = "pvpc_eur_mwh"


# ---------------------------------------------------------------------------
# Preparación de los datos
# ---------------------------------------------------------------------------
def pasar_a_horario(serie):
    """Convierte precios de 15 minutos en precios por hora (la media de cada hora).

    Desde octubre de 2025 el mercado da un precio cada 15 minutos, pero antes
    daba uno por hora. Hacemos la media para tener todo en horas. Si los datos
    ya son horarios, no cambian.
    La serie debe tener zona horaria para que los días de cambio de hora
    (con 23 o 25 horas) salgan bien.
    """
    if serie.index.tz is None:
        raise ValueError("La serie necesita zona horaria (tz).")
    return serie.resample("h").mean()


def limpiar_serie(serie, max_hueco=3):
    """Rellena los huecos pequeños (hasta `max_hueco` horas seguidas) con una recta.

    Los huecos más largos se dejan vacíos: es mejor no inventar datos.
    """
    serie = serie.sort_index()
    todas_las_horas = pd.date_range(serie.index[0], serie.index[-1], freq="h")
    serie = serie.reindex(todas_las_horas)
    return serie.interpolate(limit=max_hueco)


def buscar_columna(tabla, palabra):
    """Busca la columna cuyo nombre contiene `palabra` (sin mirar mayúsculas)."""
    for columna in tabla.columns:
        if palabra.lower() in str(columna).lower():
            return columna
    raise ValueError(
        "No encuentro una serie con '" + palabra + "'. "
        "Series disponibles: " + str(list(tabla.columns))
    )


# ---------------------------------------------------------------------------
# Descarga de precios (REData)
# ---------------------------------------------------------------------------
def leer_respuesta_redata(respuesta):
    """Convierte el JSON de REData en una tabla de pandas (una columna por serie).

    El JSON tiene esta forma (según la documentación oficial):
      included -> lista de series; cada una tiene attributes -> title y values
      values   -> lista de {"value": número, "datetime": "2026-11-10T00:00:00.000+01:00"}
    """
    filas = []
    for serie in respuesta.get("included", []):
        nombre = serie["attributes"]["title"]
        for dato in serie["attributes"]["values"]:
            filas.append({"fecha": dato["datetime"], "serie": nombre, "valor": dato["value"]})

    if len(filas) == 0:
        return pd.DataFrame()

    tabla = pd.DataFrame(filas)
    tabla["fecha"] = pd.to_datetime(tabla["fecha"], utc=True).dt.tz_convert(ZONA)
    return tabla.pivot_table(index="fecha", columns="serie", values="valor").sort_index()


def trozos_de_fechas(inicio, fin, dias=30):
    """Parte un rango de fechas ('AAAA-MM-DD') en trozos de como mucho `dias` días.

    Pedir años enteros de golpe puede fallar, así que descargamos por trozos.
    Devuelve una lista de pares (inicio, fin) como texto.
    """
    trozos = []
    actual = date.fromisoformat(inicio)
    ultimo = date.fromisoformat(fin)
    while actual <= ultimo:
        fin_trozo = min(actual + timedelta(days=dias - 1), ultimo)
        trozos.append((actual.isoformat(), fin_trozo.isoformat()))
        actual = fin_trozo + timedelta(days=1)
    return trozos


def descargar_tramo(inicio, fin, intentos=3):
    """Descarga un tramo de fechas, reintentando si falla la conexión."""
    parametros = {
        "start_date": inicio + "T00:00",
        "end_date": fin + "T23:59",
        "time_trunc": "hour",
    }
    for intento in range(1, intentos + 1):
        try:
            respuesta = requests.get(URL_REDATA, params=parametros, headers=CABECERAS, timeout=30)
            respuesta.raise_for_status()  # si la web da error, salta al except
            return leer_respuesta_redata(respuesta.json())
        except requests.RequestException as error:
            if intento == intentos:
                raise RuntimeError("No se pudo descargar " + inicio + " a " + fin + ": " + str(error))
            time.sleep(2 * intento)  # espera un poco más en cada reintento


def descargar_precios(inicio, fin, pausa=0.5):
    """Descarga precios por hora entre dos fechas ('AAAA-MM-DD').

    Devuelve una tabla con dos columnas: spot_eur_mwh (mercado mayorista) y
    pvpc_eur_mwh (tarifa regulada).
    """
    tablas = []
    for ini_trozo, fin_trozo in trozos_de_fechas(inicio, fin):
        tabla = descargar_tramo(ini_trozo, fin_trozo)
        if len(tabla) > 0:
            tablas.append(tabla)
        time.sleep(pausa)  # pausa corta para no saturar la web de Red Eléctrica

    if len(tablas) == 0:
        raise ValueError("REData no ha devuelto datos entre " + inicio + " y " + fin + ".")

    todo = pd.concat(tablas)
    todo = todo[~todo.index.duplicated(keep="last")].sort_index()

    spot = pasar_a_horario(todo[buscar_columna(todo, "spot")])
    pvpc = pasar_a_horario(todo[buscar_columna(todo, "pvpc")])
    return pd.DataFrame({COLUMNA_SPOT: spot, COLUMNA_PVPC: pvpc})


# ---------------------------------------------------------------------------
# Archivo CSV local (así la web no depende de internet para arrancar)
# ---------------------------------------------------------------------------
def guardar_csv(tabla, ruta=RUTA_CSV):
    """Guarda la tabla en CSV. Las fechas se guardan en UTC para evitar líos con el cambio de hora."""
    salida = tabla.copy()
    salida.index = salida.index.tz_convert("UTC")
    salida.index.name = "fecha_utc"
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    salida.to_csv(ruta)


def leer_csv(ruta=RUTA_CSV):
    """Lee el CSV y devuelve la tabla con hora de Madrid. Si no existe, devuelve None."""
    if not Path(ruta).exists():
        return None
    tabla = pd.read_csv(ruta, index_col="fecha_utc")
    tabla.index = pd.to_datetime(tabla.index, utc=True).tz_convert(ZONA)
    tabla.index.name = "fecha"
    return tabla


def unir_tablas(vieja, nueva):
    """Une dos tablas sin repetir horas (si una hora está en las dos, manda la nueva)."""
    todo = pd.concat([vieja, nueva])
    return todo[~todo.index.duplicated(keep="last")].sort_index()


def actualizar_csv(ruta=RUTA_CSV, desde="2021-01-01", hasta=None):
    """Descarga los precios que faltan y actualiza el CSV.

    - Si el CSV no existe, descarga desde `desde` (por defecto, 2021).
    - Si ya existe, solo descarga desde 3 días antes de su último dato.
    - Intenta traer también los precios de mañana (se publican a media tarde).
    Devuelve la tabla completa.
    """
    hoy = date.fromisoformat(hasta) if hasta else date.today()
    manana = hoy + timedelta(days=1)

    existente = leer_csv(ruta)
    if existente is not None and len(existente) > 0:
        ultimo_dia = existente.index[-1].date()
        desde = (ultimo_dia - timedelta(days=3)).isoformat()

    nueva = descargar_precios(desde, hoy.isoformat())

    try:
        precios_manana = descargar_precios(manana.isoformat(), manana.isoformat())
        nueva = unir_tablas(nueva, precios_manana)
    except (RuntimeError, ValueError):
        print("Los precios de mañana todavía no están publicados (es normal antes de media tarde).")

    resultado = nueva if existente is None else unir_tablas(existente, nueva)
    guardar_csv(resultado, ruta)
    return resultado


# ---------------------------------------------------------------------------
# Tiempo (Open-Meteo)
# ---------------------------------------------------------------------------
def descargar_tiempo(dias=7):
    """Descarga la previsión del tiempo en Madrid: temperatura, viento y sol.

    Sirve para PREDECIR. Para ENTRENAR habrá que usar previsiones antiguas
    (Historical Forecast API de Open-Meteo), no datos "reales" pasados,
    o el modelo parecerá mejor de lo que es.
    """
    parametros = {
        "latitude": 40.4168,
        "longitude": -3.7038,
        "hourly": "temperature_2m,wind_speed_10m,shortwave_radiation",
        "forecast_days": dias,
        "timezone": ZONA,
    }
    respuesta = requests.get(URL_TIEMPO, params=parametros, timeout=30)
    respuesta.raise_for_status()
    tabla = pd.DataFrame(respuesta.json()["hourly"])
    tabla["time"] = pd.to_datetime(tabla["time"]).dt.tz_localize(ZONA, ambiguous="infer")
    return tabla.set_index("time")
