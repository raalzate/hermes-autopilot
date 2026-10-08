# Módulo 6 — Aprender de los incidentes (20 min)

**Idea:** una escalada del loop o un freno que mordió de más son incidentes. Un incidente que
termina en un post-it se repite. Uno que termina en un mecanismo, no. Siempre el más fuerte
disponible: test > freno o lint > skill > markdown (P15).

## Ejercicio 6.1 — Diagnosticar la escalada del módulo 4

La tarea `[!]` del agente terco escaló con la firma `tests (unittest)` dos veces seguidas.

1. Corré `ap gate` y leé la primera señal roja: `AssertionError: -1 != 5`.
2. **Hipótesis:** el agente devuelve `a - b`.
3. **¿Qué mecanismo falta?** Ninguno. El más fuerte ya existe, es el test, y cazó el bug las dos
   veces. Y el loop hizo lo suyo: paró en vez de quemar dos intentos más. La acción no va en el
   arnés, va en el agente o en la tarea (más chica, con el criterio explícito).

No todo incidente pide una regla nueva. Una regla sin cicatriz detrás es ruido que gasta el
contexto del agente (P17).

## Ejercicio 6.2 — Un incidente que sí pide un freno

Un incidente típico, para practicar: el agente deja un `breakpoint()` en `app/calc.py` mientras
depura. En una terminal, el gate se cuelga esperando a `pdb`. En el loop, que corre todo con stdin
cerrado, `pdb` recibe EOF y revienta con `BdbQuit`: el gate da un rojo que no dice nada del bug
real, y el agente gasta el intento siguiente persiguiendo eso.

El test no lo puede evitar (el test es lo que se rompe). Un freno sí, antes de que se escriba:

```bash
ap rule add patterns --id breakpoint-olvidado \
  --pattern '^\s*(breakpoint\(\)|import\s+pdb|pdb\.set_trace\(\))' \
  --path '^app/' --example-path app/calc.py \
  --example 'breakpoint()' --more 'import pdb' \
  --reason "un breakpoint en el código cuelga el gate en una terminal y lo rompe con BdbQuit en el loop. Sacalo antes de terminar." \
  --apply
ap selftest
```

**Tiene que salir:** `✓ el ejemplo frena, ningún inocente muerde y el config pasa el lint.` y el
self-test verde. Desde ahora pasan dos cosas. El `write_file` de Hermes que meta un breakpoint en
`app/` se frena **antes** de escribirse. Y el pre-commit frena el que entre por otro lado. El lazo
se acortó: el error se corrige en la herramienta, no un intento después.

Probá una variante multilínea, por ejemplo un patrón con `\n` entre el `def` y el `return`. La
CLI la rechaza: `patterns` se evalúa línea por línea en el lint y en los patch V4A de Hermes, así
que un patrón multilínea frenaría un `write_file` y nunca un commit.

## Ejercicio 6.3 — El formato del incidente

Agregá el incidente a `docs/gotchas.md` con el formato fijo que exige el lint:

```markdown
### GOTCHA — breakpoint() rompió el gate del loop

- **Síntoma:** el gate del loop salió rojo con `BdbQuit`, sin relación con la tarea.
- **Causa:** el agente dejó `breakpoint()` en `app/calc.py`; pdb no tenía terminal.
- **Regla:** `patterns[breakpoint-olvidado]`.
- **Mecanismo:** freno en `pre_tool_call`, pre-commit y el self-test con el `example` de la regla.
```

Después corré `ap lint`. Si sacás la línea **Mecanismo**, el lint lo marca: un incidente sin
mecanismo es una anécdota. Con Hermes, la skill `/lesson` hace este ciclo entero.

## Cierre — la lista de chequeo (5 min)

Tu agente es autónomo **y** confiable si podés contestar que sí a todo:

- [ ] «Terminado» es un comando (el gate), y el loop lo usa como salida.
- [ ] Cada freno tiene `example`, y el self-test prueba que muerde y que no muerde de más.
- [ ] El mismo error dos veces para el loop y te avisa.
- [ ] Hay tope de intentos y de tiempo por tarea.
- [ ] Podés pararlo sin romper nada (`--stop`).
- [ ] Lo ves trabajar sin leer su conversación (el panel).
- [ ] No publica sin vos.
- [ ] Cada incidente terminó en el mecanismo más fuerte disponible, no en una advertencia.

Para seguir: el [módulo 7](07-casos.md) lleva todo esto a casos reales de infraestructura,
oficina, datos y soporte; [`../huecos.md`](../huecos.md) tiene los huecos que el arnés todavía no
cierra, y [`../portar.md`](../portar.md) cómo llevarlo a tu repo real.
