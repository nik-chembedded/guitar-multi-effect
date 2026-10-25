-- -----------------------------------------------------------------------------
-- allpass_filter.vhd
-- Schroeder all-pass for the reverb:
--   delayline_in = x + g+ * delayed / 65536
--   out          = delayed + g- * delayline_in / 65536      (g- = -g+)
-- DW-bit samples and delay line (step C); DW = 16 is bit-exact to v1.
-- TAPS / P_GAIN / N_GAIN generics are unused (values come from the reverb type).
-- -----------------------------------------------------------------------------
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity allpass_filter is
generic (TAPS : integer:=677;
			P_GAIN : integer:= 30000;
			N_GAIN : integer:= -30000;
			DW     : positive := 16                   -- sample width (16 or 24)
			);
port(
      clk  : in std_logic;   -- system clock (v2 B1)
      en_rise  : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
      en_fall  : in std_logic;   -- strobe: v1 falling edge
		int_TAPS      : in integer range 0 to 4095;
		int_GAIN_pos  : in integer range -65535 to 65535;
		int_GAIN_neg  : in integer range -65535 to 65535;
      data_in       : in std_logic_vector(DW - 1 downto 0);
      data_out      : out std_logic_vector(DW - 1 downto 0)
     );
end entity;


architecture rtl of allpass_filter is

signal read_pointer  : std_logic_vector(11 DOWNTO 0);
signal write_pointer : std_logic_vector(11 DOWNTO 0) := (others => '0');

signal delayline_in      : std_logic_vector(DW - 1 DOWNTO 0);
signal gain_feedback     : signed(DW - 1 DOWNTO 0);
signal neg_gain_feedback : signed(DW - 1 DOWNTO 0);
signal delayline_out     : std_logic_vector(DW - 1 DOWNTO 0);

begin

COUNTER_PROC: 	process(clk)
				   begin
				     if rising_edge(clk) and en_fall = '1' then -- falling because it is left channel '0'
				        write_pointer <= std_logic_vector( unsigned(write_pointer) + 1 );			 
				   end if;				
				   end process;				
				       read_pointer <= std_logic_vector( unsigned(write_pointer) - int_TAPS );
						 
					delayline_in <= std_logic_vector(add_sat(signed(data_in), gain_feedback, DW));

DELAY_LINE : entity work.fx_dpram generic map (WIDTH => DW, ADDR_W => 12) port map(
								clock	  => clk,
								clocken	  => en_rise,
								data 	  => delayline_in,
								rdaddress => read_pointer,
								wraddress => write_pointer,
								wren	  => '1',
								q         => delayline_out
								 );

					gain_feedback     <= resize(smul_shr(signed(delayline_out), to_signed(int_GAIN_pos, 18), 16), DW);
					neg_gain_feedback <= resize(smul_shr(signed(delayline_in),  to_signed(int_GAIN_neg, 18), 16), DW);

					data_out <= std_logic_vector(add_sat(signed(delayline_out), neg_gain_feedback, DW));

end rtl;
