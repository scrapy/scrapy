"""Tools for preparing code to be run in the REPL (removing blank lines,
etc)"""

from codeop import CommandCompiler
from typing import Match
from itertools import tee, islice, chain

from ..lazyre import LazyReCompile

# TODO specifically catch IndentationErrors instead of any syntax errors

indent_empty_lines_re = LazyReCompile(r"\s*")
tabs_to_spaces_re = LazyReCompile(r"^\t+")


def indent_empty_lines(s: str, compiler: CommandCompiler) -> str:
    """Indents blank lines that would otherwise cause early compilation

    Only really works if starting on a new line"""
    initial_lines = s.split("\n")
    ends_with_newline = False
    if initial_lines and not initial_lines[-1]:
        ends_with_newline = True
        initial_lines.pop()
    result_lines = []

    prevs, lines, nexts = tee(initial_lines, 3)
    prevs = chain(("",), prevs)
    nexts = chain(islice(nexts, 1, None), ("",))

    for p_line, line, n_line in zip(prevs, lines, nexts):
        if len(line) == 0:
            # "\s*" always matches
            p_indent = indent_empty_lines_re.match(p_line).group()  # type: ignore
            n_indent = indent_empty_lines_re.match(n_line).group()  # type: ignore
            result_lines.append(min([p_indent, n_indent], key=len) + line)
        else:
            result_lines.append(line)

    return "\n".join(result_lines) + ("\n" if ends_with_newline else "")


def leading_tabs_to_spaces(s: str) -> str:
    def tab_to_space(m: Match[str]) -> str:
        return len(m.group()) * 4 * " "

    return "\n".join(
        tabs_to_spaces_re.sub(tab_to_space, line) for line in s.split("\n")
    )


def preprocess(s: str, compiler: CommandCompiler) -> str:
    return indent_empty_lines(leading_tabs_to_spaces(s), compiler)
