# Workspace: varios proyectos, un orquestador

Un workspace son varios repos sobre una **forja**: GitHub por defecto, o GitLab o Azure DevOps.

- **Un proyecto de gestión**, donde trabaja el orquestador (Hermes). No tiene código: tiene las
  épicas, los milestones, el tablero de portafolio, la wiki y la cola del orquestador.
- **N codificadores**, cada uno con su repo, su tablero, su cola y su agente (Claude Code o Hermes),
  y su propio arnés.

Lo que los une es la **épica**: un issue padre en gestión, con un checklist de hijos, y un issue
hijo por línea en el repo de cada codificador. Por qué está hecho así: [ADR 0013](decisions/0013-workspace-y-forjas.md).

```
gestión (Hermes orquesta)                     codificador `api` (Claude Code)
  épica #12  ── M2 · First delivery             issue acme/api#5  «Part of acme/gestion#12»
  - [ ] [api] Login       → acme/api#5   ──▶    .hermes/loop/tasks.md:  - [ ] Login [issue: acme/api#5]
  - [ ] [web] Pantalla    → grupo/web#3  ──▶    codificador `web` (GitLab, Hermes)
  tablero de portafolio · wiki · roadmap        tablero del proyecto · su gate · su CI
```

## De cero

```bash
# 1. El proyecto de gestión. En seco imprime lo que haría; --local sólo escribe los archivos.
python3 scripts/workspace.py init ../gestion --org acme
python3 scripts/workspace.py init ../gestion --org acme --apply      # repo, milestones y tablero en la forja

cd ../gestion && git init && python3 .hermes/harness/scripts/githooks.py install

# 2. Cada codificador: lo registra, le instala el arnés con su perfil, su forja y su agente.
python3 .hermes/harness/scripts/workspace.py add api --repo acme/api --dir ../api --profile python --agent claude-code --create --apply
python3 .hermes/harness/scripts/workspace.py add web --repo grupo/web --forge gitlab --dir ../web --profile front --apply

# 3. Una épica, su despacho y su seguimiento.
python3 .hermes/harness/scripts/workspace.py epic "Login" --child api:"Endpoint de login" --child web:"Pantalla de login" \
    --milestone "M2 · First delivery" --goal "Los clientes entran con su correo." --apply
python3 .hermes/harness/scripts/workspace.py dispatch 12            # el plan, con la épica real
python3 .hermes/harness/scripts/workspace.py dispatch 12 --apply    # publica (pide aprobación)
python3 .hermes/harness/scripts/workspace.py status                 # [x] cerrado · [!] escalado
python3 .hermes/harness/scripts/workspace.py wiki --apply           # regenera Proyectos.md y empuja wiki/
```

`init` deja en el proyecto de gestión:

- `workspace.json` (esquema: `plantillas/workspace/workspace.schema.json`);
- un `AGENTS.md` con el rol del orquestador;
- `wiki/` (Home, Proyectos, Arquitectura, Decisiones);
- `roadmap.json`, con los milestones;
- la plantilla de issue «Epic» de la forja;
- la cola del orquestador;
- el arnés instalado con el perfil de gestión y la señal `workspace.py check` en su gate.

## La épica

`workspace.py epic` la crea desde la plantilla (`plantillas/workspace/management/epic.md`), con su
milestone, y la suma al tablero de portafolio. Su checklist:

```markdown
## Hijos

- [ ] [api] Endpoint de login
- [ ] [web] Pantalla de login
```

- **`[api]`** es el `id` de un codificador de `workspace.json`. Si una línea nombra un proyecto que no
  existe, `epic` no crea nada.
- **`dispatch`** crea un hijo por cada línea que no tenga referencia todavía:
  - el hijo es un issue en el repo del proyecto, con «Part of <gestión>#12» en el cuerpo;
  - se vincula al padre: sub-issue en GitHub, issue link en GitLab, Parent en Azure. Entre forjas
    distintas, el vínculo es sólo el texto;
  - va al tablero del proyecto;
  - si el proyecto tiene `dir`, se encola en el loop del codificador:
    `- [ ] Endpoint de login [issue: acme/api#5]`. El loop le pasa al agente `HARNESS_ISSUE`, el
    issue que cierra su PR (en GitHub, `Closes #5`).
