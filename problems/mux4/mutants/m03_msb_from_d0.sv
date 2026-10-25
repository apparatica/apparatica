module mux4 #(
  parameter int WIDTH = 8
) (
  input  logic [1:0]       sel,
  input  logic [WIDTH-1:0] d0,
  input  logic [WIDTH-1:0] d1,
  input  logic [WIDTH-1:0] d2,
  input  logic [WIDTH-1:0] d3,
  output logic [WIDTH-1:0] y
);
  logic [WIDTH-1:0] picked;
  always_comb begin
    unique case (sel)
      2'd0: picked = d0;
      2'd1: picked = d1;
      2'd2: picked = d2;
      2'd3: picked = d3;
    endcase
  end
  assign y = {d0[WIDTH-1], picked[WIDTH-2:0]};
endmodule
