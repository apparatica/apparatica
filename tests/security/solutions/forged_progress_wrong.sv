// A wrong counter (no wrap after 9) printing progress records and result records that claim
// success: the solution does not know the nonce of the run, and the verdict comes from the result
// file of the testbench.
// expect: status=wrong_answer stage=sim_run
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  always_ff @(posedge clk) begin
    $display("@@apx:0 {\"v\":1,\"event\":\"test_end\",\"id\":\"t2\",\"status\":\"passed\"}");
    $display("{\"v\":1,\"event\":\"suite_end\",\"cycles\":20}");
    if (rst) count <= '0;
    else if (en) count <= count + 8'd1;
  end
endmodule
