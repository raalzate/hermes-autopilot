# El arnés de este repo

Qué guía, qué freno y qué sensor actúa en cada momento del trabajo con Hermes, y qué comando lo
prueba. Si una fila no tiene comando, no es un freno: es una esperanza.

| Momento | Pieza | Tipo | Prueba de vida |
|---|---|---|---|
| abrir la sesión | `AGENTS.md` (contexto de proyecto) | guía | lint `CONTEXTO` (tope + escáner de Hermes) |
| abrir la sesión | sección `repo-harness.status` (rama, hooks de git, gate pendiente, `STATUS.md`) | guía | self-test §6 |
| cada pedido | `routes` → `pre_llm_call` | guía | self-test §6 (el `example` de cada ruta) |
| antes de `terminal` | `terminal.deny` / `terminal.ask` | freno | self-test §3 (cada `example`, + `innocent`) |
| antes de `write_file`/`patch` | `protectedPaths`, `patterns` | freno | self-test §3 (+ symlink interno, + rutas de Windows) |
| antes de `memory` | `memory.deny` | freno | self-test §3 |
| antes de `skill_manage` | `skills.deny` + `terminal.deny` heredado | freno | self-test §3 |
| antes de `cronjob_manage` | `cron.deny`, `cron.minIntervalMinutes` | freno | self-test §3 |
| después de escribir | lint del archivo → `transform_tool_result`; marca el gate | sensor | self-test §6 |
| cerrar el turno | `pre_verify` con el gate pendiente | freno | self-test §6 |
| commit | `.githooks/pre-commit` (rutas protegidas + lint), `commit-msg` (registro) | freno | self-test §9 (funciones + git real) |
| push | `.githooks/pre-push` (`branches.protected`: a main se entra por PR) | freno | self-test §12 (función + push real a un remoto temporal) |
| escribir una guía | lint `COHERENCIA`: lo que `AGENTS.md`, `docs/` o una skill recomiendan en un bloque de shell no puede estar en `terminal.deny` | sensor | self-test §12 (cada `example` de `terminal.deny` recomendado en una guía) |
| escribir un perfil | lint `PERFIL`: un perfil de stack no trae reglas (`profiles.forbiddenKeys`) | sensor | self-test §12 y §11 (los perfiles reales) |
| entregar | `scripts/gate.py` | freno | es el gate; CI lo corre igual |
| el self-test mismo | `scripts/mutations.py` — 38 mutaciones (frenos, config, cada hallazgo de la revisión y cada pieza traída de agent-harness) | sensor | señal del gate: cada una tiene que poner rojo el self-test |
| el arnés entero | `scripts/map.py` — cada pieza con dirección (guía · freno · sensor), tipo y etapa desde `taxonomy` | sensor | señal del gate: una pieza sin clasificar es rojo |
| el costo | `scripts/timing.py` — la mediana de cada callback del plugin contra `observability.budgetMs` | sensor | señal del gate; self-test §12 (con presupuesto 0 tiene que salir rojo) |
| continuo (semanal) | `scripts/drift.py` por `.github/workflows/drift.yml`: `STATUS.md` vencido = rojo, regla que nunca cazó nada = aviso | sensor | self-test §12 (que el `runner` invoque el comando, y los casos de fecha e historial) |
| esta máquina | `scripts/doctor.py` | sensor | a mano / skill `harness-audit` |
| el Hermes real: carga | `hermes plugins doctor plugin --ci` | sensor | señal del gate (OMITIDA sin Hermes) |
| el Hermes real: contrato | `scripts/hermes_e2e.py` — cada `example` por `get_pre_tool_call_directive`, `pre_verify`, `pre_llm_call`, `transform_tool_result` y la sección del prompt, dentro de Hermes | sensor | señal del gate (OMITIDA sin Hermes) |

## Por qué el self-test no necesita Hermes

Los frenos son funciones puras; el plugin se carga con un `ctx` falso que respeta las firmas de
`hermes_cli/plugins.py` y rechaza lo mismo que Hermes (ids de sección inválidos, `max_chars` > 4000).
Además el self-test carga el plugin desde una **copia** de su directorio y como paquete
registrado en `sys.modules`, igual que `hermes_cli/plugins_loader.py`.

Lo que sólo el Hermes real puede probar lo prueban dos señales que salen OMITIDAS donde Hermes no
está (omitido no es verde): `hermes plugins doctor` (el manifiesto y `register(ctx)` encajan con la
versión instalada) y `scripts/hermes_e2e.py` (las decisiones del arnés sobreviven al código de
Hermes que las interpreta). El e2e corre con el intérprete de Hermes —lo lee del shebang de
`hermes`— sobre una copia del repo y un `HERMES_HOME` temporal, y no ejecuta ninguna herramienta.

## Deuda conocida

- La terminal escribe archivos de muchas formas: el freno ve las redirecciones (`>`, `>>`, `tee`),
  no `cp x .env`, `mv`, ni un `python -c` que abra el archivo. Para eso está el pre-commit (lo
  protegido no entra al historial) y el `approvals.deny` de Hermes.
- El shell hook no puede pedirle a Hermes el cwd de la sesión (corre en otro proceso): usa
  `workdir`, `TERMINAL_CWD` o el cwd del proceso. El plugin sí lo pide.
- La lista `context.blockedPatterns` es una copia a mano de un subconjunto del escáner de Hermes:
  si Hermes suma un patrón, el lint no lo sabe hasta que alguien lo copie.
- `doctor.py` lee `config.yaml` con regex (sin PyYAML): entiende las dos formas de lista que
  escribe Hermes; una forma más rara sale como "no encontrado", no como falso verde.
