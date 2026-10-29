"""
app/main.py
-----------
API REST local del sistema de reservas de equipos de laboratorio.

Construida con FastAPI.  La aplicación se conecta a SQLite por medio de una
dependencia inyectable (``get_db``), lo que permite reemplazarla en tests con
una base de datos en memoria sin modificar el código de los endpoints.

Endpoints disponibles:
  GET  /unidades                        → Lista el inventario de 5 unidades.
  GET  /disponibilidad                  → Consulta disponibilidad de una unidad.
  POST /reservas                        → Crea una reserva activa (HTTP 201).
  GET  /reservas                        → Lista todas las reservas (activas + canceladas).
  POST /reservas/{reserva_id}/cancelar  → Cancela una reserva (soft-delete).

Mapeo de errores de dominio a HTTP:
  ValueError (unidad no encontrada, reserva no encontrada) → 404 Not Found
  ValueError (superposición, datos inválidos de negocio)   → 409 Conflict
  ValidationError de Pydantic                              → 422 Unprocessable Entity
"""

import sqlite3
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.database import _DEFAULT_DB, get_connection, init_db
from app.models import DisponibilidadConsulta, ReservaCrear, ReservaRespuesta, Unidad
from app import service

# ---------------------------------------------------------------------------
# Inicialización de la aplicación
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Sistema de Reservas de Laboratorio",
    description=(
        "API local para gestionar reservas de equipos de laboratorio. "
        "Evita superposiciones de horarios y conserva el historial completo "
        "de cancelaciones mediante soft-delete."
    ),
    version="1.1.0",
)

# Asegurarse de que el esquema y el inventario existan al arrancar
init_db(_DEFAULT_DB)


# ---------------------------------------------------------------------------
# Dependencia: conexión a la base de datos
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    """Dependencia FastAPI que abre una conexión SQLite por request y la cierra
    al finalizar, garantizando que no queden conexiones abiertas.

    Puede sobreescribirse en tests mediante ``app.dependency_overrides``.
    """
    conn = get_connection(_DEFAULT_DB)
    try:
        yield conn
    finally:
        conn.close()


DBDep = Annotated[sqlite3.Connection, Depends(get_db)]


# ---------------------------------------------------------------------------
# Helpers para manejo de errores de dominio
# ---------------------------------------------------------------------------

def _not_found(msg: str) -> HTTPException:
    """404 para recursos inexistentes (unidad desconocida, reserva no encontrada)."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)


def _conflict(msg: str) -> HTTPException:
    """409 para violaciones de reglas de negocio (superposición, ya cancelada)."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)


# Fragmentos de mensaje que indican "no encontrado" vs "conflicto"
_NOT_FOUND_HINTS = (
    "no existe",
    "no encontr",
    "inventario",
)


def _classify_value_error(exc: ValueError) -> HTTPException:
    """Clasifica un ``ValueError`` del servicio en 404 o 409.

    Heurística: si el mensaje menciona que algo "no existe" o "no está en el
    inventario" → 404.  Cualquier otro error de regla de negocio → 409.
    """
    msg = str(exc).lower()
    if any(hint in msg for hint in _NOT_FOUND_HINTS):
        return _not_found(str(exc))
    return _conflict(str(exc))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# ── GET /unidades ──────────────────────────────────────────────────────────

@app.get(
    "/unidades",
    response_model=list[Unidad],
    summary="Listar inventario de unidades",
    tags=["Inventario"],
)
def listar_unidades(conn: DBDep) -> list[Unidad]:
    """Devuelve las 5 unidades de equipamiento precargadas en el inventario.

    Returns:
        Lista de unidades con su ID y descripción.
    """
    return service.obtener_inventario(conn)


# ── GET /disponibilidad ────────────────────────────────────────────────────

@app.get(
    "/disponibilidad",
    summary="Consultar disponibilidad de una unidad",
    tags=["Disponibilidad"],
    responses={
        200: {"description": "Consulta exitosa (puede estar disponible u ocupada)."},
        404: {"description": "La unidad no existe en el inventario."},
        422: {"description": "Parámetros de fecha inválidos o inicio >= fin."},
    },
)
def consultar_disponibilidad(
    conn: DBDep,
    unidad_id: str = Query(..., alias="unidad_id", example="MIC-01"),
    inicio: str = Query(..., example="2025-06-15T10:00"),
    fin: str = Query(..., example="2025-06-15T11:00"),
) -> JSONResponse:
    """Verifica si la unidad está disponible en el intervalo ``[inicio, fin)``.

    Aplica exactamente las mismas reglas de negocio que la creación de reservas
    (Adaptación Específica 1 de ``.agent/rules.md``):
    - La unidad debe existir en el inventario.
    - No debe haber superposición con ninguna reserva ACTIVA.
    - ``inicio < fin`` (duración mínima 1 minuto).

    Args:
        unidad_id: Identificador de la unidad (ej. ``MIC-01``).
        inicio:    Inicio del intervalo ISO 8601 ``YYYY-MM-DDTHH:MM``.
        fin:       Fin del intervalo ISO 8601 ``YYYY-MM-DDTHH:MM``.

    Returns:
        JSON con ``disponible: true/false`` y un mensaje descriptivo.
    """
    # Validación de formato e inicio < fin delegada a Pydantic
    try:
        consulta = DisponibilidadConsulta(
            id_unidad=unidad_id, inicio=inicio, fin=fin
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        disponible = service.consultar_disponibilidad(conn, consulta)
    except ValueError as exc:
        raise _classify_value_error(exc) from exc

    if disponible:
        mensaje = (
            f"La unidad '{unidad_id}' está disponible en el intervalo "
            f"[{inicio}, {fin})."
        )
    else:
        mensaje = (
            f"La unidad '{unidad_id}' NO está disponible en el intervalo "
            f"[{inicio}, {fin}): existe al menos una reserva ACTIVA que se superpone."
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"disponible": disponible, "mensaje": mensaje},
    )


