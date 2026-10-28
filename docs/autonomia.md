# Autonomía por niveles: se gana con evidencia

Un agente nuevo no arranca confiable: arranca **observando**. Hermes Autopilot gradúa lo que el
agente puede hacer en cuatro niveles (P27). Sube de a uno, cuando la evidencia alcanza y un humano
firma, y baja solo cuando algo sale mal (P28). En todo momento se ve dónde está y qué le falta (P29).

| Nivel | Nombre | Puede | No puede |
|---|---|---|---|
| **L0** | Observador | leer el repo, correr comandos de sólo lectura (`git status/diff/log`, `ls`, `cat`, `grep`) y reportar en la respuesta | escribir, correr tests, ejecutar código, guardar memoria, usar integraciones que no sean de lectura |
| **L1** | Recomendar | todo lo de L0, correr el gate y los tests, y escribir propuestas en `.hermes/recomendaciones/` | cambiar código o configuración |
| **L2** | Con aprobación | cambiar el repo, con un humano que aprueba antes cada escritura, cada comando que cambia algo y cada código ejecutado | trabajar desatendido: sin humano, la aprobación se niega |
| **L3** | Autonomía | trabajar solo, también desatendido en el loop | lo que vedan los frenos del repo, que siguen mordiendo |

Toda instalación arranca en **L0**. Qué permite cada nivel, cuánta evidencia hace falta y qué lo
hace bajar se declara en la clave `autonomia` del config: son decisiones del equipo, no del arnés.

## Cómo se hace cumplir

El freno de nivel (`nivel_guard`, en `plugin/harness/guards.py`) corre en cada tool call **antes**
que los otros frenos.

- **Si bloquea, gana.** El mensaje dice en qué nivel está el agente, qué puede hacer y dónde ver lo
  que le falta.
- **Si pide aprobación** (L2), los frenos del repo corren igual y un bloqueo de ellos le gana.
  Aprobar un cambio no aprueba un `git commit --no-verify`.
- **La terminal de sólo lectura se evalúa por subcomando.** `git status && rm -r src` no pasa por
  ser `git status`. Una sustitución (`$(…)`, backticks) o una redirección (`>`, salvo `2>&1`)
  nunca pasa como lectura.
- **El loop autónomo no arranca** en un nivel sin `loop: true`, y explica qué evidencia falta.
- **Un estado ilegible vale L0.** Un archivo roto no regala autonomía (ADR 0012).

## La evidencia

Sale del registro de eventos (`observability.events`), contada **desde la última transición**.
Cambiar de nivel reinicia la ventana.

| Métrica | Qué cuenta | Evento |
|---|---|---|
| `sesionesLimpias` | sesiones en las que el agente no intentó salirse de su nivel | `turno` (una vez por sesión), menos las sesiones con un `block` de una regla `nivel-*` del agente |
| `intentosFueraDeNivel` | bloqueos del freno de nivel que son del agente | `block` con regla `nivel-*` y sin `origen` |
| `recomendaciones`, `aceptadasMin` | propuestas de L1 juzgadas, y la proporción aceptada | `recomendacion` |
| `hallazgosJuzgados`, `falsosPositivosMax` | alertas del agente que una persona juzgó, y la proporción que no era real | `hallazgo` |
| `certificadosVerificadosMin` | propuestas juzgadas cuyo porqué comprobó el verificador del repo | `recomendacion` con `certificado` |
| `cambiosAprobados`, `denegadosMax` | aprobaciones de L2 concedidas, y la proporción denegada | `aprobacion` (lo registra `post_tool_call`) |
| `gatesMin`, `gateVerdeMin` | gates completos corridos, y la proporción verde | `gate` |
| `tamperings` | veces que el agente tocó intocables durante una tarea del loop | `tampering` |
| `diasMin` | días en el nivel | — |

Los umbrales de la plantilla:

```json
"ascenso": {
  "L0->L1": {"sesionesLimpias": 3},
  "L1->L2": {"recomendaciones": 5, "aceptadasMin": 0.8, "sesionesLimpias": 3},
  "L2->L3": {"cambiosAprobados": 10, "denegadosMax": 0.1, "gatesMin": 3, "gateVerdeMin": 0.9, "tamperings": 0}
}
```

Una métrica que el arnés no sabe medir **no se da por cumplida**. Si un umbral la nombra con un
error de tipeo, nadie sube.

**Un bloqueo que no es del agente no le resta.** Una herramienta de una integración que no está en
`toolNames` de su manifiesto es nueva: vale `write` y se bloquea igual, pero el evento lleva
`origen: config` y el panel lo muestra como alerta («clasificala en su manifiesto»). Lo que Hermes
hace por su cuenta (la revisión de skills en segundo plano) lo avisa `doctor.py`. Lo aprendió el
piloto doctiling-sre: sus dos primeros bloqueos fueron del arnés y de Hermes.

