// ----------------------------------------------------------------------------
// pll_sys.v  (v2 step B5)
// Fractional-N PLL, 50 MHz -> sys_clk 49.152 MHz (c0) and codec MCLK
// 12.288 MHz (c1), phase-aligned. Same altera_pll instantiation style that
// Quartus Prime 18.1 generates for Cyclone V (see the v1 audio_pll).
// ----------------------------------------------------------------------------
`timescale 1 ps / 1 ps
module pll_sys (
    input  wire refclk,     // 50 MHz
    input  wire rst,        // active high
    output wire sys_clk,    // 49.152 MHz
    output wire mclk,       // 12.288 MHz
    output wire locked
);
    altera_pll #(
        .fractional_vco_multiplier("true"),
        .reference_clock_frequency("50.0 MHz"),
        .operation_mode("direct"),
        .number_of_clocks(2),
        .output_clock_frequency0("49.152000 MHz"),
        .phase_shift0("0 ps"),
        .duty_cycle0(50),
        .output_clock_frequency1("12.288000 MHz"),
        .phase_shift1("0 ps"),
        .duty_cycle1(50),
        .pll_type("General"),
        .pll_subtype("General")
    ) altera_pll_i (
        .rst      (rst),
        .outclk   ({mclk, sys_clk}),
        .locked   (locked),
        .fboutclk (),
        .fbclk    (1'b0),
        .refclk   (refclk)
    );
endmodule
