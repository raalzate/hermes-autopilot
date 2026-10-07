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

## Qué queda en el repo destino

```
.hermes/harness.config.json   las reglas de ESE repo (arrancan con un piso mínimo, cada una con example)
.hermes/harness/              el código del arnés: harness/, plugin/, scripts/, plantillas/
.hermes/skills/               gate · lesson · new-guardrail · harness-audit · harness-review · harness-port
AGENTS.md  STATUS.md  docs/gotchas.md  .githooks/ (pre-commit · commit-msg · pre-push)
.github/workflows/harness.yml         el gate en CI
.github/workflows/harness-drift.yml   la deriva, semanal (depende del reloj: no va en el gate)
```

`branches.protected` arranca vacío: si el equipo trabaja por PR, poné ahí la rama principal y
`pre-push` frena el empujón directo. `observability.probe.filePath` lo completa el perfil.

Lo que ya existía se reporta con `=` y no se toca. `--upgrade` reemplaza sólo el código de
`.hermes/harness/` (nunca el config, `AGENTS.md`, las skills ni los docs).

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

## Después

Las reglas del repo destino se escriben con **sus** incidentes (skill `lesson`), no copiando las
de otro. El piso que trae la plantilla es lo único universal: no saltarse la verificación, no
autoasignarse YOLO, no desarmar el arnés, no escribir secretos ni la memoria a mano.