**Obedecer no es lo mismo que acertar.** Las métricas de la plantilla miden que el agente no se
salga del nivel. Para un agente que observa y avisa, sumá `hallazgosJuzgados` y
`falsosPositivosMax`: cuántas de sus alertas juzgó una persona y cuántas no eran reales.

## Subir: evidencia y firma

```bash
python3 .hermes/harness/scripts/cli.py nivel                          # dónde está y qué le falta
python3 .hermes/harness/scripts/cli.py nivel subir --firma "Ana Pérez"
```

`subir` se niega si la evidencia no alcanza y lista lo que falta. Nunca salta niveles.

En L1, las propuestas del agente se juzgan con:

```bash
python3 .hermes/harness/scripts/cli.py recomendacion list
python3 .hermes/harness/scripts/cli.py recomendacion aceptar .hermes/recomendaciones/001-x.md --firma "Ana Pérez"
```

**El agente no se firma a sí mismo.** Si corre estos comandos, la regla `nivel-firma` de
`terminal.ask` se lo escala al humano, y desatendido se niega. El estado vive bajo `.git/`, que el
agente no escribe.

## Producción: sin shell ni `.git`

Un agente desplegado (un contenedor, un servicio administrado) no tiene `.git` ni una terminal
estable para firmar. El piloto doctiling-sre lo resolvió así, y quedó en el arnés
([ADR 0014](decisions/0014-piloto-en-produccion.md)):

- **El estado en un volumen.** `HARNESS_AUTONOMIA_FILE=/ruta/absoluta.json` (como
  `HARNESS_EVENTS_FILE` para el registro). Sin ninguna transición, la evidencia cuenta desde el
  primer evento del registro: los días corren desde que el agente empezó a trabajar.
- **Firmar es mergear.** `autonomia.firmadas` apunta a un archivo versionado:

  ```json
  {"transiciones": [
    {"id": "2026-10-27-l1", "accion": "subir", "firma": "Ana Pérez"},
    {"id": "2026-11-02-l0", "accion": "declarar", "a": "L0", "firma": "Ana Pérez", "motivo": "ventana nueva"}
  ]}
  ```

  Un PR revisado agrega la entrada; el arranque corre `cli.py nivel aplicar`, que aplica cada
  entrada una vez (su `id` queda como `ref` en el historial) y en orden. Un `subir` sin la evidencia
  cumplida no se aplica, y las siguientes esperan al próximo arranque. El agente no puede editar el
  archivo (freno `autonomia-firmada`).
- **Juzgar afuera.** Las propuestas y las alertas se juzgan donde la gente ya mira (el issue en el
  tablero, un botón en el chat). Un adaptador del repo lo registra con la referencia y la firma de
  quien juzgó; cuenta una vez por referencia:

  ```bash
  python3 .hermes/harness/scripts/cli.py recomendacion juzgar issue#54 aceptada --firma "ana"
  python3 .hermes/harness/scripts/cli.py hallazgo juzgar issue#60 falso --firma "ana"
  ```

  En el piloto, el adaptador es el espejo del tablero: una etiqueta `rec:aceptada` o
  `rec:rechazada` en el issue.

## Certificados: comprobar el porqué sin creerle

Desde L2 el agente hace cosas, y aprobar «reiniciar studio» o «volver al deploy anterior» es
aprobar una conclusión. Que el agente no se haya salido de su nivel no dice si la conclusión se
sigue de los hechos. Un **certificado** sí: al lado de la propuesta (`001-x.md` →
`001-x.cert.json`) el agente deja los hechos, las reglas y la deducción, y un **verificador que no
comparte código con el agente** la comprueba. Si alguien (el agente, un correo plantado, un humano)
edita la conclusión o una premisa, no verifica.

```json
"certificados": {
  "verificador": ["python3", "scripts/verificar_certificado.py", "{certificado}"],
  "extension": ".cert.json",
  "timeoutSegundos": 30
}
```

- **Quién lo corre.** La CLI, al juzgar: `recomendacion aceptar|rechazar` mira el certificado de
  al lado, `recomendacion juzgar … --certificado <archivo>` el que le pasa el adaptador, y
  `recomendacion verificar <propuesta>` sólo informa, para mirarlo antes de aprobar. Nunca un freno:
  los frenos no lanzan procesos. En L2, el mensaje de «pide aprobación» le dice al humano cómo
  verificarlo.
- **Qué queda.** El evento del juicio lleva `certificado`: `verificado`, `rechazado`, `ausente`
  o `error`. La métrica `certificadosVerificadosMin` es la proporción de propuestas juzgadas con
  certificado verificado; una sin certificado cuenta como no verificada.
- **Qué prueba y qué no.** Que la conclusión se deduce de las reglas dadas, no que las reglas sean
  ciertas. Esas reglas las escribe una persona y viven en el repo, revisadas como código.
