"""Events for keystrokes and other input events"""
import codecs
import itertools
import sys
from enum import Enum, auto
from typing import Optional, List, Sequence, Union

from .termhelpers import Termmode
from .curtsieskeys import CURTSIES_NAMES as special_curtsies_names

chr_byte = lambda i: chr(i).encode("latin-1")
chr_uni = chr


CURTSIES_NAMES = {chr_byte(i): "<Ctrl-%s>" % chr(i + 0x60) for i in range(0x00, 0x1B)}
for i in range(0x00, 0x80):
    CURTSIES_NAMES[b"\x1b" + chr_byte(i)] = "<Esc+%s>" % chr(i)
for i in range(0x00, 0x1B):  # Overwrite the control keys with better labels
    CURTSIES_NAMES[b"\x1b" + chr_byte(i)] = "<Esc+Ctrl-%s>" % chr(i + 0x40)
for i in range(0x00, 0x80):
    CURTSIES_NAMES[chr_byte(i + 0x80)] = "<Meta-%s>" % chr(i)
for i in range(0x00, 0x1B):  # Overwrite the control keys with better labels
    CURTSIES_NAMES[chr_byte(i + 0x80)] = "<Meta-Ctrl-%s>" % chr(i + 0x40)

CURTSIES_NAMES.update(special_curtsies_names)

CURSES_NAMES = {
    b"\x1bOP": "KEY_F(1)",
    b"\x1bOQ": "KEY_F(2)",
    b"\x1bOR": "KEY_F(3)",
    b"\x1bOS": "KEY_F(4)",
    b"\x1b[15~": "KEY_F(5)",
    b"\x1b[17~": "KEY_F(6)",
    b"\x1b[18~": "KEY_F(7)",
    b"\x1b[19~": "KEY_F(8)",
    b"\x1b[20~": "KEY_F(9)",
    b"\x1b[21~": "KEY_F(10)",
    b"\x1b[23~": "KEY_F(11)",
    b"\x1b[24~": "KEY_F(12)",
    # see bpython #626
    b"\x1b[11~": "KEY_F(1)",
    b"\x1b[12~": "KEY_F(2)",
    b"\x1b[13~": "KEY_F(3)",
    b"\x1b[14~": "KEY_F(4)",
    b"\x1b[A": "KEY_UP",
    b"\x1b[B": "KEY_DOWN",
    b"\x1b[C": "KEY_RIGHT",
    b"\x1b[D": "KEY_LEFT",
    b"\x1b[F": "KEY_END",  # https://github.com/bpython/bpython/issues/490
    b"\x1b[H": "KEY_HOME",  # https://github.com/bpython/bpython/issues/490
    b"\x08": "KEY_BACKSPACE",
    b"\x1b[Z": "KEY_BTAB",
    # see curtsies #78 - taken from https://github.com/jquast/blessed/blob/e9ad7b85dfcbbba49010ab8c13e3a5920d81b010/blessed/keyboard.py#L409
    b"\x1b[1~": "KEY_FIND",  # find
    b"\x1b[2~": "KEY_IC",  # insert (0)
    b"\x1b[3~": "KEY_DC",  # delete (.), "Execute"
    b"\x1b[4~": "KEY_SELECT",  # select
    b"\x1b[5~": "KEY_PPAGE",  # pgup   (9)
    b"\x1b[6~": "KEY_NPAGE",  # pgdown (3)
    b"\x1b[7~": "KEY_HOME",  # home
    b"\x1b[8~": "KEY_END",  # end
    b"\x1b[OA": "KEY_UP",  # up     (8)
    b"\x1b[OB": "KEY_DOWN",  # down   (2)
    b"\x1b[OC": "KEY_RIGHT",  # right  (6)
    b"\x1b[OD": "KEY_LEFT",  # left   (4)
    b"\x1b[OF": "KEY_END",  # end    (1)
    b"\x1b[OH": "KEY_HOME",  # home   (7)
}

KEYMAP_PREFIXES = set()
for table in (CURSES_NAMES, CURTSIES_NAMES):
    for k in table:
        if k.startswith(b"\x1b"):
            for i in range(1, len(k)):
                KEYMAP_PREFIXES.add(k[:i])

MAX_KEYPRESS_SIZE = max(
    len(seq) for seq in itertools.chain(CURSES_NAMES.keys(), CURTSIES_NAMES.keys())
)


