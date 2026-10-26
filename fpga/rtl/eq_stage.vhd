-- -----------------------------------------------------------------------------
-- eq_stage.vhd  (v2 step D5)
-- 3-band EQ stage (eq3.vhd) between the cabinet and the modulated delay, with a
-- zero-latency bypass (fx_bypass.vhd).
--
--   * strobe of the block = half_tick. Its input, the cabinet stage output, is stable
--     from sample_tick + 1 until the next sample_tick, so it is the same whether a
--     frame has 16 clocks (simulation) or 1024 (board). The result is registered 7
--     clocks after half_tick.
--   * the modulated delay samples the stage output at the NEXT half_tick, i.e. it takes
--     the EQ result of the previous frame: with the stage on (g = 256) the chain is one
--     frame longer, with the stage off the stage output is the cabinet output itself.
--     The stage output changes 7 clocks after half_tick, but its only consumers sample
--     at half_tick, so simulation and board timing give identical samples.
--   * the block runs on every sample (enable = '1'): filter state is warm, the fade-in
--     has no transient.
--   * coefficients: cw_* write port + apply (see eq3.vhd); a new set becomes active
--     at one half_tick for all three sections.
-- Per-clock pipeline u_eq: excluded from the multicycle relaxation in top_v2.sdc.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity eq_stage is
  generic (
    DW    : positive := 24;
    XFADE : boolean  := true
  );
  port (
    clk         : in  std_logic;
    sample_tick : in  std_logic;
    half_tick   : in  std_logic;
    enable      : in  std_logic;
    cw_en       : in  std_logic;
    cw_addr     : in  std_logic_vector(3 downto 0);
    cw_data     : in  std_logic_vector(17 downto 0);
    apply       : in  std_logic;
    din         : in  std_logic_vector(DW - 1 downto 0);
    dout        : out std_logic_vector(DW - 1 downto 0)
  );
end entity;

architecture rtl of eq_stage is
  signal wet    : std_logic_vector(DW - 1 downto 0);
  signal active : std_logic;
begin

  u_eq : entity work.eq3
    generic map (DW => DW)
    port map (clk => clk, strobe => half_tick, enable => '1',
              cw_en => cw_en, cw_addr => cw_addr, cw_data => cw_data, apply => apply,
              data_in => din, data_out => wet);

  u_fade : entity work.fx_bypass
    generic map (DW => DW, XFADE => XFADE)
    port map (clk => clk, tick => sample_tick, enable => enable,
              din => din, wet => wet, dout => dout, active => active);

end architecture;
