"""Variables ("pistas") que se le darán al modelo de aprendizaje automático (Sprint 2)."""
import pandas as pd


def variables_de_calendario(horas):
    """Crea una tabla con la hora, el día de la semana, el mes y si es fin de semana.

    `horas` es el índice de fechas de la serie de precios.
    (Pendiente: añadir festivos.)
    """
    tabla = pd.DataFrame(index=horas)
    tabla["hora"] = horas.hour
    tabla["dia_semana"] = horas.dayofweek
    tabla["mes"] = horas.month
    tabla["fin_de_semana"] = (horas.dayofweek >= 5).astype(int)
    return tabla


def anadir_precios_pasados(serie, retardos=(168, 336)):
    """Añade columnas con el precio de hace 168 h (1 semana) y 336 h (2 semanas).

    Para prever 7 días hay que usar solo retardos de 168 horas o más: uno
    menor usaría precios que todavía no existen cuando haces la previsión
    (sería "hacer trampa" y el modelo parecería mejor de lo que es).
    """
    for retardo in retardos:
        if retardo < 168:
            raise ValueError("Con previsión a 7 días, los retardos deben ser de 168 horas o más.")

    tabla = pd.DataFrame({"precio": serie})
    for retardo in retardos:
        tabla["precio_hace_" + str(retardo) + "h"] = serie.shift(retardo)
    return tabla
