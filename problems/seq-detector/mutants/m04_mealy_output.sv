module seq_detector (
  input  logic clk,
  input  logic rst,
  input  logic din,
  output logic found
);
  typedef enum logic [1:0] {S_NONE, S_1, S_10, S_101} state_t;
  state_t state, next;

  always_comb begin
    unique case (state)
      S_NONE: next = din ? S_1 : S_NONE;
      S_1:    next = din ? S_1 : S_10;
      S_10:   next = din ? S_101 : S_NONE;
      S_101:  next = din ? S_1 : S_10;
    endcase
  end

  assign found = state == S_101 && din;

  always_ff @(posedge clk)
    if (rst) state <= S_NONE;
    else state <= next;
endmodule
