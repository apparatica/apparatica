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
  assign cout = 1'b0;
endmodule
