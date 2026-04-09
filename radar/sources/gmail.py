"""Gmail source connector for ai-radar.

Stage: source fetch (step 1 of pipeline)
Input:  GmailConfig + GMAIL_REFRESH_TOKEN env var
Output: list[RawItem] (content_type="email")

Reads unread emails from configured Gmail labels, filtered to configured senders.
MVP supports newsletter_type="link_list" only: extracts URLs from each email body
and returns one RawItem per URL. The URL is the linked article; surrounding link
text becomes the title (falls back to email subject if link text is absent/generic).

OAuth credentials are loaded from the GMAIL_REFRESH_TOKEN environment variable.

Design decisions:
- Title fallback: link text → email subject (issue #64)
- max_age_days filtering: applied via Gmail API query operator newer_than:Nd (issue #65)

Spec reference: SPEC.md §3.1 (Gmail connector, OAuth), §3.7 (failure handling).
"""

# 1. Standard library imports
import base64
import binascii
import os
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

# 2. Third-party imports
import structlog
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# 3. Internal imports
from radar.config import GmailConfig, GmailSenderConfig
from radar.models import RawItem
from radar.sources.base import Source

# 4. Module-level logger
logger = structlog.get_logger(__name__)

# 5. Constants
_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_MAX_RESULTS = 25
_GENERIC_LINK_TEXTS = frozenset(
    {"read more", "click here", "here", "read", "more", "link", "view", "open"}
)


class GmailSource(Source):
    """Gmail source connector.

    Reads link-list newsletters from configured Gmail labels, filtered to
    configured senders. Returns one RawItem per extracted URL.
    """

    def __init__(self, config: GmailConfig) -> None:
        self._config = config

    def fetch(self) -> list[RawItem]:
        """Fetch recent newsletter emails and extract article URLs as RawItems.

        Returns an empty list if the connector is disabled, credentials are
        missing/expired, or all API calls fail. Never raises.
        """
        if not self._config.enabled:
            return []

        try:
            creds = _get_credentials()
        except RefreshError:
            logger.error(  # noqa: TRY400
                "gmail_token_expired",
                instructions=(
                    "Re-run 'python -m radar auth gmail' and update the GMAIL_REFRESH_TOKEN secret."
                ),
            )
            return []

        if creds is None:
            return []

        start = time.monotonic()
        try:
            service = build("gmail", "v1", credentials=creds)
        except Exception:  # noqa: BLE001 — google-api-client raises broadly on build failures
            logger.error("gmail_build_failed")  # noqa: TRY400
            return []

        query = _build_query(self._config)
        items: list[RawItem] = []

        for label in self._config.labels:
            label_items = _fetch_label(service, label, query, self._config)
            items.extend(label_items)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "source_fetch_complete",
            source="gmail",
            item_count=len(items),
            elapsed_ms=elapsed_ms,
        )
        return items


def _get_credentials() -> Credentials | None:
    """Load OAuth credentials from GMAIL_REFRESH_TOKEN env var.

    Returns None and logs ERROR if the token is missing.
    Raises RefreshError if the token is expired.
    """
    token = os.environ.get("GMAIL_REFRESH_TOKEN")
    if not token:
        logger.error(
            "gmail_missing_refresh_token",
            instructions=(
                "Set GMAIL_REFRESH_TOKEN environment variable. "
                "Run 'python -m radar auth gmail' to obtain a token."
            ),
        )
        return None

    return Credentials(  # type: ignore[no-untyped-call]
        token=None,
        refresh_token=token,
        token_uri="https://oauth2.googleapis.com/token",  # noqa: S106
        client_id=os.environ.get("GMAIL_CLIENT_ID", ""),
        client_secret=os.environ.get("GMAIL_CLIENT_SECRET", ""),
        scopes=_GMAIL_SCOPES,
    )


def _build_query(config: GmailConfig) -> str:
    """Build the Gmail search query string."""
    parts = [f"newer_than:{config.max_age_days}d"]
    if config.senders:
        sender_terms = " OR ".join(f"from:{s.email}" for s in config.senders)
        parts.append(f"({sender_terms})")
    return " ".join(parts)


