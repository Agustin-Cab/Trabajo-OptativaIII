"""
app/service.py
--------------
Lógica de dominio del sistema de reservas.

Todas las operaciones reciben una conexión SQLite activa (``conn``) como primer
argumento para facilitar las pruebas: los tests pueden inyectar una base de datos
en memoria (``:memory:``) sin efectos secundarios.

Operaciones disponibles:
  - ``obtener_inventario``: lista todas las unidades.
  - ``consultar_disponibilidad``: verifica si un intervalo está libre.
  - ``crear_reserva``: crea una nueva reserva validando todas las reglas.
  - ``cancelar_reserva``: cambia estado a CANCELADA (nunca DELETE).
  - ``obtener_reserva``: devuelve una reserva por ID.
  - ``listar_reservas``: devuelve todas las reservas, opcionalmente filtradas.

Adaptaciones aplicadas (ver ``.agent/rules.md``):
  - Adaptación 1: superposición = inicio_1 < fin_2 AND inicio_2 < fin_1
                  solo sobre reservas con estado = 'ACTIVA'.
  - Adaptación 2: cancelación vía UPDATE estado = 'CANCELADA', jamás DELETE.
"""

import sqlite3
from typing import Optional

from app.models import DisponibilidadConsulta, ReservaCrear, ReservaRespuesta, Unidad


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _row_to_reserva(row: sqlite3.Row) -> ReservaRespuesta:
    """Convierte una fila SQLite a ``ReservaRespuesta``."""
    return ReservaRespuesta(
        id=row["id"],
        id_unidad=row["id_unidad"],
        solicitante=row["solicitante"],
        inicio=row["inicio"],
        fin=row["fin"],
        estado=row["estado"],
    )


def _unidad_existe(conn: sqlite3.Connection, id_unidad: str) -> bool:
    """Devuelve ``True`` si ``id_unidad`` está en el inventario precargado."""
    cur = conn.execute(
        "SELECT 1 FROM unidades WHERE id = ?;", (id_unidad,)
    )
    return cur.fetchone() is not None


def _hay_superposicion(
    conn: sqlite3.Connection, id_unidad: str, inicio: str, fin: str,
    excluir_id: Optional[int] = None,
) -> bool:
    """Detecta si existe al menos una reserva ACTIVA que se superponga con el
    intervalo ``[inicio, fin)`` para la unidad dada.

    Condición de superposición (Adaptación Específica 1):
        inicio_existente < fin_nueva  AND  fin_existente > inicio_nueva

    Esto garantiza que los límites consecutivos (p. ej. 10:00-11:00 y
    11:00-12:00) sean válidos, ya que en ese caso:
        fin_existente == inicio_nueva  →  NOT (fin_existente > inicio_nueva)
        → NO hay superposición ✅

    Args:
        conn:        Conexión activa a la base de datos.
        id_unidad:   Identificador de la unidad a verificar.
        inicio:      Inicio del nuevo intervalo (ISO 8601 YYYY-MM-DDTHH:MM).
        fin:         Fin del nuevo intervalo (ISO 8601 YYYY-MM-DDTHH:MM).
        excluir_id:  ID de reserva a excluir de la búsqueda (útil para
                     reagendamientos futuros).

    Returns:
        ``True`` si hay superposición; ``False`` en caso contrario.
    """
    sql = """
        SELECT 1
        FROM   reservas
        WHERE  id_unidad = ?
          AND  estado    = 'ACTIVA'
          AND  inicio    < ?
          AND  fin       > ?
    """
    params: list = [id_unidad, fin, inicio]

    if excluir_id is not None:
        sql += " AND id != ?"
        params.append(excluir_id)

    sql += " LIMIT 1;"
    cur = conn.execute(sql, params)
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Operaciones públicas del servicio
# ---------------------------------------------------------------------------

def obtener_inventario(conn: sqlite3.Connection) -> list[Unidad]:
    """Devuelve todas las unidades del inventario precargado.

    Args:
        conn: Conexión activa a la base de datos.

    Returns:
        Lista de ``Unidad``.
    """
    cur = conn.execute("SELECT id, descripcion FROM unidades ORDER BY id;")
    return [Unidad(id=row["id"], descripcion=row["descripcion"]) for row in cur.fetchall()]


def consultar_disponibilidad(
    conn: sqlite3.Connection,
    consulta: DisponibilidadConsulta,
) -> bool:
    """Verifica si la unidad está disponible en el intervalo solicitado.

    Aplica exactamente las mismas reglas que ``crear_reserva`` (Adaptación
    Específica 1: misma lógica en consulta y en creación):
      1. La unidad debe existir en el inventario.
      2. No debe haber superposición con reservas ACTIVAS.

    Args:
        conn:    Conexión activa a la base de datos.
        consulta: Parámetros validados por ``DisponibilidadConsulta``.

    Returns:
        ``True`` si el intervalo está disponible; ``False`` si está ocupado.

    Raises:
        ValueError: Si la unidad no existe en el inventario.
    """
    if not _unidad_existe(conn, consulta.id_unidad):
        raise ValueError(
            f"La unidad '{consulta.id_unidad}' no existe en el inventario. "
            f"Unidades válidas: MIC-01, MIC-02, OSC-01, MUL-01, FUE-01."
        )

    return not _hay_superposicion(conn, consulta.id_unidad, consulta.inicio, consulta.fin)


