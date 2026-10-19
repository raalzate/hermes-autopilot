#!/usr/bin/env python3
"""
El workspace: varios proyectos sobre una forja, uno de GESTIÓN y N CODIFICADORES (ADR 0013).

    python3 scripts/workspace.py init <dir> --org X [--forja github] [--nombre N] [--repo X/gestion] [--local] [--apply]
    python3 scripts/workspace.py add <id> --repo R [--dir D] [--perfil P] [--agente claude-code] [--forja gitlab] [--crear] [--local] [--apply]
    python3 scripts/workspace.py despachar <n> [--apply]
    python3 scripts/workspace.py estado [<n> …] [--apply]
    python3 scripts/workspace.py wiki [--apply]
    python3 scripts/workspace.py check

El proyecto de gestión (este `workspace.json`) tiene las épicas, los milestones, el tablero de
portafolio, la wiki y la cola del ORQUESTADOR (Hermes). No tiene código. Cada codificador tiene su
repo, su tablero, su cola y su agente (Claude Code o Hermes), con su propio arnés. Lo que los une
es la épica: un issue padre en gestión con un checklist de hijos, y un issue hijo por línea en el
repo del codificador, vinculado al padre (plugin/harness/forja.py).

  init       el esqueleto de gestión: workspace.json, AGENTS.md del orquestador, wiki/, roadmap,
             la plantilla de épica y el arnés instalado; en la forja, el repo, los milestones y el
             tablero (`--local`: sólo los archivos).
  add        un codificador: lo registra, le instala el arnés en `--dir` con su perfil, su forja y
             su agente como `loop.agentCommand`, y le crea el tablero (`--crear`: también el repo).
  despachar  los hijos de la épica `<n>` que todavía no salieron: un issue por línea en su repo,
             vinculado al padre, encolado en el loop del codificador (`[issue: <repo>#<n>]`).
  estado     el checklist de cada épica según la forja: `[x]` lo cerrado, `[!]` lo que el loop del
             codificador escaló a un humano.
  wiki       regenera wiki/Proyectos.md desde workspace.json y empuja wiki/ al repo de la wiki.
  check      sin red: cada forja con sus ejemplos, cada operación clasificada por su integración, el
             pipeline de cada forja y un despacho de punta a punta contra la forja simulada. Señal
             del gate.

DRY-RUN por defecto (P9): las LECTURAS van a la forja de verdad (el plan sale con la épica real) y
lo que escribe se imprime y se simula. `--apply` publica. `--simulado`: todo contra la forja de
juguete, sin red. El loop nunca publica (P13): con `--apply` esto lo corre o lo aprueba un humano
(regla `terminal.ask` `workspace-publica`).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent  # el repo del arnés (o una copia instalada)
PLANT = HOME / "plantillas"
GESTION = PLANT / "workspace" / "gestion"
WS = "workspace.json"
sys.path.insert(0, str(HOME / "plugin"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import forja as fj  # noqa: E402
from harness import integ as nucleo  # noqa: E402

SEÑAL = {"name": "workspace (manifiesto y forjas)", "command": ["python3", ".hermes/harness/scripts/workspace.py", "check"],
         "why": "un workspace.json que nombra un proyecto, una forja o un agente que no existe, o una forja cuyo comando ya no "
                "es el que su integración clasifica, falla recién al despachar, con la mitad de los hijos ya publicados"}


def _json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def forjas() -> dict[str, dict]:
    return {f.stem: _json(f) for f in sorted((PLANT / "forjas").glob("*.json"))}


def integraciones() -> dict[str, dict]:
    return {f.stem: _json(f) for f in sorted((PLANT / "integraciones").glob("*.json"))}


def buscar_ws(desde: Path) -> Path | None:
    for d in (desde, *desde.parents):
        if (d / WS).is_file():
            return d
    return None


def leer_ws(d: Path) -> dict:
    return _json(d / WS)


def escribir_ws(d: Path, ws: dict) -> None:
    (d / WS).write_text(json.dumps(ws, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def proyectos(ws: dict) -> dict[str, dict]:
    return {p["id"]: p for p in ws.get("proyectos") or [] if isinstance(p, dict) and p.get("id")}


def forja_de(ws: dict, p: dict | None = None) -> dict:
    fid = (p or {}).get("forja") or ws.get("forja") or "github"
    m = forjas().get(fid)
    if m is None:
        raise fj.ForjaError(f"la forja `{fid}` no existe (plantillas/forjas/)")
    return m


def de_repo(ws: dict, repo: str) -> dict | None:
    if (ws.get("gestion") or {}).get("repo") == repo:
        return ws["gestion"]
    return next((p for p in proyectos(ws).values() if p.get("repo") == repo), None)


def a_forja(m: dict, texto: str) -> str:
    """Azure guarda la descripción como HTML: cada salto de línea, un `<br>`."""
    s = m.get("saltoDeLinea")
    return texto.replace("\n", s) if s else texto


def de_forja(m: dict, texto: str) -> str:
    s = m.get("saltoDeLinea")
    return texto.replace(s, "\n") if s else texto


def problemas_de_ws(ws: dict) -> list[str]:
    out, fs = [], forjas()
    agentes = ws.get("agentes") or {}
    if ws.get("forja") not in fs:
        out.append(f"`forja` {ws.get('forja')!r} no es una de {', '.join(fs)}")
    g = ws.get("gestion") or {}
    try:
        fj.vars_de_repo(g.get("repo", ""))
    except fj.ForjaError as e:
        out.append(f"gestion.repo: {e}")
    if g.get("agente") and g["agente"] not in agentes:
        out.append(f"gestion.agente `{g['agente']}` no está en `agentes`")
    vistos = set()
    for i, p in enumerate(ws.get("proyectos") or []):
        donde = f"proyectos[{i}] ({p.get('id')})"
        if not re.fullmatch(r"[\w.-]+", str(p.get("id") or "")):
            out.append(f"{donde}: `id` en letras, dígitos, `.`, `_` o `-`")
        if p.get("id") in vistos:
            out.append(f"{donde}: `id` repetido")
        vistos.add(p.get("id"))
        if p.get("rol", "codificador") != "codificador":
            out.append(f"{donde}: `rol` es `codificador` (la gestión es una sola: `gestion`)")
        try:
            fj.vars_de_repo(p.get("repo", ""))
        except fj.ForjaError as e:
            out.append(f"{donde}: {e}")
        if p.get("repo") == g.get("repo"):
            out.append(f"{donde}: es el repo de gestión: el código no va ahí")
        if p.get("forja") and p["forja"] not in fs:
            out.append(f"{donde}: la forja `{p['forja']}` no existe")
        if p.get("agente") and p["agente"] not in agentes:
            out.append(f"{donde}: el agente `{p['agente']}` no está en `agentes`")
        if p.get("perfil") and not (PLANT / "perfiles" / f"{p['perfil']}.json").is_file():
            out.append(f"{donde}: el perfil `{p['perfil']}` no existe")
    for nombre, argv in agentes.items():
        if not (isinstance(argv, list) and argv and any("{prompt}" in str(a) for a in argv)):
            out.append(f"agentes.{nombre}: argv sin `{{prompt}}`: el loop no tendría cómo pasarle la tarea")
    return out


# ── ejecutar contra la forja ─────────────────────────────────────────────────

class Simulada:
    """La forja de juguete: issues, cuerpos y vínculos en memoria. Responde con la MISMA forma que la
    CLI de verdad (`simulado` del manifiesto), así que lo que lee la salida se prueba igual."""

    def __init__(self):
        self.issues: dict[tuple[str, str], dict] = {}
        self.vinculos: list[tuple[str, str]] = []
        self._cont: dict[str, int] = {}

    def _n(self, clave: str) -> int:
        self._cont[clave] = self._cont.get(clave, 0) + 1
        return self._cont[clave]

    def conoce(self, vars_: dict) -> bool:
        return (vars_.get("repo", ""), str(vars_.get("n", ""))) in self.issues

    @staticmethod
    def crudo(m: dict, estado: str) -> str:
        return next((k for k, v in (m.get("estados") or {}).items() if v == estado), estado)

    def sembrar(self, m: dict, repo: str, cuerpo: str, n: str | None = None) -> str:
        n = str(n or self._n(repo))
        self.issues[(repo, n)] = {"cuerpo": cuerpo, "crudo": self.crudo(m, "abierto")}
        return n

    def cerrar(self, m: dict, repo: str, n: str) -> None:
        self.issues[(repo, str(n))]["crudo"] = self.crudo(m, "cerrado")

    def hacer(self, m: dict, op: str, vars_: dict) -> str:
        repo, n = vars_.get("repo", ""), str(vars_.get("n", ""))
        val: dict = {"repo": repo, "n": n}
        if op == "issue.crear":
            val["n"] = self.sembrar(m, repo, vars_.get("cuerpo", ""))
        elif op in ("issue.estado", "issue.cuerpo", "issue.id"):
            i = self.issues.get((repo, n))
            if i is None:
                raise fj.ForjaError(f"la forja simulada no tiene {repo}#{n}")
            val.update(crudo=i["crudo"], cuerpo=i["cuerpo"], id=f"9{n}", json_cuerpo=json.dumps({"description": i["cuerpo"]}))
        elif op == "issue.editar":
            self.issues.setdefault((repo, n), {"crudo": self.crudo(m, "abierto")})["cuerpo"] = vars_.get("cuerpo", "")
        elif op == "issue.vincular":
            self.vinculos.append((f"{vars_.get('repo_padre')}#{vars_.get('n_padre')}", str(vars_.get("id_hijo") or n)))
        elif op == "tablero.crear":
            val["n"] = self._n("tablero")
        return fj.rellenar((m.get("simulado") or {}).get(op, ""), val)


class Ejecutor:
    """`apply`: todo de verdad · `seco`: las lecturas de verdad, lo demás simulado · `simulado`: nada sale."""

    def __init__(self, modo: str, sim: Simulada | None = None, log=print):
        self.modo, self.sim, self.log = modo, sim or Simulada(), log

    def __call__(self, m: dict, op: str, vars_: dict) -> str | None:
        argv = fj.comando(m, op, vars_)
        if argv is None:
            return None
        lee = (m.get("clases") or {}).get(op) == "read"
        if self.modo == "apply" or (self.modo == "seco" and lee and not self.sim.conoce(vars_)):
            self.log(f"  $ {shlex.join(argv)}")
            try:
                p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            except FileNotFoundError:
                raise fj.ForjaError(f"no está `{argv[0]}` en el PATH. Setup de la forja `{m['id']}`: "
                                    + " · ".join(m.get("setup") or [])) from None
            if p.returncode != 0:
                raise fj.ForjaError(f"`{shlex.join(argv[:4])} …` salió {p.returncode}: {(p.stderr or p.stdout).strip()[:400]}")
            if self.modo == "seco" and op == "issue.cuerpo":
                # Lo que se leyó de verdad, la simulación lo recuerda: lo que sigue (editarlo) es en seco.
                self.sim.sembrar(m, vars_.get("repo", ""), fj.leer_salida(m, op, p.stdout), vars_.get("n"))
            return p.stdout
        self.log(f"  {'·' if lee else '+'} {shlex.join(argv)}")
        return self.sim.hacer(m, op, vars_)


def vars_repo(repo: str, **extra) -> dict:
    return {**fj.vars_de_repo(repo), **{k: v for k, v in extra.items() if v is not None}}


# ── el despacho y el estado (lo que prueba `check` contra la simulada) ─────

def leer_cuerpo(ws: dict, n, ej: Ejecutor) -> str:
    m = forja_de(ws)
    return de_forja(m, fj.leer_salida(m, "issue.cuerpo", ej(m, "issue.cuerpo", vars_repo(ws["gestion"]["repo"], n=n)) or ""))


def linea_de_cola(titulo: str, r: str) -> str:
    return f"- [ ] {titulo} [issue: {r}]"


def cola_de(ws_dir: Path | None, p: dict) -> Path | None:
    if ws_dir is None or not p.get("dir"):
        return None
    cola = (ws_dir / p["dir"]).resolve() / ".hermes" / "loop" / "tasks.md"
    return cola if cola.is_file() else None


def despachar(ws: dict, n, ej: Ejecutor, ws_dir: Path | None = None, escribir: bool = False, log=print) -> tuple[list[str], list[str]]:
    """(referencias creadas, problemas). Todo o nada: con un problema en el checklist no se crea ninguno."""
    mg, gestion = forja_de(ws), ws["gestion"]["repo"]
    cuerpo = leer_cuerpo(ws, n, ej)
    crear, problemas = fj.plan_despacho(cuerpo, proyectos(ws))
    if not fj.hijos(cuerpo):
        problemas.append(f"la épica {gestion}#{n} no tiene checklist de hijos (`- [ ] [<proyecto>] <título>`)")
    if problemas or not crear:
        return [], problemas
    padre = fj.ref(gestion, n)
    padre_vars = vars_repo(gestion)
    creados = []
    for h in crear:
        p = proyectos(ws)[h["proyecto"]]
        m = forja_de(ws, p)
        salida = ej(m, "issue.crear", vars_repo(p["repo"], titulo=h["titulo"], cuerpo=a_forja(m, fj.cuerpo_hijo(m, padre)),
                                               etiqueta=p.get("etiqueta")))
        nh = fj.leer_salida(m, "issue.crear", salida or "")
        r = fj.ref(p["repo"], nh)
        if m["id"] == mg["id"]:
            # El vínculo nativo, sólo dentro de la misma forja. Entre forjas queda el del texto del hijo.
            idh = fj.leer_salida(m, "issue.id", ej(m, "issue.id", vars_repo(p["repo"], n=nh)) or "") if (m.get("ops") or {}).get("issue.id") else nh
            ej(m, "issue.vincular", vars_repo(p["repo"], n=nh, id_hijo=idh, repo_padre=gestion, n_padre=n,
                                              repo_padre_enc=padre_vars["repo_enc"]))
        else:
            log(f"  · {r} está en otra forja ({m['id']}): el vínculo con {padre} queda en el cuerpo del issue")
        url = (salida or "").strip()
        if p.get("tablero") and url.startswith("http"):
            ej(m, "tablero.agregar", vars_repo(p["repo"], tablero=p["tablero"], url=url))
        cuerpo = fj.con_ref(cuerpo, h["linea"], r)
        cola = cola_de(ws_dir, p)
        if cola is not None:
            log(f"  + {cola}: {linea_de_cola(h['titulo'], r)}")
            if escribir:
                texto = cola.read_text(encoding="utf-8")
                cola.write_text(texto + ("" if texto.endswith("\n") else "\n") + linea_de_cola(h["titulo"], r) + "\n", encoding="utf-8")
        creados.append(r)
    ej(mg, "issue.editar", vars_repo(gestion, n=n, cuerpo=a_forja(mg, cuerpo)))
    return creados, []


def escalado(ws_dir: Path | None, p: dict | None, r: str) -> bool:
    cola = cola_de(ws_dir, p or {})
    if cola is None:
        return False
    return re.search(rf"^\s*[-*]\s+\[!\].*\[issue:\s*{re.escape(r)}\]", cola.read_text(encoding="utf-8"), re.M) is not None


def estado(ws: dict, n, ej: Ejecutor, ws_dir: Path | None = None) -> tuple[dict[str, str], bool]:
    """({referencia: marca}, cambió). Cerrado en la forja → `x`; escalado en la cola → `!`; si no, ` `."""
    mg = forja_de(ws)
    cuerpo = leer_cuerpo(ws, n, ej)
    marcas = {}
    for h in fj.hijos(cuerpo):
        if not h["ref"]:
            continue
        repo, nh = fj.partir_ref(h["ref"])
        p = de_repo(ws, repo)
        m = forja_de(ws, p)
        e = fj.estado(m, fj.leer_salida(m, "issue.estado", ej(m, "issue.estado", vars_repo(repo, n=nh)) or ""))
        marcas[h["ref"]] = "x" if e == "cerrado" else ("!" if escalado(ws_dir, p, h["ref"]) else " ")
    nuevo = fj.con_marcas(cuerpo, marcas)
    if nuevo != cuerpo:
        ej(mg, "issue.editar", vars_repo(ws["gestion"]["repo"], n=n, cuerpo=a_forja(mg, nuevo)))
    return marcas, nuevo != cuerpo


# ── check: sin red ───────────────────────────────────────────────────────────

def _repos_de_ensayo(m: dict) -> tuple[str, str, str]:
    """`partesRepo`: cuántas partes tiene el nombre de un repo en esa forja (Azure: org/proyecto/repo)."""
    base = "/".join(["org", "plat", "x"][-int(m.get("partesRepo") or 2):][:-1])
    return f"{base}/gestion", f"{base}/api", f"{base}/web"


def ensayo(m: dict) -> list[str]:
    """Una épica de punta a punta contra la simulada: despachar, no repetir, cerrar un hijo, marcar."""
    out = []
    rg, ra, rw = _repos_de_ensayo(m)
    ws = {"nombre": "ensayo", "forja": m["id"], "gestion": {"repo": rg, "agente": "hermes"}, "epicas": [],
          "proyectos": [{"id": "api", "repo": ra, "rol": "codificador"}, {"id": "web", "repo": rw, "rol": "codificador"}],
          "agentes": {"hermes": ["hermes", "chat", "-q", "{prompt}"]}}
    sim = Simulada()
    ej = Ejecutor("simulado", sim, log=lambda *_: None)
    n = sim.sembrar(m, rg, a_forja(m, "## Hijos\n\n- [ ] [api] Login\n- [ ] [web] Pantalla de login\n"))
    try:
        creados, prob = despachar(ws, n, ej, log=lambda *_: None)
        if prob or len(creados) != 2:
            return [f"el despacho de una épica con 2 hijos creó {len(creados)} ({'; '.join(prob)})"]
        cuerpo = leer_cuerpo(ws, n, ej)
        if [h["ref"] for h in fj.hijos(cuerpo)] != creados:
            out.append("la épica no quedó con la referencia de cada hijo")
        if (m.get("ops") or {}).get("issue.vincular") and len(sim.vinculos) != 2:
            out.append(f"el vínculo nativo padre→hijo se hizo {len(sim.vinculos)} veces, no 2")
        for r in creados:
            repo, nh = fj.partir_ref(r)
            if fj.ref(rg, n) not in de_forja(m, sim.issues[(repo, nh)]["cuerpo"]):
                out.append(f"el hijo {r} no nombra a su padre en el cuerpo")
        otra, prob = despachar(ws, n, ej, log=lambda *_: None)
        if otra:
            out.append(f"despachar dos veces la misma épica volvió a crear {otra}")
        sim.cerrar(m, *fj.partir_ref(creados[0]))
        marcas, cambio = estado(ws, n, ej)
        if marcas != {creados[0]: "x", creados[1]: " "} or not cambio:
            out.append(f"estado: con el primer hijo cerrado, las marcas son {marcas}")
        if [h["marca"] for h in fj.hijos(leer_cuerpo(ws, n, ej))] != ["x", " "]:
            out.append("estado no dejó el checklist de la épica marcado en la forja")
        n2 = sim.sembrar(m, rg, a_forja(m, "- [ ] [api] Uno\n- [ ] [nadie] Otro\n"))
        antes = len(sim.issues)
        creados, prob = despachar(ws, n2, ej, log=lambda *_: None)
        if creados or not prob or len(sim.issues) != antes:
            out.append("una épica con un proyecto que no existe se despachó a medias: tiene que ser todo o nada")
    except fj.ForjaError as e:
        out.append(f"el ensayo revienta: {e}")
    return out


def problemas_de_forja(m: dict, integ: dict | None) -> list[str]:
    """Una forja: su forma, sus ejemplos, cada operación clasificada por su integración como la forja
    dice, su pipeline y un despacho de punta a punta contra la simulada."""
    forma = fj.problemas_de_manifiesto(m)
    if forma:
        return forma
    out = []
    for ej in m.get("examples") or []:
        try:
            hizo = fj.comando(m, ej["op"], ej.get("vars") or {})
        except fj.ForjaError as e:
            hizo = str(e)
        if hizo != ej.get("argv"):
            out.append(f"ejemplo `{ej['op']}` ({ej.get('why')}): arma {hizo}, se esperaba {ej.get('argv')}")
    if integ is None:
        out.append(f"la integración `{m.get('integracion')}` no está en plantillas/integraciones: nada gobierna su CLI")
    for op, plantilla in (m.get("ops") or {}).items():
        if plantilla is None or integ is None:
            continue
        texto = " ".join(fj.comando(m, op, {v: "v1" for v in fj.variables(plantilla)}) or [])
        esperada = (m.get("clases") or {}).get(op)
        hay = nucleo.clase(integ, texto)
        if not re.search(integ.get("command") or "(?!)", texto):
            out.append(f"`{op}` ({texto}) no es un comando de la integración `{integ.get('id')}`")
        elif hay == "deny":
            out.append(f"`{op}` es una clase `deny` para su integración: el agente nunca podría correrlo")
        elif hay != esperada:
            out.append(f"`{op}`: la integración lo clasifica `{hay}` y la forja declara `{esperada}`")
    hay_gate = False
    for e in m.get("ci") or []:
        f = PLANT / e["de"]
        if not f.is_file():
            out.append(f"el pipeline `{e['de']}` no existe")
            continue
        texto = f.read_text(encoding="utf-8")
        hay_gate = hay_gate or "scripts/gate.py" in texto
        if e.get("runner") == "drift" and "scripts/drift.py" not in texto:
            out.append(f"`{e['de']}` es el runner de la deriva y no corre drift.py: encendido y nadie que lo corra")
    if not hay_gate:
        out.append("ningún pipeline de la forja corre el gate: CI verde sin gate es CI que no mira")
    return out + [f"ensayo: {e}" for e in ensayo(m)]


def problemas_de_forjas() -> list[str]:
    ints = integraciones()
    return [f"{fid}: {e}" for fid, m in forjas().items() for e in problemas_de_forja(m, ints.get(m.get("integracion") or ""))]


def config_del_repo(d: Path) -> dict | None:
    p = d / ".hermes" / "harness.config.json"
    try:
        return _json(p)
    except (OSError, ValueError):
        return None


def problemas_de_gestion(ws_dir: Path) -> list[str]:
    """El repo de gestión no es destino de código: su config no declara código que el loop toque."""
    cfg = config_del_repo(ws_dir)
    if cfg is None or (cfg.get("workspace") or {}).get("rol") != "gestion":
        return []
    propias = set(_json(GESTION / "perfil.json").get("codeExtensions") or [])
    otras = sorted(set((cfg.get("gate") or {}).get("codeExtensions") or []) - propias)
    if otras:
        return [f"el config del repo de gestión declara código de un stack ({', '.join(otras)}): el código va a un codificador"]
    return []


# ── los comandos ─────────────────────────────────────────────────────────────

def _instalar(d: Path, perfil: str | None, forja: str, ajustes, propios: dict[Path, str], apply: bool) -> int:
    """El instalador de siempre (install.plan), con los archivos propios del workspace primero y el
    config ajustado. Nunca sobreescribe."""
    import install as ins

    items = [(a, dst, src) for a, dst, src in ins.plan(d, perfil, False, forja) if dst not in propios]
    for a, dst, src in items:
        if isinstance(src, dict) and dst.name == "harness.config.json":
            ajustes(src)
    todos = [("=" if dst.exists() else "+", dst, texto) for dst, texto in propios.items()] + items
    for a, dst, _ in todos:
        if "/.hermes/harness/" not in dst.as_posix():
            print(f"{a}  {os.path.relpath(dst, d)}")
    codigo = sum(1 for a, dst, _ in todos if a == "+" and "/.hermes/harness/" in dst.as_posix())
    print(f"+  .hermes/harness/  ({codigo} archivos del arnés)")
    if apply:
        for a, dst, src in todos:
            if a == "=":
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(src, dict):
                dst.write_text(json.dumps(src, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            elif isinstance(src, str):
                dst.write_text(src, encoding="utf-8")
            else:
                shutil.copy2(src, dst)
                if dst.parent.name == ".githooks":
                    dst.chmod(0o755)
    return sum(1 for a, *_ in todos if a != "=")


def agents_gestion(nombre: str) -> str:
    base = (PLANT / "AGENTS.md").read_text(encoding="utf-8")
    propio = (GESTION / "AGENTS-gestion.md").read_text(encoding="utf-8").replace("{workspace}", nombre)
    nuevo = re.sub(r"(## Qué es este repo\n\n)<!--[^>]*-->\n", lambda mm: mm.group(1) + propio, base, count=1)
    return nuevo if nuevo != base else base + "\n## El proyecto de gestión\n\n" + propio


def proyectos_md(ws: dict) -> str:
    filas = [f"| gestión | `{ws['gestion']['repo']}` | {ws.get('forja')} | {ws['gestion'].get('agente') or '—'} | "
             f"{ws['gestion'].get('tablero') or '—'} |"]
    for p in ws.get("proyectos") or []:
        filas.append(f"| {p['id']} | `{p['repo']}` | {p.get('forja') or ws.get('forja')} | {p.get('agente') or '—'} | "
                     f"{p.get('tablero') or '—'} |")
    return ("# Proyectos\n\nLo regenera `workspace.py wiki` desde `workspace.json`: no se edita a mano.\n\n"
            "| Proyecto | Repo | Forja | Agente | Tablero |\n|---|---|---|---|---|\n" + "\n".join(filas) + "\n")


def cmd_init(a, ej: Ejecutor, apply: bool) -> int:
    d = Path(a.dir).expanduser().resolve()
    if (d / WS).exists():
        print(f"workspace: {d} ya es un workspace ({WS} existe). Para sumar un proyecto: `workspace.py add`.")
        return 1
    m = forjas().get(a.forja)
    if m is None:
        print(f"workspace: no existe la forja `{a.forja}`. Son: {', '.join(forjas())}")
        return 1
    nombre = a.nombre or d.name
    repo = a.repo or (f"{a.org}/{nombre}" if a.org else "")
    ws = _json(GESTION / WS)
    ws.update(nombre=nombre, forja=a.forja)
    ws["gestion"]["repo"] = repo
    prob = problemas_de_ws(ws)
    if prob:
        print("workspace: " + "\n  ".join(prob) + ("\n  (pasá --org o --repo)" if not repo else ""))
        return 1
    print(f"{'Creando' if apply else 'DRY-RUN (--apply para ejecutar)'} el proyecto de gestión `{nombre}` en {d} · forja {a.forja}\n")
    propios = {d / WS: json.dumps(ws, indent=2, ensure_ascii=False) + "\n",
               d / "AGENTS.md": agents_gestion(nombre),
               d / ".hermes" / "loop" / "tasks.md": (GESTION / "tasks.md").read_text(encoding="utf-8"),
               d / "roadmap.json": (GESTION / "roadmap.json").read_text(encoding="utf-8"),
               d / "wiki" / "Proyectos.md": proyectos_md(ws)}
    for f in sorted((GESTION / "wiki").glob("*.md")):
        propios[d / "wiki" / f.name] = f.read_text(encoding="utf-8").replace("{workspace}", nombre)
    if m.get("plantillaIssue"):
        propios[d / m["plantillaIssue"]["ruta"]] = m["plantillaIssue"].get("encabezado", "") + (GESTION / "epica.md").read_text(encoding="utf-8")

    def ajustes(cfg: dict) -> None:
        import install as ins

        cfg.update(ins.merge_profile(cfg, _json(GESTION / "perfil.json")))
        cfg["workspace"] = {"rol": "gestion", "manifiesto": WS}
        cfg.setdefault("loop", {})["agentCommand"] = ws["agentes"][ws["gestion"]["agente"]]
        cfg.setdefault("gate", {}).setdefault("signals", []).append(SEÑAL)

    if apply:
        d.mkdir(parents=True, exist_ok=True)
    _instalar(d, None, a.forja, ajustes, propios, apply)
    if not a.local:
        print(f"\nEn la forja ({m['id']}):")
        ej(m, "repo.crear", vars_repo(repo, descripcion=f"Gestión del workspace {nombre}: épicas, milestones, tablero y wiki"))
        for ms in _json(GESTION / "roadmap.json").get("milestones") or []:
            ej(m, "milestone.crear", vars_repo(repo, titulo=ms["titulo"], descripcion=ms.get("descripcion"), fecha=ms.get("fecha")))
        salida = ej(m, "tablero.crear", vars_repo(repo, titulo=f"{nombre} · portafolio"))
        if salida is not None:
            ws["gestion"]["tablero"] = fj.leer_salida(m, "tablero.crear", salida)
            if apply:
                escribir_ws(d, ws)
    print(f"""
