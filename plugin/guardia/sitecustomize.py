"""
Instala la guardia del arnés (guardia.py) en este proceso Python, si `HARNESS_GUARDIA` lo pide o,
sin esa variable, si el repo del directorio actual dejó su spec en `.git/harness-guardia.json`.

Python importa `sitecustomize` solo, al arrancar, si está en el `PYTHONPATH`: el loop lo pone ahí
para el agente, y el plugin en el proceso de Hermes (sesiones interactivas, `sessionGuard.python`). Nada de esto puede romper el arranque de Python: cualquier error, y la guardia no
se instala (el agente sigue frenado por el plugin, el worktree y los intocables).
"""
import json
import os
import sys


def _instalar():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import guardia

    if os.environ.get("HARNESS_GUARDIA"):
        spec = json.loads(os.environ["HARNESS_GUARDIA"])
    else:
        spec = guardia.buscar_spec(os.getcwd())
        if not spec:
            return

    raiz = spec.get("raiz") or os.getcwd()
    dentro = [False]

    def registrar(regla, rel):
        if not spec.get("registro") or dentro[0]:
            return
        dentro[0] = True
        try:
            import time
            linea = json.dumps({"at": round(time.time(), 3), "kind": "block", "rule": regla.get("id", "?"),
                                "tool": "python", "path": rel}, ensure_ascii=False)
            fd = os.open(spec["registro"], os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(fd, (linea + "\n").encode("utf-8"))
            finally:
                os.close(fd)
        except Exception:  # noqa: BLE001 — registrar nunca bloquea
            pass
        finally:
            dentro[0] = False

    def hook(evento, args):
        if dentro[0]:
            return
        if evento == "open":
            rutas, w = [args[0]], guardia.escribe(args[1], args[2] if len(args) > 2 else None)
        elif evento in ("os.remove", "os.unlink", "os.rmdir", "shutil.rmtree", "os.truncate"):
            rutas, w = [args[0]], True
        elif evento in ("os.rename", "os.replace", "shutil.move", "shutil.copyfile"):
            rutas, w = [args[0], args[1]], True
        else:
            return
        for ruta in rutas:
            rel = guardia.relativa(ruta, raiz)
            if rel is None:
                continue
            regla = guardia.decidir(rel, w, spec)
            if regla:
                registrar(regla, rel)
                raise PermissionError(
                    f"GUARDIA DEL ARNÉS: `{rel}` no se {'escribe' if w else 'lee'} desde un programa del agente.\n"
                    f"Motivo: {regla.get('reason', '')}")

    sys.addaudithook(hook)


if not os.environ.get("HARNESS_GUARDIA_OFF"):
    try:
        _instalar()
    except Exception:  # noqa: BLE001 — una guardia rota no puede romper Python
        pass
