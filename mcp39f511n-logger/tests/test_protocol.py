"""Protocol layer tests — frame builder, checksum, parser, error paths."""

from __future__ import annotations

import pytest
from conftest import FakeSerial, make_ack_response

from mcp39f511n.exceptions import ChecksumError, DeviceTimeoutError, FrameError, NakError
from mcp39f511n.protocol import (
    ACK,
    CSFAIL,
    NAK,
    _checksum,
    build_frame,
    build_read_frame,
    build_save_flash_frame,
    build_write_frame,
    read_response,
    send_and_receive,
)

# ---------------------------------------------------------------------------
# Checksum helper
# ---------------------------------------------------------------------------


def test_checksum_basic():
    assert _checksum(b"\xa5\x08\x41\x00\x02\x4e\x20") == 0x5E


def test_checksum_empty():
    assert _checksum(b"") == 0


def test_checksum_overflow_wraps():
    # 0xFF + 0x01 = 0x100 → masked to 0x00
    assert _checksum(b"\xff\x01") == 0x00


# ---------------------------------------------------------------------------
# Datasheet Table 4-2 byte-for-byte verification
# Reading 32 bytes (0x20) from address 0x0002
# Expected: A5 08 41 00 02 4E 20 5E
# ---------------------------------------------------------------------------


def test_datasheet_table4_2_exact_bytes():
    """Verify the exact byte sequence from MCP39F511N datasheet Table 4-2."""
    frame = build_read_frame(address=0x0002, n_bytes=0x20)
    expected = bytes([0xA5, 0x08, 0x41, 0x00, 0x02, 0x4E, 0x20, 0x5E])
    got = frame.hex(" ").upper()
    want = expected.hex(" ").upper()
    assert frame == expected, f"Got: {got!r}, want: {want!r}"


# ---------------------------------------------------------------------------
# Frame builder
# ---------------------------------------------------------------------------


def test_build_frame_structure():
    cmd = bytes([0x41, 0x00, 0x02])
    frame = build_frame(cmd)
    # header=0xA5, num_bytes=3+3-1=... let's just verify header + checksum
    assert frame[0] == 0xA5
    assert frame[1] == len(frame)
    assert frame[-1] == _checksum(frame[:-1])


def test_build_frame_multiple_packets():
    """Two command packets chained into one frame."""
    p1 = bytes([0x41, 0x00, 0x02])  # SET_ADDRESS
    p2 = bytes([0x4E, 0x20])  # READ_N 32
    frame = build_frame(p1, p2)
    assert frame[0] == 0xA5
    assert frame[1] == len(frame)
    assert frame[-1] == _checksum(frame[:-1])
    # Total payload = 3 + 2 = 5 bytes; frame = 0xA5 + len + 5 + chk = 8 bytes
    assert len(frame) == 8


def test_build_frame_too_large():
    with pytest.raises(FrameError, match="too large"):
        # 35 bytes max total; payload of 33 bytes → 36 bytes total
        build_frame(bytes(33))


def test_build_read_frame():
    frame = build_read_frame(0x0006, 16)
    assert frame[0] == 0xA5
    # SET_ADDRESS: 0x41, 0x00, 0x06  (3 bytes)
    # READ_N: 0x4E, 0x10             (2 bytes)
    assert 0x41 in frame
    assert 0x4E in frame
    assert frame[-1] == _checksum(frame[:-1])


def test_build_write_frame():
    data = b"\x01\x02\x03\x04"
    frame = build_write_frame(0x00A0, data)
    assert frame[0] == 0xA5
    assert 0x41 in frame
    assert 0x4D in frame
    assert frame[-1] == _checksum(frame[:-1])


def test_build_save_flash_frame():
    frame = build_save_flash_frame()
    assert frame[0] == 0xA5
    assert 0x53 in frame
    assert frame[-1] == _checksum(frame[:-1])


# ---------------------------------------------------------------------------
# Response parser — happy path
# ---------------------------------------------------------------------------


def test_read_response_no_data():
    """ACK with zero data bytes."""
    response = make_ack_response(b"")
    fs = FakeSerial(response)
    data = read_response(fs)
    assert data == b""


def test_read_response_with_data():
    payload = bytes(range(8))
    response = make_ack_response(payload)
    fs = FakeSerial(response)
    data = read_response(fs)
    assert data == payload


def test_send_and_receive_roundtrip():
    """send_and_receive writes the frame and returns parsed data."""
    payload = b"\xde\xad\xbe\xef"
    response = make_ack_response(payload)
    fs = FakeSerial(response)
    frame = build_read_frame(0x0006, 4)
    data = send_and_receive(fs, frame)
    assert data == payload
    # Verify the correct frame was written
    assert fs.written == frame


# ---------------------------------------------------------------------------
# Response parser — error paths
# ---------------------------------------------------------------------------


def test_nak_raises():
    fs = FakeSerial(bytes([NAK]))
    with pytest.raises(NakError):
        read_response(fs)


def test_csfail_raises():
    fs = FakeSerial(bytes([CSFAIL]))
    with pytest.raises(ChecksumError):
        read_response(fs)


def test_unexpected_first_byte_raises():
    fs = FakeSerial(bytes([0xAB]))
    with pytest.raises(FrameError, match="Unexpected response byte"):
        read_response(fs)


def test_timeout_on_empty_response():
    fs = FakeSerial(b"")
    with pytest.raises(DeviceTimeoutError):
        read_response(fs)


def test_timeout_missing_length_byte():
    fs = FakeSerial(bytes([ACK]))
    with pytest.raises(DeviceTimeoutError, match="length byte"):
        read_response(fs)


def test_timeout_truncated_data():
    # ACK + num_bytes=10 (7 data bytes) but only 3 data bytes provided
    fs = FakeSerial(bytes([ACK, 10]) + bytes(3))
    with pytest.raises(DeviceTimeoutError, match="expected 7 data bytes"):
        read_response(fs)


def test_host_checksum_mismatch_raises():
    """Corrupt the checksum byte in an otherwise valid response."""
    good_response = make_ack_response(b"\x01\x02\x03\x04")
    # Flip the last byte (checksum)
    bad_response = good_response[:-1] + bytes([(good_response[-1] ^ 0xFF)])
    fs = FakeSerial(bad_response)
    with pytest.raises(FrameError, match="checksum mismatch"):
        read_response(fs)


def test_invalid_num_bytes_raises():
    # num_bytes = 2 → data_len = 2 - 3 = -1 (invalid)
    fs = FakeSerial(bytes([ACK, 2]))
    with pytest.raises(FrameError, match="Invalid num_bytes"):
        read_response(fs)
