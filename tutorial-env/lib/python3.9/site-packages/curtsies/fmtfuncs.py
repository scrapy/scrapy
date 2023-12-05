from functools import partial as _partial
from .formatstring import fmtstr

black = _partial(fmtstr, style="black")
red = _partial(fmtstr, style="red")
green = _partial(fmtstr, style="green")
yellow = _partial(fmtstr, style="yellow")
blue = _partial(fmtstr, style="blue")
magenta = _partial(fmtstr, style="magenta")
cyan = _partial(fmtstr, style="cyan")
gray = _partial(fmtstr, style="gray")

on_black = _partial(fmtstr, style="on_black")
on_dark = on_black  # deprecated, old name of on_black
on_red = _partial(fmtstr, style="on_red")
on_green = _partial(fmtstr, style="on_green")
on_yellow = _partial(fmtstr, style="on_yellow")
on_blue = _partial(fmtstr, style="on_blue")
on_magenta = _partial(fmtstr, style="on_magenta")
on_cyan = _partial(fmtstr, style="on_cyan")
on_gray = _partial(fmtstr, style="on_gray")

bold = _partial(fmtstr, style="bold")
dark = _partial(fmtstr, style="dark")
underline = _partial(fmtstr, style="underline")
blink = _partial(fmtstr, style="blink")
invert = _partial(fmtstr, style="invert")

plain = _partial(fmtstr)
