"""Datos de DEMOSTRACIÓN: precios inventados que imitan el patrón real.

NO son precios reales. Sirven para desarrollar la web mientras no tenemos
los datos de verdad. Patrón: barato al mediodía (sol), caro por la noche,
más barato en fin de semana y con algo de ruido aleatorio.
"""
import numpy as np
import pandas as pd

ZONA = "Europe/Madrid"


def crear_precios_demo(dias=730, fin=None, semilla=0):
    """Devuelve una serie de pandas con un precio por hora, en €/MWh."""
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

    # Más caro en invierno y más barato en verano
    estacion = 1 + 0.35 * np.cos(2 * np.pi * (dia_del_anio - 15) / 365)
    # Bajada del mediodía por la energía solar
    bajada_solar = -70 * np.exp(-((hora_del_dia - 14) ** 2) / 18)
    # Subida de la noche
    subida_noche = 55 * np.exp(-((hora_del_dia - 21) ** 2) / 6)
    # Fin de semana más barato
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
