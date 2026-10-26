-- -----------------------------------------------------------------------------
-- distortion.vhd
-- Waveshaping with ROM transfer curves (|f(|x|)| for |x| = 0..16383), sign
-- restored, dry/wet mix. DW-bit samples (step C): the table is addressed with
-- |x| / 2^(DW-16) and its value scaled by 2^(DW-16). DW = 16 is bit-exact to v1.
-- D6: the shaped value (the wet path, before the dry/wet mix) is multiplied by the output
-- level (level_gain.vhd, Q8 log2 units, 0 = exactly unity) and saturated at +-(2^(DW-1)-1);
-- the sign is restored afterwards, so the level stage is symmetric.
-- -----------------------------------------------------------------------------
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity distortion is
generic (
      DW : positive := 16                         -- sample width (16 or 24)
);
port(

      clk  : in std_logic;   -- system clock (v2 B1)
      en_rise  : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
      en_fall  : in std_logic;   -- strobe: v1 falling edge
		dist_enable     : in std_logic;
		
		--drive     : in std_logic_vector(15 downto 0); 
		mix      : in std_logic_vector(15 downto 0);
		d_type   : in std_logic_vector(15 downto 0); 
		level    : in std_logic_vector(15 downto 0) := (others => '0');   -- D6: output level, signed Q8 log2 units
		
      data_in       : in std_logic_vector(DW - 1 downto 0);
      
      data_out      : out std_logic_vector(DW - 1 downto 0) := (others => '0')   -- power-up 0 (sim: no X before the first strobe)
     );
end entity;


architecture rtl of distortion is


COMPONENT dist_ROM IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (14 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;

COMPONENT dist_ROM_soft IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (13 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		rden		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;

COMPONENT dist_ROM_medium IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (13 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		rden		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;

COMPONENT dist_ROM_hard IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (13 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		rden		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;


	constant S : natural := DW - 16;

	signal data_temp : std_logic_vector(15 downto 0);
	signal mag       : unsigned(DW downto 0);                    -- |x| / 2^S (no overflow at -2^(DW-1))
	signal data_to_addr  : integer range 0 to 16383 := 0;   -- |x| saturated to the table size
	signal d_addr  : std_logic_vector(13 downto 0);
	signal neg_d   : boolean := false;                      -- sign of the sample in the ROM
	signal dry_d   : signed(DW - 1 downto 0) := (others => '0');   -- dry sample aligned with the ROM output
	signal wet     : signed(DW - 1 downto 0);
	signal wet_mag : signed(DW - 1 downto 0);               -- |wet| after the level stage
	signal lv_mant : unsigned(16 downto 0);                  -- level_gain output (combinational)
	signal lv_sh   : natural range 14 to 20;
	signal lv_mant_r : unsigned(16 downto 0) := to_unsigned(65536, 17);   -- ... registered with the address (same strobe)
	signal lv_sh_r   : natural range 14 to 20 := 16;
	signal lv_p    : unsigned(32 downto 0);                  -- table value * mantissa
	signal lv_s    : unsigned(32 + S downto 0);              -- ... * 2^S
	signal lv_m    : unsigned(32 + S downto 0);              -- ... / 2^sh
	signal out_dat : signed(DW - 1 downto 0);

	signal soft_en : std_logic;
	signal med_en  : std_logic;
	signal hard_en : std_logic;
	signal soft_out_temp : std_logic_vector(15 downto 0);
	signal med_out_temp  : std_logic_vector(15 downto 0);
	signal hard_out_temp : std_logic_vector(15 downto 0);
	signal temp_type    : std_logic_vector(1 downto 0);

begin



			
			mag <= shift_right(unsigned(abs(resize(signed(data_in), DW + 1))), S);
			
			-- The transfer curves only cover |x| = 0..16383 (14-bit address).
			-- Saturate the address instead of letting |x| >= 16384 wrap around,
			-- and remember the sign so the curve is applied symmetrically.
			process(clk)
			begin
				if rising_edge(clk) and en_rise = '1' then
					if mag > 16383 then
						data_to_addr <= 16383;
					else
						data_to_addr <= to_integer(mag);
					end if;
					neg_d <= signed(data_in) < 0;
					dry_d <= signed(data_in);
					lv_mant_r <= lv_mant;       -- the level belongs to the sample it is registered with (and keeps
					lv_sh_r   <= lv_sh;         -- the smoother -> table path off the multiplier path)
			 end if;
			end process;
			
			d_addr <= std_logic_vector(to_unsigned(data_to_addr, d_addr'length));

--ROM   : dist_ROM port map(
--							address => d_addr,
--							clock   => clk,
--							q       => data_temp
--								);
								
ROM_soft : dist_ROM_soft port map(
							address => d_addr,
							rden    => soft_en,
							clock   => clk,
							q       => soft_out_temp
								);
ROM_med  : dist_ROM_medium port map(
							address => d_addr,
							rden    => med_en,
							clock   => clk,
							q       => med_out_temp
								);
ROM_hard : dist_ROM_hard port map(
							address => d_addr,
							rden    => hard_en,
							clock   => clk,
							q       => hard_out_temp
								);
								
			temp_type <= d_type(1 downto 0);
			process(temp_type, soft_out_temp, med_out_temp, hard_out_temp)   -- all mux inputs (simulation)
			begin
			case (temp_type) is
			when "00"   => data_temp <= soft_out_temp;
								soft_en   <= '1';
								med_en    <= '0';
								hard_en   <= '0';
			when "01"   => data_temp <= med_out_temp;
								soft_en   <= '0';
								med_en    <= '1';
								hard_en   <= '0';
			when "10"   => data_temp <= hard_out_temp;
								soft_en   <= '0';
								med_en    <= '0';
								hard_en   <= '1';
			when "11"   => data_temp <= soft_out_temp;
								soft_en   <= '1';
								med_en    <= '0';
								hard_en   <= '0';
			when others => data_temp <= soft_out_temp;
								soft_en   <= '1';
								med_en    <= '0';
								hard_en   <= '0';
			end case;
			end process;
			
			
--										temp_int_sign <= to_integer(unsigned(data_temp));
--										
--determine_sign_proc :			process(clk)
--										begin
--											if rising_edge(clk) and en_rise = '1' then
--												if temp_int >= 0 then
--												  int_sign <= temp_int_sign;	
--												else
--												  int_sign <= (-1) * temp_int_sign;	
--												end if;
--											end if;
--										end process;
--										temp_data_sign <= std_logic_vector(to_signed(int_sign, temp_data_sign'length));
								
			-- restore the sign of the waveshaped sample (the ROM holds |f(|x|)|)
			-- D6 level stage on the magnitude (one 16 x 17 multiplier, combinational: data_out loads only on the strobe)
			u_lvl : entity work.level_gain port map (level => level, mant => lv_mant, sh => lv_sh);
			lv_p    <= unsigned(data_temp) * lv_mant_r;
			lv_s    <= shift_left(resize(lv_p, 33 + S), S);
			lv_m    <= shift_right(lv_s, lv_sh_r);
			wet_mag <= to_signed(2 ** (DW - 1) - 1, DW) when lv_m > 2 ** (DW - 1) - 1
			           else signed(resize(lv_m, DW));
			wet     <= -wet_mag when neg_d else wet_mag;

			out_dat <= mix8(dry_d, wet, unsigned(mix(7 downto 0)));

	process(clk)
	 begin
		if rising_edge(clk) and en_rise = '1' then
			if(dist_enable = '1') then
				 data_out <= std_logic_vector(out_dat);
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;
	
	
end rtl;