-- -----------------------------------------------------------------------------
-- sim_dpram.vhd
-- Behavioural model of an Intel altsyncram simple dual-port RAM as generated
-- for this project:
--   operation_mode DUAL_PORT, single clock0
--   port A: write (address, data, wren registered on clock0)
--   port B: read, address_reg_b = CLOCK0, outdata_reg_b = CLOCK0
--           -> q valid 2 clocks after rdaddress
--   read_during_write_mode_mixed_ports = OLD_DATA (also used for DONT_CARE)
--   power_up_uninitialized = FALSE -> contents start at 0
--   optional clocken0: enables all input and output registers (v2)
-- Used instead of altera_mf for simulators without Intel libraries (GHDL).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sim_dpram is
  generic (
    WIDTH  : positive;
    ADDR_W : positive
  );
  port (
    clock     : in  std_logic;
    data      : in  std_logic_vector(WIDTH - 1 downto 0);
    rdaddress : in  std_logic_vector(ADDR_W - 1 downto 0);
    wraddress : in  std_logic_vector(ADDR_W - 1 downto 0);
    wren      : in  std_logic := '0';
    clocken   : in  std_logic := '1';   -- clock_enable_input/output = NORMAL
    q         : out std_logic_vector(WIDTH - 1 downto 0)
  );
end entity;

architecture behav of sim_dpram is
  type mem_t is array (0 to 2 ** ADDR_W - 1) of std_logic_vector(WIDTH - 1 downto 0);
  signal q_reg : std_logic_vector(WIDTH - 1 downto 0) := (others => '0');
begin

  -- Matches altera_mf (verified in sim/models/tb_ip_equiv): the word is read
  -- on the edge that registers rdaddress, BEFORE that edge's write (OLD_DATA
  -- when rdaddress = wraddress), and appears on q after the next edge.
  process(clock)
    variable mem     : mem_t := (others => (others => '0'));
    variable rd_word : std_logic_vector(WIDTH - 1 downto 0) := (others => '0');
  begin
    if rising_edge(clock) and clocken = '1' then
      q_reg   <= rd_word;
      rd_word := mem(to_integer(unsigned(rdaddress)));
      if wren = '1' then
        mem(to_integer(unsigned(wraddress))) := data;
      end if;
    end if;
  end process;

  q <= q_reg;

end architecture;
