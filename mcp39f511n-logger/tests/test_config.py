"""Configuration loader tests."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mcp39f511n.config import ConfigError, load_config


def write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_minimal_config(tmp_path):
    cfg_file = write_yaml(
        tmp_path,
        """
        serial:
          port: /dev/ttyUSB0
    """,
    )
    cfg = load_config(cfg_file)
    assert cfg.serial.port == "/dev/ttyUSB0"
    assert cfg.serial.baudrate == 115200
    assert cfg.serial.timeout == 1.0
    assert cfg.polling.interval_seconds == 1.0
    assert cfg.polling.include_energy is True
    assert cfg.polling.energy_interval_seconds == 10.0
    assert cfg.logging.csv_path == "/var/log/mcp39f511n/power.csv"
    assert cfg.logging.stdout_json is True


def test_full_config(tmp_path):
    cfg_file = write_yaml(
        tmp_path,
        """
        serial:
          port: /dev/ttyAMA0
          baudrate: 9600
          timeout: 2.0
        polling:
          interval_seconds: 5.0
          include_energy: false
          energy_interval_seconds: 30.0
        logging:
          csv_path: /tmp/power.csv
          stdout_json: false
    """,
    )
    cfg = load_config(cfg_file)
    assert cfg.serial.port == "/dev/ttyAMA0"
    assert cfg.serial.baudrate == 9600
    assert cfg.serial.timeout == 2.0
    assert cfg.polling.interval_seconds == 5.0
    assert cfg.polling.include_energy is False
    assert cfg.polling.energy_interval_seconds == 30.0
    assert cfg.logging.csv_path == "/tmp/power.csv"
    assert cfg.logging.stdout_json is False


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.yaml")


def test_missing_serial_section_raises(tmp_path):
    cfg_file = write_yaml(tmp_path, "logging:\n  stdout_json: true\n")
    with pytest.raises(ConfigError, match="serial"):
        load_config(cfg_file)


def test_missing_port_raises(tmp_path):
    cfg_file = write_yaml(tmp_path, "serial:\n  baudrate: 115200\n")
    with pytest.raises(ConfigError, match="port"):
        load_config(cfg_file)


def test_invalid_baudrate_raises(tmp_path):
    cfg_file = write_yaml(tmp_path, "serial:\n  port: /dev/ttyUSB0\n  baudrate: 99999\n")
    with pytest.raises(ConfigError, match="baudrate"):
        load_config(cfg_file)


def test_negative_timeout_raises(tmp_path):
    cfg_file = write_yaml(tmp_path, "serial:\n  port: /dev/ttyUSB0\n  timeout: -1\n")
    with pytest.raises(ConfigError, match="timeout"):
        load_config(cfg_file)


def test_negative_interval_raises(tmp_path):
    cfg_file = write_yaml(
        tmp_path,
        """
        serial:
          port: /dev/ttyUSB0
        polling:
          interval_seconds: 0
    """,
    )
    with pytest.raises(ConfigError, match="interval_seconds"):
        load_config(cfg_file)


def test_not_a_mapping_raises(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("- item1\n- item2\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(cfg_file)
