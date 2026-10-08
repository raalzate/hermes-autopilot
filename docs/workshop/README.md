# Workshop — agentes autónomos con Hermes, gobernados por un arnés

**Duración:** 3 h 30 min (6 módulos y un cierre) · **Formato:** práctico, en un repo sandbox
propio · **Para:** quien quiere dejar a un agente trabajando solo y poder confiar en lo que entrega.

## Lo que te llevás

Al final tenés un repo con un agente que toma tareas de una cola, las trabaja, verifica con un
gate, reintenta con el error en la mano, escala cuando se traba y nunca publica sin vos. Y un
panel donde ves todo eso pasar en vivo.

Más importante: entendés **por qué** cada pieza está ahí. Un agente autónomo no es un modelo
bueno: es un modelo metido en lazos de control bien hechos
([`../ingenieria-de-loops.md`](../ingenieria-de-loops.md)).

## Agenda

| Módulo | Tiempo | Qué se hace | Idea central |
|---|---|---|---|
| [0 · Preparación](00-preparacion.md) | 20 min | instalar el arnés en un sandbox, gate y panel | el entregable es un comando, no una opinión |
| [1 · Guías](01-guias.md) | 25 min | `AGENTS.md`, rutas, el escáner de contexto de Hermes | decirle al agente qué hacer antes de que decida |
| [2 · Frenos](02-frenos.md) | 35 min | reglas con `cli.py rule add`, verlas morder en el panel | todo freno prueba que muerde y que no muerde de más |
| [3 · Sensores y gate](03-sensores-y-gate.md) | 30 min | señales con `why`, mutaciones, el mapa | un sensor que no se prueba es una esperanza |
| *pausa* | 10 min | | |
| [4 · El loop autónomo](04-loop-autonomo.md) | 40 min | cola de tareas, agente de juguete, verde, escalada | la salida es el gate; el mismo error dos veces es un bucle |
| [5 · Operar](05-operar.md) | 25 min | panel en vivo, freno de mano, leer una escalada, Hermes real | lo que pasa adentro se ve afuera |
| [6 · Aprender de los incidentes](06-aprender.md) | 20 min | de una escalada a una regla nueva, con la skill `lesson` | cada incidente deja infraestructura |
| Cierre | 5 min | la lista de chequeo | |
| [7 · Casos reales](07-casos.md) *(extra)* | 30–60 min | infra, oficina, datos, soporte: correr un caso y escribir el de tu equipo | lo que pasa con la calculadora pasa en todos lados |

## Requisitos

- Python 3.11 o más nuevo, y `git`.
- Este repo clonado. En los módulos, `$AUTOPILOT` es su ruta.
- **Hermes Agent es opcional.** Los módulos 0 a 4 usan un *agente de juguete* determinista
  ([`sandbox/agente_juguete.py`](sandbox/agente_juguete.py)), así la mecánica se aprende sin API
  key y sin depender de qué conteste un modelo ese día. El módulo 5 cambia el juguete por Hermes,
  para quien lo tenga.

```bash
git clone https://github.com/raalzate/hermes-autopilot.git
export AUTOPILOT="$PWD/hermes-autopilot"
```

## Para quien lo dicta

- Cada módulo tiene **Ejercicio**, **Tiene que salir** y **Si no sale**. Si a alguien no le sale
  lo que dice «Tiene que salir», eso es un hallazgo del workshop: anotalo y abrí un issue.
- Dejá el panel proyectado desde el módulo 0. Es el hilo de toda la sesión.
- El momento clave es la escalada del módulo 4. Dejá que el grupo vea al agente terco fallar dos
  veces igual y al loop **parar solo**. Ahí se entiende la diferencia entre autonomía y un
  `while true`.
