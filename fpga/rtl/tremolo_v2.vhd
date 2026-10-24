library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity tremolo_v2 is
port(

      clk  : in std_logic;   -- system clock (v2 B1)
      en_rise  : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
      en_fall  : in std_logic;   -- strobe: v1 falling edge
		tremolo_enable : in std_logic;
		
		t_wave			: in std_logic_vector(15 downto 0);
		t_depth			: in std_logic_vector(15 downto 0);
		
      data_in       : in std_logic_vector(15 downto 0);
      
      data_out      : out std_logic_vector(15 downto 0) := (others => '0')   -- power-up 0 (sim: no X before the first strobe)
     );
end entity;


architecture rtl of tremolo_v2 is


COMPONENT sine_5hz IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (13 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (7 DOWNTO 0)
	);
END COMPONENT;

COMPONENT sine_7hz IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (12 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (7 DOWNTO 0)
	);
END COMPONENT;

COMPONENT my_sin_10hz IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (12 DOWNTO 0);
		clock		   : IN STD_LOGIC  := '1';
		q		      : OUT STD_LOGIC_VECTOR (7 DOWNTO 0)
	);
END COMPONENT;

COMPONENT sine_12hz IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (11 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (7 DOWNTO 0)
	);
END COMPONENT;

COMPONENT sine_15hz IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (11 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (7 DOWNTO 0)
	);
END COMPONENT;


COMPONENT triangle_5hz IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (13 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (7 DOWNTO 0)
	);
END COMPONENT;


COMPONENT triangle_10hz IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (12 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (7 DOWNTO 0)
	);
END COMPONENT;

COMPONENT saw_10hz IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (12 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (7 DOWNTO 0)
	);
END COMPONENT;


signal counter_7hz   : integer range 0 to 6856 := 0;   -- sine_7hz_8bit.mif : 6857 entries
signal addr_7hz      : std_logic_vector(12 downto 0);

signal counter_5hz   : integer range 0 to 9599 := 0;   -- *_5hz_8bit.mif    : 9600 entries
signal addr_5hz      : std_logic_vector(13 downto 0);

signal counter_10hz   : integer range 0 to 4799 := 0;  -- *_10hz mif        : 4800 entries
signal addr_10hz      : std_logic_vector(12 downto 0);

signal counter_12hz   : integer range 0 to 3999 := 0;  -- sine_12hz_8bit.mif : 4000 entries
signal addr_12hz      : std_logic_vector(11 downto 0);

signal counter_15hz   : integer range 0 to 3199 := 0;  -- sine_15hz_8bit.mif : 3200 entries
signal addr_15hz      : std_logic_vector(11 downto 0);



signal temp_sine : std_logic_vector(7 downto 0);

signal temp_sine_5hz : std_logic_vector(7 downto 0);
signal temp_sine_7hz : std_logic_vector(7 downto 0);
signal temp_sine_10hz : std_logic_vector(7 downto 0);
signal temp_sine_12hz : std_logic_vector(7 downto 0);
signal temp_sine_15hz : std_logic_vector(7 downto 0);

signal temp_triangle_5hz : std_logic_vector(7 downto 0);
signal temp_triangle_10hz : std_logic_vector(7 downto 0);

signal temp_saw_10hz : std_logic_vector(7 downto 0);

signal result    : std_logic_vector(31 downto 0);

-- LFO value after smoothing, 8 fractional bits (0 .. 255*256)
signal lfo_s     : integer range 0 to 65535 := 0;

signal temp_depth   : std_logic_vector(7 downto 0);
signal invert_depth : std_logic_vector(7 downto 0);
signal int_depth   : integer := 0;

signal out_dat : std_logic_vector(23 downto 0); 

signal temp  : integer := 0;
signal sine  : integer range 0 to 255;
signal data  : integer := 0;

signal a,b,c : integer := 0;

signal wave_sel : std_logic_vector(2 downto 0);
signal en_5hz  : std_logic;
signal en_7hz  : std_logic;
signal en_10hz  : std_logic;
signal en_12hz  : std_logic;
signal en_15hz  : std_logic;

