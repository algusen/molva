"""Конфигурация демона: дефолты, переопределяемые через env или ~/.molva/config.toml.

Приоритет: env (MOLVA_*) > файл конфига > дефолты.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".molva" / "config.toml"


@dataclass(frozen=True)
class Config:
    host: str = "127.0.0.1"
    port: int = 8765
    backend: str = "stub"
    default_language: str = "ru"
    default_formats: tuple[str, ...] = ("txt",)
    log_dir: Path = Path.home() / "Library" / "Logs" / "Molva"
    notify: bool = True
    clipboard: bool = False
    # Локальный путь к весам GigaAM-v3 (папка проекта models/GigaAM-v3-e2e_rnnt/).
    # None = загрузить из HuggingFace Hub (требует интернет при первом запуске).
    model_path: Path | None = None
    model_revision: str = "e2e_rnnt"


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_formats(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_optional_path(value: str) -> Path | None:
    stripped = value.strip()
    return Path(stripped) if stripped else None


_ENV_PARSERS = {
    "host": str,
    "port": int,
    "backend": str,
    "default_language": str,
    "default_formats": _parse_formats,
    "log_dir": Path,
    "notify": _parse_bool,
    "clipboard": _parse_bool,
    "model_path": _parse_optional_path,
    "model_revision": str,
}


def _load_file_overrides(config_path: Path) -> dict:
    if not config_path.is_file():
        return {}
    with config_path.open("rb") as f:
        data = tomllib.load(f)
    overrides = {}
    for field in fields(Config):
        if field.name in data:
            value = data[field.name]
            if field.name == "default_formats" and isinstance(value, list):
                value = tuple(value)
            elif field.name in ("log_dir",):
                value = Path(value)
            elif field.name == "model_path":
                value = Path(value) if value else None
            overrides[field.name] = value
    return overrides


def _load_env_overrides() -> dict:
    overrides = {}
    for field in fields(Config):
        env_key = f"MOLVA_{field.name.upper()}"
        if env_key in os.environ:
            parser = _ENV_PARSERS[field.name]
            overrides[field.name] = parser(os.environ[env_key])
    return overrides


def load_config(config_path: Path | None = None) -> Config:
    """Собирает конфиг: дефолты -> файл -> env."""
    path = config_path if config_path is not None else DEFAULT_CONFIG_PATH
    values: dict = {}
    values.update(_load_file_overrides(path))
    values.update(_load_env_overrides())
    return Config(**values)
