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
    ya ganó (nadie lo vuelve a intentar). Decide un humano;
  - cada dependencia fijada de las integraciones (las habilitadas y las del catálogo) contra la base
    pública de vulnerabilidades OSV → ROJO si la versión fijada tiene una conocida (es código que
    corre con tus credenciales), y AVISO si salió una versión nueva: se prueba con
    `integ_run.py --probe` antes de subirla, nunca sola. Sin red, AVISO: no se midió.

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


ECOSISTEMA = {"npm": "npm", "pypi": "PyPI"}


def dependencias(config: dict) -> list[tuple[str, str, str, str]]:
    """[(origen, ecosistema, paquete, versión)] de las integraciones habilitadas y del catálogo."""
    out = []
    habilitadas = ((config.get("integrations") or {}).get("enabled") or {})
    fuentes = [(f"integración `{i}`", e) for i, e in habilitadas.items() if isinstance(e, dict)]
    catalogo = Path(__file__).resolve().parent.parent / "plantillas" / "integraciones"
    for f in sorted(catalogo.glob("*.json")):
        try:
            fuentes.append((f"catálogo `{f.stem}`", json.loads(f.read_text(encoding="utf-8"))))
        except ValueError:
            continue
    for origen, m in fuentes:
        for r in m.get("requires") or []:
            if r.get("kind") in ECOSISTEMA and r.get("package") and r.get("version"):
                out.append((origen, ECOSISTEMA[r["kind"]], r["package"], str(r["version"])))
    return sorted(set(out))


def _http_json(url: str, cuerpo: dict | None = None):
    import urllib.request
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, headers={"Content-Type": "application/json", "User-Agent": "repo-harness-drift"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 — URLs fijas de OSV, npm y PyPI
        return json.loads(r.read().decode("utf-8"))


def consultar_osv(deps: list[tuple[str, str, str, str]]) -> list[list[str]]:
    """Los ids de vulnerabilidades conocidas de cada (ecosistema, paquete, versión), en orden."""
    res = _http_json("https://api.osv.dev/v1/querybatch", {"queries": [
        {"package": {"name": p, "ecosystem": e}, "version": v} for _, e, p, v in deps]})
    return [[x.get("id", "?") for x in (r or {}).get("vulns") or []] for r in res.get("results") or []]


def ultima_version(ecosistema: str, paquete: str) -> str:
    if ecosistema == "npm":
        return str(_http_json(f"https://registry.npmjs.org/{paquete}/latest").get("version", ""))
    return str(_http_json(f"https://pypi.org/pypi/{paquete}/json").get("info", {}).get("version", ""))


def integraciones(config: dict, osv=consultar_osv, ultima=ultima_version) -> tuple[list[str], list[str], list[str]]:
    """(rojos, avisos, verdes) de las dependencias de las integraciones. `osv` y `ultima` se
    inyectan: el self-test prueba la lógica sin red."""
    deps = dependencias(config)
    if not deps:
        return [], [], []
    try:
        vulns = osv(deps)
    except (OSError, ValueError) as e:
        return [], [f"no pude consultar OSV ({e}): las dependencias de las integraciones no se midieron."], []
    rojos = [f"{o}: {p}@{v} ({e}) tiene vulnerabilidades conocidas: {', '.join(ids[:5])}. Subí la versión "
             "(probala con `integ_run.py --probe`) o deshabilitá la integración." for (o, e, p, v), ids in zip(deps, vulns) if ids]
    avisos = []
    for o, e, p, v in deps:
        try:
            u = ultima(e, p)
        except (OSError, ValueError):
            continue
        if u and u != v:
            avisos.append(f"{o}: {p} fijado en {v}, salió {u}. Probalo con `integ_run.py --probe` antes de subirlo.")
    verdes = [] if rojos else [f"{len(deps)} dependencias de integraciones sin vulnerabilidades conocidas (OSV)"]
    return rojos, avisos, verdes


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

    if "--sin-red" not in argv:
        r_i, a_i, v_i = integraciones(config)
        rojos += r_i
        avisos += a_i
        verdes += v_i

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
