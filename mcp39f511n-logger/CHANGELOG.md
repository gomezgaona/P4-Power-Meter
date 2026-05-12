# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-05-12

### Added
- Core `mcp39f511n` Python package with `MCP39F511N` device class.
- Transport-agnostic protocol layer (`protocol.py`) with frame builder, checksum, and parser.
- `Snapshot` and `EnergySnapshot` dataclasses with sign-corrected active/reactive power.
- Energy accumulation enable with optional flash-save.
- CLI entry point `mcp39f511n-logger` with YAML config, CSV sink, JSON-stdout sink.
- Daily CSV rotation.
- SIGTERM/SIGINT clean shutdown and exponential-backoff reconnect.
- Systemd unit with security hardening.
- Idempotent `install.sh` for Debian/Ubuntu VMs.
- GitHub Actions CI on Python 3.10, 3.11, 3.12 (ruff + pytest).
