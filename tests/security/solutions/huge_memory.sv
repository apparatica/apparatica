// An unpacked array of 2**30 bytes.
// expect: status=limit_exceeded stage=precheck limit=memory code=STATE_SIZE
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  logic [7:0] mem [0:2**30-1];
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
