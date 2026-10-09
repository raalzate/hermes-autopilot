"""
El despacho de herramientas de Hermes, simulado, con el plugin REAL del repo en el medio.

Los agentes de los casos (`casos/*/agente.py`) son deterministas: no hay modelo. Pero cada cosa
que hacen pasa por el mismo camino que una herramienta de Hermes:

    pre_tool_call (el plugin del sandbox, con SUS reglas) — escribir, leer, terminal, memoria, cron
        → block   : la herramienta no corre; el agente recibe el `message` (y lo imprime)
        → approve : en el loop no hay humano que apruebe → se niega (como en cron o el gateway)
        → None    : la herramienta corre
    transform_tool_result (después de escribir): el lint del archivo, pegado al resultado

Así un caso prueba los frenos de punta a punta —quedan en el registro de eventos y en el panel—
sin Hermes instalado y sin API key. Lo que esto NO prueba es cómo reacciona un modelo de verdad
al `message`: eso es lo que se ve corriendo el caso con `--hermes` (casos/README.md).

Portable a propósito: el comando de terminal es lo que evalúa el freno; su EFECTO lo emula el
agente en Python (`efecto=`), así el caso corre igual en Windows, donde `rm` o `cp` no existen.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import types
from pathlib import Path


class Hermes:
    def __init__(self, raiz: Path | None = None):
        self.raiz = (raiz or Path.cwd()).resolve()
        self.config = json.loads((self.raiz / ".hermes" / "harness.config.json").read_text(encoding="utf-8"))
        self.tools = self.config.get("tools") or {}
        self.plugin = self._cargar_plugin()
        self.frenados: list[str] = []

    def _cargar_plugin(self):
        """Como lo carga Hermes: un paquete con `__path__` propio (ver scripts/selftest.py)."""
        d = self.raiz / ".hermes" / "harness" / "plugin"
        padre = "hermes_plugins_sim"
        if padre not in sys.modules:
            ns = types.ModuleType(padre)
            ns.__path__ = []
            sys.modules[padre] = ns
        nombre = f"{padre}.repo_harness"
        spec = importlib.util.spec_from_file_location(nombre, d / "__init__.py", submodule_search_locations=[str(d)])
        mod = importlib.util.module_from_spec(spec)
        mod.__package__, mod.__path__ = nombre, [str(d)]
        sys.modules[nombre] = mod
        spec.loader.exec_module(mod)
        return mod

    def _tool(self, familia: str) -> str:
        return (self.tools.get(familia) or [familia])[0]  # los nombres salen del config (P4)

    def _pedir(self, familia: str, args: dict, tool: str = "") -> bool:
        tool = tool or self._tool(familia)
        r = self.plugin.on_pre_tool_call(tool_name=tool, args=args, session_id="caso")
        if isinstance(r, dict) and r.get("action") == "block":
            self.frenados.append(r.get("message", ""))
            print(f"  [{tool}] ✗ FRENADO\n    " + r.get("message", "").replace("\n", "\n    "))
            return False
        if isinstance(r, dict) and r.get("action") == "approve":
            self.frenados.append(r.get("message", ""))
            print(f"  [{tool}] ✗ pide aprobación humana y en el loop no hay humano: NEGADA\n    {r.get('message', '')}")
            return False
        return True

    # ── herramientas ─────────────────────────────────────────────────────────

    def escribir(self, ruta: str, contenido: str) -> bool:
        args = {"path": ruta, "content": contenido}
        if not self._pedir("write", args):
            return False
        p = self.raiz / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contenido, encoding="utf-8")
        extra = self.plugin.on_transform_tool_result(tool_name=self._tool("write"), args=args, result="ok")
        print(f"  [{self._tool('write')}] ✓ {ruta}" + (f"\n    {extra[3:].strip()}" if isinstance(extra, str) else ""))
        return True

    def terminal(self, comando: str, efecto=None) -> bool:
        """`efecto`: código Python que emula lo que el comando haría (portable: `rm` no existe en
        Windows). Corre en un proceso APARTE y sin la guardia de Python, como correría el binario
        real (`rm` no es Python: la guardia no lo ve; lo ven los frenos de terminal y el loop)."""
        if not self._pedir("shell", {"command": comando}):
            return False
        print(f"  [{self._tool('shell')}] ✓ {comando}")
        if efecto:
            import os
            env = {k: v for k, v in os.environ.items() if k not in ("HARNESS_GUARDIA", "PYTHONPATH")}
            subprocess.run([sys.executable, "-c", efecto], cwd=self.raiz, env=env, stdin=subprocess.DEVNULL)
        return True

    def python(self, codigo: str) -> bool:
        """`python3 -c '…'`: un canal de escritura que el freno de terminal NO ve por dentro."""
        if not self._pedir("shell", {"command": f"python3 -c {codigo!r}"}):
            return False
        print(f"  [{self._tool('shell')}] ✓ python3 -c …")
        import os
        p = subprocess.run([sys.executable, "-c", codigo], cwd=self.raiz, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if p.returncode != 0:
            # Lo que Hermes le devolvería al modelo: la salida del comando, con el error de la guardia.
            ultima = [l for l in (p.stderr or "").splitlines() if l.strip()]
            print("    ✗ el comando falló:\n    " + "\n    ".join(ultima[-2:]))
            return False
        return True

    def codigo(self, codigo: str) -> bool:
        """`execute_code` de Hermes: Python que no pasa por la terminal (y sí por el freno de código)."""
        if not self._pedir("code", {"code": codigo}):
            return False
        print(f"  [{self._tool('code')}] ✓ ejecutado")
        subprocess.run([sys.executable, "-c", codigo], cwd=self.raiz, stdin=subprocess.DEVNULL)
        return True

    def memoria(self, texto: str) -> bool:
        if not self._pedir("memory", {"action": "add", "target": "memory", "content": texto}):
            return False
        sim = self.raiz / ".sim" / "memoria.md"
        sim.parent.mkdir(exist_ok=True)
        with sim.open("a", encoding="utf-8") as f:
            f.write(f"- {texto}\n")
        print(f"  [{self._tool('memory')}] ✓ guardado")
        return True

    def cron(self, cuando: str, prompt: str) -> bool:
        if not self._pedir("cron", {"action": "create", "schedule": cuando, "prompt": prompt}):
            return False
        sim = self.raiz / ".sim" / "cron.json"
        sim.parent.mkdir(exist_ok=True)
        trabajos = json.loads(sim.read_text(encoding="utf-8")) if sim.is_file() else []
        trabajos.append({"schedule": cuando, "prompt": prompt})
        sim.write_text(json.dumps(trabajos, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  [{self._tool('cron')}] ✓ programado: {cuando}")
        return True

    def herramienta(self, nombre: str, args: dict, resultado: str = "ok") -> str | None:
        """Una herramienta de una integración (`mcp__<server>__<tool>` o una propia de Hermes), con el
        nombre con que Hermes la registra. Frenada → None. Lo que hizo queda en `.sim/integraciones.jsonl`
        (el verificador del caso lo lee: lo mandado no se des-manda)."""
        if not self._pedir("", args, tool=nombre):
            return None
        self.registrar("integraciones", {"tool": nombre, "args": args})
        print(f"  [{nombre}] ✓")
        r = self.plugin.on_transform_tool_result(tool_name=nombre, args=args, result=resultado)
        return r if isinstance(r, str) else resultado

    def mcp(self, servidor: str, herramienta: str, args: dict, resultado: str = "ok") -> str | None:
        return self.herramienta(f"mcp__{servidor}__{herramienta}", args, resultado)

    def registrar(self, nombre: str, dato: dict) -> None:
        sim = self.raiz / ".sim" / f"{nombre}.jsonl"
        sim.parent.mkdir(exist_ok=True)
        with sim.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dato, ensure_ascii=False) + "\n")

    def leer(self, ruta: str) -> str | None:
        """read_file: también pasa por el freno (`protectedReads`). Frenado → None."""
        if not self._pedir("read", {"path": ruta}):
            return None
        return (self.raiz / ruta).read_text(encoding="utf-8")


def intento(argv: list[str] | None = None) -> int:
    """El número de intento, del prompt del loop (`loop.retryPrompt` empieza con «Intento N»)."""
    prompt = (argv or sys.argv)[1] if len(argv or sys.argv) > 1 else ""
    m = re.search(r"Intento\s+(\d+)", prompt)
    return int(m.group(1)) if m else 1


def modo(defecto: str = "aprende") -> str:
    import os
    return os.environ.get("JUGUETE", defecto)
