"""
Plomería compartida del arnés.

Todo lo específico del repo vive en `.hermes/harness.config.json`: cambiar una regla es editar
JSON, no Python (P4). Este módulo no conoce ni un literal de dominio.

Contrato de un freno (ver `docs/decisions/0003-contrato-de-frenos.md`):
  - un freno es una función PURA `(evento, config) -> Decision`;
  - `Decision.block` con un `message` que explica el porqué: es lo ÚNICO que el agente lee;
  - un config ausente o inválido devuelve `None` en `load_config()` y los frenos DEJAN PASAR:
    el arnés no puede bloquear al humano por estar roto.

Que los frenos sean puros (sin I/O, sin procesos) no es estética: es lo que deja al self-test
llamarlos directo, sin Hermes instalado, y lo que mantiene la latencia de cada tool call en
microsegundos.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

# Dónde vive el CÓDIGO del arnés (plugin/, scripts/, plantillas/). En este repo es la raíz; en un
# repo donde se instaló, es `.hermes/harness/`. Este archivo está en `plugin/harness/core.py`.
HARNESS_HOME = Path(__file__).resolve().parents[2]


def _raiz_con_config(desde: Path) -> Path | None:
    for cand in (desde, *desde.parents):
        if (cand / ".hermes" / "harness.config.json").is_file():
            return cand
    return None


# El repo GOBERNADO: el primer ancestro del código con `.hermes/harness.config.json`. Se busca
# hacia arriba en vez de asumir `parent.parent` porque el mismo código corre en dos lugares.
REPO_ROOT = _raiz_con_config(HARNESS_HOME) or HARNESS_HOME
CONFIG_PATH = REPO_ROOT / ".hermes" / "harness.config.json"


def repo_root(cwd: str | os.PathLike | None = None) -> Path:
    """La raíz del repo que se está gobernando.

    El plugin vive instalado en `~/.hermes/plugins/`, no en el repo: ahí `REPO_ROOT` apuntaría
    al plugin. Se busca hacia arriba desde `cwd` —el directorio de trabajo de la SESIÓN, que el
    plugin le pide a Hermes— el primer directorio con `.hermes/harness.config.json` (como git
    busca `.git`). `HARNESS_REPO` fuerza la raíz: lo usan el self-test y el e2e. No lo exportes
    globalmente: aplicaría las reglas de un repo a todos.
    """
    env = os.environ.get("HARNESS_REPO")
    if env:
        return Path(env).resolve()
    d = Path(cwd or Path.cwd()).resolve()
    encontrada = _raiz_con_config(d)
    if encontrada:
        return encontrada
    # Sin config encontrado se devuelve el cwd, NO el repo del arnés: un plugin instalado para
    # el usuario no puede aplicar las reglas de un repo a otro que no las declaró.
    return d


def load_config(root: Path | None = None) -> dict | None:
    """El config del arnés, o None. Ausente o inválido NUNCA bloquea (P5)."""
    path = (root or repo_root()) / ".hermes" / "harness.config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


@dataclass
class Decision:
    block: bool = False
    approve: bool = False
    message: str = ""
    rule: dict | None = None
    notes: list[str] = field(default_factory=list)

    @staticmethod
    def allow(note: str = "") -> "Decision":
        return Decision(notes=[note] if note else [])

    @staticmethod
    def deny(message: str, rule: dict | None = None) -> "Decision":
        return Decision(block=True, message=message, rule=rule)

    @staticmethod
    def ask(message: str, rule: dict | None = None) -> "Decision":
        return Decision(approve=True, message=message, rule=rule)

    def to_hermes(self) -> dict | None:
        """La forma que `pre_tool_call` entiende. `block` sin mensaje Hermes lo IGNORA, así que
        un bloqueo sin motivo no es un bloqueo: se garantiza el texto acá."""
        if self.block:
            return {"action": "block", "message": self.message or "Bloqueado por el arnés del repo."}
        if self.approve:
            key = (self.rule or {}).get("id") or "repo-harness"
            return {"action": "approve", "message": self.message, "rule_key": f"repo-harness:{key}"}
        return None


@dataclass
class Event:
    """Una llamada a herramienta, normalizada.

    Hermes nombra sus herramientas (`terminal`, `write_file`, `patch`…) y sus argumentos
    (`command`, `path`, `content`…). Los nombres NO se cablean acá: salen de `tools` en el
    config, porque cambian entre versiones de Hermes y porque un plugin o un MCP puede sumar
    herramientas que escriben archivos con otro nombre.
    """
    tool: str
    args: dict
    cwd: str = ""
    session_id: str = ""
    contaminada: str = ""  # de dónde vino el contenido de terceros que esta sesión ya leyó ("" = limpia)
    integraciones: tuple | None = None  # las que la tarea permite (`HARNESS_INTEGRACIONES`); None = todas las habilitadas
    uso: dict = field(default_factory=dict)  # {"<integración>:<clase>": usos en la última hora}, lo cuenta el plugin


def tool_kind(config: dict, tool: str) -> str | None:
    """'shell' | 'write' | 'read' | None, según `config.tools`."""
    for kind, names in (config.get("tools") or {}).items():
        if kind.startswith("$"):
            continue
        if isinstance(names, list) and tool in names:
            return kind
    return None


def _first_arg(args: dict, keys: list[str]) -> str:
    for k in keys:
        v = args.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def command_of(config: dict, ev: Event) -> str:
    keys = ((config.get("tools") or {}).get("$args") or {}).get("command") or ["command"]
    return _first_arg(ev.args, keys)


def path_of(config: dict, ev: Event) -> str:
    keys = ((config.get("tools") or {}).get("$args") or {}).get("path") or ["path", "file_path"]
    return _first_arg(ev.args, keys)


def _multi(config: dict) -> dict:
    return (config.get("tools") or {}).get("$multiFilePatch") or {}


def _patch_texts(config: dict, ev: Event) -> list[str]:
    mf = _multi(config)
    return [ev.args[k] for k in mf.get("args") or [] if isinstance(ev.args.get(k), str)]


def paths_of(config: dict, ev: Event) -> list[str]:
    """TODAS las rutas que la herramienta va a tocar.

    `patch` de Hermes tiene un modo V4A: un solo argumento de texto con encabezados
    `*** Update File: x` (y Add, Delete, Move a -> b) y SIN `path`. Mirar sólo `path` dejaba
    pasar cualquier escritura por ese camino, incluidas las rutas protegidas. La gramática de
    los encabezados es de Hermes, así que vive en `tools.$multiFilePatch` del config.
    """
    out = [p for p in [path_of(config, ev)] if p]
    for texto in _patch_texts(config, ev):
        for patron in _multi(config).get("pathPatterns") or []:
            try:
                for m in re.finditer(patron, texto, re.M):
                    out += [g.strip() for g in m.groups() if g and g.strip()]
            except re.error:
                continue
    return list(dict.fromkeys(out))


def content_of(config: dict, ev: Event) -> str:
    """El texto que la herramienta quiere escribir: el archivo entero, el reemplazo de un patch
    y las líneas `+` de un patch V4A. Nunca lo que se BORRA (`old_string`): prohibir escribir no
    puede prohibir limpiar."""
    keys = ((config.get("tools") or {}).get("$args") or {}).get("content") or ["content", "new_string"]
    partes = [ev.args[k] for k in keys if isinstance(ev.args.get(k), str)]
    agregada = _multi(config).get("addedLine")
    for texto in _patch_texts(config, ev):
        try:
            partes += [m.group(1) for m in re.finditer(agregada, texto, re.M)] if agregada else [texto]
        except re.error:
            partes.append(texto)
    return "\n".join(partes)


def written_text(config: dict, args, action_keys=("action",)) -> str:
    """Lo que una herramienta de aprendizaje (memory, skill_manage, cronjob_manage) va a GUARDAR.

    Sólo los campos de `tools.$written` (lo que se escribe), recorriendo `operations[]` y otros
    anidados. Una operación de borrado (`tools.$removeActions`) no aporta nada: si un secreto ya
    quedó guardado, la herramienta tiene que poder sacarlo — el freno que impide limpiar no es
    un freno, es una trampa (P3).
    """
    t = config.get("tools") or {}
    campos = set(t.get("$written") or ["content", "new_text", "new_string", "file_content", "prompt", "script"])
    borrar = {a.lower() for a in t.get("$removeActions") or ["remove", "delete", "remove_file"]}
    out: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            accion = next((v.get(k) for k in action_keys if isinstance(v.get(k), str)), "")
            if accion.lower() in borrar:
                return
            for k, x in v.items():
                if k in campos and isinstance(x, str):
                    out.append(x)
                elif isinstance(x, (dict, list, tuple)):
                    walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(args if isinstance(args, dict) else {})
    return "\n".join(out)


def abs_path(raw: str, root: Path, cwd: str = "") -> str:
    """La ruta absoluta resuelta (symlinks del ancestro existente), con `/`. Es contra ésta, y no
    contra el texto crudo, que se evalúan las reglas de fuera del repo: `.hermes/.env` relativo
    a un cwd en el home, o un symlink a `~/.hermes`, no pueden ser otros nombres que no casan."""
    raw = os.path.expanduser(raw or "")
    if not raw:
        return ""
    if re.match(r"^[A-Za-z]:[\\/]", raw) and os.name != "nt":
        return "/".join(split_path(raw))
    p = Path(raw) if os.path.isabs(raw) else Path(cwd or root) / raw
    try:
        p = p.resolve()
    except OSError:
        pass
    return p.as_posix()


def split_path(p: str) -> list[str]:
    """Segmentos de una ruta aceptando `/` y `\\` a la vez.

    Hermes corre en Windows vía WSL y también nativo; el modelo puede mandar `C:\\repo\\x.py`
    o mezclar separadores. Partir sólo por `os.sep` deja la ruta entera como UN segmento y
    ninguna regla por ruta caza nada: el freno no falla, desaparece.
    """
    return [s for s in re.split(r"[\\/]+", p) if s]


def rel_to_repo(raw: str, root: Path, cwd: str = "") -> str:
    """La ruta relativa a la raíz con `/`, o con `../` adelante si cae FUERA del repo.

    El `../` es la única señal que los frenos miran para decir "no es asunto de este repo".
    Se resuelven symlinks del ancestro existente: un `alias/ → secretos/` no puede ser un
    segundo nombre que las reglas no ven.
    """
    if not raw:
        return ""
    raw = os.path.expanduser(raw)
    is_win_abs = bool(re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith("\\\\"))
    if is_win_abs and os.name != "nt":
        # Una ruta de Windows vista desde POSIX (Hermes en WSL recibiendo `C:\...`): no es
        # relativa al cwd — `Path` la tomaría por un nombre raro DENTRO del repo y las reglas
        # del repo se aplicarían a un archivo que no es del repo. Es de afuera.
        return "../" + "/".join(split_path(raw))
    p = Path(raw) if (os.path.isabs(raw) or is_win_abs) else Path(cwd or root) / raw
    try:
        # resolve(strict=False) resuelve el ancestro existente y deja el resto literal.
        abs_ = p.resolve()
    except OSError:
        abs_ = p
    try:
        root_r = root.resolve()
    except OSError:
        root_r = root
    try:
        return PurePosixPath(abs_.relative_to(root_r).as_posix()).as_posix()
    except ValueError:
        return "../" + "/".join(split_path(str(abs_)))


def first_match(rules: list | None, text: str, flags: int = re.IGNORECASE) -> dict | None:
    """La primera regla `{pattern, reason}` cuyo patrón casa. Un patrón inválido se saltea:
    lo caza el self-test, no el turno del usuario."""
    for rule in rules or []:
        if not isinstance(rule, dict) or not isinstance(rule.get("pattern"), str):
            continue
        try:
            if re.search(rule["pattern"], text, flags):
                return rule
        except re.error:
            continue
    return None


def under_any(rel: str, prefixes: list[str] | None) -> bool:
    for p in prefixes or []:
        p = p.rstrip("/")
        if rel == p or rel.startswith(p + "/"):
            return True
    return False


def is_code(config: dict, rel: str) -> bool:
    gate = config.get("gate") or {}
    exts = gate.get("codeExtensions") or []
    globs = gate.get("codeGlobs") or []
    if not rel or rel.startswith(".."):
        return False
    if exts and not any(rel.endswith(e) for e in exts):
        return False
    return under_any(rel, globs) if globs else bool(exts)


def git_dir(root: Path) -> Path | None:
    """El directorio de git del repo. En un worktree (`hermes -w`, los de kanban) `.git` es un
    ARCHIVO `gitdir: <ruta>`: tratarlo como directorio hace fallar en silencio todo lo que
    escribe adentro (el marcador del gate, por ejemplo)."""
    g = root / ".git"
    if g.is_dir():
        return g
    if g.is_file():
        try:
            m = re.match(r"gitdir:\s*(.+)", g.read_text(encoding="utf-8", errors="replace").strip())
        except OSError:
            return None
        if m:
            p = Path(m.group(1).strip())
            return p if p.is_absolute() else (root / p).resolve()
    return None


def marker_path(config: dict | None, root: Path | None = None) -> Path | None:
    m = ((config or {}).get("gate") or {}).get("marker")
    if not m:
        return None
    root = root or repo_root()
    if m.startswith(".git/"):
        g = git_dir(root)
        if g is not None:
            return g / m[len(".git/"):]
    return root / m


def mark_gate_dirty(config: dict, root: Path | None = None) -> None:
    """Marca "hay código editado sin gate verde". Lo lee el freno de fin de turno."""
    m = marker_path(config, root)
    if not m:
        return
    try:
        m.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        m.write_text(datetime.now(timezone.utc).isoformat())
    except OSError:
        pass  # si no se puede marcar, el gate sigue siendo responsabilidad del agente


def is_win_path(p: str) -> bool:
    return bool(PureWindowsPath(p).drive)
