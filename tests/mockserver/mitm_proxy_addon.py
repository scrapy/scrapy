from typing import Any

# headers of the CONNECT request of each client connection, so that headers
# sent to the proxy can also be checked for requests that go through a tunnel,
# which the proxy cannot read
connect_headers: dict[Any, Any] = {}


def http_connect(flow) -> None:
    connect_headers[flow.client_conn.peername] = flow.request.headers.copy()


def response(flow) -> None:
    # add custom headers to be able to check that the request went through the proxy
    flow.response.headers["X-Via-Mitmproxy"] = "1"
    if flow.client_conn.tls_established:
        flow.response.headers["X-Via-Mitmproxy-TLS"] = "1"
    headers = connect_headers.get(flow.client_conn.peername, flow.request.headers)
    if echo := headers.get("X-Proxy-Echo"):
        flow.response.headers["X-Proxy-Echo"] = echo
