-- -----------------------------------------------------------------------------
-- uart_rx.vhd  (v2 step B3)
-- 8N1 UART receiver, 16x oversampling. The oversampling enable comes from a
-- fractional (phase accumulator) divider, so any baud rate is exact on average
-- (115200 at 49.152 MHz: error < 0.01 %).
-- rx is synchronised (2 FF); the start bit is validated at its middle; data
-- bits are sampled in the middle of each bit; a low stop bit sets frame_err.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity uart_rx is
  generic (
    CLK_HZ : positive := 49_152_000;
    BAUD   : positive := 115_200
  );
  port (
    clk       : in  std_logic;
    rst       : in  std_logic;
    rx        : in  std_logic;
    data      : out std_logic_vector(7 downto 0);
    valid     : out std_logic;                     -- 1-cycle pulse, byte in data
    frame_err : out std_logic                      -- 1-cycle pulse, stop bit was 0
  );
end entity;

architecture rtl of uart_rx is
  constant INC : natural := BAUD * 16;
  signal acc     : natural range 0 to CLK_HZ + INC := 0;
  signal os_en   : std_logic := '0';               -- 16 x baud enable
  signal sync    : std_logic_vector(2 downto 0) := (others => '1');
  type state_t is (IDLE, START, DATA_BITS, STOP);
  signal state   : state_t := IDLE;
  signal os_cnt  : natural range 0 to 15 := 0;
  signal bit_cnt : natural range 0 to 7 := 0;
  signal shreg   : std_logic_vector(7 downto 0) := (others => '0');
begin

  baud_gen : process(clk)
  begin
    if rising_edge(clk) then
      if acc + INC >= CLK_HZ then
        acc   <= acc + INC - CLK_HZ;
        os_en <= '1';
      else
        acc   <= acc + INC;
        os_en <= '0';
      end if;
    end if;
  end process;

  process(clk)
    variable r : std_logic;
  begin
    if rising_edge(clk) then
      sync      <= sync(1 downto 0) & rx;
      r         := sync(2);
      valid     <= '0';
      frame_err <= '0';
      if rst = '1' then
        state <= IDLE;
      elsif os_en = '1' then
        case state is
          when IDLE =>
            if r = '0' then                        -- possible start bit
              state  <= START;
              os_cnt <= 0;
            end if;
          when START =>
            if os_cnt = 7 then                     -- middle of the start bit
              if r = '0' then
                state   <= DATA_BITS;
                os_cnt  <= 0;
                bit_cnt <= 0;
              else
                state <= IDLE;                     -- glitch, not a start bit
              end if;
            else
              os_cnt <= os_cnt + 1;
            end if;
          when DATA_BITS =>
            if os_cnt = 15 then                    -- middle of the data bit
              os_cnt <= 0;
              shreg  <= r & shreg(7 downto 1);     -- LSB first
              if bit_cnt = 7 then
                state <= STOP;
              else
                bit_cnt <= bit_cnt + 1;
              end if;
            else
              os_cnt <= os_cnt + 1;
            end if;
          when STOP =>
            if os_cnt = 15 then
              state <= IDLE;
              if r = '1' then
                valid <= '1';
              else
                frame_err <= '1';
              end if;
            else
              os_cnt <= os_cnt + 1;
            end if;
        end case;
      end if;
    end if;
  end process;

  data <= shreg;

end architecture;