# ── POST /reservas ─────────────────────────────────────────────────────────

@app.post(
    "/reservas",
    response_model=ReservaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva reserva",
    tags=["Reservas"],
    responses={
        201: {"description": "Reserva creada exitosamente."},
        404: {"description": "La unidad no existe en el inventario."},
        409: {"description": "Superposición con una reserva existente."},
        422: {"description": "Datos de entrada inválidos (formato, inicio >= fin, solicitante vacío)."},
    },
)
def crear_reserva(datos: ReservaCrear, conn: DBDep) -> ReservaRespuesta:
    """Crea una reserva activa para una unidad en el intervalo especificado.

    Reglas verificadas (en orden):
    1. ``solicitante`` no vacío ni solo espacios (validado por Pydantic).
    2. ``inicio`` y ``fin`` en formato ISO 8601 ``YYYY-MM-DDTHH:MM`` (Pydantic).
    3. ``inicio < fin`` — duración mínima 1 minuto (Pydantic).
    4. La unidad debe existir en el inventario (servicio → 404).
    5. No debe haber superposición con reservas ACTIVAS de la misma unidad
       (Adaptación Específica 1: ``inicio_existente < fin_nueva AND
       fin_existente > inicio_nueva``) (servicio → 409).

    Returns:
        La reserva recién creada con su ID asignado y estado ``ACTIVA``.
    """
    try:
        return service.crear_reserva(conn, datos)
    except ValueError as exc:
        raise _classify_value_error(exc) from exc


# ── GET /reservas ──────────────────────────────────────────────────────────

@app.get(
    "/reservas",
    response_model=list[ReservaRespuesta],
    summary="Listar todas las reservas",
    tags=["Reservas"],
)
def listar_reservas(
    conn: DBDep,
    unidad_id: Optional[str] = Query(
        default=None,
        alias="unidad_id",
        description="Filtra por unidad (ej. MIC-01). Omitir para ver todas.",
        example="MIC-01",
    ),
    solo_activas: bool = Query(
        default=False,
        description="Si es true, devuelve solo reservas con estado ACTIVA.",
    ),
) -> list[ReservaRespuesta]:
    """Lista todas las reservas registradas, incluyendo las CANCELADAS.

    El historial completo se conserva gracias a la política de soft-delete
    (Adaptación Específica 2 de ``.agent/rules.md``): las cancelaciones nunca
    eliminan el registro de la base de datos.

    Args:
        unidad_id:    Filtro opcional por unidad.
        solo_activas: Si ``true``, excluye las reservas canceladas.

    Returns:
        Lista de reservas ordenadas por ``inicio`` ascendente.
    """
    return service.listar_reservas(conn, id_unidad=unidad_id, solo_activas=solo_activas)


# ── POST /reservas/{reserva_id}/cancelar ──────────────────────────────────

@app.post(
    "/reservas/{reserva_id}/cancelar",
    response_model=ReservaRespuesta,
    summary="Cancelar una reserva activa",
    tags=["Reservas"],
    responses={
        200: {"description": "Reserva cancelada exitosamente (estado = CANCELADA)."},
        404: {"description": "La reserva no existe."},
        409: {"description": "La reserva ya estaba cancelada."},
    },
)
def cancelar_reserva(reserva_id: int, conn: DBDep) -> ReservaRespuesta:
    """Cancela una reserva ACTIVA cambiando su estado a ``CANCELADA``.

    IMPORTANTE (Adaptación Específica 2 de ``.agent/rules.md``):
    - Se ejecuta un ``UPDATE`` sobre la columna ``estado``. **Nunca** se
      ejecuta un ``DELETE``.
    - El registro conserva su ``id`` original y todos los datos originales.
    - El intervalo horario queda liberado para futuras reservas activas.

    Args:
        reserva_id: ID numérico de la reserva a cancelar.

    Returns:
        La reserva actualizada con estado ``CANCELADA``.
    """
    try:
        return service.cancelar_reserva(conn, reserva_id)
    except ValueError as exc:
        raise _classify_value_error(exc) from exc
