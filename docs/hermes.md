# Cómo se engancha el arnés a Hermes

Todo lo de esta página está **verificado contra el código** de `NousResearch/hermes-agent`
(HEAD `47676981`, 2026-09-30) y no contra la documentación: donde las dos difieren, gana el código
y se anota. Si Hermes cambia, esta página y la señal `hermes plugins doctor` del gate son las que
se enteran primero.

## Los puntos de extensión que usa el arnés

| Necesidad del arnés | Mecanismo de Hermes | Lo usa | Contrato |
|---|---|---|---|
| frenar una herramienta antes de que corra | hook de plugin `pre_tool_call` | `plugin/__init__.py` → `plugin/harness/guards.py` | devolver `{"action": "block", "message"}`. **Sin `message` Hermes lo ignora.** El mensaje llega al modelo como resultado de la herramienta (`error_type: plugin_block`) |
| pedir aprobación humana para un patrón propio | `pre_tool_call` → `{"action": "approve", "message", "rule_key"}` | `terminal.ask` | escala al gate de aprobación de Hermes; en cron/gateway sin humano, se niega. Hermes **no** tiene una clave de config para sumar patrones de "preguntar" (sólo `approvals.deny`, que prohíbe) |
| lint del archivo recién escrito | hook `transform_tool_result` | `turn.after_write` | el primer `str` devuelto reemplaza el resultado que ve el modelo; `None` lo deja igual |
| no cerrar el turno con el gate pendiente | hook `pre_verify` | `turn.verify` | `{"action": "continue", "message"}` suma un turno sintético. **Sólo se dispara si el turno editó archivos**, y como mucho `agent.max_verify_nudges` (3) veces |
| estado verificado al abrir la sesión | `ctx.register_system_prompt_section` | `turn.session_status` | ≤ 4000 caracteres (Hermes **rechaza**, no trunca), se congela por sesión |
| pistas según lo que pide el humano | hook `pre_llm_call` | `turn.route` | `{"context": str}` se suma al mensaje del usuario, nunca al system prompt |
| `/harness` | `ctx.register_command` | `plugin.cmd_harness` | `handler(raw_args) -> str` |

Fuentes: `hermes_cli/plugins.py` (`register_hook`, `register_system_prompt_section`,
`_get_pre_tool_call_directive_details`, `get_pre_verify_continue_message`), `model_tools.py`
(`_apply_transform_tool_result_hook`), `agent/turn_stop_gates.py` (`_pre_verify_nudge`),
`hermes_cli/plugins_dispatch.py` (topes de secciones).

## La diferencia que más importa: `pre_tool_call` falla CERRADO

En Hermes, un callback de `pre_tool_call` que **lanza una excepción o se pasa de tiempo bloquea
la herramienta** (`_HOOK_TIMEOUT_FAIL_CLOSED_HOOKS = {"pre_tool_call"}`). Los demás hooks fallan
abiertos. En Claude Code pasaba lo contrario: un hook roto no bloqueaba nada.

Consecuencia: un arnés con un bug no es un arnés que "no frena", es un arnés que **frena todo**, y
ése se desinstala en una tarde. Por eso cada callback del plugin pasa por `_seguro` (atrapa todo y
devuelve `None`), y el lint exige que exista (`invariants` sobre `plugin/__init__.py`). El
self-test lo prueba con un freno que divide por cero y con el núcleo entero roto.

## Plugin o shell hook

| | Plugin (`plugin/`) — recomendado | Shell hook (`scripts/hook.py`) |
|---|---|---|
| dónde se declara | `~/.hermes/plugins/repo-harness/` + `plugins.enabled` | `hooks:` en `~/.hermes/config.yaml` |
| costo por tool call | una llamada de función | un proceso de Python |
| consentimiento | habilitar el plugin (opt-in) | Hermes pregunta la primera vez por cada `(evento, comando)`; en gateway/cron hace falta `hooks_auto_accept` o `HERMES_ACCEPT_HOOKS=1` |
| si revienta | `_seguro` → deja pasar | exit ≠ 2 y stdout no-JSON → deja pasar (salvo `fail_closed: true`) |
| lint tras escribir | se inyecta en el resultado (`transform_tool_result`) | queda en el log (`post_tool_call` es sólo observador) |

Contrato del shell hook (`agent/shell_hooks.py`): stdin JSON con `hook_event_name`, `tool_name`,
`tool_input`, `session_id`, `cwd`, `extra`; `matcher` es un regex con **fullmatch** sobre el
nombre de la herramienta; **exit 2 bloquea** sólo en `pre_tool_call`; **exit 1 no bloquea**.

Los plugins de proyecto (`<repo>/.hermes/plugins/`) sólo cargan con
`HERMES_ENABLE_PROJECT_PLUGINS=1`; por eso el instalador enlaza el plugin en el `HERMES_HOME` del
usuario y el plugin lee el config del repo en el que Hermes está trabajando (sin config, no hace
nada).

## Las herramientas que miran los frenos

Nombres y argumentos de hermes-agent 2026-09, declarados en `tools` del config (no en el código):

