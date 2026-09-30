# 0002 — Python de la biblioteca estándar, sin dependencias

**Estado:** aceptada · 2026-09-30

## Contexto

`agent-harness` es Node sin dependencias porque Claude Code trae Node. Hermes es Python
(≥ 3.11) y sus plugins se importan dentro de su proceso.

## Decisión

Todo el arnés —plugin, frenos, gate, lint, self-test, instalador— es Python stdlib. Ni PyYAML:
el frontmatter de las skills y el `config.yaml` de Hermes se leen con parsers mínimos de las
formas que Hermes escribe. El config del arnés es JSON para no necesitar un parser de YAML.

## Consecuencias

- Donde hay Hermes, hay todo lo que el arnés necesita: copiar es instalar.
- Un plugin con dependencias rompería el entorno de Hermes (`python_dependencies` nunca se
  instala sola). La regla `patterns[dependencia]` lo caza en el código del arnés.
- `doctor.py` puede no entender una forma rara de YAML: la reporta como "no encontrado", nunca
  como verde.
