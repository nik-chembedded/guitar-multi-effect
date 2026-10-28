-- -----------------------------------------------------------------------------
-- gme_core.vhd  (v2 step B5)
-- Everything of the multi-effect that runs on sys_clk (49.152 MHz):
--   i2s_core   FPGA = I2S master, stereo 24-bit, sample_tick / half_tick
--   FX_chain   the effects, 24-bit (step C), click-free on/off; mono: left input,
--              output to both channels
--   param_smooth  one-pole smoothing of the continuous parameters (step C)
--   ctrl_avmm  register file behind an Avalon-MM slave (HPS lightweight bridge)
--   codec_ctrl WM8731 init sequence + host codec writes over I2C
--   level meters for the STATUS/level registers, status LEDs
-- top_v2.vhd adds the PLL, the HPS (Platform Designer system hps_sys), the reset
-- synchroniser and the pin buffers.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity gme_core is
  generic (
    I2C_DIV        : positive := 123;              -- I2C quarter period -> 99.9 kHz
    INIT_WAIT_CLKS : positive := 491_520;          -- codec power-up pause (10 ms)
    SMOOTH         : boolean  := true;             -- parameter smoothing
    XFADE          : boolean  := true;             -- click-free effect on/off
    CAB_TAPS       : positive := 2048;             -- cabinet FIR length (D3)
    CAB_INIT       : string   := "cab_default.mif"; -- its power-up coefficients
    VERSION        : std_logic_vector(15 downto 0) := x"0209"
  );
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;                    -- synchronous, active high
    pll_locked : in  std_logic;
    -- codec audio (FPGA is I2S master)
    bclk       : out std_logic;
    lrclk      : out std_logic;
    dacdat     : out std_logic;
    adcdat     : in  std_logic;
    -- codec control (open drain: *_oe = '1' pulls low)
    scl_oe     : out std_logic;
    sda_oe     : out std_logic;
    sda_in     : in  std_logic;
    -- host: Avalon-MM slave on the HPS lightweight bridge (byte address)
    avs_address       : in  std_logic_vector(7 downto 0);
    avs_read          : in  std_logic;
    avs_write         : in  std_logic;
    avs_writedata     : in  std_logic_vector(31 downto 0);
    avs_byteenable    : in  std_logic_vector(3 downto 0);
    avs_readdata      : out std_logic_vector(31 downto 0);
    avs_readdatavalid : out std_logic;
    avs_waitrequest   : out std_logic;
    -- LEDs: 0 PLL locked, 1 codec init done, 2 codec NAK, 3 heartbeat (1 Hz)
    leds       : out std_logic_vector(3 downto 0)
  );
end entity;

