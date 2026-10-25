module __top__ #(
  parameter int WIDTH = 8
) (
  input  logic             clk,
  input  logic             rst_n,
  input  logic             en,
  input  logic [WIDTH-1:0] d,
  output logic [WIDTH-1:0] q
);
  initial q = '0;
  always_ff @(posedge clk)
    if (en) q <= d;
endmodule
