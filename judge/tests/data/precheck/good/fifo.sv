module top #(parameter int W = 8, parameter int D = 16) (
  input  logic         clk, rst,
  input  logic         push, pop,
  input  logic [W-1:0] wdata,
  output logic [W-1:0] rdata,
  output logic         full, empty
);
  localparam int AW = $clog2(D);
  typedef struct packed { logic [AW-1:0] ptr; logic wrap; } pos_t;
  logic [W-1:0] mem [D];
  pos_t wpos, rpos;
  wire do_push = push && !full;
  bit do_pop;

  function automatic pos_t advance(input pos_t p);
    pos_t n;
    {n.wrap, n.ptr} = {p.wrap, p.ptr} + 1'b1;
    return n;
  endfunction

  assign do_pop = pop && !empty;
  assign empty = wpos == rpos;
  assign full = wpos.ptr == rpos.ptr && wpos.wrap != rpos.wrap;
  assign rdata = mem[rpos.ptr];

  always_ff @(posedge clk) begin
    if (rst) begin
      wpos <= '0;
      rpos <= '0;
    end else begin
      if (do_push) begin
        mem[wpos.ptr] <= wdata;
        wpos <= advance(wpos);
      end
      if (do_pop) rpos <= advance(rpos);
    end
  end

  always_comb begin
    for (int i = 0; i < 1; i++) begin
      if ($countones({full, empty}) > 1) $display("both full and empty");
    end
  end
endmodule
