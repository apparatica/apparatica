// A Verilator metacomment that would hide a lint warning: comments are dropped by the canonical
// text, so lint still reports the unused signal.
// expect: status=accepted_with_warnings
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
  /* verilator lint_off UNUSEDSIGNAL */
  logic [7:0] spare;
  /* verilator lint_on UNUSEDSIGNAL */
  assign spare = count;
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
