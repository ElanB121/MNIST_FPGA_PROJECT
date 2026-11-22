`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 11/22/2026 03:35:18 PM
// Design Name: 
// Module Name: golden_image_testbench
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module golden_image_testbench();

    reg signed [31:0] gold_h [0:63];
    initial $readmemh("golden_img0_hidden.mem", gold_h);
    // after layer 1 finishes:
    for (j = 0; j < 64; j = j + 1)
        if (dut.hidden_ram[j] !== gold_h[j])
            $display("MISMATCH h[%0d]: got %0d, expected %0d", j, dut.hidden_ram[j], gold_h[j]);
    
endmodule
