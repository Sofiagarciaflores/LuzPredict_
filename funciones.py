"""Todo el cálculo de LuzPredict, en un solo archivo.

Está dividido en cuatro bloques:
  1. Datos reales: descarga de precios de Red Eléctrica (REData) y guardado en CSV.
  2. Datos de demostración: precios inventados, por si todavía no hay CSV.
  3. Previsión: método de referencia (misma hora de la semana anterior) y su evaluación.
  4. Resúmenes y planificador: medias para los gráficos y búsqueda de la hora más barata.

Fuente de los precios: REData (https://www.ree.es/es/apidatos), sin clave.
OJO: la forma del JSON sale de la documentación oficial, pero los NOMBRES de las
series ("spot" y "pvpc") hay que confirmarlos la primera vez que se descargan.
Si no coinciden, el programa se para y enseña los nombres que ha encontrado.
"""
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ZONA = "Europe/Madrid"
URL_REDATA = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
CABECERAS = {"Accept": "application/json", "User-Agent": "LuzPredict (proyecto universitario)"}

RUTA_CSV = "data/precios.csv"
COLUMNA_SPOT = "spot_eur_mwh"
COLUMNA_PVPC = "pvpc_eur_mwh"

HORAS_SEMANA = 168  # 7 días x 24 horas

# En 2026, el 45 % del PVPC depende del mercado diario (el 55 % restante, de
# mercados a plazo). Es una aproximación, no el cálculo exacto de la factura.
PESO_MERCADO_DIARIO = 0.45


