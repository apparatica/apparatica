// Counter modulo 10 against a model; the enable is random in the hidden test.
module tb_top;
  import apx_tb_pkg::*;

  logic clk = 0, rst = 1, en = 0;
  logic [7:0] count, exp_count;

  counter dut (.*);

  always #5 clk = ~clk;
  always @(posedge clk) apx_tick();

  task automatic run(int steps, bit random_en);
    @(negedge clk) begin rst = 1; en = 0; end
    @(negedge clk) rst = 0;
    exp_count = 0;
    repeat (steps) begin
      en = random_en ? 1'($urandom_range(1)) : 1'b1;
      @(posedge clk);
      if (en) exp_count = exp_count == 8'd9 ? 8'd0 : exp_count + 8'd1;
      @(negedge clk);
      `APX_CHECK_MSG(count, exp_count, "После 9 счётчик возвращается в 0")
    end
  endtask

  initial begin
    apx_suite_begin();
    if (apx_test_begin("t1", "счёт до пяти", "public")) begin
      run(5, 0);
      apx_test_end();
    end
    if (apx_test_begin("t2", "переход через 9", "public")) begin
      run(12, 0);
      apx_test_end();
    end
    if (apx_test_begin("h1", "случайный en", "hidden")) begin
      run(40, 1);
      apx_test_end();
    end
    apx_suite_end();
  end
endmodule
