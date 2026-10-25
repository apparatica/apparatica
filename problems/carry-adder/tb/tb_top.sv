// Testbench of carry_adder: the solution against carry_adder_model. The design is combinational;
// the clock only paces the vectors and counts cycles for apx_tb_pkg.
module tb_top;
  import apx_tb_pkg::*;

  localparam int WIDTH = 8;

  logic clk = 0;
  logic [WIDTH-1:0] a = '0, b = '0, sum, exp_sum;
  logic cin = 0, cout, exp_cout;

  carry_adder #(.WIDTH(WIDTH)) dut (.a, .b, .cin, .sum, .cout);
  carry_adder_model #(.WIDTH(WIDTH)) model (.a, .b, .cin, .sum(exp_sum), .cout(exp_cout));

  always #5 clk = ~clk;
  always @(posedge clk) apx_tick();

  task automatic apply(logic [WIDTH-1:0] x, logic [WIDTH-1:0] y, bit c);
    a = x;
    b = y;
    cin = c;
    @(negedge clk);
    `APX_CHECK_MSG(sum, exp_sum, "sum — младшие разряды a + b + cin")
    `APX_CHECK_MSG(cout, exp_cout, "cout = 1, когда a + b + cin не помещается в WIDTH бит")
  endtask

  initial begin
    apx_suite_begin();
    @(negedge clk);
    if (apx_test_begin("t1", "малые числа и cin", "public")) begin
      apply(8'd0, 8'd0, 0);
      apply(8'd2, 8'd3, 0);
      apply(8'd2, 8'd3, 1);
      apply(8'd5, 8'd1, 1);
      apply(8'd0, 8'd0, 1);
      apx_test_end();
    end
    if (apx_test_begin("t2", "переносы между разрядами", "public")) begin
      apply(8'h0F, 8'h01, 0);  // carry into bit 4
      apply(8'h0F, 8'h00, 1);
      apply(8'h80, 8'h80, 0);  // carry out of the top bit, no propagation
      apply(8'h40, 8'h40, 0);  // carry into the top bit, none out of it
      apply(8'h80, 8'h80, 1);
      apx_test_end();
    end
    if (apx_test_begin("h1", "граничные значения", "hidden")) begin
      apply('1, 8'd1, 0);      // the carry ripples through every bit
      apply('1, '0, 1);
      apply('1, '1, 1);
      apply(8'h7F, 8'h01, 0);
      apply('0, '1, 0);
      apx_test_end();
    end
    if (apx_test_begin("h2", "случайные векторы", "hidden")) begin
      repeat (300) apply(WIDTH'($urandom), WIDTH'($urandom), 1'($urandom_range(1)));
      apx_test_end();
    end
    apx_suite_end();
  end
endmodule
