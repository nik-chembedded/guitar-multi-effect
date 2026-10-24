# -----------------------------------------------------------------------------
# My_Audio.sdc - timing constraints for the guitar multi-effect (DE1-SoC)
#
# Before this file existed, TimeQuest only knew the JTAG clock: the 50 MHz
# system clock, the Nios II / SDRAM PLL clocks and the audio clocks were not
# analysed at all.
# -----------------------------------------------------------------------------

# ---- Board clock and PLL outputs (Nios II, SDRAM, codec MCLK, I2C) ----------
create_clock -name CLOCK_50 -period 20.000 [get_ports {clk}]
derive_pll_clocks
derive_clock_uncertainty

# ---- Audio codec clocks -----------------------------------------------------
# The codec is I2S master: MCLK 18.432 MHz -> BCLK = MCLK/4 = 4.608 MHz,
# LRCLK = 48 kHz. The effect datapath is clocked directly by DACLRCLK (and its
# inversion), the I2S shift registers by BCLK.
create_clock -name AUD_BCLK   -period 217.014   [get_ports {AUD_BCLK}]
create_clock -name AUD_LRCLK  -period 20833.333 [get_ports {AUD_DACLRCLK}]

# Codec outputs change on the falling edge of BCLK and are sampled on the
# rising edge by the FPGA (and vice versa for DACDAT). Generous budgets: a
# BCLK half period is ~108 ns.
set_input_delay  -clock AUD_BCLK -clock_fall -max 20 [get_ports {AUD_ADCDAT AUD_ADCLRCLK AUD_DACLRCLK}]
set_input_delay  -clock AUD_BCLK -clock_fall -min 0  [get_ports {AUD_ADCDAT AUD_ADCLRCLK AUD_DACLRCLK}]
set_output_delay -clock AUD_BCLK -max 20  [get_ports {AUD_DACDAT}]
set_output_delay -clock AUD_BCLK -min -10 [get_ports {AUD_DACDAT}]

# ---- Clock domain crossings -------------------------------------------------
# The effect parameters are written by the Nios II (system clock) and are
# quasi-static from the point of view of the 48 kHz datapath; the datapath
# also hands samples to logic on the codec MCLK (ROM lookups, multipliers)
# and is held stable for a whole sample period. These crossings are not
# synchronised in RTL (known limitation, see docs/FIXES.md), so the domains
# are declared asynchronous here instead of reporting false violations.
set_clock_groups -asynchronous \
    -group [get_clocks {CLOCK_50 *sys_sdram_pll*}] \
    -group [get_clocks {*audio_pll*}] \
    -group [get_clocks {AUD_BCLK}] \
    -group [get_clocks {AUD_LRCLK}] \
    -group [get_clocks {altera_reserved_tck}]

# ---- Slow / asynchronous I/O ------------------------------------------------
set_false_path -from [get_ports {reset_n LR_RESET od_enable tremolo_enable echo_enable UART_RX i2c_sda}]
set_false_path -to   [get_ports {UART_TX i2c_scl i2c_sda aud_xck}]
