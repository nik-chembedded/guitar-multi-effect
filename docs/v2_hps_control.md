# v2: HPS control (Linux on the ARM)

**Status:** RTL and Platform Designer system done, cocotb tests pass, Quartus build
meets timing. Board test pending.

The UART control block of step B is replaced by the ARM HPS: Linux on the
DE1-SoC writes the effect registers through the **lightweight HPS-to-FPGA bridge**.
This is the control part of phase 3 (step F), brought forward. The UART version is
kept at the tag `v2-uart`.

## Architecture

```
 ARM Cortex-A9 (Linux, Terasic SD card)
   │  /dev/mem  0xFF200000 + 4·n           tools/gme_hps.py
   ▼
 lightweight HPS-to-FPGA bridge (AXI, hard IP)
   │  hps_sys.qsys: AXI → Avalon-MM interconnect, gme_bridge (Avalon-MM bridge, 32-bit, 256 B)
   │  clocked by sys_clk 49.152 MHz → one clock domain, no clock crossing in our logic
   ▼
 gme_core.ctrl_avmm  (Avalon-MM slave: readdatavalid 1 cycle after read, no wait states)
   ├── reg_file   0x00..0x14  (effect, status, CONTROL registers, unchanged)
   └── CODEC      0x15        (one WM8731 write over I²C, busy/NAK/dropped flags)
   byte enables honoured (CPython's struct '<I' on /dev/mem stores byte by byte)
```

| File | What |
|------|------|
| `fpga/hps/ghrd_soc_system.qsys` | Terasic DE1-SoC GHRD system (System CD 5.1.3, Quartus 16.0): source of the HPS configuration |
| `fpga/hps/make_hps_sys.tcl` | builds `fpga/hps_sys.qsys` from it: keeps `hps_0` (DDR3, HPS I/O, clocks), removes all FPGA peripherals, disables the full bridges / FPGA resets / interrupts, adds `gme_bridge` on the lightweight bridge |
| `fpga/hps_sys.qsys` | the resulting Platform Designer system (generated HDL in `fpga/hps_sys/`, not in git) |
| `fpga/rtl/ctrl_avmm.vhd` | Avalon-MM slave + `reg_file` + CODEC register |
| `fpga/rtl/top_v2.vhd` | top level: PLL, `hps_sys`, `gme_core`; HPS pin names as in the GHRD |
| `fpga/My_Audio.qsf` | HPS pin I/O standards / termination copied from the GHRD (HPS pins are dedicated: no locations) |
| `tools/gme_hps.py` | Linux tool on the board (Python 2.7 or 3) |
| `sim/cocotb/test_avmm.py` | cocotb tests of `ctrl_avmm` (Avalon master model) |

Why the GHRD's HPS settings: the preloader and U-Boot on the Terasic SD card
configure DDR3 and the HPS pin-mux at boot; the FPGA design must match them. No
new Linux, preloader or device tree is needed.

The HPS reset output (`h2f_reset`) does not reset the audio, so a Linux reboot
does not interrupt the sound. `KEY0` still resets the FPGA logic.

## Build

```bash
cd fpga
qsys-script --script=hps/make_hps_sys.tcl          # only after changing the tcl (hps_sys.qsys is in git)
qsys-generate hps_sys.qsys --synthesis=VERILOG --output-directory=hps_sys \
              --family="Cyclone V" --part=5CSEMA5F31C6
quartus_sh --flow compile My_Audio
quartus_cpf -c -o bitstream_compression=off output_files/my_audio.sof output_files/soc_system.rbf
```

Results (Quartus Prime Lite 18.1): 0 errors, 1,254 ALMs (4 %), 324 M10K, 35 DSP;
**timing met** in all corners (worst setup slack +1.73 ns, in the DDR3 PHY; hold +0.143 ns;
our sys_clk domain +10.7 ns). The critical warnings "no exact pin location for 72 pins"
and "1 RZQ pin" are the dedicated HPS DDR3 pins; Terasic's GHRD build reports the same.
The unconstrained ports are HPS peripheral pins (timed by the hard IP), as in the GHRD.

`soc_system.rbf` is uncompressed (7.0 MB), the same format as Terasic's SD-card images.

## Board bring-up

**1. JTAG first (nothing on the SD card changes).** Boot the board as usual (Terasic's
rbf loads), log in as root, then program `output_files/my_audio.sof` from the Quartus
Programmer (device 5CSEMA5; leave SOCVHPS alone). Linux keeps running.
Don't touch `0xFF200000` while programming.

Copy the tool to the board (`scp tools/gme_hps.py root@<board-ip>:`, or put it on the
SD card's FAT partition and `mount /dev/mmcblk0p1 /mnt`), then:

```
# python gme_hps.py status
version 0x0201, status 0x0005: codec init done, codec NAK no, PLL locked yes
effects none, mute off, level in 812, out 812
# python gme_hps.py preset crunch
# python gme_hps.py meter
```

**2. Boot from the SD card.** Rename the card's `soc_system.rbf` to `soc_system_terasic.rbf`
(keep it), copy our `output_files/soc_system.rbf` next to it. U-Boot loads it at boot
and enables the bridges. To go back, restore the Terasic file. If U-Boot cannot load
the uncompressed file, `soc_system_compressed.rbf` is a fallback to try.

## Tests

`sim/cocotb/test_avmm.py` (5 tests) drives the slave like the bridge does: VERSION /
STATUS / levels; all 15 effect registers with random 32-bit words (bits 31..16 ignored);
unknown and read-only addresses; CONTROL mute + codec re-init pulse; CODEC write with
busy, NAK and dropped flags; byte and halfword stores with garbage on the other lanes
(registers merge per byte, exactly one correct codec write). `test_system.py` runs the whole `gme_core` with the same
Avalon master: codec init → STATUS/VERSION → dry audio bit-exact → overdrive set over the
bridge bit-exact → mute → output meter decays to 0 → CODEC write reaches the I²C bus.

## Board test log

* 2026-10-25, JTAG `.sof` with Linux running: `status`/`dump` correct (VERSION 0x0201,
  STATUS 0x0005), all presets audible. Found two bugs, fixed in the next build:
  * `codec` gave "write dropped" and the sound got quiet: Python's `struct.pack_into('<I')`
    stores byte by byte, the slave ignored byte enables and started the I²C transfer on
    the first byte (stale register number). Fix: byte enables in `ctrl_avmm`, CODEC
    transfer on the write that contains byte 1; `gme_hps.py` uses 32-bit ctypes accesses.
  * level meters stuck at 255: `p - p/256` stops decaying below 256. Fix: decay by 1 there.
