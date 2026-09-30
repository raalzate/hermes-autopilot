#!/usr/bin/env python3
"""
El plugin dentro del Hermes REAL: cada `example` del config por el despacho de Hermes.

    python3 scripts/hermes_e2e.py

El self-test prueba el plugin con un `ctx` falso; `hermes plugins doctor` prueba que carga. Esto
prueba lo que queda en el medio: que las decisiones del arnés SOBREVIVEN al código de Hermes que
las interpreta — que un `block` llega como bloqueo, que un `approve` llega como aprobación, que un
inocente pasa, que `pre_verify` sigue el turno y que la sección de estado se renderiza.

No ejecuta ninguna herramienta: usa las funciones de Hermes que resuelven la directiva de
`pre_tool_call` (`get_pre_tool_call_directive`) y el resto de los hooks, sin despachar nada.
Trabaja sobre una COPIA temporal del repo y un HERMES_HOME temporal: no toca ni el repo (P7) ni el
Hermes del usuario.

Corre con el intérprete de Hermes (lo saca del shebang del ejecutable `hermes`); si se lo invoca
con otro, se re-ejecuta con ése. Sin `hermes` en el PATH, sale 3: el gate lo marca OMITIDA
(`skipIfNoExecutable`), nunca verde.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent


def interprete_de_hermes() -> str | None:
    exe = shutil.which("hermes")
    if not exe:
        return None
    try:
        primera = Path(exe).read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return None
    if primera.startswith("#!"):
        partes = primera[2:].strip().split()
        return partes[-1] if partes and "env" in partes[0] and len(partes) > 1 else (partes[0] if partes else None)
    return None


def main() -> int:
    if os.environ.get("HARNESS_E2E_INNER") != "1":
        py = interprete_de_hermes()
        if not py:
            print("hermes_e2e: no hay `hermes` en el PATH (o no se puede leer su intérprete).")
            return 3
        return subprocess.run([py, __file__], env={**os.environ, "HARNESS_E2E_INNER": "1"}).returncode
    return adentro()


def adentro() -> int:
    fallas: list[str] = []
    verdes = 0

    def check(cond, desc):
        nonlocal verdes
        if cond:
            verdes += 1
        else:
            fallas.append(desc)
            print(f"  ✗ {desc}")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        shutil.copytree(HOME, repo, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        (repo / ".git").mkdir()
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/e2e\n", encoding="utf-8")
        hh = Path(tmp) / "hermes-home"
        (hh / "plugins").mkdir(parents=True)
        shutil.copytree(repo / "plugin", hh / "plugins" / "repo-harness")  # como lo instala Hermes: copia
        (hh / "config.yaml").write_text("plugins:\n  enabled:\n    - repo-harness\n", encoding="utf-8")
        os.environ["HERMES_HOME"] = str(hh)
        os.environ.pop("HARNESS_REPO", None)
        os.chdir(repo)

        from hermes_cli import plugins as hp  # noqa: E402 — sólo existe dentro de Hermes

        hp.discover_plugins(force=True)
        mgr = hp.get_plugin_manager()
        cargado = next((p for k, p in mgr._plugins.items() if "repo-harness" in str(k)), None)
        check(cargado is not None and not getattr(cargado, "error", None) and getattr(cargado, "enabled", False),
              f"Hermes no cargó repo-harness: {getattr(cargado, 'error', 'no descubierto')}")
        if fallas:
            return fin(fallas, verdes)

        config = json.loads((repo / ".hermes" / "harness.config.json").read_text(encoding="utf-8"))
        tools = config["tools"]

        def directiva(tool, args):
            accion, msg = hp.get_pre_tool_call_directive(tool, args, session_id="e2e")
            return accion, msg or ""

        t = config.get("terminal") or {}
        for r in t.get("deny") or []:
            for caso in [r["example"]] + list(r.get("moreExamples") or []):
                a, m = directiva(tools["shell"][0], {"command": caso})
                check(a == "block" and r["reason"] in m, f"Hermes no bloquea terminal.deny[{r['id']}] `{caso}` ({a!r})")
        mf = tools.get("$multiFilePatch") or {}
        enrepo = [r for r in config.get("protectedPaths") or [] if not r.get("outsideRepo")]
        if mf.get("args") and enrepo:
            v4a = f"*** Begin Patch\n*** Update File: {enrepo[0]['example']}\n+x\n*** End Patch"
            check(directiva(tools["write"][-1], {"mode": "patch", mf["args"][0]: v4a})[0] == "block",
                  "Hermes no bloquea un patch V4A hacia una ruta protegida")
        for r in t.get("ask") or []:
            a, _ = directiva(tools["shell"][0], {"command": r["example"]})
            check(a == "approve", f"Hermes no escala terminal.ask[{r['id']}] a aprobación ({a!r})")
        for c in t.get("innocent") or []:
            check(directiva(tools["shell"][0], {"command": c})[0] is None, f"Hermes bloquea el inocente `{c}`")
        for r in config.get("protectedPaths") or []:
            for tool in tools["write"]:
                a, _ = directiva(tool, {"path": r["example"], "content": "x"})
                check(a == "block", f"Hermes no bloquea {tool} → protectedPaths[{r['id']}]")
        for r in (config.get("memory") or {}).get("deny") or []:
            check(directiva(tools["memory"][0], {"action": "add", "content": r["example"]})[0] == "block",
                  f"Hermes no bloquea memory.deny[{r['id']}]")
        for r in (config.get("cron") or {}).get("deny") or []:
            check(directiva(tools["cron"][0], {"action": "create", "schedule": "every 2h", "prompt": r["example"]})[0] == "block",
                  f"Hermes no bloquea cron.deny[{r['id']}]")
        check(directiva("read_file", {"path": "AGENTS.md"})[0] is None, "Hermes bloquea read_file (sin familia)")

        # Hermes arrancado FUERA del repo (gateway, cron) con la sesión ADENTRO: el plugin tiene
        # que seguir el cwd que Hermes resuelve para sus herramientas, no el del proceso.
        afuera = Path(tmp) / "afuera"
        afuera.mkdir()
        os.chdir(afuera)
        os.environ["TERMINAL_CWD"] = str(repo)
        try:
            a, _ = directiva(tools["shell"][0], {"command": t["deny"][0]["example"]})
            check(a == "block", f"con el proceso fuera del repo y la sesión adentro, Hermes no bloquea ({a!r})")
            if enrepo:
                a, _ = directiva(tools["write"][0], {"path": enrepo[0]["example"], "content": "x"})
                check(a == "block", "ruta relativa a la sesión (no al proceso) no se protege dentro de Hermes")
        finally:
            os.environ.pop("TERMINAL_CWD", None)
            os.chdir(repo)

        # Sección de estado: la renderiza Hermes, con su tope.
        secciones = hp.render_system_prompt_sections({"cwd": str(repo), "session_id": "e2e", "platform": "cli"})
        texto = "\n".join(getattr(s, "content", "") or getattr(s, "text", "") or str(s) for s in secciones)
        check("e2e" in texto and "repo-harness" in texto, "Hermes no renderizó la sección de estado del arnés")

        # Gate pendiente → pre_verify sigue el turno (y sin pendiente, no).
        check(hp.get_pre_verify_continue_message(changed_paths=["x"], coding=True) is None, "pre_verify frenó sin gate pendiente")
        marker = repo / config["gate"]["marker"]
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("e2e", encoding="utf-8")
        msg = hp.get_pre_verify_continue_message(changed_paths=["x"], coding=True)
        check(bool(msg) and "GATE PENDIENTE" in msg, f"pre_verify no siguió el turno con el gate pendiente ({msg!r})")

        # Ruteo: pre_llm_call devuelve contexto para el ejemplo de cada ruta.
        for rt in config.get("routes") or []:
            res = hp.invoke_hook("pre_llm_call", user_message=rt["example"], session_id="e2e", is_first_turn=True)
            check(any(isinstance(x, dict) and rt["hint"] in x.get("context", "") for x in res),
                  f"Hermes no recibió la pista de routes[{rt['id']}]")

        # Lint tras escribir: transform_tool_result devuelve el hallazgo.
        pat = next((p for p in config.get("patterns") or [] if p.get("examplePath")), None)
        if pat:
            dest = repo / pat["examplePath"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(pat["example"] + "\n", encoding="utf-8")
            res = hp.invoke_hook("transform_tool_result", tool_name=tools["write"][0],
                                 args={"path": pat["examplePath"]}, result='{"ok": true}', status="ok")
            check(any(isinstance(x, str) and f"PATRON[{pat['id']}]" in x for x in res),
                  "transform_tool_result no devolvió el hallazgo del lint dentro de Hermes")

    return fin(fallas, verdes)


def fin(fallas, verdes) -> int:
    if fallas:
        print(f"E2E ROJO — {len(fallas)} falla(s) dentro de Hermes, {verdes} verdes.")
        return 1
    print(f"E2E VERDE — {verdes} verificaciones dentro del Hermes real.")
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
