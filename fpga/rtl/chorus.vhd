
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity chorus is
port(
		AUD_DACLRCLK  : in std_logic;
		chorus_enable : in std_logic;
		gain          : in std_logic_vector(15 downto 0);
		chorus_rate   : in std_logic_vector(15 downto 0);
		chorus_depth  : in std_logic_vector(15 downto 0);
		data_in       : in std_logic_vector(15 downto 0);
		data_out       : out std_logic_vector(15 downto 0)
	 );
end entity;

architecture rtl of chorus is

COMPONENT chorus_RAM IS
	PORT
	(
		clock		: IN STD_LOGIC  := '1';
		data		: IN STD_LOGIC_VECTOR (15 DOWNTO 0);
		rdaddress		: IN STD_LOGIC_VECTOR (9 DOWNTO 0);
		wraddress		: IN STD_LOGIC_VECTOR (9 DOWNTO 0);
		wren		: IN STD_LOGIC  := '0';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;


signal counter_187 : integer range 0 to 1023; -- 1023
signal counter_144 : integer range 0 to 1023;
signal clk_375     : std_logic;
signal up_dwn      : std_logic;

signal read_pointer : std_logic_vector(9 downto 0);
signal write_pointer : std_logic_vector(9 downto 0);

signal ram_out : std_logic_vector(15 downto 0);
signal kmult_out : std_logic_vector(15 downto 0);
signal km1mult_out : std_logic_vector(15 downto 0);

signal  a : integer;
signal  b : integer;
signal  c : integer;
signal  result : std_logic_vector(31 downto 0);
signal data_divided : std_logic_vector(15 downto 0); 
signal data_in_feedback : std_logic_vector(15 downto 0);

signal rate_threshold : integer range 0 to 1023;
signal temp_rate    : std_logic_vector(9 downto 0);

signal depth_threshold : integer range 0 to 1023;
signal temp_depth    : std_logic_vector(9 downto 0);

begin


					temp_rate      <= chorus_rate(9 downto 0);
					rate_threshold <= to_integer(unsigned(temp_rate));
					
					temp_depth <= chorus_depth(9 downto 0);
					depth_threshold <= to_integer(unsigned(temp_depth) + 2);

clkdiv_proc : process(AUD_DACLRCLK)                      -------- chorus rate
				  begin
				      if chorus_enable = '0' then
							counter_187 <= 0;
							clk_375     <= '1';
						elsif rising_edge(AUD_DACLRCLK) then
							if counter_187 > rate_threshold then  -- 120
								clk_375 <= not(clk_375);
								counter_187 <= 0;
							else
								counter_187 <= counter_187 + 1;
							end if;
						end if;							
				  end process;
				  
updown_cntr : process(clk_375)							-------- chorus depth
				  begin
						if chorus_enable = '0' then
							 counter_144 <= 0;
							 up_dwn <= '0';
						elsif rising_edge(clk_375) then
							if up_dwn = '0' then
								if counter_144 = depth_threshold then --510
								    up_dwn <= '1';
									 counter_144 <= counter_144 - 1;
								else
								 counter_144 <= counter_144 + 1;
								end if;
							elsif up_dwn = '1' then
								if counter_144 = 2 then
								    up_dwn <= '0';
									 counter_144 <= counter_144 + 1;
								else
								 counter_144 <= counter_144 - 1;
								end if;
							end if;
						end if;
				  end process;
				  
RAM_RW_proc: 	process(AUD_DACLRCLK)
				begin
				 if falling_edge(AUD_DACLRCLK) then -- falling because it is left channel '0'
				    write_pointer <= std_logic_vector( unsigned(write_pointer) + 1 );			 
				 end if;				
				end process;
								
				read_pointer <= std_logic_vector( unsigned(write_pointer) - counter_144);				  

DELAY_RAM :     chorus_RAM port map(
								clock	  => AUD_DACLRCLK,
								data 	  => data_in_feedback,
								rdaddress => read_pointer,
								wraddress => write_pointer,
								wren	  => chorus_enable, -- was '1'
								q         => ram_out
								 );
								 
						a <= to_integer(unsigned(gain)); -------- chorus mix / level
					   b <= to_integer(signed(ram_out));
						c <= a*b;
						result <= std_logic_vector(to_signed(c, result'length));
		            data_divided <= result(31 downto 16);
						data_in_feedback <= std_logic_vector( (signed(data_divided) / 64) + signed(data_in) );
										
	 	 process(AUD_DACLRCLK)
	    begin
		  if rising_edge(AUD_DACLRCLK) then
			if(chorus_enable = '1') then
				 data_out <= std_logic_vector(signed(data_in_feedback) + signed(data_divided));
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;										
														
end rtl;














