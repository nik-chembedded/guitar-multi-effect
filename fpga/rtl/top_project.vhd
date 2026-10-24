

library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity top_project is
port(
      clk     : in std_logic;
		LR_RESET : in std_logic;
		reset_n : in std_logic;
		i2c_scl : out std_logic;
      i2c_sda : inout std_logic;
		 	
		od_enable       : in std_logic;
		tremolo_enable  : in std_logic;
		echo_enable   : in std_logic;
		
		AUD_BCLK     : in std_logic;
		
		AUD_ADCDAT   : in std_logic;
		AUD_ADCLRCLK : in std_logic;
		
		AUD_DACLRCLK : in std_logic;		
      AUD_DACDAT   : out std_logic;
		
		
		UART_RX      : in std_logic;
		UART_TX      : out std_logic;
		
		sdram_addr                 : out   std_logic_vector(12 downto 0);                    --                  r_sdram.addr
		sdram_ba                   : out   std_logic_vector(1 downto 0);                     --                         .ba
		sdram_cas_n                : out   std_logic;                                        --                         .cas_n
		sdram_cke                  : out   std_logic;                                        --                         .cke
		sdram_cs_n                 : out   std_logic;                                        --                         .cs_n
		sdram_dq                   : inout std_logic_vector(15 downto 0) := (others => '0'); --                         .dq
		sdram_dqm                  : out   std_logic_vector(1 downto 0);                     --                         .dqm
		sdram_ras_n                : out   std_logic;                                        --                         .ras_n
		sdram_we_n                 : out   std_logic; 

		sdram_clk                  : out   std_logic; 
		
		aud_xck : out std_logic
	 );
end entity;

architecture rtl of top_project is

component my_audio is
	port (
		aud_xck_clk                  : out   std_logic;                                        --                  aud_xck.clk
		clk_clk                      : in    std_logic                     := '0';             --                      clk.clk
		i2c_scl_export               : out   std_logic;                                        --                  i2c_scl.export
		i2s_sda_export               : inout std_logic                     := '0';             --                  i2s_sda.export
		r_chorus_depth_export        : out   std_logic_vector(15 downto 0);                    --           r_chorus_depth.export
		r_chorus_level_export        : out   std_logic_vector(15 downto 0);                    --           r_chorus_level.export
		r_chorus_rate_export         : out   std_logic_vector(15 downto 0);                    --            r_chorus_rate.export
		r_dist_mix_export            : out   std_logic_vector(15 downto 0);                    --               r_dist_mix.export
		r_dist_type_export           : out   std_logic_vector(15 downto 0);                    --              r_dist_type.export
		r_echo_level_export          : out   std_logic_vector(15 downto 0);                    --             r_echo_level.export
		r_echo_repeat_export         : out   std_logic_vector(15 downto 0);                    --            r_echo_repeat.export
		r_echo_time_export           : out   std_logic_vector(15 downto 0);                    --              r_echo_time.export
		r_effects_enable_export      : out   std_logic_vector(15 downto 0);                    --         r_effects_enable.export
		r_od_drive_export            : out   std_logic_vector(15 downto 0);                    --               r_od_drive.export
		r_od_gain_export             : out   std_logic_vector(15 downto 0);                    --                r_od_gain.export
		r_reverb_mix_export          : out   std_logic_vector(15 downto 0);                    --             r_reverb_mix.export
		r_reverb_type_export         : out   std_logic_vector(15 downto 0);                    --            r_reverb_type.export
		r_sdram_addr                 : out   std_logic_vector(12 downto 0);                    --                  r_sdram.addr
		r_sdram_ba                   : out   std_logic_vector(1 downto 0);                     --                         .ba
		r_sdram_cas_n                : out   std_logic;                                        --                         .cas_n
		r_sdram_cke                  : out   std_logic;                                        --                         .cke
		r_sdram_cs_n                 : out   std_logic;                                        --                         .cs_n
		r_sdram_dq                   : inout std_logic_vector(15 downto 0) := (others => '0'); --                         .dq
		r_sdram_dqm                  : out   std_logic_vector(1 downto 0);                     --                         .dqm
		r_sdram_ras_n                : out   std_logic;                                        --                         .ras_n
		r_sdram_we_n                 : out   std_logic;                                        --                         .we_n
		r_trem_depth_export          : out   std_logic_vector(15 downto 0);                    --             r_trem_depth.export
		r_trem_wave_export           : out   std_logic_vector(15 downto 0);                    --              r_trem_wave.export
		reset_reset_n                : in    std_logic                     := '0'; 
		sdram_clk_clk                : out   std_logic; 		--                    reset.reset_n
		uart_external_connection_rxd : in    std_logic                     := '0';             -- uart_external_connection.rxd
		uart_external_connection_txd : out   std_logic                                         --                         .txd
	);
