# 0008 — El código del agente pasa por los frenos, y las herramientas se verifican en el código de Hermes

**Estado:** aceptada · **Fecha:** 2026-10-08

## Contexto

La auditoría de huecos (ADR 0007) dejaba abierto «otras herramientas de lectura de Hermes», porque
sumar nombres sin verificarlos es adivinar. Esta vez se verificaron contra el código de
hermes-agent (`tools/*.py`, 2026-10). Además de `search_files` y `vision_analyze`, apareció
**`execute_code`**: Python arbitrario como herramienta propia, que no pasa por la terminal. Ningún
freno del arnés lo veía, así que cada regla de terminal tenía un desvío. Era un hueco más grave
que los listados.

## Decisión

- **Familia `code`** (`tools.code: [execute_code]`) con `code_guard`. Lo que la terminal veda o
  escala, el código también, sobre el texto entero y sobre cada cadena. Además, las rutas que el
  código **nombra**: un secreto nombrado no se lee, y una ruta protegida nombrada en un código que
  escribe no se escribe. Mandar datos desde Python (`sendPatterns`) escala a un humano.
- **El mismo análisis para el código en línea de la terminal** (`python3 -c`, `bash -c`…,
  `terminal.inlineCode.interpreters`).
- **No es un sandbox, y no lo pretende.** Un regex ve lo que el código nombra, no lo que hace: una
  ruta armada por partes pasa. Esa parte la cubre el loop con los intocables, y los casos lo
  muestran con el modo `ofuscado`. Cerrarlo del todo es aislar al agente, y eso es de Hermes.
- **El entorno ya lo cuida Hermes.** Quita los secretos del entorno de la terminal y de
  `execute_code` por defecto (`tools/env_passthrough.py`). Lo que queda es avisar cuando alguien los
  deja pasar (`doctor.py`, `terminal.env_passthrough`).
- **Paralelo con worktrees.** Cada tarea corre en su worktree con su gitdir, y con él su candado,
  su estado y sus intocables, sin código nuevo de concurrencia. El coordinador sólo reparte, marca
  la cola y redirige los eventos al registro principal.

## Consecuencias

- `docs/huecos.md`: seis cerrados más (12–17). Quedan abiertos los programas por dentro, la
  inyección de prompt, el sensor inferencial y Hermes real en el loop, cada uno con su porqué.
- Los casos con `python3 -c` sobre una ruta nombrada ahora los frena el freno, no el loop. Para
  seguir mostrando la capa del loop se agregó el modo `ofuscado`.
- Constitución 1.4.0: P8 nombra `code_guard`; P21 suma el paralelo.
