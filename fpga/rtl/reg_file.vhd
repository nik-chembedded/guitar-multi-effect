-- -----------------------------------------------------------------------------
-- reg_file.vhd  (v2 step B3)
-- 16-bit control/status registers behind a simple bus, written by the HPS
-- through ctrl_avmm (Avalon-MM slave on the lightweight bridge).
--
--   0x00..0x0E  effect registers, same meaning as v1 (docs/register_map.md)   R/W
--   0x10        VERSION                                                        R
--   0x11        STATUS  (from status_in)                                       R
--   0x12        input  peak level                                              R
--   0x13        output peak level                                              R
--   0x14        CONTROL: bit0 = re-run codec init, bit1 = mute (level)         W, R
--               bit0 is a self-clearing pulse on codec_init
--   0x16..0x2F  extension registers (step D), R/W, all reaching the core on the
--               flat bus ext (register 0x16 + i = ext(16*i+15 downto 16*i)):
--               0x16 TREM_RATE, 0x18 MOD_BASE, 0x19 MOD_FB, 0x1A MOD_SHAPE, ...
--               (docs/register_map.md)
-- Any other address: err = '1' (read and write).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity reg_file is
  generic (
    VERSION : std_logic_vector(15 downto 0) := x"0204"
  );
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;
    -- bus
    addr       : in  std_logic_vector(7 downto 0);
    wdata      : in  std_logic_vector(15 downto 0);
    we         : in  std_logic;
    rdata      : out std_logic_vector(15 downto 0);
    err        : out std_logic;                          -- address not valid
    -- status inputs
    status_in  : in  std_logic_vector(15 downto 0);
    level_in   : in  std_logic_vector(15 downto 0);
    level_out  : in  std_logic_vector(15 downto 0);
    -- effect registers
    effects_enable : out std_logic_vector(15 downto 0);
    od_drive       : out std_logic_vector(15 downto 0);
    od_gain        : out std_logic_vector(15 downto 0);
    trem_wave      : out std_logic_vector(15 downto 0);
    trem_depth     : out std_logic_vector(15 downto 0);
    echo_time      : out std_logic_vector(15 downto 0);
    echo_repeat    : out std_logic_vector(15 downto 0);
    echo_level     : out std_logic_vector(15 downto 0);
    dist_mix       : out std_logic_vector(15 downto 0);
    dist_type      : out std_logic_vector(15 downto 0);
    chorus_level   : out std_logic_vector(15 downto 0);
    chorus_depth   : out std_logic_vector(15 downto 0);
    chorus_rate    : out std_logic_vector(15 downto 0);
    reverb_mix     : out std_logic_vector(15 downto 0);
    reverb_type    : out std_logic_vector(15 downto 0);
    ext            : out std_logic_vector(26 * 16 - 1 downto 0);   -- 0x16 .. 0x2F
    -- control
    codec_init     : out std_logic;                      -- 1-cycle pulse
    mute           : out std_logic
  );
end entity;

architecture rtl of reg_file is
  type regs_t is array (0 to 14) of std_logic_vector(15 downto 0);
  signal regs    : regs_t := (others => (others => '0'));
  signal control : std_logic_vector(15 downto 0) := (others => '0');
  constant EXT_LO : natural := 16#16#;
  constant EXT_HI : natural := 16#2F#;
  type ext_t is array (EXT_LO to EXT_HI) of std_logic_vector(15 downto 0);
  signal ext_r   : ext_t := (others => (others => '0'));
  signal init_p  : std_logic := '0';
begin

  process(clk)
    variable a : natural range 0 to 255;
  begin
    if rising_edge(clk) then
      init_p <= '0';
      if rst = '1' then
        regs    <= (others => (others => '0'));
        control <= (others => '0');
        ext_r   <= (others => (others => '0'));
      elsif we = '1' then
        a := to_integer(unsigned(addr));
        if a <= 14 then
          regs(a) <= wdata;
        elsif a = 16#14# then
          control <= wdata and x"0002";      -- bit0 is a pulse, not stored
          init_p  <= wdata(0);
        elsif a >= EXT_LO and a <= EXT_HI then
          ext_r(a) <= wdata;
        end if;
      end if;
    end if;
  end process;

  read_mux : process(addr, regs, status_in, level_in, level_out, control, ext_r)
    variable a : natural range 0 to 255;
  begin
    a     := to_integer(unsigned(addr));
    err   <= '0';
    rdata <= (others => '0');
    if a <= 14 then
      rdata <= regs(a);
    elsif a = 16#10# then
      rdata <= VERSION;
    elsif a = 16#11# then
      rdata <= status_in;
    elsif a = 16#12# then
      rdata <= level_in;
    elsif a = 16#13# then
      rdata <= level_out;
    elsif a = 16#14# then
      rdata <= control;
    elsif a >= EXT_LO and a <= EXT_HI then
      rdata <= ext_r(a);
    else
      err <= '1';
    end if;
  end process;

  effects_enable <= regs(0);
  od_drive       <= regs(1);
  od_gain        <= regs(2);
  trem_wave      <= regs(3);
  trem_depth     <= regs(4);
  echo_time      <= regs(5);
  echo_repeat    <= regs(6);
  echo_level     <= regs(7);
  dist_mix       <= regs(8);
  dist_type      <= regs(9);
  chorus_level   <= regs(10);
  chorus_depth   <= regs(11);
  chorus_rate    <= regs(12);
  reverb_mix     <= regs(13);
  reverb_type    <= regs(14);
  ext_out : for i in EXT_LO to EXT_HI generate
    ext(16 * (i - EXT_LO) + 15 downto 16 * (i - EXT_LO)) <= ext_r(i);
  end generate;
  codec_init     <= init_p;
  mute           <= control(1);

end architecture;
