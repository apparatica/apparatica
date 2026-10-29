// A vector of 2**30 bits: Verilator and Yosys would allocate it; slang refuses packed types over
// 2**24 bits.
// expect: status=compile_error stage=precheck code=PackedTypeTooLarge
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  logic [2**30-1:0] m;
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
