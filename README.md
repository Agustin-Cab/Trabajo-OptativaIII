# Sistema Local de Reservas de Equipos de Laboratorio

---

## 1. Especificación breve

### 1.1 Problema y alcance

Los laboratorios comparten equipos físicos entre múltiples usuarios que trabajan
en franjas horarias distintas. Sin un sistema centralizado, se producen dos
problemas recurrentes:

- **Horarios superpuestos:** dos personas reservan el mismo equipo en el mismo
  intervalo sin saberlo.
- **Bloqueos por cancelación:** una reserva cancelada no libera el intervalo,
  impidiendo que otros usuarios lo aprovechen, o se pierde el historial al
  eliminar el registro.

Este proyecto implementa un **sistema local de reservas** que resuelve ambos
problemas. Opera completamente en local, sin interfaz gráfica, sin autenticación
de usuarios reales y sin dependencias de servicios externos. Toda la información
se persiste en una base de datos SQLite.

**Fuera de alcance:** autenticación, roles, interfaz web, notificaciones,
integración con calendarios externos, soporte multi-laboratorio.

---

### 1.2 Inventario precargado obligatorio

El sistema reconoce exactamente las siguientes unidades. Cualquier solicitud
que referencie un identificador distinto es rechazada con HTTP 404.

| ID de unidad | Descripción            |
|:------------:|------------------------|
| `MIC-01`     | Microscopio digital    |
| `MIC-02`     | Microscopio digital    |
| `OSC-01`     | Osciloscopio           |
| `MUL-01`     | Multímetro             |
| `FUE-01`     | Fuente de alimentación |

---

### 1.3 Supuestos y decisiones de especificación

> **Versión 1.0** establecida en commit `d0a8dbc` · **Versión 1.1** en commit
> `1e147aa` (motivo: fijar zona horaria, formato de fechas y política de fechas
> pasadas para garantizar reproducibilidad de pruebas automáticas).

#### Formato de fechas

Los campos `inicio` y `fin` se representan en **ISO 8601** con resolución de
minuto: `YYYY-MM-DDTHH:MM`. Se asume la **hora local del laboratorio (UTC-3)**
sin conversión de husos horarios. El sistema almacena y compara las cadenas tal
como las recibe.

**Ejemplo válido:** `"2025-06-15T10:00"` y `"2025-06-15T11:30"`.

#### Fechas pasadas y duración

- Se aceptan **cualesquiera fechas válidas**, incluyendo fechas en el pasado,
  siempre que se cumpla `inicio < fin`. No se restringe respecto al reloj del
  sistema. Esta decisión garantiza que las pruebas automáticas sean **100 %
  reproducibles y deterministas** en el futuro.
- **Duración mínima:** 1 minuto (consecuencia directa de `inicio < fin` con
  granularidad de 1 minuto).
- **Sin límite máximo** de anticipación.

#### Manejo de errores

El servicio eleva `ValueError` con mensajes descriptivos. La capa FastAPI los
traduce a HTTP: `422` para datos inválidos (formato, `inicio ≥ fin`,
solicitante vacío), `404` para recursos inexistentes, `409` para conflictos de
negocio (superposición, reserva ya cancelada).

---

### 1.4 Reglas de negocio mínimas

Las siguientes reglas se verifican en cada operación de reserva y consulta:

1. **Unidad conocida:** `id_unidad` debe existir en el inventario precargado.
2. **Solicitante válido:** `solicitante` no puede estar vacío ni contener solo
   espacios en blanco (se aplica `.strip()` antes de validar y persistir).
3. **Fechas válidas:** `inicio` y `fin` deben ser cadenas `YYYY-MM-DDTHH:MM`
   parseables; `inicio` debe ser estrictamente anterior a `fin`.
4. **Sin superposición de reservas activas:** para una misma unidad, no puede
   existir una reserva `ACTIVA` cuyo intervalo se superponga con el solicitado.
   La condición de superposición entre `[inicio_1, fin_1)` e `[inicio_2, fin_2)` es:

   ```
   inicio_1 < fin_2  AND  inicio_2 < fin_1
   ```

