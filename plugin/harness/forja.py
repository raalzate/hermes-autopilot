"""
Forjas: dónde viven el repo, los issues, los milestones, el tablero y la wiki de cada proyecto del
workspace (GitHub, GitLab, Azure DevOps…). Lo usa `scripts/workspace.py` (ADR 0013).

Una forja es un manifiesto (`plantillas/forjas/<id>.json`) que traduce OPERACIONES abstractas
(`issue.crear`, `issue.vincular`…) a argv de su CLI. Nada de un proveedor vive acá (P4): ni `gh`,
ni `glab`, ni `az`. Estas funciones son puras: arman comandos, leen salidas y reescriben el
checklist de una épica. No lanzan procesos (P19): lo ejecuta el script, que es el que publica, y
sólo con `--apply` (P13: el loop nunca publica).

Plantilla de un argumento: `"{var}"` se reemplaza; una sublista `["-m", "{milestone}"]` es un grupo
OPCIONAL: entra entero si tiene todas sus variables, y se omite si le falta alguna. Una variable
que falta fuera de un grupo es error, nunca un argumento vacío.

El checklist de una épica (el issue padre en el repo de gestión) es la fuente de la verdad del
despacho: cada hijo es una línea `- [ ] [<proyecto>] <título>`; despachado, la línea gana su
referencia (`→ <repo>#<n>`); cerrado en la forja, se marca `[x]`; escalado por el loop, `[!]`.
"""
from __future__ import annotations

import json
import re

OPERACIONES = ("repo.crear", "issue.crear", "issue.id", "issue.vincular", "issue.estado", "issue.cuerpo",
               "issue.editar", "milestone.crear", "tablero.crear", "tablero.agregar")
ESTADOS = ("abierto", "cerrado")
_VAR = re.compile(r"\{([a-z_]+)\}")
# `- [ ] [api] Título → org/api#12` · la marca, el proyecto, el título y (si ya salió) la referencia.
HIJO = re.compile(r"^(?P<pre>\s*[-*]\s+\[)(?P<marca>[ xX!])\]\s+\[(?P<proyecto>[\w.-]+)\]\s+(?P<titulo>.+?)"
                  r"(?:\s+→\s+(?P<ref>\S+#\d+))?\s*$")


class ForjaError(ValueError):
    pass


def variables(plantilla) -> set[str]:
    out: set[str] = set()
    for a in plantilla or []:
        for x in (a if isinstance(a, list) else [a]):
            out.update(_VAR.findall(str(x)))
    return out


def _sust(texto: str, vars_: dict) -> str:
    return _VAR.sub(lambda m: str(vars_[m.group(1)]), texto)


def rellenar(texto: str, vars_: dict) -> str:
    """Como una plantilla de argumento, pero lo que no tiene valor queda como está (la URL de la wiki,
    la salida de la forja simulada). Una sola pasada: un valor con llaves no se vuelve a leer."""
    return _VAR.sub(lambda m: str(vars_[m.group(1)]) if m.group(1) in vars_ else m.group(0), texto or "")


def comando(manifiesto: dict, op: str, vars_: dict) -> list[str] | None:
    """El argv de `op` en esta forja. None si la forja no la tiene (declarada `null`: no hace falta
    o no existe, como el tablero de Azure Boards, que viene con el proyecto)."""
    ops = manifiesto.get("ops") or {}
    if op not in ops:
        raise ForjaError(f"la forja `{manifiesto.get('id')}` no declara la operación `{op}`")
    plantilla = ops[op]
    if plantilla is None:
        return None
    dados = {**(manifiesto.get("defaults") or {}), **{k: v for k, v in vars_.items() if v is not None and v != ""}}
    argv: list[str] = []
    for a in plantilla:
        if isinstance(a, list):
            if all(v in dados for x in a for v in _VAR.findall(str(x))):
                argv.extend(_sust(str(x), dados) for x in a)
            continue
        faltan = [v for v in _VAR.findall(str(a)) if v not in dados]
        if faltan:
            raise ForjaError(f"`{op}` en `{manifiesto.get('id')}`: falta {', '.join(faltan)}")
        argv.append(_sust(str(a), dados))
    return argv


def leer_salida(manifiesto: dict, op: str, salida: str) -> str:
    """Lo que interesa de lo que imprimió la CLI: `{"regex": …}` (primer grupo) o `{"json": "a.b"}`."""
    spec = (manifiesto.get("salida") or {}).get(op)
    texto = (salida or "").strip()
    if not spec:
        return texto
    if spec.get("regex"):
        m = re.search(spec["regex"], texto)
        if not m:
            raise ForjaError(f"`{op}`: la salida no tiene lo esperado ({spec['regex']}): {texto[:200]!r}")
        return m.group(1)
    if spec.get("json"):
        try:
            v = json.loads(texto)
            for k in spec["json"].split("."):
                v = v[int(k)] if isinstance(v, list) else v[k]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ForjaError(f"`{op}`: la salida no es el JSON esperado ({spec['json']}): {e}") from e
        return str(v)
    return texto


