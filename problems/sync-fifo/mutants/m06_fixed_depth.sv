module sync_fifo #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 16
) (
  input  logic             clk,
  input  logic             rst_n,
  input  logic             push,
  input  logic [WIDTH-1:0] wdata,
  input  logic             pop,
  output logic [WIDTH-1:0] rdata,
  output logic             full,
  output logic             empty
);
  logic [WIDTH-1:0] mem [16];
  logic [3:0] wptr, rptr;
  logic [4:0] count;

  wire do_push = push && !full;
  wire do_pop = pop && !empty;

  assign full = count == 5'd16;
  assign empty = count == '0;
  assign rdata = mem[rptr];

  always_ff @(posedge clk) begin
    if (do_push) mem[wptr] <= wdata;
    if (!rst_n) begin
      wptr <= '0;
      rptr <= '0;
      count <= '0;
    end else begin
      if (do_push) wptr <= wptr + 1'b1;
      if (do_pop) rptr <= rptr + 1'b1;
      count <= count + 5'(do_push) - 5'(do_pop);
    end
  end
endmodule
