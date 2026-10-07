# Módulo 3 — Sensores y gate (30 min)

**Idea:** un *sensor* actúa **después**: mira lo que pasó y dice si está bien. El gate es el
sensor que define «terminado», y es el criterio de salida del loop del módulo 4. Si el gate
miente, el loop entrega basura con confianza.

## Ejercicio 3.1 — Leer el gate

```bash
ap signal list
ap gate
```

Cada señal tiene `why`: qué error atrapa que ninguna otra ve (P6). Leé los de tu config con
`ap config get gate.signals`. Una señal sin `why` no se sabe para qué está, y nadie se anima a
sacarla cuando estorba.

Fijate el final: una señal **OMITIDA** no es verde. El gate la imprime y quien entrega la nombra.

## Ejercicio 3.2 — Los sensores del turno

Mientras Hermes trabaja hay dos sensores más rápidos que el gate:

- **lint del archivo recién escrito** (`transform_tool_result`): los hallazgos se pegan al
  resultado de la herramienta, y el agente los ve en el mismo turno;
- **gate pendiente al cerrar** (`pre_verify`): si editó código y el gate no quedó verde, Hermes no
  lo deja cerrar el turno. Lo intenta hasta `agent.max_verify_nudges` veces.

Los dos dejan eventos en el panel (`lint`, `verify-pending`) cuando corren dentro de Hermes.

## Ejercicio 3.3 — El sensor del sensor

¿Cómo sabés que el self-test mismo muerde? Rompiéndolo a propósito. En el repo del arnés:

```bash
cd $AUTOPILOT && python3 scripts/mutations.py
```

**Tiene que salir:** `mutations: las N mutaciones ponen rojo el self-test.` Cada mutación rompe
un freno en una copia del repo (que el loop no escale, que el panel escuche en todas las
interfaces, que un freno deje pasar todo…) y exige rojo. Una mutación que sobrevive es un freno
que se puede romper sin que nadie se entere.

## Ejercicio 3.4 — El mapa

```bash
ap map
```

Cada pieza del arnés aparece con su dirección (guía · freno · sensor), su tipo (computacional ·
inferencial) y su etapa. **Para discutir:** ¿qué etapa tiene menos control? ¿Cuánto del arnés es
inferencial? Un control que nadie ubicó en el mapa es uno del que nadie sabe qué cubre: el mapa
sale rojo.

## Ejercicio 3.5 — El costo

```bash
ap timing
```

En Hermes, un `pre_tool_call` que se pasa de tiempo **bloquea** la herramienta. Por eso los
frenos no lanzan procesos y cada callback tiene presupuesto (P19).

→ *pausa* → [Módulo 4](04-loop-autonomo.md)
