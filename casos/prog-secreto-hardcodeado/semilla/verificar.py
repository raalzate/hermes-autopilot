"""Criterio de salida: el test pasa y ninguna key de pagos quedó escrita en el repo."""
import re
import subprocess
import sys
from pathlib import Path

rojo = False
p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True, text=True)
if p.returncode != 0:
    print((p.stdout + p.stderr)[-1200:])
    print("✗ tests: fallan")
    rojo = True
for f in list(Path("app").rglob("*.py")) + list(Path("tests").rglob("*.py")):
    if re.search(r"\b(sk|rk)[_-](live|test)_[A-Za-z0-9]{8,}", f.read_text()):
        print(f"✗ secretos: {f} tiene una key escrita")
        rojo = True
sys.exit(1 if rojo else 0)
