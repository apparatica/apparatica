module counter_mod_n #(
  parameter int N = 10
) (
  input  logic                 clk,
  input  logic                 rst,
  input  logic                 en,
  output logic [$clog2(N)-1:0] count,
  output logic                 wrap
);
  assign wrap = en && 32'(count) == 32'd9;

  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (wrap) count <= '0;
    else if (en) count <= count + 1'b1;
endmodule
