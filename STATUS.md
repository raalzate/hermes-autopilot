# STATUS — estado verificado

Lo inyecta el plugin al abrir cada sesión (primeras líneas). **Sólo va lo verificado con un
comando**; lo que se supone va en "deuda conocida".

- **Fecha del último gate completo:** 2026-10-09
- **Veredicto:** VERDE con 1 OMITIDA — `python3 scripts/gate.py` con Hermes real en el PATH (Hermes
  Agent `aa74e184`, 2026.9.24, desde el código fuente con `scripts/hermes_fuente.py`): 11 señales,
  10 verdes y el revisor inferencial OMITIDO porque no hay un modelo configurado (`HARNESS_REVIEW`).
  Sin Hermes en el PATH salen además OMITIDAS las 2 de Hermes; en CI corren en el job `hermes-real`.

## Señales

| Señal | Resultado |
|---|---|
| self-test | verde — 1107 verificaciones (incluye la guardia de Python en una sesión interactiva con procesos reales, el contenido que sale por una integración, la respuesta tapada y con aviso de contaminada, lo aprobado contado en el presupuesto y las cifras de la portada contra su fuente; §14, integraciones: el catálogo con cada perfil por el plugin, destinatarios, redes internas, archivos locales, presupuesto contando de verdad, sesión contaminada, alcance por tarea, MCP sin declarar, recorte del resultado, nombres de Hermes saneados y cortados, el lanzador con secretos por referencia, la sonda de contrato, el lock, doctor, deriva con OSV y la tarjeta del panel; además el loop aislado en worktree, la guardia de Python con procesos reales, la sesión contaminada en cada fuente y regla, el revisor medido con revisores de mentira y `omitIfExit` en el gate; `execute_code` y el código en línea contra cada regla, `search_files`/`vision_analyze`, el loop en paralelo con worktrees, los frenos de lectura `protectedReads` por herramienta y por terminal, `cp`/`mv`/`rm`/`sed -i` sobre rutas protegidas, los intocables y el candado del loop, la forma del catálogo de casos; incluye el portado de los 8 perfiles con su self-test/lint/link-check/mapa/costo, el self-test de un repo instalado **sin** la marca de anidado y su pre-commit sobre lo instalado, el `pre-push` contra un remoto real, y §13: registro de eventos, tres corridas reales del loop con un agente de mentira, la CLI y el panel por HTTP/SSE) |
| mutaciones | 106/106 ponen rojo el self-test (9 de los huecos 25-28 y la portada; 25 de integraciones; cada hallazgo de la revisión, la consola cp1252 de Windows, cada pieza traída de agent-harness, la autonomía y los huecos cerrados en `docs/huecos.md`; en Windows 1 sale «no aplica», con su motivo) |
| mapa del arnés | completo — 39 piezas (guía 7 · freno 7 · sensor 25; computacional 32 · inferencial 7), ninguna sin clasificar |
| casos replicables | 46/46 corridas de 22 casos dan lo esperado (programación 6, infraestructura 6, oficina 5, soporte 3, datos 1, operación 1; cinco con integraciones), cada una en un repo instalado de cero |
| loop autónomo | probado de punta a punta en los 22 casos (con el alcance de integraciones por tarea), aislado en worktree y con la guardia de Python. **Sin probar todavía con un modelo como agente** (`hermes chat -q` necesita una key) |
| revisor inferencial (`scripts/revision.py`) | en el gate, OMITIDO: sin modelo configurado. Medido a mano con un modelo real el 2026-10-09 (Claude Sonnet 5.5 por `claude -p`): recall 100 % (10/10 atajos) y precisión 91 % (1 arreglo bueno frenado), sobre el umbral de 80 % — `evals/mediciones/revision-2026-10-09-claude-sonnet-5-5.txt`. El pipeline nocturno lo mide con Hermes cuando exista el secreto `HERMES_ENV` |
| costo | cada callback del plugin < 2 ms de mediana (presupuesto 50 ms), incluidos `post_tool_call`, `transform_llm_output` y una herramienta de integración; con presupuesto por hora y un registro de 3000 líneas, ~4 ms |
| deriva (`scripts/drift.py`) | sin deriva; las 3 dependencias del catálogo sin vulnerabilidades conocidas (OSV); 3 avisos: `print-en-plugin` y `dependencia` nunca cazaron nada en el historial, y salió `workspace-mcp` 2.1.0 (fijado en 2.0.1: se prueba con `--probe` antes de subirlo) |
| `hermes plugins doctor plugin --ci` | OK: manifiesto, import y registro; 6 hooks |
| `scripts/hermes_e2e.py` | 179 verificaciones dentro de Hermes (`aa74e184`) (un envío aprobado contado por el emisor real de `post_tool_call`, la respuesta tapada por `apply_llm_output_transform`; el nombre de cada herramienta MCP contra `mcp_prefixed_tool_name` real, cada ejemplo del catálogo de integraciones con cada perfil, el MCP sin declarar; directivas de `pre_tool_call`, V4A, cwd de sesión, `pre_verify`, `pre_llm_call`, `transform_tool_result`, sección del prompt) |
| CI (GitHub Actions) | matriz Linux, macOS y Windows × Python 3.11 y 3.13, y el job `hermes-real` con el gate contra Hermes desde el código fuente |
| GitHub Pages | https://raalzate.github.io/hermes-autopilot/ publicado desde `main:/docs`, con la consola de los casos (corridas reales) |
| integraciones | 7 en el catálogo, verificadas contra el servidor o el código real (`tools/list` de Playwright MCP 0.0.83, workspace-mcp 2.0.1 y ms-365-mcp-server 0.160.0); `navegador` instalado de punta a punta en un repo de prueba (`deps` → lock con hash → `--probe` → una navegación headless real por el lanzador). Google y Microsoft **sin probar con una cuenta real** (necesitan OAuth del dueño) |
| shell hook | probado a mano con `hermes hooks test pre_tool_call --for-tool terminal`: bloqueo parseado en la forma de Hermes, inocente pasa |

## Deuda conocida

- `context.blockedPatterns` es una copia a mano de un subconjunto del escáner de Hermes.
- En una sesión interactiva (fuera del loop), lo que un programa **no-Python** hace por dentro (Python ya lo ve `sessionGuard.python`): ver `docs/huecos.md`.
- El loop con un modelo de verdad como agente, y el revisor medido en CI, esperan el secreto `HERMES_ENV` (ver `docs/huecos.md`).
- Las integraciones de Google y Microsoft no se probaron con una cuenta real: su contrato (`tools/list`) sí, el envío no.
