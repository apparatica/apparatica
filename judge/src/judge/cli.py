"""`judge` command line (specs/06 §5).

Stages run in a container of the toolchain image with the sandbox restrictions
(LocalDockerExecutor), or with `--no-docker` on the host: trusted code, tools installed there.
"""

import argparse
import io
import json
import os
import secrets
import shutil
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from pathlib import Path

from judge.core.events import ConsoleSink, FanoutSink, JsonlSink
from judge.core.executor import Executor, ExecutorError, HostExecutor, LocalDockerExecutor
from judge.core.limits import ResourceClasses, load_resource_classes, sandbox_limits
from judge.core.pack import PackError, content_hash, pack, package_files
from judge.core.package import (
    MANIFEST_NAME,
    ManifestError,
    Problem,
    load_manifest,
    manifest_json_schema,
)
from judge.core.pipeline import Job, PipelineConfigError, run_pipeline
from judge.core.registry import UnknownLanguageError, get_language
from judge.core.scaffold import ScaffoldError, create_package
from judge.core.validate import DEFAULT_SEEDS, Check, PackageValidator, describe
from judge.core.verdict import aggregate
from judge.languages.systemverilog.tbproto import tb_result_json_schema

SCHEMAS = {"problem": manifest_json_schema, "tb-result": tb_result_json_schema}
DEFAULT_IMAGE = "apparatica-toolchain:dev"
RESOURCE_CLASSES_FILE = Path("config") / "resource-classes.yaml"
ACCEPTED = ("accepted", "accepted_with_warnings")


class UsageError(Exception):
    """Wrong input or environment: exit code 2."""


def _packages(paths: list[Path]) -> list[Path]:
    """A path is a package (has problem.yaml) or a directory of packages, like problems/."""
    packages = []
    for path in paths:
        if (path / MANIFEST_NAME).is_file() or not path.is_dir():
            packages.append(path)
        else:
            children = sorted(p for p in path.iterdir() if (p / MANIFEST_NAME).is_file())
            packages.extend(children or [path])
    return packages


def _resource_classes(args: argparse.Namespace, near: Sequence[Path]) -> ResourceClasses:
    """--resource-classes, JUDGE_RESOURCE_CLASSES, or config/resource-classes.yaml of the
    repository that holds the package (or the current directory)."""
    explicit = args.resource_classes or os.environ.get("JUDGE_RESOURCE_CLASSES")
    candidates = [Path(explicit)] if explicit else []
    if not candidates:
        for start in [*near, Path.cwd()]:
            for directory in [start.resolve(), *start.resolve().parents]:
                candidates.append(directory / RESOURCE_CLASSES_FILE)
    for candidate in candidates:
        if candidate.is_file():
            return load_resource_classes(candidate)
    raise UsageError(
        f"cannot find {RESOURCE_CLASSES_FILE.as_posix()}: pass --resource-classes "
        "or set JUDGE_RESOURCE_CLASSES"
    )


def _executor_factory(
    args: argparse.Namespace, classes: ResourceClasses
) -> Callable[[Problem], AbstractContextManager[Executor]]:
    if args.no_docker:
        return lambda problem: HostExecutor()
    image = args.image or os.environ.get("JUDGE_TOOLCHAIN_IMAGE") or DEFAULT_IMAGE
    runtime = args.runtime or os.environ.get("JUDGE_SANDBOX_RUNTIME") or None
    return lambda problem: LocalDockerExecutor(
        image, sandbox_limits(problem, classes), runtime=runtime
    )


def _load(package: Path) -> Problem:
    try:
        return load_manifest(package)
    except ManifestError as error:
        issues = "\n".join(f"  {issue}" for issue in error.issues)
        raise UsageError(f"{error.source}:\n{issues}") from None


# --- validate -----------------------------------------------------------------------------------

_MARKS = {"ok": "ok  ", "fail": "FAIL", "skip": "--  "}


def _print_check(check: Check) -> None:
    detail = f" — {check.detail}" if check.detail else ""
    print(f"  {_MARKS[check.status]} {check.what}{detail}", flush=True)


def _validate_schema(paths: list[Path]) -> int:
    failed = 0
    for package in _packages(paths):
        try:
            load_manifest(package)
        except ManifestError as error:
            failed += 1
            print(f"FAIL {error.source}")
            for issue in error.issues:
                print(f"  {issue}")
        else:
            print(f"ok   {package / MANIFEST_NAME}")
    return 1 if failed else 0


def _validate(args: argparse.Namespace) -> int:
    if args.schema_only:
        return _validate_schema(args.paths)
    packages = _packages(args.paths)
    classes = _resource_classes(args, packages)
    validator = PackageValidator(
        _executor_factory(args, classes),
        classes,
        seeds=args.seeds,
        determinism=args.determinism,
        on_check=_print_check,
        sink_factory=(lambda title: ConsoleSink()) if args.verbose else None,
    )
    failed = []
    for package in packages:
        print(f"{package}", flush=True)
        checks = validator.validate(package)
        if any(check.status == "fail" for check in checks):
            failed.append(package)
    if failed:
        print(f"невалидных пакетов: {len(failed)} из {len(packages)}")
        return 1
    print(f"все пакеты валидны: {len(packages)}")
    return 0


# --- run ----------------------------------------------------------------------------------------


