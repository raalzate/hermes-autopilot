#!/usr/bin/env python3
"""
El arnés como sistema de control: cada pieza con su dirección, su tipo y su etapa del ciclo.

    python3 scripts/map.py

El marco de guías y sensores (docs/guias-y-sensores.md) pide mirar el arnés entero de una vez:
¿qué etapa no tiene ningún control?, ¿cuánto del arnés es inferencial y cuánto computacional?
`lint.py --rules` contesta qué reglas hay; esto contesta DÓNDE actúa cada pieza.

Tres ejes:
    dirección  guía (antes de decidir) · freno (decidido, no ejecutado) · sensor (después)
    tipo       computacional (determinista) · inferencial (un modelo que juzga)
    etapa      de la sesión al barrido continuo — la lista la declara `taxonomy.stages`

Agnóstico: el script no sabe qué hook de Hermes es qué. `taxonomy` dice cómo se clasifica cada
hook que el manifiesto del plugin declara, cada hook de git, cada skill, cada guía y cada
pipeline. Una pieza que la taxonomía no clasifica es ROJO: un control nuevo que nadie ubicó es
uno del que nadie sabe qué cubre. Las etapas vacías se informan (decidir si importan es de un
humano), no bloquean.

Exit: 0 = todo clasificado · 1 = hay piezas sin clasificar.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from harness.core import HARNESS_HOME, REPO_ROOT, CONFIG_PATH  # noqa: E402


def manifest_hooks(home: Path) -> list[str]:
    """`provides_hooks` de plugin.yaml, sin PyYAML (lista YAML de una columna)."""
    out, dentro = [], False
    try:
        lineas = (home / "plugin" / "plugin.yaml").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lineas:
        if re.match(r"^provides_hooks:\s*$", line):
            dentro = True
        elif dentro and re.match(r"^\s+-\s+\S+", line):
            out.append(line.split("-", 1)[1].strip())
        elif dentro and line.strip():
            dentro = False
    return out


def construir(config: dict, raiz: Path = REPO_ROOT, home: Path = HARNESS_HOME) -> dict | None:
    """El mapa como DATO. Sin `taxonomy` devuelve None: el repo no declaró cómo se lee su arnés,
    y eso no es un mapa vacío."""
    tax = config.get("taxonomy")
    if not isinstance(tax, dict):
        return None
    piezas: list[dict] = []
    sin: list[str] = []

    def agregar(nombre, c, tipo_def):
        etapas = c.get("stage")
        piezas.append({"nombre": nombre, "dir": c.get("direction", "?"), "tipo": c.get("kind", tipo_def),
                       "etapas": etapas if isinstance(etapas, list) else [etapas]})

    # Hooks del plugin: la dirección y la etapa las pone el HOOK de Hermes, no el freno.
    for h in manifest_hooks(home):
        c = (tax.get("events") or {}).get(h)
        if c:
            agregar(f"plugin · {h}", c, "computacional")
        else:
            sin.append(f"hook `{h}` del plugin: `taxonomy.events` no dice qué es")

    # Hooks de git: lo que hay en el directorio es lo que corre.
    dir_git = tax.get("gitHooksDir", ".githooks")
    if (raiz / dir_git).is_dir():
        for f in sorted(p.name for p in (raiz / dir_git).iterdir() if p.is_file()):
            c = (tax.get("gitHooks") or {}).get(f)
            if c:
                agregar(f"{dir_git}/{f}", c, "computacional")
            else:
                sin.append(f"hook de git `{dir_git}/{f}`: `taxonomy.gitHooks` no lo ubica")

    # Señales del gate: un sensor computacional en cada lugar donde corre el gate COMPLETO.
    for s in (config.get("gate") or {}).get("signals") or []:
        agregar(f"gate · {s.get('name')}", {"direction": "sensor", "stage": tax.get("gateStages") or []}, "computacional")

    # Skills: el lugar donde vive lo inferencial, así que cada una se declara.
    for root in (config.get("skills") or {}).get("roots") or []:
        d = raiz / root
        for sk in sorted(p.parent.name for p in d.glob("*/SKILL.md")) if d.is_dir() else []:
            c = (tax.get("skills") or {}).get(sk)
            if c:
                agregar(f"skill · {sk}", c, "inferencial")
            else:
                sin.append(f"skill `{root}/{sk}`: `taxonomy.skills` no la ubica")

    # Guías, pipelines y piezas sueltas: las declara la taxonomía tal cual, y tienen que existir.
    for grupo, dir_def, tipo_def in (("guides", "guía", "inferencial"), ("pipelines", "sensor", "computacional"),
                                     ("pieces", "?", "computacional")):
        for nombre, c in (tax.get(grupo) or {}).items():
            if nombre.startswith("$"):
                continue
            archivo = c.get("file", nombre)
            if not any((b / archivo).exists() for b in (raiz, home)):
                sin.append(f"`taxonomy.{grupo}` nombra `{archivo}`, que no existe")
            else:
                agregar(nombre, {"direction": dir_def, **c}, tipo_def)

    etapas = tax.get("stages") or sorted({e for p in piezas for e in p["etapas"]})
    for e in sorted({e for p in piezas for e in p["etapas"]} - set(etapas), key=str):
        sin.append(f"la etapa `{e}` no está en `taxonomy.stages`")
    for p in piezas:
        if p["dir"] not in ("guía", "freno", "sensor"):
            sin.append(f"`{p['nombre']}` tiene dirección `{p['dir']}`: es guía, freno o sensor")
    huecos = [e for e in etapas if not any(e in p["etapas"] for p in piezas)]
    return {"etapas": etapas, "piezas": piezas, "huecos": huecos, "sinClasificar": sin}


def main() -> int:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"map: OMITIDO — no pude leer el config ({e}).")
        return 0
    mapa = construir(config)
    if mapa is None:
        print("map: OMITIDO — el repo no declara `taxonomy`.")
        return 0
    print("Mapa del arnés — dirección · tipo · etapa (sale de `taxonomy` en el config)\n")
    for etapa in mapa["etapas"]:
        aca = [p for p in mapa["piezas"] if etapa in p["etapas"]]
        print(etapa)
        if not aca:
            print("  (ningún control)")
        for p in aca:
            print(f"  {p['dir']:<7} {p['tipo']:<14} {p['nombre']}")
    cuenta = lambda k, v: sum(1 for p in mapa["piezas"] if p[k] == v)  # noqa: E731
    print(f"\nTotales: {len(mapa['piezas'])} pieza(s) · guía {cuenta('dir', 'guía')} · freno {cuenta('dir', 'freno')}"
          f" · sensor {cuenta('dir', 'sensor')} · computacional {cuenta('tipo', 'computacional')}"
          f" · inferencial {cuenta('tipo', 'inferencial')}")
    if mapa["huecos"]:
        print(f"Huecos (etapas sin control, para que decida un humano): {' · '.join(mapa['huecos'])}")
    if mapa["sinClasificar"]:
        print("\nSIN CLASIFICAR — piezas del arnés que nadie ubicó en el mapa:")
        for s in mapa["sinClasificar"]:
            print(f"  ✗ {s}")
        print("\nUn control que nadie ubicó es uno del que nadie sabe qué cubre. Declaralo en `taxonomy`.")
        return 1
    print("\nMAPA COMPLETO — cada pieza tiene dirección, tipo y etapa.")
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
