# Constitución — Hermes Autopilot

**Versión 1.5.0** · Principios que no se negocian **en este repo**. Las convenciones operativas
viven en `AGENTS.md`; el arnés que los hace cumplir, en `docs/arnes.md`.

Cada principio dice su **fuerza**:

- **BLOCKING** — hay un comando que falla si se viola. No hay excepción por prisa.
- **REVIEW** — no es verificable por máquina todavía; lo evalúa la skill `harness-review`.

Un principio BLOCKING **nombra su comando**. Si no se puede nombrar, es REVIEW: etiquetar de
BLOCKING lo que nadie verifica es la forma más rápida de que nadie crea en este documento.

Enmendar esta constitución es un commit propio, con la versión subida y el motivo en el cuerpo.
Un principio que nadie hace cumplir se borra o se convierte en mecanismo.

---

## P1 — Nada se entrega sin gate verde · BLOCKING

El entregable es `python3 scripts/gate.py`. Una señal **omitida** no es verde: el gate la imprime y
quien entrega la nombra. `gate.py fast` verde tampoco es entregable.

*Mecanismo:* `scripts/gate.py`, el freno de fin de turno del plugin (`pre_verify` →
`plugin/harness/turn.py`) y el job `gate` de CI.

## P2 — Todo freno prueba que muerde · BLOCKING

Toda regla del config queda cubierta por el self-test automáticamente: el caso se **deriva** de
la regla, no se escribe a mano. Toda clase de regla nueva o freno nuevo llega con su caso escrito.

*Mecanismo:* `python3 scripts/selftest.py`.

## P3 — Todo freno prueba que NO muerde de más · BLOCKING

Un freno que bloquea trabajo legítimo se desactiva a mano en una semana. Cada validación es
doble: ¿muerde? y ¿el repo sigue pasando?

*Mecanismo:* el gate corre `python3 scripts/lint.py` sobre el repo entero, y el self-test incluye
casos inocentes (un `git status`, un archivo normal, una memoria normal).

## P4 — La especificidad va en el config, no en el código · BLOCKING

Los frenos son **genéricos**. Toda regla, ruta, patrón, comando **y nombre de herramienta de
Hermes** vive en `.hermes/harness.config.json`. Hermes renombra y suma herramientas entre
versiones (y cada MCP trae las suyas): cablear `terminal` en el código es apagar el freno el día
que alguien conecte otro backend.

*Mecanismo:* regla `INVARIANTE` del lint sobre `plugin/harness/guards.py` (no nombra herramientas) y
la skill `harness-review` para el resto.

## P5 — El contrato del plugin se respeta · BLOCKING

Un freno bloquea devolviendo `{"action": "block", "message": ...}` desde `pre_tool_call`, y ese
mensaje es lo único que el agente lee. En Hermes, un `pre_tool_call` que **lanza una excepción o
se pasa de tiempo bloquea la herramienta**: un arnés con un bug frenaría todo. Por eso ningún
callback lanza, y un config ausente o inválido **nunca** bloquea al humano. En el shell hook,
exit 2 bloquea y exit 1 no se usa (no bloquea y pasa desapercibido).

*Mecanismo:* regla `INVARIANTE` sobre `plugin/__init__.py` (todo callback envuelto en `_seguro`)
y casos del self-test con config roto. El porqué de fallar abierto está en
`docs/decisions/0003-contrato-de-frenos.md`.

## P6 — Cada señal del gate declara qué error atrapa · BLOCKING

Ninguna señal entra sin su campo `why`.

*Mecanismo:* el self-test rechaza una señal sin `why`.

## P7 — El arnés no escribe en el árbol de fuentes · BLOCKING

Probar un freno no crea archivos dentro del código: el contenido va por stdin o en memoria.

*Mecanismo:* los frenos son funciones puras; `scripts/lint.py --stdin`; un caso del self-test
falla si quedaron temporales en la raíz.

## P8 — Rutas protegidas · BLOCKING

Secretos (incluido `~/.hermes/.env`), lockfiles, `.git/` y derivados no los edita el agente. Y los
secretos tampoco los **lee**: lo que el agente lee entra al contexto del modelo, viaja al proveedor
y queda en el historial de la sesión. Escribir y leer son riesgos distintos, con listas distintas.

