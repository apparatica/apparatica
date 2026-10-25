"""`judge` command line (specs/06 §5)."""

import argparse
import io
import sys
from collections.abc import Sequence
from pathlib import Path

from judge.core.package import MANIFEST_NAME, ManifestError, load_manifest, manifest_json_schema


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


def _validate(args: argparse.Namespace) -> int:
    if not args.schema_only:
        print(
            "judge validate: only --schema-only is implemented so far; "
            "reference, mutant and test checks come with T0.10",
            file=sys.stderr,
        )
        return 2
    failed = 0
    for package in _packages(args.paths):
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


def _schema(args: argparse.Namespace) -> int:
    # Bytes, not text: the result must not depend on the console encoding or shell newlines.
    data = manifest_json_schema().encode("utf-8")
    if args.output is None:
        sys.stdout.buffer.write(data)
    else:
        args.output.write_bytes(data)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")  # e.g. a cp1251 Windows console
    parser = argparse.ArgumentParser(prog="judge", description="Apparatica judge")
    commands = parser.add_subparsers(required=True, metavar="command")

    validate = commands.add_parser("validate", help="validate problem packages")
    validate.add_argument("paths", nargs="+", type=Path, help="package or directory of packages")
    validate.add_argument(
        "--schema-only", action="store_true", help="check problem.yaml against the schema only"
    )
    validate.set_defaults(handler=_validate)

    schema = commands.add_parser("schema", help="print the JSON Schema of problem.yaml")
    schema.add_argument("--output", type=Path, help="write to a file instead of stdout")
    schema.set_defaults(handler=_schema)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
