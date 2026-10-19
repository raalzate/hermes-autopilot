# 0013 — Workspace: un repo de gestión que orquesta, codificadores que codifican

**Estado:** aceptada · **Fecha:** 2026-10-19

## Contexto

El arnés gobernaba un repo, una cola y un agente. Un equipo con varios repos necesita además:

- un lugar para las épicas, los milestones, el tablero de portafolio y la wiki;
- una forma de partir una épica en tareas de cada repo;
- una forma de volver a saber qué se cerró.

Esas tareas son de dos clases:

- las del **orquestador**: partir, despachar, seguir, escalar;
- las del **codificador**: un issue chico que verifica el gate de su repo. Las trabaja Claude Code
  o Hermes, cada uno con su tablero y su cola.

Mezclarlas en un mismo repo hace que el orquestador escriba código y que el codificador decida el
alcance.

Hay tres forjas en uso: GitHub, GitLab y Azure DevOps. El instalador sólo sabía de GitHub Actions,
y la única pieza de forja del config era `tracker`, el formato de la referencia a un issue en un
commit.

## Decisión

1. **Dos roles, dos repos.**
   - El **repo de gestión** (`workspace.json`, `workspace.py init`) no tiene código. Tiene las
     épicas, los milestones, el tablero, la wiki y la cola del orquestador (Hermes).
   - Cada **codificador** (`workspace.py add`) tiene su repo, su tablero, su cola, su perfil de
     stack y su agente como `loop.agentCommand`.
   - `workspace.py check` rechaza dos cosas: un codificador apuntando al repo de gestión, y un repo
     de gestión que declara código de un stack.
2. **La épica es la fuente de la verdad del despacho.** Es un issue padre con un checklist, una
   línea por hijo: `- [ ] [<proyecto>] <título>`.
   - `despachar` crea un issue por línea en el repo del proyecto y lo vincula al padre con el
     vínculo nativo de la forja: sub-issue en GitHub, issue link en GitLab, Parent en Azure.
   - Además, el padre queda nombrado en el cuerpo del hijo, que es el vínculo que sobrevive entre
     forjas distintas.
   - Agrega la referencia a la línea (`→ org/repo#n`) y encola la tarea en el loop del
     codificador con `[issue: …]`.
   - Es todo o nada: con una línea inválida no se crea ningún hijo. Despachar dos veces no repite.
   - `estado` marca `[x]` lo cerrado en la forja y `[!]` lo que el loop del codificador escaló.
3. **Las forjas son manifiestos** (`plantillas/forjas/<id>.json`), no código (P4).
   - Cada operación abstracta (`issue.crear`, `issue.vincular`…) es un argv de su CLI, con grupos
     opcionales. La salida se lee con una regex o una ruta JSON.
   - `plugin/harness/forja.py` es puro: arma comandos y reescribe el checklist, y no lanza procesos.
   - Agregar una forja es agregar un manifiesto.
4. **Cada operación está clasificada por la integración de su CLI** (`github`, `gitlab`,
   `azure-devops`).
   - `check` exige que la clase que declara la forja sea la que la integración decide. Si no, el
     plan diría «leer» y el freno «mandar».
   - Así, si Hermes corre `gh issue create` a mano, lo gobierna el mismo perfil.
5. **Seco por defecto, y publicar lo aprueba un humano** (P9, P13).
   - Sin `--apply`, las lecturas van a la forja de verdad, para que el plan salga con la épica
     real, y lo que escribe se imprime y se simula.
   - El plugin ve `python3 workspace.py despachar --apply`, no cada `gh`. Por eso la regla
     `terminal.ask` `workspace-publica` pide aprobación en la plantilla de todo repo.
   - El loop sigue sin publicar.
6. **El pipeline sale de la forja.** `install.py --forja` instala GitHub Actions, GitLab CI o Azure
   Pipelines, todos con el mismo `gate.py`. También apunta `drift.runner` al archivo que corre la
   deriva y fija `tracker` desde el manifiesto.

## Consecuencias

- `workspace.py check` es una señal del gate, sin red. Cubre cada forja con sus ejemplos, cada
  operación contra su integración, el pipeline y un despacho de punta a punta contra la forja
  simulada. Doce mutaciones exigen que el self-test (§16) note cada pieza rota.
- **Abierto (docs/huecos.md):** el despacho contra una forja real. GitLab y Azure son adaptadores
  probados en seco. GitHub está completo en operaciones, pero tampoco tiene una corrida automática
  contra una organización real.
- **Límites conocidos:**
  - La descripción de un work item de Azure es HTML: el checklist viaja con `<br>`.
  - La wiki de GitHub y la de Azure se crean una vez desde la web.
  - El tablero de GitHub (Projects) pide el scope `project` de `gh`.