begin


	addr_5hz <= std_logic_vector(to_unsigned(counter_5hz, addr_5hz'length));
	addr_7hz <= std_logic_vector(to_unsigned(counter_7hz, addr_7hz'length));
	
	addr_10hz <= std_logic_vector(to_unsigned(counter_10hz, addr_10hz'length));
	addr_12hz <= std_logic_vector(to_unsigned(counter_12hz, addr_12hz'length));
	addr_15hz <= std_logic_vector(to_unsigned(counter_15hz, addr_15hz'length));

cyclic_counter_5hz : process(clk)
                     begin
								if rising_edge(clk) and en_rise = '1' and en_5hz = '1' then
									if counter_5hz >= 9599 then
										counter_5hz <= 0;
									else
										counter_5hz <= counter_5hz + 1;
									end if;
							end if;					  
							end process;
							
cyclic_counter_7hz : process(clk)
                     begin
								if rising_edge(clk) and en_rise = '1' and en_7hz = '1' then
									if counter_7hz >= 6856 then
										counter_7hz <= 0;
									else
										counter_7hz <= counter_7hz + 1;
									end if;
							end if;					  
							end process;
							
cyclic_counter_10hz : process(clk)
                     begin
								if rising_edge(clk) and en_rise = '1' and en_10hz = '1' then
									if counter_10hz >= 4799 then
										counter_10hz <= 0;
									else
										counter_10hz <= counter_10hz + 1;
									end if;
							end if;					  
							end process;
							
cyclic_counter_12hz : process(clk)
                     begin
								if rising_edge(clk) and en_rise = '1' and en_12hz = '1' then
									if counter_12hz >= 3999 then
										counter_12hz <= 0;
									else
										counter_12hz <= counter_12hz + 1;
									end if;
							end if;					  
							end process;							

cyclic_counter_15hz : process(clk)
                     begin
								if rising_edge(clk) and en_rise = '1' and en_15hz = '1' then
									if counter_15hz >= 3199 then
										counter_15hz <= 0;
									else
										counter_15hz <= counter_15hz + 1;
									end if;
							end if;					  
							end process;							
                 
					  sine <= to_integer(unsigned(temp_sine));
					  data <= to_integer(signed(data_in));

					  -- One-pole smoothing of the LFO (time constant 32 samples, ~0.7 ms):
					  -- removes the click of hard-edged waveforms (sawtooth reset) and the
					  -- zipper steps of the 8-bit tables without reducing the depth of the
					  -- 5..15 Hz LFOs.
					  lfo_smooth : process(clk)
					  begin
						if rising_edge(clk) and en_rise = '1' then
							lfo_s <= lfo_s + (sine * 256 - lfo_s) / 32;
						end if;
					  end process;

					  process(clk)
					  begin
					   if rising_edge(clk) then
							  temp   <= data * lfo_s;     -- |data| * 65280 < 2^31
						end if;
					  end process;


					  result <= std_logic_vector(to_signed(temp, result'length));
					  
					  
					  temp_depth   <= t_depth(7 downto 0);
					  invert_depth <= std_logic_vector(255 - unsigned(temp_depth));
					  int_depth    <= to_integer(unsigned(temp_depth));
					  
					  a <= int_depth * to_integer(signed(result(31 downto 16)));   -- data * lfo / 65536
					  b <= to_integer(unsigned(invert_depth)) * data;
					  c <= a + b;
					  
					  out_dat <= std_logic_vector(to_signed(c, out_dat'length)); -- was unsigned
					  
					   process(clk)
						begin
							if rising_edge(clk) and en_rise = '1' then
								if(tremolo_enable = '1') then
									data_out <= out_dat(23 downto 8); --- divide by 256
								else
									data_out <= data_in;
							end if;
						end if;
					end process;
					  

ROM_5hz :  sine_5hz port map(
                     address => addr_5hz,
							clock   => clk,
							q       => temp_sine_5hz
                           );
									
ROM_7hz :  sine_7hz port map(
                     address => addr_7hz,
							clock   => clk,
							q       => temp_sine_7hz
                           );
									
ROM_10hz :  my_sin_10hz port map(
                     address => addr_10hz,
							clock   => clk,
							q       => temp_sine_10hz
                           );
								
ROM_12hz :  sine_12hz port map(
                     address => addr_12hz,
							clock   => clk,
							q       => temp_sine_12hz
                           );
									
ROM_15hz :  sine_15hz port map(
                     address => addr_15hz,
							clock   => clk,
							q       => temp_sine_15hz
                           );	
									
									
ROM_T_5hz :	  triangle_5hz port map(
                     address => addr_5hz,
							clock   => clk,
							q       => temp_triangle_5hz
                           );									
									
ROM_T_10hz :	triangle_10hz port map(
                     address => addr_10hz,
							clock   => clk,
							q       => temp_triangle_10hz
                           );	

ROM_SAW_10hz :	saw_10hz port map(
                     address => addr_10hz,
							clock   => clk,
							q       => temp_saw_10hz
                           );									
									
									
					wave_sel <= t_wave(2 downto 0);
					
					process(clk)
					begin
					 if rising_edge(clk) and en_rise = '1' then
						case wave_sel is
							when "000" 	=>  en_5hz  <= '1';
												 en_7hz  <= '0';
												 en_10hz  <= '0';
												 en_12hz <= '0';
												 en_15hz <= '0';
												 temp_sine <= temp_sine_5hz;
												 
							when "001" 	=>  en_5hz  <= '0';
												 en_7hz  <= '1';
												 en_10hz  <= '0';
												 en_12hz <= '0';
												 en_15hz <= '0';
												 temp_sine <= temp_sine_7hz;
												 
							when "010" 	=>  en_5hz  <= '0';
												 en_7hz  <= '0';
												 en_10hz  <= '1';
												 en_12hz <= '0';
												 en_15hz <= '0';
												 temp_sine<= temp_sine_10hz;

							when "011" 	=>  en_5hz  <= '0';
												 en_7hz  <= '0';
												 en_10hz  <= '0';
												 en_12hz <= '1';
												 en_15hz <= '0';
												 temp_sine<= temp_sine_12hz;

							when "100" 	=>  en_5hz  <= '0';
												 en_7hz  <= '0';
												 en_10hz  <= '0';
												 en_12hz <= '0';
												 en_15hz <= '1';
												 temp_sine <= temp_sine_15hz;
												 
							when "101" 	=>  en_5hz  <= '1';
												 en_7hz  <= '0';
												 en_10hz  <= '0';
												 en_12hz <= '0';
												 en_15hz <= '0';
												 temp_sine <= temp_triangle_5hz;
												 
							when "110" 	=>  en_5hz  <= '0';
												 en_7hz  <= '0';
												 en_10hz  <= '1';
												 en_12hz <= '0';
												 en_15hz <= '0';
												 temp_sine <= temp_triangle_10hz;

							when "111" 	=>  en_5hz  <= '0';
												 en_7hz  <= '0';
												 en_10hz  <= '1';
												 en_12hz <= '0';
												 en_15hz <= '0';
												 temp_sine <= temp_saw_10hz;												 
												 
							when others =>  en_5hz  <= '1';
												 en_7hz  <= '0';
												 en_10hz  <= '0';
												 en_12hz <= '0';
												 en_15hz <= '0';	
												 temp_sine <= temp_sine_5hz;
						end case;
					 end if;
					end process;

end architecture;





