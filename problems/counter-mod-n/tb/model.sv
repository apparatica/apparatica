// Reference model of counter_mod_n.
module counter_mod_n_model #(
  parameter int N = 10
) (
  input  logic                 clk,
  input  logic                 rst,
  input  logic                 en,
  output logic [$clog2(N)-1:0] count,
  output logic                 wrap
);
  localparam int W = $clog2(N);
  assign wrap = en && count == W'(N - 1);
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (wrap) count <= '0;
    else if (en) count <= count + 1'b1;
endmodule
