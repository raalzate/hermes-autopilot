# Módulo 6 — Tu repo (10 min)

**Idea:** los niveles son del arnés, pero **los umbrales son de tu equipo**. Cuánta evidencia hace
falta para confiar en alguien nuevo depende de qué se rompe si se equivoca.

## Ejercicio 6.1 — Instalarlo en tu repo

```bash
python3 $AUTOPILOT/scripts/install.py <tu-repo> --profile <tu-stack>          # DRY-RUN
python3 $AUTOPILOT/scripts/install.py <tu-repo> --profile <tu-stack> --apply
```

El agente arranca en L0. Si tu repo ya tenía el arnés instalado (`--upgrade`), el config no se toca
y el freno de nivel no actúa hasta que copies la clave `autonomia` desde
`$AUTOPILOT/plantillas/harness.config.json`. Graduar la autonomía es una decisión del repo.

## Ejercicio 6.2 — Elegir los umbrales

Discutilo con tu equipo y editá `autonomia.ascenso` en `.hermes/harness.config.json`:

| Pregunta | Clave |
|---|---|
| ¿Cuántas sesiones mirando sin salirse del nivel? | `L0->L1.sesionesLimpias` |
| ¿Cuántas propuestas juzgadas, y qué proporción aceptada? | `L1->L2.recomendaciones`, `aceptadasMin` |
| ¿Cuántos cambios aprobados antes de trabajar solo? | `L2->L3.cambiosAprobados` |
| ¿Cuánto rechazo se tolera? | `L2->L3.denegadosMax` |
| ¿Cuántos días mínimos en un nivel? | `diasMin`, en cualquier paso |

Y en `autonomia.descenso`: qué reglas de tu repo son **críticas** (`reglasCriticas`), y cuántas
denegaciones o escaladas seguidas bajan el nivel.

Una métrica mal escrita no se da por cumplida: si un umbral nombra algo que el arnés no sabe medir,
nadie sube. Después de editar:

```bash
ap selftest
ap nivel
```

## Cierre — la lista de chequeo

- [ ] El agente arrancó en L0, y en el panel se ve en qué nivel está.
- [ ] Cada ascenso tiene una firma y la evidencia que lo justificó (`ap nivel`, «Transiciones»).
- [ ] El agente no puede firmarse ni juzgar sus propias recomendaciones (`nivel-firma` en `terminal.ask`).
- [ ] El loop desatendido sólo corre en L3.
- [ ] Sabés qué baja el nivel en tu repo, y lo viste bajar al menos una vez.
- [ ] Si algún nivel está **declarado** y no ganado, el equipo sabe por qué y hasta cuándo.

Lo que no cubre esta pista está en el [workshop general](../README.md): las reglas del repo
(módulo 2), los sensores (módulo 3), operar el loop (módulo 5) y aprender de los incidentes
(módulo 6).