def _run(args: argparse.Namespace) -> int:
    problem = _load(args.path)
    solution = args.solution.read_bytes()
    seed = args.seed if args.seed is not None else secrets.randbits(63)
    language = get_language(problem.language)
    classes = _resource_classes(args, [args.path])
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    for key in problem.stages:  # artifacts of an earlier run must not mix with this one
        shutil.rmtree(out / key, ignore_errors=True)

    def keep(stage: str, name: str, data: bytes) -> None:
        target = out / stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    print(f"# {problem.id}@{problem.version} · {args.kind} · seed {seed}", flush=True)
    job = Job(problem, args.path, args.kind, seed, solution)
    with (out / "events.jsonl").open("wb") as events:
        sink = FanoutSink(ConsoleSink(), JsonlSink(events))
        with _executor_factory(args, classes)(problem) as executor:
            results = run_pipeline(job, language, executor, sink, classes, on_artifact=keep)
    verdict = aggregate(results)
    report = {
        "problem": problem.id,
        "version": problem.version,
        "kind": args.kind,
        "seed": seed,
        "verdict": verdict.model_dump(mode="json"),
        "stages": [result.model_dump(mode="json") for result in results],
    }
    (out / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"verdict: {describe(results, verdict)}")
    print(f"# результаты: {out}")
    return 0 if verdict.status in ACCEPTED else 1


# --- pack, new, schema --------------------------------------------------------------------------


def _pack(args: argparse.Namespace) -> int:
    problem = _load(args.path)
    try:
        files = package_files(args.path)
    except PackError as error:
        raise UsageError(str(error)) from None
    digest = content_hash(files)
    output = args.output or Path(f"{problem.id}-{problem.version}.tar.zst")
    output.write_bytes(pack(files))
    print(f"{output}")
    print(f"content_hash {digest}")
    return 0


def _new(args: argparse.Namespace) -> int:
    try:
        written = create_package(get_language(args.language), args.dir, args.slug)
    except ScaffoldError as error:
        raise UsageError(str(error)) from None
    for path in written:
        print(path)
    print(f"# дальше: отредактируйте пакет и проверьте его — judge validate {args.dir / args.slug}")
    return 0


def _schema(args: argparse.Namespace) -> int:
    # Bytes, not text: the result must not depend on the console encoding or shell newlines.
    data = SCHEMAS[args.name]().encode("utf-8")
    if args.output is None:
        sys.stdout.buffer.write(data)
    else:
        args.output.write_bytes(data)
    return 0


# --- arguments ----------------------------------------------------------------------------------


def _executor_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("execution")
    group.add_argument(
        "--image", help=f"toolchain image (JUDGE_TOOLCHAIN_IMAGE, default {DEFAULT_IMAGE})"
    )
    group.add_argument("--runtime", help="container runtime, e.g. runsc (JUDGE_SANDBOX_RUNTIME)")
    group.add_argument(
        "--no-docker",
        action="store_true",
        help="run the tools on the host: no sandbox, for trusted code only",
    )
    group.add_argument(
        "--resource-classes",
        type=Path,
        help="resource class limits (JUDGE_RESOURCE_CLASSES, default config/resource-classes.yaml)",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="judge", description="Apparatica judge")
    commands = parser.add_subparsers(required=True, metavar="command")

    validate = commands.add_parser("validate", help="validate problem packages")
    validate.add_argument("paths", nargs="+", type=Path, help="package or directory of packages")
    validate.add_argument(
        "--schema-only", action="store_true", help="check problem.yaml against the schema only"
    )
    validate.add_argument(
        "--seeds",
        type=int,
        default=DEFAULT_SEEDS,
        help=f"seeds per reference solution (default {DEFAULT_SEEDS})",
    )
    validate.add_argument(
        "--determinism",
        action="store_true",
        help="repeat the first reference run with its seed; results must match byte for byte",
    )
    validate.add_argument("-v", "--verbose", action="store_true", help="print the stage consoles")
    _executor_options(validate)
    validate.set_defaults(handler=_validate)

    run = commands.add_parser("run", help="judge a solution locally, like Run or Submit")
    run.add_argument("path", type=Path, help="problem package")
    run.add_argument("--solution", type=Path, required=True, help="solution file (.sv)")
    run.add_argument("--kind", choices=("run", "submit"), default="run")
    run.add_argument("--seed", type=int, help="reproduce a run (default: a new random seed)")
    run.add_argument("--out", type=Path, default=Path("out"), help="results directory (./out)")
    _executor_options(run)
    run.set_defaults(handler=_run)

    pack_ = commands.add_parser("pack", help="deterministic tar.zst of a package and its hash")
    pack_.add_argument("path", type=Path, help="problem package")
    pack_.add_argument("--output", type=Path, help="archive path (default <id>-<version>.tar.zst)")
    pack_.set_defaults(handler=_pack)

    new = commands.add_parser("new", help="create a package from the template")
    new.add_argument("slug", help="problem id, e.g. sync-fifo")
    new.add_argument("--dir", type=Path, default=Path("problems"), help="packages directory")
    new.add_argument("--language", default="systemverilog")
    new.set_defaults(handler=_new)

    schema = commands.add_parser("schema", help="print a JSON Schema generated from the models")
    schema.add_argument(
        "name",
        nargs="?",
        default="problem",
        choices=SCHEMAS,
        help="problem: problem.yaml (default); tb-result: a record of the testbench result file",
    )
    schema.add_argument("--output", type=Path, help="write to a file instead of stdout")
    schema.set_defaults(handler=_schema)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")  # e.g. a cp1251 Windows console
    args = _parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (UsageError, UnknownLanguageError, PipelineConfigError, ExecutorError, OSError) as error:
        print(f"judge: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
