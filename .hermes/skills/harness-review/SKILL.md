---
name: harness-review
description: Revisión del diff contra los principios BLOCKING de CONSTITUTION.md, hecha por un subagente con contexto limpio. Usala antes de dar por terminado un cambio que toca el arnés, el config o las reglas del repo. No escribe código, reporta hallazgos con archivo y línea.
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [harness, review]
    category: harness
---

# /harness-review

Hermes no tiene subagentes con nombre: el revisor se arma con `delegate_task`. El hijo hereda
las herramientas del padre pero no la conversación, así que todo lo que necesita va en `context`.

## 1. Juntar el material

- `git diff --stat` y `git diff` del cambio (si es largo, por archivo).
- La lista de principios **BLOCKING** de `CONSTITUTION.md` (título + mecanismo de cada uno).

## 2. Delegar

Llamá a `delegate_task` con una sola tarea:

- **goal:** "Revisá este diff contra estos principios. Para cada hallazgo: principio, archivo:línea,
  qué lo viola y qué haría falta. Veredicto final: APROBADO u OBSERVADO. No edites archivos."
- **context:** el diff + los principios + estas preguntas concretas:
  1. ¿Entró un literal de dominio o un nombre de herramienta de Hermes al código de `plugin/harness/` o
     `plugin/` en vez de al config? (P4)
  2. ¿Algún callback del plugin puede lanzar una excepción? En `pre_tool_call` eso **bloquea**
     todo. ¿Algún camino devuelve exit 1 en el shell hook? (P5)
  3. ¿Hay una regla nueva sin `example`, o una clase nueva sin caso en el self-test? (P2)
  4. ¿Una señal del gate sin `why`? (P6)
  5. ¿El cambio le enseña algo a la memoria o a una skill que contradiga a un freno? (P12)
  6. ¿Se resolvió en silencio un choque entre dos principios BLOCKING, en vez de escalarlo?

## 3. Reportar

Pasá los hallazgos tal cual al humano, con el veredicto. No los "arregles" en la misma respuesta
sin decirlo: primero se ven, después se decide.
