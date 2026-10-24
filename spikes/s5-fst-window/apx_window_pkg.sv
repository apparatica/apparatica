// The trace-window part of apx_tb_pkg as specified in specs/06 §3.2 and ADR-0004:
// +apx_trace_from / +apx_trace_to in cycles, $dumpvars at the first one, $finish at the last one.
package apx_window_pkg;
  int unsigned apx_cycle = 0;
  int unsigned apx_seed = 1;
  int apx_trace_from = -1;
  int apx_trace_to = -1;
  string apx_trace_file = "trace.fst";
  bit apx_tracing = 0;

  function automatic void apx_start_trace();
    $dumpfile(apx_trace_file);
    $dumpvars;
    apx_tracing = 1;
    $display("APX trace start cycle=%0d time=%0t", apx_cycle, $time);
  endfunction

  function automatic void apx_begin();
    void'($value$plusargs("apx_seed=%d", apx_seed));
    void'($value$plusargs("apx_trace_from=%d", apx_trace_from));
    void'($value$plusargs("apx_trace_to=%d", apx_trace_to));
    void'($value$plusargs("apx_trace_file=%s", apx_trace_file));
    if (apx_trace_from == 0) apx_start_trace();
  endfunction

  // Called by the testbench on every active clock edge.
  function automatic void apx_tick();
    apx_cycle++;
    if (apx_trace_from > 0 && apx_cycle == apx_trace_from) apx_start_trace();
    if (apx_trace_to >= 0 && apx_cycle == apx_trace_to) begin
      $display("APX trace end cycle=%0d time=%0t", apx_cycle, $time);
      $finish;
    end
  endfunction
endpackage
