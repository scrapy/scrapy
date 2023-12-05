r"""Colored strings that behave mostly like strings

>>> s = fmtstr("Hey there!", 'red')
>>> s
red('Hey there!')
>>> s[4:7]
red('the')
>>> red_on_blue = fmtstr('hello', 'red', 'on_blue')
>>> blue_on_red = fmtstr('there', fg='blue', bg='red')
>>> green = fmtstr('!', 'green')
>>> full = red_on_blue + ' ' + blue_on_red + green
>>> full
on_blue(red('hello'))+' '+on_red(blue('there'))+green('!')
>>> str(full)
'\x1b[31m\x1b[44mhello\x1b[49m\x1b[39m \x1b[34m\x1b[41mthere\x1b[49m\x1b[39m\x1b[32m!\x1b[39m'
>>> fmtstr(', ').join(['a', fmtstr('b'), fmtstr('c', 'blue')])
'a'+', '+'b'+', '+blue('c')
>>> fmtstr(u'hello', u'red', bold=False)
red('hello')
"""

import re
from cwcwidth import wcswidth, wcwidth
from itertools import chain
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    Union,
    cast,
    no_type_check,
)

try:
    from functools import cached_property
except ImportError:
    from backports.cached_property import cached_property  # type: ignore

from .escseqparse import parse, remove_ansi
from .termformatconstants import (
    FG_COLORS,
    BG_COLORS,
    STYLES,
    FG_NUMBER_TO_COLOR,
    BG_NUMBER_TO_COLOR,
    RESET_ALL,
    RESET_BG,
    RESET_FG,
    seq,
)

one_arg_xforms: Mapping[str, Callable[[str], str]] = {
    "bold": lambda s: seq(STYLES["bold"]) + s + seq(RESET_ALL),
    "dark": lambda s: seq(STYLES["dark"]) + s + seq(RESET_ALL),
    "underline": lambda s: seq(STYLES["underline"]) + s + seq(RESET_ALL),
    "blink": lambda s: seq(STYLES["blink"]) + s + seq(RESET_ALL),
    "invert": lambda s: seq(STYLES["invert"]) + s + seq(RESET_ALL),
}

two_arg_xforms: Mapping[str, Callable[[str, int], str]] = {
    "fg": lambda s, v: "{}{}{}".format(seq(v), s, seq(RESET_FG)),
    "bg": lambda s, v: seq(v) + s + seq(RESET_BG),
}


class FrozenAttributes(Dict[str, Union[int, bool]]):
    """Immutable dictionary class for format string attributes"""

    def __setitem__(self, key: str, value: Union[int, bool]) -> None:
        raise Exception("Cannot change value.")

    def update(self, *args: Any, **kwds: Any) -> None:
        raise Exception("Cannot change value.")

    def extend(self, dictlike: Mapping[str, Union[int, bool]]) -> "FrozenAttributes":
        return FrozenAttributes(chain(self.items(), dictlike.items()))

    def remove(self, *keys: str) -> "FrozenAttributes":
        return FrozenAttributes((k, v) for k, v in self.items() if k not in keys)


def stable_format_dict(d: Mapping) -> str:
    """A sorted, python2/3 stable formatting of a dictionary.

    Does not work for dicts with unicode strings as values."""
    inner = ", ".join(
        "{}: {}".format(
            repr(k)[1:]
            if repr(k).startswith("u'") or repr(k).startswith('u"')
            else repr(k),
            v,
        )
        for k, v in sorted(d.items())
    )
    return "{%s}" % inner


