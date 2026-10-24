
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity FX_chain is
port(

      clk           : in std_logic;   -- system clock (49.152 MHz in v2)
      sample_tick   : in std_logic;   -- 1-cycle strobe per frame (v1: LRCLK rising)
      half_tick     : in std_logic;   -- 1-cycle strobe half a frame later (v1: LRCLK falling)
		od_enable       : in std_logic;
		tremolo_enable  : in std_logic;
		echo_enable   : in std_logic;
		
		
		effects_enable 	: in std_logic_vector(15 downto 0);
		od_drive				: in std_logic_vector(15 downto 0);
		od_gain				: in std_logic_vector(15 downto 0);
		trem_depth			: in std_logic_vector(15 downto 0);
		trem_wave			: in std_logic_vector(15 downto 0);
		echo_time			: in std_logic_vector(15 downto 0);
		echo_level			: in std_logic_vector(15 downto 0);
		echo_repeat			: in std_logic_vector(15 downto 0);
		
		chorus_rate       : in std_logic_vector(15 downto 0);
		chorus_level      : in std_logic_vector(15 downto 0);
		chorus_depth      : in std_logic_vector(15 downto 0);
		dist_mix          : in std_logic_vector(15 downto 0);
		dist_type         : in std_logic_vector(15 downto 0);
		reverb_type       : in std_logic_vector(15 downto 0);
		reverb_mix        : in std_logic_vector(15 downto 0);
		
		data_in_left  : in std_logic_vector(15 downto 0);
		data_in_right : in std_logic_vector(15 downto 0);
		
		data_out_left  : out std_logic_vector(15 downto 0);
		data_out_right : out std_logic_vector(15 downto 0)
);
end entity;

architecture rtl of FX_chain is

component distortion is
port(

      clk  : in std_logic;
      en_rise  : in std_logic;
      en_fall  : in std_logic;
		dist_enable     : in std_logic;
		
		mix      : in std_logic_vector(15 downto 0); 
		d_type   : in std_logic_vector(15 downto 0); 
		
      data_in       : in std_logic_vector(15 downto 0);
      
      data_out      : out std_logic_vector(15 downto 0)
     );
end component;

component tremolo_top is
port(

      clk  : in std_logic;
      en_rise  : in std_logic;
      en_fall  : in std_logic;
		tremolo_enable : in std_logic;
		t_wave			: in std_logic_vector(15 downto 0);
		t_depth			: in std_logic_vector(15 downto 0);
      data_in       : in std_logic_vector(15 downto 0);
      
      data_out      : out std_logic_vector(15 downto 0)
     );
end component;

component overdrive is
port(

      clk  : in std_logic;
      en_rise  : in std_logic;
      en_fall  : in std_logic;
		od_enable     : in std_logic;
		
		drive     : in std_logic_vector(15 downto 0); 
		gain      : in std_logic_vector(15 downto 0); 
		
      data_in       : in std_logic_vector(15 downto 0);
      
      data_out      : out std_logic_vector(15 downto 0)
     );
end component;

component echo is
port(
		clk  : in std_logic;
		en_rise  : in std_logic;
		en_fall  : in std_logic;
		echo_enable   : in std_logic; 
		e_time			: in std_logic_vector(15 downto 0);
      e_level			: in std_logic_vector(15 downto 0);	
		e_repeat			: in std_logic_vector(15 downto 0);	
		data_in       : in std_logic_vector(15 downto 0);
		
		data_out       : out std_logic_vector(15 downto 0)
);
end component;

component chorus is
port(
		clk  : in std_logic;
		en_rise  : in std_logic;
		en_fall  : in std_logic;
		chorus_enable   : in std_logic;
		gain          : in std_logic_vector(15 downto 0);
		chorus_rate   : in std_logic_vector(15 downto 0);
		chorus_depth  : in std_logic_vector(15 downto 0);
		data_in       : in std_logic_vector(15 downto 0);
		data_out       : out std_logic_vector(15 downto 0)
	 );
end component;

