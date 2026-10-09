"""Shared resolution of the statuses that a spider handles itself.

Used by :class:`~scrapy.spidermiddlewares.httperror.HttpErrorMiddleware` and
:class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware`.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, cast
from weakref import WeakKeyDictionary

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.deprecate import warn_on_deprecated_spider_attribute

if TYPE_CHECKING:
    from collections.abc import Container, Mapping

    from scrapy import Spider
    from scrapy.settings import BaseSettings

    # True means every status, False means no status, and a container is
    # checked for membership.
    HandledCodes = bool | Container[int]


SETTING = "HANDLE_HTTP_CODES"
META_KEY = "handle_http_codes"

_LEGACY_SETTING_ALL = "HTTPERROR_ALLOW_ALL"
_LEGACY_SETTING_LIST = "HTTPERROR_ALLOWED_CODES"
# Both a spider attribute and a request meta key.
_LEGACY_LIST = "handle_httpstatus_list"
_LEGACY_ALL = "handle_httpstatus_all"

# Same string values that BaseSettings.getbool() accepts.
_TRUE_STRINGS = frozenset({"1", "True", "true"})
_FALSE_STRINGS = frozenset({"0", "False", "false"})

_warned_meta_keys: WeakKeyDictionary[Any, set[str]] = WeakKeyDictionary()


def normalize(value: Any) -> HandledCodes:
    """Return *value* as either a boolean or a container of status codes.

    Booleans are returned as they are, integers become single-code containers,
    strings are parsed as they come from the command line or the environment,
    and sequences have their items coerced to integers. Any other container is
    returned untouched, so that objects such as
    :class:`~scrapy.utils.datatypes.SequenceExclude` keep working.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return frozenset({value})
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return False
        if value in _TRUE_STRINGS:
            return True
        if value in _FALSE_STRINGS:
            return False
        return frozenset(int(code) for code in value.split(","))
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(int(code) for code in value)
    if not hasattr(value, "__contains__"):
        raise ValueError(
            f"Unsupported {SETTING} value: {value!r}. Expected a boolean, an "
            f"integer, a string, or a container of integers."
        )
    return cast("Container[int]", value)


def matches(value: HandledCodes | None, status: int) -> bool:
    if value is True:
        return True
    if not value:  # False, None or an empty container
        return False
    return status in value


class StatusHandling:
    """Tell whether the spider handles a response status code itself.

    *legacy_settings* enables reading the deprecated
    :setting:`HTTPERROR_ALLOWED_CODES` and :setting:`HTTPERROR_ALLOW_ALL`
    settings, which only ever applied to
    :class:`~scrapy.spidermiddlewares.httperror.HttpErrorMiddleware`.

    *union_legacy_meta* combines a deprecated request meta key with the
    deprecated spider attribute, instead of overriding it, as
    :class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware` used to
    do.

    :meth:`spider_opened` must be called on the ``spider_opened`` signal, so
    that the deprecated ``handle_httpstatus_list`` spider attribute is taken
    into account.
    """

    def __init__(
        self,
        settings: BaseSettings,
        *,
        legacy_settings: bool = False,
        union_legacy_meta: bool = False,
    ):
        self._settings_value: HandledCodes = self._from_settings(
            settings, legacy_settings
        )
        self._union_legacy_meta = union_legacy_meta
        self._spider_value: HandledCodes | None = None
        self._warning_scope: Any = self

    def spider_opened(self, spider: Spider) -> None:
        # Deprecation warnings about request meta keys are emitted once per
        # crawl, no matter how many components ask about the same key.
        self._warning_scope = getattr(spider, "crawler", None) or self
        value = getattr(spider, _LEGACY_LIST, None)
        if value is None:
            return
        warn_on_deprecated_spider_attribute(_LEGACY_LIST, SETTING)
        self._spider_value = normalize(value)

    def handles(self, status: int, meta: Mapping[str, Any]) -> bool:
        value, from_legacy_meta = self._from_meta(meta)
        if value is None:
            value = self._spider_value
        if value is None:
            value = self._settings_value
        handled = matches(value, status)
        if handled or not (from_legacy_meta and self._union_legacy_meta):
            return handled
        return matches(self._spider_value, status)

    @staticmethod
    def _from_settings(settings: BaseSettings, legacy: bool) -> HandledCodes:
        value = settings.get(SETTING)
        if value is not None:
            return normalize(value)
        if not legacy:
            return False
        for name in (_LEGACY_SETTING_ALL, _LEGACY_SETTING_LIST):
            if (settings.getpriority(name) or 0) > 0:
                warnings.warn(
                    f"The {name} setting is deprecated, use {SETTING} instead.",
                    category=ScrapyDeprecationWarning,
                    stacklevel=2,
                )
        if settings.getbool(_LEGACY_SETTING_ALL):
            return True
        return normalize(settings.getlist(_LEGACY_SETTING_LIST))

    def _from_meta(self, meta: Mapping[str, Any]) -> tuple[HandledCodes | None, bool]:
        """Return the value that *meta* defines, if any, and whether it comes
        from a deprecated meta key."""
        value = meta.get(META_KEY)
        if value is not None:
            return normalize(value), False
        # The deprecated keys used to be checked in this order: a true
        # handle_httpstatus_all took precedence over handle_httpstatus_list,
        # and a false one was only taken into account on its own.
        legacy_all = meta.get(_LEGACY_ALL)
        if legacy_all:
            self._warn_meta_key(_LEGACY_ALL)
            return True, True
        if _LEGACY_LIST in meta:
            self._warn_meta_key(_LEGACY_LIST)
            return normalize(meta[_LEGACY_LIST]), True
        if legacy_all is not None:
            self._warn_meta_key(_LEGACY_ALL)
            return False, True
        return None, False

    def _warn_meta_key(self, key: str) -> None:
        warned = _warned_meta_keys.setdefault(self._warning_scope, set())
        if key in warned:
            return
        warned.add(key)
        warnings.warn(
            f"The {key!r} request meta key is deprecated, use {META_KEY!r} instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
