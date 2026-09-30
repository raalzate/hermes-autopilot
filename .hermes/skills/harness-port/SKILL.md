---
name: harness-port
description: Instala este arnés en otro repositorio (cualquier lenguaje) y deja el gate verde allá. Usala cuando el humano pide llevar el arnés a otro proyecto o actualizar el que ya tiene.
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [harness, install]
    category: harness
---

# /harness-port

1. **Dry-run primero** (P9): `python3 scripts/install.py <repo> --profile <stack>` y mostrale
   la lista al humano. Perfiles: los `.json` de `plantillas/perfiles/`. El perfil trae HECHOS del
   stack (qué es código, qué es derivado, cómo se testea), nunca reglas de otro repo.
2. Con su confirmación: la misma línea con `--apply`. Nunca sobreescribe: lo que ya existía sale
   con `=` y queda como estaba.
3. Lo que hace **el humano** (el instalador no toca `~/.hermes/config.yaml`):
   - `hermes skills trust <repo>`
   - `python3 <repo>/.hermes/harness/scripts/install.py <repo> --link-plugin --apply`
   - `hermes plugins enable repo-harness`
   - `python3 <repo>/.hermes/harness/scripts/githooks.py install`
4. En el repo destino: `python3 .hermes/harness/scripts/gate.py`. Si sale rojo, se arregla allá
   con la skill `gate`. Después `scripts/doctor.py` para ver que quedó vivo en esta máquina.
5. Las reglas del repo destino se escriben con **sus** incidentes (skill `lesson`). Copiar las
   reglas de este repo es ruido bien intencionado que gasta contexto.

Si el repo tenía `CLAUDE.md`: Hermes lo lee sólo desde el cwd, sólo si no hay `AGENTS.md`, y no
resuelve sus `@imports`. Las reglas se pasan a `AGENTS.md`.
