# De agent-harness (Claude Code) a hermes-harness

Este repo nace de `agent-harness`, el arnés para Claude Code. Los **principios** viajan; los
**mecanismos** se rehicieron para el modelo de extensión de Hermes. Esta tabla es el mapa.

| agent-harness (Claude Code) | hermes-harness (Hermes Agent) | Por qué cambió |
|---|---|---|
| `.claude/settings.json` → hooks `node …` | plugin `repo-harness` (`plugin/`) + shell hook opcional | Hermes es Python y sus plugins corren en proceso: sin un proceso por tool call |
| `.claude/harness.config.json` | `.hermes/harness.config.json` | mismo papel; suma `tools` (nombres de herramientas) |
| `PreToolUse` exit 2 | `pre_tool_call` → `{"action":"block","message"}` | en Hermes un hook que revienta **bloquea**: el envoltorio `_seguro` es obligatorio |
| `PostToolUse` (lint en un proceso) | `transform_tool_result` (lint en proceso, inyectado en el resultado) | el agente ve el hallazgo en el mismo turno |
| `Stop` + `stop_hook_active` | `pre_verify` (tope `max_verify_nudges`) | Hermes ya trae el anti-loop |
| `SessionStart` (stdout, lanza `git`) | `register_system_prompt_section` (lee `.git/HEAD`, sin procesos) | congelada por sesión, cache-safe |
| `UserPromptSubmit` (ruteo) | `pre_llm_call` → `{"context"}` | — |
| `CLAUDE.md` con `@CONSTITUTION.md` | `AGENTS.md` (Hermes no resuelve imports) | y hay que cuidarlo del escáner de inyección |
| `.claude/agents/reviewer.md` | skill `harness-review` + `delegate_task` | Hermes no tiene subagentes con nombre |
| `.claude/commands/*.md` | skills en `.hermes/skills/` (`/gate`, `/lesson`…) | cada skill es un comando en Hermes |
| `bash-guard` | `terminal_guard` (+ `terminal.ask` → aprobación humana) | Hermes no permite sumar patrones de "preguntar" por config |
| `protected-paths` | `protected_paths` (+ `outsideRepo` para `~/.hermes/`) | los secretos y la memoria de Hermes viven fuera del repo |
| — | `memory_guard`, `skill_guard`, `cron_guard` | Hermes **aprende** y **corre desatendido**: P12 y P13 son nuevos |
| — | lint `CONTEXTO` | Hermes descarta un AGENTS.md entero si una línea parece inyección |
| `sampleFromPattern` en el self-test | `example` obligatorio en cada regla | generar una muestra desde un regex es frágil; un ejemplo real además documenta |
| `npm run gate` | `python3 scripts/gate.py` | sin Node en el camino: Hermes ya trae Python |
| `harness-bench` (repos de juguete por stack) | self-test §11: instala cada perfil en un repo temporal y corre su self-test | — |
| `repo-lint` `COHERENCIA` | `rules.rule_coherencia` (en proceso, también sobre lo que escribe el agente) | contra `terminal.deny`, con la misma función que el freno |
| `repo-lint` `PERFIL` | `rules.rule_perfil` | — |
| `hooks-timing.mjs` (fuera del gate) | `scripts/timing.py` (**en** el gate) | los callbacks corren en proceso y miden < 1 ms; en Hermes pasarse de tiempo bloquea |
| `harness-map.mjs` | `scripts/map.py` (en el gate) | la dirección la pone el hook de Hermes, no el evento de Claude Code |
| `drift-check.mjs` + `drift.yml` | `scripts/drift.py` + `.github/workflows/drift.yml` | — |
| `.githooks/pre-push` (bash + node) | `.githooks/pre-push` → `githooks.py pre-push` | la decisión en Python: en Windows un freno sólo de shell desaparece |

## Lo que no se portó (todavía)

- El panel HTML y el eval del revisor: dependían de las transcripciones de Claude Code y de una
  CLI con modelo en CI. En Hermes la fuente equivalente es `~/.hermes/state.db` (SQLite + FTS5);
  queda como trabajo futuro, y el hueco está declarado en `docs/guias-y-sensores.md`.
- `cycle-check` (ramas y prácticas XP, `--verify-red`) y `artifacts-check`: se pueden sumar como
  señales del gate sin tocar el código del arnés.
- El índice de código obligatorio (codegraph): es independiente del agente; se puede sumar como
  señal del gate con `skipIfNoExecutable`.

El porqué de lo que sí se portó y en qué cambió: `docs/decisions/0005-practicas-de-agent-harness.md`.
