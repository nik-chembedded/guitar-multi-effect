-- -----------------------------------------------------------------------------
-- top_v2.vhd  (v2) - Terasic DE1-SoC top level
-- PLL (49.152 MHz system clock + 12.288 MHz codec MCLK), the HPS (hps_sys:
-- Platform Designer, DDR3 + HPS I/O as in Terasic's GHRD, lightweight bridge
-- to an Avalon-MM bridge), reset synchroniser, open-drain I2C buffers, gme_core.
-- Control: Linux on the HPS writes the registers at 0xFF200000 + 4*n.
-- The HPS-to-FPGA bridge runs on sys_clk, so the design has one clock domain.
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
    -- status: 0 PLL locked, 1 codec init done, 2 codec NAK, 3 heartbeat
    LEDR         : out   std_logic_vector(3 downto 0);
    -- HPS: DDR3
    HPS_DDR3_ADDR    : out   std_logic_vector(14 downto 0);
    HPS_DDR3_BA      : out   std_logic_vector(2 downto 0);
    HPS_DDR3_CAS_N   : out   std_logic;
    HPS_DDR3_CKE     : out   std_logic;
    HPS_DDR3_CK_N    : out   std_logic;
    HPS_DDR3_CK_P    : out   std_logic;
    HPS_DDR3_CS_N    : out   std_logic;
    HPS_DDR3_DM      : out   std_logic_vector(3 downto 0);
    HPS_DDR3_DQ      : inout std_logic_vector(31 downto 0);
    HPS_DDR3_DQS_N   : inout std_logic_vector(3 downto 0);
    HPS_DDR3_DQS_P   : inout std_logic_vector(3 downto 0);
    HPS_DDR3_ODT     : out   std_logic;
    HPS_DDR3_RAS_N   : out   std_logic;
    HPS_DDR3_RESET_N : out   std_logic;
    HPS_DDR3_RZQ     : in    std_logic;
    HPS_DDR3_WE_N    : out   std_logic;
    -- HPS: peripherals (pin-mux of the GHRD)
    HPS_CONV_USB_N   : inout std_logic;
    HPS_ENET_GTX_CLK : out   std_logic;
    HPS_ENET_INT_N   : inout std_logic;
    HPS_ENET_MDC     : out   std_logic;
    HPS_ENET_MDIO    : inout std_logic;
    HPS_ENET_RX_CLK  : in    std_logic;
    HPS_ENET_RX_DATA : in    std_logic_vector(3 downto 0);
    HPS_ENET_RX_DV   : in    std_logic;
    HPS_ENET_TX_DATA : out   std_logic_vector(3 downto 0);
    HPS_ENET_TX_EN   : out   std_logic;
    HPS_FLASH_DATA   : inout std_logic_vector(3 downto 0);
    HPS_FLASH_DCLK   : out   std_logic;
    HPS_FLASH_NCSO   : out   std_logic;
    HPS_GSENSOR_INT  : inout std_logic;
    HPS_I2C1_SCLK    : inout std_logic;
    HPS_I2C1_SDAT    : inout std_logic;
    HPS_I2C2_SCLK    : inout std_logic;
    HPS_I2C2_SDAT    : inout std_logic;
    HPS_I2C_CONTROL  : inout std_logic;
    HPS_KEY          : inout std_logic;
    HPS_LED          : inout std_logic;
    HPS_LTC_GPIO     : inout std_logic;
    HPS_SD_CLK       : out   std_logic;
    HPS_SD_CMD       : inout std_logic;
    HPS_SD_DATA      : inout std_logic_vector(3 downto 0);
    HPS_SPIM_CLK     : out   std_logic;
    HPS_SPIM_MISO    : in    std_logic;
    HPS_SPIM_MOSI    : out   std_logic;
    HPS_SPIM_SS      : inout std_logic;
    HPS_UART_RX      : in    std_logic;
    HPS_UART_TX      : out   std_logic;
    HPS_USB_CLKOUT   : in    std_logic;
    HPS_USB_DATA     : inout std_logic_vector(7 downto 0);
    HPS_USB_DIR      : in    std_logic;
    HPS_USB_NXT      : in    std_logic;
    HPS_USB_STP      : out   std_logic
  );
end entity;

