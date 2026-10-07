# 0005 — Las prácticas de `agent-harness` que faltaban, portadas como mecanismo

**Estado:** aceptada · 2026-09-30

## Contexto

`hermes-harness` nació de `agent-harness` 1.0 y se rehízo para Hermes. `agent-harness` siguió
creciendo (constitución 1.2.0): guías y sensores, coherencia entre guía y freno, perfiles sin
reglas, deriva programada, mapa del arnés, costo medido y un freno de push. Acá sólo existían
como deuda o no existían.

## Decisión

Se portan como **mecanismo**, no como prosa, y cada uno con su caso en el self-test y al menos una
mutación que lo rompa:

| Práctica | Mecanismo | Principio |
|---|---|---|
| lo que viaja son los principios | regla `PERFIL` del lint (`profiles.forbiddenKeys`) | P17 |
| guía y freno no se contradicen | regla `COHERENCIA`, evaluada con el mismo `first_match` que `terminal_guard` | P18 |
| el costo del arnés, medido | `scripts/timing.py`, señal del gate | P19 |
| deriva y controles fuera del gate | `scripts/drift.py` + `.github/workflows/drift.yml`; el self-test exige que el `runner` invoque el comando | P20 |
| el arnés como sistema de control | `scripts/map.py` (`taxonomy`), señal del gate | P20 |
| el trabajo entra por PR | `.githooks/pre-push` (`branches.protected`) | P11 |

Diferencias con `agent-harness`:

- **timing va en el gate.** Allá mide procesos `node` (decenas de ms, ruidosos); acá los callbacks
  corren en proceso y miden fracciones de ms, así que un presupuesto de 50 ms no es frágil, y en
  Hermes pasarse de tiempo **bloquea** la herramienta: el costo es contrato, no comodidad.
- **map va en el gate.** Es determinista y barato; allá también falla, pero se corre a mano.
- **Los principios nuevos se numeran al final** (P17–P20) para no romper las referencias a P1–P16
  en código, skills y docs.

## Lo que no se portó

- El eval del revisor (`reviewer-eval`): `harness-review` es una skill que corre dentro de la sesión
  de Hermes; tomarle la prueba con tasa necesita un Hermes con modelo en CI. Queda como hueco
  declarado en `docs/guias-y-sensores.md`.
- `cycle-check` (ramas y prácticas XP, `--verify-red`) y `artifacts-check`: dependen de la forma de
  trabajo del repo destino; se pueden sumar como señales del gate sin tocar el código del arnés.
- El panel HTML: sigue en `docs/desde-claude-code.md`.

## Consecuencias

- El gate suma dos señales (mapa y costo) y el self-test una sección (§12).
- Una skill, un hook o un pipeline nuevo se declara en `taxonomy` o el gate sale rojo.
- En este repo `main` queda protegido: se trabaja en una rama y se entra por PR.
