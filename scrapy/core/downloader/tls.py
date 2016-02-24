from OpenSSL import SSL


METHOD_SSLv3 = 'SSLv3'
METHOD_TLS = 'TLS'
METHOD_TLSv10 = 'TLSv1.0'
METHOD_TLSv11 = 'TLSv1.1'
METHOD_TLSv12 = 'TLSv1.2'

openssl_methods = {
    METHOD_TLS:    SSL.SSLv23_METHOD,                   # protocol negotiation (recommended)
    METHOD_SSLv3:  SSL.SSLv3_METHOD,                    # SSL 3 (NOT recommended)
    METHOD_TLSv10: SSL.TLSv1_METHOD,                    # TLS 1.0 only
    METHOD_TLSv11: getattr(SSL, 'TLSv1_1_METHOD', 5),   # TLS 1.1 only
    METHOD_TLSv12: getattr(SSL, 'TLSv1_2_METHOD', 6),   # TLS 1.2 only
}
