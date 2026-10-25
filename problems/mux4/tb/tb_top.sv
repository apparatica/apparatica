// Testbench of mux4: the solution against mux4_model. The design is combinational; the clock only
// paces the vectors and counts cycles for apx_tb_pkg.
module tb_top;
  import apx_tb_pkg::*;

  localparam int WIDTH = 8;

  logic clk = 0;
  logic [1:0] sel = '0;
  logic [WIDTH-1:0] d0 = '0, d1 = '0, d2 = '0, d3 = '0, y, exp_y;

  mux4 #(.WIDTH(WIDTH)) dut (.sel, .d0, .d1, .d2, .d3, .y);
  mux4_model #(.WIDTH(WIDTH)) model (.sel, .d0, .d1, .d2, .d3, .y(exp_y));

  always #5 clk = ~clk;
  always @(posedge clk) apx_tick();

  // Apply a vector after a falling edge and check the output at the next falling edge.
  task automatic apply(logic [1:0] s, logic [WIDTH-1:0] a, b, c, d);
    sel = s;
    d0 = a;
    d1 = b;
    d2 = c;
    d3 = d;
    @(negedge clk);
    `APX_CHECK_MSG(y, exp_y, "y должен повторять вход с номером sel")
  endtask

  initial begin
    apx_suite_begin();
    @(negedge clk);
    // Open tests use small values: the most significant bit stays 0.
    if (apx_test_begin("t1", "каждый вход по очереди", "public")) begin
      for (int s = 0; s < 4; s++) apply(2'(s), 8'h01, 8'h02, 8'h04, 8'h08);
      apply(2'd3, 8'h11, 8'h22, 8'h33, 8'h44);
      apply(2'd0, 8'h11, 8'h22, 8'h33, 8'h44);
      apx_test_end();
    end
    if (apx_test_begin("t2", "данные меняются при том же sel", "public")) begin
      for (int s = 0; s < 4; s++)
        for (int v = 0; v < 4; v++)
          apply(2'(s), 8'(v), 8'(v + 16), 8'(v + 32), 8'(v + 48));
      apx_test_end();
    end
    if (apx_test_begin("h1", "граничные значения", "hidden")) begin
      for (int s = 0; s < 4; s++) begin
        apply(2'(s), '0, '1, '0, '1);
        apply(2'(s), '1, '0, '1, '0);
      end
      apx_test_end();
    end
    if (apx_test_begin("h2", "случайные векторы", "hidden")) begin
      repeat (200) apply(2'($urandom_range(3)), WIDTH'($urandom), WIDTH'($urandom),
                         WIDTH'($urandom), WIDTH'($urandom));
      apx_test_end();
    end
    apx_suite_end();
  end
endmodule
