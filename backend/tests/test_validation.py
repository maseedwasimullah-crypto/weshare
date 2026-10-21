import pytest

from app.moderation import ContentRejected, load_blocked_terms, moderate, validate_text


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


def test_moderation_blocks_promotional_text():
    with pytest.raises(ContentRejected):
        moderate("please buy now while supplies last")
    with pytest.raises(ContentRejected):
        moderate("visit www.suspicious.zip today")


def test_moderation_allows_ordinary_links():
    moderate("read https://example.org/news for details")
