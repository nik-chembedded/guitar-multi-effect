

library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity overdrive is
port(

      AUD_DACLRCLK  : in std_logic;
		CLK_18MHZ     : in std_logic;
		od_enable     : in std_logic;
		
		drive     : in std_logic_vector(15 downto 0); 
		gain      : in std_logic_vector(15 downto 0); 
		
      data_in       : in std_logic_vector(15 downto 0);      
      data_out      : out std_logic_vector(15 downto 0)
     );
end entity;


architecture rtl of overdrive is

  signal temp_data    : integer;
  signal temp_product : integer;
  signal new_out : integer;
  signal od_out  : integer;
  
  signal t_drive : integer;
  signal t_gain  : integer;
  
begin

	

    temp_data <= to_integer(signed(data_in));
	 
	 t_drive <= to_integer(unsigned(drive));
	 t_gain  <= to_integer(unsigned(gain));
	 
	 
    process(AUD_DACLRCLK)
	 begin
	   if rising_edge(AUD_DACLRCLK) then
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
	 
	 process(AUD_DACLRCLK)
	 begin
			od_out <= t_gain * new_out;
	 end process;
 
	 process(AUD_DACLRCLK)
	 begin
		if rising_edge(AUD_DACLRCLK) then
			if(od_enable = '1') then
				 data_out <= std_logic_vector(to_signed(od_out, data_out'length)); 
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;

end rtl;

