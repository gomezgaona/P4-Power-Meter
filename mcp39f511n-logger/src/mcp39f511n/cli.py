"""CLI entry point for mcp39f511n-logger."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from types import FrameType

from .config import ConfigError, load_config
from .device import MCP39F511N
from .exceptions import ProtocolError
from .sinks import CsvSink, JsonStdoutSink

logger = logging.getLogger("mcp39f511n")

_DEFAULT_CONFIG = "/etc/mcp39f511n-logger/config.yaml"
_BACKOFF_INITIAL = 1.0
_BACKOFF_MAX = 60.0


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Poll an MCP39F511N power monitor and log readings to CSV."
    )
    p.add_argument(
        "--config",
        metavar="PATH",
        default=_DEFAULT_CONFIG,
        help=f"Path to YAML config file (default: {_DEFAULT_CONFIG})",
    )
    p.add_argument("--once", action="store_true", help="Read once, print to stdout, then exit")
    p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Read measurements but do not write the CSV",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``mcp39f511n-logger`` command."""
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ConfigError) as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)

    csv_sink = CsvSink(cfg.logging.csv_path, dry_run=args.dry_run)
    json_sink = JsonStdoutSink() if cfg.logging.stdout_json else None

    # Clean shutdown on SIGTERM/SIGINT
    _shutdown = False

    def _handle_signal(signum: int, frame: FrameType | None) -> None:
        nonlocal _shutdown
        logger.info("Received signal %d, shutting down …", signum)
        _shutdown = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if args.once:
        _run_once(cfg, csv_sink, json_sink, args.dry_run)
        csv_sink.close()
        return

    _run_loop(cfg, csv_sink, json_sink, lambda: _shutdown)
    csv_sink.close()
    logger.info("mcp39f511n-logger stopped")


def _run_once(cfg, csv_sink, json_sink, dry_run: bool) -> None:
    """Read a single snapshot and print / write it."""
    import json as _json

    with MCP39F511N(cfg.serial.port, cfg.serial.baudrate, cfg.serial.timeout) as dev:
        snap = dev.read_snapshot()
        energy = dev.read_energy() if cfg.polling.include_energy else None

    csv_sink.write_snapshot(snap)
    if energy:
        csv_sink.write_energy(energy)

    # Always print to stdout in --once mode
    record = {
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
    if energy:
        record.update(
            import_energy_active_1=energy.import_energy_active_1,
            import_energy_active_2=energy.import_energy_active_2,
            export_energy_active_1=energy.export_energy_active_1,
            export_energy_active_2=energy.export_energy_active_2,
        )
    print(_json.dumps(record, indent=2))


def _run_loop(cfg, csv_sink, json_sink, shutdown_flag) -> None:
    """Main polling loop with exponential-backoff reconnect on errors."""
    backoff = _BACKOFF_INITIAL
    last_energy_time = 0.0
    dev: MCP39F511N | None = None

    while not shutdown_flag():
        # Open / reopen device
        if dev is None:
            try:
                dev = MCP39F511N(cfg.serial.port, cfg.serial.baudrate, cfg.serial.timeout)
                dev.open()
                logger.info("Connected to %s", cfg.serial.port)
                backoff = _BACKOFF_INITIAL
            except Exception as exc:
                logger.error(
                    "Failed to open %s: %s — retrying in %.0fs", cfg.serial.port, exc, backoff
                )
                _interruptible_sleep(backoff, shutdown_flag)
                backoff = min(backoff * 2, _BACKOFF_MAX)
                dev = None
                continue

        cycle_start = time.monotonic()
        try:
            snap = dev.read_snapshot()

            # Energy on slower cadence
            energy = None
            now = time.monotonic()
            energy_due = (now - last_energy_time) >= cfg.polling.energy_interval_seconds
            if cfg.polling.include_energy and energy_due:
                energy = dev.read_energy()
                last_energy_time = now

            csv_sink.write_snapshot(snap)
            if energy:
                csv_sink.write_energy(energy)

            if json_sink:
                json_sink.write_snapshot(snap, energy)

            logger.debug("Snapshot written at %s", snap.timestamp.isoformat())

        except ProtocolError as exc:
            logger.warning("Protocol error: %s — reconnecting", exc)
            dev.close()
            dev = None
            _interruptible_sleep(backoff, shutdown_flag)
            backoff = min(backoff * 2, _BACKOFF_MAX)
            continue
        except Exception as exc:
            logger.error("Unexpected error: %s — reconnecting", exc)
            try:
                dev.close()
            except Exception:
                pass
            dev = None
            _interruptible_sleep(backoff, shutdown_flag)
            backoff = min(backoff * 2, _BACKOFF_MAX)
            continue

        # Sleep for the remainder of the interval
        elapsed = time.monotonic() - cycle_start
        remaining = cfg.polling.interval_seconds - elapsed
        if remaining > 0:
            _interruptible_sleep(remaining, shutdown_flag)

    if dev is not None:
        dev.close()


def _interruptible_sleep(seconds: float, shutdown_flag) -> None:
    """Sleep in small increments so we respond to the shutdown flag promptly."""
    deadline = time.monotonic() + seconds
    while not shutdown_flag():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.1, remaining))
