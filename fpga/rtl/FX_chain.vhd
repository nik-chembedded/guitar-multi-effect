-- -----------------------------------------------------------------------------
-- FX_chain.vhd
-- Effect chain of nine effects: Dynamics (gate + compressor, D5), Overdrive, Distortion,
-- Cabinet (FIR, D3), EQ (3 bands, D5), Chorus/flanger/vibrato (mod_delay, D2), Tremolo,
-- Echo, Reverb (Freeverb, D4). Step E: the ORDER is selectable at run time (fx_route.vhd);
-- the power-up / reset order is DYN OD DIST CAB EQ MOD TREM ECHO REVERB.
-- Every effect advances on the strobes (sample_tick / half_tick, v2 B1).
--   DW    : sample width, 16 (bit-exact to v1) or 24 (step C)
--   XFADE : click-free on/off (fx_xfade, 5.3 ms crossfade per effect)
--   ECHO_AW : echo line 2^ECHO_AW words (15 = 32 k; 16 = the v1 size)
--   CAB_TAPS, CAB_INIT : cabinet FIR length (2048; 16 for simulations with 16-clock
--             frames) and the .mif of its power-up coefficients (bank 0)
-- Routing (step E): every effect (block + its own crossfade / bypass, unchanged) takes its input
-- from fx_in(id) and delivers its stage output to fx_out(id); fx_route registers every stage
-- output at sample_tick (slot_q) and selects each input from the previous slot of the list.
-- Effect id = enable bit: 0 OD, 1 TREM, 2 ECHO, 3 DIST, 4 MOD, 5 REVERB, 6 CAB, 7 DYN, 8 EQ.
-- The chain input is registered at sample_tick (in_q): the I2S receive word changes in the
-- middle of the frame, in_q is stable for the whole frame, so every effect sees the same
-- value whatever its strobe. Latency: fixed per slot (1 frame for an effect that updates at
-- half_tick, 2 for one that updates at sample_tick or has a long sequencer), the same for any
-- order (an effect that is off keeps its place): 11 frames with every effect off. An effect
-- that is on adds its own internal delay: overdrive, distortion, cabinet one frame each, the
-- others none (test_fx_chain::test_latency).
-- chain_order = shadow list (36 bits, slot 0 in bits 3:0), chain_apply = 1-clock pulse that
-- checks it and starts the order fade (about 5 ms dip), chain_busy / chain_rejected = status
-- (registers 0x30 .. 0x33), chain_active = the list in use.
-- Cabinet (enable bit 6): cab_ctrl = CAB_CTRL register (bit 0 bank, 3:1 shift of bank 0,
-- 6:4 shift of bank 1), coefficient write port cab_cw_*; with the cabinet off the stage
-- output is its input itself, see cab_stage.vhd.
-- Dynamics (enable bit 7) and EQ (enable bit 8): bypass (dyn_stage / eq_stage, fx_bypass) when
-- off. dyn_ctrl = DYN_CTRL register (bit 0 gate, bit 1 compressor), eq_cw_* / eq_apply = EQ
-- coefficient port.
-- D6: od_level / dist_level scale the overdrive / distortion wet path (level_gain.vhd).
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

		-- D6: output level of the overdrive / distortion, signed Q8 log2 units (0 = unity, -1024 .. +512)
		od_level          : in std_logic_vector(15 downto 0) := (others => '0');
		dist_level        : in std_logic_vector(15 downto 0) := (others => '0');

		-- D5 EQ: coefficient write port (address 0..14 coefficient, 15 scale word) and apply pulse
		eq_cw_en          : in std_logic := '0';
		eq_cw_addr        : in std_logic_vector(3 downto 0) := (others => '0');
		eq_cw_data        : in std_logic_vector(17 downto 0) := (others => '0');
		eq_apply          : in std_logic := '0';

		-- step E: effect order (registers 0x30 .. 0x33); default = DYN OD DIST CAB EQ MOD TREM ECHO REVERB
		chain_order       : in std_logic_vector(35 downto 0) := x"521486307";
		chain_apply       : in std_logic := '0';
		chain_busy        : out std_logic;
		chain_rejected    : out std_logic;
		chain_active      : out std_logic_vector(35 downto 0);

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
  signal rev_out                                                   : sample_t;

  -- step E: stage inputs / outputs as seen by fx_route (id = enable bit), chain input register
  constant N_FX    : positive := 9;
  constant ID_OD   : natural := 0;
  constant ID_TREM : natural := 1;
  constant ID_ECHO : natural := 2;
  constant ID_DIST : natural := 3;
  constant ID_MOD  : natural := 4;
  constant ID_REV  : natural := 5;
  constant ID_CAB  : natural := 6;
  constant ID_DYN  : natural := 7;
  constant ID_EQ   : natural := 8;
  signal fx_in, fx_out : std_logic_vector(N_FX * DW - 1 downto 0);
  signal in_q          : sample_t := (others => '0');
  signal chain_res     : sample_t;
  signal dyn_in, od_in, dist_in, cab_in, eq_in, chorus_in, trem_in, echo_in, rev_in : sample_t;

