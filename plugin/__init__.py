"""
repo-harness — el plugin de Hermes que ejecuta el arnés del repo.

Es un ADAPTADOR, y fino a propósito: traduce los hooks de Hermes a las funciones puras de
`plugin/harness/` y de vuelta. Ninguna regla vive acá (P4): todo sale de `.hermes/harness.config.json`
del repo en el que Hermes está trabajando. Sin ese archivo, el plugin no hace nada.

Contrato con Hermes (verificado en `hermes_cli/plugins.py` y `model_tools.py`):
  - los callbacks reciben KWARGS y siempre aceptan `**_`: Hermes suma campos entre versiones;
  - `pre_tool_call` → `{"action": "block", "message": ...}` bloquea; el mensaje es el resultado de
    la herramienta que el modelo lee. `block` SIN mensaje Hermes lo ignora;
  - `pre_tool_call` que LANZA o se pasa de tiempo FALLA CERRADO: Hermes bloquea la herramienta.
    Por eso todo callback pasa por `_seguro`: un arnés roto deja pasar, nunca bloquea al humano (P5);
  - `pre_verify` → `{"action": "continue", "message": ...}` sigue el turno (sólo si hubo ediciones);
  - `transform_tool_result` → un `str` reemplaza el resultado; `None` lo deja igual;
  - `pre_llm_call` → `{"context": ...}` se suma al mensaje del usuario (no al system prompt);
  - `post_tool_call` → observador: corre DESPUÉS de ejecutar, con `status="blocked"` si el freno o
    el humano dijeron que no (`model_tools.handle_function_call`, aa74e184);
  - `transform_llm_output` → un `str` reemplaza la respuesta final del turno, antes de mostrarla y
    de guardarla (`agent/turn_finalizer.py::apply_llm_output_transform`).
"""
from __future__ import annotations

import logging
import os

# El núcleo viaja DENTRO del plugin y se importa relativo. Hermes carga el plugin como paquete
# (`hermes_plugins.<slug>`, con `__path__` en su directorio) y lo COPIA para validarlo e
# instalarlo: un núcleo afuera del directorio, o un `sys.path` apuntando al repo del arnés, se
# rompe exactamente ahí (docs/gotchas.md).
from .harness import core, events, guards, integ, turn

logger = logging.getLogger("repo-harness")


def _seguro(fn):
    """Un freno que revienta NO puede bloquear: en `pre_tool_call` Hermes convierte la excepción
    en un bloqueo, y un arnés roto que frena todo se desinstala en una tarde."""
    def envuelto(*a, **kw):
        try:
            return fn(*a, **kw)
        except (Exception, SystemExit):  # noqa: BLE001 — la frontera con Hermes: nada cruza
            logger.warning("repo-harness: %s falló; se deja pasar", fn.__name__, exc_info=True)
            return None
    envuelto.__name__ = fn.__name__
    return envuelto


def _contexto(cwd: str | None = None):
    root = core.repo_root(cwd)
    return root, core.load_config(root)


def _cwd_de_sesion(task_id: str = "") -> str:
    """El directorio de trabajo de la SESIÓN, como lo resuelve Hermes para sus herramientas.

    No es el cwd del proceso: el gateway, cron y Desktop arrancan en otro lado, y un `cd` en la
    terminal mueve el cwd de la sesión sin mover el del proceso. Usar el del proceso apagaba el
    arnés entero fuera del repo, o evaluaba `write_file config` tras `cd .git` como `config`.
    Hermes lo expone en `tools.file_tools_paths._authoritative_workspace_root` (privado: por eso
    en try, y con `TERMINAL_CWD` y el cwd del proceso de respaldo).
    """
    try:
        from tools.file_tools_paths import _authoritative_workspace_root  # type: ignore

        wd = _authoritative_workspace_root(task_id or "default")
        if wd:
            return str(wd)
    except Exception:  # noqa: BLE001 — otra versión de Hermes, o fuera de Hermes (self-test)
        pass
    return os.environ.get("TERMINAL_CWD") or ""


