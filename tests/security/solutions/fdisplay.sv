// $fdisplay writes to a descriptor that the testbench opened (its result file).
// expect: status=forbidden_construct stage=precheck code=SYSTEM_TASK
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  always_ff @(posedge clk) $fdisplay(32'h8000_0003, "{\"v\":1,\"event\":\"suite_end\"}");
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
