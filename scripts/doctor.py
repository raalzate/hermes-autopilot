#!/usr/bin/env python3
"""
¿El arnés está VIVO en esta máquina? — lo que el gate no puede ver porque vive fuera del repo.

    python3 scripts/doctor.py

El gate verifica el repo; esto verifica el Hermes de quien lo corre. Un plugin instalado y no
habilitado, unas skills sin `hermes skills trust`, un `.hermes.md` que tapa a `AGENTS.md`: el
repo pasa el gate y el agente trabaja sin ningún freno. "Instalado y muerto".

No va en el gate: depende de la máquina, y en CI no hay Hermes. Sale 1 si hay algo ROJO.
No escribe nada, y no lee `.env` ni `auth.json` (P8).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

# El núcleo vive DENTRO del plugin (`plugin/harness/`): Hermes copia el directorio del plugin
# al instalarlo y al validarlo, y lo que quede afuera no viaja (docs/gotchas.md).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from harness.core import REPO_ROOT, first_match, load_config  # noqa: E402

ROJO, AMARILLO, VERDE = "✗", "!", "✓"
hallazgos: list[tuple[str, str]] = []


def nota(nivel: str, msg: str) -> None:
    hallazgos.append((nivel, msg))


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser()


def yaml_lista(texto: str, clave_padre: str, clave: str) -> list[str]:
    """`padre:\\n  clave: [a, b]` o en bloque `- a`. Sin PyYAML: sólo las dos formas que escribe
    Hermes. Si no encuentra nada devuelve [] — y el diagnóstico lo dice, no lo inventa."""
    m = re.search(rf"^{clave_padre}:\s*\n((?:[ \t]+.*\n?)*)", texto, re.M)
    if not m:
        return []
    bloque = m.group(1)
    mm = re.search(rf"^\s+{clave}:\s*\[(.*?)\]", bloque, re.M)
    if mm:
        return [x.strip().strip("'\"") for x in mm.group(1).split(",") if x.strip()]
    mm = re.search(rf"^(\s+){clave}:\s*\n((?:\1\s+-\s*.*\n?)*)", bloque, re.M)
    return re.findall(r"-\s*['\"]?([^'\"\n]+)", mm.group(2)) if mm else []


def yaml_int(texto: str, clave: str, defecto: int) -> int:
    m = re.search(rf"^\s+{clave}:\s*(\d+)", texto, re.M)
    return int(m.group(1)) if m else defecto


def main() -> int:
    config = load_config(REPO_ROOT)
    home = hermes_home()
    print(f"doctor — repo {REPO_ROOT} · HERMES_HOME {home}\n")
    if not config:
        nota(ROJO, "sin `.hermes/harness.config.json` válido: el plugin no hace nada en este repo")

    # 1. Hermes y su config
    if shutil.which("hermes"):
        nota(VERDE, "hermes en el PATH")
    else:
        nota(AMARILLO, "hermes no está en el PATH (¿otra terminal, otro venv?)")
    cfg_yaml = home / "config.yaml"
    texto = cfg_yaml.read_text(encoding="utf-8", errors="replace") if cfg_yaml.is_file() else ""
    if not texto:
        nota(AMARILLO, f"no hay {cfg_yaml}: Hermes corre con defaults")

    # 2. El plugin: instalado, importable, habilitado
    plug = home / "plugins" / "repo-harness"
    if not plug.exists():
        nota(ROJO, f"plugin no instalado en {plug} → `python3 {Path(__file__).parent / 'install.py'} {REPO_ROOT} --link-plugin --apply`")
    else:
        real = plug.resolve()
        importable = (real / "harness" / "core.py").is_file()
        nota(VERDE if importable else ROJO, f"plugin en {plug}" + (f" → {real}" if real != plug else "")
             + ("" if importable else " — pero le falta `harness/` adentro: no carga"))
        if real != plug and REPO_ROOT not in real.parents:
            nota(AMARILLO, f"el plugin apunta al arnés de OTRO repo ({real}): corre ese código con el config de éste")
        habilitados = yaml_lista(texto, "plugins", "enabled")
        deshabilitados = yaml_lista(texto, "plugins", "disabled")
        if "repo-harness" in deshabilitados:
            nota(ROJO, "repo-harness está en plugins.disabled: instalado y muerto")
        elif "repo-harness" in habilitados:
            nota(VERDE, "repo-harness habilitado (plugins.enabled)")
        else:
            nota(ROJO, "repo-harness no está en plugins.enabled: los plugins generales son opt-in → `hermes plugins enable repo-harness`")

    # 3. Skills del repo: sin trust, Hermes no las carga
    raiz_skills = [(REPO_ROOT / r) for r in ((config or {}).get("skills") or {}).get("roots") or []]
    if any(r.is_dir() and any(r.rglob("SKILL.md")) for r in raiz_skills):
        confiados = yaml_lista(texto, "skills", "trusted_project_dirs")
        if any(Path(os.path.expanduser(c)).resolve() == REPO_ROOT for c in confiados):
            nota(VERDE, "skills del repo confiadas (skills.trusted_project_dirs)")
        else:
            nota(ROJO, f"skills del repo sin confiar: Hermes no las carga → `hermes skills trust {REPO_ROOT}`")

    # 4. Qué archivo de contexto carga Hermes DE VERDAD (gana el primero que exista)
    for tapa in (".hermes.md", "HERMES.md"):
        if (REPO_ROOT / tapa).is_file():
            nota(ROJO, f"`{tapa}` existe: Hermes carga ése y NO AGENTS.md. Las reglas del arnés quedan afuera.")
    if (REPO_ROOT / "CLAUDE.md").is_file() and (REPO_ROOT / "AGENTS.md").is_file():
        nota(AMARILLO, "hay CLAUDE.md y AGENTS.md: Hermes sólo carga AGENTS.md (y nunca resuelve `@imports`)")
    if not yaml_lista(texto, "security", "protected_instruction_extra_patterns"):
        nota(AMARILLO, "`.hermes.md` no está en security.protected_instruction_extra_patterns: el agente puede "
                       "crear uno sin aprobación y tapar AGENTS.md")

    # 5. Memoria: cerca del tope, o con algo que el arnés prohíbe ya guardado de antes
    mem_dir = home / "memories"
    for nombre, clave, defecto in (("MEMORY.md", "memory_char_limit", 2200), ("USER.md", "user_char_limit", 1375)):
        f = mem_dir / nombre
        if not f.is_file():
            continue
        contenido = f.read_text(encoding="utf-8", errors="replace")
        tope = yaml_int(texto, clave, defecto)
        uso = len(contenido) / tope if tope else 0
        nota(AMARILLO if uso > 0.9 else VERDE, f"{nombre}: {len(contenido)}/{tope} caracteres ({uso:.0%})"
             + (" — casi lleno: Hermes rechaza las escrituras nuevas, no compacta" if uso > 0.9 else ""))
        hit = first_match(((config or {}).get("memory") or {}).get("deny"), contenido)
        if hit:
            nota(ROJO, f"{nombre} YA contiene algo que el arnés prohíbe [{hit.get('id')}]: entra en cada sesión. "
                       "Quitalo con `/memory` (el freno sólo mira escrituras nuevas).")

    # 6. Shell hooks: sin consentimiento, en gateway y cron se saltean
    allow = home / "shell-hooks-allowlist.json"
    if "scripts/hook.py" in texto and not allow.is_file():
        nota(AMARILLO, "hay shell hooks del arnés en config.yaml y ningún consentimiento guardado: "
                       "en gateway/cron se saltean sin `hooks_auto_accept` o HERMES_ACCEPT_HOOKS=1")

    for nivel, msg in hallazgos:
        print(f"  {nivel} {msg}")
    rojos = sum(1 for n, _ in hallazgos if n == ROJO)
    print(f"\ndoctor: {rojos} rojo(s), {sum(1 for n, _ in hallazgos if n == AMARILLO)} aviso(s).")
    return 1 if rojos else 0


if __name__ == "__main__":
    sys.exit(main())
