import logging
import re
import threading
import unicodedata
from pathlib import Path

from .config import settings

logger = logging.getLogger("weshare.moderation")

URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
PROMO_RE = re.compile(r"(?:\b(?:buy now|crypto giveaway|free money|click here)\b)", re.I)
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_terms_lock = threading.Lock()
_terms_cache: dict[str, object] = {"key": None, "terms": []}


class ContentRejected(ValueError):
    """Raised when user supplied text fails validation or moderation."""


def _file_key(path: Path):
    try:
        stat = path.stat()
    except OSError:
        return None
    return (str(path), stat.st_mtime_ns, stat.st_size)


def load_blocked_terms(path: Path | None = None) -> list[str]:
    """Read the administrator maintained block list, cached on file change."""
    target = path or settings.blocked_terms_path
    key = _file_key(target)
    with _terms_lock:
        if _terms_cache["key"] == key:
            return list(_terms_cache["terms"])  # type: ignore[arg-type]
    terms: list[str] = []
    if target.exists():
        try:
            raw = target.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Could not read blocked terms file: %s", target)
            raw = ""
        for line in raw.splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                terms.append(value)
    with _terms_lock:
        _terms_cache["key"] = key
        _terms_cache["terms"] = terms
    return list(terms)


def validate_text(text: str, maximum: int) -> None:
    """Reject empty text, over-long text, blank lines and control characters."""
    if text is None or not isinstance(text, str):
        raise ContentRejected("Text must be a string.")
    if not text or not text.strip():
        raise ContentRejected("Text cannot be empty.")
    if len(text) > maximum:
        raise ContentRejected(f"Text must be {maximum} characters or fewer.")
    if "\n\n" in text or "\r\n\r\n" in text or re.search(r"\n[ \t]*\n", text):
        raise ContentRejected("Blank lines and multiple paragraphs are not allowed.")
    if any(not line.strip() for line in text.splitlines()):
        raise ContentRejected("Empty lines are not allowed.")
    if CONTROL_CHAR_RE.search(text):
        raise ContentRejected("Control characters are not allowed.")


def moderate(text: str) -> None:
    """Apply the configured block list and URL/promotion heuristics."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    for term in load_blocked_terms():
        candidate = unicodedata.normalize("NFKC", term).casefold()
        if not candidate:
            continue
        if re.search(r"(?<!\w)" + re.escape(candidate) + r"(?!\w)", normalized):
            raise ContentRejected("This text contains language that is not allowed.")
        if len(candidate) >= 4 and candidate in compact:
            raise ContentRejected("This text contains language that is not allowed.")
    if PROMO_RE.search(text):
        raise ContentRejected("This text appears to contain unwanted promotional spam.")
    for match in URL_RE.findall(text):
        if re.search(
            r"https?://(?:\d{1,3}\.){3}\d{1,3}|\.(?:zip|mov|click|top|xyz)(?:/|$)",
            match,
            re.I,
        ):
            raise ContentRejected("This link is not allowed.")
