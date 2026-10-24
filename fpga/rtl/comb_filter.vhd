

library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity comb_filter is
generic (TAPS : integer:=677;
			GAIN : integer:= 10000
			);
port(
      AUD_DACLRCLK  : in std_logic;		
		int_TAPS      : in integer range 0 to 2047;
		int_GAIN      : in integer range 0 to 65535;
      data_in       : in std_logic_vector(15 downto 0);    
      data_out      : out std_logic_vector(15 downto 0)
     );
end entity;


architecture rtl of comb_filter is

component K_multiply
port(
		data_in  : in std_logic_vector(15 downto 0);
		gain     : in std_logic_vector(15 downto 0);
		data_out : out std_logic_vector(15 downto 0)
	 );
end component;

COMPONENT fcomb_RAM2 IS
	PORT
	(
		clock		: IN STD_LOGIC  := '1';
		data		: IN STD_LOGIC_VECTOR (15 DOWNTO 0);
		rdaddress		: IN STD_LOGIC_VECTOR (10 DOWNTO 0);
		wraddress		: IN STD_LOGIC_VECTOR (10 DOWNTO 0);
		wren		: IN STD_LOGIC  := '0';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;


signal read_pointer  : std_logic_vector(10 DOWNTO 0);
signal write_pointer : std_logic_vector(10 DOWNTO 0) := (others => '0');

signal temp_adder    : std_logic_vector(15 DOWNTO 0);
signal delayline_in  : std_logic_vector(15 DOWNTO 0);
signal gain_feedback : std_logic_vector(15 DOWNTO 0);
signal delayline_out : std_logic_vector(15 DOWNTO 0);

signal c_gain : std_logic_vector(15 DOWNTO 0);

signal result : std_logic_vector(31 downto 0); 
signal  a : integer;
signal  b : integer;
signal  c : integer; 

begin

					c_gain <= std_logic_vector(to_signed(GAIN, c_gain'length));

COUNTER_PROC: 	process(AUD_DACLRCLK)
				   begin
				     if falling_edge(AUD_DACLRCLK) then -- falling because it is left channel '0'
				        write_pointer <= std_logic_vector( unsigned(write_pointer) + 1 );			 
				   end if;				
				   end process;				
				       read_pointer <= std_logic_vector( unsigned(write_pointer) - int_TAPS );
						 
					delayline_in <= sat16_slv( to_integer(signed(data_in)) + to_integer(signed(gain_feedback)) );

DELAY_LINE : fcomb_RAM2 port map(
								clock	  => AUD_DACLRCLK,
								data 	  => delayline_in,
								rdaddress => read_pointer,
								wraddress => write_pointer,
								wren	  => '1',
								q         => delayline_out
								 );
								 
						a <= int_GAIN;
					   b <= to_integer(signed(delayline_out));
						c <= a*b;
						result <= std_logic_vector(to_signed(c, result'length));
		            gain_feedback <= result(31 downto 16);
			
						data_out <= delayline_out;
								 

								 
								 
end rtl;



