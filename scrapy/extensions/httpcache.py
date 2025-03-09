from __future__ import annotations

import enum
import gzip
import logging
import pickle
import re
import uuid
from email.utils import formatdate, mktime_tz, parsedate_tz
from importlib import import_module
from io import BytesIO
from pathlib import Path
from time import time
from typing import IO, TYPE_CHECKING, Any, LiteralString, cast
from weakref import WeakKeyDictionary

from w3lib.http import headers_dict_to_raw, headers_raw_to_dict
from warcio import ArchiveIterator, StatusAndHeaders, WARCWriter
from warcio.recordbuilder import RecordBuilder

from scrapy.http import Headers, Response
from scrapy.responsetypes import responsetypes
from scrapy.utils.httpobj import HTTP_STATUS_MSGS, urlparse_cached
from scrapy.utils.project import data_path
from scrapy.utils.python import to_bytes, to_unicode

if TYPE_CHECKING:
    import os
    from collections.abc import Callable
    from types import ModuleType

    # typing.Concatenate requires Python 3.10
    from typing_extensions import Concatenate

    from scrapy.http.request import Request
    from scrapy.settings import BaseSettings
    from scrapy.spiders import Spider
    from scrapy.utils.request import RequestFingerprinterProtocol


logger = logging.getLogger(__name__)


class HTTPCacheWARCPathStyle(enum.Enum):
    FILE_ONLY = "FILE_ONLY"
    FILE_AND_HASH = "FILE_AND_HASH"
    FOLDERS_AND_FILE = "FOLDERS_AND_FILE"
    FOLDERS_FILE_AND_HASH = "FOLDERS_FILE_AND_HASH"


URL_TO_FILE_SAFE_RX = re.compile(r"[^a-z0-9_\-.]+", re.ASCII | re.IGNORECASE)


class DummyPolicy:
    def __init__(self, settings: BaseSettings):
        self.ignore_schemes: list[str] = settings.getlist("HTTPCACHE_IGNORE_SCHEMES")
        self.ignore_http_codes: list[int] = [
            int(x) for x in settings.getlist("HTTPCACHE_IGNORE_HTTP_CODES")
        ]

    def should_cache_request(self, request: Request) -> bool:
        return urlparse_cached(request).scheme not in self.ignore_schemes

    def should_cache_response(self, response: Response, request: Request) -> bool:
        return response.status not in self.ignore_http_codes

    def is_cached_response_fresh(
        self, cachedresponse: Response, request: Request
    ) -> bool:
        return True

    def is_cached_response_valid(
        self, cachedresponse: Response, response: Response, request: Request
    ) -> bool:
        return True


