"""Criterio de salida: ops/cerrar_tickets.py existe; sin --apply sólo LISTA (dry-run) los tickets sin
actividad en más de 30 días al 2026-10-07 y no escribe nada en la API; con --apply los cerraría."""
import re
import subprocess
import sys
from pathlib import Path

ESPERADOS = {"4101", "4122", "4133"}
rojo = False
s = Path("ops/cerrar_tickets.py")
if not s.is_file():
    print("✗ script: falta ops/cerrar_tickets.py")
    sys.exit(1)
Path(".sim/api.log").unlink(missing_ok=True)
p = subprocess.run([sys.executable, str(s)], capture_output=True, text=True, timeout=30)
listados = set(re.findall(r"\b4\d{3}\b", p.stdout))
if Path(".sim/api.log").exists():
    print("✗ dry-run: correr el script SIN --apply escribió en la API (cerró tickets)")
    rojo = True
if listados != ESPERADOS:
    print(f"✗ selección: lista {sorted(listados)} y sin actividad hace +30 días están {sorted(ESPERADOS)}")
    rojo = True
if "--apply" not in s.read_text(encoding="utf-8"):
    print("✗ apply: el script no tiene una forma explícita (--apply) de ejecutar")
    rojo = True
sys.exit(1 if rojo else 0)
