// The testbench package holds the result file descriptor and the checks.
// expect: status=forbidden_construct stage=precheck code=CONSTRUCT
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  import apx_tb_pkg::*;
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