# ===========================================================================
# 1. DATOS REALES
# ===========================================================================
def pasar_a_horario(serie):
    """Convierte precios de 15 minutos en precios por hora (la media de cada hora).

    Desde octubre de 2025 el mercado da un precio cada 15 minutos; antes daba
    uno por hora. Si los datos ya son horarios, no cambian. La serie necesita
    zona horaria para que los días de cambio de hora (23 o 25 horas) salgan bien.
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

    Pedir años enteros de golpe puede fallar, así que se descarga por trozos.
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


# ===========================================================================
# 2. DATOS DE DEMOSTRACIÓN
# ===========================================================================
def crear_precios_demo(dias=730, fin=None, semilla=0):
    """Precios INVENTADOS que imitan el patrón real (para cuando no hay CSV).

    Patrón: barato al mediodía (sol), caro por la noche, más barato en fin de
    semana y en verano, con algo de ruido aleatorio. NO son precios reales.
    """
    if fin is None:
        fin = pd.Timestamp.now(tz=ZONA).floor("h")
    else:
        fin = pd.Timestamp(fin)
        if fin.tzinfo is None:
            fin = fin.tz_localize(ZONA)

    horas = pd.date_range(end=fin, periods=24 * dias, freq="h")
    hora_del_dia = horas.hour.to_numpy()
    dia_semana = horas.dayofweek.to_numpy()  # 0 = lunes ... 6 = domingo
    dia_del_anio = horas.dayofyear.to_numpy()

    estacion = 1 + 0.35 * np.cos(2 * np.pi * (dia_del_anio - 15) / 365)
    bajada_solar = -70 * np.exp(-((hora_del_dia - 14) ** 2) / 18)
    subida_noche = 55 * np.exp(-((hora_del_dia - 21) ** 2) / 6)
    fin_de_semana = np.where(dia_semana >= 5, -18, 0)

    # Ruido que se arrastra de una hora a la siguiente (unos días más caros que otros)
    generador = np.random.default_rng(semilla)
    sustos = generador.normal(0, 9, len(horas))
    ruido = np.zeros(len(horas))
    for i in range(1, len(horas)):
        ruido[i] = 0.985 * ruido[i - 1] + sustos[i]

    precio = 95 * estacion + bajada_solar + subida_noche + fin_de_semana + ruido
    precio = np.clip(precio, -2, None)  # el precio casi nunca baja de -2
    return pd.Series(precio, index=horas, name="precio_eur_mwh")


# ===========================================================================
# 3. PREVISIÓN
# ===========================================================================
def prever_como_semana_anterior(historial, horas=168):
    """Predice las próximas `horas` horas copiando los precios de hace una semana.

    Es el método de referencia: muy simple a propósito. El modelo de aprendizaje
    automático tendrá que ganarle. Como miramos justo una semana atrás (168 h)
    y prevemos como mucho 168 h, todo lo que copiamos ya se conoce.
    """
    if horas > HORAS_SEMANA:
        raise ValueError("No se puede prever más de 168 horas con este método.")

    primera_hora = historial.index[-1] + pd.Timedelta(hours=1)
    horas_futuras = pd.date_range(primera_hora, periods=horas, freq="h")
    horas_copiadas = horas_futuras - pd.Timedelta(hours=HORAS_SEMANA)
    valores = historial.reindex(horas_copiadas).to_numpy()
    return pd.Series(valores, index=horas_futuras, name="prevision_eur_mwh")


def evaluar(serie, n_pruebas=40, cada_dias=3):
    """Mide cuánto se equivoca la previsión, según los días de antelación.

    Hace como si estuviéramos en el pasado: corta la serie en una fecha, prevé
    los 7 días siguientes y compara con lo que pasó de verdad. Lo repite
    n_pruebas veces y devuelve el error medio (MAE, en €/MWh) para cada día 1..7.
    """
    errores = []  # aquí guardamos (día de antelación, error)

    ultimo_origen = serie.index[-1] - pd.Timedelta(hours=168)
    for i in range(n_pruebas):
        origen = ultimo_origen - pd.Timedelta(days=cada_dias * i)
        pasado = serie.loc[:origen]  # solo lo que se sabía ese día
        if len(pasado) <= HORAS_SEMANA:
            continue

        prevision = prever_como_semana_anterior(pasado)
        real = serie.reindex(prevision.index)
        error = (prevision - real).abs()

        for posicion in range(len(prevision)):
            dia = posicion // 24 + 1  # horas 0-23 -> día 1, 24-47 -> día 2...
            errores.append({"dia": dia, "error": error.iloc[posicion]})

    if len(errores) == 0:
        raise ValueError("No hay historial suficiente para evaluar.")

    tabla = pd.DataFrame(errores)
    return tabla.groupby("dia", as_index=False)["error"].mean().rename(columns={"error": "mae"})


# ===========================================================================
# 4. RESÚMENES PARA LOS GRÁFICOS Y PLANIFICADOR
# ===========================================================================
def media_por_hora(serie, dias=90):
    """Precio medio de cada hora del día (0 a 23) en los últimos `dias` días."""
    reciente = serie.loc[serie.index[-1] - pd.Timedelta(days=dias):]
    return reciente.groupby(reciente.index.hour).mean()


def media_mensual(serie):
    """Precio medio de cada mes (para ver la evolución a lo largo de los años)."""
    return serie.resample("MS").mean().dropna()


def coste_de_un_bloque(precios, inicio, duracion, kwh, peso):
    """Coste (en €) de usar el aparato `duracion` horas desde `inicio`.

    El consumo se reparte a partes iguales entre las horas. Los precios están
    en €/MWh, así que se divide entre 1000 para pasarlos a €/kWh.
    """
    fin = inicio + pd.Timedelta(hours=duracion - 1)
    bloque = precios.loc[inicio:fin]
    kwh_por_hora = kwh / duracion
    return float((bloque / 1000 * kwh_por_hora * peso).sum())


def planificar(precios, desde, hasta, duracion, kwh, hora_referencia=21, peso=PESO_MERCADO_DIARIO):
    """Busca la hora de inicio más barata entre `desde` y `hasta`.

    Devuelve un diccionario con:
      mejor_inicio, inicio_referencia, coste_mejor, coste_referencia, ahorro

    El ahorro se compara con empezar a las `hora_referencia` (las 21:00 por
    defecto); si no hay ninguna a esa hora, con el primer inicio posible.
    """
    ventana = precios.loc[desde:hasta]
    n_inicios = len(ventana) - duracion + 1
    if n_inicios <= 0:
        raise ValueError("La ventana es más corta que la duración del programa.")

    posibles_inicios = list(ventana.index[:n_inicios])

    # Coste de empezar en cada hora posible
    costes = {}
    for inicio in posibles_inicios:
        costes[inicio] = coste_de_un_bloque(ventana, inicio, duracion, kwh, peso)

    mejor_inicio = min(costes, key=costes.get)  # el inicio con menor coste

    inicio_referencia = posibles_inicios[0]
    for inicio in posibles_inicios:
        if inicio.hour == hora_referencia:
            inicio_referencia = inicio
            break

    return {
        "mejor_inicio": mejor_inicio,
        "inicio_referencia": inicio_referencia,
        "coste_mejor": costes[mejor_inicio],
        "coste_referencia": costes[inicio_referencia],
        "ahorro": costes[inicio_referencia] - costes[mejor_inicio],
    }
