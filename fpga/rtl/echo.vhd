library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity echo is
port(
		clk  : in std_logic;   -- system clock (v2 B1)
		en_rise  : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
		en_fall  : in std_logic;   -- strobe: v1 falling edge
		echo_enable   : in std_logic;
		
		e_time			: in std_logic_vector(15 downto 0);
      e_level			: in std_logic_vector(15 downto 0);	
		e_repeat			: in std_logic_vector(15 downto 0);	
			
		data_in       : in std_logic_vector(15 downto 0);
		data_out       : out std_logic_vector(15 downto 0) := (others => '0')   -- power-up 0 (sim: no X before the first strobe)
);
end entity;

architecture rtl of echo is



COMPONENT echo_ram IS
	PORT
	(
		clocken		: IN STD_LOGIC  := '1';
		clock		: IN STD_LOGIC  := '1';
		data		: IN STD_LOGIC_VECTOR (15 DOWNTO 0);
		rdaddress		: IN STD_LOGIC_VECTOR (15 DOWNTO 0);
		wraddress		: IN STD_LOGIC_VECTOR (15 DOWNTO 0);
		wren		: IN STD_LOGIC  := '0';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;


signal read_pointer : std_logic_vector(15 downto 0);
signal write_pointer : std_logic_vector(15 downto 0) := (others => '0');

signal data_temp : std_logic_vector(15 downto 0);
signal data_divided : std_logic_vector(15 downto 0); 

signal data_in_feedback : std_logic_vector(15 downto 0); 

signal result : std_logic_vector(31 downto 0); 
signal  a : integer := 0;
signal  b : integer := 0;
signal  c : integer := 0;

signal echo_rep   : std_logic_vector(7 downto 0);
signal d,e,f      : integer := 0;
signal rep_result : std_logic_vector(23 downto 0); 
signal rep_result_div : std_logic_vector(15 downto 0); 

signal t_time : std_logic_vector(14 downto 0);
signal interval : integer range 0 to 32767;


begin

		interval <= to_integer(unsigned( e_time(14 downto 0) ));

COUNTER_PROC: 	process(clk)
				begin
				 if rising_edge(clk) and en_fall = '1' then -- falling because it is left channel '0'
				    write_pointer <= std_logic_vector( unsigned(write_pointer) + 1 );			 
				 end if;				
				end process;
				
				read_pointer <= std_logic_vector( unsigned(write_pointer) - interval ); -- was +
				
DELAY_RAM :     echo_ram port map(
								clock	  => clk,
								clocken	  => en_rise,
								data 	  => data_in_feedback,
								rdaddress => read_pointer,
								wraddress => write_pointer,
								wren	  => '1',
								q         => data_temp
								 );
				
	 --process(echo_enable)
	 --begin
	 --case (echo_enable) is
	 -- when '1' => data_out <= std_logic_vector( signed(data_temp) + signed(data_in) );
	 --when '0' => data_out <= data_in;
	 -- end case;
	 --end process;
	    
		 				a <= to_integer(unsigned(e_level));
					   b <= to_integer(signed(data_temp));
						c <= a*b;
						result <= std_logic_vector(to_signed(c, result'length));
		            data_divided <= result(31 downto 16);
						
						-- Feedback = repeat * delayed (independent of the output level), so
						-- echo n has amplitude level * repeat^(n-1) * x.
						echo_rep 	<= e_repeat(7 downto 0);
						d        	<= to_integer(unsigned(echo_rep));
						e        	<= to_integer(signed(data_temp));
						f        	<= d*e;
						rep_result  <= std_logic_vector(to_signed(f, rep_result'length));
					   rep_result_div <= rep_result(23 downto 8);

						data_in_feedback <= sat16_slv( to_integer(signed(rep_result_div)) + to_integer(signed(data_in)) );

	 	 process(clk)
	    begin
		  if rising_edge(clk) and en_rise = '1' then
			if(echo_enable = '1') then
				 -- dry + level * delayed (the feedback path is not added to the output twice)
				 data_out <= sat16_slv( to_integer(signed(data_divided)) + to_integer(signed(data_in)) );
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;
				
end rtl;