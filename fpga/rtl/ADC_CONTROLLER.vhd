library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity ADC_CONTROLLER is 
port (
		AUD_BCLK     : in std_logic;		
		AUD_ADCDAT   : in std_logic;
		AUD_ADCLRCLK : in std_logic;
		
		fifo_bclk    : out std_logic;
		
		left_full    : in std_logic;
		right_full   : in std_logic;
		
		left_right_reset : in std_logic;
		
		left_ready    : out std_logic;
		right_ready   : out std_logic;		
		channel_left : out std_logic_vector(15 downto 0);
		channel_right : out std_logic_vector(15 downto 0)		

      );
end entity;

architecture rtl of ADC_CONTROLLER is

signal left_temp_buf          : std_logic_vector(31 downto 0);
signal right_temp_buf          : std_logic_vector(31 downto 0);
signal left_index     : integer range 0 to 32;
signal right_index    : integer range 0 to 32;

signal left_done : std_logic;
signal right_done : std_logic;

begin

		process(AUD_BCLK)
		begin
		     if rising_edge(AUD_BCLK) then
			     if left_right_reset = '0' then
				    left_temp_buf <=  (others => '0');
					right_temp_buf <= (others => '0');
			 
			      elsif AUD_ADCLRCLK = '0' then        --- left channel
				    left_temp_buf(31 - left_index) <= AUD_ADCDAT;
                    left_index <= left_index + 1;
				      if left_index = 17 and left_full = '0' then
					     left_ready <= '1';
					  elsif left_index = 31 then
					         left_index <= 0;
					  else
					     left_ready <= '0';
					   end if;
					right_index <= 0;
					right_ready <= '0';

                  elsif	AUD_ADCLRCLK = '1' then        ---- right channel
                    right_temp_buf(31 - right_index) <= AUD_ADCDAT;
                    right_index <= right_index + 1;
                     if right_index = 17 and right_full = '0' then
                        right_ready <= '1';
                     elsif right_index = 31 then
					         right_index <= 0;
					else
					    right_ready <='0';
                     end if;
 					left_index <= 0;
                    left_ready <= '0';					
                end if;					
		      end if;
		end process;
		
        channel_left  <= left_temp_buf(30 downto 15); 
		  channel_right <= right_temp_buf(30 downto 15); 
		  
		  --channel_left  <= x"FF90";
		  --channel_right <= x"004B";
		  
		  fifo_bclk <= not(AUD_BCLK);
	 
end architecture;



