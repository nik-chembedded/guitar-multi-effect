library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;

entity audio_processor is
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
end entity;
 
architecture rtl of audio_processor is


component FX_chain is
port(

      AUD_DACLRCLK  : in std_logic;
		CLK_18MHZ     : in std_logic;
		
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
end component;


component ADC_CONTROLLER is 
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
end component;

component AUDIO_DAC is
port(
			clk : in std_logic;
			reset : in std_logic;
			write : in std_logic;
			writedata : in std_logic_vector(31 downto 0);
			full : out std_logic;
			clear : in std_logic;
			daclrc : in std_logic;
			bclk : in std_logic;
			dacdat : out std_logic			
     );
end component;

component DAC_CONTROLLER is
port(
      AUD_BCLK      : in std_logic;
      AUD_DACLRCLK  : in std_logic;		

	  channel_left  : in std_logic_vector(15 downto 0);
	  channel_right : in std_logic_vector(15 downto 0);
	  
	  left_empty    : in std_logic;
	  right_empty   : in std_logic;
			
	  AUD_DACDAT    : out std_logic
     );
end component;

component my_fifo IS
	PORT
	(
		data		: IN STD_LOGIC_VECTOR (15 DOWNTO 0);
		rdclk		: IN STD_LOGIC ;
		rdreq		: IN STD_LOGIC ;
		wrclk		: IN STD_LOGIC ;
		wrreq		: IN STD_LOGIC ;
		q		: OUT STD_LOGIC_VECTOR (15 DOWNTO 0);
		rdempty		: OUT STD_LOGIC ;
		wrfull		: OUT STD_LOGIC 
	);
END component;

component overdrive is
port(

      AUD_DACLRCLK  : in std_logic;
		CLK_18MHZ     : in std_logic;
		od_enable     : in std_logic;
      data_in       : in std_logic_vector(15 downto 0);
      
      data_out      : out std_logic_vector(15 downto 0)
     );
end component;

component echo is
port(
		AUD_DACLRCLK  : in std_logic;
		echo_enable   : in std_logic;
		--delay_offset  : in std_logic_vector(7 downto 0); 
		data_in       : in std_logic_vector(15 downto 0);
		data_out       : out std_logic_vector(15 downto 0)
);
end component;

signal fifo_clock_write  : std_logic;
signal fifo_full_left    : std_logic;
signal fifo_full_right   : std_logic;
signal fifo_wreq_left    : std_logic;
signal fifo_wreq_right   : std_logic;

signal fifo_data_write_left  : std_logic_vector(15 downto 0);
signal fifo_data_write_right : std_logic_vector(15 downto 0);

signal fifo_data_read_left  : std_logic_vector(15 downto 0);
signal fifo_data_read_right : std_logic_vector(15 downto 0);

signal tremolo_data_left : std_logic_vector(15 downto 0);
signal tremolo_data_right : std_logic_vector(15 downto 0);

signal OD_data_left : std_logic_vector(15 downto 0);
signal OD_data_right : std_logic_vector(15 downto 0);

signal FX_data_left  : std_logic_vector(15 downto 0);
signal FX_data_right : std_logic_vector(15 downto 0);

signal read_left_sig     : std_logic;
signal read_right_sig    : std_logic;

signal t_data_out : std_logic_vector(15 downto 0);
 
begin


ADC_CONT : ADC_CONTROLLER port map(
                            AUD_BCLK         => AUD_BCLK,
							AUD_ADCDAT       => AUD_ADCDAT,
							AUD_ADCLRCLK     => AUD_ADCLRCLK,
		               fifo_bclk        => fifo_clock_write,
		               left_full        => fifo_full_left,
		               right_full       =>	fifo_full_right,
	                  left_right_reset =>	L_R_RESET,
	                  left_ready       =>	fifo_wreq_left,
							right_ready      =>	fifo_wreq_right,	
							channel_left     =>	fifo_data_write_left,
							channel_right    =>	fifo_data_write_right							
						  );

FIFO_LEFT : my_fifo port map(
						data    => fifo_data_write_left,
						rdclk	=> not(AUD_DACLRCLK),--(AUD_DACLRCLK),--not(AUD_DACLRCLK),
						rdreq	=> not(read_left_sig),
						wrclk	=> fifo_clock_write,
						wrreq	=> fifo_wreq_left,
						q		=> fifo_data_read_left,
						rdempty	=> read_left_sig,
					    wrfull	=> fifo_full_left
                    );
					
--FIFO_RIGHT : audio_fifo port map(
--						data    => fifo_data_write_right,
--						rdclk	=> AUD_DACLRCLK,
--						rdreq	=> not(read_right_sig),
--						wrclk	=> fifo_clock_write,
--						wrreq	=> fifo_wreq_right,
--						q		=> fifo_data_read_right,
--						rdempty	=> read_right_sig,
--					    wrfull	=> fifo_full_right
--                    );

--							process(AUD_DACLRCLK)
--							begin
--									if rising_edge(AUD_DACLRCLK) then
--										t_data_out <= FX_data_left;
--									end if;
--							end process;	


--t_dac     : AUDIO_DAC port map(
--									clk => AUD_DACLRCLK,
--									reset => '0',
--									write => '1',
--									writedata =>  FX_data_left & x"0000",
--									full => open,
--									clear => '0',
--									bclk => AUD_BCLK,
--									daclrc => AUD_DACLRCLK,
--									dacdat => AUD_DACDAT	
--										);

DAC_CONT  : DAC_CONTROLLER port map(
							AUD_BCLK      => AUD_BCLK,
							AUD_DACLRCLK  => AUD_DACLRCLK,	
							channel_left  => FX_data_left,--t_data_out,--FX_data_left,      ---fifo_data_read_left,
							channel_right => FX_data_left,--t_data_out,--FX_data_left,     --fifo_data_read_right,	  
							left_empty    => '0',
							right_empty   => '0',		
							AUD_DACDAT    => AUD_DACDAT
                            );


FX           : FX_chain port map(
								 AUD_DACLRCLK   => AUD_DACLRCLK,
								 CLK_18MHZ      => clk_18Mhz,
								 od_enable      => od_enable,
								 tremolo_enable => tremolo_enable,
								 echo_enable    => echo_enable,
								 
								 		
								effects_enable 	=> effects_enable,
								od_drive				=> od_drive,
								od_gain				=> od_gain,
								trem_depth			=> trem_depth,
								trem_wave			=> trem_wave,
								echo_time			=> echo_time,
								echo_level			=> echo_level,
								echo_repeat			=> echo_repeat,
								
								chorus_rate       => chorus_rate,
								chorus_level      => chorus_level,
								chorus_depth      => chorus_depth,
								dist_mix          => dist_mix,
								dist_type         => dist_type,
								reverb_type       => reverb_type,
								reverb_mix        => reverb_mix,
								 
								 data_in_left   => fifo_data_read_left,
								 data_in_right  => fifo_data_read_right,
								 
								 data_out_left  => FX_data_left,
								 data_out_right => FX_data_right
											);
						 
end architecture;



