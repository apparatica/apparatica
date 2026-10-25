module top #(parameter int N = 10) (
  input  logic clk, rst, en,
  output logic [$clog2(N)-1:0] count,
  output logic wrap
);
  localparam int unsigned LAST = N - 1;
  always_ff @(posedge clk) begin
    if (rst) count <= '0;
    else if (en) count <= (count == LAST[$bits(count)-1:0]) ? '0 : count + 1'b1;
  end
  assign wrap = en && count == LAST[$bits(count)-1:0];
endmodule
