# LuzPredict

Panel web con la previsión a 7 días del precio de la luz en España y un planificador que dice a qué hora conviene poner un electrodoméstico.

Proyecto de la asignatura *Desarrollo de Aplicaciones para la Visualización de Datos* (ICAI, Universidad Pontificia Comillas).

## Qué hace

- **Panel:** precio de la próxima hora, hora más barata y más cara de las próximas 24 h, previsión a 7 días, mejores horas del día, mapa de colores y evolución mensual.
- **Planificador:** elige un electrodoméstico y una hora límite; la web busca el mejor momento y calcula el ahorro frente a empezar a las 21:00.
- **Calidad de la previsión:** cuánto se equivoca la previsión según los días de antelación.

## Archivos

```
app.py                 la web, hecha con Dash (panel, planificador y calidad)
funciones.py           todo el cálculo: datos, previsión, resúmenes y planificador
actualizar_datos.py    descarga los precios reales y los guarda en data/precios.csv
test_funciones.py      pruebas automáticas (pytest)
requirements.txt       librerías necesarias
render.yaml            configuración del despliegue en Render
assets/estilo.css      colores y diseño de la web
assets/paneles.jpg     foto de la cabecera
.github/workflows/     tests en cada subida y descarga diaria de datos
data/precios.csv       precios horarios reales (se crea al descargar)
```

## Cómo ejecutarlo

Necesita Python 3.10 o superior.

```bash
python3 -m venv .venv
source .venv/bin/activate          # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
python actualizar_datos.py 2026-10-01   # descarga precios reales (prueba corta)
python app.py                          # web en http://127.0.0.1:8050
pytest -q                               # pruebas
```

Sin `data/precios.csv`, la web usa datos de demostración (inventados) y lo avisa en pantalla.

## Despliegue

Se despliega en Render como servicio web de Python (ver `render.yaml`): instala `requirements.txt` y arranca con `gunicorn app:server`.

## Datos

- **Fuente:** API pública de Red Eléctrica de España, REData (`apidatos.ree.es`): mercado diario (spot) y PVPC. Sin clave.
- **Primera descarga:** `python actualizar_datos.py` (desde 2021) o, en GitHub, *Actions → CI y datos → Run workflow*.
- **Después:** la acción de GitHub se ejecuta cada día y guarda los precios nuevos en `data/precios.csv`.
- **Aviso:** los nombres de las series de la API (`spot`, `pvpc`) están sin confirmar contra la respuesta real. Si la primera descarga falla, el error enseña qué series ha encontrado.
- Desde octubre de 2025 el mercado da precios cada 15 minutos; se promedian a horas.

## Decisiones técnicas

- **Previsión:** se comparan tres métodos en el pasado (misma hora de la semana anterior, media de las 4 semanas anteriores y un modelo de aprendizaje automático) y la web usa el que menos se equivoca. El modelo de aprendizaje automático solo se usa si de verdad gana a los dos sencillos.
- **Modelo:** gradient boosting (scikit-learn, `HistGradientBoostingRegressor`) con tres versiones (percentil 10, mediana y percentil 90). La mediana es la previsión y los otros dos forman el intervalo del 80 %, que se calibra con datos que el modelo no ha visto (calibración conforme). Se regulariza fuerte porque los precios son muy ruidosos.
- **Examen limpio:** el modelo que se evalúa se entrena con datos anteriores a las pruebas. La pestaña *Calidad* muestra su error y cuántas veces el precio real cae dentro del intervalo (ideal: cerca del 80 %).
- **Sin fuga de información:** la previsión y su evaluación solo usan datos anteriores al momento de predecir.
- **PVPC:** el planificador usa un peso del 45 % del mercado diario (2026). Es una aproximación: no incluye peajes por periodo, cargos ni impuestos.
- **Precios negativos o cero:** se mantienen, porque ocurren de verdad en el mercado.
- **Cambio de hora:** series con zona horaria `Europe/Madrid`; los días de cambio tienen 23 o 25 horas.

## Plan de trabajo

| Paso | Contenido | Estado |
|---|---|---|
| 1 | Panel, planificador y previsión de referencia con datos de demostración | Hecho |
| 2 | Datos reales de REData y descarga diaria automática | Hecho (falta la primera descarga real) |
| 3 | Despliegue de la web en Render | Pendiente |
| 4 | Modelo de aprendizaje automático con intervalo al 80 % | Hecho (probado con datos de demostración; falta reevaluarlo con datos reales) |
| 4b | Añadir el tiempo (Open-Meteo) como variable del modelo | Pendiente |
| 5 | Planificador calibrado con el PVPC real, pulido y presentación | Pendiente |

## Créditos

Foto de cabecera (`assets/paneles.jpg`): **pendiente de confirmar la fuente y la licencia**. Antes de la entrega final, sustituirla por una foto de licencia libre (Unsplash, Pexels o Pixabay) e indicar aquí el autor y el enlace.