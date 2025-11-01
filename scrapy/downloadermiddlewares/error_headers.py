import logging
import socket
import ssl
from urllib.parse import urlsplit

from twisted.web._newclient import ResponseFailed

from scrapy.http import Headers, Response

logger = logging.getLogger(__name__)


class LenientHttpDownloaderMiddleware:
    """
    Fallback lenient fetch when Twisted fails parsing malformed response headers.
    see: https://github.com/scrapy/scrapy/issues/210
    """

    def process_exception(self, request, exception) -> Response | None:
        if not isinstance(exception, ResponseFailed):
            return None

        # server sent a malformed header that Twisted couldn't parse
        # see for details: https://github.com/scrapy/scrapy/issues/210
        if "not enough values to unpack (expected 2, got 1)" not in str(exception):
            return None

        try:
            logger.debug(
                "LenientHttpDownloaderMiddleware: bad header detected for request: %(request)s",
                {"request": request},
            )
            return self._lenient_fetch(request.url)
        except Exception:
            return None

    def _lenient_fetch(self, url: str, timeout: int = 5) -> Response:
        parts = urlsplit(url)
        host: str = parts.hostname
        port: int = parts.port
        path: str = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")

        sock: socket.socket = socket.create_connection((host, port), timeout=timeout)
        try:
            if parts.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(
                    sock, server_hostname=host
                )

            req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
            sock.sendall(req.encode("utf-8"))

            data: bytes = b""
            while chunk := sock.recv(8192):
                data += chunk
        finally:
            sock.close()

        # Find body separator
        # Try the standard CRLF separator (\r\n\r\n); fall back to LF (\n\n) for non‑compliant servers.
        headers_raw: bytes = b""
        body: bytes = data
        for sep in (b"\r\n\r\n", b"\n\n"):
            if sep in data:
                headers_raw, body = data.split(sep, 1)
                break

        # Default values
        status: int = 200
        headers_dict: dict[str, list[bytes]] = {}

        if headers_raw:
            lines: list[str] = headers_raw.decode("latin-1").splitlines()

            # Parse status line (skip if broken)
            if lines:
                first_line = lines[0].strip()
                parts = first_line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    status = int(parts[1])

            # Parse headers: keep only valid "name: value" lines
            for line in lines[1:]:
                line = line.strip()

                # skip blank/whitespace-only lines
                if not line:
                    continue

                if ":" in line:
                    name, value = line.split(":", 1)
                    name = name.strip()
                    value = value.strip()
                    if name:  # valid header name
                        headers_dict.setdefault(name, []).append(
                            value.encode("latin-1")
                        )
                else:
                    # Invalid line - drop silently
                    pass

        return Response(
            url=url,
            status=status,
            headers=Headers(headers_dict),
            body=body,
            flags=["BAD_HEADER_FALLBACK"],
        )
