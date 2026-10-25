-- -----------------------------------------------------------------------------
-- fx_dpram.vhd (simulation) - same entity as fpga/rtl/fx_dpram.vhd, built on
-- the behavioural sim_dpram (verified against altera_mf, see README.md).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity fx_dpram is
  generic (
    WIDTH  : positive;
    ADDR_W : positive
  );
  port (
    clock     : in  std_logic;
    clocken   : in  std_logic := '1';
    data      : in  std_logic_vector(WIDTH - 1 downto 0);
    rdaddress : in  std_logic_vector(ADDR_W - 1 downto 0);
    wraddress : in  std_logic_vector(ADDR_W - 1 downto 0);
    wren      : in  std_logic := '0';
    q         : out std_logic_vector(WIDTH - 1 downto 0)
  );
end entity;

architecture sim of fx_dpram is
begin
  m : entity work.sim_dpram
    generic map (WIDTH => WIDTH, ADDR_W => ADDR_W)
    port map (clock => clock, data => data, rdaddress => rdaddress, wraddress => wraddress,
              wren => wren, clocken => clocken, q => q);
end architecture;