- Después del despacho, la línea gana su referencia (`→ acme/api#5`).
- **Todo o nada:** con un `[proyecto]` que no existe no se crea ningún hijo.
- **Despachar dos veces no repite.**
- **`status`** pasa a `[x]` lo cerrado en la forja y a `[!]` lo que el loop del codificador escaló
  a un humano. La épica la cierra un humano.

## Las forjas

| Forja | CLI | Vínculo padre→hijo | Milestone | Tablero | Pipeline | Estado |
|---|---|---|---|---|---|---|
| `github` | `gh` | sub-issue | milestone | GitHub Projects (`gh auth refresh -s project`) | Actions | probado contra GitHub real (2026-10-19) |
| `gitlab` | `glab` | issue link | milestone | board del proyecto | `.gitlab-ci.yml` | adaptador: en seco |
| `azure` | `az` + azure-devops | Parent | iteración | Azure Boards (viene con el proyecto) | `azure-pipelines.yml` | adaptador: en seco |

- **Una forja es un manifiesto** (`plantillas/forges/<id>.json`), con su esquema
  (`plantillas/forges/forge.schema.json`). Declara:
  - cada operación (`repo.create`, `issue.create`, `issue.link`, `issue.state`, `issue.body`,
    `issue.edit`, `milestone.create`, `board.create`, `board.add`) como argv de su CLI;
  - cómo leer la salida;
  - los estados;
  - la clase de cada operación;
  - la URL de la wiki;
  - el pipeline;
  - sus `examples`.
- **Agregar una forja** es agregar un manifiesto y la integración de su CLI
  (`plantillas/integraciones/`). `workspace.py check` los prueba juntos: el esquema, los ejemplos,
  cada operación clasificada por su integración y una épica de punta a punta contra la forja
  simulada.
- **En Azure**, el repo se nombra `<org>/<proyecto>/<repo>`.

**`install.py --forge gitlab`** instala `.gitlab-ci.yml` en lugar de los workflows de GitHub y
apunta `drift.runner` ahí. En GitLab, la deriva corre en un pipeline programado
(CI/CD → Schedules).

## Seco, aplicar y quién aprueba

- **Sin `--apply` (seco):** las lecturas van a la forja de verdad y lo que escribe se imprime con
  `+` y se simula.
- **`--simulated`:** todo contra la forja de juguete, sin red.
- **`--apply`:** publica. Cuando lo corre Hermes, la regla `terminal.ask` `workspace-publica` pide
  aprobación: el plugin ve `workspace.py`, no cada `gh`. El loop nunca publica (P13).

## Tablero de problemas

| Síntoma | Causa | Arreglo |
|---|---|---|
| `no workspace.json found` | corriste fuera del repo de gestión | `cd` al repo de gestión o `--ws <dir>` |
| `nothing dispatched (all or nothing)` o `nothing created` | una línea nombra un proyecto que no está en `workspace.json` | `workspace.py add <id> …` o corregí la línea |
| `gh project create … does not have permission` | el token de `gh` no tiene el scope `project`, o no podés crear proyectos en esa org | `gh auth refresh -s project`; si es la org, pedí el permiso |
| `glab is not on the PATH` | falta la CLI de la forja | el `setup` del manifiesto (`brew install glab`, `az extension add --name azure-devops`) |
| `workspace.py wiki` falla al clonar (`Repository not found`) | la wiki de GitHub o de Azure no existe todavía; en GitHub, un repo **privado** sólo tiene wiki con un plan pago (`has_wiki: false` en el plan gratuito) | creá la primera página desde la web y repetí; con un repo privado en el plan gratuito, usá la carpeta `wiki/` del repo de gestión como wiki |
| el gate del repo de gestión pide un perfil | lo instalaste con `install.py` y no con `workspace.py init` | `init` le pone el perfil de gestión (`plantillas/workspace/management/profile.json`) |
