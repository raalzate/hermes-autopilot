"""
Lo que el arnés hace alrededor del turno, no de una herramienta:

    session_status   el estado verificado al abrir la sesión   (system prompt section)
    route            pistas según lo que pide el humano        (pre_llm_call)
    after_write      marcar el gate + lint del archivo tocado  (post_tool_call / transform_tool_result)
    verify           no cerrar con el gate pendiente           (pre_verify)
    respuesta        tapar secretos y avisar de dónde leyó     (transform_llm_output)

Todo sin lanzar procesos: la rama se lee de `.git/HEAD` y el `core.hooksPath` de `.git/config`.
El original para Claude Code lanzaba `git` al abrir cada sesión; acá la sección del prompt se
calcula en proceso, y un `git` colgado (un repo en red, un lock) no puede demorar a Hermes.
"""
from __future__ import annotations

import re
from pathlib import Path

from .core import (
    Event,
    content_of,
    first_match,
    git_dir,
    is_code,
    mark_gate_dirty,
    marker_path,
    paths_of,
    rel_to_repo,
    tool_kind,
)
from .rules import lint_one


def branch_of(root: Path) -> str:
    g = git_dir(root)
    try:
        head = (g / "HEAD").read_text(encoding="utf-8").strip() if g else ""
    except OSError:
        return "?"
    m = re.match(r"ref:\s*refs/heads/(.+)", head)
    return m.group(1) if m else (head[:10] or "?")


def hooks_path_of(root: Path) -> str:
    g = git_dir(root)
    # En un worktree el config vive en el directorio común, no en el del worktree.
    for cand in [g / "config" if g else None, (g / ".." / ".." / "config").resolve() if g else None]:
        try:
            text = cand.read_text(encoding="utf-8") if cand else ""
        except OSError:
            continue
        m = re.search(r"^\s*hooksPath\s*=\s*(.+)$", text, re.M | re.I)
        if m:
            return m.group(1).strip()
    return ""


def session_status(config: dict, root: Path, max_chars: int = 3800) -> str:
    """La sección del system prompt: corta a propósito, entra en CADA sesión.

    Hermes la congela al abrir la sesión (cache del prompt): se calcula una vez, no por turno.
    """
    st = config.get("status") or {}
    lines = ["## Estado del repo (repo-harness)", f"- Rama: `{branch_of(root)}`"]
    hp = hooks_path_of(root)
    if hp != ".githooks":
        cmd = (config.get("gate") or {}).get("installHooksCommand", "git config core.hooksPath .githooks")
        lines.append(f"- ⚠️ hooks de git NO instalados (`core.hooksPath` ≠ `.githooks`). Corré `{cmd}`.")
    m = marker_path(config, root)
    if m and m.exists():
        lines.append(f"- ⚠️ Gate pendiente de una sesión anterior: corré `{(config.get('gate') or {}).get('command', 'el gate')}`.")
    f = root / st.get("file", "STATUS.md")
    if f.is_file():
        head = "\n".join(f.read_text(encoding="utf-8", errors="replace").splitlines()[: st.get("headLines", 25)])
        lines += ["", f"### {st.get('file', 'STATUS.md')} (encabezado)", head]
    else:
        lines.append(f"- ⚠️ Falta `{st.get('file', 'STATUS.md')}`: nadie sabe qué está verificado.")
    lines += ["", st.get("reminder") or f"Nada se entrega sin `{(config.get('gate') or {}).get('command', 'el gate')}` verde."]
    out = "\n".join(lines)
    # Hermes rechaza (no trunca) una sección más larga que su tope: cortar acá es no perderla.
    return out if len(out) <= max_chars else out[: max_chars - 20] + "\n[…recortado]"


def route(config: dict, user_message: str) -> str:
    """Pistas de ruteo: cada `routes[]` que casa con el pedido suma su `hint` al turno.

    Informa, no bloquea: es una guía (feedforward). Lo que tiene que cumplirse sí o sí es un freno.
    """
    if not user_message:
        return ""
    hints = []
    for r in config.get("routes") or []:
        if first_match([r], user_message):
            hints.append(f"- **{r.get('id', '?')}** · {r.get('hint', '')}")
    return ("## Ruteo del arnés (repo-harness)\n" + "\n".join(hints)) if hints else ""


def after_write(ev: Event, config: dict, root: Path) -> list[str]:
    """Tras escribir: marca el gate si fue código y devuelve los hallazgos del lint del archivo.

    El lint corre sobre el archivo YA escrito (el `patch` sólo trae el fragmento), leído del disco:
    es lectura, no escritura, así que no toca P7.
    """
    if tool_kind(config, ev.tool) != "write":
        return []
    rels = [r for r in (rel_to_repo(p, root, ev.cwd) for p in paths_of(config, ev)) if r and not r.startswith("..")]
    if not rels:
        return []
    if any(is_code(config, r) for r in rels):
        mark_gate_dirty(config, root)
    hallazgos: list[str] = []
    for rel in rels:  # un patch V4A toca varios archivos
        p = root / rel
        try:
            text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else content_of(config, ev)
        except OSError:
            continue
        hallazgos += lint_one(config, rel, text)
    return hallazgos


def verify(config: dict, root: Path) -> str | None:
    """El mensaje para seguir el turno si el gate quedó pendiente, o None para cerrar.

    Hermes ya limita esto a `agent.max_verify_nudges` (3): no hace falta un anti-loop propio
    como el `stop_hook_active` de Claude Code. Al tercer intento el turno cierra igual, y por eso
    el mensaje exige decir en voz alta que no es entregable.
    """
    m = marker_path(config, root)
    if not m or not m.exists():
        return None
    cmd = (config.get("gate") or {}).get("command", "el gate")
    return (
        "GATE PENDIENTE: hay código editado en esta sesión y el gate no quedó verde.\n"
        f"Corré `{cmd}` y arreglá lo que salga rojo.\n"
        'Si el trabajo no es entregable todavía, decilo explícitamente: reportar "listo" sin gate '
        "verde es una violación, no un descuido."
    )


def respuesta(config: dict, texto: str, contaminada: str = "") -> str | None:
    """La respuesta final del turno, corregida, o None si queda igual (`output` del config).

    Lo que queda EN EL TEXTO no lo frena ningún `pre_tool_call`: no es una herramienta. Dos cosas sí
    son mecánicas: un secreto copiado en la respuesta se tapa antes de que llegue a la pantalla, al
    historial y al gateway (`redact`), y una respuesta escrita después de leer a un tercero lleva al
    pie de dónde (`taintNotice`). Si obedeció una instrucción plantada no lo sabe el arnés; el
    humano sí sabe que pudo pasar, y de qué fuente."""
    spec = (config or {}).get("output") or {}
    if not isinstance(texto, str) or not texto or not spec:
        return None
    nuevo = texto
    tapa = spec.get("redactWith") or "[tapado por el arnés]"
    for regla in spec.get("redact") or []:
        try:
            nuevo = re.sub(regla["pattern"], tapa, nuevo, flags=re.I)
        except (re.error, KeyError, TypeError):
            continue
    aviso = spec.get("taintNotice")
    if contaminada and isinstance(aviso, str) and aviso and aviso.split("{")[0] not in nuevo:
        nuevo = nuevo.rstrip() + "\n\n" + aviso.replace("{fuente}", contaminada)
    return nuevo if nuevo != texto else None
