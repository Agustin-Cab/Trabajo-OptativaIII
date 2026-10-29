"""
app/models.py
-------------
Esquemas Pydantic v2 para validación de entradas y serialización de salidas.

Validaciones de dominio aplicadas en este módulo:
  - ``solicitante``: no vacío ni compuesto solo por espacios (se aplica strip).
  - ``inicio`` y ``fin``: cadenas ISO 8601 parseables como ``datetime``.
  - ``inicio < fin``: la duración mínima es 1 minuto.

Las reglas de negocio que requieren consultar la base de datos (unidad conocida,
superposición de reservas) se validan en ``app/service.py``.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Formato ISO 8601 aceptado por el sistema (resolución de minuto)
_FMT = "%Y-%m-%dT%H:%M"


def _parse_dt(value: str) -> datetime:
    """Parsea una cadena ISO 8601 ``YYYY-MM-DDTHH:MM`` a ``datetime``.

    Raises:
        ValueError: Si el formato no coincide.
    """
    try:
        return datetime.strptime(value, _FMT)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Formato de fecha inválido: '{value}'. "
            f"Se esperaba YYYY-MM-DDTHH:MM (ej. 2025-06-15T10:00)."
        ) from exc


# ---------------------------------------------------------------------------
# Esquema de Unidad
# ---------------------------------------------------------------------------

class Unidad(BaseModel):
    """Representa una unidad de equipamiento del inventario."""

    id: str = Field(..., examples=["MIC-01"])
    descripcion: str = Field(..., examples=["Microscopio digital"])

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquema de creación de Reserva (entrada)
# ---------------------------------------------------------------------------

class ReservaCrear(BaseModel):
    """Datos requeridos para solicitar una nueva reserva.

    Validaciones aplicadas:
    - ``id_unidad``: no vacío.
    - ``solicitante``: no vacío ni solo espacios en blanco.
    - ``inicio`` y ``fin``: ISO 8601 parseables.
    - ``inicio < fin`` (duración mínima 1 minuto).
    """

    id_unidad: str = Field(..., examples=["MIC-01"])
    solicitante: str = Field(..., examples=["Ana García"])
    inicio: str = Field(..., examples=["2025-06-15T10:00"])
    fin: str = Field(..., examples=["2025-06-15T11:00"])

    # -----------------------------------------------------------------------
    # Validadores de campo individuales
    # -----------------------------------------------------------------------

    @field_validator("solicitante", mode="before")
    @classmethod
    def solicitante_no_vacio(cls, v: str) -> str:
        """Rechaza solicitantes vacíos o compuestos solo por espacios."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError(
                "El campo 'solicitante' no puede estar vacío ni contener "
                "únicamente espacios en blanco."
            )
        return v.strip()

    @field_validator("inicio", "fin", mode="before")
    @classmethod
    def fecha_formato_valido(cls, v: str) -> str:
        """Verifica que la cadena sea parseable como ISO 8601 YYYY-MM-DDTHH:MM."""
        _parse_dt(v)  # lanza ValueError si falla
        return v

    # -----------------------------------------------------------------------
    # Validador cruzado: inicio < fin
    # -----------------------------------------------------------------------

    @model_validator(mode="after")
    def inicio_estrictamente_anterior_a_fin(self) -> "ReservaCrear":
        """Garantiza que ``inicio`` sea estrictamente anterior a ``fin``."""
        dt_inicio = _parse_dt(self.inicio)
        dt_fin = _parse_dt(self.fin)
        if dt_inicio >= dt_fin:
            raise ValueError(
                f"'inicio' ({self.inicio}) debe ser estrictamente anterior a "
                f"'fin' ({self.fin}). La duración mínima es 1 minuto."
            )
        return self

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquema de respuesta de Reserva (salida)
# ---------------------------------------------------------------------------

class ReservaRespuesta(BaseModel):
    """Representación completa de una reserva devuelta por el sistema."""

    id: int
    id_unidad: str
    solicitante: str
    inicio: str
    fin: str
    estado: Literal["ACTIVA", "CANCELADA"]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Esquema de consulta de disponibilidad (entrada)
# ---------------------------------------------------------------------------

class DisponibilidadConsulta(BaseModel):
    """Parámetros para consultar si una unidad está disponible en un intervalo.

    Aplica las mismas validaciones de formato e ``inicio < fin`` que
    ``ReservaCrear`` (Adaptación Específica 1: misma lógica en consulta
    y en creación).
    """

    id_unidad: str = Field(..., examples=["MIC-01"])
    inicio: str = Field(..., examples=["2025-06-15T10:00"])
    fin: str = Field(..., examples=["2025-06-15T11:00"])

    @field_validator("inicio", "fin", mode="before")
    @classmethod
    def fecha_formato_valido(cls, v: str) -> str:
        _parse_dt(v)
        return v

    @model_validator(mode="after")
    def inicio_estrictamente_anterior_a_fin(self) -> "DisponibilidadConsulta":
        dt_inicio = _parse_dt(self.inicio)
        dt_fin = _parse_dt(self.fin)
        if dt_inicio >= dt_fin:
            raise ValueError(
                f"'inicio' ({self.inicio}) debe ser estrictamente anterior a "
                f"'fin' ({self.fin})."
            )
        return self

    model_config = {"from_attributes": True}

