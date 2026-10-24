
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity reverbe is
port(
      AUD_DACLRCLK    : in std_logic;				
      data_in         : in std_logic_vector(15 downto 0);
		reverb_mix      : in std_logic_vector(15 downto 0);
	 	reverb_type     : in std_logic_vector(15 downto 0);
		reverbe_enable  : in std_logic;	
      data_out        : out std_logic_vector(15 downto 0)
     );
end entity;

architecture rtl of reverbe is

component comb_filter is
generic (TAPS : integer:=677;
			GAIN : integer:= 45873
			);
port(
      AUD_DACLRCLK  : in std_logic;		
		int_TAPS      : in integer range 0 to 2047;
		int_GAIN      : in integer range 0 to 65535;
      data_in       : in std_logic_vector(15 downto 0);    
      data_out      : out std_logic_vector(15 downto 0)
     );
end component;

component allpass_filter is
generic (TAPS : integer:=677;
			P_GAIN : integer:= 30000;
			N_GAIN : integer:= -30000
			);
port(
      AUD_DACLRCLK  : in std_logic;	
		int_TAPS      : in integer range 0 to 4095;
		int_GAIN_pos  : in integer range -65535 to 65535;
		int_GAIN_neg  : in integer range -65535 to 65535;
      data_in       : in std_logic_vector(15 downto 0);    
      data_out      : out std_logic_vector(15 downto 0)
     );
end component;

	signal temp_mix   : std_logic_vector(7 downto 0);
   signal invert_mix : std_logic_vector(7 downto 0);
   signal int_mix    : integer;

	signal a : integer;
	signal b : integer;
	signal c : integer;
	
	signal out_dat : std_logic_vector(23 downto 0); 
	

signal cf1_out : std_logic_vector(15 downto 0);
signal cf2_out : std_logic_vector(15 downto 0);
signal cf3_out : std_logic_vector(15 downto 0);
signal cf4_out : std_logic_vector(15 downto 0);

signal cf_combined   : std_logic_vector(15 downto 0); 
signal comb_in       : std_logic_vector(15 downto 0);   -- reverb input attenuated by 4 (12 dB headroom)
signal cf_normalized : std_logic_vector(15 downto 0);

signal apf1_out : std_logic_vector(15 downto 0);

signal apf2_out : std_logic_vector(15 downto 0);

signal t_out : std_logic_vector(15 downto 0); 

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

CF1 : comb_filter generic map(TAPS => 1429 , GAIN => 52000)
						port map(
							AUD_DACLRCLK => AUD_DACLRCLK,
							int_TAPS     => cf1_taps,
							int_GAIN     => cf1_gain,
							data_in      => comb_in,
							data_out     => cf1_out
									);

CF2 : comb_filter generic map(TAPS => 1783 , GAIN => 51500)
						port map(
							AUD_DACLRCLK => AUD_DACLRCLK,
							int_TAPS     => cf2_taps,
							int_GAIN     => cf2_gain,							
							data_in      => comb_in,
							data_out     => cf2_out
									);
									
CF3 : comb_filter generic map(TAPS => 1937 , GAIN => 50000)
						port map(
							AUD_DACLRCLK => AUD_DACLRCLK,
							int_TAPS     => cf3_taps,
							int_GAIN     => cf3_gain,								
							data_in      => comb_in,
							data_out     => cf3_out
									);
									
CF4 : comb_filter generic map(TAPS => 2017 , GAIN => 50500)
						port map(
							AUD_DACLRCLK => AUD_DACLRCLK,
							int_TAPS     => cf4_taps,
							int_GAIN     => cf4_gain,								
							data_in      => comb_in,
							data_out     => cf4_out
									);	
									
							cf_combined <= sat16_slv( to_integer(signed(cf1_out)) + to_integer(signed(cf2_out))
			                         + to_integer(signed(cf3_out)) + to_integer(signed(cf4_out)) );	
						    
							--cf_normalized <= std_logic_vector( signed(cf_combined) / 4 ); 
									
APF1 : allpass_filter generic map(TAPS => 2309 , P_GAIN => 45000 , N_GAIN => -45000)
						port map(
							AUD_DACLRCLK => AUD_DACLRCLK,
							int_TAPS         => apf1_taps,
							int_GAIN_pos     => apf1_pos_gain,
							int_GAIN_neg     => apf1_neg_gain, 						
							data_in      => cf_combined,
							data_out     => apf1_out
									);		
									
APF2 : allpass_filter generic map(TAPS => 1583 , P_GAIN => 40000 , N_GAIN => -40000)
						port map(
							AUD_DACLRCLK => AUD_DACLRCLK,
							int_TAPS         => apf2_taps,
							int_GAIN_pos     => apf2_pos_gain,
							int_GAIN_neg     => apf2_neg_gain, 
							data_in      => apf1_out,
							data_out     => apf2_out
									);	
									
							--t_out <= std_logic_vector( signed(apf2_out) / 4 );
							
							
			temp_mix   <= reverb_mix(7 downto 0);
			invert_mix <= std_logic_vector(255 - unsigned(temp_mix));
			int_mix    <= to_integer(unsigned(temp_mix));
			
			a <= int_mix * to_integer(signed(apf2_out));
			b <= to_integer(unsigned(invert_mix)) * to_integer(signed(data_in));
			c <= a + b;
			
			out_dat <= std_logic_vector(to_signed(c, out_dat'length));		

	 	 process(AUD_DACLRCLK)
	    begin
		  if rising_edge(AUD_DACLRCLK) then
			if(reverbe_enable = '1') then
				 data_out <= out_dat(23 downto 8);
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;

									
end rtl;