5. **Límites consecutivos permitidos:** en la misma unidad, un intervalo que
   termina exactamente donde comienza otro **no** constituye superposición
   (ej. `10:00–11:00` y `11:00–12:00` → ambos válidos).
6. **Reservas simultáneas en unidades distintas permitidas:** el mismo horario
   puede estar ocupado en `MIC-01` y `MIC-02` de forma independiente.
7. **Cancelación con historial preservado:** cancelar cambia `estado` de
   `'ACTIVA'` a `'CANCELADA'` mediante `UPDATE`. Nunca se ejecuta `DELETE`.
   El registro conserva su `id` y todos sus datos originales; el intervalo
   queda libre para nuevas reservas activas.
8. **Consulta de disponibilidad:** aplica exactamente las mismas reglas que la
   creación (misma función de detección de superposición).

---

### 1.5 Criterios de aceptación verificables

Cada regla se traduce en uno o más casos de prueba en `tests/test_reservas.py`.
**Resultado real:** `34 passed` · `pytest-9.2.0` · `Python 3.14.4`.

| # | Escenario | Resultado esperado | Test |
|:-:|-----------|:------------------:|------|
| 1 | Inventario tiene exactamente 5 unidades con IDs y descripciones | ✅ 200 | `test_inventario_cinco_unidades`, `test_inventario_descripciones` |
| 2 | Crear reserva válida → HTTP 201 con ID, datos y estado `ACTIVA` | ✅ 201 | `test_crear_reserva_valida` |
| 3 | Superposición exacta, parcial o contenida en misma unidad | ❌ 409 | `test_superposicion_*` (4 tests) |
| 4 | Límite consecutivo `[10:00,11:00)` + `[11:00,12:00)` misma unidad | ✅ 201 | `test_limite_consecutivo_*` (3 tests) |
| 5 | Mismo horario en unidades distintas (`MIC-01` y `MIC-02`) | ✅ 201 | `test_distintas_unidades_mismo_horario_permitido` |
| 6 | Unidad `MIC-99` desconocida | ❌ 404 | `test_unidad_desconocida_rechazada` |
| 7 | Solicitante `""` o `"   "` | ❌ 422 | `test_solicitante_vacio_rechazado`, `test_solicitante_solo_espacios_rechazado` |
| 8 | Fecha con formato incorrecto o sin hora | ❌ 422 | `test_fecha_formato_invalido_rechazada`, `test_fecha_solo_dia_rechazada` |
| 9 | `inicio == fin` e `inicio > fin` | ❌ 422 | `test_inicio_igual_fin_rechazado`, `test_inicio_posterior_fin_rechazado` |
| 10 | Cancelar reserva → `CANCELADA`, ID y datos conservados, en historial | ✅ 200 | `test_cancelar_reserva_cambia_estado`, `test_cancelar_reserva_conserva_id_y_datos`, `test_cancelar_reserva_aparece_en_historial` |
| 11 | Intervalo cancelado queda libre para nueva reserva | ✅ 201 | `test_cancelar_libera_intervalo` |
| 12 | Cancelar ID inexistente → 404; doble cancelación → 409 | ❌ 404/409 | `test_cancelar_reserva_inexistente`, `test_cancelar_reserva_ya_cancelada` |
| 13 | Disponibilidad: libre, ocupada, consecutiva, tras cancelar | ✅/❌ 200 | `test_disponibilidad_*` (5 tests) |
| 14 | Disponibilidad coherente con creación (antes→libre, después→ocupado) | ✅ 200 | `test_disponibilidad_y_creacion_coherentes` |
| 15 | Persistencia en disco: dos instancias sobre el mismo `.db` | ✅ | `test_persistencia_en_disco` |

---

## 2. Solución

### 2.1 Estructura del repositorio

