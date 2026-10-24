-- -----------------------------------------------------------------------------
-- codec_ctrl.vhd  (v2 step B4)
-- WM8731 configuration over I2C without a CPU:
--   * after reset (and on init_start) an init sequence from a ROM is written:
--     v2 settings - FPGA is I2S master, codec slave, 24-bit, 256 fs, 48 kHz
--   * afterwards host write requests (from ctrl_uart) are forwarded
-- I2C writes are 16 bits: (register << 9) | 9-bit data, device address 0x34.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity codec_ctrl is
  generic (
    I2C_DIV    : positive := 123;              -- quarter SCL period in clk cycles
    WAIT_CLKS  : positive := 491_520           -- pause before "active" (10 ms)
  );
  port (
    clk        : in  std_logic;
    rst        : in  std_logic;
    init_start : in  std_logic;                -- re-run the init sequence
    -- host requests (ctrl_uart)
    req        : in  std_logic;
    req_reg    : in  std_logic_vector(6 downto 0);
    req_data   : in  std_logic_vector(8 downto 0);
    busy       : out std_logic;                -- init running or transfer active
    done       : out std_logic;
    nak        : out std_logic;
    -- status
    init_done  : out std_logic;
    init_nak   : out std_logic;                -- a write of the init sequence was NAKed
    -- I2C pins (open drain)
    scl_oe     : out std_logic;
    sda_oe     : out std_logic;
    sda_in     : in  std_logic
  );
end entity;

architecture rtl of codec_ctrl is
  constant DEV : std_logic_vector(6 downto 0) := "0011010";   -- 0x1A (8-bit write address 0x34)

  -- (register, 9-bit data); register 16#7F# = wait WAIT_CLKS
  type init_t is array (natural range <>) of std_logic_vector(15 downto 0);
  function w(r : natural; d : natural) return std_logic_vector is
  begin
    return std_logic_vector(to_unsigned(r, 7)) & std_logic_vector(to_unsigned(d, 9));
  end function;
  constant INIT : init_t := (
    w(15, 16#000#),   -- R15 reset
    w( 9, 16#000#),   -- R9  inactive while configuring
    w( 0, 16#01A#),   -- R0  left line-in volume
    w( 1, 16#01A#),   -- R1  right line-in volume
    w( 2, 16#07A#),   -- R2  left headphone volume
    w( 3, 16#07A#),   -- R3  right headphone volume
    w( 4, 16#010#),   -- R4  analog path: DAC select, line input
    w( 5, 16#000#),   -- R5  digital path
    w( 6, 16#000#),   -- R6  power: all on
    w( 7, 16#00A#),   -- R7  interface: I2S, 24-bit, SLAVE (FPGA is master)
    w( 8, 16#000#),   -- R8  sampling: normal mode, 256 fs, 48 kHz (MCLK 12.288 MHz)
    w(16, 16#07B#),   -- R16 ALC control 1
    w(17, 16#032#),   -- R17 ALC control 2
    w(18, 16#000#),   -- R18 noise gate
    w(127, 0),        -- wait
    w( 9, 16#001#));  -- R9  active

  type state_t is (INIT_NEXT, INIT_XFER, INIT_WAIT, READY, HOST_XFER);
  signal state     : state_t := INIT_NEXT;
  signal idx       : natural range 0 to INIT'length := 0;
  signal wcnt      : natural range 0 to WAIT_CLKS := 0;
  signal m_start   : std_logic := '0';
  signal m_b1      : std_logic_vector(7 downto 0) := (others => '0');
  signal m_b2      : std_logic_vector(7 downto 0) := (others => '0');
  signal m_busy    : std_logic;
  signal m_done    : std_logic;
  signal m_nak     : std_logic;
  signal done_r    : std_logic := '0';
  signal nak_r     : std_logic := '0';
  signal idone_r   : std_logic := '0';
  signal inak_r    : std_logic := '0';
begin

  u_i2c : entity work.i2c_master
    generic map (DIV => I2C_DIV)
    port map (clk => clk, rst => rst, start => m_start, dev => DEV, byte1 => m_b1, byte2 => m_b2,
              busy => m_busy, done => m_done, nak => m_nak,
              scl_oe => scl_oe, sda_oe => sda_oe, sda_in => sda_in);

  process(clk)
    variable e : std_logic_vector(15 downto 0);
  begin
    if rising_edge(clk) then
      m_start <= '0';
      done_r  <= '0';
      if rst = '1' or init_start = '1' then
        state   <= INIT_NEXT;
        idx     <= 0;
        idone_r <= '0';
        inak_r  <= '0';
      else
        case state is
          when INIT_NEXT =>
            if idx = INIT'length then
              state   <= READY;
              idone_r <= '1';
            else
              e := INIT(idx);
              if e(15 downto 9) = "1111111" then
                wcnt  <= 0;
                state <= INIT_WAIT;
              elsif m_busy = '0' and m_start = '0' then
                m_b1    <= e(15 downto 8);              -- (reg << 1) | d8
                m_b2    <= e(7 downto 0);
                m_start <= '1';
                state   <= INIT_XFER;
              end if;
            end if;

          when INIT_XFER =>
            if m_done = '1' then
              if m_nak = '1' then inak_r <= '1'; end if;
              idx   <= idx + 1;
              state <= INIT_NEXT;
            end if;

          when INIT_WAIT =>
            if wcnt = WAIT_CLKS then
              idx   <= idx + 1;
              state <= INIT_NEXT;
            else
              wcnt <= wcnt + 1;
            end if;

          when READY =>
            if req = '1' then
              m_b1    <= req_reg & req_data(8);
              m_b2    <= req_data(7 downto 0);
              m_start <= '1';
              state   <= HOST_XFER;
            end if;

          when HOST_XFER =>
            if m_done = '1' then
              done_r <= '1';
              nak_r  <= m_nak;
              state  <= READY;
            end if;
        end case;
      end if;
    end if;
  end process;

  busy      <= '0' when state = READY else '1';
  done      <= done_r;
  nak       <= nak_r;
  init_done <= idone_r;
  init_nak  <= inak_r;

end architecture;