class Keynames(Enum):
    CURTSIES = auto()
    CURSES = auto()
    BYTES = auto()


class Event:
    pass


class ScheduledEvent(Event):
    """Event scheduled for a future time.

    args:
        when (float): unix time in seconds for which this event is scheduled

    Custom events that occur at a specific time in the future should
    be subclassed from ScheduledEvent."""

    def __init__(self, when: float) -> None:
        self.when = when


class WindowChangeEvent(Event):
    def __init__(
        self, rows: int, columns: int, cursor_dy: Optional[int] = None
    ) -> None:
        self.rows = rows
        self.columns = columns
        self.cursor_dy = cursor_dy

    x = width = property(lambda self: self.columns)
    y = height = property(lambda self: self.rows)

    def __repr__(self) -> str:
        return "<WindowChangeEvent (%d, %d)%s>" % (
            self.rows,
            self.columns,
            "" if self.cursor_dy is None else " cursor_dy: %d" % self.cursor_dy,
        )

    @property
    def name(self) -> str:
        return "<WindowChangeEvent>"


class SigIntEvent(Event):
    """Event signifying a SIGINT"""

    def __repr__(self) -> str:
        return "<SigInt Event>"

    @property
    def name(self) -> str:
        return repr(self)


class PasteEvent(Event):
    """Multiple keypress events combined, likely from copy/paste.

    The events attribute contains a list of keypress event strings.
    """

    def __init__(self) -> None:
        self.events: List[str] = []

    def __repr__(self) -> str:
        return "<Paste Event with data: %r>" % self.events

    @property
    def name(self) -> str:
        return repr(self)


def decodable(seq: bytes, encoding: str) -> bool:
    try:
        u = seq.decode(encoding)
    except UnicodeDecodeError:
        return False
    else:
        return True


def _key_name(seq: bytes, encoding: str, keynames: Keynames) -> str:
    if keynames == Keynames.CURSES:
        # may not be here (and still not decodable) curses names incomplete
        if seq in CURSES_NAMES:
            return CURSES_NAMES[seq]

        # Otherwise, there's no special curses name for this
        try:
            # for normal decodable text or a special curtsies sequence with bytes that can be decoded
            return seq.decode(encoding)
        except UnicodeDecodeError:
            # this sequence can't be decoded with this encoding, so we need to represent the bytes
            if len(seq) == 1:
                return "x%02X" % ord(seq)
                # TODO figure out a better thing to return here
            else:
                raise NotImplementedError(
                    "are multibyte unnameable sequences possible?"
                )
                return "bytes: " + "-".join(
                    "x%02X" % ord(seq[i : i + 1]) for i in range(len(seq))
                )
                # TODO if this isn't possible, return multiple meta keys as a paste event if paste events enabled
    elif keynames == Keynames.CURTSIES:
        if seq in CURTSIES_NAMES:
            return CURTSIES_NAMES[seq]
        # assumes that curtsies names are a subset of curses ones
        return seq.decode(encoding)
    else:
        assert keynames == Keynames.BYTES
        return seq  # type: ignore


def get_key(
    bytes_: Sequence[bytes],
    encoding: str,
    keynames: Keynames = Keynames.CURTSIES,
    full: bool = False,
) -> Optional[str]:
    """Return key pressed from bytes_ or None

    Return a key name or None meaning it's an incomplete sequence of bytes
    (more bytes needed to determine the key pressed)

    encoding is how the bytes should be translated to unicode - it should
    match the terminal encoding.

    keynames is a string describing how keys should be named:

    * curtsies uses unicode strings like <F8>

    * curses uses unicode strings similar to those returned by
      the Python ncurses window.getkey function, like KEY_F(8),
      plus a nonstandard representation of meta keys (bytes 128-255)
      because returning the corresponding unicode code point would be
      indistinguishable from the multibyte sequence that encodes that
      character in the current encoding

    * bytes returns the original bytes from stdin (NOT unicode)

    if full, match a key even if it could be a prefix to another key
    (useful for detecting a plain escape key for instance, since
    escape is also a prefix to a bunch of char sequences for other keys)

    Events are subclasses of Event, or unicode strings

    Precondition: get_key(prefix, keynames) is None for all proper prefixes of
    bytes. This means get_key should be called on progressively larger inputs
    (for 'asdf', first on 'a', then on 'as', then on 'asd' - until a non-None
    value is returned)
    """
    if not all(isinstance(c, bytes) for c in bytes_):
        raise TypeError("get key expects bytes, got %r" % bytes_)  # expects raw bytes
    seq = b"".join(bytes_)
    if len(seq) > MAX_KEYPRESS_SIZE:
        raise ValueError("unable to decode bytes %r" % seq)

    key_known = seq in CURTSIES_NAMES or seq in CURSES_NAMES or decodable(seq, encoding)

    if full and key_known:
        return _key_name(seq, encoding, keynames)
    elif seq in KEYMAP_PREFIXES or could_be_unfinished_char(seq, encoding):
        return None  # need more input to make up a full keypress
    elif key_known:
        return _key_name(seq, encoding, keynames)
    else:
        # this will raise a unicode error (they're annoying to raise ourselves)
        seq.decode(encoding)
        assert False, "should have raised an unicode decode error"


