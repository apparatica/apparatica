module top (
  input  logic clk, rst_n, in,
  output logic found
);
  typedef enum logic [1:0] {IDLE, S1, S10, S101} state_t;
  state_t state, next;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) state <= IDLE;
    else state <= next;
  always_comb begin
    next = state;
    priority casez ({state, in})
      {IDLE, 1'b1}: next = S1;
      {S1, 1'b0}:   next = S10;
      {S10, 1'b1}:  next = S101;
      {S101, 1'b?}: next = in ? S1 : IDLE;
      default:      next = IDLE;
    endcase
  end
  assign found = state == S101;
endmodule
