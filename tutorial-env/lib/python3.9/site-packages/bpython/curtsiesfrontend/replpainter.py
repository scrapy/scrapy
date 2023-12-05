import logging
import itertools

from curtsies import fsarray, fmtstr, FSArray
from curtsies.formatstring import linesplit
from curtsies.fmtfuncs import bold

from .parse import func_for_letter

logger = logging.getLogger(__name__)

# All paint functions should
# * return an array of the width they were asked for
# * return an array not taller than the height they were asked for


def display_linize(msg, columns, blank_line=False):
    """Returns lines obtained by splitting msg over multiple lines.

    Warning: if msg is empty, returns an empty list of lines"""
    if not msg:
        return [""] if blank_line else []
    msg = fmtstr(msg)
    try:
        display_lines = list(msg.width_aware_splitlines(columns))
    # use old method if wcwidth can't determine width of msg
    except ValueError:
        display_lines = [
            msg[start:end]
            for start, end in zip(
                range(0, len(msg), columns),
                range(columns, len(msg) + columns, columns),
            )
        ]
    return display_lines


def paint_history(rows, columns, display_lines):
    lines = []
    for r, line in zip(range(rows), display_lines[-rows:]):
        lines.append(fmtstr(line[:columns]))
    r = fsarray(lines, width=columns)
    assert r.shape[0] <= rows, repr(r.shape) + " " + repr(rows)
    assert r.shape[1] <= columns, repr(r.shape) + " " + repr(columns)
    return r


def paint_current_line(rows, columns, current_display_line):
    lines = display_linize(current_display_line, columns, True)
    return fsarray(lines, width=columns)


def paginate(rows, matches, current, words_wide):
    if current not in matches:
        current = matches[0]
    per_page = rows * words_wide
    current_page = matches.index(current) // per_page
    return matches[per_page * current_page : per_page * (current_page + 1)]


