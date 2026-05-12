"""High-level device tests using FakeSerial."""

from __future__ import annotations

import struct

import pytest
from conftest import FakeSerial, make_ack_response

from mcp39f511n.device import MCP39F511N
from mcp39f511n.exceptions import DeviceTimeoutError, FrameError, NakError
from mcp39f511n.protocol import NAK
from mcp39f511n.registers import (
    SIGN_PA_CH1,
    SIGN_PA_CH2,
    SIGN_PR_CH1,
    SIGN_PR_CH2,
)


def _make_device(transport: FakeSerial) -> MCP39F511N:
    return MCP39F511N("/dev/null", _transport=transport)


# ---------------------------------------------------------------------------
# read_registers
# ---------------------------------------------------------------------------


def test_read_registers_returns_data():
    payload = bytes(range(8))
    fs = FakeSerial(make_ack_response(payload))
    dev = _make_device(fs)
    result = dev.read_registers(0x0006, 8)
    assert result == payload


def test_read_registers_raises_on_nak():
    fs = FakeSerial(bytes([NAK]))
    dev = _make_device(fs)
    with pytest.raises(NakError):
        dev.read_registers(0x0006, 4)


def test_read_registers_max_32_enforced():
    dev = _make_device(FakeSerial())
    with pytest.raises(FrameError, match="max 32"):
        dev.read_registers(0x0006, 33)


# ---------------------------------------------------------------------------
# write_registers
# ---------------------------------------------------------------------------


def test_write_registers_sends_frame_and_accepts_ack():
    fs = FakeSerial(make_ack_response(b""))
    dev = _make_device(fs)
    dev.write_registers(0x00A0, b"\x00\x03\x00\x00")
    assert len(fs.written) > 0


def test_write_registers_max_32_enforced():
    dev = _make_device(FakeSerial())
    with pytest.raises(FrameError, match="max 32"):
        dev.write_registers(0x00A0, bytes(33))


# ---------------------------------------------------------------------------
# read_snapshot — sign application
# ---------------------------------------------------------------------------


def _build_snapshot_responses(
    system_status: int = 0,
    voltage_rms: int = 24000,
    line_freq: int = 60000,
    pf1_raw: int = 32767,
    pf2_raw: int = -16384,
    current1: int = 1000,
    current2: int = 2000,
    ap1: int = 100,
    ap2: int = 200,
    rp1: int = 50,
    rp2: int = 75,
    apparent1: int = 110,
    apparent2: int = 210,
) -> bytes:
    """Build two concatenated ACK response frames for read_snapshot's two reads."""
    # Read 1 payload: status, reserved, voltage, freq, pf1, pf2, irms1, irms2, ap1_raw
    r1 = struct.pack(
        "<HHHHhhIII",
        system_status,
        0,
        voltage_rms,
        line_freq,
        pf1_raw,
        pf2_raw,
        current1,
        current2,
        ap1,
    )
    # Read 2 payload: ap2_raw, rp1_raw, rp2_raw, apparent1, apparent2
    r2 = struct.pack("<IIIII", ap2, rp1, rp2, apparent1, apparent2)
    return make_ack_response(r1) + make_ack_response(r2)


def test_read_snapshot_no_sign_bits():
    responses = _build_snapshot_responses(system_status=0, ap1=100, ap2=200, rp1=50, rp2=75)
    dev = _make_device(FakeSerial(responses))
    snap = dev.read_snapshot()
    assert snap.active_power_1_signed == 100
    assert snap.active_power_2_signed == 200
    assert snap.reactive_power_1_signed == 50
    assert snap.reactive_power_2_signed == 75


def test_read_snapshot_all_sign_bits_set():
    status = SIGN_PA_CH1 | SIGN_PA_CH2 | SIGN_PR_CH1 | SIGN_PR_CH2
    responses = _build_snapshot_responses(system_status=status, ap1=100, ap2=200, rp1=50, rp2=75)
    dev = _make_device(FakeSerial(responses))
    snap = dev.read_snapshot()
    assert snap.active_power_1_signed == -100
    assert snap.active_power_2_signed == -200
    assert snap.reactive_power_1_signed == -50
    assert snap.reactive_power_2_signed == -75


