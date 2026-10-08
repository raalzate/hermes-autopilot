# STATUS — estado verificado

Lo inyecta el plugin al abrir cada sesión (primeras líneas). **Sólo va lo verificado con un
comando**; lo que se supone va en "deuda conocida".

- **Fecha del último gate completo:** 2026-10-08
- **Veredicto:** VERDE con 1 OMITIDA — `python3 scripts/gate.py` con Hermes real en el PATH (Hermes
  Agent `aa74e184`, 2026.9.24, desde el código fuente con `scripts/hermes_fuente.py`): 10 señales,
  9 verdes y el revisor inferencial OMITIDO porque no hay un modelo configurado (`HARNESS_REVIEW`).
  Sin Hermes en el PATH salen además OMITIDAS las 2 de Hermes; en CI corren en el job `hermes-real`.

## Señales

| Señal | Resultado |
|---|---|
| self-test | verde — 981 verificaciones (incluye el loop aislado en worktree, la guardia de Python con procesos reales, la sesión contaminada en cada fuente y regla, el revisor medido con revisores de mentira y `omitIfExit` en el gate; `execute_code` y el código en línea contra cada regla, `search_files`/`vision_analyze`, el loop en paralelo con worktrees, los frenos de lectura `protectedReads` por herramienta y por terminal, `cp`/`mv`/`rm`/`sed -i` sobre rutas protegidas, los intocables y el candado del loop, la forma del catálogo de casos; incluye el portado de los 8 perfiles con su self-test/lint/link-check/mapa/costo, el self-test de un repo instalado **sin** la marca de anidado y su pre-commit sobre lo instalado, el `pre-push` contra un remoto real, y §13: registro de eventos, tres corridas reales del loop con un agente de mentira, la CLI y el panel por HTTP/SSE) |
| mutaciones | 72/72 ponen rojo el self-test (cada hallazgo de la revisión, la consola cp1252 de Windows, cada pieza traída de agent-harness, la autonomía y los huecos cerrados en `docs/huecos.md`; en Windows 1 sale «no aplica», con su motivo) |
| mapa del arnés | completo — 32 piezas (guía 7 · freno 3 · sensor 22; computacional 25 · inferencial 7), ninguna sin clasificar |
| casos replicables | 34/34 corridas de 17 casos dan lo esperado (programación 5, infraestructura 5, oficina 3, soporte 2, datos 1, operación 1), cada una en un repo instalado de cero |
| loop autónomo | probado de punta a punta en los 17 casos, aislado en worktree y con la guardia de Python. **Sin probar todavía con un modelo como agente** (`hermes chat -q` necesita una key) |
| revisor inferencial (`scripts/revision.py`) | OMITIDO: sin modelo configurado. Mecanismo probado con revisores de mentira; lo mide `hermes-nocturno.yml` cuando exista el secreto `HERMES_ENV` |
| costo | cada callback del plugin < 0,5 ms de mediana (presupuesto 50 ms) |
| deriva (`scripts/drift.py`) | sin deriva; 2 avisos: `print-en-plugin` y `dependencia` nunca cazaron nada en el historial (¿cicatriz o ya ganaron? decide un humano) |
| `hermes plugins doctor plugin --ci` | OK: manifiesto, import y registro; 4 hooks |
| `scripts/hermes_e2e.py` | 87 verificaciones dentro de Hermes (`aa74e184`) (directivas de `pre_tool_call`, V4A, cwd de sesión, `pre_verify`, `pre_llm_call`, `transform_tool_result`, sección del prompt) |
| CI (GitHub Actions) | matriz Linux, macOS y Windows × Python 3.11 y 3.13, y el job `hermes-real` con el gate contra Hermes desde el código fuente |
| GitHub Pages | https://raalzate.github.io/hermes-autopilot/ publicado desde `main:/docs`, con la consola de los casos (corridas reales) |
| shell hook | probado a mano con `hermes hooks test pre_tool_call --for-tool terminal`: bloqueo parseado en la forma de Hermes, inocente pasa |

## Deuda conocida

- `context.blockedPatterns` es una copia a mano de un subconjunto del escáner de Hermes.
- En una sesión interactiva (fuera del loop), lo que un programa no-Python hace por dentro: ver `docs/huecos.md`.
- El revisor inferencial y el loop con un modelo de verdad esperan el secreto `HERMES_ENV` (ver `docs/huecos.md`).
