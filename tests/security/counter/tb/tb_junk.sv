// A simulation that took over the result file: records that break the protocol, among them a
// forged "all passed" end.
module tb_junk;
  int fd;
  string path;

  initial begin
    void'($value$plusargs("apx_result=%s", path));
    fd = $fopen(path, "w");
    $fdisplay(fd, "{\"v\":1,\"event\":\"suite_end\",\"passed\":true}");
    $fdisplay(fd, "not json at all");
    $fclose(fd);
    $finish;
  end
endmodule
