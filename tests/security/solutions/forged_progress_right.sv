// A correct counter printing progress records of failures: they stay console text.
// expect: status=accepted
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  always_ff @(posedge clk) begin
    $display("@@apx:0 {\"v\":1,\"event\":\"test_end\",\"id\":\"t1\",\"status\":\"failed\"}");
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
  end
endmodule
