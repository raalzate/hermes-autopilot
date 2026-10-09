#!/usr/bin/env python3
"""
Instala el arnés en otro repo. DRY-RUN por defecto (P9): muestra la lista y no toca nada.

    python3 scripts/install.py <repo> [--profile python] [--apply] [--upgrade] [--link-plugin]

    --profile      hechos del stack (plantillas/perfiles/<nombre>.json): extensiones, lockfiles,
                   el comando de tests. Nunca reglas: las reglas del repo se escriben con sus
                   cicatrices, no se heredan de otro.
    --apply        ejecuta el plan. Sin esto, sólo lo imprime.
    --upgrade      reemplaza el CÓDIGO del arnés (`.hermes/harness/`) por esta versión. Nunca toca
                   el config, AGENTS.md, las skills ni los docs del repo: ésos son del repo.
    --link-plugin  enlaza `$HERMES_HOME/plugins/repo-harness` al plugin instalado (copia si el
                   sistema no permite symlinks). Es lo único que escribe FUERA del repo, y por
                   eso va con su propia bandera.

Nunca sobreescribe un archivo que ya existe: lo reporta como `=` y sigue. El config de Hermes
(`~/.hermes/config.yaml`) no se edita jamás: se imprime qué agregar.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent  # el repo del arnés (o una copia instalada)
PLANT = HOME / "plantillas"
CODE_FILES = ["gate.py", "lint.py", "linkcheck.py", "selftest.py", "hook.py", "githooks.py", "install.py", "doctor.py",
              "drift.py", "map.py", "timing.py", "cli.py", "loop.py", "panel.py", "integ.py", "integ_run.py"]
DEST_CODE = Path(".hermes") / "harness"


def merge_profile(base: dict, perfil: dict) -> dict:
    """El perfil completa huecos del config base; nunca borra una regla del base."""
    cfg = json.loads(json.dumps(base))
    g = cfg.setdefault("gate", {})
    if perfil.get("codeExtensions"):
        g["codeExtensions"] = perfil["codeExtensions"]
    if perfil.get("codeGlobs"):
        g["codeGlobs"] = perfil["codeGlobs"]
    for s in perfil.get("signals") or []:
        g.setdefault("signals", []).append(s)
    cfg.setdefault("protectedPaths", []).extend(perfil.get("protectedPaths") or [])
    if perfil.get("commitCodePattern"):
        cfg.setdefault("commitMsg", {})["codePattern"] = perfil["commitCodePattern"]
    # La medición de latencia tiene que escribir CÓDIGO del stack: con un archivo cualquiera,
    # `transform_tool_result` toma el atajo y se mide el camino que no cuesta nada.
    probe = cfg.get("observability", {}).get("probe")
    if isinstance(probe, dict) and g.get("codeExtensions"):
        probe["filePath"] = f"{(g.get('codeGlobs') or [''])[0]}x{g['codeExtensions'][0]}"
    cfg["$profile"] = perfil.get("name")
    return cfg


def plan(target: Path, profile: str | None, upgrade: bool) -> list[tuple[str, Path, object]]:
    """[(acción, destino, fuente)] — acción: '+' crear, '~' reemplazar código, '=' ya existe."""
    items: list[tuple[str, Path, object]] = []

    def add(dst: Path, src, codigo: bool = False):
        existe = dst.exists()
        if existe and not (codigo and upgrade):
            items.append(("=", dst, src))
        else:
            items.append(("~" if existe else "+", dst, src))

    for d in ("plugin",):
        for f in sorted((HOME / d).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                add(target / DEST_CODE / f.relative_to(HOME), f, codigo=True)
    for name in CODE_FILES:
        if (HOME / "scripts" / name).is_file():
            add(target / DEST_CODE / "scripts" / name, HOME / "scripts" / name, codigo=True)
    for f in sorted(PLANT.rglob("*")):
        if f.is_file():
            add(target / DEST_CODE / "plantillas" / f.relative_to(PLANT), f, codigo=True)

    base = json.loads((PLANT / "harness.config.json").read_text(encoding="utf-8"))
    if profile:
        pf = PLANT / "perfiles" / f"{profile}.json"
        if not pf.is_file():
            disponibles = ", ".join(p.stem for p in (PLANT / "perfiles").glob("*.json"))
            sys.exit(f"install: no existe el perfil `{profile}`. Disponibles: {disponibles}")
        base = merge_profile(base, json.loads(pf.read_text(encoding="utf-8")))
    add(target / ".hermes" / "harness.config.json", base)

    add(target / "AGENTS.md", PLANT / "AGENTS.md")
    add(target / "STATUS.md", PLANT / "STATUS.md")
    add(target / "docs" / "gotchas.md", PLANT / "gotchas.md")
    add(target / ".hermes" / "loop" / "tasks.md", PLANT / "tasks.md")
    add(target / ".github" / "workflows" / "harness.yml", PLANT / "ci.yml")
    add(target / ".github" / "workflows" / "harness-drift.yml", PLANT / "drift.yml")
    for h in ("pre-commit", "commit-msg", "pre-push"):
        add(target / ".githooks" / h, HOME / ".githooks" / h)
    for f in sorted((HOME / ".hermes" / "skills").rglob("*")):
        if f.is_file():
            add(target / ".hermes" / "skills" / f.relative_to(HOME / ".hermes" / "skills"), f)
    return items


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser()


def link_plugin(target: Path, apply: bool) -> str:
    dst = hermes_home() / "plugins" / "repo-harness"
    src = (target / DEST_CODE / "plugin").resolve()
    if dst.exists() or dst.is_symlink():
        return f"=  {dst} (ya existe: no se toca; si apunta a otro repo, decidilo vos)"
    if not apply:
        return f"+  {dst} → {src}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        dst.symlink_to(src, target_is_directory=True)
        return f"+  {dst} → {src} (symlink)"
    except OSError:
        # Windows sin privilegio de symlink: copia (el plugin es autocontenido: trae su `harness/`).
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        return f"+  {dst} (copia: re-ejecutá con --link-plugin tras un --upgrade)"


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Instala el arnés en otro repo (dry-run por defecto).")
    ap.add_argument("repo")
    ap.add_argument("--profile")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--upgrade", action="store_true")
    ap.add_argument("--link-plugin", action="store_true")
    if not argv:
        print(__doc__)
        return 1
    a = ap.parse_args(argv)
    target = Path(a.repo).expanduser().resolve()
    if not target.is_dir():
        print(f"install: {target} no es un directorio.")
        return 1
    profile, apply, upgrade = a.profile, a.apply, a.upgrade

    if a.link_plugin:
        # Paso aparte a propósito: es lo único que escribe fuera del repo.
        if not (target / DEST_CODE / "plugin" / "__init__.py").is_file():
            print(f"install: {target} no tiene el arnés instalado; corré primero sin --link-plugin.")
            return 1
        print(("" if apply else "DRY-RUN — ") + "plugin de Hermes:\n" + link_plugin(target, apply))
        return 0

    items = plan(target, profile, upgrade)
    print(f"{'Instalando' if apply else 'DRY-RUN (nada se escribe; --apply para ejecutar)'} en {target}"
          f"{f' · perfil {profile}' if profile else ''}\n")
    for accion, dst, _ in items:
        print(f"{accion}  {dst.relative_to(target)}")
    if apply:
        for accion, dst, src in items:
            if accion == "=":
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(src, dict):
                dst.write_text(json.dumps(src, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            else:
                shutil.copy2(src, dst)
                if dst.parent.name == ".githooks":
                    dst.chmod(0o755)

    if (target / "CLAUDE.md").is_file() and not (target / "AGENTS.md").exists():
        print("\n⚠️  El repo tiene CLAUDE.md: Hermes lo lee SÓLO desde el cwd, sólo si no hay AGENTS.md, y "
              "no resuelve sus `@imports`. Pasá las reglas a AGENTS.md (se instala uno nuevo).")
    creados = sum(1 for a, *_ in items if a != "=")
    print(f"\n{creados} a escribir, {len(items) - creados} ya existían (no se tocan).")
    print(f"""
Siguiente (lo hace el humano — el instalador no toca el config de Hermes):
  1. cd {target} && python3 .hermes/harness/scripts/githooks.py install
  2. hermes skills trust {target}            # las skills de .hermes/skills/ del repo
  3. python3 .hermes/harness/scripts/install.py {target} --link-plugin --apply
     hermes plugins enable repo-harness     # los plugins generales son opt-in
  4. python3 .hermes/harness/scripts/gate.py
  5. Las reglas de ESTE repo, cada una con su `example` (la CLI la prueba antes de escribirla):
     python3 .hermes/harness/scripts/cli.py rule add terminal.deny --id … --pattern … --example … --reason …
  6. Panel en vivo y loop autónomo:
     python3 .hermes/harness/scripts/cli.py panel
     python3 .hermes/harness/scripts/cli.py task add "…" && python3 .hermes/harness/scripts/cli.py loop""")
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
