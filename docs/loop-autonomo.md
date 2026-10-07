# El loop autónomo — operarlo

`scripts/loop.py` es el lazo de la tarea (el 4 de [`ingenieria-de-loops.md`](ingenieria-de-loops.md)).
Toma la próxima tarea de una lista, se la da a Hermes, corre el gate y decide: verde, reintento
con el rojo o escalada a un humano. Lo hace cumplir P21 de la constitución.

```
tarea ──▶ agente (Hermes, no interactivo) ──▶ gate ──▶ verde ─────────────▶ [x] y la próxima (--all)
                ▲                                │
                └── reintento: señales rojas ◀───┤ rojo distinto
                    + cola de la salida          │
                                                 └ mismo rojo N veces · tope · stopFile ──▶ [!] escala
```

## En cinco comandos

```bash
python3 scripts/cli.py task add "Agregá la regla X con su example y su caso"   # la cola
python3 scripts/cli.py loop                    # DRY-RUN: tarea, rama, prompt, comandos, topes
python3 scripts/cli.py loop --apply            # una tarea, hasta verde o hasta escalar
python3 scripts/cli.py loop --apply --all      # sigue mientras salgan verdes
python3 scripts/cli.py loop --stop             # freno de mano: para entre iteraciones
```

`cli.py loop` es un pasamanos a `scripts/loop.py`, y los dos aceptan lo mismo. En un repo
instalado la ruta es `.hermes/harness/scripts/`. Mientras corre, `python3 scripts/cli.py panel`
lo muestra en vivo.

## La cola de tareas

`.hermes/loop/tasks.md` (`loop.tasksFile`) es markdown con casillas. El loop toma la primera
`- [ ]`, y al terminar la marca `- [x]` (verde) o `- [!] … — motivo` (escaló). Lo demás del archivo
no lo toca.

Una tarea buena para el loop:

- **es chica y verificable por el gate.** Si el gate no puede decir que está hecha, el loop
  tampoco: «que `suma` pase `test_calc.py`», no «mejorá el cálculo»;
- **no requiere decisiones de producto.** El agente no tiene a quién preguntarle. Si la tarea
  necesita un criterio, escribilo en la tarea;
- **tiene su prueba antes.** El mejor gate para una tarea nueva es un test que hoy falla.

## Qué hace en cada intento

1. Si la rama actual está en `branches.protected`, abre `loop/<slug-de-la-tarea>` (el loop no
   trabaja sobre `main`).
2. Arma el prompt: `loop.prompt` la primera vez y `loop.retryPrompt` en los reintentos, con
   `{task}`, `{gate}`, `{failures}`, `{gate_tail}` y `{attempt}`.
3. Corre `loop.agentCommand` sin shell (`{prompt}` se reemplaza dentro de cada argumento), con
   timeout `agentTimeoutMinutes`. Adentro, el agente sigue gobernado por el arnés de siempre:
   frenos, lint y `pre_verify`.
4. Corre `loop.gateCommand` con timeout `gateTimeoutMinutes`. **Solo esto decide.**
5. Registra el intento (`.git/harness-loop.json` y el registro de eventos) y decide con `decidir()`.

## Cuándo para

| Resultado | Cuándo | Exit | Marca |
|---|---|---|---|
| `verde` | el gate sale 0 | 0 | `[x]` |
| `escalar` | el mismo rojo (misma *firma*) `sameFailureLimit` veces seguidas | 2 | `[!]` |
| `escalar` | `maxIterations` intentos sin verde | 2 | `[!]` |
| `escalar` | pasaron `maxMinutes` | 2 | `[!]` |
| `parado` | existe `stopFile` al terminar un intento | 2 | queda `[ ]` |

La **firma** de un rojo son los nombres de las señales `✗` del gate, ordenados. Las duraciones no
cuentan: si contaran, el mismo error parecería distinto en cada intento y nunca escalaría.

## Cuando escala

El loop paró porque el agente no está progresando. Eso es información, no un fracaso del loop.

1. Mirá el motivo en el panel o con `python3 scripts/loop.py --status`. Los intentos están con su firma.
2. Corré el gate vos y leé la primera señal roja.
3. Decidí: ¿la tarea estaba mal escrita? Reescribila, más chica o con el criterio que faltaba.
   ¿Hay un freno que la hace imposible? El freno está bien o mal, pero no se rodea. ¿Es un
   incidente? Usá la skill `lesson` (P15).
4. Volvé la casilla a `- [ ]` y corré de nuevo.

## Correrlo desatendido

El loop no necesita una terminal abierta, pero **sí necesita que alguien haya decidido qué puede
hacer solo** (P13):

- en segundo plano, en una sesión de `tmux`/`screen` o con `nohup`, y con el panel abierto en otra
  pestaña;
- programado (cron del sistema, un runner de CI con Hermes instalado). El loop nunca empuja, así
  que lo programado deja ramas `loop/*` verdes para revisar a la mañana. **No** lo programes con
  el cron de Hermes para que publique: `cron.deny` lo frena, y está bien que lo frene.

## La configuración

| Clave de `loop` | Qué decide | Por defecto |
|---|---|---|
| `tasksFile` | la cola | `.hermes/loop/tasks.md` |
| `agentCommand` | argv del agente; `{prompt}` se reemplaza | `["hermes", "chat", "-q", "{prompt}"]` |
| `gateCommand` | argv del criterio de salida | `["python3", "scripts/gate.py"]` |
| `maxIterations` | intentos por tarea | 4 |
| `sameFailureLimit` | mismo rojo seguido que escala (P16) | 2 |
| `maxMinutes` | reloj por tarea | 90 |
| `agentTimeoutMinutes`, `gateTimeoutMinutes` | timeout de cada proceso | 30, 20 |
| `branchPrefix` | rama que abre si arranca en una protegida | `loop/` |
| `stopFile`, `stateFile` | freno de mano y estado (bajo `.git/`, fuera del árbol) | `.git/harness-loop.stop`, `.git/harness-loop.json` |
| `prompt`, `retryPrompt` | lo que lee el agente | ver el config |

Se cambian con la CLI y se prueban antes de escribirse:

```bash
python3 scripts/cli.py config set loop.maxIterations 6
python3 scripts/cli.py config set loop.maxIterations 6 --apply
```

## Lo que el loop no hace

- **No empuja ni abre PR.** Lo verde queda en la rama y lo publica un humano.
- **No se saltea frenos.** Si la tarea choca con uno, el agente lo explica y el gate no da verde.
- **No reintenta a ciegas.** Cada reintento lleva el rojo, y el mismo rojo dos veces es escalada.
- **No paraleliza.** Trabaja una tarea por vez, en una rama.
