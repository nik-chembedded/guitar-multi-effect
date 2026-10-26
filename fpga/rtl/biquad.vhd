-- -----------------------------------------------------------------------------
-- biquad.vhd  (v2 step D5b)
-- One Direct Form I biquad section with first-order error feedback (noise
-- shaping of the truncation error). Sub-block of eq3.vhd.
--
--   acc = ((b0*x + b1*x1 + b2*x2) << sh) - a1*y1 - a2*y2 + e
--   y   = sat(acc >> 16, DW)            floor shift
--   e   = acc mod 2^16                  the truncated bits, fed into the next sample
--
-- Coefficients are signed Q2.16 (18 bit), a0 = 1. The feed-forward sum is
-- multiplied by 2^sh (sh = 0..3) so that b coefficients up to +-16 can be stored as
-- b / 2^sh in the +-2 range of Q2.16 (a +12 dB shelf has b0 ~ 4).
--
-- Error feedback: the quantiser adds the previous remainder e before the floor, so
--   y[n] = S[n] + e[n-1] - e[n]   (S = exact sum)
-- i.e. the rounding error is shaped by (1 - z^-1): zero noise at DC, where a 100 Hz
-- shelf would otherwise amplify the truncation noise by its full boost and where
-- plain truncation causes DC offsets / limit cycles.
--
-- Accumulator: 48 bit signed (ACCW). Largest value: three products of 24 x 18 bit
-- (<= 2^40 each) shifted left by 3, plus two more products and e < 2^16, below 2^46.
--
-- Timing: go (one pulse, x valid) -> product register stage (5 multipliers,
-- 24 x 18, one DSP each) -> sum / saturate stage -> done pulse and y valid.
-- done comes 2 clocks after go. State (x1, x2, y1, y2, e) updates on each go.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fx_pkg.all;

entity biquad is
  generic (
    DW : positive := 24
  );
  port (
    clk  : in  std_logic;
    go   : in  std_logic;                        -- one pulse per sample, x valid
    x    : in  signed(DW - 1 downto 0);
    b0   : in  signed(17 downto 0);
    b1   : in  signed(17 downto 0);
    b2   : in  signed(17 downto 0);
    a1   : in  signed(17 downto 0);
    a2   : in  signed(17 downto 0);
    sh   : in  unsigned(1 downto 0);             -- feed-forward left shift
    y    : out signed(DW - 1 downto 0) := (others => '0');
    done : out std_logic := '0'                  -- y valid from this clock on
  );
end entity;

architecture rtl of biquad is
  constant ACCW : positive := 48;

  signal x1, x2, y1, y2 : signed(DW - 1 downto 0) := (others => '0');
  signal p0, p1, p2, p3, p4 : signed(ACCW - 1 downto 0) := (others => '0');
  signal sh_r : unsigned(1 downto 0) := (others => '0');
  signal e    : unsigned(15 downto 0) := (others => '0');
  signal v1   : std_logic := '0';
begin

  process(clk)
    variable acc : signed(ACCW - 1 downto 0);
    variable yy  : signed(DW - 1 downto 0);
  begin
    if rising_edge(clk) then
      -- stage 1: the five products
      v1 <= go;
      if go = '1' then
        p0 <= resize(x  * b0, ACCW);
        p1 <= resize(x1 * b1, ACCW);
        p2 <= resize(x2 * b2, ACCW);
        p3 <= resize(y1 * a1, ACCW);
        p4 <= resize(y2 * a2, ACCW);
        sh_r <= sh;
        x2 <= x1;
        x1 <= x;
      end if;
      -- stage 2: sum, error feedback, floor, saturate
      done <= v1;
      if v1 = '1' then
        acc := shift_left(p0 + p1 + p2, to_integer(sh_r)) - p3 - p4
               + signed(resize(e, ACCW));
        yy  := sat(shift_right(acc, 16), DW);
        e   <= unsigned(acc(15 downto 0));
        y2  <= y1;
        y1  <= yy;
        y   <= yy;
      end if;
    end if;
  end process;

end architecture;
