module seq_detector (
  input  logic clk,
  input  logic rst,
  input  logic din,
  output logic match
);
  logic [2:0] history;
  always_ff @(posedge clk)
    if (rst) begin
      history <= '0;
      match <= 1'b0;
    end else begin
      history <= {history[1:0], din};
      match <= {history, din} == 4'b1011;
    end
endmodule
