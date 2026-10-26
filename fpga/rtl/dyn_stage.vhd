-- -----------------------------------------------------------------------------
-- dyn_stage.vhd  (v2 step D5)
-- Dynamics stage (noise gate + compressor, dynamics.vhd) at the very start of the
-- effect chain, with a zero-latency bypass (fx_bypass.vhd).
--
--   * strobe of the block = sample_tick delayed by one clock: the chain input
--     (rx_left, valid long before sample_tick; in the testbench presented before it)
--     is stable then. The result is registered 10 clocks after that strobe, i.e. 11
--     clocks after sample_tick (16 clocks per frame in simulation, 1024 on the
--     board: in both the result is there before the next sample_tick).
--   * the overdrive takes the stage output at the NEXT sample_tick: with the stage on
--     (g = 256) the chain is one frame longer, with the stage off (g = 0) the stage
--     output is the input itself. The stage output changes between two sample_ticks
--     (when the result arrives) but its only consumers sample at sample_tick, so the
--     simulation timing and the board timing give identical samples.
--   * the block runs on every sample (enable = '1'), also while the stage is off:
--     envelope and gain state are warm, the fade-in has no start-up transient. The
--     gain-reduction meter shows 0 while the stage is off.
--   * thresholds, ratio and makeup are not smoothed; the gain itself glides (attack /
--     release in the block, 1 ms gate opening), so register changes are click-free.
-- Per-clock pipeline u_dyn: excluded from the multicycle relaxation in top_v2.sdc.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity dyn_stage is
  generic (
    DW    : positive := 24;
    XFADE : boolean  := true
  );
  port (
    clk          : in  std_logic;
    sample_tick  : in  std_logic;
    enable       : in  std_logic;                      -- effect enable bit
    dyn_ctrl     : in  std_logic_vector(15 downto 0);  -- bit0 gate_en, bit1 comp_en
    gate_thresh  : in  std_logic_vector(15 downto 0);
    comp_thresh  : in  std_logic_vector(15 downto 0);
    comp_ratio   : in  std_logic_vector(15 downto 0);
    comp_attack  : in  std_logic_vector(15 downto 0);
    comp_release : in  std_logic_vector(15 downto 0);
    comp_makeup  : in  std_logic_vector(15 downto 0);
    din          : in  std_logic_vector(DW - 1 downto 0);
    dout         : out std_logic_vector(DW - 1 downto 0);
    gain_red     : out std_logic_vector(15 downto 0)
  );
end entity;

architecture rtl of dyn_stage is
  signal start  : std_logic := '0';
  signal wet    : std_logic_vector(DW - 1 downto 0);
  signal gr     : std_logic_vector(15 downto 0);
  signal active : std_logic;
begin

  process(clk)
  begin
    if rising_edge(clk) then
      start <= sample_tick;
    end if;
  end process;

  u_dyn : entity work.dynamics
    generic map (DW => DW)
    port map (clk => clk, strobe => start, enable => '1',
              gate_en => dyn_ctrl(0), comp_en => dyn_ctrl(1),
              gate_thresh => gate_thresh, comp_thresh => comp_thresh,
              comp_ratio => comp_ratio, comp_makeup => comp_makeup,
              comp_attack => comp_attack, comp_release => comp_release,
              data_in => din, data_out => wet, gain_reduction => gr);

  u_fade : entity work.fx_bypass
    generic map (DW => DW, XFADE => XFADE)
    port map (clk => clk, tick => sample_tick, enable => enable,
              din => din, wet => wet, dout => dout, active => active);

  gain_red <= gr when active = '1' else (others => '0');

end architecture;
