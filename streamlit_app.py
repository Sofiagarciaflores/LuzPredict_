"""LuzPredict: previsión a 7 días del precio de la luz y planificador de consumo.

Usa los precios reales de Red Eléctrica guardados en data/precios.csv (se crean
con `python actualizar_datos.py`). Si ese archivo no existe, usa datos de
demostración y lo avisa. La previsión es, por ahora, el método de referencia
(misma hora de la semana anterior); el modelo LightGBM llega en el Sprint 2.

Para ejecutarla:  streamlit run streamlit_app.py
"""
import base64
from datetime import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from luzpredict.datos import COLUMNA_SPOT, ZONA, leer_csv, limpiar_serie
from luzpredict.planificador import PESO_MERCADO_DIARIO, planificar
from luzpredict.referencia import evaluar, prever_como_semana_anterior
from luzpredict.sinteticos import crear_precios_demo

st.set_page_config(page_title="LuzPredict", layout="wide")

# Carpeta donde está este archivo (para encontrar las imágenes)
CARPETA = Path(__file__).parent
RUTA_DATOS = CARPETA / "data" / "precios.csv"

# Colores
VERDE = "#1b7f5c"
AMBAR = "#d97706"
AZUL = "#0b2545"
ROJO = "#c0392b"
GRIS = "#6b7785"
CUADRICULA = "#dfe5ec"

# Electrodomésticos: nombre -> (duración en horas, consumo total en kWh)
ELECTRODOMESTICOS = {
    "Lavadora": (2, 1.0),
    "Lavavajillas": (2, 1.2),
    "Coche eléctrico (carga de 30 kWh)": (8, 30.0),
    "Termo eléctrico": (3, 3.0),
}

NOMBRES_DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

# Estilo extra: los números grandes usan la fuente de los títulos
st.markdown(
    """
<style>
[data-testid="stMetricValue"] { font-family: "Fraunces", serif; font-weight: 600; }
.block-container { padding-top: 2rem; }
div.cabecera { background-size: cover; background-position: center; border-radius: 6px;
               padding: 2.8rem 3rem; margin-bottom: 1.2rem; }
div.cabecera h1 { font-family: "Fraunces", serif; font-weight: 700; font-size: 3.2rem;
                  color: #ffffff; margin: 0 0 0.6rem 0; padding: 0; }
div.cabecera p { color: #dbe6f3; font-size: 1.15rem; max-width: 620px; margin: 0; line-height: 1.5; }
[data-testid="stAlert"] { background-color: #fff4e0; border-left: 4px solid #d97706; border-radius: 4px; }
[data-testid="stAlert"] * { color: #5a3a00; }
</style>
    """,
    unsafe_allow_html=True,
)


def escribir_dia(fecha):
    """Convierte una fecha en texto, por ejemplo 'mié 18/11'."""
    return NOMBRES_DIAS[fecha.dayofweek] + " " + fecha.strftime("%d/%m")


def escribir_euros(valor):
    """Escribe un número como euros con 2 decimales (evita que salga '-0.00')."""
    valor = round(valor, 2) + 0.0
    return str(format(valor, ".2f")) + " €"


