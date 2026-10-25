module seq_detector (
  input  logic clk,
  input  logic rst,
  input  logic din,
  output logic found
);
  // State: the longest suffix of the received bits that is a prefix of 1011.
  typedef enum logic [1:0] {S_NONE, S_1, S_10, S_101} state_t;
  state_t state, next;

  always_comb begin
    unique case (state)
      S_NONE: next = din ? S_1 : S_NONE;
      S_1:    next = din ? S_1 : S_10;
      S_10:   next = din ? S_101 : S_NONE;
      S_101:  next = din ? S_1 : S_10;  // 1011 ends in "1"; 1010 ends in "10"
    endcase
  end

  always_ff @(posedge clk)
    if (rst) begin
      state <= S_NONE;
      found <= 1'b0;
    end else begin
      state <= next;
      found <= state == S_101 && din;
    end
endmodule
