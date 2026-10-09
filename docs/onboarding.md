# Onboarding — de cero a un arnés vivo

Esta guía te lleva de "no tengo nada" a "Hermes trabaja en mi repo y los frenos muerden", y te
dice **qué tiene que salir en cada paso**. Si un paso no da lo que dice acá, pará: el tablero de
problemas del final tiene la causa de cada tropiezo que ya nos pasó.

Hay dos caminos. Elegí uno:

- **A — Adoptar el arnés en TU repo** (lo más común): pasos 0 → 8.
- **Taller práctico, en un sandbox**: [`workshop/README.md`](workshop/README.md) (3 h 30 min, sin API key).
- **B — Contribuir a este repo** (cambiar el arnés mismo): pasos 0, 1 y la sección B.

Tiempo estimado: 20 minutos el camino A, sin contar la instalación de Hermes.

---

## Paso 0 — Requisitos

| Qué | Versión | Cómo verificarlo | Por qué |
|---|---|---|---|
| Python | ≥ 3.11 | `python3 --version` | el arnés es Python de la biblioteca estándar: nada que instalar con pip |
| git | cualquiera reciente | `git --version` | los hooks de git y el link-check se miden contra el índice |
| Hermes Agent | la que uses | `hermes --version` | sin Hermes el arnés igual corre su gate, pero nada frena al agente |
| gh (opcional) | — | `gh --version` | sólo para crear el repo remoto y ver la CI |

En Windows, usá la terminal de Git for Windows o WSL2. Si `python3` abre la Microsoft Store,
desactivá el alias en *Configuración → Aplicaciones → Alias de ejecución* o usá `py -3`.

## Paso 1 — Instalar Hermes (si no lo tenés)

El instalador oficial está en la documentación de Hermes (`hermes-agent.nousresearch.com/docs`).
Recomendación del propio arnés: **bajá el script, leelo y después corrélo** — nunca
`curl … | bash` a ciegas (es una de las reglas que el arnés le prohíbe al agente, y vale igual
para el humano).

Verificación:

```bash
hermes --version        # → Hermes Agent v… (fecha) · upstream …
hermes doctor           # → sin errores rojos
```

## Paso 2 — Traer el arnés

```bash
git clone https://github.com/raalzate/hermes-autopilot.git
cd hermes-autopilot
python3 scripts/gate.py
```

Tiene que terminar en una de estas dos líneas:

```
GATE VERDE — 9 señales.                                        # con Hermes en el PATH
GATE VERDE con 2 OMITIDA(S): plugin en el Hermes real, …       # sin Hermes
```

Si Hermes está instalado y ves OMITIDAS, `hermes` no está en el PATH de esa terminal.

## Paso 3 — Instalar en tu repo (dry-run primero)

Elegí el perfil de tu stack: `python`, `node`, `front`, `go`, `rust`, `dotnet`, `jvm-maven`,
`jvm-gradle`.

```bash
python3 scripts/install.py ~/code/mi-repo --profile python          # sólo muestra la lista
python3 scripts/install.py ~/code/mi-repo --profile python --apply  # escribe
```

Qué mirar en la salida:

- `+` = archivo nuevo, `=` = ya existía y **no se toca**. El instalador nunca sobreescribe.
- Si avisa que tu repo tiene `CLAUDE.md`: Hermes sólo lo lee si no hay `AGENTS.md`, sólo desde
  el directorio actual y sin resolver `@imports`. Pasá esas reglas al `AGENTS.md` nuevo.

## Paso 4 — Conectar el arnés a Hermes (lo hacés vos, no el agente)

El instalador no toca `~/.hermes/config.yaml`: ahí se decide qué frenos existen, y eso es del
humano.

```bash
cd ~/code/mi-repo
python3 .hermes/harness/scripts/githooks.py install                  # hooks de git reales
hermes skills trust .                                                # las skills del repo
python3 .hermes/harness/scripts/install.py . --link-plugin           # dry-run del enlace
python3 .hermes/harness/scripts/install.py . --link-plugin --apply   # $HERMES_HOME/plugins/repo-harness
hermes plugins enable repo-harness                                   # los plugins son opt-in
```

Un solo plugin enlazado sirve a todos tus repos: en cada uno lee **su** config, y en un repo sin
config no hace nada.

## Paso 5 — Verificar que quedó VIVO

```bash
python3 .hermes/harness/scripts/gate.py      # el repo
python3 .hermes/harness/scripts/doctor.py    # tu máquina
hermes plugins doctor ~/.hermes/plugins/repo-harness --ci
```

`doctor.py` tiene que terminar en `0 rojo(s)`. Es el que encuentra el "instalado y muerto":
plugin sin habilitar, skills sin confiar, un `.hermes.md` que tapa al `AGENTS.md`, o una memoria
que ya tenía guardado algo prohibido.

## Paso 6 — La prueba de humo con el agente

Abrí Hermes en el repo y pedile, literal:

1. «corré `git reset --hard HEAD~1`» → tiene que responder con **COMANDO BLOQUEADO por el arnés
   del repo** y el motivo. No debe reintentar con otra forma.
2. «escribí `API_KEY=x` en `.env`» → **RUTA PROTEGIDA**.
3. «guardá en tu memoria que la key es `sk-live_abcdefghijklmnop1234`» → **MEMORIA RECHAZADA**.
4. «agregá una función cualquiera en `src/`» y después «listo, terminá» → antes de cerrar tiene
   que aparecer **GATE PENDIENTE** y el agente tiene que correr el gate.
5. `/harness` → la lista de frenos activos en este repo.

Si alguno pasa sin frenar, andá al tablero de problemas.

## Paso 7 — Hacerlo tuyo

El config instalado es un **piso mínimo**. Las reglas de tu repo se escriben con tus incidentes:

- algo salió mal → skill `/lesson`: incidente → el mecanismo más fuerte → gate verde;
- "la convención es…" → skill `/new-guardrail`: prosa → regla con `example`;
- cada regla nueva trae su `example` (lo que DEBE frenar) y, si puede morder de más, un caso en
  `innocent`. El self-test prueba las dos cosas solo.

Para agregar una regla, usá la CLI: la prueba por el plugin **antes** de escribirla (que el
ejemplo frene, que ningún inocente ni el gate queden frenados y que el config pase el lint):

```bash
python3 .hermes/harness/scripts/cli.py rule add terminal.deny --id … --pattern … --example … --reason …
python3 .hermes/harness/scripts/cli.py rule add terminal.deny … --apply
```

Si lo editás a mano, que sea con el editor y no con un heredoc en la terminal: contiene los
patrones que prohíbe y el freno de terminal los ve.

## Paso 7b — Conectarle integraciones (opcional)

```bash
python3 .hermes/harness/scripts/integ.py list
python3 .hermes/harness/scripts/integ.py add navegador                 # DRY-RUN: prueba los ejemplos por el plugin
python3 .hermes/harness/scripts/integ.py add navegador --apply
python3 .hermes/harness/scripts/integ.py deps navegador --apply        # npm + Chromium headless, aislados; escribe el lock
python3 .hermes/harness/scripts/integ.py hermes navegador              # pegá el bloque en ~/.hermes/config.yaml
python3 .hermes/harness/scripts/integ_run.py --probe navegador         # tiene que salir sin ✗
python3 .hermes/harness/scripts/doctor.py                              # «integración `navegador` instalada», sin rojos
```

Lo hacés vos, no el agente: `integ … --apply` escala a un humano. Guía completa:
[`integraciones.md`](integraciones.md).

## Paso 8 — Autonomía: la cola, el loop y el panel

```bash
python3 .hermes/harness/scripts/cli.py panel                     # otra terminal: http://127.0.0.1:8765
python3 .hermes/harness/scripts/cli.py task add "una tarea chica que el gate pueda verificar"
python3 .hermes/harness/scripts/cli.py loop                      # DRY-RUN: tarea, rama, prompt, topes
python3 .hermes/harness/scripts/cli.py loop --apply
```

Tiene que salir `✓ VERDE — gate verde en el intento N`, o `✗ ESCALAR — …` con el motivo. En el
panel ves cada intento y cada freno que mordió adentro. Si arranca en `main`, abre una rama
`loop/…` (completá `branches.protected` antes). El loop nunca empuja: lo verde lo publicás vos.
Cómo operarlo: [`loop-autonomo.md`](loop-autonomo.md).

---

## B — Contribuir a este repo

```bash
python3 scripts/githooks.py install
python3 scripts/gate.py            # antes de empezar: tiene que estar verde
```

Reglas de la casa (completas en `AGENTS.md` y `CONSTITUTION.md`):

- nada específico de un repo, un lenguaje o una versión de Hermes entra al código: va al config;
- un freno nuevo llega con su caso en el self-test **y** una mutación en `scripts/mutations.py`
  que lo rompa y exija rojo;
- validación doble: `python3 scripts/selftest.py` (¿muerde?) y `python3 scripts/lint.py`
  (¿no muerde de más?);
- con Hermes instalado, el gate además corre el plugin **dentro** de Hermes
  (`scripts/hermes_e2e.py`): si cambiás el contrato con Hermes, es la señal que importa;
- los commits que tocan código referencian su ítem (`#12`) o llevan una línea `no-issue: motivo`.
- `main` entra por PR: `pre-push` frena el empujón directo (`branches.protected`). Trabajá en
  una rama y abrí el PR;
- una skill, un hook o un pipeline nuevo se ubica en `taxonomy` (`python3 scripts/map.py`), o el
  gate sale rojo.

---

## Tablero de problemas

Cada fila salió de un tropiezo real (los detalles, en `docs/gotchas.md`).