def could_be_unfinished_char(seq: bytes, encoding: str) -> bool:
    """Whether seq bytes might create a char in encoding if more bytes were added"""
    if decodable(seq, encoding):
        return False  # any sensible encoding surely doesn't require lookahead (right?)
        # (if seq bytes encoding a character, adding another byte shouldn't also encode something)

    if codecs.getdecoder("utf8") is codecs.getdecoder(encoding):
        return could_be_unfinished_utf8(seq)
    elif codecs.getdecoder("ascii") is codecs.getdecoder(encoding):
        return False
    else:
        return True  # We don't know, it could be


def could_be_unfinished_utf8(seq: bytes) -> bool:
    # http://en.wikipedia.org/wiki/UTF-8#Description
    o = ord(seq[0:1])
    return (
        (o & 0b11100000 == 0b11000000 and len(seq) < 2)
        or (o & 0b11110000 == 0b11100000 and len(seq) < 3)
        or (o & 0b11111000 == 0b11110000 and len(seq) < 4)
        or (o & 0b11111100 == 0b11111000 and len(seq) < 5)
        or (o & 0b11111110 == 0b11111100 and len(seq) < 6)
    )


def pp_event(seq: Union[Event, str]) -> Union[str, bytes]:
    """Returns pretty representation of an Event or keypress"""

    if isinstance(seq, Event):
        return str(seq)

    # Get the original sequence back if seq is a pretty name already
    rev_curses = {v: k for k, v in CURSES_NAMES.items()}
    rev_curtsies = {v: k for k, v in CURTSIES_NAMES.items()}
    bytes_seq: Optional[bytes] = None
    if seq in rev_curses:
        bytes_seq = rev_curses[seq]
    elif seq in rev_curtsies:
        bytes_seq = rev_curtsies[seq]

    if bytes_seq:
        pretty = curtsies_name(bytes_seq)
        if pretty != seq:
            return pretty
    return repr(seq).lstrip("u")[1:-1]


def curtsies_name(seq: bytes) -> Union[str, bytes]:
    return CURTSIES_NAMES.get(seq, seq)


def try_keys() -> None:
    print(
        "press a bunch of keys (not at the same time, but you can hit them pretty quickly)"
    )
    import os
    from .termhelpers import Cbreak

    def ask_what_they_pressed(seq: bytes, Normal: Termmode) -> None:
        print("Unidentified character sequence!")
        with Normal:
            while True:
                r = input("type 'ok' to prove you're not pounding keys ")
                if r.lower().strip() == "ok":
                    break
        while True:
            print(f"Press the key that produced {seq!r} again please")
            retry = os.read(sys.stdin.fileno(), 1000)
            if seq == retry:
                break
            print("nope, that wasn't it")
        with Normal:
            name = input("Describe in English what key you pressed: ")
            f = open("keylog.txt", "a")
            f.write(f"{seq!r} is called {name}\n")
            f.close()
            print(
                "Thanks! Please open an issue at https://github.com/bpython/curtsies/issues"
            )
            print(
                "or email thomasballinger@gmail.com. Include this terminal history or keylog.txt."
            )
            print("You can keep pressing keys")

    with Cbreak(sys.stdin) as NoCbreak:
        while True:
            try:
                chars = os.read(sys.stdin.fileno(), 1000)
                print("---")
                print(repr(chars))
                if chars in CURTSIES_NAMES:
                    print(CURTSIES_NAMES[chars])
                elif len(chars) == 1:
                    print("literal")
                else:
                    print("unknown!!!")
                    ask_what_they_pressed(chars, NoCbreak)
            except OSError:
                pass


if __name__ == "__main__":
    try_keys()
