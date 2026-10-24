-- -----------------------------------------------------------------------------
-- tb_fx_wav.vhd
--
-- Frame-level testbench: streams a recorded audio file through FX_chain.
--
-- Unlike tb_audio_processor (bit-accurate I2S + FIFO), this bench drives
-- FX_chain directly, one sample per LRCLK period, which makes it fast enough
-- for seconds of real guitar audio. The datapath only counts LRCLK edges, so
-- the sample-domain behaviour (LFO rates, delays) is the same as at 48 kHz;
-- CLK_18MHZ just needs a few cycles per LRCLK phase for the ROM lookups and
-- the tremolo multiplier.
--
-- Files (one signed 16-bit integer per line, 48 kHz mono):
--   IN_FILE   input samples   (sim/tools/wavconv.py to-txt)
--   OUT_FILE  output samples  (sim/tools/wavconv.py to-wav)
-- TAIL_FRAMES of silence are appended so echo/reverb tails are captured.
-- All effect registers are generics (same encoding as docs/register_map.md).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_fx_wav is
  generic (
    IN_FILE      : string  := "in.txt";
    OUT_FILE     : string  := "out.txt";
    TAIL_FRAMES  : natural := 24000;     -- 0.5 s
    CLK_PER_HALF : positive := 8;        -- CLK_18MHZ cycles per LRCLK half period

    EFFECTS      : natural := 0;         -- reg 0: bit0 OD, 1 TREM, 2 ECHO, 3 DIST, 4 CHORUS, 5 REVERB
    OD_DRIVE     : natural := 3000;      -- reg 1
    OD_GAIN      : natural := 3;         -- reg 2
    TREM_WAVE    : natural := 0;         -- reg 3
    TREM_DEPTH   : natural := 200;       -- reg 4
    ECHO_TIME    : natural := 14400;     -- reg 5  (300 ms)
    ECHO_REPEAT  : natural := 100;       -- reg 6
    ECHO_LEVEL   : natural := 26000;     -- reg 7
    DIST_MIX     : natural := 255;       -- reg 8
    DIST_TYPE    : natural := 1;         -- reg 9
    CHORUS_LEVEL : natural := 40000;     -- reg 10
    CHORUS_DEPTH : natural := 400;       -- reg 11
    CHORUS_RATE  : natural := 40;        -- reg 12
    REVERB_MIX   : natural := 100;       -- reg 13
    REVERB_TYPE  : natural := 2          -- reg 14
  );
end entity;

architecture sim of tb_fx_wav is

  constant CLK_PERIOD : time := 10 ns;

  function slv16(v : natural) return std_logic_vector is
  begin
    return std_logic_vector(to_unsigned(v, 16));
  end function;

  signal clk      : std_logic := '0';
  signal lrclk    : std_logic := '0';
  signal running  : boolean := true;
  signal data_in  : std_logic_vector(15 downto 0) := (others => '0');
  signal data_out : std_logic_vector(15 downto 0);
  signal unused_r : std_logic_vector(15 downto 0);

begin

  clk <= not clk after CLK_PERIOD / 2 when running else '0';

  dut : entity work.FX_chain
    port map (
      AUD_DACLRCLK   => lrclk,
      CLK_18MHZ      => clk,
      od_enable      => '0',
      tremolo_enable => '0',
      echo_enable    => '0',
      effects_enable => slv16(EFFECTS),
      od_drive       => slv16(OD_DRIVE),
      od_gain        => slv16(OD_GAIN),
      trem_depth     => slv16(TREM_DEPTH),
      trem_wave      => slv16(TREM_WAVE),
      echo_time      => slv16(ECHO_TIME),
      echo_level     => slv16(ECHO_LEVEL),
      echo_repeat    => slv16(ECHO_REPEAT),
      chorus_rate    => slv16(CHORUS_RATE),
      chorus_level   => slv16(CHORUS_LEVEL),
      chorus_depth   => slv16(CHORUS_DEPTH),
      dist_mix       => slv16(DIST_MIX),
      dist_type      => slv16(DIST_TYPE),
      reverb_type    => slv16(REVERB_TYPE),
      reverb_mix     => slv16(REVERB_MIX),
      data_in_left   => data_in,
      data_in_right  => (others => '0'),
      data_out_left  => data_out,
      data_out_right => unused_r
    );

  stream : process
    file     fin, fout : text;
    variable lin, lout : line;
    variable s         : integer;
    variable n, n_x    : natural := 0;
    variable tail      : natural := 0;
    variable done_in   : boolean := false;
  begin
    file_open(fin, IN_FILE, read_mode);
    file_open(fout, OUT_FILE, write_mode);

    while tail < TAIL_FRAMES loop
      -- next input sample, presented at the falling LRCLK edge (like the FIFO)
      if not done_in and not endfile(fin) then
        readline(fin, lin);
        read(lin, s);
      else
        done_in := true;
        s       := 0;
        tail    := tail + 1;
      end if;
      data_in <= std_logic_vector(to_signed(s, 16));

      -- one LRCLK period: low half, rising edge, high half, falling edge
      for i in 1 to CLK_PER_HALF loop wait until rising_edge(clk); end loop;
      lrclk <= '1';
      for i in 1 to CLK_PER_HALF loop wait until rising_edge(clk); end loop;
      lrclk <= '0';
      wait until rising_edge(clk);

      -- output of the chain (last stage registers on the falling LRCLK edge)
      if is_x(data_out) then
        -- the first frames are X until the pipeline registers are filled
        if n >= 16 then
          n_x := n_x + 1;
        end if;
        write(lout, 0);
      else
        write(lout, to_integer(signed(data_out)));
      end if;
      writeline(fout, lout);

      n := n + 1;
      if n mod 48000 = 0 then
        report "tb_fx_wav: " & integer'image(n / 48000) & " s of audio processed";
      end if;
    end loop;

    file_close(fin);
    file_close(fout);
    if n_x > 0 then
      report "tb_fx_wav: " & integer'image(n_x) & " output samples were X/U" severity error;
    end if;
    report "tb_fx_wav: DONE " & integer'image(n) & " frames -> " & OUT_FILE;
    running <= false;
    std.env.stop;
    wait;
  end process;

end architecture;