component reverbe is
port(
      clk    : in std_logic;
      en_rise    : in std_logic;
      en_fall    : in std_logic;
      data_in         : in std_logic_vector(15 downto 0);
		reverb_mix      : in std_logic_vector(15 downto 0);
	 	reverb_type     : in std_logic_vector(15 downto 0);
		reverbe_enable  : in std_logic;	
      data_out        : out std_logic_vector(15 downto 0)
     );
end component;


component tremolo_v2 is
port(

      clk   : in std_logic;
      en_rise   : in std_logic;
      en_fall   : in std_logic;
		tremolo_enable : in std_logic;
		
		t_wave			: in std_logic_vector(15 downto 0);
		t_depth			: in std_logic_vector(15 downto 0);
		
      data_in       : in std_logic_vector(15 downto 0);   
      data_out      : out std_logic_vector(15 downto 0)
     );
end component;


signal tremolout_delayin_left  : std_logic_vector(15 downto 0);
signal tremolout_delayin_right : std_logic_vector(15 downto 0);

signal odout_tremolin_left  : std_logic_vector(15 downto 0);
signal odout_tremolin_right : std_logic_vector(15 downto 0);


signal odOUT_distIN  : std_logic_vector(15 downto 0);
signal distOUT_chorusIN  : std_logic_vector(15 downto 0);
signal chorusOUT_tremIN  : std_logic_vector(15 downto 0);
signal tremOUT_echoIN  : std_logic_vector(15 downto 0);
signal echoOUT_reverbIN  : std_logic_vector(15 downto 0);

begin

					
					
OD_left : overdrive port map(
									clk          => clk,
									en_rise      => sample_tick,   -- v1: LRCLK rising
									en_fall      => half_tick,
									od_enable    => effects_enable(0),
									drive 		 => od_drive,
									gain 		 => od_gain,
									data_in      => data_in_left,
									data_out     => odOUT_distIN
									  );
									  
dist_left : distortion port map(
									clk          => clk,
									en_rise      => sample_tick,   -- v1: LRCLK rising
									en_fall      => half_tick,
									dist_enable  => effects_enable(3),
									mix			 => dist_mix,
									d_type       => dist_type,
									data_in      => odOUT_distIN,
									data_out     => distOUT_chorusIN
									  );									  
CHORUS_left  : chorus port map(
									clk          => clk,
									en_rise      => half_tick,     -- v1: not(LRCLK) rising = LRCLK falling
									en_fall      => sample_tick,
									chorus_enable   => effects_enable(4),
									gain            => chorus_level,
									chorus_rate     => chorus_rate,
								   chorus_depth    => chorus_depth,	
									data_in			=> distOUT_chorusIN,
									data_out        => chorusOUT_tremIN							
										); 
										
TREMOLO_left :   tremolo_v2 port map(
									clk          => clk,
									en_rise      => half_tick,     -- v1: not(LRCLK) rising = LRCLK falling
									en_fall      => sample_tick,
									tremolo_enable => effects_enable(1),
									t_wave		   => trem_wave,
									t_depth		   => trem_depth,
									data_in        => chorusOUT_tremIN,
									data_out       => tremOUT_echoIN
										  );
										  
ECHO_left  :    echo port map(
									clk          => clk,
									en_rise      => half_tick,     -- v1: not(LRCLK) rising = LRCLK falling
									en_fall      => sample_tick,
									echo_enable    => effects_enable(2),
									e_time 		   => echo_time,
									e_level        => echo_level,
									e_repeat			=> echo_repeat,
									data_in		   => tremOUT_echoIN,
									data_out       => echoOUT_reverbIN							
										);
										  
REVERB_left  : 	reverbe port map(
							clk          => clk,
							en_rise      => half_tick,     -- v1: not(LRCLK) rising = LRCLK falling
							en_fall      => sample_tick,
							data_in         => echoOUT_reverbIN,
							reverb_mix      => reverb_mix,
							reverb_type     => reverb_type,
							reverbe_enable  => effects_enable(5),	
							data_out        => data_out_left
									  	 );
										  



										
										
							

end architecture;

