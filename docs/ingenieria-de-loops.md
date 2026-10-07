# Ingeniería de loops — un agente autónomo es una pila de lazos de control

Un agente autónomo no es un modelo bueno: es un modelo metido en lazos de retroalimentación bien
hechos. Cada lazo tiene un **sensor** (qué mira), un **actuador** (qué cambia), un **criterio de
salida** (cuándo termina), un **tope** (cuándo deja de intentar) y un **lugar donde se ve**. Si
le falta cualquiera de los cinco, no es autonomía: es un `while true` caro.

Este documento lista los lazos de Hermes Autopilot, del más rápido al más lento, y qué pieza
cumple cada rol. El marco de guías, frenos y sensores está en
[`guias-y-sensores.md`](guias-y-sensores.md). Cómo se opera el lazo de la tarea está en
[`loop-autonomo.md`](loop-autonomo.md).

## Los ocho lazos

| # | Lazo | Frecuencia | Sensor | Actuador (qué recibe el agente) | Sale cuando | Tope | Se ve en |
|---|---|---|---|---|---|---|---|
| 1 | herramienta | cada tool call (ms) | `pre_tool_call`: `terminal.deny`, `protectedPaths`, `patterns`, memoria, skills, cron | el `reason` del freno, como resultado de la herramienta | el agente reformula | — (el freno no cede) | eventos `block` / `ask` |
| 2 | escritura | cada archivo escrito (s) | lint del archivo recién escrito (`transform_tool_result`) | los hallazgos, pegados al resultado | el archivo pasa el lint | — | eventos `lint` |
| 3 | turno | cada cierre de turno (min) | `pre_verify`: ¿hay código editado con el gate pendiente? | «corré el gate y arreglá lo rojo» | el gate queda verde | `agent.max_verify_nudges` de Hermes (3) | eventos `verify-pending` |
| 4 | **tarea** | cada tarea (min a h) | **el gate completo** (`loop.gateCommand`) | la tarea, y en el reintento las señales rojas y la cola de la salida | gate verde | `sameFailureLimit` (mismo rojo), `maxIterations`, `maxMinutes`, `stopFile` | panel: loop, intentos, tareas |
| 5 | integración | cada commit, push y PR (h) | `pre-commit`, `commit-msg`, `pre-push`, el gate en CI (Linux · macOS · Windows) | el mensaje del hook; el check rojo del PR | CI verde y revisión humana | — (sin humano no entra a `main`) | el PR |
| 6 | deriva | semanal | `scripts/drift.py` por `drift.yml` | rojo en el pipeline | `STATUS.md` al día | — | Actions |
| 7 | aprendizaje | cada incidente | un humano o el agente notan que algo costó tiempo | skill `lesson`: el mecanismo más fuerte disponible (P15) | el incidente tiene su freno, su caso y su `### GOTCHA` | — | `docs/gotchas.md`, el historial |
| 8 | el arnés sobre sí mismo | cada gate | `scripts/mutations.py` (el sensor del sensor), `map.py`, `timing.py` | señal roja del gate | cada mutación pone rojo el self-test | — | el gate |

Los lazos se **anidan**: el lazo de la tarea (4) contiene muchos turnos (3), cada turno contiene
muchas herramientas (1, 2), y lo que sale del lazo de la tarea entra al de integración (5). Un
lazo interno sano hace barato al externo. Un freno que corta un `--no-verify` en el lazo 1 ahorra
un PR rojo en el lazo 5.

## Las siete reglas de un lazo bien hecho

1. **La salida la decide un sensor, no el actor.** El agente no se declara terminado: el lazo 3
   le pide el gate y el lazo 4 lo corre él mismo. `scripts/loop.py` registra lo que dice el
   agente, pero solo decide con el código de salida del gate.
2. **El error vuelve con contenido.** Un «falló» no sirve para reintentar. El `reason` de un freno
   dice qué pasó, por qué importa y qué hacer. El reintento del loop lleva las señales rojas y la
   cola de la salida del gate (`loop.retryPrompt`).
3. **El mismo error dos veces es un bucle, no persistencia.** P16 dice «2 intentos sobre el mismo
   error; al tercero se para y se escala». En el lazo 4 eso es mecanismo: la *firma* de un rojo
   (los nombres de las señales `✗`, sin duraciones) se compara entre intentos. Con
   `sameFailureLimit` iguales seguidos, el loop para y escala. Dos rojos distintos sí son
   progreso: hubo hipótesis nueva.
4. **Todo lazo tiene tope.** Hay tope de intentos, de reloj y de nudges. Un lazo sin tope no es
   autónomo: es desatendido, y lo desatendido se decide al crearlo (P13).
5. **La latencia es proporcional a la frecuencia.** El lazo 1 corre en cada tool call. Por eso no
   lanza procesos y tiene presupuesto medido (P19, `timing.py`). El gate completo es caro y corre
   una vez por intento, no por herramienta.
6. **Un humano puede frenar sin romper.** `loop.py --stop` crea el `stopFile`. El loop termina la
   iteración en curso y para, sin matar al agente con un archivo a medio escribir.
7. **Lo que pasa adentro se ve afuera.** Cada bloqueo, escalada, hallazgo, gate y vuelta del loop
   queda en el registro de eventos (P22), y el panel lo muestra en vivo. Un lazo que nadie ve es
   un lazo que nadie ajusta.

Y una regla que no es de control sino de responsabilidad: **ningún lazo publica**. El lazo 4
deja lo verde en una rama `loop/*`. El lazo 5 exige PR. Empujar es `terminal.ask` y, en cron,
está vedado (`cron.deny`).

## Lo que este arnés todavía no cierra

| Hueco | Por qué importa | Estado |
|---|---|---|
| un sensor **inferencial** con tasa de acierto (`harness-review` no tiene prueba de vida) | lo que el gate no puede verificar (diseño, intención) queda a juicio sin medir | abierto: ver [`guias-y-sensores.md`](guias-y-sensores.md) §6 |
| varias tareas **en paralelo** (worktrees) | el loop trabaja una tarea a la vez, en una rama | abierto |
| el loop **abre el PR** | hoy lo publica un humano, a propósito (P13) | decisión, no hueco |
| calidad de las **pruebas** del repo destino | el lazo 4 es tan bueno como el gate que lo cierra: si las pruebas no prueban nada, el verde no significa nada | del repo destino |
