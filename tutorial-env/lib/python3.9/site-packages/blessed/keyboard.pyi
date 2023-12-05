# std imports
from typing import Set, Dict, Type, Mapping, TypeVar, Iterable, Optional, OrderedDict

# local
from .terminal import Terminal

_T = TypeVar("_T")

class Keystroke(str):
    def __new__(
        cls: Type[_T],
        ucs: str = ...,
        code: Optional[int] = ...,
        name: Optional[str] = ...,
    ) -> _T: ...
    @property
    def is_sequence(self) -> bool: ...
    @property
    def name(self) -> Optional[str]: ...
    @property
    def code(self) -> Optional[int]: ...

def get_keyboard_codes() -> Dict[int, str]: ...
def get_keyboard_sequences(term: Terminal) -> OrderedDict[str, int]: ...
def get_leading_prefixes(sequences: Iterable[str]) -> Set[str]: ...
def resolve_sequence(
    text: str, mapper: Mapping[str, int], codes: Mapping[int, str]
) -> Keystroke: ...
