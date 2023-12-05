"""Helpers."""
from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import sys
from collections.abc import Callable, Hashable, Iterable
from pathlib import Path
from typing import (
    TypeVar,
    cast,
)

import requests
from filelock import FileLock

LOG = logging.getLogger(__name__)

_DID_LOG_UNABLE_TO_CACHE = False

T = TypeVar("T")

if sys.version_info >= (3, 9):

    def md5(*args: bytes) -> hashlib._Hash:
        """Use argument only available in newer Python.

        In this file, MD5 is only used for cache location, not security.
        """
        return hashlib.md5(*args, usedforsecurity=False)

else:
    md5 = hashlib.md5


def get_pkg_unique_identifier() -> str:
    """
    Generate an identifier unique to the python version, tldextract version, and python instance.

    This will prevent interference between virtualenvs and issues that might arise when installing
    a new version of tldextract
    """
    try:
        from tldextract._version import version
    except ImportError:
        version = "dev"

    tldextract_version = "tldextract-" + version
    python_env_name = os.path.basename(sys.prefix)
    # just to handle the edge case of two identically named python environments
    python_binary_path_short_hash = md5(sys.prefix.encode("utf-8")).hexdigest()[:6]
    python_version = ".".join([str(v) for v in sys.version_info[:-1]])
    identifier_parts = [
        python_version,
        python_env_name,
        python_binary_path_short_hash,
        tldextract_version,
    ]
    pkg_identifier = "__".join(identifier_parts)

    return pkg_identifier


def get_cache_dir() -> str:
    """
    Get a cache dir that we have permission to write to.

    Try to follow the XDG standard, but if that doesn't work fallback to the package directory
    http://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
    """
    cache_dir = os.environ.get("TLDEXTRACT_CACHE", None)
    if cache_dir is not None:
        return cache_dir

    xdg_cache_home = os.getenv("XDG_CACHE_HOME", None)
    if xdg_cache_home is None:
        user_home = os.getenv("HOME", None)
        if user_home:
            xdg_cache_home = str(Path(user_home, ".cache"))

    if xdg_cache_home is not None:
        return str(
            Path(xdg_cache_home, "python-tldextract", get_pkg_unique_identifier())
        )

    # fallback to trying to use package directory itself
    return str(Path(os.path.dirname(__file__), ".suffix_cache"))


class DiskCache:
    """Disk _cache that only works for jsonable values."""

    def __init__(self, cache_dir: str | None, lock_timeout: int = 20):
        """Construct a disk cache in the given directory."""
        self.enabled = bool(cache_dir)
        self.cache_dir = os.path.expanduser(str(cache_dir) or "")
        self.lock_timeout = lock_timeout
        # using a unique extension provides some safety that an incorrectly set cache_dir
        # combined with a call to `.clear()` wont wipe someones hard drive
        self.file_ext = ".tldextract.json"

    def get(self, namespace: str, key: str | dict[str, Hashable]) -> object:
        """Retrieve a value from the disk cache."""
        if not self.enabled:
            raise KeyError("Cache is disabled")
        cache_filepath = self._key_to_cachefile_path(namespace, key)

        if not os.path.isfile(cache_filepath):
            raise KeyError("namespace: " + namespace + " key: " + repr(key))
        try:
            with open(cache_filepath) as cache_file:
                return json.load(cache_file)
        except (OSError, ValueError) as exc:
            LOG.error("error reading TLD cache file %s: %s", cache_filepath, exc)
            raise KeyError("namespace: " + namespace + " key: " + repr(key)) from None

    def set(  # noqa: A003
        self, namespace: str, key: str | dict[str, Hashable], value: object
    ) -> None:
        """Set a value in the disk cache."""
        if not self.enabled:
            return

        cache_filepath = self._key_to_cachefile_path(namespace, key)

        try:
            _make_dir(cache_filepath)
            with open(cache_filepath, "w") as cache_file:
                json.dump(value, cache_file)
        except OSError as ioe:
            global _DID_LOG_UNABLE_TO_CACHE
            if not _DID_LOG_UNABLE_TO_CACHE:
                LOG.warning(
                    "unable to cache %s.%s in %s. This could refresh the "
                    "Public Suffix List over HTTP every app startup. "
                    "Construct your `TLDExtract` with a writable `cache_dir` or "
                    "set `cache_dir=None` to silence this warning. %s",
                    namespace,
                    key,
                    cache_filepath,
                    ioe,
                )
                _DID_LOG_UNABLE_TO_CACHE = True

    def clear(self) -> None:
        """Clear the disk cache."""
        for root, _, files in os.walk(self.cache_dir):
            for filename in files:
                if filename.endswith(self.file_ext) or filename.endswith(
                    self.file_ext + ".lock"
                ):
                    try:
                        os.unlink(str(Path(root, filename)))
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        # errno.ENOENT == "No such file or directory"
                        # https://docs.python.org/2/library/errno.html#errno.ENOENT
                        if exc.errno != errno.ENOENT:
                            raise

    def _key_to_cachefile_path(
        self, namespace: str, key: str | dict[str, Hashable]
    ) -> str:
        namespace_path = str(Path(self.cache_dir, namespace))
        hashed_key = _make_cache_key(key)

        cache_path = str(Path(namespace_path, hashed_key + self.file_ext))

        return cache_path

    def run_and_cache(
        self,
        func: Callable[..., T],
        namespace: str,
        kwargs: dict[str, Hashable],
        hashed_argnames: Iterable[str],
    ) -> T:
        """Get a url but cache the response."""
        if not self.enabled:
            return func(**kwargs)

        key_args = {k: v for k, v in kwargs.items() if k in hashed_argnames}
        cache_filepath = self._key_to_cachefile_path(namespace, key_args)
        lock_path = cache_filepath + ".lock"
        try:
            _make_dir(cache_filepath)
        except OSError as ioe:
            global _DID_LOG_UNABLE_TO_CACHE
            if not _DID_LOG_UNABLE_TO_CACHE:
                LOG.warning(
                    "unable to cache %s.%s in %s. This could refresh the "
                    "Public Suffix List over HTTP every app startup. "
                    "Construct your `TLDExtract` with a writable `cache_dir` or "
                    "set `cache_dir=None` to silence this warning. %s",
                    namespace,
                    key_args,
                    cache_filepath,
                    ioe,
                )
                _DID_LOG_UNABLE_TO_CACHE = True

            return func(**kwargs)

        with FileLock(lock_path, timeout=self.lock_timeout):
            try:
                result = cast(T, self.get(namespace=namespace, key=key_args))
            except KeyError:
                result = func(**kwargs)
                self.set(namespace=namespace, key=key_args, value=result)

            return result

    def cached_fetch_url(
        self, session: requests.Session, url: str, timeout: float | int | None
    ) -> str:
        """Get a url but cache the response."""
        return self.run_and_cache(
            func=_fetch_url,
            namespace="urls",
            kwargs={"session": session, "url": url, "timeout": timeout},
            hashed_argnames=["url"],
        )


def _fetch_url(session: requests.Session, url: str, timeout: int | None) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    text = response.text

    if not isinstance(text, str):
        text = str(text, "utf-8")

    return text


def _make_cache_key(inputs: str | dict[str, Hashable]) -> str:
    key = repr(inputs)
    return md5(key.encode("utf8")).hexdigest()


def _make_dir(filename: str) -> None:
    """Make a directory if it doesn't already exist."""
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
