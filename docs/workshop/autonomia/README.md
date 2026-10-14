# Workshop — un agente desarrollador que se gana la autonomía

**Duración:** 2 h 30 min (7 módulos) · **Formato:** práctico, sobre un repo de juguete ·
**Para:** equipos que quieren un agente que desarrolle software y no saben cuánto dejarlo hacer solo.

## La idea

**La autonomía se gana con evidencia.** Un agente nuevo arranca como cualquier persona nueva en
un equipo: primero mira, después propone, después cambia con revisión, y recién al final trabaja
solo. Cada paso se gana con lo que hizo en el anterior, y un error serio lo hace retroceder.

Hermes Autopilot hace cumplir eso. No hace falta que el agente lo «sepa»:

| Nivel | Nombre | El agente puede |
|---|---|---|
| **L0** | Observador | leer y reportar |
| **L1** | Recomendar | correr los tests y dejar propuestas que vos juzgás |
| **L2** | Con aprobación | cambiar el código, con tu aprobación en cada escritura y cada commit |
| **L3** | Autonomía | trabajar solo, en el loop desatendido |

Los principios son P27 (cuatro niveles, se arranca en L0), P28 (subir lo firma un humano, bajar es
automático) y P29 (la salud del agente se ve). La referencia completa está en
[`../../autonomia.md`](../../autonomia.md).

## Lo que te llevás

- Un agente desarrollador que recorrió **L0 → L3** en un repo real, con la evidencia de cada paso
  en el registro.
- El panel con la sección **Salud del agente**: en qué nivel está, qué puede hacer, cuánta
  evidencia tiene contra el umbral del siguiente nivel y quién firmó cada ascenso.
- Un descenso automático visto en vivo, y el criterio para elegir los umbrales de **tu** equipo.

## Agenda

| Módulo | Tiempo | Qué se hace | Idea central |
|---|---|---|---|
| [0 · Instalar en L0](00-instalar-en-L0.md) | 20 min | el repo de juguete, el arnés, el panel | todo agente arranca observando |
| [1 · L0 Observador](01-L0-observador.md) | 20 min | el agente lee y reporta; el impaciente choca con el nivel | el nivel lo hace cumplir el plugin, no el prompt |
| [2 · L1 Recomendar](02-L1-recomendar.md) | 25 min | propuestas en `.hermes/recomendaciones/`, vos las juzgás | juzgar es evidencia |
| [3 · L2 Con aprobación](03-L2-con-aprobacion.md) | 30 min | cambios aprobados uno por uno, gates verdes | lo que decís que no también cuenta |
| *pausa* | 10 min | | |
| [4 · L3 Autonomía](04-L3-autonomia.md) | 20 min | el loop resuelve la cola de tareas solo | L3 no apaga los frenos: los suma al loop |
| [5 · Perder el nivel](05-perder-el-nivel.md) | 15 min | el agente hace trampa y baja solo | bajar no espera a nadie |
| [6 · Tu repo](06-tu-repo.md) | 10 min | umbrales propios, la lista de chequeo | los umbrales son decisión del equipo |

## Requisitos

- Python 3.11 o más nuevo, y `git`.
- Este repo clonado. En los módulos, `$AUTOPILOT` es su ruta.
- **Hermes Agent es opcional.** El agente de esta pista es de juguete y determinista
  ([`agente_dev.py`](agente_dev.py)). Igual pasa cada herramienta por el **plugin real** del
  sandbox, a través del despacho simulado de Hermes (`casos/hermes_sim.py`). El freno de nivel, los
  frenos del repo y el registro de eventos son los de verdad. Cada módulo dice cómo hacerlo con
  Hermes real, para quien lo tenga.

```bash
git clone https://github.com/raalzate/hermes-autopilot.git
export AUTOPILOT="$PWD/hermes-autopilot"
```

## Para quien lo dicta

- Cada ejercicio tiene **Ejercicio**, **Tiene que salir** y **Si no sale**. Si algo no sale como
  dice el texto, es un hallazgo: abrí un issue.
- Proyectá el panel desde el módulo 0. La sección **Salud del agente** es el hilo de la sesión:
  la escalera L0–L3 se va llenando y las barras de evidencia crecen con cada ejercicio.
- Hay dos momentos clave:
  - En el módulo 1, el agente impaciente intenta arreglar el bug y el nivel lo frena. Sin regla
    del repo y sin prompt: el freno es el nivel.
  - En el módulo 5, el agente hace trampa y **baja solo**, sin que nadie lo decida.
- Si el grupo ya hizo el [workshop general](../README.md), esta pista reemplaza la declaración de
  L3 del módulo 4 por el camino que se gana.
