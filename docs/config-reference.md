# Referencia de `.hermes/harness.config.json`

El único archivo específico del repo. Toda regla es un objeto con, al menos:

```json
{ "id": "corto", "pattern": "regex (Python, sin distinguir mayúsculas)", "example": "caso que DEBE frenar",
  "reason": "qué pasó, por qué importa, qué hacer en su lugar" }
```

`example` no es documentación: el self-test lo pasa por el plugin y falla si no frena. Una regla
sin `example` es roja.

## Claves

| Clave | Qué declara |
|---|---|
| `tools.{shell,write,read,code,memory,skill,cron}` | qué herramientas de Hermes le tocan a cada familia de frenos. `read`: `read_file`, `search_files`, `vision_analyze`; `code`: `execute_code` (verificadas contra el código de hermes-agent, 2026-10) |
| `tools.$readArgs`, `tools.$args.code` | qué argumentos de una herramienta de lectura son rutas (`path`, `file_glob` —sin comodines—, `image_url`), y en cuál viene el código de `execute_code` |
| `tools.$args.{command,path,content}` | en qué argumento de la herramienta está el comando, la ruta, el contenido |
| `tools.$multiFilePatch` | `{args[], pathPatterns[], addedLine}` — la gramática V4A del `patch` de Hermes: de dónde salen las rutas y qué líneas se agregan |
| `tools.$written`, `tools.$removeActions` | qué campos de memory/skill_manage/cronjob_manage son lo que se GUARDA, y qué acciones son borrados (no se filtran) |
| `gate.command`, `gate.fastCommand` | cómo se corre el gate (lo nombran los mensajes al agente) |
| `gate.signals[]` | `{name, command[], why, fastSkip?, skipIfMissing?, skipIfNoExecutable?}` — `why` obligatorio (P6) |
| `gate.marker` | el archivo que dice "hay código editado sin gate verde" |
| `gate.codeGlobs`, `gate.codeExtensions` | qué cuenta como código (marca el gate al escribirlo) |
| `gate.installHooksCommand` | lo que el aviso de sesión sugiere si los hooks de git no están |
| `terminal.deny[]` | comandos que se bloquean |
| `terminal.ask[]` | comandos que piden aprobación humana (`{"action":"approve"}`) |
| `terminal.innocent[]` | comandos que NO deben frenar (P3) |
| `terminal.dataArgs[]` | prefijos cuyo texto entre comillas es dato (mensaje de commit, término de búsqueda) y no se compara |
| `terminal.redirectTargets[]` | regex con un grupo: destinos de escritura por la terminal (`>`, `tee`, destino de `cp`/`mv`, argumentos de `rm`, archivo de `sed -i`…), evaluados contra `protectedPaths`. Un grupo con varios argumentos se evalúa token por token (salteando las banderas) |
| `terminal.inlineCode` | `{interpreters, writeMarkers, sendPatterns[], innocent[], codeInnocent[]}`: código en línea (`python3 -c`, `bash -c`…) y `execute_code`. Cada cadena entre comillas se evalúa contra `protectedReads` y, si el código escribe, contra `protectedPaths`; `sendPatterns` (mandar datos desde Python) escala a un humano |
| `terminal.readTargets[]` | igual, para los comandos que LEEN (`cat`, `grep`, `head`, origen de `cp`, `source`, `< archivo`, lo que `curl` sube con `@`): evaluados contra `protectedReads` |
| `moreExamples[]` (en cualquier regla) | variantes que el `reason` dice cubrir; el self-test y el e2e prueban cada una |
| `protectedPaths[]` | rutas que el agente no escribe. `agentOnly: true` = el agente no, el humano sí puede commitearla. `outsideRepo: true` = se evalúa sobre la ruta absoluta (p.ej. `~/.hermes/.env`) |
| `protectedInnocent[]` | rutas que NO deben frenar |
| `protectedReads[]`, `protectedReadsInnocent[]` | lo que el agente no **lee** (lo leído viaja al proveedor del modelo): mismas claves que `protectedPaths`, incluido `outsideRepo`. Lo aplican `read_guard` (sobre `tools.read`) y `readTargets` en la terminal |
| `patterns[]` | regex prohibida en lo que se escribe (multilínea: `^` es cada línea). `paths`/`exceptPaths` la acotan; `examplePath` es dónde se prueba el ejemplo y `exceptExample` una ruta de `exceptPaths` donde NO debe frenar |
| `memory.deny[]`, `memory.innocent[]` | lo que no entra a la memoria persistente |
| `skills.roots`, `namePattern`, `maxName`, `maxDescription`, `maxBodyChars` | forma de las skills versionadas |
| `skills.deny[]`, `skills.inheritTerminalDeny`, `skills.innocent[]` | lo que una skill escrita por el agente no puede enseñar |
| `cron.deny[]`, `cron.minIntervalMinutes`, `cron.exampleTooFrequent`, `cron.moreTooFrequent[]`, `cron.scheduleArgs`, `cron.innocent[]` | lo que una tarea programada no puede hacer |
| `routes[]` | `{id, pattern, example, hint}` — pista que se suma al turno si el pedido casa |
| `context.files`, `maxChars`, `blockedPatterns[]` | archivos de contexto de Hermes: tope y patrones del escáner |
| `invariants[]` | `{file, mustContain[], mustNotContain[], reason}` |
| `incidents` | `{file, heading, requiredLines[]}` — formato de `docs/gotchas.md` |
| `docs.pathRoots`, `externalPaths`, `ignoreFiles` | qué backticks cuentan como rutas del repo en el link-check |
| `status.file`, `headLines`, `reminder` | lo que la sección de estado muestra al abrir la sesión |
| `tracker.issuePattern`, `issueExample` | qué cuenta como referencia a un ítem de trabajo |
| `commitMsg.codePattern`, `ignoreExtensions`, `escapeLine`, `skipSubjects` | qué commits piden registro y cómo se declara la excepción |
| `lint.ignore[]` | rutas que el lint no barre |
| `profiles.dir`, `requiredKeys`, `forbiddenKeys`, `reason` | regla `PERFIL`: un perfil de stack lleva hechos del lenguaje, no reglas (P17). Una clave con punto (`gate.signals`) es una ruta anidada |
| `coherence.guides`, `commandPattern`, `configKeys`, `shellFences`, `configFile`, `reason` | regla `COHERENCIA` (P18): los comandos de los bloques de shell de las guías y los citados entre backticks en `configKeys` no pueden casar con `terminal.deny`. Sin `commandPattern` no corre |
| `branches.protected[]`, `reason` | ramas a las que `.githooks/pre-push` no deja empujar directo. Vacío = el freno no corre |
| `observability.budgetMs`, `runs`, `budgets{}`, `probe{command, filePath, content, prompt}`, `reason` | presupuesto de latencia de cada callback del plugin (P19); `probe.filePath` tiene que ser código |
| `observability.events{file, maxBytes}` | el registro de eventos (P22): una línea JSON por bloqueo, escalada, hallazgo, gate y vuelta del loop, bajo `.git/`. Rota pasado `maxBytes`. Sin `events` no se escribe nada |
| `loop.aislar` | `true`: cada tarea corre en su `git worktree` (bajo `.git/harness-worktrees/`), donde lo ignorado por git (el `.env`) no existe. Un caso puede apagarlo (`loop` en su `caso.json`) |
| `loop.guardiaPython` | `true`: los procesos Python del agente cargan la guardia (`plugin/guardia`, audit hook): lo que ABREN se compara con `protectedReads`, `protectedPaths` y `lockedPaths` del repo |
| `loop.lockedPaths[]` | regex de rutas que el agente no puede cambiar DURANTE una tarea por ningún canal (su config, su cola, `.env`), aunque estén ignoradas por git. Junto con los `protectedPaths` versionados, el loop las compara antes y después de cada intento: si cambió alguna, escala aunque el gate dé verde |
| `loop.tasksFile`, `agentCommand`, `gateCommand`, `maxIterations`, `sameFailureLimit`, `maxMinutes`, `agentTimeoutMinutes`, `gateTimeoutMinutes`, `branchPrefix`, `stopFile`, `stateFile`, `prompt`, `retryPrompt`, `reason` | el loop autónomo (P21). Ver [`loop-autonomo.md`](loop-autonomo.md) |
| `drift.statusDatePattern`, `statusMaxAgeDays`, `historyCommits`, `runner`, `command`, `reason` | el barrido de deriva (P20). `runner` es el pipeline que lo corre y `command` lo que ese pipeline tiene que invocar |
| `taxonomy.stages`, `events`, `gitHooksDir`, `gitHooks`, `gateStages`, `skills`, `guides`, `pieces`, `pipelines` | el mapa guía/freno/sensor (P20): cada pieza con `direction`, `kind` (opcional) y `stage`. Una sin clasificar es rojo |

