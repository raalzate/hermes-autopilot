# Módulo 4 — L3 Autonomía (20 min)

**Idea:** en L3 el agente trabaja solo, también desatendido. L3 no apaga nada: los frenos del repo
siguen mordiendo en cada tool call, y lo que decide si una tarea terminó sigue siendo el gate, no el
agente. La diferencia es que nadie aprueba cada paso: el loop toma la tarea, la trabaja, la
verifica y sigue.

## Ejercicio 4.1 — El loop con el agente de juguete

```bash
ap config set loop.agentCommand "[\"python3\", \"$AUTOPILOT/docs/workshop/autonomia/agente_dev.py\", \"loop\", \"{prompt}\"]" --apply
ap config set branches.protected '["main"]' --apply
git add .hermes && git commit -m "chore: el loop con el agente de juguete" -m "no-issue: sandbox del workshop"
cat .hermes/loop/tasks.md
ap loop
```

**Tiene que salir:** el `DRY-RUN del loop` con la primera tarea (`iva(items, tasa=0.19)`), la rama
que abriría y el comando del agente. Nada se ejecutó (P9).

## Ejercicio 4.2 — La cola, sola

Mirá el panel y corré:

```bash
ap loop --apply --all
```

**Tiene que salir:**

```
✓ VERDE    Agregá iva(items, tasa=0.19) en tienda/carrito.py: …
✓ VERDE    Agregá cupon(items, codigo) en tienda/carrito.py: …
```

Las dos tareas quedan `- [x]` en la cola. Cada una trabajó en su worktree y su rama `loop/…`: el loop
no empuja ni abre PR (P13). Revisar lo verde y publicarlo sigue siendo tuyo.

**Si no sale:** si el loop dice `el agente está en L2 … ese nivel no trabaja desatendido`, no
firmaste el ascenso del módulo 3 (`ap nivel`). Si escala con `harness self-test` en rojo, corré
`ap gate` y mirá qué señal falla.

## Ejercicio 4.3 — Leé la salud

En el panel, la sección **Salud del agente** muestra:

- la escalera completa, con L3 resaltado;
- tres transiciones `ganado`, cada una con tu firma;
- ninguna alerta.

En `cli.py status` aparece la línea `nivel L3 (Autonomía)`.

**Para discutir:** el repo del propio Hermes Autopilot está en L3 **declarado**, no ganado: se
trabajaba así antes de que existieran los niveles. Mirá su panel: la alerta lo dice. ¿Cuándo se
justifica declarar un nivel en vez de ganarlo? ¿Quién debería poder hacerlo?

→ [Módulo 5](05-perder-el-nivel.md)
