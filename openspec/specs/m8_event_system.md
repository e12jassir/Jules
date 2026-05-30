# Spec: Módulo 8 — Sistema de Eventos (Fase 1)
**Clasificación**: SEMI-CRÍTICO
**Asignación de Implementación**: GPT 5.4 (OpenCode)
**Estado**: Listo para implementar

## 1. Objetivo del Módulo
Jules necesita detectar cuándo empiezas a codear, cuándo cambias de proyecto y cuándo terminas la sesión, sin que se lo digas explícitamente. Este módulo provee la plomería para reaccionar a esos estímulos del sistema operativo, limitados estrictamente a 5 eventos básicos (sin eventos cognitivos todavía).

## 2. Restricciones y Decisiones de Arquitectura
- **Shell detectado**: `/usr/bin/zsh`. Los hooks de shell **SOLO** deben enfocarse en Zsh (`precmd` y `preexec` en `~/.zshrc`). No es necesario soportar Bash o Fish en esta iteración.
- **Inotify limits**: Jules debe verificar obligatoriamente `/proc/sys/fs/inotify/max_user_watches` antes de iniciar watchers para no fallar silenciosamente en proyectos grandes.
- **Idempotencia**: La inyección del hook en `.zshrc` debe ser segura y no duplicarse si el installer corre varias veces.
- **EventBus Simple**: Un diccionario simple en memoria (`dict[EventType, list[Callable]]`). Nada complejo.

## 3. Especificación de Componentes

### 3.1. `jules/core/events.py`
Debe definir:
- `EventType` (Enum): `SESSION_STARTED`, `PROJECT_OPENED`, `CODING_DETECTED`, `IDLE_DETECTED`, `SESSION_ENDED`.
- `EventBus` (Clase):
  - `subscribe(event_type: EventType, handler: Callable)`
  - `emit(event_type: EventType, payload: dict)`
- Handlers básicos conectados al `SessionContext`:
  - `SESSION_STARTED` → Valida variables de entorno.
  - `PROJECT_OPENED` → Actualiza el directorio de trabajo activo.
  - `CODING_DETECTED` → Marca timestamp de última actividad.

### 3.2. `jules/linux/watcher.py`
Debe definir:
- Función de chequeo `inotify`: Leer `/proc/sys/fs/inotify/max_user_watches`. Si es menor a `65536`, usar `logger.warning` indicando la orden `echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.d/jules.conf`.
- Un watcher simple que detecte escrituras/modificaciones en archivos y emita el evento `CODING_DETECTED`.

### 3.3. `jules/linux/shell.py`
Debe definir:
- Lógica de detección: leer `os.environ.get("SHELL")`.
- Función `install_zsh_hooks()` que inyecte en `~/.zshrc` el bloque protegido por marcadores:
```zsh
# JULES_ZSH_HOOKS_START
# Hook para capturar finalización de comandos (prompt)
precmd() {
    # TODO: IPC hacia Jules
}
# Hook para capturar comandos tipeados antes de ejecutar
preexec() {
    # TODO: IPC hacia Jules
}
# JULES_ZSH_HOOKS_END
```
- Debe detectar si el marcador `# JULES_ZSH_HOOKS_START` ya existe y hacer bypass.

## 4. Pruebas Unitarias Exigidas (Criterio de Done)
- `tests/unit/test_events.py`: El EventBus debe enrutar correctamente los eventos a los handlers.
- `tests/unit/test_shell.py`: La inyección de hooks debe ser idempotente (llamar a `install_zsh_hooks()` tres veces debe resultar en una sola inyección real en el archivo mock).
- `tests/unit/test_watcher.py`: Mockear la lectura de `/proc/.../max_user_watches` y verificar que el Warning se dispara correctamente.

## 5. Instrucciones para OpenCode (GPT 5.4)
1. Lee este Spec completamente.
2. Implementa los tres archivos (`events.py`, `watcher.py`, `shell.py`).
3. Agrega los tests unitarios exigidos en el punto 4.
4. Asegúrate de ejecutar `pytest` y que no haya regresiones.
5. NO agregues eventos fuera de los 5 definidos en el enum. Cíñete estrictamente al Spec.
