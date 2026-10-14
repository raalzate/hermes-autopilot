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
| `sesionesLimpias` | sesiones en las que el agente no intentó salirse de su nivel | `turno` (una vez por sesión), menos las sesiones con un `block` de una regla `nivel-*` |
| `intentosFueraDeNivel` | bloqueos del freno de nivel | `block` con regla `nivel-*` |
| `recomendaciones`, `aceptadasMin` | propuestas de L1 juzgadas, y la proporción aceptada | `recomendacion` |
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
| Estado firmado (nivel e historial) | `.git/harness-autonomia.json`, en el gitdir común: lo ven los worktrees |
| Núcleo (evidencia, disparadores, transiciones) | `plugin/harness/autonomia.py` |
| Freno | `nivel_guard` en `plugin/harness/guards.py` |
| CLI | `cli.py nivel`, `cli.py recomendacion` |
| Pruebas | self-test §15 y mutaciones |
| Por qué está hecho así | [ADR 0012](decisions/0012-autonomia-por-evidencia.md) |

Para recorrerlo de punta a punta con un repo de juguete: [workshop de autonomía](workshop/autonomia/README.md).
