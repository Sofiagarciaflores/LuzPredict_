"""Pruebas automáticas de funciones.py. Se ejecutan con:  pytest -q

Las pruebas de descarga usan un "servidor falso" (no usan internet). OJO: el JSON
falso sigue la forma de la documentación oficial de REData, pero los títulos de las
series ("Precio mercado spot", "PVPC") son una suposición. Estas pruebas comprueban
NUESTRO código; no demuestran que REData responda exactamente así.
"""
import pandas as pd
import pytest
import requests

import funciones
from funciones import (
    COLUMNA_PVPC,
    COLUMNA_SPOT,
    ZONA,
    actualizar_csv,
    buscar_columna,
    crear_precios_demo,
    descargar_precios,
    evaluar,
    guardar_csv,
    leer_csv,
    leer_respuesta_redata,
    limpiar_serie,
    media_mensual,
    media_por_hora,
    pasar_a_horario,
    planificar,
    prever_como_semana_anterior,
    trozos_de_fechas,
)


# ---------------------------------------------------------------------------
# Servidor falso
# ---------------------------------------------------------------------------
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

    monkeypatch.setattr(funciones.requests, "get", get_falso)
    monkeypatch.setattr(funciones.time, "sleep", lambda segundos: None)
    return llamadas


# ---------------------------------------------------------------------------
# Datos: horas, limpieza y lectura de REData
# ---------------------------------------------------------------------------
def test_pasar_a_horario_hace_la_media_de_cada_hora():
    horas = pd.date_range("2026-03-01 00:00", periods=8, freq="15min", tz=ZONA)
    precios = pd.Series([10, 20, 30, 40, 100, 100, 100, 100], index=horas, dtype=float)
    assert list(pasar_a_horario(precios).values) == [25.0, 100.0]


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
    ejemplo = {"included": [{"attributes": {"title": "Precio mercado spot", "values": [
        {"value": 50.0, "datetime": "2026-11-10T00:00:00.000+01:00"},
        {"value": 40.0, "datetime": "2026-11-10T01:00:00.000+01:00"},
    ]}}]}
    assert leer_respuesta_redata(ejemplo)["Precio mercado spot"].tolist() == [50.0, 40.0]


def test_limpiar_serie_rellena_huecos_pequenos_pero_no_grandes():
    horas = pd.date_range("2026-01-01", periods=12, freq="h", tz=ZONA)
    serie = pd.Series(range(12), index=horas, dtype=float)
    serie.iloc[2:4] = float("nan")   # hueco de 2 horas: se rellena
    serie.iloc[6:11] = float("nan")  # hueco de 5 horas: solo se rellenan 3 (límite)
    limpia = limpiar_serie(serie, max_hueco=3)
    assert limpia.iloc[2] == pytest.approx(2.0)
    assert limpia.iloc[3] == pytest.approx(3.0)
    assert limpia.iloc[6:9].notna().all()
    assert limpia.iloc[9:11].isna().all()


def test_buscar_columna_ignora_mayusculas_y_avisa_si_no_existe():
    tabla = pd.DataFrame({"Precio mercado SPOT": [1], "PVPC": [2]})
    assert buscar_columna(tabla, "spot") == "Precio mercado SPOT"
    with pytest.raises(ValueError) as error:
        buscar_columna(tabla, "gas")
    assert "Series disponibles" in str(error.value)  # el mensaje enseña los nombres reales


# ---------------------------------------------------------------------------
# Descarga y CSV
# ---------------------------------------------------------------------------
def test_trozos_de_fechas_cubren_todo_sin_huecos_ni_solapes():
    trozos = trozos_de_fechas("2021-01-01", "2021-03-15", dias=30)
    assert trozos[0][0] == "2021-01-01"
    assert trozos[-1][1] == "2021-03-15"
    for anterior, siguiente in zip(trozos[:-1], trozos[1:]):
        dia_siguiente = pd.Timestamp(anterior[1]) + pd.Timedelta(days=1)
        assert siguiente[0] == dia_siguiente.strftime("%Y-%m-%d")
    for inicio, fin in trozos:
        assert (pd.Timestamp(fin) - pd.Timestamp(inicio)).days <= 29


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

    monkeypatch.setattr(funciones.requests, "get", get_que_falla_una_vez)
    monkeypatch.setattr(funciones.time, "sleep", lambda segundos: None)
    tabla = funciones.descargar_tramo("2026-01-01", "2026-01-02")
    assert len(intentos) == 2
    assert len(tabla) == 48


