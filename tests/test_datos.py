import pandas as pd
import pytest

from luzpredict.datos import ZONA, leer_respuesta_redata, pasar_a_horario


def test_pasar_a_horario_hace_la_media_de_cada_hora():
    horas = pd.date_range("2026-03-01 00:00", periods=8, freq="15min", tz=ZONA)
    precios = pd.Series([10, 20, 30, 40, 100, 100, 100, 100], index=horas, dtype=float)
    resultado = pasar_a_horario(precios)
    assert list(resultado.values) == [25.0, 100.0]


def test_dias_de_cambio_de_hora_tienen_23_y_25_horas():
    # 29 de marzo de 2026 (se adelanta la hora: 23 h) y 25 de octubre (se atrasa: 25 h)
    for dia, horas_esperadas in [("2026-03-29", 23), ("2026-10-25", 25)]:
        cuartos = pd.date_range(dia, periods=horas_esperadas * 4, freq="15min", tz=ZONA)
        precios = pd.Series(1.0, index=cuartos)
        assert len(pasar_a_horario(precios)) == horas_esperadas


def test_pasar_a_horario_exige_zona_horaria():
    precios = pd.Series([1.0], index=pd.date_range("2026-01-01", periods=1, freq="h"))
    with pytest.raises(ValueError):
        pasar_a_horario(precios)


def test_leer_respuesta_redata_con_un_ejemplo():
    # OJO: esta forma de JSON está ASUMIDA; hay que compararla con la API real.
    ejemplo = {
        "included": [
            {
                "attributes": {
                    "title": "Precio mercado spot",
                    "values": [
                        {"value": 50.0, "datetime": "2026-11-10T00:00:00.000+01:00"},
                        {"value": 40.0, "datetime": "2026-11-10T01:00:00.000+01:00"},
                    ],
                }
            }
        ]
    }
    tabla = leer_respuesta_redata(ejemplo)
    assert tabla["Precio mercado spot"].tolist() == [50.0, 40.0]
