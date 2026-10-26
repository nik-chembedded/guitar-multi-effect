-- -----------------------------------------------------------------------------
-- FX_chain.vhd
-- Effect chain: Dynamics (gate + compressor, D5) -> Overdrive -> Distortion ->
--               Cabinet (FIR, D3) -> EQ (3 bands, D5) -> Chorus/flanger/vibrato
--               (mod_delay, D2) -> Tremolo -> Echo -> Reverb (Freeverb, D4).
-- Every effect advances on the strobes (sample_tick / half_tick, v2 B1).
--   DW    : sample width, 16 (bit-exact to v1) or 24 (step C)
--   XFADE : click-free on/off (fx_xfade, 5.3 ms crossfade per effect)
--   ECHO_AW : echo line 2^ECHO_AW words (15 = 32 k; 16 = the v1 size)
--   CAB_TAPS, CAB_INIT : cabinet FIR length (2048; 16 for simulations with 16-clock
--             frames) and the .mif of its power-up coefficients (bank 0)
-- Cabinet (enable bit 6): cab_ctrl = CAB_CTRL register (bit 0 bank, 3:1 shift of bank 0,
-- 6:4 shift of bank 1), coefficient write port cab_cw_*; with the cabinet off the stage
-- output is the distortion output itself (no latency), see cab_stage.vhd.
-- Dynamics (enable bit 7) and EQ (enable bit 8): zero-latency bypass when off (dyn_stage /
-- eq_stage, fx_bypass); when on each adds one frame. dyn_ctrl = DYN_CTRL register (bit 0 gate,
-- bit 1 compressor), eq_cw_* / eq_apply = EQ coefficient port.
-- Mono: the left input is processed; data_out_right is not driven by effects.
-- -----------------------------------------------------------------------------
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.cab_fir_pkg.all;

