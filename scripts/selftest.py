#!/usr/bin/env python3
"""
Prueba de vida del arnés: ¿los frenos muerden? ¿y NO muerden de más? (P2, P3)

    python3 scripts/selftest.py

Los casos se GENERAN desde `.hermes/harness.config.json`: cada regla trae su `example`, y ese
ejemplo se pasa por el camino completo que usa Hermes (el callback del plugin, con su envoltorio
y su traducción a `{"action": "block"}`), no por la función suelta. Una regla sin ejemplo es una
regla sin prueba de vida, y eso es rojo.

No necesita Hermes instalado: el plugin se carga con un `ctx` de mentira que registra lo que el
plugin le pide. Que encaje con el Hermes REAL lo prueba la señal `hermes plugins doctor` del gate.

Nada de esto escribe en el árbol del repo (P7): lo que necesita disco va a un temporal.
"""
from __future__ import annotations

import atexit
import copy
import importlib.util
import types
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# El núcleo vive DENTRO del plugin (`plugin/harness/`): Hermes copia el directorio del plugin
# al instalarlo y al validarlo, y lo que quede afuera no viaja (docs/gotchas.md).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from harness import core, guards, rules, turn  # noqa: E402
from harness.core import HARNESS_HOME, REPO_ROOT, CONFIG_PATH  # noqa: E402

FALLAS: list[str] = []
OK = 0


def section(t: str) -> None:
    print(f"\n── {t}")


def check(cond: bool, desc: str) -> None:
    global OK
    if cond:
        OK += 1
    else:
        FALLAS.append(desc)
        print(f"  ✗ {desc}")


def load_plugin():
    """Carga `plugin/` como Hermes (`hermes_cli/plugins_loader.py::_load_directory_module`): desde
    una COPIA del directorio —así lo valida `hermes plugins doctor`—, como paquete con `__path__`
    propio y registrado en `sys.modules` antes de ejecutarlo. Cargarlo de otra forma probaba un
    plugin que en Hermes no importaba (docs/gotchas.md)."""
    tmp = tempfile.mkdtemp(prefix="repo-harness-plugin-")
    atexit.register(shutil.rmtree, tmp, True)
    copia = Path(tmp) / "repo-harness"
    shutil.copytree(HARNESS_HOME / "plugin", copia, ignore=shutil.ignore_patterns("__pycache__"))
    padre = "hermes_plugins_selftest"
    if padre not in sys.modules:  # el paquete padre de espacio de nombres, como `hermes_plugins`
        ns = types.ModuleType(padre)
        ns.__path__ = []
        sys.modules[padre] = ns
    nombre = f"{padre}.repo_harness"
    spec = importlib.util.spec_from_file_location(nombre, copia / "__init__.py", submodule_search_locations=[str(copia)])
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = nombre
    mod.__path__ = [str(copia)]
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeCtx:
    """El `ctx` de `register(ctx)`, con las firmas de hermes_cli/plugins.py."""

    def __init__(self):
        self.hooks: dict[str, list] = {}
        self.sections: dict[str, tuple] = {}
        self.commands: dict[str, object] = {}

    def register_hook(self, name, cb):
        self.hooks.setdefault(name, []).append(cb)

    def register_system_prompt_section(self, id, content, *, position="after_memory", max_chars=4000):
        assert re.fullmatch(r"[a-z0-9._-]{1,128}", id), "id inválido para Hermes"
        assert 0 < max_chars <= 4000, "Hermes rechaza max_chars > 4000"
        self.sections[id] = (content, max_chars)

    def register_command(self, name, handler, description="", args_hint="", argument_mode=None):
        self.commands[name] = handler


def manifest_hooks() -> list[str]:
    """`provides_hooks` de plugin.yaml, sin PyYAML (lista YAML de una columna)."""
    out, dentro = [], False
    for line in (HARNESS_HOME / "plugin" / "plugin.yaml").read_text(encoding="utf-8").splitlines():
        if re.match(r"^provides_hooks:\s*$", line):
            dentro = True
        elif dentro and re.match(r"^\s+-\s+\S+", line):
            out.append(line.split("-", 1)[1].strip())
        elif dentro and line.strip():
            dentro = False
    return out


