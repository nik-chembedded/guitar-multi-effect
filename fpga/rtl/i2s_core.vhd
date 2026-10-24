-- -----------------------------------------------------------------------------
-- i2s_core.vhd  (v2 step B2)
--
-- I2S master for the WM8731 codec in slave mode (R7 = 0x0A: I2S, 24-bit),
-- stereo, 24-bit, 48 kHz from a 49.152 MHz system clock (1024 clocks/frame).
--
-- Everything is derived from one frame counter in the clk domain:
--   cnt   = 0..1023            one LRCLK frame
--   bit   = cnt / 16 (0..63)   BCLK = clk / 16 = 3.072 MHz, 32 bits per channel
--   phase = cnt mod 16         BCLK = '0' for phase 0..7, '1' for 8..15
--   LRCLK = '0' for bits 0..31 (left), '1' for 32..63 (right); it changes
--           together with a BCLK falling edge, as I2S requires.
--   slot  = bit mod 32: slot 0 is the I2S one-bit delay, slots 1..24 carry
--           data bits 23..0 (MSB first), slots 25..31 are zero.
--   DACDAT changes at phase 0 (BCLK falling), the codec samples it on rising.
--   ADCDAT is sampled at phase 8 (BCLK rising); the codec drives it on falling.
--
-- Strobes (one clk cycle wide):
--   sample_tick  cnt = 960: both received channels are valid on rx_left/rx_right
--   half_tick    cnt = 448: half a frame later (second step of the effect chain)
-- tx_left/tx_right are latched at cnt = 0 and sent during that frame.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity i2s_core is
  port (
    clk         : in  std_logic;                       -- 49.152 MHz
    rst         : in  std_logic;                       -- synchronous, active high

    -- codec pins
    bclk        : out std_logic;
    lrclk       : out std_logic;                       -- to ADCLRCK and DACLRCK
    dacdat      : out std_logic;
    adcdat      : in  std_logic;

    -- sample interface
    rx_left     : out std_logic_vector(23 downto 0);   -- valid from sample_tick on
    rx_right    : out std_logic_vector(23 downto 0);
    tx_left     : in  std_logic_vector(23 downto 0);   -- latched at the frame start
    tx_right    : in  std_logic_vector(23 downto 0);
    sample_tick : out std_logic;
    half_tick   : out std_logic
  );
end entity;

architecture rtl of i2s_core is
  constant SAMPLE_CNT : natural := 960;
  constant HALF_CNT   : natural := 448;

  signal cnt       : unsigned(9 downto 0) := (others => '0');
  signal tx_l_reg  : std_logic_vector(23 downto 0) := (others => '0');
  signal tx_r_reg  : std_logic_vector(23 downto 0) := (others => '0');
  signal rx_shift  : std_logic_vector(23 downto 0) := (others => '0');
  signal rx_l_hold : std_logic_vector(23 downto 0) := (others => '0');
  signal rx_l_out  : std_logic_vector(23 downto 0) := (others => '0');
  signal rx_r_out  : std_logic_vector(23 downto 0) := (others => '0');
  signal bclk_r    : std_logic := '0';
  signal lrclk_r   : std_logic := '0';
  signal dacdat_r  : std_logic := '0';
  signal stick_r   : std_logic := '0';
  signal htick_r   : std_logic := '0';
begin

  process(clk)
    variable bit_i  : natural range 0 to 63;
    variable phase  : natural range 0 to 15;
    variable slot   : natural range 0 to 31;
    variable right  : boolean;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        cnt      <= (others => '0');
        bclk_r   <= '0';
        lrclk_r  <= '0';
        dacdat_r <= '0';
        stick_r  <= '0';
        htick_r  <= '0';
      else
        cnt   <= cnt + 1;
        bit_i := to_integer(cnt(9 downto 4));
        phase := to_integer(cnt(3 downto 0));
        slot  := bit_i mod 32;
        right := bit_i >= 32;

        -- clocks
        if phase = 0 then bclk_r <= '0'; elsif phase = 8 then bclk_r <= '1'; end if;
        if phase = 0 then
          if right then lrclk_r <= '1'; else lrclk_r <= '0'; end if;
        end if;

        -- transmit: new bit with the BCLK falling edge
        if cnt = 0 then
          tx_l_reg <= tx_left;
          tx_r_reg <= tx_right;
        end if;
        if phase = 0 then
          if slot >= 1 and slot <= 24 then
            if right then
              dacdat_r <= tx_r_reg(24 - slot);
            else
              dacdat_r <= tx_l_reg(24 - slot);
            end if;
          else
            dacdat_r <= '0';
          end if;
        end if;

        -- receive: sample with the BCLK rising edge
        if phase = 8 and slot >= 1 and slot <= 24 then
          rx_shift <= rx_shift(22 downto 0) & adcdat;
          if slot = 24 then
            if right then
              rx_r_out <= rx_shift(22 downto 0) & adcdat;
              rx_l_out <= rx_l_hold;
            else
              rx_l_hold <= rx_shift(22 downto 0) & adcdat;
            end if;
          end if;
        end if;

        -- strobes
        if cnt = SAMPLE_CNT - 1 then stick_r <= '1'; else stick_r <= '0'; end if;
        if cnt = HALF_CNT - 1 then htick_r <= '1'; else htick_r <= '0'; end if;
      end if;
    end if;
  end process;

  bclk        <= bclk_r;
  lrclk       <= lrclk_r;
  dacdat      <= dacdat_r;
  rx_left     <= rx_l_out;
  rx_right    <= rx_r_out;
  sample_tick <= stick_r;
  half_tick   <= htick_r;

end architecture;
