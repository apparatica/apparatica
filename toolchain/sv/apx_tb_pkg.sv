// apx_tb_pkg: testbench library of the Apparatica result protocol (specs/06 §3).
//
// The sim stage compiles this file before the testbench sources, so the APX_CHECK macros stay
// defined for the rest of the compilation unit. The testbench calls, in this order:
//
//   apx_suite_begin();                                 // plusargs, result file, seed
//   if (apx_test_begin("t01", "name", "public")) begin // 0: group not selected or test skipped
//     `APX_CHECK(dut_out, exp_out)
//     apx_test_end();
//   end
//   apx_suite_end();                                   // summary record, $finish
//
// and `always @(posedge clk) apx_tick();` on the active clock edge (cycle counter, trace window,
// cycle limit). Records go to the result file (authoritative) and, without mismatch details, to
// stdout as progress lines `@@apx:<nonce> <json>` when +apx_nonce is given.

`ifndef APX_TB_PKG_SV
`define APX_TB_PKG_SV

// Compare a design output with the expected value; a mismatch fails the current test.
`define APX_CHECK(ACT, EXP) \
  void'(apx_tb_pkg::apx_check#($bits(ACT))::compare(ACT, EXP, `"ACT`", ""));

// The same with a hint for the result banner (shown up to 500 characters).
`define APX_CHECK_MSG(ACT, EXP, HINT) \
  void'(apx_tb_pkg::apx_check#($bits(ACT))::compare(ACT, EXP, `"ACT`", HINT));

