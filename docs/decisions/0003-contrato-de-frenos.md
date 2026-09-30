# 0003 — El contrato de un freno: puro, explicado y fallando abierto

**Estado:** aceptada · 2026-09-30

## Contexto

Hermes decide el flujo con lo que devuelve un hook: `{"action": "block", "message"}` en
`pre_tool_call`, `{"action": "continue", "message"}` en `pre_verify`. Y en `pre_tool_call` una
excepción o un timeout **bloquean** (ver `docs/gotchas.md`).

## Decisión

1. Un freno es una función pura `(Event, config, root) -> Decision` en `plugin/harness/guards.py`: sin
   I/O de escritura, sin procesos. Por eso el self-test la llama sin Hermes, y cuesta
   microsegundos en cada tool call.
2. `Decision.to_hermes()` es el único lugar que conoce la forma que Hermes espera, y garantiza que
   un bloqueo siempre lleve mensaje (Hermes ignora un `block` sin mensaje).
3. El mensaje explica qué pasó, por qué importa y qué hacer: es lo único que el agente lee.
4. **Falla abierto**: config ausente o inválido, freno que revienta, núcleo que revienta → deja
   pasar. `evaluate()` atrapa por freno y `_seguro` atrapa en la frontera con Hermes.
5. En el shell hook: exit 2 bloquea; exit 1 no se usa nunca (en Hermes no bloquea y pasa
   desapercibido).

## Por qué fallar abierto

Un arnés roto que bloquea todo se desinstala, y con él se van los frenos que sí servían. El gate
sí falla cerrado (un gate que no puede leer su config es rojo): el que no puede bloquear al humano
es el freno del turno, no el entregable.