*Mecanismo:* freno `protected_paths` del plugin + `.githooks/pre-commit`, leyendo la misma lista;
freno `read_guard` y `terminal.readTargets` sobre `protectedReads`; `code_guard` y
`terminal.inlineCode` para lo que el código (`execute_code`, `python3 -c`) nombra; la guardia de
Python (`plugin/guardia`, audit hook PEP 578) para lo que un programa del agente ABRE, aunque arme
la ruta por partes.

## P9 — Acciones amplias: dry-run y reversibilidad · BLOCKING

Antes de borrar, mover o reescribir en lote: commit o backup, mostrar la lista, esperar
confirmación. El instalador es dry-run por defecto y nunca sobreescribe.

*Mecanismo:* freno `terminal_guard` (`terminal.deny`) y el `--apply` explícito de
`scripts/install.py`.

## P10 — La documentación no apunta a la nada · BLOCKING

*Mecanismo:* `python3 scripts/linkcheck.py`, medido contra `git ls-files`.

## P11 — El trabajo queda registrado · BLOCKING

Un commit que toca código referencia su ítem de trabajo, o declara en su propia línea por qué no.

*Mecanismo:* `.githooks/commit-msg` → `scripts/githooks.py`, con casos en el self-test. Lo que
entra a una rama de `branches.protected` entra por PR: `.githooks/pre-push` lo frena antes de la
red (el freno fuerte es la protección de la forja, y hay que activarla igual).

## P12 — Lo que el agente aprende solo pasa por los mismos frenos · BLOCKING

Hermes aprende: escribe su memoria y crea skills sin que nadie las revise. Una memoria o una
skill que contradice a un freno es un freno apagado **en todas las sesiones futuras**, en todas las
plataformas del gateway. Lo aprendido se filtra con las mismas reglas que lo ejecutado.

*Mecanismo:* frenos `memory_guard` y `skill_guard` (heredan `terminal.deny`) y regla `SKILL` del
lint sobre las skills versionadas.

## P13 — Lo desatendido se decide al crearlo · BLOCKING

En un cron o en el gateway no hay humano para aprobar un comando peligroso. Lo que una tarea
programada puede hacer se decide cuando se crea.

*Mecanismo:* freno `cron_guard` (`cron.deny`, `cron.minIntervalMinutes`).

## P14 — El contexto tiene presupuesto · BLOCKING

`AGENTS.md`, la memoria y las skills entran al prompt en cada turno. Un archivo de contexto que
crece sin techo se trunca en silencio y lo que se corta es, justamente, lo último que se agregó.

*Mecanismo:* regla `CONTEXTO` del lint (`context.maxChars`) y `scripts/doctor.py` para la memoria
de `~/.hermes/`.

## P15 — Cada incidente deja infraestructura · BLOCKING

Un problema que costó tiempo termina en el mecanismo más fuerte disponible (test > freno/lint >
skill > markdown). La skill `lesson` es el ciclo.

*Mecanismo:* regla `INCIDENTE` del lint — todo `### GOTCHA` de `docs/gotchas.md` declara
**Síntoma / Causa / Regla / Mecanismo**.

## P16 — Conducta ante el error · REVIEW

Leer la salida real antes de reintentar; reintentar sólo con hipótesis nueva; **2 intentos** sobre
el mismo error y al tercero se para y se escala con el diagnóstico.

*Mecanismo parcial:* dentro del loop autónomo es BLOCKING — el mismo rojo del gate
`loop.sameFailureLimit` veces seguidas para el loop y escala (P21). En una sesión con un humano
sigue siendo juicio.

## P17 — Lo que viaja son los principios, no las reglas ajenas · REVIEW

Las reglas concretas describen los incidentes de **un** repo; en otro son ruido bien intencionado
que gasta contexto del agente y paciencia del equipo. Lo que se comparte entre repos es esta
constitución, el método de portado y las clases de regla. Una regla instalada sin cicatriz detrás
es un hallazgo de review.

*Mecanismo parcial:* regla `PERFIL` del lint (un perfil de stack no lleva `profiles.forbiddenKeys`)
y el aviso de `scripts/drift.py` para la regla que nunca cazó nada en el historial. Que una regla
del repo tenga su cicatriz sigue siendo juicio (`harness-review`).

