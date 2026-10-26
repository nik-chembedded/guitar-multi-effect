-- -----------------------------------------------------------------------------
-- cab_stage.vhd  (v2 step D3)
-- Cabinet stage of the effect chain: cab_fir + click-free on/off + bank switch.
--
--   * cab_fir runs on every sample (start = sample_tick delayed by one clock:
--     the previous stage's output has been updated by the sample_tick edge), so
--     the history is always warm. Its output is one sample late (cab_fir header),
--     valid from start until the next start.
--   * dout = din + floor((wet - din) * g / 256), g = 0 .. 256, COMBINATIONAL from din:
--     g = 0 gives exactly din (cabinet off = the stage costs no latency, the
--     chain stays bit-exact to the chains without a cabinet), g = 256 gives
--     exactly wet. g moves once per sample_tick: +-1 for enable / disable
--     (256 samples, 5.3 ms), +-2 while the bank changes (128 samples).
--     fx_xfade is not used: its dry path is registered (one clock more latency).
--   * bank change (bank_req /= the bank in use): g fades to 0 in 128 samples, the
--     bank in use (cur) switches at g = 0, then g fades back to 256 in 128 samples
--     (only if the cabinet is enabled). XFADE = false: g and the bank jump.
--   * coefficient writes (cw_*) reach the RAM only for the bank that is neither in
--     use nor requested, so a playing cabinet is never disturbed; writes to the
--     active bank are ignored.
--   * shift (3 bits, per bank) is sampled by cab_fir at start together with the bank.
--
-- Per-clock pipeline (cab_fir): excluded from the multicycle relaxation in
-- top_v2.sdc (instance name CAB_left).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.cab_fir_pkg.all;

entity cab_stage is
  generic (
    DW        : positive := 24;
    TAPS      : positive := 2048;
    LANES     : positive := 4;
    XFADE     : boolean  := true;
    INIT_FILE : string   := "cab_default.mif"
  );
  port (
    clk         : in  std_logic;
    sample_tick : in  std_logic;
    enable      : in  std_logic;                     -- effect enable bit
    bank_req    : in  std_logic;                     -- requested bank (CAB_CTRL bit 0)
    shift0      : in  std_logic_vector(2 downto 0);  -- coefficient shift of bank 0
    shift1      : in  std_logic_vector(2 downto 0);
    cw_en       : in  std_logic;                     -- coefficient write
    cw_bank     : in  std_logic;
    cw_addr     : in  std_logic_vector(clog2(TAPS) - 1 downto 0);
    cw_data     : in  std_logic_vector(17 downto 0);
    din         : in  std_logic_vector(DW - 1 downto 0);
    dout        : out std_logic_vector(DW - 1 downto 0)
  );
end entity;

architecture rtl of cab_stage is
  signal start   : std_logic := '0';
  signal cur     : std_logic := '0';                 -- bank in use
  signal sw      : std_logic := '0';                 -- bank change in progress (fade steps of 2)
  signal g       : natural range 0 to 256 := 0;
  signal wet     : std_logic_vector(DW - 1 downto 0);
  signal shift   : std_logic_vector(2 downto 0);
  signal cw_ok   : std_logic;
  signal diff    : signed(DW downto 0);
  signal prod    : signed(DW + 10 downto 0);
begin

  shift <= shift1 when cur = '1' else shift0;
  cw_ok <= cw_en when (cw_bank /= cur and cw_bank /= bank_req) else '0';

  u_fir : entity work.cab_fir
    generic map (DW => DW, TAPS => TAPS, LANES => LANES, INIT_FILE => INIT_FILE)
    port map (clk => clk, start => start, data_in => din, data_out => wet,
              bank => cur, shift => shift,
              cw_en => cw_ok, cw_bank => cw_bank, cw_addr => cw_addr, cw_data => cw_data);

  process(clk)
    variable want_on : boolean;
    variable step    : natural range 1 to 2;
  begin
    if rising_edge(clk) then
      start <= sample_tick;
      if sample_tick = '1' then
        want_on := enable = '1' and bank_req = cur;
        if not XFADE then
          cur <= bank_req;
          if enable = '1' then g <= 256; else g <= 0; end if;
        else
          if sw = '1' then step := 2; else step := 1; end if;
          if want_on then
            if g + step >= 256 then g <= 256; else g <= g + step; end if;
          else
            if g <= step then g <= 0; else g <= g - step; end if;
          end if;
          if bank_req /= cur then
            sw <= '1';
            if g = 0 then
              cur <= bank_req;                       -- faded out: switch
            end if;
          elsif g = 256 or (enable = '0' and g = 0) then
            sw <= '0';
          end if;
        end if;
      end if;
    end if;
  end process;

  diff <= resize(signed(wet), DW + 1) - resize(signed(din), DW + 1);
  prod <= diff * signed('0' & to_unsigned(g, 9));
  dout <= std_logic_vector(resize(resize(signed(din), DW + 11) + shift_right(prod, 8), DW));

end architecture;
