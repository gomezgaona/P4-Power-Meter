"""High-level MCP39F511N device driver."""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from types import TracebackType
from typing import Any

import serial

from . import protocol as proto
from .exceptions import DeviceTimeoutError, FrameError
from .registers import (
    ENERGY1_ENABLE,
    ENERGY2_ENABLE,
    REG_APPARENT_POWER_2,
    REG_IMPORT_ENERGY_ACTIVE_1,
    REG_SYSTEM_CONFIG,
    REG_SYSTEM_STATUS,
    SIGN_PA_CH1,
    SIGN_PA_CH2,
    SIGN_PR_CH1,
    SIGN_PR_CH2,
    EnergySnapshot,
    Snapshot,
)

# The device-ID NAK byte expected from a ping
DEVICE_ID = 0x03


def _apply_sign(raw: int, status: int, mask: int) -> int:
    """Return *raw* negated if *status* has *mask* set."""
    return -raw if (status & mask) else raw


class MCP39F511N:
    """Driver for the Microchip MCP39F511N dual-channel power monitor.

    Can be used as a context manager::

        with MCP39F511N("/dev/ttyUSB0") as dev:
            snap = dev.read_snapshot()
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
        _transport: Any = None,
    ) -> None:
        """Create a driver instance.

        Args:
            port: Serial port path (e.g. ``/dev/ttyUSB0``).
            baudrate: UART baud rate (default 115200).
            timeout: Read timeout in seconds (default 1.0).
            _transport: Override transport for testing (must expose .read/.write).
        """
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._transport = _transport
        self._serial: serial.Serial | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> MCP39F511N:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the serial port (no-op if a test transport was injected)."""
        if self._transport is not None:
            return
        self._serial = serial.Serial(
            self._port,
            baudrate=self._baudrate,
            bytesize=8,
            parity=serial.PARITY_NONE,
            stopbits=1,
            timeout=self._timeout,
        )
        self._transport = self._serial

    def close(self) -> None:
        """Close the serial port."""
        if self._serial is not None:
            self._serial.close()
            self._serial = None
            self._transport = None

    @property
    def transport(self) -> Any:
        if self._transport is None:
            raise DeviceTimeoutError("Serial port is not open")
        return self._transport

    # ------------------------------------------------------------------
    # Low-level register access
    # ------------------------------------------------------------------

    def read_registers(self, address: int, n_bytes: int) -> bytes:
        """Read *n_bytes* bytes starting at *address*.

        Args:
            address: 16-bit register byte address.
            n_bytes: Number of bytes to read (max 32).

        Returns:
            Raw register bytes (little-endian).

        Raises:
            NakError, ChecksumError, FrameError, DeviceTimeoutError.
        """
        if n_bytes > 32:
            raise FrameError(f"Register Read N Bytes: max 32, requested {n_bytes}")
        frame = proto.build_read_frame(address, n_bytes)
        return proto.send_and_receive(self.transport, frame, expected_data_bytes=n_bytes)

    def write_registers(self, address: int, data: bytes) -> None:
        """Write *data* to registers starting at *address*.

        Args:
            address: 16-bit register byte address.
            data: Raw bytes to write (little-endian, max 32 bytes).
        """
        if len(data) > 32:
            raise FrameError(f"Register Write N Bytes: max 32, got {len(data)}")
        frame = proto.build_write_frame(address, data)
        proto.send_and_receive(self.transport, frame, expected_data_bytes=0)

    # ------------------------------------------------------------------
    # High-level reads
    # ------------------------------------------------------------------

    def read_snapshot(self) -> Snapshot:
        """Read all instantaneous measurement registers and return a :class:`Snapshot`.

        Two reads are issued:
        - Read 1: 0x0002, 24 bytes  ->  status, voltage, freq, PFx2, irmsx2, apwrx2
        - Read 2: 0x001A, 12 bytes  ->  active pwr 2, reactive pwr x2, apparent pwr x2

        Active and reactive powers have their signs applied from System Status before
        being returned.
        """
        ts = datetime.now(tz=timezone.utc)

        # Read 1: 0x0002 + 24 bytes covers up to 0x0019
        # Layout (LSB-first):
        #   0x0002  u16 system_status         (2 bytes)
        #   0x0004  u16 -- reserved --        (2 bytes)
        #   0x0006  u16 voltage_rms           (2 bytes)
        #   0x0008  u16 line_frequency        (2 bytes)
        #   0x000A  s16 power_factor_1        (2 bytes)
        #   0x000C  s16 power_factor_2        (2 bytes)
        #   0x000E  u32 current_rms_1         (4 bytes)
        #   0x0012  u32 current_rms_2         (4 bytes)
        #   0x0016  u32 active_power_1        (4 bytes)
        # Total: 24 bytes
        raw1 = self.read_registers(REG_SYSTEM_STATUS, 24)

        # Read 2: 0x001A + 20 bytes covers up to 0x002D
        # Layout:
        #   0x001A  u32 active_power_2        (4 bytes)
        #   0x001E  u32 reactive_power_1      (4 bytes)
        #   0x0022  u32 reactive_power_2      (4 bytes)
        #   0x0026  u32 apparent_power_1      (4 bytes)
        #   0x002A  u32 apparent_power_2      (4 bytes)
        # Total: 20 bytes
        raw2 = self.read_registers(REG_APPARENT_POWER_2 - 16, 20)  # 0x001A, 20 bytes

        # --- Unpack read 1 ---
        (
            system_status,
            _reserved,
            voltage_rms,
            line_frequency,
            pf1_raw,
            pf2_raw,
            current_rms_1,
            current_rms_2,
            active_power_1_raw,
        ) = struct.unpack_from("<HHHHhhIII", raw1)

        # --- Unpack read 2 ---
        (
            active_power_2_raw,
            reactive_power_1_raw,
            reactive_power_2_raw,
            apparent_power_1,
            apparent_power_2,
        ) = struct.unpack_from("<IIIII", raw2)

        # Power factor: s16, LSB weight = 2^-15
        pf1 = pf1_raw / 32768.0
        pf2 = pf2_raw / 32768.0

        # Apply sign from System Status
        ap1 = _apply_sign(active_power_1_raw, system_status, SIGN_PA_CH1)
        ap2 = _apply_sign(active_power_2_raw, system_status, SIGN_PA_CH2)
        rp1 = _apply_sign(reactive_power_1_raw, system_status, SIGN_PR_CH1)
        rp2 = _apply_sign(reactive_power_2_raw, system_status, SIGN_PR_CH2)

        return Snapshot(
            timestamp=ts,
            system_status=system_status,
            voltage_rms_raw=voltage_rms,
            line_frequency_mhz=line_frequency,
            power_factor_1=pf1,
            power_factor_2=pf2,
            current_rms_1_raw=current_rms_1,
            current_rms_2_raw=current_rms_2,
            active_power_1_signed=ap1,
            active_power_2_signed=ap2,
            reactive_power_1_signed=rp1,
            reactive_power_2_signed=rp2,
            apparent_power_1_raw=apparent_power_1,
            apparent_power_2_raw=apparent_power_2,
        )

    def read_energy(self) -> EnergySnapshot:
        """Read all four energy accumulator registers.

        Returns:
            :class:`EnergySnapshot` with four u64 accumulator values.

        Note:
            Energy counting must be enabled via :meth:`enable_energy_accumulation`
            before these counters advance.
        """
        ts = datetime.now(tz=timezone.utc)

        # Four u64s (8 bytes each) starting at 0x002E = 32 bytes total
        raw = self.read_registers(REG_IMPORT_ENERGY_ACTIVE_1, 32)
        ie1, ie2, ee1, ee2 = struct.unpack_from("<QQQQ", raw)
        return EnergySnapshot(
            timestamp=ts,
            import_energy_active_1=ie1,
            import_energy_active_2=ie2,
            export_energy_active_1=ee1,
            export_energy_active_2=ee2,
        )

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def enable_energy_accumulation(self, save_to_flash: bool = False) -> None:
        """Enable energy counting on both channels in System Configuration register.

        Args:
            save_to_flash: If True, also persist the setting across resets.
        """
        raw = self.read_registers(REG_SYSTEM_CONFIG, 4)
        (cfg,) = struct.unpack_from("<I", raw)
        cfg |= ENERGY1_ENABLE | ENERGY2_ENABLE
        self.write_registers(REG_SYSTEM_CONFIG, struct.pack("<I", cfg))
        if save_to_flash:
            self.save_to_flash()

    def save_to_flash(self) -> None:
        """Save the current register state to flash (CMD_SAVE_FLASH = 0x53)."""
        frame = proto.build_save_flash_frame()
        proto.send_and_receive(self.transport, frame, expected_data_bytes=0)

    def ping(self) -> int:
        """Send a ping frame (header = 0x5A instead of 0xA5) to verify connectivity.

        The device replies with a NAK containing the device ID byte.

        Returns:
            Device ID byte (0x03 for MCP39F511N).

        Note:
            This method constructs the raw frame manually because the ping header
            is intentionally invalid (0x5A), causing the device to echo its ID.
        """
        # Ping frame: 0x5A 0x03 checksum — total 3 bytes
        ping_bytes = bytes([0x5A, 0x03])
        ping_bytes += bytes([proto._checksum(ping_bytes)])
        self.transport.write(ping_bytes)

        # Device replies: NAK + ID byte (2 bytes)
        resp = self.transport.read(2)
        if len(resp) < 2:
            raise DeviceTimeoutError("Timeout waiting for ping response")
        if resp[0] != proto.NAK:
            raise FrameError(f"Unexpected ping response: 0x{resp[0]:02X}")
        return resp[1]