def crear_reserva(
    conn: sqlite3.Connection,
    datos: ReservaCrear,
) -> ReservaRespuesta:
    """Crea una nueva reserva si todas las reglas de negocio se cumplen.

    Reglas verificadas (en orden):
      1. La unidad existe en el inventario.
      2. No hay superposición con reservas ACTIVAS en la misma unidad
         (Adaptación Específica 1: condición semiabierta).

    Las validaciones de ``solicitante`` e ``inicio < fin`` ya fueron aplicadas
    por el esquema ``ReservaCrear`` (Pydantic).

    Args:
        conn:  Conexión activa a la base de datos.
        datos: Datos validados de la nueva reserva.

    Returns:
        ``ReservaRespuesta`` con el registro creado (incluyendo el ID asignado).

    Raises:
        ValueError: Si la unidad no existe o hay superposición.
    """
    # Regla 1: unidad conocida
    if not _unidad_existe(conn, datos.id_unidad):
        raise ValueError(
            f"La unidad '{datos.id_unidad}' no existe en el inventario. "
            f"Unidades válidas: MIC-01, MIC-02, OSC-01, MUL-01, FUE-01."
        )

    # Regla 2: sin superposición con reservas ACTIVAS (Adaptación 1)
    if _hay_superposicion(conn, datos.id_unidad, datos.inicio, datos.fin):
        raise ValueError(
            f"La unidad '{datos.id_unidad}' ya tiene una reserva ACTIVA que se "
            f"superpone con el intervalo [{datos.inicio}, {datos.fin}). "
            f"Elija otro horario o unidad."
        )

    # Inserción
    with conn:
        cur = conn.execute(
            """
            INSERT INTO reservas (id_unidad, solicitante, inicio, fin, estado)
            VALUES (?, ?, ?, ?, 'ACTIVA');
            """,
            (datos.id_unidad, datos.solicitante, datos.inicio, datos.fin),
        )
        nuevo_id = cur.lastrowid

    # Recuperar el registro recién creado para devolverlo completo
    return obtener_reserva(conn, nuevo_id)


def cancelar_reserva(
    conn: sqlite3.Connection,
    reserva_id: int,
) -> ReservaRespuesta:
    """Cancela una reserva ACTIVA cambiando su estado a 'CANCELADA'.

    IMPORTANTE (Adaptación Específica 2 de rules.md):
      - Se ejecuta un UPDATE, NUNCA un DELETE.
      - El ID y todos los datos originales se conservan en la base de datos.
      - El intervalo horario queda liberado para futuras reservas activas.

    Args:
        conn:       Conexión activa a la base de datos.
        reserva_id: ID de la reserva a cancelar.

    Returns:
        ``ReservaRespuesta`` con el estado actualizado a 'CANCELADA'.

    Raises:
        ValueError: Si la reserva no existe o ya estaba cancelada.
    """
    # Verificar existencia y estado actual
    cur = conn.execute(
        "SELECT estado FROM reservas WHERE id = ?;", (reserva_id,)
    )
    fila = cur.fetchone()

    if fila is None:
        raise ValueError(f"No existe ninguna reserva con ID {reserva_id}.")

    if fila["estado"] == "CANCELADA":
        raise ValueError(
            f"La reserva {reserva_id} ya se encuentra en estado CANCELADA."
        )

    # Soft-delete: UPDATE estado = 'CANCELADA' (Adaptación Específica 2)
    with conn:
        conn.execute(
            """
            UPDATE reservas
            SET    estado = 'CANCELADA'
            WHERE  id     = ? AND estado = 'ACTIVA';
            """,
            (reserva_id,),
        )

    return obtener_reserva(conn, reserva_id)


def obtener_reserva(
    conn: sqlite3.Connection,
    reserva_id: int,
) -> ReservaRespuesta:
    """Devuelve una reserva por su ID.

    Args:
        conn:       Conexión activa a la base de datos.
        reserva_id: ID de la reserva a recuperar.

    Returns:
        ``ReservaRespuesta`` correspondiente.

    Raises:
        ValueError: Si no existe ninguna reserva con ese ID.
    """
    cur = conn.execute(
        "SELECT id, id_unidad, solicitante, inicio, fin, estado "
        "FROM reservas WHERE id = ?;",
        (reserva_id,),
    )
    fila = cur.fetchone()
    if fila is None:
        raise ValueError(f"No existe ninguna reserva con ID {reserva_id}.")
    return _row_to_reserva(fila)


def listar_reservas(
    conn: sqlite3.Connection,
    id_unidad: Optional[str] = None,
    solo_activas: bool = False,
) -> list[ReservaRespuesta]:
    """Lista reservas con filtros opcionales.

    Args:
        conn:        Conexión activa a la base de datos.
        id_unidad:   Si se provee, filtra por esa unidad.
        solo_activas: Si es ``True``, devuelve solo reservas con estado ACTIVA.

    Returns:
        Lista de ``ReservaRespuesta`` ordenada por ``inicio`` ascendente.
    """
    sql = (
        "SELECT id, id_unidad, solicitante, inicio, fin, estado "
        "FROM reservas WHERE 1=1"
    )
    params: list = []

    if id_unidad is not None:
        sql += " AND id_unidad = ?"
        params.append(id_unidad)

    if solo_activas:
        sql += " AND estado = 'ACTIVA'"

    sql += " ORDER BY inicio ASC;"

    cur = conn.execute(sql, params)
    return [_row_to_reserva(fila) for fila in cur.fetchall()]

