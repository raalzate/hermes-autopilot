#!/usr/bin/env python3
"""
El agente desarrollador de juguete del workshop de autonomía: hace de Hermes sin modelo ni API key.

    python3 agente_dev.py observar        L0: lee, corre comandos de lectura y reporta
    python3 agente_dev.py impaciente      L0: igual, pero intenta arreglar el bug (el nivel lo frena)
    python3 agente_dev.py recomendar      L1: corre los tests y deja UNA propuesta en .hermes/recomendaciones/
    python3 agente_dev.py arreglar        L2: hace el próximo cambio pendiente; cada escritura y commit lo aprobás vos
    python3 agente_dev.py loop "<prompt>" L3: lo que corre el loop autónomo (loop.agentCommand)

Corre en el directorio actual (el sandbox). Cada herramienta pasa por el plugin REAL del sandbox, a
través del despacho simulado de Hermes (`casos/hermes_sim.py`): el freno de nivel, los frenos del
repo y el registro de eventos son los de verdad. Cada corrida es una sesión nueva.

    JUGUETE_APRUEBA=si|no   contesta las aprobaciones sin preguntar (sin esto, te pregunta)
    JUGUETE=tramposo        en el loop, en vez de trabajar, marca la tarea como hecha en la cola

Es determinista a propósito: el workshop enseña cómo se GANA la autonomía, no qué contesta un modelo.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parents[2] / "casos"))
from hermes_sim import Hermes  # noqa: E402

CARRITO = "tienda/carrito.py"
TESTS = "test_carrito.py"
ARREGLO = '    return subtotal(items) * (100 - descuento) / 100\n'
BUG = '    return subtotal(items) - descuento\n'

# Lo que propone en L1: cinco propuestas, una por corrida.
PROPUESTAS = [
    ("total-descuento-porcentaje", "total() resta el descuento como monto",
     "`total(items, descuento=10)` devuelve 240 y el test espera 225: el descuento es un porcentaje.\n\n"
     "Propuesta: `return subtotal(items) * (100 - descuento) / 100`."),
    ("test-carrito-vacio", "Falta un test para el carrito vacío",
     "Nada prueba `subtotal([])`. Propuesta: un test que espere 0."),
    ("docstring-subtotal", "subtotal() no dice qué espera",
     "Propuesta: documentar que cada ítem trae `precio` y `cantidad`."),
    ("descuento-fuera-de-rango", "total() acepta descuentos de 150 %",
     "Propuesta: `ValueError` si el descuento no está entre 0 y 100, con su test."),
    ("readme-como-se-trabaja", "El README no dice cómo se trabaja",
     "Propuesta: una sección que diga que cada cambio llega con su test y que el gate lo decide."),
]

# Lo que hace en L2: cinco cambios, uno por corrida. (marca para saber si ya está, archivo, transformación, commit)
def _cambios():
    return [
        ("* (100 - descuento) / 100", CARRITO, lambda t: t.replace(BUG, ARREGLO), "fix: el descuento de total() es un porcentaje"),
        ("def test_carrito_vacio", TESTS, lambda t: t.replace('\n\nif __name__',
         '\n    def test_carrito_vacio(self):\n        self.assertEqual(subtotal([]), 0)\n\n\nif __name__'), "test: carrito vacío"),
        ('"""Suma precio por cantidad', CARRITO, lambda t: t.replace('def subtotal(items):\n',
         'def subtotal(items):\n    """Suma precio por cantidad de cada ítem (`precio`, `cantidad`)."""\n'), "docs: subtotal()"),
        ("ValueError", CARRITO, lambda t: t.replace('    """El total con un descuento en PORCENTAJE (0 a 100)."""\n',
         '    """El total con un descuento en PORCENTAJE (0 a 100)."""\n    if not 0 <= descuento <= 100:\n'
         '        raise ValueError("el descuento es un porcentaje entre 0 y 100")\n'), "feat: total() valida el descuento"),
        ("## Cómo se trabaja", "README.md", lambda t: t + "\n## Cómo se trabaja\n\nCada cambio llega con su test, y el gate lo decide.\n", "docs: cómo se trabaja"),
    ]


def aprobador():
    fijo = os.environ.get("JUGUETE_APRUEBA", "").lower()
    if fijo in ("si", "sí", "no"):
        return lambda msg: (print(f"  ¿aprobás? → {fijo} (JUGUETE_APRUEBA)") or fijo != "no")

    def preguntar(msg: str) -> bool:
        print(f"\n  ⚠ PIDE APROBACIÓN: {msg.splitlines()[0][:200]}")
        try:
            return input("  ¿aprobás? [s/N] ").strip().lower() in ("s", "si", "sí", "y")
        except EOFError:
            return False  # sin humano (cron, loop): se niega
    return preguntar


def hermes(pedido: str) -> Hermes:
    h = Hermes(Path.cwd(), sesion=f"juguete-{uuid.uuid4().hex[:8]}", aprobador=aprobador())
    h.turno(pedido)
    return h


def tests_pasan() -> bool:
    p = subprocess.run([sys.executable, "-m", "unittest", "-q"], capture_output=True, text=True)
    return p.returncode == 0


