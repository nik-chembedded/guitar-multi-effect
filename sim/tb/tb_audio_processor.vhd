-- -----------------------------------------------------------------------------
-- tb_audio_processor.vhd
--
-- Self-checking testbench for the complete audio path:
--
--     i2s_codec_model --(I2S)--> audio_processor --(I2S)--> i2s_codec_model
--                                 ADC_CONTROLLER -> my_fifo -> FX_chain -> DAC_CONTROLLER
--
-- The effect registers are driven directly (the Nios II / Avalon path is not
-- part of this testbench). One simulation run executes one test, selected by
-- the TEST generic:
--
--   bypass      all effects off, PRBS input      -> output must be bit-exact (after latency)
--   overdrive   clip @ 3000, gain 4, 440 Hz sine -> bit-exact against a reference model
--   distortion  medium curve, full wet, 440 Hz   -> no wrap glitches, symmetric output (no DC)
--   tremolo     5 Hz sine LFO, full depth        -> envelope must be modulated
--   chorus      depth 200, rate 20, 440 Hz       -> no X, no wrap glitches, wet differs from dry
--   echo        1200 samples, level 0.5, rep 0.5 -> echo 1 = 0.5*x, echo 2 = 0.25*x at k*1200
--   reverb      heavy room, 50 % mix, tone burst -> no wrap glitches, decaying tail
--
-- Every test also fails if the DAC output contains X/U (uninitialised logic)
-- or full-scale jumps between consecutive samples (two's-complement wrap).
--
-- Results: "RESULT: PASS <test>" / "RESULT: FAIL <test>" in the transcript, and
-- the captured samples in <OUT_DIR>/<test>.txt  (columns: n  input  output).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;
use std.textio.all;

entity tb_audio_processor is
  generic (
    TEST     : string   := "bypass";
    N_FRAMES : positive := 4800;          -- 0.1 s @ 48 kHz
    OUT_DIR  : string   := "out"
  );
end entity;

architecture sim of tb_audio_processor is

  constant FS         : real    := 48000.0;
  constant MAX_LAT    : natural := 32;     -- latency search window [frames]
  constant SKIP       : natural := 64;     -- start-up frames ignored by the checks
  constant WRAP_STEP  : natural := 30000;  -- |y[n]-y[n-1]| above this = wrap-around

  type int_array is array (natural range <>) of integer;

  -- DUT configuration
  signal effects_enable : std_logic_vector(15 downto 0) := (others => '0');
  signal od_drive       : std_logic_vector(15 downto 0) := (others => '0');
  signal od_gain        : std_logic_vector(15 downto 0) := (others => '0');
  signal trem_depth     : std_logic_vector(15 downto 0) := (others => '0');
  signal trem_wave      : std_logic_vector(15 downto 0) := (others => '0');
  signal echo_time      : std_logic_vector(15 downto 0) := (others => '0');
  signal echo_level     : std_logic_vector(15 downto 0) := (others => '0');
  signal echo_repeat    : std_logic_vector(15 downto 0) := (others => '0');
  signal chorus_rate    : std_logic_vector(15 downto 0) := (others => '0');
  signal chorus_level   : std_logic_vector(15 downto 0) := (others => '0');
  signal chorus_depth   : std_logic_vector(15 downto 0) := (others => '0');
  signal dist_mix       : std_logic_vector(15 downto 0) := (others => '0');
  signal dist_type      : std_logic_vector(15 downto 0) := (others => '0');
  signal reverb_type    : std_logic_vector(15 downto 0) := (others => '0');
  signal reverb_mix     : std_logic_vector(15 downto 0) := (others => '0');

  -- Codec interface
  signal run         : boolean := true;
  signal mclk        : std_logic;
  signal bclk        : std_logic;
  signal lrclk       : std_logic;
  signal adcdat      : std_logic;
  signal dacdat      : std_logic;
  signal adc_left    : integer := 0;
  signal frame_start : std_logic;
  signal dac_left    : integer;
  signal dac_right   : integer;
  signal dac_meta    : boolean;
  signal dac_valid   : std_logic;

  function slv16(v : natural) return std_logic_vector is
  begin
    return std_logic_vector(to_unsigned(v, 16));
  end function;

  function sine(n : natural; f, amp : real) return integer is
  begin
    return integer(round(amp * sin(MATH_2_PI * f * real(n) / FS)));
  end function;

begin

  -- ---------------------------------------------------------------------------
  codec : entity work.i2s_codec_model
    port map (
      enable      => run,
      mclk        => mclk,
      bclk        => bclk,
      lrclk       => lrclk,
      adcdat      => adcdat,
      dacdat      => dacdat,
      adc_left    => adc_left,
      adc_right   => adc_left,
      frame_start => frame_start,
      dac_left    => dac_left,
      dac_right   => dac_right,
      dac_meta    => dac_meta,
      dac_valid   => dac_valid
    );

  dut : entity work.audio_processor
    port map (
      clk_18Mhz      => mclk,
      AUD_BCLK       => bclk,
      AUD_ADCDAT     => adcdat,
      AUD_ADCLRCLK   => lrclk,
      L_R_RESET      => '1',
      od_enable      => '0',
      tremolo_enable => '0',
      echo_enable    => '0',
      effects_enable => effects_enable,
      od_drive       => od_drive,
      od_gain        => od_gain,
      trem_depth     => trem_depth,
      trem_wave      => trem_wave,
      echo_time      => echo_time,
      echo_level     => echo_level,
      echo_repeat    => echo_repeat,
      chorus_rate    => chorus_rate,
      chorus_level   => chorus_level,
      chorus_depth   => chorus_depth,
      dist_mix       => dist_mix,
      dist_type      => dist_type,
      reverb_type    => reverb_type,
      reverb_mix     => reverb_mix,
      AUD_DACLRCLK   => lrclk,
      AUD_DACDAT     => dacdat
    );

  -- ---------------------------------------------------------------------------
  main : process
    variable stim     : int_array(0 to N_FRAMES - 1);
    variable resp     : int_array(0 to N_FRAMES - 1);
    variable n_tx     : natural := 0;
    variable n_rx     : natural := 0;
    variable n_meta   : natural := 0;
    variable errors   : natural := 0;
    variable lat      : integer := -1;
    variable seed1    : positive := 17;
    variable seed2    : positive := 4242;
    variable r        : real;

    -- ---- helpers ---------------------------------------------------------
    procedure fail(msg : string) is
    begin
      report TEST & ": " & msg severity error;
      errors := errors + 1;
    end procedure;

    procedure info(msg : string) is
    begin
      report TEST & ": " & msg severity note;
    end procedure;

    -- latency at which resp matches stim with the lowest absolute error
    procedure find_latency(variable best_lat : out integer; variable best_err : out integer) is
      variable e : integer;
    begin
      best_lat := -1;
      best_err := integer'high;
      for l in 0 to MAX_LAT loop
        e := 0;
        for n in SKIP to SKIP + 400 loop
          e := e + abs (resp(n + l) - stim(n));
          exit when e > best_err;
        end loop;
        if e < best_err then
          best_err := e;
          best_lat := l;
        end if;
      end loop;
    end procedure;

    -- first output frame whose magnitude exceeds thr
    function first_above(a : int_array; thr : natural) return integer is
    begin
      for n in a'range loop
        if abs a(n) > thr then
          return n;
        end if;
      end loop;
      return -1;
    end function;

    function peak_near(a : int_array; c, w : integer) return integer is
      variable m : integer := 0;
    begin
      for n in c - w to c + w loop
        if n >= a'low and n <= a'high and abs a(n) > abs m then
          m := a(n);
        end if;
      end loop;
      return m;
    end function;

    procedure check_wrap is
      variable cnt : natural := 0;
    begin
      for n in SKIP + 1 to n_rx - 1 loop
        if abs (resp(n) - resp(n - 1)) > WRAP_STEP then
          if cnt < 5 then
            fail("wrap-around/glitch at frame " & integer'image(n) & ": "
                 & integer'image(resp(n - 1)) & " -> " & integer'image(resp(n)));
          end if;
          cnt := cnt + 1;
        end if;
      end loop;
      if cnt > 0 then
        fail(integer'image(cnt) & " wrap-around glitches in total");
      end if;
    end procedure;

    procedure dump is
      file     f : text;
      variable l : line;
    begin
      file_open(f, OUT_DIR & "/" & TEST & ".txt", write_mode);
      write(l, string'("# n input output   (test=" & TEST & ")"));
      writeline(f, l);
      for n in 0 to n_rx - 1 loop
        write(l, n);
        write(l, ' ');
        write(l, stim(n));
        write(l, ' ');
        write(l, resp(n));
        writeline(f, l);
      end loop;
      file_close(f);
    end procedure;

    -- ---- per-test configuration and stimulus -----------------------------
    procedure configure is
    begin
      if TEST = "bypass" then
        null;
      elsif TEST = "overdrive" then
        od_drive       <= slv16(3000);
        od_gain        <= slv16(4);
        effects_enable <= slv16(16#01#);
      elsif TEST = "tremolo" then
        trem_wave      <= slv16(0);      -- 5 Hz sine
        trem_depth     <= slv16(255);
        effects_enable <= slv16(16#02#);
      elsif TEST = "echo" then
        echo_time      <= slv16(1200);   -- 25 ms
        echo_level     <= slv16(32768);  -- 0.5
        echo_repeat    <= slv16(128);    -- 0.5
        effects_enable <= slv16(16#04#);
      elsif TEST = "distortion" then
        dist_type      <= slv16(1);      -- medium
        dist_mix       <= slv16(255);    -- fully wet
        effects_enable <= slv16(16#08#);
      elsif TEST = "chorus" then
        chorus_level   <= slv16(32768);
        chorus_depth   <= slv16(200);
        chorus_rate    <= slv16(20);
        effects_enable <= slv16(16#10#);
      elsif TEST = "reverb" then
        reverb_type    <= slv16(3);      -- heavy
        reverb_mix     <= slv16(128);
        effects_enable <= slv16(16#20#);
      else
        report "Unknown TEST '" & TEST & "'" severity failure;
      end if;
    end procedure;

    impure function stimulus(n : natural) return integer is
    begin
      if n = 0 then
        return 0;
      elsif TEST = "bypass" then
        uniform(seed1, seed2, r);
        return integer(trunc(r * 65535.0)) - 32768;          -- full-scale PRBS
      elsif TEST = "overdrive" or TEST = "chorus" then
        return sine(n, 440.0, 12000.0);
      elsif TEST = "distortion" then
        return sine(n, 440.0, 24000.0);
      elsif TEST = "tremolo" then
        return sine(n, 440.0, 16000.0);
      elsif TEST = "echo" then
        if n = 100 then return 16000; else return 0; end if;  -- impulse
      elsif TEST = "reverb" then
        if n < 2400 then return sine(n, 440.0, 12000.0); else return 0; end if;
      end if;
      return 0;
    end function;

    -- ---- checks ----------------------------------------------------------
    procedure check_test is
      variable e, m, p0, pk, sum, cnt : integer;
      variable ref                    : integer;
      variable bmin, bmax, b          : integer;
    begin
      if TEST = "bypass" then
        find_latency(lat, e);
        info("latency = " & integer'image(lat) & " frames");
        cnt := 0;
        for n in SKIP to n_rx - 1 - MAX_LAT loop
          if resp(n + lat) /= stim(n) then
            if cnt < 5 then
              fail("mismatch at n=" & integer'image(n) & " exp " & integer'image(stim(n))
                   & " got " & integer'image(resp(n + lat)));
            end if;
            cnt := cnt + 1;
          end if;
        end loop;
        if cnt > 0 then
          fail(integer'image(cnt) & " mismatching samples");
        end if;

      elsif TEST = "overdrive" then
        -- reference: clip(x, +-drive) * gain
        e := integer'high;
        lat := -1;
        for l in 0 to MAX_LAT loop
          m := 0;
          for n in SKIP to n_rx - 1 - MAX_LAT loop
            ref := stim(n);
            if ref >= 3000 then ref := 3000; elsif ref <= -3000 then ref := -3000; end if;
            m := m + abs (resp(n + l) - 4 * ref);
          end loop;
          if m < e then e := m; lat := l; end if;
        end loop;
        info("best latency " & integer'image(lat) & ", total abs error " & integer'image(e));
        if e /= 0 then
          fail("output differs from clip(x,3000)*4 reference");
        end if;

      elsif TEST = "distortion" then
        check_wrap;
        -- symmetric clipping curve -> mean over whole 440 Hz cycles ~ 0
        sum := 0; pk := 0; cnt := 0;
        for n in 1000 to 1000 + 12 * 1200 / 11 - 1 loop     -- 12 periods of 440 Hz (~109.09 frames)
          exit when n >= n_rx;
          sum := sum + resp(n);
          cnt := cnt + 1;
          if abs resp(n) > pk then pk := abs resp(n); end if;
        end loop;
        m := sum / cnt;
        info("peak " & integer'image(pk) & ", mean (DC) " & integer'image(m));
        if pk < 10000 then
          fail("output level too low");
        end if;
        if abs m > pk / 20 then
          fail("output is not symmetric (DC offset " & integer'image(m)
               & ") - negative half-wave lost?");
        end if;
        -- negative input must give negative output somewhere
        cnt := 0;
        for n in 1000 to n_rx - 1 loop
          if resp(n) < -1000 then cnt := cnt + 1; end if;
        end loop;
        if cnt = 0 then
          fail("no negative output samples at all (signal is rectified)");
        end if;

      elsif TEST = "tremolo" then
        check_wrap;
        -- envelope per 5 ms block must vary by > 2x over one LFO period
        bmin := integer'high; bmax := 0;
        for blk in 1 to (n_rx / 240) - 1 loop
          b := 0;
          for n in blk * 240 to blk * 240 + 239 loop
            if abs resp(n) > b then b := abs resp(n); end if;
          end loop;
          if b < bmin then bmin := b; end if;
          if b > bmax then bmax := b; end if;
        end loop;
        info("envelope min " & integer'image(bmin) & ", max " & integer'image(bmax));
        if bmax < 2 * bmin + 1 then
          fail("no amplitude modulation detected");
        end if;

      elsif TEST = "chorus" then
        check_wrap;
        find_latency(lat, e);
        info("dry/wet difference over 400 frames = " & integer'image(e));
        if e < 1000 then
          fail("output identical to input - effect not active");
        end if;

      elsif TEST = "echo" then
        check_wrap;
        p0 := first_above(resp, 8000);
        if p0 < 0 then
          fail("dry impulse not found in output");
        else
          info("dry impulse at output frame " & integer'image(p0)
               & " = " & integer'image(resp(p0)));
          m := peak_near(resp, p0 + 1200, 3);
          info("echo 1 = " & integer'image(m) & " (expected 8000)");
          if abs (m - 8000) > 400 then
            fail("echo 1 amplitude wrong");
          end if;
          m := peak_near(resp, p0 + 2400, 3);
          info("echo 2 = " & integer'image(m) & " (expected 4000)");
          if abs (m - 4000) > 400 then
            fail("echo 2 amplitude wrong");
          end if;
        end if;

      elsif TEST = "reverb" then
        check_wrap;
        -- energy in the tail after the burst must be > 0 and decay
        sum := 0; m := 0;
        for n in 2600 to 3299 loop sum := sum + abs resp(n) / 16; end loop;
        for n in 4000 to 4699 loop m := m + abs resp(n) / 16; end loop;
        info("tail energy early " & integer'image(sum) & ", late " & integer'image(m));
        if sum = 0 then
          fail("no reverb tail after the burst");
        elsif m >= sum then
          fail("reverb tail does not decay");
        end if;
      end if;
    end procedure;

  begin
    info("starting, " & integer'image(N_FRAMES) & " frames");
    configure;
    for n in stim'range loop
      stim(n) := stimulus(n);
    end loop;
    adc_left <= stim(0);

    -- stream samples in, capture samples out
    while n_rx < N_FRAMES loop
      wait until rising_edge(frame_start) or rising_edge(dac_valid);
      if frame_start = '1' then
        n_tx := n_tx + 1;
        if n_tx < N_FRAMES then
          adc_left <= stim(n_tx);
        else
          adc_left <= 0;
        end if;
      else
        resp(n_rx) := dac_left;
        if dac_meta and n_rx >= SKIP then
          n_meta := n_meta + 1;
        end if;
        n_rx := n_rx + 1;
      end if;
    end loop;

    run <= false;
    dump;

    if n_meta > 0 then
      fail(integer'image(n_meta) & " output frames contained X/U values (uninitialised logic)");
    end if;
    check_test;

    if errors = 0 then
      report "RESULT: PASS " & TEST severity note;
    else
      report "RESULT: FAIL " & TEST & " (" & integer'image(errors) & " errors)" severity note;
    end if;
    std.env.stop;
    wait;
  end process;

end architecture;
