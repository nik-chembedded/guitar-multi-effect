-- -----------------------------------------------------------------------------
-- param_smooth.vhd  (v2 step C)
-- One-pole smoothing of a user parameter, so register changes glide instead of
-- jumping (no zipper noise). Once per sample (tick):
--   y += (target - y) / 2^K        (FRAC extra fraction bits)
-- with a final +-1 step when (target - y) / 2^K rounds to 0, so y reaches the
-- target exactly. Output = y / 2^FRAC. Starts at INIT (default 0) after reset.
-- K = 7: time constant 128 samples (2.7 ms); a full-scale 16-bit step settles
-- exactly in about 1650 samples (34 ms).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity param_smooth is
  generic (
    WIDTH : positive := 16;
    K     : natural  := 7;
    FRAC  : natural  := 8;
    INIT  : natural  := 0                  -- value after reset (D6: offset-binary level starts at 0 dB)
  );
  port (
    clk    : in  std_logic;
    rst    : in  std_logic;
    tick   : in  std_logic;
    target : in  std_logic_vector(WIDTH - 1 downto 0);
    value  : out std_logic_vector(WIDTH - 1 downto 0);
    value_frac : out std_logic_vector(FRAC - 1 downto 0)   -- fraction of value (D2: echo time)
  );
end entity;

architecture rtl of param_smooth is
  constant L : positive := WIDTH + FRAC;
  constant Y0 : unsigned(L - 1 downto 0) := shift_left(to_unsigned(INIT, L), FRAC);
  signal y : unsigned(L - 1 downto 0) := Y0;
begin

  process(clk)
    variable t    : unsigned(L - 1 downto 0);
    variable diff : signed(L downto 0);
    variable step : signed(L downto 0);
    variable sum  : signed(L downto 0);
  begin
    if rising_edge(clk) then
      if rst = '1' then
        y <= Y0;
      elsif tick = '1' then
        t    := shift_left(resize(unsigned(target), L), FRAC);
        diff := signed('0' & t) - signed('0' & y);
        step := shift_right(diff, K);
        if step = 0 and diff > 0 then
          step := to_signed(1, L + 1);
        elsif step = 0 and diff < 0 then
          step := to_signed(-1, L + 1);
        end if;
        sum := signed('0' & y) + step;               -- 0 .. target range, never negative
        y   <= unsigned(sum(L - 1 downto 0));          -- (resize would keep the sign bit)
      end if;
    end if;
  end process;

  value <= std_logic_vector(y(L - 1 downto FRAC));
  value_frac <= std_logic_vector(y(FRAC - 1 downto 0));

end architecture;
