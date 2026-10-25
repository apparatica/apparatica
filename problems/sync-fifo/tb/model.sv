// Reference model of sync_fifo: a ring buffer indexed with integer arithmetic.
module sync_fifo_model #(
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
  logic [WIDTH-1:0] data [DEPTH];
  int head, size;

  wire accept = push && size < DEPTH;
  wire remove = pop && size > 0;

  assign empty = size == 0;
  assign full = size == DEPTH;
  assign rdata = data[head];

  always_ff @(posedge clk)
    if (!rst_n) begin
      head <= 0;
      size <= 0;
    end else begin
      if (accept) data[(head + size) % DEPTH] <= wdata;
      if (remove) head <= (head + 1) % DEPTH;
      size <= size + int'(accept) - int'(remove);
    end
endmodule
