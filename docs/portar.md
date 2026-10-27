# Portar el arnés a otro repo

```bash
python3 scripts/install.py ~/code/mi-repo --profile python          # DRY-RUN: sólo la lista
python3 scripts/install.py ~/code/mi-repo --profile python --apply  # ejecuta; nunca sobreescribe
```

Perfiles disponibles (`plantillas/perfiles/`): `python`, `node`, `front`, `go`, `rust`, `dotnet`,
`jvm-maven`, `jvm-gradle`. Un perfil trae **hechos del stack** —qué extensión es código, qué es
derivado (lockfiles, `target/`, `node_modules/`), cómo se corren los tests— y nunca reglas de
otro repo. El self-test del repo destino falla si no quedó nada declarado como código: sin eso,
el gate pendiente nunca se marca y `pre_verify` no frena nada.

`--forge` (`plantillas/forges/`: `github` por defecto, `gitlab`, `azure`) elige el pipeline que se
instala (GitHub Actions, `.gitlab-ci.yml`, `azure-pipelines.yml`, todos con el mismo gate) y el
formato de la referencia a un issue en los commits. Para varios repos con un proyecto de gestión
que orquesta, no instales uno por uno: [`workspace.md`](workspace.md) (`workspace.py add` instala
cada codificador con su perfil, su forja y su agente).

## Qué queda en el repo destino

```
.hermes/harness.config.json   las reglas de ESE repo (arrancan con un piso mínimo, cada una con example)
.hermes/harness/              el código del arnés: harness/, plugin/, scripts/, plantillas/
.hermes/skills/               gate · lesson · new-guardrail · harness-audit · harness-review · harness-port
.hermes/loop/tasks.md         la cola del loop autónomo (vacía)
AGENTS.md  STATUS.md  docs/gotchas.md  .githooks/ (pre-commit · commit-msg · pre-push)
.github/workflows/harness.yml         el gate en CI
.github/workflows/harness-drift.yml   la deriva, semanal (depende del reloj: no va en el gate)
```

`branches.protected` arranca vacío: si el equipo trabaja por PR, poné ahí la rama principal y
`pre-push` frena el empujón directo. También es lo que hace que el loop autónomo abra una rama
`loop/…` en vez de trabajar sobre `main`. `observability.probe.filePath` lo completa el perfil, y
`observability.events` (el registro que lee el panel) viene encendido. El loop arranca **aislado**
(`loop.aislar`: cada tarea en su worktree, sin los secretos ignorados) y con la **guardia de
Python** (`loop.guardiaPython`), y la sesión contaminada (`taint`) viene con las herramientas web
de Hermes y las rutas `tickets/`, `inbox/`, `correos/`: ajustá esas rutas a las de tu repo.

Todo se parametriza con la CLI del repo instalado: `python3 .hermes/harness/scripts/cli.py`.
Ver [`cli-y-panel.md`](cli-y-panel.md).

Lo que ya existía se reporta con `=` y no se toca. `--upgrade` reemplaza sólo el código de
`.hermes/harness/` (nunca el config, `AGENTS.md`, las skills ni los docs).