def matches_lines(rows, columns, matches, current, config, match_format):
    highlight_color = func_for_letter(config.color_scheme["operator"].lower())

    if not matches:
        return []
    color = func_for_letter(config.color_scheme["main"])
    max_match_width = max(len(m) for m in matches)
    words_wide = max(1, (columns - 1) // (max_match_width + 1))
    matches = [match_format(m) for m in matches]
    if current:
        current = match_format(current)

    matches = paginate(rows, matches, current, words_wide)

    result = [
        fmtstr(" ").join(
            color(m.ljust(max_match_width))
            if m != current
            else highlight_color(m.ljust(max_match_width))
            for m in matches[i : i + words_wide]
        )
        for i in range(0, len(matches), words_wide)
    ]

    logger.debug("match: %r" % current)
    logger.debug("matches_lines: %r" % result)
    return result


def formatted_argspec(funcprops, arg_pos, columns, config):
    # Pretty directly taken from bpython.cli
    func = funcprops.func
    args = funcprops.argspec.args
    kwargs = funcprops.argspec.defaults
    _args = funcprops.argspec.varargs
    _kwargs = funcprops.argspec.varkwargs
    is_bound_method = funcprops.is_bound_method
    kwonly = funcprops.argspec.kwonly
    kwonly_defaults = funcprops.argspec.kwonly_defaults or dict()

    arg_color = func_for_letter(config.color_scheme["name"])
    func_color = func_for_letter(config.color_scheme["name"].swapcase())
    punctuation_color = func_for_letter(config.color_scheme["punctuation"])
    token_color = func_for_letter(config.color_scheme["token"])
    bolds = {
        token_color: lambda x: bold(token_color(x)),
        arg_color: lambda x: bold(arg_color(x)),
    }

    s = func_color(func) + arg_color(": (")

    if is_bound_method and isinstance(arg_pos, int):
        # TODO what values could this have?
        arg_pos += 1

    for i, arg in enumerate(args):
        kw = None
        if kwargs and i >= len(args) - len(kwargs):
            kw = str(kwargs[i - (len(args) - len(kwargs))])
        color = token_color if arg_pos in (i, arg) else arg_color
        if i == arg_pos or arg == arg_pos:
            color = bolds[color]

        s += color(arg)

        if kw is not None:
            s += punctuation_color("=")
            s += token_color(kw)

        if i != len(args) - 1:
            s += punctuation_color(", ")

    if _args:
        if args:
            s += punctuation_color(", ")
        s += token_color(f"*{_args}")

    if kwonly:
        if not _args:
            if args:
                s += punctuation_color(", ")
            s += punctuation_color("*")
        marker = object()
        for arg in kwonly:
            s += punctuation_color(", ")
            color = token_color
            if arg_pos:
                color = bolds[color]
            s += color(arg)
            default = kwonly_defaults.get(arg, marker)
            if default is not marker:
                s += punctuation_color("=")
                s += token_color(repr(default))

    if _kwargs:
        if args or _args or kwonly:
            s += punctuation_color(", ")
        s += token_color(f"**{_kwargs}")
    s += punctuation_color(")")

    return linesplit(s, columns)


def formatted_docstring(docstring, columns, config):
    if isinstance(docstring, bytes):
        docstring = docstring.decode("utf8")
    elif isinstance(docstring, str):
        pass
    else:
        # TODO: fail properly here and catch possible exceptions in callers.
        return []
    color = func_for_letter(config.color_scheme["comment"])
    return sum(
        (
            [
                color(x)
                for x in (display_linize(line, columns) if line else fmtstr(""))
            ]
            for line in docstring.split("\n")
        ),
        [],
    )


def paint_infobox(
    rows,
    columns,
    matches,
    funcprops,
    arg_pos,
    match,
    docstring,
    config,
    match_format,
):
    """Returns painted completions, funcprops, match, docstring etc."""
    if not (rows and columns):
        return FSArray(0, 0)
    width = columns - 4
    from_argspec = (
        formatted_argspec(funcprops, arg_pos, width, config)
        if funcprops
        else []
    )
    from_doc = (
        formatted_docstring(docstring, width, config) if docstring else []
    )
    from_matches = (
        matches_lines(
            max(1, rows - len(from_argspec) - 2),
            width,
            matches,
            match,
            config,
            match_format,
        )
        if matches
        else []
    )

    lines = from_argspec + from_matches + from_doc

    def add_border(line):
        """Add colored borders left and right to a line."""
        new_line = border_color(config.left_border + " ")
        new_line += line.ljust(width)[:width]
        new_line += border_color(" " + config.right_border)
        return new_line

    border_color = func_for_letter(config.color_scheme["main"])

    top_line = border_color(
        config.left_top_corner
        + config.top_border * (width + 2)
        + config.right_top_corner
    )
    bottom_line = border_color(
        config.left_bottom_corner
        + config.bottom_border * (width + 2)
        + config.right_bottom_corner
    )

    output_lines = list(
        itertools.chain((top_line,), map(add_border, lines), (bottom_line,))
    )
    r = fsarray(
        output_lines[: min(rows - 1, len(output_lines) - 1)] + output_lines[-1:]
    )
    return r


def paint_last_events(rows, columns, names, config):
    if not names:
        return fsarray([])
    width = min(max(len(name) for name in names), columns - 2)
    output_lines = []
    output_lines.append(
        config.left_top_corner
        + config.top_border * width
        + config.right_top_corner
    )
    for name in reversed(names[max(0, len(names) - (rows - 2)) :]):
        output_lines.append(
            config.left_border
            + name[:width].center(width)
            + config.right_border
        )
    output_lines.append(
        config.left_bottom_corner
        + config.bottom_border * width
        + config.right_bottom_corner
    )
    return fsarray(output_lines)


def paint_statusbar(rows, columns, msg, config):
    func = func_for_letter(config.color_scheme["main"])
    return fsarray([func(msg.ljust(columns))[:columns]])