begin

  -- strobes per effect (as in v1): overdrive / distortion on sample_tick,
  -- the delay-based effects on half_tick (en_fall = the other strobe)

  -- stage inputs from fx_route, stage outputs to it
  dyn_in    <= fx_in(ID_DYN  * DW + DW - 1 downto ID_DYN  * DW);
  od_in     <= fx_in(ID_OD   * DW + DW - 1 downto ID_OD   * DW);
  dist_in   <= fx_in(ID_DIST * DW + DW - 1 downto ID_DIST * DW);
  cab_in    <= fx_in(ID_CAB  * DW + DW - 1 downto ID_CAB  * DW);
  eq_in     <= fx_in(ID_EQ   * DW + DW - 1 downto ID_EQ   * DW);
  chorus_in <= fx_in(ID_MOD  * DW + DW - 1 downto ID_MOD  * DW);
  trem_in   <= fx_in(ID_TREM * DW + DW - 1 downto ID_TREM * DW);
  echo_in   <= fx_in(ID_ECHO * DW + DW - 1 downto ID_ECHO * DW);
  rev_in    <= fx_in(ID_REV  * DW + DW - 1 downto ID_REV  * DW);
  fx_out(ID_DYN  * DW + DW - 1 downto ID_DYN  * DW) <= dyn_out;
  fx_out(ID_OD   * DW + DW - 1 downto ID_OD   * DW) <= od_out;
  fx_out(ID_DIST * DW + DW - 1 downto ID_DIST * DW) <= dist_out;
  fx_out(ID_CAB  * DW + DW - 1 downto ID_CAB  * DW) <= cab_out;
  fx_out(ID_EQ   * DW + DW - 1 downto ID_EQ   * DW) <= eq_out;
  fx_out(ID_MOD  * DW + DW - 1 downto ID_MOD  * DW) <= chorus_out;
  fx_out(ID_TREM * DW + DW - 1 downto ID_TREM * DW) <= trem_out;
  fx_out(ID_ECHO * DW + DW - 1 downto ID_ECHO * DW) <= echo_out;
  fx_out(ID_REV  * DW + DW - 1 downto ID_REV  * DW) <= rev_out;

  -- chain input register: the I2S receive word changes in the middle of the frame, in_q only at sample_tick
  process(clk)
  begin
    if rising_edge(clk) then
      if sample_tick = '1' then
        in_q <= data_in_left;
      end if;
    end if;
  end process;

  u_route : entity work.fx_route
    generic map (DW => DW, N => N_FX)
    port map (clk => clk, sample_tick => sample_tick, order_in => chain_order, apply => chain_apply,
              busy => chain_busy, rejected => chain_rejected, order_active => chain_active,
              chain_in => in_q, fx_out => fx_out, fx_in => fx_in, chain_out => chain_res);
  data_out_left <= chain_res;

  -- dynamics; bypass (g = 0) is combinational, see dyn_stage.vhd
  DYN_left : entity work.dyn_stage generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, sample_tick => sample_tick, enable => effects_enable(7),
      dyn_ctrl => dyn_ctrl, gate_thresh => gate_thresh, comp_thresh => comp_thresh,
      comp_ratio => comp_ratio, comp_attack => comp_attack, comp_release => comp_release,
      comp_makeup => comp_makeup, din => dyn_in, dout => dyn_out, gain_red => dyn_gr);

  OD_left : entity work.overdrive generic map (DW => DW) port map(
      clk => clk, en_rise => sample_tick, en_fall => half_tick, od_enable => od_en,
      drive => od_drive, gain => od_gain, level => od_level, data_in => od_in, data_out => od_wet);
  OD_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => sample_tick, enable_in => effects_enable(0),
      enable_eff => od_en, din => od_in, wet => od_wet, dout => od_out);

  dist_left : entity work.distortion generic map (DW => DW) port map(
      clk => clk, en_rise => sample_tick, en_fall => half_tick, dist_enable => dist_en,
      mix => dist_mix, d_type => dist_type, level => dist_level, data_in => dist_in, data_out => dist_wet);
  dist_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => sample_tick, enable_in => effects_enable(3),
      enable_eff => dist_en, din => dist_in, wet => dist_wet, dout => dist_out);

  -- cabinet: crossfade with its own input, combinational at g = 0
  CAB_left : entity work.cab_stage
    generic map (DW => DW, TAPS => CAB_TAPS, LANES => 4, XFADE => XFADE, INIT_FILE => CAB_INIT)
    port map (
      clk => clk, sample_tick => sample_tick, enable => effects_enable(6),
      bank_req => cab_ctrl(0), shift0 => cab_ctrl(3 downto 1), shift1 => cab_ctrl(6 downto 4),
      cw_en => cab_cw_en, cw_bank => cab_cw_bank,
      cw_addr => cab_cw_addr(clog2(CAB_TAPS) - 1 downto 0), cw_data => cab_cw_data,
      din => cab_in, dout => cab_out);

  -- EQ: samples its input at half_tick, combinational at g = 0, see eq_stage.vhd
  EQ_left : entity work.eq_stage generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, sample_tick => sample_tick, half_tick => half_tick, enable => effects_enable(8),
      cw_en => eq_cw_en, cw_addr => eq_cw_addr, cw_data => eq_cw_data, apply => eq_apply,
      din => eq_in, dout => eq_out);

  CHORUS_left : entity work.mod_delay generic map (DW => DW) port map(
      clk => clk, en_rise => half_tick, enable => chorus_en,
      mix => chorus_level, depth => chorus_depth, rate => chorus_rate,
      base => mod_base, fb => mod_fb, shape => mod_shape,
      data_in => chorus_in, data_out => chorus_wet);
  CHORUS_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(4),
      enable_eff => chorus_en, din => chorus_in, wet => chorus_wet, dout => chorus_out);

  TREMOLO_left : entity work.tremolo_v2 generic map (DW => DW) port map(
      clk => clk, en_rise => half_tick, en_fall => sample_tick, tremolo_enable => trem_en,
      t_wave => trem_wave, t_depth => trem_depth, t_rate => trem_rate,
      data_in => trem_in, data_out => trem_wet);
  TREMOLO_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(1),
      enable_eff => trem_en, din => trem_in, wet => trem_wet, dout => trem_out);

  ECHO_left : entity work.echo generic map (DW => DW, AW => ECHO_AW) port map(
      clk => clk, en_rise => half_tick, en_fall => sample_tick, echo_enable => echo_en,
      e_time => echo_time, e_frac => echo_frac, e_level => echo_level, e_repeat => echo_repeat,
      data_in => echo_in, data_out => echo_wet);
  ECHO_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(2),
      enable_eff => echo_en, din => echo_in, wet => echo_wet, dout => echo_out);

  -- room presets / custom size and damping are chosen outside (gme_core: smoothed)
  REVERB_left : entity work.reverb_fv generic map (DW => DW) port map(
      clk => clk, en_rise => half_tick, en_fall => sample_tick, enable => rev_en,
      size => reverb_size, damp => reverb_damp, mix => reverb_mix,
      data_in => rev_in, data_out => rev_wet);
  REVERB_fade : entity work.fx_xfade generic map (DW => DW, XFADE => XFADE) port map(
      clk => clk, tick => sample_tick, en_rise => half_tick, enable_in => effects_enable(5),
      enable_eff => rev_en, din => rev_in, wet => rev_wet, dout => rev_out);

  data_out_right <= (others => '0');

end architecture;
