# 0006 — Autonomía: loop externo, CLI que prueba antes de escribir, panel local por SSE

**Estado:** aceptada · **Fecha:** 2026-10-07

## Contexto

El arnés gobernaba el **turno** de Hermes (frenos, lint, gate pendiente al cerrar), pero el
propósito es un agente **autónomo**: que tome trabajo, lo termine y lo entregue sin que alguien
le escriba cada paso. Faltaban tres cosas:

1. el lazo de la **tarea**: alguien que le dé trabajo al agente, decida si terminó y qué hacer
   si no;
2. una forma de **parametrizar** el arnés que no fuera editar a mano un JSON de 800 líneas lleno
   de regex;
3. una forma de **ver** qué hace el arnés fuera de la conversación que lo provocó.

## Decisión

**Loop externo, no un hook.** `scripts/loop.py` es un proceso aparte que invoca a Hermes no
interactivo (`loop.agentCommand`) y después corre el gate (`loop.gateCommand`). Un hook de Hermes
no podría hacerlo: `pre_verify` ya tiene su tope (`max_verify_nudges`), y meter el gate completo
dentro de un callback rompería P19. Afuera, el loop no depende de la versión de Hermes, funciona
igual con otro agente (en el workshop, uno de juguete) y se prueba de punta a punta sin Hermes.

- **La salida es el gate**, nunca lo que el agente dice de sí mismo.
- **La firma de un rojo** es el conjunto de señales `✗` del gate, sin duraciones. Comparar texto
  completo haría que el mismo error pareciera distinto en cada intento y el loop nunca escalaría.
- **Escala con el mismo rojo `sameFailureLimit` veces seguidas** (P16 hecho mecanismo), y con
  `maxIterations` y `maxMinutes`.
- **Freno de mano por archivo** (`stopFile`), leído entre intentos: parar no deja nada a medio
  escribir.
- **stdin cerrado** para el agente y el gate. En el loop no hay humano: un `pdb` o una aprobación
  interactiva reciben EOF en vez de esperar hasta el timeout.
- **Nunca publica** (P13): abre una rama si arranca en una protegida y deja lo verde ahí.

**CLI que prueba antes de escribir.** `scripts/cli.py rule add` pasa la regla nueva por
`guards.evaluate` —el mismo camino que el plugin— con su `example`, sus `moreExamples`, los
inocentes de la familia y el gate del repo, y corre el lint sobre el config resultante. Recién
entonces escribe, y solo con `--apply`. La alternativa, escribir y dejar que el self-test se queje,
deja una ventana donde el config en disco frena el gate (y con eso, al loop).

**Panel local por SSE.** `scripts/panel.py` es `http.server` más un `EventSource`. Sin websockets,
sin build y sin dependencias (ADR 0002). La fuente es un registro JSONL bajo `.git/` que escriben el
plugin, el gate y el loop. El servidor mira las fechas de modificación cada segundo y empuja el
estado entero cuando cambia. Escucha en `127.0.0.1` por defecto: el estado incluye motivos de
frenos y salida del gate.

**El registro lo escribe el adaptador, no los frenos.** Los frenos siguen siendo funciones puras
(ADR 0003). `plugin/__init__.py` registra la `Decision` que devolvieron. El registro nunca lanza,
no lanza procesos y tiene techo (`maxBytes`, rota a `.1`).

## Consecuencias

- P21 y P22 entran a la constitución (1.2.0), con su caso en el self-test §13 y sus mutaciones.
- El ensayo del workshop destapó dos bugs que ya existían en todo repo instalado, y se cerraron
  con un caso cada uno:
  - el gate salía **rojo de entrada**: el self-test intentaba re-portar el arnés desde
    `.hermes/harness/`. El portado anidado del self-test corre con `HARNESS_NESTED` y no lo veía;
  - el pre-commit **no dejaba commitear** la plantilla del config, que trae el ejemplo de la clave
    privada.
- El proyecto pasa a llamarse **Hermes Autopilot**: el propósito es el agente autónomo, y el arnés
  es lo que lo hace confiable. El plugin sigue llamándose `repo-harness`, porque renombrarlo rompe
  las instalaciones existentes (`$HERMES_HOME/plugins/repo-harness`, `hermes plugins enable`).
- Queda abierto: varias tareas en paralelo (worktrees) y un sensor inferencial con tasa de acierto.
