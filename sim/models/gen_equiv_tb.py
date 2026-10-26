#!/usr/bin/env python3
"""
gen_equiv_tb.py - generate an equivalence testbench that compares every Intel
IP wrapper (library "intel", compiled from fpga/ip with altera_mf) against its
behavioural replacement (library "model", compiled from sim/models/ip).

Same random stimulus into both, every output compared on every clock. Writes
sim/models/tb_ip_equiv.vhd. Run with sim/models/run_equiv.sh (ModelSim).
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IP_DIR = os.path.join(ROOT, "fpga", "ip")
OUT = os.path.join(ROOT, "sim", "models", "tb_ip_equiv.vhd")


def param(text, name):
    m = re.search(r"\b%s\s*=>\s*\"?([^\",\s)]+)\"?" % name, text)
    return m.group(1) if m else None


roms, rams, fifos = [], [], []
for fn in sorted(os.listdir(IP_DIR)):
    if not fn.endswith(".vhd"):
        continue
    s = open(os.path.join(IP_DIR, fn), encoding="latin-1").read()
    n = fn[:-4]
    mode = param(s, "operation_mode")
    if mode == "ROM":
        roms.append((n, int(param(s, "width_a")), int(param(s, "widthad_a")),
                     int(param(s, "numwords_a")), re.search(r"\brden\s*:\s*IN", s, re.I) is not None))
    elif mode == "DUAL_PORT":
        rams.append((n, int(param(s, "width_a")), int(param(s, "widthad_a")),
                     param(s, "read_during_write_mode_mixed_ports"), ""))
    elif param(s, "lpm_numwords"):
        fifos.append((n, int(param(s, "lpm_width"))))

# generic delay-line RAM of the effects (fpga/rtl/fx_dpram.vhd, step C): every
# width / depth used (echo 2^15 and 2^16, comb 2^11, all-pass 2^12, chorus 2^10)
for w, aw in ((24, 15), (16, 16), (24, 11), (24, 12), (24, 10), (16, 10)):
    rams.append(("fx_dpram", w, aw, "OLD_DATA", " generic map (WIDTH => %d, ADDR_W => %d)" % (w, aw)))

# cabinet coefficient RAM (fpga/rtl/cab_coef_ram.vhd, step D3): mixed width, 18 bit
# write / 72 bit read, power-up content from random test .mif files cab_eq_<ADDR_W>.mif
# (ADDR_W = log2(TAPS) + 1: 12 for TAPS = 2048, 7 for TAPS = 64; DEPTH = full RAM, both banks)
cabs = [(12, 2), (7, 2)]

import random as _random
_r = _random.Random(2025)
for aw, _ in cabs:
    with open(os.path.join(ROOT, "sim", "models", "cab_eq_%d.mif" % aw), "w", newline="\n") as f:
        f.write("WIDTH=18;\nDEPTH=%d;\n\nADDRESS_RADIX=UNS;\nDATA_RADIX=UNS;\n\nCONTENT BEGIN\n" % 2 ** aw)
        for a in range(2 ** aw):
            f.write("\t%d\t:\t%d;\n" % (a, _r.randrange(1 << 18)))
        f.write("END;\n")

decl, inst, check = [], [], []
vdecl = ["    variable cw, cr : integer;"]
for i, (n, w, aw, depth, has_rden) in enumerate(roms):
    decl.append("  signal r%d_a : std_logic_vector(%d downto 0) := (others => '0');" % (i, aw - 1))
    decl.append("  signal r%d_qi, r%d_qm : std_logic_vector(%d downto 0);" % (i, i, w - 1))
    rd = "rden => rden, " if has_rden else ""
    inst.append("  r%d_i : entity intel.%s port map (address => r%d_a, clock => clk, %sq => r%d_qi);" % (i, n, i, rd, i))
    inst.append("  r%d_m : entity model.%s port map (address => r%d_a, clock => clk, %sq => r%d_qm);" % (i, n, i, rd, i))
    check.append("      r%d_a <= std_logic_vector(to_unsigned(rnd(%d), %d));" % (i, depth, aw))
    check.append("      cmp(\"%s\", r%d_qi, r%d_qm, false);" % (n, i, i))
for i, (n, w, aw, rdw, gen) in enumerate(rams):
    decl.append("  signal m%d_wa, m%d_ra : std_logic_vector(%d downto 0) := (others => '0');" % (i, i, aw - 1))
    decl.append("  signal m%d_d : std_logic_vector(%d downto 0) := (others => '0');" % (i, w - 1))
    decl.append("  signal m%d_qi, m%d_qm : std_logic_vector(%d downto 0);" % (i, i, w - 1))
    for lib, suf in (("intel", "i"), ("model", "m")):
        inst.append("  m%d_%s : entity %s.%s%s port map (clock => clk, data => m%d_d, rdaddress => m%d_ra, "
                    "wraddress => m%d_wa, wren => wren, clocken => cen, q => m%d_q%s);"
                    % (i, suf, lib, n, gen, i, i, i, i, suf))
    # small address window so reads hit written words and collide with writes
    check.append("      m%d_wa <= std_logic_vector(to_unsigned(rnd(64), %d));" % (i, aw))
    check.append("      if rnd(4) = 0 then m%d_ra <= m%d_wa; else m%d_ra <= std_logic_vector(to_unsigned(rnd(64), %d)); end if;" % (i, i, i, aw))
    check.append("      m%d_d <= std_logic_vector(to_unsigned(rnd(2 ** %d), %d));" % (i, min(w, 30), w))
    # DONT_CARE: Intel model may give X on a same-address read/write; skip those
    check.append("      cmp(\"%s%s\", m%d_qi, m%d_qm, %s);" % (n, "_%dx%d" % (w, aw) if gen else "", i, i,
                                                       "true" if rdw == "DONT_CARE" else "false"))

for i, (aw, ll) in enumerate(cabs):
    ww = 18 * 2 ** ll
    decl.append("  signal c%d_wa : std_logic_vector(%d downto 0) := (others => '0');" % (i, aw - 1))
    decl.append("  signal c%d_ra : std_logic_vector(%d downto 0) := (others => '0');" % (i, aw - ll - 1))
    decl.append("  signal c%d_d : std_logic_vector(17 downto 0) := (others => '0');" % i)
    decl.append("  signal c%d_qi, c%d_qm : std_logic_vector(%d downto 0);" % (i, i, ww - 1))
    vdecl.append("    variable k%d_1, k%d_2 : boolean := true;" % (i, i))
    for lib, suf in (("intel", "i"), ("model", "m")):
        inst.append("  c%d_%s : entity %s.cab_coef_ram generic map (WIDTH => 18, LANES_LOG2 => %d, ADDR_W => %d, "
                    "INIT_FILE => \"cab_eq_%d.mif\") port map (clock => clk, wren => wren, wraddress => c%d_wa, "
                    "data => c%d_d, rdaddress => c%d_ra, q => c%d_q%s);" % (i, suf, lib, ll, aw, aw, i, i, i, i, suf))
    check += [
        "      cw := rnd(2) * %d + rnd(64);" % 2 ** (aw - 1),
        "      c%d_wa <= std_logic_vector(to_unsigned(cw, %d));" % (i, aw),
        "      if rnd(2) = 0 then cr := (cw / %d + rnd(2)) mod %d; else cr := rnd(%d); end if;"
        % (2 ** ll, 2 ** (aw - ll), 2 ** (aw - ll)),
        "      c%d_ra <= std_logic_vector(to_unsigned(cr, %d));" % (i, aw - ll),
        "      c%d_d <= std_logic_vector(to_unsigned(rnd(%d), 18));" % (i, 2 ** 18),
        # q appears 2 clocks after the address; DONT_CARE: skip when the word read is being written
        "      if not k%d_2 then cmp(\"cab_coef_ram_%d\", c%d_qi, c%d_qm, false); else cskips := cskips + 1; end if;"
        % (i, aw, i, i),
        "      k%d_2 := k%d_1; k%d_1 := (cr = cw / %d);" % (i, i, i, 2 ** ll),
    ]

tb = """-- Generated by sim/models/gen_equiv_tb.py - do not edit.
-- Equivalence test: Intel altera_mf IP wrappers vs behavioural models.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;
library intel, model;

