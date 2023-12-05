# The MIT License
#
# Copyright (c) 2008 Bob Farrell
# Copyright (c) bpython authors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# mypy: disallow_untyped_defs=True
# mypy: disallow_untyped_calls=True

# Modified by Brandon Navra
# Notes for Windows
# Prerequisites
#  - Curses
#  - pyreadline
#
# Added
#
# - Support for running on windows command prompt
# - input from numpad keys
#
# Issues
#
# - Suspend doesn't work nor does detection of resizing of screen
# - Instead the suspend key exits the program
# - View source doesn't work on windows unless you install the less program (From GnuUtils or Cygwin)


import curses
import errno
import functools
import math
import os
import platform
import re
import struct
import sys
import time
from typing import (
    Iterator,
    NoReturn,
    List,
    MutableMapping,
    Any,
    Callable,
    TypeVar,
    cast,
    IO,
    Iterable,
    Optional,
    Union,
    Tuple,
    Collection,
    Dict,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from _curses import _CursesWindow

from ._typing_compat import Literal
import unicodedata
from dataclasses import dataclass

if platform.system() != "Windows":
    import signal  # Windows does not have job control
    import termios  # Windows uses curses
    import fcntl  # Windows uses curses


# These are used for syntax highlighting
from pygments import format
from pygments.formatters import TerminalFormatter
from pygments.lexers import Python3Lexer
from pygments.token import Token, _TokenType
from .formatter import BPythonFormatter

# This for config
from .config import getpreferredencoding, Config

# This for keys
from .keys import cli_key_dispatch as key_dispatch

# This for i18n
from . import translations
from .translations import _

from . import repl, inspection
from . import args as bpargs
from .pager import page
from .args import parse as argsparse

F = TypeVar("F", bound=Callable[..., Any])

# --- module globals ---
stdscr = None
colors: Optional[MutableMapping[str, int]] = None

DO_RESIZE = False
# ---


@dataclass
class ShowListState:
    cols: int = 0
    rows: int = 0
    wl: int = 0


def forward_if_not_current(func: F) -> F:
    @functools.wraps(func)
    def newfunc(self, *args, **kwargs):  # type: ignore
        dest = self.get_dest()
        if self is dest:
            return func(self, *args, **kwargs)
        else:
            return getattr(self.get_dest(), newfunc.__name__)(*args, **kwargs)

    return cast(F, newfunc)


class FakeStream:
    """Provide a fake file object which calls functions on the interface
    provided."""

    def __init__(self, interface: "CLIRepl", get_dest: IO[str]) -> None:
        self.encoding: str = getpreferredencoding()
        self.interface = interface
        self.get_dest = get_dest

    @forward_if_not_current
    def write(self, s: str) -> None:
        self.interface.write(s)

    @forward_if_not_current
    def writelines(self, l: Iterable[str]) -> None:
        for s in l:
            self.write(s)

    def isatty(self) -> bool:
        # some third party (amongst them mercurial) depend on this
        return True

    def flush(self) -> None:
        self.interface.flush()


class FakeStdin:
    """Provide a fake stdin type for things like raw_input() etc."""

    def __init__(self, interface: "CLIRepl") -> None:
        """Take the curses Repl on init and assume it provides a get_key method
        which, fortunately, it does."""

        self.encoding = getpreferredencoding()
        self.interface = interface
        self.buffer: List[str] = list()

    def __iter__(self) -> Iterator:
        return iter(self.readlines())

    def flush(self) -> None:
        """Flush the internal buffer. This is a no-op. Flushing stdin
        doesn't make any sense anyway."""

    def write(self, value: str) -> NoReturn:
        # XXX IPython expects sys.stdin.write to exist, there will no doubt be
        # others, so here's a hack to keep them happy
        raise OSError(errno.EBADF, "sys.stdin is read-only")

    def isatty(self) -> bool:
        return True

    def readline(self, size: int = -1) -> str:
        """I can't think of any reason why anything other than readline would
        be useful in the context of an interactive interpreter so this is the
        only one I've done anything with. The others are just there in case
        someone does something weird to stop it from blowing up."""

        if not size:
            return ""
        elif self.buffer:
            buffer = self.buffer.pop(0)
        else:
            buffer = ""

        curses.raw(True)
        try:
            while not buffer.endswith(("\n", "\r")):
                key = self.interface.get_key()
                if key in (curses.erasechar(), "KEY_BACKSPACE"):
                    y, x = self.interface.scr.getyx()
                    if buffer:
                        self.interface.scr.delch(y, x - 1)
                        buffer = buffer[:-1]
                    continue
                elif key == chr(4) and not buffer:
                    # C-d
                    return ""
                elif key not in ("\n", "\r") and (
                    len(key) > 1 or unicodedata.category(key) == "Cc"
                ):
                    continue
                sys.stdout.write(key)
                # Include the \n in the buffer - raw_input() seems to deal with trailing
                # linebreaks and will break if it gets an empty string.
                buffer += key
        finally:
            curses.raw(False)

        if size > 0:
            rest = buffer[size:]
            if rest:
                self.buffer.append(rest)
            buffer = buffer[:size]

        return buffer

    def read(self, size: Optional[int] = None) -> str:
        if size == 0:
            return ""

        data = list()
        while size is None or size > 0:
            line = self.readline(size or -1)
            if not line:
                break
            if size is not None:
                size -= len(line)
            data.append(line)

        return "".join(data)

    def readlines(self, size: int = -1) -> List[str]:
        return list(iter(self.readline, ""))


# TODO:
#
# Tab completion does not work if not at the end of the line.
#
# Numerous optimisations can be made but it seems to do all the lookup stuff
# fast enough on even my crappy server so I'm not too bothered about that
# at the moment.
#
# The popup window that displays the argspecs and completion suggestions
# needs to be an instance of a ListWin class or something so I can wrap
# the addstr stuff to a higher level.
#

# Have to ignore the return type on this one because the colors variable
# is Optional[MutableMapping[str, int]] but for the purposes of this
# function it can't be None
def get_color(config: Config, name: str) -> int:  # type: ignore[return]
    global colors
    if colors:
        return colors[config.color_scheme[name].lower()]


def get_colpair(config: Config, name: str) -> int:
    return curses.color_pair(get_color(config, name) + 1)


def make_colors(config: Config) -> Dict[str, int]:
    """Init all the colours in curses and bang them into a dictionary"""

    # blacK, Red, Green, Yellow, Blue, Magenta, Cyan, White, Default:
    c = {
        "k": 0,
        "r": 1,
        "g": 2,
        "y": 3,
        "b": 4,
        "m": 5,
        "c": 6,
        "w": 7,
        "d": -1,
    }

    if platform.system() == "Windows":
        c = dict(
            list(c.items())
            + [
                ("K", 8),
                ("R", 9),
                ("G", 10),
                ("Y", 11),
                ("B", 12),
                ("M", 13),
                ("C", 14),
                ("W", 15),
            ]
        )

    for i in range(63):
        if i > 7:
            j = i // 8
        else:
            j = c[config.color_scheme["background"]]
        curses.init_pair(i + 1, i % 8, j)

    return c


class CLIInteraction(repl.Interaction):
    def __init__(self, config: Config, statusbar: "Statusbar"):
        super().__init__(config)
        self.statusbar = statusbar

    def confirm(self, q: str) -> bool:
        """Ask for yes or no and return boolean"""
        try:
            reply = self.statusbar.prompt(q)
        except ValueError:
            return False

        return reply.lower() in (_("y"), _("yes"))

    def notify(
        self, s: str, n: float = 10.0, wait_for_keypress: bool = False
    ) -> None:
        self.statusbar.message(s, n)

    def file_prompt(self, s: str) -> Optional[str]:
        return self.statusbar.prompt(s)


class CLIRepl(repl.Repl):
    def __init__(
        self,
        scr: "_CursesWindow",
        interp: repl.Interpreter,
        statusbar: "Statusbar",
        config: Config,
        idle: Optional[Callable] = None,
    ):
        super().__init__(interp, config)
        # mypy doesn't quite understand the difference between a class variable with a callable type and a method.
        # https://github.com/python/mypy/issues/2427
        self.interp.writetb = self.writetb  # type:ignore[assignment]
        self.scr: "_CursesWindow" = scr
        self.stdout_hist = ""  # native str (bytes in Py2, unicode in Py3)
        self.list_win = newwin(get_colpair(config, "background"), 1, 1, 1, 1)
        self.cpos = 0
        self.do_exit = False
        self.exit_value: Tuple[Any, ...] = ()
        self.f_string = ""
        self.idle = idle
        self.in_hist = False
        self.paste_mode = False
        self.last_key_press = time.time()
        self.s = ""
        self.statusbar = statusbar
        self.formatter = BPythonFormatter(config.color_scheme)
        self.interact = CLIInteraction(self.config, statusbar=self.statusbar)
        self.ix: int
        self.iy: int
        self.arg_pos: Union[str, int, None]
        self.prev_block_finished: int

        if config.cli_suggestion_width <= 0 or config.cli_suggestion_width > 1:
            config.cli_suggestion_width = 0.8

    def _get_cursor_offset(self) -> int:
        return len(self.s) - self.cpos

    def _set_cursor_offset(self, offset: int) -> None:
        self.cpos = len(self.s) - offset

    def addstr(self, s: str) -> None:
        """Add a string to the current input line and figure out
        where it should go, depending on the cursor position."""
        self.rl_history.reset()
        if not self.cpos:
            self.s += s
        else:
            l = len(self.s)
            self.s = self.s[: l - self.cpos] + s + self.s[l - self.cpos :]

        self.complete()

    def atbol(self) -> bool:
        """Return True or False accordingly if the cursor is at the beginning
        of the line (whitespace is ignored). This exists so that p_key() knows
        how to handle the tab key being pressed - if there is nothing but white
        space before the cursor then process it as a normal tab otherwise
        attempt tab completion."""

        return not self.s.lstrip()

    # This function shouldn't return None because of pos -= self.bs() later on
    def bs(self, delete_tabs: bool = True) -> int:  # type: ignore[return-value]
        """Process a backspace"""

        self.rl_history.reset()
        y, x = self.scr.getyx()

        if not self.s:
            return None  # type: ignore[return-value]

        if x == self.ix and y == self.iy:
            return None  # type: ignore[return-value]

        n = 1

        self.clear_wrapped_lines()

        if not self.cpos:
            # I know the nested if blocks look nasty. :(
            if self.atbol() and delete_tabs:
                n = len(self.s) % self.config.tab_length
                if not n:
                    n = self.config.tab_length

            self.s = self.s[:-n]
        else:
            self.s = self.s[: -self.cpos - 1] + self.s[-self.cpos :]

        self.print_line(self.s, clr=True)

        return n

    def bs_word(self) -> str:
        self.rl_history.reset()
        pos = len(self.s) - self.cpos - 1
        deleted = []
        # First we delete any space to the left of the cursor.
        while pos >= 0 and self.s[pos] == " ":
            deleted.append(self.s[pos])
            pos -= self.bs()
        # Then we delete a full word.
        while pos >= 0 and self.s[pos] != " ":
            deleted.append(self.s[pos])
            pos -= self.bs()

        return "".join(reversed(deleted))

    def check(self) -> None:
        """Check if paste mode should still be active and, if not, deactivate
        it and force syntax highlighting."""

        if (
            self.paste_mode
            and time.time() - self.last_key_press > self.config.paste_time
        ):
            self.paste_mode = False
            self.print_line(self.s)

    def clear_current_line(self) -> None:
        """Called when a SyntaxError occurred in the interpreter. It is
        used to prevent autoindentation from occurring after a
        traceback."""
        repl.Repl.clear_current_line(self)
        self.s = ""

    def clear_wrapped_lines(self) -> None:
        """Clear the wrapped lines of the current input."""
        # curses does not handle this on its own. Sad.
        height, width = self.scr.getmaxyx()
        max_y = min(self.iy + (self.ix + len(self.s)) // width + 1, height)
        for y in range(self.iy + 1, max_y):
            self.scr.move(y, 0)
            self.scr.clrtoeol()

    def complete(self, tab: bool = False) -> None:
        """Get Autocomplete list and window.

        Called whenever these should be updated, and called
        with tab
        """
        if self.paste_mode:
            self.scr.touchwin()  # TODO necessary?
            return

        list_win_visible = repl.Repl.complete(self, tab)

        if list_win_visible:
            try:
                f = None
                if self.matches_iter.completer:
                    f = self.matches_iter.completer.format

                self.show_list(
                    self.matches_iter.matches,
                    self.arg_pos,
                    topline=self.funcprops,
                    formatter=f,
                )
            except curses.error:
                # XXX: This is a massive hack, it will go away when I get
                # cusswords into a good enough state that we can start
                # using it.
                self.list_win.border()
                self.list_win.refresh()
                list_win_visible = False
        if not list_win_visible:
            self.scr.redrawwin()
            self.scr.refresh()

    def clrtobol(self) -> None:
        """Clear from cursor to beginning of line; usual C-u behaviour"""
        self.clear_wrapped_lines()

        if not self.cpos:
            self.s = ""
        else:
            self.s = self.s[-self.cpos :]

        self.print_line(self.s, clr=True)
        self.scr.redrawwin()
        self.scr.refresh()

    def _get_current_line(self) -> str:
        return self.s

    def _set_current_line(self, line: str) -> None:
        self.s = line

    def cut_to_buffer(self) -> None:
        """Clear from cursor to end of line, placing into cut buffer"""
        self.cut_buffer = self.s[-self.cpos :]
        self.s = self.s[: -self.cpos]
        self.cpos = 0
        self.print_line(self.s, clr=True)
        self.scr.redrawwin()
        self.scr.refresh()

    def delete(self) -> None:
        """Process a del"""
        if not self.s:
            return

        if self.mvc(-1):
            self.bs(False)

    def echo(self, s: str, redraw: bool = True) -> None:
        """Parse and echo a formatted string with appropriate attributes. It
        uses the formatting method as defined in formatter.py to parse the
        strings. It won't update the screen if it's reevaluating the code (as it
        does with undo)."""
        a = get_colpair(self.config, "output")
        if "\x01" in s:
            rx = re.search("\x01([A-Za-z])([A-Za-z]?)", s)
            if rx:
                fg = rx.groups()[0]
                bg = rx.groups()[1]
                col_num = self._C[fg.lower()]
                if bg and bg != "I":
                    col_num *= self._C[bg.lower()]

                a = curses.color_pair(int(col_num) + 1)
                if bg == "I":
                    a = a | curses.A_REVERSE
                s = re.sub("\x01[A-Za-z][A-Za-z]?", "", s)
                if fg.isupper():
                    a = a | curses.A_BOLD
        s = s.replace("\x03", "")
        s = s.replace("\x01", "")

        # Replace NUL bytes, as addstr raises an exception otherwise
        s = s.replace("\0", "")
        # Replace \r\n bytes, as addstr remove the current line otherwise
        s = s.replace("\r\n", "\n")

        self.scr.addstr(s, a)

        if redraw and not self.evaluating:
            self.scr.refresh()

    def end(self, refresh: bool = True) -> bool:
        self.cpos = 0
        h, w = gethw()
        y, x = divmod(len(self.s) + self.ix, w)
        y += self.iy
        self.scr.move(y, x)
        if refresh:
            self.scr.refresh()

        return True

    def hbegin(self) -> None:
        """Replace the active line with first line in history and
        increment the index to keep track"""
        self.cpos = 0
        self.clear_wrapped_lines()
        self.rl_history.enter(self.s)
        self.s = self.rl_history.first()
        self.print_line(self.s, clr=True)

    def hend(self) -> None:
        """Same as hbegin() but, well, forward"""
        self.cpos = 0
        self.clear_wrapped_lines()
        self.rl_history.enter(self.s)
        self.s = self.rl_history.last()
        self.print_line(self.s, clr=True)

    def back(self) -> None:
        """Replace the active line with previous line in history and
        increment the index to keep track"""

        self.cpos = 0
        self.clear_wrapped_lines()
        self.rl_history.enter(self.s)
        self.s = self.rl_history.back()
        self.print_line(self.s, clr=True)

    def fwd(self) -> None:
        """Same as back() but, well, forward"""

        self.cpos = 0
        self.clear_wrapped_lines()
        self.rl_history.enter(self.s)
        self.s = self.rl_history.forward()
        self.print_line(self.s, clr=True)

    def search(self) -> None:
        """Search with the partial matches from the history object."""

        self.cpo = 0
        self.clear_wrapped_lines()
        self.rl_history.enter(self.s)
        self.s = self.rl_history.back(start=False, search=True)
        self.print_line(self.s, clr=True)

    def get_key(self) -> str:
        key = ""
        while True:
            try:
                key += self.scr.getkey()
                # Seems like we get a in the locale's encoding
                # encoded string in Python 3 as well, but of
                # type str instead of bytes, hence convert it to
                # bytes first and decode then
                key = key.encode("latin-1").decode(getpreferredencoding())
                self.scr.nodelay(False)
            except UnicodeDecodeError:
                # Yes, that actually kind of sucks, but I don't see another way to get
                # input right
                self.scr.nodelay(True)
            except curses.error:
                # I'm quite annoyed with the ambiguity of this exception handler. I previously
                # caught "curses.error, x" and accessed x.message and checked that it was "no
                # input", which seemed a crappy way of doing it. But then I ran it on a
                # different computer and the exception seems to have entirely different
                # attributes. So let's hope getkey() doesn't raise any other crazy curses
                # exceptions. :)
                self.scr.nodelay(False)
                # XXX What to do here? Raise an exception?
                if key:
                    return key
            else:
                if key != "\x00":
                    t = time.time()
                    self.paste_mode = (
                        t - self.last_key_press <= self.config.paste_time
                    )
                    self.last_key_press = t
                    return key
                else:
                    key = ""
            finally:
                if self.idle:
                    self.idle(self)

    def get_line(self) -> str:
        """Get a line of text and return it
        This function initialises an empty string and gets the
        curses cursor position on the screen and stores it
        for the echo() function to use later (I think).
        Then it waits for key presses and passes them to p_key(),
        which returns None if Enter is pressed (that means "Return",
        idiot)."""

        self.s = ""
        self.rl_history.reset()
        self.iy, self.ix = self.scr.getyx()

        if not self.paste_mode:
            for _ in range(self.next_indentation()):
                self.p_key("\t")

        self.cpos = 0

        while True:
            key = self.get_key()
            if self.p_key(key) is None:
                if self.config.cli_trim_prompts and self.s.startswith(">>> "):
                    self.s = self.s[4:]
                return self.s

    def home(self, refresh: bool = True) -> bool:
        self.scr.move(self.iy, self.ix)
        self.cpos = len(self.s)
        if refresh:
            self.scr.refresh()
        return True

    def lf(self) -> None:
        """Process a linefeed character; it only needs to check the
        cursor position and move appropriately so it doesn't clear
        the current line after the cursor."""
        if self.cpos:
            for _ in range(self.cpos):
                self.mvc(-1)

        # Reprint the line (as there was maybe a highlighted paren in it)
        self.print_line(self.s, newline=True)
        self.echo("\n")

    def mkargspec(
        self,
        topline: inspection.FuncProps,
        in_arg: Union[str, int, None],
        down: bool,
    ) -> int:
        """This figures out what to do with the argspec and puts it nicely into
        the list window. It returns the number of lines used to display the
        argspec.  It's also kind of messy due to it having to call so many
        addstr() to get the colouring right, but it seems to be pretty
        sturdy."""

        r = 3
        fn = topline.func
        args = topline.argspec.args
        kwargs = topline.argspec.defaults
        _args = topline.argspec.varargs
        _kwargs = topline.argspec.varkwargs
        is_bound_method = topline.is_bound_method
        kwonly = topline.argspec.kwonly
        kwonly_defaults = topline.argspec.kwonly_defaults or dict()
        max_w = int(self.scr.getmaxyx()[1] * 0.6)
        self.list_win.erase()
        self.list_win.resize(3, max_w)
        h, w = self.list_win.getmaxyx()

        self.list_win.addstr("\n  ")
        self.list_win.addstr(
            fn, get_colpair(self.config, "name") | curses.A_BOLD
        )
        self.list_win.addstr(": (", get_colpair(self.config, "name"))
        maxh = self.scr.getmaxyx()[0]

        if is_bound_method and isinstance(in_arg, int):
            in_arg += 1

        punctuation_colpair = get_colpair(self.config, "punctuation")

        for k, i in enumerate(args):
            y, x = self.list_win.getyx()
            ln = len(str(i))
            kw = None
            if kwargs and k + 1 > len(args) - len(kwargs):
                kw = repr(kwargs[k - (len(args) - len(kwargs))])
                ln += len(kw) + 1

            if ln + x >= w:
                ty = self.list_win.getbegyx()[0]
                if not down and ty > 0:
                    h += 1
                    self.list_win.mvwin(ty - 1, 1)
                    self.list_win.resize(h, w)
                elif down and h + r < maxh - ty:
                    h += 1
                    self.list_win.resize(h, w)
                else:
                    break
                r += 1
                self.list_win.addstr("\n\t")

            if str(i) == "self" and k == 0:
                color = get_colpair(self.config, "name")
            else:
                color = get_colpair(self.config, "token")

            if k == in_arg or i == in_arg:
                color |= curses.A_BOLD

            self.list_win.addstr(str(i), color)
            if kw is not None:
                self.list_win.addstr("=", punctuation_colpair)
                self.list_win.addstr(kw, get_colpair(self.config, "token"))
            if k != len(args) - 1:
                self.list_win.addstr(", ", punctuation_colpair)

        if _args:
            if args:
                self.list_win.addstr(", ", punctuation_colpair)
            self.list_win.addstr(f"*{_args}", get_colpair(self.config, "token"))

        if kwonly:
            if not _args:
                if args:
                    self.list_win.addstr(", ", punctuation_colpair)
                self.list_win.addstr("*", punctuation_colpair)
            marker = object()
            for arg in kwonly:
                self.list_win.addstr(", ", punctuation_colpair)
                color = get_colpair(self.config, "token")
                if arg == in_arg:
                    color |= curses.A_BOLD
                self.list_win.addstr(arg, color)
                default = kwonly_defaults.get(arg, marker)
                if default is not marker:
                    self.list_win.addstr("=", punctuation_colpair)
                    self.list_win.addstr(
                        repr(default), get_colpair(self.config, "token")
                    )

        if _kwargs:
            if args or _args or kwonly:
                self.list_win.addstr(", ", punctuation_colpair)
            self.list_win.addstr(
                f"**{_kwargs}", get_colpair(self.config, "token")
            )
        self.list_win.addstr(")", punctuation_colpair)

        return r

    def mvc(self, i: int, refresh: bool = True) -> bool:
        """This method moves the cursor relatively from the current
        position, where:
            0 == (right) end of current line
            length of current line len(self.s) == beginning of current line
        and:
            current cursor position + i
            for positive values of i the cursor will move towards the beginning
            of the line, negative values the opposite."""
        y, x = self.scr.getyx()

        if self.cpos == 0 and i < 0:
            return False

        if x == self.ix and y == self.iy and i >= 1:
            return False

        h, w = gethw()
        if x - i < 0:
            y -= 1
            x = w

        if x - i >= w:
            y += 1
            x = 0 + i

        self.cpos += i
        self.scr.move(y, x - i)
        if refresh:
            self.scr.refresh()

        return True

    def p_key(self, key: str) -> Union[None, str, bool]:
        """Process a keypress"""

        if key is None:
            return ""

        config = self.config

        if platform.system() == "Windows":
            C_BACK = chr(127)
            BACKSP = chr(8)
        else:
            C_BACK = chr(8)
            BACKSP = chr(127)

        if key == C_BACK:  # C-Backspace (on my computer anyway!)
            self.clrtobol()
            key = "\n"
            # Don't return; let it get handled

        if key == chr(27):  # Escape Key
            return ""

        if key in (BACKSP, "KEY_BACKSPACE"):
            self.bs()
            self.complete()
            return ""

        elif key in key_dispatch[config.delete_key] and not self.s:
            # Delete on empty line exits
            self.do_exit = True
            return None

        elif key in ("KEY_DC",) + key_dispatch[config.delete_key]:
            self.delete()
            self.complete()
            # Redraw (as there might have been highlighted parens)
            self.print_line(self.s)
            return ""

        elif key in key_dispatch[config.undo_key]:  # C-r
            n = self.prompt_undo()
            if n > 0:
                self.undo(n=n)
            return ""

        elif key in key_dispatch[config.search_key]:
            self.search()
            return ""

        elif key in ("KEY_UP",) + key_dispatch[config.up_one_line_key]:
            # Cursor Up/C-p
            self.back()
            return ""

        elif key in ("KEY_DOWN",) + key_dispatch[config.down_one_line_key]:
            # Cursor Down/C-n
            self.fwd()
            return ""

        elif key in ("KEY_LEFT", " ^B", chr(2)):  # Cursor Left or ^B
            self.mvc(1)
            # Redraw (as there might have been highlighted parens)
            self.print_line(self.s)

        elif key in ("KEY_RIGHT", "^F", chr(6)):  # Cursor Right or ^F
            self.mvc(-1)
            # Redraw (as there might have been highlighted parens)
            self.print_line(self.s)

        elif key in ("KEY_HOME", "^A", chr(1)):  # home or ^A
            self.home()
            # Redraw (as there might have been highlighted parens)
            self.print_line(self.s)

        elif key in ("KEY_END", "^E", chr(5)):  # end or ^E
            self.end()
            # Redraw (as there might have been highlighted parens)
            self.print_line(self.s)

        elif key in ("KEY_NPAGE",):  # page_down
            self.hend()
            self.print_line(self.s)

        elif key in ("KEY_PPAGE",):  # page_up
            self.hbegin()
            self.print_line(self.s)

        elif key in key_dispatch[config.cut_to_buffer_key]:  # cut to buffer
            self.cut_to_buffer()
            return ""

        elif key in key_dispatch[config.yank_from_buffer_key]:
            # yank from buffer
            self.yank_from_buffer()
            return ""

        elif key in key_dispatch[config.clear_word_key]:
            self.cut_buffer = self.bs_word()
            self.complete()
            return ""

        elif key in key_dispatch[config.clear_line_key]:
            self.clrtobol()
            return ""

        elif key in key_dispatch[config.clear_screen_key]:
            # clear all but current line
            self.screen_hist: List = [self.screen_hist[-1]]
            self.highlighted_paren = None
            self.redraw()
            return ""

        elif key in key_dispatch[config.exit_key]:
            if not self.s:
                self.do_exit = True
                return None
            else:
                return ""

        elif key in key_dispatch[config.save_key]:
            self.write2file()
            return ""

        elif key in key_dispatch[config.pastebin_key]:
            self.pastebin()
            return ""

        elif key in key_dispatch[config.copy_clipboard_key]:
            self.copy2clipboard()
            return ""

        elif key in key_dispatch[config.last_output_key]:
            page(self.stdout_hist[self.prev_block_finished : -4])
            return ""

        elif key in key_dispatch[config.show_source_key]:
            try:
                source = self.get_source_of_current_name()
            except repl.SourceNotFound as e:
                self.statusbar.message(f"{e}")
            else:
                if config.highlight_show_source:
                    source = format(
                        Python3Lexer().get_tokens(source), TerminalFormatter()
                    )
                page(source)
            return ""

        elif key in ("\n", "\r", "PADENTER"):
            self.lf()
            return None

        elif key == "\t":
            return self.tab()

        elif key == "KEY_BTAB":
            return self.tab(back=True)

        elif key in key_dispatch[config.suspend_key]:
            if platform.system() != "Windows":
                self.suspend()
                return ""
            else:
                self.do_exit = True
                return None

        elif key == "\x18":
            return self.send_current_line_to_editor()

        elif key == "\x03":
            raise KeyboardInterrupt()

        elif key[0:3] == "PAD" and key not in ("PAD0", "PADSTOP"):
            pad_keys = {
                "PADMINUS": "-",
                "PADPLUS": "+",
                "PADSLASH": "/",
                "PADSTAR": "*",
            }
            try:
                self.addstr(pad_keys[key])
                self.print_line(self.s)
            except KeyError:
                return ""
        elif len(key) == 1 and not unicodedata.category(key) == "Cc":
            self.addstr(key)
            self.print_line(self.s)

        else:
            return ""

        return True

    def print_line(
        self, s: Optional[str], clr: bool = False, newline: bool = False
    ) -> None:
        """Chuck a line of text through the highlighter, move the cursor
        to the beginning of the line and output it to the screen."""

        if not s:
            clr = True

        if self.highlighted_paren is not None:
            # Clear previous highlighted paren

            lineno = self.highlighted_paren[0]
            tokens = self.highlighted_paren[1]
            # mypy thinks tokens is List[Tuple[_TokenType, str]]
            # but it is supposed to be MutableMapping[_TokenType, str]
            self.reprint_line(lineno, tokens)
            self.highlighted_paren = None

        if self.config.syntax and (not self.paste_mode or newline):
            o = format(self.tokenize(s, newline), self.formatter)
        else:
            o = s

        self.f_string = o
        self.scr.move(self.iy, self.ix)

        if clr:
            self.scr.clrtoeol()

        if clr and not s:
            self.scr.refresh()

        if o:
            for t in o.split("\x04"):
                self.echo(t.rstrip("\n"))

        if self.cpos:
            t = self.cpos
            for _ in range(self.cpos):
                self.mvc(1)
            self.cpos = t

    def prompt(self, more: Any) -> None:  # I'm not sure of the type on this one
        """Show the appropriate Python prompt"""
        if not more:
            self.echo(
                "\x01{}\x03{}".format(
                    self.config.color_scheme["prompt"], self.ps1
                )
            )
            self.stdout_hist += self.ps1
            self.screen_hist.append(
                "\x01%s\x03%s\x04"
                % (self.config.color_scheme["prompt"], self.ps1)
            )
        else:
            prompt_more_color = self.config.color_scheme["prompt_more"]
            self.echo(f"\x01{prompt_more_color}\x03{self.ps2}")
            self.stdout_hist += self.ps2
            self.screen_hist.append(
                f"\x01{prompt_more_color}\x03{self.ps2}\x04"
            )

    def push(self, s: str, insert_into_history: bool = True) -> bool:
        # curses.raw(True) prevents C-c from causing a SIGINT
        curses.raw(False)
        try:
            return super().push(s, insert_into_history)
        except SystemExit as e:
            # Avoid a traceback on e.g. quit()
            self.do_exit = True
            self.exit_value = e.args
            return False
        finally:
            curses.raw(True)

    def redraw(self) -> None:
        """Redraw the screen using screen_hist"""
        self.scr.erase()
        for k, s in enumerate(self.screen_hist):
            if not s:
                continue
            self.iy, self.ix = self.scr.getyx()
            for i in s.split("\x04"):
                self.echo(i, redraw=False)
            if k < len(self.screen_hist) - 1:
                self.scr.addstr("\n")
        self.iy, self.ix = self.scr.getyx()
        self.print_line(self.s)
        self.scr.refresh()
        self.statusbar.refresh()

    def repl(self) -> Tuple[Any, ...]:
        """Initialise the repl and jump into the loop. This method also has to
        keep a stack of lines entered for the horrible "undo" feature. It also
        tracks everything that would normally go to stdout in the normal Python
        interpreter so it can quickly write it to stdout on exit after
        curses.endwin(), as well as a history of lines entered for using
        up/down to go back and forth (which has to be separate to the
        evaluation history, which will be truncated when undoing."""

        # Use our own helper function because Python's will use real stdin and
        # stdout instead of our wrapped
        self.push("from bpython._internal import _help as help\n", False)

        self.iy, self.ix = self.scr.getyx()
        self.more = False
        while not self.do_exit:
            self.f_string = ""
            self.prompt(self.more)
            try:
                inp = self.get_line()
            except KeyboardInterrupt:
                self.statusbar.message("KeyboardInterrupt")
                self.scr.addstr("\n")
                self.scr.touchwin()
                self.scr.refresh()
                continue

            self.scr.redrawwin()
            if self.do_exit:
                return self.exit_value

            self.history.append(inp)
            self.screen_hist[-1] += self.f_string
            self.stdout_hist += inp + "\n"
            stdout_position = len(self.stdout_hist)
            self.more = self.push(inp)
            if not self.more:
                self.prev_block_finished = stdout_position
                self.s = ""
        return self.exit_value

    def reprint_line(
        self, lineno: int, tokens: List[Tuple[_TokenType, str]]
    ) -> None:
        """Helper function for paren highlighting: Reprint line at offset
        `lineno` in current input buffer."""
        if not self.buffer or lineno == len(self.buffer):
            return

        real_lineno = self.iy
        height, width = self.scr.getmaxyx()
        for i in range(lineno, len(self.buffer)):
            string = self.buffer[i]
            # 4 = length of prompt
            length = len(string.encode(getpreferredencoding())) + 4
            real_lineno -= int(math.ceil(length / width))
        if real_lineno < 0:
            return

        self.scr.move(
            real_lineno, len(self.ps1) if lineno == 0 else len(self.ps2)
        )
        line = format(tokens, BPythonFormatter(self.config.color_scheme))
        for string in line.split("\x04"):
            self.echo(string)

    def resize(self) -> None:
        """This method exists simply to keep it straight forward when
        initialising a window and resizing it."""
        self.size()
        self.scr.erase()
        self.scr.resize(self.h, self.w)
        self.scr.mvwin(self.y, self.x)
        self.statusbar.resize(refresh=False)
        self.redraw()

    def getstdout(self) -> str:
        """This method returns the 'spoofed' stdout buffer, for writing to a
        file or sending to a pastebin or whatever."""

        return self.stdout_hist + "\n"

    def reevaluate(self) -> None:
        """Clear the buffer, redraw the screen and re-evaluate the history"""

        self.evaluating = True
        self.stdout_hist = ""
        self.f_string = ""
        self.buffer: List[str] = []
        self.scr.erase()
        self.screen_hist = []
        # Set cursor position to -1 to prevent paren matching
        self.cpos = -1

        self.prompt(False)

        self.iy, self.ix = self.scr.getyx()
        for line in self.history:
            self.stdout_hist += line + "\n"
            self.print_line(line)
            self.screen_hist[-1] += self.f_string
            # I decided it was easier to just do this manually
            # than to make the print_line and history stuff more flexible.
            self.scr.addstr("\n")
            self.more = self.push(line)
            self.prompt(self.more)
            self.iy, self.ix = self.scr.getyx()

        self.cpos = 0
        indent = repl.next_indentation(self.s, self.config.tab_length)
        self.s = ""
        self.scr.refresh()

        if self.buffer:
            for _ in range(indent):
                self.tab()

        self.evaluating = False
        # map(self.push, self.history)
        # ^-- That's how simple this method was at first :(

    def write(self, s: str) -> None:
        """For overriding stdout defaults"""
        if "\x04" in s:
            for block in s.split("\x04"):
                self.write(block)
            return
        if s.rstrip() and "\x03" in s:
            t = s.split("\x03")[1]
        else:
            t = s

        if not self.stdout_hist:
            self.stdout_hist = t
        else:
            self.stdout_hist += t

        self.echo(s)
        self.screen_hist.append(s.rstrip())

    def show_list(
        self,
        items: List[str],
        arg_pos: Union[str, int, None],
        topline: Optional[inspection.FuncProps] = None,
        formatter: Optional[Callable] = None,
        current_item: Optional[str] = None,
    ) -> None:
        v_items: Collection
        shared = ShowListState()
        y, x = self.scr.getyx()
        h, w = self.scr.getmaxyx()
        down = y < h // 2
        if down:
            max_h = h - y
        else:
            max_h = y + 1
        max_w = int(w * self.config.cli_suggestion_width)
        self.list_win.erase()

        if items and formatter:
            items = [formatter(x) for x in items]
            if current_item is not None:
                current_item = formatter(current_item)

        if topline:
            height_offset = self.mkargspec(topline, arg_pos, down) + 1
        else:
            height_offset = 0

        def lsize() -> bool:
            wl = max(len(i) for i in v_items) + 1
            if not wl:
                wl = 1
            cols = ((max_w - 2) // wl) or 1
            rows = len(v_items) // cols

            if cols * rows < len(v_items):
                rows += 1

            if rows + 2 >= max_h:
                return False

            shared.rows = rows
            shared.cols = cols
            shared.wl = wl
            return True

        if items:
            # visible items (we'll append until we can't fit any more in)
            v_items = [items[0][: max_w - 3]]
            lsize()
        else:
            v_items = []

        for i in items[1:]:
            v_items.append(i[: max_w - 3])
            if not lsize():
                del v_items[-1]
                v_items[-1] = "..."
                break

        rows = shared.rows
        if rows + height_offset < max_h:
            rows += height_offset
            display_rows = rows
        else:
            display_rows = rows + height_offset

        cols = shared.cols
        wl = shared.wl

        if topline and not v_items:
            w = max_w
        elif wl + 3 > max_w:
            w = max_w
        else:
            t = (cols + 1) * wl + 3
            if t > max_w:
                t = max_w
            w = t

        if height_offset and display_rows + 5 >= max_h:
            del v_items[-(cols * (height_offset)) :]

        if self.docstring is None:
            self.list_win.resize(rows + 2, w)
        else:
            docstring = self.format_docstring(
                self.docstring, max_w - 2, max_h - height_offset
            )
            docstring_string = "".join(docstring)
            rows += len(docstring)
            self.list_win.resize(rows, max_w)

        if down:
            self.list_win.mvwin(y + 1, 0)
        else:
            self.list_win.mvwin(y - rows - 2, 0)

        if v_items:
            self.list_win.addstr("\n ")

        for ix, i in enumerate(v_items):
            padding = (wl - len(i)) * " "
            if i == current_item:
                color = get_colpair(self.config, "operator")
            else:
                color = get_colpair(self.config, "main")
            self.list_win.addstr(i + padding, color)
            if (cols == 1 or (ix and not (ix + 1) % cols)) and ix + 1 < len(
                v_items
            ):
                self.list_win.addstr("\n ")

        if self.docstring is not None:
            self.list_win.addstr(
                "\n" + docstring_string, get_colpair(self.config, "comment")
            )
            # XXX: After all the trouble I had with sizing the list box (I'm not very good
            # at that type of thing) I decided to do this bit of tidying up here just to
            # make sure there's no unnecessary blank lines, it makes things look nicer.

        y = self.list_win.getyx()[0]
        self.list_win.resize(y + 2, w)

        self.statusbar.win.touchwin()
        self.statusbar.win.noutrefresh()
        self.list_win.attron(get_colpair(self.config, "main"))
        self.list_win.border()
        self.scr.touchwin()
        self.scr.cursyncup()
        self.scr.noutrefresh()

        # This looks a little odd, but I can't figure a better way to stick the cursor
        # back where it belongs (refreshing the window hides the list_win)

        self.scr.move(*self.scr.getyx())
        self.list_win.refresh()

    def size(self) -> None:
        """Set instance attributes for x and y top left corner coordinates
        and width and height for the window."""
        global stdscr
        if stdscr:
            h, w = stdscr.getmaxyx()
        self.y: int = 0
        self.w: int = w
        self.h: int = h - 1
        self.x: int = 0

    def suspend(self) -> None:
        """Suspend the current process for shell job control."""
        if platform.system() != "Windows":
            curses.endwin()
            os.kill(os.getpid(), signal.SIGSTOP)

    def tab(self, back: bool = False) -> bool:
        """Process the tab key being hit.

        If there's only whitespace
        in the line or the line is blank then process a normal tab,
        otherwise attempt to autocomplete to the best match of possible
        choices in the match list.

        If `back` is True, walk backwards through the list of suggestions
        and don't indent if there are only whitespace in the line.
        """

        # 1. check if we should add a tab character
        if self.atbol() and not back:
            x_pos = len(self.s) - self.cpos
            num_spaces = x_pos % self.config.tab_length
            if not num_spaces:
                num_spaces = self.config.tab_length

            self.addstr(" " * num_spaces)
            self.print_line(self.s)
            return True

        # 2. run complete() if we aren't already iterating through matches
        if not self.matches_iter:
            self.complete(tab=True)
            self.print_line(self.s)

        # 3. check to see if we can expand the current word
        if self.matches_iter.is_cseq():
            # TODO resolve this error-prone situation:
            # can't assign at same time to self.s and self.cursor_offset
            # because for cursor_offset
            # property to work correctly, self.s must already be set
            temp_cursor_offset, self.s = self.matches_iter.substitute_cseq()
            self.cursor_offset = temp_cursor_offset
            self.print_line(self.s)
            if not self.matches_iter:
                self.complete()

        # 4. swap current word for a match list item
        elif self.matches_iter.matches:
            current_match = (
                self.matches_iter.previous()
                if back
                else next(self.matches_iter)
            )
            try:
                f = None
                if self.matches_iter.completer:
                    f = self.matches_iter.completer.format

                self.show_list(
                    self.matches_iter.matches,
                    self.arg_pos,
                    topline=self.funcprops,
                    formatter=f,
                    current_item=current_match,
                )
            except curses.error:
                # XXX: This is a massive hack, it will go away when I get
                # cusswords into a good enough state that we can start
                # using it.
                self.list_win.border()
                self.list_win.refresh()
            _, self.s = self.matches_iter.cur_line()
            self.print_line(self.s, True)
        return True

    def undo(self, n: int = 1) -> None:
        repl.Repl.undo(self, n)

        # This will unhighlight highlighted parens
        self.print_line(self.s)

    def writetb(self, lines: List[str]) -> None:
        for line in lines:
            self.write(
                "\x01{}\x03{}".format(self.config.color_scheme["error"], line)
            )

    def yank_from_buffer(self) -> None:
        """Paste the text from the cut buffer at the current cursor location"""
        self.addstr(self.cut_buffer)
        self.print_line(self.s, clr=True)

    def send_current_line_to_editor(self) -> str:
        lines = self.send_to_external_editor(self.s).split("\n")
        self.s = ""
        self.print_line(self.s)
        while lines and not lines[-1]:
            lines.pop()
        if not lines:
            return ""

        self.f_string = ""
        self.cpos = -1  # Set cursor position to -1 to prevent paren matching

        self.iy, self.ix = self.scr.getyx()
        self.evaluating = True
        for line in lines:
            self.stdout_hist += line + "\n"
            self.history.append(line)
            self.print_line(line)
            self.screen_hist[-1] += self.f_string
            self.scr.addstr("\n")
            self.more = self.push(line)
            self.prompt(self.more)
            self.iy, self.ix = self.scr.getyx()
        self.evaluating = False

        self.cpos = 0
        indent = repl.next_indentation(self.s, self.config.tab_length)
        self.s = ""
        self.scr.refresh()

        if self.buffer:
            for _ in range(indent):
                self.tab()

        self.print_line(self.s)
        self.scr.redrawwin()
        return ""


class Statusbar:
    """This class provides the status bar at the bottom of the screen.
    It has message() and prompt() methods for user interactivity, as
    well as settext() and clear() methods for changing its appearance.

    The check() method needs to be called repeatedly if the statusbar is
    going to be aware of when it should update its display after a message()
    has been called (it'll display for a couple of seconds and then disappear).

    It should be called as:
        foo = Statusbar(stdscr, scr, 'Initial text to display')
    or, for a blank statusbar:
        foo = Statusbar(stdscr, scr)

    It can also receive the argument 'c' which will be an integer referring
    to a curses colour pair, e.g.:
        foo = Statusbar(stdscr, 'Hello', c=4)

    stdscr should be a curses window object in which to put the status bar.
    pwin should be the parent window. To be honest, this is only really here
    so the cursor can be returned to the window properly.

    """

    def __init__(
        self,
        scr: "_CursesWindow",
        pwin: "_CursesWindow",
        background: int,
        config: Config,
        s: Optional[str] = None,
        c: Optional[int] = None,
    ):
        """Initialise the statusbar and display the initial text (if any)"""
        self.size()
        self.win: "_CursesWindow" = newwin(
            background, self.h, self.w, self.y, self.x
        )

        self.config = config

        self.s = s or ""
        self._s = self.s
        self.c = c
        self.timer = 0
        self.pwin = pwin
        if s:
            self.settext(s, c)

    def size(self) -> None:
        """Set instance attributes for x and y top left corner coordinates
        and width and height for the window."""
        h, w = gethw()
        self.y = h - 1
        self.w = w
        self.h = 1
        self.x = 0

    def resize(self, refresh: bool = True) -> None:
        """This method exists simply to keep it straight forward when
        initialising a window and resizing it."""
        self.size()
        self.win.mvwin(self.y, self.x)
        self.win.resize(self.h, self.w)
        if refresh:
            self.refresh()

    def refresh(self) -> None:
        """This is here to make sure the status bar text is redraw properly
        after a resize."""
        self.settext(self._s)

    def check(self) -> None:
        """This is the method that should be called every half second or so
        to see if the status bar needs updating."""
        if not self.timer:
            return

        if time.time() < self.timer:
            return

        self.settext(self._s)

    def message(self, s: str, n: float = 3.0) -> None:
        """Display a message for a short n seconds on the statusbar and return
        it to its original state."""
        self.timer = int(time.time() + n)
        self.settext(s)

    def prompt(self, s: str = "") -> str:
        """Prompt the user for some input (with the optional prompt 's') and
        return the input text, then restore the statusbar to its original
        value."""

        self.settext(s or "? ", p=True)
        iy, ix = self.win.getyx()

        def bs(s: str) -> str:
            y, x = self.win.getyx()
            if x == ix:
                return s
            s = s[:-1]
            self.win.delch(y, x - 1)
            self.win.move(y, x - 1)
            return s

        o = ""
        while True:
            c = self.win.getch()

            # '\b'
            if c == 127:
                o = bs(o)
            # '\n'
            elif c == 10:
                break
            # ESC
            elif c == 27:
                curses.flushinp()
                raise ValueError
            # literal
            elif 0 < c < 127:
                d = chr(c)
                self.win.addstr(d, get_colpair(self.config, "prompt"))
                o += d

        self.settext(self._s)
        return o

    def settext(self, s: str, c: Optional[int] = None, p: bool = False) -> None:
        """Set the text on the status bar to a new permanent value; this is the
        value that will be set after a prompt or message. c is the optional
        curses colour pair to use (if not specified the last specified colour
        pair will be used).  p is True if the cursor is expected to stay in the
        status window (e.g. when prompting)."""

        self.win.erase()
        if len(s) >= self.w:
            s = s[: self.w - 1]

        self.s = s
        if c:
            self.c = c

        if s:
            if self.c:
                self.win.addstr(s, self.c)
            else:
                self.win.addstr(s)

        if not p:
            self.win.noutrefresh()
            self.pwin.refresh()
        else:
            self.win.refresh()

    def clear(self) -> None:
        """Clear the status bar."""
        self.win.clear()


def init_wins(
    scr: "_CursesWindow", config: Config
) -> Tuple["_CursesWindow", Statusbar]:
    """Initialise the two windows (the main repl interface and the little
    status bar at the bottom with some stuff in it)"""
    # TODO: Document better what stuff is on the status bar.

    background = get_colpair(config, "background")
    h, w = gethw()

    main_win = newwin(background, h - 1, w, 0, 0)
    main_win.scrollok(True)

    # I think this is supposed to be True instead of 1?
    main_win.keypad(1)  # type:ignore[arg-type]
    # Thanks to Angus Gibson for pointing out this missing line which was causing
    # problems that needed dirty hackery to fix. :)

    commands = (
        (_("Rewind"), config.undo_key),
        (_("Save"), config.save_key),
        (_("Pastebin"), config.pastebin_key),
        (_("Pager"), config.last_output_key),
        (_("Show Source"), config.show_source_key),
    )

    message = "  ".join(
        f"<{key}> {command}" for command, key in commands if key
    )

    statusbar = Statusbar(
        scr, main_win, background, config, message, get_colpair(config, "main")
    )

    return main_win, statusbar


def sigwinch(unused_scr: "_CursesWindow") -> None:
    global DO_RESIZE
    DO_RESIZE = True


def sigcont(unused_scr: "_CursesWindow") -> None:
    sigwinch(unused_scr)
    # Forces the redraw
    curses.ungetch("\x00")


def gethw() -> Tuple[int, int]:
    """I found this code on a usenet post, and snipped out the bit I needed,
    so thanks to whoever wrote that, sorry I forgot your name, I'm sure you're
    a great guy.

    It's unfortunately necessary (unless someone has any better ideas) in order
    to allow curses and readline to work together. I looked at the code for
    libreadline and noticed this comment:

        /* This is the stuff that is hard for me.  I never seem to write good
           display routines in C.  Let's see how I do this time. */

    So I'm not going to ask any questions.

    """

    if platform.system() != "Windows":
        h, w = struct.unpack(
            "hhhh",
            fcntl.ioctl(
                sys.__stdout__, termios.TIOCGWINSZ, "\000" * 8
            ),  # type:ignore[call-overload]
        )[0:2]
    else:
        # Ignoring mypy's windll error because it's Windows-specific
        from ctypes import (  # type:ignore[attr-defined]
            windll,
            create_string_buffer,
        )

        # stdin handle is -10
        # stdout handle is -11
        # stderr handle is -12

        h = windll.kernel32.GetStdHandle(-12)
        csbi = create_string_buffer(22)
        res = windll.kernel32.GetConsoleScreenBufferInfo(h, csbi)

        if res:
            (
                bufx,
                bufy,
                curx,
                cury,
                wattr,
                left,
                top,
                right,
                bottom,
                maxx,
                maxy,
            ) = struct.unpack("hhhhHhhhhhh", csbi.raw)
            sizex = right - left + 1
            sizey = bottom - top + 1
        elif stdscr:
            # can't determine actual size - return default values
            sizex, sizey = stdscr.getmaxyx()

        h, w = sizey, sizex
    return h, w


def idle(caller: CLIRepl) -> None:
    """This is called once every iteration through the getkey()
    loop (currently in the Repl class, see the get_line() method).
    The statusbar check needs to go here to take care of timed
    messages and the resize handlers need to be here to make
    sure it happens conveniently."""
    global DO_RESIZE

    if caller.module_gatherer.find_coroutine() or caller.paste_mode:
        caller.scr.nodelay(True)
        key = caller.scr.getch()
        caller.scr.nodelay(False)
        if key != -1:
            curses.ungetch(key)
        else:
            curses.ungetch("\x00")
    caller.statusbar.check()
    caller.check()

    if DO_RESIZE:
        do_resize(caller)


def do_resize(caller: CLIRepl) -> None:
    """This needs to hack around readline and curses not playing
    nicely together. See also gethw() above."""
    global DO_RESIZE
    h, w = gethw()
    if not h:
        # Hopefully this shouldn't happen. :)
        return

    curses.endwin()
    os.environ["LINES"] = str(h)
    os.environ["COLUMNS"] = str(w)
    curses.doupdate()
    DO_RESIZE = False

    try:
        caller.resize()
    except curses.error:
        pass
    # The list win resizes itself every time it appears so no need to do it here.


class FakeDict:
    """Very simple dict-alike that returns a constant value for any key -
    used as a hacky solution to using a colours dict containing colour codes if
    colour initialisation fails."""

    def __init__(self, val: int):
        self._val = val

    def __getitem__(self, k: Any) -> int:
        return self._val


def newwin(background: int, *args: int) -> "_CursesWindow":
    """Wrapper for curses.newwin to automatically set background colour on any
    newly created window."""
    win = curses.newwin(*args)
    win.bkgd(" ", background)
    return win


def curses_wrapper(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """Like curses.wrapper(), but reuses stdscr when called again."""
    global stdscr
    if stdscr is None:
        stdscr = curses.initscr()
    try:
        curses.noecho()
        curses.cbreak()
        # Should this be keypad(True)?
        stdscr.keypad(1)  # type:ignore[arg-type]

        try:
            curses.start_color()
        except curses.error:
            pass

        return func(stdscr, *args, **kwargs)
    finally:
        # Should this be keypad(False)?
        stdscr.keypad(0)  # type:ignore[arg-type]
        curses.echo()
        curses.nocbreak()
        curses.endwin()


def main_curses(
    scr: "_CursesWindow",
    args: List[str],
    config: Config,
    interactive: bool = True,
    locals_: Optional[Dict[str, Any]] = None,
    banner: Optional[str] = None,
) -> Tuple[Tuple[Any, ...], str]:
    """main function for the curses convenience wrapper

    Initialise the two main objects: the interpreter
    and the repl. The repl does what a repl does and lots
    of other cool stuff like syntax highlighting and stuff.
    I've tried to keep it well factored but it needs some
    tidying up, especially in separating the curses stuff
    from the rest of the repl.

    Returns a tuple (exit value, output), where exit value is a tuple
    with arguments passed to SystemExit.
    """
    global stdscr
    global DO_RESIZE
    global colors
    DO_RESIZE = False

    if platform.system() != "Windows":
        old_sigwinch_handler = signal.signal(
            signal.SIGWINCH, lambda *_: sigwinch(scr)
        )
        # redraw window after being suspended
        old_sigcont_handler = signal.signal(
            signal.SIGCONT, lambda *_: sigcont(scr)
        )

    stdscr = scr
    try:
        curses.start_color()
        curses.use_default_colors()
        cols = make_colors(config)
    except curses.error:
        # Not sure what to do with the types here...
        # FakeDict acts as a dictionary, but isn't actually a dictionary
        cols = FakeDict(-1)  # type:ignore[assignment]

    # FIXME: Gargh, bad design results in using globals without a refactor :(
    colors = cols

    scr.timeout(300)

    curses.raw(True)
    main_win, statusbar = init_wins(scr, config)

    interpreter = repl.Interpreter(locals_)

    clirepl = CLIRepl(main_win, interpreter, statusbar, config, idle)
    clirepl._C = cols

    # Not sure how to type these Fake types
    sys.stdin = FakeStdin(clirepl)  # type:ignore[assignment]
    sys.stdout = FakeStream(clirepl, lambda: sys.stdout)  # type:ignore
    sys.stderr = FakeStream(clirepl, lambda: sys.stderr)  # type:ignore

    if args:
        exit_value: Tuple[Any, ...] = ()
        try:
            bpargs.exec_code(interpreter, args)
        except SystemExit as e:
            # The documentation of code.InteractiveInterpreter.runcode claims
            # that it reraises SystemExit. However, I can't manage to trigger
            # that. To be one the safe side let's catch SystemExit here anyway.
            exit_value = e.args
        if not interactive:
            curses.raw(False)
            return (exit_value, clirepl.getstdout())
    else:
        sys.path.insert(0, "")
        try:
            clirepl.startup()
        except OSError as e:
            # Handle this with a proper error message.
            if e.errno != errno.ENOENT:
                raise

    if banner is not None:
        clirepl.write(banner)
        clirepl.write("\n")

    # XXX these deprecation warnings need to go at some point
    clirepl.write(
        _(
            "WARNING: You are using `bpython-cli`, the curses backend for `bpython`. This backend has been deprecated in version 0.19 and might disappear in a future version."
        )
    )
    clirepl.write("\n")

    exit_value = clirepl.repl()
    if hasattr(sys, "exitfunc"):
        # Seems like the if statement should satisfy mypy, but it doesn't
        sys.exitfunc()  # type:ignore[attr-defined]
        delattr(sys, "exitfunc")

    main_win.erase()
    main_win.refresh()
    statusbar.win.clear()
    statusbar.win.refresh()
    curses.raw(False)

    # Restore signal handlers
    if platform.system() != "Windows":
        signal.signal(signal.SIGWINCH, old_sigwinch_handler)
        signal.signal(signal.SIGCONT, old_sigcont_handler)

    return (exit_value, clirepl.getstdout())


def main(
    args: Optional[List[str]] = None,
    locals_: Optional[MutableMapping[str, str]] = None,
    banner: Optional[str] = None,
) -> Any:
    translations.init()

    config, options, exec_args = argsparse(args)

    # Save stdin, stdout and stderr for later restoration
    orig_stdin = sys.stdin
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr

    try:
        (exit_value, output) = curses_wrapper(
            main_curses,
            exec_args,
            config,
            options.interactive,
            locals_,
            banner=banner,
        )
    finally:
        sys.stdin = orig_stdin
        sys.stderr = orig_stderr
        sys.stdout = orig_stdout

    # Fake stdout data so everything's still visible after exiting
    if config.flush_output and not options.quiet:
        sys.stdout.write(output)
    if hasattr(sys.stdout, "flush"):
        sys.stdout.flush()
    return repl.extract_exit_value(exit_value)


if __name__ == "__main__":
    sys.exit(main())

# vim: sw=4 ts=4 sts=4 ai et
