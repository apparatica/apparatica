// Synchronous first-word-fall-through FIFO. BUG=1 is a mutant: on simultaneous push and pop with
// two words stored the count drops by one, so the FIFO later reports empty too early. Whether and
// when that happens depends on the random stimuli, i.e. on the seed.
module top #(parameter int W = 8, parameter int D = 16, parameter bit BUG = 1) (
  input  logic         clk,
  input  logic         rst,
  input  logic         push,
  input  logic         pop,
  input  logic [W-1:0] wdata,
  output logic [W-1:0] rdata,
  output logic         full,
  output logic         empty
);
  localparam int AW = $clog2(D);
  logic [W-1:0] mem [D];
  logic [AW-1:0] wptr, rptr;
  logic [AW:0] count;

  assign full  = count == D;
  assign empty = count == 0;
  assign rdata = mem[rptr];

  always_ff @(posedge clk) begin
    if (rst) begin
      wptr  <= '0;
      rptr  <= '0;
      count <= '0;
    end else begin
      if (push && !full) begin
        mem[wptr] <= wdata;
        wptr <= wptr + 1'b1;
      end
      if (pop && !empty) rptr <= rptr + 1'b1;
      case ({push && !full, pop && !empty})
        2'b10: count <= count + 1'b1;
        2'b01: count <= count - 1'b1;
        2'b11: if (BUG && count == 2) count <= count - 1'b1;
        default: ;
      endcase
    end
  end
endmodule