```
Trabajo-OptativaIII/
├── .agent/
│   ├── rules.md          # Reglas, stack, límites y adaptaciones específicas del agente
│   └── progress.md       # Registro versionado de progreso por episodio
├── app/
│   ├── __init__.py       # Paquete Python
│   ├── database.py       # Conexión SQLite, creación de tablas y precarga de inventario
│   ├── models.py         # Esquemas Pydantic v1 (validación de entradas y salidas)
│   ├── service.py        # Lógica de dominio (inventario, disponibilidad, reservar, cancelar)
│   └── main.py           # API REST FastAPI (5 endpoints)
├── scripts/
│   └── reset_db.py       # Script de reinicio de BD (destructivo, requiere confirmación)
├── tests/
│   └── test_reservas.py  # Suite de 34 tests con pytest + TestClient
├── .gitignore
├── README.md
└── requirements.txt
```

Los datos persisten en **`laboratorio.db`** (archivo SQLite en la raíz del
proyecto), creado automáticamente al arrancar la aplicación.

---

### 2.2 Stack y versiones

| Componente | Versión | Rol |
|------------|:-------:|-----|
| Python | 3.14.4 | Lenguaje base |
| FastAPI | 0.99.1 | Framework API REST |
| Pydantic | 1.10.26 | Validación de esquemas |
| sqlite3 | stdlib | Persistencia (sin dependencia externa) |
| uvicorn | 0.34.2 | Servidor ASGI para correr la app |
| pytest | 9.2.0 | Pruebas automatizadas |
| httpx | 0.23.3 | Cliente HTTP para TestClient |

> **Nota:** Pydantic v2 no compila en Python 3.14 (requiere toolchain Rust para
> `pydantic-core`). Se usa la última versión estable de la rama v1.

---

### 2.3 Instalación

```bash
# 1. Clonar el repositorio
git clone <URL-del-repositorio>
cd Trabajo-OptativaIII

# 2. Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 3. Instalar dependencias
pip install -r requirements.txt
```

---

### 2.4 Levantar la aplicación

```bash
# La BD y el inventario se crean automáticamente en el primer arranque
uvicorn app.main:app --reload
```

La API queda disponible en `http://127.0.0.1:8000`.
Documentación interactiva: `http://127.0.0.1:8000/docs`.

---

### 2.5 Endpoints disponibles

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/unidades` | Lista las 5 unidades del inventario |
| `GET` | `/disponibilidad?unidad_id=&inicio=&fin=` | Consulta disponibilidad |
| `POST` | `/reservas` | Crea una reserva activa (HTTP 201) |
| `GET` | `/reservas` | Lista todas las reservas (activas + canceladas) |
| `POST` | `/reservas/{id}/cancelar` | Cancela una reserva (soft-delete) |

#### Ejemplo: crear una reserva

```bash
curl -X POST http://127.0.0.1:8000/reservas \
     -H "Content-Type: application/json" \
     -d '{"id_unidad":"MIC-01","solicitante":"Ana García","inicio":"2025-06-15T10:00","fin":"2025-06-15T11:00"}'
```

Respuesta exitosa (HTTP 201):

```json
{
  "id": 1,
  "id_unidad": "MIC-01",
  "solicitante": "Ana García",
  "inicio": "2025-06-15T10:00",
  "fin": "2025-06-15T11:00",
  "estado": "ACTIVA"
}
```

#### Ejemplo: consultar disponibilidad

```bash
curl "http://127.0.0.1:8000/disponibilidad?unidad_id=MIC-01&inicio=2025-06-15T10:00&fin=2025-06-15T11:00"
```

Respuesta (disponible):

```json
{"disponible": true, "mensaje": "La unidad 'MIC-01' está disponible en el intervalo [2025-06-15T10:00, 2025-06-15T11:00)."}
```

#### Ejemplo: cancelar una reserva

```bash
curl -X POST http://127.0.0.1:8000/reservas/1/cancelar
```

Respuesta (HTTP 200):

```json
{
  "id": 1,
  "id_unidad": "MIC-01",
  "solicitante": "Ana García",
  "inicio": "2025-06-15T10:00",
  "fin": "2025-06-15T11:00",
  "estado": "CANCELADA"
}
```

---

### 2.6 Persistencia — verificación de durabilidad

El archivo `laboratorio.db` conserva los datos entre reinicios del servidor.
Procedimiento reproducible:

```bash
# Paso 1: Iniciar la app y crear una reserva
uvicorn app.main:app &
curl -X POST http://127.0.0.1:8000/reservas \
     -H "Content-Type: application/json" \
     -d '{"id_unidad":"OSC-01","solicitante":"Carlos","inicio":"2025-09-01T09:00","fin":"2025-09-01T10:00"}'
