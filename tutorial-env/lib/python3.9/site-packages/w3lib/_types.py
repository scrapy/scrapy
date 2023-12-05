from typing import Union

# the base class UnicodeError doesn't have attributes like start / end
AnyUnicodeError = Union[UnicodeEncodeError, UnicodeDecodeError]
StrOrBytes = Union[str, bytes]