def iter_patterns(node, ruta="$"):
    """Toda clave `pattern`/listas de regex del config, con su ruta para el mensaje."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("pattern", "codePattern", "issuePattern") and isinstance(v, str):
                yield f"{ruta}.{k}", v
            elif k in ("paths", "exceptPaths", "mustContain", "mustNotContain", "ignore") and isinstance(v, list):
                for i, p in enumerate(v):
                    if isinstance(p, str):
                        yield f"{ruta}.{k}[{i}]", p
            else:
                yield from iter_patterns(v, f"{ruta}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_patterns(v, f"{ruta}[{i}]")


def main() -> int:
    raiz_antes = sorted(p.name for p in REPO_ROOT.iterdir())
    # Los casos de "el freno revienta" loguean su traza a propósito: acá es ruido esperado.
    logging.getLogger("repo-harness").disabled = True
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    tools = config.get("tools") or {}
    os.environ["HARNESS_REPO"] = str(REPO_ROOT)
    # Cientos de bloqueos de prueba no pueden llenar el panel del humano: el registro de eventos
    # se apaga acá y la sección 13 lo enciende en un repo temporal.
    os.environ["HARNESS_NO_EVENTS"] = "1"

    # ── 1. El plugin carga y registra lo que su manifiesto promete ───────────
    section("1. plugin: carga y registro")
    plugin = load_plugin()
    ctx = FakeCtx()
    plugin.register(ctx)
    promete = manifest_hooks()
    check(bool(promete), "plugin.yaml declara provides_hooks")
    for h in promete:
        check(h in ctx.hooks, f"plugin.yaml promete `{h}` y register() no lo registra")
    for h in ctx.hooks:
        check(h in promete, f"register() registra `{h}` y plugin.yaml no lo declara")
    check("repo-harness.status" in ctx.sections, "sección de estado del system prompt registrada")
    check("harness" in ctx.commands, "comando /harness registrado")
    pre = ctx.hooks["pre_tool_call"][0]

    # ── 2. El config no apunta a la nada ─────────────────────────────────────
    section("2. config: regex, rutas y herramientas")
    for ruta, p in iter_patterns(config):
        try:
            re.compile(p)
            check(True, "")
        except re.error as e:
            check(False, f"regex inválida en {ruta}: {e}")
    for kind in ("shell", "write", "memory", "skill", "cron"):
        check(bool(tools.get(kind)), f"`tools.{kind}` vacío: esa familia de frenos no ve ninguna herramienta")
    for kind, fams in guards.GUARDS.items():
        check(kind in tools, f"hay frenos para `{kind}` y `tools` no lo declara")
    g = config.get("gate") or {}
    check(bool(g.get("codeExtensions") or g.get("codeGlobs")),
          "gate.codeExtensions y gate.codeGlobs vacíos: nada cuenta como código, el gate pendiente nunca se marca "
          "y pre_verify nunca frena (instalá con --profile o llenalos)")
    for inv in config.get("invariants") or []:
        check((REPO_ROOT / inv["file"]).is_file(), f"invariante sobre {inv['file']}, que no existe")
    for f in (config.get("context") or {}).get("files") or []:
        check((REPO_ROOT / f).is_file(), f"context.files: {f} no existe")
    for r in (config.get("skills") or {}).get("roots") or []:
        check((REPO_ROOT / r).is_dir(), f"skills.roots: {r} no existe")
    inc = (config.get("incidents") or {}).get("file")
    check(not inc or (REPO_ROOT / inc).is_file(), f"incidents.file: {inc} no existe")

    # ── 3. Los frenos muerden, por el camino del plugin ─────────────────────
    section("3. los frenos muerden (casos derivados del config)")

    def bloquea(tool, args, desc, accion="block"):
        r = pre(tool_name=tool, args=args, session_id="selftest")
        ok = isinstance(r, dict) and r.get("action") == accion and bool(r.get("message"))
        check(ok, f"{desc} → esperaba {accion}, obtuvo {r!r}")
        return r

    def pasa(tool, args, desc):
        r = pre(tool_name=tool, args=args, session_id="selftest")
        check(r is None, f"{desc} → debía pasar (P3), obtuvo {r!r}")

    t = config.get("terminal") or {}
    for regla in t.get("deny") or []:
        ej = regla.get("example")
        check(bool(ej), f"terminal.deny[{regla.get('id')}] sin `example`: regla sin prueba de vida")
        if not ej:
            continue
        check(bool(re.search(regla["pattern"], ej, re.I)), f"terminal.deny[{regla.get('id')}]: el ejemplo no casa con su patrón")
        # `moreExamples`: las variantes que el `reason` dice cubrir (flags largos, `git -C`, sudo…).
        for caso in [ej] + list(regla.get("moreExamples") or []):
            for tool in tools.get("shell") or []:
                r = bloquea(tool, {"command": caso}, f"{tool}: terminal.deny[{regla['id']}] `{caso}`")
                if r:
                    check(regla.get("reason", "") in r.get("message", ""), f"el bloqueo de {regla['id']} no explica el porqué")
    for regla in t.get("ask") or []:
        ej = regla.get("example")
        check(bool(ej), f"terminal.ask[{regla.get('id')}] sin `example`")
        if ej:
            r = bloquea(tools["shell"][0], {"command": ej}, f"terminal.ask[{regla['id']}]", "approve")
            check(isinstance(r, dict) and str(r.get("rule_key", "")).startswith("repo-harness:"),
                  f"terminal.ask[{regla['id']}]: sin rule_key propio, Hermes recordaría la aprobación bajo la herramienta entera")
    for inocente in t.get("innocent") or []:
        pasa(tools["shell"][0], {"command": inocente}, f"terminal inocente `{inocente}`")
    check(bool(t.get("innocent")), "terminal.innocent vacío: nada prueba que el freno no muerde de más")

    for regla in config.get("protectedPaths") or []:
        ej = regla.get("example")
        check(bool(ej), f"protectedPaths[{regla.get('id')}] sin `example`")
        if not ej:
            continue
        for caso in [ej] + list(regla.get("moreExamples") or []):
            for tool in tools.get("write") or []:
                bloquea(tool, {"path": caso, "content": "x"}, f"{tool}: protectedPaths[{regla['id']}] ({caso})")
            # Escribir por la terminal es escribir: una redirección a la ruta protegida también frena.
            if (t.get("redirectTargets")):
                bloquea(tools["shell"][0], {"command": f"echo x > {caso}"}, f"terminal: redirección a protectedPaths[{regla['id']}]")
        # Windows: la misma ruta con barras invertidas tiene que caer igual.
        if regla.get("outsideRepo"):
            bloquea(tools["write"][0], {"path": "C:" + ej.replace("/", "\\"), "content": "x"},
                    f"protectedPaths[{regla['id']}] con separadores de Windows")
    for inocente in config.get("protectedInnocent") or []:
        pasa(tools["write"][0], {"path": inocente, "content": "hola"}, f"escritura inocente {inocente}")
    # Symlink interno: otro nombre de una ruta protegida no la desprotege.
    if hasattr(os, "symlink"):
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp).resolve()
            (troot / ".hermes").mkdir()
            shutil.copy(CONFIG_PATH, troot / ".hermes" / "harness.config.json")
            (troot / ".git").mkdir()
            try:
                os.symlink(troot / ".git", troot / "alias")
                d = guards.evaluate(core.Event(tools["write"][0], {"path": "alias/config", "content": "x"}), config, troot)
                check(d.block, "un symlink interno (`alias/ → .git/`) desprotege la ruta")
            except OSError:
                pass  # Windows sin privilegio de symlink: el caso no aplica

    for regla in config.get("patterns") or []:
        ej, donde = regla.get("example"), regla.get("examplePath")
        check(bool(ej and donde), f"patterns[{regla.get('id')}] sin `example`/`examplePath`")
        if not (ej and donde):
            continue
        # En la línea 2, no en la 1: un `^` sin re.M sólo mira la primera línea, y un ejemplo en la
        # primera línea no lo nota nunca.
        bloquea(tools["write"][0], {"path": donde, "content": "x = 1\n" + ej}, f"patterns[{regla['id']}] (línea 2) al escribir {donde}")
        check(any(f"PATRON[{regla['id']}]" in h for h in rules.lint_one(config, donde, ej)),
              f"patterns[{regla['id']}]: el lint no lo caza por stdin")
        # `exceptPaths`: donde la regla NO aplica (el config que contiene el ejemplo). Si el freno
        # lo ignorara, el config no se podría reescribir con write_file, que es como se edita.
        if regla.get("exceptPaths"):
            ex = regla.get("exceptExample")
            check(bool(ex), f"patterns[{regla['id']}] con exceptPaths y sin `exceptExample`")
            if ex:
                pasa(tools["write"][0], {"path": ex, "content": "x = 1\n" + ej}, f"patterns[{regla['id']}] en su exceptPath {ex}")
                check(not any(f"PATRON[{regla['id']}]" in h for h in rules.lint_one(config, ex, ej)), f"el lint caza patterns[{regla['id']}] en su exceptPath")

    mem = config.get("memory") or {}
    for regla in mem.get("deny") or []:
        ej = regla.get("example")
        check(bool(ej), f"memory.deny[{regla.get('id')}] sin `example`")
        if ej:
            for tool in tools.get("memory") or []:
                bloquea(tool, {"action": "add", "target": "memory", "content": ej}, f"{tool}: memory.deny[{regla['id']}]")
                bloquea(tool, {"action": "replace", "old_text": "viejo", "content": ej}, f"{tool} replace: memory.deny[{regla['id']}]")
    for inocente in mem.get("innocent") or []:
        pasa(tools["memory"][0], {"action": "add", "content": inocente}, f"memoria inocente «{inocente}»")

    sk = config.get("skills") or {}
    heredadas = list(t.get("deny") or []) if sk.get("inheritTerminalDeny", True) else []
    for regla in (sk.get("deny") or []) + heredadas:
        ej = regla.get("example")
        if not ej:
            check(False, f"skills.deny[{regla.get('id')}] sin `example`")
            continue
        for tool in tools.get("skill") or []:
            # skill_manage anida el contenido: `operations: [{content}]`. El freno tiene que verlo.
            bloquea(tool, {"operations": [{"action": "create", "name": "x", "content": f"---\nname: x\n---\n{ej}\n"}]},
                    f"{tool}: skill que enseña `{regla.get('id')}`")
    for inocente in sk.get("innocent") or []:
        pasa(tools["skill"][0], {"operations": [{"action": "create", "content": inocente}]}, "skill inocente")

    cr = config.get("cron") or {}
    for regla in cr.get("deny") or []:
        ej = regla.get("example")
        check(bool(ej), f"cron.deny[{regla.get('id')}] sin `example`")
        if ej:
            bloquea(tools["cron"][0], {"action": "create", "schedule": "every day at 9am", "prompt": ej}, f"cron.deny[{regla['id']}]")
    if cr.get("minIntervalMinutes"):
        ej = cr.get("exampleTooFrequent")
        check(bool(ej), "cron.minIntervalMinutes sin `exampleTooFrequent`")
        for caso in ([ej] if ej else []) + list(cr.get("moreTooFrequent") or []):
            bloquea(tools["cron"][0], {"action": "create", "schedule": caso, "prompt": "x"}, f"cron cada `{caso}`")
    for inocente in cr.get("innocent") or []:
        pasa(tools["cron"][0], {"action": "create", "schedule": "every 2h", "prompt": inocente}, "cron inocente")
        pasa(tools["cron"][0], {"action": "create", "schedule": "in 5m", "prompt": inocente}, "cron one-shot (sin intervalo)")

    # Una herramienta que ningún freno reclama pasa siempre: el arnés no inventa jurisdicción.
    pasa("read_file", {"path": ".env"}, "herramienta sin familia (read_file)")

    # ── 3b. Las formas de Hermes que un freno ingenuo no ve (revisión 2026-09-30) ──
    section("3b. formas reales de Hermes: V4A, cwd de sesión, limpiar, homes movidos, worktrees")
    enrepo = [r for r in config.get("protectedPaths") or [] if not r.get("outsideRepo") and r.get("example")]
    mf = tools.get("$multiFilePatch") or {}
    if mf.get("args") and enrepo:
        arg = mf["args"][0]
        for tool in tools.get("write") or []:
            for r in enrepo:
                v4a = f"*** Begin Patch\n*** Update File: docs/ok.md\n+hola\n*** Update File: {r['example']}\n+x\n*** End Patch"
                bloquea(tool, {"mode": "patch", arg: v4a}, f"{tool} V4A sin `path` hacia protectedPaths[{r['id']}]")
            movido = f"*** Begin Patch\n*** Move File: docs/ok.md -> {enrepo[0]['example']}\n*** End Patch"
            bloquea(tool, {"mode": "patch", arg: movido}, f"{tool} V4A Move hacia una ruta protegida")
            pasa(tool, {"mode": "patch", arg: "*** Begin Patch\n*** Update File: docs/ok.md\n+hola\n*** End Patch"}, f"{tool} V4A inocente")
        for regla in config.get("patterns") or []:
            if regla.get("example") and regla.get("examplePath"):
                v4a = f"*** Begin Patch\n*** Update File: {regla['examplePath']}\n x = 1\n+{regla['example']}\n*** End Patch"
                bloquea(tools["write"][-1], {"mode": "patch", arg: v4a}, f"V4A agrega patterns[{regla['id']}]")
                borrado = f"*** Begin Patch\n*** Update File: {regla['examplePath']}\n-{regla['example']}\n*** End Patch"
                pasa(tools["write"][-1], {"mode": "patch", arg: borrado}, f"V4A que BORRA patterns[{regla['id']}] (limpiar no se frena)")
    elif enrepo:
        check(False, "tools.$multiFilePatch vacío: un patch V4A de Hermes (sin `path`) se saltea los frenos de escritura")

    # El cwd de la SESIÓN, no el del proceso: `cd .git` y después `write_file config`.
    git_rule = next((r for r in enrepo if r["example"].startswith(".git/")), None)
    if git_rule:
        viejo = {k: os.environ.get(k) for k in ("HARNESS_REPO", "TERMINAL_CWD")}
        try:
            os.environ.pop("HARNESS_REPO", None)
            os.environ["TERMINAL_CWD"] = str(REPO_ROOT / ".git")
            nombre = git_rule["example"].split("/", 1)[1]
            bloquea(tools["write"][0], {"path": nombre, "content": "x"}, f"ruta relativa al cwd de la sesión (.git/) → `{nombre}`")
            # Hermes arrancado FUERA del repo (gateway, cron): el arnés sigue el cwd de la sesión.
            with tempfile.TemporaryDirectory() as fuera:
                antes = os.getcwd()
                os.chdir(fuera)
                try:
                    os.environ["TERMINAL_CWD"] = str(REPO_ROOT)
                    bloquea(tools["write"][0], {"path": git_rule["example"], "content": "x"}, "proceso de Hermes fuera del repo, sesión adentro")
                finally:
                    os.chdir(antes)
        finally:
            for k, v in viejo.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    # Limpiar lo que ya se guardó: sacar un secreto de la memoria o un paso de una skill (P3).
    for regla in mem.get("deny") or []:
        if regla.get("example"):
            pasa(tools["memory"][0], {"action": "remove", "target": "memory", "old_text": regla["example"]}, f"memoria: remove de memory.deny[{regla['id']}]")
            pasa(tools["memory"][0], {"action": "replace", "old_text": regla["example"], "content": "ok"}, f"memoria: reemplazar memory.deny[{regla['id']}] por algo limpio")
    if heredadas:
        ej0 = heredadas[0]["example"]
        pasa(tools["skill"][0], {"operations": [{"action": "patch", "name": "x", "old_string": ej0, "new_string": "paso limpio"}]}, "skill: patch que SACA un paso prohibido")
        pasa(tools["skill"][0], {"operations": [{"action": "delete", "name": "x", "content": ej0}]}, "skill: borrar una skill que enseñaba un paso prohibido")
        bloquea(tools["skill"][0], {"operations": [{"action": "patch", "name": "x", "old_string": "a", "new_string": ej0}]}, "skill: patch que AGREGA un paso prohibido")

    # Reglas de fuera del repo: contra la ruta resuelta y con un HERMES_HOME movido.
    fuera_rules = [r for r in config.get("protectedPaths") or [] if r.get("outsideRepo") and r.get("example")]
    if fuera_rules:
        r0 = fuera_rules[0]
        cola = r0["example"].split("/.hermes/", 1)[-1]
        with tempfile.TemporaryDirectory() as home:
            d = guards.evaluate(core.Event(tools["write"][0], {"path": f".hermes/{cola}", "content": "x"}, cwd=home), config, REPO_ROOT)
            check(d.block, f"`.hermes/{cola}` relativo a un cwd en el home no frena (protectedPaths[{r0['id']}])")
            viejo = os.environ.get("HERMES_HOME")
            os.environ["HERMES_HOME"] = str(Path(home) / "perfil-movido")
            try:
                d = guards.evaluate(core.Event(tools["write"][0], {"path": str(Path(home) / "perfil-movido" / cola), "content": "x"}), config, REPO_ROOT)
                check(d.block, f"un HERMES_HOME movido desprotege protectedPaths[{r0['id']}]")
            finally:
                if viejo is None:
                    os.environ.pop("HERMES_HOME", None)
                else:
                    os.environ["HERMES_HOME"] = viejo

    # Worktree (`hermes -w`): `.git` es un archivo; el marcador tiene que caer en el gitdir real.
    with tempfile.TemporaryDirectory() as tmp:
        wt, real = Path(tmp) / "wt", Path(tmp) / "gitdir"
        wt.mkdir()
        real.mkdir()
        (wt / ".git").write_text(f"gitdir: {real}\n", encoding="utf-8")
        core.mark_gate_dirty(config, wt)
        m = core.marker_path(config, wt)
        check(m is not None and m.exists() and real in m.parents, f"en un worktree el marcador del gate no se escribe ({m})")
        check(turn.verify(config, wt) is not None, "en un worktree pre_verify no ve el gate pendiente")

    # ── 4. El contrato con Hermes (P5) ───────────────────────────────────────
    section("4. contrato del plugin con Hermes (P5)")
    ej_deny = (t.get("deny") or [{}])[0].get("example", "")
    # 4a. basura en los kwargs: nunca lanza (en pre_tool_call Hermes convierte la excepción en bloqueo)
    for kw in ({}, {"tool_name": None, "args": None}, {"tool_name": tools["shell"][0], "args": "no-es-dict"},
               {"tool_name": tools["write"][0], "args": {"path": 123}}, {"campo_nuevo_de_hermes": 1}):
        try:
            r = pre(**kw)
            check(r is None, f"kwargs basura {kw} → debía dejar pasar, obtuvo {r!r}")
        except Exception as e:  # noqa: BLE001
            check(False, f"pre_tool_call lanzó con {kw}: {e!r} (Hermes lo convierte en BLOQUEO)")
    # 4b. un freno que revienta deja pasar
    # Se parchea el módulo que usa el PLUGIN (`<paquete>.harness.guards`), no el `harness.guards`
    # importado acá: son dos objetos distintos, y parchear el equivocado da un verde falso.
    pg = plugin.guards
    original = pg.GUARDS["shell"]
    pg.GUARDS["shell"] = [lambda *a: 1 / 0]
    try:
        check(pre(tool_name=tools["shell"][0], args={"command": ej_deny}) is None, "un freno que revienta bloqueó")
    finally:
        pg.GUARDS["shell"] = original
    # 4c. el núcleo entero revienta: `_seguro` lo ataja
    ev_orig = plugin.guards.evaluate
    plugin.guards.evaluate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("roto"))
    try:
        check(pre(tool_name=tools["shell"][0], args={"command": ej_deny}) is None, "_seguro no atajó la excepción")
    finally:
        plugin.guards.evaluate = ev_orig
    # 4d. sin config / config inválido: deja pasar
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HARNESS_REPO"] = tmp
        check(pre(tool_name=tools["shell"][0], args={"command": ej_deny}) is None, "sin config bloqueó (P5)")
        (Path(tmp) / ".hermes").mkdir()
        (Path(tmp) / ".hermes" / "harness.config.json").write_text("{ roto", encoding="utf-8")
        check(pre(tool_name=tools["shell"][0], args={"command": ej_deny}) is None, "config inválido bloqueó (P5)")
        os.environ["HARNESS_REPO"] = str(REPO_ROOT)
    # 4e. un block siempre lleva mensaje: sin él Hermes lo ignora
    check(core.Decision.deny("").to_hermes()["message"] != "", "un block sin mensaje (Hermes lo ignoraría)")

    # ── 5. El shell hook, de punta a punta con un proceso real ───────────────
    section("5. shell hook (scripts/hook.py) con el payload de Hermes")
    hook = HARNESS_HOME / "scripts" / "hook.py"

    def run_hook(payload, env_extra=None, cwd=None, raw=None):
        env = {**os.environ, **(env_extra or {})}
        return subprocess.run([sys.executable, str(hook)], input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=cwd or REPO_ROOT, timeout=30)

    base = {"hook_event_name": "pre_tool_call", "tool_name": tools["shell"][0], "session_id": "s",
            "cwd": str(REPO_ROOT), "profile": "default", "extra": {}}
    p = run_hook({**base, "tool_input": {"command": ej_deny}})
    check(p.returncode == 2, f"shell hook con comando prohibido: exit {p.returncode}, esperaba 2")
    try:
        check(json.loads(p.stdout).get("action") == "block", "shell hook: stdout sin JSON de bloqueo")
    except ValueError:
        check(False, f"shell hook: stdout no es JSON ({p.stdout!r})")
    check(bool(p.stderr.strip()), "shell hook: stderr vacío (Hermes lo usa si el stdout no parsea)")
    p = run_hook({**base, "tool_input": {"command": (t.get("innocent") or ["git status"])[0]}})
    check(p.returncode == 0 and not p.stdout.strip(), f"shell hook inocente: exit {p.returncode}, stdout {p.stdout!r}")
    p = run_hook(None, raw="esto no es json")
    check(p.returncode == 0, f"shell hook con stdin basura: exit {p.returncode}")
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if k != "HARNESS_REPO"}
        p = subprocess.run([sys.executable, str(hook)], input=json.dumps({**base, "cwd": tmp, "tool_input": {"command": ej_deny}}),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=tmp, timeout=30)
        check(p.returncode == 0, f"shell hook fuera de un repo con config: exit {p.returncode} (debía dejar pasar)")

    # ── 6. El turno: gate pendiente, lint tras escribir, estado, ruteo ──────
    section("6. turno: pre_verify, transform_tool_result, estado de sesión, ruteo")
    with tempfile.TemporaryDirectory() as tmp:
        troot = Path(tmp).resolve()
        (troot / ".hermes").mkdir()
        cfg = copy.deepcopy(config)
        (troot / ".hermes" / "harness.config.json").write_text(json.dumps(cfg), encoding="utf-8")
        (troot / ".git").mkdir()
        (troot / ".git" / "HEAD").write_text("ref: refs/heads/feat/prueba\n", encoding="utf-8")
        os.environ["HARNESS_REPO"] = str(troot)
        try:
            verify = ctx.hooks["pre_verify"][0]
            check(verify(changed_paths=["docs/x.md"]) is None, "pre_verify sin gate pendiente pidió seguir")
            codigo = next((g for g in (config.get("gate") or {}).get("codeGlobs") or []), "")
            ext = next(iter((config.get("gate") or {}).get("codeExtensions") or [".py"]))
            rel = f"{codigo.rstrip('/')}/nuevo{ext}" if codigo else f"nuevo{ext}"
            (troot / rel).parent.mkdir(parents=True, exist_ok=True)
            patron = next((r for r in config.get("patterns") or [] if r.get("examplePath")), None)
            contenido = patron["example"] if patron and re.search((patron.get("paths") or ["."])[0], rel) else "x = 1\n"
            (troot / rel).write_text(contenido, encoding="utf-8")
            transform = ctx.hooks["transform_tool_result"][0]
            r = transform(tool_name=tools["write"][0], args={"path": rel, "content": contenido}, result='{"ok": true}', status="ok")
            check(core.marker_path(cfg, troot).exists(), "escribir código no marcó el gate pendiente")
            if patron and contenido == patron["example"]:
                check(isinstance(r, str) and f"PATRON[{patron['id']}]" in r, "transform_tool_result no devolvió el hallazgo del lint")
            check(transform(tool_name=tools["write"][0], args={"path": rel}, result='{"error":"x"}', status="error") is None,
                  "transform_tool_result decoró un resultado de error")
            v = verify(changed_paths=[rel])
            check(isinstance(v, dict) and v.get("action") == "continue" and v.get("message"), f"pre_verify con gate pendiente: {v!r}")
            estado = plugin._seccion_estado({"cwd": str(troot)})
            check("feat/prueba" in estado, "la sección de estado no lee la rama de .git/HEAD")
            check("Gate pendiente" in estado, "la sección de estado no avisa del gate pendiente")
            check(len(estado) <= 4000, f"sección de estado de {len(estado)} > 4000 (Hermes la rechaza)")
            llm = ctx.hooks["pre_llm_call"][0]
            for rt in config.get("routes") or []:
                check(bool(rt.get("example")), f"routes[{rt.get('id')}] sin `example`")
                if rt.get("example"):
                    r = llm(user_message=rt["example"], is_first_turn=True)
                    check(isinstance(r, dict) and rt["hint"] in r.get("context", ""), f"routes[{rt['id']}] no rutea su ejemplo")
            check(llm(user_message="¿qué hora es?") is None, "ruteo inventó una pista para un pedido neutro")
        finally:
            os.environ["HARNESS_REPO"] = str(REPO_ROOT)

    # ── 7. Las clases del lint muerden (por stdin: no escribe archivos) ──────
    section("7. reglas del lint")
    inc = config.get("incidents") or {}
    if inc.get("file"):
        completos = "\n".join(f"- **{c}:** x" for c in inc.get("requiredLines") or [])
        check(not rules.rule_incidente(config, inc["file"], f"{inc['heading']} bien\n{completos}\n"), "INCIDENTE: muerde un incidente completo")
        incompleto = "\n".join(f"- **{c}:** x" for c in (inc.get("requiredLines") or [])[:-1])
        check(bool(rules.rule_incidente(config, inc["file"], f"{inc['heading']} mal\n{incompleto}\n")), "INCIDENTE: no caza un incidente sin su último campo")
    ctxc = config.get("context") or {}
    for f in ctxc.get("files") or []:
        for r in ctxc.get("blockedPatterns") or []:
            check(bool(r.get("example")), f"context.blockedPatterns[{r.get('id')}] sin `example`")
            if r.get("example"):
                check(any(f"CONTEXTO[{r['id']}]" in h for h in rules.rule_contexto(config, f, f"# ok\n{r['example']}\n")),
                      f"CONTEXTO: no caza `{r['id']}` en {f}")
        if ctxc.get("maxChars"):
            check(bool(rules.rule_contexto(config, f, "x" * (ctxc["maxChars"] + 1))), "CONTEXTO: no caza un archivo sobre el tope")
            check(not rules.rule_contexto(config, f, "# Reglas\nCorré el gate.\n"), "CONTEXTO: muerde un archivo inocente")
    for root in (config.get("skills") or {}).get("roots") or []:
        ok = f"---\nname: buena\ndescription: Hace una cosa.\n---\ncuerpo\n"
        check(not rules.rule_skill(config, f"{root}/buena/SKILL.md", ok), "SKILL: muerde una skill válida")
        check(bool(rules.rule_skill(config, f"{root}/x/SKILL.md", "sin frontmatter")), "SKILL: no caza la falta de frontmatter")
        check(bool(rules.rule_skill(config, f"{root}/otra/SKILL.md", ok)), "SKILL: no caza name ≠ carpeta")
        check(bool(rules.rule_skill(config, f"{root}/Mala/SKILL.md", ok.replace("buena", "Mala"))), "SKILL: no caza un name inválido")
        check(bool(rules.rule_skill(config, f"{root}/buena/SKILL.md", "---\nname: buena\n---\n")), "SKILL: no caza la falta de description")
        multi = "---\nname: buena\ndescription: >\n  línea uno\n  línea dos\n---\n"
        check(not rules.rule_skill(config, f"{root}/buena/SKILL.md", multi), "SKILL: no entiende una description multilínea")
    for inv in config.get("invariants") or []:
        if inv.get("mustContain"):
            check(bool(rules.rule_invariante(config, inv["file"], "")), f"INVARIANTE {inv['file']}: no caza un archivo vacío")
        actual = (REPO_ROOT / inv["file"]).read_text(encoding="utf-8") if (REPO_ROOT / inv["file"]).is_file() else ""
        check(not rules.rule_invariante(config, inv["file"], actual), f"INVARIANTE {inv['file']}: el archivo real ya lo viola")
    # Los mustNotContain de hook.py y del plugin, a mano: son las dos violaciones de P5.
    # (Sólo en el repo del arnés: en un repo instalado esos archivos viven bajo .hermes/harness/.)
    con_inv = {i.get("file") for i in config.get("invariants") or []}
    if "scripts/hook.py" in con_inv:
        check(bool(rules.rule_invariante(config, "scripts/hook.py", "return 2\n        return 1\n")), "INVARIANTE: no caza un `return 1` en el shell hook")
    if "plugin/__init__.py" in con_inv:
        check(bool(rules.rule_invariante(config, "plugin/__init__.py", "def _seguro(\n@_seguro\ndef on_pre_tool_call\n    raise X\n")), "INVARIANTE: no caza un `raise` en el plugin")
    p = subprocess.run([sys.executable, str(HARNESS_HOME / "scripts" / "lint.py"), "--stdin", (ctxc.get("files") or ["AGENTS.md"])[0]],
                       input="x" * ((ctxc.get("maxChars") or 10) + 1), capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO_ROOT, timeout=60)
    check(p.returncode == 1, f"lint --stdin no falla con un hallazgo (exit {p.returncode})")

    # ── 8. Señales del gate (P6) ─────────────────────────────────────────────
    section("8. gate: cada señal declara qué error atrapa")
    senales = (config.get("gate") or {}).get("signals") or []
    check(bool(senales), "gate.signals vacío")
    for s in senales:
        check(bool(str(s.get("why", "")).strip()), f"señal `{s.get('name')}` sin `why` (P6)")
        cmd = s.get("command") or []
        check(isinstance(cmd, list) and cmd, f"señal `{s.get('name')}` sin command argv")
        for a in cmd[1:]:
            if isinstance(a, str) and a.endswith(".py"):
                check((REPO_ROOT / a).is_file(), f"señal `{s.get('name')}` apunta a {a}, que no existe")

    # Windows: consola cp1252. El gate imprime `▶ ✓ ✗` y reventaba antes de verificar nada (la
    # matriz de CI lo cazó). Se emula forzando cp1252 en cada script que imprime no-ASCII.
    cp1252 = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    for script, args in (("lint.py", ["--rules"]), ("linkcheck.py", []), ("doctor.py", [])):
        p = subprocess.run([sys.executable, str(HARNESS_HOME / "scripts" / script), *args], cwd=REPO_ROOT,
                           env=cp1252, capture_output=True, timeout=120)
        check(b"UnicodeEncodeError" not in p.stderr, f"{script} revienta con una consola cp1252 (Windows): {p.stderr[-200:]!r}")
    with tempfile.TemporaryDirectory() as tmp:
        troot = Path(tmp)
        for d in ("plugin", "scripts"):
            shutil.copytree(HARNESS_HOME / d, troot / d, ignore=shutil.ignore_patterns("__pycache__"))
        (troot / ".hermes").mkdir()
        mini = {"gate": {"marker": ".git/harness-gate-dirty", "signals": [
            {"name": "señal trivial ✓", "command": ["python3", "-c", "print('ñ ✓')"], "why": "prueba de consola"}]}}
        (troot / ".hermes" / "harness.config.json").write_text(json.dumps(mini), encoding="utf-8")
        p = subprocess.run([sys.executable, str(troot / "scripts" / "gate.py")], cwd=troot, env=cp1252, capture_output=True, timeout=120)
        check(p.returncode == 0 and b"UnicodeEncodeError" not in p.stderr,
              f"gate.py revienta con una consola cp1252 (Windows): rc {p.returncode} {p.stderr[-200:]!r}")

    # ── 9. Hooks de git: registro del trabajo (P11) y rutas protegidas ───────
    section("9. hooks de git (pre-commit, commit-msg)")
    sys.path.insert(0, str(HARNESS_HOME / "scripts"))
    import githooks  # noqa: E402

    cm = config.get("commitMsg") or {}
    if cm.get("codePattern"):
        gg = config.get("gate") or {}
        candidatas = [f"{d}x{e}" for d in (gg.get("codeGlobs") or []) + [""] for e in (gg.get("codeExtensions") or [".py"])]
        cod = next((c for c in candidatas if re.search(cm["codePattern"], c)), None)
        check(bool(cod), "commitMsg.codePattern no casa con ningún archivo de código (codeGlobs × codeExtensions)")
        if cod:
            ej_issue = (config.get("tracker") or {}).get("issueExample", "#1")
            fuga = cm.get("escapeLine", "no-issue:")
            check(githooks.commit_msg(config, "feat: x\n", [cod]) is not None, "commit-msg deja pasar código sin registro")
            check(githooks.commit_msg(config, f"feat: x {ej_issue}\n", [cod]) is None, "commit-msg frena un commit con su ítem")
            check(githooks.commit_msg(config, f"fix: x\n\n{fuga} typo sin superficie\n", [cod]) is None, "commit-msg frena la fuga declarada")
            check(githooks.commit_msg(config, f"fix: x\n\n{fuga}\n", [cod]) is not None, "commit-msg acepta una fuga sin motivo")
            check(githooks.commit_msg(config, "docs: x\n", ["docs/x.md"]) is None, "commit-msg pide ítem para sólo docs")
            check(githooks.commit_msg(config, "Merge branch 'x'\n", [cod]) is None, "commit-msg frena un merge")
    enrepo = [r for r in config.get("protectedPaths") or [] if not r.get("agentOnly") and not r.get("outsideRepo") and r.get("example")]
    for r in enrepo:
        check(bool(githooks.pre_commit(config, [r["example"]])), f"pre-commit deja commitear {r['example']}")
    for r in config.get("protectedPaths") or []:
        if r.get("agentOnly") and r.get("example"):
            check(not any("ruta protegida" in f for f in githooks.pre_commit(config, [r["example"]])),
                  f"pre-commit frena {r['example']}, que es agentOnly (sólo el agente no lo edita)")
    # De punta a punta: el envoltorio de .githooks/ en un repo git temporal.
    if shutil.which("git") and shutil.which("sh"):
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            for d in ("plugin", "scripts"):
                shutil.copytree(HARNESS_HOME / d, troot / d, ignore=shutil.ignore_patterns("__pycache__"))
            ghooks = next((b / ".githooks" for b in (HARNESS_HOME, REPO_ROOT) if (b / ".githooks").is_dir()), None)
            if ghooks:
                shutil.copytree(ghooks, troot / ".githooks")
            (troot / ".hermes").mkdir()
            shutil.copy(CONFIG_PATH, troot / ".hermes" / "harness.config.json")
            g = lambda *a: subprocess.run(["git", *a], cwd=troot, capture_output=True, text=True, encoding="utf-8", errors="replace")  # noqa: E731
            g("init", "-q")
            g("config", "user.email", "t@t")
            g("config", "user.name", "t")
            g("config", "core.hooksPath", ".githooks")
            if cod:
                (troot / cod).parent.mkdir(parents=True, exist_ok=True)
                (troot / cod).write_text("x = 1\n", encoding="utf-8")
                g("add", cod)
                p = g("commit", "-q", "-m", "feat: sin registro")
                check(p.returncode != 0, "commit-msg real (en git) dejó pasar un commit de código sin registro")
                p = g("commit", "-q", "-m", f"feat: con registro {(config.get('tracker') or {}).get('issueExample', '#1')}")
                check(p.returncode == 0, f"commit-msg real frenó un commit con registro: {p.stdout}{p.stderr}")
            issue = (config.get("tracker") or {}).get("issueExample", "#1")
            # Un rename hacia una ruta protegida es un archivo protegido NUEVO en el commit.
            if enrepo:
                (troot / "notas.txt").write_text("x\n", encoding="utf-8")
                g("add", "notas.txt")
                g("commit", "-q", "-m", f"docs: notas {issue}")
                destino = enrepo[0]["example"]
                (troot / destino).parent.mkdir(parents=True, exist_ok=True)
                p = g("mv", "notas.txt", destino)
                if p.returncode == 0:
                    p = g("commit", "-q", "-m", f"chore: mover {issue}")
                    check(p.returncode != 0, f"pre-commit real dejó pasar un rename hacia {destino}")
                    g("reset", "-q", "HEAD")
            # Lo que se commitea es el índice: un secreto staged y limpiado del disco igual entra.
            # Un examplePath que NO sea un archivo existente: pisar `plugin/harness/core.py` rompía el
            # propio hook y el commit fallaba por la razón equivocada (un verde falso de este caso).
            pat = next((r for r in config.get("patterns") or [] if r.get("example") and r.get("examplePath")
                        and not (troot / r["examplePath"]).exists()), None)
            check(pat is not None, "ningún patterns[] con examplePath libre para probar el índice en git real")
            if pat:
                f = troot / pat["examplePath"]
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(pat["example"] + "\n", encoding="utf-8")
                g("add", pat["examplePath"])
                f.write_text("limpio\n", encoding="utf-8")
                p = g("commit", "-q", "-m", f"docs: x {issue}")
                check(p.returncode != 0, "pre-commit real leyó el disco y no el índice: el patrón staged entró al commit")

    # ── 12. Las piezas traídas de agent-harness: cada una muerde y no de más ──
    section("12. coherencia, perfiles, pre-push, deriva, mapa, costo y controles fuera del gate")
    import drift as drift_mod  # noqa: E402
    import map as mapa_mod  # noqa: E402
    import timing as timing_mod  # noqa: E402

    # COHERENCIA (P18): cada `example` de `terminal.deny` recomendado en una guía es rojo.
    co = config.get("coherence") or {}
    if co.get("commandPattern"):
        guia = next((g for g in co.get("guides") or [] if g.endswith(".md")), None) or \
            f"{(co.get('guides') or ['docs'])[0].rstrip('/')}/x.md"
        check(rules.es_guia(config, guia), f"coherence.guides: `{guia}` no cuenta como guía")
        rx = re.compile(co["commandPattern"])
        con_forma = [r for r in (config.get("terminal") or {}).get("deny") or [] if r.get("example") and rx.search(r["example"])]
        check(bool(con_forma), "COHERENCIA: ningún `terminal.deny[].example` tiene la forma de `commandPattern`: la regla no prueba nada")
        for r in con_forma:
            hall = rules.rule_coherencia(config, guia, f"# guía\n```bash\n$ {r['example']}  # así\n```\n")
            check(any("COHERENCIA" in h for h in hall), f"COHERENCIA: no caza `{r['example']}` recomendado en {guia}")
            check(not rules.rule_coherencia(config, guia, f"No hagas `{r['example']}`.\n"),
                  f"COHERENCIA: muerde `{r['example']}` citado en prosa (fuera de un bloque de shell)")
        check(not rules.rule_coherencia(config, guia, "```bash\ngit status\n```\n"), "COHERENCIA: muerde un `git status` recomendado")
        check(not rules.rule_coherencia(config, guia, "```python\n" + (con_forma[0]["example"] if con_forma else "") + "\n```\n"),
              "COHERENCIA: mira un bloque que no es de shell")
        check(not rules.rule_coherencia(config, "fuera/de/las/guias.md", "```bash\n" + (con_forma[0]["example"] if con_forma else "") + "\n```\n"),
              "COHERENCIA: mira un archivo que no es guía")
        if len(con_forma) >= 2:
            cfg_rel = co.get("configFile", ".hermes/harness.config.json")
            a, b = con_forma[0], con_forma[1]
            ofrece = json.dumps({"terminal": {"deny": [{**a, "reason": f"usá `{b['example']}` en su lugar"}, b]}})
            check(any("COHERENCIA" in h for h in rules.rule_coherencia({**config, "terminal": json.loads(ofrece)["terminal"]}, cfg_rel, ofrece)),
                  "COHERENCIA: no caza un `reason` que ofrece como salida un comando vedado")
            propia = json.dumps({"terminal": {"deny": [{**a, "reason": f"`{a['example']}` es la ofensa"}]}})
            check(not rules.rule_coherencia(config, cfg_rel, propia), "COHERENCIA: muerde la ofensa citada por su propia regla")

    # PERFIL (P17): un perfil con una clave prohibida es rojo; uno sin lo obligatorio, también.
    pf_spec = config.get("profiles") or {}
    if pf_spec.get("dir"):
        rel_pf = f"{pf_spec['dir'].rstrip('/')}/x.json"
        base_pf = {k: ["x"] for k in pf_spec.get("requiredKeys") or []}
        check(not rules.rule_perfil(config, rel_pf, json.dumps(base_pf)), "PERFIL: muerde un perfil con sólo lo obligatorio")
        for k in pf_spec.get("forbiddenKeys") or []:
            malo = copy.deepcopy(base_pf)
            nodo = malo
            *padres, hoja = k.split(".")
            for p_ in padres:
                nodo = nodo.setdefault(p_, {})
            nodo[hoja] = [{"pattern": "x"}]
            check(bool(rules.rule_perfil(config, rel_pf, json.dumps(malo))), f"PERFIL: no caza `{k}` en un perfil")
        for k in pf_spec.get("requiredKeys") or []:
            check(bool(rules.rule_perfil(config, rel_pf, json.dumps({x: v for x, v in base_pf.items() if x != k}))),
                  f"PERFIL: no caza un perfil sin `{k}`")
        check(bool(rules.rule_perfil(config, rel_pf, "{no es json")), "PERFIL: no caza un perfil que no es JSON")

    # pre-push: empujar directo a una rama protegida frena; a otra rama, no.
    for rama in (config.get("branches") or {}).get("protected") or []:
        check(githooks.pre_push(config, [f"refs/heads/x abc refs/heads/{rama} def"]) is not None, f"pre-push deja empujar directo a `{rama}`")
    check(githooks.pre_push({**config, "branches": {"protected": ["main"]}}, ["refs/heads/f abc refs/heads/feat/x def"]) is None,
          "pre-push frena una rama de trabajo")
    check(githooks.pre_push({**config, "branches": {"protected": ["main"]}}, ["refs/heads/f abc refs/heads/main def"]) is not None,
          "pre-push no mira `branches.protected`")
    # De punta a punta: el envoltorio de .githooks/pre-push recibe las refs por stdin de git real.
    ghooks = next((b / ".githooks" for b in (HARNESS_HOME, REPO_ROOT) if (b / ".githooks" / "pre-push").is_file()), None)
    if ghooks and shutil.which("git") and shutil.which("sh"):
        with tempfile.TemporaryDirectory() as tmp:
            troot, remoto = Path(tmp) / "repo", Path(tmp) / "remoto.git"
            for d in ("plugin", "scripts"):
                shutil.copytree(HARNESS_HOME / d, troot / d, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(ghooks, troot / ".githooks")
            (troot / ".hermes").mkdir()
            (troot / ".hermes" / "harness.config.json").write_text(
                json.dumps({"branches": {"protected": ["main"], "reason": "por PR"}}), encoding="utf-8")
            g = lambda *a: subprocess.run(["git", *a], cwd=troot, capture_output=True, text=True, encoding="utf-8", errors="replace")  # noqa: E731
            subprocess.run(["git", "init", "-q", "--bare", str(remoto)], capture_output=True)
            for a in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"), ("config", "user.name", "t"),
                      ("config", "core.hooksPath", ".githooks"), ("remote", "add", "origin", str(remoto))):
                g(*a)
            (troot / "a.txt").write_text("a\n", encoding="utf-8")
            g("add", "a.txt")
            g("commit", "-q", "-m", "docs: a")
            p = g("push", "-q", "origin", "main")
            check(p.returncode != 0 and "rama protegida" in p.stdout + p.stderr, f"pre-push real dejó empujar a main: {p.stdout}{p.stderr}")
            p = g("push", "-q", "origin", "main:feat/x")
            check(p.returncode == 0, f"pre-push real frenó una rama de trabajo: {p.stdout}{p.stderr}")

    # Deriva (P20): un veredicto viejo o sin fecha es rojo; uno fresco, verde.
    dr = config.get("drift") or {}
    if dr.get("statusDatePattern") and dr.get("statusMaxAgeDays"):
        import datetime as dt
        hoy = dt.date(2026, 9, 30)
        texto = lambda d: f"- **Fecha del último gate completo:** {d}\n"  # noqa: E731
        fresca, vieja = hoy - dt.timedelta(days=int(dr["statusMaxAgeDays"])), hoy - dt.timedelta(days=int(dr["statusMaxAgeDays"]) + 1)
        check(bool(re.search(dr["statusDatePattern"], texto(hoy))), "drift.statusDatePattern no casa con la línea de fecha del STATUS")
        check(not drift_mod.edad_del_veredicto(config, texto(fresca), hoy)[0], "drift: rojo con un veredicto dentro del plazo")
        check(bool(drift_mod.edad_del_veredicto(config, texto(vieja), hoy)[0]), "drift: no caza un veredicto vencido")
        check(bool(drift_mod.edad_del_veredicto(config, "sin fecha\n", hoy)[0]), "drift: no caza un STATUS sin fecha")
        check(bool(drift_mod.edad_del_veredicto(config, None, hoy)[0]), "drift: no caza un STATUS que no existe")
    pats = [r for r in config.get("patterns") or [] if r.get("example")]
    if pats:
        r0 = pats[0]
        ruta = r0.get("examplePath", "x.py")
        log = f"diff --git a/{ruta} b/{ruta}\n--- a/{ruta}\n+++ b/{ruta}\n@@ -1 +1 @@\n+{r0['example']}\n"
        check(r0 not in drift_mod.reglas_sin_cicatriz(config, log), f"drift: no ve que `{r0.get('id')}` cazó algo en el historial")
        check(r0 in drift_mod.reglas_sin_cicatriz(config, ""), f"drift: da por cazada a `{r0.get('id')}` sin historial")

    # Controles fuera del gate: encendido y sin nadie que lo corra es «instalado y muerto».
    for clave, spec_ in config.items():
        if isinstance(spec_, dict) and spec_.get("runner"):
            runner = REPO_ROOT / spec_["runner"]
            check(runner.is_file(), f"`{clave}.runner` apunta a {spec_['runner']}, que no existe")
            cmd_ = spec_.get("command") or ""
            check(bool(cmd_) and runner.is_file() and Path(cmd_).name in runner.read_text(encoding="utf-8"),
                  f"`{clave}.runner` ({spec_['runner']}) no invoca `{cmd_}`: el control está encendido y nadie lo corre")

    # Mapa: el real está completo; una pieza nueva sin clasificar es rojo.
    if config.get("taxonomy"):
        m = mapa_mod.construir(config, REPO_ROOT, HARNESS_HOME)
        check(m is not None and not m["sinClasificar"], f"map: hay piezas sin clasificar: {(m or {}).get('sinClasificar')}")
        sin_git = copy.deepcopy(config)
        sin_git["taxonomy"]["gitHooks"] = {}
        m2 = mapa_mod.construir(sin_git, REPO_ROOT, HARNESS_HOME)
        check(any("hook de git" in s for s in m2["sinClasificar"]), "map: no caza un hook de git sin clasificar")
        sin_ev = copy.deepcopy(config)
        sin_ev["taxonomy"]["events"] = {}
        check(any("del plugin" in s for s in mapa_mod.construir(sin_ev, REPO_ROOT, HARNESS_HOME)["sinClasificar"]),
              "map: no caza un hook del plugin sin clasificar")
    check(mapa_mod.construir({}, REPO_ROOT, HARNESS_HOME) is None, "map: sin `taxonomy` inventa un mapa")

    # Costo: con presupuesto cero todo callback está pasado; si no, la medición no mide.
    if config.get("observability"):
        marcador = core.marker_path(config, REPO_ROOT)
        habia = bool(marcador and marcador.exists())
        cero = {**config, "observability": {**config["observability"], "budgetMs": 0, "budgets": {}, "runs": 1}}
        med = timing_mod.medir(cero, timing_mod.repo_de_prueba(config))
        check(len(med) >= 5 and all(ms > b for _, ms, b in med), "timing: con presupuesto 0 hay callbacks que no se pasan (¿mide algo?)")
        check(os.environ.get("HARNESS_REPO") == str(REPO_ROOT), "timing: no restauró HARNESS_REPO")
        check(bool(marcador and marcador.exists()) == habia, "timing: la medición tocó el marcador del gate del repo real (P7)")
        check(timing_mod.presupuesto({"budgetMs": 7, "budgets": {"pre_verify": 9}}, "pre_verify") == 9, "timing: ignora `budgets`")

    # ── 13. Autonomía: eventos, loop, CLI y panel (P21) ──────────────────────
    section("13. autonomía: registro de eventos, loop autónomo, CLI y panel")
    import cli as cli_mod  # noqa: E402
    import loop as loop_mod  # noqa: E402
    import panel as panel_mod  # noqa: E402
    from harness import events as events_mod  # noqa: E402

    obs_ev = (config.get("observability") or {}).get("events")
    check(isinstance(obs_ev, dict) and bool(obs_ev.get("file")), "observability.events no declara `file`: el panel no ve nada")
    deny0 = next((r for r in (config.get("terminal") or {}).get("deny") or [] if r.get("example")), None)

    # Eventos: el plugin registra lo que frena, sólo eso, con techo y sin lanzar jamás.
    with tempfile.TemporaryDirectory() as tmp:
        troot = Path(tmp).resolve()
        subprocess.run(["git", "init", "-q"], cwd=troot, capture_output=True)
        (troot / ".hermes").mkdir()
        cfg_ev = {**config, "observability": {**(config.get("observability") or {}), "events": {"file": ".git/harness-events.jsonl", "maxBytes": 400}}}
        (troot / ".hermes" / "harness.config.json").write_text(json.dumps(cfg_ev), encoding="utf-8")
        os.environ["HARNESS_REPO"] = str(troot)
        os.environ.pop("HARNESS_NO_EVENTS", None)
        try:
            if deny0 and tools.get("shell"):
                pre(tool_name=tools["shell"][0], args={"command": deny0["example"]}, session_id="selftest")
                evs = events_mod.tail(cfg_ev, troot)
                check(any(e.get("kind") == "block" and e.get("rule") == deny0.get("id") for e in evs),
                      f"el plugin no registró el bloqueo de `{deny0.get('id')}` en el registro de eventos")
                antes_ev = len(events_mod.tail(cfg_ev, troot))
                pre(tool_name=tools["shell"][0], args={"command": "git status"}, session_id="selftest")
                check(len(events_mod.tail(cfg_ev, troot)) == antes_ev, "el plugin registra eventos de lo que deja pasar")
                for _ in range(20):
                    events_mod.record(cfg_ev, troot, "x", relleno="y" * 40)
                p_ev = events_mod.path(cfg_ev, troot)
                check(p_ev.stat().st_size < 400 + 200 and p_ev.with_name(p_ev.name + ".1").exists(),
                      "el registro de eventos no rota pasado `maxBytes`: crece sin techo")
            os.environ["HARNESS_NO_EVENTS"] = "1"
            n_ev = len(events_mod.tail(cfg_ev, troot))
            events_mod.record(cfg_ev, troot, "apagado")
            check(len(events_mod.tail(cfg_ev, troot)) == n_ev, "HARNESS_NO_EVENTS no apaga el registro")
        finally:
            os.environ["HARNESS_REPO"] = str(REPO_ROOT)
            os.environ["HARNESS_NO_EVENTS"] = "1"
    try:
        events_mod.record({"observability": {"events": {"file": "no/existe/\0/x"}}}, Path("/nonexistent-dir-xyz"), "x")
        check(True, "")
    except Exception as e:  # noqa: BLE001
        check(False, f"events.record lanzó ({e!r}): en pre_tool_call eso BLOQUEARÍA la herramienta (P5)")

    # Loop — decisiones puras: la salida es el gate, el mismo rojo escala (P16), hay topes y freno de mano.
    lspec = config.get("loop") or {}
    check(bool(lspec), "el config no declara `loop`")
    if lspec:
        check(bool(lspec.get("agentCommand")) and any("{prompt}" in str(a) for a in lspec["agentCommand"]),
              "loop.agentCommand no lleva `{prompt}`: el agente no recibiría la tarea")
        check(int(lspec.get("sameFailureLimit", 0)) >= 1 and int(lspec.get("maxIterations", 0)) >= 1 and float(lspec.get("maxMinutes", 0)) > 0,
              "loop sin topes (`sameFailureLimit`, `maxIterations`, `maxMinutes`): un loop sin tope no es autónomo, es desatendido")
    sp = {"maxIterations": 4, "sameFailureLimit": 2, "maxMinutes": 60}
    roja = lambda f: {"green": False, "signature": f}  # noqa: E731
    check(loop_mod.decidir([roja("a"), {"green": True}], sp, 1, False)[0] == "verde", "loop: un gate verde no termina la tarea")
    check(loop_mod.decidir([roja("a")], sp, 1, False)[0] == "seguir", "loop: no reintenta tras un primer rojo")
    check(loop_mod.decidir([roja("a"), roja("a")], sp, 1, False)[0] == "escalar", "loop: el mismo rojo dos veces no escala (P16)")
    check(loop_mod.decidir([roja("a"), roja("b")], sp, 1, False)[0] == "seguir", "loop: escala con rojos DISTINTOS (hay hipótesis nueva)")
    check(loop_mod.decidir([roja("a"), roja("b"), roja("c"), roja("d")], sp, 1, False)[0] == "escalar", "loop: sin tope de iteraciones")
    check(loop_mod.decidir([roja("a")], sp, 3601, False)[0] == "escalar", "loop: sin tope de tiempo")
    check(loop_mod.decidir([roja("a")], sp, 1, True)[0] == "parado", "loop: ignora el freno de mano (`stopFile`)")
    check(loop_mod.firma("▶ x\n✗ lint (exit 1, 0.3s)\n✗ self-test (exit 1, 9.1s)\n") == "lint · self-test",
          "loop: la firma de un rojo del gate no son sus señales rojas")
    check(loop_mod.firma("✗ lint (exit 1, 0.3s)") == loop_mod.firma("✗ lint (exit 1, 7.9s)"),
          "loop: la duración cambia la firma (el mismo rojo parecería distinto y nunca escalaría)")
    check(loop_mod.firma("✗ tests (unittest) (exit 1, 0.3s)\n✗ docs: no existe el ejecutable `x`\n") == "docs · tests (unittest)",
          "loop: la firma corta el nombre de una señal con paréntesis o pierde la de un ejecutable ausente")
    tl = "# t\n- [x] hecha\n- [ ] sigue\n- [ ] otra\n"
    check(loop_mod.proxima_tarea(tl) == (2, "sigue"), "loop: no toma la primera casilla vacía")
    check(loop_mod.marcar(tl, 2, "!", "motivo").splitlines()[2] == "- [!] sigue — motivo", "loop: no marca la escalada")

    # Loop — de punta a punta, con un agente de mentira, en un repo temporal sobre una rama protegida.
    if shutil.which("git"):
        agente = ("import pathlib;p=pathlib.Path('n.txt');n=int(p.read_text()) if p.exists() else 0;p.write_text(str(n+1));"
                  "import sys;pathlib.Path('.git/harness-loop.stop').write_text('x') if 'PARAR' in sys.argv[1] else None")
        gate_ok2 = "import pathlib,sys;n=int(pathlib.Path('n.txt').read_text());print('✗ tests (exit 1)') if n<2 else None;sys.exit(0 if n>=2 else 1)"

        def loop_en(tmp, gate_src, tareas="# t\n- [ ] una tarea\n"):
            troot = Path(tmp)
            g_ = lambda *a: subprocess.run(["git", *a], cwd=troot, capture_output=True, text=True)  # noqa: E731
            g_("init", "-q", "-b", "main")
            for d in ("plugin", "scripts"):
                shutil.copytree(HARNESS_HOME / d, troot / d, ignore=shutil.ignore_patterns("__pycache__"))
            (troot / ".hermes" / "loop").mkdir(parents=True)
            cfg_l = {"branches": {"protected": ["main"]}, "observability": {"events": {"file": ".git/harness-events.jsonl"}},
                     "loop": {**sp, "tasksFile": ".hermes/loop/tasks.md", "agentCommand": ["python3", "-c", agente, "{prompt}"],
                              "gateCommand": ["python3", "-c", gate_src]}}
            (troot / ".hermes" / "harness.config.json").write_text(json.dumps(cfg_l), encoding="utf-8")
            (troot / ".hermes" / "loop" / "tasks.md").write_text(tareas, encoding="utf-8")
            g_("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
            env_l = {k: v for k, v in os.environ.items() if k not in ("HARNESS_REPO", "HARNESS_NO_EVENTS")}
            p_ = subprocess.run([sys.executable, str(troot / "scripts" / "loop.py"), "--apply"], cwd=troot, env=env_l,
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            est = json.loads((troot / ".git" / "harness-loop.json").read_text(encoding="utf-8")) if (troot / ".git" / "harness-loop.json").is_file() else {}
            return troot, p_, est, g_

        with tempfile.TemporaryDirectory() as tmp:
            troot, p_, est, g_ = loop_en(tmp, gate_ok2)
            check(p_.returncode == 0 and est.get("phase") == "verde" and len(est.get("attempts") or []) == 2,
                  f"loop real: no llegó a verde en el intento 2 (el gate decide, no el agente): rc={p_.returncode} {est}\n{p_.stdout[-600:]}")
            check("- [x] una tarea" in (troot / ".hermes" / "loop" / "tasks.md").read_text(encoding="utf-8"), "loop real: no marcó la tarea verde")
            check(g_("branch", "--show-current").stdout.strip().startswith("loop/"), "loop real: trabajó sobre la rama protegida")
            kinds = [e.get("kind") for e in events_mod.tail({"observability": {"events": {"file": ".git/harness-events.jsonl"}}}, troot)]
            check("loop-iter" in kinds and "loop-verde" in kinds, f"loop real: no dejó sus eventos para el panel ({kinds})")
        with tempfile.TemporaryDirectory() as tmp:
            troot, p_, est, _ = loop_en(tmp, "print('✗ lint (exit 1, 0.1s)');raise SystemExit(1)")
            check(p_.returncode == 2 and est.get("phase") == "escalar" and len(est.get("attempts") or []) == 2,
                  f"loop real: el mismo rojo dos veces no escaló con exit 2: rc={p_.returncode} {est.get('phase')} {len(est.get('attempts') or [])}")
            check("- [!] una tarea" in (troot / ".hermes" / "loop" / "tasks.md").read_text(encoding="utf-8"), "loop real: no marcó la escalada")
        with tempfile.TemporaryDirectory() as tmp:
            troot, p_, est, _ = loop_en(tmp, "raise SystemExit(1)", "# t\n- [ ] PARAR ya\n")
            check(p_.returncode == 2 and est.get("phase") == "parado" and len(est.get("attempts") or []) == 1,
                  f"loop real: el freno de mano no paró entre iteraciones: {est.get('phase')} {len(est.get('attempts') or [])}")
            check(not (troot / ".git" / "harness-loop.stop").exists(), "loop real: el pedido de parada quedó después de cumplirse")
        with tempfile.TemporaryDirectory() as tmp:
            troot = Path(tmp)
            (troot / ".hermes").mkdir()
            (troot / ".hermes" / "harness.config.json").write_text(json.dumps({"loop": {**sp}}), encoding="utf-8")
            for d in ("plugin", "scripts"):
                shutil.copytree(HARNESS_HOME / d, troot / d, ignore=shutil.ignore_patterns("__pycache__"))
            p_ = subprocess.run([sys.executable, str(troot / "scripts" / "loop.py"), "--task", "x"], cwd=troot, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=60)
            check(p_.returncode == 0 and "DRY-RUN" in p_.stdout and not (troot / "n.txt").exists(), "loop: sin --apply ejecutó algo (P9)")

    # CLI: una regla se prueba por el plugin ANTES de escribirse.
    buena = {"id": "selftest-nueva", "pattern": r"\bzzq-selftest\b", "example": "zzq-selftest --go", "reason": "prueba."}
    check(not cli_mod.validar(config, "terminal.deny", buena), f"cli: rechaza una regla buena: {cli_mod.validar(config, 'terminal.deny', buena)}")
    check(any("no frena" in e for e in cli_mod.validar(config, "terminal.deny", {**buena, "example": "otra cosa"})),
          "cli: acepta una regla cuyo ejemplo no frena (P2)")
    check(any("falta `example`" in e for e in cli_mod.validar(config, "terminal.deny", {**buena, "example": ""})), "cli: acepta una regla sin example")
    inoc = ((config.get("terminal") or {}).get("innocent") or ["git status"])[0]
    check(any("muerde de más" in e for e in cli_mod.validar(config, "terminal.deny", {**buena, "pattern": re.escape(inoc) + "|zzq-selftest"})),
          "cli: acepta una regla que muerde un inocente (P3)")
    gate_cmd = (config.get("gate") or {}).get("command", "python3 scripts/gate.py")
    sin_inoc = {**config, "terminal": {**(config.get("terminal") or {}), "innocent": []}}
    check(any(gate_cmd in e for e in cli_mod.validar(sin_inoc, "terminal.deny", {**buena, "pattern": re.escape(gate_cmd) + "|zzq-selftest"})),
          "cli: acepta una regla que veda el gate (el agente y el loop no podrían terminar nunca)")
    if deny0:
        check(any("ya lo frena" in e for e in cli_mod.validar(config, "terminal.deny", {**buena, "pattern": "zzq|" + deny0["pattern"], "example": deny0["example"]})),
              "cli: acepta una regla cuyo ejemplo ya frenaba otra (no prueba nada propio)")
        check(any("ya hay" in e for e in cli_mod.validar(config, "terminal.deny", {**buena, "id": deny0["id"]})), "cli: acepta un id repetido")
    check(cli_mod.get_ruta(cli_mod.set_ruta({"a": {"b": [1, 2]}}, "a.b.1", 9), "a.b.1") == 9, "cli: set/get por ruta con índice")
    multi = {"id": "zz-multi", "pattern": r"def f\(.*\n\s+return 1", "example": "def f():\n    return 1", "examplePath": "plugin/zz.py",
             "paths": ["^plugin/"], "reason": "x."}
    check(any("línea por línea" in e for e in cli_mod.validar(config, "patterns", multi)),
          "cli: acepta un `patterns` multilínea, que frena un write_file y nunca el lint ni un patch V4A")
    check(any("P6" in e for e in cli_mod.validar_senal(config, {"name": "x", "command": ["true"]})), "cli: acepta una señal del gate sin `why` (P6)")
    check(not cli_mod.validar_senal(config, {"name": "zz-nueva", "why": "porque", "command": ["true"]}), "cli: rechaza una señal buena")

    # Panel: el estado como dato, sólo local, y empuja por SSE.
    st_ = panel_mod.estado(config, REPO_ROOT)
    for k in ("branch", "gate", "rules", "loop", "events", "status"):
        check(k in st_, f"panel: el estado no trae `{k}`")
    srv = panel_mod.servidor(REPO_ROOT, port=0, intervalo=0.1)
    check(srv.server_address[0] == "127.0.0.1", f"panel: escucha en {srv.server_address[0]} por defecto, no sólo en esta máquina")
    import threading
    import urllib.request
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        with urllib.request.urlopen(base + "/api/state", timeout=10) as r:
            check(r.status == 200 and "rules" in json.loads(r.read().decode("utf-8")), "panel: /api/state no devuelve el estado")
        with urllib.request.urlopen(base + "/", timeout=10) as r:
            check("EventSource" in r.read().decode("utf-8"), "panel: la página no se suscribe al stream")
        with urllib.request.urlopen(base + "/api/stream", timeout=10) as r:
            check(r.readline().decode("utf-8").startswith("event: state"), "panel: el stream no empuja el estado")
    except OSError as e:
        check(False, f"panel: no respondió ({e})")
    finally:
        srv.shutdown()
        srv.server_close()

    # ── 11. Portado: el instalador y cada perfil, en un repo temporal ────────
    # (Primero, porque la sección 10 mira que nada quede en la raíz.)
    section("11. portado: instalador y perfiles de stack")
    install = HARNESS_HOME / "scripts" / "install.py"
    perfiles_dir = HARNESS_HOME / "plantillas" / "perfiles"
    if os.environ.get("HARNESS_NESTED"):
        print("  (omitida: corrida anidada dentro del portado)")
    elif HARNESS_HOME.resolve() != REPO_ROOT.resolve():
        # En un repo INSTALADO el código vive en `.hermes/harness/` y los hooks y skills en la raíz:
        # re-portar desde ahí no tiene de dónde copiarlos. Corría igual y dejaba el gate de todo
        # repo recién instalado en ROJO (lo destapó el ensayo del workshop; el portado anidado de
        # este self-test corre con HARNESS_NESTED y no lo veía). El portado se prueba acá, en el
        # repo del arnés, contra cada perfil.
        print("  (omitida: repo instalado — el portado se prueba en el repo del arnés)")
    elif not install.is_file():
        check(False, "no existe scripts/install.py")
    else:
        perfiles = sorted(perfiles_dir.glob("*.json"))
        check(bool(perfiles), "no hay perfiles de stack")
        for pf in perfiles:
            try:
                perfil = json.loads(pf.read_text(encoding="utf-8"))
            except ValueError as e:
                check(False, f"perfil {pf.name} no es JSON: {e}")
                continue
            check(perfil.get("name") == pf.stem, f"perfil {pf.name}: `name` ≠ nombre del archivo")
            check(bool(perfil.get("codeExtensions")), f"perfil {pf.stem}: sin codeExtensions")
            for r in perfil.get("protectedPaths") or []:
                ok = bool(r.get("example")) and bool(re.search(r.get("pattern", "(?!)"), r["example"]))
                check(ok, f"perfil {pf.stem}: protectedPaths[{r.get('id')}] sin example que case")
            for s in perfil.get("signals") or []:
                check(bool(s.get("why")), f"perfil {pf.stem}: señal `{s.get('name')}` sin why")
            if (config.get("profiles") or {}).get("dir"):
                rel_pf = f"{config['profiles']['dir'].rstrip('/')}/{pf.name}"
                check(not rules.rule_perfil(config, rel_pf, pf.read_text(encoding="utf-8")),
                      f"perfil {pf.stem} trae REGLAS: un perfil son hechos del stack, las reglas se escriben con cicatrices")

        env_hijo = {k: v for k, v in os.environ.items() if k != "HARNESS_REPO"}
        env_hijo["HARNESS_NESTED"] = "1"

        def correr(args, cwd):
            return subprocess.run([sys.executable, *args], cwd=cwd, env=env_hijo, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)

        with tempfile.TemporaryDirectory() as tmp:
            p = correr([str(install), tmp, "--profile", perfiles[0].stem if perfiles else "python"], REPO_ROOT)
            check(p.returncode == 0 and not any(Path(tmp).iterdir()), f"el dry-run escribió en el destino o falló: {p.stdout[-300:]}")

        for pf in perfiles:
            with tempfile.TemporaryDirectory() as tmp:
                t = Path(tmp)
                subprocess.run(["git", "init", "-q"], cwd=t, capture_output=True)
                p = correr([str(install), tmp, "--profile", pf.stem, "--apply"], REPO_ROOT)
                check(p.returncode == 0, f"[{pf.stem}] install --apply falló: {p.stdout[-400:]}{p.stderr[-400:]}")
                for f in (".hermes/harness.config.json", "AGENTS.md", ".hermes/harness/plugin/__init__.py",
                          ".hermes/harness/plugin/harness/core.py", ".githooks/commit-msg", ".githooks/pre-push",
                          ".github/workflows/harness-drift.yml", ".hermes/skills/gate/SKILL.md"):
                    check((t / f).is_file(), f"[{pf.stem}] el instalador no dejó {f}")
                for script in ("selftest.py", "lint.py", "linkcheck.py", "map.py", "timing.py"):
                    p = correr([str(t / ".hermes" / "harness" / "scripts" / script)], t)
                    check(p.returncode == 0, f"[{pf.stem}] {script} del repo instalado sale rojo:\n{(p.stdout + p.stderr)[-800:]}")
                if pf == perfiles[0]:
                    # El self-test del repo instalado, como lo corre su gate: SIN la marca de anidado.
                    env_real = {k: v for k, v in env_hijo.items() if k != "HARNESS_NESTED"}
                    try:
                        p = subprocess.run([sys.executable, str(t / ".hermes" / "harness" / "scripts" / "selftest.py")], cwd=t, env=env_real,
                                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
                        check(p.returncode == 0, f"[{pf.stem}] el self-test de un repo recién instalado (sin HARNESS_NESTED) sale rojo:\n{(p.stdout + p.stderr)[-800:]}")
                    except subprocess.TimeoutExpired:
                        check(False, f"[{pf.stem}] el self-test de un repo recién instalado no termina (¿re-porta el arnés desde la instalación?)")
                    # Lo instalado se tiene que poder COMMITEAR: el lint de un repo recién instalado
                    # no tiene nada versionado y pasa vacío; el pre-commit mira lo staged de verdad
                    # (la plantilla del config trae el ejemplo de la clave privada, por ejemplo).
                    subprocess.run(["git", "add", ".hermes", ".githooks", ".github", "AGENTS.md", "STATUS.md", "docs"],
                                   cwd=t, capture_output=True)
                    p = correr([str(t / ".hermes" / "harness" / "scripts" / "githooks.py"), "pre-commit"], t)
                    check(p.returncode == 0, f"[{pf.stem}] lo que instala el instalador no pasa su propio pre-commit:\n{(p.stdout + p.stderr)[-600:]}")
                    # Nunca sobreescribe; --upgrade toca sólo el código del arnés.
                    (t / "AGENTS.md").write_text("# mío\n", encoding="utf-8")
                    core_py = t / ".hermes" / "harness" / "plugin" / "harness" / "core.py"
                    core_py.write_text("# viejo\n", encoding="utf-8")
                    correr([str(install), tmp, "--profile", pf.stem, "--apply"], REPO_ROOT)
                    check((t / "AGENTS.md").read_text(encoding="utf-8") == "# mío\n", "el instalador sobreescribió AGENTS.md")
                    check(core_py.read_text(encoding="utf-8") == "# viejo\n", "--apply sin --upgrade reemplazó código")
                    correr([str(install), tmp, "--profile", pf.stem, "--apply", "--upgrade"], REPO_ROOT)
                    check(core_py.read_text(encoding="utf-8") != "# viejo\n", "--upgrade no reemplazó el código del arnés")
                    check((t / "AGENTS.md").read_text(encoding="utf-8") == "# mío\n", "--upgrade tocó AGENTS.md")
                    # --link-plugin en un HERMES_HOME temporal: nunca en el del usuario.
                    hh = t / "hermes-home"
                    env_link = {**env_hijo, "HERMES_HOME": str(hh)}
                    p = subprocess.run([sys.executable, str(install), tmp, "--link-plugin"], env=env_link, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                    check(p.returncode == 0 and not hh.exists(), "--link-plugin sin --apply escribió")
                    p = subprocess.run([sys.executable, str(install), tmp, "--link-plugin", "--apply"], env=env_link, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                    enlazado = hh / "plugins" / "repo-harness" / "__init__.py"
                    check(p.returncode == 0 and enlazado.is_file(), f"--link-plugin --apply no dejó el plugin: {p.stdout}{p.stderr}")

    # ── 10. P7: el self-test no dejó nada en la raíz ─────────────────────────
    section("10. el self-test no escribe en el árbol (P7)")
    raiz_despues = sorted(p.name for p in REPO_ROOT.iterdir())
    nuevos = set(raiz_despues) - set(raiz_antes)
    check(not nuevos, f"quedaron archivos nuevos en la raíz: {sorted(nuevos)}")

    print("\n" + "─" * 60)
    if FALLAS:
        print(f"SELF-TEST ROJO — {len(FALLAS)} falla(s), {OK} verificaciones verdes.")
        return 1
    print(f"SELF-TEST VERDE — {OK} verificaciones.")
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
