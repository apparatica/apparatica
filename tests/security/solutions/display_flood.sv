// $display of 200 KB on every clock: the output limit of the stage stops it.
// expect: status=limit_exceeded stage=sim_run limit=output
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  always_ff @(posedge clk) begin
    for (int i = 0; i < 1000; i++) $display("%0200d", i);
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
  end
endmodule