entity tb_ip_equiv is
  generic (CYCLES : positive := 20000);
end entity;

architecture sim of tb_ip_equiv is
  signal clk  : std_logic := '0';
  signal rclk : std_logic := '0';
  signal done : boolean := false;
  signal rden : std_logic := '1';
  signal wren : std_logic := '0';
  signal cen  : std_logic := '1';
{decl}
{fifo_decl}
begin
  clk  <= not clk  after 5 ns when not done else '0';
  rclk <= not rclk after 7 ns when not done else '0';   -- unrelated FIFO read clock

{inst}
{fifo_inst}

  stim : process
    variable s1 : positive := 7;
    variable s2 : positive := 99;
    variable r  : real;
    variable errors, xskips, cskips : natural := 0;
{vdecl}
    impure function rnd(n : positive) return natural is
    begin
      uniform(s1, s2, r);
      return integer(trunc(r * real(n))) mod n;
    end function;
    procedure cmp(name : string; a, b : std_logic_vector; skip_x : boolean) is
    begin
      if is_x(a) and skip_x then
        xskips := xskips + 1;
      elsif a /= b then
        if errors < 20 then
          report "MISMATCH " & name & " intel=" & to_hstring(a)
                 & " model=" & to_hstring(b) severity error;
        end if;
        errors := errors + 1;
      end if;
    end procedure;
  begin
    for c in 1 to CYCLES loop
      wait until rising_edge(clk);
      wait for 1 ns;
      if rnd(8) = 0 then rden <= '0'; else rden <= '1'; end if;
      if rnd(2) = 0 then wren <= '1'; else wren <= '0'; end if;
      if rnd(3) = 0 then cen <= '0'; else cen <= '1'; end if;
{check}
    end loop;
    wait for 200 ns;
    report "EQUIV: " & integer'image(errors) & " mismatches, " & integer'image(xskips)
           & " X outputs skipped (DONT_CARE collisions), "
           & integer'image(cskips) & " cab_coef_ram read/write collisions skipped, " & integer'image(CYCLES) & " cycles";
    if errors = 0 then report "RESULT: PASS ip_equiv"; else report "RESULT: FAIL ip_equiv"; end if;
    done <= true;
    std.env.stop;
    wait;
  end process;
{fifo_proc}
end architecture;
"""

with open(OUT, "w", newline="\n") as f:
    f.write(tb.format(decl="\n".join(decl), fifo_decl="",
                      inst="\n".join(inst), fifo_inst="",
                      check="\n".join(check), fifo_proc="", vdecl="\n".join(vdecl)))
print("wrote %s: %d ROMs, %d RAMs (%d FIFOs ignored)" %
      (os.path.relpath(OUT, ROOT), len(roms), len(rams), len(fifos)))
