# Hermes Autopilot

Un agente autónomo sobre [Hermes Agent](https://hermes-ai.net/) (Nous Research), y el arnés que lo
hace confiable. Hermes toma tareas de una cola, las trabaja, las verifica con un gate, reintenta
con el error en la mano, escala cuando se traba y nunca publica sin un humano. Mientras tanto, las
reglas del repo se hacen cumplir solas: en la CLI, en el gateway de mensajería y en las tareas
programadas. Y un panel muestra todo en vivo.

> Antes se llamaba `hermes-harness`. Ver [`docs/decisions/0006-autonomia-loop-cli-panel.md`](docs/decisions/0006-autonomia-loop-cli-panel.md).

Hermes es un agente que **aprende** (escribe su memoria, crea y parchea skills) y que **corre
desatendido** (cron, Telegram, Slack…). Eso lo hace más útil y también más difícil de gobernar:
lo que aprende mal lo repite en todas las sesiones, y donde corre solo no hay humano para aprobar
un comando peligroso. Este arnés pone frenos en esos dos lugares además de en la terminal y los
archivos, y un gate que define qué es "terminado".

## Qué trae

- **Loop autónomo** (`scripts/loop.py`): tarea → agente → gate, hasta verde o hasta escalar. La
  salida es el gate. El mismo rojo dos veces seguidas para y te avisa. Tiene tope de intentos y
  de reloj y un freno de mano (`--stop`), y nunca empuja.
- **CLI** (`scripts/cli.py`) para parametrizar sin editar JSON: `rule add` prueba la regla por el
  plugin **antes** de escribirla. También tiene `signal`, `config`, `task` y `status`, y es la
  puerta a todo lo demás.
- **Panel en vivo** (`scripts/panel.py`): gate, loop, tareas, frenos y cada evento en el momento
  en que pasa. Usa Server-Sent Events y escucha solo en 127.0.0.1.
- **Workshop** ([`docs/workshop/`](docs/workshop/README.md)): 3 h 30 min prácticas en un sandbox,
  con un agente de juguete y sin API key.
- **Integraciones** ([`docs/integraciones.md`](docs/integraciones.md)): navegador headless, Google
  Workspace, Microsoft 365, WhatsApp/Telegram/Slack/correo (`hermes send`), GitHub y PostgreSQL. Hermes
  conecta; el arnés decide qué clase de acción es cada herramienta, a quién se manda, cuánto, desde qué
  tarea y con qué secretos arranca cada servidor. Se habilitan con un comando que prueba antes de
  escribir (`integ.py add`), se instalan aisladas y fijadas con lock (`integ.py deps`), y Hermes registra
  sólo lo que el perfil permite y las arranca recién cuando se usan.
- **22 casos reales replicables** ([`casos/`](casos/README.md)) de programación, infraestructura,
  oficina, datos, soporte y operación (cinco con integraciones): un agente toma un atajo y el arnés lo frena, lo escala o lo
  deja llegar a verde. Se corre cada uno con un comando, y el gate los corre todos.
- **Auditoría de huecos** ([`docs/huecos.md`](docs/huecos.md)): 23 cerrados con su prueba, y lo
  que sigue abierto con su porqué.
- **Defensa en capas para lo desatendido:** cada tarea del loop corre aislada en su worktree (los
  secretos no están), una guardia de Python ve lo que un programa abre, y una sesión que leyó a un
  tercero no publica ni se reescribe sola (inyección de prompt).
- **Hermes real en CI** (`scripts/hermes_fuente.py`, job `hermes-real`) y el **revisor inferencial
  medido** con una tasa (`scripts/revision.py`).
- **Plugin `repo-harness`** para Hermes: frena herramientas en `pre_tool_call` (terminal,
  escritura, memoria, skills, cron), corre el lint del archivo recién escrito y se lo muestra al
  modelo, no deja cerrar el turno con el gate pendiente (`pre_verify`) e inyecta el estado
  verificado del repo al abrir la sesión.
- **Un solo archivo de reglas**: `.hermes/harness.config.json`. El código no sabe nada del repo.
  Cada regla trae su `example`, y el self-test prueba que frene.
- **Gate** (`scripts/gate.py`): la única definición de entregable, declarativa, igual en CI.
- **Lint** con una regla que ningún otro arnés tiene: caza lo que haría que el escáner de
  inyección de Hermes **descarte tu `AGENTS.md` entero**.
- **Skills** (`/gate`, `/lesson`, `/new-guardrail`, `/harness-audit`, `/harness-review`,
  `/harness-port`) y **doctor** para ver si el arnés está vivo en tu máquina.
- **Instalador** para cualquier repo (Python, Node, front, Go, Rust, .NET, JVM), dry-run por
  defecto y sin sobreescribir nada.

Python de la biblioteca estándar. Sin dependencias.

## Empezar

```bash
# en este repo
python3 scripts/gate.py
python3 scripts/cli.py status
python3 scripts/cli.py panel                                      # http://127.0.0.1:8765

# en tu repo
python3 scripts/install.py ~/code/mi-repo --profile python          # mirá la lista
python3 scripts/install.py ~/code/mi-repo --profile python --apply
cd ~/code/mi-repo
hermes skills trust .
python3 .hermes/harness/scripts/install.py . --link-plugin --apply
hermes plugins enable repo-harness
python3 .hermes/harness/scripts/githooks.py install
python3 .hermes/harness/scripts/gate.py
python3 .hermes/harness/scripts/doctor.py

# conectarle cosas (dry-run sin --apply)
python3 .hermes/harness/scripts/integ.py list
python3 .hermes/harness/scripts/integ.py add navegador --apply && python3 .hermes/harness/scripts/integ.py deps navegador --apply

# y dejarlo trabajar solo
python3 .hermes/harness/scripts/cli.py task add "una tarea chica que el gate pueda verificar"
python3 .hermes/harness/scripts/cli.py loop --apply
```

## Leer después

- [`docs/onboarding.md`](docs/onboarding.md) — **empezá acá**: de cero a un arnés vivo, paso a paso, con qué tiene que salir en cada paso.
- [`docs/workshop/README.md`](docs/workshop/README.md) — el workshop de agentes autónomos.
- [`docs/ingenieria-de-loops.md`](docs/ingenieria-de-loops.md) — los lazos de control del agente, y qué hace bueno a un lazo.
- [`docs/loop-autonomo.md`](docs/loop-autonomo.md) — operar el loop.
- [`docs/cli-y-panel.md`](docs/cli-y-panel.md) — la CLI y el panel.
- [`docs/integraciones.md`](docs/integraciones.md) — correo, WhatsApp, navegador, Google, Microsoft, GitHub, bases: catálogo, perfiles, secretos, recursos y dependencias.
- [`docs/hermes.md`](docs/hermes.md) — cómo se engancha a Hermes, verificado contra su código.
- [`CONSTITUTION.md`](CONSTITUTION.md) — los principios y qué comando hace cumplir cada uno.
- [`docs/portar.md`](docs/portar.md) — instalar en otro repo, con plugin o con shell hook.
- [`docs/config-reference.md`](docs/config-reference.md) — cada clave y quién la lee.
- [`docs/desde-claude-code.md`](docs/desde-claude-code.md) — el mapa desde `agent-harness`.
