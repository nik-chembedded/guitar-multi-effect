-- -----------------------------------------------------------------------------
-- i2s_codec_model.vhd
--
-- Behavioural model of the DE1-SoC audio codec (WM8731 / SSM2603 compatible)
-- configured the way the Nios II firmware programs it:
--   * Master mode (codec drives BCLK and LRCLK)          R7  = 0x42
--   * I2S format, 16-bit words                           R7  = 0x42
--   * Normal mode, 384fs, 48 kHz from MCLK = 18.432 MHz   R8  = 0x02
--
-- In this mode BCLK = MCLK/4 and one LRCLK period is 96 BCLKs (48 per channel).
-- LRCLK and ADCDAT change on the falling edge of BCLK; the codec samples DACDAT
-- on the rising edge. I2S places the MSB one BCLK after the LRCLK edge.
--
-- Sample interface:
--   * adc_left/adc_right are latched at the start of every frame; frame_start
--     pulses at that moment so the testbench can present the next sample.
--   * dac_left/dac_right hold the last word received; dac_valid pulses once
--     per frame after the right word is complete. dac_meta is TRUE if the
--     received left word contained X/U/Z/W bits.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity i2s_codec_model is
  generic (
    MCLK_PERIOD : time     := 54.253 ns;  -- 18.432 MHz
    BCLK_DIV    : positive := 4;          -- BCLK = MCLK / BCLK_DIV
    BITS_PER_CH : positive := 48          -- BCLKs per channel (fs = MCLK/(BCLK_DIV*2*BITS_PER_CH))
  );
  port (
    enable      : in  boolean;
    mclk        : out std_logic;
    bclk        : out std_logic;
    lrclk       : out std_logic;
    adcdat      : out std_logic;
    dacdat      : in  std_logic;

    adc_left    : in  integer;
    adc_right   : in  integer;
    frame_start : out std_logic;

    dac_left    : out integer;
    dac_right   : out integer;
    dac_meta    : out boolean;
    dac_valid   : out std_logic
  );
end entity;

architecture behav of i2s_codec_model is
  signal mclk_i  : std_logic := '0';
  signal bclk_i  : std_logic := '0';
  signal lrclk_i : std_logic := '1';
begin

  mclk  <= mclk_i;
  bclk  <= bclk_i;
  lrclk <= lrclk_i;

  mclk_gen : process
  begin
    while enable loop
      mclk_i <= '1';
      wait for MCLK_PERIOD / 2;
      mclk_i <= '0';
      wait for MCLK_PERIOD / 2;
    end loop;
    wait until enable;
  end process;

  bclk_gen : process(mclk_i)
    variable cnt : natural := 0;
  begin
    if rising_edge(mclk_i) then
      cnt := cnt + 1;
      if cnt = BCLK_DIV / 2 then
        cnt    := 0;
        bclk_i <= not bclk_i;
      end if;
    end if;
  end process;

  -- ADC side: drive LRCLK and serial ADC data on the falling BCLK edge
  tx : process(bclk_i)
    variable pos    : natural := 0;    -- falling-edge index within the frame
    variable p      : natural;
    variable wl, wr : signed(15 downto 0) := (others => '0');
  begin
    if falling_edge(bclk_i) then
      if pos = 0 then
        wl          := to_signed(adc_left, 16);
        wr          := to_signed(adc_right, 16);
        lrclk_i     <= '0';            -- left channel
        frame_start <= '1';
      else
        frame_start <= '0';
      end if;
      if pos = BITS_PER_CH then
        lrclk_i <= '1';                -- right channel
      end if;

      p := pos mod BITS_PER_CH;
      if p >= 1 and p <= 16 then       -- I2S: MSB one BCLK after the LRCLK edge
        if pos < BITS_PER_CH then
          adcdat <= wl(16 - p);
        else
          adcdat <= wr(16 - p);
        end if;
      else
        adcdat <= '0';
      end if;

      pos := (pos + 1) mod (2 * BITS_PER_CH);
    end if;
  end process;

  -- DAC side: sample serial DAC data on the rising BCLK edge
  rx : process(bclk_i)
    variable rpos    : natural := 0;   -- rising edges since the last LRCLK edge
    variable last_lr : std_logic := '1';
    variable sh      : std_logic_vector(15 downto 0) := (others => '0');
  begin
    if rising_edge(bclk_i) then
      dac_valid <= '0';
      if lrclk_i /= last_lr then
        rpos    := 0;
        last_lr := lrclk_i;
      end if;

      if rpos >= 1 and rpos <= 16 then
        sh(16 - rpos) := dacdat;
      end if;

      if rpos = 16 then
        if last_lr = '0' then
          dac_meta <= is_x(sh);
          if is_x(sh) then
            dac_left <= 0;
          else
            dac_left <= to_integer(signed(sh));
          end if;
        else
          if is_x(sh) then
            dac_right <= 0;
          else
            dac_right <= to_integer(signed(sh));
          end if;
          dac_valid <= '1';
        end if;
      end if;

      rpos := rpos + 1;
    end if;
  end process;

end architecture;
