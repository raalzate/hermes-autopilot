#!/usr/bin/env python3
"""
Hermes desde su código fuente, en un commit fijo: para correr el gate contra el Hermes REAL.

    python3 scripts/hermes_fuente.py <dir> [--ref <commit>]

Las dos señales del gate que miran a Hermes por dentro (`hermes plugins doctor` y el e2e del
contrato) salen OMITIDAS donde no está instalado. Hermes no publica wheels de su rama principal
(el build los rechaza a propósito) y el paquete de PyPI va meses atrás (0.19.0 no tiene
`plugins doctor` ni las secciones del system prompt). Esto arma, sin tocar el sistema:

    <dir>/fuente   clon de NousResearch/hermes-agent en `--ref` (por defecto, el verificado)
    <dir>/venv     venv con las dependencias de PyPI, SIN el paquete viejo, y un `.pth` al clon
    <dir>/bin      un `hermes` mínimo que corre `hermes_cli.main` del clon

Imprime las tres variables a exportar. Lo usa CI (job `hermes-real`) y sirve igual en tu máquina.
No escribe en `~/.hermes`: exportá `HERMES_HOME` a un directorio propio.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

VERIFICADO = "aa74e184ea779994af642ab4f888e10a95415d90"  # el commit de hermes-agent contra el que se verificó el arnés (2026.9.24)


def run(*argv, cwd=None):
    print("$ " + " ".join(str(a) for a in argv), flush=True)
    subprocess.run([str(a) for a in argv], cwd=cwd, check=True)


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 1
    base = Path(argv[0]).expanduser().resolve()
    ref = argv[argv.index("--ref") + 1] if "--ref" in argv else VERIFICADO
    fuente, venv, binario = base / "fuente", base / "venv", base / "bin"
    if not (fuente / ".git").is_dir():
        run("git", "clone", "-q", "https://github.com/NousResearch/hermes-agent", fuente)
    run("git", "-C", fuente, "fetch", "-q", "--depth", "1", "origin", ref)
    run("git", "-C", fuente, "checkout", "-q", "FETCH_HEAD")
    if not venv.is_dir():
        run(sys.executable, "-m", "venv", venv)
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(py, "-m", "pip", "install", "-q", "--disable-pip-version-check", "hermes-agent")  # trae las dependencias
    run(py, "-m", "pip", "uninstall", "-q", "-y", "hermes-agent")  # …y se va el código viejo
    sitio = subprocess.run([str(py), "-c", "import site; print(site.getsitepackages()[0])"],
                           capture_output=True, text=True, check=True).stdout.strip()
    Path(sitio, "hermes-fuente.pth").write_text(str(fuente) + "\n", encoding="utf-8")
    binario.mkdir(parents=True, exist_ok=True)
    hermes = binario / "hermes"
    hermes.write_text(f"#!{py}\nimport sys\nfrom hermes_cli.main import main\nsys.exit(main())\n", encoding="utf-8")
    hermes.chmod(0o755)
    print(f"\nHermes desde el código fuente ({ref}) listo. Exportá:\n"
          f"  PATH={binario}{os.pathsep}$PATH\n  HERMES_HOME=<un directorio propio, no ~/.hermes>")
    if os.environ.get("GITHUB_PATH"):
        with open(os.environ["GITHUB_PATH"], "a", encoding="utf-8") as f:
            f.write(f"{binario}\n")
    return 0 if shutil.which("git") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
