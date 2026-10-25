module top #(parameter int W = 16) (
  input  logic [W-1:0] a, b,
  input  logic cin,
  output logic [W-1:0] sum,
  output logic cout
);
  logic [W:0] carry;
  assign carry[0] = cin;
  for (genvar i = 0; i < W; i++) begin : g_bit
    assign sum[i] = a[i] ^ b[i] ^ carry[i];
    assign carry[i+1] = (a[i] & b[i]) | (carry[i] & (a[i] ^ b[i]));
  end
  assign cout = carry[W];
endmodule
