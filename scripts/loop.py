#!/usr/bin/env python3
"""
El loop autónomo: tarea → agente → gate → verde, o reintento con el rojo en la mano, hasta un tope.

    python3 scripts/loop.py                     DRY-RUN: qué tarea sigue, con qué prompt y qué comandos
    python3 scripts/loop.py --apply             corre UNA tarea hasta verde o hasta escalar
    python3 scripts/loop.py --apply --all       sigue con la próxima mientras salgan verdes
    python3 scripts/loop.py --task "texto"      una tarea suelta, sin la lista
    python3 scripts/loop.py --stop              pide parar: el loop lo lee entre iteraciones
    python3 scripts/loop.py --status            dónde está el loop (lo mismo que ve el panel)

El arnés gobierna el TURNO (frenos, lint, gate pendiente al cerrar). Este script gobierna el
TRABAJO: toma la próxima tarea de `loop.tasksFile`, se la da al agente (`loop.agentCommand`,
Hermes no interactivo), corre el gate y decide. La salida del loop es el gate, no lo que el
agente dice de sí mismo.

Lo que lo hace un loop y no un `while true` (docs/ingenieria-de-loops.md):
  - salida verificable: verde = `loop.gateCommand` sale 0;
  - retroalimentación: el reintento lleva las señales rojas y la cola de la salida del gate;
  - P16 hecho mecanismo: el MISMO rojo `sameFailureLimit` veces seguidas para y escala. Reintentar
    sin hipótesis nueva es el bucle que la constitución prohíbe;
  - topes: `maxIterations` por tarea y `maxMinutes` de reloj;
  - freno de mano: `loop.stopFile` existe → para entre iteraciones, sin matar al agente a mitad;
  - nunca publica (P13): no empuja ni abre PR. Lo verde queda en una rama `branchPrefix*` y el
    humano decide. Si arranca en una rama de `branches.protected`, abre una rama nueva primero;
  - intocables: entre el antes y el después de cada intento compara lo que el agente no puede
    cambiar —los `protectedPaths` versionados y `loop.lockedPaths` (su config, su cola, su
    verificador)—, sin importar por qué canal lo cambió. Cambió → escala aunque el gate dé verde:
    un verde conseguido ablandando el criterio de salida no es verde (P8);
  - un loop por repo: `.git/harness-loop.lock` (dos loops se pisan el estado y la rama).

Todo lo que hace queda en `loop.stateFile` y en el registro de eventos: el panel lo muestra en vivo.

Exit: 0 verde (o nada que hacer) · 2 escaló a un humano o se pidió parar · 1 error de uso o de config.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from harness import events  # noqa: E402
from harness.core import CONFIG_PATH, REPO_ROOT, git_dir  # noqa: E402
from harness.turn import branch_of  # noqa: E402

PENDIENTE = re.compile(r"^(\s*[-*]\s+)\[ \]\s+(.+?)\s*$")


# ── decisiones puras: el self-test las llama directo ─────────────────────────

def firma(salida: str) -> str:
    """Qué falló, sin lo que cambia entre corridas (duraciones, números de línea).

    Del gate: los nombres de las señales `✗`. De otro comando: la última línea no vacía.
    Dos rojos con la misma firma son el mismo error, aunque el texto exacto difiera.
    """
    rojas = sorted({m.group(1).strip() for m in re.finditer(r"^✗\s+(.+?)(?:\s+\(exit\b.*|:\s.*)?$", salida, re.M)})
    if rojas:
        return " · ".join(rojas)
    ultima = next((l for l in reversed(salida.strip().splitlines()) if l.strip()), "")
    return re.sub(r"\d+(\.\d+)?", "#", ultima.strip())[:200] or "(sin salida)"


def decidir(intentos: list[dict], spec: dict, transcurrido_s: float, parar: bool) -> tuple[str, str]:
    """('verde' | 'seguir' | 'escalar' | 'parado', motivo) después de cada intento."""
    if intentos and intentos[-1].get("tampered"):
        return "escalar", ("el agente cambió lo que no puede tocar durante la tarea: "
                           f"{', '.join(intentos[-1]['tampered'][:5])}. Aunque el gate diera verde, no vale (P8). Lo mira un humano.")
    if intentos and intentos[-1].get("green"):
        return "verde", f"gate verde en el intento {len(intentos)}"
    if parar:
        return "parado", "se pidió parar (existe `loop.stopFile`)"
    limite = int(spec.get("sameFailureLimit", 2))
    firmas = [i.get("signature") for i in intentos]
    if limite > 0 and len(firmas) >= limite and len(set(firmas[-limite:])) == 1:
        return "escalar", (f"el mismo rojo {limite} veces seguidas ({firmas[-1]}): reintentar sin hipótesis "
                           "nueva es el bucle que P16 prohíbe. Lo mira un humano.")
    tope = int(spec.get("maxIterations", 4))
    if len(intentos) >= tope:
        return "escalar", f"{tope} intentos sin verde (`loop.maxIterations`)"
    minutos = float(spec.get("maxMinutes", 60))
    if transcurrido_s > minutos * 60:
        return "escalar", f"pasaron más de {minutos:g} minutos (`loop.maxMinutes`)"
    return "seguir", ""


def proxima_tarea(texto: str) -> tuple[int, str] | None:
    """(índice de línea, tarea) de la primera casilla `- [ ]` de la lista."""
    for i, linea in enumerate(texto.splitlines()):
        m = PENDIENTE.match(linea)
        if m:
            return i, m.group(2)
    return None


def marcar(texto: str, indice: int, marca: str, nota: str = "") -> str:
    """`- [ ] x` → `- [x] x` (verde) o `- [!] x — motivo` (escalada). El resto queda igual."""
    lineas = texto.splitlines(keepends=True)
    fin = "\n" if lineas[indice].endswith("\n") else ""
    m = PENDIENTE.match(lineas[indice].rstrip("\n"))
    if m:
        lineas[indice] = f"{m.group(1)}[{marca}] {m.group(2)}{f' — {nota}' if nota else ''}{fin}"
    return "".join(lineas)


def armar_prompt(spec: dict, tarea: str, intentos: list[dict], gate_cmd: str) -> str:
    if not intentos:
        plantilla = spec.get("prompt") or "{task}\n\nTerminado = `{gate}` verde."
        return plantilla.format(task=tarea, gate=gate_cmd)
    ult = intentos[-1]
    plantilla = spec.get("retryPrompt") or "{task}\n\nEl gate salió rojo ({failures}):\n{gate_tail}"
    return plantilla.format(task=tarea, gate=gate_cmd, failures=ult.get("signature", "?"),
                            gate_tail=ult.get("tail", ""), attempt=len(intentos) + 1)


def slug(texto: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")
    return s[:40].rstrip("-") or "tarea"


# ── plomería ──────────────────────────────────────────────────────────────────

def ruta_estado(root: Path, rel: str) -> Path | None:
    """`.git/x` contra el gitdir real (en un worktree `.git` es un archivo)."""
    if rel.startswith(".git/"):
        g = git_dir(root)
        return (g / rel[len(".git/"):]) if g is not None else None
    return root / rel


def leer_estado(spec: dict, root: Path) -> dict:
    p = ruta_estado(root, spec.get("stateFile", ".git/harness-loop.json"))
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p and p.is_file() else {}
    except (OSError, ValueError):
        return {}


def guardar_estado(spec: dict, root: Path, estado: dict) -> None:
    p = ruta_estado(root, spec.get("stateFile", ".git/harness-loop.json"))
    if p is None:
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(estado, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def argv_de(plantilla: list, prompt: str = "") -> list[str]:
    """`{prompt}` se reemplaza dentro de cada argumento: sin shell, nada se interpola (como el gate)."""
    argv = [str(a).replace("{prompt}", prompt) for a in plantilla]
    if argv and argv[0] in ("python3", "python"):
        argv[0] = sys.executable  # en Windows `python3` suele no existir (ver gate.py)
    return argv


def correr(argv: list[str], root: Path, timeout_s: float) -> tuple[int, str]:
    """stdin cerrado: en el loop no hay humano. Un `pdb` o una aprobación interactiva reciben EOF y
    terminan, en vez de esperar una terminal hasta el timeout (lo desatendido se decide al crearlo, P13)."""
    try:
        p = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout_s, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        salida = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return 124, salida + f"\n✗ timeout: pasaron {timeout_s:.0f}s"
    except OSError as e:
        return 127, f"✗ no se pudo ejecutar `{argv[0]}`: {e}"


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")


def cola(texto: str, lineas: int = 40, chars: int = 4000) -> str:
    return "\n".join(texto.strip().splitlines()[-lineas:])[-chars:]


def _ls(root: Path, *args: str) -> list[str]:
    p = subprocess.run(["git", "ls-files", "-z", *args], cwd=root, capture_output=True)
    return [f for f in p.stdout.decode("utf-8", "replace").split("\0") if f and not f.endswith("/")] if p.returncode == 0 else []


def intocables(config: dict, root: Path) -> dict[str, str]:
    """{ruta: hash} de lo que el agente no puede cambiar durante una tarea.

    - los archivos VERSIONADOS que casan con `protectedPaths` del repo (no los de fuera del repo);
    - los que casan con `loop.lockedPaths`, versionados o no, incluso ignorados (un `.env`).
    Lo regenerable sin versionar (`__pycache__/`, `node_modules/`) no se mira: cambia solo.
    """
    def rx(lista):
        out = []
        for p in lista:
            try:
                out.append(re.compile(p))
            except (re.error, TypeError):
                continue
        return out

    protegidas = rx([r.get("pattern") for r in config.get("protectedPaths") or [] if not r.get("outsideRepo")])
    trabadas = rx((config.get("loop") or {}).get("lockedPaths") or [])
    versionados = _ls(root, "-c")
    candidatos = {f for f in versionados if any(r.search(f) for r in protegidas + trabadas)}
    if trabadas:
        sueltos = _ls(root, "-o", "--exclude-standard") + _ls(root, "-o", "-i", "--exclude-standard", "--directory")
        candidatos |= {f for f in sueltos if any(r.search(f) for r in trabadas)}
    huellas = {}
    for f in sorted(candidatos):
        try:
            huellas[f] = hashlib.sha256((root / f).read_bytes()).hexdigest()
        except OSError:
            huellas[f] = ""  # no existe (o no se lee): que aparezca después también es un cambio
    return huellas


def cambiaron(antes: dict[str, str], despues: dict[str, str]) -> list[str]:
    return sorted(f for f in set(antes) | set(despues) if antes.get(f) != despues.get(f))


# ── el loop ───────────────────────────────────────────────────────────────────

def una_tarea(config: dict, root: Path, tarea: str, quiet: bool = False) -> tuple[str, str, list[dict]]:
    """Corre UNA tarea hasta verde, escalar o parar. Devuelve (resultado, motivo, intentos)."""
    spec = config.get("loop") or {}
    gate_argv = spec.get("gateCommand") or ["python3", "scripts/gate.py"]
    gate_txt = " ".join(gate_argv)
    stop = ruta_estado(root, spec.get("stopFile", ".git/harness-loop.stop"))
    intentos: list[dict] = []
    inicio = time.time()
    estado = {"task": tarea, "phase": "inicio", "startedAt": inicio, "attempts": intentos, "reason": ""}
    events.record(config, root, "loop-start", task=tarea)
    log = (lambda *_: None) if quiet else (lambda m: print(m, flush=True))

    while True:
        n = len(intentos) + 1
        prompt = armar_prompt(spec, tarea, intentos, gate_txt)
        estado.update(phase="agente", iteration=n)
        guardar_estado(spec, root, estado)
        log(f"\n▶ intento {n}: agente")
        t0 = time.time()
        antes = intocables(config, root)
        rc_agente, salida_agente = correr(argv_de(spec.get("agentCommand") or [], prompt), root,
                                          float(spec.get("agentTimeoutMinutes", 30)) * 60)
        log(cola(salida_agente, 15, 1500))
        tocados = cambiaron(antes, intocables(config, root))
        if tocados:
            # Ni se corre el gate: lo que decide si terminó puede ser justo lo que se cambió.
            intento = {"n": n, "green": False, "agentExit": rc_agente, "gateExit": None, "tampered": tocados,
                       "signature": "intocables: " + " · ".join(tocados[:5]), "tail": "", "secs": round(time.time() - t0, 1)}
        else:
            estado.update(phase="gate")
            guardar_estado(spec, root, estado)
            log(f"▶ intento {n}: gate (`{gate_txt}`)")
            rc_gate, salida_gate = correr(argv_de(gate_argv), root, float(spec.get("gateTimeoutMinutes", 30)) * 60)
            intento = {"n": n, "green": rc_gate == 0, "agentExit": rc_agente, "gateExit": rc_gate,
                       "signature": "" if rc_gate == 0 else firma(salida_gate), "tail": "" if rc_gate == 0 else cola(salida_gate),
                       "secs": round(time.time() - t0, 1)}
        intentos.append(intento)
        events.record(config, root, "loop-iter", task=tarea, n=n, green=intento["green"], signature=intento["signature"])
        log(f"{'✓' if intento['green'] else '✗'} intento {n}: {'verde' if intento['green'] else intento['signature']}")

        resultado, motivo = decidir(intentos, spec, time.time() - inicio, bool(stop and stop.exists()))
        if resultado == "parado" and stop is not None:
            try:
                stop.unlink()  # pedido cumplido: si quedara, el panel diría «parada pedida» para siempre
            except OSError:
                pass
        if resultado != "seguir":
            estado.update(phase=resultado, reason=motivo, endedAt=time.time())
            guardar_estado(spec, root, estado)
            events.record(config, root, f"loop-{resultado}", task=tarea, reason=motivo, attempts=len(intentos))
            return resultado, motivo, intentos


def asegurar_rama(config: dict, root: Path, tarea: str) -> str:
    """El loop no trabaja sobre una rama protegida: abre `branchPrefix<slug>` antes de tocar nada."""
    rama = branch_of(root)
    protegidas = (config.get("branches") or {}).get("protected") or []
    if rama not in protegidas:
        return rama
    nueva = f"{(config.get('loop') or {}).get('branchPrefix', 'loop/')}{slug(tarea)}"
    p = git(root, "checkout", "-b", nueva)
    if p.returncode != 0:
        p = git(root, "checkout", nueva)
    return nueva if p.returncode == 0 else rama


def plan(config: dict, root: Path, tarea: str | None) -> str:
    spec = config.get("loop") or {}
    rama = branch_of(root)
    protegidas = (config.get("branches") or {}).get("protected") or []
    gate_argv = spec.get("gateCommand") or ["python3", "scripts/gate.py"]
    lineas = [f"DRY-RUN del loop (nada se ejecuta; --apply para correr) en {root}", ""]
    if not tarea:
        return "\n".join(lineas + ["Nada que hacer: no hay casillas `- [ ]` en "
                                   f"`{spec.get('tasksFile', '.hermes/loop/tasks.md')}` (ni --task)."])
    lineas += [
        f"tarea       {tarea}",
        f"rama        {rama}" + (f"  → protegida: abriría `{spec.get('branchPrefix', 'loop/')}{slug(tarea)}`" if rama in protegidas else ""),
        f"agente      {' '.join(argv_de(spec.get('agentCommand') or [], '<prompt>'))}",
        f"gate        {' '.join(gate_argv)}",
        f"topes       {spec.get('maxIterations', 4)} intentos · el mismo rojo {spec.get('sameFailureLimit', 2)} veces"
        f" escala · {spec.get('maxMinutes', 60)} min",
        f"parar       crear {spec.get('stopFile', '.git/harness-loop.stop')} (o `loop.py --stop`)",
        "", "prompt del primer intento:", "  " + armar_prompt(spec, tarea, [], " ".join(gate_argv)).replace("\n", "\n  "),
    ]
    return "\n".join(lineas)


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Loop autónomo: tarea → agente → gate (dry-run por defecto).")
    ap.add_argument("--apply", action="store_true", help="ejecutar (sin esto, sólo muestra el plan)")
    ap.add_argument("--all", action="store_true", help="seguir con la próxima tarea mientras salgan verdes")
    ap.add_argument("--task", help="una tarea suelta, sin la lista")
    ap.add_argument("--stop", action="store_true", help="pedir que el loop pare entre iteraciones")
    ap.add_argument("--status", action="store_true", help="dónde está el loop")
    a = ap.parse_args(argv)

    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"loop: no pude leer el config ({e}).")
        return 1
    spec = config.get("loop")
    if not isinstance(spec, dict):
        print("loop: el config no declara `loop`: el repo no decidió cómo se trabaja desatendido (P13).")
        return 1
    root = REPO_ROOT
    stop = ruta_estado(root, spec.get("stopFile", ".git/harness-loop.stop"))

    if a.status:
        print(json.dumps(leer_estado(spec, root) or {"phase": "nunca corrió"}, indent=1, ensure_ascii=False))
        return 0
    if a.stop:
        if stop is None:
            print("loop: no hay directorio de git para el stopFile.")
            return 1
        stop.parent.mkdir(parents=True, exist_ok=True)
        stop.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
        print(f"loop: pedido de parada en {stop}. El loop termina la iteración en curso y para.")
        return 0

    tareas = root / spec.get("tasksFile", ".hermes/loop/tasks.md")

    def siguiente():
        if a.task:
            return None, a.task
        try:
            hit = proxima_tarea(tareas.read_text(encoding="utf-8"))
        except OSError:
            return None, None
        return (hit[0], hit[1]) if hit else (None, None)

    indice, tarea = siguiente()
    if not a.apply:
        print(plan(config, root, tarea))
        return 0
    if not tarea:
        print(plan(config, root, None))
        return 0
    agente = argv_de(spec.get("agentCommand") or [])
    if not agente or not (shutil.which(agente[0]) or Path(agente[0]).exists()):
        print(f"loop: `loop.agentCommand` no se puede ejecutar ({agente[:1] or 'vacío'}). ¿Hermes instalado?")
        return 1
    candado = ruta_estado(root, ".git/harness-loop.lock")
    if candado is not None and candado_vivo(candado, spec):
        print(f"loop: ya hay un loop corriendo en este repo ({candado}). Dos loops se pisan el estado y la rama.")
        return 1
    if stop and stop.exists():
        stop.unlink()  # un pedido de parada viejo no frena una corrida nueva
    try:
        if candado is not None:
            candado.write_text(json.dumps({"pid": os.getpid(), "at": time.time()}), encoding="utf-8")
        return correr_tareas(config, root, a, tareas, indice, tarea, siguiente)
    finally:
        if candado is not None:
            try:
                candado.unlink()
            except OSError:
                pass


def candado_vivo(candado: Path, spec: dict) -> bool:
    """¿El candado es de un loop que sigue corriendo? Uno viejo (un loop matado con -9) no traba."""
    try:
        dato = json.loads(candado.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    tope_s = (float(spec.get("maxMinutes", 60)) + float(spec.get("agentTimeoutMinutes", 30))
              + float(spec.get("gateTimeoutMinutes", 30))) * 60
    if time.time() - float(dato.get("at", 0)) > tope_s:
        return False
    if os.name != "nt":  # en Windows os.kill(pid, 0) no pregunta: manda una señal
        try:
            os.kill(int(dato.get("pid", 0)), 0)
        except (OSError, ValueError):
            return False
    return True


def correr_tareas(config, root, a, tareas, indice, tarea, siguiente) -> int:
    codigo = 0
    while tarea:
        rama = asegurar_rama(config, root, tarea)
        print(f"\n━━ tarea: {tarea}  (rama {rama})")
        resultado, motivo, intentos = una_tarea(config, root, tarea)
        print(f"\n{'✓' if resultado == 'verde' else '✗'} {resultado.upper()} — {motivo}")
        if indice is not None and resultado in ("verde", "escalar"):
            try:
                texto = tareas.read_text(encoding="utf-8")
                tareas.write_text(marcar(texto, indice, "x" if resultado == "verde" else "!",
                                         "" if resultado == "verde" else motivo.split(":")[0]), encoding="utf-8")
            except OSError:
                pass
        if resultado != "verde":
            codigo = 2
            break
        if not a.all or a.task:
            break
        indice, tarea = siguiente()
    if codigo == 0:
        print("\nLo verde queda en la rama: el loop no empuja ni abre PR (P13). Revisalo y publicalo vos.")
    return codigo


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
