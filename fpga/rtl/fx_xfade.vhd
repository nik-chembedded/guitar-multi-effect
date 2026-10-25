-- -----------------------------------------------------------------------------
-- fx_xfade.vhd  (v2 step C)
-- Click-free on/off for one effect. When the enable bit changes, the output
-- fades between the dry signal and the effect output over 256 samples
-- (5.3 ms at 48 kHz); the effect keeps running until the fade-out is complete.
--   g = 0   : dout = dry  (exactly what the effect itself outputs when bypassed)
--   g = 256 : dout = effect output (exact)
--   between : dout = dry + floor((wet - dry) * g / 256)
-- dry is the effect input registered on the effect's strobe, i.e. aligned like
-- the effects' own bypass register. XFADE = false: dout = wet, no fade (v1).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity fx_xfade is
  generic (
    DW    : positive := 16;
    XFADE : boolean  := true
  );
  port (
    clk        : in  std_logic;
    tick       : in  std_logic;                     -- once per sample: fade step
    en_rise    : in  std_logic;                     -- the effect's strobe
    enable_in  : in  std_logic;                     -- register bit
    enable_eff : out std_logic;                     -- to the effect
    din        : in  std_logic_vector(DW - 1 downto 0);   -- effect input
    wet        : in  std_logic_vector(DW - 1 downto 0);   -- effect output
    dout       : out std_logic_vector(DW - 1 downto 0)
  );
end entity;

architecture rtl of fx_xfade is
  signal g     : unsigned(8 downto 0) := (others => '0');   -- 0 .. 256
  signal dry_d : signed(DW - 1 downto 0) := (others => '0');
  signal diff  : signed(DW downto 0);
  signal step  : signed(DW + 10 downto 0);
begin

  no_fade : if not XFADE generate
    enable_eff <= enable_in;
    dout       <= wet;
  end generate;

  fade : if XFADE generate
    process(clk)
    begin
      if rising_edge(clk) then
        if tick = '1' then
          if enable_in = '1' and g /= 256 then
            g <= g + 1;
          elsif enable_in = '0' and g /= 0 then
            g <= g - 1;
          end if;
        end if;
        if en_rise = '1' then
          dry_d <= signed(din);
        end if;
      end if;
    end process;

    enable_eff <= '1' when enable_in = '1' or g /= 0 else '0';

    diff <= resize(signed(wet), DW + 1) - resize(dry_d, DW + 1);
    step <= shift_right(diff * signed('0' & g), 8);
    dout <= std_logic_vector(resize(resize(dry_d, DW + 11) + step, DW));
  end generate;

end architecture;
