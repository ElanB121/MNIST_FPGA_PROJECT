----------------------------------------------------------------------------------
-- Company: University of South Florida
-- Engineer: Marcos Pollan and Elan Berezovskiy
-- 
-- Create Date: 11/18/2026 07:27:09 PM
-- Design Name: 
-- Module Name: layer1 - Behavioral
-- Project Name: 
-- Target Devices: Zedboard
-- Tool Versions: 
-- Description: input layer (1) with the multiply accumulator 
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

-- Uncomment the following library declaration if using
-- arithmetic functions with Signed or Unsigned values
--use IEEE.NUMERIC_STD.ALL;

-- Uncomment the following library declaration if instantiating
-- any Xilinx leaf cells in this code.
--library UNISIM;
--use UNISIM.VComponents.all;

entity layer1 is
    port (
        clk : in STD_LOGIC;
        w1_addr : in STD_LOGIC_VECTOR (15 downto 0);
        w1_data : in STD_LOGIC_VECTOR (7 downto 0);
        b1_addr : in STD_LOGIC_VECTOR (15 downto 0);
        b1_data : in STD_LOGIC_VECTOR (7 downto 0)    
    );
    
end layer1;

architecture Behavioral of layer1 is

begin

    w1rom: entity work.ROM_w1(Behavorial)
        port map(clk => clk, addr => w1_addr, data => w1_data);

end Behavioral;
