-- -----------------------------------------------------------------------------
-- fx_dpram.vhd  (v2 step C)
-- Delay-line RAM for the effects: simple dual-port altsyncram with generic
-- width and depth. Same settings as the former MegaWizard wrappers (echo_ram,
-- chorus_RAM, fcomb_RAM2/4): write port A, read port B with address and output
-- registers (q 2 clocks after rdaddress), OLD_DATA on read-during-write, clock
-- enable on all registers, contents start at 0.
-- Simulation: sim/models/fx_dpram.vhd (same entity, behavioural).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
library altera_mf;
use altera_mf.altera_mf_components.all;

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

architecture syn of fx_dpram is
begin

  altsyncram_component : altsyncram
    generic map (
      address_aclr_b                     => "NONE",
      address_reg_b                      => "CLOCK0",
      clock_enable_input_a               => "NORMAL",
      clock_enable_input_b               => "NORMAL",
      clock_enable_output_b              => "NORMAL",
      intended_device_family             => "Cyclone V",
      lpm_type                           => "altsyncram",
      numwords_a                         => 2 ** ADDR_W,
      numwords_b                         => 2 ** ADDR_W,
      operation_mode                     => "DUAL_PORT",
      outdata_aclr_b                     => "NONE",
      outdata_reg_b                      => "CLOCK0",
      power_up_uninitialized             => "FALSE",
      read_during_write_mode_mixed_ports => "OLD_DATA",
      widthad_a                          => ADDR_W,
      widthad_b                          => ADDR_W,
      width_a                            => WIDTH,
      width_b                            => WIDTH,
      width_byteena_a                    => 1
    )
    port map (
      address_a => wraddress,
      address_b => rdaddress,
      clock0    => clock,
      clocken0  => clocken,
      data_a    => data,
      wren_a    => wren,
      q_b       => q
    );

end architecture;
