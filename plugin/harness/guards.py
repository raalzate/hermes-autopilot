"""
Los frenos. Cada uno es una función pura `(Event, config, root) -> Decision`.

Qué herramienta de Hermes le toca a cada freno lo decide `config.tools` (qué nombres son
`shell`, `write`, `memory`, `skill`, `cron`), no este archivo. Un freno nuevo se agrega a
`GUARDS` con su clase de herramienta y llega con su caso escrito en el self-test (P2).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .core import (
    Decision,
    Event,
    abs_path,
    command_of,
    content_of,
    first_match,
    paths_of,
    rel_to_repo,
    tool_kind,
    written_text,
)


# ── shell ────────────────────────────────────────────────────────────────────
def _para_comparar(cmd: str, config: dict) -> str:
    """El comando sin los textos entre comillas que son DATOS y no instrucciones.

    `git commit -m 'por qué git push --force está prohibido'` no empuja nada: el mensaje sólo
    menciona la frase. Este repo escribe esas frases todo el tiempo, y un freno que muerde un
    mensaje de commit se desactiva a mano. Qué argumentos son datos lo declara
    `terminal.dataArgs` (regex del prefijo; el texto entre comillas que le sigue se ignora).
    `bash -c '…'` NO está ahí: lo que va entre esas comillas sí se ejecuta.
    """
    out = cmd
    for pref in (config.get("terminal") or {}).get("dataArgs") or []:
        try:
            out = re.sub(rf"({pref})(['\"])(?:(?!\2).)*\2", r"\1''", out, flags=re.S)
        except re.error:
            continue
    return out


def terminal_guard(ev: Event, config: dict, root: Path) -> Decision:
    """Comandos irreversibles o que saltan la verificación (`terminal.deny`).

    Hermes ya trae su propia detección de comandos peligrosos con aprobación humana. Este freno
    no la reemplaza: la COMPLETA con las reglas de ESTE repo (sus cicatrices), y a diferencia de
    la aprobación no depende de que haya un humano mirando — en el gateway o en un cron no lo hay.
    """
    cmd = command_of(config, ev)
    if not cmd:
        return Decision.allow()
    t = config.get("terminal") or {}
    comparable = _para_comparar(cmd, config)
    hit = first_match(t.get("deny"), comparable)
    if hit:
        return Decision.deny(
            f"COMANDO BLOQUEADO por el arnés del repo: `{cmd}`\n"
            f"Motivo: {hit.get('reason', '(sin motivo declarado)')}\n"
            "Reformulá el comando o pedí confirmación explícita al humano. No lo reintentes igual.",
            hit,
        )
    # Escribir una ruta protegida por la terminal (`echo x > .env`, `tee`) es escribirla: las
    # mismas reglas que a `write_file`, sobre cada destino de redirección.
    for patron in t.get("redirectTargets") or []:
        try:
            destinos = [m.group(1) for m in re.finditer(patron, comparable)]
        except re.error:
            continue
        for destino in destinos:
            d = _ruta_protegida(destino.strip("'\""), config, root, ev.cwd)
            if d.block:
                return d
    # `ask`: Hermes no tiene una clave para sumar patrones propios a "pedir aprobación" (sólo
    # `approvals.deny`, que prohíbe). Este es el hueco que llena: el comando no se prohíbe, se
    # escala al humano con el motivo — y donde no hay humano (cron), la aprobación se niega sola.
    ask = first_match(t.get("ask"), comparable)
    if ask:
        return Decision.ask(
            f"El arnés del repo pide aprobación humana para `{cmd}`: {ask.get('reason', '')}", ask)
    return Decision.allow()


# ── write ────────────────────────────────────────────────────────────────────
def _nombres_fuera(raw: str, root: Path, cwd: str) -> list[str]:
    """Los nombres contra los que se evalúa una ruta de FUERA del repo: el texto crudo, la ruta
    absoluta resuelta y, si cae bajo un `HERMES_HOME` propio, su equivalente en `~/.hermes/`
    (las reglas se escriben contra el lugar por defecto; un home movido no las apaga)."""
    nombres = [raw]
    a = abs_path(raw, root, cwd)
    if a:
        nombres.append(a)
        hh = os.environ.get("HERMES_HOME")
        if hh:
            try:
                base = Path(os.path.expanduser(hh)).resolve().as_posix().rstrip("/")
            except OSError:
                base = ""
            if base and (a == base or a.startswith(base + "/")):
                nombres.append("/.hermes" + a[len(base):])
    return list(dict.fromkeys(nombres))


def _ruta_protegida(raw: str, config: dict, root: Path, cwd: str) -> Decision:
    rel = rel_to_repo(raw, root, cwd)
    if not rel:
        return Decision.allow()
    reglas = config.get("protectedPaths") or []
    # Fuera del repo sólo se miran las reglas que lo piden (p.ej. `~/.hermes/.env`): el resto
    # del disco no es asunto de este repo.
    if rel.startswith(".."):
        fuera = [r for r in reglas if r.get("outsideRepo")]
        for nombre in _nombres_fuera(raw, root, cwd):
            hit = first_match(fuera, nombre)
            if hit:
                return _deny_ruta(raw, hit)
        return Decision.allow()
    hit = first_match([r for r in reglas if not r.get("outsideRepo")], rel)
    return _deny_ruta(rel, hit) if hit else Decision.allow()


def protected_paths(ev: Event, config: dict, root: Path) -> Decision:
    """Secretos, lockfiles, `.git/` y derivados no los edita el agente (P8). Todas las rutas
    que la herramienta toca, incluidas las de un patch V4A (`paths_of`)."""
    for raw in paths_of(config, ev):
        d = _ruta_protegida(raw, config, root, ev.cwd)
        if d.block:
            return d
    return Decision.allow()


def _deny_ruta(ruta: str, hit: dict) -> Decision:
    return Decision.deny(
        f"RUTA PROTEGIDA: `{ruta}` no se edita desde el agente.\n"
        f"Motivo: {hit.get('reason', '(sin motivo declarado)')}\n"
        "Si el cambio hace falta de verdad, pedíselo al humano y que lo haga él.",
        hit,
    )


def _casa_alguna(patrones, rel: str) -> bool:
    for p in patrones or []:
        try:
            if re.search(p, rel):
                return True
        except re.error:
            continue
    return False


def content_patterns(ev: Event, config: dict, root: Path) -> Decision:
    """Patrones prohibidos en lo que se escribe (`patterns`), acotados por `paths`/`exceptPaths`.

    Multilínea (`re.M`): un `^` ancla a CADA línea, como en el lint. Sin eso, el freno sólo miraba
    la primera línea del archivo y el lint cazaba después lo que el freno había dejado pasar.
    """
    rels = [r for r in (rel_to_repo(p, root, ev.cwd) for p in paths_of(config, ev)) if r and not r.startswith("..")]
    if not rels:
        return Decision.allow()
    texto = content_of(config, ev)
    if not texto:
        return Decision.allow()
    for regla in config.get("patterns") or []:
        for rel in rels:
            if regla.get("paths") and not _casa_alguna(regla["paths"], rel):
                continue
            if _casa_alguna(regla.get("exceptPaths"), rel):
                continue
            flags = re.M | (0 if regla.get("caseSensitive") else re.IGNORECASE)
            if first_match([regla], texto, flags):
                return Decision.deny(
                    f"PATRÓN PROHIBIDO [{regla.get('id', '?')}] en `{rel}`.\n"
                    f"Motivo: {regla.get('reason', '(sin motivo declarado)')}",
                    regla,
                )
    return Decision.allow()


# ── memory ───────────────────────────────────────────────────────────────────
def memory_guard(ev: Event, config: dict, root: Path) -> Decision:
    """Lo que el agente guarda en su memoria persistente.

    La memoria de Hermes entra al prompt de TODAS las sesiones siguientes, en todas las
    plataformas del gateway. Un secreto guardado ahí no se filtra una vez: se filtra siempre.
    Y una "regla" guardada ahí (p.ej. "en este repo se puede saltar el gate") es una guía que
    contradice a los frenos, sin revisión y sin commit. Sólo se mira lo que se GUARDA: sacar un
    secreto ya guardado tiene que poder hacerse.
    """
    texto = written_text(config, ev.args)
    if not texto:
        return Decision.allow()
    hit = first_match((config.get("memory") or {}).get("deny"), texto)
    if hit:
        return Decision.deny(
            "MEMORIA RECHAZADA: esa entrada no se guarda en la memoria persistente.\n"
            f"Motivo: {hit.get('reason', '(sin motivo declarado)')}\n"
            "Si es una regla del repo, va a AGENTS.md o al config del arnés, con commit y revisión.",
            hit,
        )
    return Decision.allow()


# ── skill ────────────────────────────────────────────────────────────────────
def skill_guard(ev: Event, config: dict, root: Path) -> Decision:
    """Las skills que el agente crea o parchea solo.

    Hermes aprende escribiendo skills: son memoria procedimental que se carga en sesiones
    futuras. Una skill que enseña a saltarse un freno es la manera más barata de apagarlo — no
    en esta sesión, en todas las que vengan. A lo que la skill ESCRIBE se le aplica la misma
    lista que al terminal (sacar un paso prohibido de una skill vieja tiene que poder hacerse).
    """
    texto = written_text(config, ev.args)
    if not texto:
        return Decision.allow()
    sk = config.get("skills") or {}
    reglas = list(sk.get("deny") or [])
    if sk.get("inheritTerminalDeny", True):
        reglas += (config.get("terminal") or {}).get("deny") or []
    hit = first_match(reglas, _para_comparar(texto, config))
    if hit:
        return Decision.deny(
            "SKILL RECHAZADA: la skill enseña algo que el arnés de este repo prohíbe.\n"
            f"Motivo: {hit.get('reason', '(sin motivo declarado)')}\n"
            "Una skill es memoria procedimental: lo que enseña se repite en cada sesión. "
            "Reescribí el procedimiento sin ese paso.",
            hit,
        )
    return Decision.allow()


# ── cron ─────────────────────────────────────────────────────────────────────
def cron_guard(ev: Event, config: dict, root: Path) -> Decision:
    """Tareas programadas que el agente crea para sí mismo.

    Un cron corre sin humano mirando: la aprobación de comandos peligrosos no tiene a quién
    preguntarle. Lo que un cron hace se decide al crearlo, y este es ese momento.
    """
    cr = config.get("cron") or {}
    texto = written_text(config, ev.args)
    hit = first_match(cr.get("deny"), texto) if texto else None
    if hit:
        return Decision.deny(
            "CRON RECHAZADO: esa tarea programada no se crea desde el agente.\n"
            f"Motivo: {hit.get('reason', '(sin motivo declarado)')}",
            hit,
        )
    minimo = cr.get("minIntervalMinutes")
    sched = next((ev.args.get(k) for k in cr.get("scheduleArgs") or ["schedule"] if isinstance(ev.args.get(k), str)), "")
    if minimo and sched:
        cada = minutos_entre_corridas(sched)
        if cada is not None and cada < minimo:
            return Decision.deny(
                f"CRON RECHAZADO: `{sched}` corre cada {cada:g} min y el mínimo del repo es {minimo}.\n"
                "Cada corrida es un turno completo del modelo: se paga en tokens aunque no haga nada.",
            )
    return Decision.allow()


def _minutos_del_campo(campo: str) -> list[int] | None:
    """Los minutos (0-59) que un campo de minutos de cron dispara: `*`, `*/5`, `0-59`,
    `0,15,30`, `10-50/10`. None si no se entiende."""
    minutos: set[int] = set()
    for parte in campo.split(","):
        m = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", parte)
        if not m:
            return None
        rango, paso = m.group(1), int(m.group(2) or 1)
        if rango == "*":
            ini, fin = 0, 59
        elif "-" in rango:
            ini, fin = (int(x) for x in rango.split("-"))
        else:
            ini = fin = int(rango)
            if m.group(2):
                fin = 59
        if paso <= 0 or not (0 <= ini <= fin <= 59):
            return None
        minutos.update(range(ini, fin + 1, paso))
    return sorted(minutos)


def minutos_entre_corridas(sched: str) -> float | None:
    """El intervalo MÁS CORTO entre corridas, en minutos. None = one-shot o no se entiende.

    Formas de Hermes (`tools/cronjob_tools.py`): `30m`, `every 2h`, `every hour`, `in 5m`
    (one-shot), naturales (`every monday 9am`: ≥ 1 día) y cron de 5 campos.
    """
    s = sched.strip().lower()
    if s.startswith("in ") or re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return None  # one-shot: corre una vez, no tiene intervalo
    if s in ("every minute",):
        return 1
    if s in ("every hour", "hourly"):
        return 60
    m = re.fullmatch(r"(?:every\s+)?(\d+)\s*(s|sec|secs|seconds?|m|min|mins|minutes?|h|hrs?|hours?)", s)
    if m:
        n, u = int(m.group(1)), m.group(2)
        return n / 60 if u.startswith("s") else (n * 60 if u.startswith("h") else n)
    campos = s.split()
    if len(campos) == 5:
        mins = _minutos_del_campo(campos[0])
        if mins is None:
            return None
        if campos[1] != "*":
            # Con hora fija, el intervalo más corto está DENTRO de la hora (o es una vez por hora).
            if len(mins) == 1:
                return 60.0
        huecos = [b - a for a, b in zip(mins, mins[1:])] + [60 - mins[-1] + mins[0]]
        return float(min(huecos))
    return None


# Qué frenos corren para qué clase de herramienta. El orden importa: el primero que bloquea gana.
GUARDS = {
    "shell": [terminal_guard],
    "write": [protected_paths, content_patterns],
    "memory": [memory_guard],
    "skill": [skill_guard],
    "cron": [cron_guard],
}


def evaluate(ev: Event, config: dict | None, root: Path) -> Decision:
    """El punto de entrada del plugin: la primera decisión que bloquea o escala, o allow."""
    if not config:
        return Decision.allow("config ausente o inválido: el arnés deja pasar (P5)")
    kind = tool_kind(config, ev.tool)
    for guard in GUARDS.get(kind or "", []):
        try:
            d = guard(ev, config, root)
        except Exception as e:  # un freno roto deja pasar: nunca tumba el turno (P5)
            return Decision.allow(f"freno {guard.__name__} roto: {e}")
        if d.block or d.approve:
            return d
    return Decision.allow()
