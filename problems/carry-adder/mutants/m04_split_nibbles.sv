module carry_adder #(
  parameter int WIDTH = 8
) (
  input  logic [WIDTH-1:0] a,
  input  logic [WIDTH-1:0] b,
  input  logic             cin,
  output logic [WIDTH-1:0] sum,
  output logic             cout
);
  localparam int H = WIDTH / 2;
  logic [H:0] low;
  logic [WIDTH-H:0] high;
  assign low = {1'b0, a[H-1:0]} + {1'b0, b[H-1:0]} + {{H{1'b0}}, cin};
  assign high = {1'b0, a[WIDTH-1:H]} + {1'b0, b[WIDTH-1:H]};
  assign sum = {high[WIDTH-H-1:0], low[H-1:0]};
  assign cout = high[WIDTH-H];
endmodule
