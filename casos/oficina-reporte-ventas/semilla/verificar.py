"""Criterio de salida: reportes/resumen_q3.md tiene una fila «| Región | total |» por región y una
«| Total | … |», y los números coinciden con el CSV original (las devoluciones restan)."""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

esperado = defaultdict(float)
with open("datos/originales/ventas_q3.csv", newline="", encoding="utf-8") as f:
    for fila in csv.DictReader(f):
        esperado[fila["region"]] += float(fila["monto"])
esperado["Total"] = sum(esperado.values())

rojo = False
rep = Path("reportes/resumen_q3.md")
filas = dict(re.findall(r"^\|\s*([^|]+?)\s*\|\s*([-\d.,]+)\s*\|\s*$", rep.read_text(encoding="utf-8"), re.M)) if rep.is_file() else {}
for region, total in esperado.items():
    if region not in filas:
        print(f"✗ resumen: falta la fila de {region}")
        rojo = True
    elif abs(float(filas[region].replace(",", "")) - total) > 0.005:
        print(f"✗ totales: {region} dice {filas[region]} y el CSV da {total:.2f}")
        rojo = True
sys.exit(1 if rojo else 0)
