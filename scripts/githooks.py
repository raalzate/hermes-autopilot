#!/usr/bin/env python3
"""
Los hooks de git, en Python y no en bash.

    python3 scripts/githooks.py pre-commit
    python3 scripts/githooks.py commit-msg <archivo-del-mensaje>
    python3 scripts/githooks.py install          core.hooksPath=.githooks

Los archivos de `.githooks/` son envoltorios de una línea: la decisión vive acá porque el
config es JSON y bash no lo lee sin ayuda, y porque en Windows un freno que sólo existe en
shell no falla — desaparece.

Barato a propósito: el gate completo vive en `scripts/gate.py` y en CI. Acá sólo lo que no
puede entrar al historial de ninguna manera.
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
from harness.core import REPO_ROOT, CONFIG_PATH, first_match  # noqa: E402
from harness.rules import TEXT_EXT, lint_one  # noqa: E402


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def load() -> dict | None:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pre_commit(config: dict, staged: list[str]) -> list[str]:
    """Rutas protegidas + lint de lo staged. Devuelve los motivos de rechazo."""
    fallas = []
    # `agentOnly`: protege de la EDICIÓN del agente, no de existir en el repo (una guía que se
    # enmienda a conciencia). Bloquear su commit haría imposible crearla.
    reglas = [r for r in config.get("protectedPaths") or [] if not r.get("agentOnly") and not r.get("outsideRepo")]
    for f in staged:
        hit = first_match(reglas, f, 0)
        if hit:
            fallas.append(f"ruta protegida en el commit: {f} — {hit.get('reason', '')}")
    for f in staged:
        if Path(f).suffix not in TEXT_EXT:
            continue
        # Lo que se commitea es el ÍNDICE, no el working tree: leer del disco dejaba pasar un
        # archivo staged con un secreto y después limpiado en la copia de trabajo.
        texto = staged_text(f)
        if texto is not None:
            fallas += lint_one(config, f, texto)
    return fallas


def staged_text(f: str) -> str | None:
    p = subprocess.run(["git", "show", f":{f}"], cwd=REPO_ROOT, capture_output=True)
    if p.returncode != 0:
        disco = REPO_ROOT / f  # fuera de un repo git (el self-test llama a la función suelta)
        return disco.read_text(encoding="utf-8", errors="replace") if disco.is_file() else None
    return p.stdout.decode("utf-8", errors="replace")


def commit_msg(config: dict, msg: str, staged: list[str]) -> str | None:
    """None = pasa. Si el commit toca código, referencia su ítem de trabajo o declara por qué no (P11)."""
    cm, tr = config.get("commitMsg") or {}, config.get("tracker") or {}
    if not cm.get("codePattern") or not tr.get("issuePattern"):
        return None  # no configurado: el freno no corre
    # Merge, revert y fixups los escribe git: no hay decisión humana nueva que declarar.
    if any(msg.startswith(p) for p in cm.get("skipSubjects") or ["Merge ", "Revert ", "fixup! ", "squash! "]):
        return None
    try:
        code_re, issue_re = re.compile(cm["codePattern"]), re.compile(tr["issuePattern"])
    except re.error:
        return None  # regex inválido: lo caza el self-test
    ignoradas = tuple(cm.get("ignoreExtensions") or [".md"])
    codigo = [f for f in staged if code_re.search(f) and not f.endswith(ignoradas)]
    if not codigo or issue_re.search(msg):
        return None
    # La fuga explícita va en su propia línea y CON motivo: un `no-issue:` pelado sería la
    # misma omisión con otro nombre.
    fuga = cm.get("escapeLine", "no-issue:")
    if re.search(rf"^{re.escape(fuga)}\s*\S+", msg, re.I | re.M):
        return None
    return (
        "commit-msg: este commit toca código y no queda registrado en ninguna parte.\n"
        f"  archivos de código: {', '.join(codigo[:5])}{' …' if len(codigo) > 5 else ''}\n"
        f"  referenciá el ítem ({tr.get('issueExample', tr['issuePattern'])}) o agregá una línea:\n"
        f"      {fuga} <por qué este cambio no lleva registro>"
    )


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 0
    if argv[0] == "install":
        subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=REPO_ROOT, check=False)
        print("hooks de git instalados (core.hooksPath=.githooks).")
        return 0
    config = load()
    if not config:
        return 0  # sin config el arnés no puede decidir nada: deja pasar
    if argv[0] == "pre-commit":
        # R incluida: `git mv notas.txt .env` es un archivo protegido NUEVO en el commit.
        staged = [f for f in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if f]
        fallas = pre_commit(config, staged)
        if fallas:
            print("pre-commit:\n  " + "\n  ".join(fallas))
            print("\nCommit abortado. Saltarse la verificación está prohibido: si el gate estorba, se arregla el gate.")
            return 1
        return 0
    if argv[0] == "commit-msg" and len(argv) > 1:
        msg = Path(argv[1]).read_text(encoding="utf-8", errors="replace")
        staged = [f for f in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if f]
        error = commit_msg(config, msg, staged)
        if error:
            print(error)
            return 1
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
