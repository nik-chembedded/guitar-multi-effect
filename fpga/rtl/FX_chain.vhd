-- -----------------------------------------------------------------------------
-- FX_chain.vhd
-- Effect chain: Overdrive -> Distortion -> Chorus -> Tremolo -> Echo -> Reverb.
-- Every effect advances on the strobes (sample_tick / half_tick, v2 B1).
--   DW    : sample width, 16 (bit-exact to v1) or 24 (step C)
--   XFADE : click-free on/off (fx_xfade, 5.3 ms crossfade per effect)
--   ECHO_AW : echo line 2^ECHO_AW words (16 = v1 size, for the reference test)
--   LEGACY_TREM : v1 ROM-table tremolo (sim/models/legacy, simulation only) instead
--           of the generated LFO; used by the v1 reference tests
-- Mono: the left input is processed; data_out_right is not driven by effects.
-- -----------------------------------------------------------------------------
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity FX_chain is
generic (
      DW    : positive := 16;
      XFADE : boolean  := false;
      ECHO_AW : positive := 15;
      LEGACY_TREM : boolean := false
);
port(

      clk           : in std_logic;   -- system clock (49.152 MHz in v2)
      sample_tick   : in std_logic;   -- 1-cycle strobe per frame (v1: LRCLK rising)
      half_tick     : in std_logic;   -- 1-cycle strobe half a frame later (v1: LRCLK falling)
		od_enable       : in std_logic;   -- unused (v1 ports)
		tremolo_enable  : in std_logic;
		echo_enable   : in std_logic;

		effects_enable 	: in std_logic_vector(15 downto 0);
		od_drive				: in std_logic_vector(15 downto 0);
		od_gain				: in std_logic_vector(15 downto 0);
		trem_depth			: in std_logic_vector(15 downto 0);
		trem_wave			: in std_logic_vector(15 downto 0);
		trem_rate			: in std_logic_vector(15 downto 0) := (others => '0');   -- 0.01 Hz (D1)
		echo_time			: in std_logic_vector(15 downto 0);
		echo_level			: in std_logic_vector(15 downto 0);
		echo_repeat			: in std_logic_vector(15 downto 0);

		chorus_rate       : in std_logic_vector(15 downto 0);
		chorus_level      : in std_logic_vector(15 downto 0);
		chorus_depth      : in std_logic_vector(15 downto 0);
		dist_mix          : in std_logic_vector(15 downto 0);
		dist_type         : in std_logic_vector(15 downto 0);
		reverb_type       : in std_logic_vector(15 downto 0);
		reverb_mix        : in std_logic_vector(15 downto 0);

		data_in_left  : in std_logic_vector(DW - 1 downto 0);
		data_in_right : in std_logic_vector(DW - 1 downto 0);

		data_out_left  : out std_logic_vector(DW - 1 downto 0);
		data_out_right : out std_logic_vector(DW - 1 downto 0)
);
end entity;

architecture rtl of FX_chain is

  subtype sample_t is std_logic_vector(DW - 1 downto 0);

  -- per stage: effect output (wet) and stage output after the crossfade
  signal od_wet, dist_wet, chorus_wet, trem_wet, echo_wet, rev_wet : sample_t;
  signal od_out, dist_out, chorus_out, trem_out, echo_out          : sample_t;
  signal od_en, dist_en, chorus_en, trem_en, echo_en, rev_en       : std_logic;

  -- simulation-only v1 tremolo (component: not needed by synthesis when unused)
  component tremolo_legacy is
    generic (DW : positive := 16);
    port (clk, en_rise, en_fall, tremolo_enable : in std_logic;
          t_wave, t_depth, t_rate : in std_logic_vector(15 downto 0);
          data_in  : in  std_logic_vector(DW - 1 downto 0);
          data_out : out std_logic_vector(DW - 1 downto 0));
  end component;

begin

  -- strobes per effect (as in v1): overdrive / distortion on sample_tick,
  -- the delay-based effects on half_tick (en_fall = the other strobe)

  OD_left : entity work.overdrive generic map (DW => DW) port map(
      clk => clk, en_rise => sample_tick, en_fall => half_tick, od_enable => od_en,
      drive => od_drive, gain => od_gain, data_in => data_in_left, data_out => od_wet);
  OD_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => sample_tick, enable_in => effects_enable(0),
      enable_eff => od_en, din => data_in_left, wet => od_wet, dout => od_out);

  dist_left : entity work.distortion generic map (DW => DW) port map(
      clk => clk, en_rise => sample_tick, en_fall => half_tick, dist_enable => dist_en,
      mix => dist_mix, d_type => dist_type, data_in => od_out, data_out => dist_wet);
  dist_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => sample_tick, enable_in => effects_enable(3),
      enable_eff => dist_en, din => od_out, wet => dist_wet, dout => dist_out);

  CHORUS_left : entity work.chorus generic map (DW => DW) port map(
      clk => clk, en_rise => half_tick, en_fall => sample_tick, chorus_enable => chorus_en,
      gain => chorus_level, chorus_rate => chorus_rate, chorus_depth => chorus_depth,
      data_in => dist_out, data_out => chorus_wet);
  CHORUS_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(4),
      enable_eff => chorus_en, din => dist_out, wet => chorus_wet, dout => chorus_out);

  trem_new : if not LEGACY_TREM generate
    TREMOLO_left : entity work.tremolo_v2 generic map (DW => DW) port map(
        clk => clk, en_rise => half_tick, en_fall => sample_tick, tremolo_enable => trem_en,
        t_wave => trem_wave, t_depth => trem_depth, t_rate => trem_rate,
        data_in => chorus_out, data_out => trem_wet);
  end generate;
  trem_v1 : if LEGACY_TREM generate
    TREMOLO_left : tremolo_legacy generic map (DW => DW) port map(
        clk => clk, en_rise => half_tick, en_fall => sample_tick, tremolo_enable => trem_en,
        t_wave => trem_wave, t_depth => trem_depth, t_rate => trem_rate,
        data_in => chorus_out, data_out => trem_wet);
  end generate;
  TREMOLO_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(1),
      enable_eff => trem_en, din => chorus_out, wet => trem_wet, dout => trem_out);

  ECHO_left : entity work.echo generic map (DW => DW, AW => ECHO_AW) port map(
      clk => clk, en_rise => half_tick, en_fall => sample_tick, echo_enable => echo_en,
      e_time => echo_time, e_level => echo_level, e_repeat => echo_repeat,
      data_in => trem_out, data_out => echo_wet);
  ECHO_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(2),
      enable_eff => echo_en, din => trem_out, wet => echo_wet, dout => echo_out);

  REVERB_left : entity work.reverbe generic map (DW => DW) port map(
      clk => clk, en_rise => half_tick, en_fall => sample_tick, data_in => echo_out,
      reverb_mix => reverb_mix, reverb_type => reverb_type, reverbe_enable => rev_en,
      data_out => rev_wet);
  REVERB_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(5),
      enable_eff => rev_en, din => echo_out, wet => rev_wet, dout => data_out_left);

  data_out_right <= (others => '0');

end architecture;
