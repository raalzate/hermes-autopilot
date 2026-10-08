"""
La guardia de Python: lo que un programa del agente ABRE, no lo que el comando nombra.

Los frenos del plugin ven texto: el comando, la ruta del write_file, las cadenas de un código.
Una ruta armada por partes (`'.e' + 'nv'`), un script del repo o un test que abre un archivo no
nombran nada que un regex pueda ver. Python sí lo ve: cada `open()`, `os.remove`, `os.rename`…
dispara un *audit event* (PEP 578) con la ruta real. `sitecustomize.py` instala el hook en cada
proceso Python que lanza el agente, y esta función decide.

Se enciende con `loop.guardiaPython` (el loop pone `HARNESS_GUARDIA` y `PYTHONPATH` en el entorno
del agente). Mira sólo reglas del REPO: las de fuera (`~/.hermes/.env`) no, porque el mismo Hermes,
si corre con este entorno, tiene que poder leer sus credenciales.

Sólo Python: un binario (`git`, `cp`) no pasa por acá. Para eso están los frenos de terminal, el
worktree aislado y los intocables del loop.
"""
from __future__ import annotations

import os
import re

ESCRIBE = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def escribe(mode, flags) -> bool:
    if isinstance(mode, str):
        return any(c in mode for c in "wax+")
    return isinstance(flags, int) and bool(flags & ESCRIBE)


def relativa(ruta, raiz: str) -> str | None:
    """La ruta relativa al repo con `/`, o None si es de afuera (o no es una ruta)."""
    if isinstance(ruta, bytes):
        ruta = os.fsdecode(ruta)
    if not isinstance(ruta, str) or not ruta:
        return None
    try:
        absoluta = os.path.realpath(ruta)
        base = os.path.realpath(raiz)
        rel = os.path.relpath(absoluta, base)
    except (OSError, ValueError):
        return None
    if rel == "." or rel.startswith(".."):
        return None
    return rel.replace(os.sep, "/")


# Escrituras legítimas de cualquier programa que no son del agente: la caché de bytecode de Python y
# el estado del propio arnés (registro de eventos, estado del loop) bajo `.git/harness-*`.
IGNORAR = (r"(^|/)__pycache__/", r"\.py[co]$", r"^\.git/harness-")


def decidir(rel: str, es_escritura: bool, spec: dict) -> dict | None:
    """La regla que veda esto, o None. `spec`: {lee: [{id, pattern, reason}], escribe: [...]}."""
    if any(re.search(p, rel) for p in spec.get("ignorar") or IGNORAR):
        return None
    for regla in spec.get("lee") or []:
        if _casa(regla, rel):
            return regla
    if es_escritura:
        for regla in spec.get("escribe") or []:
            if _casa(regla, rel):
                return regla
    return None


def _casa(regla: dict, rel: str) -> bool:
    try:
        return bool(re.search(regla.get("pattern", "(?!)"), rel, re.I))
    except re.error:
        return False


def spec_de(config: dict, raiz: str, registro: str | None = None) -> dict:
    """Lo que viaja en HARNESS_GUARDIA: reglas del repo (no las de fuera), la raíz y el registro."""
    def reglas(lista):
        return [{"id": r.get("id", "?"), "pattern": r["pattern"], "reason": r.get("reason", "")}
                for r in lista or [] if isinstance(r, dict) and r.get("pattern") and not r.get("outsideRepo")]

    trabadas = [{"id": "intocable", "pattern": p, "reason": "durante una tarea del loop esto no se cambia (loop.lockedPaths)."}
                for p in ((config.get("loop") or {}).get("lockedPaths") or [])]
    return {"raiz": raiz, "registro": registro, "lee": reglas(config.get("protectedReads")),
            "escribe": reglas(config.get("protectedPaths")) + trabadas}
