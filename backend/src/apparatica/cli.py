"""`apparatica` command line: run the API or the ingestor, migrate the database, write the OpenAPI
document."""

import argparse
import asyncio
import json
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from apparatica.core.settings import get_settings


def alembic_config(database_url: str | None = None) -> Config:
    """Migrations live in the package (`apparatica.migrations`): no alembic.ini is needed."""
    config = Config()
    config.set_main_option("script_location", "apparatica:migrations")
    config.set_main_option("sqlalchemy.url", database_url or get_settings().database_url)
    return config


def _serve(args: argparse.Namespace) -> int:
    uvicorn.run(
        "apparatica.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=True,
        forwarded_allow_ips=args.forwarded_allow_ips,
        log_config=None,  # structlog configures logging in create_app
    )
    return 0


def _ingest(args: argparse.Namespace) -> int:
    from apparatica.core.logging import configure_logging
    from apparatica.judging.consumer import run_ingest

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    async def main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for name in (signal.SIGINT, signal.SIGTERM):
            signal.signal(name, lambda *_: loop.call_soon_threadsafe(stop.set))
        await run_ingest(settings, stop)

    asyncio.run(main())
    return 0


def _migrate(args: argparse.Namespace) -> int:
    command.upgrade(alembic_config(), args.revision)
    return 0


def openapi_document(config_dir: Path | None = None) -> str:
    """The OpenAPI document of the API, as committed in backend/openapi.json (specs/05 §0)."""
    from apparatica.main import create_app  # the app is needed only by this command

    settings = get_settings()
    if config_dir is not None:
        settings = settings.model_copy(update={"config_dir": config_dir})
    schema = create_app(settings).openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def _openapi(args: argparse.Namespace) -> int:
    document = openapi_document(args.config_dir)
    if args.output is None:
        sys.stdout.write(document)
    else:
        args.output.write_text(document, encoding="utf-8", newline="\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apparatica", description="Apparatica platform")
    commands = parser.add_subparsers(required=True, metavar="command")

    serve = commands.add_parser("serve", help="run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="restart on code changes")
    serve.add_argument(
        "--forwarded-allow-ips",
        default="127.0.0.1",
        help="proxies trusted for X-Forwarded-* (the Caddy address in compose)",
    )
    serve.set_defaults(handler=_serve)

    ingest = commands.add_parser(
        "ingest", help="store the results of checks: judge:results to the database (ADR-0009)"
    )
    ingest.set_defaults(handler=_ingest)

    migrate = commands.add_parser("migrate", help="apply database migrations")
    migrate.add_argument("revision", nargs="?", default="head")
    migrate.set_defaults(handler=_migrate)

    openapi = commands.add_parser("openapi", help="write the OpenAPI document of the API")
    openapi.add_argument("--output", type=Path, help="file to write (default: stdout)")
    openapi.add_argument("--config-dir", type=Path, help="directory of config/*.yaml")
    openapi.set_defaults(handler=_openapi)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
