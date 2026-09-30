"""
Las clases de regla del lint, como funciones puras `(config, ruta, texto) -> [hallazgos]`.

Viven en el paquete y no en `scripts/lint.py` porque las usan dos: el comando del gate y el
plugin, que las corre EN PROCESO sobre lo que el agente acaba de escribir. Lanzar un proceso por
cada edición cuesta latencia en cada tool call; importar una función, no.

Clases:
    PATRON      `patterns`      regex prohibida en archivos (misma lista que el freno de escritura)
    INVARIANTE  `invariants`    un archivo DEBE contener / NO debe contener una regex
    INCIDENTE   `incidents`     cada incidente declara Síntoma / Causa / Regla / Mecanismo
    CONTEXTO    `context`       los archivos de contexto que Hermes inyecta caben y no se bloquean
    SKILL       `skills`        cada SKILL.md tiene frontmatter válido para Hermes (agentskills.io)
"""
from __future__ import annotations

import re

TEXT_EXT = {".py", ".md", ".json", ".yaml", ".yml", ".sh", ".toml", ".txt", ".cfg", ".ini", ""}


def _re(p: str, flags: int = 0):
    try:
        return re.compile(p, flags)
    except (re.error, TypeError):
        return None


def _linea(text: str, pos: int) -> int:
    return text[:pos].count("\n") + 1


def rule_patron(config, rel, text):
    out = []
    for r in config.get("patterns") or []:
        rutas = r.get("paths")
        if rutas and not any((_re(p) and _re(p).search(rel)) for p in rutas):
            continue
        if any(_re(p) and _re(p).search(rel) for p in r.get("exceptPaths") or []):
            continue
        rx = _re(r.get("pattern", ""), 0 if r.get("caseSensitive") else re.I)
        if not rx:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if rx.search(line) and "harness-lint: allow" not in line:
                out.append(f"PATRON[{r.get('id', '?')}] {rel}:{n} — {r.get('reason', '')}")
                break
    return out


def rule_invariante(config, rel, text):
    out = []
    for inv in config.get("invariants") or []:
        if inv.get("file") != rel:
            continue
        for p in inv.get("mustContain") or []:
            rx = _re(p, re.M)
            if not (rx and rx.search(text)):
                out.append(f"INVARIANTE {rel} — debe contener /{p}/: {inv.get('reason', '')}")
        for p in inv.get("mustNotContain") or []:
            rx = _re(p, re.M)
            m = rx.search(text) if rx else None
            if m:
                out.append(f"INVARIANTE {rel}:{_linea(text, m.start())} — no debe contener /{p}/: {inv.get('reason', '')}")
    return out


def rule_incidente(config, rel, text):
    inc = config.get("incidents") or {}
    if inc.get("file") != rel:
        return []
    heading = inc.get("heading", "### GOTCHA")
    out = []
    for b in re.split(rf"^(?={re.escape(heading)})", text, flags=re.M):
        if not b.startswith(heading):
            continue
        titulo = b.splitlines()[0]
        for campo in inc.get("requiredLines") or []:
            if not re.search(rf"^\s*[-*]?\s*\*\*{re.escape(campo)}:?\*\*", b, re.M):
                out.append(f"INCIDENTE {rel} — «{titulo}» sin **{campo}:** (un incidente sin mecanismo no es una lección)")
    return out


def rule_contexto(config, rel, text):
    """Los archivos de contexto que Hermes inyecta en el prompt.

    Dos fallas silenciosas, las dos de Hermes y no del repo:
      - pasado el tope, Hermes TRUNCA (70 % cabeza, 20 % cola) y lo que se pierde es el medio;
      - si una sola línea casa con su escáner de inyección, Hermes reemplaza el archivo ENTERO
        por `[BLOCKED: ...]` y el agente arranca sin ninguna regla. Un comando de ejemplo que lee
        un secreto alcanza. Los patrones van en `context.blockedPatterns` (copiados del escáner
        de la versión de Hermes que se use), no acá.
    """
    ctx = config.get("context") or {}
    if rel not in (ctx.get("files") or []):
        return []
    out = []
    tope = ctx.get("maxChars")
    if tope and len(text) > tope:
        out.append(f"CONTEXTO {rel} — {len(text)} caracteres > {tope}: {ctx.get('reason', '')}")
    for r in ctx.get("blockedPatterns") or []:
        rx = _re(r.get("pattern", ""), re.I)
        m = rx.search(text) if rx else None
        if m:
            out.append(f"CONTEXTO[{r.get('id', '?')}] {rel}:{_linea(text, m.start())} — "
                       f"Hermes descarta el archivo ENTERO si ve esto: {r.get('reason', '')}")
    return out


FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)


def parse_frontmatter(text: str) -> dict | None:
    """Frontmatter YAML plano: `clave: valor` de una línea, o `>`/`|` con continuación
    indentada. Sin PyYAML a propósito: el arnés no tiene dependencias."""
    m = FRONT.match(text)
    if not m:
        return None
    data: dict = {}
    key = None
    for line in m.group(1).splitlines():
        if key and line.startswith("  ") and data.get(key) is not None and not re.match(r"^\s+[A-Za-z0-9_-]+:", line):
            data[key] = (data[key] + " " + line.strip()).strip()
            continue
        mm = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if mm:
            key, val = mm.group(1), mm.group(2).strip()
            data[key] = "" if val in (">", "|", ">-", "|-") else val.strip("'\"")
        elif not line.startswith(" "):
            key = None
    return data


def rule_skill(config, rel, text):
    sk = config.get("skills") or {}
    roots = sk.get("roots") or []
    if not rel.endswith("/SKILL.md") or not any(rel.startswith(r.rstrip("/") + "/") for r in roots):
        return []
    fm = parse_frontmatter(text)
    if fm is None:
        return [f"SKILL {rel} — sin frontmatter `---`: Hermes no la indexa y el agente nunca la ve"]
    out = []
    carpeta = rel.split("/")[-2]
    nombre = fm.get("name", "")
    patron = sk.get("namePattern", r"[a-z0-9][a-z0-9._-]*")
    if not nombre:
        out.append(f"SKILL {rel} — falta `name`")
    elif len(nombre) > sk.get("maxName", 64) or not re.fullmatch(patron, nombre):
        out.append(f"SKILL {rel} — `name: {nombre}` no cumple {patron} (≤ {sk.get('maxName', 64)})")
    elif nombre != carpeta:
        out.append(f"SKILL {rel} — `name: {nombre}` ≠ carpeta `{carpeta}`")
    desc = fm.get("description", "")
    if not desc:
        out.append(f"SKILL {rel} — falta `description`: es lo único que el agente lee para decidir cargarla")
    elif len(desc) > sk.get("maxDescription", 1024):
        out.append(f"SKILL {rel} — description de {len(desc)} > {sk.get('maxDescription', 1024)} caracteres")
    tope = sk.get("maxBodyChars")
    if tope and len(text) > tope:
        out.append(f"SKILL {rel} — {len(text)} caracteres > {tope}: se carga entera al invocarla")
    return out


RULES = [("PATRON", rule_patron), ("INVARIANTE", rule_invariante), ("INCIDENTE", rule_incidente),
         ("CONTEXTO", rule_contexto), ("SKILL", rule_skill)]


def lint_one(config: dict, rel: str, text: str) -> list[str]:
    out: list[str] = []
    for _, fn in RULES:
        out += fn(config, rel, text)
    return out
