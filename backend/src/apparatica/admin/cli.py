"""`apparatica-admin` command line: platform administration (specs/06 §6, FR-ADM-01).

Exit codes: 0 done, 1 refused (nothing changed), 2 usage error.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from apparatica.core.db import Database
from apparatica.core.platform import load_platform_config
from apparatica.core.settings import get_settings
from apparatica.core.storage import Storage
from apparatica.problems.importer import (
    TAGS_FILE,
    ImportRefusedError,
    Package,
    import_packages,
    load_tags,
    read_package,
)
from judge.core.pack import PackError
from judge.core.package import MANIFEST_NAME, ManifestError


def _package_dirs(paths: Sequence[Path]) -> list[Path]:
    """A path is a package (has problem.yaml) or a directory of packages, like problems/."""
    packages = []
    for path in paths:
        if (path / MANIFEST_NAME).is_file():
            packages.append(path)
        else:
            packages.extend(sorted(p for p in path.iterdir() if (p / MANIFEST_NAME).is_file()))
    return packages


def _read(dirs: Sequence[Path]) -> list[Package] | None:
    packages, failed = [], False
    for path in dirs:
        try:
            packages.append(read_package(path))
        except ManifestError as error:
            failed = True
            print(f"FAIL {error.source}")
            for issue in error.issues:
                print(f"  {issue}")
        except PackError as error:
            failed = True
            print(f"FAIL {path}: {error}")
    return None if failed else packages


def _import(args: argparse.Namespace) -> int:
    dirs = _package_dirs(args.paths)
    if not dirs:
        print("пакеты задач не найдены", file=sys.stderr)
        return 2
    packages = _read(dirs)
    if packages is None:
        print("импорт отменён: есть невалидные пакеты; база не изменена")
        return 1
    settings = get_settings()
    difficulties = [d.key for d in load_platform_config(settings.config_dir).difficulties]
    tags_file: Path = args.tags or dirs[0].resolve().parent / TAGS_FILE

    async def run() -> list[str]:
        database = Database(settings.database_url)
        try:
            results = await import_packages(
                database,
                Storage(settings),
                settings.s3_bucket_packages,
                packages,
                load_tags(tags_file),
                difficulties,
                publish=args.publish,
            )
        finally:
            await database.dispose()
        return [
            f"{result.outcome:<9} {result.package.name}"
            + (", published" if result.published else "")
            for result in results
        ]

    try:
        lines = asyncio.run(run())
    except ImportRefusedError as error:
        for issue in error.issues:
            print(f"FAIL {issue}")
        print("импорт отменён; база не изменена")
        return 1
    print("\n".join(lines))
    created = sum(line.startswith("created") for line in lines)
    print(f"новых версий: {created}, без изменений: {len(lines) - created}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apparatica-admin", description="Apparatica administration"
    )
    commands = parser.add_subparsers(required=True, metavar="command")

    problems = commands.add_parser("problems", help="problems of the catalogue")
    problem_commands = problems.add_subparsers(required=True, metavar="command")
    import_ = problem_commands.add_parser(
        "import", help="import problem packages: new versions, tags, publication"
    )
    import_.add_argument("paths", nargs="+", type=Path, help="a package or a directory of packages")
    import_.add_argument(
        "--publish", action="store_true", help="make the imported versions current and published"
    )
    import_.add_argument(
        "--tags", type=Path, help=f"tag catalogue (default: {TAGS_FILE} next to the packages)"
    )
    import_.set_defaults(handler=_import)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
