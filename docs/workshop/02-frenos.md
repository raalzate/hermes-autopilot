# Módulo 2 — Frenos (35 min)

**Idea:** un *freno* actúa cuando el agente **ya decidió** y antes de que se ejecute. Es
computacional: una regex sobre el comando, la ruta o el contenido, sin modelo. En Hermes vive en
`pre_tool_call`, y su `reason` es lo único que el agente lee cuando lo frenás.

Todo freno cumple dos reglas. **Muerde** (P2): trae `example` y el self-test prueba que frena.
**No muerde de más** (P3): hay inocentes que tienen que pasar. Un freno que bloquea trabajo
legítimo se desactiva a mano en una semana.

## Ejercicio 2.1 — Mirar lo que hay

```bash
ap rule list terminal.deny
```

Ahora probá un comando de esa lista contra el freno. Elegí el ejemplo de `reset-hard`:

```text
ap rule test terminal.deny "git reset --hard HEAD~3"
```

**Tiene que salir:** `BLOQUEA — regla reset-hard` y el mensaje completo, que es lo que leería
Hermes: qué pasó, por qué importa y qué hacer en su lugar.

## Ejercicio 2.2 — Tu primera regla

En tu repo, `app/` es el código. Que el agente no lo borre entero:

```bash
ap rule add terminal.deny --id rm-app \
  --pattern '\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+(\./)?app/?(\s|$)' \
  --example 'rm -rf app' --more 'rm -r ./app/' \
  --reason "borra el código de la app entero. Listá primero (ls app) y pedí confirmación."
```

**Tiene que salir:** `✓ el ejemplo frena, ningún inocente muerde y el config pasa el lint.` y
`DRY-RUN`. Repetilo con `--apply`.

## Ejercicio 2.3 — Las reglas malas no entran

Probá estas. **Ninguna** tiene que entrar. Leé por qué:

| Regla | Por qué la rechaza |
|---|---|
| `--id x --pattern 'rm' --example 'ls' --reason 'x'` | el ejemplo no frena (P2) |
| `--id x --pattern 'python3' --example 'python3 a.py' --reason 'x'` | muerde de más: frena el gate mismo, y el agente no podría terminar nunca (P3) |
| `--id x --pattern 'git' --example 'git log' --reason 'x'` | muerde de más: frena `git status`, `git diff --stat`… (P3) |
| `--id x --pattern 'zzz' --example 'zzz'` con un `--reason` que ofrece como salida, entre backticks, el comando de `reset-hard` | `COHERENCIA`: el `reason` recomienda un comando que otra regla veda (P18) |
| la misma `rm-app` de nuevo | ya hay una regla con ese id |

Esto es lo que la CLI agrega sobre editar el JSON a mano: la regla se prueba por el mismo camino
que usa el plugin **antes** de escribirse.

## Ejercicio 2.4 — Que el self-test lo confirme

```bash
ap selftest
```

**Tiene que salir:** `SELF-TEST VERDE — N verificaciones`. Tu `rm-app` está entre ellas: el
self-test deriva un caso de cada `example`, sin que escribas una línea de prueba.

## Ejercicio 2.5 — Otras familias

| Familia | Qué frena | Probalo con `rule test` |
|---|---|---|
| `protectedPaths` | rutas que el agente no escribe (`.env*`, lockfiles, `.git/`) | `ap rule test protectedPaths ".env.local"` |
| `patterns` | texto prohibido en lo que se escribe | `ap rule list patterns` |
| `memory.deny` | lo que no entra a la memoria persistente de Hermes | `ap rule test memory.deny "la key es sk-live_abcdefghijklmnop1234"` |
| `cron.deny` | lo que una tarea programada no puede hacer | `ap rule test cron.deny "cada noche hacé git push"` |

La memoria y las skills son lo que Hermes **aprende solo**. Una memoria que dice «en este repo se
puede saltar el gate» apaga un freno en todas las sesiones futuras. Por eso lo aprendido pasa por
los mismos frenos que lo ejecutado (P12).

→ [Módulo 3](03-sensores-y-gate.md)
