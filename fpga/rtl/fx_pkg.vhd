-- -----------------------------------------------------------------------------
-- fx_pkg.vhd
-- Shared fixed-point helpers for the effect datapath (16-bit signed samples).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package fx_pkg is

  constant SAMPLE_MAX : integer :=  32767;
  constant SAMPLE_MIN : integer := -32768;

  -- clamp an integer to the signed 16-bit sample range
  function sat16(x : integer) return integer;

  -- clamp an integer to the signed 16-bit range and return it as a sample vector
  function sat16_slv(x : integer) return std_logic_vector;

end package;

package body fx_pkg is

  function sat16(x : integer) return integer is
  begin
    if x > SAMPLE_MAX then
      return SAMPLE_MAX;
    elsif x < SAMPLE_MIN then
      return SAMPLE_MIN;
    else
      return x;
    end if;
  end function;

  function sat16_slv(x : integer) return std_logic_vector is
  begin
    return std_logic_vector(to_signed(sat16(x), 16));
  end function;

end package body;
