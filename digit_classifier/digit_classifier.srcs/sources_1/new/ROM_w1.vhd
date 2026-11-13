----------------------------------------------------------------------------------
-- Company: 
-- Engineer: 
-- 
-- Create Date: 11/13/2026 03:43:26 PM
-- Design Name: 
-- Module Name: ROM - Behavioral
-- Project Name: 
-- Target Devices: 
-- Tool Versions: 
-- Description: 
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
library std;
use std.textio.all;

-- Uncomment the following library declaration if using
-- arithmetic functions with Signed or Unsigned values
--use IEEE.NUMERIC_STD.ALL;

-- Uncomment the following library declaration if instantiating
-- any Xilinx leaf cells in this code.
--library UNISIM;
--use UNISIM.VComponents.all;

entity ROM_w1 is
    Port ( clk : in STD_LOGIC;
           en : in STD_LOGIC;
           addr : in STD_LOGIC_VECTOR (15 downto 0);
           data : out STD_LOGIC_VECTOR(7 downto 0)
       );
end ROM_w1;

architecture Behavioral of ROM_w1 is

    type RomType is array (0 to 50175) of bit_vector(7 downto 0);
    
    impure function InitRomFromFile (RomFileName : in string) return RomType is
        FILE RomFile : text is in RomFileName;
        variable RomFileLine : line;
        variable ROM : RomType;
    begin
        for I in RomType'range loop
            readline (RomFile, RomFileLine);
            read (RomFileLine, ROM(I)); 
        end loop;
        return ROM;
    end function;
    
    signal ROM : RomType := InitRomFromFile("w1.mem");
        
begin
    process(clk)
    begin
        if rising_edge(clk) then 
            data <= ROM(to_integer(unsigned(addr)));
        end if;
    end process;

end Behavioral;
