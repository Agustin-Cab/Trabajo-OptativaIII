"""
tests/test_reservas.py
-----------------------
Suite de pruebas automatizadas del sistema de reservas de laboratorio.

Estrategia de aislamiento:
  - Cada test recibe un ``TestClient`` configurado con una base de datos SQLite
    en un archivo temporal dentro de ``tmp_path`` (pytest fixture).
  - La dependencia ``get_db`` de FastAPI se sobreescribe via
    ``app.dependency_overrides`` para inyectar esa conexión aislada.
  - Al terminar cada test, pytest elimina ``tmp_path`` automáticamente.
  - El test de persistencia usa deliberadamente un archivo .db en disco
    (dentro de ``tmp_path``) y abre dos instancias de aplicación distintas
    sobre el mismo archivo para verificar la durabilidad de los datos.

Cobertura obligatoria (ver README.md §1.5 y .agent/rules.md):
  1.  Inventario: 5 unidades precargadas.
  2.  Creación válida de reserva.
  3.  Superposición de reservas activas → rechazada.
  4.  Límites consecutivos → permitidos.
  5.  Unidades distintas, mismo horario → permitido.
  6a. Unidad desconocida → rechazada.
  6b. Solicitante vacío → rechazado.
  6c. Solicitante solo espacios → rechazado.
  6d. Fechas con formato inválido → rechazadas.
  6e. inicio == fin → rechazado.
  6f. inicio > fin  → rechazado.
  7.  Cancelación: conserva ID+datos, estado=CANCELADA, libera intervalo.
  8.  Disponibilidad: coherente con las mismas reglas de creación.
  9.  Persistencia en disco: dos instancias independientes sobre el mismo .db.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Importaciones del proyecto
from app.database import get_connection, init_db
from app.main import app, get_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_client(db_path: str) -> TestClient:
    """Crea un ``TestClient`` que usa ``db_path`` como base de datos.

    Sobreescribe la dependencia ``get_db`` de FastAPI para inyectar una
    conexión a la BD de prueba, garantizando aislamiento entre tests.
    """
    init_db(db_path)

    def _get_db_override():
        conn = get_connection(db_path)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _get_db_override
    client = TestClient(app, raise_server_exceptions=True)
    return client


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """Fixture principal: cliente HTTP con BD SQLite temporal aislada."""
    db_path = str(tmp_path / "test_laboratorio.db")
    yield _make_client(db_path)
    # Limpiar override para no contaminar otros tests
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crear_reserva(client: TestClient, id_unidad: str, inicio: str, fin: str,
                   solicitante: str = "Solicitante Test") -> dict:
    """Crea una reserva y devuelve el JSON de respuesta (assert 201 interno)."""
    r = client.post("/reservas", json={
        "id_unidad": id_unidad,
        "solicitante": solicitante,
        "inicio": inicio,
        "fin": fin,
    })
    assert r.status_code == 201, f"Se esperaba 201, got {r.status_code}: {r.text}"
    return r.json()


# ===========================================================================
# 1. Inventario: 5 unidades precargadas
# ===========================================================================

def test_inventario_cinco_unidades(client: TestClient) -> None:
    """GET /unidades devuelve exactamente las 5 unidades del inventario."""
    r = client.get("/unidades")
    assert r.status_code == 200
    unidades = r.json()
    assert len(unidades) == 5

    ids = {u["id"] for u in unidades}
    assert ids == {"MIC-01", "MIC-02", "OSC-01", "MUL-01", "FUE-01"}


def test_inventario_descripciones(client: TestClient) -> None:
    """Cada unidad devuelve los campos 'id' y 'descripcion' no vacíos."""
    r = client.get("/unidades")
    for u in r.json():
        assert u["id"]
        assert u["descripcion"]


# ===========================================================================
# 2. Creación válida de reserva
# ===========================================================================

def test_crear_reserva_valida(client: TestClient) -> None:
    """POST /reservas crea una reserva activa y devuelve HTTP 201 con ID."""
    data = _crear_reserva(client, "MIC-01", "2025-06-15T10:00", "2025-06-15T11:00",
                          "Ana García")
    assert data["id"] > 0
    assert data["id_unidad"] == "MIC-01"
    assert data["solicitante"] == "Ana García"
    assert data["inicio"] == "2025-06-15T10:00"
    assert data["fin"] == "2025-06-15T11:00"
    assert data["estado"] == "ACTIVA"


def test_crear_reserva_id_autoincremental(client: TestClient) -> None:
    """Las reservas sucesivas reciben IDs distintos y crecientes."""
    r1 = _crear_reserva(client, "MIC-01", "2025-01-01T08:00", "2025-01-01T09:00")
    r2 = _crear_reserva(client, "MIC-02", "2025-01-01T08:00", "2025-01-01T09:00")
    assert r2["id"] > r1["id"]


# ===========================================================================
# 3. Rechazo de superposición (misma unidad, reserva activa)
# ===========================================================================

def test_superposicion_exacta_rechazada(client: TestClient) -> None:
    """Reservar el mismo intervalo exacto en la misma unidad → 409."""
    _crear_reserva(client, "MIC-01", "2025-06-15T10:00", "2025-06-15T12:00")
    r = client.post("/reservas", json={
        "id_unidad": "MIC-01", "solicitante": "Luis",
        "inicio": "2025-06-15T10:00", "fin": "2025-06-15T12:00",
    })
    assert r.status_code == 409


def test_superposicion_parcial_inicio_rechazada(client: TestClient) -> None:
    """Reserva que empieza dentro de una activa → 409."""
    _crear_reserva(client, "OSC-01", "2025-06-15T10:00", "2025-06-15T12:00")
    r = client.post("/reservas", json={
        "id_unidad": "OSC-01", "solicitante": "Luis",
        "inicio": "2025-06-15T11:00", "fin": "2025-06-15T13:00",
    })
    assert r.status_code == 409


def test_superposicion_parcial_fin_rechazada(client: TestClient) -> None:
    """Reserva que termina dentro de una activa → 409."""
    _crear_reserva(client, "MUL-01", "2025-06-15T10:00", "2025-06-15T12:00")
    r = client.post("/reservas", json={
        "id_unidad": "MUL-01", "solicitante": "Carlos",
        "inicio": "2025-06-15T09:00", "fin": "2025-06-15T11:00",
    })
    assert r.status_code == 409


def test_superposicion_contenida_rechazada(client: TestClient) -> None:
    """Reserva contenida completamente dentro de una activa → 409."""
    _crear_reserva(client, "FUE-01", "2025-06-15T08:00", "2025-06-15T14:00")
    r = client.post("/reservas", json={
        "id_unidad": "FUE-01", "solicitante": "María",
        "inicio": "2025-06-15T10:00", "fin": "2025-06-15T12:00",
    })
    assert r.status_code == 409


# ===========================================================================
# 4. Límites consecutivos en la misma unidad → permitidos
# ===========================================================================

def test_limite_consecutivo_despues_permitido(client: TestClient) -> None:
    """[10:00,11:00) seguida de [11:00,12:00) en MIC-01 → ambas aceptadas."""
    _crear_reserva(client, "MIC-01", "2025-06-15T10:00", "2025-06-15T11:00")
    data = _crear_reserva(client, "MIC-01", "2025-06-15T11:00", "2025-06-15T12:00")
    assert data["estado"] == "ACTIVA"


def test_limite_consecutivo_antes_permitido(client: TestClient) -> None:
    """[09:00,10:00) anterior a [10:00,11:00) en MIC-01 → ambas aceptadas."""
    _crear_reserva(client, "MIC-01", "2025-06-15T10:00", "2025-06-15T11:00")
    data = _crear_reserva(client, "MIC-01", "2025-06-15T09:00", "2025-06-15T10:00")
    assert data["estado"] == "ACTIVA"


def test_tres_franjas_consecutivas_permitidas(client: TestClient) -> None:
    """Tres reservas consecutivas [08:00,09:00) [09:00,10:00) [10:00,11:00) → todas OK."""
    _crear_reserva(client, "OSC-01", "2025-06-15T08:00", "2025-06-15T09:00")
    _crear_reserva(client, "OSC-01", "2025-06-15T09:00", "2025-06-15T10:00")
    data = _crear_reserva(client, "OSC-01", "2025-06-15T10:00", "2025-06-15T11:00")
    assert data["estado"] == "ACTIVA"


# ===========================================================================
# 5. Unidades distintas, mismo horario → permitido
# ===========================================================================

def test_distintas_unidades_mismo_horario_permitido(client: TestClient) -> None:
    """MIC-01 y MIC-02 pueden reservarse en el mismo intervalo."""
    _crear_reserva(client, "MIC-01", "2025-06-15T10:00", "2025-06-15T11:00")
    data = _crear_reserva(client, "MIC-02", "2025-06-15T10:00", "2025-06-15T11:00")
    assert data["estado"] == "ACTIVA"


def test_todas_unidades_mismo_horario(client: TestClient) -> None:
    """Las 5 unidades pueden reservarse simultáneamente en la misma franja."""
    for uid in ["MIC-01", "MIC-02", "OSC-01", "MUL-01", "FUE-01"]:
        data = _crear_reserva(client, uid, "2025-07-01T09:00", "2025-07-01T10:00",
                              f"Solicitante-{uid}")
        assert data["estado"] == "ACTIVA"


# ===========================================================================
# 6. Rechazo de entradas inválidas
# ===========================================================================

def test_unidad_desconocida_rechazada(client: TestClient) -> None:
    """Unidad 'MIC-99' no existe en el inventario → 404."""
    r = client.post("/reservas", json={
        "id_unidad": "MIC-99", "solicitante": "Ana",
        "inicio": "2025-06-15T10:00", "fin": "2025-06-15T11:00",
    })
    assert r.status_code == 404


def test_solicitante_vacio_rechazado(client: TestClient) -> None:
    """Solicitante vacío '' → 422 Unprocessable Entity."""
    r = client.post("/reservas", json={
        "id_unidad": "MIC-01", "solicitante": "",
        "inicio": "2025-06-15T10:00", "fin": "2025-06-15T11:00",
    })
    assert r.status_code == 422


def test_solicitante_solo_espacios_rechazado(client: TestClient) -> None:
    """Solicitante compuesto únicamente por espacios '   ' → 422."""
    r = client.post("/reservas", json={
        "id_unidad": "MIC-01", "solicitante": "   ",
        "inicio": "2025-06-15T10:00", "fin": "2025-06-15T11:00",
    })
    assert r.status_code == 422


def test_fecha_formato_invalido_rechazada(client: TestClient) -> None:
    """Fechas en formato incorrecto (no ISO 8601 YYYY-MM-DDTHH:MM) → 422."""
    # Formato DD/MM/YYYY HH:MM
    r = client.post("/reservas", json={
        "id_unidad": "MIC-01", "solicitante": "Ana",
        "inicio": "15/06/2025 10:00", "fin": "15/06/2025 11:00",
    })
    assert r.status_code == 422


def test_fecha_solo_dia_rechazada(client: TestClient) -> None:
    """Fecha sin hora → 422."""
    r = client.post("/reservas", json={
        "id_unidad": "MIC-01", "solicitante": "Ana",
        "inicio": "2025-06-15", "fin": "2025-06-16",
    })
    assert r.status_code == 422


def test_inicio_igual_fin_rechazado(client: TestClient) -> None:
    """inicio == fin → duración cero → 422."""
    r = client.post("/reservas", json={
        "id_unidad": "MIC-01", "solicitante": "Ana",
        "inicio": "2025-06-15T10:00", "fin": "2025-06-15T10:00",
    })
    assert r.status_code == 422


def test_inicio_posterior_fin_rechazado(client: TestClient) -> None:
    """inicio > fin → 422."""
    r = client.post("/reservas", json={
        "id_unidad": "MIC-01", "solicitante": "Ana",
        "inicio": "2025-06-15T11:00", "fin": "2025-06-15T10:00",
    })
    assert r.status_code == 422


# ===========================================================================
# 7. Cancelación de reserva
# ===========================================================================

def test_cancelar_reserva_cambia_estado(client: TestClient) -> None:
    """Cancelar una reserva activa → respuesta con estado CANCELADA."""
    creada = _crear_reserva(client, "MIC-01", "2025-08-01T10:00", "2025-08-01T11:00",
                            "Carlos López")
    r = client.post(f"/reservas/{creada['id']}/cancelar")
    assert r.status_code == 200
    cancelada = r.json()
    assert cancelada["estado"] == "CANCELADA"


def test_cancelar_reserva_conserva_id_y_datos(client: TestClient) -> None:
    """La reserva cancelada conserva su ID original y todos sus datos."""
    creada = _crear_reserva(client, "OSC-01", "2025-08-01T14:00", "2025-08-01T16:00",
                            "María Fernández")
    r = client.post(f"/reservas/{creada['id']}/cancelar")
    cancelada = r.json()

    # ID conservado
    assert cancelada["id"] == creada["id"]
    # Datos originales intactos
    assert cancelada["id_unidad"] == creada["id_unidad"]
    assert cancelada["solicitante"] == creada["solicitante"]
    assert cancelada["inicio"] == creada["inicio"]
    assert cancelada["fin"] == creada["fin"]
    # Solo cambió el estado
    assert cancelada["estado"] == "CANCELADA"


def test_cancelar_reserva_aparece_en_historial(client: TestClient) -> None:
    """La reserva cancelada se conserva en GET /reservas (historial completo)."""
    creada = _crear_reserva(client, "MUL-01", "2025-08-01T09:00", "2025-08-01T10:00")
    client.post(f"/reservas/{creada['id']}/cancelar")

    r = client.get("/reservas")
    assert r.status_code == 200
    ids = [rv["id"] for rv in r.json()]
    assert creada["id"] in ids

    # El estado en historial es CANCELADA
    reserva_en_bd = next(rv for rv in r.json() if rv["id"] == creada["id"])
    assert reserva_en_bd["estado"] == "CANCELADA"


def test_cancelar_libera_intervalo(client: TestClient) -> None:
    """Tras cancelar, el mismo intervalo queda libre y puede reservarse."""
    creada = _crear_reserva(client, "FUE-01", "2025-08-01T10:00", "2025-08-01T12:00")
    client.post(f"/reservas/{creada['id']}/cancelar")

    # Mismo intervalo, misma unidad → debe aceptarse ahora
    nueva = _crear_reserva(client, "FUE-01", "2025-08-01T10:00", "2025-08-01T12:00",
                           "Nuevo Solicitante")
    assert nueva["estado"] == "ACTIVA"
    assert nueva["id"] != creada["id"]  # Es una reserva distinta


def test_cancelar_reserva_inexistente(client: TestClient) -> None:
    """Cancelar un ID que no existe → 404."""
    r = client.post("/reservas/99999/cancelar")
    assert r.status_code == 404


def test_cancelar_reserva_ya_cancelada(client: TestClient) -> None:
    """Cancelar una reserva ya cancelada → 409 Conflict."""
    creada = _crear_reserva(client, "MIC-01", "2025-09-01T10:00", "2025-09-01T11:00")
    client.post(f"/reservas/{creada['id']}/cancelar")
    # Segunda cancelación
    r = client.post(f"/reservas/{creada['id']}/cancelar")
    assert r.status_code == 409


# ===========================================================================
# 8. Consulta de disponibilidad
# ===========================================================================

def test_disponibilidad_unidad_libre(client: TestClient) -> None:
    """Unidad sin reservas activas → disponible."""
    r = client.get("/disponibilidad", params={
        "unidad_id": "MIC-01",
        "inicio": "2025-06-15T10:00",
        "fin": "2025-06-15T11:00",
    })
    assert r.status_code == 200
    assert r.json()["disponible"] is True


def test_disponibilidad_con_reserva_activa(client: TestClient) -> None:
    """Unidad con reserva activa superpuesta → no disponible."""
    _crear_reserva(client, "MIC-01", "2025-06-15T10:00", "2025-06-15T12:00")
    r = client.get("/disponibilidad", params={
        "unidad_id": "MIC-01",
        "inicio": "2025-06-15T10:00",
        "fin": "2025-06-15T12:00",
    })
    assert r.status_code == 200
    assert r.json()["disponible"] is False


def test_disponibilidad_turno_consecutivo_libre(client: TestClient) -> None:
    """Franja consecutiva (fin de activa == inicio consultado) → disponible."""
    _crear_reserva(client, "MIC-01", "2025-06-15T10:00", "2025-06-15T11:00")
    r = client.get("/disponibilidad", params={
        "unidad_id": "MIC-01",
        "inicio": "2025-06-15T11:00",
        "fin": "2025-06-15T12:00",
    })
    assert r.status_code == 200
    assert r.json()["disponible"] is True


def test_disponibilidad_tras_cancelar_libre(client: TestClient) -> None:
    """Intervalo previamente ocupado por reserva cancelada → disponible."""
    creada = _crear_reserva(client, "OSC-01", "2025-06-15T09:00", "2025-06-15T10:00")
    client.post(f"/reservas/{creada['id']}/cancelar")

    r = client.get("/disponibilidad", params={
        "unidad_id": "OSC-01",
        "inicio": "2025-06-15T09:00",
        "fin": "2025-06-15T10:00",
    })
    assert r.status_code == 200
    assert r.json()["disponible"] is True


def test_disponibilidad_unidad_desconocida(client: TestClient) -> None:
    """Consultar disponibilidad para unidad inexistente → 404."""
    r = client.get("/disponibilidad", params={
        "unidad_id": "MIC-99",
        "inicio": "2025-06-15T10:00",
        "fin": "2025-06-15T11:00",
    })
    assert r.status_code == 404


def test_disponibilidad_inicio_igual_fin(client: TestClient) -> None:
    """Consulta con inicio == fin → 422."""
    r = client.get("/disponibilidad", params={
        "unidad_id": "MIC-01",
        "inicio": "2025-06-15T10:00",
        "fin": "2025-06-15T10:00",
    })
    assert r.status_code == 422


def test_disponibilidad_y_creacion_coherentes(client: TestClient) -> None:
    """La disponibilidad antes de reservar es True; tras reservar es False."""
    params = {
        "unidad_id": "MUL-01",
        "inicio": "2025-06-15T14:00",
        "fin": "2025-06-15T15:00",
    }
    # Antes de reservar: disponible
    r1 = client.get("/disponibilidad", params=params)
    assert r1.json()["disponible"] is True

    # Crear reserva
    _crear_reserva(client, "MUL-01", "2025-06-15T14:00", "2025-06-15T15:00")

    # Después de reservar: no disponible
    r2 = client.get("/disponibilidad", params=params)
    assert r2.json()["disponible"] is False


# ===========================================================================
# 9. Persistencia en disco: dos instancias sobre el mismo archivo .db
# ===========================================================================

def test_persistencia_en_disco(tmp_path: Path) -> None:
    """Verifica que los datos persisten al abrir una nueva instancia de la app.

    Flujo:
      1. Instancia A: crear una reserva ACTIVA y cancelar otra.
      2. Cerrar el override de la instancia A.
      3. Instancia B: abrir el mismo .db sin borrar datos.
      4. Verificar que ambas reservas existen con sus estados correctos.
    """
    db_path = str(tmp_path / "persistencia.db")

    # ── Instancia A ──────────────────────────────────────────────────────
    client_a = _make_client(db_path)

    # Crear reserva que quedará ACTIVA
    activa = _crear_reserva(client_a, "MIC-01",
                            "2025-10-01T09:00", "2025-10-01T10:00",
                            "Solicitante Activo")
    id_activa = activa["id"]

    # Crear y cancelar una reserva
    a_cancelar = _crear_reserva(client_a, "MIC-02",
                                "2025-10-01T11:00", "2025-10-01T12:00",
                                "Solicitante Cancelado")
    id_cancelada = a_cancelar["id"]
    client_a.post(f"/reservas/{id_cancelada}/cancelar")

    # Limpiar dependencia de instancia A
    app.dependency_overrides.pop(get_db, None)

    # ── Instancia B (nueva instancia, mismo archivo) ──────────────────────
    client_b = _make_client(db_path)

    r = client_b.get("/reservas")
    assert r.status_code == 200
    reservas = {rv["id"]: rv for rv in r.json()}

    # La reserva activa persiste con estado ACTIVA
    assert id_activa in reservas, "La reserva activa no se encontró en instancia B"
    assert reservas[id_activa]["estado"] == "ACTIVA"
    assert reservas[id_activa]["solicitante"] == "Solicitante Activo"
    assert reservas[id_activa]["inicio"] == "2025-10-01T09:00"
    assert reservas[id_activa]["fin"] == "2025-10-01T10:00"

    # La reserva cancelada persiste con estado CANCELADA (historial intacto)
    assert id_cancelada in reservas, "La reserva cancelada no se encontró en instancia B"
    assert reservas[id_cancelada]["estado"] == "CANCELADA"
    assert reservas[id_cancelada]["solicitante"] == "Solicitante Cancelado"
    assert reservas[id_cancelada]["inicio"] == "2025-10-01T11:00"
    assert reservas[id_cancelada]["fin"] == "2025-10-01T12:00"

    app.dependency_overrides.pop(get_db, None)
