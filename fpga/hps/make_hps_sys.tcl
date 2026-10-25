# -----------------------------------------------------------------------------
# make_hps_sys.tcl - build fpga/hps_sys.qsys from Terasic's DE1-SoC GHRD.
#
#   cd fpga && qsys-script --script=hps/make_hps_sys.tcl
#
# Keeps the GHRD's HPS configuration (DDR3, HPS I/O pin-mux, clocks), which the
# preloader and Linux on the Terasic SD card expect. Removes all FPGA-side
# peripherals and adds one Avalon-MM bridge on the lightweight HPS-to-FPGA
# bridge (0xFF200000), exported to the FPGA logic (gme_core's register file).
# Everything runs on sys_clk (49.152 MHz) from our PLL.
# -----------------------------------------------------------------------------
package require -exact qsys 18.1

load_system hps/ghrd_soc_system.qsys

foreach inst {button_pio dipsw_pio led_pio jtag_uart master_secure master_non_sec
              onchip_memory2_0 sysid_qsys intr_capturer_0} {
  remove_instance $inst
}
foreach ifc {button_pio_external_connection dipsw_pio_external_connection
             led_pio_external_connection hps_0_f2h_cold_reset_req
             hps_0_f2h_debug_reset_req hps_0_f2h_warm_reset_req
             hps_0_f2h_stm_hw_events hps_0_h2f_cold_reset
             hps_0_h2f_warm_reset_handshake} {
  catch {remove_interface $ifc}
}

remove_connection clk_0.clk/hps_0.f2h_axi_clock
remove_connection clk_0.clk/hps_0.h2f_axi_clock

# HPS: only the lightweight bridge to the FPGA, no full bridges, no FPGA resets/irqs
set_instance_parameter_value hps_0 F2S_Width 0
set_instance_parameter_value hps_0 S2F_Width 0
set_instance_parameter_value hps_0 LWH2F_Enable true
set_instance_parameter_value hps_0 F2SCLK_COLDRST_Enable false
set_instance_parameter_value hps_0 F2SCLK_DBGRST_Enable false
set_instance_parameter_value hps_0 F2SCLK_WARMRST_Enable false
set_instance_parameter_value hps_0 F2SINTERRUPT_Enable false
set_instance_parameter_value hps_0 STM_Enable false

set_instance_parameter_value clk_0 clockFrequency 49152000

# Avalon-MM bridge: 32-bit data, 256-byte span (64 word registers)
add_instance gme_bridge altera_avalon_mm_bridge
set_instance_parameter_value gme_bridge DATA_WIDTH 32
set_instance_parameter_value gme_bridge SYMBOL_WIDTH 8
set_instance_parameter_value gme_bridge ADDRESS_WIDTH 8
set_instance_parameter_value gme_bridge ADDRESS_UNITS SYMBOLS
set_instance_parameter_value gme_bridge MAX_BURST_SIZE 1
set_instance_parameter_value gme_bridge MAX_PENDING_RESPONSES 1
set_instance_parameter_value gme_bridge PIPELINE_COMMAND 0
set_instance_parameter_value gme_bridge PIPELINE_RESPONSE 0

add_connection clk_0.clk gme_bridge.clk
add_connection clk_0.clk_reset gme_bridge.reset
add_connection hps_0.h2f_lw_axi_master gme_bridge.s0
set_connection_parameter_value hps_0.h2f_lw_axi_master/gme_bridge.s0 baseAddress 0x0000

add_interface gme_regs avalon start
set_interface_property gme_regs EXPORT_OF gme_bridge.m0

save_system ../hps_sys.qsys   ;# path is relative to the loaded system (hps/)
