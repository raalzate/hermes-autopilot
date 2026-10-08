"""Criterio de salida: los tests pasan y `app/` sólo importa la biblioteca estándar."""
import ast
import subprocess
import sys
from pathlib import Path

rojo = False
p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True, text=True)
if p.returncode != 0:
    print((p.stdout + p.stderr)[-1200:])
    print("✗ tests: fallan")
    rojo = True
for f in Path("app").rglob("*.py"):
    for nodo in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        mods = [a.name for a in nodo.names] if isinstance(nodo, ast.Import) else [nodo.module or ""] if isinstance(nodo, ast.ImportFrom) else []
        for m in mods:
            raiz = m.split(".")[0]
            if raiz and raiz not in sys.stdlib_module_names and raiz != "app":
                print(f"✗ dependencias: {f} importa `{m}`, que no es de la biblioteca estándar")
                rojo = True
sys.exit(1 if rojo else 0)
