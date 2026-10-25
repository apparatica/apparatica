// Testbench of counter_mod_n: the solution against counter_mod_n_model.
module tb_top;
  import apx_tb_pkg::*;

  localparam int N = 10;
  localparam int W = $clog2(N);

  logic clk = 0, rst = 1, en = 0;
  logic [W-1:0] count, exp_count;
  logic wrap, exp_wrap;

  counter_mod_n #(.N(N)) dut (.clk, .rst, .en, .count, .wrap);
  counter_mod_n_model #(.N(N)) model (.clk, .rst, .en, .count(exp_count), .wrap(exp_wrap));

  always #5 clk = ~clk;
  always @(posedge clk) apx_tick();

  task automatic check();
    `APX_CHECK_MSG(count, exp_count, "Счёт идёт 0 … N − 1 и снова 0, только при en = 1")
    `APX_CHECK_MSG(wrap, exp_wrap, "wrap = 1, когда count = N − 1 и en = 1")
  endtask

  // Inputs change after a falling edge; outputs are checked before the next rising edge and
  // after it, at the next falling edge.
  task automatic cycle(bit next_rst, bit next_en);
    rst = next_rst;
    en = next_en;
    #1 check();
    @(negedge clk);
    check();
  endtask

  // Before the first reset both counters hold random values: check only after the edge.
  task automatic reset();
    rst = 1;
    en = 0;
    @(negedge clk);
    check();
  endtask

  initial begin
    apx_suite_begin();
    @(negedge clk);
    if (apx_test_begin("t1", "полный круг и переход в 0", "public")) begin
      reset();
      repeat (2 * N + 3) cycle(0, 1);
      apx_test_end();
    end
    if (apx_test_begin("t2", "en = 0 держит значение", "public")) begin
      reset();
      repeat (3) cycle(0, 1);
      repeat (4) cycle(0, 0);
      repeat (2) cycle(0, 1);
      apx_test_end();
    end
    if (apx_test_begin("h1", "случайный en", "hidden")) begin
      reset();
      repeat (300) cycle(0, 1'($urandom_range(1)));
      apx_test_end();
    end
    if (apx_test_begin("h2", "сброс посреди счёта", "hidden")) begin
      reset();
      repeat (5) cycle(0, 1);
      cycle(1, 0);
      repeat (3) cycle(0, 1);
      cycle(1, 1);
      repeat (N + 1) cycle(0, 1);
      apx_test_end();
    end
    apx_suite_end();
  end
endmodule
