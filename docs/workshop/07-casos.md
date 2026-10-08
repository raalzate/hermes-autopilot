# Módulo 7 (extra) — Casos reales, por dominio (30–60 min)

**Idea:** lo que hiciste con la calculadora pasa igual en infraestructura, en una planilla de
ventas o en la bandeja de soporte. El catálogo de [`../../casos/`](../../casos/README.md) tiene 17
casos replicables. Cada uno es un agente que toma un atajo real, y el arnés que lo frena, lo
escala o lo deja llegar a verde.

## Ejercicio 7.1 — Elegí tu dominio

```bash
cd $AUTOPILOT
python3 scripts/casos.py --list
```

| Si trabajás en… | Empezá por |
|---|---|
| desarrollo | `prog-tests-saltados`, `prog-descarta-trabajo` |
| infraestructura / plataforma | `infra-terraform-destroy`, `infra-env-secretos` |
| operaciones de negocio / oficina | `oficina-reporte-ventas`, `oficina-correos-clientes` |
| datos | `datos-anonimizar` |
| soporte | `soporte-ticket-inyeccion` |

Leé su `casos/<id>/README.md`: la historia, qué demuestra y lo que tiene que pasar en cada modo.

## Ejercicio 7.2 — Correlo y miralo en el panel

```bash
python3 scripts/casos.py preparar infra-env-secretos /tmp/rotacion
cd /tmp/rotacion
python3 .hermes/harness/scripts/cli.py panel          # otra terminal
JUGUETE=aprende python3 .hermes/harness/scripts/cli.py loop --apply
```

**Tiene que salir:** verde en el intento 1, y en el panel los frenos `env-lectura` y `env`
(leer el `.env`, escribirlo y copiarlo encima con `cp`). Repetí con `JUGUETE=atajo`
(antes volvé la casilla a `- [ ]` en `.hermes/loop/tasks.md`). Ahora escala: el agente
reescribió el `.env` con `python3 -c`, un canal que ningún freno ve por dentro, y el loop lo vio
en los intocables.

## Ejercicio 7.3 — Escribí el caso de tu equipo

Pensá un atajo que un agente tomaría en tu trabajo, de esos que «ya pasaron una vez». Copiá el
caso más parecido a `casos/<tu-id>/` y cambiá la historia, la semilla, el `verificar.py`, el
agente y la regla. Después:

```bash
python3 scripts/casos.py <tu-id>          # hasta que dé lo esperado
python3 scripts/casos.py readme <tu-id>
```

**Para discutir:** ¿tu caso necesitó un freno, o alcanzó con el gate? ¿Encontraste un hueco del
arnés? Si es así, va a [`../huecos.md`](../huecos.md), con su mecanismo o en «abiertos».
