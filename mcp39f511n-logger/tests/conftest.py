"""Shared test fixtures."""

from __future__ import annotations

import io

import pytest


class FakeSerial:
    """Minimal fake transport backed by a scripted byte buffer.

    Usage::

        fs = FakeSerial(response_bytes)
        data = fs.read(4)
        # Check what was written:
        written = fs.written
    """

    def __init__(self, response: bytes = b"") -> None:
        self._in = io.BytesIO(response)
        self._out = io.BytesIO()

    def read(self, n: int) -> bytes:
        return self._in.read(n)

    def write(self, data: bytes) -> None:
        self._out.write(data)

    @property
    def written(self) -> bytes:
        return self._out.getvalue()

    def set_response(self, response: bytes) -> None:
        self._in = io.BytesIO(response)
        self._out = io.BytesIO()


def make_ack_response(data: bytes) -> bytes:
    """Build a well-formed ACK response frame for *data*.

    Structure: ACK | num_bytes | data... | checksum
    num_bytes = 1 (ACK) + 1 (len byte) + len(data) + 1 (checksum) = len(data) + 3
    """
    from mcp39f511n.protocol import ACK, _checksum

    num_bytes = len(data) + 3
    frame = bytes([ACK, num_bytes]) + data
    return frame + bytes([_checksum(frame)])


@pytest.fixture
def fake_serial() -> FakeSerial:
    return FakeSerial()
