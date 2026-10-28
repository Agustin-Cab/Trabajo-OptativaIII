# Sistema Local de Reservas de Equipos de Laboratorio

## 1. Especificación breve — Versión 1.0 Inicial

### 1.1 Problema y Alcance

Los laboratorios comparten equipos físicos entre múltiples usuarios que trabajan
en franjas horarias distintas. Sin un sistema centralizado, se producen dos
problemas recurrentes:

- **Horarios superpuestos:** dos personas reservan el mismo equipo en el mismo
  intervalo sin saberlo.
- **Bloqueos por cancelación:** una reserva cancelada no libera el intervalo,
  impidiendo que otros usuarios lo aprovechen, o se pierde el historial al
  eliminar el registro.

Este proyecto implementa un **sistema local de reservas** que resuelve ambos
problemas sin interfaz gráfica, sin autenticación de usuarios reales y sin
dependencias de servicios externos. Toda la información se persiste en una base
de datos SQLite local.

---

### 1.2 Inventario Precargado Obligatorio

El sistema reconoce exactamente las siguientes unidades de equipamiento. Cualquier
solicitud que referencie un identificador distinto debe ser rechazada.

| ID de Unidad | Descripción            |
|--------------|------------------------|
| `MIC-01`     | Microscopio digital    |
| `MIC-02`     | Microscopio digital    |
| `OSC-01`     | Osciloscopio           |
| `MUL-01`     | Multímetro             |
| `FUE-01`     | Fuente de alimentación |

---

### 1.3 Reglas de Negocio Mínimas

Las siguientes reglas son obligatorias y deben verificarse en cada operación de
reserva y de consulta de disponibilidad:

1. **Unidad conocida:** el `id_unidad` debe existir en el inventario precargado.
   Se rechaza cualquier identificador que no figure en la tabla anterior.

2. **Solicitante válido:** el campo `solicitante` no puede estar vacío ni
   contener únicamente caracteres de espacio en blanco.

3. **Fechas y horas válidas:** `inicio` debe ser estrictamente anterior a `fin`
   (`inicio < fin`). Valores iguales o invertidos son rechazados.

4. **Sin superposición de reservas activas:** para una misma unidad, no puede
   existir una reserva con `estado = 'ACTIVA'` cuyo intervalo se superponga con
   el intervalo solicitado. La condición de superposición entre
   `[inicio_1, fin_1)` e `[inicio_2, fin_2)` es:

   ```
   inicio_1 < fin_2  AND  inicio_2 < fin_1
   ```

5. **Límites consecutivos permitidos:** en la misma unidad, un intervalo que
   termina exactamente donde comienza otro **no** constituye superposición y debe
   ser aceptado (ej. `10:00–11:00` y `11:00–12:00`).

6. **Reservas simultáneas en unidades distintas permitidas:** el mismo intervalo
   horario puede estar reservado en `MIC-01` y en `MIC-02` de forma
   independiente y simultánea.

7. **Cancelación con historial preservado:** cancelar una reserva cambia su
   `estado` de `'ACTIVA'` a `'CANCELADA'` mediante un `UPDATE`. Jamás se
   elimina el registro (`DELETE`). El `id` y todos los datos originales se
   conservan. El intervalo horario queda liberado para nuevas reservas activas.

---

### 1.4 Criterios de Aceptación Verificables

Cada regla de negocio se traduce en uno o más casos de prueba automáticos en
`tests/test_reservas.py`. El sistema se considera correcto cuando **todos** los
siguientes escenarios pasan:

| # | Escenario | Resultado esperado |
|---|-----------|-------------------|
| 1 | Crear reserva con `id_unidad` desconocido | Error / rechazo |
| 2 | Crear reserva con `solicitante` vacío o solo espacios | Error / rechazo |
| 3 | Crear reserva con `inicio >= fin` | Error / rechazo |
| 4 | Crear reserva superpuesta con una activa en la misma unidad | Error / rechazo |
| 5 | Crear reserva con límite consecutivo en la misma unidad (ej. `11:00` = `fin` de la anterior) | ✅ Aceptada |
| 6 | Crear reserva en el mismo horario pero en unidad distinta | ✅ Aceptada |
| 7 | Cancelar una reserva activa | Estado cambia a `CANCELADA`; registro conservado |
| 8 | Crear reserva en un intervalo previamente cancelado | ✅ Aceptada (intervalo liberado) |
| 9 | Consultar disponibilidad aplica las mismas reglas que la creación | Resultado coherente con reglas 1–4 |
