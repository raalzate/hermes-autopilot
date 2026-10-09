# 0010 — Integraciones: Hermes conecta, el arnés gobierna

**Estado:** aceptada · **Fecha:** 2026-10-09

## Contexto

Un agente autónomo vale por lo que puede hacer afuera: leer y contestar correo, avisar por
WhatsApp, navegar, compartir un archivo de Drive, revisar un PR, consultar una base. Cada una de
esas cosas es también un permiso para dañar afuera, donde un `git revert` no alcanza: un mensaje
mandado no se des-manda y un filtro de Gmail reenvía correo durante meses.

Hermes ya trae los conectores, verificados en su código (hermes-agent `aa74e184`):

- un cliente MCP con `lazy`, `idle_timeout_seconds` y `tools.include`, y un entorno filtrado para
  cada servidor;
- un gateway con WhatsApp (bridge o Cloud API), Telegram, Slack, Teams, correo y más, con listas de
  quién le puede hablar al agente;
- un navegador propio (agent-browser).

Lo que no trae: decidir **qué clase de acción** es cada herramienta, a quién se puede mandar,
cuánto, desde qué tarea, y con qué secretos y recursos arranca cada servidor. Tres datos del código
cambiaron el diseño:

- **Nombres.** Las herramientas MCP se registran como `mcp__<server>__<tool>`, con doble guion bajo
  y `[^A-Za-z0-9_]` cambiado por `_`. La documentación de Hermes dice `mcp_<server>_<tool>`.
- **Mensajería.** `send_message` NO es una herramienta del modelo. El canal para escribirle a
  terceros es `hermes send --to plataforma:destino` por la terminal.
- **Carga perezosa.** Ya la hace Hermes. Un proxy propio que demorara el arranque habría duplicado
  `lazy` y metido un proceso en el medio de cada mensaje.

## Decisión

**Hermes conecta, el arnés gobierna.** Una integración es un MANIFIESTO de un catálogo
(`plantillas/integraciones/<id>.json`), del mismo tipo que los perfiles de stack. `scripts/integ.py
add` lo materializa en `integrations.enabled.<id>` del config, que sigue siendo la única fuente de
especificidad (P4). Antes de escribirlo, pasa sus `examples` por el mismo `guards.evaluate` que usa
el plugin: P2 (frena y lo frena esta integración) y P3 (los inocentes pasan).

| Pieza | Dónde | Qué decide |
|---|---|---|
| clase por nombre | `plugin/harness/integ.py` (puro) | deny · destructive · send · read · write. Lo no declarado muta (`write`). Por nombre y no por anotaciones: el plugin no ve las anotaciones, y las escribe el autor del servidor |
| perfil | el manifiesto (`lectura` · `asistente` · `autonomo`) | allow · ask · deny · allowlist por clase |
| destinatarios, URLs, archivos | `recipientKeys`/`recipientPattern`, `urlKeys`, `fileKeys`/`filePattern` | lista blanca; redes internas y esquemas; los archivos locales pasan por `protectedReads`/`protectedPaths` (subir el `.env` es leerlo) |
| presupuesto | `budget.maxPerHour` | el plugin cuenta en el registro de eventos (vale entre procesos) o en memoria |
| contaminación | `thirdParty` | lo que entra de afuera marca la sesión; después, mandar o mutar escala |
| alcance por tarea | `HARNESS_INTEGRACIONES` (lo pone el loop) | `[integraciones: a, b]` en la cola; `loop.defaultIntegrations: []` |
| sin declarar | `integrations.undeclared` | un `mcp__*` que nadie clasificó escala |
| arranque | `scripts/integ_run.py` | secretos `secret://` sólo en el entorno del servidor, techo de memoria, `nice`, `exec`; `--read-only` en la fuente cuando el servidor lo tiene |
| registro en Hermes | `integ.py hermes <id>` | `lazy`, `idle_timeout_seconds`, `timeout` y `tools.include` sin lo vedado: menos esquemas en el prompt |
| dependencias | `integ.py deps` | npm/pip aislados en `~/.hermes/integraciones/<id>/<versión>`, versiones fijas, `.hermes/integraciones.lock` con hash; nunca `sudo` |
| contrato | `integ_run.py --probe` | lo declarado contra el `tools/list` real |
| deriva | `drift.py` | vulnerabilidades conocidas (OSV) y versiones nuevas: semanal, fuera del gate |

Catálogo inicial, cada uno verificado contra el servidor o el código real:

- `navegador` (Playwright MCP);
- `navegador-hermes`;
- `google-workspace` (workspace-mcp);
- `microsoft-365` (ms-365-mcp-server);
- `mensajeria` (`hermes send`);
- `github` (`gh`);
- `postgres` (`psql`).

## Consecuencias

- Constitución 1.6.0: P26 (lo que el agente hace afuera tiene clase, destinatario y tope).
- La plantilla trae `integrations` (ninguna habilitada, `undeclared: ask`), `loop.defaultIntegrations: []`,
  la ruta protegida `lock-integraciones` y la escalada `integraciones-cambia`: habilitar o ampliar una
  integración con `--apply` lo decide un humano.
- `publicar-contaminado` se afinó: `gh pr diff` o `gh issue view` (leer) ya no escalan tras leer a
  un tercero. Mordía de más y lo cazó el caso `dev-issue-contaminado` (P3).
- Una señal nueva del gate (`integ.py check`), 25 mutaciones y 5 casos replicables.
- Lo que no cubre está en `docs/huecos.md`: el texto de un mensaje permitido y una aprobación humana
  que no se cuenta en el presupuesto.
