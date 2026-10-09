# Integraciones

Lo que el agente hace **afuera** del repo: correo, WhatsApp y otras mensajerías, navegador, Google
Workspace, Microsoft 365, GitHub, bases de datos. Hermes trae los conectores; el arnés decide qué
puede hacer cada uno, con quién, cuánto, desde qué tarea, y con qué secretos y recursos arranca.
Por qué está hecho así: [ADR 0010](decisions/0010-integraciones.md).

```bash
python3 scripts/integ.py list                                   # el catálogo y qué está habilitado
python3 scripts/integ.py show google-workspace                  # perfiles, secretos, pasos
python3 scripts/integ.py add google-workspace --perfil asistente \
        --set 'policy.allowRecipients=["@miempresa\\.com$"]'    # DRY-RUN: prueba antes de escribir
python3 scripts/integ.py add google-workspace --perfil asistente --set '…' --apply
python3 scripts/integ.py deps google-workspace --apply          # instala aislado, fija versión, escribe el lock
python3 scripts/integ.py hermes google-workspace                # el bloque para ~/.hermes/config.yaml
python3 scripts/integ_run.py --secretos google-workspace        # ¿se resuelve cada secreto? (sin mostrarlos)
python3 scripts/integ_run.py --probe google-workspace           # ¿el servidor publica lo que dice el manifiesto?
python3 scripts/integ.py test google-workspace send_gmail_message '{"args": {"to": "x@afuera.com"}}'
```

Todo eso también está como `python3 scripts/cli.py integ …`.

## El catálogo

| Integración | Tipo | Qué conecta | Arranca en | Verificado contra |
|---|---|---|---|---|
| `navegador` | MCP | Chromium headless (Playwright MCP), instancia aislada, sin imágenes en las respuestas | `lectura` | `@playwright/mcp` 0.0.83: `tools/list` real y una navegación real por el lanzador |
| `navegador-hermes` | Hermes | el navegador propio de Hermes (agent-browser) | `lectura` | `tools/browser_tool.py` |
| `google-workspace` | MCP | Gmail, Drive, Calendar, Docs, Sheets (workspace-mcp); en `lectura`, scopes de sólo lectura | `lectura` | `workspace-mcp` 2.0.1: `tools/list` real (120) |
| `microsoft-365` | MCP | Outlook, OneDrive, Calendar, Excel, To Do, Planner (Graph); firma «enviado por un agente» | `lectura` | `@softeria/ms-365-mcp-server` 0.160.0: `tools/list` real (189) |
| `mensajeria` | CLI | WhatsApp, Telegram, Slack, Teams, correo… vía `hermes send` | `asistente` | `hermes_cli/send_cmd.py` |
| `github` | CLI | `gh`: issues, PRs, releases, API | `asistente` | subcomandos y banderas de `gh` 2.x |
| `postgres` | CLI | `psql`, con el SQL clasificado; la defensa de verdad es un rol de sólo lectura | `lectura` | `psql` 14+ |

Un MCP de un servidor remoto del catálogo de Hermes (`hermes mcp install linear`) también se puede
gobernar: si no tiene manifiesto, cada herramienta suya escala (`integrations.undeclared`). Para
que deje de escalar, escribile un manifiesto (ver «Agregar una integración»).

## Cómo decide

Cada llamada a una herramienta de una integración pasa, en `pre_tool_call`, por estas preguntas en
orden. Cada respuesta es una regla con id propio (`integ:<id>:<regla>`): así aparece en el panel y
en el registro.

1. **¿La tarea la declara?** En el loop, una tarea usa sólo lo que nombra
   (`- [ ] … [integraciones: google-workspace]`). Si no nombra nada, usa `loop.defaultIntegrations`,
   que en la plantilla es `[]`: ninguna. Si la tarea no la declara, la regla es `fuera-de-la-tarea`.
2. **¿Qué clase de acción es?** Se decide por el nombre de la herramienta, o por el comando si es
   una CLI:

   | Clase | Ejemplos | Notas |
   |---|---|---|
   | `deny` | Apps Script, `graph-batch`, `gh secret set`, `DROP TABLE`, JavaScript arbitrario en la página | frena en todo perfil |
   | `destructive` | filtros y reglas de correo, permisos de Drive, borrar | |
   | `send` | correo, mensaje, compartir, subir un archivo | |
   | `read` | | |
   | `write` | | todo lo que no está declarado cae acá: muta |

