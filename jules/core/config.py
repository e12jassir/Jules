from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True, slots=True)
class RoutingTier:
    antigravity: tuple[str, ...] = ()
    opencode: tuple[str, ...] = ()
    provider: str | None = None
    models: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RoutingConfig:
    default_tier: str
    tiers: dict[str, RoutingTier]
    fallback_chain: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    base_url: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class CliProviderConfig:
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    ollama: OllamaConfig
    antigravity: CliProviderConfig
    opencode: CliProviderConfig


@dataclass(frozen=True, slots=True)
class DoctorConfig:
    scoring_variance_threshold: float
    scoring_window_size: int
    inotify_min_watches: int


@dataclass(frozen=True, slots=True)
class PermissionsConfig:
    require_confirmation_packages: bool = True
    require_confirmation_config_writes: bool = True
    prohibited_patterns: tuple[str, ...] = ()
    required_patterns: tuple[str, ...] = ()
    safe_patterns: tuple[str, ...] = ()
    notify_timeout_seconds: float = 120.0


@dataclass(frozen=True, slots=True)
class JulesConfig:
    routing: RoutingConfig
    providers: ProviderConfig
    doctor: DoctorConfig
    permissions: PermissionsConfig


def default_config_paths() -> tuple[Path, ...]:
    return (Path.cwd() / "config.toml", Path.home() / ".jules" / "config.toml")


def load_config(path: Path | str | None = None) -> JulesConfig:
    config_path = _resolve_config_path(path)
    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)
    return _parse_config(raw, config_path)


def _resolve_config_path(path: Path | str | None) -> Path:
    if path is not None:
        config_path = Path(path).expanduser()
        if not config_path.exists():
            raise FileNotFoundError(f"Jules config.toml not found: {config_path}")
        return config_path

    for candidate in default_config_paths():
        if candidate.exists():
            return candidate

    searched = ", ".join(str(candidate) for candidate in default_config_paths())
    raise FileNotFoundError(f"Jules config.toml not found. Searched: {searched}")


def _parse_config(raw: dict[str, object], config_path: Path) -> JulesConfig:
    routing_raw = _require_table(raw, "routing", config_path)
    tiers_raw = _require_table(routing_raw, "tiers", config_path)
    fallback_raw = _optional_table(routing_raw, "fallback")
    providers_raw = _optional_table(raw, "providers")
    doctor_raw = _optional_table(raw, "doctor")
    permissions_raw = _optional_table(raw, "permissions")

    tiers = {
        name: _parse_tier(name, value, config_path)
        for name, value in tiers_raw.items()
    }
    if "free" not in tiers or not tiers["free"].models:
        raise ValueError(f"{config_path}: [routing.tiers.free].models is required")

    default_tier = _require_str(routing_raw, "default_tier", config_path)
    if default_tier not in tiers:
        raise ValueError(f"{config_path}: routing.default_tier '{default_tier}' is not defined")

    fallback_chain = _str_tuple(fallback_raw.get("chain", ["primary", "ollama"]), config_path, "routing.fallback.chain")

    return JulesConfig(
        routing=RoutingConfig(
            default_tier=default_tier,
            tiers=tiers,
            fallback_chain=fallback_chain,
        ),
        providers=_parse_providers(providers_raw),
        doctor=_parse_doctor(doctor_raw, config_path),
        permissions=_parse_permissions(permissions_raw, config_path),
    )


def _parse_permissions(raw: dict[str, object], config_path: Path) -> PermissionsConfig:
    return PermissionsConfig(
        require_confirmation_packages=bool(raw.get("require_confirmation_packages", True)),
        require_confirmation_config_writes=bool(raw.get("require_confirmation_config_writes", True)),
        prohibited_patterns=_str_tuple(raw.get("prohibited_patterns", []), config_path, "permissions.prohibited_patterns"),
        required_patterns=_str_tuple(raw.get("required_patterns", []), config_path, "permissions.required_patterns"),
        safe_patterns=_str_tuple(raw.get("safe_patterns", []), config_path, "permissions.safe_patterns"),
        notify_timeout_seconds=_optional_float(raw.get("notify_timeout_seconds"), 120.0, config_path, "permissions.notify_timeout_seconds"),
    )


