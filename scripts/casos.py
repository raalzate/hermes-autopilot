#!/usr/bin/env python3
"""
Casos replicables: escenarios reales (programación, infraestructura, oficina, datos) corridos de
punta a punta por el loop autónomo, en un repo temporal con el arnés instalado.

    python3 scripts/casos.py                    corre TODOS y compara con lo esperado (señal del gate)
    python3 scripts/casos.py --list             el catálogo
    python3 scripts/casos.py infra-env-secretos oficina-reporte-ventas
    python3 scripts/casos.py preparar <id> <dir> [--hermes]   un sandbox para replicarlo a mano
    python3 scripts/casos.py readme [<id>…]     regenera el README de cada caso desde caso.json + agente.py

Cada caso vive en `casos/<id>/`:
    caso.json    historia, tarea, reglas que agrega (y sus inocentes), intocables y CORRIDAS esperadas
    semilla/     los archivos del repo al empezar (incluye `verificar.py`, el criterio de salida);
                 `dot.env` llega al sandbox como `.env` (versionado acá, lo frenaría el pre-commit)
    pendiente/   (opcional) cambios del humano SIN commitear al empezar
    agente.py    un agente determinista con modos (`JUGUETE=aprende|terco|atajo…`): cada acción pasa
                 por el plugin real (`casos/hermes_sim.py`), así los frenos muerden de verdad
    README.md    la historia, qué demuestra y cómo replicarlo — GENERADO (`casos.py readme`); el runner
                 exige que nombre cada modo y cada regla del caso

Qué se compara en cada corrida: el resultado del loop (verde · escalar · parado), cuántos intentos,
qué reglas mordieron (del registro de eventos) y si el loop vio intocables cambiados. Además, cada
regla que el caso agrega pasa por `cli.validar` antes de entrar: si su ejemplo no frena o muerde un
inocente, el caso está roto.

Exit: 0 = todos como se esperaba · 1 = alguno no.
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

HERE = Path(__file__).resolve().parent
HOME = HERE.parent
CASOS = HOME / "casos"
sys.path.insert(0, str(HOME / "plugin"))
sys.path.append(str(HERE))
import cli  # noqa: E402

CLAVES = ("id", "dominio", "titulo", "historia", "demuestra", "tarea", "corridas")


def catalogo() -> list[dict]:
    out = []
    for f in sorted(CASOS.glob("*/caso.json")):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            out.append({"id": f.parent.name, "_error": f"caso.json inválido: {e}"})
            continue
        c["_dir"] = f.parent
        out.append(c)
    return out


def problemas_de_forma(c: dict) -> list[str]:
    if c.get("_error"):
        return [c["_error"]]
    p = [f"falta `{k}`" for k in CLAVES if not c.get(k)]
    d = c["_dir"]
    if c.get("id") != d.name:
        p.append(f"`id` ({c.get('id')}) ≠ directorio ({d.name})")
    for f in ("agente.py", "README.md", "semilla/verificar.py"):
        if not (d / f).is_file():
            p.append(f"falta {f}")
    readme = (d / "README.md").read_text(encoding="utf-8") if (d / "README.md").is_file() else ""
    nombres = [f"`{r.get('modo')}`" for r in c.get("corridas") or []] + \
        [f"`{x.get('id')}`" for rs in (c.get("reglas") or {}).values() for x in rs]
    for n in nombres:
        if n not in readme:
            p.append(f"README.md no nombra {n}: el README y caso.json se desincronizaron")
    for r in c.get("corridas") or []:
        if r.get("resultado") not in ("verde", "escalar", "parado"):
            p.append(f"corrida `{r.get('modo')}`: resultado `{r.get('resultado')}` (verde · escalar · parado)")
    return p


FAMILIA_TXT = {"terminal.deny": "freno de terminal", "terminal.ask": "escala a un humano (en el loop: negado)",
               "protectedPaths": "ruta protegida (escribir)", "protectedReads": "lectura protegida",
               "patterns": "patrón prohibido al escribir", "memory.deny": "memoria persistente",
               "skills.deny": "skill", "cron.deny": "tarea programada", "routes": "ruta (guía)"}


def readme(c: dict) -> str:
    """El README del caso, generado de `caso.json` y del docstring de `agente.py`: una sola fuente."""
    import ast
    import re

    d = c["_dir"]
    doc = ast.get_docstring(ast.parse((d / "agente.py").read_text(encoding="utf-8"))) or ""
    modos: list[list[str]] = []
    for linea in doc.split("\n")[1:]:
        m = re.match(r"^\s{0,2}(\S+)\s{2,}(.*)$", linea)
        if m and not linea.startswith("   "):
            modos.append([m.group(1), m.group(2).strip()])
        elif modos and linea.strip():
            modos[-1][1] += " " + linea.strip()
    reglas = [f"| `{r['id']}` | {FAMILIA_TXT.get(fam, fam)} (`{fam}`) | {r.get('reason') or r.get('hint')} |"
              for fam, rs in (c.get("reglas") or {}).items() for r in rs]
    corridas = []
    for r in c["corridas"]:
        extra = ([f"muerden {', '.join(f'`{x}`' for x in r['frenos'])}"] if r.get("frenos") else []) + \
            (["el loop ve intocables cambiados"] if r.get("intocables") else [])
        corridas.append(f"| `{r['modo']}` | **{r['resultado']}** en {r.get('intentos', '?')} intento(s) | {'; '.join(extra) or '—'} |")
    locked = c.get("lockedPaths") or []
    archivos = lambda sub: sorted(str(p.relative_to(d / sub).as_posix()) for p in (d / sub).rglob("*") if p.is_file()) if (d / sub).is_dir() else []  # noqa: E731
    m0 = c["corridas"][0]["modo"]
    partes = [f"# {c['titulo']}", "", f"**Dominio:** {c['dominio']} · **Caso:** `{c['id']}`", "",
              "## La historia", "", c["historia"], "", "## Qué demuestra", "", c["demuestra"], "",
              "## La tarea que recibe el agente", "", f"> {c['tarea']}", "",
              "**Terminado** lo decide `verificar.py` (el gate del caso), no el agente. El agente no lo puede tocar: "
              "está en `loop.lockedPaths`" + (", igual que " + ", ".join(f"`{x}`" for x in locked) if locked else "") + ".", "",
              "## Las reglas que agrega", ""]
    if reglas:
        partes += ["| Regla | Tipo | Motivo (lo que lee el agente) |", "|---|---|---|", *reglas, "",
                   "Cada una pasa por `cli.validar` antes de entrar: si su ejemplo no frena, o muerde un inocente o el gate, "
                   "el caso está roto."]
    else:
        partes += ["Ninguna propia: usa lo que trae la plantilla instalada (y el loop)."]
    if c.get("inocentes"):
        partes += ["", "Inocentes que tienen que seguir pasando: " + ", ".join(f"`{x}`" for l in c["inocentes"].values() for x in l) + "."]
    partes += ["", "## Los modos del agente de juguete", "", *[f"- `{k}` — {v}" for k, v in modos], "",
               "## Lo que tiene que pasar", "", "| Modo | Resultado | Además |", "|---|---|---|", *corridas, "",
               "## Los archivos", "", f"- `semilla/`: {', '.join(f'`{a}`' for a in archivos('semilla'))}."]
    if archivos("pendiente"):
        partes += [f"- `pendiente/` (trabajo del humano **sin commitear** al empezar): {', '.join(f'`{a}`' for a in archivos('pendiente'))}."]
    partes += ["", "## Replicarlo", "", "```bash",
               f"python3 scripts/casos.py {c['id']}                 # todas las corridas, comparadas con lo esperado",
               f"python3 scripts/casos.py preparar {c['id']} /tmp/{c['id']}",
               f"cd /tmp/{c['id']}",
               "python3 .hermes/harness/scripts/cli.py panel       # en otra terminal",
               f"JUGUETE={m0} python3 .hermes/harness/scripts/cli.py loop --apply", "```", "",
               f"Con Hermes de verdad: `python3 scripts/casos.py preparar {c['id']} /tmp/{c['id']}-hermes --hermes`. "
               "Ahí lo que se prueba es si el modelo lee el motivo del freno y cambia de camino.", ""]
    return "\n".join(partes)


def git(d: Path, *a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace")


def armar(c: dict, destino: Path, hermes: bool = False) -> list[str]:
    """Instala el arnés en `destino`, siembra el caso y agrega sus reglas (probadas). Devuelve problemas."""
    destino.mkdir(parents=True, exist_ok=True)
    git(destino, "init", "-q", "-b", "main")
    git(destino, "config", "user.email", "caso@ejemplo.test")
    git(destino, "config", "user.name", "Caso")
    p = subprocess.run([sys.executable, str(HERE / "install.py"), str(destino), "--profile", c.get("perfil", "python"), "--apply"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        return [f"install falló: {p.stdout[-300:]}{p.stderr[-300:]}"]
    shutil.copytree(c["_dir"] / "semilla", destino, dirs_exist_ok=True)
    # `dot.env` → `.env`: un `.env` versionado en ESTE repo lo frena el pre-commit (con razón). Las
    # semillas lo guardan con otro nombre y el sandbox lo recibe con el suyo.
    for f in sorted(destino.rglob("dot.*")):
        if ".git" not in f.parts and ".hermes" not in f.parts:
            f.rename(f.with_name(f.name[3:]))

    cfg_p = destino / ".hermes" / "harness.config.json"
    config = json.loads(cfg_p.read_text(encoding="utf-8"))
    problemas = []
    # Los inocentes del caso entran ANTES que sus reglas: `cli.validar` prueba que ninguna los muerda (P3).
    for donde, lista in (c.get("inocentes") or {}).items():
        config = cli.set_ruta(config, donde, list(cli.get_ruta(config, donde) or []) + list(lista))
    for familia, reglas in (c.get("reglas") or {}).items():
        for regla in reglas:
            errores = cli.validar(config, familia, regla, destino)
            if errores:
                problemas += [f"regla `{regla.get('id')}` ({familia}): {e}" for e in errores]
                continue
            config = cli.set_ruta(config, familia, cli.lista_de(config, familia) + [regla])
    loop = config.setdefault("loop", {})
    agente = ["hermes", "chat", "-q", "{prompt}"] if hermes else ["python3", str(c["_dir"] / "agente.py"), "{prompt}"]
    loop.update({"agentCommand": agente, "gateCommand": c.get("verificar") or ["python3", "verificar.py"],
                 "lockedPaths": list(loop.get("lockedPaths") or []) + ["^verificar\\.py$"] + list(c.get("lockedPaths") or [])})
    loop.update(c.get("loop") or {})
    config.setdefault("branches", {})["protected"] = ["main"]
    cfg_p.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (destino / ".hermes" / "loop" / "tasks.md").write_text(f"# Tareas\n\n- [ ] {c['tarea']}\n", encoding="utf-8")
    (destino / ".gitignore").write_text("__pycache__/\n.sim/\n", encoding="utf-8")
    git(destino, "add", "-A")
    git(destino, "commit", "-q", "-m", f"caso: {c['id']}")  # el sandbox no instala hooks de git: no hay nada que saltear
    if (c["_dir"] / "pendiente").is_dir():  # trabajo del humano SIN commitear: lo que un atajo se lleva puesto
        shutil.copytree(c["_dir"] / "pendiente", destino, dirs_exist_ok=True)
    return problemas


def correr(c: dict, corrida: dict) -> dict:
    """Una corrida en un sandbox nuevo. Devuelve lo observado y las diferencias con lo esperado."""
    with tempfile.TemporaryDirectory(prefix=f"caso-{c['id']}-") as tmp:
        d = Path(tmp) / "repo"
        problemas = armar(c, d)
        if problemas:
            return {"caso": c["id"], "modo": corrida.get("modo"), "dif": problemas}
        env = {k: v for k, v in os.environ.items() if k not in ("HARNESS_REPO", "HARNESS_NO_EVENTS")}
        env["JUGUETE"] = corrida.get("modo", "aprende")
        p = subprocess.run([sys.executable, str(d / ".hermes" / "harness" / "scripts" / "loop.py"), "--apply"], cwd=d, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        try:
            est = json.loads((d / ".git" / "harness-loop.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            est = {}
        evs = []
        try:
            for linea in (d / ".git" / "harness-events.jsonl").read_text(encoding="utf-8").splitlines():
                evs.append(json.loads(linea))
        except (OSError, ValueError):
            pass
        intentos = est.get("attempts") or []
        obs = {"resultado": est.get("phase"), "intentos": len(intentos),
               "frenos": sorted({e.get("rule") for e in evs if e.get("kind") in ("block", "ask")}),
               "intocables": any(i.get("tampered") for i in intentos)}
        dif = []
        if obs["resultado"] != corrida.get("resultado"):
            dif.append(f"resultado {obs['resultado']} (esperado {corrida.get('resultado')})")
        if "intentos" in corrida and obs["intentos"] != corrida["intentos"]:
            dif.append(f"{obs['intentos']} intento(s) (esperado {corrida['intentos']})")
        faltan = sorted(set(corrida.get("frenos") or []) - set(obs["frenos"]))
        if faltan:
            dif.append(f"no mordieron: {', '.join(faltan)} (mordieron: {', '.join(obs['frenos']) or 'ninguno'})")
        if bool(corrida.get("intocables")) != obs["intocables"]:
            dif.append(f"intocables {'no ' if not obs['intocables'] else ''}detectados (esperado {'sí' if corrida.get('intocables') else 'no'})")
        if dif:
            dif.append("salida del loop:\n      " + "\n      ".join((p.stdout + p.stderr).strip().splitlines()[-25:]))
        return {"caso": c["id"], "modo": corrida.get("modo"), "obs": obs, "dif": dif}


def main(argv: list[str]) -> int:
    casos = catalogo()
    if argv[:1] == ["--list"]:
        print(f"{'caso':<30} {'dominio':<16} título")
        for c in casos:
            print(f"{c['id']:<30} {c.get('dominio', '?'):<16} {c.get('titulo', '')}")
        print(f"\n{len(casos)} casos. Detalle: casos/<id>/README.md")
        return 0
    if argv[:1] == ["readme"]:
        for c in casos:
            if c.get("_error") or (argv[1:] and c.get("id") not in argv[1:]):
                continue
            (c["_dir"] / "README.md").write_text(readme(c), encoding="utf-8")
            print(f"  ✓ casos/{c['id']}/README.md")
        return 0
    if argv[:1] == ["preparar"]:
        if len(argv) < 3:
            print("uso: casos.py preparar <id> <dir> [--hermes]")
            return 1
        c = next((x for x in casos if x.get("id") == argv[1]), None)
        destino = Path(argv[2]).expanduser().resolve()
        if c is None or (destino.exists() and any(destino.iterdir())):
            print("casos: no existe ese caso, o el directorio no está vacío (no se pisa nada).")
            return 1
        problemas = armar(c, destino, hermes="--hermes" in argv)
        for pr in problemas:
            print(f"  ✗ {pr}")
        modos = ", ".join(r["modo"] for r in c["corridas"])
        print(f"""Sandbox listo en {destino}
  tarea   {c['tarea']}
  agente  {'Hermes (hermes chat -q)' if '--hermes' in argv else f'de juguete — modos: {modos}'}

  cd {destino}
  python3 .hermes/harness/scripts/cli.py panel          # otra terminal
  {'' if '--hermes' in argv else 'JUGUETE=<modo> '}python3 .hermes/harness/scripts/cli.py loop --apply""")
        return 1 if problemas else 0

    elegidos = [c for c in casos if not argv or c.get("id") in argv]
    if argv and len(elegidos) != len(argv):
        print(f"casos: no existe {sorted(set(argv) - {c.get('id') for c in elegidos})}. Mirá --list.")
        return 1
    forma = [(c.get("id"), p) for c in elegidos for p in problemas_de_forma(c)]
    indice = (CASOS / "README.md").read_text(encoding="utf-8") if (CASOS / "README.md").is_file() else ""
    forma += [(c.get("id"), "casos/README.md (el catálogo) no lo nombra") for c in elegidos if f"[`{c.get('id')}`]" not in indice]
    for cid, p in forma:
        print(f"  ✗ {cid}: {p}")
    trabajos = [(c, r) for c in elegidos if not problemas_de_forma(c) for r in c["corridas"]]
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as ex:
        resultados = list(ex.map(lambda cr: correr(*cr), trabajos))
    malos = 0
    for r in resultados:
        o = r.get("obs") or {}
        marca = "✓" if not r["dif"] else "✗"
        print(f"  {marca} {r['caso']:<30} {r['modo']:<10} {o.get('resultado', '?'):<8} {o.get('intentos', '?')} int."
              + (f" · frenos: {', '.join(o.get('frenos') or [])}" if o.get("frenos") else "")
              + (" · intocables" if o.get("intocables") else ""))
        for dd in r["dif"]:
            print(f"      {dd}")
        malos += bool(r["dif"])
    if malos or forma:
        print(f"\ncasos: {malos + len(forma)} con diferencias de {len(resultados)} corridas.")
        return 1
    print(f"\ncasos: las {len(resultados)} corridas de {len(elegidos)} casos dieron lo esperado.")
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
