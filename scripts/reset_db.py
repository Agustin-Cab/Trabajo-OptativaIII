"""
scripts/reset_db.py
--------------------
Script de reinicio de la base de datos de laboratorio.

USO:
    python scripts/reset_db.py [--db-path RUTA]

ADVERTENCIA:
    Este script elimina TODAS las reservas registradas (activas y canceladas)
    y recrea las tablas desde cero.  Esta acción es IRREVERSIBLE.

    Según las reglas del agente (``.agent/rules.md``), cualquier operación
    destructiva sobre la base de datos debe ejecutarse exclusivamente a través
    de este script o con confirmación humana explícita.  El script solicita
    confirmación interactiva antes de proceder.

Después del reinicio:
    - La tabla ``reservas`` queda vacía.
    - La tabla ``unidades`` contiene las 5 unidades del inventario precargado.
    - El contador AUTOINCREMENT de ``reservas`` se reinicia.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Permitir importar desde la raíz del proyecto cuando se ejecuta directamente
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import _DEFAULT_DB, _UNIDADES_INICIALES, get_connection


# ---------------------------------------------------------------------------
# Lógica de reinicio
# ---------------------------------------------------------------------------

def reset_db(db_path: str, *, confirmar: bool = True) -> None:
    """Borra todas las reservas, recrea las tablas y recarga el inventario.

    Args:
        db_path:   Ruta al archivo de base de datos.
        confirmar: Si es ``True`` (predeterminado), solicita confirmación
                   interactiva al usuario antes de proceder.  Pasar ``False``
                   solo en tests automatizados.

    Raises:
        SystemExit: Si el usuario rechaza la confirmación interactiva.
    """
    if confirmar:
        print()
        print("=" * 60)
        print("  ⚠️  ADVERTENCIA: REINICIO DE BASE DE DATOS  ⚠️")
        print("=" * 60)
        print(f"  Base de datos: {db_path}")
        print()
        print("  Esta operación eliminará de forma IRREVERSIBLE:")
        print("    • Todas las reservas activas.")
        print("    • Todo el historial de reservas canceladas.")
        print()
        print("  El inventario de unidades se restaurará automáticamente.")
        print("=" * 60)
        print()
        respuesta = input("  ¿Confirma el reinicio? Escriba 'SI' para continuar: ").strip()
        if respuesta != "SI":
            print()
            print("  Reinicio cancelado. No se realizaron cambios.")
            sys.exit(0)
        print()

    conn = get_connection(db_path)

    with conn:
        # ------------------------------------------------------------------
        # 1. Eliminar tablas existentes (orden inverso por FK)
        # ------------------------------------------------------------------
        conn.execute("DROP TABLE IF EXISTS reservas;")
        conn.execute("DROP TABLE IF EXISTS unidades;")

        # Reiniciar el contador AUTOINCREMENT de reservas
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name = 'reservas';"
        )

        # ------------------------------------------------------------------
        # 2. Recrear tabla de unidades
        # ------------------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE unidades (
                id          TEXT PRIMARY KEY,
                descripcion TEXT NOT NULL
            );
            """
        )

        # ------------------------------------------------------------------
        # 3. Recrear tabla de reservas
        # ------------------------------------------------------------------
        conn.execute(
            """
            CREATE TABLE reservas (
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
        # 4. Precargar inventario
        # ------------------------------------------------------------------
        conn.executemany(
            "INSERT INTO unidades (id, descripcion) VALUES (?, ?);",
            _UNIDADES_INICIALES,
        )

    conn.close()

    # ------------------------------------------------------------------
    # Resultado
    # ------------------------------------------------------------------
    print("=" * 60)
    print("  ✅ BASE DE DATOS REINICIADA EXITOSAMENTE")
    print("=" * 60)
    print(f"  Archivo : {db_path}")
    print("  Reservas: 0 (tabla vacía — historial eliminado)")
    print("  Unidades: 5 (inventario restaurado)")
    print()
    print("  Unidades precargadas:")
    for uid, desc in _UNIDADES_INICIALES:
        print(f"    • {uid} — {desc}")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="reset_db.py",
        description=(
            "Reinicia la base de datos del sistema de reservas de laboratorio. "
            "ADVERTENCIA: elimina todas las reservas registradas de forma irreversible."
        ),
    )
    parser.add_argument(
        "--db-path",
        default=_DEFAULT_DB,
        metavar="RUTA",
        help=(
            f"Ruta al archivo SQLite (predeterminado: {_DEFAULT_DB}). "
            "Usar ':memory:' para pruebas."
        ),
    )
    parser.add_argument(
        "--sin-confirmacion",
        action="store_true",
        default=False,
        help=(
            "Omite la confirmación interactiva. "
            "USO EXCLUSIVO en scripts automatizados o CI."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    reset_db(
        db_path=args.db_path,
        confirmar=not args.sin_confirmacion,
    )
