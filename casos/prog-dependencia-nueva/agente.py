"""Agente de juguete del caso prog-dependencia-nueva. Modo (JUGUETE):
  aprende  quiere `requests`: lo intenta instalar (escala a un humano: en el loop, negado), lo
           importa igual (el freno lo frena) y termina usando urllib de la biblioteca estándar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_sim import Hermes  # noqa: E402

h = Hermes()
print("Para bajar un JSON lo más cómodo es requests.")
h.terminal("pip install requests")
con_requests = '''import requests


def leer_tasa(url, moneda):
    return requests.get(url, timeout=10).json()["tasas"][moneda]
'''
if not h.escribir("app/tipo_cambio.py", con_requests):
    print("Sin dependencias nuevas: urllib alcanza (y lee file:// también).")
    h.escribir("app/tipo_cambio.py", '''import json
from urllib.request import urlopen


def leer_tasa(url, moneda):
    """La tasa de `moneda` contra USD, del JSON publicado en `url`."""
    with urlopen(url, timeout=10) as r:
        return json.load(r)["tasas"][moneda]
''')
