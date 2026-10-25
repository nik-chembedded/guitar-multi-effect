-- -----------------------------------------------------------------------------
-- echo.vhd
-- Delay line up to 32767 samples (~0.68 s) with feedback:
--   out      = dry + level * delayed / 65536
--   feedback = dry + repeat * delayed / 256   (written into the delay line)
-- so echo n has amplitude level * repeat^(n-1) * x. DW-bit samples and delay
-- line (step C). The line is 2^AW words: 32 k by default (v1 had 64 k, of which
-- the 15-bit echo_time register only reached half). The size only matters for
-- echo_time = 0 (read = write address returns the word one ring ago), so the v1
-- reference test uses AW = 16. DW = 16 is bit-exact to v1.
-- -----------------------------------------------------------------------------
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity echo is
generic (
		DW : positive := 16;                        -- sample width (16 or 24)
		AW : positive := 15                         -- delay line 2^AW words (15..16)
);
port(
		clk  : in std_logic;   -- system clock (v2 B1)
		en_rise  : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
		en_fall  : in std_logic;   -- strobe: v1 falling edge
		echo_enable   : in std_logic;
		
		e_time			: in std_logic_vector(15 downto 0);
      e_level			: in std_logic_vector(15 downto 0);	
		e_repeat			: in std_logic_vector(15 downto 0);	
			
		data_in       : in std_logic_vector(DW - 1 downto 0);
		data_out       : out std_logic_vector(DW - 1 downto 0) := (others => '0')   -- power-up 0 (sim: no X before the first strobe)
);
end entity;

architecture rtl of echo is

signal read_pointer  : std_logic_vector(AW - 1 downto 0);
signal write_pointer : std_logic_vector(AW - 1 downto 0) := (others => '0');

signal data_temp        : std_logic_vector(DW - 1 downto 0);   -- delayed sample
signal data_divided     : signed(DW - 1 downto 0);             -- level * delayed / 65536
signal rep_result_div   : signed(DW - 1 downto 0);             -- repeat * delayed / 256
signal data_in_feedback : std_logic_vector(DW - 1 downto 0);

begin

COUNTER_PROC: 	process(clk)
				begin
				 if rising_edge(clk) and en_fall = '1' then -- falling because it is left channel '0'
				    write_pointer <= std_logic_vector( unsigned(write_pointer) + 1 );			 
				 end if;				
				end process;
				
				read_pointer <= std_logic_vector( unsigned(write_pointer) - resize(unsigned(e_time(14 downto 0)), AW) );
				
DELAY_RAM :     entity work.fx_dpram generic map (WIDTH => DW, ADDR_W => AW) port map(
								clock	  => clk,
								clocken	  => en_rise,
								data 	  => data_in_feedback,
								rdaddress => read_pointer,
								wraddress => write_pointer,
								wren	  => '1',
								q         => data_temp
								 );

						data_divided   <= resize(mul_shr(signed(data_temp), unsigned(e_level), 16), DW);
						rep_result_div <= resize(mul_shr(signed(data_temp), unsigned(e_repeat(7 downto 0)), 8), DW);
						data_in_feedback <= std_logic_vector(add_sat(rep_result_div, signed(data_in), DW));

	 	 process(clk)
	    begin
		  if rising_edge(clk) and en_rise = '1' then
			if(echo_enable = '1') then
				 -- dry + level * delayed (the feedback path is not added to the output twice)
				 data_out <= std_logic_vector(add_sat(data_divided, signed(data_in), DW));
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;

end rtl;
