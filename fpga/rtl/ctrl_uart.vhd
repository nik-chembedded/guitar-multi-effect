-- -----------------------------------------------------------------------------
-- ctrl_uart.vhd  (v2 step B3)
-- Host control over UART: frame parser + bus master + reply generator.
--
-- Request (host -> FPGA):  A5 | cmd | addr | data_hi | data_lo | crc8(cmd..data_lo)
-- Reply   (FPGA -> host):  5A | status | data_hi | data_lo | crc8(status..data_lo)
--   cmd 01 WRITE  register addr <- data                      reply data = 0
--   cmd 02 READ   register addr                              reply data = register
--   cmd 03 CODEC  I2C write: codec register addr(6:0), 9-bit data(8:0)
--                 (reply when the I2C transfer has finished)
--   cmd 04 PING                                              reply data = VERSION
--   status 00 OK, 01 CRC error, 02 bad command/address, 03 I2C NAK, 04 I2C busy
-- CRC-8: polynomial 0x07, init 0x00, no reflection (CRC-8/SMBUS).
-- The parser hunts for A5; a partial frame is dropped after TIMEOUT_CLKS
-- without a byte, so a lost byte costs at most one frame.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity ctrl_uart is
  generic (
    CLK_HZ       : positive := 49_152_000;
    BAUD         : positive := 115_200;
    TIMEOUT_CLKS : positive := 491_520;        -- 10 ms at 49.152 MHz
    VERSION      : std_logic_vector(15 downto 0) := x"0200"
  );
  port (
    clk       : in  std_logic;
    rst       : in  std_logic;
    uart_rx   : in  std_logic;
    uart_tx   : out std_logic;
    -- register bus (to reg_file)
    bus_addr  : out std_logic_vector(7 downto 0);
    bus_wdata : out std_logic_vector(15 downto 0);
    bus_we    : out std_logic;
    bus_rdata : in  std_logic_vector(15 downto 0);
    bus_err   : in  std_logic;
    -- codec I2C write requests (to the I2C master)
    i2c_req   : out std_logic;                          -- 1-cycle pulse
    i2c_reg   : out std_logic_vector(6 downto 0);
    i2c_data  : out std_logic_vector(8 downto 0);
    i2c_busy  : in  std_logic;
    i2c_done  : in  std_logic;                          -- 1-cycle pulse
    i2c_nak   : in  std_logic;                          -- valid with i2c_done
    -- statistics
    crc_errors : out std_logic_vector(7 downto 0)
  );
end entity;

architecture rtl of ctrl_uart is

  function crc8_byte(crc : std_logic_vector(7 downto 0); b : std_logic_vector(7 downto 0))
    return std_logic_vector is
    variable c : std_logic_vector(7 downto 0) := crc xor b;
  begin
    for i in 0 to 7 loop
      if c(7) = '1' then
        c := (c(6 downto 0) & '0') xor x"07";
      else
        c := c(6 downto 0) & '0';
      end if;
    end loop;
    return c;
  end function;

  signal rx_data  : std_logic_vector(7 downto 0);
  signal rx_valid : std_logic;
  signal tx_data  : std_logic_vector(7 downto 0) := (others => '0');
  signal tx_start : std_logic := '0';
  signal tx_busy  : std_logic;

  type state_t is (HUNT, RECV, EXEC, WAIT_I2C, SEND);
  signal state    : state_t := HUNT;
  type bytes_t is array (0 to 4) of std_logic_vector(7 downto 0);
  signal req      : bytes_t := (others => (others => '0'));   -- cmd addr dh dl crc
  signal nrx      : natural range 0 to 5 := 0;
  signal crc      : std_logic_vector(7 downto 0) := (others => '0');
  signal tmo      : natural range 0 to TIMEOUT_CLKS := 0;
  signal rep      : bytes_t := (others => (others => '0'));   -- 5A st dh dl crc
  signal ntx      : natural range 0 to 5 := 0;
  signal crc_cnt  : unsigned(7 downto 0) := (others => '0');

begin

  u_rx : entity work.uart_rx
    generic map (CLK_HZ => CLK_HZ, BAUD => BAUD)
    port map (clk => clk, rst => rst, rx => uart_rx, data => rx_data, valid => rx_valid, frame_err => open);

  u_tx : entity work.uart_tx
    generic map (CLK_HZ => CLK_HZ, BAUD => BAUD)
    port map (clk => clk, rst => rst, data => tx_data, start => tx_start, busy => tx_busy, tx => uart_tx);

  bus_addr  <= req(1);
  bus_wdata <= req(2) & req(3);
  i2c_reg   <= req(1)(6 downto 0);
  i2c_data  <= req(2)(0) & req(3);
  crc_errors <= std_logic_vector(crc_cnt);

  process(clk)
    procedure reply(st : std_logic_vector(7 downto 0); d : std_logic_vector(15 downto 0)) is
      variable c : std_logic_vector(7 downto 0);
    begin
      c := crc8_byte(x"00", st);
      c := crc8_byte(c, d(15 downto 8));
      c := crc8_byte(c, d(7 downto 0));
      rep   <= (x"5A", st, d(15 downto 8), d(7 downto 0), c);
      ntx   <= 0;
      state <= SEND;
    end procedure;
  begin
    if rising_edge(clk) then
      bus_we   <= '0';
      i2c_req  <= '0';
      tx_start <= '0';
      if rst = '1' then
        state   <= HUNT;
        crc_cnt <= (others => '0');
      else
        case state is
          when HUNT =>
            if rx_valid = '1' and rx_data = x"A5" then
              state <= RECV;
              nrx   <= 0;
              crc   <= x"00";
              tmo   <= 0;
            end if;

          when RECV =>
            if rx_valid = '1' then
              req(nrx) <= rx_data;
              tmo      <= 0;
              if nrx < 4 then
                crc <= crc8_byte(crc, rx_data);
                nrx <= nrx + 1;
              else
                state <= EXEC;                   -- rx_data is the CRC byte
              end if;
            elsif tmo = TIMEOUT_CLKS then
              state <= HUNT;                     -- partial frame: drop it
            else
              tmo <= tmo + 1;
            end if;

          when EXEC =>
            if req(4) /= crc then
              crc_cnt <= crc_cnt + 1;
              reply(x"01", x"0000");
            else
              case req(0) is
                when x"01" =>                    -- WRITE
                  if bus_err = '1' then
                    reply(x"02", x"0000");
                  else
                    bus_we <= '1';
                    reply(x"00", x"0000");
                  end if;
                when x"02" =>                    -- READ
                  if bus_err = '1' then
                    reply(x"02", x"0000");
                  else
                    reply(x"00", bus_rdata);
                  end if;
                when x"03" =>                    -- CODEC
                  if i2c_busy = '1' then
                    reply(x"04", x"0000");
                  else
                    i2c_req <= '1';
                    state   <= WAIT_I2C;
                  end if;
                when x"04" =>                    -- PING
                  reply(x"00", VERSION);
                when others =>
                  reply(x"02", x"0000");
              end case;
            end if;

          when WAIT_I2C =>
            if i2c_done = '1' then
              if i2c_nak = '1' then
                reply(x"03", x"0000");
              else
                reply(x"00", x"0000");
              end if;
            end if;

          when SEND =>
            if tx_busy = '0' and tx_start = '0' then
              if ntx = 5 then
                state <= HUNT;
              else
                tx_data  <= rep(ntx);
                tx_start <= '1';
                ntx      <= ntx + 1;
              end if;
            end if;
        end case;
      end if;
    end if;
  end process;

end architecture;