Siguiente (lo hace el humano):
  1. cd {d} && git init && python3 .hermes/harness/scripts/githooks.py install
  2. git remote add origin <la URL de {repo}> y el primer push
  3. {m.get('wikiNota') or 'la wiki: `workspace.py wiki --apply`'}
  4. Cada codificador: python3 .hermes/harness/scripts/workspace.py add <id> --repo <org/repo> --dir <ruta> --perfil <stack> --agente claude-code
  5. Una épica: un issue con la plantilla «Épica» y su checklist; después `workspace.py despachar <n>`""")
    return 0


def _ws_dir(a) -> Path:
    d = Path(a.ws).expanduser().resolve() if a.ws else buscar_ws(Path.cwd())
    if d is None or not (d / WS).is_file():
        sys.exit("workspace: no encuentro workspace.json (corré desde el repo de gestión o pasá --ws)")
    return d


def cmd_add(a, ej: Ejecutor, apply: bool) -> int:
    d = _ws_dir(a)
    ws = leer_ws(d)
    if a.id in proyectos(ws) or a.id == "gestion":
        print(f"workspace: el proyecto `{a.id}` ya existe")
        return 1
    p = {"id": a.id, "repo": a.repo, "rol": "codificador", "perfil": a.perfil, "agente": a.agente,
         "dir": os.path.relpath(Path(a.dir).expanduser().resolve(), d) if a.dir else None, "tablero": None}
    if a.forja:
        p["forja"] = a.forja
    p = {k: v for k, v in p.items() if v is not None or k == "tablero"}
    nuevo = {**ws, "proyectos": [*(ws.get("proyectos") or []), p]}
    prob = problemas_de_ws(nuevo)
    if prob:
        print("workspace: " + "\n  ".join(prob))
        return 1
    m = forja_de(ws, p)
    print(f"{'Sumando' if apply else 'DRY-RUN (--apply para ejecutar)'} el codificador `{a.id}` ({a.repo}) · forja {m['id']}"
          f" · agente {a.agente or '—'}\n")
    if a.dir:
        destino = Path(a.dir).expanduser().resolve()
        if apply:
            destino.mkdir(parents=True, exist_ok=True)

        def ajustes(cfg: dict) -> None:
            cfg["workspace"] = {"rol": "codificador", "id": a.id, "gestion": ws["gestion"]["repo"]}
            if a.agente:
                cfg.setdefault("loop", {})["agentCommand"] = ws["agentes"][a.agente]

        _instalar(destino, a.perfil, m["id"], ajustes, {}, apply)

    def registrar() -> None:
        # Antes de la forja y después del tablero: si la forja falla, el proyecto ya quedó registrado.
        if apply:
            escribir_ws(d, {**ws, "proyectos": [*(ws.get("proyectos") or []), p]})
            (d / "wiki").mkdir(exist_ok=True)
            (d / "wiki" / "Proyectos.md").write_text(proyectos_md(leer_ws(d)), encoding="utf-8")

    registrar()
    print(f"\n{'' if apply else '(en seco) '}{WS}: + proyectos[{a.id}] · wiki/Proyectos.md al día")
    if a.local:
        return 0
    print(f"\nEn la forja ({m['id']}):")
    if a.crear:
        ej(m, "repo.crear", vars_repo(a.repo, descripcion=f"{ws.get('nombre')} · {a.id}"))
    salida = ej(m, "tablero.crear", vars_repo(a.repo, titulo=f"{ws.get('nombre')} · {a.id}"))
    if salida is not None:
        p["tablero"] = fj.leer_salida(m, "tablero.crear", salida)
        registrar()
    return 0


def cmd_despachar(a, ej: Ejecutor, apply: bool) -> int:
    d = _ws_dir(a)
    ws = leer_ws(d)
    prob = problemas_de_ws(ws)
    if prob:
        print("workspace: " + "\n  ".join(prob))
        return 1
    print(f"{'Despachando' if apply else 'DRY-RUN (--apply para publicar)'} la épica {ws['gestion']['repo']}#{a.n}\n")
    creados, prob = despachar(ws, a.n, ej, d, escribir=apply)
    if prob:
        print("workspace: no se despacha nada (todo o nada):\n  " + "\n  ".join(prob))
        return 1
    if not creados:
        print("  (nada que despachar: cada hijo ya tiene su issue)")
    if apply and int(a.n) not in (ws.get("epicas") or []):
        ws["epicas"] = [*(ws.get("epicas") or []), int(a.n)]
        escribir_ws(d, ws)
    print(f"\n{len(creados)} hijo(s): {', '.join(creados) or '—'}")
    return 0


def cmd_estado(a, ej: Ejecutor, apply: bool) -> int:
    d = _ws_dir(a)
    ws = leer_ws(d)
    epicas = a.n or ws.get("epicas") or []
    if not epicas:
        print("workspace: no hay épicas despachadas (`workspace.py despachar <n>` las registra)")
        return 0
    rc = 0
    for n in epicas:
        print(f"\n{ws['gestion']['repo']}#{n}")
        try:
            marcas, cambio = estado(ws, n, ej, d)
        except fj.ForjaError as e:
            print(f"  ✗ {e}")
            rc = 1
            continue
        hechos = sum(1 for v in marcas.values() if v == "x")
        escalados = [r for r, v in marcas.items() if v == "!"]
        print(f"  {hechos}/{len(marcas)} cerrados" + (f" · escalados a un humano: {', '.join(escalados)}" if escalados else "")
              + ("" if cambio else " · el checklist ya estaba al día"))
    return rc


def cmd_wiki(a, ej: Ejecutor, apply: bool) -> int:
    d = _ws_dir(a)
    ws = leer_ws(d)
    m = forja_de(ws)
    remoto = fj.rellenar(m.get("wiki") or "", fj.vars_de_repo(ws["gestion"]["repo"]))
    print(f"{'Publicando' if apply else 'DRY-RUN (--apply para publicar)'} la wiki en {remoto}\n  + wiki/Proyectos.md (desde {WS})")
    if apply:
        (d / "wiki").mkdir(exist_ok=True)
        (d / "wiki" / "Proyectos.md").write_text(proyectos_md(ws), encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        pasos = [["git", "clone", "-q", remoto, tmp], ["copiar", str(d / "wiki"), tmp], ["git", "-C", tmp, "add", "-A"],
                 ["git", "-C", tmp, "commit", "-q", "-m", "wiki: desde workspace.py"], ["git", "-C", tmp, "push", "-q"]]
        for paso in pasos:
            print(f"  {'$' if apply else '+'} {shlex.join(paso)}")
            if not apply:
                continue
            if paso[0] == "copiar":
                for f in Path(paso[1]).glob("*.md"):
                    shutil.copy2(f, Path(tmp) / f.name)
                continue
            p = subprocess.run(paso, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            if p.returncode != 0 and "commit" not in paso:
                print(f"workspace: {(p.stderr or p.stdout).strip()[:400]}\n  {m.get('wikiNota') or ''}")
                return 1
    return 0


def cmd_check(a) -> int:
    errores = problemas_de_forjas()
    d = Path(a.ws).expanduser().resolve() if a.ws else buscar_ws(Path.cwd())
    plantilla = problemas_de_ws(_json(GESTION / WS))
    errores += [f"plantilla de {WS}: {e}" for e in plantilla]
    if d is not None and (d / WS).is_file():
        errores += [f"{WS}: {e}" for e in problemas_de_ws(leer_ws(d)) + problemas_de_gestion(d)]
    for e in errores:
        print(f"  ✗ {e}")
    if errores:
        print(f"\nworkspace: {len(errores)} problema(s).")
        return 1
    print(f"✓ workspace: {len(forjas())} forjas con sus ejemplos, sus operaciones clasificadas por su integración, su "
          f"pipeline y un despacho de punta a punta contra la simulada" + (f" · {d / WS} válido" if d else ""))
    return 0


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="El workspace: gestión + codificadores sobre una forja (dry-run por defecto).")
    ap.add_argument("--ws", help="el repo de gestión (por defecto, el que contiene workspace.json desde el cwd)")
    sub = ap.add_subparsers(dest="cmd")
    comunes = argparse.ArgumentParser(add_help=False)
    comunes.add_argument("--apply", action="store_true")
    comunes.add_argument("--simulado", action="store_true", help="todo contra la forja de juguete, sin red")
    comunes.add_argument("--ws", default=argparse.SUPPRESS)
    p = sub.add_parser("init", parents=[comunes])
    p.add_argument("dir")
    p.add_argument("--forja", default="github")
    p.add_argument("--org")
    p.add_argument("--nombre")
    p.add_argument("--repo")
    p.add_argument("--local", action="store_true", help="sólo los archivos; nada en la forja")
    p = sub.add_parser("add", parents=[comunes])
    p.add_argument("id")
    p.add_argument("--repo", required=True)
    p.add_argument("--dir")
    p.add_argument("--perfil")
    p.add_argument("--agente")
    p.add_argument("--forja")
    p.add_argument("--crear", action="store_true", help="crear también el repo en la forja")
    p.add_argument("--local", action="store_true", help="registrar e instalar; nada en la forja")
    p = sub.add_parser("despachar", parents=[comunes])
    p.add_argument("n")
    p = sub.add_parser("estado", parents=[comunes])
    p.add_argument("n", nargs="*")
    sub.add_parser("wiki", parents=[comunes])
    sub.add_parser("check", parents=[comunes])
    if not argv:
        print(__doc__)
        return 1
    a = ap.parse_args(argv)
    if a.cmd == "check":
        return cmd_check(a)
    apply = bool(getattr(a, "apply", False))
    ej = Ejecutor("apply" if apply else ("simulado" if a.simulado else "seco"))
    if apply and a.simulado:
        print("workspace: --apply y --simulado no van juntos")
        return 1
    try:
        return {"init": cmd_init, "add": cmd_add, "despachar": cmd_despachar, "estado": cmd_estado,
                "wiki": cmd_wiki}[a.cmd](a, ej, apply)
    except fj.ForjaError as e:
        print(f"workspace: {e}")
        return 1


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