3. **¿Qué permite el perfil para esa clase?** Una de cuatro acciones:

   | Acción | Qué hace |
   |---|---|
   | `allow` | pasa |
   | `ask` | escala a un humano; en el loop o en cron se niega |
   | `deny` | frena |
   | `allowlist` | pasa sólo si cada destinatario está en `policy.allowRecipients`; si no, escala |

   Los perfiles del catálogo:

   | Perfil | `read` | `write` | `send` | `destructive` |
   |---|---|---|---|---|
   | `lectura` | allow | deny | deny | deny |
   | `asistente` | allow | ask | allowlist | deny |
   | `autonomo` | allow | allow | allowlist | ask |

4. **Archivos locales** (`fileKeys`, `filePattern`): un adjunto, una subida o un `--body-file`
   pasan por las mismas reglas que `read_file` y `write_file`. Subir el `.env` es leerlo.
5. **URLs** (`urlKeys`): se revisan tres cosas:
   - esquema: sólo `http(s)`; `file:` lee el disco y `javascript:` ejecuta código;
   - redes internas y de metadatos (`169.254.169.254`, `localhost`, `10.x`…): siempre frenadas;
   - `policy.allowDomains`: si la lista no está vacía, lo de afuera escala.
6. **Lo que dice** (`integrations.content`): un secreto o una plantilla sin completar
   (`Hola {{nombre}}`) en el texto que sale frena aunque todo lo demás esté bien. El texto
   correcto no lo decide un regex; el que nunca puede salir, sí.
7. **Presupuesto** (`budget.maxPerHour` por clase): un error no se repite cien veces. Lo que un
   humano aprueba también cuenta: el plugin lo descuenta en `post_tool_call`, cuando Hermes ya lo
   ejecutó (una aprobación negada no gasta).
8. **Sesión contaminada:** si la sesión ya leyó contenido de terceros (`thirdParty`: un correo,
   una web, un issue), mandar o mutar escala aunque el destinatario esté en la lista.
9. Por último, la acción del perfil.

Un `mcp__*` que ninguna integración declara escala (`undeclared`). Una integración con un manifiesto
roto deja pasar (P5): lo caza `integ.py check` en el gate, no el turno del usuario.

## Seguro

- **Secretos por referencia.** En el manifiesto y en el config sólo hay `secret://…`:

  | Referencia | De dónde sale el valor |
  |---|---|
  | `secret://keychain/<servicio>/<cuenta>` | llavero de macOS |
  | `secret://keyring/<servicio>/<cuenta>` | llavero del sistema: macOS, o `secret-tool` en Linux |
  | `secret://op/<bóveda>/<ítem>/<campo>` | 1Password |
  | `secret://file/<ruta>` | un archivo **fuera** del repo |
  | `secret://env/<NOMBRE>` | una variable que Hermes ya le pasa al servidor |

  `integ_run.py` las resuelve al arrancar el servidor y las pone sólo en su entorno. El valor no pasa
  por el repo, ni por el config de Hermes, ni por el contexto del modelo. Un secreto con su valor en
  un manifiesto es rojo en el gate.
- **Mínimo privilegio en la fuente.** Google y Microsoft arrancan con `--read-only` en `lectura`: el
  proveedor ni siquiera entrega una credencial que pueda mandar.
- **Lo que el perfil veda no se registra.** `integ.py hermes <id>` genera `tools.include` sin las
  herramientas vedadas: el modelo ni las ve.
- **El agente no se da permisos.** Dos reglas lo frenan:
  - `integ … --apply` (habilitar, cambiar perfil o destinatarios, instalar) escala a un humano: es la
    regla `integraciones-cambia`;
  - `.hermes/integraciones.lock` es una ruta protegida.
- **Quién le habla al agente.** En el gateway lo decide Hermes (`<PLATAFORMA>_ALLOWED_USERS`, o el
  emparejamiento). `doctor.py` marca rojo `allow_all_users: true` y cualquier `*_ALLOW_ALL_USERS`
  encendida.

## Óptimo en recursos

| Qué | Cómo |
|---|---|
| tokens | `tools.include` registra sólo lo que el perfil permite. Microsoft 365 publica 189 herramientas; en `lectura` el modelo ve las de lectura. Las CLI (`gh`, `psql`, `hermes send`) no agregan ningún esquema |
| procesos | `lazy: true`: el servidor arranca con el primer uso. `idle_timeout_seconds` lo apaga si no se usa (`budget.idleMinutes`) |
| memoria y CPU | `budget.maxMemoryMB` (heap de Node, o `RLIMIT_AS` en Python) y `budget.nice` |
| navegador | headless, perfil en memoria (`--isolated`), sin imágenes en las respuestas: lee el árbol de accesibilidad, que es texto |
| resultados | `budget.maxResultChars` recorta en `transform_tool_result` y le dice al modelo que pida menos. Hermes además guarda aparte lo que pasa de 50k (`tool_budget.mcp_result_size_chars`) |
| costo del freno | ~0.6 ms por llamada. Con presupuesto lee el registro de eventos: ~4 ms con 3000 líneas (`timing.py`) |

