-- -----------------------------------------------------------------------------
-- eq3.vhd  (v2 step D5b)
-- 3-band EQ: low shelf, peaking mid, high shelf in series, three biquad.vhd
-- sections (Direct Form I, 48-bit accumulator, first-order error feedback, each
-- section output saturated to DW). Coefficients come from the HPS
-- (tools/eq_coefs.py); the python model is sim/cocotb/eq3_model.py (bit-exact).
--
-- Coefficient write port (cw_en, cw_addr, cw_data):
--   addr 0..14   section * 5 + index (b0 b1 b2 a1 a2), signed 18 bit, Q2.16
--   addr 15      scale register, 2 bits per section (section 0 in bits 1:0): the
--                section's feed-forward sum is multiplied by 2^n, so the b coefficients
--                of a boosting shelf (b0 ~ 4 at a +12 dB high shelf) fit as b / 2^n
--                in the +-2 range of Q2.16
--   Writes only go to shadow registers. `apply` (one pulse, after the write burst)
--   marks them; at the next strobe all 15 coefficients + the scale register are copied
--   to the active set before that sample is computed, so a half-written set is never
--   used and the whole set (all three sections) changes at one sample boundary.
--   A cw write or an apply in the same clock as the strobe takes effect one sample later.
-- Power-up values: b0 = 1.0 (65536), all others 0, scale 0: transparent.
--
-- Per sample (strobe): the result is in data_out 7 clocks after the strobe
-- (1 input / coefficient latch, 2 per section x 3). With enable = 0, data_out <=
-- data_in at the strobe (registered like the other effects); the filters keep
-- running on the input so re-enabling is free of transients.
-- Multipliers: 15 (5 per section, 24 x 18 bit, one DSP block each, all parallel).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity eq3 is
  generic (
    DW : positive := 24
  );
  port (
    clk      : in  std_logic;
    strobe   : in  std_logic;                    -- once per sample
    enable   : in  std_logic;
    cw_en    : in  std_logic;
    cw_addr  : in  std_logic_vector(3 downto 0); -- 0..14 coefficient, 15 scale
    cw_data  : in  std_logic_vector(17 downto 0);
    apply    : in  std_logic;
    data_in  : in  std_logic_vector(DW - 1 downto 0);
    data_out : out std_logic_vector(DW - 1 downto 0) := (others => '0')
  );
end entity;

architecture rtl of eq3 is
  type coef_t is array (0 to 14) of signed(17 downto 0);

  function unity return coef_t is
    variable c : coef_t := (others => (others => '0'));
  begin
    for s in 0 to 2 loop
      c(s * 5) := to_signed(65536, 18);
    end loop;
    return c;
  end function;

  signal shadow, active : coef_t := unity;
  signal sc_shadow, sc_active : std_logic_vector(5 downto 0) := (others => '0');
  signal pend   : std_logic := '0';
  signal go1    : std_logic := '0';
  signal en_l   : std_logic := '1';
  signal xin    : signed(DW - 1 downto 0) := (others => '0');
  signal y1, y2, y3 : signed(DW - 1 downto 0);
  signal d1, d2, d3 : std_logic;
begin

  u1 : entity work.biquad
    generic map (DW => DW)
    port map (clk => clk, go => go1, x => xin,
              b0 => active(0), b1 => active(1), b2 => active(2), a1 => active(3), a2 => active(4),
              sh => unsigned(sc_active(1 downto 0)), y => y1, done => d1);
  u2 : entity work.biquad
    generic map (DW => DW)
    port map (clk => clk, go => d1, x => y1,
              b0 => active(5), b1 => active(6), b2 => active(7), a1 => active(8), a2 => active(9),
              sh => unsigned(sc_active(3 downto 2)), y => y2, done => d2);
  u3 : entity work.biquad
    generic map (DW => DW)
    port map (clk => clk, go => d2, x => y2,
              b0 => active(10), b1 => active(11), b2 => active(12), a1 => active(13), a2 => active(14),
              sh => unsigned(sc_active(5 downto 4)), y => y3, done => d3);

  process(clk)
    variable a : integer range 0 to 15;
  begin
    if rising_edge(clk) then
      -- coefficient write (shadow)
      if cw_en = '1' then
        a := to_integer(unsigned(cw_addr));
        if a < 15 then
          shadow(a) <= signed(cw_data);
        else
          sc_shadow <= cw_data(5 downto 0);
        end if;
      end if;

      go1 <= strobe;
      if strobe = '1' then
        if pend = '1' then                       -- atomic update at the sample boundary
          active    <= shadow;
          sc_active <= sc_shadow;
          pend      <= '0';
        end if;
        xin  <= signed(data_in);
        en_l <= enable;
        if enable = '0' then
          data_out <= data_in;
        end if;
      end if;
      if apply = '1' then
        pend <= '1';
      end if;

      if d3 = '1' and en_l = '1' then
        data_out <= std_logic_vector(y3);
      end if;
    end if;
  end process;

end architecture;
