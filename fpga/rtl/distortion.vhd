


library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity distortion is
port(

      AUD_DACLRCLK  : in std_logic;
		CLK_18MHZ     : in std_logic;
		dist_enable     : in std_logic;
		
		--drive     : in std_logic_vector(15 downto 0); 
		mix      : in std_logic_vector(15 downto 0);
		d_type   : in std_logic_vector(15 downto 0); 
		
      data_in       : in std_logic_vector(15 downto 0);
      
      data_out      : out std_logic_vector(15 downto 0)
     );
end entity;


architecture rtl of distortion is


COMPONENT dist_ROM IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (14 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;

COMPONENT dist_ROM_soft IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (13 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		rden		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;

COMPONENT dist_ROM_medium IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (13 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		rden		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;

COMPONENT dist_ROM_hard IS
	PORT
	(
		address		: IN STD_LOGIC_VECTOR (13 DOWNTO 0);
		clock		: IN STD_LOGIC  := '1';
		rden		: IN STD_LOGIC  := '1';
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0)
	);
END COMPONENT;


	signal data_temp : std_logic_vector(15 downto 0);
	signal temp_int  : integer;
	signal data_to_addr  : integer;
	signal d_addr  : std_logic_vector(13 downto 0);
	
	signal temp_depth   : std_logic_vector(7 downto 0);
   signal invert_depth : std_logic_vector(7 downto 0);
   signal int_depth    : integer;

	signal a : integer;
	signal b : integer;
	signal c : integer;
	
	signal out_dat : std_logic_vector(23 downto 0); 
	
	signal soft_en : std_logic;
	signal med_en  : std_logic;
	signal hard_en : std_logic;
	signal soft_out_temp : std_logic_vector(15 downto 0);
	signal med_out_temp  : std_logic_vector(15 downto 0);
	signal hard_out_temp : std_logic_vector(15 downto 0);
	signal temp_type    : std_logic_vector(1 downto 0);
	
	signal temp_data_sign : std_logic_vector(15 downto 0); 
	signal temp_int_sign  : integer;
	signal int_sign      :  integer;
	
begin



			
			temp_int <= to_integer(signed(data_in));
			
			process(AUD_DACLRCLK)
			begin
				if rising_edge(AUD_DACLRCLK) then
					if temp_int < 0 then
						data_to_addr <= (-1) * temp_int;
					else
						data_to_addr <= temp_int;
				end if;
			 end if;
			end process;
			
			d_addr <= std_logic_vector(to_unsigned(data_to_addr, d_addr'length));

--ROM   : dist_ROM port map(
--							address => d_addr,
--							clock   => CLK_18MHZ,
--							q       => data_temp
--								);
								
ROM_soft : dist_ROM_soft port map(
							address => d_addr,
							rden    => soft_en,
							clock   => CLK_18MHZ,
							q       => soft_out_temp
								);
ROM_med  : dist_ROM_medium port map(
							address => d_addr,
							rden    => med_en,
							clock   => CLK_18MHZ,
							q       => med_out_temp
								);
ROM_hard : dist_ROM_hard port map(
							address => d_addr,
							rden    => hard_en,
							clock   => CLK_18MHZ,
							q       => hard_out_temp
								);
								
			temp_type <= d_type(1 downto 0);
			process(temp_type)
			begin
			case (temp_type) is
			when "00"   => data_temp <= soft_out_temp;
								soft_en   <= '1';
								med_en    <= '0';
								hard_en   <= '0';
			when "01"   => data_temp <= med_out_temp;
								soft_en   <= '0';
								med_en    <= '1';
								hard_en   <= '0';
			when "10"   => data_temp <= hard_out_temp;
								soft_en   <= '0';
								med_en    <= '0';
								hard_en   <= '1';
			when "11"   => data_temp <= soft_out_temp;
								soft_en   <= '1';
								med_en    <= '0';
								hard_en   <= '0';
			when others => data_temp <= soft_out_temp;
								soft_en   <= '1';
								med_en    <= '0';
								hard_en   <= '0';
			end case;
			end process;
			
			
--										temp_int_sign <= to_integer(unsigned(data_temp));
--										
--determine_sign_proc :			process(AUD_DACLRCLK)
--										begin
--											if rising_edge(AUD_DACLRCLK) then
--												if temp_int >= 0 then
--												  int_sign <= temp_int_sign;	
--												else
--												  int_sign <= (-1) * temp_int_sign;	
--												end if;
--											end if;
--										end process;
--										temp_data_sign <= std_logic_vector(to_signed(int_sign, temp_data_sign'length));
								
			temp_depth   <= mix(7 downto 0);
			invert_depth <= std_logic_vector(255 - unsigned(temp_depth));
			int_depth    <= to_integer(unsigned(temp_depth));
			
			a <= int_depth * to_integer(signed(data_temp));
			b <= to_integer(unsigned(invert_depth)) * to_integer(signed(data_in));
			c <= a + b;
			
			out_dat <= std_logic_vector(to_signed(c, out_dat'length));
			
								

	process(AUD_DACLRCLK)
	 begin
		if rising_edge(AUD_DACLRCLK) then
			if(dist_enable = '1') then
				 data_out <= out_dat(23 downto 8);
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;
	
	
end rtl;