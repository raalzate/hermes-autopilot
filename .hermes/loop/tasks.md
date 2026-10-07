# Tareas del loop autónomo

La cola que consume `scripts/loop.py`: la primera casilla vacía es la próxima tarea. El loop marca
`[x]` la que terminó con el gate verde y `[!]` la que escaló a un humano (con el motivo).

Una tarea buena para el loop es chica, verificable por el gate y sin decisiones de producto:
"agregá la regla X con su example", no "mejorá el arnés". Se agregan con
`python3 scripts/cli.py task add "texto"`.

