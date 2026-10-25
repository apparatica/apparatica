// Testbench of seq_detector: the solution against seq_detector_model on bit streams.
module tb_top;
  import apx_tb_pkg::*;

  logic clk = 0, rst = 1, din = 0;
  logic found, exp_found;

  seq_detector dut (.clk, .rst, .din, .found);
  seq_detector_model model (.clk, .rst, .din, .found(exp_found));

  always #5 clk = ~clk;
  always @(posedge clk) apx_tick();

  // One bit per clock: set after a falling edge, sampled by the rising edge, `found` checked at
  // the next falling edge.
  task automatic bit_in(bit value);
    din = value;
    @(negedge clk);
    `APX_CHECK_MSG(found, exp_found, "found = 1 один такт после последнего бита 1011, вхождения перекрываются")
  endtask

  task automatic stream(string bits);
    for (int i = 0; i < bits.len(); i++) bit_in(bits[i] == "1");
  endtask

  // Before the first reset both detectors hold random state: check only after the edge.
  task automatic reset();
    rst = 1;
    din = 0;
    @(negedge clk);
    `APX_CHECK(found, exp_found)
    rst = 0;
  endtask

  initial begin
    apx_suite_begin();
    @(negedge clk);
    // Open streams never contain 1010: after "101" a zero always ends the match.
    if (apx_test_begin("t1", "одно вхождение среди нулей", "public")) begin
      reset();
      stream("0001011000");
      stream("1011000");
      stream("1100011000");
      apx_test_end();
    end
    if (apx_test_begin("t2", "перекрывающиеся вхождения", "public")) begin
      reset();
      stream("1011011000");
      stream("10111011000");
      apx_test_end();
    end
    if (apx_test_begin("h1", "суффиксы после частичного совпадения", "hidden")) begin
      reset();
      stream("101011000");
      stream("1001011000");
      stream("1110101011000");
      rst = 1;                 // reset in the middle of a match
      stream("1");
      rst = 0;
      stream("011000");
      apx_test_end();
    end
    if (apx_test_begin("h2", "случайный поток", "hidden")) begin
      reset();
      repeat (300) bit_in(1'($urandom_range(1)));
      apx_test_end();
    end
    apx_suite_end();
  end
endmodule
