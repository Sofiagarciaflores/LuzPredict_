# LuzPredict

Previsión a 7 días del precio de la luz y planificador de consumo para el hogar.

Proyecto de la asignatura *Desarrollo de Aplicaciones para la Visualización de Datos* (ICAI, Universidad Pontificia Comillas).

## Descripción

Muchos hogares tienen la tarifa regulada (PVPC), cuyo precio cambia cada hora. Las webs existentes muestran el precio de hoy y mañana, que ya está publicado. LuzPredict añade una **previsión de 2 a 7 días** con un modelo de aprendizaje automático, un **rango de fiabilidad** y un **planificador** que dice a qué hora conviene poner la lavadora o cargar el coche y cuánto se ahorra.

## Objetivos

1. Predecir el precio horario del mercado mayorista (€/MWh) a 7 días vista con un error menor que el método simple de referencia.
2. Dar un intervalo de predicción al 80 % cuya cobertura real se mida y se muestre.
3. Traducir la previsión a ahorro en euros para el PVPC (45 % del precio depende del mercado diario en 2026; el resto, de mercados a plazo).
4. Publicar una web clara, interactiva y actualizada cada día.

## Plan de trabajo

| Sprint | Contenido | Estado |
|---|---|---|
| 0 | Esqueleto del repo, tests, CI, modelo de referencia, app con datos de demostración | Hecho |
| 1 | Datos reales: REData (precios, promedio horario de los cuartos de hora desde oct-2025) | Hecho (falta la primera descarga real) |
| 1b | Open-Meteo (previsiones pasadas, no reanálisis) como variables del modelo | Pendiente |
| 2 | Modelo LightGBM por horizonte, regresión por cuantiles (10 %-90 %), backtesting y cobertura | Pendiente |
| 3 | App con datos reales desplegada en Streamlit Community Cloud | Pendiente |
| 4 | Planificador calibrado con el PVPC de ESIOS, panel de calidad, diseño final | Pendiente |
| 5 | Pulido, documentación y ensayo de la exposición (5 min + 2 de preguntas) | Pendiente |

## Estructura

```
luzpredict/            funciones del proyecto
  datos.py             descarga de precios (REData), limpieza y guardado en CSV; pasa 15 min a horas
  sinteticos.py        precios de demostración (inventados)
  referencia.py        método simple de comparación y su evaluación
  variables.py         "pistas" para el modelo (calendario y precios pasados)
  planificador.py      busca la mejor hora para un electrodoméstico
streamlit_app.py       la aplicación web (4 pestañas)
actualizar_datos.py    descarga los precios reales y actualiza data/precios.csv
.github/workflows/     tests (ci.yml) y descarga diaria de datos (actualizar-datos.yml)
assets/                foto de cabecera (paneles solares) e ilustración de ahorro (SVG)
static/fonts/          tipografías Fraunces y DM Sans (licencia SIL OFL)
tests/                 pruebas automáticas (se ejecutan con `pytest`)
data/precios.csv       precios horarios reales (€/MWh), se sube a GitHub
```

### Cómo se conectan las piezas

1. `datos.py` lee `data/precios.csv` (precios reales por hora). Si no existe, `sinteticos.py` crea precios de demostración.
2. `referencia.py` predice la próxima semana y mide cuánto se equivoca.
3. `planificador.py` usa esa previsión para elegir la hora más barata.
4. `streamlit_app.py` llama a todo lo anterior y lo dibuja con gráficos.

## Cómo ejecutarlo

```bash
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q                      # pruebas
streamlit run streamlit_app.py # app en http://localhost:8501
```

## Datos

- **Fuente:** API pública de Red Eléctrica de España, REData (`apidatos.ree.es`), mercado diario (spot) y PVPC.
- **Primera descarga** (tarda unos minutos, descarga desde 2021): en GitHub, pestaña *Actions* → *Actualizar datos* → *Run workflow*. O en tu ordenador: `python actualizar_datos.py`.
- **Después** la acción se ejecuta sola cada día y guarda el resultado en `data/precios.csv`.
- **Aviso:** los nombres de las series de la API (`spot`, `pvpc`) y las unidades están sin verificar contra la respuesta real; si la primera descarga falla, el error indica qué series ha encontrado.

## Decisiones técnicas

- **Sin fuga de información:** con horizonte de 7 días solo se usan retardos de precio de 168 h o más, y variables meteorológicas de *previsiones* pasadas.
- **Precios negativos o cero:** se mantienen, porque ocurren de verdad en el mercado.
- **Cambio de hora:** series con zona horaria (`Europe/Madrid`); los días de cambio tienen 23 o 25 horas.

## Créditos

- Tipografías: Fraunces y DM Sans (licencia SIL OFL, en `static/fonts/`).
- Ilustración de ahorro: dibujo propio.
- Foto de cabecera (`assets/hero_paneles.jpg`): **pendiente de confirmar la fuente y la licencia**. Antes de la entrega final, sustituirla por una foto de licencia libre (Unsplash, Pexels o Pixabay) e indicar aquí el autor y el enlace.

## Estado actual

La versión 0.2 usa precios **reales** de REData cuando existe `data/precios.csv`; si no, datos de demostración con aviso. La previsión sigue siendo el método de referencia (el modelo LightGBM llega en el Sprint 2). Ver [CHANGELOG](CHANGELOG.md).
