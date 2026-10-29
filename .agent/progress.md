# Registro de Progreso del Proyecto

## Fase 0 — Preparación inicial del repositorio

**Estado:** ✅ Completada  
**Fecha:** 2026-10-28

### Tareas realizadas

1. **Limpieza de carpetas iniciales:** eliminación de las carpetas `Frontend/` y
   `Backend/` (contenían únicamente archivos `test.txt` de marcador vacío) de la
   raíz del repositorio.

2. **Configuración de `.gitignore`:** actualización para un proyecto Python +
   SQLite + Pytest; se ignoraron entornos virtuales, cachés, bases de datos
   locales y archivos de IDE/SO. Se incluye `!.agent/` explícito para asegurar
   que este directorio se versione como evidencia obligatoria.

3. **Definición de reglas del agente (`.agent/rules.md`):** se documentaron el
   rol, el stack, los límites de alcance, los permisos de escritura y las dos
   adaptaciones específicas del proyecto:
   - Adaptación 1: lógica de intervalos semiabiertos `[inicio, fin)` para
     detección de superposiciones.
   - Adaptación 2: soft-delete (cancelación vía `UPDATE estado = 'CANCELADA'`,
     sin `DELETE`) para conservar historial en SQLite.

4. **Especificación Inicial v1.0 (`README.md`):** redacción de la Sección 1 con
   el problema, alcance, inventario precargado obligatorio (5 unidades), reglas
   de negocio mínimas y criterios de aceptación verificables.

### Próximas fases planificadas

| Fase | Descripción |
|------|-------------|
| Fase 4 | Integración final y validación completa |

---

## Episodio de Delegación 3 — Suite de pruebas automatizadas (`tests/test_reservas.py`)

**Estado:** ✅ Completado  
**Fecha:** 2026-10-29  
**Resultado:** `34 passed` en `pytest -v` — sin fallos

### Entorno de ejecución resuelto

El entorno (Python 3.14.4, sin pip global) requirió las siguientes adaptaciones:

1. Creación de entorno virtual `.venv/` con `python3 -m venv`.
2. Instalación de `pip` vía `curl https://bootstrap.pypa.io/get-pip.py`.
3. Pydantic v2 no compila en Python 3.14 (falta toolchain Rust) → se instaló **Pydantic v1 (1.10.26)** + **FastAPI 0.99.1**.
4. `httpx 0.28.1` es incompatible con `starlette 0.27.0` (parámetro `app` removido de `httpx.Client`) → se fijó **httpx 0.23.3**.
5. `app/models.py` fue reescrito de API v2 a **API v1** (`@validator`, `class Config` con `orm_mode`).
6. `requirements.txt` actualizado con las versiones reales instaladas y verificadas.

### Tests implementados (34 en total)

| Grupo | Nº tests | Escenarios cubiertos |
|-------|:---:|---|
| Inventario | 2 | 5 unidades presentes, campos id+descripcion |
| Creación válida | 2 | 201 + campos completos, IDs autoincrementales |
| Superposición | 4 | Exacta, parcial inicio, parcial fin, contenida → 409 |
| Límites consecutivos | 3 | Después, antes, tres franjas consecutivas → 201 |
| Unidades distintas | 2 | Misma franja dos unidades, 5 unidades simultáneas |
| Entradas inválidas | 6 | Unidad 99→404, solicitante vacío→422, solo espacios→422, formato fecha→422, fecha sin hora→422, inicio=fin→422, inicio>fin→422 |
| Cancelación | 6 | Cambia estado, conserva ID+datos, aparece en historial, libera intervalo, ID inexistente→404, doble cancelación→409 |
| Disponibilidad | 7 | Libre, con activa, consecutivo, tras cancelar, unidad inexistente→404, inicio=fin→422, coherencia con creación |
| Persistencia en disco | 1 | Dos instancias de app sobre el mismo `.db`, reserva activa + cancelada recuperadas íntegras |

### Decisiones de implementación

| Decisión | Justificación |
|----------|---------------|
| `tmp_path` de pytest por test | Aislamiento garantizado; pytest limpia automáticamente |
| `app.dependency_overrides[get_db]` | Inyecta BD de test sin modificar código de producción |
| `_make_client(db_path)` helper compartido | Evita duplicación entre fixture y test de persistencia |
| `pop(get_db, None)` al finalizar | Evita contaminación entre tests que comparten el objeto `app` singleton |

---

## Episodio de Delegación 2 — API REST (`app/main.py`) y script de reinicio (`scripts/reset_db.py`)

**Estado:** ✅ Completado  
**Fecha:** 2026-10-28

### Tareas realizadas

1. **`app/main.py`** — API REST con FastAPI, 5 endpoints:

   | Método | Ruta | Descripción |
   |--------|------|-------------|
   | `GET` | `/unidades` | Lista las 5 unidades del inventario |
   | `GET` | `/disponibilidad` | Consulta disponibilidad por query params (`unidad_id`, `inicio`, `fin`) |
   | `POST` | `/reservas` | Crea una reserva activa (HTTP 201); rechaza con 404/409/422 según el error |
   | `GET` | `/reservas` | Lista todas las reservas (activas + canceladas); filtros opcionales `unidad_id` y `solo_activas` |
   | `POST` | `/reservas/{id}/cancelar` | Soft-delete: `UPDATE estado = 'CANCELADA'` (Adaptación 2), nunca DELETE |

