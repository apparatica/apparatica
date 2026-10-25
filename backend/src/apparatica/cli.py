"""`apparatica` command line: run the API and migrate the database."""

import argparse
import sys
from collections.abc import Sequence

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


def _migrate(args: argparse.Namespace) -> int:
    command.upgrade(alembic_config(), args.revision)
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

    migrate = commands.add_parser("migrate", help="apply database migrations")
    migrate.add_argument("revision", nargs="?", default="head")
    migrate.set_defaults(handler=_migrate)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
