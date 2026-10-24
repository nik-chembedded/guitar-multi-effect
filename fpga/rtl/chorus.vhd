
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

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


signal counter_187 : integer range 0 to 1023 := 0; -- LFO step divider
signal counter_144 : integer range 0 to 1023 := 2; -- current delay [samples]
signal clk_375     : std_logic := '1';
signal up_dwn      : std_logic := '0';

signal read_pointer : std_logic_vector(9 downto 0);
signal write_pointer : std_logic_vector(9 downto 0) := (others => '0');

signal ram_out : std_logic_vector(15 downto 0);
signal kmult_out : std_logic_vector(15 downto 0);
signal km1mult_out : std_logic_vector(15 downto 0);

signal  a : integer := 0;
signal  b : integer := 0;
signal  c : integer := 0;
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
					-- sweep limit = depth + 2, clamped to the 1024-word delay line
					depth_threshold <= 1023 when to_integer(unsigned(temp_depth)) > 1021
					                   else to_integer(unsigned(temp_depth)) + 2;

-- Triangle LFO for the delay length, entirely in the sample clock domain.
-- (Previously a divided ripple clock "clk_375" drove a second process, and both
-- used chorus_enable - a register from the Nios clock domain - as an
-- asynchronous reset.) The step rate is unchanged: one step every
-- 2*(rate+2) samples.
lfo_proc : process(AUD_DACLRCLK)                      -------- chorus rate / depth
				  begin
						if rising_edge(AUD_DACLRCLK) then
							if chorus_enable = '0' then
								counter_187 <= 0;
								clk_375     <= '1';
								counter_144 <= 2;
								up_dwn      <= '0';
							elsif counter_187 > rate_threshold then
								clk_375     <= not(clk_375);
								counter_187 <= 0;
								if clk_375 = '0' then             -- former rising edge of clk_375: one LFO step
									if up_dwn = '0' then
										-- ">=" so that lowering the depth while sweeping up turns
										-- around immediately (with "=" the counter ran on to 1023
										-- and wrapped to 0)
										if counter_144 >= depth_threshold then
											up_dwn      <= '1';
											counter_144 <= counter_144 - 1;
										else
											counter_144 <= counter_144 + 1;
										end if;
									else
										if counter_144 <= 2 then
											up_dwn      <= '0';
											counter_144 <= counter_144 + 1;
										else
											counter_144 <= counter_144 - 1;
										end if;
									end if;
								end if;
							else
								counter_187 <= counter_187 + 1;
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
						data_in_feedback <= sat16_slv( to_integer(signed(data_divided)) / 64 + to_integer(signed(data_in)) );

	 	 process(AUD_DACLRCLK)
	    begin
		  if rising_edge(AUD_DACLRCLK) then
			if(chorus_enable = '1') then
				 data_out <= sat16_slv( to_integer(signed(data_in_feedback)) + to_integer(signed(data_divided)) );
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;										
														
end rtl;














