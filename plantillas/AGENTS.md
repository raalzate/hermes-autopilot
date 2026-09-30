# AGENTS.md

Hermes carga este archivo al abrir cada sesión en este repo. Tiene que ser corto: después de
20 000 caracteres Hermes lo trunca y se pierde el medio (el lint del arnés lo mide).

## Qué es este repo

<!-- Una o dos frases: qué hace y para quién. -->

## Cómo se verifica

- El entregable es `python3 .hermes/harness/scripts/gate.py`. Una señal **omitida** no es verde.
- Si editaste código y el gate no quedó verde, Hermes no te deja cerrar el turno: corrélo y
  arreglá lo rojo. Si no es entregable todavía, decilo explícitamente.
- `/harness` muestra qué frenos están activos y por qué.

## Frenos del arnés

Viven en `.hermes/harness.config.json` y los aplica el plugin `repo-harness`. Si uno te bloquea,
el mensaje explica el porqué: leelo antes de reintentar y no reformules para esquivarlo. Si el
freno está mal, se arregla el freno (con su `example`), no se rodea.

- Lo que es **regla del repo** va acá o al config, con commit. La memoria es para preferencias
  del humano; las skills, para procedimientos. Las dos pasan por los mismos frenos.
- Presupuesto de error: 2 intentos sobre el mismo error con hipótesis nueva; al tercero, parar y
  escalar con el diagnóstico.

## Skills del repo

`.hermes/skills/` (cargan tras `hermes skills trust`): `/gate`, `/lesson`, `/harness-audit`,
`/new-guardrail`, `/harness-review`.
