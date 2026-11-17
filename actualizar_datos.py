"""Descarga (o actualiza) los precios reales y los guarda en data/precios.csv.

Cómo usarlo, desde la carpeta del proyecto:

    python actualizar_datos.py              # primera vez: descarga desde 2021
    python actualizar_datos.py 2023-01-01   # elegir la fecha de inicio
    python actualizar_datos.py              # después: solo descarga lo que falta

También se ejecuta solo cada día en GitHub (ver .github/workflows/actualizar-datos.yml).
"""
import sys

from luzpredict.datos import RUTA_CSV, actualizar_csv

desde = "2021-01-01"
if len(sys.argv) > 1:
    desde = sys.argv[1]

print("Descargando precios de Red Eléctrica (REData)... puede tardar un par de minutos.")
tabla = actualizar_csv(RUTA_CSV, desde=desde)

print("Listo.")
print("Horas guardadas:", len(tabla))
print("Primer dato:", tabla.index[0])
print("Último dato:", tabla.index[-1])
print("Archivo:", RUTA_CSV)
