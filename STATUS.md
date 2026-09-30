# STATUS — estado verificado

Lo inyecta el plugin al abrir cada sesión (primeras líneas). **Sólo va lo verificado con un
comando**; lo que se supone va en "deuda conocida".

- **Fecha del último gate completo:** 2026-09-30
- **Veredicto:** VERDE — `python3 scripts/gate.py`, 6/6 señales con Hermes Agent `47676981`
  (2026.9.24) instalado; sin Hermes, 4 verdes y 2 OMITIDAS (plugin doctor, e2e).

## Señales

| Señal | Resultado |
|---|---|
| self-test | verde — ~390 verificaciones (+ portado de los 8 perfiles, cada uno con su self-test/lint/link-check) |
| mutaciones | 27/27 ponen rojo el self-test (incluye cada hallazgo de la revisión del 2026-09-30) |
| `hermes plugins doctor plugin --ci` | OK: manifiesto, import y registro; 4 hooks |
| `scripts/hermes_e2e.py` | 70 verificaciones dentro de Hermes (directivas de `pre_tool_call`, V4A, cwd de sesión, `pre_verify`, `pre_llm_call`, `transform_tool_result`, sección del prompt) |
| shell hook | probado a mano con `hermes hooks test pre_tool_call --for-tool terminal`: bloqueo parseado en la forma de Hermes, inocente pasa |

## Deuda conocida

- CI todavía no corrió (el repo no tiene commits ni remoto): la matriz de Windows no está verificada.
- `context.blockedPatterns` es una copia a mano de un subconjunto del escáner de Hermes.
- Escrituras por la terminal que no son redirección (`cp`, `mv`, `python -c`): ver `docs/arnes.md`.
- Sin panel ni medición de latencia todavía (ver `docs/desde-claude-code.md`).
