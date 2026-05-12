"""Register address constants and measurement dataclasses for the MCP39F511N."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# ---------------------------------------------------------------------------
# Register addresses (byte addresses as per the MCP39F511N datasheet)
# ---------------------------------------------------------------------------

REG_SYSTEM_STATUS = 0x0002  # u16 — sign bits for active/reactive power
REG_VOLTAGE_RMS = 0x0006  # u16
REG_LINE_FREQUENCY = 0x0008  # u16, 1 mHz resolution
REG_POWER_FACTOR_1 = 0x000A  # s16, LSB weight = 2^-15, range -1.0..+1.0
REG_POWER_FACTOR_2 = 0x000C  # s16
REG_CURRENT_RMS_1 = 0x000E  # u32
REG_CURRENT_RMS_2 = 0x0012  # u32
REG_ACTIVE_POWER_1 = 0x0016  # u32 (sign from System Status)
REG_ACTIVE_POWER_2 = 0x001A  # u32
REG_REACTIVE_POWER_1 = 0x001E  # u32 (sign from System Status)
REG_REACTIVE_POWER_2 = 0x0022  # u32
REG_APPARENT_POWER_1 = 0x0026  # u32
REG_APPARENT_POWER_2 = 0x002A  # u32

REG_IMPORT_ENERGY_ACTIVE_1 = 0x002E  # u64
REG_IMPORT_ENERGY_ACTIVE_2 = 0x0036  # u64
REG_EXPORT_ENERGY_ACTIVE_1 = 0x003E  # u64
REG_EXPORT_ENERGY_ACTIVE_2 = 0x0046  # u64

REG_SYSTEM_CONFIG = 0x00A0  # b32 — bit 8 = ENERGY1 enable, bit 9 = ENERGY2 enable

# ---------------------------------------------------------------------------
# System Status bit masks
# ---------------------------------------------------------------------------

SIGN_PA_CH1 = 1 << 0  # bit 0: active power channel 1 is negative
SIGN_PA_CH2 = 1 << 1  # bit 1: active power channel 2 is negative
SIGN_PR_CH1 = 1 << 2  # bit 2: reactive power channel 1 is negative
SIGN_PR_CH2 = 1 << 3  # bit 3: reactive power channel 2 is negative

# System Configuration energy-enable bits
ENERGY1_ENABLE = 1 << 8
ENERGY2_ENABLE = 1 << 9


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Snapshot:
    """Instantaneous measurement snapshot from both channels."""

    timestamp: datetime
    system_status: int

    # Voltage / frequency (shared)
    voltage_rms_raw: int  # raw u16 register value
    line_frequency_mhz: int  # raw u16, units = 1 mHz (divide by 1000 for Hz)

    # Power factor (s16, LSB = 2^-15)
    power_factor_1: float
    power_factor_2: float

    # Current (raw u32 register values)
    current_rms_1_raw: int
    current_rms_2_raw: int

    # Active power (sign already applied; negative = energy export direction)
    active_power_1_signed: int
    active_power_2_signed: int

    # Reactive power (sign already applied)
    reactive_power_1_signed: int
    reactive_power_2_signed: int

    # Apparent power (always positive)
    apparent_power_1_raw: int
    apparent_power_2_raw: int


@dataclass
class EnergySnapshot:
    """Energy accumulator values from both channels."""

    timestamp: datetime
    import_energy_active_1: int  # u64
    import_energy_active_2: int  # u64
    export_energy_active_1: int  # u64
    export_energy_active_2: int  # u64
