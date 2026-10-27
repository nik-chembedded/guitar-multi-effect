-- -----------------------------------------------------------------------------
-- fx_route.vhd  (v2 step E1)
-- Run-time effect order: per-effect slot registers + source muxes + order fade.
--
--   * Effect ids (= the enable bits of register 0): 0 OD, 1 TREM, 2 ECHO, 3 DIST,
--     4 MOD, 5 REVERB, 6 CAB, 7 DYN, 8 EQ. An order is a list of N nibbles, slot 0
--     in bits 3:0, each nibble the id of the effect in that slot.
--   * fx_out(e) is the output of effect e (after its own crossfade / bypass), fx_in(e)
--     its input. Effects may pass din -> dout combinationally (bypass, g = 0), so
--     every route must start at a register: slot_q(e) <= fx_out(e) at every
--     sample_tick, and fx_in(e) is a mux over {chain_in, slot_q(0..N-1)} selected by
--     registers only (src, last). No combinational loop can exist, in any order.
--     Each hop costs one frame; the latency is the same for every order.
--   * src(e) = the effect before e in the list (N = chain_in for slot 0); last = the
--     effect in slot N-1. Both are registers, computed from the active list at the
--     moment of the switch.
--   * apply (1-clock pulse): order_in is checked, all nibbles in 0 .. N-1 and every id
--     once. Not a permutation: rejected = 1, nothing else changes (a running fade
--     goes on). A permutation: rejected = 0, it becomes the pending list and the output
--     fade starts: g (0 .. 128) falls by 1 per sample_tick to 0, at the tick where it
--     reaches 0 the active list / src / last switch, then g rises by 1 per tick to 128.
--     busy = 1 from the apply until g is back at 128. An apply during the fade replaces
--     the pending list; during the rise the fade turns around and falls from the
--     current g (no jump) to the switch to the newest list. order_in alone changes nothing.
--   * chain_out = floor(slot_q(last) * g / 128) (arithmetic shift of the whole product):
--     exactly slot_q(last) at g = 128.
--   * Power-up (no reset, signal initial values): DEFAULT_ORDER active, g = 128, busy = 0.
--   * Everything advances per sample_tick, the pulse-wide apply is taken at any clock, so
--     the behaviour does not depend on the number of clocks per frame. A tick and an apply
--     in the same clock act as the apply one clock earlier.
--   * Limit: N <= 16 (4-bit ids).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity fx_route is
  generic (
    DW            : positive := 16;
    N             : positive := 9;
    -- 4 bits per slot, slot 0 in bits 3:0: DYN OD DIST CAB EQ MOD TREM ECHO REVERB
    DEFAULT_ORDER : std_logic_vector := x"521486307"
  );
  port (
    clk          : in  std_logic;
    sample_tick  : in  std_logic;                                -- 1-clock strobe per frame
    order_in     : in  std_logic_vector(4 * N - 1 downto 0);     -- shadow list (registers 0x30..0x32 in E2)
    apply        : in  std_logic;                                -- 1-clock pulse (write to CHAIN_APPLY 0x33)
    busy         : out std_logic;                                -- an order change (fade) is running
    rejected     : out std_logic;                                -- the last applied list was not a permutation
    order_active : out std_logic_vector(4 * N - 1 downto 0);     -- the list in use (read-back / debug)
    chain_in     : in  std_logic_vector(DW - 1 downto 0);        -- chain input sample
    fx_out       : in  std_logic_vector(N * DW - 1 downto 0);    -- output of effect e, bits e*DW+DW-1 .. e*DW
    fx_in        : out std_logic_vector(N * DW - 1 downto 0);    -- input of effect e
    chain_out    : out std_logic_vector(DW - 1 downto 0)
  );
end entity;

architecture rtl of fx_route is
  subtype list_t is std_logic_vector(4 * N - 1 downto 0);
  type slot_array is array (0 to N - 1) of std_logic_vector(DW - 1 downto 0);
  type src_array is array (0 to N - 1) of natural range 0 to N;

  constant DEF : list_t := DEFAULT_ORDER;

  function nib(l : list_t; k : natural) return natural is
  begin
    return to_integer(unsigned(l(4 * k + 3 downto 4 * k)));
  end function;

  -- every id 0 .. N-1 exactly once
  function is_perm(l : list_t) return boolean is
    variable seen : std_logic_vector(15 downto 0) := (others => '0');
    variable v    : natural;
  begin
    for k in 0 to N - 1 loop
      v := nib(l, k);
      if v >= N or seen(v) = '1' then
        return false;
      end if;
      seen(v) := '1';
    end loop;
    return true;
  end function;

  -- source of every effect: the effect in the previous slot, N (chain input) for slot 0
  function make_src(l : list_t) return src_array is
    variable s : src_array := (others => N);
  begin
    for k in 0 to N - 1 loop
      if k > 0 then
        s(nib(l, k)) := nib(l, k - 1);
      end if;
    end loop;
    return s;
  end function;

  signal slot_q : slot_array := (others => (others => '0'));
  signal active : list_t := DEF;
  signal pend   : list_t := DEF;
  signal src    : src_array := make_src(DEF);
  signal last   : natural range 0 to N - 1 := nib(DEF, N - 1);
  signal g      : natural range 0 to 128 := 128;      -- output gain, 128 = 1.0
  signal dn     : std_logic := '0';                   -- fading down towards the switch
  signal busy_r : std_logic := '0';
  signal rej_r  : std_logic := '0';
  signal prod   : signed(DW + 8 downto 0);
begin

  busy         <= busy_r;
  rejected     <= rej_r;
  order_active <= active;

  g_in : for e in 0 to N - 1 generate
    fx_in(e * DW + DW - 1 downto e * DW) <= chain_in when src(e) = N else slot_q(src(e));
  end generate;

  process(clk)
    variable dn_v   : std_logic;
    variable pend_v : list_t;
  begin
    if rising_edge(clk) then
      dn_v   := dn;
      pend_v := pend;
      if apply = '1' then
        if is_perm(order_in) then
          rej_r  <= '0';
          pend_v := order_in;
          dn_v   := '1';
          busy_r <= '1';
        else
          rej_r <= '1';
        end if;
      end if;
      if sample_tick = '1' then
        for e in 0 to N - 1 loop
          slot_q(e) <= fx_out(e * DW + DW - 1 downto e * DW);
        end loop;
        if dn_v = '1' then
          if g <= 1 then                                  -- faded out: switch
            g      <= 0;
            active <= pend_v;
            src    <= make_src(pend_v);
            last   <= nib(pend_v, N - 1);
            dn_v   := '0';
          else
            g <= g - 1;
          end if;
        elsif g < 128 then
          g <= g + 1;
          if g = 127 then
            busy_r <= '0';
          end if;
        end if;
      end if;
      dn   <= dn_v;
      pend <= pend_v;
    end if;
  end process;

  prod      <= signed(slot_q(last)) * signed('0' & to_unsigned(g, 8));
  chain_out <= std_logic_vector(resize(shift_right(prod, 7), DW));

end architecture;