def estado(manifiesto: dict, crudo: str) -> str:
    """El estado de la forja (`OPEN`, `opened`, `Done`…) en el vocabulario del workspace."""
    mapa = manifiesto.get("estados") or {}
    return mapa.get((crudo or "").strip(), "abierto")


def vars_de_repo(repo: str) -> dict:
    """`org/repo` u `org/proyecto/repo` (Azure): las partes que usan las plantillas."""
    partes = [p for p in (repo or "").split("/") if p]
    if len(partes) < 2:
        raise ForjaError(f"`{repo}` no es `<dueño>/<repo>`")
    from urllib.parse import quote
    return {"repo": "/".join(partes), "owner": partes[0], "nombre": partes[-1],
            "proyecto": partes[1] if len(partes) > 2 else partes[-1], "repo_enc": quote("/".join(partes), safe="")}


def ref(repo: str, n) -> str:
    return f"{repo}#{n}"


def partir_ref(r: str) -> tuple[str, str]:
    repo, _, n = (r or "").rpartition("#")
    if not repo or not n.isdigit():
        raise ForjaError(f"`{r}` no es una referencia `<repo>#<n>`")
    return repo, n


def hijos(cuerpo: str) -> list[dict]:
    """Las líneas hijas del checklist de la épica, en orden, con su número de línea."""
    out = []
    for i, linea in enumerate((cuerpo or "").splitlines()):
        m = HIJO.match(linea)
        if m:
            out.append({"linea": i, "marca": m.group("marca").lower(), "proyecto": m.group("proyecto"),
                        "titulo": m.group("titulo").strip(), "ref": m.group("ref") or ""})
    return out


def plan_despacho(cuerpo: str, proyectos: dict) -> tuple[list[dict], list[str]]:
    """(lo que hay que crear, problemas). Un hijo ya despachado no se repite; uno de un proyecto que
    el workspace no tiene, o que no es codificador, es un problema y no se crea."""
    crear, problemas = [], []
    for h in hijos(cuerpo):
        if h["ref"]:
            continue
        p = proyectos.get(h["proyecto"])
        if not p:
            problemas.append(f"línea {h['linea'] + 1}: el proyecto `{h['proyecto']}` no está en workspace.json")
        elif p.get("rol", "codificador") != "codificador":
            problemas.append(f"línea {h['linea'] + 1}: `{h['proyecto']}` no es codificador: el código no va al repo de gestión")
        else:
            crear.append(h)
    return crear, problemas


def con_ref(cuerpo: str, linea: int, r: str) -> str:
    lineas = (cuerpo or "").splitlines()
    lineas[linea] = lineas[linea].rstrip() + f" → {r}"
    return "\n".join(lineas) + ("\n" if (cuerpo or "").endswith("\n") else "")


def con_marcas(cuerpo: str, marcas: dict[str, str]) -> str:
    """El checklist con la marca de cada hijo según su referencia: `x` cerrado, `!` escalado, ` ` abierto."""
    lineas = (cuerpo or "").splitlines()
    for h in hijos(cuerpo):
        nueva = marcas.get(h["ref"])
        if h["ref"] and nueva is not None and nueva != h["marca"]:
            m = HIJO.match(lineas[h["linea"]])
            lineas[h["linea"]] = lineas[h["linea"]][:m.end("pre")] + nueva + lineas[h["linea"]][m.end("marca"):]
    return "\n".join(lineas) + ("\n" if (cuerpo or "").endswith("\n") else "")


def cuerpo_hijo(manifiesto: dict, padre: str, texto: str = "") -> str:
    """El cuerpo del issue hijo: siempre nombra al padre, aunque la forja tenga vínculo nativo (si el
    vínculo falla o se pierde, el texto queda y `estado` lo encuentra igual)."""
    plantilla = manifiesto.get("cuerpoHijo") or "Parte de {padre}"
    return (texto.strip() + "\n\n" if texto.strip() else "") + plantilla.replace("{padre}", padre)


def problemas_de_manifiesto(m: dict) -> list[str]:
    out = []
    for k in ("id", "cli", "ops", "issuePattern", "issueExample", "estados", "clases", "ci", "examples"):
        if k not in m:
            out.append(f"falta `{k}`")
    ops = m.get("ops") or {}
    for op in OPERACIONES:
        if op not in ops:
            out.append(f"falta la operación `{op}` (null si la forja no la necesita)")
    for op, plantilla in ops.items():
        if op not in OPERACIONES:
            out.append(f"`{op}` no es una operación del workspace")
        elif plantilla is not None and (not plantilla or str(plantilla[0]) != m.get("cli")):
            out.append(f"`{op}` no empieza con la CLI de la forja (`{m.get('cli')}`)")
    for v in (m.get("estados") or {}).values():
        if v not in ESTADOS:
            out.append(f"estado `{v}` no es uno de {ESTADOS}")
    try:
        if m.get("issueExample") and not re.search(m.get("issuePattern") or "(?!)", m["issueExample"]):
            out.append("`issueExample` no casa con `issuePattern`")
    except re.error as e:
        out.append(f"`issuePattern` no compila: {e}")
    return out