entity FX_chain is
generic (
      DW    : positive := 16;
      XFADE : boolean  := false;
      ECHO_AW : positive := 15;
      CAB_TAPS : positive := 2048;
      CAB_INIT : string  := "cab_default.mif"
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
		-- D2: modulated delay (chorus_level = mix 0..255, chorus_depth = depth in samples,
		-- chorus_rate = LFO rate in 0.01 Hz) and fractional echo time
		mod_base			: in std_logic_vector(15 downto 0) := (others => '0');   -- samples
		mod_fb			: in std_logic_vector(15 downto 0) := (others => '0');   -- signed Q15
		mod_shape		: in std_logic_vector(15 downto 0) := (others => '0');   -- 0 sine, 1 triangle
		echo_frac		: in std_logic_vector(7 downto 0)  := (others => '0');   -- 1/256 sample
		echo_time			: in std_logic_vector(15 downto 0);
		echo_level			: in std_logic_vector(15 downto 0);
		echo_repeat			: in std_logic_vector(15 downto 0);

		chorus_rate       : in std_logic_vector(15 downto 0);
		chorus_level      : in std_logic_vector(15 downto 0);
		chorus_depth      : in std_logic_vector(15 downto 0);
		dist_mix          : in std_logic_vector(15 downto 0);
		dist_type         : in std_logic_vector(15 downto 0);
		reverb_size       : in std_logic_vector(15 downto 0) := (others => '0');   -- D4: feedback Q0.16 (block clamps to 0.98)
		reverb_damp       : in std_logic_vector(15 downto 0) := (others => '0');   -- D4: [7:0]
		reverb_mix        : in std_logic_vector(15 downto 0);

		-- D3 cabinet: CAB_CTRL register and coefficient write port (18-bit, bank, tap address)
		cab_ctrl          : in std_logic_vector(15 downto 0) := (others => '0');
		cab_cw_en         : in std_logic := '0';
		cab_cw_bank       : in std_logic := '0';
		cab_cw_addr       : in std_logic_vector(10 downto 0) := (others => '0');
		cab_cw_data       : in std_logic_vector(17 downto 0) := (others => '0');

		-- D5 dynamics: DYN_CTRL .. COMP_MAKEUP registers (signed Q8 log2 units), gain-reduction meter
		dyn_ctrl          : in std_logic_vector(15 downto 0) := (others => '0');
		gate_thresh       : in std_logic_vector(15 downto 0) := (others => '0');
		comp_thresh       : in std_logic_vector(15 downto 0) := (others => '0');
		comp_ratio        : in std_logic_vector(15 downto 0) := (others => '0');
		comp_attack       : in std_logic_vector(15 downto 0) := (others => '0');
		comp_release      : in std_logic_vector(15 downto 0) := (others => '0');
		comp_makeup       : in std_logic_vector(15 downto 0) := (others => '0');
		dyn_gr            : out std_logic_vector(15 downto 0);

		-- D5 EQ: coefficient write port (address 0..14 coefficient, 15 scale word) and apply pulse
		eq_cw_en          : in std_logic := '0';
		eq_cw_addr        : in std_logic_vector(3 downto 0) := (others => '0');
		eq_cw_data        : in std_logic_vector(17 downto 0) := (others => '0');
		eq_apply          : in std_logic := '0';

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
  signal dyn_out, od_out, dist_out, cab_out, eq_out, chorus_out, trem_out, echo_out : sample_t;
  signal od_en, dist_en, chorus_en, trem_en, echo_en, rev_en       : std_logic;

begin

  -- strobes per effect (as in v1): overdrive / distortion on sample_tick,
  -- the delay-based effects on half_tick (en_fall = the other strobe)

  -- dynamics: the first stage; combinational at g = 0 (no latency), see dyn_stage.vhd
  DYN_left : entity work.dyn_stage generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, sample_tick => sample_tick, enable => effects_enable(7),
      dyn_ctrl => dyn_ctrl, gate_thresh => gate_thresh, comp_thresh => comp_thresh,
      comp_ratio => comp_ratio, comp_attack => comp_attack, comp_release => comp_release,
      comp_makeup => comp_makeup, din => data_in_left, dout => dyn_out, gain_red => dyn_gr);

  OD_left : entity work.overdrive generic map (DW => DW) port map(
      clk => clk, en_rise => sample_tick, en_fall => half_tick, od_enable => od_en,
      drive => od_drive, gain => od_gain, data_in => dyn_out, data_out => od_wet);
  OD_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => sample_tick, enable_in => effects_enable(0),
      enable_eff => od_en, din => dyn_out, wet => od_wet, dout => od_out);

  dist_left : entity work.distortion generic map (DW => DW) port map(
      clk => clk, en_rise => sample_tick, en_fall => half_tick, dist_enable => dist_en,
      mix => dist_mix, d_type => dist_type, data_in => od_out, data_out => dist_wet);
  dist_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => sample_tick, enable_in => effects_enable(3),
      enable_eff => dist_en, din => od_out, wet => dist_wet, dout => dist_out);

  -- cabinet: crossfade with the distortion output, combinational at g = 0 (no latency)
  CAB_left : entity work.cab_stage
    generic map (DW => DW, TAPS => CAB_TAPS, LANES => 4, XFADE => XFADE, INIT_FILE => CAB_INIT)
    port map (
      clk => clk, sample_tick => sample_tick, enable => effects_enable(6),
      bank_req => cab_ctrl(0), shift0 => cab_ctrl(3 downto 1), shift1 => cab_ctrl(6 downto 4),
      cw_en => cab_cw_en, cw_bank => cab_cw_bank,
      cw_addr => cab_cw_addr(clog2(CAB_TAPS) - 1 downto 0), cw_data => cab_cw_data,
      din => dist_out, dout => cab_out);

  -- EQ: samples the cabinet output at half_tick, combinational at g = 0, see eq_stage.vhd
  EQ_left : entity work.eq_stage generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, sample_tick => sample_tick, half_tick => half_tick, enable => effects_enable(8),
      cw_en => eq_cw_en, cw_addr => eq_cw_addr, cw_data => eq_cw_data, apply => eq_apply,
      din => cab_out, dout => eq_out);

  CHORUS_left : entity work.mod_delay generic map (DW => DW) port map(
      clk => clk, en_rise => half_tick, enable => chorus_en,
      mix => chorus_level, depth => chorus_depth, rate => chorus_rate,
      base => mod_base, fb => mod_fb, shape => mod_shape,
      data_in => eq_out, data_out => chorus_wet);
  CHORUS_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(4),
      enable_eff => chorus_en, din => eq_out, wet => chorus_wet, dout => chorus_out);

  TREMOLO_left : entity work.tremolo_v2 generic map (DW => DW) port map(
      clk => clk, en_rise => half_tick, en_fall => sample_tick, tremolo_enable => trem_en,
      t_wave => trem_wave, t_depth => trem_depth, t_rate => trem_rate,
      data_in => chorus_out, data_out => trem_wet);
  TREMOLO_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(1),
      enable_eff => trem_en, din => chorus_out, wet => trem_wet, dout => trem_out);

  ECHO_left : entity work.echo generic map (DW => DW, AW => ECHO_AW) port map(
      clk => clk, en_rise => half_tick, en_fall => sample_tick, echo_enable => echo_en,
      e_time => echo_time, e_frac => echo_frac, e_level => echo_level, e_repeat => echo_repeat,
      data_in => trem_out, data_out => echo_wet);
  ECHO_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(2),
      enable_eff => echo_en, din => trem_out, wet => echo_wet, dout => echo_out);

  -- room presets / custom size and damping are chosen outside (gme_core: smoothed)
  REVERB_left : entity work.reverb_fv generic map (DW => DW) port map(
      clk => clk, en_rise => half_tick, en_fall => sample_tick, enable => rev_en,
      size => reverb_size, damp => reverb_damp, mix => reverb_mix,
      data_in => echo_out, data_out => rev_wet);
  REVERB_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(5),
      enable_eff => rev_en, din => echo_out, wet => rev_wet, dout => data_out_left);

  data_out_right <= (others => '0');

end architecture;