## P18 — Guía y freno no se contradicen · BLOCKING

Una guía (`AGENTS.md`, una skill, un `reason`) y un freno (`terminal.deny`) se escriben en momentos
distintos y nadie los mira juntos. Cuando chocan, el agente hace lo que le dijeron, el freno lo
bloquea y reintenta en bucle.

*Mecanismo:* regla `COHERENCIA` del lint — un comando de un bloque de shell de `coherence.guides`, o
citado entre backticks en un `reason` del config, no puede casar con `terminal.deny`. Evalúa con
la misma función que el freno.

## P19 — El arnés tiene presupuesto de latencia · BLOCKING

Todo freno se paga en cada tool call. En Hermes, además, un `pre_tool_call` que se pasa de tiempo
**bloquea** la herramienta: un freno lento no es caro, frena todo. Un subprocess dentro de un
freno pasa el self-test (el freno muerde igual) y sólo un número lo ve.

*Mecanismo:* `python3 scripts/timing.py` en el gate — la mediana de cada callback del plugin contra
`observability.budgetMs`.

## P20 — Lo que no cabe en el gate igual está vivo · BLOCKING

Lo que depende del reloj (un `STATUS.md` vencido que el plugin le inyecta al agente como verdad de
hoy) no va en el gate de cada commit: un gate que se pone rojo porque pasó un martes enseña a
ignorarlo. Va en un pipeline declarado, y un control encendido sin nadie que lo corra es
«instalado y muerto». Tampoco entra una pieza al arnés sin que se sepa dónde actúa.

*Mecanismo:* `scripts/drift.py` corrido por `drift.runner` (`.github/workflows/drift.yml`); el
self-test verifica que cada `runner` exista e invoque su comando. `python3 scripts/map.py` en el
gate: una pieza (hook, hook de git, skill, guía, pipeline) sin dirección, tipo y etapa en
`taxonomy` es rojo.

## P21 — El loop autónomo tiene salida, tope y freno de mano · BLOCKING

Un agente que trabaja solo, tarea tras tarea, no se declara terminado a sí mismo: **la salida del
loop es el gate**. Reintenta con el rojo en la mano, no a ciegas; el mismo rojo dos veces es el
bucle de P16 y escala a un humano; hay tope de intentos y de reloj; un humano lo para entre
iteraciones sin matarlo a mitad. Y nunca publica: lo verde queda en una rama, y lo publica una
persona (P13).

El agente tampoco puede tocar lo que decide si terminó: el verificador, sus reglas, su cola. Un
verde conseguido ablandando el criterio de salida no es verde. Y hay un loop por repo, o uno
por worktree cuando las tareas corren en paralelo. Por defecto cada tarea corre AISLADA en su
worktree (`loop.aislar`): lo que git ignora —los secretos— no existe donde trabaja el agente.

*Mecanismo:* `scripts/loop.py` (`decidir`, con la configuración de `loop`; los intocables
—`protectedPaths` versionados y `loop.lockedPaths`— comparados entre intentos; el candado),
self-test §13 (las decisiones y corridas reales con un agente de mentira: verde en el intento 2,
escalada por el mismo rojo, freno de mano, un agente que reescribe su verificador, dos loops) y
mutaciones que sacan cada tope.

## P22 — Lo que el arnés hace se ve fuera de la conversación · BLOCKING

Un freno que muerde sólo dentro del chat que lo provocó es invisible para el equipo: nadie sabe
cuántas veces mordió cada regla ni si el loop está trabado desde hace una hora. Cada bloqueo,
escalada, hallazgo del lint, gate y vuelta del loop queda registrado fuera del árbol de fuentes, y
un panel local lo muestra en vivo. Registrar nunca bloquea (P5) ni lanza procesos (P19).

*Mecanismo:* `plugin/harness/events.py` (`observability.events`), `scripts/panel.py` (sólo
`127.0.0.1` por defecto) y self-test §13 (el plugin registra lo que frena y no lo que deja pasar;
el registro rota; el panel responde y empuja por SSE).

## P23 — Lo que el arnés promete se reproduce de punta a punta · BLOCKING

