"""Jules daemon package for background service, IPC, and real-time state."""

from jules.daemon.ipc import (
    IPCClient,
    IPCConnectionError,
    IPCError,
    IPCServer,
    IPCTimeoutError,
    resolve_socket_path,
)
from jules.daemon.service import (
    JulesDaemon,
    install_systemd_user_service,
)
from jules.daemon.state import (
    DEFAULT_STATE_ICONS,
    DaemonState,
    DaemonStateSnapshot,
    StatePublisher,
    resolve_state_path,
)

__all__ = [
    "DEFAULT_STATE_ICONS",
    "DaemonState",
    "DaemonStateSnapshot",
    "IPCClient",
    "IPCConnectionError",
    "IPCError",
    "IPCServer",
    "IPCTimeoutError",
    "JulesDaemon",
    "StatePublisher",
    "install_systemd_user_service",
    "resolve_socket_path",
    "resolve_state_path",
]
