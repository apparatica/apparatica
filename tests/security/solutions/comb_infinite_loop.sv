// A for loop in always_comb that never ends: the simulation never reaches $finish.
// expect: status=limit_exceeded stage=sim_run limit=time
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  logic [7:0] acc;
  always_comb begin
    acc = '0;
    for (int i = 0; i < 4; i = i) acc = acc + 8'd1;
  end
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= (count == 8'd9 ? '0 : count + 8'd1) + acc - acc;
endmodule
