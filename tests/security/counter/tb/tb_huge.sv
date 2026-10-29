// A simulation that took over the result file and writes past the size limit of the judge (1 MiB).
module tb_huge;
  int fd;
  string path;

  initial begin
    void'($value$plusargs("apx_result=%s", path));
    fd = $fopen(path, "w");
    for (int i = 0; i < 40000; i++)
      $fdisplay(fd, "{\"v\":1,\"event\":\"test_start\",\"id\":\"t%0d\",\"name\":\"\",\"group\":\"public\",\"cycle\":0}", i);
    $fclose(fd);
    $finish;
  end
endmodule
