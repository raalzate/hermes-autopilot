#!/usr/bin/env python3
"""
El barrido de deriva: lo que se degrada sin que ningún cambio lo rompa.

    python3 scripts/drift.py [--hoy AAAA-MM-DD]

El gate mide un cambio. Hay cosas que se pudren sin cambio: un STATUS.md que dice «verde» desde
hace dos meses (y el plugin se lo inyecta al agente al abrir cada sesión como verdad de hoy), o
una regla que nunca cazó nada en el historial (¿tiene cicatriz detrás, o se instaló porque sí?
P17). Es la etapa «continua» del ciclo (docs/guias-y-sensores.md).

Por qué NO es una señal del gate: depende del reloj. Un gate que se pone rojo porque pasó un
martes, sin que nadie cambiara nada, enseña a ignorar el gate. Lo corre `drift.runner`, programado.

Qué mide (todo sale de `drift` en el config; sin la clave, no corre):
  - la edad del veredicto de `status.file` contra `drift.statusMaxAgeDays` → ROJO si venció;
  - las reglas de `patterns` que no casan con ninguna línea agregada o quitada en los últimos
    `drift.historyCommits` commits → AVISO, no rojo: puede ser una regla sin cicatriz o una que
    ya ganó (nadie lo vuelve a intentar). Decide un humano.

Exit: 0 = sin deriva (o sólo avisos) · 1 = deriva que atender. Corre en CI, no dentro de Hermes:
el contrato de los frenos no aplica.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from harness.core import REPO_ROOT, CONFIG_PATH  # noqa: E402
from harness.rules import _re  # noqa: E402


def edad_del_veredicto(config: dict, texto: str | None, hoy: dt.date) -> tuple[list[str], list[str]]:
    """(rojos, verdes) sobre el texto de `status.file` (None = no existe)."""
    spec, archivo = config.get("drift") or {}, (config.get("status") or {}).get("file")
    rx, maximo = _re(spec.get("statusDatePattern", "")), int(spec.get("statusMaxAgeDays") or 0)
    if not (archivo and rx and maximo):
        return [], []
    if texto is None:
        return [f"`{archivo}` no existe: el plugin no tiene veredicto que mostrarle al agente."], []
    m = rx.search(texto)
    try:
        fecha = dt.date.fromisoformat(m.group(1)) if m else None
    except (ValueError, IndexError):
        fecha = None
    if fecha is None:
        return [f"`{archivo}` no declara la fecha de su veredicto (`drift.statusDatePattern`): sin fecha, "
                "nadie sabe si sigue siendo cierto."], []
    dias = (hoy - fecha).days
    if dias > maximo:
        return [f"`{archivo}` declara un veredicto de hace {dias} días (máximo {maximo}). El agente lo lee "
                "al abrir la sesión como si fuera de hoy: corré el gate y actualizalo."], []
    return [], [f"el veredicto de `{archivo}` tiene {dias} día(s) (máximo {maximo})"]


def reglas_sin_cicatriz(config: dict, log: str) -> list[dict]:
    """Las reglas de `patterns` que no casan con ninguna línea +/- de `git log -p`.

    El archivo sale de `diff --git a/… b/…`, y `---`/`+++` sólo son encabezado ANTES del primer
    `@@`: adentro de un hunk, una línea quitada `-- comentario` (SQL, Lua) se ve como `--- …`, y
    leerla como encabezado sacaba del ámbito al resto del hunk."""
    reglas = []
    for r in config.get("patterns") or []:
        rx = _re(r.get("pattern", ""), 0 if r.get("caseSensitive") else re.I)
        if rx:
            reglas.append((r, rx, [p for p in (_re(x) for x in r.get("paths") or []) if p]))
    vistas: set[int] = set()
    archivo, encabezado = "", False
    for linea in log.splitlines():
        if linea.startswith("diff --git "):
            m = re.search(r" b/(.*)$", linea)
            archivo, encabezado = (m.group(1) if m else ""), True
            continue
        if encabezado:
            encabezado = not linea.startswith("@@")
            continue
        if not linea[:1] in ("+", "-"):
            continue
        for i, (r, rx, rutas) in enumerate(reglas):
            if i not in vistas and (not rutas or any(p.search(archivo) for p in rutas)) and rx.search(linea[1:]):
                vistas.add(i)
        if len(vistas) == len(reglas):
            break
    return [r for i, (r, _, _) in enumerate(reglas) if i not in vistas]


def main(argv: list[str]) -> int:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("drift: OMITIDO — no hay config legible.")
        return 0
    spec = config.get("drift")
    if not spec:
        print("drift: OMITIDO — el repo no declara `drift`.")
        return 0
    hoy = dt.date.fromisoformat(argv[argv.index("--hoy") + 1]) if "--hoy" in argv else dt.date.today()

    archivo = (config.get("status") or {}).get("file")
    p = REPO_ROOT / archivo if archivo else None
    texto = p.read_text(encoding="utf-8", errors="replace") if p and p.is_file() else None
    rojos, verdes = edad_del_veredicto(config, texto, hoy)
    avisos: list[str] = []

    n = int(spec.get("historyCommits") or 0)
    if n > 0 and config.get("patterns"):
        log = subprocess.run(["git", "log", "-p", "--no-color", "--format=", f"-n{n}"], cwd=REPO_ROOT,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        if log.returncode != 0:
            avisos.append("no pude leer el historial de git: las reglas sin cicatriz no se midieron.")
        else:
            nunca = reglas_sin_cicatriz(config, log.stdout)
            avisos += [f"la regla `{r.get('id', r.get('pattern'))}` no casó con ninguna línea en los últimos {n} "
                       "commits. ¿Tiene cicatriz detrás (P17), o ya ganó? Decidilo y dejalo escrito." for r in nunca]
            if not nunca:
                verdes.append(f"las {len(config['patterns'])} reglas de contenido cazaron algo en los últimos {n} commits")

    for v in verdes:
        print(f"  ✓ {v}")
    for a in avisos:
        print(f"  ! {a}")
    if rojos:
        for r in rojos:
            print(f"  ✗ {r}")
        print(f"\nDERIVA — {len(rojos)} cosa(s) se degradaron sin que ningún cambio las rompiera. {spec.get('reason', '')}".rstrip())
        return 1
    print(f"\nSIN DERIVA{f' ({len(avisos)} aviso(s) para que decida un humano)' if avisos else ''}.")
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