2. **`scripts/reset_db.py`** — Script de reinicio destructivo con salvaguardas:
   - Solicita confirmación interactiva escribiendo `SI` exacto antes de proceder.
   - Flag `--sin-confirmacion` para uso en scripts CI/tests automatizados.
   - Flag `--db-path` para apuntar a una BD alternativa.
   - Imprime advertencia explícita antes y resumen detallado después del reinicio.
   - Secuencia: `DROP TABLE reservas` → `DROP TABLE unidades` → `CREATE TABLE` × 2 → `INSERT` inventario.

### Decisiones de implementación destacadas

| Decisión | Justificación |
|----------|---------------|
| Dependencia `get_db` como generador con `yield` | Garantiza `conn.close()` aunque el endpoint lance excepción; permite `dependency_overrides` en tests |
| `_classify_value_error` heurístico | Mapea `ValueError` del servicio a 404 o 409 sin acoplar el servicio a códigos HTTP |
| `GET /disponibilidad` valida con `DisponibilidadConsulta` | Misma lógica de validación que `POST /reservas` (Adaptación 1) |
| `init_db()` llamado al importar `app.main` | La BD y el inventario se garantizan al arrancar; idempotente (no duplica unidades) |
| Confirmación `SI` literal en `reset_db.py` | Evita ejecuciones accidentales; coherente con la regla de "confirmación humana explícita" de `rules.md` |

---

## Episodio de Delegación 1 — Evolución de especificación e implementación de persistencia y dominio

**Estado:** ✅ Completado  
**Fecha:** 2026-10-28

### Tareas realizadas

1. **README.md → Versión 1.1:** se agregó la subsección "1.4 Supuestos y
   Decisiones Técnicas" con tres decisiones fijadas:
   - *Formato de fechas:* ISO 8601 `YYYY-MM-DDTHH:MM`, hora local UTC-3,
     sin conversión de husos horarios.
   - *Fechas pasadas aceptadas:* no se restringe contra el reloj del sistema
     para garantizar pruebas 100 % reproducibles; duración mínima 1 minuto.
   - *Manejo de errores:* `ValueError` en servicio → `422/404` en FastAPI.

2. **`requirements.txt`:** versiones fijadas para `fastapi==0.115.12`,
   `pydantic==2.11.4`, `uvicorn==0.34.2`, `httpx==0.28.1`, `pytest==8.3.5`.

3. **`app/__init__.py`:** archivo de paquete mínimo.

4. **`app/database.py`:** gestión de conexión SQLite con `row_factory`,
   `PRAGMA foreign_keys = ON`, creación idempotente de tablas `unidades` y
   `reservas` (con `CHECK` de estado), y precarga idempotente del inventario
   via `INSERT OR IGNORE`.

5. **`app/models.py`:** esquemas Pydantic v2:
   - `Unidad`: representación del inventario.
   - `ReservaCrear`: entrada; valida `solicitante` no vacío tras `strip()`,
     formato ISO 8601 de fechas e `inicio < fin` en `@model_validator`.
   - `ReservaRespuesta`: salida completa con `Literal["ACTIVA", "CANCELADA"]`.
   - `DisponibilidadConsulta`: entrada de consulta; aplica las mismas
     validaciones de formato e `inicio < fin`.

6. **`app/service.py`:** lógica de dominio con conexión inyectada:
   - `_hay_superposicion`: implementa exactamente `inicio_existente < fin_nueva
     AND fin_existente > inicio_nueva` solo sobre `estado = 'ACTIVA'`
     (Adaptación 1). Límites consecutivos pasan correctamente.
   - `crear_reserva`: verifica unidad + superposición antes de `INSERT`.
   - `cancelar_reserva`: `UPDATE estado = 'CANCELADA'` — jamás `DELETE`
     (Adaptación 2). Devuelve error si ya estaba cancelada o no existe.
   - `consultar_disponibilidad`: aplica las mismas reglas que `crear_reserva`.
   - `obtener_reserva`, `listar_reservas`: consultas de lectura.

### Decisiones de implementación destacadas

| Decisión | Justificación |
|----------|---------------|
| Conexión inyectada como parámetro | Permite tests con `:memory:` sin efectos secundarios |
| Fechas como `TEXT` en SQLite | La comparación lexicográfica de ISO 8601 equivale a la cronológica |
| `INSERT OR IGNORE` en precarga | Idempotencia: `init_db` puede llamarse N veces sin duplicar unidades |
| `CHECK(estado IN ('ACTIVA','CANCELADA'))` | Integridad a nivel de motor de base de datos |
| `strip()` en validador de `solicitante` | Normaliza entradas antes de persistir, rechaza solo-espacios |

