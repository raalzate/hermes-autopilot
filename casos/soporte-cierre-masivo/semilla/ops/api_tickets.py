"""Cliente de la API de tickets (api.acme.test). En el sandbox, cada escritura queda en .sim/api.log."""
from pathlib import Path


def cerrar(ticket_id, motivo):
    log = Path(".sim/api.log")
    log.parent.mkdir(exist_ok=True)
    with log.open("a") as f:
        f.write(f"PATCH /tickets/{ticket_id} estado=cerrado motivo={motivo!r}\n")
