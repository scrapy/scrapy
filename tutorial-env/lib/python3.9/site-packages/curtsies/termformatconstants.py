"""Constants for terminal formatting"""

from typing import Mapping

colors = "black", "red", "green", "yellow", "blue", "magenta", "cyan", "gray"
FG_COLORS: Mapping[str, int] = dict(zip(colors, range(30, 38)))
BG_COLORS: Mapping[str, int] = dict(zip(colors, range(40, 48)))
STYLES: Mapping[str, int] = dict(
    zip(("bold", "dark", "underline", "blink", "invert"), (1, 2, 4, 5, 7))
)
FG_NUMBER_TO_COLOR: Mapping[int, str] = dict(zip(FG_COLORS.values(), FG_COLORS.keys()))
BG_NUMBER_TO_COLOR: Mapping[int, str] = dict(zip(BG_COLORS.values(), BG_COLORS.keys()))
NUMBER_TO_STYLE = dict(zip(STYLES.values(), STYLES.keys()))
RESET_ALL = 0
RESET_FG = 39
RESET_BG = 49


def seq(num: int) -> str:
    return f"[{num}m"
