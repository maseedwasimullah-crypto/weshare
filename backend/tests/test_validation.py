import pytest

from app.config import Settings
from app.moderation import ContentRejected, load_blocked_terms, moderate, validate_text


def test_database_url_defaults_to_psycopg3():
    """Managed Postgres providers hand out a plain postgresql:// URL."""
    assert (
        Settings(database_url="postgresql://u:p@host:5432/db").database_url
        == "postgresql+psycopg://u:p@host:5432/db"
    )
    assert (
        Settings(database_url="postgres://u:p@host:5432/db").database_url
        == "postgresql+psycopg://u:p@host:5432/db"
    )


def test_database_url_keeps_an_explicit_driver():
    assert (
        Settings(database_url="postgresql+psycopg://u:p@host/db").database_url
        == "postgresql+psycopg://u:p@host/db"
    )
    assert (
        Settings(database_url="postgresql+psycopg2://u:p@host/db").database_url
        == "postgresql+psycopg2://u:p@host/db"
    )
    assert (
        Settings(database_url="sqlite:///./test.db").database_url == "sqlite:///./test.db"
    )


def test_frontend_origins_accepts_a_comma_separated_list():
    settings = Settings(frontend_origin="https://a.example, https://b.example/")
    assert settings.frontend_origins == ["https://a.example", "https://b.example"]


def test_frontend_origins_ignores_blank_entries():
    """An empty entry must not turn into a wildcard origin."""
    assert Settings(frontend_origin="").frontend_origins == []
    assert Settings(frontend_origin="  ,  ").frontend_origins == []
    assert Settings(frontend_origin="https://a.example,").frontend_origins == [
        "https://a.example"
    ]


def test_cors_allows_the_configured_origin(client):
    origin = {"Origin": "http://localhost:5173"}
    response = client.get("/api/health", headers=origin)
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_preflight_rejects_an_unknown_origin(client):
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_text_validation():
    validate_text("Two lines\nremain readable.", 1000)
    for value in ("", "   ", "first\n\nsecond", "x" * 1001):
        with pytest.raises(ContentRejected):
            validate_text(value, 1000)


def test_empty_and_whitespace_only_text_is_rejected():
    for value in ("", " ", "\t", "\n", "\r\n", "   \n   "):
        with pytest.raises(ContentRejected):
            validate_text(value, 1000)


def test_blank_lines_are_rejected():
    for value in ("first\n\nsecond", "first\n \nsecond", "first\r\n\r\nsecond", "first\n\t\nsecond"):
        with pytest.raises(ContentRejected):
            validate_text(value, 1000)


def test_empty_line_inside_text_is_rejected():
    with pytest.raises(ContentRejected):
        validate_text("first\n\nsecond", 1000)
    with pytest.raises(ContentRejected):
        validate_text("first\n   \nsecond", 1000)


def test_single_newline_is_allowed():
    validate_text("first\nsecond", 1000)
    validate_text("trailing newline\n", 1000)


def test_length_limits():
    validate_text("x" * 1000, 1000)
    with pytest.raises(ContentRejected):
        validate_text("x" * 1001, 1000)
    validate_text("y" * 100, 100)
    with pytest.raises(ContentRejected):
        validate_text("y" * 101, 100)


def test_control_characters_are_rejected():
    with pytest.raises(ContentRejected):
        validate_text("hello\x00world", 1000)


def test_moderation_blocks_configured_terms(use_blocked_terms):
    with pytest.raises(ContentRejected):
        moderate("this contains forbiddenterm inside")
    moderate("this text is completely fine")


def test_moderation_ignores_comments_and_blank_lines_in_block_list(use_blocked_terms):
    terms = load_blocked_terms()
    assert "forbiddenterm" in terms
    assert "# comment line" not in terms
    assert "" not in terms


def test_block_list_with_a_byte_order_mark_does_not_become_a_term(tmp_path, monkeypatch):
    """A BOM in blocked_terms.txt must not turn the first comment into a term."""
    from app.config import settings

    path = tmp_path / "blocked_terms.txt"
    path.write_bytes("\ufeff# a comment line\nsecondterm\n".encode("utf-8"))
    monkeypatch.setattr(settings, "moderation_blocked_terms_file", str(path))

    terms = load_blocked_terms()
    assert "secondterm" in terms
    assert not any(term.startswith("\ufeff") for term in terms)
    assert len(terms) == 1


def test_moderation_blocks_promotional_text():
    with pytest.raises(ContentRejected):
        moderate("please buy now while supplies last")
    with pytest.raises(ContentRejected):
        moderate("visit www.suspicious.zip today")


def test_moderation_allows_ordinary_links():
    moderate("read https://example.org/news for details")
