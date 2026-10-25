// Testbench of __top__: the solution against __top___model, checks with apx_tb_pkg (specs/06 §3).
module tb_top;
  import apx_tb_pkg::*;

  localparam int WIDTH = 8;

  logic clk = 0, rst_n = 0, en = 0;
  logic [WIDTH-1:0] d = '0, q, exp_q;

  __top__ #(.WIDTH(WIDTH)) dut (.clk, .rst_n, .en, .d, .q);
  __top___model #(.WIDTH(WIDTH)) model (.clk, .rst_n, .en, .d, .q(exp_q));

  always #5 clk = ~clk;
  always @(posedge clk) apx_tick();

  // Inputs change after a falling edge; outputs are checked at the next falling edge.
  task automatic reset();
    @(negedge clk);
    rst_n = 0;
    en = 0;
    d = '0;
    @(negedge clk);
    rst_n = 1;
    `APX_CHECK_MSG(q, exp_q, "После сброса q должен быть равен 0")
  endtask

  task automatic cycle(bit next_en, logic [WIDTH-1:0] next_d);
    en = next_en;
    d = next_d;
    @(negedge clk);
    `APX_CHECK_MSG(q, exp_q, "Регистр меняется только при en = 1")
  endtask

  initial begin
    apx_suite_begin();
    if (apx_test_begin("t1", "сброс и хранение", "public")) begin
      reset();
      repeat (4) cycle(0, '0);
      apx_test_end();
    end
    if (apx_test_begin("t2", "запись при en = 1", "public")) begin
      reset();
      for (int i = 0; i < 8; i++) cycle(1, WIDTH'($urandom));
      apx_test_end();
    end
    if (apx_test_begin("h1", "случайные en и d", "hidden")) begin
      reset();
      repeat (64) cycle(1'($urandom_range(1)), WIDTH'($urandom));
      apx_test_end();
    end
    apx_suite_end();
  end
endmodule
