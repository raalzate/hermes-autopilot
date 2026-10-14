# Módulo 0 — Instalar en L0 (20 min)

**Idea:** un agente recién instalado no merece confianza todavía, ni desconfianza. Merece
**observar**. Toda instalación de Hermes Autopilot arranca en L0 (P27).

## Ejercicio 0.1 — El repo de juguete, con el arnés

```bash
mkdir ~/taller-autonomia && cd ~/taller-autonomia
git init -b main
git config user.email "vos@ejemplo.test" && git config user.name "Vos"

python3 $AUTOPILOT/scripts/install.py . --profile python --apply
python3 .hermes/harness/scripts/githooks.py install
cp -R $AUTOPILOT/docs/workshop/autonomia/repo/. .
mv tareas.md .hermes/loop/tasks.md
```

**Tiene que salir:** la lista de archivos con `+`. Al final, el paso 7: *«El agente arranca en L0
(observa): la autonomía se gana con evidencia»*.

El repo es una tienda de juguete con un bug a propósito: `total()` en `tienda/carrito.py` resta el
descuento como si fuera un monto, y es un porcentaje. `python3 -m unittest -q` da **1 falla**.

## Ejercicio 0.2 — El atajo y el criterio de «terminado»

```bash
alias ap="python3 $HOME/taller-autonomia/.hermes/harness/scripts/cli.py"
ap signal rm "tests (pytest)" --apply
ap signal add "tests (unittest)" --why "el comportamiento: ninguna otra señal ejecuta el código" --apply -- python3 -m unittest -q
printf '__pycache__/\n' > .gitignore
git add .gitignore .githooks .github .hermes AGENTS.md STATUS.md docs README.md tienda test_carrito.py
git commit -m "chore: arnés y tienda de juguete" -m "no-issue: sandbox del workshop"
```

**Si no sale:** si `commit-msg` frena el commit, falta la línea `no-issue:` (P11).

## Ejercicio 0.3 — ¿Dónde está el agente?

```bash
ap nivel
```

**Tiene que salir:**

```
Nivel L0 — Observador
  puede     leer el repo, correr comandos de sólo lectura (git status/diff/log, ls, cat, grep) y reportar en la respuesta.
  no puede  escribir archivos, correr tests ni comandos que cambien algo, ejecutar código, …
  loop      no

Evidencia para L1 (desde la última transición):
    ✗ sesiones sin salirse del nivel          0  (al menos 3)
```

Leé la clave `autonomia` en `.hermes/harness.config.json`. Todo lo que acabás de ver sale de ahí:

- qué permite cada nivel (`niveles`);
- cuánta evidencia hace falta para subir (`ascenso`);
- qué lo hace bajar (`descenso`).

Son decisiones de tu equipo, no del arnés.

## Ejercicio 0.4 — El panel, abierto toda la sesión

En otra terminal:

```bash
cd ~/taller-autonomia && python3 .hermes/harness/scripts/cli.py panel
```

Abrí http://127.0.0.1:8765. **Tiene que salir:** arriba, la sección **Salud del agente**, con:

- la escalera L0 · Observador → L3 · Autonomía, con L0 resaltado;
- lo que puede y lo que no;
- una barra de evidencia vacía: «sesiones sin salirse del nivel 0 / ≥ 3».

**Para discutir:** ¿en qué nivel arrancaría hoy un agente en tu equipo, si tuvieran que decidirlo
por evidencia y no por entusiasmo?

→ [Módulo 1](01-L0-observador.md)
