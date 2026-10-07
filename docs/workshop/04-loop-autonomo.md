# Módulo 4 — El loop autónomo (40 min)

**Idea:** el agente no se declara terminado. Un loop externo le da la tarea, corre el gate y
decide: verde, reintento con el error en la mano, o escalada a un humano. Las reglas de diseño
están en [`../ingenieria-de-loops.md`](../ingenieria-de-loops.md) y la operación en
[`../loop-autonomo.md`](../loop-autonomo.md).

## Ejercicio 4.1 — Poner al agente de juguete

El agente de juguete escribe `app/calc.py`. En el primer intento mete un bug. Cuando el prompt
trae el rojo del gate (el reintento empieza con «Intento N»), lo corrige. Es determinista: hace
lo mismo en todas las máquinas.

```bash
ap config set loop.agentCommand "[\"python3\", \"$AUTOPILOT/docs/workshop/sandbox/agente_juguete.py\", \"{prompt}\"]" --apply
ap config set branches.protected '["main"]' --apply
```

Lo segundo hace que el loop no trabaje sobre `main`: abre una rama `loop/…` antes de tocar nada.

## Ejercicio 4.2 — La tarea, y el plan sin ejecutar

```bash
ap task add "Implementá suma(a, b) en app/calc.py para que pase test_calc.py"
ap loop
```

**Tiene que salir:** `DRY-RUN del loop`, con la tarea, la rama que abriría, el comando del
agente, el del gate, los topes y el prompt del primer intento. Nada se ejecutó (P9).

## Ejercicio 4.3 — Verde en el intento 2

Mirá el panel y corré:

```bash
ap loop --apply
```

**Tiene que salir:**

```text
✗ intento 1: tests (unittest)
✓ intento 2: verde
✓ VERDE — gate verde en el intento 2
```

En el panel, el loop pasa por las fases `agente` → `gate`, el intento #1 queda rojo con su firma
y el #2 verde. Las tareas suman una verde. Además:

- `git branch --show-current` muestra `loop/implement-suma-…`: no tocó `main`;
- `ap task list` muestra la tarea con `[x]`;
- el loop **no empujó nada**. Lo verde queda en la rama y lo publicás vos (P13).

**Para discutir:** el agente de juguete «dijo» que terminó en el intento 1. ¿Por qué el loop no
le creyó? Porque la salida la decide el gate, no el actor.

## Ejercicio 4.4 — El agente terco y la escalada

```bash
git checkout main
ap task add "Que suma(a, b) siga pasando test_calc.py"
JUGUETE=terco ap loop --apply
```

**Tiene que salir:**

```text
✗ intento 1: tests (unittest)
✗ intento 2: tests (unittest)
✗ ESCALAR — el mismo rojo 2 veces seguidas (tests (unittest)): reintentar sin hipótesis nueva
  es el bucle que P16 prohíbe. Lo mira un humano.
```

El exit es 2, la tarea queda `[!]` con el motivo y el panel muestra la escalada en rojo.

**Este es el momento central del workshop.** El loop tenía 4 intentos y usó 2. Paró porque el
agente repetía **el mismo** error: seguir hubiera quemado tiempo y plata sin información nueva.
Dos rojos *distintos* sí son progreso, y el loop sigue. Probalo: `ap config set
loop.sameFailureLimit 3 --apply` y repetí (dejá la tarea en `- [ ]` antes). Ahora quema un
intento más antes de escalar: el número es una decisión del equipo, no del agente.

## Ejercicio 4.5 — Leé el estado

```bash
python3 .hermes/harness/scripts/loop.py --status
```

Cada intento queda con `agentExit`, `gateExit`, su `signature` y lo que tardó. Es lo que ve el
panel y lo que vas a leer en el módulo 6 para decidir qué hacer.

→ [Módulo 5](05-operar.md)
