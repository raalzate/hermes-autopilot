#!/usr/bin/env python3
"""
El costo del arnés, medido: la latencia de cada callback del plugin contra su presupuesto.

    python3 scripts/timing.py            mide y compara con `observability`
    python3 scripts/timing.py --rules    qué presupuesto rige cada callback

Todo freno se paga en latencia, en CADA tool call y en cada turno. En Hermes además un
`pre_tool_call` que se pasa de tiempo BLOQUEA la herramienta (P5): un freno lento no es un
freno caro, es uno que frena todo. «Los frenos no lanzan procesos» se defendía con una
intuición; esto la vuelve un número que falla.

Los presupuestos son holgados a propósito: los callbacks puros miden fracciones de milisegundo,
y un runner de CI cargado mide más. Lo que esto caza no son milisegundos, es el orden de
magnitud — el día que alguien meta un `subprocess` o un typecheck dentro de un freno.

Se mide contra una COPIA del config en un directorio temporal (`HARNESS_REPO`): los callbacks
escriben estado (el marcador del gate) y medirlos sobre el repo real dejaría el turno siguiente
bloqueado por una medición (P7).
"""
from __future__ import annotations

import atexit
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
from harness.core import HARNESS_HOME, REPO_ROOT, CONFIG_PATH  # noqa: E402


def cargar_plugin():
    """Como lo carga Hermes: paquete con `__path__` propio, desde una copia (ver selftest.py)."""
    tmp = tempfile.mkdtemp(prefix="repo-harness-timing-")
    atexit.register(shutil.rmtree, tmp, True)
    copia = Path(tmp) / "repo-harness"
    shutil.copytree(HARNESS_HOME / "plugin", copia, ignore=shutil.ignore_patterns("__pycache__"))
    padre = "hermes_plugins_timing"
    if padre not in sys.modules:
        ns = types.ModuleType(padre)
        ns.__path__ = []
        sys.modules[padre] = ns
    nombre = f"{padre}.repo_harness"
    spec = importlib.util.spec_from_file_location(nombre, copia / "__init__.py", submodule_search_locations=[str(copia)])
    mod = importlib.util.module_from_spec(spec)
    mod.__package__, mod.__path__ = nombre, [str(copia)]
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


def llamadas(plugin, config: dict) -> dict:
    """Un caso por callback, armado desde `observability.probe` y `tools`: ninguna clave nombra
    una herramienta de Hermes (P4)."""
    probe = (config.get("observability") or {}).get("probe") or {}
    tools = config.get("tools") or {}
    shell = (tools.get("shell") or ["terminal"])[0]
    write = (tools.get("write") or ["write_file"])[0]
    archivo = probe.get("filePath", "x.py")
    escribir = {"path": archivo, "content": probe.get("content", "x = 1\n")}
    return {
        "pre_tool_call (terminal)": lambda: plugin.on_pre_tool_call(tool_name=shell, args={"command": probe.get("command", "git status")}),
        "pre_tool_call (escritura)": lambda: plugin.on_pre_tool_call(tool_name=write, args=escribir),
        "transform_tool_result": lambda: plugin.on_transform_tool_result(tool_name=write, args=escribir, result="ok"),
        "pre_verify": lambda: plugin.on_pre_verify(),
        "pre_llm_call": lambda: plugin.on_pre_llm_call(user_message=probe.get("prompt", "¿cómo está el arnés?")),
        "sección de estado": lambda: plugin._seccion_estado({}),
    }


def presupuesto(obs: dict, nombre: str) -> float:
    return float((obs.get("budgets") or {}).get(nombre, obs.get("budgetMs", 50)))


def medir(config: dict, raiz: Path) -> list[tuple[str, float, float]]:
    """[(callback, mediana en ms, presupuesto en ms)], contra `raiz` (un repo de prueba)."""
    obs = config.get("observability") or {}
    corridas = max(1, int(obs.get("runs", 20)))
    anterior = os.environ.get("HARNESS_REPO")
    os.environ["HARNESS_REPO"] = str(raiz)
    try:
        plugin = cargar_plugin()
        out = []
        for nombre, fn in llamadas(plugin, config).items():
            fn()  # la primera paga imports y cachés: no es la que se repite en cada turno
            tope = presupuesto(obs, nombre)
            mejor = float("inf")
            # Hasta 3 rondas, y vale la MENOR mediana: el ruido de un runner cargado sólo suma
            # tiempo (lo cazó CI: 99 ms una vez en ubuntu), y un subprocess metido en un freno es
            # lento en las tres. Si la primera entra en el presupuesto, no se repite.
            for _ronda in range(3):
                tiempos = []
                for _ in range(corridas):
                    t0 = time.perf_counter()
                    fn()
                    tiempos.append((time.perf_counter() - t0) * 1000)
                mejor = min(mejor, statistics.median(tiempos))
                if mejor <= tope:
                    break
            out.append((nombre, mejor, tope))
        return out
    finally:
        if anterior is None:
            os.environ.pop("HARNESS_REPO", None)
        else:
            os.environ["HARNESS_REPO"] = anterior


def repo_de_prueba(config: dict) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="repo-harness-timing-repo-"))
    atexit.register(shutil.rmtree, tmp, True)
    subprocess.run(["git", "init", "-q"], cwd=tmp, capture_output=True)
    (tmp / ".hermes").mkdir()
    (tmp / ".hermes" / "harness.config.json").write_text(json.dumps(config), encoding="utf-8")
    status = (config.get("status") or {}).get("file")
    if status and (REPO_ROOT / status).is_file():
        shutil.copy(REPO_ROOT / status, tmp / status)
    return tmp


def main(argv: list[str]) -> int:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"timing: no se puede leer el config: {e}")
        return 1
    obs = config.get("observability")
    if not obs:
        print("timing: OMITIDO — el repo no declara `observability`.")
        return 0
    if "--rules" in argv:
        print(f"Presupuesto base: {obs.get('budgetMs', 50)} ms · {obs.get('runs', 20)} corrida(s) por callback (mediana)")
        for k, v in (obs.get("budgets") or {}).items():
            if not k.startswith("$"):
                print(f"  {k}: {v} ms")
        return 0
    resultados = medir(config, repo_de_prueba(config))
    pasados = [(n, ms, b) for n, ms, b in resultados if ms > b]
    for n, ms, b in resultados:
        print(f"  {'✗' if ms > b else '✓'} {n:<28} {ms:8.3f} ms   (presupuesto {b:g} ms)")
    if pasados:
        print(f"\ntiming: {len(pasados)} callback(s) sobre su presupuesto. {obs.get('reason', '')}".rstrip())
        return 1
    print("\ntiming: cada callback entra en su presupuesto.")
    return 0


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
