"""implementations of simple readline edit operations

just the ones that fit the model of transforming the current line
and the cursor location
based on http://www.bigsmoke.us/readline/shortcuts"""

from ..lazyre import LazyReCompile
import inspect

from ..line import cursor_on_closing_char_pair

INDENT = 4

# TODO Allow user config of keybindings for these actions
getargspec = lambda func: inspect.signature(func).parameters


class AbstractEdits:

    default_kwargs = {
        "line": "hello world",
        "cursor_offset": 5,
        "cut_buffer": "there",
    }

    def __init__(self, simple_edits=None, cut_buffer_edits=None):
        self.simple_edits = {} if simple_edits is None else simple_edits
        self.cut_buffer_edits = (
            {} if cut_buffer_edits is None else cut_buffer_edits
        )
        self.awaiting_config = {}

    def add(self, key, func, overwrite=False):
        if key in self:
            if overwrite:
                del self[key]
            else:
                raise ValueError(f"key {key!r} already has a mapping")
        params = getargspec(func)
        args = {k: v for k, v in self.default_kwargs.items() if k in params}
        r = func(**args)
        if len(r) == 2:
            if hasattr(func, "kills"):
                raise ValueError(
                    "function %r returns two values, but has a "
                    "kills attribute" % (func,)
                )
            self.simple_edits[key] = func
        elif len(r) == 3:
            if not hasattr(func, "kills"):
                raise ValueError(
                    "function %r returns three values, but has "
                    "no kills attribute" % (func,)
                )
            self.cut_buffer_edits[key] = func
        else:
            raise ValueError(f"return type of function {func!r} not recognized")

    def add_config_attr(self, config_attr, func):
        if config_attr in self.awaiting_config:
            raise ValueError(
                f"config attribute {config_attr!r} already has a mapping"
            )
        self.awaiting_config[config_attr] = func

    def call(self, key, **kwargs):
        func = self[key]
        params = getargspec(func)
        args = {k: v for k, v in kwargs.items() if k in params}
        return func(**args)

    def call_without_cut(self, key, **kwargs):
        """Looks up the function and calls it, returning only line and cursor
        offset"""
        r = self.call_for_two(key, **kwargs)
        return r[:2]

    def __contains__(self, key):
        return key in self.simple_edits or key in self.cut_buffer_edits

    def __getitem__(self, key):
        if key in self.simple_edits:
            return self.simple_edits[key]
        if key in self.cut_buffer_edits:
            return self.cut_buffer_edits[key]
        raise KeyError(f"key {key!r} not mapped")

    def __delitem__(self, key):
        if key in self.simple_edits:
            del self.simple_edits[key]
        elif key in self.cut_buffer_edits:
            del self.cut_buffer_edits[key]
        else:
            raise KeyError(f"key {key!r} not mapped")


class UnconfiguredEdits(AbstractEdits):
    """Maps key to edit functions, and bins them by what parameters they take.

    Only functions with specific signatures can be added:
        * func(**kwargs) -> cursor_offset, line
        * func(**kwargs) -> cursor_offset, line, cut_buffer
        where kwargs are in among the keys of Edits.default_kwargs
    These functions will be run to determine their return type, so no side
    effects!

    More concrete Edits instances can be created by applying a config with
    Edits.mapping_with_config() - this creates a new Edits instance
    that uses a config file to assign config_attr bindings.

    Keys can't be added twice, config attributes can't be added twice.
    """

    def mapping_with_config(self, config, key_dispatch):
        """Creates a new mapping object by applying a config object"""
        return ConfiguredEdits(
            self.simple_edits,
            self.cut_buffer_edits,
            self.awaiting_config,
            config,
            key_dispatch,
        )

    def on(self, key=None, config=None):
        if not ((key is None) ^ (config is None)):
            raise ValueError("Must use exactly one of key, config")
        if key is not None:

            def add_to_keybinds(func):
                self.add(key, func)
                return func

            return add_to_keybinds
        else:

            def add_to_config(func):
                self.add_config_attr(config, func)
                return func

            return add_to_config


class ConfiguredEdits(AbstractEdits):
    def __init__(
        self,
        simple_edits,
        cut_buffer_edits,
        awaiting_config,
        config,
        key_dispatch,
    ):
        super().__init__(dict(simple_edits), dict(cut_buffer_edits))
        for attr, func in awaiting_config.items():
            for key in key_dispatch[getattr(config, attr)]:
                super().add(key, func, overwrite=True)

    def add_config_attr(self, config_attr, func):
        raise NotImplementedError("Config already set on this mapping")

    def add(self, key, func, overwrite=False):
        raise NotImplementedError("Config already set on this mapping")


edit_keys = UnconfiguredEdits()

# Because the edits.on decorator runs the functions, functions which depend
# on other functions must be declared after their dependencies


def kills_behind(func):
    func.kills = "behind"
    return func


def kills_ahead(func):
    func.kills = "ahead"
    return func


@edit_keys.on(config="left_key")
@edit_keys.on("<LEFT>")
def left_arrow(cursor_offset, line):
    return max(0, cursor_offset - 1), line


@edit_keys.on(config="right_key")
@edit_keys.on("<RIGHT>")
def right_arrow(cursor_offset, line):
    return min(len(line), cursor_offset + 1), line


@edit_keys.on(config="beginning_of_line_key")
@edit_keys.on("<HOME>")
def beginning_of_line(cursor_offset, line):
    return 0, line


@edit_keys.on(config="end_of_line_key")
@edit_keys.on("<END>")
def end_of_line(cursor_offset, line):
    return len(line), line


forward_word_re = LazyReCompile(r"\S\s")


