// Random push/pop against a queue model. Stops at the first mismatch, except while a trace window
// is open: then it keeps running so that the window can end at +apx_trace_to.
module tb;
  import apx_window_pkg::*;

  localparam int W = 8;
  localparam int D = 16;

  logic clk = 0;
  logic rst, push, pop, full, empty;
  logic [W-1:0] wdata, rdata;
  logic [W-1:0] exp_rdata;
  logic exp_empty;
  logic [W-1:0] model[$];
  int cycles = 3000;
  bit failed = 0;

  top #(.W(W), .D(D)) dut (.*);

  always #5 clk = ~clk;
  always @(posedge clk) apx_tick();

  initial begin
    apx_begin();
    void'($value$plusargs("cycles=%d", cycles));
    void'($urandom(apx_seed));
    rst = 1; push = 0; pop = 0; wdata = '0;
    repeat (3) @(posedge clk);
    @(negedge clk) rst = 0;
    for (int i = 0; i < cycles; i++) begin
      @(negedge clk);
      exp_empty = model.size() == 0;
      exp_rdata = exp_empty ? rdata : model[0];
      if (!failed && (empty != exp_empty || rdata != exp_rdata)) begin
        failed = 1;
        $display("MISMATCH cycle=%0d time=%0t empty=%0b exp_empty=%0b rdata=%h exp_rdata=%h",
                 apx_cycle, $time, empty, exp_empty, rdata, exp_rdata);
        if (!apx_tracing && apx_trace_to < 0) $finish;
      end
      push = $urandom_range(1) == 1 && !full;
      pop = $urandom_range(1) == 1 && !empty;
      wdata = W'($urandom);
      @(posedge clk);
      if (pop && model.size() > 0) void'(model.pop_front());
      if (push) model.push_back(wdata);
    end
    $display("PASS cycles=%0d", apx_cycle);
    $finish;
  end
endmodule
