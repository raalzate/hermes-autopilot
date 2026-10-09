#!/usr/bin/env python3
"""
`integ_run.py` — el lanzador de un servidor MCP de una integración, y su prueba de contrato.

    python3 scripts/integ_run.py <id> [--repo R]       lo que Hermes arranca (`mcp_servers.<server>.command`)
    python3 scripts/integ_run.py --probe <id> [--repo R]     ¿el servidor publica lo que el manifiesto declara?
    python3 scripts/integ_run.py --secretos <id> [--repo R]  ¿se resuelve cada secreto? (nunca imprime un valor)

Hermes arranca el servidor; el arnés decide CON QUÉ. El lanzador:

  - resuelve las referencias `secret://…` de `launch.env` y las pone SÓLO en el entorno del servidor:
    el valor no pasa por el config, ni por el `.env` del repo, ni por el contexto del modelo.
      secret://keychain/<servicio>/<cuenta>   llavero de macOS (`security`)
      secret://keyring/<servicio>/<cuenta>    llavero del sistema (macOS `security`, Linux `secret-tool`)
      secret://op/<bóveda>/<ítem>/<campo>     1Password (`op read`)
      secret://file/<ruta>                    un archivo FUERA del repo (`~/.config/…`)
      secret://env/<NOMBRE>                   una variable que Hermes ya le pasa (`env` del mcp_servers)
  - baja la prioridad (`budget.nice`) y pone techo de memoria (`budget.maxMemoryMB`: el heap de Node,
    o `RLIMIT_AS` para Python): un servidor que se desboca no se lleva la máquina;
  - reemplaza su proceso por el del servidor (`exec`): no queda un intermediario en el medio de cada
    mensaje. Lo perezoso (`lazy`), el apagado por inactividad y el filtro de herramientas los hace
    Hermes con lo que `integ.py hermes <id>` le pone en `mcp_servers`.

Un secreto que no se resuelve corta el arranque con el NOMBRE de la referencia, nunca con un valor.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugin"))
sys.path.append(str(HERE))
from harness import core  # noqa: E402
from harness import integ as nucleo  # noqa: E402


class SinSecreto(Exception):
    pass


def _correr(argv: list[str]) -> str:
    exe = shutil.which(argv[0])
    if not exe:
        raise SinSecreto(f"no está `{argv[0]}`")
    p = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, timeout=30)
    if p.returncode != 0 or not p.stdout.strip():
        raise SinSecreto(f"`{argv[0]}` no lo encontró")
    return p.stdout.rstrip("\n")


def resolver(ref: str, repo: Path) -> str:
    """El valor de una referencia `secret://…`. Lanza SinSecreto con un motivo sin el valor."""
    m = re.match(r"^secret://([a-z]+)/(.+)$", ref)
    if not m:
        return ref
    tipo, resto = m.group(1), m.group(2)
    partes = resto.split("/")
    if tipo in ("keychain", "keyring") and len(partes) >= 2:
        servicio, cuenta = partes[0], "/".join(partes[1:])
        if sys.platform == "darwin":
            return _correr(["security", "find-generic-password", "-s", servicio, "-a", cuenta, "-w"])
        if tipo == "keyring" and sys.platform.startswith("linux"):
            return _correr(["secret-tool", "lookup", "service", servicio, "account", cuenta])
        raise SinSecreto(f"`{tipo}` no está soportado en {sys.platform}: usá secret://op/… o secret://file/…")
    if tipo == "op":
        return _correr(["op", "read", "op://" + resto])
    if tipo == "file":
        # `secret://file/home/u/x` → /home/u/x; `secret://file/~/x`; en Windows `secret://file/C:/x`.
        crudo = resto if resto.startswith("~") or re.match(r"^[A-Za-z]:", resto) else "/" + resto.lstrip("/")
        p = Path(os.path.expanduser(crudo)).resolve()
        try:
            p.relative_to(repo.resolve())
            raise SinSecreto("el archivo está DENTRO del repo: un secreto ahí termina en un commit")
        except ValueError:
            pass
        try:
            return p.read_text(encoding="utf-8").strip()
        except OSError:
            raise SinSecreto("no se puede leer el archivo") from None
    if tipo == "env":
        v = os.environ.get(resto)
        if v is None:
            raise SinSecreto(f"la variable `{resto}` no está en el entorno del servidor (¿falta en `env` de mcp_servers?)")
        return v
    raise SinSecreto(f"tipo `{tipo}` desconocido")


def entrada(iid: str, repo: Path) -> dict:
    config = core.load_config(repo)
    entry = nucleo.habilitadas(config).get(iid) if config else None
    if entry is None:
        raise SystemExit(f"integ_run: `{iid}` no está habilitada en {repo}/.hermes/harness.config.json")
    return entry


def plantilla(texto: str, prefijo: Path) -> str:
    return texto.replace("{prefix}", prefijo.as_posix())


def comando(iid: str, entry: dict, repo: Path) -> tuple[list[str], dict]:
    """(argv, entorno) del servidor, con los secretos resueltos."""
    import integ as cfg  # scripts/integ.py: dónde se instaló

    pre = cfg.prefijo_de(iid, entry)
    la = entry.get("launch") or {}
    b = la.get("bin") or {}
    if b:
        exe = cfg._bin_dir(pre, b.get("kind", "npm")) / (b["name"] + (".cmd" if os.name == "nt" and b.get("kind") == "npm" else ""))
        if not exe.exists():
            raise SystemExit(f"integ_run: falta {exe}. Instalá con `python3 scripts/integ.py deps {iid} --apply`.")
        argv = [str(exe)]
    else:
        argv = [la.get("command") or ""]
    argv += [plantilla(str(a), pre) for a in la.get("args") or []]
    # Lo que el perfil achica en la FUENTE: `--read-only` pide al proveedor sólo los scopes de lectura,
    # así ni un freno roto deja mandar un correo con una credencial que no puede.
    argv += [plantilla(str(a), pre) for a in (la.get("argsPorPerfil") or {}).get(entry.get("perfil"), [])]
    env = dict(os.environ)
    for k, v in (la.get("env") or {}).items():
        try:
            env[k] = resolver(plantilla(str(v), pre), repo)
        except SinSecreto as e:
            raise SystemExit(f"integ_run: el secreto `{k}` ({v}) no se resolvió: {e}") from None
    techo = (entry.get("budget") or {}).get("maxMemoryMB")
    if techo and la.get("runtime") == "node":
        env["NODE_OPTIONS"] = (env.get("NODE_OPTIONS", "") + f" --max-old-space-size={int(techo)}").strip()
    return argv, env


def _limites(entry: dict):
    b = entry.get("budget") or {}
    runtime = (entry.get("launch") or {}).get("runtime")

    def aplicar():
        try:
            if b.get("nice"):
                os.nice(int(b["nice"]))
            if b.get("maxMemoryMB") and runtime == "python":
                import resource
                tope = int(b["maxMemoryMB"]) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (tope, tope))
        except (OSError, ValueError, ImportError):
            pass  # sin límites antes que sin servidor
    return aplicar


def lanzar(iid: str, repo: Path) -> int:
    entry = entrada(iid, repo)
    argv, env = comando(iid, entry, repo)
    if os.name == "nt":
        return subprocess.run(argv, env=env).returncode
    _limites(entry)()
    os.execvpe(argv[0], argv, env)
    return 0  # no se llega


# ── la prueba de contrato ────────────────────────────────────────────────────

def publicadas(argv: list[str], env: dict, timeout: float = 90) -> list[dict]:
    """`initialize` + `tools/list` por stdio (JSON-RPC, una línea por mensaje)."""
    p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, encoding="utf-8", env=env)
    q: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [q.put(x) for x in p.stdout], daemon=True).start()

    def mandar(o):
        p.stdin.write(json.dumps(o) + "\n")
        p.stdin.flush()

    def esperar(i):
        while True:
            try:
                linea = q.get(timeout=timeout)
            except queue.Empty:
                raise SystemExit(f"integ_run: el servidor no contestó en {timeout:.0f}s") from None
            try:
                m = json.loads(linea)
            except ValueError:
                continue
            if m.get("id") == i:
                return m

    try:
        mandar({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "repo-harness-probe", "version": "1"}}})
        esperar(1)
        mandar({"jsonrpc": "2.0", "method": "notifications/initialized"})
        herramientas, cursor = [], None
        for n in range(2, 40):
            mandar({"jsonrpc": "2.0", "id": n, "method": "tools/list", "params": {"cursor": cursor} if cursor else {}})
            r = esperar(n).get("result") or {}
            herramientas += r.get("tools") or []
            cursor = r.get("nextCursor")
            if not cursor:
                break
        return herramientas
    finally:
        p.kill()


def contraste(entry: dict, herramientas: list[dict]) -> tuple[list[str], list[str]]:
    """(errores, avisos) entre lo declarado y lo publicado."""
    declaradas = set(entry.get("toolNames") or [])
    hay = {t.get("name") for t in herramientas}
    errores = [f"el manifiesto declara `{t}` y el servidor no la publica (¿cambió la versión?)" for t in sorted(declaradas - hay)]
    avisos = [f"el servidor publica `{t}` y el manifiesto no la declara: Hermes no la registra (`tools.include`)"
              for t in sorted(hay - declaradas)]
    for t in herramientas:
        if nucleo._rx(entry.get("ignoreAnnotations"), t.get("name", "")):
            continue  # el manifiesto dice por qué no le cree a las anotaciones (`$ignoreAnnotations`)
        a = t.get("annotations") or {}
        c = nucleo.clase(entry, t.get("name", ""))
        if c == "read" and a.get("readOnlyHint") is False and a.get("destructiveHint") is True:
            errores.append(f"`{t['name']}` es `read` para el manifiesto y el servidor la anota destructiva")
        if c == "write" and a.get("destructiveHint") is True and t.get("name") in declaradas:
            avisos.append(f"`{t['name']}` cae en `write` por defecto y el servidor la anota destructiva: ¿va en `classes.destructive`?")
    return errores, avisos


def main(argv: list[str]) -> int:
    repo = Path(argv[argv.index("--repo") + 1]).resolve() if "--repo" in argv else core.repo_root()
    resto = [a for i, a in enumerate(argv) if a != "--repo" and (i == 0 or argv[i - 1] != "--repo")]
    if not resto or resto[0] in ("-h", "--help"):
        print(__doc__)
        return 1
    if resto[0] == "--secretos" and len(resto) > 1:
        entry = entrada(resto[1], repo)
        rojo = 0
        for k, v in ((entry.get("launch") or {}).get("env") or {}).items():
            if isinstance(v, str) and v.startswith("secret://"):
                try:
                    resolver(v, repo)
                    print(f"  ✓ {k} ← {v}")
                except SinSecreto as e:
                    print(f"  ✗ {k} ← {v}: {e}")
                    rojo = 1
        return rojo
    if resto[0] == "--probe" and len(resto) > 1:
        iid = resto[1]
        entry = entrada(iid, repo)
        argv_srv, env = comando(iid, entry, repo)
        herramientas = publicadas(argv_srv, env)
        errores, avisos = contraste(entry, herramientas)
        print(f"{iid}: el servidor publica {len(herramientas)} herramientas; el manifiesto declara "
              f"{len(entry.get('toolNames') or [])}; el perfil `{entry.get('perfil')}` registra {len(_incluidas(entry))}.")
        for a in avisos:
            print(f"  ! {a}")
        for e in errores:
            print(f"  ✗ {e}")
        return 1 if errores else 0
    return lanzar(resto[0], repo)


def _incluidas(entry: dict) -> list[str]:
    return [t for t in entry.get("toolNames") or [] if nucleo.accion(entry, nucleo.clase(entry, t)) != "deny"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
