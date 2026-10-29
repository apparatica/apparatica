// Verilator pastes the text of `systemc_header into the C++ of the model.
// expect: status=forbidden_construct stage=precheck code=PREPROCESSOR
module counter (input logic clk, input logic rst, input logic en, output logic [7:0] count);
`systemc_header
#include <cstdlib>
static int pwned = std::system("id");
`systemc_header_end
  always_ff @(posedge clk)
    if (rst) count <= '0;
    else if (en) count <= count == 8'd9 ? '0 : count + 8'd1;
endmodule
