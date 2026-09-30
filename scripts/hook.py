#!/usr/bin/env python3
"""
El arnés como SHELL HOOK de Hermes: el segundo adaptador del mismo núcleo.

El camino recomendado es el plugin (`plugin/`): corre en proceso y cuesta microsegundos. Éste
existe para quien no puede habilitar plugins (una política de la organización, un perfil
gestionado) y para que el self-test pruebe el contrato de punta a punta con un proceso real.

Se declara en `~/.hermes/config.yaml` (lo imprime `scripts/install.py`):

    hooks:
      pre_tool_call:
        - matcher: "terminal|write_file|patch|memory|skill_manage|cronjob_manage"
          command: "python3 /ruta/al/repo/scripts/hook.py"
      post_tool_call:
        - matcher: "write_file|patch"
          command: "python3 /ruta/al/repo/scripts/hook.py"
      pre_verify:
        - command: "python3 /ruta/al/repo/scripts/hook.py"

Contrato (verificado en `agent/shell_hooks.py`):
  - stdin: `{"hook_event_name", "tool_name", "tool_input", "session_id", "cwd", "extra"}`;
  - `pre_tool_call`: exit 2 bloquea, y el mensaje sale del JSON de stdout (o de stderr, cortado
    a 400 caracteres). Se mandan LOS DOS: un JSON de bloqueo más exit 2;
  - `exit 1` NO bloquea. Nunca se usa: un error del hook es un error, no una decisión (P5);
  - cualquier excepción acá termina en exit 0: el arnés roto deja pasar.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# El núcleo vive DENTRO del plugin (`plugin/harness/`): Hermes copia el directorio del plugin
# al instalarlo y al validarlo, y lo que quede afuera no viaja (docs/gotchas.md).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))


def main() -> int:
    from harness import core, guards, turn

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    evento = payload.get("hook_event_name") or ""
    args = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    # El `cwd` del payload es el del PROCESO de Hermes, no el de la sesión (docs/hermes.md). Desde
    # un proceso aparte no se le puede preguntar a Hermes el de la sesión: se usa `workdir` si la
    # herramienta lo trae y `TERMINAL_CWD` si Hermes lo exporta. Por esto el plugin es el camino
    # recomendado.
    cwd = ((args.get("workdir") if isinstance(args.get("workdir"), str) else "")
           or os.environ.get("TERMINAL_CWD") or payload.get("cwd") or "")
    root = core.repo_root(cwd or None)
    config = core.load_config(root)
    if not config:
        return 0
    ev = core.Event(tool=payload.get("tool_name") or "", args=args, cwd=cwd,
                    session_id=payload.get("session_id") or "")

    if evento == "pre_tool_call":
        d = guards.evaluate(ev, config, root).to_hermes()
        if d:
            print(json.dumps(d, ensure_ascii=False))
            if d["action"] == "block":
                # stderr también: Hermes lo usa si el stdout no parsea. Cortado por ellos a 400.
                sys.stderr.write(d["message"][:400] + "\n")
                return 2
        return 0
    if evento == "post_tool_call":
        for h in turn.after_write(ev, config, root):
            sys.stderr.write(h + "\n")  # observador: Hermes no lo inyecta, queda en el log
        return 0
    if evento == "pre_verify":
        msg = turn.verify(config, root)
        if msg:
            print(json.dumps({"action": "continue", "message": msg}, ensure_ascii=False))
        return 0
    if evento == "pre_llm_call":
        hint = turn.route(config, (payload.get("extra") or {}).get("user_message") or "")
        if hint:
            print(json.dumps({"context": hint}, ensure_ascii=False))
        return 0
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — un hook roto deja pasar (P5)
        sys.exit(0)