## Quién lee cada clave

Tocar una clave sin mirar esta tabla es la forma de romper algo lejos.

| Clave | Lee |
|---|---|
| `tools` | `plugin/harness/core.py` (`tool_kind`, `command_of`, `paths_of`, `content_of`, `written_text`), `scripts/selftest.py`, `scripts/hermes_e2e.py` |
| `gate.*` | `scripts/gate.py`, `plugin/harness/core.py` (`is_code`, `marker_path`), `plugin/harness/turn.py`, `scripts/selftest.py` |
| `terminal.*` | `plugin/harness/guards.py` (`terminal_guard`, `skill_guard`), `scripts/selftest.py`, `plugin/__init__.py` (`/harness`) |
| `protectedPaths`, `protectedInnocent` | `plugin/harness/guards.py`, `scripts/githooks.py`, `scripts/loop.py` (intocables), `scripts/selftest.py` |
| `protectedReads`, `protectedReadsInnocent` | `plugin/harness/guards.py` (`read_guard`, `terminal_guard`), `scripts/cli.py`, `scripts/selftest.py` |
| `patterns` | `plugin/harness/guards.py`, `plugin/harness/rules.py`, `scripts/selftest.py` |
| `memory.*` | `plugin/harness/guards.py`, `scripts/doctor.py`, `scripts/selftest.py` |
| `skills.*` | `plugin/harness/guards.py`, `plugin/harness/rules.py`, `scripts/doctor.py`, `scripts/selftest.py` |
| `cron.*` | `plugin/harness/guards.py`, `scripts/selftest.py` |
| `routes` | `plugin/harness/turn.py`, `scripts/selftest.py` |
| `context.*` | `plugin/harness/rules.py`, `scripts/lint.py`, `scripts/selftest.py` |
| `invariants`, `incidents`, `lint` | `plugin/harness/rules.py`, `scripts/lint.py`, `scripts/selftest.py` |
| `docs.*` | `scripts/linkcheck.py` |
| `status.*` | `plugin/harness/turn.py` |
| `tracker`, `commitMsg` | `scripts/githooks.py`, `scripts/selftest.py` |
| `profiles` | `plugin/harness/rules.py` (`rule_perfil`), `scripts/lint.py`, `scripts/selftest.py` |
| `coherence` | `plugin/harness/rules.py` (`rule_coherencia`, `es_guia`), `scripts/lint.py`, `scripts/selftest.py` |
| `branches` | `scripts/githooks.py` (`pre_push`), `scripts/selftest.py` |
| `observability` | `scripts/timing.py`, `scripts/install.py` (`probe.filePath` desde el perfil), `scripts/selftest.py`; `events`: `plugin/harness/events.py`, `scripts/gate.py`, `scripts/loop.py`, `scripts/panel.py` |
| `loop` | `scripts/loop.py`, `scripts/panel.py`, `scripts/cli.py` (`task`, y `gateCommand` como inocente de `rule add`), `scripts/selftest.py` |
| `drift` | `scripts/drift.py`, `scripts/selftest.py` (que el `runner` invoque el `command`) |
| `taxonomy` | `scripts/map.py`, `scripts/panel.py` (salud), `scripts/selftest.py` |

Todas las claves también las lee y escribe `scripts/cli.py` (`config get|set`, `rule`, `signal`).
La CLI prueba cada regla antes de escribirla: ver [`cli-y-panel.md`](cli-y-panel.md).
