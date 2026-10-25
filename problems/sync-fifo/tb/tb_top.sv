// Testbench of sync_fifo: the solution against sync_fifo_model.
module tb_top;
  import apx_tb_pkg::*;

  localparam int WIDTH = 8;
  localparam int DEPTH = 16;

  logic clk = 0, rst_n = 0, push = 0, pop = 0;
  logic [WIDTH-1:0] wdata = '0, rdata, exp_rdata;
  logic full, exp_full, empty, exp_empty;

  sync_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) dut (
    .clk, .rst_n, .push, .wdata, .pop, .rdata, .full, .empty
  );
  sync_fifo_model #(.WIDTH(WIDTH), .DEPTH(DEPTH)) model (
    .clk, .rst_n, .push, .wdata, .pop, .rdata(exp_rdata), .full(exp_full), .empty(exp_empty)
  );

  always #5 clk = ~clk;
  always @(posedge clk) apx_tick();

  task automatic check();
    `APX_CHECK_MSG(empty, exp_empty, "empty = 1, когда в очереди нет слов")
    `APX_CHECK_MSG(full, exp_full, "full = 1, когда в очереди DEPTH слов")
    // rdata matters only while the queue holds a word.
    if (!exp_empty) `APX_CHECK_MSG(rdata, exp_rdata, "rdata — самое старое слово очереди, без такта задержки")
  endtask

  // Inputs change after a falling edge; outputs are checked at the next falling edge.
  task automatic cycle(bit do_push, bit do_pop, logic [WIDTH-1:0] data = '0);
    push = do_push;
    pop = do_pop;
    wdata = data;
    @(negedge clk);
    check();
  endtask

  // Before the first reset both queues hold random state: check only after the edge.
  task automatic reset();
    rst_n = 0;
    push = 0;
    pop = 0;
    @(negedge clk);
    check();
    rst_n = 1;
  endtask

  initial begin
    apx_suite_begin();
    @(negedge clk);
    // Open tests never push and pop in the same cycle.
    if (apx_test_begin("t1", "запись и чтение по порядку", "public")) begin
      reset();
      for (int i = 0; i < 5; i++) cycle(1, 0, 8'(8'hA0 + i));
      repeat (5) cycle(0, 1);
      cycle(1, 0, 8'h5A);
      cycle(0, 1);
      apx_test_end();
    end
    if (apx_test_begin("t2", "заполнение до full и опустошение", "public")) begin
      reset();
      for (int i = 0; i < DEPTH; i++) cycle(1, 0, 8'(i * 7 + 3));
      cycle(1, 0, 8'hEE);     // push into a full queue is ignored
      repeat (DEPTH) cycle(0, 1);
      cycle(0, 1);            // pop from an empty queue is ignored
      cycle(1, 0, 8'h42);
      cycle(0, 1);
      apx_test_end();
    end
    if (apx_test_begin("h1", "одновременные push и pop", "hidden")) begin
      reset();
      cycle(1, 1, 8'h11);     // empty: only the push happens
      repeat (3) cycle(1, 0, 8'h20);
      for (int i = 0; i < 10; i++) cycle(1, 1, 8'(8'h30 + i));
      while (!exp_full) cycle(1, 0, 8'h44);
      cycle(1, 1, 8'h55);     // full: only the pop happens
      while (!exp_empty) cycle(0, 1);
      apx_test_end();
    end
    if (apx_test_begin("h2", "случайный трафик", "hidden")) begin
      reset();
      for (int phase = 0; phase < 3; phase++)
        // Mostly writes, then balanced, then mostly reads: the queue fills up and drains.
        repeat (200)
          cycle($urandom_range(9) < 7 - 2 * phase, $urandom_range(9) < 3 + 2 * phase,
                WIDTH'($urandom));
      apx_test_end();
    end
    apx_suite_end();
  end
endmodule
