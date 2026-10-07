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
    PERFIL      `profiles`      un perfil de stack lleva hechos del lenguaje, nunca reglas de otro repo
    COHERENCIA  `coherence`     lo que una guía le recomienda al agente, `terminal.deny` no lo veda
"""
from __future__ import annotations

import json
import re

from .core import first_match, under_any

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


def _en(obj, ruta: str):
    for k in ruta.split("."):
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def rule_perfil(config, rel, text):
    """Un perfil de stack lleva la FORMA del lenguaje (qué es código, qué es derivado, cómo se
    testea) y nada más. Las reglas concretas son las cicatrices de UN repo: instaladas en otro
    son ruido que gasta contexto y se desactivan en una semana (P17). Sin esta regla, el primer
    apuro mete `terminal.deny` en un perfil y el arnés empieza a viajar con cicatrices ajenas."""
    spec = config.get("profiles") or {}
    carpeta = spec.get("dir")
    if not carpeta or not rel.endswith(".json") or not under_any(rel, [carpeta]):
        return []
    try:
        perfil = json.loads(text)
    except ValueError as e:
        return [f"PERFIL {rel} — no es JSON válido: {e}"]
    if not isinstance(perfil, dict):
        return [f"PERFIL {rel} — un perfil es un objeto JSON"]
    vacio = lambda v: v is None or (isinstance(v, (list, dict)) and not v)  # noqa: E731
    out = [f"PERFIL {rel} — un perfil no lleva `{k}`. {spec.get('reason', '')}".rstrip()
           for k in spec.get("forbiddenKeys") or [] if not vacio(_en(perfil, k))]
    out += [f"PERFIL {rel} — falta `{k}`: sin eso el perfil no le aporta nada al instalador"
            for k in spec.get("requiredKeys") or [] if vacio(_en(perfil, k))]
    return out


def _comando_vedado(config, comando: str):
    """La regla de `terminal.deny` que frenaría este comando, con la MISMA función que usa el
    freno: si COHERENCIA evaluara distinto que `terminal_guard`, mediría otro freno."""
    return first_match((config.get("terminal") or {}).get("deny"), comando)


def es_guia(config, rel: str) -> bool:
    guias = (config.get("coherence") or {}).get("guides") or []
    return rel.endswith(".md") and (rel in guias or under_any(rel, guias))


def rule_coherencia(config, rel, text):
    """Una guía y un freno se escriben en momentos distintos y nadie los mira juntos. Cuando
    chocan, el agente queda en un bucle: hace lo que la guía dice, el freno lo bloquea,
    reintenta. Qué cuenta como «recomendado», sin adivinar intención:

      - en una guía (`coherence.guides`), cada línea de un bloque de shell;
      - en el config, cada comando entre backticks de un `reason`/`message`. El que casa con la
        PROPIA regla que lo cita es la ofensa que ese motivo describe; cualquier otro es la
        salida que se le ofrece al agente, y tiene que pasar.

    `commandPattern` es la forma de un comando en ESTE repo: sin él la regla no corre."""
    co = config.get("coherence") or {}
    rx = _re(co.get("commandPattern", "") or "(?!)")
    if not co.get("commandPattern") or not rx:
        return []
    motivo = co.get("reason", "")
    out = []

    def denegar(linea: int, comando: str):
        hit = _comando_vedado(config, comando)
        if hit:
            out.append(f"COHERENCIA {rel}:{linea} — se le recomienda al agente `{comando}` y "
                       f"`terminal.deny[{hit.get('id', '?')}]` lo bloquea. {motivo} "
                       "Corregí la guía o la regla: las dos no pueden tener razón.")

    if rel == co.get("configFile", ".hermes/harness.config.json"):
        try:
            cfg = json.loads(text)
        except ValueError:
            return []  # un config que no parsea ya lo reporta el self-test
        claves = set(co.get("configKeys") or ["reason", "message"])

        def visitar(nodo):
            if isinstance(nodo, list):
                for v in nodo:
                    visitar(v)
            elif isinstance(nodo, dict):
                for k, v in nodo.items():
                    if k in claves and isinstance(v, str):
                        for comando in re.findall(r"`([^`]+)`", v):
                            if not rx.search(comando) or (nodo.get("pattern") and first_match([nodo], comando)):
                                continue
                            i = text.find(comando)
                            denegar(_linea(text, i) if i >= 0 else 0, comando)
                    else:
                        visitar(v)

        visitar(cfg)
        return out

    if not es_guia(config, rel):
        return []
    vallas = {v.lower() for v in co.get("shellFences") or ["bash", "sh", "shell", "console"]}
    en_bloque = False
    for n, linea in enumerate(text.splitlines(), 1):
        m = re.match(r"^\s*```\s*([\w-]*)", linea)
        if m:
            en_bloque = not en_bloque and m.group(1).lower() in vallas
            continue
        if not en_bloque:
            continue
        # El `$ ` del prompt y el comentario de cola no son parte del comando.
        comando = re.sub(r"\s+#\s.*$", "", re.sub(r"^\s*\$\s+", "", linea)).strip()
        if comando and not comando.startswith("#") and rx.search(comando):
            denegar(n, comando)
    return out


RULES = [("PATRON", rule_patron), ("INVARIANTE", rule_invariante), ("INCIDENTE", rule_incidente),
         ("CONTEXTO", rule_contexto), ("SKILL", rule_skill), ("PERFIL", rule_perfil),
         ("COHERENCIA", rule_coherencia)]


def lint_one(config: dict, rel: str, text: str) -> list[str]:
    out: list[str] = []
    for _, fn in RULES:
        out += fn(config, rel, text)
    return out
