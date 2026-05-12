# mcp39f511n-logger

A production-ready Python logger for the **Microchip MCP39F511N** dual-channel
single-phase power-monitoring IC, connected over UART on Linux.

Reads both channels' instantaneous measurements and energy accumulators, writes
them to daily-rotating CSV files, and optionally emits structured JSON to stdout
(captured by `journald` when run as a systemd service).

---

## Features

- Transport-agnostic protocol layer (fully unit-testable without hardware).
- Typed exceptions for every error the device can produce.
- Daily CSV rotation with a date suffix in the filename.
- JSON-stdout mode for `journald` ingestion.
- SIGTERM / SIGINT clean shutdown.
- Exponential-backoff reconnect on serial errors (1 s → 2 s → … capped at 60 s).
- Idempotent installer + hardened systemd unit.
- CI on Python 3.10, 3.11, 3.12 (ruff + pytest).

---

## Out of Scope

The following features are **not implemented** and are outside this project's
logging focus:

- Calibration UX (gain / offset register writing).
- EEPROM page reads and writes.
- PWM output control.
- Event-pin / surge-detection handling.
- InfluxDB or time-series database sinks.

---

## Quick Start (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Read once (requires hardware):
mcp39f511n-logger --config deploy/config.example.yaml --once

# Run tests (no hardware needed):
pip install pytest
pytest
```

---

## Deployment on a Fresh Debian / Ubuntu VM

### Prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git rsync
```

Python ≥ 3.10 is required. Check with `python3 --version`.

> **Serial access:** The installer creates a dedicated `mcp39f511n` system user
> and adds it to the `dialout` group. If you run the logger as your own user
> during development, add yourself: `sudo usermod -aG dialout $USER` (then log
> out and back in).

### 1 — Clone the repository

```bash
git clone https://github.com/<your-org>/mcp39f511n-logger.git
cd mcp39f511n-logger
```

### 2 — Run the installer

```bash
sudo ./deploy/install.sh
```

The installer is **idempotent** — safe to run multiple times. It will:

- Create system user `mcp39f511n` (no shell, no home) in group `dialout`.
- Sync sources to `/opt/mcp39f511n-logger/`.
- Create a Python venv and install the package.
- Create `/var/log/mcp39f511n/` owned by the service user.
- Install the systemd unit to `/etc/systemd/system/mcp39f511n-logger.service`.
- Copy `config.example.yaml` to `/etc/mcp39f511n-logger/config.yaml` **only if
  the file does not already exist** (so re-running never clobbers your config).
- Run `systemctl daemon-reload`.

### 3 — Edit the configuration

```bash
sudo nano /etc/mcp39f511n-logger/config.yaml
```

At minimum, set `serial.port` to your device (e.g. `/dev/ttyUSB0`).  
Full reference: [`deploy/config.example.yaml`](deploy/config.example.yaml).

### 4 — Enable and start

```bash
sudo systemctl enable --now mcp39f511n-logger
```

### 5 — Verify

```bash
# Live journal output:
journalctl -u mcp39f511n-logger -f

# Inspect the CSV:
ls /var/log/mcp39f511n/
tail -f /var/log/mcp39f511n/power_$(date +%Y-%m-%d).csv
```

---

## Uninstall

```bash
sudo systemctl disable --now mcp39f511n-logger
sudo rm /etc/systemd/system/mcp39f511n-logger.service
sudo systemctl daemon-reload
sudo userdel mcp39f511n
sudo rm -rf /opt/mcp39f511n-logger /etc/mcp39f511n-logger /var/log/mcp39f511n
```

---

## Configuration Reference

```yaml
serial:
  port: /dev/ttyUSB0      # required
  baudrate: 115200         # optional, default 115200
  timeout: 1.0             # optional, default 1.0 s

polling:
  interval_seconds: 1.0         # default 1.0 s
  include_energy: true          # default true
  energy_interval_seconds: 10.0 # default 10.0 s

logging:
  csv_path: /var/log/mcp39f511n/power.csv  # base path; date suffix appended
  stdout_json: true                          # emit JSON line per cycle to stdout
```

---

## CSV Format

### Instantaneous snapshot (`power_YYYY-MM-DD.csv`)

| Column | Description |
|--------|-------------|
| `timestamp` | ISO-8601 UTC timestamp |
| `system_status` | Raw System Status register (u16) |
| `voltage_rms_raw` | Voltage RMS raw register value (u16) |
| `line_frequency_mhz` | Line frequency in mHz (u16; divide by 1000 for Hz) |
| `power_factor_1` | Power factor channel 1 (float, −1.0 … +1.0) |
| `power_factor_2` | Power factor channel 2 |
| `current_rms_1_raw` | Current RMS channel 1 raw (u32) |
| `current_rms_2_raw` | Current RMS channel 2 raw |
| `active_power_1_signed` | Active power ch 1 with sign applied (int) |
| `active_power_2_signed` | Active power ch 2 |
| `reactive_power_1_signed` | Reactive power ch 1 with sign applied |
| `reactive_power_2_signed` | Reactive power ch 2 |
| `apparent_power_1_raw` | Apparent power ch 1 raw (u32) |
| `apparent_power_2_raw` | Apparent power ch 2 raw |

### Energy snapshot (appended to the same daily file)

| Column | Description |
|--------|-------------|
| `timestamp` | ISO-8601 UTC timestamp |
| `import_energy_active_1` | Import energy accumulator ch 1 (u64) |
| `import_energy_active_2` | Import energy accumulator ch 2 |
| `export_energy_active_1` | Export energy accumulator ch 1 |
| `export_energy_active_2` | Export energy accumulator ch 2 |

---

## CLI Reference

```
mcp39f511n-logger [--config PATH] [--once] [--verbose] [--dry-run]

  --config PATH   Path to YAML config (default: /etc/mcp39f511n-logger/config.yaml)
  --once          Read once, print JSON to stdout, exit
  --verbose / -v  Enable debug logging to stderr
  --dry-run       Read measurements but do not write CSV
```

---

## Python API

```python
from mcp39f511n import MCP39F511N

with MCP39F511N("/dev/ttyUSB0") as dev:
    snap = dev.read_snapshot()
    print(snap.voltage_rms_raw, snap.active_power_1_signed)

    energy = dev.read_energy()
    print(energy.import_energy_active_1)

    # Enable energy counting and persist to flash
    dev.enable_energy_accumulation(save_to_flash=True)

    # Verify connectivity
    device_id = dev.ping()  # should return 0x03
```

See [`docs/PROTOCOL.md`](docs/PROTOCOL.md) for the full wire-protocol reference.

---

## Development

```bash
pip install ruff pytest
ruff check src tests        # lint
ruff format src tests       # format
pytest                      # run tests (no hardware required)
```

Tests are in `tests/` and use a `FakeSerial` transport — no USB adapter needed.

---

## License

MIT — see [`LICENSE`](LICENSE).
