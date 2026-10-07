# STATUS — estado verificado

Lo inyecta el plugin al abrir cada sesión (primeras líneas). **Sólo va lo verificado con un
comando**; lo que se supone va en "deuda conocida".

- **Fecha del último gate completo:** 2026-09-30
- **Veredicto:** VERDE con 2 OMITIDAS — `python3 scripts/gate.py`, 8 señales: 6 verdes y las 2 de
  Hermes (plugin doctor, e2e) OMITIDAS porque esta máquina no tiene `hermes` en el PATH. La última
  corrida con Hermes Agent `47676981` (2026.9.24) fue antes de sumar mapa, costo y pre-push.

## Señales

| Señal | Resultado |
|---|---|
| self-test | verde — 639 verificaciones (incluye el portado de los 8 perfiles, cada uno con su self-test/lint/link-check/mapa/costo, y el `pre-push` contra un remoto real) |
| mutaciones | 38/38 ponen rojo el self-test (cada hallazgo de la revisión, la consola cp1252 de Windows y cada pieza traída de agent-harness; en Windows 1 sale «no aplica», con su motivo) |
| mapa del arnés | completo — 27 piezas (guía 7 · freno 3 · sensor 17; computacional 20 · inferencial 7), ninguna sin clasificar |
| costo | cada callback del plugin < 0,5 ms de mediana (presupuesto 50 ms) |
| deriva (`scripts/drift.py`) | sin deriva; 2 avisos: `print-en-plugin` y `dependencia` nunca cazaron nada en el historial (¿cicatriz o ya ganaron? decide un humano) |
| `hermes plugins doctor plugin --ci` | OK: manifiesto, import y registro; 4 hooks |
| `scripts/hermes_e2e.py` | 70 verificaciones dentro de Hermes (directivas de `pre_tool_call`, V4A, cwd de sesión, `pre_verify`, `pre_llm_call`, `transform_tool_result`, sección del prompt) |
| CI (GitHub Actions) | verde en Linux, macOS y Windows × Python 3.11 y 3.13 (`b17207b`); en CI las 2 señales de Hermes salen OMITIDAS |
| GitHub Pages | https://raalzate.github.io/hermes-harness/ publicado desde `main:/docs` |
| shell hook | probado a mano con `hermes hooks test pre_tool_call --for-tool terminal`: bloqueo parseado en la forma de Hermes, inocente pasa |

## Deuda conocida

- `context.blockedPatterns` es una copia a mano de un subconjunto del escáner de Hermes.
- Escrituras por la terminal que no son redirección (`cp`, `mv`, `python -c`): ver `docs/arnes.md`.
- Sin panel ni prueba de vida con tasa de `harness-review` (ver `docs/guias-y-sensores.md`).
- Mapa, costo, deriva y `pre-push` no se corrieron todavía en CI ni con Hermes instalado.
