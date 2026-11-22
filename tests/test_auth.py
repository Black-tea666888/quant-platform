"""Optional sign-in gate in the Streamlit app and the account CLI."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from quant_platform import accounts_cli  # noqa: E402
from quant_platform.accounts import AccountStore  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PASSWORD = "correct-horse-battery"


@pytest.fixture
def auth_env(tmp_path, monkeypatch):
    db = tmp_path / "accounts.sqlite"
    store = AccountStore(db, tmp_path / "workspace")
    store.create_user("nick@example.com", PASSWORD, role="member")
    store.close()
    monkeypatch.setenv("QP_AUTH_DB", str(db))
    monkeypatch.setenv("QP_WORKSPACE", str(tmp_path / "workspace"))
    return db


def _submit(at, email, password):
    at.text_input(key="auth_email").input(email)
    at.text_input(key="auth_password").input(password)
    next(b for b in at.button if b.label == "Sign in").click().run()
    return at


def test_no_database_means_no_login_page(monkeypatch):
    monkeypatch.delenv("QP_AUTH_DB", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert len(at.tabs) == 4


def test_login_required_hides_tabs(auth_env):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert len(at.tabs) == 0


def test_wrong_password_shows_generic_error(auth_env):
    at = AppTest.from_file(APP, default_timeout=30).run()
    _submit(at, "nick@example.com", "wrong-password-here")
    assert not at.exception
    assert any("incorrect" in e.value for e in at.error)
    assert len(at.tabs) == 0


def test_correct_password_opens_app(auth_env):
    at = AppTest.from_file(APP, default_timeout=30).run()
    _submit(at, "nick@example.com", PASSWORD)
    assert not at.exception
    assert len(at.tabs) == 4


def test_cli_creates_account(tmp_path, monkeypatch, capsys):
    answers = iter(["another-long-password", "another-long-password"])
    monkeypatch.setattr(accounts_cli.getpass, "getpass", lambda prompt="": next(answers))
    code = accounts_cli.main(["--db", str(tmp_path / "a.sqlite"), "--workspace", str(tmp_path / "w"),
                              "create", "--email", "new@example.com"])
    assert code == 0
    assert "created user 1" in capsys.readouterr().out


def test_cli_rejects_mismatched_passwords(tmp_path, monkeypatch, capsys):
    answers = iter(["one-long-password", "two-long-password"])
    monkeypatch.setattr(accounts_cli.getpass, "getpass", lambda prompt="": next(answers))
    code = accounts_cli.main(["--db", str(tmp_path / "a.sqlite"), "--workspace", str(tmp_path / "w"),
                              "create", "--email", "new@example.com"])
    assert code == 2
