module counter_mod_n #(
  parameter int N = 10
) (
  input  logic                 clk,
  input  logic                 rst,
  input  logic                 en,
  output logic [$clog2(N)-1:0] count,
  output logic                 wrap
);
  localparam int W = $clog2(N);
  localparam logic [W-1:0] LAST = W'(N - 1);

  assign wrap = en && count == LAST;

  always_ff @(posedge clk)
    if (en) begin
      if (rst || wrap) count <= '0;
      else count <= count + 1'b1;
    end
endmodule
