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
| `gate.signals[]` | `{name, command[], why, fastSkip?, skipIfMissing?, skipIfNoExecutable?, omitIfExit?}` — `why` obligatorio (P6). `omitIfExit`: el código con que la señal dice «no tengo con qué correr» (sale OMITIDA, nunca verde) |
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
| `taint.sources{tools[], readPaths[]}`, `askCommands[]`, `askWrites[]`, `askKinds[]`, `kindsReason`, `innocentAfter[]`, `innocentWritesAfter[]` | la **sesión contaminada**: después de leer contenido de terceros (herramientas web y de navegador de Hermes, o rutas como `tickets/`), lo que tiene efecto afuera escala a un humano —comandos (`askCommands`, también en `execute_code`), escrituras donde una instrucción quedaría permanente (`askWrites`) y guardar memoria, skills o cron (`askKinds`; limpiar no). Sólo el plugin (el shell hook no tiene memoria de la sesión) |
| `integrations.$naming{prefix, sanitize}` | cómo nombra Hermes una herramienta MCP: `mcp__{server}__`, con `[^A-Za-z0-9_]` cambiado por `_` (verificado en `tools/mcp_tool_schema.py`) |
| `integrations.undeclared{pattern, allow, action, reason}` | una herramienta con forma de integración (`^mcp__`) que ninguna declara: `ask` (plantilla), `deny` o pasa. `allow` es una regex de las que pasan igual |
| `integrations.content{classes[], deny[], innocent[]}` | **lo que dice** lo que sale: cada texto de los argumentos de una llamada de clase `classes` (`send`, `write`) —en una integración por CLI, el comando— se compara con `deny` (un secreto, una plantilla sin completar). Frena aunque el destinatario esté en la lista |
| `integrations.enabled.<id>` | una integración MATERIALIZADA del catálogo (`plantillas/integraciones/<id>.json`) por `scripts/integ.py add`. Ver la tabla de abajo |
| `output{redact[], redactWith, innocent[], taintNotice}` | la **respuesta** del turno (`transform_llm_output`): lo que casa con `redact` se reemplaza por `redactWith` antes de mostrarse y guardarse; si la sesión leyó a un tercero, se agrega `taintNotice` al pie (`{fuente}` dice de dónde) |
| `sessionGuard.python` | `true`: la guardia de Python también en las sesiones interactivas de Hermes (fuera del loop). El plugin pone `plugin/guardia` en el `PYTHONPATH` de Hermes y deja el spec en `.git/harness-guardia.json`; sin los intocables del loop. `HARNESS_GUARDIA_OFF=1` la apaga para un comando. Plantilla: `false` (un test que lee el `.env` a propósito se frenaría) |
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
| `loop.defaultIntegrations[]` | las integraciones que una tarea puede usar si no las nombra (`[integraciones: a, b]` en su línea). `[]` = ninguna (plantilla); ausente = todas las habilitadas. El loop las pasa en `HARNESS_INTEGRACIONES` |
| `loop.tasksFile`, `agentCommand`, `gateCommand`, `maxIterations`, `sameFailureLimit`, `maxMinutes`, `agentTimeoutMinutes`, `gateTimeoutMinutes`, `branchPrefix`, `stopFile`, `stateFile`, `prompt`, `retryPrompt`, `reason` | el loop autónomo (P21). Ver [`loop-autonomo.md`](loop-autonomo.md) |
| `drift.statusDatePattern`, `statusMaxAgeDays`, `historyCommits`, `runner`, `command`, `reason` | el barrido de deriva (P20). `runner` es el pipeline que lo corre y `command` lo que ese pipeline tiene que invocar |
| `review.command`, `dataset`, `minRecall`, `minPrecision`, `timeoutSeconds`, `requiresEnv`, `runner`, `runnerCommand`, `reason` | el revisor inferencial medido (`scripts/revision.py`): `command` es el revisor (`{prompt}` lleva el diff y la tarea), `dataset` los diffs etiquetados, los umbrales, y `requiresEnv` la variable que dice que hay un modelo (sin ella, OMITIDA) |
| `taxonomy.stages`, `events`, `gitHooksDir`, `gitHooks`, `gateStages`, `skills`, `guides`, `pieces`, `pipelines` | el mapa guía/freno/sensor (P20): cada pieza con `direction`, `kind` (opcional) y `stage`. Una sin clasificar es rojo |

