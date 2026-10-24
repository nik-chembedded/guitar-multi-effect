library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity DAC_CONTROLLER is
port(
      AUD_BCLK      : in std_logic;
      AUD_DACLRCLK  : in std_logic;		

	  channel_left  : in std_logic_vector(15 downto 0);
	  channel_right : in std_logic_vector(15 downto 0);
	  
	  left_empty    : in std_logic;
	  right_empty   : in std_logic;
			
	  AUD_DACDAT    : out std_logic
     );
end entity;


architecture rtl of DAC_CONTROLLER is

signal left_ch_counter  : integer range 0 to 32;
signal right_ch_counter : integer range 0 to 32;

--signal temp_data        : std_logic_vector(31 downto 0);
signal temp_left  : std_logic_vector(31 downto 0);
signal temp_right : std_logic_vector(31 downto 0);

signal out_temp         : std_logic;

signal bit_clock         : std_logic;
signal inverse_bit_clock : std_logic;

begin

    AUD_DACDAT <= out_temp;
	
	
	process(AUD_BCLK)             --- load left channel data
	begin
	  if rising_edge(AUD_BCLK) then
	         if left_ch_counter = 0 and AUD_DACLRCLK = '0' then
			    temp_left <= channel_left & "0000000000000000";
			end if;	
	  end if;
	end process;
	
	process(AUD_BCLK)             --- load left channel data
	begin
	  if rising_edge(AUD_BCLK) then
	         if right_ch_counter = 0 and AUD_DACLRCLK = '1' then
			    temp_right <= channel_right & "0000000000000000";
			end if;	
	  end if;
	end process;
	

   process(AUD_BCLK)
	begin
	      if falling_edge(AUD_BCLK) and AUD_DACLRCLK = '0' then    --- left channel
			 if left_empty = '1' then
			       out_temp <= '0';
             else
                 out_temp <= temp_left(31-left_ch_counter);
             end if;
			 
			 if left_ch_counter = 31 then
			    left_ch_counter <= 0;
			 else
			    left_ch_counter <= left_ch_counter + 1;
			 end if;
			 right_ch_counter <= 0;
		     
		  elsif falling_edge(AUD_BCLK) and AUD_DACLRCLK = '1' then    --- right channel
			 if right_empty = '1' then
			      out_temp <= '0';
			 else
                  out_temp <= temp_right(31-right_ch_counter);
             end if;				  
			 if right_ch_counter = 31 then
			    right_ch_counter <= 0;
			 else
			    right_ch_counter <= right_ch_counter + 1;
			 end if;
			 left_ch_counter <= 0;
		  end if;	
	end process;

end architecture;








