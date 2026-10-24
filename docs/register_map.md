# Register Map (v2)

The registers live in `reg_file.vhd`, inside the UART control block (`ctrl_block`).
The host reaches them over UART with the framed protocol below. In phase 3 the
ARM HPS will use the same register bus. (v1, on the `v1` branch, used a Nios II
and the Avalon slave `RegistersControl` at `0x0800_1000`.)

| Property      | Value |
|---------------|-------|
| Data width    | 16 bit |
| Address width | 8 bit |
| Access        | effect registers R/W, status registers R |
| Reset value   | 0 (all effects off) |

Every register is 16 bits wide. Bits not listed below are reserved: write `0`.
The bit ranges are the bits the RTL actually reads.

| Reg | Name            | R/W | Bits used | Field                         | Description |
|----:|-----------------|:---:|-----------|-------------------------------|-------------|
| 0   | Effects Enable  | W   | `[5:0]`   | `REVERB CHORUS DIST ECHO TREM OD` | One enable bit per effect, see [(1)](#1-effects-enable). |
| 1   | Overdrive Drive | W   | `[15:0]`  | Drive Value                   | Clipping threshold (unsigned sample amplitude). GUI range 0 … 3500. |
| 2   | Overdrive Gain  | W   | `[15:0]`  | Gain Volume                   | Integer post-clip gain multiplier. GUI range 1 … 5. |
| 3   | Tremolo Wave    | W   | `[2:0]`   | Waveform Selection            | LFO waveform/rate, see [(2)](#2-tremolo-waveform-selection). |
| 4   | Tremolo Depth   | W   | `[7:0]`   | Modulation Depth Value        | 0 = dry … 255 = full modulation. |
| 5   | Echo Time       | W   | `[14:0]`  | Echo Reflection Time Value    | Delay in samples @ 48 kHz (bit 15 must be `0`). 32767 ≈ 0.68 s. |
| 6   | Echo Repeat     | W   | `[7:0]`   | Repeat Decay Volume           | Feedback amount, 0 … 255 (/256). |
| 7   | Echo Level      | W   | `[15:0]`  | Initial Reflection Volume     | Wet level, unsigned Q0.16 (65535 ≈ 1.0). GUI range 0 … 32000. |
| 8   | Distortion Mix  | W   | `[7:0]`   | Distortion Mixed Signal Value | Dry/wet mix, 0 = dry … 255 = wet. |
| 9   | Distortion Type | W   | `[1:0]`   | Distortion Type Selection     | Clipping curve, see [(3)](#3-distortion-type-selection). |
| 10  | Chorus Level    | W   | `[15:0]`  | Chorus Mixed Signal Value     | Wet level, unsigned Q0.16. |
| 11  | Chorus Depth    | W   | `[9:0]`   | Chorus Delay Depth Value      | LFO sweep depth in samples (sweeps 2 … depth+2). |
| 12  | Chorus Rate     | W   | `[9:0]`   | Chorus Delay Rate Value       | LFO clock divider (higher = slower). |
| 13  | Reverb Mix      | W   | `[7:0]`   | Reverb Mixed Signal Value     | Dry/wet mix, 0 = dry … 255 = wet. |
| 14  | Reverb Type     | W   | `[3:0]`   | Reverb Type Selection         | Room preset, see [(4)](#4-reverb-type-selection). |
| 0x10 | VERSION        | R   | `[15:0]`  | | `0x0200` = v2.0 |
| 0x11 | STATUS         | R   | `[2:0]`   | | bit0 codec init done, bit1 codec NAK (init), bit2 PLL locked |
| 0x12 | LEVEL_IN       | R   | `[15:0]`  | | input peak level (left, 16-bit magnitude, decays ~1/256 per sample) |
| 0x13 | LEVEL_OUT      | R   | `[15:0]`  | | output peak level |
| 0x14 | CONTROL        | R/W | `[1:0]`   | | bit0 = re-run codec init (self-clearing), bit1 = mute |

## Field encodings

### (1) Effects Enable

| Bit | Effect     | `0`     | `1`    |
|----:|------------|---------|--------|
| 0   | Overdrive  | Bypass  | Enable |
| 1   | Tremolo    | Bypass  | Enable |
| 2   | Echo       | Bypass  | Enable |
| 3   | Distortion | Bypass  | Enable |
| 4   | Chorus     | Bypass  | Enable |
| 5   | Reverb     | Bypass  | Enable |

Signal chain order (fixed in `FX_chain.vhd`):
`Overdrive → Distortion → Chorus → Tremolo → Echo → Reverb`

### (2) Tremolo Waveform Selection

| Value | Waveform | Rate  |
|------:|----------|-------|
| 0     | Sine     | 5 Hz  |
| 1     | Sine     | 7 Hz  |
| 2     | Sine     | 10 Hz |
| 3     | Sine     | 12 Hz |
| 4     | Sine     | 15 Hz |
| 5     | Triangle | 5 Hz  |
| 6     | Triangle | 10 Hz |
| 7     | Sawtooth | 10 Hz |

### (3) Distortion Type Selection

| Value | Type              |
|------:|-------------------|
| 0     | Soft distortion   |
| 1     | Medium distortion |
| 2     | Heavy distortion  |
| 3     | (= Soft)          |

### (4) Reverb Type Selection

| Value | Type              |
|------:|-------------------|
| 0     | Very light reverb |
| 1     | Light reverb      |
| 2     | Medium reverb     |
| 3     | Heavy reverb      |
| other | (= Heavy)         |

## UART protocol (v2)

115200 baud, 8N1, on GPIO_0 (`UART_RX` = D0, `UART_TX` = D1, 3.3 V USB-UART adapter).
Host tool: [`tools/gme_ctl.py`](../tools/gme_ctl.py).

**Request (host → FPGA)**

| Byte | 0 | 1 | 2 | 3 | 4 | 5 |
|------|---|---|---|---|---|---|
| | `0xA5` sync | command | address | data\[15:8\] | data\[7:0\] | CRC-8 over bytes 1–4 |

| Command | Function | Reply data |
|---------|----------|------------|
| `0x01` WRITE | write register *address* | 0 |
| `0x02` READ | read register *address* | register value |
| `0x03` CODEC | I²C write to the codec: *address* = codec register (0..127), data = 9-bit value | 0 (sent when the I²C transfer is done) |
| `0x04` PING | | VERSION |

**Reply (FPGA → host):** `0x5A`, status, data\[15:8\], data\[7:0\], CRC-8 over bytes 1–3.

| Status | Meaning |
|--------|---------|
| `0x00` | OK |
| `0x01` | CRC error in the request (nothing executed) |
| `0x02` | unknown command or invalid address |
| `0x03` | codec did not ACK (I²C NAK) |
| `0x04` | I²C busy (codec init still running) |

CRC-8/SMBUS: polynomial 0x07, initial value 0, no reflection (check value for
"123456789" is 0xF4). The FPGA hunts for `0xA5`. A partial frame is dropped
after 10 ms without a byte, so a lost byte costs at most one frame.

The codec is initialised by the FPGA itself after reset (I²S slave, 24-bit,
48 kHz; see `codec_ctrl.vhd`). CODEC commands are only needed to change volumes
or routing.
