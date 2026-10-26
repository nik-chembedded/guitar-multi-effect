-- -----------------------------------------------------------------------------
-- cab_fir.vhd  (v2 step D3)
-- Cabinet-simulator FIR filter: TAPS-tap convolution on LANES parallel MAC lanes
-- (one DW x 18-bit multiply per lane and clock), two coefficient banks.
--
--   y[n] = sat( floor( sum_{k=0..TAPS-1} h_bank[k] * x[n-k] / 2^(17+shift) ), DW )
--
-- x = DW-bit signed samples (history starts as zeros), h = 18-bit signed
-- coefficients (Q1.17 scaled up by 2^shift, block floating point, see
-- tools/cab_coefs.py), exact accumulator (no intermediate rounding), one floor
-- rounding and one saturation at the end.
--
-- TIMING
--   start     1-cycle strobe, once per sample. At that clock edge x[n] = data_in
--             is written into the history, bank and shift are sampled, and
--             data_out is loaded with y[n-1]: ONE SAMPLE LATENCY, registered.
--   data_out  = y[n-1] from the start strobe of sample n until the next one
--             (0 before the first result). y[n] is computed in the following
--             TAPS/LANES + 6 clock edges (the internal result register "res" is
--             loaded TAPS/LANES + 6 edges after the start edge) and waits there
--             until the next start. The next start must come at least
--             TAPS/LANES + 7 clocks after this one: 519 of the 1024 clocks per
--             sample for TAPS = 2048 / LANES = 4, 11 for TAPS = 16 / LANES = 4.
--   bank, shift  sampled at start (apply to the y[n] started there).
--   cw_*      coefficient write, any time, one coefficient per clock into
--             bank cw_bank (do not write the bank in use during a computation:
--             the result of that sample would be undefined). Bank 0 is loaded
--             from INIT_FILE at power-up, bank 1 starts at 0.
--
-- STRUCTURE (interleaved lanes)
--   sample m is stored in history RAM (m mod LANES) at address (m / LANES) mod
--   TPL (TPL = TAPS / LANES). Lane l computes the taps k with
--   (n - k) mod LANES = l, i.e. k = r + LANES * j, r = (n - l) mod LANES, j =
--   0..TPL-1: it reads one history word per clock (address walks down) and the
--   coefficient field r of the wide coefficient RAM word j (cab_coef_ram: one
--   read = LANES consecutive coefficients, the same address for all lanes, a
--   LANES:1 field selector per lane). One 18-bit .mif of 2*TAPS words (bank 0, then zeros)
--   initialises the RAM.
--   pipeline (j = tap index within the lane, edge E0 = start edge):
--     address of word j after E(j), RAM output after E(j+2), operand
--     registers E(j+3), product E(j+4), accumulate E(j+5); lane sum E(TPL+5),
--     shift + saturate into res E(TPL+6).
--   accumulator DW + 18 + log2(TAPS) bits (53 for 24 bit / 2048 taps).
--
-- RESOURCES (DW 24, TAPS 2048, LANES 4): 4 multipliers 24 x 18, history 4 x
-- (512 x 24) bits, coefficients 2 x 2048 x 18 bit (as 1024 x 72 on the read side).
-- Python model: sim/cocotb/cabfir_model.py (bit-exact).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package cab_fir_pkg is
  function clog2(n : positive) return natural;
end package;

package body cab_fir_pkg is
  function clog2(n : positive) return natural is
    variable r : natural := 0;
    variable v : positive := 1;
  begin
    while v < n loop
      v := v * 2;
      r := r + 1;
    end loop;
    return r;
  end function;
end package body;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fx_pkg.all;
use work.cab_fir_pkg.all;

entity cab_fir is
  generic (
    DW        : positive := 24;
    TAPS      : positive := 2048;               -- power of two
    LANES     : positive := 4;                  -- power of two, >= 2, TAPS / LANES taps per lane
    INIT_FILE : string   := "cab_default.mif"   -- bank 0 power-up coefficients (18-bit .mif)
  );
  port (
    clk      : in  std_logic;
    start    : in  std_logic;                   -- once per sample
    data_in  : in  std_logic_vector(DW - 1 downto 0);
    data_out : out std_logic_vector(DW - 1 downto 0) := (others => '0');
    bank     : in  std_logic;                   -- active coefficient bank (sampled at start)
    shift    : in  std_logic_vector(2 downto 0);  -- coefficient scale 2^shift (sampled at start)
    cw_en    : in  std_logic;                   -- coefficient write
    cw_bank  : in  std_logic;
    cw_addr  : in  std_logic_vector(clog2(TAPS) - 1 downto 0);
    cw_data  : in  std_logic_vector(17 downto 0)
  );
end entity;

