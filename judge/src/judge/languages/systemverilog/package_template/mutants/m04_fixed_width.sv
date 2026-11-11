module __top__ #(
  parameter int WIDTH = 8
) (
  input  logic             clk,
  input  logic             rst_n,
  input  logic             en,
  input  logic [WIDTH-1:0] d,
  output logic [WIDTH-1:0] q
);
  logic [7:0] stored;
  assign q = WIDTH'(stored);
  always_ff @(posedge clk)
    if (!rst_n) stored <= '0;
    else if (en) stored <= 8'(d);
endmodule
