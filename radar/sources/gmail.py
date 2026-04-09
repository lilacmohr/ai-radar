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
- Title fallback: email subject used when link text is absent (see issue #64)
- max_age_days filtering: applied via Gmail API query operator (see issue #65)

Spec reference: SPEC.md §3.1 (Gmail connector, OAuth), §3.7 (failure handling).
"""

from radar.config import GmailConfig
from radar.models import RawItem
from radar.sources.base import Source


class GmailSource(Source):
    """Gmail source connector."""

    def __init__(self, config: GmailConfig) -> None:
        self._config = config

    def fetch(self) -> list[RawItem]:
        """Fetch recent newsletter emails and extract article URLs as RawItems."""
        raise NotImplementedError
