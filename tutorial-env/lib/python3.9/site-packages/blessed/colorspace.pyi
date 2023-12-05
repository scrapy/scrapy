# std imports
from typing import Set, Dict, Tuple, NamedTuple

CGA_COLORS: Set[str]

class RGBColor(NamedTuple):
    red: int
    green: int
    blue: int

X11_COLORNAMES_TO_RGB: Dict[str, RGBColor]
RGB_256TABLE: Tuple[RGBColor, ...]
