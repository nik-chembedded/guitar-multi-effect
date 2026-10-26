-- -----------------------------------------------------------------------------
-- fx_bypass.vhd  (v2 step D5)
-- Zero-latency click-free bypass of a chain stage (dynamics, EQ; the cabinet,
-- cab_stage.vhd, has the same arithmetic with its own bank logic).
--
--   dout = din + floor((wet - din) * g / 256),  g = 0 .. 256, COMBINATIONAL from din
--   g = 0   : dout = din exactly (stage off = no latency, chain stays bit-exact)
--   g = 256 : dout = wet exactly
--   g moves once per `tick` (sample_tick): +1 while enable = 1, -1 while enable = 0
--   (256 samples = 5.3 ms). XFADE = false: g jumps to 0 / 256 at the tick.
-- active = '1' while the stage is on or still fading out (g /= 0 or enable).
-- fx_xfade is not used: its dry path is registered (one clock more latency).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity fx_bypass is
  generic (
    DW    : positive := 24;
    XFADE : boolean  := true
  );
  port (
    clk    : in  std_logic;
    tick   : in  std_logic;                       -- once per sample: fade step
    enable : in  std_logic;
    din    : in  std_logic_vector(DW - 1 downto 0);
    wet    : in  std_logic_vector(DW - 1 downto 0);
    dout   : out std_logic_vector(DW - 1 downto 0);
    active : out std_logic
  );
end entity;

architecture rtl of fx_bypass is
  signal g    : natural range 0 to 256 := 0;
  signal diff : signed(DW downto 0);
  signal prod : signed(DW + 10 downto 0);
begin

  process(clk)
  begin
    if rising_edge(clk) then
      if tick = '1' then
        if not XFADE then
          if enable = '1' then g <= 256; else g <= 0; end if;
        elsif enable = '1' then
          if g /= 256 then g <= g + 1; end if;
        elsif g /= 0 then
          g <= g - 1;
        end if;
      end if;
    end if;
  end process;

  active <= '1' when enable = '1' or g /= 0 else '0';

  diff <= resize(signed(wet), DW + 1) - resize(signed(din), DW + 1);
  prod <= diff * signed('0' & to_unsigned(g, 9));
  dout <= std_logic_vector(resize(resize(signed(din), DW + 11) + shift_right(prod, 8), DW));

end architecture;
