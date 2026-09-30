---
name: gate
description: Corre el gate del repo (la única definición de entregable) e interpreta el resultado. Usala antes de decir que algo está listo, cuando el arnés avisa GATE PENDIENTE, o cuando el humano pregunta si esto anda.
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [harness, quality, gate]
    category: harness
---

# /gate

1. Leé el comando en `.hermes/harness.config.json` → `gate.command` (no lo adivines: cambia
   entre repos). Corrélo con `terminal`.
2. Leé el **veredicto de la última línea**:
   - `GATE VERDE` → entregable. Si dice `con N OMITIDA(S)`, nombralas en tu respuesta: omitido
     no es verde, y el humano tiene que saber qué no se verificó.
   - `GATE ROJO` → buscá la **primera** señal con `✗` y leé su salida real (archivo, línea,
     mensaje). Las siguientes suelen ser consecuencia de la primera.
   - `gate:fast verde` → señal de desarrollo, **no** entregable.
3. Arreglá la causa, no el síntoma. Si la señal roja es un freno que está mal, el arreglo es el
   freno (skill `new-guardrail`), nunca saltearlo.
4. Presupuesto: 2 intentos sobre el mismo error, cada uno con una hipótesis nueva. Al tercero,
   pará y reportá el diagnóstico: qué señal, qué error, qué probaste.

## Qué no hacer

- Reportar "listo" con el gate rojo o sin correrlo. El plugin no te deja cerrar el turno con
  código editado y el gate pendiente; si el trabajo no es entregable, decilo con esas palabras.
- Correr sólo la señal que falló y dar por bueno el resto: el entregable es el gate completo.
