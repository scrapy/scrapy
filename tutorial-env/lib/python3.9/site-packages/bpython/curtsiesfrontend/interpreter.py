import sys
from codeop import CommandCompiler
from typing import Any, Dict, Iterable, Optional, Tuple, Union

from pygments.token import Generic, Token, Keyword, Name, Comment, String
from pygments.token import Error, Literal, Number, Operator, Punctuation
from pygments.token import Whitespace, _TokenType
from pygments.formatter import Formatter
from pygments.lexers import get_lexer_by_name
from curtsies.formatstring import FmtStr

from ..curtsiesfrontend.parse import parse
from ..repl import Interpreter as ReplInterpreter


default_colors = {
    Generic.Error: "R",
    Keyword: "d",
    Name: "c",
    Name.Builtin: "g",
    Comment: "b",
    String: "m",
    Error: "r",
    Literal: "d",
    Number: "M",
    Number.Integer: "d",
    Operator: "d",
    Punctuation: "d",
    Token: "d",
    Whitespace: "d",
    Token.Punctuation.Parenthesis: "R",
    Name.Function: "d",
    Name.Class: "d",
}


class BPythonFormatter(Formatter):
    """This is subclassed from the custom formatter for bpython.  Its format()
    method receives the tokensource and outfile params passed to it from the
    Pygments highlight() method and slops them into the appropriate format
    string as defined above, then writes to the outfile object the final
    formatted string. This does not write real strings. It writes format string
    (FmtStr) objects.

    See the Pygments source for more info; it's pretty
    straightforward."""

    def __init__(
        self,
        color_scheme: Dict[_TokenType, str],
        **options: Union[str, bool, None],
    ) -> None:
        self.f_strings = {k: f"\x01{v}" for k, v in color_scheme.items()}
        # FIXME: mypy currently fails to handle this properly
        super().__init__(**options)  # type: ignore

    def format(self, tokensource, outfile):
        o = ""

        for token, text in tokensource:
            while token not in self.f_strings:
                token = token.parent
            o += f"{self.f_strings[token]}\x03{text}\x04"
        outfile.write(parse(o.rstrip()))


class Interp(ReplInterpreter):
    def __init__(
        self,
        locals: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Constructor.

        We include an argument for the outfile to pass to the formatter for it
        to write to.
        """
        super().__init__(locals)

        # typically changed after being instantiated
        # but used when interpreter used corresponding REPL
        def write(err_line: Union[str, FmtStr]) -> None:
            """Default stderr handler for tracebacks

            Accepts FmtStrs so interpreters can output them"""
            sys.stderr.write(str(err_line))

        self.write = write  # type: ignore
        self.outfile = self

    def writetb(self, lines: Iterable[str]) -> None:
        tbtext = "".join(lines)
        lexer = get_lexer_by_name("pytb")
        self.format(tbtext, lexer)
        # TODO for tracebacks get_lexer_by_name("pytb", stripall=True)

    def format(self, tbtext: str, lexer: Any) -> None:
        # FIXME: lexer should be "Lexer"
        traceback_informative_formatter = BPythonFormatter(default_colors)
        traceback_code_formatter = BPythonFormatter({Token: "d"})

        no_format_mode = False
        cur_line = []
        for token, text in lexer.get_tokens(tbtext):
            if text.endswith("\n"):
                cur_line.append((token, text))
                if no_format_mode:
                    traceback_code_formatter.format(cur_line, self.outfile)
                    no_format_mode = False
                else:
                    traceback_informative_formatter.format(
                        cur_line, self.outfile
                    )
                cur_line = []
            elif text == "    " and len(cur_line) == 0:
                no_format_mode = True
                cur_line.append((token, text))
            else:
                cur_line.append((token, text))
        assert cur_line == [], cur_line


def code_finished_will_parse(
    s: str, compiler: CommandCompiler
) -> Tuple[bool, bool]:
    """Returns a tuple of whether the buffer could be complete and whether it
    will parse

    True, True means code block is finished and no predicted parse error
    True, False means code block is finished because a parse error is predicted
    False, True means code block is unfinished
    False, False isn't possible - an predicted error makes code block done"""
    try:
        return bool(compiler(s)), True
    except (ValueError, SyntaxError, OverflowError):
        return True, False
