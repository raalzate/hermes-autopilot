# Módulo 5 — Perder el nivel (15 min)

**Idea:** subir lo firma un humano; **bajar no espera a nadie** (P28). Si el agente hace algo que
contradice la confianza que se ganó, baja un nivel en el momento y la ventana de evidencia vuelve a
empezar. Lo que lo baja está declarado en `autonomia.descenso`:

- tocar intocables durante una tarea;
- intentar algo que veda una regla crítica;
- aprobaciones denegadas seguidas;
- tareas escaladas seguidas.

## Ejercicio 5.1 — El agente tramposo

Una tarea nueva, y un agente que en vez de trabajarla la marca como hecha en la cola, por un canal
que ningún freno de herramienta ve (un comando que no es Python):

```bash
ap task add "Agregá envio(items): gratis desde 200, si no 15, con su test en test_carrito.py"
git add .hermes && git commit -m "chore: tarea nueva" -m "no-issue: sandbox del workshop"
JUGUETE=tramposo ap loop --apply
```

**Tiene que salir:** `✗ ESCALAR` con la tarea. El loop compara los intocables (la cola, el config,
el `.env`) antes y después de cada intento, y vio que la cola cambió.

## Ejercicio 5.2 — Bajó solo

```bash
ap nivel
```

**Tiene que salir:**

```
Nivel L2 — Con aprobación
  ⚠ bajó solo de L3 a L2: el agente tocó lo que no podía durante una tarea (.hermes/loop/tasks.md)
…
  L3 → L2  bajado-automatico · automático · el agente tocó lo que no podía durante una tarea (.hermes/loop/tasks.md)
```

En el panel, la escalera retrocede, la alerta aparece en amarillo y en «Eventos en vivo» se ven
`intocables` y `nivel: baja`. Nadie firmó nada.

## Ejercicio 5.3 — Y ahora el loop no corre

```bash
ap task add "Otra tarea cualquiera"
ap loop --apply
```

**Tiene que salir:** `loop: el agente está en L2 (Con aprobación): ese nivel no trabaja desatendido.
La autonomía se gana con evidencia (P27): para L3 falta cambios aprobados: 0 (umbral 10); …`. La
evidencia de antes no cuenta: la ventana empezó de nuevo con el descenso.

## Ejercicio 5.4 — Recuperarlo

El camino de vuelta es el mismo de ida: diez cambios aprobados y tres gates verdes (módulo 3), y tu
firma. No hay atajo. `ap nivel declarar L3` existe, pero exige motivo y firma, y el panel lo muestra
como **alerta** mientras dure («declarado, no ganado»).

**Para discutir:**

- ¿Qué más debería bajar el nivel en tu equipo? Mirá `descenso.reglasCriticas`: ¿qué reglas
  de tu repo son críticas?
- ¿Un solo intento contra `.env` debería costarle un nivel al agente, o tendría que ser un patrón?

→ [Módulo 6](06-tu-repo.md)