architecture rtl of top_v2 is
  component pll_sys is
    port (refclk : in std_logic; rst : in std_logic;
          sys_clk : out std_logic; mclk : out std_logic; locked : out std_logic);
  end component;

  component hps_sys is
    port (
      clk_clk                 : in    std_logic;
      reset_reset_n           : in    std_logic;
      gme_regs_waitrequest    : in    std_logic;
      gme_regs_readdata       : in    std_logic_vector(31 downto 0);
      gme_regs_readdatavalid  : in    std_logic;
      gme_regs_burstcount     : out   std_logic_vector(0 downto 0);
      gme_regs_writedata      : out   std_logic_vector(31 downto 0);
      gme_regs_address        : out   std_logic_vector(7 downto 0);
      gme_regs_write          : out   std_logic;
      gme_regs_read           : out   std_logic;
      gme_regs_byteenable     : out   std_logic_vector(3 downto 0);
      gme_regs_debugaccess    : out   std_logic;
      hps_0_h2f_reset_reset_n : out   std_logic;
      hps_0_hps_io_hps_io_emac1_inst_TX_CLK : out   std_logic;
      hps_0_hps_io_hps_io_emac1_inst_TXD0   : out   std_logic;
      hps_0_hps_io_hps_io_emac1_inst_TXD1   : out   std_logic;
      hps_0_hps_io_hps_io_emac1_inst_TXD2   : out   std_logic;
      hps_0_hps_io_hps_io_emac1_inst_TXD3   : out   std_logic;
      hps_0_hps_io_hps_io_emac1_inst_RXD0   : in    std_logic;
      hps_0_hps_io_hps_io_emac1_inst_MDIO   : inout std_logic;
      hps_0_hps_io_hps_io_emac1_inst_MDC    : out   std_logic;
      hps_0_hps_io_hps_io_emac1_inst_RX_CTL : in    std_logic;
      hps_0_hps_io_hps_io_emac1_inst_TX_CTL : out   std_logic;
      hps_0_hps_io_hps_io_emac1_inst_RX_CLK : in    std_logic;
      hps_0_hps_io_hps_io_emac1_inst_RXD1   : in    std_logic;
      hps_0_hps_io_hps_io_emac1_inst_RXD2   : in    std_logic;
      hps_0_hps_io_hps_io_emac1_inst_RXD3   : in    std_logic;
      hps_0_hps_io_hps_io_qspi_inst_IO0     : inout std_logic;
      hps_0_hps_io_hps_io_qspi_inst_IO1     : inout std_logic;
      hps_0_hps_io_hps_io_qspi_inst_IO2     : inout std_logic;
      hps_0_hps_io_hps_io_qspi_inst_IO3     : inout std_logic;
      hps_0_hps_io_hps_io_qspi_inst_SS0     : out   std_logic;
      hps_0_hps_io_hps_io_qspi_inst_CLK     : out   std_logic;
      hps_0_hps_io_hps_io_sdio_inst_CMD     : inout std_logic;
      hps_0_hps_io_hps_io_sdio_inst_D0      : inout std_logic;
      hps_0_hps_io_hps_io_sdio_inst_D1      : inout std_logic;
      hps_0_hps_io_hps_io_sdio_inst_CLK     : out   std_logic;
      hps_0_hps_io_hps_io_sdio_inst_D2      : inout std_logic;
      hps_0_hps_io_hps_io_sdio_inst_D3      : inout std_logic;
      hps_0_hps_io_hps_io_usb1_inst_D0      : inout std_logic;
      hps_0_hps_io_hps_io_usb1_inst_D1      : inout std_logic;
      hps_0_hps_io_hps_io_usb1_inst_D2      : inout std_logic;
      hps_0_hps_io_hps_io_usb1_inst_D3      : inout std_logic;
      hps_0_hps_io_hps_io_usb1_inst_D4      : inout std_logic;
      hps_0_hps_io_hps_io_usb1_inst_D5      : inout std_logic;
      hps_0_hps_io_hps_io_usb1_inst_D6      : inout std_logic;
      hps_0_hps_io_hps_io_usb1_inst_D7      : inout std_logic;
      hps_0_hps_io_hps_io_usb1_inst_CLK     : in    std_logic;
      hps_0_hps_io_hps_io_usb1_inst_STP     : out   std_logic;
      hps_0_hps_io_hps_io_usb1_inst_DIR     : in    std_logic;
      hps_0_hps_io_hps_io_usb1_inst_NXT     : in    std_logic;
      hps_0_hps_io_hps_io_spim1_inst_CLK    : out   std_logic;
      hps_0_hps_io_hps_io_spim1_inst_MOSI   : out   std_logic;
      hps_0_hps_io_hps_io_spim1_inst_MISO   : in    std_logic;
      hps_0_hps_io_hps_io_spim1_inst_SS0    : out   std_logic;
      hps_0_hps_io_hps_io_uart0_inst_RX     : in    std_logic;
      hps_0_hps_io_hps_io_uart0_inst_TX     : out   std_logic;
      hps_0_hps_io_hps_io_i2c0_inst_SDA     : inout std_logic;
      hps_0_hps_io_hps_io_i2c0_inst_SCL     : inout std_logic;
      hps_0_hps_io_hps_io_i2c1_inst_SDA     : inout std_logic;
      hps_0_hps_io_hps_io_i2c1_inst_SCL     : inout std_logic;
      hps_0_hps_io_hps_io_gpio_inst_GPIO09  : inout std_logic;
      hps_0_hps_io_hps_io_gpio_inst_GPIO35  : inout std_logic;
      hps_0_hps_io_hps_io_gpio_inst_GPIO40  : inout std_logic;
      hps_0_hps_io_hps_io_gpio_inst_GPIO48  : inout std_logic;
      hps_0_hps_io_hps_io_gpio_inst_GPIO53  : inout std_logic;
      hps_0_hps_io_hps_io_gpio_inst_GPIO54  : inout std_logic;
      hps_0_hps_io_hps_io_gpio_inst_GPIO61  : inout std_logic;
      memory_mem_a       : out   std_logic_vector(14 downto 0);
      memory_mem_ba      : out   std_logic_vector(2 downto 0);
      memory_mem_ck      : out   std_logic;
      memory_mem_ck_n    : out   std_logic;
      memory_mem_cke     : out   std_logic;
      memory_mem_cs_n    : out   std_logic;
      memory_mem_ras_n   : out   std_logic;
      memory_mem_cas_n   : out   std_logic;
      memory_mem_we_n    : out   std_logic;
      memory_mem_reset_n : out   std_logic;
      memory_mem_dq      : inout std_logic_vector(31 downto 0);
      memory_mem_dqs     : inout std_logic_vector(3 downto 0);
      memory_mem_dqs_n   : inout std_logic_vector(3 downto 0);
      memory_mem_odt     : out   std_logic;
      memory_mem_dm      : out   std_logic_vector(3 downto 0);
      memory_oct_rzqin   : in    std_logic
    );
  end component;

  signal sys_clk, locked : std_logic;
  signal rst_sync        : std_logic_vector(2 downto 0) := (others => '1');
  signal rst, rst_n      : std_logic;
  signal lrclk           : std_logic;
  signal scl_oe, sda_oe  : std_logic;
  signal sda_meta, sda_s : std_logic := '1';

  signal avs_address       : std_logic_vector(7 downto 0);
  signal avs_read, avs_write, avs_readdatavalid, avs_waitrequest : std_logic;
  signal avs_writedata, avs_readdata : std_logic_vector(31 downto 0);
  signal avs_byteenable    : std_logic_vector(3 downto 0);
