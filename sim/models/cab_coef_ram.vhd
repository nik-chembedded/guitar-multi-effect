-- -----------------------------------------------------------------------------
-- cab_coef_ram.vhd (simulation) - same entity as fpga/rtl/cab_coef_ram.vhd.
-- Behavioural model of the mixed-width altsyncram: write port A (WIDTH bits,
-- 2**ADDR_W words), read port B (2**LANES_LOG2 consecutive coefficients per
-- word, lowest address in the least significant bits), address and output
-- registered (q 2 clocks after rdaddress, word read BEFORE the same edge's write).
-- Contents are loaded from INIT_FILE (.mif, "address : value;" lines as in
-- sim_rom; values may be unsigned or negative decimal); words not listed or
-- addresses >= 2**ADDR_W are 0 / ignored.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity cab_coef_ram is
  generic (
    WIDTH      : positive := 18;
    LANES_LOG2 : positive := 2;
    ADDR_W     : positive;
    INIT_FILE  : string := "cab_default.mif"
  );
  port (
    clock     : in  std_logic;
    wren      : in  std_logic := '0';
    wraddress : in  std_logic_vector(ADDR_W - 1 downto 0);
    data      : in  std_logic_vector(WIDTH - 1 downto 0);
    rdaddress : in  std_logic_vector(ADDR_W - LANES_LOG2 - 1 downto 0);
    q         : out std_logic_vector(WIDTH * 2 ** LANES_LOG2 - 1 downto 0)
  );
end entity;

architecture behav of cab_coef_ram is

  constant L : positive := 2 ** LANES_LOG2;
  type mem_t is array (0 to 2 ** ADDR_W - 1) of std_logic_vector(WIDTH - 1 downto 0);

  impure function load_mif(name : string) return mem_t is
    file     f       : text;
    variable status  : file_open_status;
    variable ln      : line;
    variable mem     : mem_t := (others => (others => '0'));
    variable a, v    : integer;
    variable c       : character;
    variable ok      : boolean;
    variable in_data : boolean := false;
  begin
    file_open(status, f, name, read_mode);
    assert status = open_ok
      report "cab_coef_ram: cannot open init file " & name severity failure;
    while not endfile(f) loop
      readline(f, ln);
      if not in_data then
        for i in ln'range loop
          if i + 4 <= ln'high and ln(i to i + 4) = "BEGIN" then
            in_data := true;
          end if;
        end loop;
      else
        read(ln, a, ok);                             -- address (or "END;")
        if ok then
          loop                                       -- skip to ':'
            read(ln, c, ok);
            exit when not ok or c = ':';
          end loop;
          read(ln, v, ok);                           -- value
          if ok and a < 2 ** ADDR_W then
            if v < 0 then
              mem(a) := std_logic_vector(to_signed(v, WIDTH));
            else
              mem(a) := std_logic_vector(to_unsigned(v, WIDTH));
            end if;
          end if;
        end if;
      end if;
    end loop;
    file_close(f);
    return mem;
  end function;

  signal q_reg : std_logic_vector(WIDTH * L - 1 downto 0) := (others => '0');

begin

  process(clock)
    variable mem     : mem_t := load_mif(INIT_FILE);
    variable rd_word : std_logic_vector(WIDTH * L - 1 downto 0) := (others => '0');
    variable base    : natural;
  begin
    if rising_edge(clock) then
      q_reg <= rd_word;
      base := to_integer(unsigned(rdaddress)) * L;
      for i in 0 to L - 1 loop
        rd_word(WIDTH * (i + 1) - 1 downto WIDTH * i) := mem(base + i);
      end loop;
      if wren = '1' then
        mem(to_integer(unsigned(wraddress))) := data;
      end if;
    end if;
  end process;

  q <= q_reg;

end architecture;
