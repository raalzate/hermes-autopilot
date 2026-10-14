# Módulo 3 — L2 Con aprobación (30 min)

**Idea:** en L2 el agente cambia el código, pero cada escritura, cada commit y cada código que
ejecuta pasa antes por vos. Lo que decidís queda en el registro como evidencia, **también cuando
decís que no**. Y un freno del repo le gana a tu aprobación: aprobar un cambio no aprueba un
`--no-verify`.

## Ejercicio 3.1 — Decir que no

```bash
JUGUETE_APRUEBA=no python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py arreglar
```

**Tiene que salir:**

```
Cambio: fix: el descuento de total() es un porcentaje
  [write_file] ✗ pide aprobación humana y el humano dijo que no: NEGADA
    NIVEL L2 (Con aprobación): escribir `tienda/carrito.py` pide aprobación humana. …
  no me dejaron escribir: no sigo con este cambio.
```

En el panel, en «Eventos en vivo», aparece una `aprobación` **denegada**. En «Salud del agente», la
barra de *aprobaciones denegadas* se pone en 100 %.

## Ejercicio 3.2 — Decir que sí, mirando

Ahora sin `JUGUETE_APRUEBA`: el agente te pregunta a vos.

```bash
python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py arreglar
```

**Tiene que salir:** dos preguntas, `⚠ PIDE APROBACIÓN: [write_file] …` y `⚠ PIDE APROBACIÓN:
[terminal] … git commit -am …`. Contestá `s` a las dos. En el medio, `python3 -m unittest -q` corre
**sin** preguntar: verificar está permitido desde L1. Al final, `git log --oneline` muestra el commit
del agente y `python3 -m unittest -q` da `OK`.

## Ejercicio 3.3 — Los cambios que faltan

El agente tiene cuatro cambios más: un test, una docstring, una validación y una sección del
README. Para no contestar ocho preguntas, aprobalos en bloque:

```bash
for i in 1 2 3 4; do JUGUETE_APRUEBA=si python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py arreglar; done
```

`JUGUETE_APRUEBA=si` es un atajo del workshop. Con Hermes real no existe: aprueba un humano mirando
cada pedido.

## Ejercicio 3.4 — El gate también es evidencia

```bash
ap gate
ap gate
ap gate
ap nivel
```

**Tiene que salir:**

```
Evidencia para L3 (desde la última transición):
    ✓ cambios aprobados                      10  (al menos 10)
    ✓ aprobaciones denegadas                 9%  (como mucho 10%)
    ✓ gates corridos                          3  (al menos 3)
    ✓ gates verdes                          100%  (al menos 90%)
    ✓ intocables tocados                      0  (como mucho 0)
```

**Si no sale:**

- *Gates verdes* bajo el 90 %: un gate rojo cuenta, aunque después lo hayas arreglado. Corré más
  gates verdes hasta que la proporción alcance.
- *Aprobaciones denegadas* sobre el 10 %: hace falta más trabajo aprobado que compense. La
  evidencia no se borra: se acumula.

## Ejercicio 3.5 — Subir a L3

```bash
ap nivel subir --firma "Vos"
```

**Tiene que salir:** `✓ L2 → L3, firmado por Vos.`. En el panel, la escalera llega a L3 y la sección
dice *«Nivel más alto: la evidencia ahora es para no bajar»*.

**Con Hermes real:** en L2, Hermes muestra su diálogo de aprobación en cada escritura. En cron o en
el gateway no hay a quién preguntarle, así que la aprobación se niega sola. Por eso L2 no corre
desatendido.

**Para discutir:** tres denegaciones seguidas bajan el nivel (`descenso.denegadasSeguidas`). ¿Es
justo? ¿Qué dice de un agente que proponés corregir tres veces seguidas?

→ [Módulo 4](04-L3-autonomia.md)
