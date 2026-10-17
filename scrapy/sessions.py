from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from scrapy.http.cookies import CookieJar

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)

_MAIN_ID = "main"


@dataclass
class Session:
    """State that requests bound to the same session share.

    .. versionadded:: VERSION
    """

    id: str
    """Session ID, i.e. the value of the :reqmeta:`session` request meta key of
    the requests bound to this session."""

    cookies: CookieJar = field(default_factory=CookieJar)
    """Cookies of the session."""

    meta: dict[Any, Any] = field(default_factory=dict)
    """Free-form data about the session."""


class Sessions:
    """Registry of the :class:`Session` objects of a crawler, available as
    :attr:`Crawler.sessions <scrapy.crawler.Crawler.sessions>`.

    .. versionadded:: VERSION

    Indexing by session ID returns the matching session, creating it if it does
    not exist, e.g. ``crawler.sessions["main"]``. IDs are strings; a value of a
    different type is used as its :func:`str` form.

    It holds at most :setting:`SESSIONS_MAX` sessions; when full, the session
    that has not been used for the longest time is dropped.
    """

    def __init__(self, crawler: Crawler):
        self._crawler = crawler
        self._max = crawler.settings.getint("SESSIONS_MAX")
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._logged_drop = False

    def __getitem__(self, session_id: Any) -> Session:
        session_id = str(session_id)
        if (session := self._sessions.get(session_id)) is not None:
            self._sessions.move_to_end(session_id)
            return session
        while self._sessions and len(self._sessions) >= self._max:
            self._drop()
        session = self._sessions[session_id] = Session(session_id)
        self._crawler.stats.inc_value("sessions/created")
        return session

    def __contains__(self, session_id: Any) -> bool:
        return str(session_id) in self._sessions

    def _drop(self) -> None:
        session_id, _ = self._sessions.popitem(last=False)
        self._crawler.stats.inc_value("sessions/dropped")
        if not self._logged_drop:
            self._logged_drop = True
            logger.warning(
                f"Dropped session {session_id!r}, and its state, to stay within "
                f"SESSIONS_MAX ({self._max}). Raise SESSIONS_MAX if your "
                f"sessions are being dropped while still in use - no more "
                f"dropped sessions will be logged.",
                extra={"spider": self._crawler.spider},
            )

    def create(self) -> Session:
        """Create a session with a unique ID and return it.

        Use it when you need a session that is certainly new and have no ID of
        your own to give it.
        """
        return self[uuid4().hex]

    def retire(self, session_id: Any) -> None:
        """Delete the session with the given ID, if it exists.

        Requests bound to it get a new, empty session.
        """
        if self._sessions.pop(str(session_id), None) is not None:
            self._crawler.stats.inc_value("sessions/retired")
