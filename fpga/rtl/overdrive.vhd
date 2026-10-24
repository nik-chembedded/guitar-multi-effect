

library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity overdrive is
port(

      clk  : in std_logic;   -- system clock (v2 B1)
      en_rise  : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
      en_fall  : in std_logic;   -- strobe: v1 falling edge
		od_enable     : in std_logic;
		
		drive     : in std_logic_vector(15 downto 0); 
		gain      : in std_logic_vector(15 downto 0); 
		
      data_in       : in std_logic_vector(15 downto 0);      
      data_out      : out std_logic_vector(15 downto 0) := (others => '0')   -- power-up 0 (sim: no X before the first strobe)
     );
end entity;


architecture rtl of overdrive is

  signal temp_data    : integer range -32768 to 32767;
  signal new_out : integer range -65535 to 65535 := 0;
  signal od_out  : integer := 0;

  signal t_drive : integer range 0 to 65535;
  signal t_gain  : integer range 0 to 65535;

begin

	

    temp_data <= to_integer(signed(data_in));
	 
	 t_drive <= to_integer(unsigned(drive));
	 t_gain  <= to_integer(unsigned(gain));
	 
	 
    process(clk)
	 begin
	   if rising_edge(clk) and en_rise = '1' then
		     if temp_data >= t_drive then
			      new_out <= t_drive;
			  elsif temp_data <= (-1)*t_drive then
			      new_out <= (-1)*t_drive;
			  else
			      --new_out <= t_gain * temp_data;
					  new_out <= temp_data;
			  end if;
		 end if;
	 end process;
	 
	 -- combinational gain stage (was a process with only the clock in its
	 -- sensitivity list, so simulation did not match the synthesised logic)
	 od_out <= t_gain * new_out;

	 process(clk)
	 begin
		if rising_edge(clk) and en_rise = '1' then
			if(od_enable = '1') then
				 data_out <= sat16_slv(od_out);   -- saturate instead of wrapping
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;

end rtl;

