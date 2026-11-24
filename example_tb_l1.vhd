library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;
use IEEE.STD_LOGIC_TEXTIO.ALL;
library STD;
use STD.TEXTIO.ALL;

entity tb_layer1 is
end tb_layer1;

architecture Behavioral of tb_layer1 is

    -- Clock period definition (100 MHz)
    constant CLK_PERIOD : time := 10 ns;

    -- UUT signals
    signal clk       : std_logic := '0';
    signal l1_valid  : std_logic;
    signal tb_h_addr : std_logic_vector(5 downto 0) := (others => '0');
    signal tb_h_do   : unsigned(15 downto 0);

    -- Golden reference storage (64 neurons x 16-bit unsigned values)
    type GoldenType is array (0 to 63) of unsigned(15 downto 0);

    impure function LoadGoldenFile (FileName : in string) return GoldenType is
        file GoldenFile     : text is in FileName;
        variable LineBuffer : line;
        variable TempVec    : std_logic_vector(15 downto 0);
        variable Result     : GoldenType;
    begin
        for I in GoldenType'range loop
            readline(GoldenFile, LineBuffer);
            hread(LineBuffer, TempVec); -- Reads 4 hex characters per line (requires VHDL-2008)
            Result(I) := unsigned(TempVec);
        end loop;
        return Result;
    end function;

    -- Replace "golden_h_img0.mem" with your exact golden filename
    constant GOLDEN_H : GoldenType := LoadGoldenFile("golden_h_img0.mem");

begin

    -- Instantiate Unit Under Test (UUT)
    uut : entity work.layer1(Behavioral)
        port map (
            clk       => clk,
            l1_valid  => l1_valid,
            tb_h_addr => tb_h_addr,
            tb_h_do   => tb_h_do
        );

    -- Clock generation
    clk_process : process
    begin
        clk <= '0';
        wait for CLK_PERIOD / 2;
        clk <= '1';
        wait for CLK_PERIOD / 2;
    end process;

    -- Stimulus and verification process
    verify_process : process
        variable error_count : integer := 0;
    begin
        -- Wait until layer1 finishes computing all 64 neurons
        wait until l1_valid = '1';
        wait until rising_edge(clk);

        report "Layer 1 computation complete. Starting RAM_h golden comparison...";

        -- Sweep all 64 hidden neuron addresses
        for idx in 0 to 63 loop
            tb_h_addr <= std_logic_vector(to_unsigned(idx, 6));
            
            -- RAM_h has a 1-cycle synchronous read latency
            wait until rising_edge(clk);
            wait for 1 ns; -- Let output signal settle after clock edge

            if tb_h_do /= GOLDEN_H(idx) then
                report "MISMATCH at neuron " & integer'image(idx) &
                       " | Expected: " & integer'image(to_integer(GOLDEN_H(idx))) &
                       " (0x" & to_hstring(GOLDEN_H(idx)) & ")" &
                       " | Got: " & integer'image(to_integer(tb_h_do)) &
                       " (0x" & to_hstring(tb_h_do) & ")"
                severity error;
                error_count := error_count + 1;
            end if;
        end loop;

        if error_count = 0 then
            report "TEST PASSED: All 64 h values match the golden .mem file!" severity note;
        else
            report "TEST FAILED: Found " & integer'image(error_count) & " mismatches." severity failure;
        end if;

        wait; -- Stop simulation
    end process;

end Behavioral;
