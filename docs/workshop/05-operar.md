# Módulo 5 — Operar (25 min)

**Idea:** un agente que trabaja solo necesita que alguien pueda ver qué hace y pararlo sin
romper nada. Eso no es un extra: un lazo que nadie ve es un lazo que nadie ajusta (P22).

## Ejercicio 5.1 — El freno de mano

Agregá dos tareas y corré el loop con `--all` (sigue mientras salgan verdes). Mientras corre, en
otra terminal:

```bash
ap loop --stop
```

**Tiene que salir:** el loop termina la iteración en curso y para con `PARADO — se pidió parar`.
El panel muestra `⏸ parada pedida` apenas creás el archivo. La tarea en curso queda `- [ ]`:
nada a medio escribir, nada marcado como hecho.

Con el agente de juguete el intento dura un segundo. Para verlo con calma, poné un agente que
tarde: `ap config set loop.agentCommand '["python3", "-c", "import time; time.sleep(20)", "{prompt}"]' --apply`.

## Ejercicio 5.2 — Leer el panel como operador

Con lo que corriste hasta acá, contestá mirando solo el panel:

1. ¿Cuántas veces mordió un freno hoy, y cuál? (Eventos: `freno`)
2. ¿El último gate fue completo o `fast`? ¿Alguna señal OMITIDA?
3. ¿Cuál fue la firma del rojo que hizo escalar, y en qué intento?
4. ¿El `STATUS.md` tiene un veredicto de cuándo? ¿Vencido?

Si alguna no se puede contestar desde el panel, es una propuesta de mejora: abrí un issue.

## Ejercicio 5.3 — Con Hermes de verdad (si lo tenés)

```bash
cd ~/taller-autopilot
hermes skills trust .
python3 .hermes/harness/scripts/install.py . --link-plugin --apply
hermes plugins enable repo-harness
ap config set loop.agentCommand '["hermes", "chat", "-q", "{prompt}"]' --apply
ap task add "Agregá resta(a, b) a app/calc.py con su test en test_calc.py"
ap loop --apply
```

Ahora en el panel aparecen eventos que el juguete no generaba: `freno` si Hermes intenta algo
vedado, `lint` si escribe algo que el lint marca, `gate pendiente` si quiere cerrar el turno sin
verificar. Son los lazos 1 a 3 de [`../ingenieria-de-loops.md`](../ingenieria-de-loops.md),
corriendo **adentro** del lazo 4.

**Si no sale:** `hermes plugins list` tiene que mostrar `repo-harness` habilitado, y
`python3 .hermes/harness/scripts/doctor.py` dice qué falta en tu máquina.

## Ejercicio 5.4 — Desatendido, con criterio

Discutí en grupo antes de programar el loop:

- ¿Qué puede hacer solo? Lo decide el config, **antes** de programarlo (P13).
- ¿Quién mira las ramas `loop/*` verdes a la mañana?
- ¿Quién lee las `[!]`?

El loop nunca empuja. Programarlo con el cron de Hermes para que publique choca con `cron.deny`,
y está bien que choque.

→ [Módulo 6](06-aprender.md)
