-- fxlib_wrap.vhd - exposes the fx_pkg functions as ports for test_fxlib.py.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fx_pkg.all;

entity fxlib_wrap is
  port (
    a24, b24 : in  signed(23 downto 0);
    a16, b16 : in  signed(15 downto 0);
    k        : in  unsigned(15 downto 0);
    ks       : in  signed(17 downto 0);
    m        : in  unsigned(7 downto 0);
    sat16_o    : out signed(15 downto 0);    -- sat(a24, 16)
    addsat24_o : out signed(23 downto 0);    -- add_sat(a24, b24, 24)
    addsat16_o : out signed(15 downto 0);    -- add_sat(a16, b16, 16)
    mulshr_o   : out signed(23 downto 0);    -- mul_shr(a24, k, 16)
    smulshr_o  : out signed(24 downto 0);    -- smul_shr(a24, ks, 16)
    div64_o    : out signed(23 downto 0);    -- div_pow2(a24, 6)
    mix24_o    : out signed(23 downto 0);    -- mix8(a24, b24, m)
    mix16_o    : out signed(15 downto 0)     -- mix8(a16, b16, m)
  );
end entity;

architecture rtl of fxlib_wrap is
begin
  sat16_o    <= sat(a24, 16);
  addsat24_o <= add_sat(a24, b24, 24);
  addsat16_o <= add_sat(a16, b16, 16);
  mulshr_o   <= resize(mul_shr(a24, k, 16), 24);
  smulshr_o  <= resize(smul_shr(a24, ks, 16), 25);
  div64_o    <= div_pow2(a24, 6);
  mix24_o    <= mix8(b24, a24, m);
  mix16_o    <= mix8(b16, a16, m);
end architecture;
