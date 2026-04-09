"""Tests for radar/sources/gmail.py.

Verifies the Gmail source connector:
- Happy path: mocked API response returns list[RawItem] with content_type="email"
- Field mapping: url (extracted link), title (link text or subject fallback),
  source (sender name from config or "gmail"), published_at (tz-aware from Date header)
- One RawItem per extracted URL; multiple emails produce flat list
- Guard clauses: disabled connector → [] without any API call
- Sender filter: non-configured senders skipped when config.senders is non-empty
- Empty senders list → no filtering; all emails processed
- max_age_days applied in API query (newer_than:Nd operator)
- Failure modes: missing GMAIL_REFRESH_TOKEN, expired token, API error,
  message fetch failure, bad base64 body → log + return [] or skip
- Contract: isinstance(Source), return type list[RawItem], published_at tz-aware

Design decisions encoded in these tests:
- Title fallback: link text → email subject (issue #64)
- max_age_days via API query operator (issue #65)
"""

# 1. Standard library imports
import base64
import os
import socket
from unittest.mock import MagicMock, patch

# 2. Third-party imports
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

# 3. Internal imports
from radar.config import GmailConfig, GmailSenderConfig
from radar.models import RawItem
from radar.sources.base import Source
from radar.sources.gmail import GmailSource

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BUILD_PATCH = "radar.sources.gmail.build"
_CREDENTIALS_PATCH = "radar.sources.gmail._get_credentials"
_REFRESH_TOKEN_ENV = "GMAIL_REFRESH_TOKEN"  # noqa: S105

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_config(
    *,
    enabled: bool = True,
    labels: list[str] | None = None,
    max_age_days: int = 1,
    senders: list[GmailSenderConfig] | None = None,
) -> GmailConfig:
    return GmailConfig(
        enabled=enabled,
        labels=labels if labels is not None else ["INBOX"],
        max_age_days=max_age_days,
        newsletter_type="link_list",
        senders=senders if senders is not None else [],
    )


def _make_sender(name: str = "TLDR AI", email: str = "dan@tldr.tech") -> GmailSenderConfig:
    return GmailSenderConfig(name=name, email=email)


def _encode_body(text: str) -> str:
    """Base64url-encode email body text as Gmail API returns it."""
    return base64.urlsafe_b64encode(text.encode()).decode()


def _make_message(
    msg_id: str = "msg_abc",
    subject: str = "TLDR AI Newsletter",
    sender: str = "dan@tldr.tech",
    date: str = "Mon, 07 Apr 2026 09:00:00 +0000",
    body_html: str = '<a href="https://example.com/article">Great Article</a>',
) -> dict[str, object]:
    return {
        "id": msg_id,
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "Date", "value": date},
            ],
            "body": {"data": _encode_body(body_html)},
        },
    }


def _make_mock_service(
    message_ids: list[str] | None = None,
    messages: list[dict[str, object]] | None = None,
) -> MagicMock:
    """Build a mock Gmail service with realistic call chains."""
    if message_ids is None:
        message_ids = ["msg_abc"]
    if messages is None:
        messages = [_make_message()]

    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": mid} for mid in message_ids]
    }
    # Configure each .get() call to return messages in order
    mock_service.users().messages().get().execute.side_effect = messages
    return mock_service


def _patched_fetch(
    config: GmailConfig,
    mock_service: MagicMock,
    token: str = "fake-refresh-token",  # noqa: S107
) -> list[RawItem]:
    """Run fetch() with all external calls mocked."""
    with (
        patch.dict(os.environ, {_REFRESH_TOKEN_ENV: token}),
        patch(_BUILD_PATCH, return_value=mock_service),
        patch(_CREDENTIALS_PATCH, return_value=MagicMock()),
    ):
        return GmailSource(config).fetch()


# ---------------------------------------------------------------------------
# Happy path: field mapping
# ---------------------------------------------------------------------------


def test_fetch_returns_list_of_raw_items() -> None:
    config = _make_config()
    mock_service = _make_mock_service()
    result = _patched_fetch(config, mock_service)
    assert isinstance(result, list)
    assert len(result) >= 1
    assert isinstance(result[0], RawItem)


def test_content_type_is_email() -> None:
    config = _make_config()
    mock_service = _make_mock_service()
    result = _patched_fetch(config, mock_service)
    assert all(item.content_type == "email" for item in result)


def test_url_is_extracted_link() -> None:
    body = '<a href="https://example.com/article-1">Read this</a>'
    msg = _make_message(body_html=body)
    config = _make_config()
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert result[0].url == "https://example.com/article-1"


def test_title_is_link_text() -> None:
    body = '<a href="https://example.com/article">My Link Text</a>'
    msg = _make_message(body_html=body)
    config = _make_config()
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert result[0].title == "My Link Text"


def test_title_falls_back_to_subject_when_link_text_absent() -> None:
    body = '<a href="https://example.com/article"></a>'
    msg = _make_message(subject="TLDR AI — April 7", body_html=body)
    config = _make_config()
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert result[0].title == "TLDR AI — April 7"


