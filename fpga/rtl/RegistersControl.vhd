LIBRARY ieee;
USE ieee.std_logic_1164.all;
use ieee.numeric_std.all;


entity RegistersControl is
	port(
		signal avs_s1_clk 	 	: in std_logic;
		signal avs_s1_reset   	: in std_logic;
		signal avs_s1_address 	: in std_logic_vector(7 downto 0 );
		signal avs_s1_write   	: in std_logic;
		signal avs_s1_writedata : in std_logic_vector(15 downto 0);
		
		signal avs_s1_export_EFFECTS_ENABLE  : out std_logic_vector(15 downto 0);
		
		signal avs_s1_export_ECHO_LEVEL 	 : out std_logic_vector(15 downto 0);
		signal avs_s1_export_ECHO_REPEAT	 : out std_logic_vector(15 downto 0);
		signal avs_s1_export_ECHO_TIME		 : out std_logic_vector(15 downto 0);
		
		signal avs_s1_export_TREMOLO_DEPTH 	 : out std_logic_vector(15 downto 0);
		signal avs_s1_export_TREMOLO_WAVE 	 : out std_logic_vector(15 downto 0);
		
		signal avs_s1_export_DISTORTION_MIX  : out std_logic_vector(15 downto 0);
		signal avs_s1_export_DISTORTION_TYPE : out std_logic_vector(15 downto 0);
		
		signal avs_s1_export_REVERB_MIX      : out std_logic_vector(15 downto 0);
		signal avs_s1_export_REVERB_TYPE     : out std_logic_vector(15 downto 0);	

		signal avs_s1_export_CHORUS_LEVEL    : out std_logic_vector(15 downto 0);
		signal avs_s1_export_CHORUS_DEPTH    : out std_logic_vector(15 downto 0);
		signal avs_s1_export_CHORUS_RATE     : out std_logic_vector(15 downto 0);		
		
		signal avs_s1_export_OVERDRIVE_DRIVE : out std_logic_vector(15 downto 0);
		signal avs_s1_export_OVERDRIVE_GAIN  : out std_logic_vector(15 downto 0)
	);
end entity RegistersControl;	
	
	
architecture rtl of RegistersControl is

constant EFF_EN   : std_logic_vector := x"00";
constant D_DRIVE  : std_logic_vector := x"01";
constant D_GAIN   : std_logic_vector := x"02";
constant T_WAVE   : std_logic_vector := x"03";
constant T_DEPTH  : std_logic_vector := x"04";
constant E_TIME   : std_logic_vector := x"05";
constant E_REPEAT : std_logic_vector := x"06";
constant E_LEVEL  : std_logic_vector := x"07";

constant DIST_MIX      : std_logic_vector := x"08";
constant DIST_TYPE     : std_logic_vector := x"09";
constant CHORUS_LEVEL  : std_logic_vector := x"0A";
constant CHORUS_DEPTH  : std_logic_vector := x"0B";
constant CHORUS_RATE   : std_logic_vector := x"0C";
constant REVERB_MIX    : std_logic_vector := x"0D";
constant REVERB_TYPE   : std_logic_vector := x"0E";

begin


	process(avs_s1_clk)
	begin
		if rising_edge(avs_s1_clk) then
		
			if( (avs_s1_write ='1') and (avs_s1_address = EFF_EN) ) then
				avs_s1_export_EFFECTS_ENABLE <= avs_s1_writedata;
			
			elsif( (avs_s1_write ='1') and (avs_s1_address = D_DRIVE) ) then
				avs_s1_export_OVERDRIVE_DRIVE <= avs_s1_writedata;
				
			elsif( (avs_s1_write ='1') and (avs_s1_address = D_GAIN) ) then
				avs_s1_export_OVERDRIVE_GAIN <= avs_s1_writedata;				
			
			elsif( (avs_s1_write ='1') and (avs_s1_address = T_WAVE) ) then
				avs_s1_export_TREMOLO_WAVE <= avs_s1_writedata;				
			
			elsif( (avs_s1_write ='1') and (avs_s1_address = T_DEPTH) ) then
				avs_s1_export_TREMOLO_DEPTH <= avs_s1_writedata;				
			
			elsif( (avs_s1_write ='1') and (avs_s1_address = E_TIME) ) then
				avs_s1_export_ECHO_TIME <= avs_s1_writedata;				
			
			elsif( (avs_s1_write ='1') and (avs_s1_address = E_REPEAT) ) then
				avs_s1_export_ECHO_REPEAT <= avs_s1_writedata;				
			
			elsif( (avs_s1_write ='1') and (avs_s1_address = E_LEVEL) ) then
				avs_s1_export_ECHO_LEVEL <= avs_s1_writedata;

			elsif( (avs_s1_write ='1') and (avs_s1_address = DIST_MIX) ) then
				avs_s1_export_DISTORTION_MIX <= avs_s1_writedata;
			elsif( (avs_s1_write ='1') and (avs_s1_address = DIST_TYPE) ) then
				avs_s1_export_DISTORTION_TYPE <= avs_s1_writedata;

			elsif( (avs_s1_write ='1') and (avs_s1_address = CHORUS_LEVEL) ) then
				avs_s1_export_CHORUS_LEVEL <= avs_s1_writedata;
			elsif( (avs_s1_write ='1') and (avs_s1_address = CHORUS_DEPTH) ) then
				avs_s1_export_CHORUS_DEPTH <= avs_s1_writedata;
			elsif( (avs_s1_write ='1') and (avs_s1_address = CHORUS_RATE) ) then
				avs_s1_export_CHORUS_RATE <= avs_s1_writedata;
				
			elsif( (avs_s1_write ='1') and (avs_s1_address = REVERB_MIX) ) then
				avs_s1_export_REVERB_MIX <= avs_s1_writedata;
			elsif( (avs_s1_write ='1') and (avs_s1_address = REVERB_TYPE) ) then
				avs_s1_export_REVERB_TYPE <= avs_s1_writedata;				
				
			end if;			
		end if;
	
	
	end process;




end rtl;
 	
