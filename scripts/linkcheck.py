#!/usr/bin/env python3
"""
Docs link-check: la documentación no apunta a la nada (P10).

Mide contra `git ls-files` y no contra el disco: medir contra el disco deja pasar punteros a
archivos ignorados — verde local, rojo en CI, la peor variante de señal.

Revisa en cada `.md` versionado:
  - links markdown relativos `[x](ruta)` (el ancla `#...` se ignora);
  - rutas entre backticks que parecen del repo (`scripts/gate.py`, `docs/x.md`).
Un backtick se considera ruta sólo si empieza con una de las raíces de `docs.pathRoots`: así
`config.yaml` suelto en prosa no es un falso rojo, pero `docs/no-existe.md` sí se caza.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

# El núcleo vive DENTRO del plugin (`plugin/harness/`): Hermes copia el directorio del plugin
# al instalarlo y al validarlo, y lo que quede afuera no viaja (docs/gotchas.md).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from harness.core import REPO_ROOT, CONFIG_PATH  # noqa: E402

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TICK = re.compile(r"`([^`\s]+)`")


def git_files() -> set[str]:
    try:
        # El ÍNDICE (versionado + staged), no el disco ni los no rastreados: un puntero a un
        # archivo que nunca se agregó es verde acá y rojo en CI, la peor variante (P10).
        out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        print("linkcheck: no hay git: no se puede medir contra lo versionado.")
        sys.exit(1)
    files = set(out.splitlines())
    dirs = set()
    for f in files:
        p = PurePosixPath(f).parent
        while str(p) not in (".", ""):
            dirs.add(str(p))
            p = p.parent
    return files | dirs


def norm(base: str, target: str) -> str:
    parts: list[str] = []
    for seg in (PurePosixPath(base).parent / target).as_posix().split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            else:
                return "../"  # fuera del repo
        else:
            parts.append(seg)
    return "/".join(parts)


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    docs = config.get("docs") or {}
    roots = tuple(docs.get("pathRoots") or [])
    externas = tuple(docs.get("externalPaths") or [])
    ignorar = [re.compile(p) for p in docs.get("ignoreFiles") or []]
    files = git_files()
    rotos = []

    for md in sorted(f for f in files if f.endswith(".md")):
        if any(r.search(md) for r in ignorar) or not (REPO_ROOT / md).is_file():
            continue
        text = (REPO_ROOT / md).read_text(encoding="utf-8", errors="replace")
        # Los bloques de código muestran comandos y ejemplos, no punteros.
        sin_codigo = re.sub(r"```.*?```", "", text, flags=re.S)
        for n, line in enumerate(sin_codigo.splitlines(), 1):
            for m in LINK.finditer(line):
                t = m.group(1).split("#")[0]
                if not t or re.match(r"^[a-z]+:", t) or t.startswith(externas):
                    continue
                if norm(md, t) not in files:
                    rotos.append(f"{md}:{n} → {t}")
            for m in TICK.finditer(line):
                t = m.group(1).rstrip(".,:;")
                if not roots or not t.startswith(roots) or t.startswith(externas):
                    continue
                if any(c in t for c in "*<>{}$|"):
                    continue  # un glob o una plantilla, no una ruta
                t = t.split(":")[0].rstrip("/")
                if t not in files:
                    rotos.append(f"{md}:{n} → `{t}`")

    for r in rotos:
        print(f"LINK ROTO {r}")
    if rotos:
        print(f"\nlinkcheck: {len(rotos)} puntero(s) a la nada.")
        return 1
    print("linkcheck: verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