| Familia | Herramienta | Argumentos que se inspeccionan |
|---|---|---|
| `shell` | `terminal` | `command` (sin el texto de `-m`, `grep`… que es dato: `terminal.dataArgs`), sus redirecciones `>`/`tee` contra `protectedPaths`, y `workdir` |
| `write` | `write_file`, `patch` | `path`, `content` / `new_string` y, en el modo **V4A** de `patch` (sin `path`), cada `*** Update/Add/Delete/Move File:` y sus líneas `+` (`tools.$multiFilePatch`) |
| `memory` | `memory` | sólo lo que se **guarda** (`content`); `remove` y el `old_text` no se miran: sacar un secreto tiene que poder hacerse |
| `skill` | `skill_manage` | lo que se escribe dentro de `operations[]` (`content`, `new_string`, `file_content`); `delete`/`remove_file` no se miran |
| `cron` | `cronjob_manage` | `prompt`, `script`, `schedule` (`30m`, `every 2h`, `every 30s`, `in 5m`, cron con listas, rangos y pasos) |

**El directorio de la sesión, no el del proceso.** Hermes resuelve las rutas relativas de sus
herramientas contra el cwd de la SESIÓN (se mueve con cada `cd` en la terminal), y el gateway, cron
y Desktop arrancan el proceso en otro lado. El plugin le pide ese cwd a Hermes
(`tools.file_tools_paths._authoritative_workspace_root(task_id)`, con `TERMINAL_CWD` de respaldo) y
busca el config del repo desde ahí. El shell hook, que corre en otro proceso, sólo tiene
`workdir`, `TERMINAL_CWD` y el cwd del proceso: por eso el plugin es el camino recomendado.

Las herramientas de un MCP llegan como `mcp_<servidor>_<herramienta>`: si una escribe archivos,
se suma a `tools.write` y los frenos de rutas la ven sin tocar código.

## Contexto: qué archivo carga Hermes de verdad

Hermes carga **un solo tipo** de contexto de proyecto, el primero que exista
(`agent/prompt_builder.py`):

1. `.hermes.md` / `HERMES.md` (el más cercano, del cwd a la raíz git);
2. la cadena de `AGENTS.md` de la raíz git al cwd;
3. `CLAUDE.md` — **sólo en el cwd**;
4. `.cursorrules`.

Consecuencias que el arnés vigila:

- **Un `.hermes.md` tapa a `AGENTS.md`**: las reglas quedan afuera. `doctor.py` lo marca rojo.
- **`CLAUDE.md` no resuelve `@imports`** y sólo vale si no hay `AGENTS.md`. El instalador avisa.
- **Truncado:** piso de 20 000 caracteres (70 % cabeza, 20 % cola). Regla `CONTEXTO` del lint.
- **Escáner de inyección** (`tools/threat_patterns.py`): si **una línea** casa, Hermes reemplaza
  el archivo **entero** por `[BLOCKED: …]` y el agente arranca sin reglas. Frases que parecen
  benignas en la documentación de un arnés alcanzan (un ejemplo de leer un secreto con cat, un
  comentario HTML que mencione al sistema, ciertas frases imperativas en inglés). `context.blockedPatterns`
  copia ese subconjunto y el lint lo caza antes de que llegue a Hermes.

## Aprendizaje: memoria y skills

- `~/.hermes/memories/MEMORY.md` (2200 caracteres) y `USER.md` (1375) entran congelados al
  prompt de cada sesión. Hermes **rechaza** escrituras sobre el tope (no compacta). El freno
  `memory_guard` filtra secretos y "reglas" que contradicen a un freno; `doctor.py` avisa el uso y
  detecta lo que ya estaba guardado antes de instalar el arnés.
- Skills: `<git-root>/.hermes/skills/` (y `.agents/skills/`) cargan **sólo tras
  `hermes skills trust`**. Nombre `^[a-z0-9][a-z0-9._-]*$` ≤ 64, descripción ≤ 1024
  (`tools/skill_manager_tool.py`). El agente las crea con `skill_manage`; `skill_guard` le aplica
  `terminal.deny` a lo que enseñan.

## Hermes desde el código fuente (y por qué no el de PyPI)

El arnés se verificó contra el código de `NousResearch/hermes-agent` (commit `aa74e184`, 2026.9.24).
Hermes no publica wheels de su rama principal (el build los rechaza a propósito) y el paquete de
PyPI va meses atrás: la 0.19.0 no tiene `hermes plugins doctor` ni `register_system_prompt_section`.
El plugin tolera esa versión (el estado al abrir la sesión simplemente no aparece), pero el gate
la prueba contra la que corresponde:

```bash
python3 scripts/hermes_fuente.py ~/hermes-dev            # clon + venv + un `hermes` del clon
export PATH=~/hermes-dev/bin:$PATH HERMES_HOME=~/hermes-dev/home
python3 scripts/gate.py                                  # las dos señales de Hermes ya no salen OMITIDAS
```

CI hace lo mismo en el job `hermes-real`, en cada PR: `hermes plugins doctor` y el e2e del
contrato corren de verdad. El pipeline `hermes-nocturno.yml` usa el mismo Hermes para medir al
revisor inferencial con un modelo (necesita el secreto `HERMES_ENV`).

## Lo que Hermes ya hace y el arnés no duplica

- `approvals.deny` (globs que bloquean aun con `--yolo`) y los `HARDLINE_PATTERNS`: el piso de
  Hermes. `terminal.deny` suma las cicatrices **del repo**.
- Checkpoints (`/rollback`): la reversibilidad de archivos. El arnés sigue exigiendo dry-run en
  acciones amplias (P9) porque un checkpoint no deshace un `git push`.
- `security.protected_instruction_files`: `write_file` a `AGENTS.md`/`CLAUDE.md` siempre pide
  aprobación. `.hermes.md` no está en esa lista por defecto (`doctor.py` lo avisa).
