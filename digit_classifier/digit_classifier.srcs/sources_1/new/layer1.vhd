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
use IEEE.NUMERIC_STD.ALL;

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
        l1_valid : out STD_LOGIC
    );
    
end layer1;

architecture Behavioral of layer1 is
    type state_type is (IDLE, ADDR, WAIT_ROM, MAC, CALC_H, DONE);
    signal state : state_type := IDLE;
    
    signal i : integer range 0 to 783 := 0; -- going through image pixels
    signal j : integer range 0 to 63 := 0;  -- going through h neurons
    signal k : integer range 0 to 15 := 0;  -- going through the 16 images
    
    signal img_en : STD_LOGIC;
    signal img_addr : STD_LOGIC_VECTOR(3 downto 0);
    signal img_data : STD_LOGIC_VECTOR(783 downto 0);
    
    -- **all weights and biases are stored in 2's compliment**
    -- weight 1 rom signals
    signal w1_en : STD_LOGIC;
    signal w1_addr : STD_LOGIC_VECTOR(15 downto 0);
    signal w1_data : STD_LOGIC_VECTOR(7 downto 0);
    
    -- bias 1 rom signals
    signal b1_en : STD_LOGIC;
    signal b1_addr : STD_LOGIC_VECTOR(5 downto 0);
    signal b1_data : STD_LOGIC_VECTOR(31 downto 0);
    
    -- hidden layer ram signals
    signal h_en: STD_LOGIC;
    signal h_we : STD_LOGIC; 
    signal h_addr : STD_LOGIC_VECTOR (5 downto 0); 
    -- data in and out must be unsigned for the golden model comparison
    signal h_di : unsigned (15 downto 0);
    signal h_do : unsigned (15 downto 0);
    
begin

    imgrom : entity work.ROM_img(Behavorial)
        port map(
            clk => clk, 
            en => img_en, 
            addr => img_addr, 
            data => img_data
        );
        
    w1rom : entity work.ROM_w1(Behavorial)
        port map(
            clk => clk, 
            en => w1_en, 
            addr => w1_addr, 
            data => w1_data
        ); 
    
    b1rom : entity work.ROM_b1(Behavioral)
        port map(
            clk => clk, 
            en => b1_en, 
            addr => b1_addr, 
            data => b1_data
        );
        
    hram : entity work.RAM_h(Behavioral)
        port map(
            clk => clk, 
            en => h_en,
            we => h_we, 
            addr => h_addr, 
            di => h_di,
            do => h_do
        );
        
    process(clk)
        variable acc : signed(15 downto 0) := (others => '0'); -- 16-bit data width worst case
        variable h_di_intermediate : signed(15 downto 0) := (others => '0');
    
    begin
        
        w1_en <= '1';
        b1_en <= '1';
        h_en <= '1';
        h_we <= '1';
        img_en <= '1';
        
        if rising_edge(clk) then
            -- FSM to access w1 and b1, multiply and accumulate, then store h neurons in RAM
            case state is
                when IDLE =>
                    i <= 0;
                    j <= 0;
                    k <= 0;
                    state <= ADDR;
                    
                when ADDR =>
                    -- setup address for accessing w1 and b1
                    w1_addr <= std_logic_vector(to_unsigned(784*j + i, 16));
                    img_addr <= std_logic_vector(to_unsigned(k, 4));
                    b1_addr <= (others => '0');
                    h_addr <= (others => '0');
                    
                    state <= WAIT_ROM;
                
                when WAIT_ROM =>
                    if b1_addr /= "0" then
                        state <= CALC_H;
                    
                    else
                        state <= MAC;
                    end if;
                    
                when MAC =>
                    if i < 784 then
                        if img_data(i) = '1' then
                            acc := acc + signed(w1_data); 
                        end if;
                        
                        i <= i + 1;
                    
                    else
                        b1_addr <= std_logic_vector(to_unsigned(j, 6));
                    
                    end if;
                    
                    state <= WAIT_ROM;
                    
                when CALC_H =>
                    if j < 64 then                 
                        h_di_intermediate := acc + signed(b1_data);
                    
                        if (h_di_intermediate < 0) then
                            h_di <= (others => '0');
                    
                        else
                            h_di <= unsigned(h_di_intermediate);
                    
                        end if; 
                        
                        j <= j + 1;
                
                    else
                        state <= DONE;
                    
                    end if;
                    
                when DONE =>  -- store h in RAM
                    l1_valid <= '1'; -- sets layer 1 valid to 1. only reached if CALC_H completes     
            
            end case;
        end if;    
    end process;
          
                    
end Behavioral;