end component;

component audio_processor is
port(
      clk_18Mhz    : in std_logic;
		AUD_BCLK     : in std_logic;
		
		AUD_ADCDAT   : in std_logic;
		AUD_ADCLRCLK : in std_logic;
		
		L_R_RESET    : in std_logic;
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
		
		AUD_DACLRCLK : in std_logic;		
      AUD_DACDAT   : out std_logic
     );
end component;

signal codec_clock 	: std_logic;
signal odgain      	: std_logic_vector(15 downto 0);
signal oddrive     	: std_logic_vector(15 downto 0);
signal tremdepth  	: std_logic_vector(15 downto 0);
signal tremwave   	: std_logic_vector(15 downto 0);
signal echolevel   	: std_logic_vector(15 downto 0);
signal echorepeat  	: std_logic_vector(15 downto 0);
signal echotime  	   : std_logic_vector(15 downto 0);
signal effectsenable : std_logic_vector(15 downto 0);

signal choruslevel  	: std_logic_vector(15 downto 0);
signal chorusdepth  	: std_logic_vector(15 downto 0);
signal chorusrate    : std_logic_vector(15 downto 0);

signal distmix  	   : std_logic_vector(15 downto 0);
signal disttype  	   : std_logic_vector(15 downto 0);

signal reverbmix  	: std_logic_vector(15 downto 0);
signal reverbtype  	: std_logic_vector(15 downto 0);


begin

     aud_xck <= codec_clock;


nios     : my_audio port map(
                aud_xck_clk    => codec_clock,
                clk_clk        => clk,				 
                i2c_scl_export => i2c_scl,
                i2s_sda_export => i2c_sda,
					 reset_reset_n  => reset_n,
					 
					 r_echo_level_export        => echolevel,	
					 r_echo_repeat_export       => echorepeat,
					 r_echo_time_export         => echotime,
				    r_effects_enable_export    => effectsenable,
					 r_od_drive_export          => oddrive,
					 r_od_gain_export           => odgain,
					 r_trem_depth_export        => tremdepth,
					 r_trem_wave_export         => tremwave,
					 
					 r_chorus_depth_export      => chorusdepth,
					 r_chorus_level_export      => choruslevel,
					 r_chorus_rate_export       => chorusrate,
					 r_dist_mix_export          => distmix,
					 r_dist_type_export         => disttype,
					 r_reverb_mix_export        => reverbmix,
					 r_reverb_type_export       => reverbtype,
					 
					 r_sdram_addr               => sdram_addr,
					 r_sdram_ba                 => sdram_ba,                   
		          r_sdram_cas_n              => sdram_cas_n,                                       
				    r_sdram_cke                => sdram_cke,                                       
					 r_sdram_cs_n               => sdram_cs_n,                                       
					 r_sdram_dq                 => sdram_dq,
					 r_sdram_dqm                => sdram_dqm,                   
					 r_sdram_ras_n              => sdram_ras_n,                                      
					 r_sdram_we_n               => sdram_we_n,
					 
					 sdram_clk_clk => sdram_clk,
					  
					 uart_external_connection_rxd => UART_RX,
					 uart_external_connection_txd => UART_TX
					        );

aud_proc : audio_processor port map(
                     clk_18Mhz => codec_clock,
							L_R_RESET => LR_RESET,
							od_enable => od_enable,
							tremolo_enable => tremolo_enable,
							echo_enable   => echo_enable,
							
							effects_enable => effectsenable,
							od_drive       => oddrive,
							od_gain			=>	odgain,
							trem_depth		=> tremdepth,
							trem_wave		=> tremwave,
							echo_time		=> echotime,
							echo_level		=> echolevel,
							echo_repeat		=> echorepeat,
							
							chorus_rate       => chorusrate,
							chorus_level      => choruslevel,
							chorus_depth      => chorusdepth,
							dist_mix          => distmix,
							dist_type         => disttype,
							reverb_type       => reverbtype,
							reverb_mix        => reverbmix,
							
							AUD_BCLK  => AUD_BCLK,
							AUD_ADCDAT => AUD_ADCDAT,
							AUD_ADCLRCLK => AUD_ADCLRCLK,
							AUD_DACLRCLK => AUD_DACLRCLK,
							AUD_DACDAT => AUD_DACDAT
							);					  
end architecture;