class Chunk:
    """A string with a single set of formatting attributes

    Subject to change, not part of the API"""

    def __init__(
        self, string: str, atts: Optional[Mapping[str, Union[int, bool]]] = None
    ):
        if not isinstance(string, str):
            raise ValueError("unicode string required, got %r" % string)
        self._s = string
        self._atts = FrozenAttributes(atts if atts else {})

    @property
    def s(self) -> str:
        return self._s

    @property
    def atts(self) -> FrozenAttributes:
        "Attributes, e.g. {'fg': 34, 'bold': True} where 34 is the escape code for ..."
        return self._atts

    def __len__(self) -> int:
        return len(self._s)

    @property
    def width(self) -> int:
        width = wcswidth(self._s)
        if len(self._s) > 0 and width < 1:
            raise ValueError("Can't calculate width of string %r" % self._s)
        return width

    @cached_property
    def color_str(self) -> str:
        "Return an escape-coded string to write to the terminal."
        s = self._s
        for k, v in sorted(self._atts.items()):
            # (self.atts sorted for the sake of always acting the same.)
            if k not in one_arg_xforms and k not in two_arg_xforms:
                # Unsupported SGR code
                continue
            elif v is False:
                continue
            elif k in one_arg_xforms:
                s = one_arg_xforms[k](s)
            else:
                s = two_arg_xforms[k](s, v)
        return s

    def __str__(self) -> str:
        value = self.color_str
        if isinstance(value, bytes):
            return value.decode("utf8", "replace")
        return value

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Chunk):
            return NotImplemented
        return self._s == other._s and self._atts == other._atts

    def __hash__(self) -> int:
        return hash((self._s, self._atts))

    def __repr__(self) -> str:
        return "Chunk({s}{sep}{atts})".format(
            s=repr(self._s),
            sep=", " if self._atts else "",
            atts=stable_format_dict(self._atts) if self._atts else "",
        )

    def repr_part(self) -> str:
        """FmtStr repr is build by concatenating these."""

        def pp_att(att: str) -> str:
            if att == "fg":
                return FG_NUMBER_TO_COLOR[self.atts[att]]
            elif att == "bg":
                return "on_" + BG_NUMBER_TO_COLOR[self.atts[att]]
            else:
                return att

        atts_out = {k: v for (k, v) in self._atts.items() if v}
        return (
            "".join(pp_att(att) + "(" for att in sorted(atts_out))
            + repr(self._s)
            + ")" * len(atts_out)
        )

    def splitter(self) -> "ChunkSplitter":
        """
        Returns a view of this Chunk from which new Chunks can be requested.
        """
        return ChunkSplitter(self)


class ChunkSplitter:
    """
    View of a Chunk for breaking it into smaller Chunks.
    """

    def __init__(self, chunk: Chunk) -> None:
        self.reinit(chunk)

    def reinit(self, chunk: Chunk) -> None:
        """Reuse an existing Splitter instance for speed."""
        # TODO benchmark to prove this is worthwhile
        self.chunk = chunk
        self.internal_offset = 0  # index into chunk.s
        self.internal_width = 0  # width of chunks.s[:self.internal_offset]
        divides = [0]
        for c in self.chunk.s:
            divides.append(divides[-1] + wcwidth(c))
        self.divides = divides

    def request(self, max_width: int) -> Optional[Tuple[int, Chunk]]:
        """Requests a sub-chunk of max_width or shorter. Returns None if no chunks left."""
        if max_width < 1:
            raise ValueError("requires positive integer max_width")

        s = self.chunk.s
        length = len(s)

        if self.internal_offset == len(s):
            return None

        width = 0
        start_offset = i = self.internal_offset
        replacement_char = " "

        while True:
            w = wcswidth(s[i], None)

            # If adding a character puts us over the requested width, return what we've got so far
            if width + w > max_width:
                self.internal_offset = i  # does not include ith character
                self.internal_width += width

                # if not adding it us makes us short, this must have been a double-width character
                if width < max_width:
                    assert (
                        width + 1 == max_width
                    ), "unicode character width of more than 2!?!"
                    assert w == 2, "unicode character of width other than 2?"
                    return (
                        width + 1,
                        Chunk(
                            s[start_offset : self.internal_offset] + replacement_char,
                            atts=self.chunk.atts,
                        ),
                    )
                return (
                    width,
                    Chunk(s[start_offset : self.internal_offset], atts=self.chunk.atts),
                )
            # otherwise add this width
            width += w

            # If one more char would put us over, return whatever we've got
            if i + 1 == length:
                self.internal_offset = (
                    i + 1
                )  # beware the fencepost, i is an index not an offset
                self.internal_width += width
                return (
                    width,
                    Chunk(s[start_offset : self.internal_offset], atts=self.chunk.atts),
                )
            # otherwise attempt to add the next character
            i += 1


