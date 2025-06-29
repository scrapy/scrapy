from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy.http import Request, Response


class ThrottlingManagerProtocol(Protocol):
    """A protocol for :setting:`THROTTLING_MANAGER` :ref:`components
    <topics-components>`."""

    def get_scopes(
        self, request: Request
    ) -> None | str | Iterable[str] | dict[str, float]:
        """Return the :ref:`throttling scopes <throttling-scopes>` that apply
        to *request*.

        Return ``None`` if no scopes apply, a string for a single scope, an
        iterable of strings for multiple scopes, or a dict with scope names as
        keys and :ref:`throttling quotas <throttling-quotas>` as values.
        """

    def get_response_throttling(
        self, response: Response
    ) -> None | str | Iterable[str] | dict[str, dict[str, Any]]:
        """Return a throttling data update based on *response*.

        Return ``None`` if there is nothing new to report, i.e. the response is
        not a :ref:`backoff <backoff>` response.

        If the response indicates that one or more scopes are currently
        exhausted, return a string for a single scope or an iterable of strings
        for multiple scopes.

        If the response indicates any other information about one or more
        scopes, return a dict with scopes as keys and dict values. Dict values
        support the following keys:

        -   ``"delay"``: a float indicating how many seconds to wait before
            sending another request for the scope.

        -   ``"quota"``: a float indicating the remaining :ref:`throttling
            quota <throttling-quotas>`.

        If ``"quota"`` is not specified, the resource is considered exhausted.

        .. code-block:: python

            return {
                "scope1": {"delay": 5.0},
                "scope2": {},
                "scope3": {"quota": 42.0},
            }
        """

    def get_exception_throttling(
        self, request: Request, exception: Exception
    ) -> None | str | Iterable[str] | dict[str, dict[str, Any]]:
        """Return a throttling data update based on *exception* and the
        *request* that caused it.

        It supports the same return values as :meth:`get_response_throttling`.
        """


class ThrottlingManager:
    """The default :setting:`THROTTLING_MANAGER` class.

    It assigns to each request its domain or subdomain as scope and handles
    backoff according to :ref:`backoff settings <basic-throttling>`.
    """

    def get_scopes(
        self, request: Request
    ) -> None | str | Iterable[str] | dict[str, float]:
        return urlparse_cached(request).netloc
