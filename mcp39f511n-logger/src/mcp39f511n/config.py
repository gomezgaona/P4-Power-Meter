"""YAML configuration loader and validator for mcp39f511n-logger."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(ValueError):
    """Raised when the configuration file is missing required keys or has bad values."""


@dataclass
class SerialConfig:
    port: str
    baudrate: int = 115200
    timeout: float = 1.0


@dataclass
class PollingConfig:
    interval_seconds: float = 1.0
    include_energy: bool = True
    energy_interval_seconds: float = 10.0


@dataclass
class LoggingConfig:
    csv_path: str = "/var/log/mcp39f511n/power.csv"
    stdout_json: bool = True


@dataclass
class AppConfig:
    serial: SerialConfig
    polling: PollingConfig = field(default_factory=PollingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _require(mapping: dict, key: str, section: str) -> object:
    if key not in mapping:
        raise ConfigError(f"[{section}] missing required key: '{key}'")
    return mapping[key]


def load_config(path: str | Path) -> AppConfig:
    """Load and validate configuration from a YAML file.

    Args:
        path: Path to the YAML config file.

    Returns:
        Validated :class:`AppConfig` instance.

    Raises:
        ConfigError: On missing required keys or invalid values.
        FileNotFoundError: If the config file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    with p.open() as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ConfigError("Config file must be a YAML mapping at the top level")

    # --- serial section (required) ---
    if "serial" not in raw:
        raise ConfigError("Missing required section: 'serial'")
    s = raw["serial"]
    if not isinstance(s, dict):
        raise ConfigError("[serial] must be a mapping")
    port = str(_require(s, "port", "serial"))

    baudrate = s.get("baudrate", 115200)
    if not isinstance(baudrate, int) or baudrate <= 0:
        raise ConfigError(f"[serial] baudrate must be a positive integer, got: {baudrate!r}")
    if baudrate not in (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200):
        raise ConfigError(f"[serial] baudrate {baudrate} is not a standard MCP39F511N rate")

    timeout = float(s.get("timeout", 1.0))
    if timeout <= 0:
        raise ConfigError(f"[serial] timeout must be > 0, got: {timeout}")

    serial_cfg = SerialConfig(port=port, baudrate=baudrate, timeout=timeout)

    # --- polling section (optional, use defaults) ---
    p_raw = raw.get("polling", {})
    if not isinstance(p_raw, dict):
        raise ConfigError("[polling] must be a mapping")

    interval = float(p_raw.get("interval_seconds", 1.0))
    if interval <= 0:
        raise ConfigError(f"[polling] interval_seconds must be > 0, got: {interval}")

    energy_interval = float(p_raw.get("energy_interval_seconds", 10.0))
    if energy_interval <= 0:
        raise ConfigError(f"[polling] energy_interval_seconds must be > 0, got: {energy_interval}")

    include_energy = bool(p_raw.get("include_energy", True))
    polling_cfg = PollingConfig(
        interval_seconds=interval,
        include_energy=include_energy,
        energy_interval_seconds=energy_interval,
    )

    # --- logging section (optional, use defaults) ---
    l_raw = raw.get("logging", {})
    if not isinstance(l_raw, dict):
        raise ConfigError("[logging] must be a mapping")

    csv_path = str(l_raw.get("csv_path", "/var/log/mcp39f511n/power.csv"))
    stdout_json = bool(l_raw.get("stdout_json", True))
    logging_cfg = LoggingConfig(csv_path=csv_path, stdout_json=stdout_json)

    return AppConfig(serial=serial_cfg, polling=polling_cfg, logging=logging_cfg)
