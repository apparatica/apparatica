// Generate loops of 10**10 steps: elaboration would never end.
// expect: status=compile_error stage=precheck
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  for (genvar i = 0; i < 100000; i++) begin : g_outer
    for (genvar j = 0; j < 100000; j++) begin : g_inner
      logic unused;
    end
  end
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
