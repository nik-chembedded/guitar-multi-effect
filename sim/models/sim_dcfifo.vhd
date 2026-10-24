-- -----------------------------------------------------------------------------
-- sim_dcfifo.vhd
-- Behavioural model of the Intel dcfifo used as my_fifo (normal, non-showahead
-- mode: q updates on the read clock edge where rdreq = '1').
-- The empty/full flags are computed from the shared fill level without the
-- synchroniser pipelines of the real FIFO. Only the timing of the flags differs
-- (by a few clocks); the data order is identical. Testbenches measure the
-- latency, so they are not affected.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;

entity sim_dcfifo is
  generic (
    WIDTH : positive;
    DEPTH : positive
  );
  port (
    data    : in  std_logic_vector(WIDTH - 1 downto 0);
    rdclk   : in  std_logic;
    rdreq   : in  std_logic;
    wrclk   : in  std_logic;
    wrreq   : in  std_logic;
    q       : out std_logic_vector(WIDTH - 1 downto 0);
    rdempty : out std_logic;
    wrfull  : out std_logic
  );
end entity;

architecture behav of sim_dcfifo is
  type mem_t is array (0 to DEPTH - 1) of std_logic_vector(WIDTH - 1 downto 0);
  signal mem    : mem_t := (others => (others => '0'));
  signal wr_cnt : natural := 0;   -- words written (monotonic)
  signal rd_cnt : natural := 0;   -- words read (monotonic)
  signal q_reg  : std_logic_vector(WIDTH - 1 downto 0) := (others => '0');
begin

  write_side : process(wrclk)
  begin
    if rising_edge(wrclk) then
      if wrreq = '1' and wr_cnt - rd_cnt < DEPTH then      -- overflow_checking ON
        mem(wr_cnt mod DEPTH) <= data;
        wr_cnt <= wr_cnt + 1;
      end if;
    end if;
  end process;

  read_side : process(rdclk)
  begin
    if rising_edge(rdclk) then
      if rdreq = '1' and wr_cnt > rd_cnt then              -- underflow_checking ON
        q_reg  <= mem(rd_cnt mod DEPTH);
        rd_cnt <= rd_cnt + 1;
      end if;
    end if;
  end process;

  q       <= q_reg;
  rdempty <= '1' when wr_cnt = rd_cnt else '0';
  wrfull  <= '1' when wr_cnt - rd_cnt >= DEPTH else '0';

end architecture;
