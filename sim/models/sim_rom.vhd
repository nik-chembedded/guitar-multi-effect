-- -----------------------------------------------------------------------------
-- sim_rom.vhd
-- Behavioural model of an Intel altsyncram ROM as generated for this project:
--   operation_mode ROM, address registered on clock0, outdata_reg_a = CLOCK0
--   -> q is valid 2 clocks after the address (registered address + registered
--      output); rden_a is a clock enable of the address register.
-- Contents are loaded from an Intel .mif file (lines "address : value;",
-- ADDRESS_RADIX=UNS, DATA_RADIX=DEC/UNS). Words not listed in the file, or
-- addresses >= DEPTH, read as 0 (like Quartus for a short .mif).
-- Used instead of altera_mf for simulators without Intel libraries (GHDL).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity sim_rom is
  generic (
    WIDTH     : positive;
    ADDR_W    : positive;
    DEPTH     : positive;
    INIT_FILE : string
  );
  port (
    clock   : in  std_logic;
    address : in  std_logic_vector(ADDR_W - 1 downto 0);
    rden    : in  std_logic := '1';
    q       : out std_logic_vector(WIDTH - 1 downto 0)
  );
end entity;

architecture behav of sim_rom is

  type mem_t is array (0 to 2 ** ADDR_W - 1) of std_logic_vector(WIDTH - 1 downto 0);

  impure function load_mif(name : string) return mem_t is
    file     f       : text;
    variable status  : file_open_status;
    variable l       : line;
    variable mem     : mem_t := (others => (others => '0'));
    variable a, v    : integer;
    variable c       : character;
    variable ok      : boolean;
    variable in_data : boolean := false;
  begin
    file_open(status, f, name, read_mode);
    assert status = open_ok
      report "sim_rom: cannot open init file " & name severity failure;
    while not endfile(f) loop
      readline(f, l);
      if not in_data then
        -- skip the header up to "CONTENT BEGIN"
        for i in l'range loop
          if i + 4 <= l'high and l(i to i + 4) = "BEGIN" then
            in_data := true;
          end if;
        end loop;
      else
        read(l, a, ok);                              -- address (or "END;")
        if ok then
          loop                                       -- skip to ':'
            read(l, c, ok);
            exit when not ok or c = ':';
          end loop;
          read(l, v, ok);                            -- value
          if ok and a < DEPTH and a < 2 ** ADDR_W then
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

  signal mem      : mem_t := load_mif(INIT_FILE);
  signal q_reg    : std_logic_vector(WIDTH - 1 downto 0) := (others => '0');

begin

  -- Matches altera_mf (verified in sim/models/tb_ip_equiv):
  --  * rden_a is a clock enable of the ADDRESS register: with rden = '0' the
  --    old address is kept and the output register keeps reloading its word
  --  * the output register always loads the word at the registered address
  --  * before the first address has been latched the output is 0
  process(clock)
    variable addr_reg : natural := 0;
    variable valid    : boolean := false;
  begin
    if rising_edge(clock) then
      if valid and addr_reg < DEPTH then
        q_reg <= mem(addr_reg);
      else
        q_reg <= (others => '0');
      end if;
      if rden = '1' then
        addr_reg := to_integer(unsigned(address));
        valid    := true;
      end if;
    end if;
  end process;

  q <= q_reg;

end architecture;
