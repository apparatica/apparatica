module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
