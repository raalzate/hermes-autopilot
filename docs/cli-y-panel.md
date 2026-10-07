# La CLI y el panel

Dos puertas al mismo arnés. La CLI sirve para **parametrizarlo** sin editar JSON a mano. El panel
sirve para **verlo funcionar** en vivo. Las dos leen `.hermes/harness.config.json`, y ninguna
tiene reglas propias (P4).

## La CLI — `scripts/cli.py`

En un repo instalado: `python3 .hermes/harness/scripts/cli.py`. Escribir siempre es `--apply`.
Sin esa bandera, la CLI muestra qué cambiaría y no toca nada (P9).

| Comando | Qué hace |
|---|---|
| `status [--json]` | rama, veredicto del gate y cada señal, edad del `STATUS.md`, frenos por familia, loop y últimos eventos |
| `rule list [familia]` | las reglas, con su motivo |
| `rule add <familia> --id … --pattern … --example … --reason … [--more …] [--apply]` | agrega una regla **después de probarla** (ver abajo) |
| `rule rm <familia> <id> [--apply]` | la quita |
| `rule test <familia> "texto"` | ¿qué regla frena esto?, y el mensaje que leería el agente |
| `signal list` · `signal add "nombre" --why "…" [--fast-skip] [--apply] -- cmd args…` · `signal rm "nombre"` | las señales del gate; `why` es obligatorio (P6) |
| `config get [ruta]` · `config set <ruta> <valor> [--apply]` | cualquier clave escalar u objeto; el valor se lee como JSON si se puede. Las listas de reglas no: van por `rule` |
| `task add "texto"` · `task list` | la cola del loop autónomo |
| `profile list` | los perfiles de stack del instalador |
| `gate` · `selftest` · `lint` · `map` · `timing` · `doctor` · `drift` · `install` · `loop` · `panel` · `mutations` · `linkcheck` | pasamanos al script del mismo nombre, con sus argumentos |

Familias de reglas: `terminal.deny`, `terminal.ask`, `protectedPaths`, `patterns`,
`memory.deny`, `skills.deny`, `cron.deny` y `routes`.

### Por qué `rule add` y no editar el JSON

Una regla nueva pasa por el mismo `guards.evaluate` que usa el plugin **antes** de escribirse:

- **P2, muerde.** Trae `example`, el ejemplo (y cada `--more`) frena, y lo frena *esta* regla. Si
  ya lo frenaba otra, la regla nueva no prueba nada propio.
- **P3, no muerde de más.** Ningún inocente de su familia (`terminal.innocent`,
  `protectedInnocent`…) queda frenado. Para la terminal tampoco el gate, `fastCommand`,
  `installHooksCommand` ni `loop.gateCommand`: un freno que bloquea el gate deja al agente y al
  loop sin forma de terminar.
- **El config resultante pasa el lint.** Por ejemplo `COHERENCIA`: un `reason` que recomienda un
  comando que otra regla veda.

```text
$ python3 scripts/cli.py rule add terminal.deny --id malo --pattern 'git' --example 'git log' --reason 'x'
✗ la regla no entra:
  - muerde de más: frena «git status», que tiene que pasar (P3)
  - muerde de más: frena «git diff --stat», que tiene que pasar (P3)
  ...
```

Después de `--apply`, la doble validación de siempre: `cli.py selftest` (¿muerde?) y
`cli.py lint` (¿no muerde de más?).

## El panel — `scripts/panel.py`

```bash
python3 scripts/cli.py panel              # http://127.0.0.1:8765
python3 scripts/cli.py panel --port 9000
python3 scripts/panel.py --once           # el mismo estado, como JSON, una vez
```

| Tarjeta | De dónde sale |
|---|---|
| **Gate**: veredicto, modo, hora y cada señal | `.git/harness-gate.json` (lo escribe `gate.py`) y el marcador de gate pendiente |
| **Loop autónomo**: fase, tarea, intento, firma de cada rojo, motivo de la escalada, parada pedida | `loop.stateFile`, `loop.stopFile` |
| **Tareas**: pendientes, verdes, escaladas y la barra de avance | `loop.tasksFile` |
| **Frenos activos**: cuántas reglas tiene cada familia | el config |
| **Salud**: edad del veredicto de `STATUS.md`, piezas del mapa, sin clasificar, etapas sin control y si el registro está encendido | `STATUS.md`, `map.construir`, el config |
| **Eventos en vivo**: cada `block`, `ask`, `lint`, `verify-pending`, `gate` y `loop-*` | `observability.events.file` |

### Cómo se actualiza

Con Server-Sent Events. El servidor mira cada segundo la fecha de modificación de esas fuentes y,
cuando algo cambió, empuja el estado entero al navegador (`/api/stream`). Manda un latido cada 15 s
para que un proxy no corte el stream. No usa websockets, ni build, ni dependencias: es
`http.server` con un `EventSource`. Si el navegador no tiene `EventSource`, consulta
`/api/state` cada 2 s.

### El registro de eventos

`observability.events` lo enciende: `{"file": ".git/harness-events.jsonl", "maxBytes": 524288}`.
Tiene una línea JSON por evento y vive bajo `.git/`, fuera del árbol de fuentes (P7). Pasado
`maxBytes` rota a `.1`. Lo escriben:

| Quién | Eventos |
|---|---|
| el plugin (`plugin/harness/events.py`) | `block`, `ask` (con `rule` y `tool`), `lint` (cuántos hallazgos y el primero), `verify-pending` |
| `scripts/gate.py` | `gate` (modo, veredicto, señales rojas y omitidas) |
| `scripts/loop.py` | `loop-start`, `loop-iter` (número, verde o firma), `loop-verde`, `loop-escalar`, `loop-parado` |

Registrar **nunca bloquea** (P5): un disco lleno o un `.git` de solo lectura no frenan una
herramienta. Tampoco lanza procesos (P19). `HARNESS_NO_EVENTS=1` lo apaga, y el self-test lo usa
para no llenar tu panel de bloqueos de prueba.

### Seguridad

El panel escucha en **127.0.0.1**, es de solo lectura y no tiene autenticación. El estado incluye
los motivos de los frenos y fragmentos de la salida del gate. Exponerlo con `--host 0.0.0.0` es
decisión tuya, y el panel lo avisa al arrancar. Si lo necesitás remoto, usá un túnel SSH
(`ssh -L 8765:127.0.0.1:8765 …`), no `--host`.
