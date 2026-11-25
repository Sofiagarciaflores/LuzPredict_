"""LuzPredict: panel con la previsión a 7 días del precio de la luz y planificador de consumo.

Hecho con Dash (Plotly). Lee los precios reales de data/precios.csv (se crea con
`python actualizar_datos.py`). Si ese archivo no existe, usa datos de demostración
y lo avisa.

Para ejecutarla en tu ordenador:  python app.py   (web en http://localhost:8050)
En Render se arranca con:         gunicorn app:server
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

from funciones import (
    COLUMNA_SPOT,
    METODOS_DE_REFERENCIA,
    MIN_DIAS_PARA_MODELO,
    NOMBRE_MODELO,
    PESO_MERCADO_DIARIO,
    ZONA,
    ahorro_al_ano,
    crear_precios_demo,
    evaluar,
    evaluar_intervalo,
    leer_csv,
    limpiar_serie,
    media_mensual,
    media_por_hora,
    planificar,
    preparar_modelos,
)

CARPETA = Path(__file__).parent

# Colores
VERDE = "#1b7f5c"
AMBAR = "#d97706"
AZUL = "#0b2545"
AZUL_CLARO = "#0b5cab"
ROJO = "#c0392b"
GRIS = "#6b7785"

# Electrodomésticos: nombre -> (duración en horas, consumo total en kWh)
ELECTRODOMESTICOS = {
    "Lavadora": (2, 1.0),
    "Lavavajillas": (2, 1.2),
    "Coche eléctrico (carga de 30 kWh)": (8, 30.0),
    "Termo eléctrico": (3, 3.0),
}

NOMBRES_DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

# Unidades de precio: clave -> (texto, factor para pasar de €/MWh, decimales)
UNIDADES = {"kwh": ("c€/kWh", 0.1, 1), "mwh": ("€/MWh", 1.0, 0)}


# ---------------------------------------------------------------------------
# Datos (se cargan una vez al arrancar el servidor)
# ---------------------------------------------------------------------------
def cargar_datos():
    """Lee los precios reales (data/precios.csv). Si no existen, usa datos de demostración.

    Devuelve (historial, origen), con origen "real" o "demo".
    """
    tabla = leer_csv(CARPETA / "data" / "precios.csv")
    if tabla is not None and len(tabla) > 24 * 30:
        historial = limpiar_serie(tabla[COLUMNA_SPOT].dropna())
        origen = "real"
    else:
        historial = crear_precios_demo(dias=730)
        origen = "demo"
    return historial, origen


historial, origen = cargar_datos()

# Probamos en el pasado los métodos sencillos y el modelo de aprendizaje automático
calidades = {nombre: evaluar(historial, n_pruebas=40, metodo=metodo)
             for nombre, metodo in METODOS_DE_REFERENCIA.items()}
modelo_final = None
cobertura = None  # % de precios reales que caen dentro del intervalo del 80 %
if len(historial) >= 24 * MIN_DIAS_PARA_MODELO:
    modelo_examen, modelo_final = preparar_modelos(historial)
    calidades[NOMBRE_MODELO] = evaluar(historial, n_pruebas=40, metodo=modelo_examen.prever_central)
    cobertura = evaluar_intervalo(historial, modelo_examen)

# Usamos el que menos se equivoca (el modelo solo si de verdad gana a los sencillos)
metodo_elegido = min(calidades, key=lambda nombre: calidades[nombre]["mae"].mean())
usa_modelo = metodo_elegido == NOMBRE_MODELO
if usa_modelo:
    banda = modelo_final.prever(historial, horas=168)  # columnas bajo, central, alto
    prevision = banda["central"].rename("prevision_eur_mwh")
else:
    banda = None
    prevision = METODOS_DE_REFERENCIA[metodo_elegido](historial, horas=168)
calidad = calidades[metodo_elegido]


def precios_proximos():
    """Devuelve la hora actual y los precios de las próximas horas.

    Son los ya publicados (mañana, si ya se conocen) más la previsión.
    Se calcula cada vez porque "ahora" cambia.
    """
    ahora = pd.Timestamp.now(tz=ZONA).floor("h")
    proximos = pd.concat([historial.loc[historial.index > ahora], prevision])
    return ahora, proximos.loc[proximos.index > ahora]


# ---------------------------------------------------------------------------
# Funciones pequeñas de ayuda
# ---------------------------------------------------------------------------
def escribir_dia(fecha):
    """Convierte una fecha en texto, por ejemplo 'mié 18/11'."""
    return NOMBRES_DIAS[fecha.day_of_week] + " " + fecha.strftime("%d/%m")


def escribir_numero(valor, decimales):
    """Escribe un número con coma decimal, como en España (evita que salga '-0,0')."""
    valor = round(valor, decimales) + 0.0
    return format(valor, "." + str(decimales) + "f").replace(".", ",")


def escribir_dinero(euros):
    """Euros si llega a 1 €; si no, céntimos (0,04 € se lee mejor como '4,0 cént.')."""
    if abs(euros) >= 1:
        return escribir_numero(euros, 2) + " €"
    return escribir_numero(euros * 100, 1) + " cént."


def escribir_precio(valor_mwh, unidad):
    """Escribe un precio (que viene en €/MWh) en la unidad elegida."""
    texto, factor, decimales = UNIDADES[unidad]
    return escribir_numero(valor_mwh * factor, decimales) + " " + texto


def dar_estilo(figura, alto=330):
    """Fondo transparente, colores y márgenes iguales en todos los gráficos."""
    figura.update_layout(
        font=dict(color=AZUL, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h"),
        separators=",.",  # coma decimal en los gráficos
        height=alto,
    )
    figura.update_xaxes(gridcolor="#dfe5ec", zerolinecolor="#dfe5ec")
    figura.update_yaxes(gridcolor="#dfe5ec", zerolinecolor="#dfe5ec")
    return figura


def tarjeta(titulo, valor, detalle=None, color=None):
    """Una tarjeta con un número grande (para los datos clave)."""
    estilo = {"fontSize": "1.3rem", "lineHeight": "1.3"} if len(valor) > 18 else None  # textos largos, más pequeños
    contenido = [html.Div(titulo, className="tarjeta-titulo"), html.Div(valor, className="tarjeta-valor", style=estilo)]
    if detalle:
        contenido.append(html.Div(detalle, className="tarjeta-detalle", style={"color": color or GRIS}))
    return html.Div(contenido, className="tarjeta")


def caja_grafico(titulo, id_grafico, nota=None, figura=None):
    """Un gráfico dentro de una caja con título (y una nota opcional debajo)."""
    contenido = [
        html.H4(titulo),
        dcc.Graph(id=id_grafico, figure=figura if figura is not None else go.Figure(),
                  config={"displayModeBar": False}),
    ]
    if nota:
        contenido.append(html.P(nota, className="nota"))
    return html.Div(contenido, className="caja")


# ---------------------------------------------------------------------------
# Gráficos que no dependen de los filtros
# ---------------------------------------------------------------------------
def grafico_mensual(unidad):
    texto, factor, _ = UNIDADES[unidad]
    mensual = media_mensual(historial)
    figura = go.Figure(go.Scatter(x=mensual.index, y=mensual.values * factor, mode="lines+markers",
                                  line=dict(color=AZUL_CLARO, width=2.5)))
    figura.update_layout(yaxis_title=texto)
    figura.update_xaxes(tickformat="%m/%Y")
    return dar_estilo(figura)


def grafico_calidad():
    figura = go.Figure()
    for (nombre, tabla), color in zip(calidades.items(), [AZUL, AMBAR, VERDE]):
        etiqueta = nombre + (" (en uso)" if nombre == metodo_elegido else "")
        figura.add_trace(go.Bar(x=tabla["dia"], y=tabla["mae"], name=etiqueta, marker_color=color))
    figura.update_layout(barmode="group", xaxis_title="Días de antelación",
                         yaxis_title="Error medio absoluto (€/MWh)")
    dar_estilo(figura, alto=340)
    figura.update_layout(legend=dict(orientation="h", y=1.12, x=0), margin=dict(l=10, r=10, t=50, b=10))
    return figura


# ---------------------------------------------------------------------------
# Diseño de la página
# ---------------------------------------------------------------------------
def aviso_de_datos(ahora):
    """Mensaje bajo la cabecera: de dónde vienen los datos y si están desactualizados."""
    if origen == "demo":
        return html.Div("Versión de desarrollo: los precios son datos de demostración (inventados), "
                        "no precios reales de mercado.", className="aviso")
    ultimo = historial.index[-1]
    mensajes = [html.P("Datos reales: Red Eléctrica de España (REData). Último precio disponible: "
                       + escribir_dia(ultimo) + " a las " + ultimo.strftime("%H:%M") + ".", className="nota")]
    if ahora - ultimo > pd.Timedelta(days=3):
        mensajes.append(html.Div("Los datos llevan más de 3 días sin actualizarse. Ejecuta "
                                 "python actualizar_datos.py o la acción de GitHub.", className="aviso"))
    return html.Div(mensajes)


def texto_prevision():
    """Frase bajo el gráfico de previsión: qué método se usa."""
    if usa_modelo:
        return ("Previsión de un modelo de aprendizaje automático (gradient boosting). La banda es el intervalo "
                "del 80 %: el precio real debería caer dentro unas 8 de cada 10 veces.")
    return ("Previsión con el método sencillo «" + metodo_elegido.lower() + "». "
            + texto_estado_del_modelo())


def texto_estado_del_modelo():
    if modelo_final is None:
        return "El modelo de aprendizaje automático necesita más historial de precios."
    return "El modelo de aprendizaje automático no mejora a los métodos sencillos con los datos actuales."


def pestana_panel():
    return [
        html.Div([
            html.Div([html.Label("Días de previsión"),
                      dcc.Slider(min=1, max=7, step=1, value=7, marks={i: str(i) for i in range(1, 8)}, id="dias-prevision")]),
            html.Div([html.Label("Histórico para las medias (días)"),
                      dcc.Dropdown(options=[30, 90, 180, 365], value=90, clearable=False, id="dias-historico")]),
            html.Div([html.Label("Unidad de precio"),
                      dcc.RadioItems(options=[{"label": "c€/kWh (hogar)", "value": "kwh"},
                                              {"label": "€/MWh (mercado)", "value": "mwh"}],
                                     value="kwh", id="unidad")]),
        ], className="filtros"),
        html.Div(id="tarjetas", className="fila-tarjetas"),
        html.Div([caja_grafico("Precio publicado y previsión", "g-prevision",
texto_prevision()),
                  caja_grafico("Horas más baratas del día", "g-horas",
                               "Media histórica por hora. En verde, las 6 más baratas.")],
                 className="rejilla"),
        html.Div([caja_grafico("Mapa de colores: cuándo es más barata la luz", "g-mapa",
                               "Verde: horas baratas · Rojo: horas caras."),
                  caja_grafico("Evolución del precio medio mensual", "g-mensual",
                               "Cada punto es la media de un mes.")],
                 className="rejilla"),
    ]


def pestana_planificador(proximos):
    dias = sorted(set(fecha.date() for fecha in proximos.index))
    opciones_dia = [{"label": escribir_dia(pd.Timestamp(dia)), "value": dia.isoformat()} for dia in dias[1:]]
    dia_por_defecto = opciones_dia[min(2, len(opciones_dia) - 1)]["value"] if opciones_dia else None
    duracion_normal, consumo_normal = ELECTRODOMESTICOS["Lavadora"]
    return [html.Div([
        html.Div([
            html.Label("Electrodoméstico"),
            dcc.Dropdown(options=list(ELECTRODOMESTICOS), value="Lavadora", clearable=False, id="aparato"),
            html.Label("Duración (horas)"),
            dcc.Input(type="number", min=1, max=24, step=1, value=duracion_normal, id="duracion"),
            html.Label("Consumo total (kWh)"),
            dcc.Input(type="number", min=0.1, max=100, step=0.1, value=consumo_normal, id="consumo"),
            html.Label("Veces que lo uso por semana"),
            dcc.Input(type="number", min=1, max=14, step=1, value=3, id="veces"),
            html.Label("Lo necesito antes de…"),
            dcc.Dropdown(options=opciones_dia, value=dia_por_defecto, clearable=False, id="dia-limite"),
            html.Label("A las"),
            dcc.Dropdown(options=[{"label": format(h, "02d") + ":00", "value": h} for h in range(24)],
                         value=8, clearable=False, id="hora-limite"),
            html.Label("Peso del mercado diario en tu PVPC (en 2026, el 45 %)"),
            dcc.Slider(min=0, max=1, step=0.05, value=PESO_MERCADO_DIARIO, marks={0: "0", 0.5: "0,5", 1: "1"},
                       tooltip={"placement": "bottom"}, id="peso"),
        ], className="formulario"),
        html.Div([html.Div(id="plan-texto"),
                  html.Div([dcc.Graph(id="g-plan", figure=go.Figure(), config={"displayModeBar": False}),
                            html.P("La franja verde es el mejor momento para poner el aparato. "
                                   "Estimación orientativa: no incluye peajes por periodo, cargos ni impuestos. "
                                   "El ahorro anual supone el mismo ahorro todas las semanas.",
                                   className="nota")], className="caja")]),
    ], className="columnas-planificador")]


def pestana_calidad():
    primero, ultimo = calidad.iloc[0], calidad.iloc[-1]
    tarjetas = [tarjeta("Error medio a 1 día", escribir_numero(primero["mae"], 1) + " €/MWh",
                        escribir_numero(primero["pct"], 0) + " % del precio medio"),
                tarjeta("Error medio a 7 días", escribir_numero(ultimo["mae"], 1) + " €/MWh",
                        escribir_numero(ultimo["pct"], 0) + " % del precio medio"),
                tarjeta("Método en uso", metodo_elegido)]
    if cobertura is not None:
        tarjetas.append(tarjeta("Intervalo del 80 % del modelo", escribir_numero(cobertura, 0) + " % de aciertos",
                                "ideal: cerca del 80 %"))
    clase = "fila-tarjetas" if len(tarjetas) == 4 else "fila-tarjetas tres"
    return [
        html.Div(tarjetas, className=clase),
        html.Div([dcc.Graph(figure=grafico_calidad(), config={"displayModeBar": False}),
                  html.P("Error de cada método en 40 previsiones de los últimos 4 meses. El modelo de aprendizaje "
                         "automático se entrena solo con datos anteriores a esas fechas, así que no hace trampas. "
                         "La web usa el que menos se equivoca.", className="nota")], className="caja"),
    ]


def crear_layout():
    """Construye la página. Dash la llama cada vez que se abre la web (así 'ahora' está al día)."""
    ahora, proximos = precios_proximos()
    cabecera = html.Div([
        html.H1("LuzPredict"),
        html.P("Previsión a 7 días del precio de la luz y planificador de consumo para el hogar. "
               "Descubre las horas más baratas de la semana y cuánto puedes ahorrar."),
    ], className="cabecera")

    if len(proximos.dropna()) == 0:
        return html.Div([cabecera, aviso_de_datos(ahora),
                         html.Div("Los datos están demasiado desactualizados para hacer una previsión. "
                                  "Ejecuta python actualizar_datos.py.", className="aviso")], className="pagina")

    return html.Div([
        cabecera,
        aviso_de_datos(ahora),
        dcc.Tabs([
            dcc.Tab(label="Panel", children=pestana_panel()),
            dcc.Tab(label="Planificador", children=pestana_planificador(proximos)),
            dcc.Tab(label="Calidad de la previsión", children=pestana_calidad()),
        ]),
        html.P("La previsión actual usa «" + metodo_elegido.lower() + "», el método de menor error en las "
               "pruebas." + ("" if usa_modelo else " " + texto_estado_del_modelo()), className="nota"),
    ], className="pagina")


app = Dash(__name__, title="LuzPredict")
server = app.server  # gunicorn usa esta variable en Render
app.layout = crear_layout


# ---------------------------------------------------------------------------
# Interacción: qué se actualiza cuando el usuario toca un filtro
# ---------------------------------------------------------------------------
@app.callback(
    Output("tarjetas", "children"),
    Output("g-prevision", "figure"),
    Output("g-horas", "figure"),
    Output("g-mapa", "figure"),
    Output("g-mensual", "figure"),
    Input("dias-prevision", "value"),
    Input("dias-historico", "value"),
    Input("unidad", "value"),
)
def actualizar_panel(dias_prevision, dias_historico, unidad):
    texto_unidad, factor, decimales = UNIDADES[unidad]
    _, proximos = precios_proximos()
    previstos = proximos.iloc[: dias_prevision * 24]
    proximas_24 = proximos.iloc[:24].dropna()
    media_24 = proximas_24.mean()
    cambio = (media_24 / historial.iloc[-720:].mean() - 1) * 100

    tarjetas = [
        tarjeta("Precio próxima hora", escribir_precio(proximos.dropna().iloc[0], unidad)),
        tarjeta("Hora más barata (24 h)", proximas_24.idxmin().strftime("%H:%M"),
                escribir_precio(proximas_24.min(), unidad), VERDE),
        tarjeta("Hora más cara (24 h)", proximas_24.idxmax().strftime("%H:%M"),
                escribir_precio(proximas_24.max(), unidad), ROJO),
        tarjeta("Media de las próximas 24 h", escribir_precio(media_24, unidad),
                format(cambio, "+.0f") + " % vs últimos 30 días", ROJO if cambio > 0 else VERDE),
    ]

    # Línea: lo ya publicado (última semana) y lo previsto
    ultima_semana = historial.iloc[-168:]
    linea = go.Figure()
    linea.add_trace(go.Scatter(x=ultima_semana.index, y=ultima_semana * factor, name="Precio ya publicado",
                               line=dict(color=AZUL, width=2.5)))
    if banda is not None:  # intervalo del 80 % (solo con el modelo de aprendizaje automático)
        franja = banda.reindex(previstos.index).dropna()
        linea.add_trace(go.Scatter(x=franja.index, y=franja["alto"] * factor, line=dict(width=0),
                                   showlegend=False, hoverinfo="skip"))
        linea.add_trace(go.Scatter(x=franja.index, y=franja["bajo"] * factor, fill="tonexty",
                                   fillcolor="rgba(217,119,6,0.18)", line=dict(width=0),
                                   name="Intervalo del 80 %", hoverinfo="skip"))
    linea.add_trace(go.Scatter(x=previstos.index, y=previstos * factor, name="Previsión",
                               line=dict(color=AMBAR, width=2.5, dash="dot")))
    linea.add_shape(type="line", x0=previstos.index[0], x1=previstos.index[0],
                    y0=0, y1=1, yref="paper", line=dict(color=GRIS, dash="dash"))
    linea.update_layout(yaxis_title=texto_unidad, hovermode="x unified")
    linea.update_xaxes(tickformat="%d/%m")

    # Barras: precio medio de cada hora del día
    por_hora = media_por_hora(historial, dias_historico)
    baratas = por_hora.nsmallest(6).index
    colores = [VERDE if hora in baratas else AZUL_CLARO for hora in por_hora.index]
    barras = go.Figure(go.Bar(x=list(por_hora.index), y=por_hora.values * factor, marker_color=colores))
    barras.update_layout(xaxis_title="Hora del día", yaxis_title=texto_unidad)

    # Mapa de colores: una fila por día y una columna por hora
    tabla = (previstos * factor).rename("precio").to_frame()
    tabla["dia"] = [escribir_dia(fecha) for fecha in tabla.index]
    tabla["hora"] = tabla.index.hour
    cuadricula = tabla.pivot_table(index="dia", columns="hora", values="precio", sort=False)
    cuadricula = cuadricula.sort_index(axis=1)  # columnas ordenadas: hora 0, 1, 2 ... 23
    mapa = go.Figure(go.Heatmap(
        z=cuadricula.values.tolist(),
        x=[int(hora) for hora in cuadricula.columns],
        y=list(cuadricula.index),
        colorscale=[[0, VERDE], [0.5, "#f2c14e"], [1, ROJO]],
        colorbar=dict(title=texto_unidad),
        hovertemplate="%{y} %{x}:00 → %{z:." + str(decimales) + "f} " + texto_unidad + "<extra></extra>",
    ))
    mapa.update_layout(xaxis_title="Hora del día", yaxis=dict(autorange="reversed"))

    return tarjetas, dar_estilo(linea), dar_estilo(barras), dar_estilo(mapa), grafico_mensual(unidad)


@app.callback(Output("duracion", "value"), Output("consumo", "value"), Input("aparato", "value"))
def rellenar_aparato(aparato):
    """Al elegir un electrodoméstico, se rellenan su duración y su consumo habituales."""
    duracion, consumo = ELECTRODOMESTICOS[aparato]
    return duracion, consumo


@app.callback(
    Output("plan-texto", "children"),
    Output("g-plan", "figure"),
    Input("duracion", "value"),
    Input("consumo", "value"),
    Input("dia-limite", "value"),
    Input("hora-limite", "value"),
    Input("peso", "value"),
    Input("veces", "value"),
)
def actualizar_plan(duracion, consumo, dia_limite, hora_limite, peso, veces):
    if not duracion or not consumo or not veces or dia_limite is None or hora_limite is None:
        return html.Div("Rellena todos los campos.", className="aviso"), go.Figure()

    _, proximos = precios_proximos()
    limite = pd.Timestamp(dia_limite).tz_localize(ZONA) + pd.Timedelta(hours=int(hora_limite))
    try:
        plan = planificar(proximos, proximos.index[0], limite - pd.Timedelta(hours=1),
                          int(duracion), float(consumo), peso=peso)
    except ValueError as error:
        return html.Div(str(error), className="aviso"), go.Figure()

    mejor = plan["mejor_inicio"]
    texto = html.Div([
        html.Div("Mejor momento para empezar", className="tarjeta-titulo"),
        html.Div(escribir_dia(mejor) + " a las " + mejor.strftime("%H:%M"), className="momento"),
        html.Div([tarjeta("Coste de la energía (parte de mercado)", escribir_dinero(plan["coste_mejor"])),
                  tarjeta("Ahorro por uso (frente a las 21:00)", escribir_dinero(plan["ahorro"])),
                  tarjeta("Ahorro al año (" + str(int(veces)) + " veces por semana)",
                          escribir_dinero(ahorro_al_ano(plan["ahorro"], int(veces))), color=None)],
                 className="fila-tarjetas tres"),
    ])

    ventana = proximos.loc[:limite]
    figura = go.Figure(go.Scatter(x=ventana.index, y=ventana * 0.1, line=dict(color=AZUL, width=2.5), name="Precio"))
    figura.add_vrect(x0=mejor, x1=mejor + pd.Timedelta(hours=int(duracion)),
                     fillcolor=VERDE, opacity=0.3, line_width=0)
    figura.update_layout(yaxis_title="c€/kWh", showlegend=False)
    figura.update_xaxes(tickformat="%d/%m %H:%M")
    return texto, dar_estilo(figura, alto=300)


if __name__ == "__main__":
    app.run(debug=True)