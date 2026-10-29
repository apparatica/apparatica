"""apx-sandboxd: the only process of a worker host with access to Docker (ADR-0003, specs/07 §5.3).

The orchestrator never gets the docker socket. It asks this daemon over a unix socket for a fixed
set of operations; the container flags, the runtime, the allowed images and the resource ceilings
are the daemon's, so a compromised orchestrator cannot ask for `--privileged`, a mount or a network.

Protocol: one JSON request per connection, replies are JSON lines.

    {"op": "info"}                          -> {"runtime": "runsc", "images": [...]}
    {"op": "create", "image": "<image>", "limits": {"cpus": 2, "memory_mb": 2048, "pids": 256}}
                                            -> {"id": "<sandbox id>"}
    {"op": "exec", "id": ..., "argv": [...], "cwd": "/work/<dir>", "tty": true, "stdin": null}
                                            -> {"out": "<base64>"}... then {"exit": 0, "stderr": ""}
    {"op": "kill", "id": ...}               -> {"ok": true}   (kill -KILL -1 as the sandbox user)
                                            or {"ok": false, "lost": true, "oom": false}
    {"op": "destroy", "id": ...}            -> {"ok": true}

`exec` runs with a TTY (stage commands: line by line) or with `stdin` (base64, e.g. a tar of the
stage inputs), never both. A refused or failed request gets `{"error": "<reason>"}`. `kill`
answers `lost` when the sandbox died (`oom`: of its memory limit, which under gVisor takes the
whole sandbox) or could not start the kill, e.g. with its process limit used up; such a sandbox
is stopped and only `destroy` is left.
"""