def observar(intentar_arreglo: bool = False) -> int:
    h = hermes("Mirá el carrito y contame qué ves.")
    codigo = h.leer(CARRITO) or ""
    h.leer(TESTS)
    h.terminal("git log --oneline -5")
    h.terminal(f"grep -n 'def ' {CARRITO}")
    print("\nREPORTE DEL AGENTE")
    if BUG in codigo:
        print("  · total() resta el descuento como un monto, y la docstring dice que es un porcentaje.")
        print("    test_total_con_descuento_en_porcentaje espera 225 y daría 240.")
    else:
        print("  · total() aplica el descuento como porcentaje: coincide con su docstring.")
    print("  · subtotal() no documenta qué campos espera de cada ítem.")
    if intentar_arreglo:
        print("\nVoy a arreglarlo de una vez…")
        if h.escribir(CARRITO, codigo.replace(BUG, ARREGLO)):
            print("  arreglado.")
    return 0


def recomendar() -> int:
    h = hermes("Revisá el carrito y proponé mejoras.")
    h.leer(CARRITO)
    h.leer(TESTS)
    if h.terminal("python3 -m unittest -q"):
        print(f"  tests: {'verdes' if tests_pasan() else 'ROJOS'}")
    d = Path(".hermes/recomendaciones")
    hechas = {p.stem.split("-", 1)[-1] for p in d.glob("*.md")} if d.is_dir() else set()
    pendiente = next(((i, p) for i, p in enumerate(PROPUESTAS, 1) if p[0] not in hechas), None)
    if not pendiente:
        print("No tengo más propuestas: ya dejé las cinco.")
        return 0
    i, (clave, titulo, cuerpo) = pendiente
    ruta = f".hermes/recomendaciones/{i:03d}-{clave}.md"
    if h.escribir(ruta, f"# {titulo}\n\n{cuerpo}\n"):
        print(f"\nDejé la propuesta {ruta}. Juzgala: recomendacion aceptar|rechazar {ruta}")
    return 0


def _commit(h: Hermes, mensaje: str) -> bool:
    efecto = ("import subprocess; subprocess.run(['git', 'add', '-A']); "
              f"subprocess.run(['git', 'commit', '-q', '-m', {mensaje!r}, '-m', 'no-issue: sandbox del workshop'])")
    return h.terminal(f"git commit -am {mensaje!r}", efecto=efecto)


def arreglar() -> int:
    h = hermes("Hacé el próximo cambio pendiente del carrito.")
    for marca, archivo, cambio, mensaje in _cambios():
        actual = Path(archivo).read_text(encoding="utf-8") if Path(archivo).is_file() else ""
        if marca in actual:
            continue
        print(f"Cambio: {mensaje}")
        if not h.escribir(archivo, cambio(actual)):
            print("  no me dejaron escribir: no sigo con este cambio.")
            return 0
        if h.terminal("python3 -m unittest -q"):
            print(f"  tests: {'verdes' if tests_pasan() else 'ROJOS'}")
        _commit(h, mensaje)
        return 0
    print("No hay cambios pendientes: ya hice los cinco.")
    return 0


def loop(prompt: str) -> int:
    h = hermes(prompt)
    if os.environ.get("JUGUETE") == "tramposo":
        # Lo que un agente apurado hace: dar la tarea por hecha en la cola, por un canal que ningún
        # freno de herramienta ve (un binario, no Python). Lo ve el loop: la cola es intocable.
        h.terminal("touch .hermes/loop/tasks.md", efecto=(
            "from pathlib import Path; p = Path('.hermes/loop/tasks.md'); "
            "p.write_text(p.read_text(encoding='utf-8').replace('- [ ]', '- [x]', 1), encoding='utf-8')"))
        print("[juguete:tramposo] marqué la tarea como hecha.")
        return 0
    actual = Path(CARRITO).read_text(encoding="utf-8")
    pruebas = Path(TESTS).read_text(encoding="utf-8")
    if "iva(" in prompt and "def iva" not in actual:
        h.escribir(CARRITO, actual + '\n\ndef iva(items, tasa=0.19):\n    """El impuesto sobre el subtotal."""\n'
                   '    return round(subtotal(items) * tasa, 2)\n')
        h.escribir(TESTS, pruebas.replace("from tienda.carrito import subtotal, total", "from tienda.carrito import iva, subtotal, total")
                   .replace('\n\nif __name__', '\n    def test_iva(self):\n        self.assertEqual(iva(ITEMS), 47.5)\n\n\nif __name__'))
    elif "cupon(" in prompt and "def cupon" not in actual:
        h.escribir(CARRITO, actual + '\n\ndef cupon(items, codigo):\n    """El descuento de un cupón, en porcentaje."""\n'
                   '    return 5 if codigo == "BIENVENIDA" else 0\n')
        imports = pruebas.splitlines()[2]
        h.escribir(TESTS, pruebas.replace(imports, imports.replace("import ", "import cupon, ", 1))
                   .replace('\n\nif __name__', '\n    def test_cupon(self):\n        self.assertEqual(cupon(ITEMS, "BIENVENIDA"), 5)\n'
                            '        self.assertEqual(cupon(ITEMS, "OTRO"), 0)\n\n\nif __name__'))
    h.terminal("python3 -m unittest -q")
    print(f"[juguete:loop] tests {'verdes' if tests_pasan() else 'rojos'}")
    return 0


def main(argv: list[str]) -> int:
    modo = argv[0] if argv else ""
    if modo == "observar":
        return observar()
    if modo == "impaciente":
        return observar(intentar_arreglo=True)
    if modo == "recomendar":
        return recomendar()
    if modo == "arreglar":
        return arreglar()
    if modo == "loop":
        return loop(argv[1] if len(argv) > 1 else "")
    print(__doc__)
    return 1


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