@edit_keys.on("<Esc+f>")
@edit_keys.on("<Ctrl-RIGHT>")
@edit_keys.on("<Esc+RIGHT>")
def forward_word(cursor_offset, line):
    match = forward_word_re.search(line[cursor_offset:] + " ")
    delta = match.end() - 1 if match else 0
    return (cursor_offset + delta, line)


def last_word_pos(string):
    """returns the start index of the last word of given string"""
    match = forward_word_re.search(string[::-1])
    index = match and len(string) - match.end() + 1
    return index or 0


@edit_keys.on("<Esc+b>")
@edit_keys.on("<Ctrl-LEFT>")
@edit_keys.on("<Esc+LEFT>")
def back_word(cursor_offset, line):
    return (last_word_pos(line[:cursor_offset]), line)


@edit_keys.on("<DELETE>")
def delete(cursor_offset, line):
    return (cursor_offset, line[:cursor_offset] + line[cursor_offset + 1 :])


@edit_keys.on("<BACKSPACE>")
@edit_keys.on(config="backspace_key")
def backspace(cursor_offset, line):
    if cursor_offset == 0:
        return cursor_offset, line
    if not line[:cursor_offset].strip():  # if just whitespace left of cursor
        # front_white = len(line[:cursor_offset]) - \
        #     len(line[:cursor_offset].lstrip())
        to_delete = ((cursor_offset - 1) % INDENT) + 1
        return (
            cursor_offset - to_delete,
            line[: cursor_offset - to_delete] + line[cursor_offset:],
        )
    # removes opening bracket along with closing bracket
    # if there is nothing between them
    # TODO: could not get config value here, works even without -B option
    on_closing_char, pair_close = cursor_on_closing_char_pair(
        cursor_offset, line
    )
    if on_closing_char and pair_close:
        return (
            cursor_offset - 1,
            line[: cursor_offset - 1] + line[cursor_offset + 1 :],
        )

    return (cursor_offset - 1, line[: cursor_offset - 1] + line[cursor_offset:])


@edit_keys.on(config="clear_line_key")
def delete_from_cursor_back(cursor_offset, line):
    return 0, line[cursor_offset:]


delete_rest_of_word_re = LazyReCompile(r"\w\b")


@edit_keys.on("<Esc+d>")  # option-d
@kills_ahead
def delete_rest_of_word(cursor_offset, line):
    m = delete_rest_of_word_re.search(line[cursor_offset:])
    if not m:
        return cursor_offset, line, ""
    return (
        cursor_offset,
        line[:cursor_offset] + line[m.start() + cursor_offset + 1 :],
        line[cursor_offset : m.start() + cursor_offset + 1],
    )


delete_word_to_cursor_re = LazyReCompile(r"\s\S")


@edit_keys.on(config="clear_word_key")
@kills_behind
def delete_word_to_cursor(cursor_offset, line):
    start = 0
    for match in delete_word_to_cursor_re.finditer(line[:cursor_offset]):
        start = match.start() + 1
    return (
        start,
        line[:start] + line[cursor_offset:],
        line[start:cursor_offset],
    )


@edit_keys.on("<Esc+y>")
def yank_prev_prev_killed_text(cursor_offset, line, cut_buffer):
    # TODO not implemented - just prev
    return (
        cursor_offset + len(cut_buffer),
        line[:cursor_offset] + cut_buffer + line[cursor_offset:],
    )


@edit_keys.on(config="yank_from_buffer_key")
def yank_prev_killed_text(cursor_offset, line, cut_buffer):
    return (
        cursor_offset + len(cut_buffer),
        line[:cursor_offset] + cut_buffer + line[cursor_offset:],
    )


@edit_keys.on(config="transpose_chars_key")
def transpose_character_before_cursor(cursor_offset, line):
    if cursor_offset < 2:
        return cursor_offset, line
    if cursor_offset == len(line):
        return cursor_offset, line[:-2] + line[-1] + line[-2]
    return (
        min(len(line), cursor_offset + 1),
        line[: cursor_offset - 1]
        + (line[cursor_offset] if len(line) > cursor_offset else "")
        + line[cursor_offset - 1]
        + line[cursor_offset + 1 :],
    )


@edit_keys.on("<Esc+t>")
def transpose_word_before_cursor(cursor_offset, line):
    return cursor_offset, line  # TODO Not implemented


# TODO undo all changes to line: meta-r

# bonus functions (not part of readline)


@edit_keys.on("<Esc+u>")
def uppercase_next_word(cursor_offset, line):
    return cursor_offset, line  # TODO Not implemented


@edit_keys.on(config="cut_to_buffer_key")
@kills_ahead
def delete_from_cursor_forward(cursor_offset, line):
    return cursor_offset, line[:cursor_offset], line[cursor_offset:]


@edit_keys.on("<Esc+c>")
def titlecase_next_word(cursor_offset, line):
    return cursor_offset, line  # TODO Not implemented


delete_word_from_cursor_back_re = LazyReCompile(r"^|\b\w")


@edit_keys.on("<Esc+BACKSPACE>")
@edit_keys.on("<Meta-BACKSPACE>")
@kills_behind
def delete_word_from_cursor_back(cursor_offset, line):
    """Whatever my option-delete does in bash on my mac"""
    if not line:
        return cursor_offset, line, ""
    start = None
    for match in delete_word_from_cursor_back_re.finditer(line):
        if match.start() < cursor_offset:
            start = match.start()
    if start is not None:
        return (
            start,
            line[:start] + line[cursor_offset:],
            line[start:cursor_offset],
        )
    else:
        return cursor_offset, line, ""
