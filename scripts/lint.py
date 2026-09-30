#!/usr/bin/env python3
"""
Convention lint: las reglas del repo que ningún compilador ve, con un comando que falla.

    python3 scripts/lint.py                      el repo entero (lo corre el gate)
    python3 scripts/lint.py --rules              qué reglas están activas y de dónde salen
    python3 scripts/lint.py --file <ruta>        un archivo
    python3 scripts/lint.py --stdin <ruta>       contenido por stdin; la ruta SÓLO elige las
                                                 reglas (P7: probar un freno no escribe archivos)

Las clases de regla viven en `plugin/harness/rules.py` (las usa también el plugin, en proceso).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# El núcleo vive DENTRO del plugin (`plugin/harness/`): Hermes copia el directorio del plugin
# al instalarlo y al validarlo, y lo que quede afuera no viaja (docs/gotchas.md).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from harness.core import REPO_ROOT, CONFIG_PATH  # noqa: E402
from harness.rules import TEXT_EXT, _re, lint_one  # noqa: E402


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=REPO_ROOT,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
        return [f for f in out.splitlines() if (REPO_ROOT / f).is_file()]
    except (OSError, subprocess.CalledProcessError):
        return [p.relative_to(REPO_ROOT).as_posix() for p in REPO_ROOT.rglob("*")
                if p.is_file() and ".git" not in p.parts]


def main(argv: list[str]) -> int:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"lint: no se puede leer {CONFIG_PATH.name}: {e}")
        return 1

    if "--rules" in argv:
        ctx, sk = config.get("context") or {}, config.get("skills") or {}
        print("Reglas activas (desde .hermes/harness.config.json):")
        print(f"  PATRON      {len(config.get('patterns') or [])} regla(s)")
        print(f"  INVARIANTE  {len(config.get('invariants') or [])} archivo(s)")
        print(f"  INCIDENTE   {(config.get('incidents') or {}).get('file', '—')}")
        print(f"  CONTEXTO    {', '.join(ctx.get('files') or []) or '—'} ≤ {ctx.get('maxChars', '—')} caracteres, "
              f"{len(ctx.get('blockedPatterns') or [])} patrón(es) del escáner de Hermes")
        print(f"  SKILL       {', '.join(sk.get('roots') or []) or '—'}")
        return 0

    if "--stdin" in argv:
        rel = argv[argv.index("--stdin") + 1]
        errores = lint_one(config, rel, sys.stdin.read())
    elif "--file" in argv:
        rel = argv[argv.index("--file") + 1]
        p = REPO_ROOT / rel
        errores = lint_one(config, rel, p.read_text(encoding="utf-8", errors="replace")) if p.is_file() else []
    else:
        errores = []
        # Un invariante sobre un archivo que no existe es un invariante que no protege nada.
        for inv in config.get("invariants") or []:
            if not (REPO_ROOT / inv.get("file", "")).is_file():
                errores.append(f"INVARIANTE {inv.get('file')} — el archivo no existe: la regla apunta a la nada")
        for f in (config.get("context") or {}).get("files") or []:
            if not (REPO_ROOT / f).is_file():
                errores.append(f"CONTEXTO {f} — no existe: Hermes arranca sin las reglas del repo")
        ignorar = [r for r in ((config.get("lint") or {}).get("ignore") or []) if _re(r)]
        for rel in tracked_files():
            if Path(rel).suffix not in TEXT_EXT or any(re.search(r, rel) for r in ignorar):
                continue
            errores += lint_one(config, rel, (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace"))

    for e in errores:
        print(e)
    if errores:
        print(f"\nlint: {len(errores)} hallazgo(s).")
        return 1
    if "--stdin" not in argv and "--file" not in argv:
        print("lint: verde.")
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
