import os


def conexion():
    """Los parámetros de conexión a la base, desde el entorno (ver .env.example)."""
    return {
        "host": os.environ.get("DATABASE_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", ""),
    }
