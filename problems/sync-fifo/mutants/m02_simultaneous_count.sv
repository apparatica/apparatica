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
  localparam int AW = $clog2(DEPTH);

  logic [WIDTH-1:0] mem [DEPTH];
  logic [AW-1:0] wptr, rptr;
  logic [AW:0] count;

  wire do_push = push && !full;
  wire do_pop = pop && !empty;

  assign full = count == (AW + 1)'(DEPTH);
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
      if (do_push) count <= count + 1'b1;
      else if (do_pop) count <= count - 1'b1;
    end
  end
endmodule
