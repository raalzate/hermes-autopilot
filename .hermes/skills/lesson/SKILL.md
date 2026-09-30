---
name: lesson
description: Convierte un incidente (algo que costó tiempo o salió mal) en una mejora del arnés que pasó el gate, con el mecanismo más fuerte disponible. Usala cuando algo se rompió, cuando el humano dice "que no vuelva a pasar", o al terminar una tarea que tuvo un tropiezo evitable.
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [harness, incident, learning]
    category: harness
---

# /lesson — el ciclo RHO

Hermes aprende solo (memoria y skills). Esta skill existe para que lo aprendido **sobre el repo**
no quede en tu memoria privada, sino en infraestructura que frena a cualquier agente.

## 1. Registrar (R)

Escribí qué pasó con la salida real: comando, error, archivo y línea. Sin reconstruir de memoria.

## 2. Hipótesis de causa (H)

¿Por qué pasó *de verdad*? "Me olvidé" no es una causa: la causa es que nada lo impedía.
Si el incidente ya estaba en `docs/gotchas.md`, el hallazgo es otro: la regla existía y no frenó
nada, así que hace falta un mecanismo **más fuerte**, no otra entrada de texto.

## 3. Obra (O): el mecanismo más fuerte que alcance

En este orden, el primero que sirva:

1. **test** del producto que falla sin el arreglo;
2. **regla del config** (`terminal.deny`, `protectedPaths`, `patterns`, `memory.deny`,
   `skills.deny`, `cron.deny`, `invariants`) con su `example` → el self-test la prueba solo;
3. **clase de regla nueva** en `plugin/harness/` → con su caso escrito a mano en `scripts/selftest.py`;
4. una línea en `AGENTS.md` (guía, no freno) — sólo si nada de lo anterior es posible.

La memoria (`memory`) **no** es un mecanismo para reglas del repo: no se revisa, no se commitea y
no frena a otro agente.

## 4. Cerrar

- Agregá el bloque a `docs/gotchas.md` con **Síntoma / Causa / Regla / Mecanismo** (lo exige
  el lint).
- Corré el gate (skill `gate`). La lección no existe hasta que el gate está verde con ella.
- Validación doble: la regla nueva **muerde** (su `example`) y **no muerde de más** (el repo
  entero sigue pasando el lint).