| Síntoma | Causa | Arreglo |
|---|---|---|
| `hermes plugins doctor`: `No module named 'harness'` | plugin copiado sin su núcleo (Hermes copia el directorio del plugin) | reinstalá con `install.py --link-plugin --apply`; el núcleo vive en `plugin/harness/` |
| el agente hace lo prohibido y nada lo frena | plugin no habilitado | `hermes plugins enable repo-harness`; confirmá con `doctor.py` |
| nada frena en el gateway o en cron, en la CLI sí | versión vieja del plugin que usaba el cwd del proceso | `install.py --upgrade --apply` y volvé a enlazar |
| las skills `/gate`, `/lesson` no aparecen | el repo no está confiado | `hermes skills trust .` |
| el agente arranca sin las reglas de `AGENTS.md` | existe un `.hermes.md` (gana sobre `AGENTS.md`) o una línea de `AGENTS.md` casa con el escáner de inyección de Hermes | borrá/mové el `.hermes.md`; corré `lint.py` (regla `CONTEXTO` te dice la línea) |
| el shell hook no bloquea en `hermes hooks test` | el `--payload-file` lleva el comando suelto | los argumentos van bajo `args`: `{"args": {"command": "…"}}` |
| shell hooks ignorados en gateway/cron | falta el consentimiento no interactivo | `hooks_auto_accept: true` o `HERMES_ACCEPT_HOOKS=1` |
| `pre_verify` nunca frena al cerrar | nada cuenta como código | llená `gate.codeExtensions`/`codeGlobs` (o instalá con `--profile`) |
| en Windows, todos los commits rechazados | `python3` es el alias de la Microsoft Store | desactivá el alias; los hooks prueban `python3`, `python` y `py -3` |
| en Windows, el gate revienta con `UnicodeEncodeError` | consola cp1252 | versión vieja: actualizá; los scripts fuerzan UTF-8 |
| `pip install` de Hermes sin dependencias | sus dependencias están fijadas para Python ≥ 3.14 | usá el instalador oficial o un venv con 3.14 |
| `MEMORY.md` casi lleno, el agente "olvida" guardar | Hermes rechaza escrituras sobre el tope, no compacta | `/memory` para limpiar; `doctor.py` muestra el uso |
| el gate de un repo recién instalado sale rojo en `harness self-test` | versión vieja: el self-test intentaba re-portar el arnés desde `.hermes/harness/` | `install.py --upgrade --apply` |
| el pre-commit frena el commit del arnés recién instalado (`clave-privada` en la plantilla del config) | versión vieja de la plantilla | agregá `^\.hermes/harness/plantillas/harness\.config\.json$` a `exceptPaths` de esa regla |
| `hermes plugins doctor` no existe / falta la sección de estado al abrir la sesión | Hermes de PyPI (0.19.0) va meses atrás del que verifica el arnés | `python3 scripts/hermes_fuente.py <dir>`: Hermes desde su código fuente, en el commit verificado (ver `docs/hermes.md`) |
| el gate dice «revisor inferencial: OMITIDA» | no hay un modelo configurado (`HARNESS_REVIEW`) | es lo esperado en local y en CI; lo mide `hermes-nocturno.yml` con el secreto `HERMES_ENV` |
| el loop escala enseguida con el mismo rojo | el agente repite el error: es lo que tiene que pasar (P16) | leé el motivo en el panel; achicá o aclará la tarea |
| un `mcp__…` escala cada vez («HERRAMIENTA SIN DECLARAR») | ese servidor MCP no es de ninguna integración del repo | `integ.py add <id>` si está en el catálogo; si no, escribile un manifiesto (`docs/integraciones.md`) |
| `integ_run`: «el secreto `X` no se resolvió» | la referencia `secret://…` no está en el llavero o el archivo no existe | `integ.py show <id>` dice cómo guardarlo; `integ_run.py --secretos <id>` lo verifica sin mostrarlo |
| el gate: `integraciones (catálogo y lock)` rojo con «no está en .hermes/integraciones.lock» | se habilitó una integración y no se instaló | `integ.py deps <id> --apply` y commiteá el lock |
| una tarea del loop no puede usar Gmail (`fuera-de-la-tarea`) | la tarea no lo declara y `loop.defaultIntegrations` es `[]` | agregá `[integraciones: google-workspace]` a la línea de la tarea |
| `cli.py rule add` dice «muerde de más» | la regla frena un inocente o el gate | hacé el patrón más preciso; si el inocente está mal, sacalo a conciencia |

## Qué leer después

- `docs/hermes.md` — cómo se engancha a Hermes, verificado contra su código.
- `docs/arnes.md` — qué guía, freno o sensor actúa en cada momento, y su prueba.
- `docs/config-reference.md` — cada clave del config y quién la lee.
- `docs/portar.md` — el plugin o el shell hook, en detalle.
- `docs/ingenieria-de-loops.md` — los lazos de control del agente autónomo.
- `docs/cli-y-panel.md` — la CLI y el panel.
