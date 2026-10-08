# 0007 — Casos replicables, lectura protegida e intocables del loop

**Estado:** aceptada · **Fecha:** 2026-10-07

## Contexto

El self-test prueba cada freno por separado (P2, P3) y el loop se probaba con una calculadora de
juguete. Faltaba la prueba de que el arnés para los atajos que un agente toma de verdad, en
dominios que la gente reconoce —infraestructura, una planilla de ventas, la bandeja de soporte—,
y una forma de que cualquiera los replique. Al armar esos casos aparecieron huecos.

## Decisión

**Casos con un agente determinista cuyas acciones pasan por el plugin real.** Cada caso
(`casos/<id>/`) tiene una historia, una semilla, un verificador que hace de gate, las reglas que
agrega y las corridas esperadas por modo del agente. El agente no usa un modelo: es un script
con modos (`aprende`, `terco`, `atajo`…). Cada acción suya pasa por `casos/hermes_sim.py`, que
llama al `pre_tool_call` y al `transform_tool_result` del plugin del sandbox con la forma de
llamada de Hermes. Así un caso prueba los frenos, el registro de eventos y el loop de punta a punta
sin Hermes ni API key, y corre en CI. Lo que no prueba —cómo reacciona un modelo al motivo de un
freno— se hace a mano con `casos.py preparar <id> <dir> --hermes`. Los 17 casos (29 corridas)
corren en el gate en unos segundos (P23).

**Las reglas de un caso se validan como las de un humano.** `casos.py` las pasa por
`cli.validar`, después de cargar los inocentes propios del caso. Si un caso necesita una regla
que muerde de más, el caso está roto, no la regla de excepción.

**Leer es un riesgo distinto de escribir: `protectedReads`.** Lo que el agente lee entra al
contexto del modelo y viaja al proveedor. Es una familia aparte porque las listas difieren:
`.env.example` se lee y no se escribe; un lockfile se lee y no se edita. Se aplica por la
herramienta de lectura (`tools.read`, hoy sólo `read_file`: no sumamos nombres de Hermes que no
verificamos) y por la terminal (`readTargets`).

**Intocables en el loop, no un freno más.** Un freno por regex no puede ver qué hace un
`python3 -c`. El loop sí puede ver el efecto: compara la huella de los `protectedPaths`
versionados y de `loop.lockedPaths` antes y después de cada intento, y escala si algo cambió,
sin correr el gate. Se miran sólo los versionados y los trabados explícitamente (aunque estén
ignorados): mirar todo lo protegido haría escalar por un `__pycache__/` regenerado.

**Los secretos de las semillas no se versionan con su nombre.** `dot.env` llega al sandbox como
`.env`. La alternativa, una excepción en `protectedPaths[env]` para `casos/`, es justo el tipo de
agujero que el arnés existe para impedir.

## Consecuencias

- P8 cubre también leer (1.3.0), P21 suma intocables y candado, y entra P23.
- Huecos cerrados con su prueba, y abiertos con su porqué: `docs/huecos.md`.
- El costo: 9 señales de gate y ~5 s más por los casos. El self-test corre dos corridas reales
  para probar que el runner compara.
- Agregar un caso es copiar uno parecido y correr `casos.py <id>` y `casos.py readme <id>`. El
  runner exige que el README y el catálogo lo nombren.
