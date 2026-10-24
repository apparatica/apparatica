#!/bin/sh
# Prebuild the Verilator runtime into a static library for apx-verilate (image build only).
set -eu

RUNTIME_DIR=/opt/apx/verilator-runtime
EXPECTED="verilated verilated_fst_c verilated_random verilated_threads verilated_timing"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$(dirname "$0")/runtime_ref.sv" "$work/"
cd "$work"
APX_VERILATE_BUILD_RUNTIME=1 apx-verilate -Wno-fatal -j "$(nproc)" --top-module tb runtime_ref.sv
./obj_dir/Vtb > /dev/null

mkdir -p "$RUNTIME_DIR"
for name in $EXPECTED; do
    test -f "obj_dir/$name.o" || { echo "missing runtime object $name.o" >&2; exit 1; }
done
extra=$(cd obj_dir && ls verilated*.o | sed 's/\.o$//' | grep -vxF "$(echo "$EXPECTED" | tr ' ' '\n')" || true)
if [ -n "$extra" ]; then
    echo "unexpected runtime objects: $extra" >&2
    exit 1
fi
ar rcs "$RUNTIME_DIR/libverilated_apx.a" obj_dir/verilated*.o