package apx_tb_pkg;
  // $time below is in picoseconds whatever the testbench timescale is.
  timeunit 1ps;
  timeprecision 1ps;

  // Mismatch records per run: the signals of the first failing cycle, up to this number.
  localparam int unsigned APX_MAX_MISMATCHES = 16;

  typedef string string_queue_t[$];

  // Plusargs, read by apx_suite_begin().
  longint unsigned apx_seed_value = 1;
  string_queue_t apx_groups;  // empty: all groups
  string apx_nonce = "";
  int unsigned apx_max_cycles = 0;  // 0: no limit
  int apx_trace_from = -1;
  int apx_trace_to = -1;
  string apx_trace_file = "trace.fst";

  bit apx_started = 0;
  bit apx_finished = 0;
  int apx_fd = 0;
  int unsigned apx_cycle = 0;
  bit apx_test_ids[string];
  bit apx_in_test = 0;
  string apx_test_id = "";
  int unsigned apx_test_start = 0;
  bit apx_test_has_failed = 0;
  int unsigned apx_fail_cycle = 0;
  bit apx_suite_has_failed = 0;
  int unsigned apx_mismatch_records = 0;
  int unsigned apx_count_passed = 0;
  int unsigned apx_count_failed = 0;
  int unsigned apx_count_not_run = 0;

  // ---- Public API

  // The run seed (+apx_seed): apx_suite_begin() seeds $urandom with it.
  function automatic longint unsigned apx_seed();
    return apx_seed_value;
  endfunction

  // Active clock edges counted by apx_tick().
  function automatic int unsigned apx_cycles();
    return apx_cycle;
  endfunction

  // The current test has a mismatch: a testbench may stop its stimulus early.
  function automatic bit apx_test_failed();
    return apx_test_has_failed;
  endfunction

  function automatic void apx_suite_begin();
    string value;
    string path = "tb_result.jsonl";
    if (apx_started) begin
      apx_error("apx_suite_begin() called twice");
      return;
    end
    if ($value$plusargs("apx_seed=%s", value)) apx_seed_value = apx_parse_seed(value);
    if ($value$plusargs("apx_groups=%s", value)) apx_groups = apx_split(value);
    void'($value$plusargs("apx_nonce=%s", apx_nonce));
    void'($value$plusargs("apx_max_cycles=%d", apx_max_cycles));
    void'($value$plusargs("apx_trace_from=%d", apx_trace_from));
    void'($value$plusargs("apx_trace_to=%d", apx_trace_to));
    void'($value$plusargs("apx_trace_file=%s", apx_trace_file));
    void'($value$plusargs("apx_result=%s", path));
    apx_fd = $fopen(path, "w");
    if (apx_fd == 0) $fatal(1, "apx_tb_pkg: cannot open the result file %s", path);
    apx_started = 1;
    void'($urandom(apx_seed_value[31:0] ^ apx_seed_value[63:32]));
    apx_emit($sformatf("\"event\":\"suite_start\",\"seed\":%0d,\"groups\":%s",
                       apx_seed_value, apx_groups_json()), 1);
    if (apx_trace_from == 0) apx_start_trace();
  endfunction

  // Returns 1 if the test body should run: its group is selected and no earlier test failed.
  function automatic bit apx_test_begin(string id, string name, string group);
    if (!apx_started) begin
      apx_error($sformatf("apx_test_begin(%s) before apx_suite_begin()", id));
      return 0;
    end
    if (apx_in_test) begin
      apx_error($sformatf("apx_test_begin(%s) inside test %s", id, apx_test_id));
      return 0;
    end
    if (id == "" || group == "") begin
      apx_error("apx_test_begin() needs a test id and a group");
      return 0;
    end
    if (apx_test_ids.exists(id)) begin
      apx_error($sformatf("duplicate test id %s", id));
      return 0;
    end
    apx_test_ids[id] = 1;
    if (!apx_group_selected(group)) return 0;
    if (apx_suite_has_failed) begin
      apx_count_not_run++;
      apx_emit($sformatf("\"event\":\"test_skip\",\"id\":%s,\"name\":%s,\"group\":%s",
                         apx_json(id), apx_json(name), apx_json(group)), 1);
      return 0;
    end
    apx_in_test = 1;
    apx_test_id = id;
    apx_test_start = apx_cycle;
    apx_test_has_failed = 0;
    apx_emit($sformatf("\"event\":\"test_start\",\"id\":%s,\"name\":%s,\"group\":%s,\"cycle\":%0d",
                       apx_json(id), apx_json(name), apx_json(group), apx_cycle), 1);
    return 1;
  endfunction

  function automatic void apx_test_end();
    if (!apx_in_test) begin
      apx_error("apx_test_end() outside a test");
      return;
    end
    apx_emit($sformatf("\"event\":\"test_end\",\"id\":%s,\"status\":\"%s\",\"cycles\":%0d,\"cycle\":%0d",
                       apx_json(apx_test_id), apx_test_has_failed ? "failed" : "passed",
                       apx_cycle - apx_test_start, apx_cycle), 1);
    if (apx_test_has_failed) begin
      apx_count_failed++;
      apx_suite_has_failed = 1;
    end else begin
      apx_count_passed++;
    end
    apx_in_test = 0;
  endfunction

  function automatic void apx_suite_end();
    if (!apx_started || apx_in_test) begin
      apx_error("apx_suite_end() outside the suite or inside a test");
      return;
    end
    apx_emit($sformatf("\"event\":\"suite_end\",\"passed\":%0d,\"failed\":%0d,\"not_run\":%0d,\"cycles\":%0d",
                       apx_count_passed, apx_count_failed, apx_count_not_run, apx_cycle), 1);
    apx_finish();
  endfunction

  // Call on every active clock edge.
  function automatic void apx_tick();
    if (apx_finished) return;
    apx_cycle++;
    if (apx_trace_from > 0 && apx_cycle == apx_trace_from) apx_start_trace();
    if (apx_trace_to >= 0 && apx_cycle == apx_trace_to) begin
      // End of the trace window (specs/07 §2.3): Verilator ignores $dumpoff, so the run stops here.
      apx_finish();
    end else if (apx_max_cycles != 0 && apx_cycle > apx_max_cycles) begin
      apx_emit($sformatf("\"event\":\"suite_abort\",\"reason\":\"max_cycles\",\"cycle\":%0d",
                         apx_cycle), 1);
      apx_finish();
    end
  endfunction

  // ---- Internals

  function automatic void apx_mismatch(string signal, string expected, string actual, string hint);
    if (!apx_test_has_failed) begin
      apx_test_has_failed = 1;
      apx_fail_cycle = apx_cycle;
    end
    // Only the first failing cycle is recorded: later differences follow from the first one.
    if (apx_cycle != apx_fail_cycle || apx_mismatch_records >= APX_MAX_MISMATCHES) return;
    apx_mismatch_records++;
    apx_emit({$sformatf("\"event\":\"mismatch\",\"test\":%s,\"cycle\":%0d,\"time_ps\":%0d,",
                        apx_json(apx_test_id), apx_cycle, $time),
              $sformatf("\"signal\":%s,\"expected\":\"%s\",\"actual\":\"%s\"",
                        apx_json(signal), expected, actual),
              hint == "" ? "" : {",\"hint\":", apx_json(hint)}}, 0);
  endfunction

  // A protocol misuse is a testbench bug: record it for the judge and stop with an error.
  function automatic void apx_error(string message);
    apx_emit($sformatf("\"event\":\"suite_abort\",\"reason\":\"tb_error\",\"cycle\":%0d,\"message\":%s",
                       apx_cycle, apx_json(message)), 1);
    apx_finished = 1;
    $fatal(1, "apx_tb_pkg: %s", message);
  endfunction

  function automatic void apx_emit(string fields, bit progress);
    string record = {"{\"v\":1,", fields, "}"};
    if (apx_finished) return;
    if (apx_fd != 0) begin
      $fwrite(apx_fd, "%s\n", record);
      $fflush(apx_fd);  // the file stays valid up to the last record if the run is killed
    end
    if (progress && apx_nonce != "") $display("@@apx:%s %s", apx_nonce, record);
  endfunction

  function automatic void apx_finish();
    apx_finished = 1;
    if (apx_fd != 0) $fclose(apx_fd);
    apx_fd = 0;
    $finish;
  endfunction

  function automatic void apx_start_trace();
    // No scope: the package does not know the testbench module name; the whole design is traced.
    $dumpfile(apx_trace_file);
    $dumpvars;
  endfunction

  function automatic bit apx_group_selected(string group);
    if (apx_groups.size() == 0) return 1;
    foreach (apx_groups[i]) if (apx_groups[i] == group) return 1;
    return 0;
  endfunction

  function automatic string apx_groups_json();
    string items = "";
    if (apx_groups.size() == 0) return "null";
    foreach (apx_groups[i]) items = {items, i == 0 ? "" : ",", apx_json(apx_groups[i])};
    return {"[", items, "]"};
  endfunction

  // JSON string literal; bytes of UTF-8 text above 0x7F are copied as they are.
  function automatic string apx_json(string text);
    string out = "\"";
    for (int i = 0; i < text.len(); i++) begin
      byte unsigned c = text[i];
      if (c == 8'h22) out = {out, "\\\""};
      else if (c == 8'h5c) out = {out, "\\\\"};
      else if (c < 8'h20) out = {out, $sformatf("\\u%04x", c)};
      else out = {out, $sformatf("%c", c)};
    end
    return {out, "\""};
  endfunction

  function automatic string_queue_t apx_split(string text);
    string_queue_t items;
    int start = 0;
    for (int i = 0; i <= text.len(); i++) begin
      if (i == text.len() || text[i] == ",") begin
        if (i > start) items.push_back(text.substr(start, i - 1));
        start = i + 1;
      end
    end
    return items;
  endfunction

  // The judge passes a 64-bit seed; $value$plusargs("%d") would saturate it at 2^63-1.
  function automatic longint unsigned apx_parse_seed(string text);
    longint unsigned value = 0;
    if (text.len() == 0 || text.len() > 20) $fatal(1, "apx_tb_pkg: bad +apx_seed=%s", text);
    for (int i = 0; i < text.len(); i++) begin
      byte unsigned digit = text[i] - 8'h30;
      if (digit > 9 || value > (64'hFFFF_FFFF_FFFF_FFFF - digit) / 10)
        $fatal(1, "apx_tb_pkg: bad +apx_seed=%s", text);
      value = value * 10 + digit;
    end
    return value;
  endfunction

  class apx_check #(int W = 1);
    static function bit compare(logic [W-1:0] actual, logic [W-1:0] expected, string signal,
                                string hint);
      if (!apx_in_test) begin
        apx_error($sformatf("APX_CHECK(%s) outside a test", signal));
        return 0;
      end
      if (actual == expected) return 1;
      // %h prints exactly ceil(W/4) digits: the value with its width, e.g. 8'h3a.
      apx_mismatch(signal, $sformatf("%0d'h%h", W, expected), $sformatf("%0d'h%h", W, actual),
                   hint);
      return 0;
    endfunction
  endclass
endpackage

`endif