def test_descargar_falla_con_mensaje_claro_si_siempre_hay_error(monkeypatch):
    def get_roto(url, params=None, headers=None, timeout=None):
        raise requests.ConnectionError("sin conexión")

    monkeypatch.setattr(funciones.requests, "get", get_roto)
    monkeypatch.setattr(funciones.time, "sleep", lambda segundos: None)
    with pytest.raises(RuntimeError) as error:
        funciones.descargar_tramo("2026-01-01", "2026-01-02")
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

    monkeypatch.setattr(funciones.requests, "get", get_cuartos)
    monkeypatch.setattr(funciones.time, "sleep", lambda segundos: None)
    tabla = descargar_precios("2026-01-01", "2026-01-01", pausa=0)
    assert tabla[COLUMNA_SPOT].tolist() == [25.0, 100.0]


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
    assert peticiones_segunda <= 3  # no repite todo el historial


# ---------------------------------------------------------------------------
# Previsión
# ---------------------------------------------------------------------------
def test_la_prevision_repite_la_semana_anterior():
    precios = crear_precios_demo(fin="2026-06-30 23:00", dias=60)
    prevision = prever_como_semana_anterior(precios, horas=168)
    assert len(prevision) == 168
    assert prevision.to_numpy() == pytest.approx(precios.iloc[-168:].to_numpy())
    assert prevision.index[0] == precios.index[-1] + pd.Timedelta(hours=1)


def test_no_se_puede_prever_mas_de_una_semana():
    precios = crear_precios_demo(dias=30)
    with pytest.raises(ValueError):
        prever_como_semana_anterior(precios, horas=200)


def test_la_prevision_no_usa_datos_del_futuro():
    # Si cambiamos lo que pasa DESPUÉS del origen, la previsión no debe cambiar.
    precios = crear_precios_demo(fin="2026-06-30 23:00", dias=60)
    origen = precios.index[-200]
    prevision_a = prever_como_semana_anterior(precios.loc[:origen])

    precios_cambiados = precios.copy()
    precios_cambiados.loc[origen + pd.Timedelta(hours=1):] += 1000
    prevision_b = prever_como_semana_anterior(precios_cambiados.loc[:origen])
    assert prevision_a.equals(prevision_b)


def test_evaluar_da_siete_dias_con_error_positivo():
    precios = crear_precios_demo(dias=200)
    resultado = evaluar(precios, n_pruebas=10)
    assert resultado["dia"].tolist() == [1, 2, 3, 4, 5, 6, 7]
    assert (resultado["mae"] > 0).all()


# ---------------------------------------------------------------------------
# Resúmenes y planificador
# ---------------------------------------------------------------------------
def test_media_por_hora_devuelve_24_horas_y_acierta():
    horas = pd.date_range("2026-01-01", periods=24 * 10, freq="h", tz=ZONA)
    precios = pd.Series([float(h.hour) for h in horas], index=horas)  # el precio es la propia hora
    resultado = media_por_hora(precios, dias=5)
    assert list(resultado.index) == list(range(24))
    assert resultado.tolist() == pytest.approx(list(range(24)))


def test_media_mensual_da_una_media_por_mes():
    horas = pd.date_range("2026-01-01", "2026-03-31 23:00", freq="h", tz=ZONA)
    precios = pd.Series([10.0 if h.month == 1 else 20.0 if h.month == 2 else 30.0 for h in horas], index=horas)
    assert media_mensual(precios).tolist() == pytest.approx([10.0, 20.0, 30.0])


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


# ---------------------------------------------------------------------------
# La web
# ---------------------------------------------------------------------------
def test_la_web_se_crea_y_el_panel_se_calcula():
    import app  # sin data/precios.csv usa datos de demostración

    assert app.crear_layout() is not None
    tarjetas, linea, barras, mapa = app.actualizar_panel(7, 90)
    assert len(tarjetas) == 4
    assert len(linea.data) == 2          # precio publicado y precio previsto
    assert len(barras.data[0].x) == 24   # una barra por hora del día


def test_el_planificador_de_la_web_responde():
    import app

    _, proximos = app.precios_proximos()
    dia = sorted(set(fecha.date() for fecha in proximos.index))[2].isoformat()
    texto, figura = app.actualizar_plan(2, 1.0, dia, 8, 0.45)
    assert len(figura.data) == 1
    assert "mejor" in str(texto).lower()
