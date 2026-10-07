"""
El registro de lo que el arnés hizo: una línea JSON por evento, en el directorio de git.

    {"at": 1759250000.1, "kind": "block", "rule": "force-push", "tool": "terminal", ...}

Lo escriben el plugin (bloqueos, escaladas, hallazgos del lint, gate pendiente al cerrar el
turno), el gate y el loop autónomo. Lo leen el panel en vivo (`scripts/panel.py`) y
`harness status`. Sin esto, lo que el arnés frena se ve sólo dentro de la conversación que lo
provocó: nadie sabe cuántas veces mordió cada regla ni si el loop está trabado.

Reglas de la casa, las mismas de los frenos:
  - nunca lanza: un disco lleno o un `.git` de sólo lectura no pueden bloquear una herramienta (P5);
  - sin procesos: append a un archivo, nada más (P19);
  - fuera del árbol de fuentes: vive bajo `.git/`, como el marcador del gate (P7);
  - con techo: pasado `maxBytes` se rota a `<archivo>.1` y se empieza de cero.

`observability.events` en el config lo enciende (`file`, `maxBytes`). Sin esa clave no se
escribe nada. `HARNESS_NO_EVENTS=1` lo apaga: el self-test y la medición de latencia ejercitan
los frenos cientos de veces y no pueden llenar el panel del humano de bloqueos de mentira.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .core import git_dir

DEFAULT_MAX_BYTES = 512 * 1024


def spec(config: dict | None) -> dict:
    ev = ((config or {}).get("observability") or {}).get("events")
    return ev if isinstance(ev, dict) and ev.get("file") else {}


def path(config: dict | None, root: Path) -> Path | None:
    """Dónde vive el registro. `.git/...` se resuelve contra el gitdir real (worktrees)."""
    rel = spec(config).get("file")
    if not rel:
        return None
    if rel.startswith(".git/"):
        g = git_dir(root)
        return (g / rel[len(".git/"):]) if g is not None else None
    return root / rel


def record(config: dict | None, root: Path, kind: str, **data) -> None:
    """Agrega un evento. Nunca lanza, nunca bloquea: si no se puede escribir, no se escribe."""
    if os.environ.get("HARNESS_NO_EVENTS"):
        return
    try:
        p = path(config, root)
        if p is None:
            return
        tope = int(spec(config).get("maxBytes") or DEFAULT_MAX_BYTES)
        if p.exists() and p.stat().st_size > tope:
            os.replace(p, p.with_name(p.name + ".1"))
        linea = json.dumps({"at": round(time.time(), 3), "kind": kind, **data}, ensure_ascii=False, default=str)
        with p.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except (OSError, ValueError, TypeError):
        return


def tail(config: dict | None, root: Path, n: int = 50) -> list[dict]:
    """Los últimos `n` eventos, del más viejo al más nuevo. Una línea rota se saltea."""
    p = path(config, root)
    if p is None or not p.is_file():
        return []
    try:
        with p.open("rb") as f:
            f.seek(0, os.SEEK_END)
            tam = f.tell()
            f.seek(max(0, tam - 256 * 1024))
            lineas = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for linea in lineas[-n:]:
        try:
            ev = json.loads(linea)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out
