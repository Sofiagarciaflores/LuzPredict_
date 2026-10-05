# LuzPredict

**Previsión a 7 días del precio de la luz en España (PVPC) y planificador de consumo para el hogar, con aprendizaje automático (ML).**

Proyecto de la asignatura *Desarrollo de Aplicaciones para la Visualización de Datos*.

## Descripción

Muchos hogares tienen la tarifa regulada de la luz (PVPC), en la que el precio cambia cada hora del día, y las diferencias entre horas pueden ser grandes: la luz suele ser barata cuando hay mucho sol y cara por la noche. Ya existen webs que muestran el precio de hoy y de mañana, pero ese dato se conoce el día anterior.

LuzPredict añade lo que esas webs no ofrecen:

- **Previsión de 2 a 7 días**, calculada con un modelo de aprendizaje automático (el ordenador aprende de los precios pasados).
- **Aviso de fiabilidad:** un rango con el precio mínimo y máximo probable, y la diferencia entre "precio ya fijado" y "precio previsto".
- **Planificador:** eliges un electrodoméstico (lavadora, lavavajillas, coche eléctrico…) y cuándo lo necesitas, y la web te dice la mejor hora y cuánto ahorras en euros.

**Alcance:** Península, tarifa PVPC para hogares, previsión por horas de los próximos 7 días, actualizada cada día.
**Usuarios:** hogares con PVPC, personas con coche eléctrico o con horario flexible.
**Aplicación web:** hecha en Python con Streamlit (para crear webs de datos de forma sencilla) y Plotly (gráficos interactivos).

## Objetivos

1. Reunir los datos necesarios: precios de la luz (Red Eléctrica de España), previsión del tiempo (Open-Meteo) y calendario de festivos.
2. Preparar y limpiar esos datos (huecos, cambios de hora, valores raros).
3. Probar tres formas de predecir el precio y compararlas: un método simple de referencia (repetir el precio de la misma hora de la semana anterior), Prophet (modelo estadístico) y LightGBM (aprendizaje automático, que además da el rango mínimo-máximo).
4. Comprobar cuánto se equivoca cada una con semanas que el modelo no ha visto. Será un buen resultado si mejora de forma constante al método simple y el precio real cae dentro del rango alrededor del 80 % de las veces.
5. Crear una web con: gráfico del precio previsto y su rango, mapa de colores (día × hora) de la semana, planificador de electrodomésticos con el ahorro en euros y un panel que muestra cuánto se equivoca el modelo.
6. Hacer que los datos y la previsión se actualicen solos cada día.

## Datos

| Fuente | Qué aporta |
|---|---|
| Red Eléctrica de España (ESIOS) | Precios de la luz de años anteriores, hora a hora. Requiere pedir una clave de acceso gratuita a Red Eléctrica. |
| REData (Red Eléctrica) | Los mismos precios casi en tiempo real, de acceso público y sin clave. Sirve como alternativa. |
| Open-Meteo | Previsión del tiempo (viento, sol y temperatura), que influye en el precio. Gratuita. |
| Calendario | Festivos y fines de semana, que cambian la demanda de electricidad. |

## Plan de trabajo inicial

| Fase | Qué se hace | Resultado |
|---|---|---|
| 0. Preparación | Crear el repositorio, preparar Python y pedir la clave a Red Eléctrica | Carpeta del proyecto lista |
| 1. Datos | Descargar los precios históricos, limpiarlos y explorarlos con gráficos | Datos limpios y primeras conclusiones |
| 2. Variables y método simple | Preparar las pistas para el modelo (hora, día, festivo, tiempo…) y calcular la referencia | Error de referencia |
| 3. Modelos | Entrenar y comparar Prophet y LightGBM | Comparativa y modelo elegido |
| 4. Aplicación web | Crear los gráficos, el planificador y el panel de calidad | Web funcionando en el ordenador |
| 5. Automatización y publicación | Actualización diaria automática (con GitHub) y publicación gratuita | Web en internet |
| 6. Cierre | Memoria final, conclusiones y limitaciones, y demostración | Entrega |

## Estructura prevista del repositorio

```
luzpredict/
├── data/                # datos descargados y preparados
├── notebooks/           # pruebas y exploración
├── src/                 # código: descarga de datos, modelo y evaluación
├── app/                 # la aplicación web
├── .github/workflows/   # tarea automática diaria
├── requirements.txt     # librerías necesarias
└── README.md            # este documento
```

## Limitaciones

Es un proyecto académico. Las previsiones a varios días son inciertas y no garantizan ningún ahorro; el precio real de la factura depende también de peajes, impuestos y del contrato de cada hogar.
