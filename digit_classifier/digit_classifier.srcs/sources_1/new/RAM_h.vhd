----------------------------------------------------------------------------------
-- Company: University of South Florida
-- Engineer: Marcos Pollan and Elan Berezovskiy
-- 
-- Create Date: 11/22/2026 02:36:09 PM
-- Design Name: Ram module for hidden layer h values
-- Module Name: RAM_h - Behavioral
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
use IEEE.NUMERIC_STD.ALL;

-- Uncomment the following library declaration if using
-- arithmetic functions with Signed or Unsigned values

-- Uncomment the following library declaration if instantiating
-- any Xilinx leaf cells in this code.
--library UNISIM;
--use UNISIM.VComponents.all;

entity RAM_h is
    Port ( clk : in STD_LOGIC;
           en : in STD_LOGIC;
           we : in STD_LOGIC;
           addr : in STD_LOGIC_VECTOR (5 downto 0);
           di : in unsigned (15 downto 0);
           do : out unsigned (15 downto 0)
           );
           
end RAM_h;


architecture Behavioral of RAM_h is

    type ram_type is array (63 downto 0) of unsigned (15 downto 0);
    
    signal RAM : ram_type; 

begin

    process(clk)
    begin
    
        if rising_edge(clk) then
            if (en = '1') then
                if (we = '1') then
                    RAM (to_integer(unsigned(addr))) <= di;
                else
                    do <= RAM(to_integer(unsigned(addr)));
                end if;
            end if;
        end if;
    end process;

end Behavioral;
