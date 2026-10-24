-- -----------------------------------------------------------------------------
-- ctrl_block.vhd  (v2 step B3)
-- UART control block: ctrl_uart (frame parser, bus master) + reg_file.
-- Replaces the v1 Nios II + RegistersControl. The codec I2C request port is
-- connected to the I2C master in the top level (step B4).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity ctrl_block is
  generic (
    CLK_HZ       : positive := 49_152_000;
    BAUD         : positive := 115_200;
    TIMEOUT_CLKS : positive := 491_520;
    VERSION      : std_logic_vector(15 downto 0) := x"0200"
  );
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;
    uart_rx    : in  std_logic;
    uart_tx    : out std_logic;
    -- codec I2C write requests
    i2c_req    : out std_logic;
    i2c_reg    : out std_logic_vector(6 downto 0);
    i2c_data   : out std_logic_vector(8 downto 0);
    i2c_busy   : in  std_logic;
    i2c_done   : in  std_logic;
    i2c_nak    : in  std_logic;
    -- status / levels shown in the registers
    status_in  : in  std_logic_vector(15 downto 0);
    level_in   : in  std_logic_vector(15 downto 0);
    level_out  : in  std_logic_vector(15 downto 0);
    -- effect registers
    effects_enable, od_drive, od_gain, trem_wave, trem_depth,
    echo_time, echo_repeat, echo_level, dist_mix, dist_type,
    chorus_level, chorus_depth, chorus_rate, reverb_mix, reverb_type
               : out std_logic_vector(15 downto 0);
    codec_init : out std_logic;
    mute       : out std_logic
  );
end entity;

architecture rtl of ctrl_block is
  signal bus_addr  : std_logic_vector(7 downto 0);
  signal bus_wdata : std_logic_vector(15 downto 0);
  signal bus_we    : std_logic;
  signal bus_rdata : std_logic_vector(15 downto 0);
  signal bus_err   : std_logic;
begin

  u_ctrl : entity work.ctrl_uart
    generic map (CLK_HZ => CLK_HZ, BAUD => BAUD, TIMEOUT_CLKS => TIMEOUT_CLKS, VERSION => VERSION)
    port map (
      clk => clk, rst => rst, uart_rx => uart_rx, uart_tx => uart_tx,
      bus_addr => bus_addr, bus_wdata => bus_wdata, bus_we => bus_we,
      bus_rdata => bus_rdata, bus_err => bus_err,
      i2c_req => i2c_req, i2c_reg => i2c_reg, i2c_data => i2c_data,
      i2c_busy => i2c_busy, i2c_done => i2c_done, i2c_nak => i2c_nak,
      crc_errors => open);

  u_regs : entity work.reg_file
    generic map (VERSION => VERSION)
    port map (
      clk => clk, rst => rst,
      addr => bus_addr, wdata => bus_wdata, we => bus_we, rdata => bus_rdata, err => bus_err,
      status_in => status_in, level_in => level_in, level_out => level_out,
      effects_enable => effects_enable, od_drive => od_drive, od_gain => od_gain,
      trem_wave => trem_wave, trem_depth => trem_depth, echo_time => echo_time,
      echo_repeat => echo_repeat, echo_level => echo_level, dist_mix => dist_mix,
      dist_type => dist_type, chorus_level => chorus_level, chorus_depth => chorus_depth,
      chorus_rate => chorus_rate, reverb_mix => reverb_mix, reverb_type => reverb_type,
      codec_init => codec_init, mute => mute);

end architecture;
