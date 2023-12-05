# All windows write only unicode to the terminal -
# that's what blessed does, so we match it.


from typing import (
    ContextManager,
    Optional,
    IO,
    Dict,
    Sequence,
    TypeVar,
    Type,
    Tuple,
    Callable,
    cast,
    TextIO,
    Union,
    List,
)
from types import TracebackType

import logging
import re
import sys

import blessed

from .formatstring import fmtstr, FmtStr
from .formatstringarray import FSArray
from .termhelpers import Cbreak

logger = logging.getLogger(__name__)


T = TypeVar("T", bound="BaseWindow")


class BaseWindow(ContextManager):
    def __init__(
        self, out_stream: Optional[IO] = None, hide_cursor: bool = True
    ) -> None:
        logger.debug("-------initializing Window object %r------" % self)
        if out_stream is None:
            out_stream = sys.__stdout__
        self.t = blessed.Terminal(stream=out_stream, force_styling=True)
        self.out_stream = out_stream
        self.hide_cursor = hide_cursor
        self._last_lines_by_row: Dict[int, Optional[FmtStr]] = {}
        self._last_rendered_width: Optional[int] = None
        self._last_rendered_height: Optional[int] = None

    def scroll_down(self) -> None:
        logger.debug("sending scroll down message w/ cursor on bottom line")

        # since scroll-down only moves the screen if cursor is at bottom
        with self.t.location(x=0, y=1000000):
            self.write(self.t.move_down)

    def write(self, msg: str) -> None:
        self.out_stream.write(msg)
        self.out_stream.flush()

    def __enter__(self: T) -> T:
        logger.debug("running BaseWindow.__enter__")
        if self.hide_cursor:
            self.write(self.t.hide_cursor)
        return self

    def __exit__(
        self,
        type: Optional[Type[BaseException]] = None,
        value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        logger.debug("running BaseWindow.__exit__")
        if self.hide_cursor:
            self.write(self.t.normal_cursor)

    def on_terminal_size_change(self, height: int, width: int) -> None:
        # Changing the terminal size breaks the cache, because it
        # is unknown how the window size change affected scrolling / the cursor
        self._last_lines_by_row = {}
        self._last_rendered_width = width
        self._last_rendered_height = height

    def render_to_terminal(
        self, array: Union[FSArray, List[FmtStr]], cursor_pos: Tuple[int, int] = (0, 0)
    ) -> Optional[int]:
        raise NotImplementedError

    def get_term_hw(self) -> Tuple[int, int]:
        """Returns current terminal height and width"""
        return self.t.height, self.t.width

    @property
    def width(self) -> int:
        "The current width of the terminal window"
        return self.t.width

    @property
    def height(self) -> int:
        "The current width of the terminal window"
        return self.t.height

    def array_from_text(self, msg: str) -> FSArray:
        """Returns a FSArray of the size of the window containing msg"""
        rows, columns = self.t.height, self.t.width
        return self.array_from_text_rc(msg, rows, columns)

    @classmethod
    def array_from_text_rc(cls, msg: str, rows: int, columns: int) -> FSArray:
        arr = FSArray(0, columns)
        i = 0
        for c in msg:
            if i >= rows * columns:
                return arr
            elif c in "\r\n":
                i = ((i // columns) + 1) * columns - 1
            else:
                arr[i // arr.width, i % arr.width] = [fmtstr(c)]
            i += 1
        return arr

    def fmtstr_to_stdout_xform(self) -> Callable[[FmtStr], str]:
        def for_stdout(s: FmtStr) -> str:
            return str(s)

        return for_stdout


class FullscreenWindow(BaseWindow, ContextManager["FullscreenWindow"]):
    """2D-text rendering window that disappears when its context is left

    FullscreenWindow will only render arrays the size of the terminal
    or smaller, and leaves no trace on exit (like top or vim). It never
    scrolls the terminal. Changing the terminal size doesn't do anything,
    but rendered arrays need to fit on the screen.

    Note:
        The context of the FullscreenWindow
        object must be entered before calling any of its methods.

        Within the context of CursorAwareWindow, refrain from writing to
        its out_stream; cached writes will be inaccurate.
    """

    def __init__(
        self, out_stream: Optional[IO] = None, hide_cursor: bool = True
    ) -> None:
        """Constructs a FullscreenWindow

        Args:
            out_stream (file): Defaults to sys.__stdout__
            hide_cursor (bool): Hides cursor while in context
        """
        super().__init__(out_stream=out_stream, hide_cursor=hide_cursor)
        self.fullscreen_ctx = self.t.fullscreen()

    def __enter__(self) -> "FullscreenWindow":
        self.fullscreen_ctx.__enter__()
        return super().__enter__()

    def __exit__(
        self,
        type: Optional[Type[BaseException]] = None,
        value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        self.fullscreen_ctx.__exit__(type, value, traceback)
        super().__exit__(type, value, traceback)

    def render_to_terminal(
        self, array: Union[FSArray, List[FmtStr]], cursor_pos: Tuple[int, int] = (0, 0)
    ) -> None:
        """Renders array to terminal and places (0-indexed) cursor

        Args:
            array (FSArray): Grid of styled characters to be rendered.

        * If array received is of width too small, render it anyway
        * If array received is of width too large,
        * render the renderable portion
        * If array received is of height too small, render it anyway
        * If array received is of height too large,
        * render the renderable portion (no scroll)
        """
        # TODO there's a race condition here - these height and widths are
        # super fresh - they might change between the array being constructed
        # and rendered
        # Maybe the right behavior is to throw away the render
        # in the signal handler?
        height, width = self.height, self.width

        for_stdout = self.fmtstr_to_stdout_xform()
        if not self.hide_cursor:
            self.write(self.t.hide_cursor)
        if height != self._last_rendered_height or width != self._last_rendered_width:
            self.on_terminal_size_change(height, width)

        current_lines_by_row: Dict[int, Optional[FmtStr]] = {}

        # rows which we have content for and don't require scrolling
        for row, line in enumerate(array):
            current_lines_by_row[row] = line
            if line == self._last_lines_by_row.get(row, None):
                continue
            self.write(self.t.move(row, 0))
            self.write(for_stdout(line))
            if len(line) < width:
                self.write(self.t.clear_eol)

        # rows onscreen that we don't have content for
        for row in range(len(array), height):
            if self._last_lines_by_row and row not in self._last_lines_by_row:
                continue
            self.write(self.t.move(row, 0))
            self.write(self.t.clear_eol)
            self.write(self.t.clear_bol)
            current_lines_by_row[row] = None

        logger.debug("lines in last lines by row: %r" % self._last_lines_by_row.keys())
        logger.debug("lines in current lines by row: %r" % current_lines_by_row.keys())
        self.write(self.t.move(*cursor_pos))
        self._last_lines_by_row = current_lines_by_row
        if not self.hide_cursor:
            self.write(self.t.normal_cursor)


class CursorAwareWindow(BaseWindow, ContextManager["CursorAwareWindow"]):
    """
    Renders to the normal terminal screen and
    can find the location of the cursor.

    Note:
        The context of the CursorAwareWindow
        object must be entered before calling any of its methods.

        Within the context of CursorAwareWindow, refrain from writing to
        its out_stream; cached writes will be inaccurate and calculating
        cursor depends on cursor not having moved since the last render.
        Only use the render_to_terminal interface for moving the cursor.
    """

    def __init__(
        self,
        out_stream: Optional[IO] = None,
        in_stream: Optional[IO] = None,
        keep_last_line: bool = False,
        hide_cursor: bool = True,
        extra_bytes_callback: Optional[Callable[[bytes], None]] = None,
    ):
        """Constructs a CursorAwareWindow

        Args:
            out_stream (file): Defaults to sys.__stdout__
            in_stream (file): Defaults to sys.__stdin__
            keep_last_line (bool): Causes the cursor to be moved down one line
                on leaving context
            hide_cursor (bool): Hides cursor while in context
            extra_bytes_callback (f(bytes) -> None): Will be called with extra
                bytes inadvertently read in get_cursor_position(). If not
                provided, a ValueError will be raised when this occurs.
        """
        super().__init__(out_stream=out_stream, hide_cursor=hide_cursor)
        if in_stream is None:
            in_stream = sys.__stdin__
        self.in_stream = in_stream
        # whether we can use blessed to handle some operations
        self._use_blessed = (
            self.out_stream == sys.__stdout__ and self.in_stream == sys.__stdin__
        )
        self._last_cursor_column: Optional[int] = None
        self._last_cursor_row: Optional[int] = None
        self.keep_last_line = keep_last_line
        self.extra_bytes_callback = extra_bytes_callback

        # whether another SIGWINCH is queued up
        self.another_sigwinch = False

        # in the cursor query code of cursor diff
        self.in_get_cursor_diff = False

    def __enter__(self) -> "CursorAwareWindow":
        self.cbreak = (
            Cbreak(self.in_stream) if not self._use_blessed else self.t.cbreak()
        )
        self.cbreak.__enter__()
        self.top_usable_row, _ = self.get_cursor_position()
        self._orig_top_usable_row = self.top_usable_row
        logger.debug("initial top_usable_row: %d" % self.top_usable_row)
        return super().__enter__()

    def __exit__(
        self,
        type: Optional[Type[BaseException]] = None,
        value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        if self.keep_last_line:
            # just moves cursor down if not on last line
            self.write(self.t.move_down)

        self.write(self.t.move_x(0))
        self.write(self.t.clear_eos)
        self.write(self.t.clear_eol)
        self.cbreak.__exit__(type, value, traceback)
        super().__exit__(type, value, traceback)

    def get_cursor_position(self) -> Tuple[int, int]:
        """Returns the terminal (row, column) of the cursor

        0-indexed, like blessed cursor positions"""

        if self._use_blessed:
            return self.t.get_location()

        # TODO would this be cleaner as a parameter?
        in_stream = self.in_stream

        query_cursor_position = "\x1b[6n"
        self.write(query_cursor_position)

        def retrying_read() -> str:
            while True:
                try:
                    c = in_stream.read(1)
                    if c == "":
                        raise ValueError(
                            "Stream should be blocking - shouldn't"
                            " return ''. Returned %r so far",
                            (resp,),
                        )
                    return c
                except OSError:
                    # apparently sometimes this happens: the only documented
                    # case is Terminal on a Ubuntu 17.10 VM on osx 10.13.
                    # see issue #732
                    logger.info("stdin.read(1) that should never error just errored.")
                    continue

        resp = ""
        while True:
            c = retrying_read()
            resp += c
            m = re.search(
                r"(?P<extra>.*)"
                r"(?P<CSI>\x1b\[|\x9b)"
                r"(?P<row>\d+);(?P<column>\d+)R",
                resp,
                re.DOTALL,
            )
            if m:
                row = int(m.groupdict()["row"])
                col = int(m.groupdict()["column"])
                extra = m.groupdict()["extra"]
                if extra:
                    if self.extra_bytes_callback is not None:
                        self.extra_bytes_callback(
                            # TODO how do we know that this works?
                            extra.encode(cast(TextIO, in_stream).encoding)
                        )
                    else:
                        raise ValueError(
                            (
                                "Bytes preceding cursor position "
                                "query response thrown out:\n%r\n"
                                "Pass an extra_bytes_callback to "
                                "CursorAwareWindow to prevent this"
                            )
                            % (extra,)
                        )
                return (row - 1, col - 1)

    def get_cursor_vertical_diff(self) -> int:
        """Returns the how far down the cursor moved since last render.

        Note:
            If another get_cursor_vertical_diff call is already in progress,
            immediately returns zero. (This situation is likely if
            get_cursor_vertical_diff is called from a SIGWINCH signal
            handler, since sigwinches can happen in rapid succession and
            terminal emulators seem not to respond to cursor position
            queries before the next sigwinch occurs.)
        """
        # Probably called by a SIGWINCH handler, and therefore
        # will do cursor querying until a SIGWINCH doesn't happen during
        # the query. Calls to the function from a signal handler COULD STILL
        # HAPPEN out of order -
        # they just can't interrupt the actual cursor query.
        if self.in_get_cursor_diff:
            self.another_sigwinch = True
            return 0

        cursor_dy = 0
        while True:
            self.in_get_cursor_diff = True
            self.another_sigwinch = False
            cursor_dy += self._get_cursor_vertical_diff_once()
            self.in_get_cursor_diff = False
            if not self.another_sigwinch:
                return cursor_dy

    def _get_cursor_vertical_diff_once(self) -> int:
        """Returns the how far down the cursor moved."""
        old_top_usable_row = self.top_usable_row
        row, col = self.get_cursor_position()
        if self._last_cursor_row is None:
            cursor_dy = 0
        else:
            cursor_dy = row - self._last_cursor_row
            logger.info("cursor moved %d lines down" % cursor_dy)
            while self.top_usable_row > -1 and cursor_dy > 0:
                self.top_usable_row += 1
                cursor_dy -= 1
            while self.top_usable_row > 1 and cursor_dy < 0:
                self.top_usable_row -= 1
                cursor_dy += 1
        logger.info(
            "top usable row changed from %d to %d",
            old_top_usable_row,
            self.top_usable_row,
        )
        logger.info("returning cursor dy of %d from curtsies" % cursor_dy)
        self._last_cursor_row = row
        return cursor_dy

    def render_to_terminal(
        self,
        array: Union[FSArray, Sequence[FmtStr]],
        cursor_pos: Tuple[int, int] = (0, 0),
    ) -> int:
        """Renders array to terminal, returns the number of lines scrolled offscreen

        Returns:
            Number of times scrolled

        Args:
          array (FSArray): Grid of styled characters to be rendered.

            If array received is of width too small, render it anyway

            if array received is of width too large, render it anyway

            if array received is of height too small, render it anyway

            if array received is of height too large, render it, scroll down,
            and render the rest of it, then return how much we scrolled down

        """
        for_stdout = self.fmtstr_to_stdout_xform()
        # caching of write and tc (avoiding the self. lookups etc) made
        # no significant performance difference here
        if not self.hide_cursor:
            self.write(self.t.hide_cursor)

        # TODO race condition here?
        height, width = self.t.height, self.t.width
        if height != self._last_rendered_height or width != self._last_rendered_width:
            self.on_terminal_size_change(height, width)

        current_lines_by_row: Dict[int, Optional[FmtStr]] = {}
        rows_for_use = list(range(self.top_usable_row, height))

        # rows which we have content for and don't require scrolling
        # TODO rename shared
        shared = min(len(array), len(rows_for_use))
        for row, line in zip(rows_for_use[:shared], array[:shared]):
            current_lines_by_row[row] = line
            if line == self._last_lines_by_row.get(row, None):
                continue
            self.write(self.t.move(row, 0))
            self.write(for_stdout(line))
            if len(line) < width:
                self.write(self.t.clear_eol)

        # rows already on screen that we don't have content for
        rest_of_lines = array[shared:]
        rest_of_rows = rows_for_use[shared:]
        for row in rest_of_rows:  # if array too small
            if self._last_lines_by_row and row not in self._last_lines_by_row:
                continue
            self.write(self.t.move(row, 0))
            self.write(self.t.clear_eol)
            # TODO probably not necessary - is first char cleared?
            self.write(self.t.clear_bol)
            current_lines_by_row[row] = None

        # lines for which we need to scroll down to render
        offscreen_scrolls = 0
        for line in rest_of_lines:  # if array too big
            self.scroll_down()
            if self.top_usable_row > 0:
                self.top_usable_row -= 1
            else:
                offscreen_scrolls += 1
            current_lines_by_row = {k - 1: v for k, v in current_lines_by_row.items()}
            logger.debug("new top_usable_row: %d" % self.top_usable_row)
            # since scrolling moves the cursor
            self.write(self.t.move(height - 1, 0))
            self.write(for_stdout(line))
            current_lines_by_row[height - 1] = line

        logger.debug("lines in last lines by row: %r" % self._last_lines_by_row.keys())
        logger.debug("lines in current lines by row: %r" % current_lines_by_row.keys())
        self._last_cursor_row = max(
            0, cursor_pos[0] - offscreen_scrolls + self.top_usable_row
        )
        self._last_cursor_column = cursor_pos[1]
        self.write(self.t.move(self._last_cursor_row, self._last_cursor_column))
        self._last_lines_by_row = current_lines_by_row
        if not self.hide_cursor:
            self.write(self.t.normal_cursor)
        return offscreen_scrolls


def demo() -> None:
    handler = logging.FileHandler(filename="display.log")
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    logging.getLogger(__name__).addHandler(handler)
    from . import input

    with FullscreenWindow(sys.stdout) as w:
        with input.Input(sys.stdin) as input_generator:
            rows, columns = w.t.height, w.t.width
            for c in input_generator:
                assert isinstance(c, str)
                if c == "":
                    sys.exit()  # same as raise SystemExit()
                elif c == "h":
                    a: Union[List[FmtStr], FSArray] = w.array_from_text(
                        "a for small array"
                    )
                elif c == "a":
                    a = [fmtstr(c * columns) for _ in range(rows)]
                elif c == "s":
                    a = [fmtstr(c * columns) for _ in range(rows - 1)]
                elif c == "d":
                    a = [fmtstr(c * columns) for _ in range(rows + 1)]
                elif c == "f":
                    a = [fmtstr(c * columns) for _ in range(rows - 2)]
                elif c == "q":
                    a = [fmtstr(c * columns) for _ in range(1)]
                elif c == "w":
                    a = [fmtstr(c * columns) for _ in range(1)]
                elif c == "e":
                    a = [fmtstr(c * columns) for _ in range(1)]
                elif c == "\x0c":  # ctrl-L
                    for _ in range(rows):
                        w.write("\n")
                    continue
                else:
                    a = w.array_from_text("unknown command")
                w.render_to_terminal(a)


def main() -> None:
    handler = logging.FileHandler(filename="display.log")
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    logging.getLogger(__name__).addHandler(handler)
    print("this should be just off-screen")
    w = FullscreenWindow(sys.stdout)
    rows, columns = w.t.height, w.t.width
    with w:
        a = [fmtstr(((f".row{row!r}.") * rows)[:columns]) for row in range(rows)]
        w.render_to_terminal(a)


if __name__ == "__main__":
    demo()
