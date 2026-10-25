# -----------------------------------------------------------------------------
# top_v2.sdc - timing constraints for v2 (one system clock, FPGA = I2S master)
# -----------------------------------------------------------------------------

create_clock -name CLOCK_50 -period 20.000 [get_ports {CLOCK_50}]
derive_pll_clocks
derive_clock_uncertainty

# ---- Effect chain: multicycle data paths ---------------------------------------
# The v1 effect arithmetic is unpipelined but its registers only advance on
# sample_tick / half_tick (>= 512 sys_clk cycles apart), so data paths into,
# inside and out of the chain get 16 cycles (325 ns). The strobes themselves are
# NOT covered (they come from u_i2s and must stay single-cycle).
set fx   [get_registers {*|u_fx|*}]
set rx   [get_registers {*|u_i2s|rx_l_out*}]   ;# right channel unused (mono effects)
set regs [get_registers {*|u_ctrl|u_regs|regs*}]

set_multicycle_path -setup -end 16 -from $fx   -to $fx
set_multicycle_path -hold  -end 15 -from $fx   -to $fx
set_multicycle_path -setup -end 16 -from $rx   -to $fx
set_multicycle_path -hold  -end 15 -from $rx   -to $fx
set_multicycle_path -setup -end 16 -from $regs -to $fx
set_multicycle_path -hold  -end 15 -from $regs -to $fx
# chain output -> I2S transmit latch (cnt 0) and level meters (sample_tick)
set_multicycle_path -setup -end 16 -from $fx   -to [get_registers {*|u_i2s|tx_* *|peak_*}]
set_multicycle_path -hold  -end 15 -from $fx   -to [get_registers {*|u_i2s|tx_* *|peak_*}]

# ---- I/O --------------------------------------------------------------------------
# Codec audio: BCLK/LRCLK/DACDAT are registered outputs, ADCDAT is sampled 8
# sys_clk cycles (163 ns) after the BCLK edge that launches it - large margins
# by construction, so no I/O timing is enforced.
set_false_path -to   [get_ports {AUD_BCLK AUD_ADCLRCK AUD_DACLRCK AUD_DACDAT AUD_XCK}]
set_false_path -from [get_ports {AUD_ADCDAT}]
# Slow / asynchronous: I2C (100 kHz), push button, LEDs
set_false_path -from [get_ports {KEY0 FPGA_I2C_SDAT FPGA_I2C_SCLK}]
set_false_path -to   [get_ports {FPGA_I2C_SDAT FPGA_I2C_SCLK LEDR[*]}]
