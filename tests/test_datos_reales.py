"""Pruebas de la descarga con un "servidor falso" (no usan internet).

OJO: el JSON falso sigue la forma de la documentación oficial de REData, pero
los títulos de las series ("Precio mercado spot", "PVPC") son una suposición.
Estas pruebas comprueban NUESTRO código; no demuestran que REData responda así.
"""
import pandas as pd
import pytest
import requests

from luzpredict import datos
from luzpredict.datos import (
    COLUMNA_PVPC,
    COLUMNA_SPOT,
    ZONA,
    actualizar_csv,
    buscar_columna,
    descargar_precios,
    guardar_csv,
    leer_csv,
    limpiar_serie,
    trozos_de_fechas,
)


class RespuestaFalsa:
    """Imita la respuesta de requests.get."""

    def __init__(self, contenido):
        self.contenido = contenido

    def raise_for_status(self):
        pass

    def json(self):
        return self.contenido


def crear_json_falso(inicio, fin):
    """Crea un JSON con la forma de REData para todas las horas entre dos fechas."""
    horas = pd.date_range(inicio[:10], pd.Timestamp(fin[:10]) + pd.Timedelta(days=1), freq="h",
                          tz=ZONA, inclusive="left")
    valores_spot = [{"value": float(i % 50), "percentage": 0.5, "datetime": h.isoformat()}
                    for i, h in enumerate(horas)]
    valores_pvpc = [{"value": float(100 + i % 50), "percentage": 0.5, "datetime": h.isoformat()}
                    for i, h in enumerate(horas)]
    return {
        "data": {"type": "Precios", "id": "x", "attributes": {"title": "Precios"}},
        "included": [
            {"type": "a", "id": "1", "attributes": {"title": "Precio mercado spot", "values": valores_spot}},
            {"type": "b", "id": "2", "attributes": {"title": "PVPC", "values": valores_pvpc}},
        ],
    }


@pytest.fixture
def servidor_falso(monkeypatch):
    """Sustituye requests.get por una función que responde con datos inventados."""
    llamadas = []

    def get_falso(url, params=None, headers=None, timeout=None):
        llamadas.append(params)
        return RespuestaFalsa(crear_json_falso(params["start_date"], params["end_date"]))

    monkeypatch.setattr(datos.requests, "get", get_falso)
    monkeypatch.setattr(datos.time, "sleep", lambda segundos: None)
    return llamadas


def test_trozos_de_fechas_cubren_todo_sin_huecos_ni_solapes():
    trozos = trozos_de_fechas("2021-01-01", "2021-03-15", dias=30)
    assert trozos[0][0] == "2021-01-01"
    assert trozos[-1][1] == "2021-03-15"
    for anterior, siguiente in zip(trozos[:-1], trozos[1:]):
        dia_siguiente = pd.Timestamp(anterior[1]) + pd.Timedelta(days=1)
        assert siguiente[0] == dia_siguiente.strftime("%Y-%m-%d")
    for inicio, fin in trozos:
        assert (pd.Timestamp(fin) - pd.Timestamp(inicio)).days <= 29


def test_buscar_columna_ignora_mayusculas_y_avisa_si_no_existe():
    tabla = pd.DataFrame({"Precio mercado SPOT": [1], "PVPC": [2]})
    assert buscar_columna(tabla, "spot") == "Precio mercado SPOT"
    with pytest.raises(ValueError) as error:
        buscar_columna(tabla, "gas")
    assert "Series disponibles" in str(error.value)  # el mensaje enseña los nombres reales


def test_descargar_precios_une_los_trozos_sin_repetir_horas(servidor_falso):
    tabla = descargar_precios("2026-01-01", "2026-03-10", pausa=0)
    assert len(servidor_falso) == 3  # 69 días en trozos de 30 días = 3 peticiones
    assert list(tabla.columns) == [COLUMNA_SPOT, COLUMNA_PVPC]
    assert not tabla.index.duplicated().any()
    assert tabla.index.is_monotonic_increasing
    assert str(tabla.index.tz) == ZONA