def _cwd_de(args, task_id: str = "") -> str:
    # `terminal` trae `workdir`: si el agente trabaja en otro directorio, las reglas son las de ESE.
    wd = args.get("workdir") if isinstance(args, dict) else None
    return wd if isinstance(wd, str) and wd else _cwd_de_sesion(task_id)


# Sesiones que ya leyeron contenido de terceros: {sesión: de dónde}. Vive en el proceso de Hermes
# (el plugin se carga una vez); los frenos siguen siendo funciones puras: reciben el dato en el Event.
_CONTAMINADAS: dict[str, str] = {}
# Usos de una clase con presupuesto ({"<integración>:<clase>": [instantes]}) cuando no hay registro
# de eventos. Con registro se cuenta de ahí: vale entre procesos (el loop, cron y el gateway).
_USOS: dict[str, list[float]] = {}
_HORA = 3600.0
# Llamadas con presupuesto que el freno mandó a aprobar: {id de la llamada: "<integración>:<clase>"}.
# `pre_tool_call` no sabe si el humano dijo que sí; `post_tool_call` sí (status ≠ "blocked").
_APROBANDO: dict[str, str] = {}
_MAX_APROBANDO = 256  # una llamada sin `post_tool_call` (un Hermes que revienta) no puede acumular memoria
# Repos a los que ya se les dejó el spec de la guardia de sesión en este proceso: {raíz: spec}.
_GUARDIAS: dict[str, str] = {}


def _integraciones_de_la_tarea():
    """`HARNESS_INTEGRACIONES` (la pone el loop desde la cola): las integraciones que la tarea
    permite. Ausente = todas las habilitadas; vacía = ninguna."""
    v = os.environ.get("HARNESS_INTEGRACIONES")
    if v is None:
        return None
    return tuple(x.strip() for x in v.split(",") if x.strip())


def _uso(config, root, clave: str) -> int:
    import time
    desde = time.time() - _HORA
    if events.spec(config) and not os.environ.get("HARNESS_NO_EVENTS"):
        return sum(1 for e in events.tail(config, root, 2000)
                   if e.get("kind") == "integ-uso" and e.get("key") == clave and (e.get("at") or 0) >= desde)
    return sum(1 for t in _USOS.get(clave, []) if t >= desde)


def _id_llamada(tool: str, args, sesion: str, tool_call_id: str = "") -> str:
    if tool_call_id:
        return tool_call_id
    import json
    try:
        return f"{sesion}:{tool}:{json.dumps(args, sort_keys=True, default=str)}"
    except (TypeError, ValueError):
        return f"{sesion}:{tool}"


def _registrar_uso(config, root, clave: str, tool: str, aprobada: bool = False) -> None:
    import time
    if events.spec(config) and not os.environ.get("HARNESS_NO_EVENTS"):
        events.record(config, root, "integ-uso", key=clave, tool=tool, **({"approved": True} if aprobada else {}))
    else:
        ahora = time.time()
        _USOS[clave] = [t for t in _USOS.get(clave, []) if t >= ahora - _HORA] + [ahora]


def _guardia_de_sesion(config, root) -> None:
    """`sessionGuard.python`: deja en el gitdir el spec de la guardia de Python para que la cargue cada
    proceso Python que lance esta sesión de Hermes (el plugin puso `plugin/guardia` en su
    `PYTHONPATH` al registrarse). Una vez por repo y por proceso; dentro del loop no hace falta:
    el loop pasa su propio spec en `HARNESS_GUARDIA`."""
    if not ((config.get("sessionGuard") or {}).get("python")) or os.environ.get("HARNESS_GUARDIA"):
        return
    import json
    from .guardia import guardia as g
    registro = events.path(config, root)
    spec = json.dumps(g.spec_de(config, str(root.resolve()), str(registro) if registro else None, trabadas=False),
                      ensure_ascii=False)
    if _GUARDIAS.get(str(root)) == spec:
        return
    gd = core.git_dir(root)
    if gd is None:
        return
    try:
        (gd / g.ARCHIVO).write_text(spec, encoding="utf-8")
        _GUARDIAS[str(root)] = spec
    except OSError:
        pass


