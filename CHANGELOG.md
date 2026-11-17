# Changelog

## 0.2.0 · Sprint 1: datos reales
- Descarga de precios reales de Red Eléctrica (REData): `python actualizar_datos.py`.
- Acción de GitHub «Actualizar datos»: descarga cada día y guarda `data/precios.csv`.
- La app lee `data/precios.csv`, muestra la fuente y la fecha del último precio, y avisa si los datos están desfasados.
- Si no hay datos, la app usa datos de demostración y lo avisa.
- El planificador y el mapa de colores usan los precios ya publicados de mañana (si existen) más la previsión.
- Tests de la descarga con un servidor falso (sin internet).

## 0.1.2 · Imagen más profesional
- Cabecera con foto de paneles solares y paleta sobria (azul marino, azul corporativo, ámbar).
- Mapa de colores y aviso con colores más saturados.
- Ilustración de ahorro recoloreada.

## 0.1.1 · Imagen y tipografía
- Nueva tipografía (Fraunces y DM Sans, incluidas en el repo) y paleta cálida.
- Ilustraciones propias en SVG: paneles solares y ahorro.
- Sin emoticonos en la interfaz.
- Corregido el mapa de colores (horas ordenadas y gráfico que no se pintaba).

## 0.1.0 · Sprint 0: esqueleto
- Estructura del repositorio, tests y CI en GitHub Actions.
- Método de referencia (misma hora de la semana anterior) y backtesting por días de antelación.
- Planificador de electrodomésticos con peso del mercado diario en el PVPC (45 % en 2026).
- App Streamlit con 4 pestañas (previsión, mapa de colores, planificador, calidad) usando datos sintéticos.
