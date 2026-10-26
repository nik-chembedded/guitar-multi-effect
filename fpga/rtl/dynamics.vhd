-- -----------------------------------------------------------------------------
-- dynamics.vhd  (v2 step D5a)
-- Noise gate + compressor in one block (one level detector, one gain multiplier).
-- Python model: sim/cocotb/dynamics_model.py (bit-exact).  DW-bit samples (<= 24).
--
-- Per sample (strobe) a 10-stage pipeline runs; data_out is registered at the 10th
-- clock edge after the strobe edge (frame: 1024 clocks at 49.152 MHz, 16 in simulation).
--   enable = 0  : data_out <= data_in at the strobe, nothing else changes
--                 (detector and gain state are frozen).
--   gate_en = comp_en = 0 : the gains glide to 1.0 (see below); once there (cs = ga = 0)
--                 G = 2^18 / 2^18 and y = x bit-exactly.
--
-- Level detector
--   a   = |x| on a 24-bit scale (DW = 16 inputs are shifted left by 8), full scale 2^23
--   env += (a - env) >> k  (Q8 fraction, 32 bit; floor, +1 step if it rounds to 0 upwards)
--         k = 2 when a > env (attack, tau 4 samples = 83 us), else 11 (release, tau 2048
--         samples = 43 ms).  Peak follower: a sine's envelope sits ~0.1 dB under its peak.
--
-- log2 domain, "Q8 log2 units":  1 unit = 1/256 of a factor 2 = 0.02352 dB
--   dB = value * 6.0206 / 256.  All levels / thresholds / makeup / gain-reduction values
--   below are in this unit (parameter registers: signed 16-bit two's complement).
--   Example encodings: -20 dBFS = -850, -40 dBFS = -1701, +6 dB makeup = 255.
--   log2:  e = env >> 8 (24-bit integer); p = leading-one position (0..23);
--          mantissa = the 12 bits under the leading one; 32-segment piecewise-linear
--          table of log2(1+f) (Q12) with linear interpolation over the 7 low mantissa
--          bits; result Q8 = p*256 + floor(table/16).  Level L = log2(e) - 23*256 <= 0
--          (0 dBFS = 0; e = 0 and e = 1 both give -5888 = -138.4 dB).
--          Accuracy (test_dynamics.py): error -0.0264 .. +0.0006 dB (floor of Q8).
--   exp2:  g (Q8, signed) -> n = g >> 8, f = g & 255; 32-segment piecewise-linear table
--          of 2^(i/32) (Q12) interpolated over the 3 low bits of f; gain = mant * 2^n,
--          unsigned Q5.18 (1.0 = 2^18).  Accuracy (test_dynamics.py): < 0.008 dB for gain >= -48 dB, 0.031 dB >= -60 dB (below that the
--          Q18 quantisation of the gain dominates).
--
-- Compressor (comp_en = 1)
--   over   = L - comp_thresh (Q8)       comp_thresh : signed, dBFS in Q8 log2 units
--   comp_ratio[2:0] : 0 = 1:1, 1 = 2:1, 2 = 4:1, 3 = 8:1, 4..7 = infinity:1
--   red    = over - (over >> ratio)  for 0 < over, ratio 1..3;  red = over for infinity;
--            red = 0 below the threshold or at 1:1;  limited to 4095 (95.9 dB).
--   target = clamp(comp_makeup - red, -4096 .. +1024)  when comp_en = 1, else 0 (0 dB)
--   cs    += (target*256 - cs) >> k   (Q16 signed gain exponent, floor, +1 if it rounds
--            to 0 upwards).  k = comp_attack[3:0] when the gain falls, comp_release[3:0]
--            when it rises: time constant 2^k samples (k = 0 immediate, 15 = 683 ms).
--   Smoothing is in the log domain (linear-in-dB glide, no zipper noise).
--   comp_en 1 -> 0 : reduction AND makeup glide to exactly 0 dB at the release speed
--   (cs reaches 0 exactly), then the stage is a true bypass.  0 -> 1 starts from the
--   current gain and glides; no jump.
--
-- Noise gate (gate_en = 1)
--   open  when L >= gate_thresh;  closes when L < gate_thresh - 128 (3.01 dB hysteresis);
--   in between the state is kept (no chatter).  Starts open.
--   ga (Q16 attenuation, 0 .. 14 log2 units = 84.3 dB) glides linearly in dB:
--   closing +384 per sample (0 -> -84 dB in 2389 samples = 49.8 ms), opening -19200 per
--   sample (-84 -> 0 dB in 48 samples = 1.0 ms).  gate_en = 0 forces the gate open: the
--   attenuation glides to exactly 0 dB at the opening speed (1 ms), then true bypass;
--   gate_en 0 -> 1 starts from the current attenuation.
--
-- Output
--   g  = (cs >> 8) - (ga >> 8), limited to -4096 .. +1024 (-96 .. +24 dB)
--   G  = exp2(g)  (unsigned Q5.18, 23 bit)
--   y  = sat((x * G) >> 18, DW)           one 24 x 24 multiplier (a single DSP block)
--   gain_reduction = min(65535, max(0, -(cs >> 8)) + (ga >> 8)): net compressor
--   reduction (makeup counts against it) + gate attenuation, Q8 log2 units, for
--   metering; updated at pipeline stage E5 (from the state registers cs / ga that E4 has just
--   written: computing it from the E4 results in the same clock was the worst timing path of the
--   chain, -3.9 ns at 49.152 MHz; the values are unchanged).
--
-- Stage map (edge numbers counted from the strobe edge E0):
--   E0 latch x / parameters, envelope update   E1 leading one    E2 log2 table
--   E3 log2 interpolation -> L                 E4 gate + compressor state update
--   E5 gain exponent g                         E6 exp2 table     E7 exp2 interpolation
--   E8 gain G (shift)                          E9 product        E10 data_out
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fx_pkg.all;

entity dynamics is
  generic (
    DW : positive := 24                          -- 16 .. 24
  );
  port (
    clk            : in  std_logic;
    strobe         : in  std_logic;              -- once per sample
    enable         : in  std_logic;
    gate_en        : in  std_logic;
    comp_en        : in  std_logic;
    gate_thresh    : in  std_logic_vector(15 downto 0);   -- signed, Q8 log2 units re full scale
    comp_thresh    : in  std_logic_vector(15 downto 0);   -- signed, Q8 log2 units re full scale
    comp_ratio     : in  std_logic_vector(15 downto 0);   -- bits 2:0, 0..4 = 1,2,4,8,inf :1
    comp_makeup    : in  std_logic_vector(15 downto 0);   -- signed, Q8 log2 units
    comp_attack    : in  std_logic_vector(15 downto 0);   -- bits 3:0, tau = 2^k samples
    comp_release   : in  std_logic_vector(15 downto 0);   -- bits 3:0, tau = 2^k samples
    data_in        : in  std_logic_vector(DW - 1 downto 0);
    data_out       : out std_logic_vector(DW - 1 downto 0) := (others => '0');
    gain_reduction : out std_logic_vector(15 downto 0) := (others => '0')
  );
end entity;

architecture rtl of dynamics is
  constant K_ATT      : natural := 2;
  constant K_REL      : natural := 11;
  constant FS_LOG     : integer := 23 * 256;
  constant GA_MAX     : integer := 3584 * 256;
  constant GATE_CLOSE : integer := 384;
  constant GATE_OPEN  : integer := 19200;
  constant GATE_HYST  : integer := 128;
  constant RED_MAX    : integer := 4095;
  constant G_MIN      : integer := -4096;
  constant G_MAX      : integer := 1024;

  type tab_t is array (0 to 32) of integer;
  constant LOG_T : tab_t := (0, 182, 358, 530, 696, 858, 1016, 1169, 1319, 1465, 1607, 1746,
    1882, 2015, 2145, 2272, 2396, 2518, 2637, 2754, 2869, 2982, 3092, 3200, 3307, 3412, 3514,
    3615, 3715, 3812, 3908, 4003, 4096);
  constant EXP_T : tab_t := (4096, 4186, 4277, 4371, 4467, 4565, 4664, 4767, 4871, 4978, 5087,
    5198, 5312, 5428, 5547, 5668, 5793, 5919, 6049, 6182, 6317, 6455, 6597, 6741, 6889, 7039,
    7194, 7351, 7512, 7677, 7845, 8016, 8192);

  -- floor(v / 2^k) for signed integers
  function ashr(v : integer; k : natural) return integer is
  begin
    return to_integer(shift_right(to_signed(v, 32), k));
  end function;

  signal vp       : std_logic_vector(1 to 10) := (others => '0');
  -- latched at the strobe
  signal x_r      : signed(DW - 1 downto 0) := (others => '0');
  signal p_gen    : std_logic := '0';
  signal p_cen    : std_logic := '0';
  signal p_gth    : integer range -32768 to 32767 := 0;
  signal p_cth    : integer range -32768 to 32767 := 0;
  signal p_mk     : integer range -32768 to 32767 := 0;
  signal p_rat    : natural range 0 to 7 := 0;
  signal p_att    : natural range 0 to 15 := 0;
  signal p_rel    : natural range 0 to 15 := 0;
  -- state
  signal env      : unsigned(31 downto 0) := (others => '0');
  signal cs       : integer range -2 ** 21 to 2 ** 21 := 0;
  signal ga       : integer range 0 to GA_MAX := 0;
  signal gopen    : std_logic := '1';
  -- pipeline
  signal lead     : natural range 0 to 23 := 0;
  signal nm       : unsigned(22 downto 0) := (others => '0');
  signal lead2    : natural range 0 to 23 := 0;
  signal lt0, lt1 : integer range 0 to 4096 := 0;
  signal lr       : natural range 0 to 127 := 0;
  signal lrel     : integer range -8192 to 8191 := 0;
  signal gexp     : integer range G_MIN to G_MAX := 0;
  signal nexp     : integer range -16 to 4 := 0;
  signal nexp2    : integer range -16 to 4 := 0;
  signal et0, et1 : integer range 0 to 8192 := 0;
  signal er       : natural range 0 to 7 := 0;
  signal mant     : integer range 0 to 8191 := 0;
  signal gain     : unsigned(22 downto 0) := (others => '0');
  signal prod     : signed(DW + 23 downto 0) := (others => '0');
begin

  process(clk)
    variable xs     : signed(24 downto 0);
    variable xa     : signed(24 downto 0);
    variable a      : unsigned(23 downto 0);
    variable t, e   : signed(32 downto 0);
    variable diff   : signed(32 downto 0);
    variable step   : signed(32 downto 0);
    variable sum    : signed(32 downto 0);
    variable envi   : unsigned(23 downto 0);
    variable pv     : natural range 0 to 23;
    variable nmv    : unsigned(23 downto 0);
    variable tl     : integer;
    variable over, red, d, st, rsn, gan, g, fr, tg : integer;
    variable gos    : std_logic;
    variable g16    : signed(15 downto 0);
    variable mant_v : unsigned(22 downto 0);
    variable k      : natural;
  begin
    if rising_edge(clk) then
      vp(1) <= '0';
      -- E0: latch, envelope update --------------------------------------------
      if strobe = '1' then
        if enable = '1' then
          vp(1) <= '1';
          x_r   <= signed(data_in);
          p_gen <= gate_en;
          p_cen <= comp_en;
          p_gth <= to_integer(signed(gate_thresh));
          p_cth <= to_integer(signed(comp_thresh));
          p_mk  <= to_integer(signed(comp_makeup));
          p_rat <= to_integer(unsigned(comp_ratio(2 downto 0)));
          p_att <= to_integer(unsigned(comp_attack(3 downto 0)));
          p_rel <= to_integer(unsigned(comp_release(3 downto 0)));
          xs := shift_left(resize(signed(data_in), 25), 24 - DW);
          xa := abs(xs);
          a  := unsigned(xa(23 downto 0));
          t    := signed('0' & a & "00000000");
          e    := signed('0' & env);
          diff := t - e;
          if diff > 0 then k := K_ATT; else k := K_REL; end if;
          step := shift_right(diff, k);
          if step = 0 and diff > 0 then
            step := to_signed(1, 33);
          end if;
          sum := e + step;
          env <= unsigned(sum(31 downto 0));
        else
          data_out <= data_in;
        end if;
      end if;
      vp(2 to 10) <= vp(1 to 9);

      -- E1: leading one ---------------------------------------------------------
      if vp(1) = '1' then
        envi := env(31 downto 8);
        pv := 0;
        for i in 0 to 23 loop
          if envi(i) = '1' then pv := i; end if;
        end loop;
        nmv  := shift_left(envi, 23 - pv);
        lead <= pv;
        nm   <= nmv(22 downto 0);
      end if;
      -- E2: log2 table lookup -----------------------------------------------------
      if vp(2) = '1' then
        lt0   <= LOG_T(to_integer(nm(22 downto 18)));
        lt1   <= LOG_T(to_integer(nm(22 downto 18)) + 1);
        lr    <= to_integer(nm(17 downto 11));
        lead2 <= lead;
      end if;
      -- E3: log2 interpolation -> level L (Q8, re full scale) -----------------------
      if vp(3) = '1' then
        tl   := lt0 + ((lt1 - lt0) * lr) / 128;
        lrel <= lead2 * 256 + tl / 16 - FS_LOG;
      end if;
      -- E4: gate + compressor state --------------------------------------------------
      if vp(4) = '1' then
        -- gate
        gos := gopen;
        gan := ga;
        if p_gen = '1' then
          if lrel >= p_gth then
            gos := '1';
          elsif lrel < p_gth - GATE_HYST then
            gos := '0';
          end if;
        else
          gos := '1';                            -- off: glide back open
        end if;
        if gos = '1' then
          gan := gan - GATE_OPEN;
          if gan < 0 then gan := 0; end if;
        else
          gan := gan + GATE_CLOSE;
          if gan > GA_MAX then gan := GA_MAX; end if;
        end if;
        gopen <= gos;
        ga    <= gan;
        -- compressor: cs glides to the target exponent (0 dB when off)
        if p_cen = '1' then
          over := lrel - p_cth;
          if over > 0 and p_rat /= 0 then
            if p_rat >= 4 then red := over; else red := over - ashr(over, p_rat); end if;
          else
            red := 0;
          end if;
          if red > RED_MAX then red := RED_MAX; end if;
          tg := p_mk - red;
          if tg < G_MIN then tg := G_MIN; end if;
          if tg > G_MAX then tg := G_MAX; end if;
        else
          tg := 0;
        end if;
        d := tg * 256 - cs;
        if d < 0 then k := p_att; else k := p_rel; end if;
        st := ashr(d, k);
        if st = 0 and d > 0 then st := 1; end if;
        rsn := cs + st;
        cs <= rsn;
      end if;
      -- E5: total gain exponent -----------------------------------------------------------
      if vp(5) = '1' then
        -- gain-reduction meter: net reduction (make-up against it) + gate attenuation
        tl := ashr(cs, 8);
        if tl > 0 then tl := 0; end if;
        tl := ga / 256 - tl;
        if tl > 65535 then tl := 65535; end if;
        gain_reduction <= std_logic_vector(to_unsigned(tl, 16));
        g := ashr(cs, 8) - (ga / 256);
        if g < G_MIN then g := G_MIN; end if;
        if g > G_MAX then g := G_MAX; end if;
        gexp <= g;
      end if;
      -- E6: exp2 table lookup --------------------------------------------------------------
      if vp(6) = '1' then
        g16 := to_signed(gexp, 16);
        fr  := to_integer(unsigned(g16(7 downto 3)));
        et0 <= EXP_T(fr);
        et1 <= EXP_T(fr + 1);
        er  <= to_integer(unsigned(g16(2 downto 0)));
        nexp <= to_integer(shift_right(g16, 8));
      end if;
      -- E7: exp2 interpolation -> mantissa (Q12, 1 .. 2) ------------------------------------------
      if vp(7) = '1' then
        mant  <= et0 + ((et1 - et0) * er) / 8;
        nexp2 <= nexp;
      end if;
      -- E8: gain G = mant * 2^n (unsigned Q5.18) ----------------------------------------------------
      if vp(8) = '1' then
        mant_v := to_unsigned(mant, 23);
        if nexp2 + 6 >= 0 then
          gain <= shift_left(mant_v, nexp2 + 6);
        else
          gain <= shift_right(mant_v, -(nexp2 + 6));
        end if;
      end if;
      -- E9: product ------------------------------------------------------------------------------------
      if vp(9) = '1' then
        prod <= x_r * signed('0' & gain);
      end if;
      -- E10: output --------------------------------------------------------------------------------------
      if vp(10) = '1' then
        data_out <= std_logic_vector(sat(shift_right(prod, 18), DW));
      end if;
    end if;
  end process;

end architecture;
