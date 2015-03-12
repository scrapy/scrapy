#!/usr/bin/python

"""

Linkfix - a companion to sphinx's linkcheck builder.

Uses the linkcheck's output file to fix links in docs.

Originally created for this issue:
https://github.com/scrapy/scrapy/issues/606

Author: dufferzafar
"""

import re

# Used for remembering the file (and its contents)
# so we don't have to open the same file again.
_filename = None
_contents = None

# A regex that matches standard linkcheck output lines
line_re = re.compile(ur'(.*)\:\d+\:\s\[(.*)\]\s(?:(.*)\sto\s(.*)|(.*))')

# Read lines from the linkcheck output file
try:
    with open("build/linkcheck/output.txt") as out:
        output_lines = out.readlines()
except IOError:
    print("linkcheck output not found; please run linkcheck first.")
    exit(1)

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
                    with open(_filename, "w") as _file:
                        _file.write(_contents)

                _filename = newfilename

                # Read the new file to memory
                with open(_filename) as _file:
                    _contents = _file.read()

            _contents = _contents.replace(match.group(3), match.group(4))
    else:
        # We don't understand what the current line means!
        print("Not Understood: " + line)
