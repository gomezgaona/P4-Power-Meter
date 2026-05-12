"""Typed exceptions for the MCP39F511N protocol layer."""

from __future__ import annotations


class ProtocolError(Exception):
    """Base class for all MCP39F511N protocol errors."""


class NakError(ProtocolError):
    """Device responded with NAK (0x15): command failed or not understood."""


class ChecksumError(ProtocolError):
    """Device responded with CSFAIL (0x51): checksum mismatch."""


class FrameError(ProtocolError):
    """Malformed frame received (unexpected length, truncated, or bad checksum on host side)."""


class DeviceTimeoutError(ProtocolError):
    """No response received within the configured timeout."""
