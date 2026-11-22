"""Multi-user foundation: accounts, password hashing, lockout, roles and per-user workspaces.

This is a local, testable core. It is not a production auth system. Before public launch you still need:
HTTPS, a managed database, email verification, password reset, audit logs, and a security review.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

PBKDF2_ITERATIONS = 310_000
MIN_PASSWORD_LENGTH = 12
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
ROLES = ("admin", "member")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AccountError(Exception):
    """Raised for user-facing account problems. The message is safe to show."""


@dataclass(frozen=True)
class User:
    id: int
    email: str
    role: str


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations_text, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(digest_b64)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_text))
    return hmac.compare_digest(actual, expected)


def safe_name(name: str) -> str:
    """Allow only simple names for user files. This blocks path tricks such as '../'."""
    if not _NAME_RE.fullmatch(name or ""):
        raise AccountError("Names may use letters, digits, '-' and '_' only (max 64 characters).")
    return name


class AccountStore:
    def __init__(self, db_path: str | Path, workspace_root: str | Path, *, clock=time.time) -> None:
        self.db_path = str(db_path)
        self.workspace_root = Path(workspace_root)
        self._clock = clock
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at REAL NOT NULL,
                event TEXT NOT NULL,
                user_id INTEGER,
                email TEXT,
                detail TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _audit(self, event: str, user_id: int | None, email: str | None, detail: str = "") -> None:
        """Record an event. Callers commit. Passwords are never written here."""
        self._conn.execute(
            "INSERT INTO audit_log (at, event, user_id, email, detail) VALUES (?, ?, ?, ?, ?)",
            (self._clock(), event, user_id, email, detail),
        )

    def list_audit(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, at, event, user_id, email, detail FROM audit_log ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_user_by_email(self, email: str) -> User | None:
        row = self._conn.execute(
            "SELECT id, email, role FROM users WHERE email = ?", ((email or "").strip().lower(),)
        ).fetchone()
        return User(id=row["id"], email=row["email"], role=row["role"]) if row else None

    def set_password(self, user_id: int, new_password: str) -> None:
        """Operator reset: sets a new password and clears any lockout. Requires access to the database file."""
        if len(new_password or "") < MIN_PASSWORD_LENGTH:
            raise AccountError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        cur = self._conn.execute(
            "UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = 0 WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        if cur.rowcount == 0:
            raise AccountError("No such account.")
        self._audit("password_changed", user_id, None)
        self._conn.commit()

    # ---- accounts ----
    def create_user(self, email: str, password: str, role: str = "member") -> User:
        email = (email or "").strip().lower()
        if not _EMAIL_RE.fullmatch(email):
            raise AccountError("Enter a valid email address.")
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise AccountError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        if role not in ROLES:
            raise AccountError("Unknown role.")
        try:
            cur = self._conn.execute(
                "INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)",
                (email, hash_password(password), role),
            )
        except sqlite3.IntegrityError as exc:
            raise AccountError("An account with this email already exists.") from exc
        self._audit("account_created", cur.lastrowid, email, role)
        self._conn.commit()
        self.user_dir(cur.lastrowid).mkdir(parents=True, exist_ok=True)
        return User(id=cur.lastrowid, email=email, role=role)

    def authenticate(self, email: str, password: str) -> User:
        """Return the user, or raise. The error message does not reveal whether the email exists."""
        email = (email or "").strip().lower()
        row = self._conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        generic = AccountError("Email or password is incorrect.")
        if row is None:
            hash_password(password or "")  # spend similar time to limit account enumeration
            self._audit("login_fail", None, email, "unknown account")
            self._conn.commit()
            raise generic
        now = self._clock()
        if row["locked_until"] > now:
            self._audit("login_locked", row["id"], email)
            self._conn.commit()
            raise AccountError("Too many failed attempts. Try again later.")
        if not verify_password(password or "", row["password_hash"]):
            failed = row["failed_attempts"] + 1
            locked_until = now + LOCKOUT_SECONDS if failed >= MAX_FAILED_ATTEMPTS else 0.0
            self._conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                (0 if locked_until else failed, locked_until, row["id"]),
            )
            self._audit("login_fail", row["id"], email)
            if locked_until:
                self._audit("login_locked", row["id"], email, "lockout started")
            self._conn.commit()
            raise generic
        self._conn.execute("UPDATE users SET failed_attempts = 0, locked_until = 0 WHERE id = ?", (row["id"],))
        self._audit("login_ok", row["id"], row["email"])
        self._conn.commit()
        return User(id=row["id"], email=row["email"], role=row["role"])

    def get_user(self, user_id: int) -> User | None:
        row = self._conn.execute("SELECT id, email, role FROM users WHERE id = ?", (user_id,)).fetchone()
        return None if row is None else User(id=row["id"], email=row["email"], role=row["role"])

    def set_role(self, actor: User, target_id: int, role: str) -> None:
        require_admin(actor)
        if role not in ROLES:
            raise AccountError("Unknown role.")
        self._conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, target_id))
        self._audit("role_changed", target_id, None, f"by {actor.id}: {role}")
        self._conn.commit()

    # ---- per-user storage ----
    def save_user_json(self, actor: User, owner_id: int, name: str, data: dict) -> Path:
        """Save a JSON document (for example a strategy configuration) under the owner's folder."""
        _owner_or_admin(actor, owner_id)
        owner = self.get_user(owner_id)
        if owner is None:
            raise AccountError("File not found.")
        path = self.user_file(owner, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_user_json(self, actor: User, owner_id: int, name: str) -> dict:
        _owner_or_admin(actor, owner_id)
        owner = self.get_user(owner_id)
        if owner is None:
            raise AccountError("File not found.")
        path = self.user_file(owner, name)
        if not path.exists():
            raise AccountError("File not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def user_dir(self, user_id: int) -> Path:
        return self.workspace_root / "users" / str(int(user_id))

    def user_file(self, user: User, name: str, suffix: str = ".json") -> Path:
        """Path to one of the user's own files. Other users' folders can never be reached through this."""
        base = self.user_dir(user.id).resolve()
        target = (base / f"{safe_name(name)}{suffix}").resolve()
        if base not in target.parents:
            raise AccountError("Invalid file name.")
        return target


def _owner_or_admin(actor: User, owner_id: int) -> None:
    if not can_access(actor, owner_id):
        # Same message whether or not the owner exists, so this does not reveal other users' data.
        raise AccountError("File not found.")


def require_admin(user: User) -> None:
    if user.role != "admin":
        raise AccountError("Administrator access required.")


def can_access(actor: User, owner_id: int) -> bool:
    """Owners can access their own data. Admins can access anyone's data."""
    return actor.id == owner_id or actor.role == "admin"
