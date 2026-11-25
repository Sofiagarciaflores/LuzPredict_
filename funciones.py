"""Todo el cálculo de LuzPredict, en un solo archivo.

Está dividido en cinco bloques:
  1. Datos reales: descarga de precios de Red Eléctrica (REData) y guardado en CSV.
  2. Datos de demostración: precios inventados, por si todavía no hay CSV.
  3. Previsión de referencia: métodos sencillos y su evaluación en el pasado.
  4. Modelo de aprendizaje automático: gradient boosting con intervalo del 80 %.
  5. Resúmenes y planificador: medias para los gráficos y búsqueda de la hora más barata.

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
from sklearn.ensemble import HistGradientBoostingRegressor

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


def trozos_de_fechas(inicio, fin):
    """Parte un rango de fechas ('AAAA-MM-DD') en trozos de como mucho un mes natural.

    REData rechaza (error 400) los tramos que cruzan varios meses, así que se pide
    mes a mes. Devuelve una lista de pares (inicio, fin) como texto.
    """
    trozos = []
    actual = date.fromisoformat(inicio)
    ultimo = date.fromisoformat(fin)
    while actual <= ultimo:
        mes_siguiente = (actual.replace(day=1) + timedelta(days=32)).replace(day=1)
        fin_trozo = min(mes_siguiente - timedelta(days=1), ultimo)
        trozos.append((actual.isoformat(), fin_trozo.isoformat()))
        actual = fin_trozo + timedelta(days=1)
    return trozos


class TramoRechazado(RuntimeError):
    """REData ha contestado con un error (por ejemplo 400) a un tramo de fechas."""


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
                mensaje = "No se pudo descargar " + inicio + " a " + fin + ": " + str(error)
                if isinstance(error, requests.HTTPError):
                    detalle = getattr(error.response, "text", "")[:200]  # REData explica el motivo aquí
                    raise TramoRechazado(mensaje + " | " + detalle)
                raise RuntimeError(mensaje)
            time.sleep(2 * intento)  # espera un poco más en cada reintento


def descargar_partiendo_si_falla(inicio, fin, dias_sin_datos):
    """Descarga un tramo; si REData lo rechaza, lo parte por la mitad y lo vuelve a intentar.

    Si ni siquiera un día suelto se puede descargar, se anota en `dias_sin_datos`.
    Los errores de conexión (sin internet) NO se parten: se paran enseguida.
    """
    try:
        return [descargar_tramo(inicio, fin)]
    except TramoRechazado:
        if inicio == fin:
            dias_sin_datos.append(inicio)
            return []
        primero, ultimo = date.fromisoformat(inicio), date.fromisoformat(fin)
        mitad = primero + (ultimo - primero) // 2
        return (descargar_partiendo_si_falla(inicio, mitad.isoformat(), dias_sin_datos)
                + descargar_partiendo_si_falla((mitad + timedelta(days=1)).isoformat(), fin, dias_sin_datos))


def descargar_precios(inicio, fin, pausa=0.5):
    """Descarga precios por hora entre dos fechas ('AAAA-MM-DD').

    Devuelve una tabla con dos columnas: spot_eur_mwh (mercado mayorista) y
    pvpc_eur_mwh (tarifa regulada).
    """
    tablas = []
    dias_sin_datos = []
    for ini_trozo, fin_trozo in trozos_de_fechas(inicio, fin):
        for tabla in descargar_partiendo_si_falla(ini_trozo, fin_trozo, dias_sin_datos):
            if len(tabla) > 0:
                tablas.append(tabla)
        time.sleep(pausa)  # pausa corta para no saturar la web de Red Eléctrica

    if len(dias_sin_datos) > 0:
        print("AVISO: REData no ha dado datos de " + str(len(dias_sin_datos)) + " día(s): "
              + ", ".join(dias_sin_datos[:10]) + (" ..." if len(dias_sin_datos) > 10 else ""))

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


def prever_como_media_de_4_semanas(historial, horas=168):
    """Predice cada hora con la media de esa misma hora en las 4 semanas anteriores.

    Es otro método sencillo: suaviza el ruido de una sola semana. Solo mira
    desplazamientos de 168, 336, 504 y 672 horas, así que no usa nada del futuro.
    """
    if horas > HORAS_SEMANA:
        raise ValueError("No se puede prever más de 168 horas con este método.")

    primera_hora = historial.index[-1] + pd.Timedelta(hours=1)
    horas_futuras = pd.date_range(primera_hora, periods=horas, freq="h")
    semanas_anteriores = {}
    for semanas in range(1, 5):
        horas_copiadas = horas_futuras - pd.Timedelta(hours=HORAS_SEMANA * semanas)
        semanas_anteriores[semanas] = historial.reindex(horas_copiadas).to_numpy()
    valores = pd.DataFrame(semanas_anteriores).mean(axis=1)  # ignora las semanas sin dato
    return pd.Series(valores.to_numpy(), index=horas_futuras, name="prevision_eur_mwh")


# Métodos de referencia que se comparan (nombre para mostrar -> función)
METODOS_DE_REFERENCIA = {
    "Misma hora de la semana anterior": prever_como_semana_anterior,
    "Media de las 4 semanas anteriores": prever_como_media_de_4_semanas,
}


def evaluar(serie, n_pruebas=40, cada_dias=3, metodo=prever_como_semana_anterior):
    """Mide cuánto se equivoca una previsión, según los días de antelación.

    Hace como si estuviéramos en el pasado: corta la serie en una fecha, prevé
    los 7 días siguientes y compara con lo que pasó de verdad. Lo repite
    n_pruebas veces y devuelve, para cada día 1..7:
      mae = error medio absoluto (en €/MWh)
      pct = ese error como % del precio medio real de las pruebas
    """
    filas = []  # aquí guardamos (día de antelación, error, precio real)

    ultimo_origen = serie.index[-1] - pd.Timedelta(hours=168)
    for i in range(n_pruebas):
        origen = ultimo_origen - pd.Timedelta(days=cada_dias * i)
        pasado = serie.loc[:origen]  # solo lo que se sabía ese día
        if len(pasado) <= HORAS_SEMANA:
            continue

        prevision = metodo(pasado)
        real = serie.reindex(prevision.index)
        error = (prevision - real).abs()

        for posicion in range(len(prevision)):
            dia = posicion // 24 + 1  # horas 0-23 -> día 1, 24-47 -> día 2...
            filas.append({"dia": dia, "error": error.iloc[posicion], "real": real.iloc[posicion]})

    if len(filas) == 0:
        raise ValueError("No hay historial suficiente para evaluar.")

    tabla = pd.DataFrame(filas).groupby("dia", as_index=False).mean()
    tabla["pct"] = 100 * tabla["error"] / tabla["real"]
    return tabla.rename(columns={"error": "mae"})[["dia", "mae", "pct"]]


# ===========================================================================
# 4. MODELO DE APRENDIZAJE AUTOMÁTICO
# ===========================================================================
NOMBRE_MODELO = "Aprendizaje automático (gradient boosting)"
CUANTILES = {"bajo": 0.10, "central": 0.50, "alto": 0.90}  # intervalo del 80 %


def crear_variables(historial, horas_objetivo):
    """Datos de entrada del modelo para cada hora que queremos prever.

    REGLA CLAVE (sin trampas): para prever la hora t solo se mira lo que ocurrió
    168 horas (una semana) o más antes de t. Como prevemos como mucho 7 días, eso
    ya se conoce siempre, sea cual sea el día de antelación.
    """
    ultima = max(horas_objetivo.max(), historial.index[-1])
    completa = historial.reindex(pd.date_range(historial.index[0], ultima, freq="h"))

    tabla = pd.DataFrame(index=completa.index)
    tabla["hace_1_semana"] = completa.shift(HORAS_SEMANA)
    tabla["hace_2_semanas"] = completa.shift(2 * HORAS_SEMANA)
    tabla["hace_3_semanas"] = completa.shift(3 * HORAS_SEMANA)
    # medias de las 24 h y de los 7 días que terminaban justo hace una semana
    tabla["media_dia_hace_1_semana"] = completa.rolling(24, min_periods=12).mean().shift(HORAS_SEMANA)
    tabla["media_semana_hace_1_semana"] = completa.rolling(HORAS_SEMANA, min_periods=48).mean().shift(HORAS_SEMANA)
    # el calendario sí se conoce siempre
    tabla["hora"] = tabla.index.hour
    tabla["dia_semana"] = tabla.index.day_of_week
    tabla["mes"] = tabla.index.month
    tabla["fin_de_semana"] = (tabla.index.day_of_week >= 5).astype(int)
    return tabla.loc[horas_objetivo]


class ModeloAprendizaje:
    """Tres modelos de gradient boosting: percentil 10, mediana y percentil 90.

    La mediana es la previsión; los otros dos forman el intervalo del 80 %
    (se espera que el precio real caiga dentro 8 de cada 10 veces).
    Los precios son muy ruidosos, así que el modelo se regulariza fuerte (árboles
    pequeños, pocas vueltas) para que no se aprenda el ruido de memoria.
    """

    def __init__(self):
        self.modelos = {}
        self.ajuste = 0.0  # cuánto se ensancha (o estrecha) el intervalo tras calibrarlo

    def entrenar(self, serie):
        datos = crear_variables(serie, serie.index)
        usables = serie.notna() & datos["hace_1_semana"].notna()
        for nombre, cuantil in CUANTILES.items():
            modelo = HistGradientBoostingRegressor(
                loss="quantile", quantile=cuantil, max_iter=100, learning_rate=0.05,
                max_depth=4, min_samples_leaf=150, l2_regularization=5.0, random_state=0)
            self.modelos[nombre] = modelo.fit(datos[usables], serie[usables])
        return self

    def _tabla(self, historial, horas_futuras):
        datos = crear_variables(historial, horas_futuras)
        tabla = pd.DataFrame({nombre: modelo.predict(datos) for nombre, modelo in self.modelos.items()},
                             index=horas_futuras)
        # por si el percentil 10 saliera por encima de la mediana (puede pasar un poco)
        valores = np.sort(tabla[["bajo", "central", "alto"]].to_numpy(), axis=1)
        return pd.DataFrame(valores, index=horas_futuras, columns=["bajo", "central", "alto"])

    def calibrar(self, serie, desde):
        """Ajusta el intervalo con datos que el modelo NO ha visto (calibración conforme).

        Mide cuánto se sale el precio real de [bajo, alto] desde `desde` hasta el final de
        `serie`, y ensancha (o estrecha) el intervalo lo justo para que contenga al 80 %.
        """
        horas = serie.index[serie.index > desde]
        tabla = self._tabla(serie, horas)
        real = serie.reindex(horas)
        validas = real.notna()
        salida = np.maximum(tabla["bajo"] - real, real - tabla["alto"])[validas]
        nivel = min(1.0, 0.8 * (1 + 1 / len(salida)))
        self.ajuste = float(np.quantile(salida, nivel))
        return self

    def prever(self, historial, horas=168):
        """Devuelve una tabla con las columnas bajo, central y alto para las próximas horas."""
        if horas > HORAS_SEMANA:
            raise ValueError("No se puede prever más de 168 horas con este modelo.")
        primera_hora = historial.index[-1] + pd.Timedelta(hours=1)
        horas_futuras = pd.date_range(primera_hora, periods=horas, freq="h")
        tabla = self._tabla(historial, horas_futuras)
        tabla["bajo"] = np.minimum(tabla["bajo"] - self.ajuste, tabla["central"])
        tabla["alto"] = np.maximum(tabla["alto"] + self.ajuste, tabla["central"])
        return tabla

    def prever_central(self, historial, horas=168):
        """Solo la previsión central (así se puede evaluar igual que los métodos de referencia)."""
        return self.prever(historial, horas)["central"].rename("prevision_eur_mwh")


MIN_DIAS_PARA_MODELO = 400  # con menos historial no hay datos para entrenar, calibrar y examinar


def preparar_modelos(serie, dias_de_prueba=130, dias_de_calibracion=90):
    """Devuelve (modelo para el examen, modelo definitivo).

    Para que el examen sea limpio, el modelo del examen se entrena con datos de antes
    de las pruebas de evaluar() y se calibra con los 90 días siguientes. El modelo
    definitivo se entrena con todo y reutiliza esa calibración.
    """
    corte_examen = serie.index[-1] - pd.Timedelta(days=dias_de_prueba)
    corte_calibracion = corte_examen - pd.Timedelta(days=dias_de_calibracion)
    del_examen = ModeloAprendizaje().entrenar(serie.loc[:corte_calibracion])
    del_examen.calibrar(serie.loc[:corte_examen], desde=corte_calibracion)
    definitivo = ModeloAprendizaje().entrenar(serie)
    definitivo.ajuste = del_examen.ajuste
    return del_examen, definitivo


def evaluar_intervalo(serie, modelo, n_pruebas=40, cada_dias=3):
    """Mide si el intervalo del 80 % acierta: % de precios reales que caen dentro (ideal: ~80 %)."""
    dentro = []
    ultimo_origen = serie.index[-1] - pd.Timedelta(hours=168)
    for i in range(n_pruebas):
        origen = ultimo_origen - pd.Timedelta(days=cada_dias * i)
        pasado = serie.loc[:origen]
        if len(pasado) <= HORAS_SEMANA:
            continue
        prevision = modelo.prever(pasado)
        real = serie.reindex(prevision.index)
        validas = real.notna()
        dentro.extend(((real >= prevision["bajo"]) & (real <= prevision["alto"]))[validas].tolist())
    if len(dentro) == 0:
        raise ValueError("No hay historial suficiente para evaluar.")
    return 100 * float(np.mean(dentro))


# ===========================================================================
# 5. RESÚMENES PARA LOS GRÁFICOS Y PLANIFICADOR
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


def ahorro_al_ano(ahorro_por_uso, veces_por_semana):
    """Ahorro en € al año si se repite el uso `veces_por_semana` veces cada semana.

    Es una extrapolación: supone un ahorro parecido todas las semanas.
    """
    return ahorro_por_uso * veces_por_semana * 52