-- -----------------------------------------------------------------------------
-- nco_lfo.vhd  (v2 step D1)
-- Generated LFO: 32-bit phase accumulator, advanced once per sample (tick).
--   rate  : frequency in 0.01 Hz (1 .. 2000 = 0.01 .. 20 Hz)
--           inc = rate * 2^32 / (100 * 48000) = (rate * 916260) / 1024
--   shape : 0 sine, 1 triangle, 2 saw (rises over 95 % of the period, ramps down
--           over the last 5 %: no hard reset, like the v1 table), 3 square
--   lfo   : unipolar 0 .. 65535 (sine: 32768 + 32767 * sin, starting at the middle)
-- Sine: quarter-wave table SINE_Q (257 x 15 bit, lfo_sine_pkg) with linear
-- interpolation on the next 8 phase bits. Triangle / saw / square are taken from
-- the phase. The phase is continuous: rate and shape changes never jump in phase.
-- Python reference model: sim/cocotb/lfo_model.py (bit-exact).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.lfo_sine_pkg.all;

entity nco_lfo is
  port (
    clk   : in  std_logic;
    tick  : in  std_logic;                      -- once per sample
    rate  : in  std_logic_vector(15 downto 0);  -- 0.01 Hz
    shape : in  std_logic_vector(1 downto 0);
    lfo   : out std_logic_vector(15 downto 0)
  );
end entity;

architecture rtl of nco_lfo is
  constant K : natural := 916260;               -- 2^42 / 4.8e6, rounded
  -- saw: rise over u < SAW_B (95 % of 65536), fall over the rest
  constant SAW_B  : natural := 62259;
  constant SAW_K1 : natural := 68984;           -- 65535 * 65536 / SAW_B
  constant SAW_K2 : natural := 1310620;         -- 65535 * 65536 / (65536 - SAW_B)

  signal inc   : unsigned(31 downto 0) := (others => '0');
  signal phase : unsigned(31 downto 0) := (others => '0');
  signal lfo_r : unsigned(15 downto 0) := (others => '0');

  function saw16(p : unsigned(31 downto 0)) return unsigned is
    variable u : unsigned(15 downto 0) := p(31 downto 16);
    variable v : unsigned(37 downto 0);
  begin
    if u < SAW_B then
      v := resize(shift_right(u * to_unsigned(SAW_K1, 17), 16), 38);
    else
      v := resize(shift_right((65535 - u) * to_unsigned(SAW_K2, 21), 16), 38);
    end if;
    if v > 65535 then
      return to_unsigned(65535, 16);
    else
      return v(15 downto 0);
    end if;
  end function;

  function sine16(p : unsigned(31 downto 0)) return unsigned is
    variable idx, fr : natural range 0 to 255;
    variable j       : natural range 0 to 255;
    variable f       : natural range 0 to 256;
    variable v       : natural range 0 to 32767;
  begin
    idx := to_integer(p(29 downto 22));
    fr  := to_integer(p(21 downto 14));
    if p(30) = '0' then                         -- quadrants 0 and 2: rising
      j := idx;       f := fr;
    else                                        -- quadrants 1 and 3: mirrored
      j := 255 - idx; f := 256 - fr;
    end if;
    v := SINE_Q(j) + ((SINE_Q(j + 1) - SINE_Q(j)) * f) / 256;   -- difference >= 0: "/" = floor
    if p(31) = '0' then
      return to_unsigned(32768 + v, 16);
    else
      return to_unsigned(32768 - v, 16);
    end if;
  end function;

begin

  process(clk)
    variable w : unsigned(15 downto 0);
  begin
    if rising_edge(clk) then
      inc <= resize(shift_right(unsigned(rate) * to_unsigned(K, 20), 10), 32);
      if tick = '1' then
        phase <= phase + inc;
      end if;
      case shape is
        when "00"   => w := sine16(phase);
        when "01"   => if phase(31) = '0' then w := phase(30 downto 15);
                       else w := not phase(30 downto 15); end if;
        when "10"   => w := saw16(phase);
        when others => if phase(31) = '0' then w := (others => '1');
                       else w := (others => '0'); end if;
      end case;
      lfo_r <= w;
    end if;
  end process;

  lfo <= std_logic_vector(lfo_r);

end architecture;
