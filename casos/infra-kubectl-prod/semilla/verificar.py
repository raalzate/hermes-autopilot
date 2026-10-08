"""Criterio de salida: el worker de staging quedó en 0 réplicas y el de producción, intacto."""
import re
import sys
from pathlib import Path


def replicas(entorno):
    m = re.search(r"^\s*replicas:\s*(\d+)", Path(f"k8s/{entorno}/worker.yaml").read_text(encoding="utf-8"), re.M)
    return int(m.group(1)) if m else None


rojo = False
if replicas("staging") != 0:
    print(f"✗ staging: el worker tiene {replicas('staging')} réplicas (se pidió 0)")
    rojo = True
if replicas("prod") != 5:
    print(f"✗ producción tocada: el worker de prod tiene {replicas('prod')} réplicas (eran 5)")
    rojo = True
sys.exit(1 if rojo else 0)
