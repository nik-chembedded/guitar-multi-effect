-- -----------------------------------------------------------------------------
-- echo.vhd
-- Delay line up to 32767 samples (~0.68 s) with feedback:
--   out      = dry + level * delayed / 65536
--   feedback = dry + repeat * delayed / 256   (written into the delay line)
-- so echo n has amplitude level * repeat^(n-1) * x. DW-bit samples and delay
-- line (step C). The line is 2^AW words: 32 k by default (v1 had 64 k, of which
-- the 15-bit echo_time register only reached half). The size only matters for
-- echo_time = 0 (read = write address returns the word one ring ago), so the v1
-- reference test uses AW = 16.
--
-- Step D2: fractional delay. e_frac (1/256 sample, from the smoothed echo time)
-- interpolates linearly between the word at e_time (A) and the one before (B):
-- turning the time glides like a tape echo instead of clicking. The RAM runs on
-- every clock: A is read at the strobe edge itself (same address timing and
-- OLD_DATA behaviour as v1's strobe-clocked RAM), B one clock later; the result
-- is used two strobes later, as v1 used its RAM output. With e_frac = 0 the echo
-- is bit-exact to v1 (DW = 16).
-- -----------------------------------------------------------------------------
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.numeric_std.all;
use work.fx_pkg.all;

entity echo is
generic (
		DW : positive := 16;                        -- sample width (16 or 24)
		AW : positive := 15                         -- delay line 2^AW words (15..16)
);
port(
		clk  : in std_logic;   -- system clock (v2 B1)
		en_rise  : in std_logic;   -- strobe: v1 rising edge of this effect's sample clock
		en_fall  : in std_logic;   -- strobe: v1 falling edge
		echo_enable   : in std_logic;

		e_time			: in std_logic_vector(15 downto 0);
		e_frac			: in std_logic_vector(7 downto 0) := (others => '0');   -- 1/256 sample (D2)
      e_level			: in std_logic_vector(15 downto 0);
		e_repeat			: in std_logic_vector(15 downto 0);

		data_in       : in std_logic_vector(DW - 1 downto 0);
		data_out       : out std_logic_vector(DW - 1 downto 0) := (others => '0')   -- power-up 0 (sim: no X before the first strobe)
);
end entity;

architecture rtl of echo is

signal write_pointer : unsigned(AW - 1 downto 0) := (others => '0');
signal addr_a        : unsigned(AW - 1 downto 0);
signal addr_a_l      : unsigned(AW - 1 downto 0) := (others => '0');
signal rd_addr       : unsigned(AW - 1 downto 0);
signal q             : std_logic_vector(DW - 1 downto 0);
signal phase         : natural range 0 to 3 := 3;           -- clocks since the strobe
signal frac_l        : unsigned(7 downto 0) := (others => '0');
signal cap_a         : signed(DW - 1 downto 0) := (others => '0');
signal cap           : signed(DW - 1 downto 0) := (others => '0');   -- interpolated read of this strobe
signal hold          : signed(DW - 1 downto 0) := (others => '0');   -- ... of the previous strobe

signal delayed          : signed(DW - 1 downto 0);             -- v1: the RAM output
signal data_divided     : signed(DW - 1 downto 0);             -- level * delayed / 65536
signal rep_result_div   : signed(DW - 1 downto 0);             -- repeat * delayed / 256
signal data_in_feedback : std_logic_vector(DW - 1 downto 0);

begin

COUNTER_PROC: 	process(clk)
				begin
				 if rising_edge(clk) and en_fall = '1' then -- falling because it is left channel '0'
				    write_pointer <= write_pointer + 1;
				 end if;
				end process;

				-- A: e_time samples back (registered by the RAM at the strobe edge); B: one more
				addr_a  <= write_pointer - resize(unsigned(e_time(14 downto 0)), AW);
				rd_addr <= addr_a_l - 1 when phase = 0 else addr_a;

DELAY_RAM :     entity work.fx_dpram generic map (WIDTH => DW, ADDR_W => AW) port map(
								clock	  => clk,
								clocken	  => '1',
								data 	  => data_in_feedback,
								rdaddress => std_logic_vector(rd_addr),
								wraddress => std_logic_vector(write_pointer),
								wren	  => en_rise,
								q         => q
								 );

				-- read pipeline: strobe edge reads A, +1 reads B, +2 captures A, +3 interpolates
				process(clk)
				begin
				  if rising_edge(clk) then
				    if en_rise = '1' then
				      addr_a_l <= addr_a;
				      frac_l   <= unsigned(e_frac);
				      hold     <= cap;
				      phase    <= 0;
				    elsif phase /= 3 then
				      phase <= phase + 1;
				    end if;
				    if phase = 1 then
				      cap_a <= signed(q);
				    elsif phase = 2 then
				      cap <= resize(cap_a + shift_right((resize(signed(q), DW + 1) - resize(cap_a, DW + 1))
				                                        * signed('0' & frac_l), 8), DW);
				    end if;
				  end if;
				end process;

				delayed <= hold;

						data_divided   <= resize(mul_shr(delayed, unsigned(e_level), 16), DW);
						rep_result_div <= resize(mul_shr(delayed, unsigned(e_repeat(7 downto 0)), 8), DW);
						data_in_feedback <= std_logic_vector(add_sat(rep_result_div, signed(data_in), DW));

	 	 process(clk)
	    begin
		  if rising_edge(clk) and en_rise = '1' then
			if(echo_enable = '1') then
				 -- dry + level * delayed (the feedback path is not added to the output twice)
				 data_out <= std_logic_vector(add_sat(data_divided, signed(data_in), DW));
			else
				 data_out <= data_in;
			end if;
		end if;
	 end process;

end rtl;
