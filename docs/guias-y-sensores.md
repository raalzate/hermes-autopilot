# Guías y sensores — el marco de *harness engineering*, aplicado a Hermes

Fuente: Birgitta Böckeler, [*Harness engineering for coding agent users*](https://martinfowler.com/articles/harness-engineering.html)
(martinfowler.com, abril de 2026), el mismo marco que usa `agent-harness`. Este documento no lo
resume: contesta, idea por idea, **qué mecanismo de este repo la hace cumplir y cuál queda como
hueco declarado**. El mapa vivo, pieza por pieza, lo imprime `python3 scripts/map.py`.

## 1. Tres momentos de control

- **Guía** (*feedforward*): orienta **antes** de que el agente decida.
- **Freno**: ve la acción ya decidida y todavía no ejecutada. En Hermes es `pre_tool_call`.
- **Sensor** (*feedback*): observa **después** y le da al agente con qué corregirse.

Con una sola dirección se falla de forma predecible: sólo sensores, y el agente repite el error;
sólo guías, y nunca se entera de si sirvieron.

| Momento | Mecanismo | Qué hace |
|---|---|---|
| **Guía** | `AGENTS.md`, `CONSTITUTION.md`, las skills | convenciones y el porqué, en prosa |
| | sección `repo-harness.status` del system prompt | rama, hooks de git, gate pendiente y la cabeza de `STATUS.md` |
| | `pre_llm_call` (`routes`) | una pista según el pedido |
| **Freno** | `pre_tool_call`: `terminal_guard`, `protected_paths`, `content_patterns`, `memory_guard`, `skill_guard`, `cron_guard` | `{"action": "block"}` con un `message` que dice qué pasó, por qué importa y qué hacer |
| | `.githooks/pre-push` | a una rama protegida se entra por PR |
| **Sensor** | `transform_tool_result` | el lint del archivo recién escrito, en el mismo turno |
| | `pre_verify` | no deja cerrar el turno con el gate pendiente |
| | `.githooks/pre-commit`, `commit-msg`, CI | el gate en los lugares donde el trabajo sale |
| | skill `harness-review` | juicio sobre lo que ninguna regla ve |

**Sensores escritos para un modelo.** Un sensor rinde más cuando su salida está pensada para que
el modelo se corrija solo. Es la regla de la casa: *los mensajes de bloqueo explican el porqué*.

## 2. Computacional e inferencial

La constitución ya está escrita con esta partición: un principio BLOCKING nombra el comando que
falla (computacional); uno REVIEW lo evalúa la skill `harness-review` (inferencial). El sesgo es
deliberado: todo lo que se pueda volver computacional, se vuelve (P15: test > freno/lint > skill >
markdown).

## 3. La calidad a la izquierda: cada etapa, su costo

| Etapa | Costo | Control |
|---|---|---|
| sesión y pedido | ~0 | sección de estado, `pre_llm_call` |
| acción decidida | < 1 ms (medido) | `pre_tool_call` |
| herramienta ejecutada | < 1 ms (medido) | `transform_tool_result` |
| fin del turno | el gate | `pre_verify` pide correrlo |
| commit / push | barato | `pre-commit`, `commit-msg`, `pre-push` |
| integración | el gate, en limpio | CI (`.github/workflows/ci.yml`), el mismo `scripts/gate.py` |
| continuo | semanal | `.github/workflows/drift.yml`: el gate sobre main y `scripts/drift.py` |

Dos reglas que salieron de incidentes en `agent-harness` y valen doble acá:

- **Cada etapa tiene presupuesto** (P19). En Hermes un `pre_tool_call` que se pasa de tiempo
  **bloquea** la herramienta, así que la latencia no es comodidad: es contrato. `scripts/timing.py`
  la mide en el gate contra `observability.budgetMs`.
- **La etapa temprana no reemplaza a la tardía.** `gate.py fast` verde no es verde (P1).

## 4. Plantillas de arnés y la ley de Ashby

`plantillas/perfiles/` + `scripts/install.py` son plantillas de arnés, con un límite: **un perfil
lleva la forma del lenguaje y nunca reglas** (P17). La regla `PERFIL` del lint lo hace cumplir.

*Un regulador sólo regula aquello de lo que tiene un modelo.* El modelo acá es
`.hermes/harness.config.json` (P4): los frenos no saben nada del repo, así que regulan exactamente
lo que el config describe.

## 5. El lugar del humano

- **fugas a la vista:** `no-issue: <motivo>` queda firmado en el historial;
- **`terminal.ask`**: lo que no se prohíbe pero se escala a la aprobación humana de Hermes;
- **lo desatendido se decide al crearlo** (P13): en cron no hay humano que apruebe;
- **la skill `lesson`** convierte el juicio del humano sobre un incidente en un mecanismo.

## 6. Las preguntas abiertas, contestadas o declaradas

| Pregunta | Respuesta de este arnés | Estado |
|---|---|---|
| ¿Cómo mantener **coherentes** guías y frenos? | una sola fuente (el config, que leen el plugin y los hooks de git); los casos del self-test salen del `example` de cada regla; y la regla `COHERENCIA`: lo que una guía recomienda en un bloque de shell, o un `reason` ofrece como salida, no puede estar en `terminal.deny` (P18) | cubierto |
| ¿Cómo medir la **cobertura** del arnés? | cada regla con su `example` por el plugin real (P2), inocentes que no deben frenar (P3), 97 mutaciones que tienen que poner rojo el self-test, y `scripts/map.py` con las etapas sin control | cubierto |
| ¿Cómo se **ve** lo que el arnés hace? | registro de eventos y `scripts/panel.py` en vivo (P22); cuántas veces mordió cada regla se lee del registro | cubierto |
| ¿Quién cierra el **lazo de la tarea**? | `scripts/loop.py`: el gate como salida, el mismo rojo escala (P16 → P21). Ver [`ingenieria-de-loops.md`](ingenieria-de-loops.md) | cubierto |
| ¿Cuánto **cuesta**? | `scripts/timing.py`, en el gate | cubierto |
| ¿Qué pasa cuando **dos instrucciones chocan**? | la precedencia de la constitución, y parar y escalar | declarado (REVIEW) |
| ¿Cómo se prueba un control **inferencial**? | con una tasa, no con un ejemplo: `scripts/revision.py` mide recall y precisión del revisor contra 16 diffs etiquetados salidos de los casos (`evals/revision.json`), con umbrales en `review`. Sin modelo sale OMITIDA; lo corre `hermes-nocturno.yml` con la key como secreto | cubierto (se activa con el secreto `HERMES_ENV`) |
| **Deriva** continua | `scripts/drift.py` por `drift.yml`: un `STATUS.md` vencido es rojo; una regla que nunca cazó nada es aviso (P20) | cubierto para el arnés |
| **Comportamiento** | la forma del proceso (gate, registro); que las pruebas prueben algo es del repo destino | a medias |

Lo que queda abierto está en la columna de estado para que nadie lo asuma cubierto.
