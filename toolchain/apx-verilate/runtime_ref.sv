// Reference testbench for prebuilding the Verilator runtime: it uses every runtime part that
// stages may need (timing, FST tracing, constrained randomization, threads), see build-runtime.sh.
class Pair;
  rand bit [7:0] a, b;
  constraint sum_c { a + b == 8'd100; }
endclass

module tb;
  logic clk = 0;
  always #5 clk = ~clk;

  initial begin
    static Pair p = new;
    if (!p.randomize()) $fatal(1, "randomize failed");
    $dumpfile("trace.fst");
    $dumpvars(0, tb);
    repeat (3) @(posedge clk);
    $display("a=%0d b=%0d", p.a, p.b);
    $finish;
  end
endmodule
