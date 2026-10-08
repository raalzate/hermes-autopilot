# STATUS — estado verificado

Lo inyecta el plugin al abrir cada sesión (primeras líneas). **Sólo va lo verificado con un
comando**; lo que se supone va en "deuda conocida".

- **Fecha del último gate completo:** 2026-10-07
- **Veredicto:** VERDE con 2 OMITIDAS — `python3 scripts/gate.py`, 9 señales: 7 verdes y las 2 de
  Hermes (plugin doctor, e2e) OMITIDAS porque esta máquina no tiene `hermes` en el PATH. La última
  corrida con Hermes Agent `47676981` (2026.9.24) fue antes de sumar mapa, costo, pre-push y la
  autonomía (loop, CLI, panel, registro de eventos).

## Señales

| Señal | Resultado |
|---|---|
| self-test | verde — 814 verificaciones (incluye los frenos de lectura `protectedReads` por herramienta y por terminal, `cp`/`mv`/`rm`/`sed -i` sobre rutas protegidas, los intocables y el candado del loop, la forma del catálogo de casos; incluye el portado de los 8 perfiles con su self-test/lint/link-check/mapa/costo, el self-test de un repo instalado **sin** la marca de anidado y su pre-commit sobre lo instalado, el `pre-push` contra un remoto real, y §13: registro de eventos, tres corridas reales del loop con un agente de mentira, la CLI y el panel por HTTP/SSE) |
| mutaciones | 57/57 ponen rojo el self-test (cada hallazgo de la revisión, la consola cp1252 de Windows, cada pieza traída de agent-harness, la autonomía y los huecos cerrados en `docs/huecos.md`; en Windows 1 sale «no aplica», con su motivo) |
| mapa del arnés | completo — 30 piezas (guía 7 · freno 3 · sensor 20; computacional 23 · inferencial 7), ninguna sin clasificar |
| casos replicables | 29/29 corridas de 17 casos dan lo esperado (programación 5, infraestructura 5, oficina 3, soporte 2, datos 1, operación 1), cada una en un repo instalado de cero |
| loop autónomo | probado de punta a punta en un sandbox instalado con `--profile python` (el ensayo del workshop): verde en el intento 2, escalada por el mismo rojo, freno de mano. **Sin probar todavía con Hermes como agente** (`hermes chat -q`) |
| costo | cada callback del plugin < 0,5 ms de mediana (presupuesto 50 ms) |
| deriva (`scripts/drift.py`) | sin deriva; 2 avisos: `print-en-plugin` y `dependencia` nunca cazaron nada en el historial (¿cicatriz o ya ganaron? decide un humano) |
| `hermes plugins doctor plugin --ci` | OK: manifiesto, import y registro; 4 hooks |
| `scripts/hermes_e2e.py` | 70 verificaciones dentro de Hermes (directivas de `pre_tool_call`, V4A, cwd de sesión, `pre_verify`, `pre_llm_call`, `transform_tool_result`, sección del prompt) |
| CI (GitHub Actions) | verde en Linux, macOS y Windows × Python 3.11 y 3.13 (`b17207b`); en CI las 2 señales de Hermes salen OMITIDAS |
| GitHub Pages | publicado desde `main:/docs`; la URL nueva (https://raalzate.github.io/hermes-autopilot/) sale con el renombre del repo y la landing nueva con el merge a `main` |
| shell hook | probado a mano con `hermes hooks test pre_tool_call --for-tool terminal`: bloqueo parseado en la forma de Hermes, inocente pasa |

## Deuda conocida

- `context.blockedPatterns` es una copia a mano de un subconjunto del escáner de Hermes.
- Escrituras por la terminal que no son redirección (`cp`, `mv`, `python -c`): ver `docs/arnes.md`.
- Sin prueba de vida con tasa de `harness-review` (ver `docs/guias-y-sensores.md`).
- Mapa, costo, deriva, `pre-push`, el loop, la CLI y el panel no se corrieron todavía en CI ni con Hermes instalado.
- El loop trabaja una tarea por vez; sin paralelismo por worktrees (`docs/ingenieria-de-loops.md`).
