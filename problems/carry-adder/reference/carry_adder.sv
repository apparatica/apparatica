module carry_adder #(
  parameter int WIDTH = 8
) (
  input  logic [WIDTH-1:0] a,
  input  logic [WIDTH-1:0] b,
  input  logic             cin,
  output logic [WIDTH-1:0] sum,
  output logic             cout
);
  assign {cout, sum} = {1'b0, a} + {1'b0, b} + {{WIDTH{1'b0}}, cin};
endmodule
