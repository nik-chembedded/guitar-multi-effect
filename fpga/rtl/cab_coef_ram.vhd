-- -----------------------------------------------------------------------------
-- cab_coef_ram.vhd  (v2 step D3)
-- Coefficient RAM of the cabinet FIR (cab_fir): simple dual-port altsyncram with
-- MIXED port widths and power-up contents from a .mif.
--   write port A : WIDTH bits x 2**ADDR_W words (HPS / test writes, 1 coefficient)
--   read  port B : WIDTH * 2**LANES_LOG2 bits x 2**(ADDR_W - LANES_LOG2) words:
--                  one read returns 2**LANES_LOG2 consecutive coefficients;
--                  coefficient (A address) a = (B address) * LANES + i is bits
--                  [WIDTH*(i+1)-1 : WIDTH*i] of word (B address)  (lowest address
--                  of the narrow port in the least significant bits)
-- Register conventions as fx_dpram: read address and output registered, q valid
-- 2 clocks after rdaddress; contents start at INIT_FILE (an Intel .mif with
-- WIDTH-bit words for port A; words not listed in the file are 0).
-- Read-during-write is DONT_CARE (the cab_fir never reads the bank it is
-- loading); the simulation twin returns the old data.
-- Simulation: sim/models/cab_coef_ram.vhd (same entity, behavioural).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
library altera_mf;
use altera_mf.altera_mf_components.all;

entity cab_coef_ram is
  generic (
    WIDTH      : positive := 18;
    LANES_LOG2 : positive := 2;
    ADDR_W     : positive;                      -- port A address bits
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

architecture syn of cab_coef_ram is
begin

  altsyncram_component : altsyncram
    generic map (
      address_aclr_b                     => "NONE",
      address_reg_b                      => "CLOCK0",
      clock_enable_input_a               => "BYPASS",
      clock_enable_input_b               => "BYPASS",
      clock_enable_output_b              => "BYPASS",
      init_file                          => INIT_FILE,
      init_file_layout                   => "PORT_A",
      intended_device_family             => "Cyclone V",
      lpm_type                           => "altsyncram",
      numwords_a                         => 2 ** ADDR_W,
      numwords_b                         => 2 ** (ADDR_W - LANES_LOG2),
      operation_mode                     => "DUAL_PORT",
      outdata_aclr_b                     => "NONE",
      outdata_reg_b                      => "CLOCK0",
      power_up_uninitialized             => "FALSE",
      read_during_write_mode_mixed_ports => "DONT_CARE",
      widthad_a                          => ADDR_W,
      widthad_b                          => ADDR_W - LANES_LOG2,
      width_a                            => WIDTH,
      width_b                            => WIDTH * 2 ** LANES_LOG2,
      width_byteena_a                    => 1
    )
    port map (
      address_a => wraddress,
      address_b => rdaddress,
      clock0    => clock,
      data_a    => data,
      wren_a    => wren,
      q_b       => q
    );

end architecture;
