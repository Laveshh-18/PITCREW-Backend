from app.security import redact


def test_db_url_and_jwt_redacted():
    out = redact("connect postgresql://u:secret@host:6543/db failed eyJhbGciOiJI.eyJzdWIiOiIx.abcdefghijk")
    assert "secret" not in out and "eyJ" not in out
