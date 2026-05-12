"""Transport-agnostic MCP39F511N frame builder, checksum, and parser.

Accepts any object with `.read(n: int) -> bytes` and `.write(data: bytes)`
so it can be used with real pyserial ports or test fakes without modification.
"""

from __future__ import annotations

from typing import Protocol

from .exceptions import ChecksumError, DeviceTimeoutError, FrameError, NakError

# ---------------------------------------------------------------------------
# Wire constants
# ---------------------------------------------------------------------------

HEADER = 0xA5
ACK = 0x06
NAK = 0x15
CSFAIL = 0x51
MAX_FRAME = 35

CMD_SET_ADDRESS = 0x41
CMD_READ_N = 0x4E
CMD_WRITE_N = 0x4D
CMD_SAVE_FLASH = 0x53


# ---------------------------------------------------------------------------
# Transport protocol
# ---------------------------------------------------------------------------


class Transport(Protocol):
    """Minimal interface required by the protocol layer."""

    def read(self, n: int) -> bytes: ...

    def write(self, data: bytes) -> None: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _checksum(data: bytes | list[int]) -> int:
    """Return sum(data) & 0xFF."""
    return sum(data) & 0xFF


def build_frame(*command_packets: bytes) -> bytes:
    """Build a complete request frame from one or more raw command packets.

    The frame structure is:
        0xA5 | num_bytes | command_packet(s)... | checksum

    ``num_bytes`` is the total length of the frame including the header,
    the length byte itself, all command bytes, and the checksum byte.
    """
    payload = b"".join(command_packets)
    # header + length byte + payload + checksum = len(payload) + 3
    num_bytes = len(payload) + 3
    if num_bytes > MAX_FRAME:
        raise FrameError(f"Frame too large: {num_bytes} bytes (max {MAX_FRAME})")
    prefix = bytes([HEADER, num_bytes]) + payload
    return prefix + bytes([_checksum(prefix)])


def build_read_frame(address: int, n_bytes: int) -> bytes:
    """Build a frame that sets the address pointer then reads N bytes."""
    addr_hi = (address >> 8) & 0xFF
    addr_lo = address & 0xFF
    set_addr = bytes([CMD_SET_ADDRESS, addr_hi, addr_lo])
    read_cmd = bytes([CMD_READ_N, n_bytes])
    return build_frame(set_addr, read_cmd)


def build_write_frame(address: int, data: bytes) -> bytes:
    """Build a frame that sets the address pointer then writes N data bytes."""
    addr_hi = (address >> 8) & 0xFF
    addr_lo = address & 0xFF
    set_addr = bytes([CMD_SET_ADDRESS, addr_hi, addr_lo])
    write_cmd = bytes([CMD_WRITE_N, len(data)]) + data
    return build_frame(set_addr, write_cmd)


def build_save_flash_frame() -> bytes:
    """Build a frame that saves registers to flash (CMD_SAVE_FLASH = 0x53)."""
    return build_frame(bytes([CMD_SAVE_FLASH]))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def read_response(transport: Transport, expected_data_bytes: int | None = None) -> bytes:
    """Read and validate one response frame from the transport.

    Returns the raw data bytes (excluding ACK, length byte, and checksum).

    Raises:
        NakError: device responded with 0x15.
        ChecksumError: device responded with 0x51.
        FrameError: unexpected first byte or frame shorter than advertised.
        DeviceTimeoutError: transport returned fewer bytes than expected (timeout).
    """
    first = transport.read(1)
    if not first:
        raise DeviceTimeoutError("No response from device")

    code = first[0]
    if code == NAK:
        raise NakError("Device returned NAK (0x15)")
    if code == CSFAIL:
        raise ChecksumError("Device returned CSFAIL (0x51): checksum mismatch")
    if code != ACK:
        raise FrameError(f"Unexpected response byte: 0x{code:02X}")

    # Write commands receive a bare ACK with no following frame bytes
    if expected_data_bytes == 0:
        return b""

    # Second byte is num_bytes: ACK + length + data + checksum
    len_byte = transport.read(1)
    if not len_byte:
        raise DeviceTimeoutError("Timeout reading frame length byte")
    num_bytes = len_byte[0]

    # data_len = num_bytes - ACK(1) - length_byte(1) - checksum(1)
    data_len = num_bytes - 3
    if data_len < 0:
        raise FrameError(f"Invalid num_bytes value: {num_bytes}")

    data = transport.read(data_len) if data_len > 0 else b""
    if len(data) < data_len:
        raise DeviceTimeoutError(f"Timeout: expected {data_len} data bytes, got {len(data)}")

    chk_byte = transport.read(1)
    if not chk_byte:
        raise DeviceTimeoutError("Timeout reading checksum byte")

    frame_bytes = bytes([ACK, num_bytes]) + data
    expected_chk = _checksum(frame_bytes)
    if chk_byte[0] != expected_chk:
        raise FrameError(
            f"Host-side checksum mismatch: got 0x{chk_byte[0]:02X}, expected 0x{expected_chk:02X}"
        )

    return data


def send_and_receive(
    transport: Transport,
    frame: bytes,
    expected_data_bytes: int | None = None,
) -> bytes:
    """Write *frame* to *transport* and return the parsed response data bytes."""
    transport.write(frame)
    return read_response(transport, expected_data_bytes)