architecture rtl of cab_fir is
  constant CW   : positive := 18;
  constant LL   : positive := clog2(LANES);
  constant TL   : positive := clog2(TAPS);
  constant HL   : positive := TL - LL;                -- address bits per lane
  constant TPL  : positive := TAPS / LANES;
  constant ACCW : positive := DW + CW + TL;

  type hq_t  is array (0 to LANES - 1) of std_logic_vector(DW - 1 downto 0);
  type ra_t  is array (0 to LANES - 1) of unsigned(HL - 1 downto 0);
  type rs_t  is array (0 to LANES - 1) of unsigned(LL - 1 downto 0);
  type h_t   is array (0 to LANES - 1) of signed(DW - 1 downto 0);
  type c_t   is array (0 to LANES - 1) of signed(CW - 1 downto 0);
  type p_t   is array (0 to LANES - 1) of signed(DW + CW - 1 downto 0);
  type acc_t is array (0 to LANES - 1) of signed(ACCW - 1 downto 0);

  signal cnt    : unsigned(TL - 1 downto 0) := (others => '0');   -- n mod TAPS
  signal b_cur  : unsigned(LL - 1 downto 0);
  signal a_cur  : unsigned(HL - 1 downto 0);
  signal wen    : std_logic_vector(LANES - 1 downto 0);
  signal hq     : hq_t;
  signal hra    : ra_t := (others => (others => '0'));
  signal cq     : std_logic_vector(CW * LANES - 1 downto 0);
  signal ca     : unsigned(HL - 1 downto 0) := (others => '0');
  signal cbank  : std_logic := '0';
  signal rsel   : rs_t := (others => (others => '0'));
  signal shift_s: unsigned(2 downto 0) := (others => '0');

  signal iss    : std_logic := '0';                   -- addresses on the RAMs are valid
  signal jleft  : natural range 0 to TPL - 1 := 0;
  signal v      : std_logic_vector(1 to 5) := (others => '0');
  signal lst    : std_logic_vector(1 to 6) := (others => '0');

  signal h_r    : h_t := (others => (others => '0'));
  signal c_r    : c_t := (others => (others => '0'));
  signal p_r    : p_t := (others => (others => '0'));
  signal acc    : acc_t := (others => (others => '0'));
  signal tot    : signed(ACCW - 1 downto 0) := (others => '0');
  signal res    : signed(DW - 1 downto 0) := (others => '0');
begin

  assert LANES >= 2 and LANES < TAPS report "cab_fir: need 2 <= LANES < TAPS" severity failure;
  assert 2 ** LL = LANES and 2 ** TL = TAPS report "cab_fir: TAPS and LANES must be powers of two"
    severity failure;

  b_cur <= cnt(LL - 1 downto 0);
  a_cur <= cnt(TL - 1 downto LL);

  g_lane : for l in 0 to LANES - 1 generate
    wen(l) <= start when to_integer(b_cur) = l else '0';
    u_hist : entity work.fx_dpram
      generic map (WIDTH => DW, ADDR_W => HL)
      port map (clock => clk, clocken => '1', data => data_in,
                rdaddress => std_logic_vector(hra(l)), wraddress => std_logic_vector(a_cur),
                wren => wen(l), q => hq(l));
  end generate;

  u_coef : entity work.cab_coef_ram
    generic map (WIDTH => CW, LANES_LOG2 => LL, ADDR_W => TL + 1, INIT_FILE => INIT_FILE)
    port map (clock => clk, wren => cw_en, wraddress => cw_bank & cw_addr, data => cw_data,
              rdaddress => cbank & std_logic_vector(ca), q => cq);

  process(clk)
    variable s       : signed(ACCW - 1 downto 0);
    variable last_now: std_logic;
  begin
    if rising_edge(clk) then
      -- address sequencer; valid flags travel down the pipeline with the data
      last_now := '0';
      if iss = '1' and jleft = 0 then
        last_now := '1';
      end if;
      v   <= iss & v(1 to 4);
      lst <= last_now & lst(1 to 5);
      if iss = '1' then
        ca <= ca + 1;
        for l in 0 to LANES - 1 loop
          hra(l) <= hra(l) - 1;
        end loop;
        if jleft = 0 then
          iss <= '0';
        else
          jleft <= jleft - 1;
        end if;
      end if;

      -- operand registers (RAM output valid), product, accumulate
      for l in 0 to LANES - 1 loop
        h_r(l) <= signed(hq(l));
        for c in 0 to LANES - 1 loop
          if to_integer(rsel(l)) = c then
            c_r(l) <= signed(cq(CW * (c + 1) - 1 downto CW * c));
          end if;
        end loop;
        p_r(l) <= h_r(l) * c_r(l);
        if v(4) = '1' then
          acc(l) <= acc(l) + resize(p_r(l), ACCW);
        end if;
      end loop;

      -- lane sum, then scale + saturate
      if lst(5) = '1' then
        s := (others => '0');
        for l in 0 to LANES - 1 loop
          s := s + acc(l);
        end loop;
        tot <= s;
      end if;
      if lst(6) = '1' then
        res <= sat(shift_right(tot, 17 + to_integer(shift_s)), DW);
      end if;

      -- new sample
      if start = '1' then
        data_out <= std_logic_vector(res);
        cnt      <= cnt + 1;
        cbank    <= bank;
        shift_s  <= unsigned(shift);
        ca       <= (others => '0');
        iss      <= '1';
        jleft    <= TPL - 1;
        for l in 0 to LANES - 1 loop
          if to_unsigned(l, LL) > b_cur then
            hra(l) <= a_cur - 1;                    -- lanes above the newest sample's lane
          else
            hra(l) <= a_cur;
          end if;
          rsel(l) <= b_cur - to_unsigned(l, LL);    -- coefficient field (n - l) mod LANES
          acc(l)  <= (others => '0');
        end loop;
      end if;
    end if;
  end process;

end architecture;