**Un parche local no se pierde.** El instalador deja `.hermes/harness/huellas.json` con el sha256
de lo que escribió. Si el repo cambió después un archivo del arnés, `--upgrade` lo marca con `!` y
no escribe nada. Lo mismo si no hay huellas (una instalación anterior) y el archivo difiere de esta
versión. Mirá el `diff`; si el arreglo le sirve a otros repos, subilo a hermes-autopilot y después
corré con `--pisar`. Las integraciones propias del repo van en `.hermes/integraciones/<id>.json`, fuera del
código del arnés ([integraciones](integraciones.md#agregar-una-integración-al-catálogo)).

## Si el repo se despliega

Un agente que corre en producción (un contenedor, sin `.git` ni shell estable) necesita tres cosas
más. Las probó el piloto doctiling-sre ([ADR 0014](decisions/0014-piloto-en-produccion.md)):

1. **Estado fuera de git.** `HARNESS_EVENTS_FILE` y `HARNESS_AUTONOMIA_FILE` apuntando a un
   volumen. Sin eso el registro y el nivel se pierden en cada deploy, y los días en el nivel no
   corren.
2. **Firmar por PR.** `autonomia.firmadas` (por defecto `config/autonomia.json`) y
   `cli.py nivel aplicar` en el arranque de la imagen ([autonomía](autonomia.md#producción-sin-shell-ni-git)).
3. **Un sandbox antes de salir.** Los tests prueban el código, no la imagen. Una señal del gate
   que construya la imagen de producción, la corra en dry-run con la configuración real y verifique
   que Hermes cargó los plugins (`hermes plugins list`: `enabled` y ningún `Skipping`), un ciclo de
   punta a punta y lo que manda. La evidencia queda atada al hash del árbol: un cambio después la
   invalida. Sin el motor de contenedores (en CI), la señal sale **omitida**, y omitida no es verde.

## Lo que hace el humano

El instalador no edita `~/.hermes/config.yaml`: decide qué frenos y qué aprobaciones existen, y
eso es del humano.

```bash
cd ~/code/mi-repo
python3 .hermes/harness/scripts/githooks.py install
hermes skills trust .
python3 .hermes/harness/scripts/install.py . --link-plugin          # dry-run del enlace
python3 .hermes/harness/scripts/install.py . --link-plugin --apply  # $HERMES_HOME/plugins/repo-harness
hermes plugins enable repo-harness
python3 .hermes/harness/scripts/gate.py
python3 .hermes/harness/scripts/doctor.py
```

Un solo plugin enlazado sirve a todos los repos de la máquina: lee el config del repo en el que
Hermes está trabajando, y en un repo sin config no hace nada. `doctor.py` avisa si el plugin
apunta al código de otro repo.

## Sin plugins: el shell hook

Si la política del equipo no permite plugins, el mismo núcleo corre como shell hook. En
`~/.hermes/config.yaml`:

```yaml
hooks:
  pre_tool_call:
    - matcher: "terminal|write_file|patch|memory|skill_manage|cronjob_manage"
      command: "python3 /ruta/a/mi-repo/.hermes/harness/scripts/hook.py"
  post_tool_call:
    - matcher: "write_file|patch"
      command: "python3 /ruta/a/mi-repo/.hermes/harness/scripts/hook.py"
  pre_verify:
    - command: "python3 /ruta/a/mi-repo/.hermes/harness/scripts/hook.py"
```

Hermes pide consentimiento la primera vez; en gateway y cron hace falta `hooks_auto_accept` o
`HERMES_ACCEPT_HOOKS=1`. Para probarlo:

```bash
echo '{"args": {"command": "git status"}}' > /tmp/p.json
hermes hooks test pre_tool_call --for-tool terminal --payload-file /tmp/p.json
```

Ojo: `--payload-file` son los *kwargs* del hook, así que los argumentos de la herramienta van
bajo `args`. Un JSON con `command` suelto termina en `extra`, el hook no ve ningún comando y deja
pasar: parece un freno roto y es un payload mal armado.

## Integraciones

El instalador copia el catálogo (`.hermes/harness/plantillas/integraciones/`) y la plantilla trae
`integrations` sin ninguna habilitada, con `undeclared: ask`. Habilitarlas es un paso del humano:
[`integraciones.md`](integraciones.md). El lock (`.hermes/integraciones.lock`) va versionado.

## Después

Las reglas del repo destino se escriben con **sus** incidentes (skill `lesson`), no copiando las
de otro. El piso que trae la plantilla es lo único universal: no saltarse la verificación, no
autoasignarse YOLO, no desarmar el arnés, no escribir secretos ni la memoria a mano.