def test_source_is_sender_name_from_config() -> None:
    sender = _make_sender(name="TLDR AI", email="dan@tldr.tech")
    config = _make_config(senders=[sender])
    msg = _make_message(sender="dan@tldr.tech")
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert result[0].source == "TLDR AI"


def test_source_falls_back_to_gmail_when_no_sender_config() -> None:
    config = _make_config(senders=[])
    mock_service = _make_mock_service()
    result = _patched_fetch(config, mock_service)
    assert result[0].source == "gmail"


def test_published_at_is_timezone_aware() -> None:
    config = _make_config()
    mock_service = _make_mock_service()
    result = _patched_fetch(config, mock_service)
    assert result[0].published_at.tzinfo is not None


def test_published_at_parsed_from_date_header() -> None:
    msg = _make_message(date="Mon, 07 Apr 2026 09:00:00 +0000")
    config = _make_config()
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    expected_year = 2026
    expected_month = 4
    expected_day = 7
    assert result[0].published_at.year == expected_year
    assert result[0].published_at.month == expected_month
    assert result[0].published_at.day == expected_day


# ---------------------------------------------------------------------------
# Happy path: one RawItem per URL, multiple emails
# ---------------------------------------------------------------------------


def test_one_raw_item_per_extracted_url() -> None:
    body = (
        '<a href="https://example.com/a1">Article 1</a>'
        '<a href="https://example.com/a2">Article 2</a>'
        '<a href="https://example.com/a3">Article 3</a>'
    )
    msg = _make_message(body_html=body)
    config = _make_config()
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert len(result) == 3  # noqa: PLR2004


def test_multiple_emails_produce_flat_list() -> None:
    msg1 = _make_message(
        msg_id="msg_1",
        body_html='<a href="https://example.com/a1">A1</a>',
    )
    msg2 = _make_message(
        msg_id="msg_2",
        body_html='<a href="https://example.com/a2">A2</a><a href="https://example.com/a3">A3</a>',
    )
    config = _make_config()
    mock_service = _make_mock_service(message_ids=["msg_1", "msg_2"], messages=[msg1, msg2])
    result = _patched_fetch(config, mock_service)
    assert len(result) == 3  # noqa: PLR2004


def test_email_with_no_urls_skipped() -> None:
    msg = _make_message(body_html="<p>No links here, just text.</p>")
    config = _make_config()
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert result == []


def test_no_messages_returns_empty_list() -> None:
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}
    config = _make_config()
    result = _patched_fetch(config, mock_service)
    assert result == []


# ---------------------------------------------------------------------------
# Happy path: guard clauses
# ---------------------------------------------------------------------------


def test_disabled_connector_returns_empty_list() -> None:
    config = _make_config(enabled=False)
    with patch(_BUILD_PATCH) as mock_build, patch(_CREDENTIALS_PATCH):
        result = GmailSource(config).fetch()
    assert result == []
    mock_build.assert_not_called()


def test_disabled_connector_does_not_call_api() -> None:
    config = _make_config(enabled=False)
    with patch(_BUILD_PATCH) as mock_build, patch(_CREDENTIALS_PATCH):
        GmailSource(config).fetch()
    mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# Sender filtering
# ---------------------------------------------------------------------------


def test_sender_filter_skips_unconfigured_sender() -> None:
    sender = _make_sender(name="TLDR AI", email="dan@tldr.tech")
    config = _make_config(senders=[sender])
    msg = _make_message(sender="unknown@other.com")
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert result == []


def test_sender_filter_passes_configured_sender() -> None:
    sender = _make_sender(name="TLDR AI", email="dan@tldr.tech")
    config = _make_config(senders=[sender])
    msg = _make_message(sender="dan@tldr.tech")
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert len(result) >= 1


def test_empty_senders_processes_all_emails() -> None:
    config = _make_config(senders=[])
    msg = _make_message(sender="anyone@anywhere.com")
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert len(result) >= 1


def test_sender_matched_by_email_address_not_display_name() -> None:
    sender = _make_sender(name="TLDR AI", email="dan@tldr.tech")
    config = _make_config(senders=[sender])
    # Gmail often includes display name: "TLDR AI <dan@tldr.tech>"
    msg = _make_message(sender="TLDR AI <dan@tldr.tech>")
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# max_age_days applied in API query
# ---------------------------------------------------------------------------


def test_max_age_days_included_in_api_query() -> None:
    config = _make_config(max_age_days=3)
    captured_kwargs: list[dict[str, object]] = []
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}

    def capture_list(**kwargs: object) -> MagicMock:
        captured_kwargs.append(dict(kwargs))
        return mock_service.users().messages().list()

    mock_service.users().messages().list = capture_list

    with (
        patch.dict(os.environ, {_REFRESH_TOKEN_ENV: "token"}),
        patch(_BUILD_PATCH, return_value=mock_service),
        patch(_CREDENTIALS_PATCH, return_value=MagicMock()),
    ):
        GmailSource(config).fetch()

    assert any("newer_than:3d" in str(kw.get("q", "")) for kw in captured_kwargs)


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_missing_refresh_token_returns_empty_list() -> None:
    config = _make_config()
    env = {k: v for k, v in os.environ.items() if k != _REFRESH_TOKEN_ENV}
    with patch.dict(os.environ, env, clear=True):
        result = GmailSource(config).fetch()
    assert result == []


