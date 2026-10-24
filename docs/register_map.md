# Register Map

The effect parameters live in the custom Avalon-MM slave **`RegistersControl`**
(`fpga/rtl/RegistersControl.vhd`), instantiated in Platform Designer as
`RegistersControl_0`.

| Property      | Value                                                        |
|---------------|--------------------------------------------------------------|
| Base address  | `REGISTERSCONTROL_0_BASE` = `0x0800_1000` (see BSP `system.h`) |
| Data width    | 16 bit                                                       |
| Access        | Write-only (no read-back)                                    |
| Byte offset   | `register_number * 2` &nbsp;(`IOWR_16DIRECT(BASE, REG*2, DATA)`) |
| Reset value   | none – registers power up as `0` (FPGA init)                 |

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

## PC → Nios II UART protocol

The PC GUI sends fixed 3-byte frames at **9600 baud, 8N1** to the Nios II UART
(`UART_RX` = GPIO_0[0], `UART_TX` = GPIO_0[1]; use a 3.3 V USB-UART adapter).

| Byte 0 (command)      | Byte 1              | Byte 2              | Action |
|-----------------------|---------------------|---------------------|--------|
| `0x00` … `0x0E`       | data\[15:8\]        | data\[7:0\]         | Write effect register *byte 0* |
| `0xCD` (codec update) | codec address byte¹ | codec data\[7:0\]   | I²C write to the audio codec |
| `0xEC` (codec preset) | don't care          | don't care          | Re-run the default codec initialisation |

¹ The codec (WM8731 / SSM2603-compatible) uses 7-bit register addresses and
9-bit data. The address byte is `(reg << 1) | data[8]`.

> The original frame format has no sync byte or checksum: one lost byte
> misaligns all following frames.