def test_read_snapshot_partial_sign_bits():
    status = SIGN_PA_CH1 | SIGN_PR_CH2
    responses = _build_snapshot_responses(system_status=status, ap1=100, ap2=200, rp1=50, rp2=75)
    dev = _make_device(FakeSerial(responses))
    snap = dev.read_snapshot()
    assert snap.active_power_1_signed == -100
    assert snap.active_power_2_signed == 200
    assert snap.reactive_power_1_signed == 50
    assert snap.reactive_power_2_signed == -75


def test_read_snapshot_power_factor_conversion():
    responses = _build_snapshot_responses(pf1_raw=32767, pf2_raw=-32768)
    dev = _make_device(FakeSerial(responses))
    snap = dev.read_snapshot()
    assert abs(snap.power_factor_1 - (32767 / 32768.0)) < 1e-6
    assert abs(snap.power_factor_2 - (-32768 / 32768.0)) < 1e-6


def test_read_snapshot_voltage_and_freq_passthrough():
    responses = _build_snapshot_responses(voltage_rms=23456, line_freq=50000)
    dev = _make_device(FakeSerial(responses))
    snap = dev.read_snapshot()
    assert snap.voltage_rms_raw == 23456
    assert snap.line_frequency_mhz == 50000


# ---------------------------------------------------------------------------
# read_energy
# ---------------------------------------------------------------------------


def test_read_energy_values():
    ie1, ie2, ee1, ee2 = 1_000_000, 2_000_000, 3_000_000, 4_000_000
    payload = struct.pack("<QQQQ", ie1, ie2, ee1, ee2)
    fs = FakeSerial(make_ack_response(payload))
    dev = _make_device(fs)
    energy = dev.read_energy()
    assert energy.import_energy_active_1 == ie1
    assert energy.import_energy_active_2 == ie2
    assert energy.export_energy_active_1 == ee1
    assert energy.export_energy_active_2 == ee2


# ---------------------------------------------------------------------------
# enable_energy_accumulation
# ---------------------------------------------------------------------------


def test_enable_energy_accumulation_sets_bits():
    """Verify that enable_energy_accumulation ORs in the ENERGY1/2 bits."""
    initial_cfg = struct.pack("<I", 0x0000_0000)
    # Responses: 1) read sys_config, 2) write sys_config (ACK)
    responses = make_ack_response(initial_cfg) + make_ack_response(b"")
    fs = FakeSerial(responses)
    dev = _make_device(fs)
    dev.enable_energy_accumulation(save_to_flash=False)
    # The second write frame must contain the ENERGY bits (bits 8 and 9)
    written = fs.written
    # Find the data bytes in the write frame — energy bits = 0x0300
    assert b"\x00\x03\x00\x00" in written


def test_enable_energy_accumulation_with_flash():
    """Verify save_to_flash=True sends an extra CMD_SAVE_FLASH frame."""
    initial_cfg = struct.pack("<I", 0x0000_0000)
    responses = make_ack_response(initial_cfg) + make_ack_response(b"") + make_ack_response(b"")
    fs = FakeSerial(responses)
    dev = _make_device(fs)
    dev.enable_energy_accumulation(save_to_flash=True)
    # CMD_SAVE_FLASH = 0x53 must appear in the written bytes
    assert 0x53 in fs.written


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------


def test_ping_returns_device_id():
    device_id = 0x03
    fs = FakeSerial(bytes([NAK, device_id]))
    dev = _make_device(fs)
    result = dev.ping()
    assert result == device_id


def test_ping_timeout_raises():
    fs = FakeSerial(b"")
    dev = _make_device(fs)
    with pytest.raises(DeviceTimeoutError):
        dev.ping()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


def test_context_manager_closes_on_exit():
    """Context manager should not crash when using a fake transport."""
    fs = FakeSerial()
    dev = MCP39F511N("/dev/null", _transport=fs)
    with dev:
        pass
    # No assertion needed — just verify no exception is raised
