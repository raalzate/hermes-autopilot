---
name: new-guardrail
description: Convierte una regla escrita en prosa ("hay que acordarse de…", "la convención es…", "no volvamos a hacer X") en un freno ejecutable del arnés, con su ejemplo y su caso inocente, validado por el gate.
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [harness, guardrail]
    category: harness
---

# /new-guardrail

## 1. ¿Qué familia la hace cumplir?

| Si la regla habla de… | Clave del config | Qué ve el freno |
|---|---|---|
| un comando de terminal | `terminal.deny` (bloquea) o `terminal.ask` (pide aprobación humana) | el `command` |
| un archivo que no se toca | `protectedPaths` (`outsideRepo: true` para `~/.hermes/…`) | la ruta |
| algo que no se escribe en el código | `patterns` (con `paths`) | el contenido, al escribir y en el lint |
| algo que no se guarda en la memoria | `memory.deny` | lo que el agente guarda |
| algo que una skill no enseña | `skills.deny` (ya hereda `terminal.deny`) | el texto de la skill |
| una tarea programada | `cron.deny`, `cron.minIntervalMinutes` | el prompt y el schedule |
| un archivo que debe/no debe contener algo | `invariants` | el archivo, en el lint |

Si ninguna encaja, es una clase de regla nueva: código en `plugin/harness/` **y** caso a mano en
`scripts/selftest.py`. Nada específico del repo entra al código (P4).

## 2. Escribir la regla

```json
{ "id": "corto", "pattern": "regex", "example": "un caso real que DEBE frenar",
  "reason": "qué pasó, por qué importa y qué hacer en su lugar" }
```

- `reason` es lo **único** que el agente lee cuando el freno lo para: tiene que explicar el
  porqué y la alternativa, o el agente reintenta con otra forma.
- `example` es la prueba de vida: el self-test lo pasa por el plugin real. Sin él, rojo.
- Sumá un caso a `innocent` de la familia si la regla puede morder de más.
- Editá el config con `write_file`/`patch`, no con un heredoc en la terminal: el archivo contiene
  los patrones que prohíbe y el freno de terminal los ve.

## 3. Validar las dos caras

1. `python3 scripts/selftest.py` (o su ruta en `.hermes/harness/`): ¿muerde?
2. `python3 scripts/lint.py`: ¿el repo sigue pasando? Esta es la que se olvida y la que importa.
3. El gate completo (skill `gate`).
