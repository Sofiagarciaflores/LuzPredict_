"""Planificador: busca la mejor hora para poner un electrodoméstico."""
import pandas as pd

# En 2026, el 45 % del PVPC depende del mercado diario (el 55 % restante, de
# mercados a plazo). Es una aproximación: más adelante se ajustará con datos
# reales del PVPC de Red Eléctrica.
PESO_MERCADO_DIARIO = 0.45


def coste_de_un_bloque(precios, inicio, duracion, kwh, peso):
    """Calcula el coste (en €) de usar el aparato `duracion` horas desde `inicio`.

    Se reparte el consumo a partes iguales entre las horas. Los precios están
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

    # Calculamos el coste de empezar en cada hora posible
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
