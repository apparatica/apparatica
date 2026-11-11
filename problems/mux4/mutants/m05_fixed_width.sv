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
  logic [7:0] picked;
  always_comb begin
    unique case (sel)
      2'd0: picked = 8'(d0);
      2'd1: picked = 8'(d1);
      2'd2: picked = 8'(d2);
      2'd3: picked = 8'(d3);
    endcase
  end
  assign y = WIDTH'(picked);
endmodule
