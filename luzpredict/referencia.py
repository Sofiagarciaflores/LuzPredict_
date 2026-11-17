"""Método de referencia: predecir que cada hora costará lo mismo que hace una semana.

Es muy simple a propósito. Nuestro modelo de aprendizaje automático tendrá que
ganarle; si no lo consigue, no merece la pena.
"""
import pandas as pd

HORAS_SEMANA = 168  # 7 días x 24 horas


def prever_como_semana_anterior(historial, horas=168):
    """Predice las próximas `horas` horas copiando los precios de hace una semana.

    Como miramos justo una semana atrás (168 h) y prevemos como mucho 168 h,
    todos los precios que copiamos ya se conocen cuando hacemos la previsión.
    """
    if horas > HORAS_SEMANA:
        raise ValueError("No se puede prever más de 168 horas con este método.")

    primera_hora = historial.index[-1] + pd.Timedelta(hours=1)
    horas_futuras = pd.date_range(primera_hora, periods=horas, freq="h")
    horas_copiadas = horas_futuras - pd.Timedelta(hours=HORAS_SEMANA)
    valores = historial.reindex(horas_copiadas).to_numpy()
    return pd.Series(valores, index=horas_futuras, name="prevision_eur_mwh")


def evaluar(serie, n_pruebas=40, cada_dias=3):
    """Mide cuánto se equivoca el método de referencia, según los días de antelación.

    Hace como si estuviéramos en el pasado: corta la serie en una fecha, prevé
    los 7 días siguientes y compara con lo que pasó de verdad. Lo repite
    n_pruebas veces y devuelve el error medio (en €/MWh) para cada día 1..7.
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
