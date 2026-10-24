# v2 step B: clocking, I²S core and UART control block

**Status: B1–B5 done and verified in simulation; Quartus build meets timing. Board test pending (no hardware access yet).** Decisions: sys_clk 49.152 MHz with the FPGA as I²S master;
new UART protocol only (the C# GUI stays on the `v1` branch). Hardware tests are
postponed (no board access yet), so verification is simulation only.

Goal: one clock domain, a clean stereo I²S interface, and the Nios II replaced
by a small RTL control block driven over UART. The effects keep their current
behaviour (DSP improvements come in steps C/D).

## Sub-steps

Each sub-step lands separately with its tests, and CI stays green.

| # | Change | How it's verified |
|---|--------|-------------------|
| **B1** ✅ | Effect chain moves to `sys_clk` + `sample_tick` (no more LRCLK clocking), same 16-bit arithmetic | **Bit-exact to v1**: v1's outputs for every test and preset are recorded first and must be reproduced exactly |
| **B2** ✅ | New I²S core: FPGA master (BCLK, LRCLK, sample/half tick), stereo, 24-bit | cocotb against a codec slave model; stereo bypass bit-exact; clock and bit-alignment checks |
| **B3** ✅ | UART + frame parser + register file | cocotb: protocol frames, CRC errors, resync, readback |
| **B4** ✅ | I²C master + codec init sequencer | cocotb against an I²C slave model (checks the exact register writes) |
| **B5** ✅ | New top level without Platform Designer/Nios II, PLL, SDC, pin changes | Quartus build, timing met, then **board bring-up** with a Python host tool |

B1 comes first because it's the riskiest change for the existing effects, and
v1 gives an exact reference to check it against.

## Clocking (decided: 49.152 MHz, FPGA is I²S master)

| Signal | Frequency | Ratio to sys_clk | Type | Purpose |
|--------|-----------|------------------|------|---------|
| `CLOCK_50` | 50 MHz | n/a | board clock | PLL reference only |
| **`sys_clk`** | **49.152 MHz** | 1 | PLL c0, the only internal clock | every register |
| `AUD_XCK` (MCLK) | 12.288 MHz | ÷4 | PLL c1, phase-locked to c0 | codec master clock, 256·fs |
| `AUD_BCLK` | 3.072 MHz | ÷16 | counter output | I²S bit clock, 32 bits per channel |
| `AUD_DACLRCK`/`ADCLRCK` | 48 kHz | ÷1024 | counter output | I²S frame clock |
| `sample_tick` | 48 kHz | 1 per 1024 | 1-cycle strobe | new stereo sample; effects step |
| `half_tick` | 48 kHz | offset 512 | 1-cycle strobe | second half-frame step (v1's falling-edge effects) |
| `uart_en` | 16 × 115200 | fractional divider | strobe | UART timing |
| `i2c_en` | 4 × 100 kHz | ÷123 | strobe | I²C quarter-phases |

* The FPGA generates BCLK and LRCLK (codec in **slave** mode: R7 = 0x0A, I²S
  24-bit; R8 = 0x00, 256·fs). No audio clock comes back into the FPGA, so there
  are no clock-domain crossings in the audio path. ADCDAT is sampled at a known
  point of the FPGA's own BCLK.
* 1024 cycles per sample give room for FIR convolution later (about 1000 taps per DSP
  block per sample).
* B1 keeps v1's unpipelined effect arithmetic. It is only enabled by the
  strobes (at least 512 cycles apart), so the SDC declares **multicycle paths** for the
  effect registers. New effects (step C onwards) are pipelined and need none.

## B1: effect chain on the sample tick

Each effect gets `clk` plus two strobes, `en_rise` and `en_fall`. They stand
for the rising and falling edge of the clock the effect saw in v1, so the change
is mechanical and exact:
`rising_edge(AUD_DACLRCLK)` → `rising_edge(clk) and en_rise = '1'`,
`falling_edge(AUD_DACLRCLK)` → `rising_edge(clk) and en_fall = '1'`.

| Effect | v1 clock | `en_rise` | `en_fall` |
|--------|----------|-----------|-----------|
| overdrive, distortion | LRCLK | `sample_tick` | n/a |
| chorus, tremolo, echo, reverb (comb, all-pass) | not(LRCLK) | `half_tick` | `sample_tick` |

* **Delay RAMs** (echo, chorus, combs, all-passes) were clocked by LRCLK, so their
  2-register read latency was **2 frames** (the measured `echo_time + 2`). They now
  run on `sys_clk` with **clock enable = `en_rise`**, which keeps exactly that latency.
* **ROMs** (distortion curves, LFO tables) and the tremolo multiplier already ran on
  the 18.432 MHz clock; they move to `sys_clk` unchanged.
* **Verification:** the v1 effect chain's outputs are recorded for about 30 presets
  (every effect, curve, waveform, room, combos, a mid-stream parameter change)
  on PRBS + sine + impulse stimuli. B1 must reproduce them bit for bit.

## B2: I²S core (`i2s_core.vhd`)

* **FPGA is I²S master**: a 10-bit frame counter on `sys_clk` makes BCLK (÷16),
  LRCLK (÷1024), `sample_tick` and `half_tick`. Codec in slave mode, I²S, 24-bit.
* RX: ADCDAT is sampled one `sys_clk` before the BCLK rising edge it belongs to
  (the codec drives it on the falling edge, 8 `sys_clk` = 163 ns earlier).
  24 bits after the 1-bit I²S delay; left while LRCLK = 0.
* TX: DACDAT changes with the BCLK falling edge, MSB one BCLK after the LRCLK edge.
* Ports: `rx_left/rx_right(23:0)` (valid at `sample_tick`),
  `tx_left/tx_right(23:0)` (latched at `sample_tick`), `sample_tick`, `half_tick`.
* The effect chain stays 16-bit in step B (it takes the top 16 bits; outputs are
  sign-extended to 24). Its width grows in step C. The right channel is passed
  through dry for now (mono effects).
* Verification: cocotb with a WM8731 **slave** model (samples DACDAT on BCLK
  rising, drives ADCDAT on falling); stereo bypass bit-exact at 24 bits; checks
  of BCLK/LRCLK frequencies and of the I²S bit alignment.

## B3: UART control block

### Physical
115200 baud 8N1 (generic), same GPIO_0 pins as v1 (RX = D0, TX = D1).

### Frame format (host → FPGA)

| Byte | Content |
|------|---------|
| 0 | `0xA5` sync |
| 1 | command |
| 2 | address |
| 3 | data high |
| 4 | data low |
| 5 | CRC-8 (poly 0x07) over bytes 1..4 |

| Command | Meaning | Reply |
|---------|---------|-------|
| `0x01` WRITE | write register `address` | ACK |
| `0x02` READ | read register `address` | ACK + data |
| `0x03` CODEC | I²C write to the codec: address = codec register (7-bit), data = 9-bit value | ACK when the I²C transfer is done |
| `0x04` PING | | ACK + version |

**Reply (FPGA → host):** `0x5A`, status (`0x00` OK, `0x01` CRC error, `0x02` bad
command/address, `0x03` I²C NAK), data high, data low, CRC-8.

**Robustness:** the parser hunts for `0xA5`. A frame with a bad CRC is NAKed, and a
partial frame is dropped after a 10 ms timeout. A lost byte therefore costs at most
one frame, unlike v1, where it shifted every frame that followed.

### Register map v2 (16-bit registers, 8-bit address)

| Address | Register | Access |
|---------|----------|--------|
| 0x00–0x0E | effect registers, same meaning as v1 ([register_map.md](register_map.md)) | R/W |
| 0x10 | `VERSION` (e.g. 0x0200) | R |
| 0x11 | `STATUS`: I²S locked, frame errors, codec init done | R |
| 0x12 / 0x13 | input / output peak level (left), decaying | R |
| 0x14 | `CONTROL`: soft reset, re-run codec init, mute | W |

The register file sits behind a simple bus (`addr`, `wdata`, `we`, `rd`, `rdata`).
In phase 3 the HPS AXI bridge connects to the same bus.

## B4: I²C master + codec init sequencer

* Bit-level I²C master (about 100 kHz from `sys_clk`), write-only plus ACK check;
  it drives `I2C_SCLK` and `I2C_SDAT` (open drain).
* The init ROM holds v1's codec settings (R15 reset, R0..R8, R16..R18, wait,
  R9 active). It runs automatically after reset and on `CONTROL`.
* An arbiter serves host CODEC commands once init has finished.

## B5: top level and board bring-up

* `top_v2.vhd`: PLL (`altera_pll` instantiated directly, no Platform Designer),
  reset synchroniser, I²S core, effect chain, UART block, I²C master.
* Removed: `my_audio.qsys`, Nios II, SDRAM controller, BSP/firmware.
  The SDRAM pins stay unused.
* The `v1` branch keeps the Nios II version.
* **Host tool** `tools/gme_ctl.py` (Python, pyserial): ping, read/write registers,
  codec writes, effect presets. It replaces the C# GUI until the phase-3 web UI exists.
* **Expected resources:** logic and RAM drop. The Nios II/e, SDRAM controller and
  interconnect go away; the UART/I²C block adds a few hundred ALMs.

## Results

### B1 (effect chain on sys_clk + strobes)
* **cocotb `test_ref`:** 27 presets × 6000 frames (every effect, distortion curve,
  tremolo waveform, reverb room, chorus/echo variants, combos, mid-stream
  parameter changes) are **bit-exact** to the v1 recordings in `sim/cocotb/ref/`.
* **ModelSim with Intel's `altera_mf`:** 16 presets through `tb_fx_wav`, v1 RTL vs
  B1 RTL, give **identical output files**. This confirms the RAM clock-enable
  wrappers on the real Intel models.
* The IP models gained `clocken` and were re-proven equivalent to `altera_mf`
  with a random clock enable (0 mismatches).
* `audio_processor.vhd` (v1 I²S path, kept until B5) derives the strobes from
  the synchronised LRCLK.

### B2 (`i2s_core.vhd`)
* cocotb `test_i2s` against a WM8731 slave model: BCLK = clk/16 with 50 % duty,
  LRCLK = clk/1024 changing only on BCLK falling edges, strobes 512 clocks apart;
  24-bit stereo receive, transmit and ADC→DAC loopback **bit-exact**
  (incl. 0x800000 / 0x7FFFFF).

### B3 (UART control block: `uart_rx`, `uart_tx`, `ctrl_uart`, `reg_file`, `ctrl_block`)
* cocotb `test_ctrl` with a Python UART host (1.536 Mbaud for speed, and ping at the
  real 115200): all 15 effect registers written and read back, VERSION/STATUS/levels,
  bad CRC / bad address / unknown command rejected, recovery after noise and a
  truncated frame, CODEC requests (9-bit data), NAK and busy reporting.

### B4 (`i2c_master`, `codec_ctrl`)
* cocotb `test_codec` with a Python I²C slave on the open-drain bus: the exact
  15-write init sequence (R7 = 0x00A slave/I²S/24-bit, R8 = 0x000 256·fs),
  every byte ACKed, SCL exactly 4 × 123 clocks (99.9 kHz), host writes, NAK
  reporting, re-init.

### B5 (`gme_core`, `top_v2`, `pll_sys.v`, `top_v2.sdc`, `tools/gme_ctl.py`)
* cocotb `test_system` on `gme_core` with all three external models (I²S codec,
  I²C codec, UART host): boot + codec init → STATUS/VERSION over UART → **dry audio
  bit-exact end to end** (latency 7 frames); overdrive enabled over UART →
  bit-exact to the reference model; level meters; mute; host codec writes.
* **Quartus Prime Lite 18.1 full compile** of `top_v2`: 0 errors, **timing met**
  (sys_clk 49.15 MHz, worst setup slack +11.4 ns, hold +0.13 ns, 0 unconstrained
  paths). Resources: **1,244 ALMs (4 %)** (v1 with Nios II/e: 1,861; original:
  3,575), 324 M10K, 35 DSP, 1 PLL.
* Removed from `main` (still on the `v1` branch): Platform Designer system, Nios II
  software, `RegistersControl`, v1 I²S controllers + FIFO, the ModelSim I²S
  testbench, the C# GUI.
* `tools/gme_ctl.py`: its frames are byte-identical to those of the cocotb host that
  drives the RTL. Hardware use is untested.
