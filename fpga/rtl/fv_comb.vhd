-- -----------------------------------------------------------------------------
-- fv_comb.vhd  (v2 step D4)
-- Freeverb lowpass-feedback comb filter, one delay line.
--   out   = line[n - LEN]                       (loop delay = exactly LEN samples)
--   store = store + ((out - store) * (256 - d)) >> 8     (= out*(256-d) + store*d, >> 8)
--   line[n] = sat(x[n] + trunc(store * fb / 2^16))   trunc = toward zero (div_pow2): the
--             tail decays to exactly 0; floor would leave a -1 LSB limit cycle
-- The block is driven by the parent's stage pulses: after a sample strobe the RAM
-- delivers `out` 2 clocks after the new read address (wp - LEN, combinational from
-- the shared write pointer wp); st_a updates the damping store from `out`, st_b
-- computes the feedback term. The feedback term is registered, so the write data
-- at the next strobe is just x + fbv (one adder).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.fx_pkg.all;

entity fv_comb is
  generic (
    DW  : positive := 16;
    LEN : positive := 1215                      -- loop delay in samples (< 2048)
  );
  port (
    clk   : in  std_logic;
    wr_en : in  std_logic;                      -- write the line (strobe and enable)
    st_a  : in  std_logic;                      -- stage pulse: damping store update
    st_b  : in  std_logic;                      -- stage pulse: feedback term
    wp    : in  unsigned(10 downto 0);          -- shared write pointer
    xin   : in  signed(DW - 1 downto 0);        -- scaled input sample
    damp  : in  unsigned(7 downto 0);
    fb    : in  unsigned(15 downto 0);          -- Q0.16, already clamped
    y     : out signed(DW - 1 downto 0)         -- delay line output (valid from stage 3)
  );
end entity;

architecture rtl of fv_comb is
  signal rd_addr : unsigned(10 downto 0);
  signal q       : std_logic_vector(DW - 1 downto 0);
  signal wr_data : std_logic_vector(DW - 1 downto 0);
  signal store   : signed(DW - 1 downto 0) := (others => '0');
  signal fbv     : signed(DW - 1 downto 0) := (others => '0');
begin

  rd_addr <= wp - to_unsigned(LEN, 11);
  wr_data <= std_logic_vector(add_sat(xin, fbv, DW));
  y       <= signed(q);

  u_line : entity work.fx_dpram
    generic map (WIDTH => DW, ADDR_W => 11)
    port map (clock => clk, clocken => '1', data => wr_data,
              rdaddress => std_logic_vector(rd_addr), wraddress => std_logic_vector(wp),
              wren => wr_en, q => q);

  process(clk)
    variable diff : signed(DW downto 0);
    variable k    : signed(9 downto 0);
    variable p    : signed(DW + 10 downto 0);
    variable pr   : signed(DW + 16 downto 0);
  begin
    if rising_edge(clk) then
      if st_a = '1' then
        diff := resize(signed(q), DW + 1) - resize(store, DW + 1);
        k    := signed('0' & (to_unsigned(256, 9) - resize(damp, 9)));   -- 256 - d = 1 .. 256
        p    := smul_shr(diff, k, 8);                                     -- floor
        store <= resize(resize(store, DW + 11) + p, DW);                  -- convex: stays in range
      end if;
      if st_b = '1' then
        pr  := store * signed('0' & fb);
        fbv <= resize(div_pow2(pr, 16), DW);                              -- toward zero (tail decays to 0)
      end if;
    end if;
  end process;

end architecture;