- **Qué lógica.** La que el repo elija; el arnés sólo pide un comando que salga 0 si verifica, 3 si no pudo verificar (falta el verificador: `error`, como una señal omitida) y otro código si rechaza. El piloto
  doctiling-sre certifica la causa raíz de sus incidentes (L2) con `oo-horn`, el verificador en
  Lean 4 de [open-ontologies](https://github.com/fabio-rovai/open-ontologies): hechos del
  incidente, reglas de `causes` por regla de detección, y el veredicto
  `entailed_under_supplied_rules`. Su verificador es un envoltorio que separa el certificado en los
  tres archivos de `oo-horn/1` y corre `oo-horn check rules.tsv asserted.tsv horn.tsv` con el binario
  fijado por sha256.

Para pedirlo en el ascenso: `"L2->L3": {…, "certificadosVerificadosMin": 0.9}`. La plantilla no lo
trae: un repo sin verificador nunca llegaría a L3 (una métrica que no se puede medir no se da por
cumplida).

## Un agente de operaciones

Los niveles se describen para un agente que desarrolla. Para uno que opera (observa producción y
avisa), el mismo esqueleto se lee así, y los textos de `niveles` del config lo dicen con sus
palabras:

| Nivel | Agente que desarrolla | Agente que opera (piloto doctiling-sre) |
|---|---|---|
| L0 | lee y reporta | detecta, abre el incidente y avisa |
| L1 | propone en `.hermes/recomendaciones/` | agrega al incidente una propuesta del runbook |
| L2 | cambia con aprobación | ejecuta **esa** acción con aprobación y verifica que la regla vuelva a verde |
| L3 | trabaja solo en el loop | ejecuta sola las acciones reversibles del catálogo, con presupuesto |

Umbrales del piloto (más exigentes que la plantilla: observa producción):
`L0->L1` 30 sesiones limpias, 0 intentos, 14 días; `L1->L2` 20 recomendaciones, 90 % aceptadas,
30 días. El modelo y el esfuerzo por nivel los fija el repo en el config de Hermes (en el piloto,
Haiku en L0 y Sonnet en L1): el arnés no elige el modelo.

## Bajar: automático

`autonomia.descenso` declara qué baja **un** nivel sin firma:

- `tampering`: tocar intocables durante una tarea del loop.
- `reglasCriticas`: intentar algo que veda una de esas reglas (un `.env`, un `--no-verify`, una clave privada).
- `denegadasSeguidas`: N aprobaciones denegadas seguidas. El humano no está de acuerdo con lo que el agente propone.
- `escaladasSeguidas`: N tareas del loop escaladas seguidas.

El plugin lo revisa después de cada bloqueo y de cada denegación; el loop, al cerrar cada tarea. La
transición queda en el registro (`nivel-baja`) y el panel la muestra como alerta. Un humano también
puede bajar a mano:

```bash
python3 .hermes/harness/scripts/cli.py nivel bajar --a L1 --motivo "cambio de equipo" --firma "Ana Pérez"
```

## Declarar sin evidencia

Para un sandbox de aprendizaje, o para un repo donde el equipo decide asumir el riesgo:

```bash
python3 .hermes/harness/scripts/cli.py nivel declarar L3 --motivo "sandbox del workshop" --firma "Ana Pérez"
```

Queda en el historial como `declarado` y el panel lo muestra como **alerta** mientras dure. Es la
excepción a P28, no una forma de ganarlo. Este repo, que es el producto, se declara en L3 con
`autonomia.inicial`.

## Dónde se ve

Hay dos lugares:

- **Panel en vivo** (`cli.py panel`), sección **Salud del agente**:
  - la escalera L0–L3;
  - qué puede y qué no puede el agente;
  - una barra de evidencia por métrica contra el umbral del siguiente nivel;
  - si está listo para subir y el comando para firmarlo (el panel no escribe nada);
  - las transiciones con su firma o motivo;
  - las alertas.
- **`cli.py nivel`** y la línea `nivel` de `cli.py status`.

## Dónde vive

| Pieza | Archivo |
|---|---|
| Niveles, umbrales y disparadores | `autonomia` en `.hermes/harness.config.json` |
| Estado firmado (nivel e historial) | `.git/harness-autonomia.json`, en el gitdir común: lo ven los worktrees; en producción, `HARNESS_AUTONOMIA_FILE` |
| Transiciones firmadas por PR | `autonomia.firmadas` (por defecto `config/autonomia.json`) |
| Núcleo (evidencia, disparadores, transiciones) | `plugin/harness/autonomia.py` |
| Freno | `nivel_guard` en `plugin/harness/guards.py` |
| CLI | `cli.py nivel` (`aplicar` en producción), `cli.py recomendacion`, `cli.py hallazgo` |
| Pruebas | self-test §15 y mutaciones |
| Por qué está hecho así | [ADR 0012](decisions/0012-autonomia-por-evidencia.md) |

Para recorrerlo de punta a punta con un repo de juguete: [workshop de autonomía](workshop/autonomia/README.md).
