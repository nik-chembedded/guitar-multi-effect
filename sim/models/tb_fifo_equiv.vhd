-- -----------------------------------------------------------------------------
-- tb_fifo_equiv.vhd
-- Equivalence test: Intel dcfifo (my_fifo, library "intel") vs sim_dcfifo
-- (library "model"). Random writes on wrclk, each FIFO read on an unrelated
-- rdclk whenever it is not empty. The flag timing differs by design (no
-- synchroniser pipeline in the model), so what is compared is the sequence of
-- data words read out, which must be identical.
-- -----------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;
library intel, model;

entity tb_fifo_equiv is
  generic (WORDS : positive := 3000);
end entity;

architecture sim of tb_fifo_equiv is
  signal wclk, rclk : std_logic := '0';
  signal done       : boolean := false;
  signal d          : std_logic_vector(15 downto 0) := (others => '0');
  signal wr         : std_logic := '0';
  signal qi, qm     : std_logic_vector(15 downto 0);
  signal ei, em     : std_logic;
  signal fi, fm     : std_logic;
  signal rdi, rdm   : std_logic;

  type seq_t is array (0 to WORDS - 1) of std_logic_vector(15 downto 0);
begin
  wclk <= not wclk after 5 ns when not done else '0';
  rclk <= not rclk after 13 ns when not done else '0';

  fi_i : entity intel.my_fifo port map (data => d, rdclk => rclk, rdreq => rdi, wrclk => wclk,
                                        wrreq => wr, q => qi, rdempty => ei, wrfull => fi);
  fm_i : entity model.my_fifo port map (data => d, rdclk => rclk, rdreq => rdm, wrclk => wclk,
                                        wrreq => wr, q => qm, rdempty => em, wrfull => fm);
  rdi <= not ei;
  rdm <= not em;

  writer : process
    variable s1 : positive := 11;
    variable s2 : positive := 23;
    variable r  : real;
    variable k  : natural := 0;
  begin
    while k < WORDS loop
      wait until rising_edge(wclk);
      wait for 1 ns;
      uniform(s1, s2, r);
      -- write only when neither FIFO is full, so both receive the same words
      if r < 0.4 and fi = '0' and fm = '0' then
        uniform(s1, s2, r);
        d  <= std_logic_vector(to_unsigned(integer(trunc(r * 65535.0)), 16));
        wr <= '1';
        k  := k + 1;
      else
        wr <= '0';
      end if;
    end loop;
    wait until rising_edge(wclk);
    wait for 1 ns;
    wr <= '0';
    wait;
  end process;

  -- non-showahead: the word appears on q after the read edge
  reader_check : process
    variable took_i, took_m : boolean;
    variable seq_i, seq_m   : seq_t;
    variable ni, nm         : natural := 0;
    variable errors         : natural := 0;
  begin
    while now < 200 us loop
      wait until rising_edge(rclk);
      took_i := rdi = '1';             -- request as seen by the FIFO on this edge
      took_m := rdm = '1';
      wait for 1 ns;
      if took_i and ni < WORDS then seq_i(ni) := qi; ni := ni + 1; end if;
      if took_m and nm < WORDS then seq_m(nm) := qm; nm := nm + 1; end if;
    end loop;
    for k in 0 to WORDS - 1 loop
      if k < ni and k < nm and seq_i(k) /= seq_m(k) then
        if errors < 10 then
          report "FIFO MISMATCH at word " & integer'image(k) severity error;
        end if;
        errors := errors + 1;
      end if;
    end loop;
    report "FIFO: intel read " & integer'image(ni) & " words, model read " & integer'image(nm)
           & ", " & integer'image(errors) & " mismatches";
    if errors = 0 and ni = WORDS and nm = WORDS then
      report "RESULT: PASS fifo_equiv";
    else
      report "RESULT: FAIL fifo_equiv";
    end if;
    done <= true;
    std.env.stop;
    wait;
  end process;
end architecture;
