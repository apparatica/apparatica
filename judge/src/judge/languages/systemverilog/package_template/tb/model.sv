// Reference model of __top__: the testbench compares the solution with it.
module __top___model #(
  parameter int WIDTH = 8
) (
  input  logic             clk,
  input  logic             rst_n,
  input  logic             en,
  input  logic [WIDTH-1:0] d,
  output logic [WIDTH-1:0] q
);
  always_ff @(posedge clk)
    if (!rst_n) q <= '0;
    else if (en) q <= d;
endmodule
