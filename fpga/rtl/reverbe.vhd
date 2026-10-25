
-- -----------------------------------------------------------------------------
-- reverbe.vhd
-- Schroeder reverb: input / 4 into 4 parallel comb filters, summed, then 2
-- all-pass filters in series; dry/wet mix. Room presets select the taps and
-- gains. DW-bit samples (step C); DW = 16 is bit-exact to v1.
-- -----------------------------------------------------------------------------
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity reverbe is
generic (
      DW : positive := 16                         -- sample width (16 or 24)
);
port(
      clk    : in std_logic;   -- system clock (v2 B1)
      en_rise    : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
      en_fall    : in std_logic;   -- strobe: v1 falling edge
      data_in         : in std_logic_vector(DW - 1 downto 0);
		reverb_mix      : in std_logic_vector(15 downto 0);
	 	reverb_type     : in std_logic_vector(15 downto 0);
		reverbe_enable  : in std_logic;	
      data_out        : out std_logic_vector(DW - 1 downto 0) := (others => '0')   -- power-up 0 (sim: no X before the first strobe)
     );
end entity;

architecture rtl of reverbe is



signal cf1_out : std_logic_vector(DW - 1 downto 0);
signal cf2_out : std_logic_vector(DW - 1 downto 0);
signal cf3_out : std_logic_vector(DW - 1 downto 0);
signal cf4_out : std_logic_vector(DW - 1 downto 0);

signal cf_combined   : std_logic_vector(DW - 1 downto 0);
signal comb_in       : std_logic_vector(DW - 1 downto 0);   -- reverb input attenuated by 4 (12 dB headroom)

signal apf1_out : std_logic_vector(DW - 1 downto 0);
signal apf2_out : std_logic_vector(DW - 1 downto 0);

signal out_dat  : signed(DW - 1 downto 0);

signal temp_type    : std_logic_vector(3 downto 0);

signal cf1_taps,cf2_taps,cf3_taps,cf4_taps : integer range 0 to 2047;
signal apf1_taps,apf2_taps						 : integer range 0 to 4095;

signal cf1_gain,cf2_gain,cf3_gain,cf4_gain : integer range 0 to 65535;
signal apf1_pos_gain,apf2_pos_gain         : integer range -65535 to 65535;
signal apf1_neg_gain,apf2_neg_gain         : integer range -65535 to 65535;

begin

			temp_type <= reverb_type(3 downto 0);
			process(temp_type)
			begin
			case (temp_type) is
			when "0011"   => cf1_taps <= 1733;           -- Heavy Reverb
								  cf2_taps <= 1493;
								  cf3_taps <= 1949;
								  cf4_taps <= 2017;
								  
								  apf1_taps <= 241; 
								  apf2_taps <= 83;
								  
								  cf1_gain <= 52756;
								  cf2_gain <= 54198;
								  cf3_gain <= 51314;
								  cf4_gain <= 50069;
								  
								  apf1_pos_gain <= 45875;
								  apf1_neg_gain <= -45875;								  
								  apf2_pos_gain <= 45875;
								  apf2_neg_gain <= -45875;
								  
			when "0000"   => cf1_taps <= 827;				-- Very Soft Reverb
								  cf2_taps <= 919;
								  cf3_taps <= 1021;
								  cf4_taps <= 1103;
								  
								  apf1_taps <= 241; 
								  apf2_taps <= 83;
								  
								  cf1_gain <= 12910;
								  cf2_gain <= 14352;
								  cf3_gain <= 11534;
								  cf4_gain <= 13369;
								  
								  apf1_pos_gain <= 29491;
								  apf1_neg_gain <= -29491;								  
								  apf2_pos_gain <= 29491;
								  apf2_neg_gain <= -29491;
								  
			when "0001"   => cf1_taps <= 1297;				-- Light Reverb
								  cf2_taps <= 1447;
								  cf3_taps <= 1571;
								  cf4_taps <= 1741;
								  
								  apf1_taps <= 241; 
								  apf2_taps <= 83;
								  
								  cf1_gain <= 27590;
								  cf2_gain <= 26673;
								  cf3_gain <= 30932;
								  cf4_gain <= 31522;
								  
								  apf1_pos_gain <= 36044;
								  apf1_neg_gain <= -36044;								  
								  apf2_pos_gain <= 36044;
								  apf2_neg_gain <= -36044;
								  
			when "0010"   => cf1_taps <= 1429;				-- Medium Reverb
								  cf2_taps <= 1783;
								  cf3_taps <= 1937;
								  cf4_taps <= 2017;
								  
								  apf1_taps <= 479; 
								  apf2_taps <= 167;
								  
								  cf1_gain <= 38928;
								  cf2_gain <= 40435;
								  cf3_gain <= 45285;
								  cf4_gain <= 36175;
								  
								  apf1_pos_gain <= 39321;
								  apf1_neg_gain <= -39321;								  
								  apf2_pos_gain <= 39321;
								  apf2_neg_gain <= -39321;
								  
								  
								  
			when others =>   cf1_taps <= 1733;
								  cf2_taps <= 1493;
								  cf3_taps <= 1949;
								  cf4_taps <= 2017;
								  
								  apf1_taps <= 241; 
								  apf2_taps <= 83;
								  
								  cf1_gain <= 52756;
								  cf2_gain <= 54198;
								  cf3_gain <= 51314;
								  cf4_gain <= 50069;
								  
								  apf1_pos_gain <= 45875;
								  apf1_neg_gain <= -45875;								  
								  apf2_pos_gain <= 45875;
								  apf2_neg_gain <= -45875;
			end case;
			end process;


