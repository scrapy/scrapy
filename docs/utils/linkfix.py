#!/usr/bin/python

"""

Linkfix - a companion to sphinx's linkcheck builder.

Uses the linkcheck's output file to fix links in docs.

Originally created for this issue:
https://github.com/scrapy/scrapy/issues/606

Author: dufferzafar
"""

import re
import sys
from pathlib import Path


def main():
    # Used for remembering the file (and its contents)
    # so we don't have to open the same file again.
    _filename = None
    _contents = None

    # A regex that matches standard linkcheck output lines
    line_re = re.compile(r"(.*)\:\d+\:\s\[(.*)\]\s(?:(.*)\sto\s(.*)|(.*))")

    # Read lines from the linkcheck output file
    try:
        with Path("build/linkcheck/output.txt").open(encoding="utf-8") as out:
            output_lines = out.readlines()
    except OSError:
        print("linkcheck output not found; please run linkcheck first.")
        sys.exit(1)

    # For every line, fix the respective file
    for line in output_lines:
        match = re.match(line_re, line)

        if match:
            newfilename = match.group(1)
            errortype = match.group(2)

            # Broken links can't be fixed and
            # I am not sure what do with the local ones.
            if errortype.lower() in ["broken", "local"]:
                print("Not Fixed: " + line)
            else:
                # If this is a new file
                if newfilename != _filename:
                    # Update the previous file
                    if _filename:
                        Path(_filename).write_text(_contents, encoding="utf-8")

                    _filename = newfilename

                    # Read the new file to memory
                    _contents = Path(_filename).read_text(encoding="utf-8")

                _contents = _contents.replace(match.group(3), match.group(4))
        else:
            # We don't understand what the current line means!
            print("Not Understood: " + line)


if __name__ == "__main__":
    main()
