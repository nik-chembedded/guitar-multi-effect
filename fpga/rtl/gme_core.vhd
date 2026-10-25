-- -----------------------------------------------------------------------------
-- gme_core.vhd  (v2 step B5)
-- Everything of the multi-effect that runs on sys_clk (49.152 MHz):
--   i2s_core   FPGA = I2S master, stereo 24-bit, sample_tick / half_tick
--   FX_chain   the v1 effects (16-bit), mono: left input, output to both channels
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
    VERSION        : std_logic_vector(15 downto 0) := x"0201"
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
  signal fx_out, fx_out_r       : std_logic_vector(15 downto 0);

  signal effects_enable, od_drive, od_gain, trem_wave, trem_depth, echo_time, echo_repeat,
         echo_level, dist_mix, dist_type, chorus_level, chorus_depth, chorus_rate,
         reverb_mix, reverb_type : std_logic_vector(15 downto 0);
  signal codec_init, mute       : std_logic;

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
    port map (
      clk => clk, sample_tick => sample_tick, half_tick => half_tick,
      od_enable => '0', tremolo_enable => '0', echo_enable => '0',
      effects_enable => effects_enable, od_drive => od_drive, od_gain => od_gain,
      trem_depth => trem_depth, trem_wave => trem_wave,
      echo_time => echo_time, echo_level => echo_level, echo_repeat => echo_repeat,
      chorus_rate => chorus_rate, chorus_level => chorus_level, chorus_depth => chorus_depth,
      dist_mix => dist_mix, dist_type => dist_type,
      reverb_type => reverb_type, reverb_mix => reverb_mix,
      data_in_left  => rx_left(23 downto 8),      -- effects are 16-bit until step C
      data_in_right => rx_right(23 downto 8),
      data_out_left => fx_out, data_out_right => open);

  -- mono effects: processed left channel to both outputs
  tx_word <= (others => '0') when mute = '1' else fx_out & x"00";

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
      chorus_rate => chorus_rate, reverb_mix => reverb_mix, reverb_type => reverb_type,
      codec_init => codec_init, mute => mute);

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
        peak_out <= peak_update(peak_out, abs16(fx_out));
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
