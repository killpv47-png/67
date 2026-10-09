import pytest

from ghbot.core import crypto
from ghbot.core.redact import redact, register_secret
from ghbot.github.access import classify_access
from ghbot.github.zipflow import ZipError, analyze_zip, detect_secrets_in_texts, strip_root
from ghbot.i18n import LANGS, missing_keys, t


# ------------------------------------------------------------------ crypto
def test_crypto_roundtrip_and_salt():
    a = crypto.encrypt(b"hello", "k" * 16)
    b = crypto.encrypt(b"hello", "k" * 16)
    assert a != b  # random salt+nonce
    assert crypto.decrypt(a, "k" * 16) == b"hello"
    with pytest.raises(crypto.DecryptError):
        crypto.decrypt(a, "wrong-key-wrong-key")
    with pytest.raises(crypto.DecryptError):
        crypto.decrypt(b"garbage", "k" * 16)


# ------------------------------------------------------------------ redact
def test_redact_patterns_and_known():
    s = "token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 and sk-abcdefghijklmnopqrstuvwxyz and 123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    out = redact(s)
    assert "ghp_" not in out and "sk-abc" not in out and "AAAAAAAA" not in out
    register_secret("my-very-secret-value")
    assert "my-very-secret-value" not in redact("x my-very-secret-value y")
    assert redact("api_key=abcdefghijklmnop123") == "api_key=[REDACTED]"


# ------------------------------------------------------------------ access
@pytest.mark.parametrize("scopes,level", [
    (["repo", "workflow", "delete_repo", "admin:org"], "GOD"),
    (["repo", "workflow", "delete_repo", "user"], "GOD"),
    (["repo", "workflow", "delete_repo"], "ARCHITECT"),
    (["repo", "workflow"], "ENGINEER"),
    (["repo"], "DEVELOPER"),
    (["public_repo"], "OBSERVER"),
    ([], "GHOST"),
])
def test_access_levels(scopes, level):
    assert classify_access(scopes).name == level


def test_access_fine_grained():
    assert classify_access(None, fine_grained_probe={"can_read": True}).name == "OBSERVER"
    assert classify_access(None, fine_grained_probe={"can_read": True, "can_write": True, "can_workflow": True}).name == "ENGINEER"
    assert classify_access(None, fine_grained_probe={"can_read": True, "can_write": True, "can_workflow": True,
                                                     "can_delete": True, "can_admin": True}).name == "GOD"


# --------------------------------------------------------------------- zip
def _zip(files: dict[str, bytes]) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


def test_zip_single_root_and_secrets():
    data = _zip({
        "proj/README.md": b"hi",
        "proj/.github/workflows/ci.yml": b"env:\n  A: ${{ secrets.MY_TOKEN }}\n  B: ${{ secrets.GITHUB_TOKEN }}\n  C: ${{ vars.REGION }}",
        "__MACOSX/._x": b"junk",
        "proj/../evil.txt": b"x",
    })
    zi = analyze_zip(data)
    assert zi.single_root == "proj"
    assert zi.secrets == ["MY_TOKEN"]  # GITHUB_TOKEN excluded
    assert zi.variables == ["REGION"]
    assert any("evil" in s or "__MACOSX" in s for s in zi.skipped)
    stripped = strip_root(zi)
    assert set(stripped.files) == {"README.md", ".github/workflows/ci.yml"}
    assert stripped.single_root is None
    assert stripped.secrets == ["MY_TOKEN"]


def test_zip_multi_root_and_errors():
    zi = analyze_zip(_zip({"a.txt": b"1", "dir/b.txt": b"2"}))
    assert zi.single_root is None and zi.count == 2
    with pytest.raises(ZipError):
        analyze_zip(b"not a zip")
    with pytest.raises(ZipError):
        analyze_zip(_zip({"d/": b""}))  # directories only -> empty


def test_detect_secrets_in_texts():
    assert detect_secrets_in_texts({"a.yml": "${{secrets.X}} ${{ secrets.Y }}"}) == ["X", "Y"]


# -------------------------------------------------------------------- i18n
def test_i18n_complete_and_fallback():
    assert len(LANGS) == 10
    assert missing_keys("fa") == []
    assert t("ru", "btn_repos") != t("en", "btn_repos")
    assert t("ru", "nr_summary", owner="o", name="n", vis="v", readme=1, gitignore=2, license=3, desc=4,
             issues=5, wiki=6, projects=7, template=8).startswith("📋")  # falls back to EN
    assert t("xx", "btn_repos") == t("en", "btn_repos")
    assert t("en", "does_not_exist") == "does_not_exist"


def test_i18n_placeholders_match_english():
    import re
    ph = lambda s: set(re.findall(r"{(\w+)}", s))  # noqa: E731
    from ghbot.i18n import en
    for lang, table in LANGS.items():
        for k, v in table.items():
            if k in en.STRINGS:
                assert ph(v) <= ph(en.STRINGS[k]), f"{lang}:{k} has unknown placeholders"
