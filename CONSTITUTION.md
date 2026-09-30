# Constitución — Hermes Harness

**Versión 1.0.0** · Principios que no se negocian **en este repo**. Las convenciones operativas
viven en `AGENTS.md`; el arnés que los hace cumplir, en `docs/arnes.md`.

Cada principio dice su **fuerza**:

- **BLOCKING** — hay un comando que falla si se viola. No hay excepción por prisa.
- **REVIEW** — no es verificable por máquina todavía; lo evalúa la skill `harness-review`.

Un principio BLOCKING **nombra su comando**. Si no se puede nombrar, es REVIEW: etiquetar de
BLOCKING lo que nadie verifica es la forma más rápida de que nadie crea en este documento.

Enmendar esta constitución es un commit propio, con la versión subida y el motivo en el cuerpo.

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

Secretos (incluido `~/.hermes/.env`), lockfiles, `.git/` y derivados no los edita el agente.

*Mecanismo:* freno `protected_paths` del plugin + `.githooks/pre-commit`, leyendo la misma lista.

## P9 — Acciones amplias: dry-run y reversibilidad · BLOCKING

Antes de borrar, mover o reescribir en lote: commit o backup, mostrar la lista, esperar
confirmación. El instalador es dry-run por defecto y nunca sobreescribe.

*Mecanismo:* freno `terminal_guard` (`terminal.deny`) y el `--apply` explícito de
`scripts/install.py`.

## P10 — La documentación no apunta a la nada · BLOCKING

*Mecanismo:* `python3 scripts/linkcheck.py`, medido contra `git ls-files`.

## P11 — El trabajo queda registrado · BLOCKING

Un commit que toca código referencia su ítem de trabajo, o declara en su propia línea por qué no.

*Mecanismo:* `.githooks/commit-msg` → `scripts/githooks.py`, con casos en el self-test.

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

## Precedencia — cuando dos BLOCKING chocan · REVIEW

Gana el más alto y **el agente para y escala**: 1) P8·P9, 2) P5, 3) P1, 4) el resto en orden.

---

### Historial

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0.0 | 2026-09-30 | Primera versión, derivada de la constitución de `agent-harness` (Claude Code) y adaptada a Hermes: P12–P14 son nuevos (aprendizaje, desatendido, presupuesto de contexto). |
