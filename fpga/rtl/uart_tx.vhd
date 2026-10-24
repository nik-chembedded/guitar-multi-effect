-- -----------------------------------------------------------------------------
-- uart_tx.vhd  (v2 step B3)
-- 8N1 UART transmitter. Bit timing from a fractional divider (exact average
-- baud rate). Pulse start with a byte on data when busy = '0'.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity uart_tx is
  generic (
    CLK_HZ : positive := 49_152_000;
    BAUD   : positive := 115_200
  );
  port (
    clk   : in  std_logic;
    rst   : in  std_logic;
    data  : in  std_logic_vector(7 downto 0);
    start : in  std_logic;
    busy  : out std_logic;
    tx    : out std_logic
  );
end entity;

architecture rtl of uart_tx is
  signal acc     : natural range 0 to CLK_HZ + BAUD := 0;
  signal shreg   : std_logic_vector(9 downto 0) := (others => '1');   -- stop & data & start
  signal bits    : natural range 0 to 10 := 0;
  signal tx_r    : std_logic := '1';
begin

  process(clk)
    variable bit_en : boolean;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        bits <= 0;
        tx_r <= '1';
        acc  <= 0;
      elsif bits = 0 then
        tx_r <= '1';
        if start = '1' then
          shreg <= '1' & data & '0';
          bits  <= 10;
          acc   <= 0;
        end if;
      else
        bit_en := acc + BAUD >= CLK_HZ;
        if bit_en then
          acc <= acc + BAUD - CLK_HZ;
        else
          acc <= acc + BAUD;
        end if;
        tx_r <= shreg(0);
        if bit_en then
          shreg <= '1' & shreg(9 downto 1);
          bits  <= bits - 1;
        end if;
      end if;
    end if;
  end process;

  tx   <= tx_r;
  busy <= '1' when bits /= 0 else '0';

end architecture;