Que cada freno muerda suelto (P2) no prueba que la historia entera funcione: un agente con un
atajo real, el freno que lo para, el motivo que lo hace cambiar de camino, el loop que escala o
llega a verde, en un repo instalado de cero. Cada clase de incidente que el arnés dice cubrir
tiene un caso que la reproduce, en un dominio reconocible (programación, infraestructura, oficina,
datos, soporte, operación), y un caso que deja de dar lo esperado es rojo.

*Mecanismo:* `scripts/casos.py` en el gate (la señal `casos replicables`); cada caso en `casos/<id>/`
con sus corridas esperadas. El agente es determinista, pero sus acciones pasan por el plugin
real. Self-test §13: la forma del catálogo, que el runner compare de verdad y que las reglas de
un caso no muerdan sus inocentes. Lo que los casos no cubren está en `docs/huecos.md`.

## P24 — Lo que entra de un tercero no sale solo · BLOCKING

Un texto no dice si es dato o instrucción: la inyección de prompt no se detecta. Su daño sí se
corta, porque necesita tres cosas juntas —datos, contenido de un tercero y un canal hacia afuera—.
Una sesión que leyó contenido de terceros (una web, un ticket, un correo) no publica, no habla con
otro servidor, no escribe donde una instrucción quedaría permanente (AGENTS.md, CI, skills) y no
guarda memoria sin un humano. En el loop o en cron, sin humano, no lo hace.

*Mecanismo:* sesión contaminada (`taint` en el config, `taint_guard` + la marca del plugin), con su
caso en el self-test, mutaciones y el caso `soporte-ticket-inyeccion` (modo `persistente`).

## P25 — Un sensor inferencial se mide con una tasa · BLOCKING

Un juicio de un modelo (`harness-review`) acierta a veces: no se prueba con un ejemplo que muerde,
se mide contra un conjunto etiquetado, con umbrales. Sin modelo, la medición sale OMITIDA —nunca
verde— y la corre un pipeline que sí lo tiene.

*Mecanismo:* `scripts/revision.py` (recall y precisión contra `evals/revision.json`, umbrales en
`review`), señal del gate con `omitIfExit` y `hermes-nocturno.yml`.

## Precedencia — cuando dos BLOCKING chocan · REVIEW

Gana el más alto y **el agente para y escala**: 1) P8·P9, 2) P5, 3) P1, 4) el resto en orden.

---

### Historial

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0.0 | 2026-09-30 | Primera versión, derivada de la constitución de `agent-harness` (Claude Code) y adaptada a Hermes: P12–P14 son nuevos (aprendizaje, desatendido, presupuesto de contexto). |
| 1.1.0 | 2026-09-30 | Prácticas de `agent-harness` (1.2.0) que faltaban: P17 (viajan los principios; `PERFIL`), P18 (guía y freno coherentes; `COHERENCIA`), P19 (presupuesto de latencia; `timing.py`), P20 (deriva programada y mapa guía/freno/sensor). P11 suma `pre-push`. Numeración nueva al final para no romper las referencias a P1–P16. |
| 1.2.0 | 2026-10-07 | Autonomía: P21 (el loop autónomo tiene salida —el gate—, tope y freno de mano; nunca publica) y P22 (lo que el arnés hace se ve: registro de eventos y panel en vivo). P16 gana mecanismo dentro del loop. El proyecto pasa a llamarse Hermes Autopilot: el propósito es un agente autónomo, y el arnés es lo que lo hace confiable. |
| 1.3.0 | 2026-10-07 | Auditoría de huecos con casos replicables: P8 también veda **leer** secretos (`protectedReads`); P21 suma los intocables (el agente no ablanda su criterio de salida) y el candado; P23 (lo que el arnés promete se reproduce de punta a punta: `scripts/casos.py` en el gate). |
| 1.4.0 | 2026-10-08 | Herramientas verificadas contra el código de Hermes: P8 suma `code_guard` (`execute_code` no pasaba por ningún freno) y el código en línea; P21 suma el paralelo por worktrees. |
| 1.5.0 | 2026-10-08 | Cierre de huecos: P8 suma la guardia de Python; P21, el loop aislado en worktree; P24 (lo que entra de un tercero no sale solo: sesión contaminada); P25 (un sensor inferencial se mide con una tasa: `revision.py`). |
