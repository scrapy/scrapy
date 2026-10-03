from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, ClassVar

from scrapy.cmdline import _build_parser, _get_commands_dict
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.project import inside_project

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from scrapy.settings import Settings


_BASH = """\
_scrapy_completion() {
    local IFS=$'\\n'
    COMPREPLY=($(scrapy complete -- "${COMP_WORDS[@]:1:COMP_CWORD}" 2>/dev/null | cut -f1))
}
complete -o default -F _scrapy_completion scrapy
"""

_ZSH = """\
#compdef scrapy
_scrapy() {
    local -a candidates
    candidates=(${(f)"$(scrapy complete -- "${(@)words[2,CURRENT]}" 2>/dev/null)"})
    if (( $#candidates )); then
        candidates=("${(@)candidates//$'\\t'/:}")
        _describe -t scrapy scrapy candidates
    else
        _default
    fi
}
compdef _scrapy scrapy
"""

_FISH = """\
function __scrapy_complete
    set -l tokens (commandline -opc)
    set -e tokens[1]
    set -l current (commandline -ct)
    set -l candidates (scrapy complete -- $tokens "$current" 2>/dev/null)
    if set -q candidates[1]
        printf '%s\\n' $candidates
    else
        __fish_complete_path "$current"
    end
end
complete -c scrapy -f -a '(__scrapy_complete)'
"""

_SCRIPTS = {"bash": _BASH, "fish": _FISH, "zsh": _ZSH}


def _positional_args(args: list[str], options: dict[str, argparse.Action]) -> list[str]:
    positional = []
    index = 0
    while index < len(args):
        arg = args[index]
        action = options.get(arg)
        if action is not None:
            index += 1 if action.nargs == 0 else 2
        elif arg.startswith("-"):
            index += 1
        else:
            positional.append(arg)
            index += 1
    return positional


def _iter_candidates(
    settings: Settings, prefix: str, typed: list[str]
) -> Iterator[tuple[str, str]]:
    """Yield ``(value, description)`` pairs for the word being completed,
    where *prefix* is that word and *typed* are the words before it."""
    cmds = _get_commands_dict(settings, inside_project())
    if not typed:
        for name, command in sorted(cmds.items()):
            yield name, command.short_desc()
        return
    cmdname, args = typed[0], typed[1:]
    cmd = cmds.get(cmdname)
    if cmd is None:
        return
    parser = _build_parser(cmd, cmdname, settings)
    # argparse offers no public access to the arguments of a parser.
    actions = parser._actions
    options = {
        option_string: action
        for action in actions
        for option_string in action.option_strings
    }
    previous = options.get(args[-1]) if args else None
    if previous is not None and previous.nargs != 0:
        values: Iterable[Any] = previous.choices or cmd.complete_option(previous.dest)
        yield from ((str(value), "") for value in values)
    elif prefix.startswith("-"):
        for action in actions:
            if action.help == argparse.SUPPRESS:
                continue
            for option_string in action.option_strings:
                yield option_string, action.help or ""
    else:
        for value in cmd.complete_argument(_positional_args(args, options)):
            yield value, ""


def _split_equal_signs(words: list[str]) -> tuple[list[str], str]:
    """Return *words* with ``--option=value`` split into two words, along with
    the ``--option=`` part of the word being completed, which shells that keep
    it as a single word expect back in every candidate.

    Bash splits on ``=`` on its own, into a separate word.
    """
    if words and words[-1] == "=":
        words = [*words[:-1], ""]
    words = [
        word
        for index, word in enumerate(words)
        if not (word == "=" and index and words[index - 1].startswith("-"))
    ]
    if words and words[-1].startswith("-") and "=" in words[-1]:
        option, _, value = words[-1].partition("=")
        return [*words[:-1], option, value], f"{option}="
    return words, ""


def _candidates(settings: Settings, words: list[str]) -> Iterator[str]:
    words, inline = _split_equal_signs(words)
    prefix = words[-1] if words else ""
    for value, description in _iter_candidates(settings, prefix, words[:-1]):
        if value.startswith(prefix):
            candidate = f"{inline}{value}"
            yield f"{candidate}\t{description}" if description else candidate


class Command(ScrapyCommand):
    requires_crawler_process = False
    default_settings: ClassVar[dict[str, Any]] = {"LOG_ENABLED": False}

    def syntax(self) -> str:
        return "<bash|fish|zsh>"

    def short_desc(self) -> str:
        return "Print a shell completion script"

    def long_desc(self) -> str:
        return (
            "Print a completion script for the given shell, to be installed as "
            "described in the Scrapy documentation."
        )

    def complete_argument(self, args: list[str]) -> Iterable[str]:
        return () if args else _SCRIPTS

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        assert self.settings is not None
        if args and args[0] == "--":
            for candidate in _candidates(self.settings, args[1:]):
                print(candidate)
        elif len(args) == 1 and args[0] in _SCRIPTS:
            print(_SCRIPTS[args[0]], end="")
        else:
            raise UsageError
