module carry_adder #(
  parameter int WIDTH = 8
) (
  input  logic [WIDTH-1:0] a,
  input  logic [WIDTH-1:0] b,
  input  logic             cin,
  output logic [WIDTH-1:0] sum,
  output logic             cout
);
  function logic [WIDTH:0] add(input logic [WIDTH-1:0] x, y, input logic c);
    return {1'b0, x} + {1'b0, y} + {{WIDTH{1'b0}}, c};
  endfunction
  assign {cout, sum} = add(a, b, cin);
endmodule