@_seguro
def on_pre_tool_call(tool_name: str = "", args=None, session_id: str = "", task_id: str = "",
                     tool_call_id: str = "", **_):
    args = args if isinstance(args, dict) else {}
    cwd = _cwd_de(args, task_id)
    root, config = _contexto(cwd or None)
    if not config:
        return None
    _guardia_de_sesion(config, root)
    sesion = session_id or task_id or "default"
    # Sólo las llamadas con presupuesto leen el registro: el resto no paga I/O (timing.py lo mide).
    cuenta = integ.contable(config, tool_name, args)
    clave = f"{cuenta[0]}:{cuenta[1]}" if cuenta else ""
    ev = core.Event(tool=tool_name, args=args, cwd=cwd, session_id=session_id,
                    contaminada=_CONTAMINADAS.get(sesion, ""), integraciones=_integraciones_de_la_tarea(),
                    uso={clave: _uso(config, root, clave)} if clave else {})
    d = guards.evaluate(ev, config, root)
    if clave and not (d.block or d.approve):
        _registrar_uso(config, root, clave, tool_name)
    elif clave and d.approve:
        # Lo que el humano apruebe también gasta el presupuesto: lo cuenta `post_tool_call`.
        if len(_APROBANDO) >= _MAX_APROBANDO:
            _APROBANDO.pop(next(iter(_APROBANDO)))
        _APROBANDO[_id_llamada(tool_name, args, sesion, tool_call_id)] = clave
    if not (d.block or d.approve):
        fuente = guards.fuente_externa(ev, config, root)
        if fuente and sesion not in _CONTAMINADAS:
            _CONTAMINADAS[sesion] = fuente
            events.record(config, root, "contaminada", source=fuente, session=sesion)
    if d.block or d.approve:
        # Lo que el freno decidió, para el panel: sin esto se ve sólo dentro de esta conversación.
        events.record(config, root, "block" if d.block else "ask", rule=(d.rule or {}).get("id", "?"),
                      tool=tool_name, session=session_id)
    return d.to_hermes()


@_seguro
def on_post_tool_call(tool_name: str = "", args=None, status: str = "", session_id: str = "", task_id: str = "",
                      tool_call_id: str = "", **_):
    """Una llamada que el freno mandó a aprobar y que se EJECUTÓ (el humano dijo que sí) cuenta en el
    presupuesto. Sin esto, con aprobaciones seguidas el tope por hora dejaba de cortar."""
    if not _APROBANDO:
        return None
    args = args if isinstance(args, dict) else {}
    clave = _APROBANDO.pop(_id_llamada(tool_name, args, session_id or task_id or "default", tool_call_id), "")
    if not clave or status == "blocked":
        return None
    root, config = _contexto(_cwd_de(args, task_id) or None)
    if config:
        _registrar_uso(config, root, clave, tool_name, aprobada=True)
    return None


@_seguro
def on_transform_llm_output(response_text: str = "", session_id: str = "", task_id: str = "", **_):
    root, config = _contexto(_cwd_de_sesion(task_id) or None)
    if not config:
        return None
    nuevo = turn.respuesta(config, response_text, _CONTAMINADAS.get(session_id or task_id or "default", ""))
    if nuevo is not None:
        events.record(config, root, "respuesta", session=session_id,
                      tapado=nuevo.count((config.get("output") or {}).get("redactWith") or "[tapado por el arnés]"))
    return nuevo


@_seguro
def on_transform_tool_result(tool_name: str = "", args=None, result=None, status: str = "", task_id: str = "", **_):
    if not isinstance(result, str) or status == "error":
        return None
    args = args if isinstance(args, dict) else {}
    cwd = _cwd_de_sesion(task_id)
    root, config = _contexto(cwd or None)
    if not config:
        return None
    recortado = integ.recortar(config, tool_name, result)
    if recortado is not None:
        events.record(config, root, "integ-recorte", tool=tool_name, chars=len(result))
        return recortado
    hallazgos = turn.after_write(core.Event(tool=tool_name, args=args, cwd=cwd), config, root)
    if not hallazgos:
        return None
    events.record(config, root, "lint", tool=tool_name, findings=len(hallazgos), first=hallazgos[0][:200])
    return (
        result
        + "\n\n[repo-harness] el archivo quedó escrito, pero el lint del repo lo marca:\n  "
        + "\n  ".join(hallazgos[:10])
        + "\nArreglalo ahora: el gate va a fallar por esto."
    )


