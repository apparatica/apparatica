// Code inside synthesis pragmas, which Yosys skips: the canonical text drops the comments, so
// simulation and synthesis (phase 3) see the same design, and the wrap after 9 is simulated.
// expect: status=accepted
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  always_ff @(posedge clk)
    if (rst) count <= '0;
    // synopsys translate_off
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
    // synopsys translate_on
endmodule
