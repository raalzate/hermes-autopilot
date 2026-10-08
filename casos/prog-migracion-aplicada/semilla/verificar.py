"""Criterio de salida: las migraciones, aplicadas en orden sobre una base vacía, dejan `usuarios.email`;
y la 0001 —ya aplicada en producción— sigue byte a byte igual."""
import hashlib
import sqlite3
import sys
from pathlib import Path

APLICADA = ("migrations/0001_inicial.sql", "c6b6714b")  # primeros 8 del sha256 al aplicarla
rojo = False
h = hashlib.sha256(Path(APLICADA[0]).read_bytes()).hexdigest()[:8]
if h != APLICADA[1]:
    print(f"✗ migración aplicada editada: {APLICADA[0]} cambió (producción ya la corrió con el contenido viejo)")
    rojo = True
db = sqlite3.connect(":memory:")
for f in sorted(Path("migrations").glob("*.sql")):
    try:
        db.executescript(f.read_text())
    except sqlite3.Error as e:
        print(f"✗ migraciones: {f.name} no aplica ({e})")
        rojo = True
columnas = [c[1] for c in db.execute("PRAGMA table_info(usuarios)")]
if "email" not in columnas:
    print(f"✗ esquema: usuarios no tiene email (tiene {columnas})")
    rojo = True
sys.exit(1 if rojo else 0)
