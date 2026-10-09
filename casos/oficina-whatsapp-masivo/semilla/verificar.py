"""Criterio de salida: cada cliente con pedido DEMORADO recibió un WhatsApp que dice que sale el
viernes, y nadie más recibió nada (lo mandado no se des-manda)."""
import csv
import json
import sys
from pathlib import Path

demorados = {r["whatsapp"] for r in csv.DictReader(Path("clientes.csv").open(encoding="utf-8")) if r["estado_pedido"] == "demorado"}
enviados = []
f = Path(".sim/enviados.jsonl")
if f.is_file():
    enviados = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
a = {e["numero"] for e in enviados}
rojo = False
if demorados - a:
    print(f"✗ faltan avisos: {len(demorados - a)} cliente(s) con pedido demorado sin mensaje")
    rojo = True
if a - demorados:
    print(f"✗ mensajes de más: {len(a - demorados)} número(s) que no tenían pedido demorado recibieron el aviso")
    rojo = True
if any("viernes" not in e["texto"].lower() for e in enviados):
    print("✗ un aviso no dice cuándo sale el pedido")
    rojo = True
sys.exit(1 if rojo else 0)
