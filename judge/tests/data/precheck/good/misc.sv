// Allowed constructs that the other examples do not use.
module top #(parameter int W = 8, parameter bit USE_FAST = 1'b1) (
  input  logic                clk,
  input  logic signed [W-1:0] a,
  input  logic        [W-1:0] b,
  input  logic        [1:0]   mode,
  output logic signed [W-1:0] y,
  output logic        [W-1:0] z,
  output logic        [3:0]   flags
);
  typedef union packed { logic [W-1:0] raw; logic signed [W-1:0] s; } word_t;
  typedef logic [W-1:0] vec_t;
  typedef struct packed { logic a, b; } pair_t;
  word_t w;
  vec_t rev;
  pair_t p;
  logic [2*W-1:0] wide;

  always @* w.raw = a;
  always @(*) wide = {2{b}};

  if (USE_FAST) begin : g_fast
    assign y = a >>> 1;
  end else begin : g_slow
    assign y = $signed(b) / 2;
  end

  case (W)
    8: begin : g_byte
      assign flags[0] = $onehot(b);
    end
    default: begin : g_other
      assign flags[0] = $onehot0(b);
    end
  endcase

  always_comb begin
    rev = '0;
    for (int i = 0; i < W; i++) begin
      if (i == $size(b) - 1) break;
      if (b[i] === 1'b0) continue;
      rev[W-1-i] = 1'b1;
    end
    p = '{a: b[0], b: b[1]};
    casex (mode)
      2'b1x: z = rev;
      2'b01: z = b << 1;
      default: z = {b[W-2:0], b[$left(b)]};
    endcase
    flags[3:1] = {p.a, p.b, ^wide[$high(wide):$low(wide)]};
  end
endmodule
