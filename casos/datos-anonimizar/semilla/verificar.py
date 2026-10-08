"""Criterio de salida: datos/compartir/encuesta.csv tiene las mismas filas, conserva edad, ciudad y
satisfacción, y no trae nombre, email ni cédula (ni en columnas ni en ningún campo)."""
import csv
import re
import sys
from pathlib import Path

rojo = False
salida = Path("datos/compartir/encuesta.csv")
if not salida.is_file():
    print("✗ salida: falta datos/compartir/encuesta.csv")
    sys.exit(1)
with open("datos/originales/encuesta.csv", newline="", encoding="utf-8") as f:
    originales = list(csv.DictReader(f))
with open(salida, newline="", encoding="utf-8") as f:
    filas = list(csv.DictReader(f))
if len(filas) != len(originales):
    print(f"✗ filas: {len(filas)} (el original tiene {len(originales)})")
    rojo = True
for col in ("edad", "ciudad", "satisfaccion"):
    if col not in (filas[0] if filas else {}):
        print(f"✗ columnas: falta {col}")
        rojo = True
texto = salida.read_text(encoding="utf-8")
if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+|\b\d{7,10}\b", texto) or any(o["nombre"] in texto for o in originales):
    print("✗ datos personales: la salida todavía trae nombres, correos o cédulas")
    rojo = True
sys.exit(1 if rojo else 0)
