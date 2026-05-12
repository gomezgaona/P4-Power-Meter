# MCP39F511N UART Protocol Reference

Distilled from the Microchip MCP39F511N datasheet for quick reference.

---

## Serial Parameters

| Parameter | Value |
|-----------|-------|
| Baud rate | 115200 (configurable 1200–115200) |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 |

---

## Frame Format

```
0xA5 | num_bytes | command_packet(s)... | checksum
```

- **0xA5** — fixed header byte.
- **num_bytes** — total frame length including header, length byte, all commands, and checksum.
- **checksum** = `sum(all preceding bytes) & 0xFF`.
- Maximum frame size: **35 bytes**.
- Multiple command packets may be chained in a single frame.

### Example — Read 32 bytes from address 0x0002 (datasheet Table 4-2)

```
Sent:    A5 08 41 00 02 4E 20 5E
         │  │  │  │  │  │  │  └─ checksum = (A5+08+41+00+02+4E+20) & 0xFF = 0x5E
         │  │  │  └──┘  │  └──── N = 32 (0x20)
         │  │  │  addr  └─────── Register Read N Bytes (0x4E)
         │  │  └──────────────── Set Address Pointer (0x41)
         │  └─────────────────── num_bytes = 8
         └────────────────────── header (0xA5)
```

---

## Response Codes

| Byte | Meaning |
|------|---------|
| `0x06` | ACK — success |
| `0x15` | NAK — command failed or not understood |
| `0x51` | CSFAIL — checksum mismatch |

A successful read response: `ACK | num_bytes | data_bytes... | checksum`
where `num_bytes = len(data) + 3`.

---

## Commands

| Opcode | Name | Arguments |
|--------|------|-----------|
| `0x41` | Set Address Pointer | 2 bytes: addr_hi, addr_lo |
| `0x4E` | Register Read N Bytes | 1 byte: N (max 32) |
| `0x4D` | Register Write N Bytes | 1 byte N, then N data bytes |
| `0x53` | Save Registers To Flash | none |

---

## Endianness

Register data is transmitted **LSB-first** (little-endian) in both directions.

---

## Register Map (used by this project)

| Address | Name | Type | Notes |
|---------|------|------|-------|
| 0x0002 | System Status | u16 | Sign bits for active/reactive power per channel |
| 0x0006 | Voltage RMS | u16 | |
| 0x0008 | Line Frequency | u16 | 1 mHz resolution (divide by 1000 for Hz) |
| 0x000A | Power Factor 1 | s16 | LSB = 2⁻¹⁵; range −1.0 … +1.0 |
| 0x000C | Power Factor 2 | s16 | |
| 0x000E | Current RMS 1 | u32 | |
| 0x0012 | Current RMS 2 | u32 | |
| 0x0016 | Active Power 1 | u32 | Sign from System Status bit 0 (`SIGN_PA_CH1`) |
| 0x001A | Active Power 2 | u32 | Sign from bit 1 (`SIGN_PA_CH2`) |
| 0x001E | Reactive Power 1 | u32 | Sign from bit 2 (`SIGN_PR_CH1`) |
| 0x0022 | Reactive Power 2 | u32 | Sign from bit 3 (`SIGN_PR_CH2`) |
| 0x0026 | Apparent Power 1 | u32 | Always positive |
| 0x002A | Apparent Power 2 | u32 | |
| 0x002E | Import Energy Active 1 | u64 | Accumulator; requires energy counting enabled |
| 0x0036 | Import Energy Active 2 | u64 | |
| 0x003E | Export Energy Active 1 | u64 | |
| 0x0046 | Export Energy Active 2 | u64 | |
| 0x00A0 | System Configuration | b32 | Bit 8 = ENERGY1 enable, bit 9 = ENERGY2 enable |

### System Status sign bits

| Bit | Name | Meaning when set |
|-----|------|-----------------|
| 0 | SIGN_PA_CH1 | Active power channel 1 is negative (exporting) |
| 1 | SIGN_PA_CH2 | Active power channel 2 is negative |
| 2 | SIGN_PR_CH1 | Reactive power channel 1 is negative |
| 3 | SIGN_PR_CH2 | Reactive power channel 2 is negative |

---

## Read Strategy

Because `Register Read N Bytes` is capped at 32, the instantaneous snapshot
is split into two reads:

1. **Read 1:** address `0x0002`, 24 bytes → System Status through Active Power 1.
2. **Read 2:** address `0x001A`, 20 bytes → Active Power 2 through Apparent Power 2.

---

## Energy Accumulation

Energy counters are disabled at reset. Before they advance, write System
Configuration register `0x00A0` with bits 8 and 9 set, then issue
`CMD_SAVE_FLASH` (`0x53`) so the setting survives a power cycle.

---

## Computation Cadence

The device refreshes outputs every `2^N` line cycles (N = Accumulation Interval
Parameter register, default N = 4 → 16 cycles → ~267–320 ms). Polling faster
than ~3 Hz yields duplicate readings; the default interval is 1 second.
