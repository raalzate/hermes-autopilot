#!/usr/bin/env python3
"""
Agente de juguete para el workshop: hace de Hermes dentro del loop, sin modelo ni API key.

    python3 agente_juguete.py "<prompt>"

Escribe `app/calc.py` en el directorio actual, como lo haría un agente que trabaja la tarea:

    JUGUETE=aprende  (por defecto) el primer intento mete un bug; cuando el prompt trae el rojo del
                     gate (el reintento empieza con "Intento N"), lo corrige. El loop llega a verde.
    JUGUETE=terco    repite el mismo bug siempre. El gate da el mismo rojo dos veces seguidas y el
                     loop escala a un humano (P16) en vez de quemar intentos.

Es determinista a propósito: en el workshop se aprende la mecánica del loop sin depender de qué
conteste un modelo ese día. Después se cambia `loop.agentCommand` por Hermes y la mecánica es la misma.
"""
import os
import sys
from pathlib import Path

prompt = sys.argv[1] if len(sys.argv) > 1 else ""
modo = os.environ.get("JUGUETE", "aprende")
corrige = modo == "aprende" and "Intento" in prompt
codigo = "def suma(a, b):\n    return a + b\n" if corrige else "def suma(a, b):\n    return a - b  # el bug\n"
Path("app").mkdir(exist_ok=True)
Path("app/calc.py").write_text(codigo, encoding="utf-8")
print(f"[juguete:{modo}] escribí app/calc.py ({'corregido' if corrige else 'con el bug'})")
