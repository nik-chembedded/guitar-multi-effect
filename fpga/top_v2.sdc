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
# Blocks with a per-clock sequencer or pipeline (RAM read -> capture -> compute
# in consecutive clocks: mod_delay, the D2 echo and the D3 cabinet FIR / its crossfade CAB_left, the D4 reverb REVERB_left,
# the D5 dynamics pipeline DYN_left|u_dyn (10 stages) and the EQ biquads EQ_left|u_eq (2 stages per
# section)) are excluded and keep full single-cycle constraints - a multicycle relaxation would hide
# real 1-clock paths. The D5 stage crossfades (DYN_left|u_fade, EQ_left|u_fade: a counter that moves on
# sample_tick and a combinational mix) are plain fx logic and stay in the multicycle group.
set seqblk [get_registers {*|u_fx|CHORUS_left|* *|u_fx|ECHO_left|* *|u_fx|CAB_left|* *|u_fx|REVERB_left|* *|u_fx|DYN_left|u_dyn|* *|u_fx|EQ_left|u_eq|*}]
set fx   [remove_from_collection [get_registers {*|u_fx|*}] $seqblk]
set rx   [get_registers {*|u_i2s|rx_l_out*}]   ;# right channel unused (mono effects)
set regs [get_registers {*|u_ctrl|u_regs|regs*}]
set sm   [get_registers {*u_sm_*|y*}]             ;# smoothed parameters (step C), update on sample_tick. NB: the instance is "param_smooth:smooth_on:u_sm_xxx" (generate label), so there is no "|" before u_sm_ (the old *|u_sm_* matched nothing)

set_multicycle_path -setup -end 16 -from $fx   -to $fx
set_multicycle_path -hold  -end 15 -from $fx   -to $fx
set_multicycle_path -setup -end 16 -from $rx   -to $fx
set_multicycle_path -hold  -end 15 -from $rx   -to $fx
set_multicycle_path -setup -end 16 -from $regs -to $fx
set_multicycle_path -hold  -end 15 -from $regs -to $fx
set_multicycle_path -setup -end 16 -from $sm   -to $fx
set_multicycle_path -hold  -end 15 -from $sm   -to $fx
# chain output -> I2S transmit latch (cnt 0) and level meters (sample_tick)
set_multicycle_path -setup -end 16 -from $fx   -to [get_registers {*|u_i2s|tx_* *|peak_*}]
set_multicycle_path -hold  -end 15 -from $fx   -to [get_registers {*|u_i2s|tx_* *|peak_*}]

# The strobe-loaded OUTPUT registers of those sequencer blocks (data_out loads only
# on the block's strobe) are a different case: everything feeding them (the
# previous stage's strobe registers and crossfades, the cabinet output, the
# block's own result computed a few clocks after the previous strobe) settles
# hundreds of clocks before that strobe, so these paths get the multicycle too.
# Without this, distortion -> cabinet crossfade -> mod_delay mix (three multipliers
# in one combinational path) was timed as a 1-clock path (+0.58 ns in D4).
set seqout [get_registers {*|u_fx|CHORUS_left|data_out* *|u_fx|ECHO_left|data_out* *|u_fx|REVERB_left|data_out*}]
set_multicycle_path -setup -end 16 -to $seqout
set_multicycle_path -hold  -end 15 -to $seqout
# D5: the dynamics and EQ blocks are NOT in seqout: their data_out loads the last pipeline result
# in the clock after the previous register (prod -> sat -> data_out in dynamics, y3 in eq3), a real
# 1-clock path that a multicycle would hide. The paths leaving them (dyn data_out -> overdrive,
# eq data_out -> crossfade) are met as ordinary single-cycle paths.

# The data input of the mod_delay line RAM (D5): the RAM is written only on the strobe
# (wren = en_rise and enable), and the data cone behind it is the chain stages in front of
# it: dist_fade -> cabinet crossfade -> EQ crossfade -> mod_delay input sum. All their
# registers change at sample_tick / half_tick + a few clocks and the RAM samples at the
# next half_tick (>= 448 clocks later), so the cone is a multicycle path like the seqout
# registers. Without this, three crossfade multipliers in series (dist, cabinet, EQ) were timed as one clock
# (D5, first compile: -4.4 ns).
set seqram [get_registers {*|u_fx|CHORUS_left|u_line|*~porta_datain_reg* *|u_fx|CHORUS_left|u_line|*~PORT_A_DATA_IN_*}]
set_multicycle_path -setup -end 16 -to $seqram
set_multicycle_path -hold  -end 15 -to $seqram

# ---- I/O --------------------------------------------------------------------------
# Codec audio: BCLK/LRCLK/DACDAT are registered outputs, ADCDAT is sampled 8
# sys_clk cycles (163 ns) after the BCLK edge that launches it - large margins
# by construction, so no I/O timing is enforced.
set_false_path -to   [get_ports {AUD_BCLK AUD_ADCLRCK AUD_DACLRCK AUD_DACDAT AUD_XCK}]
set_false_path -from [get_ports {AUD_ADCDAT}]
# Slow / asynchronous: I2C (100 kHz), push button, LEDs
set_false_path -from [get_ports {KEY0 FPGA_I2C_SDAT FPGA_I2C_SCLK}]
set_false_path -to   [get_ports {FPGA_I2C_SDAT FPGA_I2C_SCLK LEDR[*]}]