## Dependencias

`integ.py deps <id>` instala lo que pide el manifiesto. Es dry-run sin `--apply`.

| `kind` | Cómo se instala | Dónde |
|---|---|---|
| `npm` | `npm install --prefix … --ignore-scripts --save-exact paquete@versión` | `~/.hermes/integraciones/<id>/<versión>/` |
| `pypi` | un venv propio y `pip install paquete==versión --report` | ahí mismo |
| `browser` | el instalador del propio servidor (sabe qué build espera) | `<prefijo>/browsers` |
| `system` | **no se instala**: se verifica la versión y se imprime el comando para el humano | — |

- **Versiones fijas.** `latest` o un rango son rojo.
- **Lock.** Después de instalar, se escribe `.hermes/integraciones.lock` con el hash de lo
  instalado: el `integrity` de npm o el sha256 del wheel. Commitealo: el equipo instala lo mismo.
- **Señal del gate.** `integ.py check` es rojo si el lock no dice lo que el config pide.
- **Fuera del entorno de Hermes.** Nada se instala ahí ni en el arnés (ADR 0002): cada servidor es
  otro proceso.
- **Vulnerabilidades.** `drift.py`, semanal, consulta OSV con lo fijado:
  - una vulnerabilidad conocida es rojo;
  - una versión nueva es aviso: se prueba con `--probe` antes de subirla, nunca sola.

## Paso a paso: Gmail con perfil asistente

1. `python3 scripts/integ.py add google-workspace --perfil asistente --set 'policy.allowRecipients=["@miempresa\\.com$"]' --apply`
2. `python3 scripts/integ.py deps google-workspace --apply`
3. Guardá el cliente OAuth en el llavero. El comando lo muestra `integ.py show google-workspace`.
4. `python3 scripts/integ.py hermes google-workspace`, y pegá el bloque en `~/.hermes/config.yaml`.
5. `python3 scripts/integ_run.py --secretos google-workspace` y `--probe google-workspace`.
6. `python3 scripts/doctor.py`: instalada, enganchada por el lanzador, sin gateway abierto.
7. En la cola del loop: `- [ ] Prepará las respuestas del buzón [integraciones: google-workspace]`.

## Agregar una integración al catálogo

1. Instalá el servidor en un directorio temporal y corré la sonda. Anotá `toolNames` tal como los
   publica.
2. Escribí `plantillas/integraciones/<id>.json`, con:
   - `classes` (regex sobre el nombre crudo; para una CLI, sobre el comando);
   - `thirdParty`, `recipientKeys`, `urlKeys` y `fileKeys`;
   - `perfiles`, `budget`, `requires` (con versión fija) y `launch` (secretos `secret://`);
   - `verificado`: qué se miró y cuándo.
3. Escribí `examples`. Cada perfil necesita al menos uno que frene y uno inocente; `regla` dice qué
   regla tiene que morder y `set` pone la política que el ejemplo necesita.
4. `python3 scripts/integ.py check`: cada ejemplo, con cada perfil, por el plugin.
5. Si no le creés a las anotaciones del servidor (Playwright marca «destructivo» hasta navegar):
   `ignoreAnnotations` y `$ignoreAnnotations`, que dice por qué.

## Lo que no cubre

Está en [huecos](huecos.md):

- el **texto** de un mensaje permitido: a quién, cuánto, y que no lleve un secreto ni un hueco de
  plantilla se controla; si lo que dice es correcto (un dato de otro cliente, una promesa), no.

Los casos que lo muestran de punta a punta:

- [`oficina-whatsapp-masivo`](../casos/oficina-whatsapp-masivo/README.md)
- [`correo-inyeccion-adjunto`](../casos/correo-inyeccion-adjunto/README.md)
- [`navegador-metadatos`](../casos/navegador-metadatos/README.md)
- [`drive-compartir-publico`](../casos/drive-compartir-publico/README.md)
- [`dev-issue-contaminado`](../casos/dev-issue-contaminado/README.md)
