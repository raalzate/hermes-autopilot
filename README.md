# Hermes Harness

Un arnés para [Hermes Agent](https://hermes-ai.net/) (Nous Research): reglas de un repo que se
hacen cumplir solas mientras Hermes trabaja en él — en la CLI, en el gateway de mensajería y en
las tareas programadas.

Hermes es un agente que **aprende** (escribe su memoria, crea y parchea skills) y que **corre
desatendido** (cron, Telegram, Slack…). Eso lo hace más útil y también más difícil de gobernar:
lo que aprende mal lo repite en todas las sesiones, y donde corre solo no hay humano para aprobar
un comando peligroso. Este arnés pone frenos en esos dos lugares además de en la terminal y los
archivos, y un gate que define qué es "terminado".

## Qué trae

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
```

## Leer después

- [`docs/onboarding.md`](docs/onboarding.md) — **empezá acá**: de cero a un arnés vivo, paso a paso, con qué tiene que salir en cada paso.
- [`docs/hermes.md`](docs/hermes.md) — cómo se engancha a Hermes, verificado contra su código.
- [`CONSTITUTION.md`](CONSTITUTION.md) — los principios y qué comando hace cumplir cada uno.
- [`docs/portar.md`](docs/portar.md) — instalar en otro repo, con plugin o con shell hook.
- [`docs/config-reference.md`](docs/config-reference.md) — cada clave y quién la lee.
- [`docs/desde-claude-code.md`](docs/desde-claude-code.md) — el mapa desde `agent-harness`.