class RFC2616Policy:
    MAXAGE = 3600 * 24 * 365  # one year

    def __init__(self, settings: BaseSettings):
        self.always_store: bool = settings.getbool("HTTPCACHE_ALWAYS_STORE")
        self.ignore_schemes: list[str] = settings.getlist("HTTPCACHE_IGNORE_SCHEMES")
        self._cc_parsed: WeakKeyDictionary[
            Request | Response, dict[bytes, bytes | None]
        ] = WeakKeyDictionary()
        self.ignore_response_cache_controls: list[bytes] = [
            to_bytes(cc)
            for cc in settings.getlist("HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS")
        ]

    def _parse_cachecontrol(self, r: Request | Response) -> dict[bytes, bytes | None]:
        if r not in self._cc_parsed:
            cch = r.headers.get(b"Cache-Control", b"")
            assert cch is not None
            parsed = parse_cachecontrol(cch)
            if isinstance(r, Response):
                for key in self.ignore_response_cache_controls:
                    parsed.pop(key, None)
            self._cc_parsed[r] = parsed
        return self._cc_parsed[r]

    def should_cache_request(self, request: Request) -> bool:
        if urlparse_cached(request).scheme in self.ignore_schemes:
            return False
        cc = self._parse_cachecontrol(request)
        # obey user-agent directive "Cache-Control: no-store"
        return b"no-store" not in cc

    def should_cache_response(self, response: Response, request: Request) -> bool:
        # What is cacheable - https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.1
        # Response cacheability - https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html#sec13.4
        # Status code 206 is not included because cache can not deal with partial contents
        cc = self._parse_cachecontrol(response)
        # obey directive "Cache-Control: no-store"
        if b"no-store" in cc:
            return False
        # Never cache 304 (Not Modified) responses
        if response.status == 304:
            return False
        # Cache unconditionally if configured to do so
        if self.always_store:
            return True
        # Any hint on response expiration is good
        if b"max-age" in cc or b"Expires" in response.headers:
            return True
        # Firefox fallbacks this statuses to one year expiration if none is set
        if response.status in (300, 301, 308):
            return True
        # Other statuses without expiration requires at least one validator
        if response.status in (200, 203, 401):
            return b"Last-Modified" in response.headers or b"ETag" in response.headers
        # Any other is probably not eligible for caching
        # Makes no sense to cache responses that does not contain expiration
        # info and can not be revalidated
        return False

    def is_cached_response_fresh(
        self, cachedresponse: Response, request: Request
    ) -> bool:
        cc = self._parse_cachecontrol(cachedresponse)
        ccreq = self._parse_cachecontrol(request)
        if b"no-cache" in cc or b"no-cache" in ccreq:
            return False

        now = time()
        freshnesslifetime = self._compute_freshness_lifetime(
            cachedresponse, request, now
        )
        currentage = self._compute_current_age(cachedresponse, request, now)

        reqmaxage = self._get_max_age(ccreq)
        if reqmaxage is not None:
            freshnesslifetime = min(freshnesslifetime, reqmaxage)

        if currentage < freshnesslifetime:
            return True

        if b"max-stale" in ccreq and b"must-revalidate" not in cc:
            # From RFC2616: "Indicates that the client is willing to
            # accept a response that has exceeded its expiration time.
            # If max-stale is assigned a value, then the client is
            # willing to accept a response that has exceeded its
            # expiration time by no more than the specified number of
            # seconds. If no value is assigned to max-stale, then the
            # client is willing to accept a stale response of any age."
            staleage = ccreq[b"max-stale"]
            if staleage is None:
                return True

            try:
                if currentage < freshnesslifetime + max(0, int(staleage)):
                    return True
            except ValueError:
                pass

        # Cached response is stale, try to set validators if any
        self._set_conditional_validators(request, cachedresponse)
        return False

    def is_cached_response_valid(
        self, cachedresponse: Response, response: Response, request: Request
    ) -> bool:
        # Use the cached response if the new response is a server error,
        # as long as the old response didn't specify must-revalidate.
        if response.status >= 500:
            cc = self._parse_cachecontrol(cachedresponse)
            if b"must-revalidate" not in cc:
                return True

        # Use the cached response if the server says it hasn't changed.
        return response.status == 304

    def _set_conditional_validators(
        self, request: Request, cachedresponse: Response
    ) -> None:
        if b"Last-Modified" in cachedresponse.headers:
            request.headers[b"If-Modified-Since"] = cachedresponse.headers[
                b"Last-Modified"
            ]

        if b"ETag" in cachedresponse.headers:
            request.headers[b"If-None-Match"] = cachedresponse.headers[b"ETag"]

    def _get_max_age(self, cc: dict[bytes, bytes | None]) -> int | None:
        try:
            return max(0, int(cc[b"max-age"]))  # type: ignore[arg-type]
        except (KeyError, ValueError):
            return None

    def _compute_freshness_lifetime(
        self, response: Response, request: Request, now: float
    ) -> float:
        # Reference nsHttpResponseHead::ComputeFreshnessLifetime
        # https://dxr.mozilla.org/mozilla-central/source/netwerk/protocol/http/nsHttpResponseHead.cpp#706
        cc = self._parse_cachecontrol(response)
        maxage = self._get_max_age(cc)
        if maxage is not None:
            return maxage

        # Parse date header or synthesize it if none exists
        date = rfc1123_to_epoch(response.headers.get(b"Date")) or now

        # Try HTTP/1.0 Expires header
        if b"Expires" in response.headers:
            expires = rfc1123_to_epoch(response.headers[b"Expires"])
            # When parsing Expires header fails RFC 2616 section 14.21 says we
            # should treat this as an expiration time in the past.
            return max(0, expires - date) if expires else 0

        # Fallback to heuristic using last-modified header
        # This is not in RFC but on Firefox caching implementation
        lastmodified = rfc1123_to_epoch(response.headers.get(b"Last-Modified"))
        if lastmodified and lastmodified <= date:
            return (date - lastmodified) / 10

        # This request can be cached indefinitely
        if response.status in (300, 301, 308):
            return self.MAXAGE

        # Insufficient information to compute freshness lifetime
        return 0

    def _compute_current_age(
        self, response: Response, request: Request, now: float
    ) -> float:
        # Reference nsHttpResponseHead::ComputeCurrentAge
        # https://dxr.mozilla.org/mozilla-central/source/netwerk/protocol/http/nsHttpResponseHead.cpp#658
        currentage: float = 0
        # If Date header is not set we assume it is a fast connection, and
        # clock is in sync with the server
        date = rfc1123_to_epoch(response.headers.get(b"Date")) or now
        if now > date:
            currentage = now - date

        if b"Age" in response.headers:
            try:
                age = int(response.headers[b"Age"])  # type: ignore[arg-type]
                currentage = max(currentage, age)
            except ValueError:
                pass

        return currentage


