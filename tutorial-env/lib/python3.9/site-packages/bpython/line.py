"""Extracting and changing portions of the current line

All functions take cursor offset from the beginning of the line and the line of
Python code, and return None, or a tuple of the start index, end index, and the
word."""

import re

from dataclasses import dataclass
from itertools import chain
from typing import Optional, Tuple

from .lazyre import LazyReCompile


@dataclass
class LinePart:
    start: int
    stop: int
    word: str


_current_word_re = LazyReCompile(r"(?<![)\]\w_.])" r"([\w_][\w0-9._]*[(]?)")
CHARACTER_PAIR_MAP = {"(": ")", "{": "}", "[": "]", "'": "'", '"': '"'}


def current_word(cursor_offset: int, line: str) -> Optional[LinePart]:
    """the object.attribute.attribute just before or under the cursor"""
    start = cursor_offset
    end = cursor_offset
    word = None
    for m in _current_word_re.finditer(line):
        if m.start(1) < cursor_offset <= m.end(1):
            start = m.start(1)
            end = m.end(1)
            word = m.group(1)
    if word is None:
        return None
    return LinePart(start, end, word)


# pieces of regex to match repr() of several hashable built-in types
_match_all_dict_keys = r"""[^\]]*"""

# https://docs.python.org/3/reference/lexical_analysis.html#string-and-bytes-literals
_match_single_quote_str_bytes = r"""
    # bytes repr() begins with `b` character; bytes and str begin with `'`
    b?'             
    # match escape sequence; this handles `\'` in the string repr()
    (?:\\['"nabfrtvxuU\\]|
    # or match any non-`\` and non-single-quote character (most of the string)
    [^'\\])*
    # matches hanging `\` or ending `'` if one is present
    [\\']?
"""

# bytes and str repr() only uses double quotes if the string contains 1 or more
# `'` character and exactly 0 `"` characters
_match_double_quote_str_bytes = r"""
    # bytes repr() begins with `b` character
    b?"
    # string continues until a `"` character is reached
    [^"]*
    # end matching at closing double-quote if one is present
    "?"""

# match valid identifier name followed by `[` character
_match_dict_before_key = r"""[\w_][\w0-9._]*\["""

_current_dict_key_re = LazyReCompile(
    f"{_match_dict_before_key}((?:"
    f"{_match_single_quote_str_bytes}|"
    f"{_match_double_quote_str_bytes}|"
    f"{_match_all_dict_keys}|)*)",
    re.VERBOSE,
)


def current_dict_key(cursor_offset: int, line: str) -> Optional[LinePart]:
    """If in dictionary completion, return the current key"""
    for m in _current_dict_key_re.finditer(line):
        if m.start(1) <= cursor_offset <= m.end(1):
            return LinePart(m.start(1), m.end(1), m.group(1))
    return None


# capture valid identifier name if followed by `[` character
_capture_dict_name = r"""([\w_][\w0-9._]*)\["""

_current_dict_re = LazyReCompile(
    f"{_capture_dict_name}((?:"
    f"{_match_single_quote_str_bytes}|"
    f"{_match_double_quote_str_bytes}|"
    f"{_match_all_dict_keys}|)*)",
    re.VERBOSE,
)


def current_dict(cursor_offset: int, line: str) -> Optional[LinePart]:
    """If in dictionary completion, return the dict that should be used"""
    for m in _current_dict_re.finditer(line):
        if m.start(2) <= cursor_offset <= m.end(2):
            return LinePart(m.start(1), m.end(1), m.group(1))
    return None


_current_string_re = LazyReCompile(
    '''(?P<open>(?:""")|"|(?:''\')|')(?:((?P<closed>.+?)(?P=open))|'''
    """(?P<unclosed>.+))"""
)


def current_string(cursor_offset: int, line: str) -> Optional[LinePart]:
    """If inside a string of nonzero length, return the string (excluding
    quotes)

    Weaker than bpython.Repl's current_string, because that checks that a
    string is a string based on previous lines in the buffer."""
    for m in _current_string_re.finditer(line):
        i = 3 if m.group(3) else 4
        if m.start(i) <= cursor_offset <= m.end(i):
            return LinePart(m.start(i), m.end(i), m.group(i))
    return None


_current_object_re = LazyReCompile(r"([\w_][\w0-9_]*)[.]")


def current_object(cursor_offset: int, line: str) -> Optional[LinePart]:
    """If in attribute completion, the object on which attribute should be
    looked up."""
    match = current_word(cursor_offset, line)
    if match is None:
        return None
    s = ".".join(
        m.group(1)
        for m in _current_object_re.finditer(match.word)
        if m.end(1) + match.start < cursor_offset
    )
    if not s:
        return None
    return LinePart(match.start, match.start + len(s), s)


_current_object_attribute_re = LazyReCompile(r"([\w_][\w0-9_]*)[.]?")


def current_object_attribute(
    cursor_offset: int, line: str
) -> Optional[LinePart]:
    """If in attribute completion, the attribute being completed"""
    # TODO replace with more general current_expression_attribute
    match = current_word(cursor_offset, line)
    if match is None:
        return None
    matches = _current_object_attribute_re.finditer(match.word)
    next(matches)
    for m in matches:
        if m.start(1) + match.start <= cursor_offset <= m.end(1) + match.start:
            return LinePart(
                m.start(1) + match.start, m.end(1) + match.start, m.group(1)
            )
    return None


