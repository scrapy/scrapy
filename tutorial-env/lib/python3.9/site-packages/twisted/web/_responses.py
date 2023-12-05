# -*- test-case-name: twisted.web.test.test_http -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HTTP response code definitions.
"""


_CONTINUE = 100
SWITCHING = 101

OK = 200
CREATED = 201
ACCEPTED = 202
NON_AUTHORITATIVE_INFORMATION = 203
NO_CONTENT = 204
RESET_CONTENT = 205
PARTIAL_CONTENT = 206
MULTI_STATUS = 207

MULTIPLE_CHOICE = 300
MOVED_PERMANENTLY = 301
FOUND = 302
SEE_OTHER = 303
NOT_MODIFIED = 304
USE_PROXY = 305
TEMPORARY_REDIRECT = 307
PERMANENT_REDIRECT = 308

BAD_REQUEST = 400
UNAUTHORIZED = 401
PAYMENT_REQUIRED = 402
FORBIDDEN = 403
NOT_FOUND = 404
NOT_ALLOWED = 405
NOT_ACCEPTABLE = 406
PROXY_AUTH_REQUIRED = 407
REQUEST_TIMEOUT = 408
CONFLICT = 409
GONE = 410
LENGTH_REQUIRED = 411
PRECONDITION_FAILED = 412
REQUEST_ENTITY_TOO_LARGE = 413
REQUEST_URI_TOO_LONG = 414
UNSUPPORTED_MEDIA_TYPE = 415
REQUESTED_RANGE_NOT_SATISFIABLE = 416
EXPECTATION_FAILED = 417

INTERNAL_SERVER_ERROR = 500
NOT_IMPLEMENTED = 501
BAD_GATEWAY = 502
SERVICE_UNAVAILABLE = 503
GATEWAY_TIMEOUT = 504
HTTP_VERSION_NOT_SUPPORTED = 505
INSUFFICIENT_STORAGE_SPACE = 507
NOT_EXTENDED = 510

RESPONSES = {
    # 100
    _CONTINUE: b"Continue",
    SWITCHING: b"Switching Protocols",
    # 200
    OK: b"OK",
    CREATED: b"Created",
    ACCEPTED: b"Accepted",
    NON_AUTHORITATIVE_INFORMATION: b"Non-Authoritative Information",
    NO_CONTENT: b"No Content",
    RESET_CONTENT: b"Reset Content.",
    PARTIAL_CONTENT: b"Partial Content",
    MULTI_STATUS: b"Multi-Status",
    # 300
    MULTIPLE_CHOICE: b"Multiple Choices",
    MOVED_PERMANENTLY: b"Moved Permanently",
    FOUND: b"Found",
    SEE_OTHER: b"See Other",
    NOT_MODIFIED: b"Not Modified",
    USE_PROXY: b"Use Proxy",
    # 306 not defined??
    TEMPORARY_REDIRECT: b"Temporary Redirect",
    PERMANENT_REDIRECT: b"Permanent Redirect",
    # 400
    BAD_REQUEST: b"Bad Request",
    UNAUTHORIZED: b"Unauthorized",
    PAYMENT_REQUIRED: b"Payment Required",
    FORBIDDEN: b"Forbidden",
    NOT_FOUND: b"Not Found",
    NOT_ALLOWED: b"Method Not Allowed",
    NOT_ACCEPTABLE: b"Not Acceptable",
    PROXY_AUTH_REQUIRED: b"Proxy Authentication Required",
    REQUEST_TIMEOUT: b"Request Time-out",
    CONFLICT: b"Conflict",
    GONE: b"Gone",
    LENGTH_REQUIRED: b"Length Required",
    PRECONDITION_FAILED: b"Precondition Failed",
    REQUEST_ENTITY_TOO_LARGE: b"Request Entity Too Large",
    REQUEST_URI_TOO_LONG: b"Request-URI Too Long",
    UNSUPPORTED_MEDIA_TYPE: b"Unsupported Media Type",
    REQUESTED_RANGE_NOT_SATISFIABLE: b"Requested Range not satisfiable",
    EXPECTATION_FAILED: b"Expectation Failed",
    # 500
    INTERNAL_SERVER_ERROR: b"Internal Server Error",
    NOT_IMPLEMENTED: b"Not Implemented",
    BAD_GATEWAY: b"Bad Gateway",
    SERVICE_UNAVAILABLE: b"Service Unavailable",
    GATEWAY_TIMEOUT: b"Gateway Time-out",
    HTTP_VERSION_NOT_SUPPORTED: b"HTTP Version not supported",
    INSUFFICIENT_STORAGE_SPACE: b"Insufficient Storage Space",
    NOT_EXTENDED: b"Not Extended",
}
