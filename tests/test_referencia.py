import pandas as pd
import pytest

from luzpredict.referencia import evaluar, prever_como_semana_anterior
from luzpredict.sinteticos import crear_precios_demo


def test_la_prevision_repite_la_semana_anterior():
    precios = crear_precios_demo(fin="2026-06-30 23:00", dias=60)
    prevision = prever_como_semana_anterior(precios, horas=168)
    assert len(prevision) == 168
    # Las 168 horas previstas son iguales a la última semana conocida
    assert prevision.to_numpy() == pytest.approx(precios.iloc[-168:].to_numpy())
    # y empiezan justo una hora después del último dato
    assert prevision.index[0] == precios.index[-1] + pd.Timedelta(hours=1)


def test_no_se_puede_prever_mas_de_una_semana():
    precios = crear_precios_demo(dias=30)
    with pytest.raises(ValueError):
        prever_como_semana_anterior(precios, horas=200)


def test_evaluar_da_siete_dias_con_error_positivo():
    precios = crear_precios_demo(dias=200)
    resultado = evaluar(precios, n_pruebas=10)
    assert resultado["dia"].tolist() == [1, 2, 3, 4, 5, 6, 7]
    assert (resultado["mae"] > 0).all()


def test_la_prevision_no_usa_datos_del_futuro():
    # Si cambiamos lo que pasa DESPUÉS del origen, la previsión no debe cambiar.
    precios = crear_precios_demo(fin="2026-06-30 23:00", dias=60)
    origen = precios.index[-200]
    prevision_a = prever_como_semana_anterior(precios.loc[:origen])

    precios_cambiados = precios.copy()
    precios_cambiados.loc[origen + pd.Timedelta(hours=1):] += 1000
    prevision_b = prever_como_semana_anterior(precios_cambiados.loc[:origen])

    assert prevision_a.equals(prevision_b)
