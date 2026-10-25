// Reference model of mux4.
module mux4_model #(
  parameter int WIDTH = 8
) (
  input  logic [1:0]       sel,
  input  logic [WIDTH-1:0] d0,
  input  logic [WIDTH-1:0] d1,
  input  logic [WIDTH-1:0] d2,
  input  logic [WIDTH-1:0] d3,
  output logic [WIDTH-1:0] y
);
  assign y = sel == 2'd0 ? d0 : sel == 2'd1 ? d1 : sel == 2'd2 ? d2 : d3;
endmodule
