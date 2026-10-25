-- -----------------------------------------------------------------------------
-- ctrl_avmm.vhd  (v2, HPS control)
-- Avalon-MM slave for the HPS lightweight bridge + reg_file. Replaces the UART
-- control block (ctrl_uart / uart_rx / uart_tx, see tag v2-uart).
--
-- Register n is at byte offset 4*n (Linux: 0xFF200000 + 4*n). Bits 31..16 read 0
-- and are ignored on write. Registers 0x00..0x14 are those of reg_file
-- (docs/register_map.md); one more is handled here:
--
--   0x15  CODEC  write: bits 15..9 = WM8731 register, bits 8..0 = data
--                       (one I2C write; ignored and bit2 set while busy)
--                read:  bit0 busy, bit1 last write NAKed, bit2 write dropped
--
-- Byte enables are honoured: a write changes only the enabled bytes of a
-- register, so byte or halfword stores (e.g. Python's struct on /dev/mem
-- writes byte by byte) give the same result as one 32-bit store. The CODEC
-- bytes are collected and the I2C transfer starts on the write that contains
-- byte 1 (bits 15..8); writes to bytes 2..3 only are ignored.
--
-- Reads: readdatavalid one cycle after read, no wait states. Unknown addresses
-- read 0, writes to them are ignored.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ctrl_avmm is
  generic (
    VERSION : std_logic_vector(15 downto 0) := x"0204"
  );
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;
    -- Avalon-MM slave (byte address)
    avs_address       : in  std_logic_vector(7 downto 0);
    avs_read          : in  std_logic;
    avs_write         : in  std_logic;
    avs_writedata     : in  std_logic_vector(31 downto 0);
    avs_byteenable    : in  std_logic_vector(3 downto 0);
    avs_readdata      : out std_logic_vector(31 downto 0);
    avs_readdatavalid : out std_logic;
    avs_waitrequest   : out std_logic;
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
    ext        : out std_logic_vector(26 * 16 - 1 downto 0);   -- registers 0x16 .. 0x2F
    codec_init : out std_logic;
    mute       : out std_logic
  );
end entity;

architecture rtl of ctrl_avmm is
  constant CODEC_ADDR : std_logic_vector(7 downto 0) := x"15";

  signal word      : std_logic_vector(7 downto 0);
  signal reg_we    : std_logic;
  signal reg_wdata : std_logic_vector(15 downto 0);
  signal stage     : std_logic_vector(15 downto 0) := (others => '0');
  signal codec_w   : std_logic_vector(15 downto 0);
  signal reg_rdata : std_logic_vector(15 downto 0);
  signal reg_err   : std_logic;

  signal req_r     : std_logic := '0';
  signal reg_r     : std_logic_vector(6 downto 0) := (others => '0');
  signal data_r    : std_logic_vector(8 downto 0) := (others => '0');
  signal last_nak  : std_logic := '0';
  signal dropped   : std_logic := '0';
  signal codec_st  : std_logic_vector(15 downto 0);
  signal rdata_r   : std_logic_vector(31 downto 0) := (others => '0');
  signal rvalid_r  : std_logic := '0';
begin

  word   <= "00" & avs_address(7 downto 2);
  -- byte enables: keep the bytes that are not written (read-modify-write;
  -- reg_file's read mux is combinational on the same address)
  reg_wdata(15 downto 8) <= avs_writedata(15 downto 8) when avs_byteenable(1) = '1' else reg_rdata(15 downto 8);
  reg_wdata(7 downto 0)  <= avs_writedata(7 downto 0)  when avs_byteenable(0) = '1' else reg_rdata(7 downto 0);
  reg_we <= avs_write and (avs_byteenable(1) or avs_byteenable(0)) when word /= CODEC_ADDR else '0';

  codec_w(15 downto 8) <= avs_writedata(15 downto 8) when avs_byteenable(1) = '1' else stage(15 downto 8);
  codec_w(7 downto 0)  <= avs_writedata(7 downto 0)  when avs_byteenable(0) = '1' else stage(7 downto 0);

  u_regs : entity work.reg_file
    generic map (VERSION => VERSION)
    port map (
      clk => clk, rst => rst,
      addr => word, wdata => reg_wdata, we => reg_we,
      rdata => reg_rdata, err => reg_err,
      status_in => status_in, level_in => level_in, level_out => level_out,
      effects_enable => effects_enable, od_drive => od_drive, od_gain => od_gain,
      trem_wave => trem_wave, trem_depth => trem_depth, echo_time => echo_time,
      echo_repeat => echo_repeat, echo_level => echo_level, dist_mix => dist_mix,
      dist_type => dist_type, chorus_level => chorus_level, chorus_depth => chorus_depth,
      chorus_rate => chorus_rate, reverb_mix => reverb_mix, reverb_type => reverb_type,
      ext => ext, codec_init => codec_init, mute => mute);

  -- CODEC register: one host I2C write at a time
  process(clk)
  begin
    if rising_edge(clk) then
      req_r <= '0';
      if rst = '1' then
        last_nak <= '0';
        dropped  <= '0';
      else
        if avs_write = '1' and word = CODEC_ADDR then
          stage <= codec_w;
          if avs_byteenable(1) = '1' then              -- the value is complete
            if i2c_busy = '0' and req_r = '0' then
              req_r   <= '1';
              reg_r   <= codec_w(15 downto 9);
              data_r  <= codec_w(8 downto 0);
              dropped <= '0';
            else
              dropped <= '1';
            end if;
          end if;
        end if;
        if i2c_done = '1' then
          last_nak <= i2c_nak;
        end if;
      end if;
    end if;
  end process;

  i2c_req  <= req_r;
  i2c_reg  <= reg_r;
  i2c_data <= data_r;
  codec_st <= (0 => i2c_busy or req_r, 1 => last_nak, 2 => dropped, others => '0');

  -- read data: registered, valid one cycle after the read
  process(clk)
  begin
    if rising_edge(clk) then
      rvalid_r <= avs_read and not rst;
      if avs_read = '1' then
        if word = CODEC_ADDR then
          rdata_r <= x"0000" & codec_st;
        elsif reg_err = '1' then
          rdata_r <= (others => '0');
        else
          rdata_r <= x"0000" & reg_rdata;
        end if;
      end if;
    end if;
  end process;

  avs_readdata      <= rdata_r;
  avs_readdatavalid <= rvalid_r;
  avs_waitrequest   <= '0';

end architecture;
