"""Create an account from the command line. Self-signup is not offered.

Example:
    python -m quant_platform.accounts_cli --db accounts.sqlite --workspace workspace \
        create --email you@example.com --role admin
The password is read from the terminal without echo.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from quant_platform.accounts import AccountError, AccountStore


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage quant-platform accounts")
    p.add_argument("--db", required=True, help="SQLite file for accounts")
    p.add_argument("--workspace", required=True, help="folder for per-user files")
    sub = p.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create an account")
    create.add_argument("--email", required=True)
    create.add_argument("--role", default="member", choices=("admin", "member"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = AccountStore(args.db, args.workspace)
    try:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("error: passwords do not match", file=sys.stderr)
            return 2
        user = store.create_user(args.email, password, role=args.role)
        print(f"created user {user.id} ({user.email}, {user.role})")
        return 0
    except AccountError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
