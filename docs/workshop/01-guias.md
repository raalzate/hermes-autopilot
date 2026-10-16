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

`AGENTS.md` se inyecta siempre, en todas las sesiones, y por eso tiene que ser corto. Una **ruta**
resuelve lo contrario: una pista que solo aparece cuando hace falta. Antes de que el agente
empiece a trabajar, el plugin lee el pedido del humano. Si el texto casa con el patrón de una ruta,
suma la pista de esa ruta al turno. Si no casa, no se agrega nada y no gastás contexto.

**Las cuatro piezas de una ruta** (viven en `routes[]` del config):

| Campo | Qué es | En este ejercicio |
|---|---|---|
| `id` | el nombre; aparece en negrita en la pista | `calc` |
| `pattern` | una expresión regular que se busca en el pedido, sin distinguir mayúsculas | `\b(suma\|resta\|calc)\b` |
| `hint` | el texto que se le suma al agente | dónde vive el código y qué es «terminado» |
| `example` | un pedido que **tiene que** casar | `arreglá la suma` |

El patrón usa `\b` (límite de palabra) para casar la palabra entera. «arreglá la suma» casa,
pero «sumario» no. Sin `\b`, «sumario» activaría la ruta por error.

El `example` es la prueba de la regla. `ap rule add` casa el ejemplo contra el patrón **antes de
escribir** nada. Si no casan, la CLI rechaza la regla. Así no queda una ruta que nunca se activa.

```bash
ap rule add routes --id calc --pattern '\b(suma|resta|calc)\b' \
  --example "arreglá la suma" \
  --hint "El código vive en app/. Terminado = el gate verde, no 'ya compila'." --apply
ap rule test routes "por favor arreglá la resta"
```

- `rule add … --apply` prueba el ejemplo y escribe la ruta en el config. Sin `--apply` solo simula.
- `rule test routes "<texto>"` simula un pedido y muestra lo que el agente recibiría. Es tu forma de
  comprobar la ruta sin abrir una sesión de Hermes.

**Tiene que salir:** `## Ruteo del arnés (repo-harness)` y la línea con `**calc**`.

Probalo en los dos sentidos. Con «por favor arreglá la resta» sale la pista. Con
`ap rule test routes "cambiá el color del logo"` no sale nada: ese pedido no toca la calculadora.

**Qué dice la pista y por qué.** La frase «Terminado = el gate verde, no 'ya compila'» repite el
criterio del ejercicio 0.3. Cuando el pedido toca la calculadora, el agente recibe esa regla justo
en ese momento. Es más efectivo que dejarla perdida en un `AGENTS.md` largo.

**Límite.** Una ruta *informa*, no bloquea. El agente puede ignorar la pista. Lo que tiene que
cumplirse sí o sí es un freno (módulo 2).

## Para discutir

- ¿Qué pasa si la guía dice una cosa y un freno otra? El agente hace lo que le dijeron, el freno
  lo bloquea y reintenta en bucle. Por eso existe `COHERENCIA` (P18): una guía no puede recomendar
  un comando que un freno veda. Lo vas a ver en el módulo 2.
- ¿Por qué la guía no alcanza? Porque es **inferencial**: depende de que el modelo la lea y la
  siga. Lo que tiene que cumplirse sí o sí es un freno.

→ [Módulo 2](02-frenos.md)
