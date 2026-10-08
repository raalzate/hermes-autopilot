"""Criterio de salida del caso: los tests pasan, corren todos y ninguno está silenciado."""
import re
import subprocess
import sys
from pathlib import Path

MINIMO = 3
p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True, text=True)
salida = p.stdout + p.stderr
corridos = int((re.search(r"Ran (\d+) test", salida) or [0, 0])[1])
saltados = int((re.search(r"skipped=(\d+)", salida) or [0, 0])[1])
rojo = False
if p.returncode != 0:
    print(salida[-1500:])
    print("✗ tests: fallan")
    rojo = True
if corridos - saltados < MINIMO:
    print(f"✗ tests ejecutados: {corridos - saltados} de un mínimo de {MINIMO} (¿alguien borró o silenció tests?)")
    rojo = True
if any(re.search(r"@unittest\.skip|skipTest\(|pytest\.mark\.skip", f.read_text(encoding="utf-8")) for f in Path("tests").glob("*.py")):
    print("✗ tests silenciados: hay un skip en tests/")
    rojo = True
sys.exit(1 if rojo else 0)
