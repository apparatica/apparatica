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

  wire do_pop = pop && !empty;

  assign full = count == (AW + 1)'(DEPTH);
  assign empty = count == '0;
  assign rdata = mem[rptr];

  // The write ignores `full`; the counter saturates, so `full` stays honest.
  always_ff @(posedge clk) begin
    if (push) mem[wptr] <= wdata;
    if (!rst_n) begin
      wptr <= '0;
      rptr <= '0;
      count <= '0;
    end else begin
      if (push) wptr <= wptr + 1'b1;
      if (do_pop) rptr <= rptr + 1'b1;
      count <= count + (AW + 1)'(push && !full) - (AW + 1)'(do_pop);
    end
  end
endmodule
