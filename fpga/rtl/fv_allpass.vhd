-- -----------------------------------------------------------------------------
-- fv_allpass.vhd  (v2 step D4)
-- Freeverb all-pass, g = 0.5 (shift), one delay line (1024 words):
--   b = line[n - LEN];  out = sat(b - in);  line[n] = sat(in + trunc(b / 2)), trunc toward zero (see fv_comb)
-- Loop delay exactly LEN samples. Evaluated at the stage pulse `st` (the line
-- output is valid 3 clocks after the sample strobe); out and the next write
-- value are registered, written to the RAM at the next strobe.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fx_pkg.all;

entity fv_allpass is
  generic (
    DW  : positive := 16;
    LEN : positive := 605                       -- delay in samples (< 1024)
  );
  port (
    clk   : in  std_logic;
    wr_en : in  std_logic;
    st    : in  std_logic;                      -- stage pulse
    wp    : in  unsigned(10 downto 0);          -- shared write pointer (low 10 bits used)
    d_in  : in  signed(DW - 1 downto 0);
    d_out : out signed(DW - 1 downto 0)
  );
end entity;

architecture rtl of fv_allpass is
  signal rd_addr : unsigned(9 downto 0);
  signal q       : std_logic_vector(DW - 1 downto 0);
  signal wr_data : signed(DW - 1 downto 0) := (others => '0');
  signal o_r     : signed(DW - 1 downto 0) := (others => '0');
begin

  rd_addr <= wp(9 downto 0) - to_unsigned(LEN, 10);
  d_out   <= o_r;

  u_line : entity work.fx_dpram
    generic map (WIDTH => DW, ADDR_W => 10)
    port map (clock => clk, clocken => '1', data => std_logic_vector(wr_data),
              rdaddress => std_logic_vector(rd_addr), wraddress => std_logic_vector(wp(9 downto 0)),
              wren => wr_en, q => q);

  process(clk)
    variable b : signed(DW - 1 downto 0);
  begin
    if rising_edge(clk) then
      if st = '1' then
        b := signed(q);
        o_r     <= sat(resize(b, DW + 2) - resize(d_in, DW + 2), DW);
        wr_data <= add_sat(d_in, div_pow2(b, 1), DW);
      end if;
    end if;
  end process;

end architecture;
