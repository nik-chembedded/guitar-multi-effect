-- -----------------------------------------------------------------------------
-- tb_fx_wav.vhd
--
-- Frame-level testbench for ModelSim: streams a recorded audio file through the
-- 24-bit FX_chain (v2 step D) and writes the result back as audio. Run it with the
-- real Intel IP (altera_mf: the distortion ROMs, fx_dpram, cab_coef_ram from
-- fpga/), which the GHDL / cocotb suite cannot do: sim/run_wav.sh.
--
-- It does the same as sim/cocotb/test_wav.py (same frame timing as
-- cocotb/fxdriver.py: CLK_PER_HALF clocks, sample_tick, CLK_PER_HALF - 1 clocks,
-- half_tick, one clock, read), so for the same input and preset the output is
-- sample-exact the same (run_wav.sh compare). 16-bit file samples are shifted by
-- DW - 16 into the chain and back.
--
-- Files (one signed 16-bit integer per line, 48 kHz mono):
--   IN_FILE   input samples   (sim/tools/wavconv.py to-txt)
--   OUT_FILE  output samples  (sim/tools/wavconv.py to-wav)
-- PRE_FRAMES silent frames run first (not written), then the file, then TAIL_FRAMES
-- of silence so that echo / reverb tails are captured. The effect registers are
-- generics (encoding of docs/register_map.md).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_fx_wav is
  generic (
    IN_FILE      : string  := "in.txt";
    OUT_FILE     : string  := "out.txt";
    DW           : positive := 24;
    CAB_TAPS     : positive := 16;       -- 16-tap cabinet: 16-clock frames (the cabinet is off in these presets)
    CAB_INIT     : string  := "cab_test16.mif";
    PRE_FRAMES   : natural := 64;
    TAIL_FRAMES  : natural := 4800;      -- 0.1 s
    CLK_PER_HALF : positive := 8;        -- clk cycles between sample_tick and half_tick

    EFFECTS      : natural := 0;         -- effects_enable: bit0 OD, 1 TREM, 2 ECHO, 3 DIST, 4 CHORUS, 5 REVERB
    OD_DRIVE     : natural := 3000;
    OD_GAIN      : natural := 3;
    TREM_WAVE    : natural := 0;
    TREM_DEPTH   : natural := 200;
    TREM_RATE    : natural := 0;
    ECHO_TIME    : natural := 14400;     -- samples (300 ms)
    ECHO_REPEAT  : natural := 100;
    ECHO_LEVEL   : natural := 26000;
    DIST_MIX     : natural := 255;
    DIST_TYPE    : natural := 1;
    CHORUS_LEVEL : natural := 128;       -- mix 0..255 (mod_delay)
    CHORUS_DEPTH : natural := 144;       -- samples
    CHORUS_RATE  : natural := 80;        -- 0.01 Hz
    MOD_BASE     : natural := 720;       -- samples
    MOD_FB       : natural := 0;         -- signed Q15 (16-bit two's complement value)
    MOD_SHAPE    : natural := 0;         -- 0 sine, 1 triangle
    REVERB_SIZE  : natural := 57672;     -- feedback Q0.16 (room 2)
    REVERB_DAMP  : natural := 60;
    REVERB_MIX   : natural := 100
  );
end entity;

architecture sim of tb_fx_wav is

  constant CLK_PERIOD : time := 10 ns;

  function slv16(v : natural) return std_logic_vector is
  begin
    return std_logic_vector(to_unsigned(v, 16));
  end function;

  signal clk      : std_logic := '0';
  signal stick    : std_logic := '0';   -- sample_tick
  signal htick    : std_logic := '0';   -- half_tick
  signal running  : boolean := true;
  signal data_in  : std_logic_vector(DW - 1 downto 0) := (others => '0');
  signal data_out : std_logic_vector(DW - 1 downto 0);
  signal unused_r : std_logic_vector(DW - 1 downto 0);

begin

  clk <= not clk after CLK_PERIOD / 2 when running else '0';

  dut : entity work.FX_chain
    generic map (DW => DW, XFADE => false, CAB_TAPS => CAB_TAPS, CAB_INIT => CAB_INIT)
    port map (
      clk            => clk,
      sample_tick    => stick,
      half_tick      => htick,
      od_enable      => '0',
      tremolo_enable => '0',
      echo_enable    => '0',
      effects_enable => slv16(EFFECTS),
      od_drive       => slv16(OD_DRIVE),
      od_gain        => slv16(OD_GAIN),
      trem_depth     => slv16(TREM_DEPTH),
      trem_wave      => slv16(TREM_WAVE),
      trem_rate      => slv16(TREM_RATE),
      mod_base       => slv16(MOD_BASE),
      mod_fb         => slv16(MOD_FB),
      mod_shape      => slv16(MOD_SHAPE),
      echo_time      => slv16(ECHO_TIME),
      echo_level     => slv16(ECHO_LEVEL),
      echo_repeat    => slv16(ECHO_REPEAT),
      chorus_rate    => slv16(CHORUS_RATE),
      chorus_level   => slv16(CHORUS_LEVEL),
      chorus_depth   => slv16(CHORUS_DEPTH),
      dist_mix       => slv16(DIST_MIX),
      dist_type      => slv16(DIST_TYPE),
      reverb_size    => slv16(REVERB_SIZE),
      reverb_damp    => slv16(REVERB_DAMP),
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
    variable n, n_x    : natural := 0;       -- frames written, X outputs among them
    variable pre       : natural := 0;
    variable tail      : natural := 0;
    variable done_in   : boolean := false;
    variable y         : signed(DW - 1 downto 0);
    variable ok        : boolean;

    -- one frame, timing of cocotb/fxdriver.py
    procedure frame is
    begin
      for i in 1 to CLK_PER_HALF loop wait until rising_edge(clk); end loop;
      stick <= '1';
      wait until rising_edge(clk);
      stick <= '0';
      for i in 2 to CLK_PER_HALF loop wait until rising_edge(clk); end loop;
      htick <= '1';
      wait until rising_edge(clk);
      htick <= '0';
      wait until rising_edge(clk);
    end procedure;
  begin
    file_open(fin, IN_FILE, read_mode);
    file_open(fout, OUT_FILE, write_mode);

    while tail < TAIL_FRAMES loop
      if pre < PRE_FRAMES then                -- settle: silent frames, not written
        pre := pre + 1;
        s   := 0;
        ok  := false;
      else
        ok := true;
        if not done_in and not endfile(fin) then
          readline(fin, lin);
          read(lin, s);
        else
          done_in := true;
          s       := 0;
          tail    := tail + 1;
        end if;
      end if;
      data_in <= std_logic_vector(shift_left(to_signed(s, DW), DW - 16));
      frame;

      if ok then
        if is_x(data_out) then
          -- the first frames are X until the pipeline registers are filled
          if n >= 16 then
            n_x := n_x + 1;
          end if;
          write(lout, 0);
        else
          y := shift_right(signed(data_out), DW - 16);
          write(lout, to_integer(y));
        end if;
        writeline(fout, lout);
        n := n + 1;
        if n mod 48000 = 0 then
          report "tb_fx_wav: " & integer'image(n / 48000) & " s of audio processed";
        end if;
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