## Una integración (`integrations.enabled.<id>` y el manifiesto del catálogo)

| Clave | Qué declara |
|---|---|
| `kind`, `server`, `tools`, `command` | `mcp` (con `server`: el prefijo de sus herramientas), `hermes` (con `tools`: regex de herramientas propias de Hermes) o `cli` (con `command`: regex del comando de terminal) |
| `toolNames[]` | lo que el servidor MCP publica, verificado con `integ_run.py --probe`; de acá sale `tools.include` |
| `classes{deny, destructive, send, read}` | regex sobre el nombre crudo (o el comando). Lo que no casa es `write` |
| `thirdParty` | lo que trae contenido de terceros: contamina la sesión |
| `recipientKeys`, `urlKeys`, `fileKeys` | regex de CLAVES de los argumentos (a cualquier profundidad) con destinatarios, URLs y archivos locales. En una CLI: `recipientPattern`, `urlPattern`, `filePattern`, regex con grupos sobre el comando |
| `policy{allowRecipients[], allowDomains[], outsideDomains, denyHosts[], schemes[]}` | a quién se manda, qué dominios se navegan (vacío = cualquiera), qué hacer fuera (`ask`/`deny`), qué hosts nunca, qué esquemas |
| `perfil`, `actions{read, write, send, destructive}` | el perfil elegido y lo que hace con cada clase: `allow` · `ask` · `deny` · `allowlist` (manifiesto: `perfiles{}`, `perfilPorDefecto`) |
| `budget{maxPerHour{clase: n}, maxResultChars, idleMinutes, timeoutSeconds, maxMemoryMB, nice}` | presupuesto por hora, recorte del resultado, apagado por inactividad y techo del proceso |
| `launch{runtime, bin{kind, name}, command, args[], argsPorPerfil{}, env{}}` | cómo arranca el servidor el lanzador; `env` con `secret://…` para los secretos y `{prefix}` para el directorio de la instalación |
| `requires[]` | `{kind: npm·pypi·browser·system, package, version (fija), bin, command, min, hint{}}` |
| `hermes.mcpServer{}` | claves extra para `mcp_servers.<server>` |
| `examples[]` | `{tool | command, args, perfil?, set?, contaminada?, uso?, expect: block·approve·allow, regla?, otroFreno?, why}`: la prueba de vida, por el plugin |
| `reasons{clase}`, `verificado`, `ignoreAnnotations` + `$ignoreAnnotations` | el porqué que lee el agente, qué se verificó y cuándo, y por qué no se le cree a las anotaciones del servidor |

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
| `integrations` | `plugin/harness/integ.py` (por `guards.evaluate`), `plugin/__init__.py` (presupuesto, alcance, recorte), `scripts/integ.py`, `scripts/integ_run.py`, `scripts/doctor.py`, `scripts/drift.py`, `scripts/panel.py`, `scripts/casos.py`, `scripts/selftest.py` |
| `memory.*` | `plugin/harness/guards.py`, `scripts/doctor.py`, `scripts/selftest.py` |
| `skills.*` | `plugin/harness/guards.py`, `plugin/harness/rules.py`, `scripts/doctor.py`, `scripts/selftest.py` |
| `cron.*` | `plugin/harness/guards.py`, `scripts/selftest.py` |
| `routes` | `plugin/harness/turn.py`, `scripts/selftest.py` |
| `output` | `plugin/harness/turn.py` (`respuesta`), `plugin/__init__.py` (`on_transform_llm_output`), `scripts/selftest.py`, `scripts/hermes_e2e.py` |
| `sessionGuard` | `plugin/__init__.py` (`_guardia_de_sesion`), `plugin/guardia/sitecustomize.py` (por el spec), `scripts/doctor.py`, `scripts/selftest.py` |
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