@_seguro
def on_pre_verify(task_id: str = "", **_):
    root, config = _contexto(_cwd_de_sesion(task_id) or None)
    msg = turn.verify(config, root) if config else None
    if msg:
        events.record(config, root, "verify-pending", session=task_id)
    return {"action": "continue", "message": msg} if msg else None


@_seguro
def on_pre_llm_call(user_message: str = "", task_id: str = "", **_):
    root, config = _contexto(_cwd_de_sesion(task_id) or None)
    hint = turn.route(config, user_message) if config else ""
    return {"context": hint} if hint else None


def _seccion_estado(info=None):
    try:
        cwd = (info or {}).get("cwd") if hasattr(info, "get") else None
        root, config = _contexto(cwd)
        return turn.session_status(config, root) if config else ""
    except (Exception, SystemExit):  # noqa: BLE001
        logger.warning("repo-harness: sección de estado falló", exc_info=True)
        return ""


@_seguro
def cmd_harness(raw_args: str = ""):
    """/harness — qué frenos están activos en este repo y por qué."""
    root, config = _contexto()
    if not config:
        return f"repo-harness: no hay `.hermes/harness.config.json` en {root} — el arnés no actúa acá."
    t = config.get("terminal") or {}
    lineas = [
        f"repo-harness en {root}",
        f"  terminal.deny   {len(t.get('deny') or [])} · terminal.ask {len(t.get('ask') or [])}",
        f"  protectedPaths  {len(config.get('protectedPaths') or [])}",
        f"  patterns        {len(config.get('patterns') or [])}",
        f"  memory.deny     {len((config.get('memory') or {}).get('deny') or [])}",
        f"  cron.deny       {len((config.get('cron') or {}).get('deny') or [])}",
        f"  gate            {(config.get('gate') or {}).get('command', '—')}",
    ]
    m = core.marker_path(config, root)
    lineas.append("  ⚠️ gate PENDIENTE" if m and m.exists() else "  gate sin pendientes")
    return "\n".join(lineas)


def _guardia_en_pythonpath() -> None:
    """Cada proceso Python que lance Hermes (la terminal y `execute_code`, que deja pasar `PYTHONPATH`)
    importa `plugin/guardia/sitecustomize.py`. Sin spec en el repo (`sessionGuard.python` apagado),
    no hace nada."""
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guardia")
    actual = os.environ.get("PYTHONPATH", "")
    if os.path.isfile(os.path.join(d, "sitecustomize.py")) and d not in actual.split(os.pathsep):
        os.environ["PYTHONPATH"] = os.pathsep.join([d] + ([actual] if actual else []))


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("transform_tool_result", on_transform_tool_result)
    ctx.register_hook("transform_llm_output", on_transform_llm_output)
    ctx.register_hook("pre_verify", on_pre_verify)
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    try:
        _guardia_en_pythonpath()
    except Exception:  # noqa: BLE001 — sin guardia de sesión, el resto del arnés sigue
        logger.warning("repo-harness: sin guardia de sesión", exc_info=True)
    # Estado al abrir la sesión: sección del system prompt, congelada por sesión (cache-safe).
    try:
        ctx.register_system_prompt_section("repo-harness.status", _seccion_estado, max_chars=4000)
    except Exception:  # noqa: BLE001 — una versión de Hermes sin secciones no tumba el resto
        logger.warning("repo-harness: sin register_system_prompt_section", exc_info=True)
    try:
        ctx.register_command("harness", cmd_harness, description="Frenos activos del arnés en este repo")
    except Exception:  # noqa: BLE001
        logger.warning("repo-harness: sin register_command", exc_info=True)
