# mcp39f511n-logger

A production-ready Python logger for the **Microchip MCP39F511N** dual-channel
single-phase power-monitoring IC, connected over UART on Linux.

The tool polls both channels of the MCP39F511N every second (configurable),
writes the measurements to a daily-rotating CSV file, and prints structured
JSON to stdout — captured by `journald` when run as a systemd service. No
calibration UI, no database sinks — just reliable, continuous measurement
logging.

---

## Table of Contents

1. [Hardware Setup](#hardware-setup)
2. [Quick Start (development)](#quick-start-development)
3. [Deployment on Debian / Ubuntu](#deployment-on-debian--ubuntu)
4. [Configuration Reference](#configuration-reference)
5. [CLI Reference](#cli-reference)
6. [Understanding the Output](#understanding-the-output)
7. [CSV Format](#csv-format)
8. [Python API](#python-api)
9. [Development](#development)
10. [Out of Scope](#out-of-scope)

---

## Hardware Setup

The MCP39F511N communicates over 8N1 UART at up to 115 200 baud. On a
Linux PC or VM the easiest adapter is the **Microchip MCP2221(a)**
USB-to-UART/I²C bridge (`lsusb` ID `04d8:00dd`), which appears as
`/dev/ttyACM0` (or `/dev/ttyACM1`, `/dev/ttyUSB0`, etc.).

```
MCP39F511N pin 1  (TX)  ──►  MCP2221 RX
MCP39F511N pin 2  (RX)  ◄──  MCP2221 TX
MCP39F511N GND         ──►  MCP2221 GND
```

> **Serial port access:** Add your user to the `dialout` group so you can
> open the port without `sudo`:
> ```bash
> sudo usermod -aG dialout $USER   # log out and back in to take effect
> ```

---

## Quick Start (development)

```bash
git clone https://github.com/<your-org>/mcp39f511n-logger.git
cd mcp39f511n-logger

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Copy the example config and point it at your serial port
cp deploy/config.example.yaml config.yaml
# Edit config.yaml: set serial.port to /dev/ttyACM0 (or whatever lsusb shows)

# Read once and print JSON, then exit (good for a quick sanity check)
mcp39f511n-logger --config config.yaml --once

# Run continuously (Ctrl-C to stop)
mcp39f511n-logger --config config.yaml

# Run tests — no hardware required
pip install pytest
pytest
```

---

## Deployment on Debian / Ubuntu

### Prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git rsync
```

Python ≥ 3.10 is required (`python3 --version`).

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
- Create a Python venv at `/opt/mcp39f511n-logger/.venv` and install the package.
- Create `/var/log/mcp39f511n/` owned by the service user.
- Install the systemd unit to `/etc/systemd/system/mcp39f511n-logger.service`.
- Copy `config.example.yaml` to `/etc/mcp39f511n-logger/config.yaml` **only if
  the file does not already exist** (re-running never clobbers your config).
- Run `systemctl daemon-reload`.

### 3 — Edit the configuration

```bash
sudo nano /etc/mcp39f511n-logger/config.yaml
```

At minimum set `serial.port` to your device. Full reference:
[`deploy/config.example.yaml`](deploy/config.example.yaml).

### 4 — Enable and start

```bash
sudo systemctl enable --now mcp39f511n-logger
```

### 5 — Verify

```bash
# Live journal output (JSON lines):
journalctl -u mcp39f511n-logger -f

# Inspect the CSV:
ls /var/log/mcp39f511n/
tail -f /var/log/mcp39f511n/power_$(date +%Y-%m-%d).csv
```

### Uninstall

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
  port: /dev/ttyUSB0      # required — path to the UART adapter
  baudrate: 115200         # default 115200; must match device setting
  timeout: 1.0             # read timeout in seconds (default 1.0)

polling:
  interval_seconds: 1.0         # how often to poll instantaneous registers
  include_energy: true          # also read energy accumulators
  energy_interval_seconds: 10.0 # how often to read energy (counters change slowly)

logging:
  csv_path: /var/log/mcp39f511n/power.csv  # date suffix appended automatically
  stdout_json: true                          # emit one JSON line per cycle
```

---

## CLI Reference

```
mcp39f511n-logger [--config PATH] [--once] [--verbose] [--dry-run]

  --config PATH   Config file path (default: /etc/mcp39f511n-logger/config.yaml)
  --once          Read one snapshot, print JSON to stdout, then exit
  --verbose / -v  Enable DEBUG logging to stderr
  --dry-run       Read measurements but do not write to the CSV file
```

---

## Understanding the Output

Each poll cycle emits one JSON line to stdout. Here is a real example from
a running system:

```json
{
  "ts": "2026-05-12T17:16:42.050680+00:00",
  "voltage_rms_raw": 1200,
  "line_frequency_mhz": 59976,
  "power_factor_1": 0.63311767578125,
  "power_factor_2": -0.0389404296875,
  "current_rms_1_raw": 3215,
  "current_rms_2_raw": 65,
  "active_power_1_signed": 2442,
  "active_power_2_signed": 3,
  "reactive_power_1_signed": 242,
  "reactive_power_2_signed": 0,
  "apparent_power_1_raw": 3857,
  "apparent_power_2_raw": 77,
  "import_energy_active_1": 0,
  "import_energy_active_2": 0,
  "export_energy_active_1": 0,
  "export_energy_active_2": 0
}
```

### Field-by-field reference

#### Timestamp

| Field | Type | Description |
|-------|------|-------------|
| `ts` | ISO 8601 string | UTC timestamp of the reading. |

#### Voltage and frequency (shared by both channels)

| Field | Type | Description |
|-------|------|-------------|
| `voltage_rms_raw` | u16 | RMS voltage register count. The physical value in volts is `voltage_rms_raw × K_V`, where `K_V` depends on your voltage-divider network and calibration constants stored in the device. With default calibration, `K_V = 0.1`, so `1200 → 120.0 V`. |
| `line_frequency_mhz` | u16 | Line frequency in **milli-hertz** (mHz). Divide by 1000 to get Hz. Example: `59976 / 1000 = 59.976 Hz`. |

#### Power factor (both channels)

| Field | Type | Description |
|-------|------|-------------|
| `power_factor_1` | float | Power factor for channel 1, already converted to the range **−1.0 … +1.0**. Positive = lagging load (inductive). Negative = leading load (capacitive). A value near ±1.0 means almost purely resistive; near 0 means mostly reactive. |
| `power_factor_2` | float | Power factor for channel 2 (same interpretation). |

#### Current (both channels)

| Field | Type | Description |
|-------|------|-------------|
| `current_rms_1_raw` | u32 | RMS current register count for channel 1. Physical value in amperes is `current_rms_1_raw × K_I`, where `K_I` depends on your current transformer or shunt ratio and calibration. With default calibration, `K_I = 0.001`, so `3215 → 3.215 A`. |
| `current_rms_2_raw` | u32 | RMS current for channel 2 (same scaling). |

#### Power (both channels)

Active, reactive, and apparent power all share the same internal scaling; the
relationship **P² + Q² = S²** holds among the raw register values.

| Field | Type | Description |
|-------|------|-------------|
| `active_power_1_signed` | int | Real (active) power for channel 1, **sign already applied** from the System Status register. Negative = energy flowing back to the grid (generation). With default calibration, multiply by `K_P = 0.1` to get watts. Example: `2442 × 0.1 = 244.2 W`. |
| `active_power_2_signed` | int | Active power for channel 2. |
| `reactive_power_1_signed` | int | Reactive power for channel 1, sign applied. Multiply by `K_P` for VAR. Positive = inductive (lagging) load. |
| `reactive_power_2_signed` | int | Reactive power for channel 2. |
| `apparent_power_1_raw` | u32 | Apparent power (VA) for channel 1 — always positive. Multiply by `K_P` for VA. Example: `3857 × 0.1 = 385.7 VA`. Cross-check: `active / apparent = 2442 / 3857 = 0.633`, which matches `power_factor_1`. |
| `apparent_power_2_raw` | u32 | Apparent power for channel 2. |

> **Calibration note:** The `K_V`, `K_I`, and `K_P` factors above are typical
> defaults. Your hardware may differ depending on the voltage divider resistor
> values, current transformer ratio, and any calibration registers you have
> programmed into the device's EEPROM. See the
> [MCP39F511N datasheet](https://www.microchip.com/en-us/product/MCP39F511N)
> (Section 5, "Calibration") for the full calibration procedure.

#### Energy accumulators (both channels)

These fields appear only when `polling.include_energy: true`. They accumulate
continuously from the moment energy counting is enabled; they do **not** reset
between polling cycles.

| Field | Type | Description |
|-------|------|-------------|
| `import_energy_active_1` | u64 | Total active energy imported (consumed) on channel 1 since counting was enabled. Raw register count; apply the same `K_P` and a time factor for Wh. |
| `import_energy_active_2` | u64 | Same for channel 2. |
| `export_energy_active_1` | u64 | Total active energy exported (generated/fed back) on channel 1. |
| `export_energy_active_2` | u64 | Same for channel 2. |

> Energy counting must be enabled once after every power cycle of the
> MCP39F511N. Call `dev.enable_energy_accumulation(save_to_flash=True)` via
> the Python API (or rely on the systemd unit's `ExecStartPre` if configured)
> to persist the setting across resets.

### Reading the example at a glance

Using the sample above (default calibration, `K_V = 0.1`, `K_I = 0.001`,
`K_P = 0.1`):

| Quantity | Calculation | Result |
|----------|------------|--------|
| Line voltage | 1200 × 0.1 | **120.0 V** |
| Line frequency | 59 976 / 1000 | **59.976 Hz** |
| Channel 1 current | 3215 × 0.001 | **3.215 A** |
| Channel 1 apparent power | 3857 × 0.1 | **385.7 VA** |
| Channel 1 active power | 2442 × 0.1 | **244.2 W** |
| Channel 1 power factor | 0.633 | **63.3 % lagging** |
| Channel 2 (lightly loaded) | 65 × 0.001 | **0.065 A**, near idle |

---

## CSV Format

The logger appends to a daily file named `power_YYYY-MM-DD.csv`. The date
suffix is derived from the UTC timestamp, so a single CSV always contains
exactly one calendar day of data.

### Instantaneous snapshot columns

| Column | Description |
|--------|-------------|
| `timestamp` | ISO 8601 UTC timestamp |
| `system_status` | Raw System Status register (u16); bits 0-3 carry the power signs |
| `voltage_rms_raw` | Voltage RMS register (u16) — see scaling above |
| `line_frequency_mhz` | Line frequency in mHz — divide by 1000 for Hz |
| `power_factor_1` | Power factor channel 1 (float, −1.0 … +1.0) |
| `power_factor_2` | Power factor channel 2 |
| `current_rms_1_raw` | Current RMS channel 1 (u32) — see scaling above |
| `current_rms_2_raw` | Current RMS channel 2 |
| `active_power_1_signed` | Active power ch 1, sign applied (int) |
| `active_power_2_signed` | Active power ch 2 |
| `reactive_power_1_signed` | Reactive power ch 1, sign applied |
| `reactive_power_2_signed` | Reactive power ch 2 |
| `apparent_power_1_raw` | Apparent power ch 1 (u32) |
| `apparent_power_2_raw` | Apparent power ch 2 |

### Energy snapshot columns

| Column | Description |
|--------|-------------|
| `timestamp` | ISO 8601 UTC timestamp |
| `import_energy_active_1` | Import energy accumulator ch 1 (u64) |
| `import_energy_active_2` | Import energy accumulator ch 2 |
| `export_energy_active_1` | Export energy accumulator ch 1 |
| `export_energy_active_2` | Export energy accumulator ch 2 |

---

## Python API

```python
from mcp39f511n import MCP39F511N

with MCP39F511N("/dev/ttyACM0") as dev:
    # Verify connectivity — should return 0x03
    device_id = dev.ping()

    # Read instantaneous measurements
    snap = dev.read_snapshot()
    print(f"Voltage raw: {snap.voltage_rms_raw}")
    print(f"Frequency: {snap.line_frequency_mhz / 1000:.3f} Hz")
    print(f"Power factor ch1: {snap.power_factor_1:.4f}")
    print(f"Active power ch1: {snap.active_power_1_signed}")

    # Read energy accumulators (must be enabled first)
    dev.enable_energy_accumulation(save_to_flash=True)
    energy = dev.read_energy()
    print(f"Imported energy ch1: {energy.import_energy_active_1}")
```

See [`docs/PROTOCOL.md`](docs/PROTOCOL.md) for the full wire-protocol reference.

---

## Development

```bash
pip install ruff pytest

ruff check src tests    # lint
ruff format src tests   # format
pytest                  # run all tests (no hardware required)
```

Tests use a `FakeSerial` transport — no USB adapter needed. CI runs on
Python 3.10, 3.11, and 3.12.

---

## Out of Scope

The following features are intentionally not implemented:

- Calibration UX (writing gain/offset registers).
- EEPROM page reads and writes.
- PWM output control.
- Event-pin / surge-detection handling.
- InfluxDB or other time-series database sinks.

---

## License

MIT — see [`LICENSE`](LICENSE).
