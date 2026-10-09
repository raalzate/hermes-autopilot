# 0011 — Lo que queda en el texto, lo que aprueba un humano y la sesión interactiva

**Estado:** aceptada · **Fecha:** 2026-10-09

## Contexto

Después de las integraciones (ADR 0010) quedaban cinco huecos abiertos en [`huecos.md`](../huecos.md).
Tres se habían dado por imposibles con un argumento sobre Hermes que el código no sostiene:

- «Hermes no le avisa al plugin que una aprobación se concedió». Sí avisa: `post_tool_call` corre
  después de ejecutar, con `status="blocked"` cuando el freno o el humano dijeron que no
  (`model_tools.handle_function_call`, hermes-agent `aa74e184`).
- «Lo que queda en el texto de la respuesta no pasa por ningún hook». Pasa: `transform_llm_output`
  recibe la respuesta final y la puede reemplazar **antes** de mostrarla y de guardarla en el
  historial (`agent/turn_finalizer.py::apply_llm_output_transform`).
- «La guardia de Python sólo sirve en el loop porque viaja en `HARNESS_GUARDIA`». Es cierto que esa
  variable no llega: `execute_code` arma el entorno de su proceso con una lista blanca. Pero en la
  lista está `PYTHONPATH` (`tools/code_execution_env.py::_SAFE_ENV_PREFIXES`).

## Decisión

1. **Lo aprobado gasta presupuesto.** El plugin recuerda cada escalada con presupuesto (por
   `tool_call_id`, con un tope de 256 en memoria) y la cuenta en `post_tool_call` si se ejecutó.
   Una aprobación negada no gasta.
2. **Lo que dice lo que sale** (`integrations.content`). Cada texto de una llamada `send`/`write`
   de una integración se compara con reglas `deny`: un secreto o una plantilla sin completar frenan
   aunque el destinatario esté en la lista. Si el texto es *correcto* sigue siendo del humano.
3. **La respuesta del turno** (`output`). Los secretos se tapan; si la sesión leyó contenido de
   terceros, la respuesta lleva al pie de qué fuente. Es un freno sobre el texto, no un detector de
   inyección: el arnés no sabe si el texto obedeció, el humano sí sabe que pudo pasar.
4. **La guardia en la sesión** (`sessionGuard.python`). Al registrarse, el plugin pone
   `plugin/guardia` en el `PYTHONPATH` del proceso de Hermes; en la primera herramienta deja el
   spec en `.git/harness-guardia.json`, y `sitecustomize` lo encuentra subiendo desde el cwd. En la
   plantilla viene apagada: un test que lee el `.env` a propósito se frenaría, y eso lo decide el
   dueño del repo. `doctor.py` avisa cuando hay secretos en el disco y está apagada.
5. **La portada no inventa números.** Cada cifra lleva `data-cifra` y la copia `casos.py cifras`
   desde su fuente (`STATUS.md`, `huecos.md`, la constitución, el catálogo de casos); la señal de
   casos del gate es roja si quedó vieja.

## Consecuencias

- 28 huecos cerrados y 4 abiertos. Los que quedan son, de verdad, de juicio: si un texto obedeció
  una inyección, si un mensaje permitido es correcto, un programa no-Python fuera del loop, y el
  loop con un modelo real como agente (necesita una key).
- El revisor inferencial se midió una vez con un modelo real (Claude Sonnet 5.5 por `claude -p`):
  recall 100 %, precisión 91 %. La medición queda en `evals/mediciones/` y es repetible con el
  comando que trae en la cabecera.
- El plugin pasa de 4 a 6 hooks; `timing.py` mide los dos nuevos contra el mismo presupuesto.
