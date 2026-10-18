"""OpenLegal operator CLI.

Tiny argparse-based runner so deployments and developers can drive seed +
reset from a shell. Wired into pyproject.toml [project.scripts] as
`openlegal`, so after `pip install -e .` you can run:

  openlegal seed
  openlegal reset
  openlegal migrate
  openlegal version
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _print(data: dict) -> None:
    print(json.dumps(data, indent=2, sort_keys=True, default=str))


def _cmd_seed(_args) -> int:
    from openlegal.services.seed import seed_if_empty
    result = asyncio.run(seed_if_empty())
    _print(result)
    return 0


def _cmd_reset(_args) -> int:
    from openlegal.services.seed import reset_and_seed
    result = asyncio.run(reset_and_seed())
    _print(result)
    return 0


def _cmd_migrate(_args) -> int:
    """Run `alembic upgrade head` from the package's checkout."""
    import subprocess
    try:
        subprocess.check_call(["alembic", "upgrade", "head"])
    except subprocess.CalledProcessError as exc:
        print(f"alembic failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_version(_args) -> int:
    from importlib import metadata
    try:
        v = metadata.version("openlegal")
    except metadata.PackageNotFoundError:
        v = "unknown (not installed)"
    print(f"openlegal {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openlegal", description="OpenLegal CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("seed", help="Seed demo data if absent")
    sub.add_parser("reset", help="Wipe and reseed demo data")
    sub.add_parser("migrate", help="Run alembic upgrade head")
    sub.add_parser("version", help="Print version")

    args = parser.parse_args(argv)
    if args.cmd == "seed":
        return _cmd_seed(args)
    if args.cmd == "reset":
        return _cmd_reset(args)
    if args.cmd == "migrate":
        return _cmd_migrate(args)
    if args.cmd == "version":
        return _cmd_version(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
