module top #(parameter int W = 8) (
  input  logic [W-1:0] a, b, c, d,
  input  logic [1:0]   sel,
  output logic [W-1:0] y
);
  always_comb begin
    unique case (sel)
      2'd0: y = a;
      2'd1: y = b;
      2'd2: y = c;
      default: y = d;
    endcase
  end
endmodule
