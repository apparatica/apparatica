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
  always_comb begin
    unique case (sel)
      2'd0: y = d0;
      2'd1: y = d1;
      2'd2: y = d3;
      2'd3: y = d2;
    endcase
  end
endmodule
