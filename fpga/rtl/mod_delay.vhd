-- -----------------------------------------------------------------------------
-- mod_delay.vhd  (v2 step D2)
-- Modulated delay with fractional (linearly interpolated) read: chorus, flanger
-- and vibrato are the same block with different settings. Replaces chorus.vhd.
--
--   d   = base + depth * (lfo - 32768) / 32768        samples, 8 fraction bits,
--                                                      clamped to 1 .. 2^AW - 2
--   wet = A + (B - A) * frac / 256                     A = line[d_int], B = line[d_int + 1]
--   line <- sat(x + fb * wet / 32768)                  feedback, fb signed Q15
--   y   = mix8(x, wet, mix)
--
-- Per sample (en_rise): output and line write use the wet value read after the
-- previous strobe; then a small sequencer reads A and B in two consecutive clocks
-- (RAM latency 2) and interpolates: done 6 clocks after the strobe, long before
-- the next one (1024 clocks at 49.152 MHz, 16 in simulation).
--   base, depth : samples (0 .. 2^AW - 2);  rate : LFO in 0.01 Hz
--   shape       : 0 sine, 1 triangle;      mix : 0 dry .. 255 wet
-- DW-bit samples. Python model: sim/cocotb/moddelay_model.py (bit-exact).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fx_pkg.all;

entity mod_delay is
  generic (
    DW : positive := 16;
    AW : positive := 11                         -- 2048-word line (42.7 ms)
  );
  port (
    clk      : in  std_logic;
    en_rise  : in  std_logic;                   -- once per sample
    enable   : in  std_logic;
    mix      : in  std_logic_vector(15 downto 0);
    depth    : in  std_logic_vector(15 downto 0);
    rate     : in  std_logic_vector(15 downto 0);
    base     : in  std_logic_vector(15 downto 0);
    fb       : in  std_logic_vector(15 downto 0);   -- signed Q15
    shape    : in  std_logic_vector(15 downto 0);   -- bit 0
    data_in  : in  std_logic_vector(DW - 1 downto 0);
    data_out : out std_logic_vector(DW - 1 downto 0) := (others => '0')
  );
end entity;

architecture rtl of mod_delay is
  constant DMAX : natural := 2 ** AW - 2;

  signal lfo      : std_logic_vector(15 downto 0);
  signal lfo_shape: std_logic_vector(1 downto 0);
  signal wp       : unsigned(AW - 1 downto 0) := (others => '0');
  signal rd_addr  : unsigned(AW - 1 downto 0) := (others => '0');
  signal wr_data  : std_logic_vector(DW - 1 downto 0);
  signal q        : std_logic_vector(DW - 1 downto 0);
  signal wet      : signed(DW - 1 downto 0) := (others => '0');
  signal a_r      : signed(DW - 1 downto 0) := (others => '0');
  signal d_int    : unsigned(AW - 1 downto 0) := (others => '0');
  signal d_frac   : unsigned(7 downto 0) := (others => '0');
  signal seq      : natural range 0 to 7 := 7;
  signal wp_s     : unsigned(AW - 1 downto 0) := (others => '0');

  -- delay in samples * 256, clamped
  function delay_q8(b, dp : std_logic_vector(15 downto 0); l : std_logic_vector(15 downto 0)) return integer is
    variable bi  : integer := to_integer(unsigned(b));
    variable dpi : integer := to_integer(unsigned(dp));
    variable li  : integer := to_integer(unsigned(l)) - 32768;
    variable d   : integer;
  begin
    if bi > DMAX then bi := DMAX; end if;
    if dpi > DMAX then dpi := DMAX; end if;
    d := bi * 256 + to_integer(shift_right(to_signed(dpi, 13) * to_signed(li, 17), 7));
    if d < 256 then d := 256; end if;
    if d > DMAX * 256 then d := DMAX * 256; end if;
    return d;
  end function;
begin

  lfo_shape <= '0' & shape(0);                 -- 0 sine, 1 triangle
  u_lfo : entity work.nco_lfo
    port map (clk => clk, tick => en_rise, rate => rate, shape => lfo_shape, lfo => lfo);

  -- line input: x + feedback * wet
  wr_data <= std_logic_vector(add_sat(signed(data_in),
               resize(smul_shr(wet, signed(fb), 15), DW + 2), DW));

  u_line : entity work.fx_dpram
    generic map (WIDTH => DW, ADDR_W => AW)
    port map (clock => clk, clocken => '1', data => wr_data, rdaddress => std_logic_vector(rd_addr),
              wraddress => std_logic_vector(wp), wren => en_rise and enable, q => q);

  process(clk)
    variable d : integer;
  begin
    if rising_edge(clk) then
      if en_rise = '1' then
        -- output with the wet value read after the previous strobe
        if enable = '1' then
          data_out <= std_logic_vector(mix8(signed(data_in), wet, unsigned(mix(7 downto 0))));
        else
          data_out <= data_in;
        end if;
        wp_s <= wp;                             -- the word written now
        if enable = '1' then
          wp <= wp + 1;
        end if;
        d := delay_q8(base, depth, lfo);
        d_int  <= to_unsigned(d / 256, AW);
        d_frac <= to_unsigned(d mod 256, 8);
        seq    <= 0;
      elsif seq /= 7 then
        seq <= seq + 1;
      end if;
      -- read sequencer: A = line[wp_s - d_int + 1], B = one sample older
      case seq is
        when 0 => rd_addr <= wp_s - d_int + 1;
        when 1 => rd_addr <= wp_s - d_int;
        when 3 => a_r <= signed(q);             -- A arrives 2 clocks after its address
        when 4 => wet <= resize(a_r + shift_right((resize(signed(q), DW + 1) - resize(a_r, DW + 1))
                                                  * signed('0' & d_frac), 8), DW);
        when others => null;
      end case;
    end if;
  end process;

end architecture;
