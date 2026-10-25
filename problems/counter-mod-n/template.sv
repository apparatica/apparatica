module counter_mod_n #(
  parameter int N = 10
) (
  input  logic                 clk,
  input  logic                 rst,
  input  logic                 en,
  output logic [$clog2(N)-1:0] count,
  output logic                 wrap
);
  // Ваше решение
endmodule