def _fetch_label(
    service: object,
    label: str,
    query: str,
    config: GmailConfig,
) -> list[RawItem]:
    """Fetch and process all matching messages from a single label."""
    try:
        response = (
            service.users()  # type: ignore[attr-defined]
            .messages()
            .list(userId="me", labelIds=[label], q=query, maxResults=_MAX_RESULTS)
            .execute()
        )
    except HttpError as exc:
        logger.warning("gmail_list_failed", label=label, error=str(exc))
        return []

    message_stubs = response.get("messages", [])
    items: list[RawItem] = []

    for stub in message_stubs:
        msg_id = str(stub.get("id", ""))
        msg_items = _process_message(service, msg_id, config)
        items.extend(msg_items)

    return items


def _process_message(
    service: object,
    msg_id: str,
    config: GmailConfig,
) -> list[RawItem]:
    """Fetch a single message and extract RawItems from its links."""
    try:
        message = (
            service.users()  # type: ignore[attr-defined]
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )
    except HttpError as exc:
        logger.warning("gmail_message_fetch_failed", msg_id=msg_id, error=str(exc))
        return []

    payload = message.get("payload", {})
    headers = {
        h["name"]: h["value"]
        for h in payload.get("headers", [])
        if isinstance(h, dict) and "name" in h and "value" in h
    }

    sender_from = str(headers.get("From", ""))
    subject = str(headers.get("Subject", ""))
    date_str = str(headers.get("Date", ""))

    # Apply sender filter
    if config.senders and not _sender_matches(sender_from, config.senders):
        return []

    source_name = _resolve_source_name(sender_from, config.senders)
    published_at = _parse_date(date_str)

    try:
        body_html = _decode_body(payload)
    except (binascii.Error, ValueError) as exc:
        logger.warning("gmail_body_decode_failed", msg_id=msg_id, error=str(exc))
        return []

    links = _extract_links(body_html)
    if not links:
        return []

    items: list[RawItem] = []
    for url, link_text in links:
        stripped = link_text.strip()
        title = stripped if stripped and stripped.lower() not in _GENERIC_LINK_TEXTS else subject
        items.append(
            RawItem(
                url=url,
                title=title,
                source=source_name,
                published_at=published_at,
                raw_content="",
                content_type="email",
            )
        )
    return items


def _sender_matches(from_header: str, senders: list[GmailSenderConfig]) -> bool:
    """Check if the From header matches any configured sender by email address."""
    from_lower = from_header.lower()
    return any(s.email.lower() in from_lower for s in senders)


def _resolve_source_name(from_header: str, senders: list[GmailSenderConfig]) -> str:
    """Return the configured sender name, or 'gmail' if no match."""
    from_lower = from_header.lower()
    for sender in senders:
        if sender.email.lower() in from_lower:
            return sender.name
    return "gmail"


def _decode_body(payload: dict[str, object]) -> str:
    """Decode the base64url-encoded email body from a Gmail message payload."""
    body = payload.get("body", {})
    data = ""
    if isinstance(body, dict):
        data = str(body.get("data", ""))

    if not data:
        # Check multipart parts
        parts = payload.get("parts", [])
        for part in parts if isinstance(parts, list) else []:
            if isinstance(part, dict):
                part_body = part.get("body", {})
                if isinstance(part_body, dict) and part_body.get("data"):
                    data = str(part_body["data"])
                    break

    if not data:
        return ""

    decoded = base64.urlsafe_b64decode(data + "==")
    return decoded.decode("utf-8", errors="replace")


def _extract_links(html: str) -> list[tuple[str, str]]:
    """Extract (url, link_text) pairs from HTML."""
    parser = _LinkExtractor()
    parser.feed(html)
    return parser.links


def _parse_date(date_str: str) -> datetime:
    """Parse an RFC 2822 email Date header to a timezone-aware datetime."""
    if not date_str:
        return datetime.now(tz=UTC)
    try:
        return parsedate_to_datetime(date_str)
    except Exception:  # noqa: BLE001 — email.utils raises various exceptions on malformed dates
        return datetime.now(tz=UTC)


class _LinkExtractor(HTMLParser):
    """HTML parser that collects (href, link_text) pairs from <a> tags."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href and _is_http_url(str(href)):
                self._current_href = str(href)
                self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href is not None:
            self.links.append((self._current_href, "".join(self._current_text)))
            self._current_href = None
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)


def _is_http_url(url: str) -> bool:
    """Return True if the URL is an http or https URL."""
    return bool(re.match(r"^https?://", url))
