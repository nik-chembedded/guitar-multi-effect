-- route_wrap.vhd - fx_route with 9 stub effects, for test_route.py.
--
-- Effect e computes  fx_out(e) = (fx_in(e) + (e+1)*1000) * (2e+1)  modulo 2^DW. The odd multiplier makes the
-- stubs not commute, so the output depends on the order (a plain "+ (e+1)*1000" would give the same sum in any
-- order). Most stubs are COMBINATIONAL (the zero-latency bypass: a combinational loop without the slot
-- registers of fx_route); the ids in REG_IDS instead register their result on half_tick (like a real block).
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity route_wrap is
  generic (
    DW : positive := 24
  );
  port (
    clk          : in  std_logic;
    sample_tick  : in  std_logic;
    half_tick    : in  std_logic;
    order_in     : in  std_logic_vector(35 downto 0);
    apply        : in  std_logic;
    busy         : out std_logic;
    rejected     : out std_logic;
    order_active : out std_logic_vector(35 downto 0);
    chain_in     : in  std_logic_vector(DW - 1 downto 0);
    chain_out    : out std_logic_vector(DW - 1 downto 0)
  );
end entity;

architecture rtl of route_wrap is
  constant N : positive := 9;
  type int_set is array (natural range <>) of natural;
  constant REG_IDS : int_set := (1, 5, 7);          -- registered stubs (TREM, REVERB, DYN)

  function is_reg(e : natural) return boolean is
  begin
    for i in REG_IDS'range loop
      if REG_IDS(i) = e then
        return true;
      end if;
    end loop;
    return false;
  end function;

  signal fx_in  : std_logic_vector(N * DW - 1 downto 0);
  signal fx_out : std_logic_vector(N * DW - 1 downto 0);
begin

  u_route : entity work.fx_route
    generic map (DW => DW, N => N)
    port map (clk => clk, sample_tick => sample_tick, order_in => order_in, apply => apply,
              busy => busy, rejected => rejected, order_active => order_active,
              chain_in => chain_in, fx_out => fx_out, fx_in => fx_in, chain_out => chain_out);

  stubs : for e in 0 to N - 1 generate
    signal y : std_logic_vector(DW - 1 downto 0);
    signal r : std_logic_vector(DW - 1 downto 0) := (others => '0');
  begin
    y <= std_logic_vector(resize((unsigned(fx_in(e * DW + DW - 1 downto e * DW)) + to_unsigned((e + 1) * 1000, DW))
                                 * to_unsigned(2 * e + 1, 8), DW));
    comb : if not is_reg(e) generate
      fx_out(e * DW + DW - 1 downto e * DW) <= y;
    end generate;
    regd : if is_reg(e) generate
      process(clk)
      begin
        if rising_edge(clk) then
          if half_tick = '1' then
            r <= y;
          end if;
        end if;
      end process;
      fx_out(e * DW + DW - 1 downto e * DW) <= r;
    end generate;
  end generate;

end architecture;
