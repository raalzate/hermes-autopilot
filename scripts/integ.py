#!/usr/bin/env python3
"""
`integ.py` — las integraciones del agente: catálogo, configuración, dependencias y prueba.

    python3 scripts/integ.py list                          catálogo y estado (habilitada · instalada · lock)
    python3 scripts/integ.py show <id>                     el manifiesto, sus perfiles y qué secretos pide
    python3 scripts/integ.py add <id> [--perfil p] [--set ruta=valor …] [--apply]
    python3 scripts/integ.py set <id> <ruta> <valor> [--apply]        p.ej. policy.allowRecipients '["^whatsapp:\\+57"]'
    python3 scripts/integ.py rm <id> [--apply]
    python3 scripts/integ.py test <id> <herramienta> ['{"args": …}']   ¿qué decide el plugin?
    python3 scripts/integ.py deps <id> [--apply]           instala lo que pide, aislado y fijado, y escribe el lock
    python3 scripts/integ.py hermes <id>                   el bloque `mcp_servers` para el config de Hermes
    python3 scripts/integ.py check                         señal del gate: catálogo válido, ejemplos que frenan, lock al día

Hermes trae los conectores; el arnés los gobierna. Una integración es un MANIFIESTO del catálogo
(`plantillas/integraciones/<id>.json`): qué herramientas trae, de qué clase es cada una (leer ·
escribir · mandar · destruir), qué hace cada perfil (`lectura`, `asistente`, `autonomo`), a quién se
puede mandar, qué dominios se navegan, cuánto se gasta, qué instala y con qué secretos arranca.
`add` lo MATERIALIZA en `integrations.enabled.<id>` del config —el config sigue siendo la única
fuente de especificidad (P4)— después de pasar sus `examples` por el mismo `guards.evaluate` que usa
el plugin (P2: cada ejemplo frena y lo frena ESTA integración; P3: los inocentes pasan).

Sin `--apply` nada se escribe (P9). `deps` nunca usa `sudo`: lo del sistema lo imprime para el humano.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugin"))
from harness import core, guards, rules  # noqa: E402
from harness import integ as nucleo  # noqa: E402
from harness.core import CONFIG_PATH, HARNESS_HOME, REPO_ROOT  # noqa: E402

CATALOGO = HARNESS_HOME / "plantillas" / "integraciones"
LOCK_REL = ".hermes/integraciones.lock"
KINDS = ("mcp", "hermes", "cli")
VERSION_FIJA = re.compile(r"^\d+(\.\d+){0,3}$")
REF_SECRETO = re.compile(r"^secret://(keychain|keyring|op|file|env)/.+")
# Claves de un manifiesto que no viajan al config: son del catálogo (instalar, describir, perfiles).
SOLO_CATALOGO = ("perfiles", "perfilPorDefecto", "descripcion", "setup")


# ── catálogo ─────────────────────────────────────────────────────────────────

def catalogo(directorio: Path = CATALOGO) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(directorio.glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            out[f.stem] = {"_error": f"{f.name}: JSON inválido: {e}"}
            continue
        m["_file"] = f.name
        out[m.get("id") or f.stem] = m
    return out


def integ_home() -> Path:
    """Dónde se instalan las dependencias: FUERA del repo y del entorno de Hermes (ADR 0002)."""
    forzado = os.environ.get("HARNESS_INTEG_HOME")
    if forzado:
        return Path(forzado).expanduser()
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser() / "integraciones"


def prefijo_de(iid: str, entry: dict) -> Path:
    return integ_home() / iid / str(entry.get("version") or "0")


def materializar(m: dict, perfil: str | None = None, sets: list[tuple[str, object]] | None = None) -> dict:
    """La entrada de `integrations.enabled.<id>`: el manifiesto con el perfil elegido resuelto en
    `actions`. Lo que sólo sirve al catálogo no viaja."""
    perfil = perfil or m.get("perfilPorDefecto") or next(iter(m.get("perfiles") or {}), "")
    if perfil not in (m.get("perfiles") or {}):
        raise ValueError(f"`{m.get('id')}` no tiene el perfil `{perfil}`. Son: {', '.join(m.get('perfiles') or {})}")
    entry = {k: copy.deepcopy(v) for k, v in m.items() if k not in SOLO_CATALOGO and not k.startswith("_")}
    entry["perfil"] = perfil
    entry["actions"] = dict(m["perfiles"][perfil])
    for ruta, valor in sets or []:
        entry = set_ruta(entry, ruta, valor)
    return entry


def _partes(ruta: str) -> list:
    return [int(p) if p.isdigit() else p for p in ruta.split(".") if p != ""]


def set_ruta(d: dict, ruta: str, valor) -> dict:
    nuevo = copy.deepcopy(d)
    partes = _partes(ruta)
    nodo = nuevo
    for p in partes[:-1]:
        nodo = nodo[p] if isinstance(nodo, list) else nodo.setdefault(p, {})
    nodo[partes[-1]] = valor
    return nuevo


def esqueleto() -> dict:
    """`integrations` de la plantilla, sin integraciones: lo que un config viejo no tiene."""
    try:
        base = json.loads((HARNESS_HOME / "plantillas" / "harness.config.json").read_text(encoding="utf-8"))
        sk = copy.deepcopy(base.get("integrations") or {})
    except (OSError, ValueError):
        sk = {}
    sk["enabled"] = {}
    return sk


def con(config: dict, iid: str, entry: dict | None) -> dict:
    """El config con la integración puesta (o quitada, con `entry=None`)."""
    nuevo = copy.deepcopy(config)
    sec = nuevo.get("integrations")
    if not isinstance(sec, dict):
        sec = nuevo["integrations"] = esqueleto()
    en = sec.setdefault("enabled", {})
    if entry is None:
        en.pop(iid, None)
    else:
        en[iid] = entry
    return nuevo


# ── la prueba: los ejemplos por el camino del plugin ─────────────────────────

def nombre_hermes(config: dict, entry: dict, crudo: str) -> str:
    return nucleo.nombre_mcp(config, entry, crudo) if entry.get("kind") == "mcp" else crudo


def evento(config: dict, iid: str, entry: dict, ej: dict) -> core.Event:
    """El Event con que Hermes llamaría: una herramienta MCP con su prefijo, una del gateway tal cual,
    una de CLI como comando de terminal."""
    uso = {f"{iid}:{c}": n for c, n in (ej.get("uso") or {}).items()}
    contaminada = "un correo de afuera" if ej.get("contaminada") else ""
    if entry.get("kind") == "cli":
        shell = ((config.get("tools") or {}).get("shell") or ["terminal"])[0]
        return core.Event(tool=shell, args={"command": ej.get("command", "")}, contaminada=contaminada, uso=uso)
    return core.Event(tool=nombre_hermes(config, entry, ej.get("tool", "")), args=ej.get("args") or {},
                      contaminada=contaminada, uso=uso)


def probar(config: dict, iid: str, root: Path = REPO_ROOT) -> list[str]:
    """Los problemas de la integración `iid` tal como está en `config`. Vacío = muerde lo que dice y
    deja pasar lo que dice."""
    entry = nucleo.habilitadas(config).get(iid)
    if entry is None:
        return [f"`{iid}` no está en `integrations.enabled`"]
    errores = []
    aplican = [e for e in entry.get("examples") or [] if e.get("perfil") in (None, entry.get("perfil"))]
    if not any(e.get("expect") in ("block", "approve") for e in aplican):
        errores.append(f"el perfil `{entry.get('perfil')}` no tiene ningún ejemplo que frene: una integración sin ejemplo es una sin prueba de vida (P2)")
    if not any(e.get("expect") == "allow" for e in aplican):
        errores.append(f"el perfil `{entry.get('perfil')}` no tiene ningún inocente: nada prueba que no muerde de más (P3)")
    for ej in aplican:
        # `set`: el ejemplo necesita una política puesta (una lista de destinatarios, de dominios).
        cfg, ent = config, entry
        if ej.get("set"):
            for ruta, valor in ej["set"].items():
                ent = set_ruta(ent, ruta, valor)
            cfg = con(config, iid, ent)
        d = guards.evaluate(evento(cfg, iid, ent, ej), cfg, root)
        hizo = "block" if d.block else ("approve" if d.approve else "allow")
        que = ej.get("tool") or ej.get("command")
        if hizo != ej.get("expect"):
            errores.append(f"ejemplo `{que}`: el plugin decide `{hizo}`, se esperaba `{ej.get('expect')}`"
                           + (f" — {d.message.splitlines()[0]}" if d.message else ""))
        elif hizo != "allow" and not str((d.rule or {}).get("id", "")).startswith(f"integ:{iid}:") and not ej.get("otroFreno"):
            errores.append(f"ejemplo `{que}`: lo frena `{(d.rule or {}).get('id')}`, no la integración (marcá `otroFreno` si es a propósito)")
        elif ej.get("regla") and (d.rule or {}).get("id") != f"integ:{iid}:{ej['regla']}" and hizo != "allow":
            errores.append(f"ejemplo `{que}`: lo frena `{(d.rule or {}).get('id')}`, se esperaba `integ:{iid}:{ej['regla']}`")
    texto = json.dumps(config, indent=2, ensure_ascii=False)
    errores += [f"lint: {h}" for h in rules.lint_one(config, ".hermes/harness.config.json", texto)]
    return errores


def problemas_de_manifiesto(m: dict) -> list[str]:
    """La forma: lo que `add` necesita para poder probarlo y lo que `deps` necesita para instalarlo."""
    if m.get("_error"):
        return [m["_error"]]
    p = []
    iid = m.get("id", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", iid):
        p.append("`id` en minúsculas, dígitos y `-`")
    if m.get("_file") and m["_file"] != f"{iid}.json":
        p.append(f"el archivo se llama {m['_file']}: tiene que ser {iid}.json")
    for k in ("titulo", "descripcion", "verificado", "kind", "perfiles", "examples"):
        if not m.get(k):
            p.append(f"falta `{k}`")
    if m.get("kind") not in KINDS:
        p.append(f"`kind` es {' · '.join(KINDS)}")
    if m.get("kind") == "mcp" and not m.get("server"):
        p.append("un MCP necesita `server`: el nombre con que Hermes prefija sus herramientas")
    if m.get("kind") == "hermes" and not m.get("tools"):
        p.append("una integración de Hermes necesita `tools`: la regex de sus herramientas")
    if m.get("kind") == "cli" and not m.get("command"):
        p.append("una integración por CLI necesita `command`: la regex del comando")
    if m.get("ignoreAnnotations") and not m.get("$ignoreAnnotations"):
        p.append("`ignoreAnnotations` sin `$ignoreAnnotations`: por qué no se le cree al servidor")
    if m.get("kind") == "mcp" and not m.get("toolNames"):
        p.append("un MCP necesita `toolNames`: la lista verificada de lo que publica (`integ_run.py --probe`)")
    for clave in ("tools", "command", "thirdParty", "recipientKeys", "urlKeys", "fileKeys", "recipientPattern",
                  "filePattern", "urlPattern", *[f"classes.{c}" for c in nucleo.CLASES]):
        v = m
        for parte in clave.split("."):
            v = v.get(parte) if isinstance(v, dict) else None
        if isinstance(v, str):
            try:
                re.compile(v)
            except re.error as e:
                p.append(f"`{clave}` no es una regex válida: {e}")
    for nombre, acciones in (m.get("perfiles") or {}).items():
        for c, a in acciones.items():
            if c not in nucleo.CLASES or c == "deny":
                p.append(f"perfil `{nombre}`: clase `{c}` desconocida (read · write · send · destructive)")
            if a not in nucleo.ACCIONES:
                p.append(f"perfil `{nombre}`: acción `{a}` desconocida ({' · '.join(nucleo.ACCIONES)})")
    if m.get("perfilPorDefecto") and m["perfilPorDefecto"] not in (m.get("perfiles") or {}):
        p.append(f"`perfilPorDefecto` {m['perfilPorDefecto']} no es un perfil")
    for n, ej in enumerate(m.get("examples") or []):
        if ej.get("expect") not in ("block", "approve", "allow"):
            p.append(f"examples[{n}]: `expect` es block · approve · allow")
        if ej.get("perfil") and ej["perfil"] not in (m.get("perfiles") or {}):
            p.append(f"examples[{n}]: el perfil `{ej['perfil']}` no existe")
        if not ej.get("why"):
            p.append(f"examples[{n}]: falta `why` (qué prueba)")
    for r in m.get("requires") or []:
        if r.get("kind") in ("npm", "pypi") and not VERSION_FIJA.match(str(r.get("version", ""))):
            p.append(f"requires `{r.get('package')}`: versión `{r.get('version')}` sin fijar (una exacta: `1.2.3`, nunca `latest` ni un rango)")
        if r.get("kind") not in ("npm", "pypi", "browser", "system"):
            p.append(f"requires: `kind` {r.get('kind')} desconocido (npm · pypi · browser · system)")
    for k, v in ((m.get("launch") or {}).get("env") or {}).items():
        if isinstance(v, str) and nucleo_secreto(k) and not REF_SECRETO.match(v) and not v.startswith("{prefix}"):
            p.append(f"launch.env.{k}: un secreto va como referencia `secret://…`, nunca su valor")
    return p


def nucleo_secreto(nombre: str) -> bool:
    return re.search(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE)", nombre, re.I) is not None


def validar_catalogo(config_base: dict, root: Path = REPO_ROOT) -> list[str]:
    """Cada manifiesto, con cada uno de sus perfiles, materializado y probado sobre `config_base`."""
    errores = []
    for iid, m in catalogo().items():
        forma = problemas_de_manifiesto(m)
        errores += [f"{iid}: {e}" for e in forma]
        if forma:
            continue
        for perfil in m["perfiles"]:
            cfg = con(config_base, iid, materializar(m, perfil))
            errores += [f"{iid} ({perfil}): {e}" for e in probar(cfg, iid, root) if not e.startswith("lint:")]
    return errores


# ── dependencias ─────────────────────────────────────────────────────────────

def _bin_dir(prefijo: Path, kind: str) -> Path:
    if kind == "npm":
        return prefijo / "node_modules" / ".bin"
    return prefijo / "venv" / ("Scripts" if os.name == "nt" else "bin")


def pasos(iid: str, entry: dict) -> list[dict]:
    """Lo que `deps` haría, en orden. `argv` None = del sistema: se informa, no se corre."""
    pre = prefijo_de(iid, entry)
    out = []
    for r in entry.get("requires") or []:
        k = r.get("kind")
        if k == "system":
            hint = (r.get("hint") or {}).get(sys.platform) or (r.get("hint") or {}).get("default") or ""
            out.append({"req": r, "que": f"sistema: `{r.get('command')}`" + (f" ≥ {r['min']}" if r.get("min") else ""),
                        "argv": None, "hint": hint, "listo": _sistema_ok(r)})
        elif k == "npm":
            npm = shutil.which("npm") or "npm"
            out.append({"req": r, "que": f"npm {r['package']}@{r['version']} en {pre}",
                        "argv": [npm, "install", "--prefix", str(pre), "--ignore-scripts", "--no-audit", "--no-fund",
                                 "--save-exact", f"{r['package']}@{r['version']}"],
                        "listo": (_bin_dir(pre, "npm") / r.get("bin", "")).exists() and _version_npm(pre, r["package"]) == r["version"]})
        elif k == "pypi":
            venv = pre / "venv"
            py = _bin_dir(pre, "pypi") / ("python.exe" if os.name == "nt" else "python")
            out.append({"req": r, "que": f"pypi {r['package']}=={r['version']} en {venv}",
                        "argv": [sys.executable, "-m", "venv", str(venv)], "luego": [str(py), "-m", "pip", "install", "-q",
                                 "--disable-pip-version-check", "--report", str(pre / "pip-report.json"), f"{r['package']}=={r['version']}"],
                        "listo": (_bin_dir(pre, "pypi") / r.get("bin", "")).exists()})
        elif k == "browser":
            # El instalador del PROPIO servidor: sabe qué build de navegador espera su versión.
            inst = r.get("bin", "playwright")
            pw = _bin_dir(pre, "npm") / (inst + (".cmd" if os.name == "nt" else ""))
            out.append({"req": r, "que": f"navegador {r.get('engine')} en {pre / 'browsers'}",
                        "argv": [str(pw), *(r.get("args") or ["install"]), r.get("engine", "chromium")],
                        "env": {"PLAYWRIGHT_BROWSERS_PATH": str(pre / "browsers")},
                        "listo": (pre / "browsers").is_dir() and any((pre / "browsers").iterdir())})
    return out


def _sistema_ok(r: dict) -> bool:
    exe = shutil.which(r.get("command", ""))
    if not exe:
        return False
    if not r.get("min"):
        return True
    try:
        salida = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    m = re.search(r"(\d+)(?:\.(\d+))?", salida or "")
    if not m:
        return False
    tiene = (int(m.group(1)), int(m.group(2) or 0))
    pide = tuple(int(x) for x in (str(r["min"]).split(".") + ["0"])[:2])
    return tiene >= pide


def _version_npm(pre: Path, paquete: str) -> str:
    try:
        return json.loads((pre / "node_modules" / paquete / "package.json").read_text(encoding="utf-8")).get("version", "")
    except (OSError, ValueError):
        return ""


def integridad(iid: str, entry: dict) -> list[dict]:
    """Lo instalado, con su hash: el de npm (package-lock) o el sha256 del wheel (el reporte de pip)."""
    pre = prefijo_de(iid, entry)
    out = []
    for r in entry.get("requires") or []:
        if r.get("kind") == "npm":
            try:
                lock = json.loads((pre / "package-lock.json").read_text(encoding="utf-8"))
                h = (lock.get("packages") or {}).get(f"node_modules/{r['package']}", {}).get("integrity", "")
            except (OSError, ValueError):
                h = ""
            out.append({"kind": "npm", "package": r["package"], "version": _version_npm(pre, r["package"]), "integrity": h})
        elif r.get("kind") == "pypi":
            h, v = "", ""
            try:
                rep = json.loads((pre / "pip-report.json").read_text(encoding="utf-8"))
                for it in rep.get("install") or []:
                    if (it.get("metadata") or {}).get("name", "").lower().replace("_", "-") == r["package"].lower().replace("_", "-"):
                        v = it["metadata"].get("version", "")
                        h = "sha256-" + (((it.get("download_info") or {}).get("archive_info") or {}).get("hashes") or {}).get("sha256", "")
            except (OSError, ValueError):
                pass
            out.append({"kind": "pypi", "package": r["package"], "version": v, "integrity": h})
    return out


def leer_lock(root: Path = REPO_ROOT) -> dict:
    try:
        v = json.loads((root / LOCK_REL).read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def escribir_lock(root: Path, lock: dict) -> None:
    p = root / LOCK_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def instalar(iid: str, entry: dict, apply: bool, root: Path = REPO_ROOT) -> int:
    lista = pasos(iid, entry)
    if not lista:
        print(f"{iid}: no instala nada (lo trae Hermes).")
        return 0
    faltan_sistema = []
    for p in lista:
        print(f"  {'✓' if p['listo'] else '·'} {p['que']}")
        if p["argv"] is None and not p["listo"]:
            faltan_sistema.append(p)
    if faltan_sistema:
        print("\nFalta software del sistema. Lo instala el humano (el arnés no usa sudo):")
        for p in faltan_sistema:
            print(f"  {p['hint'] or p['que']}")
        return 1
    if not apply:
        print("\nDRY-RUN — nada se instaló. Repetí con --apply.")
        return 0
    for p in lista:
        if p["listo"] or p["argv"] is None:
            continue
        prefijo_de(iid, entry).mkdir(parents=True, exist_ok=True)
        for argv in [p["argv"]] + ([p["luego"]] if p.get("luego") else []):
            print("$ " + " ".join(argv), flush=True)
            r = subprocess.run(argv, env={**os.environ, **(p.get("env") or {})})
            if r.returncode != 0:
                print(f"✗ falló ({r.returncode}). Nada se escribió en el lock.")
                return 1
    lock = leer_lock(root)
    lock[iid] = {"version": entry.get("version"), "requires": integridad(iid, entry)}
    escribir_lock(root, lock)
    print(f"✓ {iid} instalada en {prefijo_de(iid, entry)}\n  lock: {LOCK_REL} (commitealo: el equipo instala lo mismo)")
    return 0


def problemas_de_lock(config: dict, root: Path = REPO_ROOT) -> list[str]:
    """Lo que el lock tiene que decir de cada integración habilitada que instala algo: la misma
    versión que el config. Un lock viejo es un `deps` que nadie volvió a correr."""
    lock = leer_lock(root)
    out = []
    for iid, entry in nucleo.habilitadas(config).items():
        pide = {(r["package"], str(r["version"])) for r in entry.get("requires") or [] if r.get("kind") in ("npm", "pypi")}
        if not pide:
            continue
        tiene = {(r.get("package"), str(r.get("version"))) for r in (lock.get(iid) or {}).get("requires") or []}
        if iid not in lock:
            out.append(f"{iid}: no está en {LOCK_REL} — `integ.py deps {iid} --apply`")
        elif pide != tiene:
            out.append(f"{iid}: el lock dice {sorted(tiene)} y el config pide {sorted(pide)} — `integ.py deps {iid} --apply`")
        elif any(not r.get("integrity") for r in lock[iid].get("requires") or []):
            out.append(f"{iid}: el lock no tiene el hash de lo instalado")
    for iid in lock:
        if iid not in nucleo.habilitadas(config):
            out.append(f"{iid}: está en el lock y no está habilitada (sacala del lock o habilitala)")
    return out


# ── Hermes ───────────────────────────────────────────────────────────────────

def incluidas(entry: dict) -> list[str]:
    """Las herramientas crudas que el perfil deja usar: lo que Hermes registra (`tools.include`).
    Lo que el perfil veda ni siquiera llega al prompt: menos esquemas, menos tokens en cada turno."""
    return [t for t in entry.get("toolNames") or [] if nucleo.accion(entry, nucleo.clase(entry, t)) != "deny"]


def servidor_hermes(iid: str, entry: dict, root: Path = REPO_ROOT) -> dict:
    """La entrada `mcp_servers.<server>` de Hermes (claves verificadas en tools/mcp_tool_*.py):
    el servidor lo arranca el LANZADOR (`integ_run.py`: secretos y límites), `lazy` lo conecta
    recién al primer uso, `idle_timeout_seconds` lo apaga cuando no se usa y `tools.include` deja
    afuera lo que el perfil veda."""
    b = entry.get("budget") or {}
    srv = {"command": "python3", "args": [(HERE / "integ_run.py").resolve().as_posix(), iid, "--repo", root.resolve().as_posix()],
           "lazy": True}
    if b.get("idleMinutes"):
        srv["idle_timeout_seconds"] = int(b["idleMinutes"]) * 60
    if b.get("timeoutSeconds"):
        srv["timeout"] = int(b["timeoutSeconds"])
    inc = incluidas(entry)
    if inc:
        srv["tools"] = {"include": inc, "resources": False, "prompts": False}
    srv.update((entry.get("hermes") or {}).get("mcpServer") or {})
    return srv


def bloque_hermes(iid: str, entry: dict, root: Path = REPO_ROOT) -> str:
    """El bloque YAML para `~/.hermes/config.yaml`. Se imprime, no se escribe: el config de Hermes es
    del humano (y el arnés no trae un parser de YAML, ADR 0002)."""
    if entry.get("kind") != "mcp":
        return ""
    lineas = ["mcp_servers:", f"  {entry['server']}:"]
    for k, v in servidor_hermes(iid, entry, root).items():
        if isinstance(v, dict):
            lineas.append(f"    {k}:")
            lineas += [f"      {kk}: {json.dumps(vv, ensure_ascii=False)}" for kk, vv in v.items()]
        else:
            lineas.append(f"    {k}: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lineas)


# ── comandos ─────────────────────────────────────────────────────────────────

def leer_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def escribir_config(nuevo: dict, apply: bool, que: str) -> int:
    if not apply:
        print(f"DRY-RUN — {que}. Nada se escribió: repetí con --apply.")
        return 0
    CONFIG_PATH.write_text(json.dumps(nuevo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✓ {que}\n  {CONFIG_PATH}")
    return 0


def _valor(texto: str):
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def cmd_list(config: dict) -> int:
    en = nucleo.habilitadas(config)
    lock = leer_lock()
    print(f"{'integración':<20} {'tipo':<7} {'estado':<26} título")
    for iid, m in catalogo().items():
        if m.get("_error"):
            print(f"{iid:<20} {'?':<7} {'✗ manifiesto roto':<26} {m['_error']}")
            continue
        if iid in en:
            listo = all(p["listo"] for p in pasos(iid, en[iid]))
            estado = f"✓ {en[iid].get('perfil')}" + ("" if listo else " · sin instalar") + ("" if iid in lock or not en[iid].get("requires") else " · sin lock")
        else:
            estado = "·"
        print(f"{iid:<20} {m.get('kind', '?'):<7} {estado:<26} {m.get('titulo', '')}")
    print("\nDetalle: integ.py show <id> · habilitar: integ.py add <id> --perfil <p>")
    return 0


def cmd_show(iid: str) -> int:
    m = catalogo().get(iid)
    if not m:
        print(f"no hay `{iid}` en el catálogo ({CATALOGO})")
        return 1
    print(f"{iid} — {m.get('titulo')}\n{m.get('descripcion')}\nverificado: {m.get('verificado')}\n")
    for nombre, acciones in (m.get("perfiles") or {}).items():
        marca = " (por defecto)" if nombre == m.get("perfilPorDefecto") else ""
        print(f"  perfil {nombre:<10}{marca} " + " · ".join(f"{c}: {a}" for c, a in acciones.items()))
    sec = {k: v for k, v in ((m.get("launch") or {}).get("env") or {}).items() if isinstance(v, str) and v.startswith("secret://")}
    if sec:
        print("\nSecretos (referencias, nunca valores):")
        for k, v in sec.items():
            print(f"  {k} ← {v}")
    for paso in m.get("setup") or []:
        print(f"  · {paso}")
    return 0


def cmd_add(config: dict, args: list[str]) -> int:
    iid = args[0]
    m = catalogo().get(iid)
    if not m:
        print(f"no hay `{iid}` en el catálogo. Mirá `integ.py list`.")
        return 1
    forma = problemas_de_manifiesto(m)
    if forma:
        print("✗ el manifiesto no es válido:\n  - " + "\n  - ".join(forma))
        return 1
    perfil = args[args.index("--perfil") + 1] if "--perfil" in args else None
    sets = []
    for i, a in enumerate(args):
        if a == "--set" and i + 1 < len(args) and "=" in args[i + 1]:
            ruta, valor = args[i + 1].split("=", 1)
            sets.append((ruta, _valor(valor)))
    try:
        entry = materializar(m, perfil, sets)
    except (ValueError, KeyError, TypeError) as e:
        print(f"✗ {e}")
        return 1
    nuevo = con(config, iid, entry)
    problemas = probar(nuevo, iid)
    print(f"{iid} · perfil {entry['perfil']}: " + " · ".join(f"{c} {a}" for c, a in entry["actions"].items()))
    if problemas:
        print("✗ la integración no entra:\n  - " + "\n  - ".join(problemas))
        return 1
    print("✓ cada ejemplo frena y lo frena esta integración; los inocentes pasan; el config pasa el lint.")
    rc = escribir_config(nuevo, "--apply" in args, f"habilitar `{iid}` ({entry['perfil']})")
    pend = [p for p in pasos(iid, entry) if not p["listo"]]
    print("\nSiguiente:")
    if pend:
        print(f"  1. python3 {_rel(HERE / 'integ.py')} deps {iid} --apply      # instala aislado y escribe el lock")
    if entry.get("kind") == "mcp":
        print("  2. en el config de Hermes (~/.hermes/config.yaml), el servidor lo arranca el lanzador:\n"
              + "\n".join("     " + x for x in bloque_hermes(iid, entry).splitlines()))
    for paso in m.get("setup") or []:
        print(f"  · {paso}")
    print(f"  · python3 {_rel(HERE / 'integ_run.py')} --probe {iid}   # ¿el servidor publica lo que el manifiesto declara?")
    return rc


def cmd_set(config: dict, args: list[str]) -> int:
    resto = [a for a in args if a != "--apply"]
    if len(resto) != 3:
        print("uso: integ.py set <id> <ruta> <valor> [--apply]")
        return 1
    iid, ruta, valor = resto[0], resto[1], _valor(resto[2])
    entry = nucleo.habilitadas(config).get(iid)
    if entry is None:
        print(f"`{iid}` no está habilitada.")
        return 1
    if ruta == "perfil":
        m = catalogo().get(iid) or {}
        if valor not in (m.get("perfiles") or {}):
            print(f"perfiles de {iid}: {', '.join(m.get('perfiles') or {})}")
            return 1
        entry = {**entry, "perfil": valor, "actions": dict(m["perfiles"][valor])}
    else:
        entry = set_ruta(entry, ruta, valor)
    nuevo = con(config, iid, entry)
    problemas = probar(nuevo, iid)
    if problemas:
        print("✗ no entra:\n  - " + "\n  - ".join(problemas))
        return 1
    return escribir_config(nuevo, "--apply" in args, f"`{iid}.{ruta}` = {json.dumps(valor, ensure_ascii=False)}")


def cmd_test(config: dict, args: list[str]) -> int:
    if len(args) < 2:
        print("uso: integ.py test <id> <herramienta|comando> ['{\"args\": …, \"contaminada\": true}']")
        return 1
    iid, que = args[0], args[1]
    entry = nucleo.habilitadas(config).get(iid)
    if entry is None:
        m = catalogo().get(iid)
        if not m:
            print(f"no hay `{iid}`")
            return 1
        entry = materializar(m)
        config = con(config, iid, entry)
        print(f"(`{iid}` no está habilitada: se prueba con el perfil {entry['perfil']})")
    extra = _valor(args[2]) if len(args) > 2 else {}
    ej = {"tool": que, "command": que, "args": (extra or {}).get("args") or {}, "contaminada": (extra or {}).get("contaminada"),
          "uso": (extra or {}).get("uso")}
    d = guards.evaluate(evento(config, iid, entry, ej), config, REPO_ROOT)
    if not (d.block or d.approve):
        print("pasa")
        return 0
    print(f"{'BLOQUEA' if d.block else 'ESCALA A UN HUMANO'} — `{(d.rule or {}).get('id')}`\n{d.message}")
    return 0


def cmd_check(config: dict) -> int:
    """La señal del gate. Sin red ni máquina: el catálogo, las integraciones del config y el lock."""
    errores = validar_catalogo(config)
    for iid in nucleo.habilitadas(config):
        errores += [f"{iid} (habilitada): {e}" for e in probar(config, iid)]
    errores += problemas_de_lock(config)
    n = len(catalogo())
    if errores:
        print("✗ integraciones:\n  - " + "\n  - ".join(errores))
        return 1
    print(f"✓ integraciones: {n} manifiestos del catálogo probados con cada perfil · "
          f"{len(nucleo.habilitadas(config))} habilitadas · lock al día")
    return 0


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(p)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if argv else 1
    cmd, resto = argv[0], argv[1:]
    if cmd == "show" and resto:
        return cmd_show(resto[0])
    if not CONFIG_PATH.is_file():
        print(f"integ: no hay {CONFIG_PATH}.")
        return 1
    config = leer_config()
    if cmd == "list":
        return cmd_list(config)
    if cmd == "check":
        return cmd_check(config)
    if cmd == "add" and resto:
        return cmd_add(config, resto)
    if cmd == "set":
        return cmd_set(config, resto)
    if cmd == "test":
        return cmd_test(config, resto)
    if cmd == "rm" and resto:
        if resto[0] not in nucleo.habilitadas(config):
            print(f"`{resto[0]}` no está habilitada.")
            return 1
        return escribir_config(con(config, resto[0], None), "--apply" in resto, f"deshabilitar `{resto[0]}`")
    if cmd in ("deps", "hermes") and resto:
        entry = nucleo.habilitadas(config).get(resto[0])
        if entry is None:
            print(f"`{resto[0]}` no está habilitada: primero `integ.py add {resto[0]}`.")
            return 1
        if cmd == "hermes":
            print(bloque_hermes(resto[0], entry) or f"`{resto[0]}` no es un MCP: la trae Hermes.")
            return 0
        return instalar(resto[0], entry, "--apply" in resto)
    print(__doc__)
    return 1


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
