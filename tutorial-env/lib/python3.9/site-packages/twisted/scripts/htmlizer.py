# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#

"""
HTML pretty-printing for Python source code.
"""


__version__ = "$Revision: 1.8 $"[11:-2]

import os
import sys

from twisted import copyright
from twisted.python import htmlizer, usage

header = """<html><head>
<title>%(title)s</title>
<meta name=\"Generator\" content="%(generator)s" />
%(alternate)s
%(stylesheet)s
</head>
<body>
"""
footer = """</body>"""

styleLink = '<link rel="stylesheet" href="%s" type="text/css" />'
alternateLink = '<link rel="alternate" href="%(source)s" type="text/x-python" />'


class Options(usage.Options):
    synopsis = """{} [options] source.py
    """.format(
        os.path.basename(sys.argv[0]),
    )

    optParameters = [
        ("stylesheet", "s", None, "URL of stylesheet to link to."),
    ]

    compData = usage.Completions(
        extraActions=[usage.CompleteFiles("*.py", descr="source python file")]
    )

    def parseArgs(self, filename):
        self["filename"] = filename


def run():
    options = Options()
    try:
        options.parseOptions()
    except usage.UsageError as e:
        print(str(e))
        sys.exit(1)
    filename = options["filename"]
    if options.get("stylesheet") is not None:
        stylesheet = styleLink % (options["stylesheet"],)
    else:
        stylesheet = ""

    with open(filename + ".html", "wb") as output:
        outHeader = header % {
            "title": filename,
            "generator": f"htmlizer/{copyright.longversion}",
            "alternate": alternateLink % {"source": filename},
            "stylesheet": stylesheet,
        }
        output.write(outHeader.encode("utf-8"))
        with open(filename, "rb") as f:
            htmlizer.filter(f, output, htmlizer.SmallerHTMLWriter)
        output.write(footer.encode("utf-8"))
