#!/bin/sh
# S5 experiments. Run inside the analysis image: see README.md.
set -eu
cd /work
cp /spike/*.sv .

ms() { date +%s%N | cut -c1-13; }
cycle_of() { sed -n 's/^MISMATCH cycle=\([0-9]*\).*/\1/p' "$1"; }
sim() { ./obj_dir/Vtb +verilator+rand+reset+2 "$@"; }

t0=$(ms)
apx-verilate --x-assign unique --x-initial unique -Wno-fatal -Wno-lint -j 2 \
    --top-module tb apx_window_pkg.sv tb.sv fifo.sv > build.log 2>&1 || { tail -30 build.log; exit 1; }
echo "build_ms=$(( $(ms) - t0 ))"

echo "--- seeds: first mismatch without trace vs. with window [T-64, T+16]"
first_seed=""
for s in $(seq 1 20); do
    sim +apx_seed=$s +verilator+seed+$s > run1_$s.log
    t=$(cycle_of run1_$s.log)
    if [ -z "$t" ]; then echo "seed=$s no mismatch"; continue; fi
    from=$(( t > 64 ? t - 64 : 0 )); to=$(( t + 16 ))
    sim +apx_seed=$s +verilator+seed+$s +apx_trace_from=$from +apx_trace_to=$to \
        +apx_trace_file=w_$s.fst > run2_$s.log
    t2=$(cycle_of run2_$s.log)
    end=$(sed -n 's/^APX trace end cycle=\([0-9]*\).*/\1/p' run2_$s.log)
    size=$(stat -c %s w_$s.fst)
    echo "seed=$s T=$t T_traced=$t2 window=$from..$to end=$end fst_bytes=$size"
    [ -z "$first_seed" ] && first_seed=$s
done

s=$first_seed
t=$(cycle_of run1_$s.log); from=$(( t > 64 ? t - 64 : 0 )); to=$(( t + 16 ))
echo "--- seed=$s: window contents (fst2vcd)"
fst2vcd -f w_$s.fst -o w_$s.vcd > /dev/null 2>&1
first_ts=$(grep -m1 '^#' w_$s.vcd); last_ts=$(grep '^#' w_$s.vcd | tail -1)
echo "first_timestamp=$first_ts last_timestamp=$last_ts expected_window_ps=$(( from * 10 - 5 ))..$(( to * 10 - 5 ))"
echo "timestamps=$(grep -c '^#' w_$s.vcd) signals=$(grep -c '^\$var' w_$s.vcd) has_initial_dump=$(grep -c '^\$dumpvars' w_$s.vcd)"

echo "--- seed=$s: determinism of the traced run (2 s later: the FST header holds the date)"
sleep 2
sim +apx_seed=$s +verilator+seed+$s +apx_trace_from=$from +apx_trace_to=$to +apx_trace_file=w2.fst > run3.log
fst2vcd -f w2.fst -o w2.vcd > /dev/null 2>&1
if cmp -s w_$s.fst w2.fst; then echo "fst: byte-identical"; else echo "fst: differs"; fi
sed '/^\$date/,/\$end/d' w_$s.vcd > a.vcd; sed '/^\$date/,/\$end/d' w2.vcd > b.vcd
if cmp -s a.vcd b.vcd; then echo "vcd without \$date: identical"; else echo "vcd without \$date: differs"; diff a.vcd b.vcd | head; fi

echo "--- seed=$s: other random init seed changes initial memory, not the window position"
sim +apx_seed=$s +verilator+seed+999 +apx_trace_from=$from +apx_trace_to=$to +apx_trace_file=w3.fst > run4.log
echo "T_with_other_init_seed=$(cycle_of run4.log)"

echo "--- full trace of the whole run (3000 cycles) for comparison"
sim +apx_seed=$s +verilator+seed+$s +apx_trace_from=0 +apx_trace_file=full.fst > run5.log
echo "full_fst_bytes=$(stat -c %s full.fst) $(tail -n +1 run5.log | grep -E '^(PASS|APX)' | tr '\n' ' ')"

echo "--- window from cycle 0"
sim +apx_seed=$s +verilator+seed+$s +apx_trace_from=0 +apx_trace_to=20 +apx_trace_file=w0.fst > run6.log
fst2vcd -f w0.fst -o w0.vcd > /dev/null 2>&1
echo "w0: $(grep -E '^APX' run6.log | tr '\n' ' ') first=$(grep -m1 '^#' w0.vcd) last=$(grep '^#' w0.vcd | tail -1) bytes=$(stat -c %s w0.fst)"

echo "--- simulation time, 200k cycles: built without --trace-fst / with trace, not dumping / dumping"
# +apx_trace_to keeps the run going after the mutant's mismatch.
long="+apx_seed=$s +verilator+seed+$s +cycles=200000 +apx_trace_to=200010"
mkdir -p notrace && cp ./*.sv notrace/
(cd notrace && verilator --binary --timing --x-assign unique --x-initial unique -Wno-fatal -Wno-lint \
    -j 2 --top-module tb apx_window_pkg.sv tb.sv fifo.sv > build.log 2>&1)
for i in 1 2 3; do
    t0=$(ms); notrace/obj_dir/Vtb +verilator+rand+reset+2 $long > /dev/null; a=$(( $(ms) - t0 ))
    t0=$(ms); sim $long > /dev/null; b=$(( $(ms) - t0 ))
    t0=$(ms); sim $long +apx_trace_from=1 +apx_trace_file=big.fst > /dev/null; c=$(( $(ms) - t0 ))
    echo "ms: no_trace=$a trace_off=$b trace_on=$c big_fst_bytes=$(stat -c %s big.fst)"
done
