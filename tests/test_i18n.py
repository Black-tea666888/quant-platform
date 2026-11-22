from quant_platform.i18n import CATALOGS, DEFAULT_LANG


def test_every_english_key_has_a_translation():
    missing = set(CATALOGS[DEFAULT_LANG]) - set(CATALOGS["zh-TW"])
    assert not missing, f"missing zh-TW keys: {sorted(missing)}"


def test_no_orphan_translations():
    extra = set(CATALOGS["zh-TW"]) - set(CATALOGS[DEFAULT_LANG])
    assert not extra, f"zh-TW keys without English: {sorted(extra)}"
