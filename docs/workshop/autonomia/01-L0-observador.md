# Módulo 1 — L0 Observador (20 min)

**Idea:** en L0 el agente lee, corre comandos de sólo lectura y reporta. No escribe nada. Eso no
depende de que el agente «entienda» su nivel: lo hace cumplir el plugin en cada tool call, antes que
cualquier otro freno.

## Ejercicio 1.1 — El agente observa

```bash
python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py observar
```

**Tiene que salir:**

```
  [terminal] ✓ git log --oneline -5
  [terminal] ✓ grep -n 'def ' tienda/carrito.py

REPORTE DEL AGENTE
  · total() resta el descuento como un monto, y la docstring dice que es un porcentaje.
    test_total_con_descuento_en_porcentaje espera 225 y daría 240.
```

En el panel, la barra de **sesiones sin salirse del nivel** pasa a 1.

## Ejercicio 1.2 — El agente impaciente

Encontró el bug. Un agente apurado lo arregla de una vez:

```bash
python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py impaciente
```

**Tiene que salir:**

```
  [write_file] ✗ FRENADO
    NIVEL L0 (Observador): escribir `tienda/carrito.py` no está permitido en este nivel.
    Lo que sí podés hacer: leer el repo, correr comandos de sólo lectura (…) y reportar en la respuesta.
    La autonomía se gana con evidencia: lo que falta para L1 lo muestra `… cli.py nivel`. …
```

Ninguna regla del repo prohíbe escribir `tienda/carrito.py`: lo frenó el **nivel**. El mensaje es
lo único que el agente lee, y le dice qué sí puede hacer y dónde ver lo que le falta.

Fijate en el panel: esta sesión **no** sumó a la barra. Una sesión que intentó salirse del nivel no
es una sesión limpia.

## Ejercicio 1.3 — Lo que parece lectura y no lo es

Probá el freno directo, sin el agente:

```bash
ap rule test terminal.deny "git status && rm -r tienda"
```

**Tiene que salir:** `pasa — ninguna regla lo frena`. `rule test` prueba las reglas del repo, no el
nivel, y ninguna regla de `terminal.deny` caza ese comando. Pero en L0 el agente igual no lo puede
correr. Mirá el patrón de L0 en el config (`autonomia.niveles.L0.terminalPermitida`).

- **Cada subcomando** tiene que casar con un patrón de lectura: `git status && rm -r tienda` no
  pasa por empezar con `git status`.
- Una sustitución (`$(…)`) o una redirección (`> archivo`) nunca pasa como lectura.

El self-test lo prueba con los `ejemplos` de cada nivel (sección 15).

## Ejercicio 1.4 — La primera firma

Intentá subir antes de tiempo:

```bash
ap nivel subir --firma "Vos"
```

**Tiene que salir:** `✗ la evidencia no alcanza para pasar de L0 a L1`, con la fila que falta.
Observá dos veces más y volvé a intentar:

```bash
python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py observar
python3 $AUTOPILOT/docs/workshop/autonomia/agente_dev.py observar
ap nivel
ap nivel subir --firma "Vos"
```

**Tiene que salir:** `✓ sesiones sin salirse del nivel 3 (al menos 3)`, *«Lista para subir»* y,
después de firmar, `✓ L0 → L1, firmado por Vos.`. En el panel, la escalera avanza y aparece la
transición con tu firma.

**Si no sale:** si `subir` sigue diciendo que no alcanza, contá las sesiones del impaciente. Una
sesión con un intento fuera del nivel no cuenta.

**Con Hermes real:** con el plugin habilitado (`hermes plugins enable repo-harness`), pedile a
Hermes que arregle el bug. Va a chocar con el mismo mensaje.

→ [Módulo 2](02-L1-recomendar.md)