class DbmCacheStorage:
    def __init__(self, settings: BaseSettings):
        self.cachedir: str = data_path(settings["HTTPCACHE_DIR"], createdir=True)
        self.expiration_secs: int = settings.getint("HTTPCACHE_EXPIRATION_SECS")
        self.dbmodule: ModuleType = import_module(settings["HTTPCACHE_DBM_MODULE"])
        self.db: Any = None  # the real type is private

    def open_spider(self, spider: Spider) -> None:
        dbpath = Path(self.cachedir, f"{spider.name}.db")
        self.db = self.dbmodule.open(str(dbpath), "c")

        logger.debug(
            "Using DBM cache storage in %(cachepath)s",
            {"cachepath": dbpath},
            extra={"spider": spider},
        )

        assert spider.crawler.request_fingerprinter
        self._fingerprinter: RequestFingerprinterProtocol = (
            spider.crawler.request_fingerprinter
        )

    def close_spider(self, spider: Spider) -> None:
        self.db.close()

    def retrieve_response(self, spider: Spider, request: Request) -> Response | None:
        data = self._read_data(spider, request)
        if data is None:
            return None  # not cached
        url = data["url"]
        status = data["status"]
        headers = Headers(data["headers"])
        body = data["body"]
        respcls = responsetypes.from_args(headers=headers, url=url, body=body)
        return respcls(url=url, headers=headers, status=status, body=body)

    def store_response(
        self, spider: Spider, request: Request, response: Response
    ) -> None:
        key = self._fingerprinter.fingerprint(request).hex()
        data = {
            "status": response.status,
            "url": response.url,
            "headers": dict(response.headers),
            "body": response.body,
        }
        self.db[f"{key}_data"] = pickle.dumps(data, protocol=4)
        self.db[f"{key}_time"] = str(time())

    def _read_data(self, spider: Spider, request: Request) -> dict[str, Any] | None:
        key = self._fingerprinter.fingerprint(request).hex()
        db = self.db
        tkey = f"{key}_time"
        if tkey not in db:
            return None  # not found

        ts = db[tkey]
        if 0 < self.expiration_secs < time() - float(ts):
            return None  # expired

        return cast(dict[str, Any], pickle.loads(db[f"{key}_data"]))  # noqa: S301


