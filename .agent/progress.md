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
| Fase 2 | Implementación de `app/main.py` (FastAPI) y `scripts/reset_db.py` |
| Fase 3 | Implementación de `tests/test_reservas.py` con casos de prueba |
| Fase 4 | Integración final y validación completa |

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

