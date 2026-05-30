# ESPECIFICACIÓN DE DISEÑO SDD: Robustez Cognitiva y Entorno (Módulos 2, 6, 7)

**Objetivo:** Implementar la "Persistencia Defensiva" (Scoring Health) y la "Detección de Entorno" (Shell) para evitar la degradación de la memoria vectorial de Jules y contextualizar el entorno del usuario, siguiendo estrictamente el `ROADMAP.md` y `JULES.md`.

## REGLAS ESTRICTAS DE IMPLEMENTACIÓN
1. Modifica únicamente lo que se pide.
2. Mantén la Arquitectura Hexagonal intacta (cero acoplamiento).
3. Todo código nuevo debe venir con sus tests unitarios correspondientes (o actualizar los existentes).
4. Escribe código de grado producción (cero soluciones "de juguete").

## ESPECIFICACIONES POR MÓDULO

### 1. Módulo 2: Modelos de Datos (`jules/memory/models.py`)
- Añade el campo `shell: str` al dataclass `SessionContext`.
- Añade la respectiva columna en el ORM (SQLAlchemy) si este modelo se persiste directamente.
- Genera y aplica la migración de Alembic correspondiente para este cambio.

### 2. Configuración (`config.toml` y parser de config `jules/core/config.py`)
- Añade una nueva sección `[doctor]` en `config.toml`.
- Define los valores por defecto: 
  ```toml
  [doctor]
  scoring_variance_threshold = 0.01
  scoring_window_size = 10
  ```
- Asegúrate de que el parser de configuración lea estos valores y los valide.

### 3. Módulo 6A: Monitor de Salud (`jules/memory/scoring.py`)
- Crea una clase `ScoringHealthMonitor`.
- **Responsabilidad:** Mantener en memoria RAM (ej. usando `collections.deque` con un `maxlen=scoring_window_size`) los últimos N scores de Llama.
- **Método `record(score: float)`:** Añade el nuevo score al historial.
- **Método `is_healthy() -> bool`:** Si hay suficientes datos (>= 3), calcula la varianza matemática (puedes usar `statistics.variance`). Devuelve `True` si la varianza es mayor a `scoring_variance_threshold`, de lo contrario `False` (lo que indica que el modelo está degenerado devolviendo puntajes constantes). Si hay menos de 3 datos, asume `True` temporalmente.

### 4. Módulo 6B: Motor de Memoria (`jules/memory/engine.py`)
- Modifica la lógica de persistencia (típicamente `persist_async` o similar).
- **Flujo requerido:**
  1. Extraer o calcular el importance score del episodio.
  2. Registrar el score en el monitor: `monitor.record(score)`.
  3. Si `is_healthy() == True` y `score >= 0.3`: Persistir en LanceDB y SQLite normalmente.
  4. Si `is_healthy() == False` (Modelo Degenerado): Entrar en **Modo Conservador**.
     - **REGLA CONSERVADORA:** Solo guardar en la base de datos si el episodio tiene `friction_score > 0.5` O si tiene tags que indican un proyecto activo.
     - Loggear de forma estructurada un warning: `logger.warning("Scoring degenerado, modo conservador activado")`.

### 5. Módulo 7: Detector de Contexto (`jules/core/context.py`)
- En la función que construye (build) el `SessionContext`, inyecta el entorno físico al instanciar.
- Utiliza `os.environ.get("SHELL", "unknown")` para poblar el campo `shell` del contexto. No lo hardcodees ni lo infieras de otra fuente.