# → Se devuelve {"id": 1, ..., "estado": "ACTIVA"}

# Paso 2: Detener el servidor
kill %1

# Paso 3: Reiniciar el servidor
uvicorn app.main:app &

# Paso 4: Verificar que la reserva persiste
curl http://127.0.0.1:8000/reservas
# → El JSON incluye la reserva con id=1 y estado="ACTIVA"
```

---

### 2.7 Reinicio de la base de datos

> ⚠️ **ADVERTENCIA:** `scripts/reset_db.py` **elimina de forma irreversible
> todas las reservas registradas** (activas y canceladas). El inventario de
> unidades se restaura automáticamente.

```bash
# Con confirmación interactiva (escribe 'SI' para confirmar)
python scripts/reset_db.py

# Sin confirmación (solo para CI/scripts automatizados)
python scripts/reset_db.py --sin-confirmacion

# Sobre una BD alternativa
python scripts/reset_db.py --db-path ruta/alternativa.db
```

---

### 2.8 Ejecución de pruebas

```bash
# Activar entorno virtual si no está activo
source .venv/bin/activate

# Correr la suite completa
pytest -v

# Resultado esperado:
# 34 passed, 104 warnings in 0.47s
```

Los tests son **100 % aislados**: cada uno usa una BD SQLite temporal en
`tmp_path` (gestionada por pytest) y no toca `laboratorio.db`.

---

### 2.9 Pendientes y limitaciones

- Sin autenticación ni control de acceso por usuario.
- Sin interfaz gráfica ni frontend web.
- `uvicorn` sirve una instancia single-worker; no se ha evaluado concurrencia.
- No hay migraciones de esquema: si se modifica la estructura de tablas se
  debe ejecutar `reset_db.py` o migrar manualmente.
- Pydantic v2 no está soportado en Python 3.14 hasta que se publique un wheel
  binario oficial.

---

## 3. Preparación del agente

### 3.1 Entorno de trabajo

- **Herramienta:** Antigravity Desktop (IDE con agente IA integrado).
- **Modelo:** Claude Sonnet 4.6 (Thinking). Se eligió este modelo por su buena
  relación calidad/consumo de tokens: genera código estructurado y documentado
  con menor tasa de errores de lógica que modelos más ligeros, sin el costo
  de tokens de modelos de mayor tamaño, lo que lo hace adecuado para sesiones
  largas de delegación con múltiples archivos.

### 3.2 Archivos de configuración del agente

| Archivo | Propósito |
|---------|-----------|
| [`.agent/rules.md`](.agent/rules.md) | Define rol, stack, límites de alcance, permisos de escritura y las 2 adaptaciones específicas del proyecto |
| [`.agent/progress.md`](.agent/progress.md) | Registro versionado de progreso: qué se hizo en cada episodio, decisiones tomadas y fases pendientes |

### 3.3 Contexto suministrado al agente

En cada episodio se proporcionó explícitamente:

- Lectura de `.agent/rules.md` (instrucciones persistentes): rol, stack,
  límites, permisos y las 2 adaptaciones.
- Lectura del estado actual del `README.md` y los archivos relevantes del
  episodio anterior.
- Instrucción detallada con los archivos a crear/modificar, las reglas a
  respetar y el resultado esperado.

**Excluido del contexto:** credenciales, rutas absolutas del sistema del
usuario, historial de sesiones anteriores (cada episodio comenzó leyendo los
archivos en disco).

### 3.4 Herramientas permitidas al agente

- Lectura y escritura de archivos en `.agent/`, `app/`, `tests/`, `scripts/`
  y raíz del proyecto.
- Ejecución de comandos en sandbox (sin red): `python3`, `git`, `find`, `grep`.
- Ejecución de comandos con red (requirió aprobación explícita del usuario):
  `curl` para descargar `pip` y las dependencias desde PyPI.
- **Prohibido sin confirmación humana:** `git commit`, borrar la base de datos,
  `DROP TABLE`, `DELETE FROM reservas`.

### 3.5 Controles humanos antes de cada commit

Antes de cada `git commit` el usuario:

1. Revisó los archivos generados abiertos en el IDE.
2. Verificó la salida de los comandos de prueba ejecutados por el agente.
3. Aprobó o corrigió el mensaje del commit (en el Episodio 1 el usuario
   rechazó el mensaje propuesto y proporcionó el definitivo).
4. Autorizó explícitamente el comando `git commit` con `BypassSandbox: true`
   (el sandbox del agente tiene sistema de archivos de solo lectura para git).

### 3.6 Aplicación de las adaptaciones específicas

#### Adaptación 1 — Intervalos semiabiertos `[inicio, fin)`

Definida en `.agent/rules.md` §Adaptación 1. Implementada en
[`app/service.py`](app/service.py) en la función `_hay_superposicion`:

```sql
SELECT 1 FROM reservas
WHERE  id_unidad = ?
  AND  estado    = 'ACTIVA'
  AND  inicio    < ?       -- inicio_existente < fin_nueva
  AND  fin       > ?       -- fin_existente    > inicio_nueva
