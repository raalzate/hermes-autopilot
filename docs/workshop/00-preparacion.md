# Módulo 0 — Preparación (20 min)

**Idea:** el entregable es un comando que sale verde o rojo, no una opinión. Antes de dejar a un
agente solo, tiene que existir ese comando.

## Ejercicio 0.1 — Un sandbox con el arnés

```bash
mkdir ~/taller-autopilot && cd ~/taller-autopilot
git init -b main
git config user.email "vos@ejemplo.test" && git config user.name "Vos"

python3 $AUTOPILOT/scripts/install.py . --profile python            # DRY-RUN: mirá la lista
python3 $AUTOPILOT/scripts/install.py . --profile python --apply
python3 .hermes/harness/scripts/githooks.py install
```

**Tiene que salir:** la lista de archivos con `+`, y `hooks de git instalados (core.hooksPath=.githooks)`.

El instalador es dry-run por defecto y nunca sobreescribe (P9). Mirá qué dejó:

- `.hermes/harness.config.json` es el único archivo con reglas, y es de tu repo;
- `.hermes/harness/` tiene el código del arnés (plugin, scripts y plantillas), que es genérico;
- `.hermes/skills/` trae las skills de Hermes (`gate`, `lesson`…);
- `.hermes/loop/tasks.md` es la cola del loop autónomo;
- `.githooks/` tiene los hooks `pre-commit`, `commit-msg` y `pre-push`.

## Ejercicio 0.2 — Un atajo

Todos los comandos del workshop pasan por la CLI. Para no escribir la ruta cada vez:

```bash
alias ap="python3 $HOME/taller-autopilot/.hermes/harness/scripts/cli.py"
ap status
```

**Tiene que salir:** `taller-autopilot · rama main`, el gate `nunca corrió` y la cantidad de
frenos por familia.

## Ejercicio 0.3 — El criterio de «terminado»

El perfil python trae una señal `tests (pytest)`. Si no tenés pytest, cambiala por `unittest`, que
viene con Python. Es la primera parametrización con la CLI:

```bash
ap signal rm "tests (pytest)" --apply
ap signal add "tests (unittest)" --why "el comportamiento: ninguna otra señal ejecuta el código" --apply -- python3 -m unittest -q
cp $AUTOPILOT/docs/workshop/sandbox/test_calc.py .
ap gate
```

**Tiene que salir:** `GATE ROJO — 1 señal(es) fallida(s): tests (unittest)`. Está bien que salga
rojo: `test_calc.py` importa `app.calc`, que todavía no existe. Ese test **es** la tarea del
módulo 4.

Probá agregar una señal sin `--why`. La CLI la rechaza: cada señal declara qué error atrapa (P6).

## Ejercicio 0.4 — El panel, abierto toda la sesión

En otra terminal:

```bash
cd ~/taller-autopilot && python3 .hermes/harness/scripts/cli.py panel
```

Abrí http://127.0.0.1:8765. **Tiene que salir:** la tarjeta Gate en `ROJO`, con `tests (unittest)`
en rojo, y en «Eventos en vivo» un `gate → roja`. Corré `ap gate` otra vez: el evento aparece sin
recargar la página.

## Ejercicio 0.5 — Primer commit

```bash
git add .githooks .github .hermes AGENTS.md STATUS.md docs test_calc.py
git commit -m "chore: arnés instalado" -m "no-issue: sandbox del workshop"
```

**Si no sale:** si `commit-msg` lo frena, falta la línea `no-issue:`. Es P11: un commit que toca
código dice qué ítem de trabajo resuelve, o declara por qué no.

→ [Módulo 1](01-guias.md)
