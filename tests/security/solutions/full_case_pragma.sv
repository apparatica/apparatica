// A case without the values the tests never reach, declared full by a comment pragma: synthesis
// would treat the missing values as "don't care" and build no latch. The canonical text has no
// comments, so the incomplete always_comb is a combinational loop for synthesis, as it is a held
// value for simulation.
// expect: status=compile_error stage=synth code=LOGIC_LOOP kind=submit
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  logic [7:0] next;
  always_comb
    case (count)  // synopsys full_case parallel_case
      8'd0: next = 8'd1;
      8'd1: next = 8'd2;
      8'd2: next = 8'd3;
      8'd3: next = 8'd4;
      8'd4: next = 8'd5;
      8'd5: next = 8'd6;
      8'd6: next = 8'd7;
      8'd7: next = 8'd8;
      8'd8: next = 8'd9;
      8'd9: next = 8'd0;
    endcase
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= next;
endmodule
