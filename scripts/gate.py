#!/usr/bin/env python3
"""
El gate: única definición de "entregable".

    python3 scripts/gate.py          todas las señales (entregable)
    python3 scripts/gate.py fast     omite las marcadas `fastSkip` → señal de DESARROLLO

Genérico a propósito: no sabe de stacks ni de repos. Las señales se declaran en
`.hermes/harness.config.json` → `gate.signals` y se ejecutan en orden.

Contrato de cada señal:
    name           lo que se imprime
    command        lista argv (["pytest", "-q"]) — sin shell: nada del config se interpola
    why            qué error atrapa que ninguna otra señal ve (lo exige el self-test, P6)
    fastSkip       true = se omite en modo fast
    skipIfMissing  ruta que, si no existe, hace que la señal salga OMITIDA en vez de fallar.
    skipIfNoExecutable  true = si `command[0]` no está instalado, OMITIDA (p.ej. `hermes` en CI).
                   "Omitido" se imprime SIEMPRE: nunca se confunde con "pasó".

Cuando TODAS las señales pasan en modo completo, borra el marcador `gate.marker`: es lo que
el hook de fin de turno mira para saber si el agente puede decir "listo".
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# El núcleo vive DENTRO del plugin (`plugin/harness/`): Hermes copia el directorio del plugin
# al instalarlo y al validarlo, y lo que quede afuera no viaja (docs/gotchas.md).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from harness.core import REPO_ROOT, CONFIG_PATH, marker_path  # noqa: E402
from harness import events  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "full"


def rojo(msg: str) -> None:
    print(f"GATE ROJO — {msg}")
    sys.exit(1)


def main() -> None:
    # Un gate que no puede leer su config no verifica nada: eso es rojo, no verde.
    # (El fallo abierto es de los HOOKS, que no pueden bloquear al humano; el gate sí.)
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        rojo(f"falta {CONFIG_PATH.relative_to(REPO_ROOT)}: el arnés no está configurado.")
    except (OSError, json.JSONDecodeError) as e:
        rojo(f"config inválido: {CONFIG_PATH.relative_to(REPO_ROOT)} ({e})")

    senales = (config.get("gate") or {}).get("signals") or []
    if not senales:
        rojo("`gate.signals` está vacío: el gate no verifica nada.")

    print(f"Gate (modo: {MODE}) — {REPO_ROOT.name}")
    fallidas, omitidas, corridas = [], [], 0
    resultados = {}

    for senal in senales:
        nombre = senal.get("name", "?")
        argv = senal.get("command")
        if not isinstance(argv, list) or not argv:
            rojo(f"señal sin command: {nombre}")

        if MODE == "fast" and senal.get("fastSkip"):
            print(f"\n· {nombre}: OMITIDA (modo fast)")
            omitidas.append(nombre)
            resultados[nombre] = "omitida"
            continue

        falta = senal.get("skipIfMissing")
        if falta and not (REPO_ROOT / falta).exists():
            print(f"\n· {nombre}: OMITIDA (no existe {falta})")
            omitidas.append(nombre)
            resultados[nombre] = "omitida"
            continue

        # `python3` del config se reemplaza por el intérprete que corre el gate: en Windows
        # `python3` suele no existir (es `py` o `python`), y el entregable no puede depender
        # del nombre del binario.
        argv = [sys.executable if a in ("python3", "python") and i == 0 else a for i, a in enumerate(argv)]
        # `skipIfNoExecutable`: una herramienta de la máquina (Hermes mismo) que en CI no está.
        # `true` mira `command[0]`; un string nombra el ejecutable que decide (la señal puede
        # correr con python3 y necesitar `hermes`). Sin la marca, un ejecutable ausente es ROJO.
        requerido = senal.get("skipIfNoExecutable")
        requerido = argv[0] if requerido is True else requerido
        if isinstance(requerido, str) and requerido and not shutil.which(requerido):
            print(f"\n· {nombre}: OMITIDA (no hay `{requerido}` en esta máquina)")
            omitidas.append(nombre)
            resultados[nombre] = "omitida"
            continue
        if not shutil.which(argv[0]) and not Path(argv[0]).exists():
            print(f"\n✗ {nombre}: no existe el ejecutable `{argv[0]}`")
            fallidas.append(nombre)
            resultados[nombre] = "roja"
            continue

        print(f"\n▶ {nombre}")
        inicio = time.monotonic()
        # PYTHONIOENCODING: una señal en Python que imprime `ñ` o `✓` en una consola cp1252
        # (Windows) revienta por el print, no por lo que verifica. El gate se lo evita a todas.
        proc = subprocess.run(argv, cwd=REPO_ROOT, env={**os.environ, "HARNESS_IN_GATE": "1", "PYTHONIOENCODING": "utf-8"})
        dur = time.monotonic() - inicio
        corridas += 1
        if proc.returncode == 0:
            print(f"✓ {nombre} ({dur:.1f}s)")
            resultados[nombre] = "verde"
        else:
            print(f"✗ {nombre} (exit {proc.returncode}, {dur:.1f}s)")
            fallidas.append(nombre)
            resultados[nombre] = "roja"

    # Lo que corrió en esta máquina: lo lee el mapa del arnés, no se commitea.
    try:
        estado = REPO_ROOT / ".git" / "harness-gate.json"
        estado.write_text(json.dumps({"mode": MODE, "at": time.time(), "signals": resultados}, indent=1))
    except OSError:
        pass
    # Y al registro de eventos: el panel muestra el veredicto apenas sale, no al recargar.
    veredicto = "roja" if fallidas else ("fast" if MODE == "fast" else ("verde-con-omitidas" if omitidas else "verde"))
    events.record(config, REPO_ROOT, "gate", mode=MODE, verdict=veredicto, failed=fallidas, skipped=omitidas)

    print("\n" + "─" * 60)
    if fallidas:
        print(f"GATE ROJO — {len(fallidas)} señal(es) fallida(s): {', '.join(fallidas)}")
        sys.exit(1)
    if MODE == "fast":
        print(f"gate:fast verde ({corridas} corridas, {len(omitidas)} omitidas) — NO es entregable.")
        sys.exit(0)
    if omitidas:
        # Omitido no es verde, pero tampoco es rojo: una señal que depende de la máquina (Hermes
        # instalado) no puede dejar el gate pendiente para siempre donde no existe. El gate lo
        # IMPRIME, y quien entrega lo nombra (P1, skill `gate`).
        print(f"GATE VERDE con {len(omitidas)} OMITIDA(S): {', '.join(omitidas)} — omitido no es verde: nombralas al entregar.")
    else:
        print(f"GATE VERDE — {corridas} señales.")
    # Sólo el gate completo limpia el marcador: gate:fast verde no es entregable (P1). Contra la
    # raíz del REPO, no del cwd: correrlo desde otro directorio dejaba el marcador real puesto.
    marker = marker_path(config, REPO_ROOT)
    if marker and marker.exists():
        marker.unlink()


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    main()
