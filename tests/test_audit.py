"""Audit trail, operator password reset and the account CLI subcommands."""
import pytest

from quant_platform import accounts_cli
from quant_platform.accounts import MAX_FAILED_ATTEMPTS, AccountError, AccountStore

PASSWORD = "correct-horse-battery"


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def store(tmp_path):
    clock = Clock()
    s = AccountStore(tmp_path / "a.sqlite", tmp_path / "w", clock=clock)
    yield s
    s.close()


def _events(store):
    return [row["event"] for row in reversed(store.list_audit(100))]


def test_login_success_and_failure_are_recorded(store):
    store.create_user("nick@example.com", PASSWORD)
    store.authenticate("nick@example.com", PASSWORD)
    with pytest.raises(AccountError):
        store.authenticate("nick@example.com", "wrong-password-here")
    assert _events(store) == ["account_created", "login_ok", "login_fail"]


def test_unknown_email_is_logged_without_user_id(store):
    with pytest.raises(AccountError):
        store.authenticate("ghost@example.com", PASSWORD)
    row = store.list_audit(1)[0]
    assert row["event"] == "login_fail" and row["user_id"] is None and row["email"] == "ghost@example.com"


def test_lockout_is_recorded_once_started(store):
    store.create_user("nick@example.com", PASSWORD)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AccountError):
            store.authenticate("nick@example.com", "wrong-password-here")
    assert "login_locked" in _events(store)


def test_passwords_never_appear_in_audit(store):
    store.create_user("nick@example.com", PASSWORD)
    with pytest.raises(AccountError):
        store.authenticate("nick@example.com", PASSWORD + "x")
    assert all(PASSWORD not in str(row) for row in store.list_audit(100))


def test_set_password_clears_lockout_and_allows_new_password(store):
    user = store.create_user("nick@example.com", PASSWORD)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AccountError):
            store.authenticate("nick@example.com", "wrong-password-here")
    store.set_password(user.id, "a-new-long-password")
    assert store.authenticate("nick@example.com", "a-new-long-password").id == user.id
    assert "password_changed" in _events(store)


def test_set_password_rejects_short_and_unknown(store):
    user = store.create_user("nick@example.com", PASSWORD)
    with pytest.raises(AccountError):
        store.set_password(user.id, "short")
    with pytest.raises(AccountError):
        store.set_password(9999, "a-new-long-password")


def test_cli_reset_password_and_audit(tmp_path, monkeypatch, capsys):
    db, workspace = str(tmp_path / "a.sqlite"), str(tmp_path / "w")
    answers = iter(["first-long-password", "first-long-password"])
    monkeypatch.setattr(accounts_cli.getpass, "getpass", lambda prompt="": next(answers))
    assert accounts_cli.main(["--db", db, "--workspace", workspace, "create", "--email", "n@example.com"]) == 0
    answers = iter(["second-long-password", "second-long-password"])
    assert accounts_cli.main(["--db", db, "--workspace", workspace, "reset-password", "--email", "n@example.com"]) == 0
    assert accounts_cli.main(["--db", db, "--workspace", workspace, "audit", "--limit", "5"]) == 0
    out = capsys.readouterr().out
    assert "password reset for user 1" in out
    assert "password_changed" in out and "account_created" in out
    assert "second-long-password" not in out


def test_cli_reset_unknown_account_fails(tmp_path, monkeypatch, capsys):
    code = accounts_cli.main(["--db", str(tmp_path / "a.sqlite"), "--workspace", str(tmp_path / "w"),
                              "reset-password", "--email", "nobody@example.com"])
    assert code == 2
    assert "no such account" in capsys.readouterr().err
