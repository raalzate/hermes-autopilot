# AGENTS.md — Hermes Autopilot

Hermes carga este archivo en cada sesión de este repo. Los principios que no se negocian están en
`CONSTITUTION.md` (Hermes no resuelve imports: leelo cuando la tarea toque el arnés).

## Qué es este repo

El producto **es el arnés de un agente autónomo**: un plugin de Hermes, frenos, gate, self-test,
skills, un loop de tareas, una CLI, un panel en vivo y docs para que otro repo —en cualquier
lenguaje— tenga reglas que se hacen cumplir solas cuando lo trabaja Hermes Agent, con o sin un
humano mirando. Es el hermano de `agent-harness` (hecho para Claude Code), rehecho para el modelo de
extensión de Hermes. Python de la biblioteca estándar, sin dependencias.

Este repo se audita a sí mismo: si algo acá no cumple lo que el arnés predica, eso **es** el bug.

## Arquitectura en una frase

`.hermes/harness.config.json` declara las reglas; `plugin/harness/` las decide con funciones puras;
`plugin/__init__.py` y `scripts/hook.py` son dos adaptadores finos al contrato de Hermes.

```
.hermes/harness.config.json  la única fuente de especificidad (reglas, rutas, nombres de herramientas)
plugin/                      el plugin `repo-harness`: pre_tool_call · transform_tool_result · pre_verify · pre_llm_call
plugin/harness/              núcleo puro, DENTRO del plugin: core · guards (frenos) · integ (integraciones) · rules (lint) · turn (turno) · events (registro)
plugin/guardia/              la guardia de Python (audit hook PEP 578) que el loop carga en cada proceso Python del agente
scripts/hook.py              el mismo núcleo como shell hook de Hermes (para quien no habilita plugins)
scripts/gate.py              ejecuta gate.signals; no sabe de stacks
scripts/selftest.py          prueba de vida: los casos salen del `example` de cada regla
scripts/lint.py              7 clases de regla; CONTEXTO evita que Hermes descarte AGENTS.md, COHERENCIA que una guía recomiende lo que un freno veda
scripts/install.py           instalador en otro repo (dry-run por defecto, perfil de stack)
scripts/mutations.py         la prueba de vida del self-test: cada mutación tiene que ponerlo rojo
scripts/map.py               el arnés como sistema de control: guía · freno · sensor por etapa (`taxonomy`)
scripts/timing.py            el costo: latencia de cada callback contra su presupuesto (en Hermes, pasarse bloquea)
scripts/drift.py             lo que se degrada sin que ningún cambio lo rompa (semanal, fuera del gate)
scripts/hermes_e2e.py        cada `example` por el despacho del Hermes REAL (señal del gate; OMITIDA sin Hermes)
scripts/doctor.py            lo que el gate no ve: el Hermes de esta máquina
scripts/loop.py              el lazo de la tarea: tarea → agente → gate; el mismo rojo escala (P21)
scripts/cli.py               parametrizar sin editar JSON: `rule add` prueba la regla ANTES de escribirla
scripts/panel.py             el panel en vivo (SSE, 127.0.0.1) sobre el registro de eventos (P22)
scripts/integ.py             las integraciones: catálogo, `add` prueba ANTES de escribir, dependencias aisladas con lock, `check` en el gate
scripts/integ_run.py         el lanzador de un servidor MCP: secretos `secret://` sólo en su entorno, límites, `--probe` contra el servidor real
scripts/casos.py             22 casos replicables de punta a punta (P23): casos/<id>/, agente de juguete, plugin real
scripts/revision.py          el revisor inferencial medido: recall y precisión contra evals/revision.json (P25)
scripts/hermes_fuente.py     Hermes desde su código fuente, en el commit verificado (CI: job hermes-real)
.hermes/loop/tasks.md        la cola del loop autónomo
.hermes/skills/              gate · lesson · new-guardrail · harness-audit · harness-review · harness-port
plantillas/                  lo que se copia al repo destino, los perfiles de stack y el catálogo de integraciones
docs/                        lo que se lee
```

## Reglas de desarrollo

- **Nada específico de un repo, de un lenguaje ni de una versión de Hermes entra al código.** Un
  literal de dominio, una extensión o un nombre de herramienta va al config. El lint lo verifica
  sobre `plugin/harness/guards.py`.
- **Toda regla del config trae `example`**, y el self-test lo pasa por el plugin real. Una clase de
  regla nueva o un freno nuevo llega con su caso escrito a mano en `scripts/selftest.py` y una
  mutación en `scripts/mutations.py`. Una pieza nueva (hook, skill, pipeline) se ubica en `taxonomy`.
- **Validación doble, siempre:** `python3 scripts/selftest.py` (¿muerde?) y `python3 scripts/lint.py`
  (¿no muerde de más?). La segunda es la que se olvida.
- **El plugin nunca lanza.** En Hermes, un `pre_tool_call` que lanza o se pasa de tiempo **bloquea**
  la herramienta. Todo callback pasa por `_seguro`: un arnés roto deja pasar.
- **Los frenos no lanzan procesos.** Corren en cada tool call, dentro del proceso de Hermes.
- **Shell hook: exit 2 bloquea, exit 1 no.** Nunca exit 1.
- **Los mensajes de bloqueo explican el porqué.** El `reason` es lo único que el agente lee cuando
  lo frenás: qué pasó, por qué importa, qué hacer.
- **El config se edita con `write_file`/`patch`, no con un heredoc**: contiene los patrones que
  prohíbe y el freno de terminal los ve. Una regla nueva, mejor con `python3 scripts/cli.py rule
  add`: la prueba por el plugin (ejemplo, inocentes, gate, lint) antes de escribirla.
- **Lo que se escribe en archivos de contexto se cuida del escáner de Hermes.** Una línea que
  parezca inyección hace que Hermes descarte el archivo entero. La regla `CONTEXTO` del lint
  lista los patrones.

## Antes de dar algo por terminado

```bash
python3 scripts/gate.py          # EL entregable: self-test · link-check · lint · plugin y contrato en Hermes real
python3 scripts/selftest.py      # ¿los frenos muerden?
python3 scripts/lint.py          # ¿el repo pasa con las reglas activas?
python3 scripts/lint.py --rules  # ¿qué reglas están activas?
python3 scripts/doctor.py        # ¿el arnés está vivo en ESTA máquina?
python3 scripts/map.py           # ¿qué guía, freno o sensor actúa en cada etapa?
python3 scripts/timing.py        # ¿cuánto cuesta el arnés en cada tool call?
python3 scripts/drift.py         # ¿algo se degradó sin que nadie lo tocara? (lo corre drift.yml)
python3 scripts/cli.py status    # todo lo anterior en una pantalla; `cli.py panel` lo muestra en vivo
python3 scripts/casos.py         # los casos replicables (también en el gate)
python3 scripts/integ.py check   # las integraciones: cada manifiesto con cada perfil, por el plugin (también en el gate)
```

- CI (`.github/workflows/ci.yml`) corre el mismo gate en Linux, macOS y Windows.
- Hooks de git: `python3 scripts/githooks.py install`. Saltarse la verificación está prohibido.
- `main` entra por PR: `pre-push` frena el empujón directo (`branches.protected`).
- Lo que no cabe en el gate (depende del reloj) vive en un pipeline declarado (`runner`), y el
  self-test verifica que ese pipeline lo invoque: encendido y sin nadie que lo corra es «instalado y muerto».
- Al cambiar el arnés, probá también el portado: `python3 scripts/install.py <repo>` en dry-run.

## Documentación: qué va dónde

| Contenido | Archivo |
|---|---|
| setup de cero, paso a paso, y tablero de problemas | `docs/onboarding.md` |
| cómo se engancha a Hermes (hooks, plugin, contexto, skills, memoria) | `docs/hermes.md` |
| el arnés de ESTE repo | `docs/arnes.md` |
| guías y sensores: el marco de *harness engineering* aplicado | `docs/guias-y-sensores.md` |
| qué hace cada clave del config y quién la lee | `docs/config-reference.md` |
| cómo se instala en otro repo | `docs/portar.md` |
| de agent-harness (Claude Code) a este | `docs/desde-claude-code.md` |
| incidentes (formato fijo, lo exige el lint) | `docs/gotchas.md` |
| los lazos de control del agente autónomo | `docs/ingenieria-de-loops.md` |
| operar el loop autónomo | `docs/loop-autonomo.md` |
| la CLI y el panel | `docs/cli-y-panel.md` |
| integraciones: catálogo, perfiles, secretos, recursos, dependencias | `docs/integraciones.md` |
| el workshop de agentes autónomos | `docs/workshop/README.md` |
| casos reales replicables (programación, infra, oficina…) | `casos/README.md` |
| huecos: los cerrados y los abiertos | `docs/huecos.md` |
| por qué está hecho así | `docs/decisions/` |