def test_descargar_reintenta_si_falla_la_conexion(monkeypatch):
    intentos = []

    def get_que_falla_una_vez(url, params=None, headers=None, timeout=None):
        intentos.append(1)
        if len(intentos) == 1:
            raise requests.ConnectionError("sin conexión")
        return RespuestaFalsa(crear_json_falso(params["start_date"], params["end_date"]))

    monkeypatch.setattr(datos.requests, "get", get_que_falla_una_vez)
    monkeypatch.setattr(datos.time, "sleep", lambda segundos: None)
    tabla = datos.descargar_tramo("2026-01-01", "2026-01-02")
    assert len(intentos) == 2
    assert len(tabla) == 48


def test_descargar_falla_con_mensaje_claro_si_siempre_hay_error(monkeypatch):
    def get_roto(url, params=None, headers=None, timeout=None):
        raise requests.ConnectionError("sin conexión")

    monkeypatch.setattr(datos.requests, "get", get_roto)
    monkeypatch.setattr(datos.time, "sleep", lambda segundos: None)
    with pytest.raises(RuntimeError) as error:
        datos.descargar_tramo("2026-01-01", "2026-01-02")
    assert "2026-01-01" in str(error.value)


def test_cuartos_de_hora_se_convierten_a_horas(monkeypatch):
    def get_cuartos(url, params=None, headers=None, timeout=None):
        horas = pd.date_range("2026-01-01", periods=8, freq="15min", tz=ZONA)
        valores = [{"value": v, "percentage": 0, "datetime": h.isoformat()}
                   for v, h in zip([10, 20, 30, 40, 100, 100, 100, 100], horas)]
        return RespuestaFalsa({"included": [
            {"attributes": {"title": "Precio mercado spot", "values": valores}},
            {"attributes": {"title": "PVPC", "values": valores}},
        ]})

    monkeypatch.setattr(datos.requests, "get", get_cuartos)
    monkeypatch.setattr(datos.time, "sleep", lambda segundos: None)
    tabla = descargar_precios("2026-01-01", "2026-01-01", pausa=0)
    assert tabla[COLUMNA_SPOT].tolist() == [25.0, 100.0]


def test_limpiar_serie_rellena_huecos_pequenos_pero_no_grandes():
    horas = pd.date_range("2026-01-01", periods=12, freq="h", tz=ZONA)
    serie = pd.Series(range(12), index=horas, dtype=float)
    serie.iloc[2:4] = float("nan")   # hueco de 2 horas: se rellena
    serie.iloc[6:11] = float("nan")  # hueco de 5 horas: se queda vacío (límite 3)
    limpia = limpiar_serie(serie, max_hueco=3)
    assert limpia.iloc[2] == pytest.approx(2.0)
    assert limpia.iloc[3] == pytest.approx(3.0)
    assert limpia.iloc[6:9].notna().all()   # solo rellena las 3 primeras horas del hueco largo
    assert limpia.iloc[9:11].isna().all()


def test_csv_guarda_y_lee_igual_incluido_el_cambio_de_hora(tmp_path):
    horas = pd.date_range("2026-10-24 12:00", periods=72, freq="h", tz=ZONA)  # incluye 25 de octubre
    tabla = pd.DataFrame({COLUMNA_SPOT: range(72), COLUMNA_PVPC: range(100, 172)}, index=horas, dtype=float)
    ruta = tmp_path / "precios.csv"
    guardar_csv(tabla, ruta)
    leida = leer_csv(ruta)
    assert len(leida) == 72
    assert leida[COLUMNA_SPOT].tolist() == tabla[COLUMNA_SPOT].tolist()
    assert str(leida.index.tz) == ZONA
    assert (leida.index == tabla.index).all()


def test_leer_csv_devuelve_none_si_no_existe(tmp_path):
    assert leer_csv(tmp_path / "no_existe.csv") is None


def test_actualizar_csv_solo_descarga_lo_nuevo_y_no_duplica(servidor_falso, tmp_path):
    ruta = str(tmp_path / "precios.csv")

    primera = actualizar_csv(ruta, desde="2026-01-01", hasta="2026-01-31")
    peticiones_primera = len(servidor_falso)

    segunda = actualizar_csv(ruta, desde="2026-01-01", hasta="2026-02-05")
    peticiones_segunda = len(servidor_falso) - peticiones_primera

    assert not segunda.index.duplicated().any()
    assert len(segunda) > len(primera)
    assert segunda.index[-1] > primera.index[-1]
    # La segunda vez no repite todo el historial: pide muchos menos tramos que desde el principio
    assert peticiones_segunda <= 3
