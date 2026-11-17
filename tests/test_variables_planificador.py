import pandas as pd
import pytest

from luzpredict.planificador import planificar
from luzpredict.variables import anadir_precios_pasados, variables_de_calendario

ZONA = "Europe/Madrid"


def test_no_se_permiten_retardos_menores_de_una_semana():
    horas = pd.date_range("2026-01-01", periods=500, freq="h", tz=ZONA)
    serie = pd.Series(range(500), index=horas, dtype=float)
    with pytest.raises(ValueError):
        anadir_precios_pasados(serie, retardos=(24, 168))


def test_el_precio_pasado_se_desplaza_bien():
    horas = pd.date_range("2026-01-01", periods=500, freq="h", tz=ZONA)
    serie = pd.Series(range(500), index=horas, dtype=float)
    tabla = anadir_precios_pasados(serie, retardos=(168,))
    assert tabla["precio_hace_168h"].iloc[200] == serie.iloc[200 - 168]


def test_sabado_y_domingo_son_fin_de_semana():
    horas = pd.date_range("2026-11-14", periods=48, freq="h", tz=ZONA)  # sábado y domingo
    assert variables_de_calendario(horas)["fin_de_semana"].all()


def crear_precios_de_prueba():
    # 48 horas a 100 €/MWh, con mediodía barato (13-15 h) y noche cara (20-22 h)
    horas = pd.date_range("2026-11-18 00:00", periods=48, freq="h", tz=ZONA)
    valores = [100.0] * 48
    for h in (13, 14, 15):
        valores[h] = 10.0
    for h in (20, 21, 22):
        valores[h] = 200.0
    return pd.Series(valores, index=horas)


def test_el_planificador_elige_las_horas_baratas_y_calcula_el_ahorro():
    precios = crear_precios_de_prueba()
    plan = planificar(precios, precios.index[0], precios.index[-1],
                      duracion=3, kwh=3.0, hora_referencia=21, peso=0.5)

    assert plan["mejor_inicio"].hour == 13
    assert plan["inicio_referencia"].hour == 21
    # Bloque barato: 3 horas a 10 €/MWh. Referencia: 21, 22 y 23 h -> 200, 200 y 100.
    assert plan["coste_mejor"] == pytest.approx((10 + 10 + 10) / 1000 * 0.5)
    assert plan["coste_referencia"] == pytest.approx((200 + 200 + 100) / 1000 * 0.5)
    assert plan["ahorro"] == pytest.approx(plan["coste_referencia"] - plan["coste_mejor"])


def test_ventana_demasiado_corta():
    precios = crear_precios_de_prueba()
    with pytest.raises(ValueError):
        planificar(precios, precios.index[0], precios.index[1], duracion=3, kwh=1.0)
