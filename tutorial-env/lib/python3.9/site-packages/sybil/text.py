import re

NEWLINE = re.compile("\n")


class LineNumberOffsets:

    def __init__(self, text: str) -> None:
        self.offsets = {
            line: match.start()+1 for (line, match) in enumerate(NEWLINE.finditer(text), start=1)
        }
        self.offsets[0] = 0

    def get(self, line: int, column: int) -> int:
        """
        Return the character offset of the  zero based line number and column offset.
        """
        return self.offsets[line] + column
