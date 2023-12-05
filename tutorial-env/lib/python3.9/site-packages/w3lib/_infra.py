# https://infra.spec.whatwg.org/

import string

# https://infra.spec.whatwg.org/commit-snapshots/59e0d16c1e3ba0e77c6a60bfc69a0929b8ffaa5d/#code-points
_ASCII_TAB_OR_NEWLINE = "\t\n\r"
_ASCII_WHITESPACE = "\t\n\x0c\r "
_C0_CONTROL = "".join(chr(n) for n in range(32))
_C0_CONTROL_OR_SPACE = _C0_CONTROL + " "
_ASCII_DIGIT = string.digits
_ASCII_HEX_DIGIT = string.hexdigits
_ASCII_ALPHA = string.ascii_letters
_ASCII_ALPHANUMERIC = string.ascii_letters + string.digits
