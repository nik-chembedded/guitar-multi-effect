-- -----------------------------------------------------------------------------
-- fx_pkg.vhd
-- Fixed-point helpers for the effect datapath (v2 step C).
--
-- Samples are signed, DW bits wide (16 or 24). The functions work on signed /
-- unsigned vectors of any width (VHDL integer is only 32-bit, too small for
-- 24 x 16-bit products). Rounding is floor (arithmetic shift), as in v1, so
-- the DW = 16 chain stays bit-exact to the v1 design.
--
--   sat(x, w)            clamp x to w bits
--   add_sat(a, b, w)     a + b clamped to w bits
--   mul_shr(x, k, s)     floor(x * k / 2^s), x signed, k unsigned
--   smul_shr(x, k, s)    floor(x * k / 2^s), x and k signed
--   div_pow2(x, s)       x / 2^s truncated toward zero (VHDL integer "/")
--   mix8(dry, wet, m)    floor((m * wet + (255 - m) * dry) / 256), m = 0..255
--
-- Results of mul_shr / smul_shr have the full product width; resize or sat
-- them to the sample width.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package fx_pkg is

  constant SAMPLE_MAX : integer :=  32767;
  constant SAMPLE_MIN : integer := -32768;

  -- clamp an integer to the signed 16-bit sample range (v1 helpers)
  function sat16(x : integer) return integer;
  function sat16_slv(x : integer) return std_logic_vector;

  function sat(x : signed; w : positive) return signed;
  function add_sat(a, b : signed; w : positive) return signed;
  function mul_shr(x : signed; k : unsigned; s : natural) return signed;
  function smul_shr(x : signed; k : signed; s : natural) return signed;
  function div_pow2(x : signed; s : natural) return signed;
  function mix8(dry, wet : signed; m : unsigned(7 downto 0)) return signed;

end package;

package body fx_pkg is

  function imax(a, b : integer) return integer is      -- (VHDL-93: no maximum)
  begin
    if a > b then return a; else return b; end if;
  end function;

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

  function sat(x : signed; w : positive) return signed is
    variable MAXV : signed(w - 1 downto 0) := (others => '1');
    variable MINV : signed(w - 1 downto 0) := (others => '0');
  begin
    MAXV(w - 1) := '0';
    MINV(w - 1) := '1';
    if x'length <= w then
      return resize(x, w);
    elsif x > resize(MAXV, x'length) then
      return MAXV;
    elsif x < resize(MINV, x'length) then
      return MINV;
    else
      return resize(x, w);
    end if;
  end function;

  function add_sat(a, b : signed; w : positive) return signed is
    constant L : positive := imax(a'length, b'length) + 1;
  begin
    return sat(resize(a, L) + resize(b, L), w);
  end function;

  function mul_shr(x : signed; k : unsigned; s : natural) return signed is
    variable p : signed(x'length + k'length downto 0);
  begin
    p := x * signed('0' & k);
    return shift_right(p, s);
  end function;

  function smul_shr(x : signed; k : signed; s : natural) return signed is
    variable p : signed(x'length + k'length - 1 downto 0);
  begin
    p := x * k;
    return shift_right(p, s);
  end function;

  function div_pow2(x : signed; s : natural) return signed is
    variable e : signed(x'length downto 0) := resize(x, x'length + 1);
  begin
    if x < 0 then
      return resize(-shift_right(-e, s), x'length);
    else
      return resize(shift_right(e, s), x'length);
    end if;
  end function;

  function mix8(dry, wet : signed; m : unsigned(7 downto 0)) return signed is
    constant L  : positive := imax(dry'length, wet'length);
    variable mw : signed(L + 9 downto 0);
    variable md : signed(L + 9 downto 0);
  begin
    mw := resize(resize(wet, L) * signed('0' & m), L + 10);
    md := resize(resize(dry, L) * signed('0' & (255 - m)), L + 10);
    return resize(shift_right(mw + md, 8), L);
  end function;

end package body;
