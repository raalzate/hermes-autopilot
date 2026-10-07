# Módulo 1 — Guías (25 min)

**Idea:** una *guía* actúa **antes** de que el agente decida: le dice qué se hace en este repo.
Es lo más barato que existe y también lo más frágil, porque el agente puede no leerla, leerla
truncada o, en Hermes, perderla entera.

## Las tres guías del arnés

| Guía | Cuándo actúa | Dónde |
|---|---|---|
| `AGENTS.md` | al abrir cada sesión (Hermes lo inyecta como contexto) | la raíz del repo |
| la sección de estado | al abrir cada sesión: rama, hooks, gate pendiente, encabezado de `STATUS.md` | el plugin |
| `routes` | en cada pedido que casa con un patrón: suma una pista al turno | el config |

## Ejercicio 1.1 — Escribí el `AGENTS.md` de tu sandbox

Abrilo y completá «Qué es este repo» con una frase: *«Una calculadora de juguete para el
workshop. El código vive en `app/`.»*

Después corré el lint:

```bash
ap lint
```

**Tiene que salir:** `lint: verde.`

## Ejercicio 1.2 — Por qué Hermes puede descartar tu `AGENTS.md` entero

Hermes escanea los archivos de contexto buscando inyección de prompts. Si una línea parece un
ataque, reemplaza **el archivo entero** por `[BLOCKED]` y el agente trabaja sin tus reglas, sin
avisarte. La regla `CONTEXTO` del lint caza esas líneas antes que Hermes.

Agregá al final de tu `AGENTS.md` una línea con un comentario HTML que diga `system`, por
ejemplo uno que avise que la sección «la regenera el system». Corré `ap lint`.

**Tiene que salir:** `CONTEXTO … html_comment_injection`, con el motivo. Borrá la línea.

La lista de patrones está en `context.blockedPatterns` del config: `ap config get context.blockedPatterns`.

## Ejercicio 1.3 — Una ruta

Una ruta suma una pista al turno cuando el pedido del humano casa con su patrón. Es una guía
dirigida: aparece solo cuando hace falta.

```bash
ap rule add routes --id calc --pattern '\b(suma|resta|calc)\b' \
  --example "arreglá la suma" \
  --hint "El código vive en app/. Terminado = el gate verde, no 'ya compila'." --apply
ap rule test routes "por favor arreglá la resta"
```

**Tiene que salir:** `## Ruteo del arnés (repo-harness)` y la línea con `**calc**`.

## Para discutir

- ¿Qué pasa si la guía dice una cosa y un freno otra? El agente hace lo que le dijeron, el freno
  lo bloquea y reintenta en bucle. Por eso existe `COHERENCIA` (P18): una guía no puede recomendar
  un comando que un freno veda. Lo vas a ver en el módulo 2.
- ¿Por qué la guía no alcanza? Porque es **inferencial**: depende de que el modelo la lea y la
  siga. Lo que tiene que cumplirse sí o sí es un freno.

→ [Módulo 2](02-frenos.md)
