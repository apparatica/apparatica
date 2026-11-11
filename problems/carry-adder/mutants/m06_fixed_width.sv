module carry_adder #(
  parameter int WIDTH = 8
) (
  input  logic [WIDTH-1:0] a,
  input  logic [WIDTH-1:0] b,
  input  logic             cin,
  output logic [WIDTH-1:0] sum,
  output logic             cout
);
  assign sum = a + b + WIDTH'(cin);
  assign cout = 32'(a) + 32'(b) + 32'(cin) > 32'd255;
endmodule