def dar_estilo(figura):
    """Aplica a un gráfico la misma fuente, fondo transparente y márgenes."""
    figura.update_layout(
        font=dict(family="DM Sans, sans-serif", color=AZUL, size=14),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    figura.update_xaxes(gridcolor=CUADRICULA, zerolinecolor=CUADRICULA)
    figura.update_yaxes(gridcolor=CUADRICULA, zerolinecolor=CUADRICULA)
    return figura


# st.cache_data hace que los cálculos pesados no se repitan en cada clic
@st.cache_data(ttl=3600)
def cargar_datos():
    """Lee los precios reales (data/precios.csv). Si no existen, usa datos de demostración."""
    tabla = leer_csv(RUTA_DATOS)
    if tabla is not None and len(tabla) > 24 * 30:
        historial = limpiar_serie(tabla[COLUMNA_SPOT].dropna())
        origen = "real"
    else:
        historial = crear_precios_demo(dias=730)
        origen = "demo"
    prevision = prever_como_semana_anterior(historial, horas=168)
    return historial, prevision, origen


@st.cache_data(ttl=3600)
def calcular_calidad(historial):
    return evaluar(historial, n_pruebas=40)


historial, prevision, origen = cargar_datos()

# Precios de las próximas horas = los ya publicados (mañana, si ya se conocen) + la previsión
ahora = pd.Timestamp.now(tz=ZONA).floor("h")
publicados = historial.loc[historial.index > ahora]
proximos = pd.concat([publicados, prevision])
proximos = proximos.loc[proximos.index > ahora]

# ---------- Cabecera: foto de paneles solares con el título encima ----------
def foto_en_base64(ruta):
    """Lee una imagen y la convierte en texto para poder incrustarla en el HTML."""
    with open(ruta, "rb") as archivo:
        return base64.b64encode(archivo.read()).decode()


foto = foto_en_base64(CARPETA / "assets" / "hero_paneles.jpg")
degradado = "linear-gradient(90deg, rgba(8,26,51,0.94) 0%, rgba(8,26,51,0.80) 42%, rgba(8,26,51,0.10) 100%)"
st.markdown(
    '<div class="cabecera" style="background-image: ' + degradado + ", url('data:image/jpeg;base64," + foto + "');\">"
    "<h1>LuzPredict</h1>"
    "<p>Previsión a 7 días del precio de la luz y planificador de consumo para el hogar. "
    "Descubre las horas más baratas de la semana y cuánto puedes ahorrar.</p>"
    "</div>",
    unsafe_allow_html=True,
)

if origen == "demo":
    st.warning(
        "Versión de desarrollo: los precios son **datos de demostración** (inventados), "
        "no precios reales de mercado."
    )
else:
    ultimo = historial.index[-1]
    st.caption("Datos reales: Red Eléctrica de España (REData). Último precio disponible: "
               + escribir_dia(ultimo) + " a las " + ultimo.strftime("%H:%M") + ".")
    if ahora - ultimo > pd.Timedelta(days=3):
        st.warning("Los datos llevan más de 3 días sin actualizarse. "
                   "Ejecuta `python actualizar_datos.py` o la acción «Actualizar datos» de GitHub.")

if len(proximos) == 0:
    st.error("Los datos están demasiado desactualizados para hacer una previsión. "
             "Ejecuta `python actualizar_datos.py`.")
    st.stop()

pestana_linea, pestana_mapa, pestana_plan, pestana_calidad = st.tabs(
    ["Previsión", "Mapa de colores", "Planificador", "Calidad del modelo"]
)

# ---------- Pestaña 1: gráfico de línea ----------
with pestana_linea:
    ultima_semana = historial.iloc[-168:]

    grafico = go.Figure()
    grafico.add_trace(go.Scatter(x=ultima_semana.index, y=ultima_semana,
                                 name="Precio ya publicado", line=dict(color=AZUL, width=2.5)))
    grafico.add_trace(go.Scatter(x=prevision.index, y=prevision,
                                 name="Precio previsto", line=dict(color=AMBAR, width=2.5, dash="dot")))
    # Línea vertical que separa el pasado del futuro
    grafico.add_shape(type="line", x0=prevision.index[0], x1=prevision.index[0],
                      y0=0, y1=1, yref="paper", line=dict(color=GRIS, dash="dash"))
    grafico.update_layout(yaxis_title="€/MWh (mercado mayorista)", hovermode="x unified",
                          legend=dict(orientation="h"))
    grafico.update_xaxes(tickformat="%d/%m")  # fechas como 18/11 (los meses de plotly salen en inglés)
    st.plotly_chart(dar_estilo(grafico), width="stretch")
    st.caption("La línea discontinua marca dónde empieza la previsión. "
               "Pendiente: rango de predicción al 80 % (modelo LightGBM).")

# ---------- Pestaña 2: mapa de colores ----------
with pestana_mapa:
    tabla = proximos.rename("precio").to_frame()
    tabla["dia"] = [escribir_dia(fecha) for fecha in tabla.index]
    tabla["hora"] = tabla.index.hour
    # Una fila por día y una columna por hora
    cuadricula = tabla.pivot_table(index="dia", columns="hora", values="precio", sort=False)
    cuadricula = cuadricula.sort_index(axis=1)  # columnas ordenadas: hora 0, 1, 2 ... 23

    mapa = go.Figure(go.Heatmap(
        z=cuadricula.values.tolist(),
        x=[int(hora) for hora in cuadricula.columns],
        y=list(cuadricula.index),
        colorscale=[[0, VERDE], [0.5, "#f2c14e"], [1, ROJO]],
        colorbar=dict(title="€/MWh"),
        hovertemplate="%{y} %{x}:00 → %{z:.0f} €/MWh<extra></extra>",
    ))
    mapa.update_layout(xaxis_title="Hora del día", yaxis=dict(autorange="reversed"))
    st.plotly_chart(dar_estilo(mapa), width="stretch")
    st.caption("Verde: horas baratas · Rojo: horas caras.")

# ---------- Pestaña 3: planificador ----------
with pestana_plan:
    columna_izq, columna_der = st.columns([1, 2])

    with columna_izq:
        nombre = st.selectbox("Electrodoméstico", list(ELECTRODOMESTICOS))
        duracion_normal, consumo_normal = ELECTRODOMESTICOS[nombre]
        duracion = st.number_input("Duración (horas)", 1, 24, duracion_normal)
        consumo = st.number_input("Consumo total (kWh)", 0.1, 100.0, float(consumo_normal))

        # Días disponibles en la previsión (sin repetir y ordenados)
        dias = sorted(set(fecha.date() for fecha in proximos.index))
        limite_dia = st.selectbox("Lo necesito antes de…", dias[1:], index=min(2, len(dias) - 2),
                                  format_func=lambda dia: escribir_dia(pd.Timestamp(dia)))
        limite_hora = st.time_input("A las", time(8, 0))
        peso = st.slider("Peso del mercado diario en tu PVPC", 0.0, 1.0, PESO_MERCADO_DIARIO, 0.05,
                         help="En 2026 el 45 % del PVPC depende del mercado diario; el resto, de mercados a plazo.")

    with columna_der:
        limite = pd.Timestamp.combine(limite_dia, limite_hora).tz_localize(proximos.index.tz)
        try:
            plan = planificar(proximos, proximos.index[0], limite - pd.Timedelta(hours=1),
                              int(duracion), float(consumo), peso=peso)
            mejor = plan["mejor_inicio"]
            st.metric("Mejor momento para empezar", escribir_dia(mejor) + " a las " + mejor.strftime("%H:%M"))
            col1, col2 = st.columns(2)
            col1.metric("Ahorro estimado", escribir_euros(plan["ahorro"]),
                        help="Frente a empezar a las 21:00. Solo cuenta la parte del PVPC ligada al mercado diario.")
            col2.metric("Coste de la energía (parte de mercado)", escribir_euros(plan["coste_mejor"]))
            st.caption("Estimación orientativa: no incluye peajes por periodo, cargos ni impuestos.")
        except ValueError as error:
            st.error(str(error))
        st.image(str(CARPETA / "assets" / "ahorro.svg"), width=320)

# ---------- Pestaña 4: calidad del modelo ----------
with pestana_calidad:
    calidad = calcular_calidad(historial)
    barras = go.Figure(go.Bar(x=calidad["dia"], y=calidad["mae"], marker_color=AZUL))
    barras.update_layout(xaxis_title="Días de antelación", yaxis_title="Error medio absoluto (€/MWh)")
    st.plotly_chart(dar_estilo(barras), width="stretch")
    st.caption("Error del método de referencia (misma hora de la semana anterior) en 40 previsiones de los últimos 4 meses. "
               "El modelo LightGBM tendrá que superar estas barras.")
