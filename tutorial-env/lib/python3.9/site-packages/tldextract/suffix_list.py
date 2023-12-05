"""tldextract helpers for testing and fetching remote resources."""

from __future__ import annotations

import logging
import pkgutil
import re
from collections.abc import Sequence
from typing import cast

import requests
from requests_file import FileAdapter  # type: ignore[import-untyped]

from .cache import DiskCache

LOG = logging.getLogger("tldextract")

PUBLIC_SUFFIX_RE = re.compile(r"^(?P<suffix>[.*!]*\w[\S]*)", re.UNICODE | re.MULTILINE)
PUBLIC_PRIVATE_SUFFIX_SEPARATOR = "// ===BEGIN PRIVATE DOMAINS==="


class SuffixListNotFound(LookupError):  # noqa: N818
    """A recoverable error while looking up a suffix list.

    Recoverable because you can specify backups, or use this library's bundled
    snapshot.
    """


def find_first_response(
    cache: DiskCache,
    urls: Sequence[str],
    cache_fetch_timeout: float | int | None = None,
    session: requests.Session | None = None,
) -> str:
    """Decode the first successfully fetched URL, from UTF-8 encoding to Python unicode."""
    session_created = False
    if session is None:
        session = requests.Session()
        session.mount("file://", FileAdapter())
        session_created = True

    try:
        for url in urls:
            try:
                return cache.cached_fetch_url(
                    session=session, url=url, timeout=cache_fetch_timeout
                )
            except requests.exceptions.RequestException:
                LOG.exception("Exception reading Public Suffix List url %s", url)
    finally:
        # Ensure the session is always closed if it's constructed in the method
        if session_created:
            session.close()

    raise SuffixListNotFound(
        "No remote Public Suffix List found. Consider using a mirror, or avoid this"
        " fetch by constructing your TLDExtract with `suffix_list_urls=()`."
    )


def extract_tlds_from_suffix_list(suffix_list_text: str) -> tuple[list[str], list[str]]:
    """Parse the raw suffix list text for its different designations of suffixes."""
    public_text, _, private_text = suffix_list_text.partition(
        PUBLIC_PRIVATE_SUFFIX_SEPARATOR
    )

    public_tlds = [m.group("suffix") for m in PUBLIC_SUFFIX_RE.finditer(public_text)]
    private_tlds = [m.group("suffix") for m in PUBLIC_SUFFIX_RE.finditer(private_text)]
    return public_tlds, private_tlds


def get_suffix_lists(
    cache: DiskCache,
    urls: Sequence[str],
    cache_fetch_timeout: float | int | None,
    fallback_to_snapshot: bool,
    session: requests.Session | None = None,
) -> tuple[list[str], list[str]]:
    """Fetch, parse, and cache the suffix lists."""
    return cache.run_and_cache(
        func=_get_suffix_lists,
        namespace="publicsuffix.org-tlds",
        kwargs={
            "cache": cache,
            "urls": urls,
            "cache_fetch_timeout": cache_fetch_timeout,
            "fallback_to_snapshot": fallback_to_snapshot,
            "session": session,
        },
        hashed_argnames=["urls", "fallback_to_snapshot"],
    )


def _get_suffix_lists(
    cache: DiskCache,
    urls: Sequence[str],
    cache_fetch_timeout: float | int | None,
    fallback_to_snapshot: bool,
    session: requests.Session | None = None,
) -> tuple[list[str], list[str]]:
    """Fetch, parse, and cache the suffix lists."""
    try:
        text = find_first_response(
            cache, urls, cache_fetch_timeout=cache_fetch_timeout, session=session
        )
    except SuffixListNotFound as exc:
        if fallback_to_snapshot:
            maybe_pkg_data = pkgutil.get_data("tldextract", ".tld_set_snapshot")
            # package maintainers guarantee file is included
            pkg_data = cast(bytes, maybe_pkg_data)
            text = pkg_data.decode("utf-8")
        else:
            raise exc

    public_tlds, private_tlds = extract_tlds_from_suffix_list(text)

    return public_tlds, private_tlds
