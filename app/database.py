"""
app/database.py
---------------
Gestión de la conexión SQLite y bootstrap del esquema.

• La base de datos por defecto es ``laboratorio.db`` en la raíz del proyecto.
• Se puede sobreescribir mediante el parámetro ``db_path`` en ``get_connection``
  o pasando la ruta en ``init_db``.  Esto permite que los tests usen ``:memory:``
  o un archivo temporal sin tocar la base de producción.
• ``init_db`` es idempotente: puede llamarse múltiples veces sin duplicar datos.
"""

import sqlite3
from pathlib import Path

# Ruta por defecto: raíz del proyecto (un nivel arriba de este archivo)
_DEFAULT_DB = str(Path(__file__).parent.parent / "laboratorio.db")

# Inventario de unidades precargadas (inmutable)
_UNIDADES_INICIALES: list[tuple[str, str]] = [
    ("MIC-01", "Microscopio digital"),
    ("MIC-02", "Microscopio digital"),
    ("OSC-01", "Osciloscopio"),
    ("MUL-01", "Multímetro"),
    ("FUE-01", "Fuente de alimentación"),
]


def get_connection(db_path: str = _DEFAULT_DB) -> sqlite3.Connection:
    """Devuelve una conexión SQLite con ``row_factory`` configurado para
    acceder a las columnas por nombre (como diccionarios).

    Args:
        db_path: Ruta al archivo de base de datos.  Usar ``:memory:`` para
                 bases de datos en memoria (tests).

    Returns:
        Conexión ``sqlite3.Connection`` lista para usar.
    """
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    # Forzar comprobación de claves foráneas en cada conexión
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = _DEFAULT_DB) -> None:
    """Crea las tablas ``unidades`` y ``reservas`` si no existen y precarga
    el inventario de forma **idempotente** (INSERT OR IGNORE).

    Args:
        db_path: Ruta al archivo de base de datos.
    """
    conn = get_connection(db_path)
    with conn:
        # ------------------------------------------------------------------
        # Tabla de unidades (inventario)
        # ------------------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS unidades (
                id          TEXT PRIMARY KEY,
                descripcion TEXT NOT NULL
            );
            """
        )

        # ------------------------------------------------------------------
        # Tabla de reservas
        #
        # ``inicio`` y ``fin`` se almacenan como TEXT en formato ISO 8601
        # (YYYY-MM-DDTHH:MM).  La comparación lexicográfica es equivalente a
        # la comparación cronológica para este formato, lo que simplifica las
        # consultas SQL de detección de superposición.
        #
        # ``estado`` puede ser 'ACTIVA' o 'CANCELADA'.  Las cancelaciones
        # nunca borran el registro (Adaptación Específica 2 de rules.md).
        # ------------------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reservas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                id_unidad   TEXT    NOT NULL REFERENCES unidades(id),
                solicitante TEXT    NOT NULL,
                inicio      TEXT    NOT NULL,
                fin         TEXT    NOT NULL,
                estado      TEXT    NOT NULL DEFAULT 'ACTIVA'
                                    CHECK(estado IN ('ACTIVA', 'CANCELADA'))
            );
            """
        )

        # ------------------------------------------------------------------
        # Precarga idempotente del inventario
        # ------------------------------------------------------------------
        conn.executemany(
            "INSERT OR IGNORE INTO unidades (id, descripcion) VALUES (?, ?);",
            _UNIDADES_INICIALES,
        )
    conn.close()
