# Reglas y Adaptaciones del Agente

## Rol y Stack Tecnológico

- **Lenguaje:** Python 3
- **Persistencia:** SQLite3 estándar (`sqlite3` de la biblioteca estándar)
- **API y validación:** FastAPI + Pydantic
- **Pruebas automatizadas:** `pytest`

## Límites de Alcance

- Sin interfaz gráfica (no GUI, no frontend web servido).
- Sin autenticación ni gestión de usuarios reales.
- Sin dependencias de servicios externos (no APIs de terceros, no red).
- El sistema opera de forma completamente local.

## Permisos y Controles de Escritura

| Ruta | Permiso |
|------|---------|
| `.agent/` | Lectura y escritura |
| `app/` | Lectura y escritura |
| `tests/` | Lectura y escritura |
| `scripts/` | Lectura y escritura |
| Archivos raíz (`requirements.txt`, `.gitignore`, `README.md`, etc.) | Lectura y escritura |

> [!CAUTION]
> Cualquier borrado de base de datos o comando destructivo sobre datos persistidos
> **requiere confirmación humana explícita** o debe ejecutarse exclusivamente a
> través de `scripts/reset_db.py`. El agente NO puede emitir `DROP TABLE` ni
> `DELETE FROM reservas` de forma autónoma sin dicho respaldo.

---

## ADAPTACIÓN ESPECÍFICA 1 — Lógica de Intervalos Semiabiertos

Para validar disponibilidad y detectar superposiciones entre reservas de una
misma unidad se utiliza el modelo de **intervalos semiabiertos** `[inicio, fin)`.

**Condición de superposición:** dos intervalos `[inicio_1, fin_1)` y
`[inicio_2, fin_2)` se superponen **sí y solo sí**:

```
inicio_1 < fin_2  AND  inicio_2 < fin_1
```

**Consecuencia directa:** los límites consecutivos son válidos y **deben
permitirse**. Ejemplos correctos:

- Reserva A: `10:00 → 11:00` + Reserva B: `11:00 → 12:00` en la **misma** unidad → ✅ permitido.
- Reserva A: `10:00 → 11:00` en `MIC-01` + Reserva B: `10:00 → 11:00` en `MIC-02` → ✅ permitido (unidades distintas).
- Reserva A: `10:00 → 12:00` + Reserva B: `11:00 → 13:00` en la **misma** unidad → ❌ rechazado (superposición).

Esta lógica debe aplicarse de forma idéntica tanto en la operación de **crear
reserva** como en la de **consultar disponibilidad**.

---

## ADAPTACIÓN ESPECÍFICA 2 — Persistencia e Historial en SQLite (Soft Delete)

Las cancelaciones de reservas **NUNCA** ejecutan `DELETE` sobre la tabla de
reservas. En su lugar, ejecutan un `UPDATE` que cambia el campo `estado`:

```sql
UPDATE reservas
SET estado = 'CANCELADA'
WHERE id = :id AND estado = 'ACTIVA';
```

**Efectos garantizados:**

- El registro conserva su `id` original y todos los datos originales intactos.
- El intervalo horario queda liberado para futuras reservas activas (la condición
  de superposición solo aplica sobre reservas con `estado = 'ACTIVA'`).
- El historial completo de reservas (activas + canceladas) permanece accesible
  en la base de datos para auditoría.

**Está explícitamente prohibido** emitir `DELETE FROM reservas` para implementar
cancelaciones bajo ninguna circunstancia.

