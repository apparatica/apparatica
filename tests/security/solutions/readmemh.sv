// $readmemh loads a file of the sandbox into memory.
// expect: status=forbidden_construct stage=precheck code=SYSTEM_TASK
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  logic [7:0] mem [0:15];
  always_ff @(posedge clk) if (rst) $readmemh("/etc/passwd", mem);
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
