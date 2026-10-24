

library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity allpass_filter is
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
end entity;


architecture rtl of allpass_filter is

component K_multiply
port(
		data_in  : in std_logic_vector(15 downto 0);
		gain     : in std_logic_vector(15 downto 0);
		data_out : out std_logic_vector(15 downto 0)
	 );
end component;

COMPONENT fcomb_RAM4 IS
	PORT
	(
		clock		: IN STD_LOGIC  := '1';
		data		: IN STD_LOGIC_VECTOR (15 DOWNTO 0);
		rdaddress		: IN STD_LOGIC_VECTOR (11 DOWNTO 0);
		wraddress		: IN STD_LOGIC_VECTOR (11 DOWNTO 0);
		wren		: IN STD_LOGIC  := '0';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;


signal read_pointer  : std_logic_vector(11 DOWNTO 0);
signal write_pointer : std_logic_vector(11 DOWNTO 0) := (others => '0');

signal temp_adder    : std_logic_vector(15 DOWNTO 0);
signal delayline_in  : std_logic_vector(15 DOWNTO 0);
signal gain_feedback : std_logic_vector(15 DOWNTO 0);
signal neg_gain_feedback : std_logic_vector(15 DOWNTO 0);
signal delayline_out : std_logic_vector(15 DOWNTO 0);

--signal pos_gain : std_logic_vector(15 DOWNTO 0);
--signal neg_gain : std_logic_vector(15 DOWNTO 0);

signal pos_gain : integer := 0;
signal neg_gain : integer := 0;


signal adder_out : std_logic_vector(15 DOWNTO 0);

signal result : std_logic_vector(31 downto 0); 
signal result_neg : std_logic_vector(31 downto 0); 
signal  a : integer := 0;
signal  b : integer := 0;
signal  c : integer := 0;
signal  d : integer := 0;

begin

--					pos_gain <= std_logic_vector(to_signed(P_GAIN, pos_gain'length));
--					neg_gain <= std_logic_vector(to_signed(N_GAIN, neg_gain'length));

COUNTER_PROC: 	process(AUD_DACLRCLK)
				   begin
				     if falling_edge(AUD_DACLRCLK) then -- falling because it is left channel '0'
				        write_pointer <= std_logic_vector( unsigned(write_pointer) + 1 );			 
				   end if;				
				   end process;				
				       read_pointer <= std_logic_vector( unsigned(write_pointer) - int_TAPS );
						 
					delayline_in <= sat16_slv( to_integer(signed(data_in)) + to_integer(signed(gain_feedback)) );
					
					adder_out    <= sat16_slv( to_integer(signed(delayline_out)) + to_integer(signed(neg_gain_feedback)) );

DELAY_LINE : fcomb_RAM4 port map(
								clock	  => AUD_DACLRCLK,
								data 	  => delayline_in,
								rdaddress => read_pointer,
								wraddress => write_pointer,
								wren	  => '1',
								q         => delayline_out
								 );
								 
								 pos_gain <= int_GAIN_pos;							 
								 a <= to_integer(signed(delayline_out));
								 c <= a * pos_gain;
								 result <= std_logic_vector(to_signed(c, result'length));
		                   gain_feedback <= result(31 downto 16); 
								 
								 neg_gain <= int_GAIN_neg;
								 b <= to_integer(signed(delayline_in));
								 d <= b * neg_gain; 
								 result_neg <=std_logic_vector(to_signed(d, result'length));
								 neg_gain_feedback <= result_neg(31 downto 16); 
								 
--G_PLUS       : K_multiply port map(
--									data_in  => delayline_out,
--									gain     => pos_gain,
--									data_out => gain_feedback
--								 );
								 
--G_MINUS      : K_multiply port map(
--									data_in  => delayline_in,
--									gain     => neg_gain,
--									data_out => neg_gain_feedback
--								 );								 
								 
								 
								 data_out <= adder_out;

								 
end rtl;



