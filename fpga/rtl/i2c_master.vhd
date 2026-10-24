-- -----------------------------------------------------------------------------
-- i2c_master.vhd  (v2 step B4)
-- Write-only I2C master for the WM8731: one transfer = START, device address
-- (write), byte 1, byte 2, STOP. Every byte must be ACKed, otherwise nak = '1'.
-- Open-drain outputs: *_oe = '1' pulls the line low, '0' releases it.
-- Bit timing: 4 quarter phases per SCL period from a clk / DIV enable
-- (DIV = 123 at 49.152 MHz -> SCL 99.9 kHz).
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity i2c_master is
  generic (
    DIV : positive := 123                          -- clk cycles per quarter SCL period
  );
  port (
    clk    : in  std_logic;
    rst    : in  std_logic;
    start  : in  std_logic;                        -- 1-cycle pulse when busy = '0'
    dev    : in  std_logic_vector(6 downto 0);     -- 7-bit device address
    byte1  : in  std_logic_vector(7 downto 0);
    byte2  : in  std_logic_vector(7 downto 0);
    busy   : out std_logic;
    done   : out std_logic;                        -- 1-cycle pulse at the end
    nak    : out std_logic;                        -- valid with done
    scl_oe : out std_logic;
    sda_oe : out std_logic;
    sda_in : in  std_logic
  );
end entity;

architecture rtl of i2c_master is
  type state_t is (IDLE, S_START, S_BIT, S_ACK, S_STOP);
  signal state  : state_t := IDLE;
  signal qcnt   : natural range 0 to DIV - 1 := 0;
  signal q      : natural range 0 to 3 := 0;      -- quarter phase
  signal shreg  : std_logic_vector(23 downto 0) := (others => '0');
  signal nbit   : natural range 0 to 7 := 0;
  signal nbyte  : natural range 0 to 2 := 0;
  signal scl_l  : std_logic := '0';               -- '1' = pull SCL low
  signal sda_l  : std_logic := '0';
  signal nak_r  : std_logic := '0';
  signal done_r : std_logic := '0';
begin

  process(clk)
    variable tick : boolean;
  begin
    if rising_edge(clk) then
      done_r <= '0';
      tick   := qcnt = DIV - 1;
      if tick then qcnt <= 0; else qcnt <= qcnt + 1; end if;

      if rst = '1' then
        state <= IDLE;
        scl_l <= '0';
        sda_l <= '0';
        q     <= 0;
      else
        case state is
          when IDLE =>
            scl_l <= '0';
            sda_l <= '0';
            if start = '1' then
              shreg <= dev & '0' & byte1 & byte2;
              nak_r <= '0';
              nbyte <= 0;
              nbit  <= 0;
              q     <= 0;
              qcnt  <= 0;
              state <= S_START;
            end if;

          when S_START =>                        -- SDA falls while SCL is high
            if tick then
              case q is
                when 0 => sda_l <= '1';          -- START condition
                when 1 => null;
                when 2 => scl_l <= '1';          -- SCL low, ready for bit 7
                when others => null;
              end case;
              if q = 3 then q <= 0; state <= S_BIT; else q <= q + 1; end if;
            end if;

          when S_BIT =>                          -- q0: set SDA, q1: SCL high, q3: SCL low
            if tick then
              case q is
                when 0 => sda_l <= not shreg(23);
                when 1 => scl_l <= '0';
                when 2 => null;
                when others => scl_l <= '1';
              end case;
              if q = 3 then
                q     <= 0;
                shreg <= shreg(22 downto 0) & '0';
                if nbit = 7 then
                  nbit  <= 0;
                  state <= S_ACK;
                else
                  nbit <= nbit + 1;
                end if;
              else
                q <= q + 1;
              end if;
            end if;

          when S_ACK =>                          -- release SDA, sample it while SCL is high
            if tick then
              case q is
                when 0 => sda_l <= '0';
                when 1 => scl_l <= '0';
                when 2 => if sda_in = '1' then nak_r <= '1'; end if;
                when others => scl_l <= '1';
              end case;
              if q = 3 then
                q <= 0;
                if nbyte = 2 then
                  state <= S_STOP;
                else
                  nbyte <= nbyte + 1;
                  state <= S_BIT;
                end if;
              else
                q <= q + 1;
              end if;
            end if;

          when S_STOP =>                         -- SDA rises while SCL is high
            if tick then
              case q is
                when 0 => sda_l <= '1';
                when 1 => scl_l <= '0';
                when 2 => sda_l <= '0';          -- STOP condition
                when others => null;
              end case;
              if q = 3 then
                q      <= 0;
                state  <= IDLE;
                done_r <= '1';
              else
                q <= q + 1;
              end if;
            end if;
        end case;
      end if;
    end if;
  end process;

  busy   <= '0' when state = IDLE else '1';
  done   <= done_r;
  nak    <= nak_r;
  scl_oe <= scl_l;
  sda_oe <= sda_l;

end architecture;