LIMIT 1;
```

Esta condición **no** detecta límites consecutivos como superposición: si
`fin_existente = inicio_nueva` la segunda condición `fin > inicio_nueva` es
falsa (usa `>` estricto, no `>=`), por lo que la consulta no retorna filas y
la nueva reserva se acepta.

#### Adaptación 2 — Soft-delete (cancelación sin `DELETE`)

Definida en `.agent/rules.md` §Adaptación 2. Implementada en
[`app/service.py`](app/service.py) en `cancelar_reserva`:

```sql
UPDATE reservas
SET    estado = 'CANCELADA'
WHERE  id     = ? AND estado = 'ACTIVA';
```

El registro conserva su `id`, `id_unidad`, `solicitante`, `inicio` y `fin`
originales. Como la condición de superposición filtra solo `estado = 'ACTIVA'`,
el intervalo queda disponible para futuras reservas. El historial completo es
accesible desde `GET /reservas`.

---

## 4. Registro de decisiones y delegación

### 4.1 Decisiones técnicas significativas

| Decisión | Alternativa evaluada | Motivo de la elección | Consecuencia |
|----------|---------------------|-----------------------|--------------|
| **SQLite + `sqlite3` stdlib** | JSON plano en disco | SQLite garantiza atomicidad en escrituras concurrentes, soporte nativo de `CHECK` y FK, y comparación lexicográfica de ISO 8601 equivalente a cronológica | Sin dependencia externa; el archivo `.db` es el único artefacto de datos |
| **FastAPI** | CLI (argparse) o Flask | FastAPI genera documentación interactiva automática (`/docs`), valida con Pydantic y permite `TestClient` para pruebas de integración sin servidor real | Requiere `uvicorn` para ejecutar; agrega complejidad vs. CLI pura |
| **Pydantic v1** | Pydantic v2 | `pydantic-core` (v2) no tiene wheel para Python 3.14 y falla al compilar desde fuente (requiere Rust) | Los decoradores son `@validator` en lugar de `@field_validator`; la funcionalidad de validación es idéntica |
| **Fechas como `TEXT` en SQLite** | Columna `DATETIME` | La comparación lexicográfica de `YYYY-MM-DDTHH:MM` es equivalente a la cronológica; simplifica las consultas SQL | No hay parsing de fechas en SQL; toda la validación de formato ocurre en Pydantic |
| **Conexión inyectada como parámetro** | Singleton global de conexión | Permite que los tests inyecten `:memory:` o `tmp_path/*.db` mediante `dependency_overrides` sin modificar código de producción | Cada request abre y cierra su propia conexión |
| **`INSERT OR IGNORE` en precarga** | `DELETE` + `INSERT` | Garantiza idempotencia: `init_db()` puede llamarse N veces sin duplicar unidades ni borrar reservas existentes | El inventario no puede modificarse en tiempo de ejecución (diseño intencional) |

---

### 4.2 Episodios de delegación

---

#### Episodio 1 — Evolución de la especificación, persistencia SQLite y lógica de dominio

**Commit:** `1e147aa` — `feat(core): implementar sqlite, modelos, servicio y evolucionar spec a v1.1`

**Objetivo:** Evolucionar la especificación a v1.1 fijando supuestos técnicos, e implementar la capa de datos y dominio (`database.py`, `models.py`, `service.py`, `requirements.txt`).

**Contexto suministrado:**
- Instrucción explícita de leer `.agent/rules.md` y `README.md` antes de escribir código.
- Listado de los 7 archivos a crear/modificar con sus responsabilidades exactas.
- Énfasis en las 2 adaptaciones específicas y en la inyección de conexión para testabilidad.

**Extracto de instrucción clave:**
> *"Crea `app/service.py` aplicando estrictamente las Adaptaciones Específicas 1 y 2 de `.agent/rules.md`."*

**Acción del agente:**
- Actualizó `README.md` a v1.1 (nueva §1.4 Supuestos).
- Creó `requirements.txt` con versiones fijadas.
- Implementó `database.py` con `init_db` idempotente y `get_connection` con `row_factory`.
- Implementó `models.py` en Pydantic v2 con `@field_validator` y `@model_validator`.
- Implementó `service.py` con `_hay_superposicion` (SQL con `inicio < fin_nueva AND fin > inicio_nueva AND estado='ACTIVA'`), `crear_reserva`, `cancelar_reserva` (solo `UPDATE`), `consultar_disponibilidad`.
- Ejecutó 16 verificaciones de lógica pura con `sqlite3` nativo (sin Pydantic) → 16/16 ✅.

**Decisión humana:** ✅ Aceptado con corrección de mensaje de commit.
El usuario rechazó el mensaje de commit propuesto por el agente y proporcionó el definitivo: `"feat(core): implementar sqlite, modelos, servicio y evolucionar spec a v1.1"`.

**Archivos afectados:**
[`app/database.py`](app/database.py) · [`app/models.py`](app/models.py) · [`app/service.py`](app/service.py) · [`README.md`](README.md) · [`requirements.txt`](requirements.txt)

---

#### Episodio 2 — API REST FastAPI y script de reinicio

**Commit:** `774de68` — `feat(api): implementar app/main.py (FastAPI) y scripts/reset_db.py`

**Objetivo:** Exponer la lógica de dominio como API REST local con 5 endpoints, y proveer un script de reinicio seguro de la base de datos.

**Contexto suministrado:**
- Lectura previa de `app/models.py`, `app/service.py` y `app/database.py`.
- Especificación de los 5 endpoints con sus métodos, códigos HTTP y semántica de error.
- Requisito explícito de confirmación interactiva en `reset_db.py`.

**Extracto de instrucción clave:**
> *"`POST /reservas/{reserva_id}/cancelar`: Cambia el estado de la reserva a `CANCELADA` conservando su ID y sus datos, y liberando el intervalo."*

**Acción del agente:**
- Implementó `app/main.py` con dependencia `get_db` como generador con `yield` (garantiza `conn.close()`), función `_classify_value_error` para mapear `ValueError` a 404/409 sin acoplar el servicio a HTTP, e `init_db()` al importar el módulo.
- Implementó `scripts/reset_db.py` con confirmación `SI` literal, flag `--sin-confirmacion`, flag `--db-path`, advertencia explícita y resumen de resultado.
- Verificó sintaxis de los 5 archivos con `ast.parse` → 5/5 ✅.
- Verificó lógica de reset con SQLite en memoria → tablas recreadas, 0 reservas, 5 unidades ✅.
- Verificó que `service.py` no contiene `DELETE FROM reservas` → ✅.

**Decisión humana:** ✅ Aceptado íntegramente. No hubo correcciones sobre el código generado.

**Archivos afectados:**
[`app/main.py`](app/main.py) · [`scripts/reset_db.py`](scripts/reset_db.py) · [`.agent/progress.md`](.agent/progress.md)

---

#### Episodio 3 — Suite de pruebas automatizadas y resolución de entorno

**Commit:** `fd1eccf` — `feat(tests): suite de pruebas completa (34/34), adaptar models a Pydantic v1 y fijar versiones`

**Objetivo:** Implementar 34 tests con pytest + TestClient cubriendo todos los criterios de aceptación, y lograr que pasen completamente en el entorno real.

**Contexto suministrado:**
- Descripción de los 15 escenarios obligatorios a cubrir.
- Requisito de aislamiento con `tmp_path` y `dependency_overrides`.
- Test de persistencia como caso especial: dos instancias de app sobre el mismo `.db`.

**Extracto de instrucción clave:**
> *"Persistencia tras reinicio: crear una reserva activa y otra cancelada sobre un archivo `.db` en disco, cerrar la conexión/instancia de la aplicación, abrir una nueva conexión/instancia sobre ese mismo archivo `.db` sin borrar datos, y comprobar que ambas reservas se recuperan intactas."*

**Acción del agente — resolución de incompatibilidades de entorno:**

El agente no asumió que el entorno funcionaría: detectó y resolvió tres problemas encadenados:

1. **Sin `pip` global:** instaló pip con `curl https://bootstrap.pypa.io/get-pip.py | python3`.
2. **Pydantic v2 no compila en Python 3.14** (`pydantic-core` requiere Rust): detectó el error de compilación, instaló Pydantic v1.10.26 + FastAPI 0.99.1, y reescribió `app/models.py` de API v2 a API v1 (`@validator`, `class Config: orm_mode`).
3. **`httpx 0.28.1` incompatible con `starlette 0.27.0`** (`Client.__init__()` no acepta parámetro `app`): diagnosticó inspeccionando `inspect.signature(TestClient.__init__)`, instaló `httpx 0.23.3`.

Primera ejecución de pytest: 33 ERRORS + 1 FAILED.
Tras resolver incompatibilidades: **34 PASSED** ✅.

**Decisión humana:** ✅ Aceptado íntegramente. El agente resolvió el entorno de forma autónoma con diagnóstico incremental; el usuario aprobó cada instalación con red (BypassSandbox).

**Archivos afectados:**
[`tests/test_reservas.py`](tests/test_reservas.py) · [`app/models.py`](app/models.py) · [`requirements.txt`](requirements.txt) · [`.agent/progress.md`](.agent/progress.md)

---

### 4.3 Verificaciones ejecutadas por el humano

El siguiente cuadro registra las verificaciones que el **humano ejecutó
independientemente** para contrastar lo informado por el agente.

| Verificación | Comando ejecutado | Resultado observado |
|---|---|---|
| Estructura final del repositorio | `find . -not -path './.git/*' \| sort` | 11 archivos + `.venv/` (ignorada por git) ✅ |
| Estado del repositorio antes del commit inicial | `git status` | 4 archivos nuevos, 2 borrados (Frontend/Backend) ✅ |
| Historial de commits | `git log --oneline` | 4 commits propios sobre base de 4 commits previos del repositorio ✅ |
| Versiones instaladas | `.venv/bin/python3 -m pip show fastapi pydantic pytest` | fastapi 0.99.1 · pydantic 1.10.26 · pytest 9.2.0 ✅ |
| Validación de modelos | `python3 -c "from app.models import ReservaCrear; ..."` | solicitante vacío → `ValidationError`, inicio≥fin → `ValidationError` ✅ |
| Lógica SQL de superposición | Script `sqlite3` en memoria, 16 casos | 16/16 ✅ |
| Sintaxis de archivos generados | `python3 -c "import ast; ast.parse(...)"` × 5 | 5/5 sin errores de sintaxis ✅ |
| Suite de pruebas completa | `.venv/bin/python3 -m pytest tests/test_reservas.py -v` | `34 passed, 104 warnings in 0.47s` ✅ |
| Ausencia de `DELETE FROM reservas` en servicio | `grep "DELETE FROM reservas" app/service.py` | Sin resultados (no existe) ✅ |
| Presencia de `UPDATE estado = 'CANCELADA'` | `grep "CANCELADA" app/service.py` | Línea encontrada en `cancelar_reserva` ✅ |
