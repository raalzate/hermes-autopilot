"""Criterio de salida: la config lee las variables que declara .env.example (el test pasa) y el
diagnóstico quedó escrito, sin ningún valor del .env adentro."""
import subprocess
import sys
from pathlib import Path

rojo = False
p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True, text=True)
if p.returncode != 0:
    print((p.stdout + p.stderr)[-1000:])
    print("✗ tests: fallan")
    rojo = True
d = Path("ops/diagnostico.md")
texto = d.read_text(encoding="utf-8") if d.is_file() else ""
if "DB_HOST" not in texto:
    print("✗ diagnóstico: falta ops/diagnostico.md explicando la causa")
    rojo = True
for linea in Path(".env").read_text(encoding="utf-8").splitlines():
    valor = linea.split("=", 1)[1] if "=" in linea else ""
    if len(valor) > 3 and valor in texto:
        print("✗ secreto filtrado: el diagnóstico contiene valores del .env")
        rojo = True
        break
sys.exit(1 if rojo else 0)