class FmtStr:
    """A string whose substrings carry attributes."""

    def __init__(self, *components: Chunk) -> None:
        # These assertions below could be useful for debugging, but slow things down considerably
        # assert all([len(x) > 0 for x in components])
        # self.chunks = [x for x in components if len(x) > 0]
        self.chunks = list(components)

        # caching these leads to a significant speedup
        self._unicode: Optional[str] = None
        self._len: Optional[int] = None
        self._s: Optional[str] = None
        self._width: Optional[int] = None

    @staticmethod
    def from_str(s: str) -> "FmtStr":
        r"""
        Return a FmtStr representing input.

        The str() of a FmtStr is guaranteed to produced the same FmtStr.
        Other input with escape sequences may not be preserved.

        >>> fmtstr("|"+fmtstr("hey", fg='red', bg='blue')+"|")
        '|'+on_blue(red('hey'))+'|'
        >>> fmtstr('|\x1b[31m\x1b[44mhey\x1b[49m\x1b[39m|')
        '|'+on_blue(red('hey'))+'|'
        """

        if "\x1b[" in s:
            try:
                tokens_and_strings = parse(s)
            except ValueError:
                return FmtStr(Chunk(remove_ansi(s)))
            else:
                chunks = []
                cur_fmt = {}
                for x in tokens_and_strings:
                    if isinstance(x, dict):
                        cur_fmt.update(x)
                    elif isinstance(x, str):
                        atts = parse_args(
                            (), {k: v for k, v in cur_fmt.items() if v is not None}
                        )
                        chunks.append(Chunk(x, atts=atts))
                    else:
                        raise TypeError(f"Expected dict or str, not {type(x)}")
                return FmtStr(*chunks)
        else:
            return FmtStr(Chunk(s))

    def copy_with_new_str(self, new_str: str) -> "FmtStr":
        """Copies the current FmtStr's attributes while changing its string."""
        # What to do when there are multiple Chunks with conflicting atts?
        old_atts = {
            att: value for bfs in self.chunks for (att, value) in bfs.atts.items()
        }
        return FmtStr(Chunk(new_str, old_atts))

    def setitem(self, startindex: int, fs: Union[str, "FmtStr"]) -> "FmtStr":
        """Shim for easily converting old __setitem__ calls"""
        return self.setslice_with_length(startindex, startindex + 1, fs, len(self))

    def setslice_with_length(
        self, startindex: int, endindex: int, fs: Union[str, "FmtStr"], length: int
    ) -> "FmtStr":
        """Shim for easily converting old __setitem__ calls"""
        if len(self) < startindex:
            fs = " " * (startindex - len(self)) + fs
        if len(self) > endindex:
            fs = fs + " " * (endindex - startindex - len(fs))
            assert len(fs) == endindex - startindex, (len(fs), startindex, endindex)
        result = self.splice(fs, startindex, endindex)
        if len(result) > length:
            raise ValueError(
                "Your change is resulting in a longer fmtstr than the original length and this is not supported."
            )
        return result

    def splice(
        self, new_str: Union[str, "FmtStr"], start: int, end: Optional[int] = None
    ) -> "FmtStr":
        """Returns a new FmtStr with the input string spliced into the
        the original FmtStr at start and end.
        If end is provided, new_str will replace the substring self.s[start:end-1].
        """
        if len(new_str) == 0:
            return self
        new_fs = new_str if isinstance(new_str, FmtStr) else fmtstr(new_str)
        assert len(new_fs.chunks) > 0, (new_fs.chunks, new_fs)
        new_components = []
        inserted = False
        if end is None:
            end = start
        tail = None

        for bfs, bfs_start, bfs_end in zip(
            self.chunks, self.divides[:-1], self.divides[1:]
        ):
            if end == bfs_start == 0:
                new_components.extend(new_fs.chunks)
                new_components.append(bfs)
                inserted = True

            elif bfs_start <= start < bfs_end:
                divide = start - bfs_start
                head = Chunk(bfs.s[:divide], atts=bfs.atts)
                tail = Chunk(bfs.s[end - bfs_start :], atts=bfs.atts)
                new_components.extend([head] + new_fs.chunks)
                inserted = True

                if bfs_start < end < bfs_end:
                    tail = Chunk(bfs.s[end - bfs_start :], atts=bfs.atts)
                    new_components.append(tail)

            elif bfs_start < end < bfs_end:
                divide = start - bfs_start
                tail = Chunk(bfs.s[end - bfs_start :], atts=bfs.atts)
                new_components.append(tail)

            elif bfs_start >= end or bfs_end <= start:
                new_components.append(bfs)

        if not inserted:
            new_components.extend(new_fs.chunks)
            inserted = True

        return FmtStr(*(s for s in new_components if s.s))

    def append(self, string: Union[str, "FmtStr"]) -> "FmtStr":
        return self.splice(string, len(self.s))

    def copy_with_new_atts(self, **attributes: Union[bool, int]) -> "FmtStr":
        """Returns a new FmtStr with the same content but new formatting"""

        return FmtStr(
            *(Chunk(bfs.s, bfs.atts.extend(attributes)) for bfs in self.chunks)
        )

    def join(self, iterable: Iterable[Union[str, "FmtStr"]]) -> "FmtStr":
        """Joins an iterable yielding strings or FmtStrs with self as separator"""
        before: List[Chunk] = []
        chunks: List[Chunk] = []
        for s in iterable:
            chunks.extend(before)
            before = self.chunks
            if isinstance(s, FmtStr):
                chunks.extend(s.chunks)
            elif isinstance(s, (bytes, str)):
                chunks.extend(fmtstr(s).chunks)  # TODO just make a chunk directly
            else:
                raise TypeError("expected str or FmtStr, %r found" % type(s))
        return FmtStr(*chunks)

    # TODO make this split work like str.split
    def split(
        self,
        sep: Optional[str] = None,
        maxsplit: Optional[int] = None,
        regex: bool = False,
    ) -> List["FmtStr"]:
        """Split based on separator, optionally using a regex.

        Capture groups are ignored in regex, the whole pattern is matched
        and used to split the original FmtStr."""
        if maxsplit is not None:
            raise NotImplementedError("no maxsplit yet")
        s = self.s
        if sep is None:
            sep = r"\s+"
        elif not regex:
            sep = re.escape(sep)
        matches = list(re.finditer(sep, s))
        return [
            self[start:end]
            for start, end in zip(
                chain((0,), (m.end() for m in matches)),
                chain((m.start() for m in matches), (len(s),)),
            )
        ]

    def splitlines(self, keepends: bool = False) -> List["FmtStr"]:
        """Return a list of lines, split on newline characters,
        include line boundaries, if keepends is true."""
        lines = self.split("\n")
        return (
            [line + "\n" for line in lines]
            if keepends
            else (lines if lines[-1] else lines[:-1])
        )

    # proxying to the string via __getattr__ is insufficient
    # because we shouldn't drop foreground or formatting info
    def ljust(self, width: int, fillchar: Optional[str] = None) -> "FmtStr":
        """S.ljust(width[, fillchar]) -> string

        If a fillchar is provided, less formatting information will be preserved
        """
        if fillchar is not None:
            return fmtstr(self.s.ljust(width, fillchar), **self.shared_atts)
        to_add = " " * (width - len(self.s))
        shared = self.shared_atts
        if "bg" in shared:
            return self + fmtstr(to_add, bg=shared["bg"]) if to_add else self
        else:
            uniform = self.new_with_atts_removed("bg")
            return uniform + fmtstr(to_add, **self.shared_atts) if to_add else uniform

    def rjust(self, width: int, fillchar: Optional[str] = None) -> "FmtStr":
        """S.rjust(width[, fillchar]) -> string

        If a fillchar is provided, less formatting information will be preserved
        """
        if fillchar is not None:
            return fmtstr(self.s.rjust(width, fillchar), **self.shared_atts)
        to_add = " " * (width - len(self.s))
        shared = self.shared_atts
        if "bg" in shared:
            return fmtstr(to_add, bg=shared["bg"]) + self if to_add else self
        else:
            uniform = self.new_with_atts_removed("bg")
            return fmtstr(to_add, **self.shared_atts) + uniform if to_add else uniform

    def __str__(self) -> str:
        if self._unicode is not None:
            return self._unicode
        self._unicode = "".join(str(fs) for fs in self.chunks)
        return self._unicode

    def __len__(self) -> int:
        if self._len is not None:
            return self._len
        value = sum(len(fs) for fs in self.chunks)
        self._len = value
        return value

    @property
    def width(self) -> int:
        """The number of columns it would take to display this string."""
        if self._width is not None:
            return self._width
        value = sum(fs.width for fs in self.chunks)
        self._width = value
        return value

    def width_at_offset(self, n: int) -> int:
        """Returns the horizontal position of character n of the string"""
        # TODO make more efficient?
        width = wcswidth(self.s, n)
        assert width != -1
        return width

    def __repr__(self) -> str:
        return "+".join(fs.repr_part() for fs in self.chunks)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, (str, bytes, FmtStr)):
            return str(self) == str(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(str(self))

    def __add__(self, other: Union["FmtStr", str]) -> "FmtStr":
        if isinstance(other, FmtStr):
            return FmtStr(*(self.chunks + other.chunks))
        elif isinstance(other, (bytes, str)):
            return FmtStr(*(self.chunks + [Chunk(other)]))

        return NotImplemented

    def __radd__(self, other: Union["FmtStr", str]) -> "FmtStr":
        if isinstance(other, FmtStr):
            return FmtStr(*(x for x in (other.chunks + self.chunks)))
        elif isinstance(other, (bytes, str)):
            return FmtStr(*(x for x in ([Chunk(other)] + self.chunks)))

        return NotImplemented

    def __mul__(self, other: int) -> "FmtStr":
        if isinstance(other, int):
            return sum((self for _ in range(other)), FmtStr())

        return NotImplemented

    # TODO ensure empty FmtStr isn't a problem

    @property
    def shared_atts(self) -> Dict[str, Union[int, bool]]:
        """Gets atts shared among all nonzero length component Chunks"""
        # TODO cache this, could get ugly for large FmtStrs
        atts = {}
        first = self.chunks[0]
        for att in sorted(first.atts):
            # TODO how to write this without the '???'?
            if all(
                fs.atts.get(att, "???") == first.atts[att]
                for fs in self.chunks
                if len(fs) > 0
            ):
                atts[att] = first.atts[att]
        return atts

    def new_with_atts_removed(self, *attributes: str) -> "FmtStr":
        """Returns a new FmtStr with the same content but some attributes removed"""

        result = FmtStr(*(Chunk(bfs.s, bfs.atts.remove(*attributes)) for bfs in self.chunks))  # type: ignore
        return result

    @no_type_check
    def __getattr__(self, att):
        # thanks to @aerenchyma/@jczett
        if not hasattr(self.s, att):
            raise AttributeError(f"No attribute {att!r}")

        @no_type_check
        def func_help(*args, **kwargs):
            result = getattr(self.s, att)(*args, **kwargs)
            if isinstance(result, (bytes, str)):
                return fmtstr(result, **self.shared_atts)
            elif isinstance(result, list):
                return [fmtstr(x, **self.shared_atts) for x in result]
            else:
                return result

        return func_help

    @property
    def divides(self) -> List[int]:
        """List of indices of divisions between the constituent chunks."""
        acc = [0]
        for s in self.chunks:
            acc.append(acc[-1] + len(s))
        return acc

    @property
    def s(self) -> str:
        if self._s is not None:
            return self._s
        self._s = "".join(fs.s for fs in self.chunks)
        return self._s

    def __getitem__(self, index: Union[int, slice]) -> "FmtStr":
        index = normalize_slice(len(self), index)
        counter = 0
        parts = []
        for chunk in self.chunks:
            if index.start < counter + len(chunk) and index.stop > counter:
                start = max(0, index.start - counter)
                end = min(index.stop - counter, len(chunk))
                if end - start == len(chunk):
                    parts.append(chunk)
                else:
                    s_part = chunk.s[
                        max(0, index.start - counter) : index.stop - counter
                    ]
                    parts.append(Chunk(s_part, chunk.atts))
            counter += len(chunk)
            if index.stop < counter:
                break
        return FmtStr(*parts) if parts else fmtstr("")

    def width_aware_slice(self, index: Union[int, slice]) -> "FmtStr":
        """Slice based on the number of columns it would take to display the substring."""
        if wcswidth(self.s, None) == -1:
            raise ValueError("bad values for width aware slicing")
        index = normalize_slice(self.width, index)
        counter = 0
        parts = []
        for chunk in self.chunks:
            if index.start < counter + chunk.width and index.stop > counter:
                start = max(0, index.start - counter)
                end = min(index.stop - counter, chunk.width)
                if end - start == chunk.width:
                    parts.append(chunk)
                else:
                    s_part = width_aware_slice(
                        chunk.s, max(0, index.start - counter), index.stop - counter
                    )
                    parts.append(Chunk(s_part, chunk.atts))
            counter += chunk.width
            if index.stop < counter:
                break
        return FmtStr(*parts) if parts else fmtstr("")

    def width_aware_splitlines(self, columns: int) -> Iterator["FmtStr"]:
        """Split into lines, pushing doublewidth characters at the end of a line to the next line.

        When a double-width character is pushed to the next line, a space is added to pad out the line.
        """
        if columns < 2:
            raise ValueError("Column width %s is too narrow." % columns)
        if wcswidth(self.s, None) == -1:
            raise ValueError("bad values for width aware slicing")
        return self._width_aware_splitlines(columns)

    def _width_aware_splitlines(self, columns: int) -> Iterator["FmtStr"]:
        splitter = self.chunks[0].splitter()
        chunks_of_line = []
        width_of_line = 0
        for source_chunk in self.chunks:
            splitter.reinit(source_chunk)
            while True:
                request = splitter.request(columns - width_of_line)
                if request is None:
                    break  # done with this source_chunk
                w, new_chunk = request
                chunks_of_line.append(new_chunk)
                width_of_line += w

                if width_of_line == columns:
                    yield FmtStr(*chunks_of_line)
                    del chunks_of_line[:]
                    width_of_line = 0

        if chunks_of_line:
            yield FmtStr(*chunks_of_line)

    def _getitem_normalized(self, index: Union[int, slice]) -> "FmtStr":
        """Builds the more compact fmtstrs by using fromstr( of the control sequences)"""
        index = normalize_slice(len(self), index)
        counter = 0
        output = ""
        for fs in self.chunks:
            if index.start < counter + len(fs) and index.stop > counter:
                s_part = fs.s[max(0, index.start - counter) : index.stop - counter]
                piece = Chunk(s_part, fs.atts).color_str
                output += piece
            counter += len(fs)
            if index.stop < counter:
                break
        return fmtstr(output)

    def __setitem__(self, index: int, value: Any) -> None:
        raise Exception("No!")

    def copy(self) -> "FmtStr":
        return FmtStr(*self.chunks)


def interval_overlap(a: int, b: int, x: int, y: int) -> int:
    """Returns by how much two intervals overlap

    assumed that a <= b and x <= y"""
    if b <= x or a >= y:
        return 0
    elif x <= a <= y:
        return min(b, y) - a
    elif x <= b <= y:
        return b - max(a, x)
    elif a >= x and b <= y:
        return b - a
    else:
        assert False


def width_aware_slice(s: str, start: int, end: int, replacement_char: str = " ") -> str:
    """
    >>> width_aware_slice(u'a\uff25iou', 0, 2)[1] == u' '
    True
    """
    divides = [0]
    for c in s:
        divides.append(divides[-1] + wcwidth(c))

    new_chunk_chars = []
    for char, char_start, char_end in zip(s, divides[:-1], divides[1:]):
        if char_start == start and char_end == start:
            continue  # don't use zero-width characters at the beginning of a slice
            # (combining characters combine with the chars before themselves)
        elif char_start >= start and char_end <= end:
            new_chunk_chars.append(char)
        else:
            new_chunk_chars.extend(
                replacement_char * interval_overlap(char_start, char_end, start, end)
            )

    return "".join(new_chunk_chars)


def linesplit(string: Union[str, FmtStr], columns: int) -> List[FmtStr]:
    """Returns a list of lines, split on the last possible space of each line.

    Split spaces will be removed. Whitespaces will be normalized to one space.
    Spaces will be the color of the first whitespace character of the
    normalized whitespace.
    If a word extends beyond the line, wrap it anyway.

    >>> linesplit(fmtstr(" home    is where the heart-eating mummy is", 'blue'), 10)
    [blue('home')+blue(' ')+blue('is'), blue('where')+blue(' ')+blue('the'), blue('heart-eati'), blue('ng')+blue(' ')+blue('mummy'), blue('is')]
    """
    if not isinstance(string, FmtStr):
        string = fmtstr(string)

    string_s = string.s
    matches = list(re.finditer(r"\s+", string_s))
    spaces = [
        string[m.start() : m.end()]
        for m in matches
        if m.start() != 0 and m.end() != len(string_s)
    ]
    words = [
        string[start:end]
        for start, end in zip(
            [0] + [m.end() for m in matches],
            [m.start() for m in matches] + [len(string_s)],
        )
        if start != end
    ]

    word_to_lines = lambda word: [
        word[columns * i : columns * (i + 1)]
        for i in range((len(word) - 1) // columns + 1)
    ]

    lines = word_to_lines(words[0])
    for word, space in zip(words[1:], spaces):
        if len(lines[-1]) + len(word) < columns:
            lines[-1] += fmtstr(" ", **space.shared_atts)
            lines[-1] += word
        else:
            lines.extend(word_to_lines(word))
    return lines


def normalize_slice(length: int, index: Union[int, slice]) -> slice:
    "Fill in the Nones in a slice."
    is_int = False
    if isinstance(index, int):
        is_int = True
        index = slice(index, index + 1)
    if index.start is None:
        index = slice(0, index.stop, index.step)
    if index.stop is None:
        index = slice(index.start, length, index.step)
    if index.start < -1:  # XXX why must this be -1?
        index = slice(length - index.start, index.stop, index.step)
    if index.stop < -1:  # XXX why must this be -1?
        index = slice(index.start, length - index.stop, index.step)
    if index.step is not None:
        raise NotImplementedError("You can't use steps with slicing yet")
    if is_int:
        if index.start < 0 or index.start > length:
            raise IndexError(f"index out of bounds: {index!r} for length {length}")
    return index


def parse_args(
    args: Tuple[str, ...],
    kwargs: MutableMapping[str, Union[int, bool, str]],
) -> Mapping[str, Union[int, bool]]:
    """Returns a kwargs dictionary by turning args into kwargs"""
    if "style" in kwargs:
        args += (cast(str, kwargs["style"]),)
        del kwargs["style"]
    for arg in args:
        if not isinstance(arg, str):
            raise ValueError(f"args must be strings: {arg!r}")
        if arg.lower() in FG_COLORS:
            if "fg" in kwargs:
                raise ValueError("fg specified twice")
            kwargs["fg"] = FG_COLORS[cast(str, arg)]
        elif arg.lower().startswith("on_") and arg[3:].lower() in BG_COLORS:
            if "bg" in kwargs:
                raise ValueError("fg specified twice")
            kwargs["bg"] = BG_COLORS[cast(str, arg[3:])]
        elif arg.lower() in STYLES:
            kwargs[arg] = True
        else:
            raise ValueError(f"couldn't process arg: {args!r}")
    for k in kwargs:
        if k not in ("fg", "bg") and k not in STYLES.keys():
            raise ValueError("Can't apply that transformation")
    if "fg" in kwargs:
        if kwargs["fg"] in FG_COLORS:
            kwargs["fg"] = FG_COLORS[cast(str, kwargs["fg"])]
        if kwargs["fg"] not in list(FG_COLORS.values()):
            raise ValueError(f"Bad fg value: {kwargs['fg']!r}")
    if "bg" in kwargs:
        if kwargs["bg"] in BG_COLORS:
            kwargs["bg"] = BG_COLORS[cast(str, kwargs["bg"])]
        if kwargs["bg"] not in list(BG_COLORS.values()):
            raise ValueError(f"Bad bg value: {kwargs['bg']!r}")
    return cast(MutableMapping[str, Union[int, bool]], kwargs)


def fmtstr(string: Union[str, FmtStr], *args: Any, **kwargs: Any) -> FmtStr:
    """
    Convenience function for creating a FmtStr

    >>> fmtstr('asdf', 'blue', 'on_red', 'bold')
    on_red(bold(blue('asdf')))
    >>> fmtstr('blarg', fg='blue', bg='red', bold=True)
    on_red(bold(blue('blarg')))
    """
    atts = parse_args(args, kwargs)
    if isinstance(string, str):
        string = FmtStr.from_str(string)
    elif not isinstance(string, FmtStr):
        raise ValueError(
            f"Bad Args: {string!r} (of type {type(string)}), {args!r}, {kwargs!r}"
        )
    return string.copy_with_new_atts(**atts)