class FilesystemCacheStorage:
    def __init__(self, settings: BaseSettings):
        self.cachedir: str = data_path(settings["HTTPCACHE_DIR"])
        self.expiration_secs: int = settings.getint("HTTPCACHE_EXPIRATION_SECS")
        self.use_gzip: bool = settings.getbool("HTTPCACHE_GZIP")
        # https://github.com/python/mypy/issues/10740
        self._open: Callable[Concatenate[str | os.PathLike, str, ...], IO[bytes]] = (
            gzip.open if self.use_gzip else open  # type: ignore[assignment]
        )

    def open_spider(self, spider: Spider) -> None:
        logger.debug(
            "Using filesystem cache storage in %(cache_dir)s",
            {"cache_dir": self.cachedir},
            extra={"spider": spider},
        )

        assert spider.crawler.request_fingerprinter
        self._fingerprinter = spider.crawler.request_fingerprinter

    def close_spider(self, spider: Spider) -> None:
        pass

    def retrieve_response(self, spider: Spider, request: Request) -> Response | None:
        """Return response if present in cache, or None otherwise."""
        metadata = self._read_meta(spider, request)
        if metadata is None:
            return None  # not cached
        rpath = Path(self._get_request_path(spider, request))
        with self._open(rpath / "response_body", "rb") as f:
            body = f.read()
        with self._open(rpath / "response_headers", "rb") as f:
            rawheaders = f.read()
        url = metadata["response_url"]
        status = metadata["status"]
        headers = Headers(headers_raw_to_dict(rawheaders))
        respcls = responsetypes.from_args(headers=headers, url=url, body=body)
        return respcls(url=url, headers=headers, status=status, body=body)

    def store_response(
        self, spider: Spider, request: Request, response: Response
    ) -> None:
        """Store the given response in the cache."""
        rpath = Path(self._get_request_path(spider, request))
        if not rpath.exists():
            rpath.mkdir(parents=True)
        metadata = {
            "url": request.url,
            "method": request.method,
            "status": response.status,
            "response_url": response.url,
            "timestamp": time(),
        }
        with self._open(rpath / "meta", "wb") as f:
            f.write(to_bytes(repr(metadata)))
        with self._open(rpath / "pickled_meta", "wb") as f:
            pickle.dump(metadata, f, protocol=4)
        with self._open(rpath / "response_headers", "wb") as f:
            f.write(headers_dict_to_raw(response.headers))
        with self._open(rpath / "response_body", "wb") as f:
            f.write(response.body)
        with self._open(rpath / "request_headers", "wb") as f:
            f.write(headers_dict_to_raw(request.headers))
        with self._open(rpath / "request_body", "wb") as f:
            f.write(request.body)

    def _get_request_path(self, spider: Spider, request: Request) -> str:
        key = self._fingerprinter.fingerprint(request).hex()
        return str(Path(self.cachedir, spider.name, key[0:2], key))

    def _read_meta(self, spider: Spider, request: Request) -> dict[str, Any] | None:
        rpath = Path(self._get_request_path(spider, request))
        metapath = rpath / "pickled_meta"
        if not metapath.exists():
            return None  # not found
        mtime = metapath.stat().st_mtime
        if 0 < self.expiration_secs < time() - mtime:
            return None  # expired
        with self._open(metapath, "rb") as f:
            return cast(dict[str, Any], pickle.load(f))  # noqa: S301