def _parse_tier(name: str, raw: object, config_path: Path) -> RoutingTier:
    if not isinstance(raw, dict):
        raise ValueError(f"{config_path}: routing.tiers.{name} must be a table")
    return RoutingTier(
        antigravity=_str_tuple(raw.get("antigravity", []), config_path, f"routing.tiers.{name}.antigravity"),
        opencode=_str_tuple(raw.get("opencode", []), config_path, f"routing.tiers.{name}.opencode"),
        provider=_optional_str(raw.get("provider"), config_path, f"routing.tiers.{name}.provider"),
        models=_str_tuple(raw.get("models", []), config_path, f"routing.tiers.{name}.models"),
    )


def _parse_doctor(raw: dict[str, object], config_path: Path) -> DoctorConfig:
    scoring_variance_threshold = _optional_float(
        raw.get("scoring_variance_threshold"),
        0.01,
        config_path,
        "doctor.scoring_variance_threshold",
    )
    scoring_window_size = _optional_int(
        raw.get("scoring_window_size"),
        10,
        config_path,
        "doctor.scoring_window_size",
    )
    if scoring_variance_threshold < 0:
        raise ValueError(f"{config_path}: doctor.scoring_variance_threshold must be >= 0")
    inotify_min_watches = _optional_int(
        raw.get("inotify_min_watches"),
        65536,
        config_path,
        "doctor.inotify_min_watches",
    )
    if scoring_window_size < 3:
        raise ValueError(f"{config_path}: doctor.scoring_window_size must be >= 3")
    if inotify_min_watches < 1:
        raise ValueError(f"{config_path}: doctor.inotify_min_watches must be >= 1")
    return DoctorConfig(
        scoring_variance_threshold=scoring_variance_threshold,
        scoring_window_size=scoring_window_size,
        inotify_min_watches=inotify_min_watches,
    )


def _parse_providers(raw: dict[str, object]) -> ProviderConfig:
    ollama_raw = _optional_table(raw, "ollama")
    antigravity_raw = _optional_table(raw, "antigravity")
    opencode_raw = _optional_table(raw, "opencode")
    return ProviderConfig(
        ollama=OllamaConfig(
            base_url=_optional_provider_url(ollama_raw.get("base_url")),
            timeout_seconds=_optional_float(ollama_raw.get("timeout_seconds"), 30.0),
        ),
        antigravity=CliProviderConfig(
            timeout_seconds=_optional_float(antigravity_raw.get("timeout_seconds"), 60.0),
        ),
        opencode=CliProviderConfig(
            timeout_seconds=_optional_float(opencode_raw.get("timeout_seconds"), 60.0),
        ),
    )


def _require_table(raw: dict[str, object], key: str, config_path: Path) -> dict[str, object]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{config_path}: [{key}] table is required")
    return value


def _optional_table(raw: dict[str, object], key: str) -> dict[str, object]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a table")
    return value


def _require_str(raw: dict[str, object], key: str, config_path: Path) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{config_path}: {key} must be a non-empty string")
    return value


def _optional_str(value: object, config_path: Path, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{config_path}: {key} must be a non-empty string")
    return value


def _optional_provider_url(value: object) -> str:
    if value is None:
        return "http://localhost:11434"
    if not isinstance(value, str) or not value:
        raise ValueError("providers.ollama.base_url must be a non-empty string")
    return value


def _optional_float(value: object, default: float, config_path: Path | None = None, key: str = "provider timeout_seconds") -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)):
        prefix = f"{config_path}: " if config_path is not None else ""
        raise ValueError(f"{prefix}{key} must be a number")
    return float(value)


def _optional_int(value: object, default: int, config_path: Path, key: str) -> int:
    if value is None:
        return default
    if not isinstance(value, int):
        raise ValueError(f"{config_path}: {key} must be an integer")
    return value


def _str_tuple(value: object, config_path: Path, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{config_path}: {key} must be a list of non-empty strings")
    return tuple(value)
