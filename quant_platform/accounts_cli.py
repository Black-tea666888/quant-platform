"""Operator commands for accounts. There is no self-signup and no web reset.

These commands need access to the accounts database file, which is the trust boundary.

Examples:
    python -m quant_platform.accounts_cli --db accounts.sqlite --workspace workspace create --email you@example.com --role admin
    python -m quant_platform.accounts_cli --db accounts.sqlite --workspace workspace reset-password --email you@example.com
    python -m quant_platform.accounts_cli --db accounts.sqlite --workspace workspace audit --limit 20

Passwords are read from the terminal without echo.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timezone

from quant_platform.accounts import AccountError, AccountStore


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage quant-platform accounts")
    p.add_argument("--db", required=True, help="SQLite file for accounts")
    p.add_argument("--workspace", required=True, help="folder for per-user files")
    sub = p.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create an account")
    create.add_argument("--email", required=True)
    create.add_argument("--role", default="member", choices=("admin", "member"))
    reset = sub.add_parser("reset-password", help="set a new password and clear any lockout")
    reset.add_argument("--email", required=True)
    audit = sub.add_parser("audit", help="show the most recent audit events")
    audit.add_argument("--limit", type=int, default=50)
    return p


def _ask_password() -> str | None:
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        print("error: passwords do not match", file=sys.stderr)
        return None
    return password


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = AccountStore(args.db, args.workspace)
    try:
        if args.command == "create":
            password = _ask_password()
            if password is None:
                return 2
            user = store.create_user(args.email, password, role=args.role)
            print(f"created user {user.id} ({user.email}, {user.role})")
        elif args.command == "reset-password":
            user = store.get_user_by_email(args.email)
            if user is None:
                print("error: no such account", file=sys.stderr)
                return 2
            password = _ask_password()
            if password is None:
                return 2
            store.set_password(user.id, password)
            print(f"password reset for user {user.id}")
        elif args.command == "audit":
            for row in store.list_audit(args.limit):
                when = datetime.fromtimestamp(row["at"], tz=timezone.utc).isoformat(timespec="seconds")
                who = row["email"] or f"user {row['user_id']}"
                print(f"{when}  {row['event']:<16} {who}  {row['detail']}".rstrip())
        return 0
    except AccountError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
