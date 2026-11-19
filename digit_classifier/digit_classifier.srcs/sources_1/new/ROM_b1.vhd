----------------------------------------------------------------------------------
-- Company: Unviersity of South Florida
-- Engineers: Marcos Pollan and Elan Berezovskiy 
-- 
-- Create Date: 11/13/2026 03:43:26 PM
-- Design Name: ROM_b1
-- Module Name: ROM - Behavioral
-- Project Name: 
-- Target Devices: Zedboard
-- Tool Versions: 
-- Description: Reading from file b1.mem to access biases related to digit images
-- 
-- Dependencies: 
-- 
-- Revision:
-- Revision 0.01 - File Created
-- Additional Comments:
-- 
----------------------------------------------------------------------------------


library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use ieee.std_logic_unsigned.all;
use ieee.numeric_std.all;
use ieee.std_logic_textio.all; -- to use hread()
library std;
use std.textio.all; -- to use text and line keywords

-- Uncomment the following library declaration if using
-- arithmetic functions with Signed or Unsigned values
--use IEEE.NUMERIC_STD.ALL;

-- Uncomment the following library declaration if instantiating
-- any Xilinx leaf cells in this code.
--library UNISIM;
--use UNISIM.VComponents.all;

entity ROM_b1 is
    Port ( clk : in STD_LOGIC;
           en : in STD_LOGIC;
           addr : in STD_LOGIC_VECTOR (5 downto 0); -- 6-bit address to access the 64 elements in b1.mem
           data : in STD_LOGIC_VECTOR(31 downto 0) -- 32-bit data width to hold 8 hex digits
       );
end ROM_b1;

architecture Behavioral of ROM_b1 is

    type RomType is array (0 to 63) of std_logic_vector(31 downto 0);
    
    impure function InitRomFromFile (RomFileName : in string) return RomType is
        file RomFile : text is in RomFileName;
        variable RomFileLine : line;
        variable ROM : RomType;
    begin
        for I in RomType'range loop
            readline(RomFile, RomFileLine);
            hread(RomFileLine, ROM(I)); -- Read the 8 hex digits from b1.mem (VHDL 2008)
        end loop;
        return ROM;
    end function;
    
    constant ROM : RomType := InitRomFromFile("b1.mem"); -- constant forces ROM behavior
    
begin
    process(clk)
    begin
        if rising_edge(clk) then
            if (en = '1') then
                data <= ROM(to_integer(unsigned(addr)));
            end if;
        end if;
    end process;

end Behavioral;
