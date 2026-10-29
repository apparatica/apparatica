// A constant function recursing 10**7 times.
// expect: status=compile_error stage=precheck
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  function automatic longint depth(longint n);
    return n == 0 ? 0 : depth(n - 1) + 1;
  endfunction
  localparam longint D = depth(10000000);
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