architecture rtl of gme_core is
  signal sample_tick, half_tick : std_logic;
  signal rx_left, rx_right      : std_logic_vector(23 downto 0);
  signal tx_word                : std_logic_vector(23 downto 0);
  signal fx_out                 : std_logic_vector(23 downto 0);

  signal effects_enable, od_drive, od_gain, trem_wave, trem_depth, echo_time, echo_repeat,
         echo_level, dist_mix, dist_type, chorus_level, chorus_depth, chorus_rate,
         reverb_mix, reverb_type : std_logic_vector(15 downto 0);
  signal ext                    : std_logic_vector(30 * 16 - 1 downto 0);   -- registers 0x16 .. 0x33
  signal trem_rate, mod_base, mod_fb, mod_shape : std_logic_vector(15 downto 0);
  -- smoothed continuous parameters (to the chain)
  signal s_od_drive, s_trem_depth, s_echo_level, s_echo_repeat, s_dist_mix,
         s_chorus_level, s_reverb_mix, s_trem_rate, s_chorus_depth, s_chorus_rate,
         s_mod_base, s_mod_fb, s_echo_time : std_logic_vector(15 downto 0);
  -- reverb (D4): size / damp from the room preset (REVERB_TYPE 0..3) or the custom
  -- registers 0x1F / 0x20 (type 4; 5..15 act as 4), before and after smoothing
  signal rev_size, rev_damp, s_rev_size, s_rev_damp : std_logic_vector(15 downto 0);
  signal rev_t                  : natural range 0 to 15;
  signal ext_rsize, ext_rdamp   : std_logic_vector(15 downto 0);   -- registers 0x1F, 0x20
  signal fb_ofs, s_fb_ofs       : std_logic_vector(15 downto 0);            -- feedback, offset binary
  signal s_echo_frac            : std_logic_vector(7 downto 0);
  -- D6 output levels (registers 0x2D / 0x2E, signed Q8 log2 units), smoothed in offset binary
  signal od_level, dist_level, s_od_level, s_dist_level : std_logic_vector(15 downto 0);
  signal od_lvl_ofs, dist_lvl_ofs, s_od_lvl_ofs, s_dist_lvl_ofs : std_logic_vector(15 downto 0);

  -- extension register 0x16 + i
  function ext_reg(e : std_logic_vector; r : natural) return std_logic_vector is
  begin
    return e(16 * (r - 16#16#) + 15 downto 16 * (r - 16#16#));
  end function;
  signal codec_init, mute       : std_logic;

  -- room presets: size Q0.16 (feedback), damp 0..255 (docs/register_map.md, REVERB_TYPE)
  function room_size(t : natural) return natural is
  begin
    case t is
      when 0 => return 45875;       -- very light  0.70
      when 1 => return 52429;       -- light       0.80
      when 2 => return 57672;       -- medium      0.88
      when others => return 61604;  -- heavy       0.94
    end case;
  end function;
  function room_damp(t : natural) return natural is
  begin
    case t is
      when 0 => return 100;
      when 1 => return 80;
      when 2 => return 60;
      when others => return 40;
    end case;
  end function;

  -- cabinet (D3): CAB_ADDR pointer + coefficient write port; CAB_DATA_HI completes a write
  -- EQ (D5): EQ_ADDR pointer + coefficient write port; EQ_DATA_HI completes a write, EQ_APPLY pulses apply
  signal eq_ptr                 : unsigned(3 downto 0) := (others => '0');
  signal eq_cw_en               : std_logic := '0';
  signal eq_cw_addr             : std_logic_vector(3 downto 0) := (others => '0');
  signal eq_cw_data             : std_logic_vector(17 downto 0) := (others => '0');
  signal eq_apply               : std_logic := '0';
  signal dyn_gr                 : std_logic_vector(15 downto 0);

  -- effect order (E): CHAIN_0..2 (0x30 .. 0x32) -> fx_route shadow list, CHAIN_APPLY (0x33) pulses chain_apply
  signal chain_apply            : std_logic := '0';
  signal chain_busy, chain_rejected : std_logic;
  signal chain_order            : std_logic_vector(35 downto 0);
  signal chain_2                : std_logic_vector(15 downto 0);
  signal chain_status           : std_logic_vector(15 downto 0);
  signal chain_apply_ev         : std_logic;

  signal ext_we                 : std_logic;
  signal ext_wa                 : std_logic_vector(7 downto 0);
  signal ext_wd                 : std_logic_vector(15 downto 0);
  signal cab_ptr                : unsigned(11 downto 0) := (others => '0');
  signal cab_cw_en              : std_logic := '0';
  signal cab_cw_bank            : std_logic := '0';
  signal cab_cw_addr            : std_logic_vector(10 downto 0) := (others => '0');
  signal cab_cw_data            : std_logic_vector(17 downto 0) := (others => '0');

  signal i2c_req, i2c_busy, i2c_done, i2c_nak : std_logic;
  signal i2c_reg                : std_logic_vector(6 downto 0);
  signal i2c_data               : std_logic_vector(8 downto 0);
  signal init_done, init_nak    : std_logic;

  signal status                 : std_logic_vector(15 downto 0);
  signal peak_in, peak_out      : unsigned(15 downto 0) := (others => '0');
  signal hb_cnt                 : natural range 0 to 23999 := 0;
  signal hb                     : std_logic := '0';

  function abs16(v : std_logic_vector(15 downto 0)) return unsigned is
    variable s : signed(15 downto 0) := signed(v);
  begin
    if s = -32768 then return to_unsigned(32767, 16);
    elsif s < 0 then return unsigned(-s);
    else return unsigned(s);
    end if;
  end function;

  function peak_update(p : unsigned(15 downto 0); a : unsigned(15 downto 0)) return unsigned is
    variable decayed : unsigned(15 downto 0) := p - shift_right(p, 8);   -- ~ -0.7 dB/ms at 48 kHz
  begin
    if p < 256 and p > 0 then                     -- p/256 rounds to 0 here: decay by 1 instead
      decayed := p - 1;
    end if;
    if a > decayed then return a; else return decayed; end if;
  end function;
begin

  -- ---- audio ----------------------------------------------------------------
  u_i2s : entity work.i2s_core
    port map (clk => clk, rst => rst, bclk => bclk, lrclk => lrclk, dacdat => dacdat,
              adcdat => adcdat, rx_left => rx_left, rx_right => rx_right,
              tx_left => tx_word, tx_right => tx_word,
              sample_tick => sample_tick, half_tick => half_tick);

  u_fx : entity work.FX_chain
    generic map (DW => 24, XFADE => XFADE, CAB_TAPS => CAB_TAPS, CAB_INIT => CAB_INIT)
    port map (
      od_level => s_od_level, dist_level => s_dist_level,
      dyn_ctrl => ext_reg(ext, 16#21#), gate_thresh => ext_reg(ext, 16#22#),
      comp_thresh => ext_reg(ext, 16#23#), comp_ratio => ext_reg(ext, 16#24#),
      comp_attack => ext_reg(ext, 16#25#), comp_release => ext_reg(ext, 16#26#),
      comp_makeup => ext_reg(ext, 16#27#), dyn_gr => dyn_gr,
      eq_cw_en => eq_cw_en, eq_cw_addr => eq_cw_addr, eq_cw_data => eq_cw_data, eq_apply => eq_apply,
      chain_order => chain_order, chain_apply => chain_apply,
      chain_busy => chain_busy, chain_rejected => chain_rejected, chain_active => open,
      cab_ctrl => ext_reg(ext, 16#1B#), cab_cw_en => cab_cw_en, cab_cw_bank => cab_cw_bank,
      cab_cw_addr => cab_cw_addr, cab_cw_data => cab_cw_data,
      clk => clk, sample_tick => sample_tick, half_tick => half_tick,
      od_enable => '0', tremolo_enable => '0', echo_enable => '0',
      effects_enable => effects_enable, od_drive => s_od_drive, od_gain => od_gain,
      trem_depth => s_trem_depth, trem_wave => trem_wave, trem_rate => s_trem_rate,
      echo_time => s_echo_time, echo_frac => s_echo_frac,
      echo_level => s_echo_level, echo_repeat => s_echo_repeat,
      chorus_rate => s_chorus_rate, chorus_level => s_chorus_level, chorus_depth => s_chorus_depth,
      mod_base => s_mod_base, mod_fb => s_mod_fb, mod_shape => mod_shape,
      dist_mix => s_dist_mix, dist_type => dist_type,
      reverb_size => s_rev_size, reverb_damp => s_rev_damp, reverb_mix => s_reverb_mix,
      data_in_left  => rx_left,
      data_in_right => rx_right,
      data_out_left => fx_out, data_out_right => open);

  -- cabinet coefficient port. CAB_ADDR (0x1C) sets the write pointer (bit 11 bank,
  -- 10:0 tap); CAB_DATA_HI (0x1E) writes {HI(1:0), CAB_DATA_LO (0x1D)} at the pointer
  -- and increments the tap address (the bank bit stays). The FX chain ignores writes
  -- to the bank in use / requested (cab_stage).
  process(clk)
  begin
    if rising_edge(clk) then
      cab_cw_en <= '0';
      if rst = '1' then
        cab_ptr <= (others => '0');
      elsif ext_we = '1' then
        if ext_wa = x"1C" then
          cab_ptr <= unsigned(ext_wd(11 downto 0));
        elsif ext_wa = x"1E" then
          cab_cw_en   <= '1';
          cab_cw_bank <= cab_ptr(11);
          cab_cw_addr <= std_logic_vector(cab_ptr(10 downto 0));
          cab_cw_data <= ext_wd(1 downto 0) & ext_reg(ext, 16#1D#);
          cab_ptr(10 downto 0) <= cab_ptr(10 downto 0) + 1;
        end if;
      end if;
    end if;
  end process;

  -- EQ coefficient port. EQ_ADDR (0x28) sets the write pointer (0..15; 15 = scale word),
  -- EQ_DATA_HI (0x2A) writes {HI(1:0), EQ_DATA_LO (0x29)} at the pointer and increments it
  -- (wrapping 15 -> 0), EQ_APPLY (0x2B): any write pulses `apply` (the new set becomes active
  -- at the next half_tick, all sections together).
  process(clk)
  begin
    if rising_edge(clk) then
      eq_cw_en <= '0';
      eq_apply <= '0';
      if rst = '1' then
        eq_ptr <= (others => '0');
      elsif ext_we = '1' then
        if ext_wa = x"28" then
          eq_ptr <= unsigned(ext_wd(3 downto 0));
        elsif ext_wa = x"2A" then
          eq_cw_en   <= '1';
          eq_cw_addr <= std_logic_vector(eq_ptr);
          eq_cw_data <= ext_wd(1 downto 0) & ext_reg(ext, 16#29#);
          eq_ptr     <= eq_ptr + 1;
        elsif ext_wa = x"2B" then
          eq_apply <= '1';
        end if;
      end if;
    end if;
  end process;

  -- effect order: CHAIN_APPLY (0x33): any write pulses `apply` (the list in CHAIN_0..2 is checked and
  -- applied with the output fade); a read returns bit0 = fade running, bit1 = last list rejected.
  chain_2     <= ext_reg(ext, 16#32#);
  chain_order <= chain_2(3 downto 0) & ext_reg(ext, 16#31#) & ext_reg(ext, 16#30#);
  -- busy (bit 0) is also 1 from the clock after the write of CHAIN_APPLY until fx_route has taken the pulse (3 clocks), so a read right
  -- behind the write already sees it; the reject flag is valid when this pending time is over
  chain_status <= (0 => chain_busy or chain_apply or chain_apply_ev, 1 => chain_rejected, others => '0');
  chain_apply_ev <= '1' when ext_we = '1' and ext_wa = x"33" else '0';
  process(clk)
  begin
    if rising_edge(clk) then
      chain_apply <= '0';
      if rst = '0' and ext_we = '1' and ext_wa = x"33" then
        chain_apply <= '1';
      end if;
    end if;
  end process;

  rev_t    <= to_integer(unsigned(reverb_type(3 downto 0)));
  rev_size <= std_logic_vector(to_unsigned(room_size(rev_t), 16)) when rev_t < 4 else ext_rsize;
  rev_damp <= std_logic_vector(to_unsigned(room_damp(rev_t), 16)) when rev_t < 4
              else x"00" & ext_rdamp(7 downto 0);
  ext_rsize <= ext_reg(ext, 16#1F#);
  ext_rdamp <= ext_reg(ext, 16#20#);

  trem_rate <= ext_reg(ext, 16#16#);
  mod_base  <= ext_reg(ext, 16#18#);
  mod_fb    <= ext_reg(ext, 16#19#);
  mod_shape <= ext_reg(ext, 16#1A#);

  -- parameter smoothing: levels, depths, mixes, drive, LFO rates, the modulated
  -- delay's base / depth / feedback, the reverb size and damping (room preset or custom,
-- D4) and the echo time (with fraction: tape-style
  -- glide, step D2). Not smoothed: gain (integer factor), selectors, enables
  -- (crossfaded in FX_chain). The signed feedback is smoothed in offset binary.
  fb_ofs   <= (not mod_fb(15)) & mod_fb(14 downto 0);
  od_level     <= ext_reg(ext, 16#2D#);
  dist_level   <= ext_reg(ext, 16#2E#);
  od_lvl_ofs   <= (not od_level(15)) & od_level(14 downto 0);
  dist_lvl_ofs <= (not dist_level(15)) & dist_level(14 downto 0);
  s_od_level   <= (not s_od_lvl_ofs(15)) & s_od_lvl_ofs(14 downto 0);
  s_dist_level <= (not s_dist_lvl_ofs(15)) & s_dist_lvl_ofs(14 downto 0);
  s_mod_fb <= (not s_fb_ofs(15)) & s_fb_ofs(14 downto 0);
  smooth_on : if SMOOTH generate
    u_sm_drive  : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => od_drive,     value => s_od_drive);
    u_sm_tdepth : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => trem_depth,   value => s_trem_depth);
    u_sm_elevel : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => echo_level,   value => s_echo_level);
    u_sm_erep   : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => echo_repeat,  value => s_echo_repeat);
    u_sm_dmix   : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => dist_mix,     value => s_dist_mix);
    u_sm_clevel : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => chorus_level, value => s_chorus_level);
    u_sm_rmix   : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => reverb_mix,   value => s_reverb_mix);
    u_sm_rsize  : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => rev_size,     value => s_rev_size);
    u_sm_rdamp  : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => rev_damp,     value => s_rev_damp);
    u_sm_trate  : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => trem_rate,    value => s_trem_rate);
    u_sm_cdepth : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => chorus_depth, value => s_chorus_depth);
    u_sm_crate  : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => chorus_rate,  value => s_chorus_rate);
    u_sm_mbase  : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => mod_base,     value => s_mod_base);
    u_sm_mfb    : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => fb_ofs,       value => s_fb_ofs);
    -- level 0 (unity) = offset binary 0x8000 after reset: no fade-in from -24 dB at power-up
    u_sm_odlvl  : entity work.param_smooth generic map (INIT => 32768) port map (clk => clk, rst => rst, tick => sample_tick, target => od_lvl_ofs,   value => s_od_lvl_ofs);
    u_sm_dlvl   : entity work.param_smooth generic map (INIT => 32768) port map (clk => clk, rst => rst, tick => sample_tick, target => dist_lvl_ofs, value => s_dist_lvl_ofs);
    u_sm_etime  : entity work.param_smooth port map (clk => clk, rst => rst, tick => sample_tick, target => echo_time,    value => s_echo_time,
                                                     value_frac => s_echo_frac);
  end generate;
  smooth_off : if not SMOOTH generate
    s_od_drive <= od_drive;     s_trem_depth <= trem_depth;     s_echo_level <= echo_level;
    s_echo_repeat <= echo_repeat; s_dist_mix <= dist_mix;       s_chorus_level <= chorus_level;
    s_reverb_mix <= reverb_mix;   s_trem_rate <= trem_rate;     s_chorus_depth <= chorus_depth;
    s_chorus_rate <= chorus_rate; s_mod_base <= mod_base;       s_fb_ofs <= fb_ofs;
    s_echo_time <= echo_time;     s_echo_frac <= (others => '0');
    s_od_level <= od_level;       s_dist_level <= dist_level;
    s_rev_size <= rev_size;       s_rev_damp <= rev_damp;
  end generate;

  -- mono effects: processed left channel to both outputs
  tx_word <= (others => '0') when mute = '1' else fx_out;

  -- ---- control ----------------------------------------------------------------
  u_ctrl : entity work.ctrl_avmm
    generic map (VERSION => VERSION)
    port map (
      clk => clk, rst => rst,
      avs_address => avs_address, avs_read => avs_read, avs_write => avs_write,
      avs_writedata => avs_writedata, avs_byteenable => avs_byteenable,
      avs_readdata => avs_readdata,
      avs_readdatavalid => avs_readdatavalid, avs_waitrequest => avs_waitrequest,
      i2c_req => i2c_req, i2c_reg => i2c_reg, i2c_data => i2c_data,
      i2c_busy => i2c_busy, i2c_done => i2c_done, i2c_nak => i2c_nak,
      status_in => status, level_in => std_logic_vector(peak_in),
      level_out => std_logic_vector(peak_out),
      effects_enable => effects_enable, od_drive => od_drive, od_gain => od_gain,
      trem_wave => trem_wave, trem_depth => trem_depth, echo_time => echo_time,
      echo_repeat => echo_repeat, echo_level => echo_level, dist_mix => dist_mix,
      dist_type => dist_type, chorus_level => chorus_level, chorus_depth => chorus_depth,
      chorus_rate => chorus_rate, reverb_mix => reverb_mix, reverb_type => reverb_type, ext => ext,
      dyn_gr => dyn_gr, chain_status => chain_status,
      codec_init => codec_init, mute => mute,
      ext_we => ext_we, ext_wa => ext_wa, ext_wd => ext_wd);

  u_codec : entity work.codec_ctrl
    generic map (I2C_DIV => I2C_DIV, WAIT_CLKS => INIT_WAIT_CLKS)
    port map (
      clk => clk, rst => rst, init_start => codec_init,
      req => i2c_req, req_reg => i2c_reg, req_data => i2c_data,
      busy => i2c_busy, done => i2c_done, nak => i2c_nak,
      init_done => init_done, init_nak => init_nak,
      scl_oe => scl_oe, sda_oe => sda_oe, sda_in => sda_in);

  -- STATUS register: bit0 codec init done, bit1 codec NAK, bit2 PLL locked
  status <= (0 => init_done, 1 => init_nak, 2 => pll_locked, others => '0');

  -- ---- level meters and heartbeat (once per frame) -------------------------------
  process(clk)
  begin
    if rising_edge(clk) then
      if rst = '1' then
        peak_in  <= (others => '0');
        peak_out <= (others => '0');
        hb_cnt   <= 0;
        hb       <= '0';
      elsif sample_tick = '1' then
        peak_in  <= peak_update(peak_in, abs16(rx_left(23 downto 8)));
        peak_out <= peak_update(peak_out, abs16(fx_out(23 downto 8)));
        if hb_cnt = 23999 then
          hb_cnt <= 0;
          hb     <= not hb;                        -- 1 Hz blink
        else
          hb_cnt <= hb_cnt + 1;
        end if;
      end if;
    end if;
  end process;

  leds <= hb & init_nak & init_done & pll_locked;

end architecture;
