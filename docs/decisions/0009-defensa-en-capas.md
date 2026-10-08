# 0009 — Defensa en capas para lo desatendido, y medir lo que no se puede probar

**Estado:** aceptada · **Fecha:** 2026-10-08

## Contexto

La auditoría (`docs/huecos.md`) dejaba cuatro abiertos: lo que un programa hace por dentro, la
inyección de prompt, el revisor inferencial sin tasa y el Hermes real que nunca corría. Ninguno se
cierra con un regex más.

## Decisión

Cada hueco se cierra en la capa donde se puede **ver** lo que pasa, no donde sería cómodo:

| Hueco | Dónde se ve | Mecanismo |
|---|---|---|
| un programa lee un secreto | en el disco: si no está, no se lee | `loop.aislar` — cada tarea en un `git worktree`, que no trae lo ignorado |
| un programa Python abre lo que no debe | en el intérprete: cada `open` tiene la ruta real | `plugin/guardia` — audit hook (PEP 578), cargado por `sitecustomize` en el entorno del agente |
| una inyección hace daño | en el canal de salida, justo después de la entrada | sesión contaminada — tras leer a un tercero, publicar o persistir escala |
| un juicio acierta a veces | en una tasa contra un conjunto etiquetado | `scripts/revision.py`, con `omitIfExit` en el gate y un pipeline nocturno |
| el contrato con Hermes | en el Hermes real | `scripts/hermes_fuente.py` y el job `hermes-real` en cada PR |

Y en ningún caso se finge: la guardia sólo cubre Python (lo dice), la sesión contaminada corta
el daño y no detecta la inyección (lo dice), y el revisor sin modelo sale OMITIDA, nunca verde.

**Trunk-based.** Cada hueco fue una rama corta desde `main`, con su PR, su CI en las tres
plataformas y su merge al trunk en cuanto estuvo verde. Nada de ramas largas.

## Consecuencias

- Constitución 1.5.0: P24 (lo que entra de un tercero no sale solo) y P25 (un sensor inferencial
  se mide con una tasa).
- La medición del revisor con un modelo depende de un secreto del dueño del repo (`HERMES_ENV`).
- Lo que sigue abierto está en `docs/huecos.md`, con su porqué.
