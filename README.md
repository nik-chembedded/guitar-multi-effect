# Guitar Multi-Effect: FPGA (VHDL) + Nios II + PC control GUI

A real-time multi-effect processor for electric guitar, implemented in VHDL on an
Intel **Cyclone V** FPGA. A **Nios II** soft processor receives settings from a
Windows GUI over UART and writes them to the effect registers.

> **Target hardware:** Terasic **DE1-SoC** board,
> Cyclone V SE **5CSEMA5F31C6**, on-board WM8731-compatible audio codec,
> on-board 64 MB SDRAM (Nios II program memory).
> Tool chain: **Quartus Prime Lite 18.1** (incl. Platform Designer, Nios II EDS,
> ModelSim-Intel Starter Edition). Other Cyclone V boards need new pin
> assignments and possibly a different codec setup.

Originally a final project from my studies (2021–2022), now being cleaned up and
developed further.

## Effects

| Effect     | Implementation                                                          | Parameters |
|------------|-------------------------------------------------------------------------|------------|
| Overdrive  | Hard clipping at a threshold, then gain                                 | drive, gain |
| Distortion | Waveshaping with ROM transfer curves (soft / medium / heavy)            | type, mix |
| Chorus     | Modulated delay line (triangle LFO) with feedback                       | rate, depth, level |
| Tremolo    | Amplitude modulation by ROM LFO (sine 5/7/10/12/15 Hz, triangle, saw)   | waveform, depth |
| Echo       | Up to ~0.68 s delay line in block RAM with feedback                     | time, level, repeat |
| Reverb     | Schroeder reverb: 4 parallel comb filters + 2 series all-pass filters   | type (4 rooms), mix |

Signal chain: `ADC → Overdrive → Distortion → Chorus → Tremolo → Echo → Reverb → DAC`
(48 kHz, 16-bit, mono. The processed left channel is sent to both outputs.)

## Block diagram

```
                       DE1-SoC / Cyclone V
 PC GUI      UART     +--------------------------------------------------------------+
 (C#, .NET) ------->  | Nios II  --Avalon-MM-->  RegistersControl (15 x 16-bit regs)  |
 9600 8N1   GPIO_0    |   |  \--- I2C (PIO bit-bang) ---> codec config               |
                      |   SDRAM (program)                    | effect parameters      |
                      |                                       v                        |
 Guitar --> codec --I2S--> ADC_CONTROLLER -> FIFO -> FX_chain -> DAC_CONTROLLER --I2S--> codec --> Amp
            (WM8731)  |                                                              |
                      +--------------------------------------------------------------+
```

## Repository layout

```
fpga/                    Quartus project (My_Audio.qpf / .qsf)
  rtl/                   hand-written VHDL (top level, I2S, effects, register block)
  ip/                    Intel megafunction wrappers (FIFO, RAM, ROM) + .mif tables
  my_audio.qsys          Platform Designer system (Nios II, SDRAM, UART, PIO, PLLs)
  RegistersControl_hw.tcl  Platform Designer component for the register block
  software/
    audio_control/       Nios II application (UART command parser, codec init)
    audio_control_bsp/   BSP settings (settings.bsp); the BSP is regenerated
sim/                     ModelSim testbench (codec model + self-checking tests)
gui/                     Windows control GUI (C# WinForms, .NET 5)
docs/
  register_map.md        effect registers, field encodings, UART protocol
```

## Board setup (DE1-SoC)

| Signal               | Board                          | Notes |
|----------------------|--------------------------------|-------|
| `clk`                | CLOCK_50 (PIN_AF14)            | |
| `reset_n`            | SW0 (PIN_AB12)                 | up = run |
| `LR_RESET`           | SW1 (PIN_AC12)                 | **must be up**. Down clears the ADC deserializer. |
| `UART_RX`/`UART_TX`  | GPIO_0 D0 (AC18) / D1 (Y17)    | external **3.3 V** USB-UART adapter, 9600 8N1 |
| Audio in / out       | LINE IN (blue) / LINE OUT (green) | codec I/O is configured by the Nios II firmware |
| `od/tremolo/echo_enable` | SW9 / SW8 / SW7            | legacy, not used by the current FX chain |

## Building

1. **Generate the Platform Designer system** (or open `my_audio.qsys` and click *Generate HDL*):
   ```bash
   cd fpga
   qsys-generate my_audio.qsys --synthesis=VHDL --output-directory=my_audio
   ```
2. **Compile** in Quartus (`My_Audio.qpf`), or run `quartus_sh --flow compile My_Audio`.
3. **Build the Nios II software** from a *Nios II Command Shell*:
   ```bash
   cd fpga/software/audio_control
   ./create-this-app          # generates the BSP + Makefile and builds audio_control.elf
   ```
4. **Program and run:**
   ```bash
   nios2-configure-sof ../../output_files/My_Audio.sof
   make download-elf
   ```
5. Start the GUI (`gui/Audio_2.sln`, Visual Studio 2019+), choose the COM port in
   *Settings* and turn the effects on.

## Simulation

The testbench in `sim/` runs the complete audio path (I2S in → FIFO → FX chain →
I2S out) against a behavioural model of the codec, with one self-checking test per
effect. See [sim/README.md](sim/README.md).

```bash
MODELSIM_BIN=/path/to/modelsim_ase/win32aloem ./sim/run_sim.sh
```

## Status

Work in progress. Known issues are tracked in [docs/](docs/). The C# GUI is
kept as-is and will be replaced by a new GUI.

## Third-party code

* `fpga/software/audio_control/I2C.*`, `my_includes.h`, `my_types.h`, `debug.*`:
  Terasic reference code (see file headers for their terms).
* `fpga/ip/*` wrappers are generated by Intel Quartus MegaWizard / IP Catalog.
