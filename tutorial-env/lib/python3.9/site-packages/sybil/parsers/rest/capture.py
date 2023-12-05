import re
import string
from typing import Iterable, List, Tuple
from textwrap import dedent

from sybil import Region, Document
from sybil.evaluators.capture import evaluate_capture

CAPTURE_DIRECTIVE = re.compile(
    r'^(?P<indent>(\t| )*)\.\.\s*-+>\s*(?P<name>\S+).*$'
)


def indent_matches(line: str, indent: str) -> bool:
    # Is the indentation of a line match what we're looking for?

    if not line.strip():
        # the line consists entirely of whitespace (or nothing at all),
        # so is not considered to be of the appropriate indentation
        return False

    if line.startswith(indent):
        if line[len(indent)] not in string.whitespace:
            return True

    # if none of the above found the indentation to be a match, it is
    # not a match
    return False


class DocumentReversedLines(List[str]):

    def __init__(self, document: Document) -> None:
        super().__init__()
        self[:] = document.text.splitlines(keepends=True)
        self.current_line = len(self)
        self.current_line_end_position = len(document.text)

    def iterate_with_line_number(self) -> Iterable[Tuple[int, str]]:
        while self.current_line > 0:
            self.current_line -= 1
            line = self[self.current_line]
            self.current_line_end_position -= len(line)
            yield self.current_line, line


class CaptureParser:
    """
    A :any:`Parser` for :ref:`captures <capture-parser>`.
    """
    def __call__(self, document: Document) -> Iterable[Region]:
        lines = DocumentReversedLines(document)

        for end_index, line in lines.iterate_with_line_number():

            directive = CAPTURE_DIRECTIVE.match(line)
            if directive:

                region_end = lines.current_line_end_position

                indent = directive.group('indent')
                for start_index, line in lines.iterate_with_line_number():
                    if indent_matches(line, indent):
                        # don't include the preceding line in the capture
                        start_index += 1
                        break
                else:
                    # make it blow up
                    start_index = end_index

                if end_index - start_index < 2:
                    raise ValueError((
                        "couldn't find the start of the block to match "
                        "%r on line %i of %s"
                    ) % (directive.group(), end_index+1, document.path))

                # after dedenting, we need to remove excess leading and trailing
                # newlines, before adding back the final newline that's strippped
                # off
                text = dedent(''.join(lines[start_index:end_index])).strip()+'\n'

                name = directive.group('name')
                parsed = name, text

                yield Region(
                    lines.current_line_end_position,
                    region_end,
                    parsed,
                    evaluate_capture
                )
