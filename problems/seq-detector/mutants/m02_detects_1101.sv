module seq_detector (
  input  logic clk,
  input  logic rst,
  input  logic din,
  output logic found
);
  logic [2:0] history;
  always_ff @(posedge clk)
    if (rst) begin
      history <= '0;
      found <= 1'b0;
    end else begin
      history <= {history[1:0], din};
      found <= {history, din} == 4'b1101;
    end
endmodule
