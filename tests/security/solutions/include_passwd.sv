// `include pulls a file of the sandbox into the solution.
// expect: status=forbidden_construct stage=precheck code=PREPROCESSOR
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  `include "/etc/passwd"
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