begin

  u_pll : pll_sys
    port map (refclk => CLOCK_50, rst => not KEY0, sys_clk => sys_clk, mclk => AUD_XCK, locked => locked);

  -- reset: asynchronous assert (button or PLL not locked), synchronous release.
  -- The HPS (h2f_reset) does not reset the audio: Linux can reboot while it plays.
  process(sys_clk, KEY0, locked)
  begin
    if KEY0 = '0' or locked = '0' then
      rst_sync <= (others => '1');
    elsif rising_edge(sys_clk) then
      rst_sync <= rst_sync(1 downto 0) & '0';
    end if;
  end process;
  rst   <= rst_sync(2);
  rst_n <= not rst;

  -- asynchronous input: 2-FF synchroniser
  process(sys_clk)
  begin
    if rising_edge(sys_clk) then
      sda_meta <= FPGA_I2C_SDAT; sda_s <= sda_meta;
    end if;
  end process;

  u_hps : hps_sys
    port map (
      clk_clk => sys_clk, reset_reset_n => rst_n,
      gme_regs_waitrequest => avs_waitrequest, gme_regs_readdata => avs_readdata,
      gme_regs_readdatavalid => avs_readdatavalid, gme_regs_burstcount => open,
      gme_regs_writedata => avs_writedata, gme_regs_address => avs_address,
      gme_regs_write => avs_write, gme_regs_read => avs_read,
      gme_regs_byteenable => avs_byteenable, gme_regs_debugaccess => open,
      hps_0_h2f_reset_reset_n => open,
      -- DDR3
      memory_mem_a => HPS_DDR3_ADDR, memory_mem_ba => HPS_DDR3_BA,
      memory_mem_ck => HPS_DDR3_CK_P, memory_mem_ck_n => HPS_DDR3_CK_N,
      memory_mem_cke => HPS_DDR3_CKE, memory_mem_cs_n => HPS_DDR3_CS_N,
      memory_mem_ras_n => HPS_DDR3_RAS_N, memory_mem_cas_n => HPS_DDR3_CAS_N,
      memory_mem_we_n => HPS_DDR3_WE_N, memory_mem_reset_n => HPS_DDR3_RESET_N,
      memory_mem_dq => HPS_DDR3_DQ, memory_mem_dqs => HPS_DDR3_DQS_P,
      memory_mem_dqs_n => HPS_DDR3_DQS_N, memory_mem_odt => HPS_DDR3_ODT,
      memory_mem_dm => HPS_DDR3_DM, memory_oct_rzqin => HPS_DDR3_RZQ,
      -- Ethernet
      hps_0_hps_io_hps_io_emac1_inst_TX_CLK => HPS_ENET_GTX_CLK,
      hps_0_hps_io_hps_io_emac1_inst_TXD0   => HPS_ENET_TX_DATA(0),
      hps_0_hps_io_hps_io_emac1_inst_TXD1   => HPS_ENET_TX_DATA(1),
      hps_0_hps_io_hps_io_emac1_inst_TXD2   => HPS_ENET_TX_DATA(2),
      hps_0_hps_io_hps_io_emac1_inst_TXD3   => HPS_ENET_TX_DATA(3),
      hps_0_hps_io_hps_io_emac1_inst_RXD0   => HPS_ENET_RX_DATA(0),
      hps_0_hps_io_hps_io_emac1_inst_MDIO   => HPS_ENET_MDIO,
      hps_0_hps_io_hps_io_emac1_inst_MDC    => HPS_ENET_MDC,
      hps_0_hps_io_hps_io_emac1_inst_RX_CTL => HPS_ENET_RX_DV,
      hps_0_hps_io_hps_io_emac1_inst_TX_CTL => HPS_ENET_TX_EN,
      hps_0_hps_io_hps_io_emac1_inst_RX_CLK => HPS_ENET_RX_CLK,
      hps_0_hps_io_hps_io_emac1_inst_RXD1   => HPS_ENET_RX_DATA(1),
      hps_0_hps_io_hps_io_emac1_inst_RXD2   => HPS_ENET_RX_DATA(2),
      hps_0_hps_io_hps_io_emac1_inst_RXD3   => HPS_ENET_RX_DATA(3),
      -- QSPI flash
      hps_0_hps_io_hps_io_qspi_inst_IO0 => HPS_FLASH_DATA(0),
      hps_0_hps_io_hps_io_qspi_inst_IO1 => HPS_FLASH_DATA(1),
      hps_0_hps_io_hps_io_qspi_inst_IO2 => HPS_FLASH_DATA(2),
      hps_0_hps_io_hps_io_qspi_inst_IO3 => HPS_FLASH_DATA(3),
      hps_0_hps_io_hps_io_qspi_inst_SS0 => HPS_FLASH_NCSO,
      hps_0_hps_io_hps_io_qspi_inst_CLK => HPS_FLASH_DCLK,
      -- SD card
      hps_0_hps_io_hps_io_sdio_inst_CMD => HPS_SD_CMD,
      hps_0_hps_io_hps_io_sdio_inst_D0  => HPS_SD_DATA(0),
      hps_0_hps_io_hps_io_sdio_inst_D1  => HPS_SD_DATA(1),
      hps_0_hps_io_hps_io_sdio_inst_CLK => HPS_SD_CLK,
      hps_0_hps_io_hps_io_sdio_inst_D2  => HPS_SD_DATA(2),
      hps_0_hps_io_hps_io_sdio_inst_D3  => HPS_SD_DATA(3),
      -- USB
      hps_0_hps_io_hps_io_usb1_inst_D0  => HPS_USB_DATA(0),
      hps_0_hps_io_hps_io_usb1_inst_D1  => HPS_USB_DATA(1),
      hps_0_hps_io_hps_io_usb1_inst_D2  => HPS_USB_DATA(2),
      hps_0_hps_io_hps_io_usb1_inst_D3  => HPS_USB_DATA(3),
      hps_0_hps_io_hps_io_usb1_inst_D4  => HPS_USB_DATA(4),
      hps_0_hps_io_hps_io_usb1_inst_D5  => HPS_USB_DATA(5),
      hps_0_hps_io_hps_io_usb1_inst_D6  => HPS_USB_DATA(6),
      hps_0_hps_io_hps_io_usb1_inst_D7  => HPS_USB_DATA(7),
      hps_0_hps_io_hps_io_usb1_inst_CLK => HPS_USB_CLKOUT,
      hps_0_hps_io_hps_io_usb1_inst_STP => HPS_USB_STP,
      hps_0_hps_io_hps_io_usb1_inst_DIR => HPS_USB_DIR,
      hps_0_hps_io_hps_io_usb1_inst_NXT => HPS_USB_NXT,
      -- SPI (LTC connector), UART (USB-UART console), I2C
      hps_0_hps_io_hps_io_spim1_inst_CLK  => HPS_SPIM_CLK,
      hps_0_hps_io_hps_io_spim1_inst_MOSI => HPS_SPIM_MOSI,
      hps_0_hps_io_hps_io_spim1_inst_MISO => HPS_SPIM_MISO,
      hps_0_hps_io_hps_io_spim1_inst_SS0  => HPS_SPIM_SS,
      hps_0_hps_io_hps_io_uart0_inst_RX   => HPS_UART_RX,
      hps_0_hps_io_hps_io_uart0_inst_TX   => HPS_UART_TX,
      hps_0_hps_io_hps_io_i2c0_inst_SDA   => HPS_I2C1_SDAT,
      hps_0_hps_io_hps_io_i2c0_inst_SCL   => HPS_I2C1_SCLK,
      hps_0_hps_io_hps_io_i2c1_inst_SDA   => HPS_I2C2_SDAT,
      hps_0_hps_io_hps_io_i2c1_inst_SCL   => HPS_I2C2_SCLK,
      -- GPIO
      hps_0_hps_io_hps_io_gpio_inst_GPIO09 => HPS_CONV_USB_N,
      hps_0_hps_io_hps_io_gpio_inst_GPIO35 => HPS_ENET_INT_N,
      hps_0_hps_io_hps_io_gpio_inst_GPIO40 => HPS_LTC_GPIO,
      hps_0_hps_io_hps_io_gpio_inst_GPIO48 => HPS_I2C_CONTROL,
      hps_0_hps_io_hps_io_gpio_inst_GPIO53 => HPS_LED,
      hps_0_hps_io_hps_io_gpio_inst_GPIO54 => HPS_KEY,
      hps_0_hps_io_hps_io_gpio_inst_GPIO61 => HPS_GSENSOR_INT);

  -- the cabinet's power-up coefficients: Quartus looks for the .mif relative to the project
  u_core : entity work.gme_core
    generic map (CAB_INIT => "ip/cab_default.mif")
    port map (
      clk => sys_clk, rst => rst, pll_locked => locked,
      bclk => AUD_BCLK, lrclk => lrclk, dacdat => AUD_DACDAT, adcdat => AUD_ADCDAT,
      scl_oe => scl_oe, sda_oe => sda_oe, sda_in => sda_s,
      avs_address => avs_address, avs_read => avs_read, avs_write => avs_write,
      avs_writedata => avs_writedata, avs_byteenable => avs_byteenable,
      avs_readdata => avs_readdata,
      avs_readdatavalid => avs_readdatavalid, avs_waitrequest => avs_waitrequest,
      leds => LEDR);

  AUD_ADCLRCK <= lrclk;
  AUD_DACLRCK <= lrclk;

  -- open-drain I2C (board pull-ups)
  FPGA_I2C_SCLK <= '0' when scl_oe = '1' else 'Z';
  FPGA_I2C_SDAT <= '0' when sda_oe = '1' else 'Z';

end architecture;
