# std imports
from typing import (Any,
                    Set,
                    List,
                    Type,
                    Tuple,
                    Union,
                    TypeVar,
                    Callable,
                    NoReturn,
                    Optional,
                    overload)

# local
from .terminal import Terminal

COLORS: Set[str]
COMPOUNDABLES: Set[str]

_T = TypeVar("_T")

class ParameterizingString(str):
    def __new__(cls: Type[_T], cap: str, normal: str = ..., name: str = ...) -> _T: ...
    @overload
    def __call__(
        self, *args: int
    ) -> Union["FormattingString", "NullCallableString"]: ...
    @overload
    def __call__(self, *args: str) -> NoReturn: ...

class ParameterizingProxyString(str):
    def __new__(
        cls: Type[_T],
        fmt_pair: Tuple[str, Callable[..., Tuple[object, ...]]],
        normal: str = ...,
        name: str = ...,
    ) -> _T: ...
    def __call__(self, *args: Any) -> "FormattingString": ...

class FormattingString(str):
    def __new__(cls: Type[_T], sequence: str, normal: str = ...) -> _T: ...
    @overload
    def __call__(self, *args: int) -> NoReturn: ...
    @overload
    def __call__(self, *args: str) -> str: ...

class FormattingOtherString(str):
    def __new__(
        cls: Type[_T], direct: ParameterizingString, target: ParameterizingString = ...
    ) -> _T: ...
    def __call__(self, *args: Union[int, str]) -> str: ...

class NullCallableString(str):
    def __new__(cls: Type[_T]) -> _T: ...
    @overload
    def __call__(self, *args: int) -> "NullCallableString": ...
    @overload
    def __call__(self, *args: str) -> str: ...

def get_proxy_string(
    term: Terminal, attr: str
) -> Optional[ParameterizingProxyString]: ...
def split_compound(compound: str) -> List[str]: ...
def resolve_capability(term: Terminal, attr: str) -> str: ...
def resolve_color(
    term: Terminal, color: str
) -> Union[NullCallableString, FormattingString]: ...
def resolve_attribute(
    term: Terminal, attr: str
) -> Union[ParameterizingString, FormattingString]: ...
