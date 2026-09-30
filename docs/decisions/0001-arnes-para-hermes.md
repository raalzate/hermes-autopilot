# 0001 — Un arnés propio para Hermes, no un puerto de configuración

**Estado:** aceptada · 2026-09-30

## Contexto

`agent-harness` resuelve "reglas que se hacen cumplir solas" para Claude Code. Hermes Agent tiene
un importador (`hermes import-agent claude-code`) que trae `CLAUDE.md`, permisos, MCP y skills,
pero **no los hooks** ni los comandos: justo lo que hace de un arnés un arnés.

Además Hermes tiene superficies que Claude Code no tiene: memoria persistente que el agente
escribe solo, skills que crea y parchea solo, cron y un gateway de mensajería donde no hay humano
mirando.

## Decisión

Un repo nuevo con los mismos principios y mecanismos rehechos para Hermes: plugin en proceso,
contrato de hooks de Hermes, `AGENTS.md` como contexto, y tres familias de frenos nuevas
(memoria, skills, cron) con sus principios (P12, P13) y el presupuesto de contexto (P14).

## Consecuencias

- Los dos arneses comparten la constitución en espíritu, no el código: cada uno se prueba contra
  su agente.
- El mapa entre los dos vive en `docs/desde-claude-code.md`.
