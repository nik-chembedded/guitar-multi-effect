-- -----------------------------------------------------------------------------
-- tremolo_v2.vhd
-- Amplitude modulation: out = mix(dry, dry * lfo, depth), with the generated
-- LFO (nco_lfo, step D1) smoothed by a one-pole filter (tau 32 samples) that
-- rounds the edges of the saw and square waves (no clicks).
--   t_wave bit 3 = 0: legacy presets (bits 2..0): 0..4 sine 5/7/10/12/15 Hz,
--                     5..6 triangle 5/10 Hz, 7 saw 10 Hz (the former ROM tables)
--   t_wave bit 3 = 1: free mode: bits 1..0 = shape (0 sine, 1 triangle, 2 saw,
--                     3 square), rate = t_rate in 0.01 Hz
-- DW-bit samples (step C). Python model: sim/cocotb/lfo_model.py.
-- -----------------------------------------------------------------------------
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity tremolo_v2 is
generic (
      DW : positive := 16                         -- sample width (16 or 24)
);
port(
      clk  : in std_logic;   -- system clock (v2 B1)
      en_rise  : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
      en_fall  : in std_logic;   -- strobe: v1 falling edge
      tremolo_enable : in std_logic;

      t_wave        : in std_logic_vector(15 downto 0);
      t_depth       : in std_logic_vector(15 downto 0);
      t_rate        : in std_logic_vector(15 downto 0);   -- free mode, 0.01 Hz

      data_in       : in std_logic_vector(DW - 1 downto 0);
      data_out      : out std_logic_vector(DW - 1 downto 0) := (others => '0')   -- power-up 0 (sim: no X before the first strobe)
     );
end entity;


architecture rtl of tremolo_v2 is

  signal shape     : std_logic_vector(1 downto 0);
  signal rate      : std_logic_vector(15 downto 0);
  signal lfo       : std_logic_vector(15 downto 0);
  -- LFO after smoothing (0 .. 65535)
  signal lfo_s     : integer range 0 to 65535 := 0;
  signal modulated : signed(DW - 1 downto 0) := (others => '0');   -- data * lfo / 65536
  signal out_dat   : signed(DW - 1 downto 0);

begin

  -- waveform register -> LFO shape and rate
  process(t_wave, t_rate)
  begin
    if t_wave(3) = '1' then
      shape <= t_wave(1 downto 0);
      rate  <= t_rate;
    else
      case t_wave(2 downto 0) is
        when "000"  => shape <= "00"; rate <= std_logic_vector(to_unsigned(500, 16));
        when "001"  => shape <= "00"; rate <= std_logic_vector(to_unsigned(700, 16));
        when "010"  => shape <= "00"; rate <= std_logic_vector(to_unsigned(1000, 16));
        when "011"  => shape <= "00"; rate <= std_logic_vector(to_unsigned(1200, 16));
        when "100"  => shape <= "00"; rate <= std_logic_vector(to_unsigned(1500, 16));
        when "101"  => shape <= "01"; rate <= std_logic_vector(to_unsigned(500, 16));
        when "110"  => shape <= "01"; rate <= std_logic_vector(to_unsigned(1000, 16));
        when others => shape <= "10"; rate <= std_logic_vector(to_unsigned(1000, 16));
      end case;
    end if;
  end process;

  u_lfo : entity work.nco_lfo
    port map (clk => clk, tick => en_rise, rate => rate, shape => shape, lfo => lfo);

  -- One-pole smoothing of the LFO (time constant 32 samples, ~0.7 ms): rounds the
  -- hard edges of the saw and square waves without reducing the depth of the
  -- 0.01 .. 20 Hz LFO.
  lfo_smooth : process(clk)
  begin
    if rising_edge(clk) and en_rise = '1' then
      lfo_s <= lfo_s + (to_integer(unsigned(lfo)) - lfo_s) / 32;
    end if;
  end process;

  process(clk)
  begin
    if rising_edge(clk) then
      modulated <= resize(mul_shr(signed(data_in), to_unsigned(lfo_s, 16), 16), DW);
    end if;
  end process;

  out_dat <= mix8(signed(data_in), modulated, unsigned(t_depth(7 downto 0)));

  process(clk)
  begin
    if rising_edge(clk) and en_rise = '1' then
      if(tremolo_enable = '1') then
        data_out <= std_logic_vector(out_dat);
      else
        data_out <= data_in;
      end if;
    end if;
  end process;

end rtl;
