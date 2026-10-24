# Behavioural models of the Intel IP

GHDL (and any simulator without Intel's `altera_mf` library) can't simulate
the megafunction wrappers in `fpga/ip/`. This folder provides drop-in
replacements: entities with the **same names and ports**, built from three
generic models.

| Model | Replaces | Behaviour (verified against `altera_mf`) |
|-------|----------|-----------------------------------------|
| `sim_rom.vhd` | `altsyncram` ROM (11 instances: distortion curves, LFO tables) | 2-clock latency (registered address + output); `rden` is a clock enable of the **address** register; output 0 before the first address; `.mif` initialisation |
| `sim_dpram.vhd` | `altsyncram` simple dual-port RAM (4: echo, chorus, comb, all-pass) | write on port A; read word fetched on the edge that registers `rdaddress`, **before** that edge's write (OLD_DATA); output after the next edge |
| `sim_dcfifo.vhd` | `dcfifo` (`my_fifo`) | same data order; empty/full flags without synchroniser delay |

`ip/*.vhd` is generated: run `python3 sim/models/gen_ip_models.py` after changing an
IP wrapper in `fpga/ip/`.

## Equivalence proof

`run_equiv.sh` compiles every Intel wrapper (with `altera_mf`, library `intel`)
and its model (library `model`) side by side in ModelSim. It drives both with
the same random stimulus and compares every output on every clock:

```bash
MODELSIM_BIN=/d/intelFPGA_lite/18.1/modelsim_ase/win32aloem PYTHON=python3 ./run_equiv.sh
```

Results:

* `tb_ip_equiv`: all 15 RAM/ROM instances, 20 000 random cycles (random addresses,
  toggling `rden`/`wren`, same-address read/write collisions): **0 mismatches**.
  Collisions on the three RAMs configured as `DONT_CARE` are skipped, because
  Intel's model outputs X there. The design never collides, since the delay taps
  are at least 2.
* `tb_fifo_equiv`: 3000 random words through both FIFOs on unrelated clocks:
  identical output sequence.

Two behaviours of the Intel models were only found by this test: `rden` gates the
address register rather than the output, and the OLD_DATA read happens on the
address-register edge. Both are now modelled.

## Using the models

* `sim/run_sim.sh` / `sim/run_wav.sh`: set `IP_MODELS=1` to compile these instead of `altera_mf`.
* GHDL / cocotb (v2 step A) always use them.
