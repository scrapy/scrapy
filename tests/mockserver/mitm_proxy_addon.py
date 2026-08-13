def response(flow) -> None:
    # add custom headers to be able to check that the request went through the proxy
    flow.response.headers["X-Via-Mitmproxy"] = "1"
    if flow.client_conn.tls_established:
        flow.response.headers["X-Via-Mitmproxy-TLS"] = "1"