_current_from_import_from_re = LazyReCompile(
    r"from +([\w0-9_.]*)(?:\s+import\s+([\w0-9_]+[,]?\s*)+)*"
)


def current_from_import_from(
    cursor_offset: int, line: str
) -> Optional[LinePart]:
    """If in from import completion, the word after from

    returns None if cursor not in or just after one of the two interesting
    parts of an import: from (module) import (name1, name2)
    """
    # TODO allow for as's
    for m in _current_from_import_from_re.finditer(line):
        if (m.start(1) < cursor_offset <= m.end(1)) or (
            m.start(2) < cursor_offset <= m.end(2)
        ):
            return LinePart(m.start(1), m.end(1), m.group(1))
    return None


_current_from_import_import_re_1 = LazyReCompile(
    r"from\s+([\w0-9_.]*)\s+import"
)
_current_from_import_import_re_2 = LazyReCompile(r"([\w0-9_]+)")
_current_from_import_import_re_3 = LazyReCompile(r", *([\w0-9_]*)")


def current_from_import_import(
    cursor_offset: int, line: str
) -> Optional[LinePart]:
    """If in from import completion, the word after import being completed

    returns None if cursor not in or just after one of these words
    """
    baseline = _current_from_import_import_re_1.search(line)
    if baseline is None:
        return None
    match1 = _current_from_import_import_re_2.search(line[baseline.end() :])
    if match1 is None:
        return None
    for m in chain(
        (match1,),
        _current_from_import_import_re_3.finditer(line[baseline.end() :]),
    ):
        start = baseline.end() + m.start(1)
        end = baseline.end() + m.end(1)
        if start < cursor_offset <= end:
            return LinePart(start, end, m.group(1))
    return None


_current_import_re_1 = LazyReCompile(r"import")
_current_import_re_2 = LazyReCompile(r"([\w0-9_.]+)")
_current_import_re_3 = LazyReCompile(r"[,][ ]*([\w0-9_.]*)")


def current_import(cursor_offset: int, line: str) -> Optional[LinePart]:
    # TODO allow for multiple as's
    baseline = _current_import_re_1.search(line)
    if baseline is None:
        return None
    match1 = _current_import_re_2.search(line[baseline.end() :])
    if match1 is None:
        return None
    for m in chain(
        (match1,), _current_import_re_3.finditer(line[baseline.end() :])
    ):
        start = baseline.end() + m.start(1)
        end = baseline.end() + m.end(1)
        if start < cursor_offset <= end:
            return LinePart(start, end, m.group(1))
    return None


_current_method_definition_name_re = LazyReCompile(r"def\s+([a-zA-Z_][\w]*)")


def current_method_definition_name(
    cursor_offset: int, line: str
) -> Optional[LinePart]:
    """The name of a method being defined"""
    for m in _current_method_definition_name_re.finditer(line):
        if m.start(1) <= cursor_offset <= m.end(1):
            return LinePart(m.start(1), m.end(1), m.group(1))
    return None


_current_single_word_re = LazyReCompile(r"(?<![.])\b([a-zA-Z_][\w]*)")


def current_single_word(cursor_offset: int, line: str) -> Optional[LinePart]:
    """the un-dotted word just before or under the cursor"""
    for m in _current_single_word_re.finditer(line):
        if m.start(1) <= cursor_offset <= m.end(1):
            return LinePart(m.start(1), m.end(1), m.group(1))
    return None


def current_dotted_attribute(
    cursor_offset: int, line: str
) -> Optional[LinePart]:
    """The dotted attribute-object pair before the cursor"""
    match = current_word(cursor_offset, line)
    if match is not None and "." in match.word[1:]:
        return match
    return None


_current_expression_attribute_re = LazyReCompile(
    r"[.]\s*((?:[\w_][\w0-9_]*)|(?:))"
)


def current_expression_attribute(
    cursor_offset: int, line: str
) -> Optional[LinePart]:
    """If after a dot, the attribute being completed"""
    # TODO replace with more general current_expression_attribute
    for m in _current_expression_attribute_re.finditer(line):
        if m.start(1) <= cursor_offset <= m.end(1):
            return LinePart(m.start(1), m.end(1), m.group(1))
    return None


def cursor_on_closing_char_pair(
    cursor_offset: int, line: str, ch: Optional[str] = None
) -> Tuple[bool, bool]:
    """Checks if cursor sits on closing character of a pair
    and whether its pair character is directly behind it
    """
    on_closing_char, pair_close = False, False
    if line is None:
        return on_closing_char, pair_close
    if cursor_offset < len(line):
        cur_char = line[cursor_offset]
        if cur_char in CHARACTER_PAIR_MAP.values():
            on_closing_char = True if ch is None else cur_char == ch
        if cursor_offset > 0:
            prev_char = line[cursor_offset - 1]
            if (
                on_closing_char
                and prev_char in CHARACTER_PAIR_MAP
                and CHARACTER_PAIR_MAP[prev_char] == cur_char
            ):
                pair_close = True if ch is None else prev_char == ch
    return on_closing_char, pair_close
