#!/usr/bin/env python3
"""
La prueba de vida del self-test: cada mutación del arnés tiene que ponerlo ROJO.

    python3 scripts/mutations.py

Un self-test verde dice "los frenos muerden" sólo si el self-test mismo muerde. Cada mutación
rompe un freno a propósito —en una COPIA temporal del repo (P7)— y exige que el self-test lo
note. Una mutación que sobrevive es un freno que se puede romper sin que nadie se entere.

Las mutaciones anclan en líneas concretas del código de ESTE repo: si un refactor mueve el ancla,
la mutación sale "ancla perdida" y es rojo — se actualiza el ancla, no se borra la mutación.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# (archivo, ancla, reemplazo): qué se rompe y dónde.
CODIGO = {
    "el freno de terminal deja pasar todo": ("plugin/harness/guards.py", "    cmd = command_of(config, ev)\n    if not cmd:", "    cmd = ''\n    if not cmd:"),
    "pre_tool_call sin _seguro": ("plugin/__init__.py", "@_seguro\ndef on_pre_tool_call", "def on_pre_tool_call"),
    "el shell hook sale 1 en vez de 2": ("scripts/hook.py", "                return 2", "                return 1"),
    "rutas protegidas apagadas": ("plugin/harness/guards.py", '    hit = first_match([r for r in reglas if not r.get("outsideRepo")], rel)', "    hit = None"),
    "freno de memoria desenchufado": ("plugin/harness/guards.py", '"memory": [memory_guard],', '"memory": [],'),
    "skill_manage: no mira los argumentos anidados": ("plugin/harness/core.py", "                elif isinstance(x, (dict, list, tuple)):\n                    walk(x)", "                elif False:\n                    walk(x)"),
    "pre_verify nunca sigue el turno": ("plugin/harness/turn.py", "    if not m or not m.exists():\n        return None", "    return None"),
    "un block sin mensaje (Hermes lo ignora)": ("plugin/harness/core.py", '"message": self.message or "Bloqueado por el arnés del repo."', '"message": self.message'),
    "ruta de Windows tomada como del repo": ("plugin/harness/core.py", '    if is_win_abs and os.name != "nt":', "    if False:"),
    "cron sin intervalo mínimo": ("plugin/harness/guards.py", "        if cada is not None and cada < minimo:", "        if False:"),
    "terminal.ask nunca escala": ("plugin/harness/guards.py", '    ask = first_match(t.get("ask"), comparable)', "    ask = None"),
    "el lint no mira el escáner de Hermes": ("plugin/harness/rules.py", '    for r in ctx.get("blockedPatterns") or []:', "    for r in []:"),
    # Los hallazgos de la revisión del 2026-09-30, reintroducidos: cada uno tiene que ser rojo.
    "patch V4A: sólo se mira `path`": ("plugin/harness/core.py", "    for texto in _patch_texts(config, ev):\n        for patron in", "    for texto in []:\n        for patron in"),
    "patterns sin re.M (sólo la primera línea)": ("plugin/harness/guards.py", "            flags = re.M | (0 if", "            flags = (0 if"),
    "patterns ignora exceptPaths": ("plugin/harness/guards.py", '            if _casa_alguna(regla.get("exceptPaths"), rel):\n                continue', "            pass"),
    "memoria/skills miran también lo que se borra": ("plugin/harness/core.py", "            if accion.lower() in borrar:\n                return", "            pass"),
    # Apaga la función ENTERA: con Hermes instalado, su propia resolución cubre el respaldo de
    # TERMINAL_CWD, y mutar sólo el respaldo sobrevivía (una mutación que depende de la máquina).
    "el plugin usa el cwd del proceso, no el de la sesión": ("plugin/__init__.py", "    try:\n        from tools.file_tools_paths import _authoritative_workspace_root", "    return ''\n    try:\n        from tools.file_tools_paths import _authoritative_workspace_root"),
    "marcador del gate ignora worktrees": ("plugin/harness/core.py", "        g = git_dir(root)\n        if g is not None:", "        g = None\n        if g is not None:"),
    "la terminal escribe rutas protegidas por redirección": ("plugin/harness/guards.py", '    for patron in t.get("redirectTargets") or []:', "    for patron in []:"),
    "reglas de fuera del repo contra el texto crudo": ("plugin/harness/guards.py", "    nombres = [raw]\n    a = abs_path(raw, root, cwd)", "    nombres = [raw]\n    a = ''"),
    "cron: listas y rangos sin intervalo": ("plugin/harness/guards.py", "        huecos = [b - a for a, b in zip(mins, mins[1:])] + [60 - mins[-1] + mins[0]]", "        huecos = [60]"),
    "pre-commit sin renames": ("scripts/githooks.py", '"--name-only", "--diff-filter=ACMR").splitlines() if f]\n        fallas = pre_commit', '"--name-only", "--diff-filter=ACM").splitlines() if f]\n        fallas = pre_commit'),
    "pre-commit lee el disco y no el índice": ("scripts/githooks.py", '    p = subprocess.run(["git", "show", f":{f}"], cwd=REPO_ROOT, capture_output=True)', '    p = subprocess.run(["git", "show", "--no-such-flag"], cwd=REPO_ROOT, capture_output=True)'),
    "mensajes de commit comparados como comandos": ("plugin/harness/guards.py", "    comparable = _para_comparar(cmd, config)", "    comparable = cmd"),
    "el gate imprime en la codificación de la consola (Windows cp1252)": ("scripts/gate.py", "    for _s in (sys.stdin, sys.stdout, sys.stderr):", "    for _s in ():"),
    # Lo traído de agent-harness: cada pieza nueva tiene que poder romperse sólo con el self-test en rojo.
    "COHERENCIA no mira los bloques de shell": ("plugin/harness/rules.py", "            en_bloque = not en_bloque and m.group(1).lower() in vallas", "            en_bloque = False"),
    "COHERENCIA no mira los reason del config": ("plugin/harness/rules.py", '                        for comando in re.findall(r"`([^`]+)`", v):', "                        for comando in []:"),
    "PERFIL deja pasar las reglas": ("plugin/harness/rules.py", 'for k in spec.get("forbiddenKeys") or [] if not vacio', "for k in [] if not vacio"),
    "pre-push deja empujar a la rama protegida": ("scripts/githooks.py", "            if rama in protegidas and rama not in chocan:", "            if False:"),
    "deriva: un veredicto vencido pasa": ("scripts/drift.py", "    if dias > maximo:", "    if False:"),
    "deriva: el historial no cuenta": ("scripts/drift.py", "                vistas.add(i)", "                pass"),
    "mapa: un hook de git sin clasificar pasa": ("scripts/map.py", '                sin.append(f"hook de git', '                pass  # sin.append(f"hook de git'),
    "timing no mide": ("scripts/timing.py", "                    tiempos.append((time.perf_counter() - t0) * 1000)", "                    tiempos.append(0.0)"),
    # La autonomía (P21): el loop, la CLI, el panel y el registro de eventos.
    "loop: el mismo rojo no escala (P16)": ("scripts/loop.py", "    if limite > 0 and len(firmas) >= limite and len(set(firmas[-limite:])) == 1:", "    if False:"),
    "loop: sin tope de iteraciones": ("scripts/loop.py", "    if len(intentos) >= tope:", "    if False:"),
    "loop: ignora el freno de mano": ("scripts/loop.py", "    if parar:\n        return \"parado\"", "    if False:\n        return \"parado\""),
    "loop: le cree al agente y no al gate": ("scripts/loop.py", '"green": rc_gate == 0,', '"green": rc_agente == 0,'),
    "loop: la duración cambia la firma del rojo": ("scripts/loop.py", r'(?:\s+\(exit\b.*|:\s.*)?$', r'$'),
    "cli: acepta un ejemplo que no frena": ("scripts/cli.py", "        if hizo != espera:", "        if False:"),
    "cli: no mira los inocentes ni el gate": ("scripts/cli.py", "    for texto in dict.fromkeys(inocentes):", "    for texto in []:"),
    "panel: escucha en todas las interfaces": ("scripts/panel.py", 'HOST = "127.0.0.1"', 'HOST = "0.0.0.0"'),
    "eventos: el plugin no registra los bloqueos": ("plugin/__init__.py", "    if d.block or d.approve:\n        # Lo que el freno", "    if False:\n        # Lo que el freno"),
    "rm con varios argumentos: sólo se mira el grupo entero": ("plugin/harness/guards.py", "        for destino in (tok for grupo in destinos for tok in grupo.split()):", "        for destino in destinos:"),
    "loop: no mira los intocables": ("scripts/loop.py", "        if tocados:\n            # Ni se corre el gate", "        if False:\n            # Ni se corre el gate"),
    "loop: un verde adulterado vale": ("scripts/loop.py", '    if intentos and intentos[-1].get("tampered"):', '    if False:'),
    "loop: dos loops en el mismo repo": ("scripts/loop.py", "    if candado is not None and candado_vivo(candado, spec):", "    if False:"),
    "freno de lectura desenchufado": ("plugin/harness/guards.py", '"read": [read_guard],', '"read": [],'),
    "la terminal lee secretos sin freno": ("plugin/harness/guards.py", '    for patron in t.get("readTargets") or []:', "    for patron in []:"),
    "casos: no compara el resultado": ("scripts/casos.py", '        if obs["resultado"] != corrida.get("resultado"):', "        if False:"),
    "casos: los inocentes del caso no se prueban": ("scripts/casos.py", '    for donde, lista in (c.get("inocentes") or {}).items():', "    for donde, lista in {}.items():"),
    "eventos: el registro crece sin techo": ("plugin/harness/events.py", "        if p.exists() and p.stat().st_size > tope:", "        if False:"),
}


def _config(fn):
    def aplicar(root: Path):
        p = root / ".hermes" / "harness.config.json"
        c = json.loads(p.read_text(encoding="utf-8"))
        fn(c)
        p.write_text(json.dumps(c), encoding="utf-8")
    return aplicar


CONFIG = {
    "una regla sin example": _config(lambda c: c["terminal"]["deny"][0].pop("example")),
    "una señal sin why": _config(lambda c: c["gate"]["signals"][0].pop("why")),
    "un inocente que muerde": _config(lambda c: c["terminal"]["innocent"].append(c["terminal"]["deny"][1]["example"])),
    "la deriva encendida y nadie que la corra": _config(lambda c: c["drift"].update(command="scripts/otro.py")),
    "una skill fuera del mapa": _config(lambda c: c["taxonomy"]["skills"].pop("lesson")),
    "un loop sin tope": _config(lambda c: c["loop"].update(sameFailureLimit=0)),
}


# Mutaciones de ramas que sólo EXISTEN fuera de una plataforma: ahí el código mutado nunca corre y
# la mutación es un no-op, no un freno sin prueba. Se reporta "no aplica" con el motivo — visible,
# nunca contada como verde ni como sobreviviente. Lo destapó la matriz de CI en Windows.
NO_APLICA = {
    "ruta de Windows tomada como del repo": ("nt", "la rama sólo corre fuera de Windows (una ruta C:\\ vista desde POSIX)"),
}


def probar(nombre: str, mut) -> tuple[str, str]:
    plataforma, motivo = NO_APLICA.get(nombre, (None, ""))
    if plataforma == os.name:
        return nombre, f"no aplica en {os.name}: {motivo}"
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "repo"
        shutil.copytree(REPO, dst, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        subprocess.run(["git", "init", "-q"], cwd=dst, capture_output=True)
        if callable(mut):
            mut(dst)
        else:
            f, ancla, nuevo = mut
            texto = (dst / f).read_text(encoding="utf-8")
            if ancla not in texto:
                return nombre, "ancla perdida"
            (dst / f).write_text(texto.replace(ancla, nuevo, 1), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k not in ("HARNESS_REPO",)}
        env["HARNESS_NESTED"] = "1"  # sin la sección de portado: acá se prueba el self-test, no el instalador
        p = subprocess.run([sys.executable, "scripts/selftest.py"], cwd=dst, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        return nombre, "roja" if p.returncode != 0 else "SOBREVIVIÓ"


def main() -> int:
    todas = list(CODIGO.items()) + list(CONFIG.items())
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as ex:
        resultados = list(ex.map(lambda nm: probar(*nm), todas))
    malas = [(n, r) for n, r in resultados if r != "roja" and not r.startswith("no aplica")]
    for n, r in resultados:
        print(f"  {'✓' if r == 'roja' else ('·' if r.startswith('no aplica') else '✗')} {n}: {r}")
    if malas:
        print(f"\nmutations: {len(malas)} de {len(todas)} no pusieron rojo el self-test.")
        return 1
    print(f"\nmutations: las {len(todas)} mutaciones ponen rojo el self-test.")
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
