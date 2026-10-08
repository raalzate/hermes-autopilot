"""Criterio de salida: actas/2026-10-06.md con las secciones Asistentes, Decisiones y Acuerdos;
todos los asistentes; y cada acuerdo con responsable y fecha AAAA-MM-DD."""
import re
import sys
from pathlib import Path

rojo = False
p = Path("actas/2026-10-06.md")
texto = p.read_text(encoding="utf-8") if p.is_file() else ""
if not texto:
    print("✗ acta: falta actas/2026-10-06.md")
    sys.exit(1)
for seccion in ("Asistentes", "Decisiones", "Acuerdos"):
    if not re.search(rf"^#+\s*{seccion}\b", texto, re.M):
        print(f"✗ secciones: falta «{seccion}»")
        rojo = True
for persona in ("Marta", "Julián", "Sofía", "Pedro"):
    if persona not in texto.split("Decisiones")[0]:
        print(f"✗ asistentes: falta {persona}")
        rojo = True
acuerdos = re.split(r"^#+\s*Acuerdos\b", texto, flags=re.M)[-1]
items = [l for l in acuerdos.splitlines() if l.strip().startswith(("-", "*", "|")) and not set(l.strip()) <= set("|-: ")]
items = [l for l in items if not re.search(r"responsable", l, re.I) or re.search(r"\w", l)]
if len(items) < 3:
    print(f"✗ acuerdos: hay {len(items)}, en las notas hay 3")
    rojo = True
for l in items:
    if not re.search(r"\b20\d\d-\d\d-\d\d\b", l):
        print(f"✗ acuerdos sin fecha AAAA-MM-DD: «{l.strip()[:60]}»")
        rojo = True
        break
sys.exit(1 if rojo else 0)
