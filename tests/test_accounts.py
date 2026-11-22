import pytest

from quant_platform.accounts import (
    AccountError,
    AccountStore,
    can_access,
    hash_password,
    require_admin,
    safe_name,
    verify_password,
)

PW = "correct horse battery staple"


@pytest.fixture
def store(tmp_path):
    clock = {"now": 1_000_000.0}
    s = AccountStore(tmp_path / "db.sqlite", tmp_path / "ws", clock=lambda: clock["now"])
    s.clock = clock
    yield s
    s.close()


def test_password_hash_round_trip_and_is_salted():
    h1 = hash_password(PW, iterations=1000)
    h2 = hash_password(PW, iterations=1000)
    assert h1 != h2  # different salts
    assert verify_password(PW, h1)
    assert not verify_password("wrong password here", h1)


def test_verify_rejects_malformed_hash():
    assert not verify_password(PW, "not-a-hash")


def test_create_and_login(store):
    user = store.create_user("Alice@Example.com", PW)
    assert user.email == "alice@example.com"  # normalized
    logged_in = store.authenticate("alice@example.com", PW)
    assert logged_in.id == user.id


def test_duplicate_email_is_rejected(store):
    store.create_user("a@example.com", PW)
    with pytest.raises(AccountError, match="already exists"):
        store.create_user("A@example.com", PW)


def test_short_password_is_rejected(store):
    with pytest.raises(AccountError, match="at least"):
        store.create_user("a@example.com", "short")


def test_invalid_email_is_rejected(store):
    with pytest.raises(AccountError, match="valid email"):
        store.create_user("not-an-email", PW)


def test_wrong_password_and_unknown_email_give_same_message(store):
    store.create_user("a@example.com", PW)
    with pytest.raises(AccountError) as wrong:
        store.authenticate("a@example.com", "wrong password here")
    with pytest.raises(AccountError) as unknown:
        store.authenticate("nobody@example.com", "wrong password here")
    assert str(wrong.value) == str(unknown.value)


def test_lockout_after_repeated_failures_then_recovers(store):
    store.create_user("a@example.com", PW)
    for _ in range(5):
        with pytest.raises(AccountError):
            store.authenticate("a@example.com", "wrong password here")
    with pytest.raises(AccountError, match="Too many failed attempts"):
        store.authenticate("a@example.com", PW)  # even the right password is blocked while locked
    store.clock["now"] += 16 * 60
    assert store.authenticate("a@example.com", PW).email == "a@example.com"


def test_successful_login_resets_failure_count(store):
    store.create_user("a@example.com", PW)
    for _ in range(4):
        with pytest.raises(AccountError):
            store.authenticate("a@example.com", "wrong password here")
    store.authenticate("a@example.com", PW)
    for _ in range(4):
        with pytest.raises(AccountError):
            store.authenticate("a@example.com", "wrong password here")
    # Still not locked: only 4 failures since the last success.
    assert store.authenticate("a@example.com", PW).email == "a@example.com"


def test_user_files_are_isolated_per_user(store, tmp_path):
    alice = store.create_user("alice@example.com", PW)
    bob = store.create_user("bob@example.com", PW)
    alice_file = store.user_file(alice, "portfolio")
    bob_file = store.user_file(bob, "portfolio")
    assert alice_file != bob_file
    assert str(store.user_dir(alice.id).resolve()) in str(alice_file)
    assert str(store.user_dir(bob.id).resolve()) in str(bob_file)


@pytest.mark.parametrize("bad", ["../secret", "a/b", "..", "", "name with space", "x" * 65])
def test_path_tricks_are_rejected(store, bad):
    alice = store.create_user("alice@example.com", PW)
    with pytest.raises(AccountError):
        store.user_file(alice, bad)


def test_safe_name_accepts_simple_names():
    assert safe_name("my_portfolio-1") == "my_portfolio-1"


def test_only_admin_can_change_roles(store):
    admin = store.create_user("admin@example.com", PW, role="admin")
    member = store.create_user("m@example.com", PW)
    other = store.create_user("o@example.com", PW)
    with pytest.raises(AccountError, match="Administrator"):
        store.set_role(member, other.id, "admin")
    store.set_role(admin, other.id, "admin")
    assert store.get_user(other.id).role == "admin"


def test_access_rules():
    owner = type("U", (), {"id": 1, "role": "member"})()
    stranger = type("U", (), {"id": 2, "role": "member"})()
    admin = type("U", (), {"id": 3, "role": "admin"})()
    assert can_access(owner, 1)
    assert not can_access(stranger, 1)
    assert can_access(admin, 1)


def test_require_admin_blocks_members():
    member = type("U", (), {"id": 1, "role": "member"})()
    with pytest.raises(AccountError):
        require_admin(member)


def test_owner_can_save_and_load_own_document(store):
    alice = store.create_user("alice@example.com", PW)
    store.save_user_json(alice, alice.id, "strategy", {"fast": 20, "slow": 60})
    assert store.load_user_json(alice, alice.id, "strategy") == {"fast": 20, "slow": 60}


def test_other_member_cannot_read_or_write_someone_elses_document(store):
    alice = store.create_user("alice@example.com", PW)
    bob = store.create_user("bob@example.com", PW)
    store.save_user_json(alice, alice.id, "strategy", {"secret": 1})
    with pytest.raises(AccountError, match="not found"):
        store.load_user_json(bob, alice.id, "strategy")
    with pytest.raises(AccountError, match="not found"):
        store.save_user_json(bob, alice.id, "strategy", {"overwritten": True})
    assert store.load_user_json(alice, alice.id, "strategy") == {"secret": 1}


def test_admin_can_read_any_document(store):
    admin = store.create_user("admin@example.com", PW, role="admin")
    alice = store.create_user("alice@example.com", PW)
    store.save_user_json(alice, alice.id, "strategy", {"fast": 5})
    assert store.load_user_json(admin, alice.id, "strategy") == {"fast": 5}


def test_missing_document_gives_generic_error(store):
    alice = store.create_user("alice@example.com", PW)
    with pytest.raises(AccountError, match="not found"):
        store.load_user_json(alice, alice.id, "does-not-exist")
