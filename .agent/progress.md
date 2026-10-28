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
| Fase 1 | Implementación de `app/database.py` y `app/models.py` |
| Fase 2 | Implementación de `app/service.py` con lógica de negocio |
| Fase 3 | Implementación de `app/main.py` (FastAPI) y `scripts/reset_db.py` |
| Fase 4 | Implementación de `tests/test_reservas.py` con casos de prueba |
| Fase 5 | Integración final, `requirements.txt` y validación completa |
