# Módulo 2 — L1 Recomendar (25 min)

**Idea:** en L1 el agente ya puede **verificar**: corre el gate y los tests. También puede
**proponer**, escribiendo propuestas en `.hermes/recomendaciones/`. Sigue sin tocar el código. Lo
que lo hace subir no es cuánto propone, sino cuánto de lo que propone aceptás vos.

## Ejercicio 2.1 — La primera propuesta

```bash
python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py recomendar
```

**Tiene que salir:**

```
  [terminal] ✓ python3 -m unittest -q
  tests: ROJOS
  [write_file] ✓ .hermes/recomendaciones/001-total-descuento-porcentaje.md
```

En L0 correr los tests estaba vedado; en L1 no. Y escribir sólo vale dentro de
`.hermes/recomendaciones/`. Comprobalo con el impaciente:

```bash
python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py impaciente
```

**Tiene que salir:** `NIVEL L1 (Recomendar): escribir tienda/carrito.py no está permitido en este nivel.`

## Ejercicio 2.2 — Juzgar es evidencia

Pedile cuatro propuestas más y leelas:

```bash
for i in 2 3 4 5; do python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py recomendar; done
ap recomendacion list
```

Juzgalas. Las buenas se aceptan y las que no te convencen se rechazan. La quinta (una sección del
README) rechazala aunque te guste, así vemos cómo cuenta un rechazo:

```bash
ap recomendacion aceptar .hermes/recomendaciones/001-total-descuento-porcentaje.md --firma "Vos"
ap recomendacion aceptar .hermes/recomendaciones/002-test-carrito-vacio.md --firma "Vos"
ap recomendacion aceptar .hermes/recomendaciones/003-docstring-subtotal.md --firma "Vos"
ap recomendacion aceptar .hermes/recomendaciones/004-descuento-fuera-de-rango.md --firma "Vos"
ap recomendacion rechazar .hermes/recomendaciones/005-readme-como-se-trabaja.md --firma "Vos"
```

Probá juzgar dos veces la misma: **Tiene que salir** `ya fue juzgada: una recomendación cuenta una vez.`

## Ejercicio 2.3 — El agente no se juzga a sí mismo

Mirá la regla `nivel-firma` en `terminal.ask` del config. Si el **agente** corre `cli.py
recomendacion aceptar` o `cli.py nivel subir`, el arnés le pide aprobación al humano. Desatendido,
sin humano, se niega:

```bash
ap rule test terminal.ask "python3 .hermes/harness/scripts/cli.py nivel subir --firma Agente"
```

**Tiene que salir:** `ESCALA A UN HUMANO — regla nivel-firma`, con su motivo: *«subir de nivel o
juzgar una recomendación es evidencia que firma un humano: el agente no se la da a sí mismo»*.

## Ejercicio 2.4 — Subir a L2

```bash
ap nivel
ap nivel subir --firma "Vos"
```

**Tiene que salir:**

```
Evidencia para L2 (desde la última transición):
    ✓ recomendaciones juzgadas                5  (al menos 5)
    ✓ recomendaciones aceptadas             80%  (al menos 80%)
    ✓ sesiones sin salirse del nivel          5  (al menos 3)
```

Y después `✓ L1 → L2, firmado por Vos.`.

**Si no sale:** con dos rechazos, la proporción baja a 60 % y no alcanza. Es a propósito: un agente
cuyas propuestas rechazás no está listo para cambiar el código. Pedile otra propuesta…
o no subas.

**Para discutir:** ¿80 % es mucho o poco para tu equipo? ¿Cuántas propuestas hacen falta para
confiar en el criterio de alguien nuevo?

→ [Módulo 3](03-L2-con-aprobacion.md)
