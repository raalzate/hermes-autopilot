# 0004 — Cada regla trae su `example`, y el self-test lo pasa por el plugin

**Estado:** aceptada · 2026-09-30

## Contexto

`agent-harness` genera una muestra a partir del regex de cada regla (`sampleFromPattern`). Es
ingenioso y frágil: un regex con lookahead o clases raras no produce muestra, y la regla queda sin
prueba sin que nadie lo note.

## Decisión

Toda regla del config declara `example`: un caso real que **debe** frenar. El self-test:

1. verifica que el ejemplo case con su propio patrón;
2. lo pasa por el callback real del plugin (`on_pre_tool_call`, con `_seguro` y `to_hermes`),
   por **cada** herramienta de la familia declarada en `tools`;
3. verifica que el mensaje de bloqueo contenga el `reason`;
4. pasa los `innocent` de cada familia y exige que NO frenen (P3).

Una regla sin `example` es roja.

## Consecuencias

- Agregar una regla es agregar su prueba en la misma línea: no hay forma de olvidarla.
- El ejemplo documenta la regla mejor que el regex.
- El config contiene literalmente los comandos que prohíbe: se edita con el editor, no con un
  heredoc en la terminal (el freno de terminal lo vería).
