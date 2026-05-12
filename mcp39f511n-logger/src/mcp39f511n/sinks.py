"""Output sinks: daily-rotating CSV writer and JSON-to-stdout writer."""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, timezone
from pathlib import Path
from typing import TextIO

from .registers import EnergySnapshot, Snapshot

# CSV column order
_SNAPSHOT_FIELDS = [
    "timestamp",
    "system_status",
    "voltage_rms_raw",
    "line_frequency_mhz",
    "power_factor_1",
    "power_factor_2",
    "current_rms_1_raw",
    "current_rms_2_raw",
    "active_power_1_signed",
    "active_power_2_signed",
    "reactive_power_1_signed",
    "reactive_power_2_signed",
    "apparent_power_1_raw",
    "apparent_power_2_raw",
]

_ENERGY_FIELDS = [
    "timestamp",
    "import_energy_active_1",
    "import_energy_active_2",
    "export_energy_active_1",
    "export_energy_active_2",
]


def _dated_path(base_path: str, dt: date) -> Path:
    """Return *base_path* with the date suffix inserted before the extension.

    Example: ``/var/log/power.csv`` → ``/var/log/power_2025-05-12.csv``
    """
    p = Path(base_path)
    return p.with_name(f"{p.stem}_{dt.isoformat()}{p.suffix}")


class CsvSink:
    """Append measurement rows to a daily-rotating CSV file.

    A new file (with a date suffix) is opened on each calendar-day rollover,
    and a header row is written once per file.
    """

    def __init__(self, base_path: str, dry_run: bool = False) -> None:
        self._base_path = base_path
        self._dry_run = dry_run
        self._current_date: date | None = None
        self._fh: TextIO | None = None
        self._writer: csv.DictWriter | None = None  # type: ignore[type-arg]

    def _ensure_open(self, fields: list[str], today: date) -> None:
        """Roll over to a new file if the date has changed."""
        if today != self._current_date:
            if self._fh:
                self._fh.close()
            self._current_date = today
            if not self._dry_run:
                path = _dated_path(self._base_path, today)
                path.parent.mkdir(parents=True, exist_ok=True)
                needs_header = not path.exists()
                self._fh = open(path, "a", newline="")
                self._writer = csv.DictWriter(self._fh, fieldnames=fields)
                if needs_header:
                    self._writer.writeheader()

    def write_snapshot(self, snap: Snapshot) -> None:
        """Append one snapshot row."""
        today = snap.timestamp.astimezone(timezone.utc).date()
        self._ensure_open(_SNAPSHOT_FIELDS, today)
        if self._dry_run or self._writer is None:
            return
        row = {f: getattr(snap, f) for f in _SNAPSHOT_FIELDS}
        row["timestamp"] = snap.timestamp.isoformat()
        self._writer.writerow(row)
        self._fh.flush()  # type: ignore[union-attr]

    def write_energy(self, energy: EnergySnapshot) -> None:
        """Append one energy row."""
        today = energy.timestamp.astimezone(timezone.utc).date()
        path = _dated_path(self._base_path, today)
        if self._dry_run:
            return
        needs_header = not path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_ENERGY_FIELDS)
            if needs_header:
                writer.writeheader()
            row = {f: getattr(energy, f) for f in _ENERGY_FIELDS}
            row["timestamp"] = energy.timestamp.isoformat()
            writer.writerow(row)

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None


class JsonStdoutSink:
    """Write one JSON object per measurement cycle to stdout (for journald ingestion)."""

    def __init__(self, stream: TextIO = sys.stdout) -> None:
        self._stream = stream

    def write_snapshot(self, snap: Snapshot, energy: EnergySnapshot | None = None) -> None:
        """Emit a JSON line for *snap*, optionally including energy data."""
        record: dict[str, object] = {
            "ts": snap.timestamp.isoformat(),
            "voltage_rms_raw": snap.voltage_rms_raw,
            "line_frequency_mhz": snap.line_frequency_mhz,
            "power_factor_1": snap.power_factor_1,
            "power_factor_2": snap.power_factor_2,
            "current_rms_1_raw": snap.current_rms_1_raw,
            "current_rms_2_raw": snap.current_rms_2_raw,
            "active_power_1_signed": snap.active_power_1_signed,
            "active_power_2_signed": snap.active_power_2_signed,
            "reactive_power_1_signed": snap.reactive_power_1_signed,
            "reactive_power_2_signed": snap.reactive_power_2_signed,
            "apparent_power_1_raw": snap.apparent_power_1_raw,
            "apparent_power_2_raw": snap.apparent_power_2_raw,
        }
        if energy is not None:
            record["import_energy_active_1"] = energy.import_energy_active_1
            record["import_energy_active_2"] = energy.import_energy_active_2
            record["export_energy_active_1"] = energy.export_energy_active_1
            record["export_energy_active_2"] = energy.export_energy_active_2

        print(json.dumps(record), file=self._stream, flush=True)
