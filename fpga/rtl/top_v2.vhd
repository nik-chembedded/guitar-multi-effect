-- -----------------------------------------------------------------------------
-- top_v2.vhd  (v2 step B5) - Terasic DE1-SoC top level
-- PLL (49.152 MHz system clock + 12.288 MHz codec MCLK), reset synchroniser,
-- open-drain I2C buffers, and gme_core. No Nios II, no SDRAM, no Platform
-- Designer. Control: UART on GPIO_0 (115200 8N1, framed protocol).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity top_v2 is
  port (
    CLOCK_50     : in    std_logic;
    KEY0         : in    std_logic;                     -- push button, low = reset
    -- audio codec (FPGA is I2S master)
    AUD_XCK      : out   std_logic;                     -- MCLK 12.288 MHz
    AUD_BCLK     : out   std_logic;
    AUD_ADCLRCK  : out   std_logic;
    AUD_DACLRCK  : out   std_logic;
    AUD_ADCDAT   : in    std_logic;
    AUD_DACDAT   : out   std_logic;
    FPGA_I2C_SCLK: inout std_logic;
    FPGA_I2C_SDAT: inout std_logic;
    -- host UART on GPIO_0 (3.3 V USB-UART adapter)
    UART_RX      : in    std_logic;                     -- GPIO_0 D0
    UART_TX      : out   std_logic;                     -- GPIO_0 D1
    -- status: 0 PLL locked, 1 codec init done, 2 codec NAK, 3 heartbeat
    LEDR         : out   std_logic_vector(3 downto 0)
  );
end entity;

architecture rtl of top_v2 is
  component pll_sys is
    port (refclk : in std_logic; rst : in std_logic;
          sys_clk : out std_logic; mclk : out std_logic; locked : out std_logic);
  end component;

  signal sys_clk, locked : std_logic;
  signal rst_sync        : std_logic_vector(2 downto 0) := (others => '1');
  signal rst             : std_logic;
  signal lrclk           : std_logic;
  signal scl_oe, sda_oe  : std_logic;
  signal sda_meta, sda_s : std_logic := '1';
  signal rx_meta, rx_s   : std_logic := '1';
begin

  u_pll : pll_sys
    port map (refclk => CLOCK_50, rst => not KEY0, sys_clk => sys_clk, mclk => AUD_XCK, locked => locked);

  -- reset: asynchronous assert (button or PLL not locked), synchronous release
  process(sys_clk, KEY0, locked)
  begin
    if KEY0 = '0' or locked = '0' then
      rst_sync <= (others => '1');
    elsif rising_edge(sys_clk) then
      rst_sync <= rst_sync(1 downto 0) & '0';
    end if;
  end process;
  rst <= rst_sync(2);

  -- asynchronous inputs: 2-FF synchronisers
  process(sys_clk)
  begin
    if rising_edge(sys_clk) then
      sda_meta <= FPGA_I2C_SDAT; sda_s <= sda_meta;
      rx_meta  <= UART_RX;       rx_s  <= rx_meta;
    end if;
  end process;

  u_core : entity work.gme_core
    port map (
      clk => sys_clk, rst => rst, pll_locked => locked,
      bclk => AUD_BCLK, lrclk => lrclk, dacdat => AUD_DACDAT, adcdat => AUD_ADCDAT,
      scl_oe => scl_oe, sda_oe => sda_oe, sda_in => sda_s,
      uart_rx => rx_s, uart_tx => UART_TX,
      leds => LEDR);

  AUD_ADCLRCK <= lrclk;
  AUD_DACLRCK <= lrclk;

  -- open-drain I2C (board pull-ups)
  FPGA_I2C_SCLK <= '0' when scl_oe = '1' else 'Z';
  FPGA_I2C_SDAT <= '0' when sda_oe = '1' else 'Z';

end architecture;