-- The comb filters have feedback gains up to ~0.83 (DC gain up to ~6x) and
-- four of them are summed: attenuate the input by 4 for headroom (the
-- adders below also saturate instead of wrapping).
comb_in <= std_logic_vector( shift_right(signed(data_in), 2) );

CF1 : entity work.comb_filter generic map(DW => DW, TAPS => 1429 , GAIN => 52000)
						port map(
							clk => clk,
							en_rise => en_rise,
							en_fall => en_fall,
							int_TAPS     => cf1_taps,
							int_GAIN     => cf1_gain,
							data_in      => comb_in,
							data_out     => cf1_out
									);

CF2 : entity work.comb_filter generic map(DW => DW, TAPS => 1783 , GAIN => 51500)
						port map(
							clk => clk,
							en_rise => en_rise,
							en_fall => en_fall,
							int_TAPS     => cf2_taps,
							int_GAIN     => cf2_gain,							
							data_in      => comb_in,
							data_out     => cf2_out
									);
									
CF3 : entity work.comb_filter generic map(DW => DW, TAPS => 1937 , GAIN => 50000)
						port map(
							clk => clk,
							en_rise => en_rise,
							en_fall => en_fall,
							int_TAPS     => cf3_taps,
							int_GAIN     => cf3_gain,								
							data_in      => comb_in,
							data_out     => cf3_out
									);
									
CF4 : entity work.comb_filter generic map(DW => DW, TAPS => 2017 , GAIN => 50500)
						port map(
							clk => clk,
							en_rise => en_rise,
							en_fall => en_fall,
							int_TAPS     => cf4_taps,
							int_GAIN     => cf4_gain,								
							data_in      => comb_in,
							data_out     => cf4_out
									);	
									
							cf_combined <= std_logic_vector(sat(
							     resize(signed(cf1_out), DW + 2) + resize(signed(cf2_out), DW + 2)
							   + resize(signed(cf3_out), DW + 2) + resize(signed(cf4_out), DW + 2), DW));
							--cf_normalized <= std_logic_vector( signed(cf_combined) / 4 ); 
									
APF1 : entity work.allpass_filter generic map(DW => DW, TAPS => 2309 , P_GAIN => 45000 , N_GAIN => -45000)
						port map(
							clk => clk,
							en_rise => en_rise,
							en_fall => en_fall,
							int_TAPS         => apf1_taps,
							int_GAIN_pos     => apf1_pos_gain,
							int_GAIN_neg     => apf1_neg_gain, 						
							data_in      => cf_combined,
							data_out     => apf1_out
									);		
									
APF2 : entity work.allpass_filter generic map(DW => DW, TAPS => 1583 , P_GAIN => 40000 , N_GAIN => -40000)
						port map(
							clk => clk,
							en_rise => en_rise,
							en_fall => en_fall,
							int_TAPS         => apf2_taps,
							int_GAIN_pos     => apf2_pos_gain,
							int_GAIN_neg     => apf2_neg_gain, 
							data_in      => apf1_out,
							data_out     => apf2_out
									);	
									
							--t_out <= std_logic_vector( signed(apf2_out) / 4 );
							
							
			out_dat <= mix8(signed(data_in), signed(apf2_out), unsigned(reverb_mix(7 downto 0)));

	 	 process(clk)
	    begin
		  if rising_edge(clk) and en_rise = '1' then
			if(reverbe_enable = '1') then
				 data_out <= std_logic_vector(out_dat);
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;

									
end rtl;




