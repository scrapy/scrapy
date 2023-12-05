import re
from functools import partial
from typing import Any, Callable, Dict, Tuple

from curtsies.formatstring import fmtstr, FmtStr
from curtsies.termformatconstants import (
    FG_COLORS,
    BG_COLORS,
    colors as CURTSIES_COLORS,
)

from ..config import COLOR_LETTERS
from ..lazyre import LazyReCompile


COLORS = CURTSIES_COLORS + ("default",)
CNAMES = dict(zip(COLOR_LETTERS, COLORS))
# hack for finding the "inverse"
INVERSE_COLORS = {
    CURTSIES_COLORS[idx]: CURTSIES_COLORS[
        (idx + (len(CURTSIES_COLORS) // 2)) % len(CURTSIES_COLORS)
    ]
    for idx in range(len(CURTSIES_COLORS))
}
INVERSE_COLORS["default"] = INVERSE_COLORS[CURTSIES_COLORS[0]]


def func_for_letter(
    letter_color_code: str, default: str = "k"
) -> Callable[..., FmtStr]:
    """Returns FmtStr constructor for a bpython-style color code"""
    if letter_color_code == "d":
        letter_color_code = default
    elif letter_color_code == "D":
        letter_color_code = default.upper()
    return partial(
        fmtstr,
        fg=CNAMES[letter_color_code.lower()],
        bold=letter_color_code.isupper(),
    )


def color_for_letter(letter_color_code: str, default: str = "k") -> str:
    if letter_color_code == "d":
        letter_color_code = default
    return CNAMES[letter_color_code.lower()]


def parse(s: str) -> FmtStr:
    """Returns a FmtStr object from a bpython-formatted colored string"""
    rest = s
    stuff = []
    while rest:
        start, rest = peel_off_string(rest)
        stuff.append(start)
    return (
        sum((fs_from_match(d) for d in stuff[1:]), fs_from_match(stuff[0]))
        if len(stuff) > 0
        else FmtStr()
    )


def fs_from_match(d: Dict[str, Any]) -> FmtStr:
    atts = {}
    color = "default"
    if d["fg"]:
        # this isn't according to spec as I understand it
        if d["fg"].isupper():
            d["bold"] = True
        # TODO figure out why boldness isn't based on presence of \x02

        color = CNAMES[d["fg"].lower()]
        if color != "default":
            atts["fg"] = FG_COLORS[color]
    if d["bg"]:
        if d["bg"] == "I":
            # hack for finding the "inverse"
            color = INVERSE_COLORS[color]
        else:
            color = CNAMES[d["bg"].lower()]
        if color != "default":
            atts["bg"] = BG_COLORS[color]
    if d["bold"]:
        atts["bold"] = True
    return fmtstr(d["string"], **atts)


peel_off_string_re = LazyReCompile(
    r"""(?P<colormarker>\x01
            (?P<fg>[krgybmcwdKRGYBMCWD]?)
            (?P<bg>[krgybmcwdKRGYBMCWDI]?)?)
        (?P<bold>\x02?)
        \x03
        (?P<string>[^\x04]*)
        \x04
        (?P<rest>.*)
        """,
    re.VERBOSE | re.DOTALL,
)


def peel_off_string(s: str) -> Tuple[Dict[str, Any], str]:
    m = peel_off_string_re.match(s)
    assert m, repr(s)
    d = m.groupdict()
    rest = d["rest"]
    del d["rest"]
    return d, rest
