# 0012 — La autonomía se gana con evidencia: niveles L0–L3

**Estado:** aceptada · **Fecha:** 2026-10-14

## Contexto

Hasta acá el arnés tenía dos modos implícitos. En una sesión, los frenos muerden en cada tool call.
Desatendido, el loop corre si alguien lo lanza. Entre «el agente puede todo lo que los frenos no
vedan» y «el agente no existe» no había nada. Un equipo que instala Hermes Autopilot para que un
agente desarrolle software tenía que confiar de entrada, o no usarlo.

La confianza en una persona nueva no funciona así: primero mira, después propone, después cambia
con revisión, y recién al final trabaja sola. Cada paso se gana con lo que hizo en el anterior, y
un error serio la hace retroceder. El pedido del dueño fue exactamente eso, como principio: la
autonomía se gana con evidencia.

## Decisión

1. **Cuatro niveles, declarados en el config** (`autonomia.niveles`, P4):

   | Nivel | Nombre | Qué puede hacer |
   |---|---|---|
   | L0 | Observador | leer y correr comandos de sólo lectura |
   | L1 | Recomendar | además corre el gate y los tests, y escribe propuestas en `.hermes/recomendaciones/` |
   | L2 | Con aprobación | cada escritura, comando mutante o código ejecutado pide aprobación humana |
   | L3 | Autonomía | trabaja solo, también desatendido en el loop |

   Para cada familia de herramienta, el nivel declara `allow`, `ask` o `deny`. Las excepciones van
   aparte:
   - `escribirPermitido`: rutas que se pueden escribir aunque la familia no deje.
   - `terminalPermitida`: cada subcomando tiene que casar con un patrón, sin `$(…)` ni
     redirecciones.

   Cada nivel trae `ejemplos`, y el self-test los pasa por el plugin (P2).
2. **El nivel lo hace cumplir el plugin, primero.** `nivel_guard` corre antes que los otros frenos.
   - Si bloquea, gana.
   - Si sólo pide aprobación, los frenos del repo corren igual y un bloqueo de ellos le gana:
     aprobar un cambio en L2 no aprueba un `--no-verify`.
   - El loop no arranca en un nivel sin `loop: true`.
3. **La evidencia es el registro de eventos.** Se cuenta desde la última transición:
   - **sesiones limpias**: un evento `turno` por sesión, menos las que se salieron del nivel;
   - **recomendaciones juzgadas** (`recomendacion`);
   - **aprobaciones**: `aprobacion`, que ahora registra el plugin en `post_tool_call` para *toda*
     escalada, no sólo las que tienen presupuesto;
   - **gates** y **tamperings**.

   Una métrica que el arnés no sabe medir no se da por cumplida.
4. **Subir lo firma un humano; bajar es automático.**
   - `cli.py nivel subir --firma` sube un nivel si la evidencia alcanza; si no, se niega y muestra
     qué falta.
   - `autonomia.revisar` baja un nivel ante un disparador de `autonomia.descenso`. Corre en el
     plugin, después de un bloqueo o una denegación, y en el loop, al cerrar cada tarea.
   - El agente no puede firmar: la regla `nivel-firma` de `terminal.ask` lo escala al humano, y el
     estado vive bajo `.git/`, que ya es ruta protegida.
5. **Declarar sin evidencia existe y se ve.** Este repo (el producto) se declara en L3 con
   `autonomia.inicial`, y los sandboxes de los casos con `cli.py nivel declarar`. El panel lo
   muestra como alerta mientras dure.

## Consecuencias

- **El estado vive en el gitdir común** (`.git/harness-autonomia.json`), no versionado.
  - Los worktrees del loop ven el mismo nivel.
  - Una firma no depende de que alguien haga commit.
  - El historial queda en el estado y en el registro de eventos, no en git. Si hace falta auditarlo
    en el repo, el siguiente paso es exportarlo.
- **Un estado ilegible vale L0.** Es la única excepción a P5 («un arnés roto deja pasar»). Un freno
  roto deja pasar, porque bloquear todo por un bug desinstala el arnés. Un *estado* roto, en
  cambio, no puede ser la forma de regalarle L3 a un agente.
- **Los repos ya instalados no cambian de comportamiento.** `install.py --upgrade` no toca el config
  y, sin la clave `autonomia`, el freno no actúa. Graduar la autonomía es una decisión del repo:
  basta copiar la clave desde la plantilla.
- **Los otros frenos se prueban sin el nivel encima.** El self-test usa `HARNESS_NIVEL_PRUEBA` para
  eso; `cli.py rule add` e `integ.py add` prueban con un config sin `autonomia`. La regla
  `nivel-prueba` de `terminal.deny` veda esa variable en cualquier comando.
- **En los casos replicables el descenso está apagado.** Un caso mide si el freno alcanza: el
  agente choca y se adapta. Que el agente merezca su nivel se prueba en el self-test (§15) y en el
  workshop de autonomía.
- **La ventana de evidencia es la del registro**, que rota en `observability.events.maxBytes`. Un
  equipo que quiera umbrales grandes tiene que darle más espacio al registro.
