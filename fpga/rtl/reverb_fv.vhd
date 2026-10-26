-- -----------------------------------------------------------------------------
-- reverb_fv.vhd  (v2 step D4)
-- Freeverb-style mono reverb: input >> IN_SHIFT (7) -> 8 parallel lowpass-feedback combs
-- (summed) -> 4 series all-pass (g = 0.5) -> wet;  y = mix8(dry, wet, mix).
--
--   comb lengths 1215 1293 1390 1476 1548 1623 1695 1760  (Freeverb @ 48 kHz)
--   all-pass     605 480 371 245
--   Loop delay of every line is EXACTLY its length in samples: the read of the
--   delayed values for sample n+1 happens right after the strobe of sample n
--   (read address = wp - LEN, RAM latency 2), so the whole feedback computation
--   for sample n+1 is finished 8 clocks after the strobe of sample n and only
--   the input add and the dry/wet mix remain at the next strobe. The wet value of
--   a sample depends only on past input (no input-to-output path through the
--   combs), as in Freeverb.
--
--   size : feedback Q0.16, clamped to 64225 (0.98) inside     damp : [7:0], 0 .. 255
--   mix  : [7:0], 0 = dry only (data_out = data_in exactly), else mix8
--   Input gain: >> IN_SHIFT = 7 (1/128; Freeverb uses 0.015 ~ 1/64 but boosts the wet). Comb DC gain is
--   1/(1-fb) <= 50, so 8 summed combs at full-scale DC would reach 3.1x full
--   scale: real signals are far below that; every sum / feedback add saturates
--   (add_sat / sat) and the damping store is a convex combination (cannot overflow).
--   Strobes: all work is sequenced from en_rise (sequencer ends 8 clocks after
--   it, frame = 16 clocks in simulation); en_fall is accepted for interface
--   compatibility and not needed.
--   Wet level: after the all-pass chain the wet is multiplied by 2^WET_SHIFT (default 2,
--   saturating) before the mix; measured wet/input RMS at size 0.84, damp 60, mix 255,
--   input -12 dBFS RMS: pink noise -2.2 dB, guitar clip +1.7 dB (WET_SHIFT 1: -8.2 / -4.3).
--   Rounding: floor (fx_pkg) everywhere except the two feedback gains (store*fb, b/2),
--   which truncate toward zero (div_pow2) so the tail decays to exactly 0 (floor
--   leaves a -1 LSB limit cycle in every loop).
--   enable = '0': bypass (data_out <= data_in), the reverb state is frozen.
-- Python model: sim/cocotb/reverbfv_model.py (bit-exact).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fx_pkg.all;

entity reverb_fv is
  generic (
    DW       : positive := 16;
    IN_SHIFT  : natural := 7;                   -- input gain 2^-IN_SHIFT (internal headroom)
    WET_SHIFT : natural := 2                    -- wet gain 2^WET_SHIFT after the all-pass chain (saturating)
  );
  port (
    clk      : in  std_logic;
    en_rise  : in  std_logic;
    en_fall  : in  std_logic;
    enable   : in  std_logic;
    size     : in  std_logic_vector(15 downto 0);
    damp     : in  std_logic_vector(15 downto 0);
    mix      : in  std_logic_vector(15 downto 0);
    data_in  : in  std_logic_vector(DW - 1 downto 0);
    data_out : out std_logic_vector(DW - 1 downto 0) := (others => '0')
  );
end entity;

architecture rtl of reverb_fv is
  type int_arr is array (natural range <>) of integer;
  constant CL : int_arr(0 to 7) := (1215, 1293, 1390, 1476, 1548, 1623, 1695, 1760);
  constant AL : int_arr(0 to 3) := (605, 480, 371, 245);
  constant FB_MAX : integer := 64225;                     -- 0.98 * 65536

  type sig_arr is array (natural range <>) of signed(DW - 1 downto 0);
  signal c_out   : sig_arr(0 to 7);
  signal a_out   : sig_arr(0 to 3);
  type ps_arr is array (0 to 3) of signed(DW downto 0);
  signal ps      : ps_arr := (others => (others => '0'));
  signal csum    : signed(DW - 1 downto 0) := (others => '0');

  signal wp      : unsigned(10 downto 0) := (others => '0');
  signal seq     : natural range 0 to 15 := 15;           -- 15 = idle; edge (strobe + k) sees seq = k
  signal damp_r  : unsigned(7 downto 0) := (others => '0');
  signal fb_r    : unsigned(15 downto 0) := (others => '0');
  signal xg      : signed(DW - 1 downto 0);
  signal wr_en   : std_logic;
  signal st      : std_logic_vector(0 to 15);
  signal wet     : signed(DW - 1 downto 0);
begin

  xg    <= shift_right(signed(data_in), IN_SHIFT);
  wr_en <= en_rise and enable;
  wet   <= sat(shift_left(resize(a_out(3), DW + WET_SHIFT), WET_SHIFT), DW);   -- level restore

  gst : for k in 0 to 15 generate
    st(k) <= '1' when seq = k else '0';
  end generate;

  gc : for i in 0 to 7 generate
    u_c : entity work.fv_comb
      generic map (DW => DW, LEN => CL(i))
      port map (clk => clk, wr_en => wr_en, st_a => st(3), st_b => st(4), wp => wp,
                xin => xg, damp => damp_r, fb => fb_r, y => c_out(i));
  end generate;

  ga : for j in 0 to 3 generate
    g0 : if j = 0 generate
      u_a : entity work.fv_allpass
        generic map (DW => DW, LEN => AL(j))
        port map (clk => clk, wr_en => wr_en, st => st(5 + j), wp => wp, d_in => csum, d_out => a_out(j));
    end generate;
    g1 : if j > 0 generate
      u_a : entity work.fv_allpass
        generic map (DW => DW, LEN => AL(j))
        port map (clk => clk, wr_en => wr_en, st => st(5 + j), wp => wp, d_in => a_out(j - 1), d_out => a_out(j));
    end generate;
  end generate;

  process(clk)
    variable fbi : integer;
  begin
    if rising_edge(clk) then
      if en_rise = '1' then
        if enable = '1' then
          if mix(7 downto 0) = x"00" then
            data_out <= data_in;                          -- mix 0: exact dry
          else
            data_out <= std_logic_vector(mix8(signed(data_in), wet, unsigned(mix(7 downto 0))));
          end if;
          wp     <= wp + 1;
          damp_r <= unsigned(damp(7 downto 0));
          fbi := to_integer(unsigned(size));
          if fbi > FB_MAX then fbi := FB_MAX; end if;
          fb_r   <= to_unsigned(fbi, 16);
          seq    <= 1;
        else
          data_out <= data_in;
        end if;
      elsif seq = 9 then
        seq <= 15;
      elsif seq /= 15 then
        seq <= seq + 1;
      end if;
      -- stage 3 (comb outputs valid): pair sums;  stage 4: comb sum (saturated)
      if st(3) = '1' then
        for k in 0 to 3 loop
          ps(k) <= resize(c_out(2 * k), DW + 1) + resize(c_out(2 * k + 1), DW + 1);
        end loop;
      end if;
      if st(4) = '1' then
        csum <= sat(resize(ps(0), DW + 3) + resize(ps(1), DW + 3)
                  + resize(ps(2), DW + 3) + resize(ps(3), DW + 3), DW);
      end if;
    end if;
  end process;

end architecture;
