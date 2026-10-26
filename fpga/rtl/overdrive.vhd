-- -----------------------------------------------------------------------------
-- overdrive.vhd
-- Hard clipping at +-drive, then * gain, saturated. DW-bit samples (step C):
-- drive is a 16-bit amplitude, scaled by 2^(DW-16). DW = 16 is bit-exact to v1.
-- D6: output level (level_gain.vhd, Q8 log2 units, 0 = exactly unity) multiplies the
-- clipped and amplified wet signal before the saturation: y = sat(floor(od_out * G)).
-- -----------------------------------------------------------------------------
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity overdrive is
generic (
      DW : positive := 16                         -- sample width (16 or 24)
);
port(

      clk  : in std_logic;   -- system clock (v2 B1)
      en_rise  : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
      en_fall  : in std_logic;   -- strobe: v1 falling edge
		od_enable     : in std_logic;

		drive     : in std_logic_vector(15 downto 0);
		gain      : in std_logic_vector(15 downto 0);
		level     : in std_logic_vector(15 downto 0) := (others => '0');   -- D6: output level, signed Q8 log2 units

      data_in       : in std_logic_vector(DW - 1 downto 0);
      data_out      : out std_logic_vector(DW - 1 downto 0) := (others => '0')   -- power-up 0 (sim: no X before the first strobe)
     );
end entity;


architecture rtl of overdrive is

  constant S : natural := DW - 16;

  signal x       : signed(DW - 1 downto 0);
  signal t_drive : signed(DW + 1 downto 0);               -- drive * 2^S, up to 65535 * 2^S
  signal new_out : signed(DW + 1 downto 0) := (others => '0');
  signal od_out  : signed(DW + 18 downto 0);
  signal lv_mant : unsigned(16 downto 0);                 -- level_gain output (combinational)
  signal lv_sh   : natural range 14 to 20;
  signal lv_mant_r : unsigned(16 downto 0) := to_unsigned(65536, 17);   -- ... registered with new_out (same strobe)
  signal lv_sh_r   : natural range 14 to 20 := 16;
  signal od_lvl  : signed(DW + 36 downto 0);

begin

    x       <= signed(data_in);
    t_drive <= shift_left(resize(signed('0' & drive), DW + 2), S);

    process(clk)
	 begin
	   if rising_edge(clk) and en_rise = '1' then
		     if resize(x, DW + 2) >= t_drive then
			      new_out <= t_drive;
			  elsif resize(x, DW + 2) <= -t_drive then
			      new_out <= -t_drive;
			  else
			      new_out <= resize(x, DW + 2);
			  end if;
			  lv_mant_r <= lv_mant;      -- the level belongs to the sample it is registered with (and keeps
			  lv_sh_r   <= lv_sh;        -- the smoother -> table path off the multiplier path)
		 end if;
	 end process;

	 -- gain stage (combinational, as in v1)
	 od_out <= mul_shr(new_out, unsigned(gain), 0);

	 -- D6 level stage (one multiplier, combinational: the output register loads only on the strobe)
	 u_lvl : entity work.level_gain port map (level => level, mant => lv_mant, sh => lv_sh);
	 od_lvl <= mul_shr(od_out, lv_mant_r, lv_sh_r);

	 process(clk)
	 begin
		if rising_edge(clk) and en_rise = '1' then
			if(od_enable = '1') then
				 data_out <= std_logic_vector(sat(od_lvl, DW));   -- saturate instead of wrapping
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;

end rtl;
