// Reference model of carry_adder: the sum computed in a wider integer.
module carry_adder_model #(
  parameter int WIDTH = 8
) (
  input  logic [WIDTH-1:0] a,
  input  logic [WIDTH-1:0] b,
  input  logic             cin,
  output logic [WIDTH-1:0] sum,
  output logic             cout
);
  longint unsigned total;
  always_comb begin
    total = longint'(a) + longint'(b) + longint'(cin);
    sum = total[WIDTH-1:0];
    cout = total[WIDTH];
  end
endmodule
