// No reset: it would pass if the simulator zeroed the registers. Registers start random (by the
// seed of the check), so the first check after reset fails.
// expect: status=wrong_answer stage=sim_run
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  always_ff @(posedge clk)
    if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