def test_missing_refresh_token_does_not_raise() -> None:
    config = _make_config()
    env = {k: v for k, v in os.environ.items() if k != _REFRESH_TOKEN_ENV}
    with patch.dict(os.environ, env, clear=True):
        GmailSource(config).fetch()  # must not raise


def test_expired_token_returns_empty_list() -> None:
    config = _make_config()
    with (
        patch.dict(os.environ, {_REFRESH_TOKEN_ENV: "expired-token"}),
        patch(_CREDENTIALS_PATCH, side_effect=RefreshError("token expired")),
    ):
        result = GmailSource(config).fetch()
    assert result == []


def test_expired_token_does_not_raise() -> None:
    config = _make_config()
    with (
        patch.dict(os.environ, {_REFRESH_TOKEN_ENV: "expired-token"}),
        patch(_CREDENTIALS_PATCH, side_effect=RefreshError("token expired")),
    ):
        GmailSource(config).fetch()  # must not raise


def test_gmail_api_error_returns_empty_list() -> None:
    config = _make_config()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.side_effect = HttpError(
        resp=MagicMock(status=500), content=b"Server Error"
    )
    result = _patched_fetch(config, mock_service)
    assert result == []


def test_gmail_api_error_does_not_raise() -> None:
    config = _make_config()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.side_effect = HttpError(
        resp=MagicMock(status=403), content=b"Forbidden"
    )
    _patched_fetch(config, mock_service)  # must not raise


def test_individual_message_fetch_failure_skips_message() -> None:
    msg_good = _make_message(msg_id="msg_good")
    config = _make_config()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg_bad"}, {"id": "msg_good"}]
    }
    mock_service.users().messages().get().execute.side_effect = [
        HttpError(resp=MagicMock(status=404), content=b"Not Found"),
        msg_good,
    ]
    result = _patched_fetch(config, mock_service)
    # msg_bad is skipped; msg_good still processed
    assert len(result) >= 1


def test_individual_message_fetch_failure_does_not_abort_pipeline() -> None:
    config = _make_config()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg_1"}, {"id": "msg_2"}]
    }
    mock_service.users().messages().get().execute.side_effect = [
        HttpError(resp=MagicMock(status=500), content=b"Error"),
        _make_message(msg_id="msg_2"),
    ]
    # Should not raise
    _patched_fetch(config, mock_service)


def test_bad_base64_body_skips_message() -> None:
    msg: dict[str, object] = {
        "id": "msg_bad_b64",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Newsletter"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "Date", "value": "Mon, 07 Apr 2026 09:00:00 +0000"},
            ],
            "body": {"data": "!!!not-valid-base64!!!"},
        },
    }
    config = _make_config()
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert result == []


def test_bad_base64_body_does_not_raise() -> None:
    msg: dict[str, object] = {
        "id": "msg_bad_b64",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Newsletter"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "Date", "value": "Mon, 07 Apr 2026 09:00:00 +0000"},
            ],
            "body": {"data": "!!!not-valid-base64!!!"},
        },
    }
    config = _make_config()
    mock_service = _make_mock_service(messages=[msg])
    _patched_fetch(config, mock_service)  # must not raise


# ---------------------------------------------------------------------------
# Contract / return type
# ---------------------------------------------------------------------------


def test_gmail_source_is_instance_of_source() -> None:
    config = _make_config()
    assert isinstance(GmailSource(config), Source)


def test_fetch_return_type_is_list() -> None:
    config = _make_config(enabled=False)
    result = GmailSource(config).fetch()
    assert isinstance(result, list)


def test_all_returned_items_are_raw_items() -> None:
    body = '<a href="https://example.com/a1">A1</a><a href="https://example.com/a2">A2</a>'
    msg = _make_message(body_html=body)
    config = _make_config()
    mock_service = _make_mock_service(messages=[msg])
    result = _patched_fetch(config, mock_service)
    assert all(isinstance(item, RawItem) for item in result)


def test_no_real_network_calls_made() -> None:
    """Verify fetch() only calls the mocked service, never real network."""

    def fail_if_connected(_self: object, *args: object, **_kwargs: object) -> None:
        msg = f"Real network call attempted: {args}"
        raise AssertionError(msg)

    config = _make_config()
    mock_service = _make_mock_service()
    with (
        patch.dict(os.environ, {_REFRESH_TOKEN_ENV: "fake"}),
        patch(_BUILD_PATCH, return_value=mock_service),
        patch(_CREDENTIALS_PATCH, return_value=MagicMock()),
        patch.object(socket.socket, "connect", fail_if_connected),
    ):
        GmailSource(config).fetch()  # must not trigger real socket.connect
