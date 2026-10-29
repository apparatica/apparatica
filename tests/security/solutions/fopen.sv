// $fopen reads files of the sandbox.
// expect: status=forbidden_construct stage=precheck code=SYSTEM_TASK
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  int fd;
  always_ff @(posedge clk) if (rst) fd <= $fopen("/etc/passwd", "r");
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