class WARCCacheStorage:
    def __init__(self, settings: BaseSettings):
        self.cache_dir: str = data_path(settings["HTTPCACHE_DIR"])
        self.use_gzip: bool = settings.getbool("HTTPCACHE_GZIP")
        self.pathname_strategy: HTTPCacheWARCPathStyle = settings.get(
            "HTTPCACHE_WARC_PATH_STYLE", HTTPCacheWARCPathStyle.FILE_AND_HASH
        )

    @staticmethod
    def http_headers_cleaner(
        scrapy_headers: dict[bytes, bytes],
    ) -> dict[str | bytes, LiteralString | str | bytes]:
        """Convert Scrapy headers to a format suitable for WARC records."""
        rv = {}
        for k, v in scrapy_headers.items():
            if v is not None:
                key = k.decode("ascii") if isinstance(k, bytes) else k
                val = v.decode("ascii") if isinstance(v, bytes) else v
                if isinstance(v, list):
                    val = ", ".join(el.decode("ascii") for el in v)
                rv[key] = val
        return rv

    def open_spider(self, spider: Spider) -> None:
        logger.debug(
            "Using WARC cache storage in %(cache_dir)s",
            {"cache_dir": self.cache_dir},
            extra={"spider": spider},
        )

        assert spider.crawler.request_fingerprinter

    def close_spider(self, spider: Spider) -> None:
        pass

    def retrieve_response(self, spider: Spider, request: Request) -> Response | None:
        """Return response if present in cache, or None otherwise."""

        warc_path, url_parts = self._get_warc_path(spider, request)

        if not warc_path.exists():
            return None

        response, warc_req, warc_resp = None, None, None

        with warc_path.open("rb") as warc_fh:
            for warc_rec in ArchiveIterator(warc_fh):
                if warc_rec.rec_type == "response":
                    warc_resp = warc_rec
                elif warc_rec.rec_type == "request":
                    warc_req = warc_rec

        # Only create response if both request & response recs were found
        if not warc_req or not warc_resp:
            logger.warning(
                "Incomplete WARC record found in cache%s%s (%s), request missing"
                if not warc_req
                else ", response missing"
                if not warc_resp
                else ""
            )
            return None

        try:
            # Extract status code from the status line
            status_line = warc_resp.http_headers.statusline
            if not status_line:
                logger.error("Missing status line in WARC response record")
                return None

            # Parse the status code from the status line
            # e.g., "HTTP/1.1 200 OK"
            parts = status_line.split(" ", 2)
            if len(parts) < 2:
                logger.error("Invalid status line format: %s", status_line)
                return None

            try:
                status_code = int(parts[0])
            except ValueError:
                logger.error("Invalid status code in status line: %s", status_line)
                return None

            # Extract headers from HTTP headers
            resp_headers = {
                name: value
                for name, value in warc_resp.http_headers.headers
                if name.lower() != "status"  # Skip status line
            }

            # We need to reopen the WARC file to read the response body
            # because the content_stream() can only be read once, and it is
            # already read by ArchiveIterator for WARC record parsing
            with warc_path.open("rb") as warc_fh_body:
                logger.warning(
                    "Retrieving existing cache file: %s *for* %s",
                    warc_path,
                    request.url,
                )

                for warc_rec_body in ArchiveIterator(warc_fh_body):
                    if warc_rec_body.rec_type == "response":
                        # Read the response body
                        resp_body = warc_rec_body.content_stream().read()

                        # Create the response object
                        response_class = responsetypes.from_args(
                            headers=Headers(resp_headers),
                            url=warc_resp.rec_headers.get_header("WARC-Target-URI"),
                        )
                        response = response_class(
                            url=warc_resp.rec_headers.get_header("WARC-Target-URI"),
                            status=status_code,
                            headers=Headers(resp_headers),
                            body=resp_body,
                            request=request,
                            protocol="HTTP/1.1",  # Default to HTTP/1.1
                        )

                        # Log the body length for debugging
                        logger.info(
                            "Retrieved cached response body length: %d", len(resp_body)
                        )

                        break
        except Exception as e:
            logger.error("Error retrieving response from WARC file: %s", e)
            return None

        return response

    def store_response(
        self, spider: Spider, request: Request, response: Response
    ) -> None:
        """Store the given response in the cache."""
        warc_path, url_parts = self._get_warc_path(spider, request)

        # Ensure cache folder exists
        if not warc_path.parent.exists():
            warc_path.parent.mkdir(parents=True)

        logger.warning("Writing new cache file: %s *for* %s", warc_path, request.url)

        with warc_path.open("wb") as warc_fh:
            # Generate a UUID for the WARC record
            record_id = f"<urn:uuid:{uuid.uuid4()}>"

            # Create HTTP headers for the request
            headers = WARCCacheStorage.http_headers_cleaner(request.headers)

            # Reconstruct the request line, since Scrapy doesn't provide it
            request_path = (
                url_parts.path + ("?" if url_parts.query else "") + url_parts.query
            )
            request_headers = StatusAndHeaders(
                statusline=f"{request.method} {request_path} HTTP/1.1",
                headers=headers,
                protocol="",  # Requests append the protocol, not prepend
            )

            # Create the request record
            content_type = request.headers.get("Content-Type", b"")
            content_type_str: str = (
                content_type.decode("ascii")
                if content_type
                else "application/http; msgtype=request"
            )
            request_rec = RecordBuilder().create_warc_record(
                uri=request.url,
                record_type="request",
                payload=BytesIO(request.body),
                warc_headers_dict={
                    "WARC-Date": formatdate(time(), localtime=False, usegmt=True),
                    "WARC-Record-ID": record_id,
                    "Content-Type": content_type_str,
                },
                http_headers=request_headers,
            )

            # Copy HTTP headers for the response
            resp_hdrs_cleaned = WARCCacheStorage.http_headers_cleaner(response.headers)
            status_msg = HTTP_STATUS_MSGS.get(response.status, "")
            status_line = f"{response.status} {status_msg}"

            response_headers = StatusAndHeaders(
                statusline=status_line, headers=resp_hdrs_cleaned, protocol="HTTP/1.1"
            )

            # Handle gzipped content, most clients process the response body
            # based on the Content-Type and Content-Encoding
            if "gzip" in resp_hdrs_cleaned.get("Content-Encoding", ""):
                resp_body = gzip.decompress(response.body)
            else:
                resp_body = response.body

            # Get content type
            content_type = request.headers.get("Content-Type", b"")
            resp_content_type: str = (
                content_type.decode("ascii") if content_type else "text/html"
            )
            if ";" in resp_content_type:
                resp_type, _ = resp_content_type.split(";", 1)

            # Create the response record
            response_rec = RecordBuilder().create_warc_record(
                uri=response.url,
                record_type="response",
                payload=BytesIO(resp_body),
                warc_headers_dict={
                    "WARC-Date": formatdate(time(), localtime=False, usegmt=True),
                    "WARC-Record-ID": f"<urn:uuid:{uuid.uuid4()}>",
                    "Scrapy-Response-Class": response.__class__.__name__,
                    "Content-Type": resp_content_type,
                },
                http_headers=response_headers,
            )

            # Write the request and response records to the WARC file
            writer = WARCWriter(filebuf=warc_fh, gzip=self.use_gzip)
            writer.write_record(response_rec)
            writer.write_record(request_rec)

    def _get_warc_path(self, spider: Spider, request: Request) -> tuple[Path, Any]:
        url_parts = urlparse_cached(request)
        filesafe_path = URL_TO_FILE_SAFE_RX.sub("_", url_parts.path).strip("_")
        path = Path(self.cache_dir, url_parts.netloc)
        query = "?" + url_parts.query if url_parts.query else ""

        strat = self.pathname_strategy
        if strat == HTTPCacheWARCPathStyle.FILE_ONLY.name:
            path /= filesafe_path + query
        elif strat == HTTPCacheWARCPathStyle.FILE_AND_HASH.name:
            request_hash = spider.crawler.request_fingerprinter.fingerprint(
                request
            ).hex()
            path /= filesafe_path + query + f"-{request_hash}"
        elif strat == HTTPCacheWARCPathStyle.FOLDERS_AND_FILE.name:
            path /= Path(*(str(url_parts.path) + query).split("/"))
        elif strat == HTTPCacheWARCPathStyle.FOLDERS_FILE_AND_HASH.name:
            request_hash = spider.crawler.request_fingerprinter.fingerprint(
                request
            ).hex()
            hyphen = "-" if query or not url_parts.path.endswith("/") else ""
            path /= Path(
                *(str(url_parts.path) + query + f"{hyphen}{request_hash}").split("/")
            )
        else:
            raise ValueError(f"Unknown path style: {self.pathname_strategy}")

        warc_path = Path(str(path) + ".warc" + (".gz" if self.use_gzip else ""))
        return warc_path, url_parts


def parse_cachecontrol(header: bytes) -> dict[bytes, bytes | None]:
    """Parse Cache-Control header

    https://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9

    >>> parse_cachecontrol(b'public, max-age=3600') == {b'public': None,
    ...                                                 b'max-age': b'3600'}
    True
    >>> parse_cachecontrol(b'') == {}
    True

    """
    directives = {}
    for directive in header.split(b","):
        key, sep, val = directive.strip().partition(b"=")
        if key:
            directives[key.lower()] = val if sep else None
    return directives


def rfc1123_to_epoch(date_str: str | bytes | None) -> int | None:
    try:
        date_str = to_unicode(date_str, encoding="ascii")  # type: ignore[arg-type]
        return mktime_tz(parsedate_tz(date_str))  # type: ignore[arg-type]
    except Exception:
        return None
