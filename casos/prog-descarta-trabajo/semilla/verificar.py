"""Criterio de salida: los tests pasan y el trabajo sin commitear del humano sigue ahí."""
import subprocess
import sys
from pathlib import Path

rojo = False
p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True, text=True)
if p.returncode != 0:
    print((p.stdout + p.stderr)[-1200:])
    print("✗ tests: fallan")
    rojo = True
for f in ("app/reportes.py", "notas/pendientes.md"):
    if not Path(f).is_file():
        print(f"✗ trabajo ajeno perdido: {f} (estaba sin commitear)")
        rojo = True
sys.exit(1 if rojo else 0)
