# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
I am a simple test resource.
"""


from twisted.web import static


class Test(static.Data):
    isLeaf = True

    def __init__(self):
        static.Data.__init__(
            self,
            b"""
            <html>
            <head><title>Twisted Web Demo</title><head>
            <body>
            Hello! This is a Twisted Web test page.
            </body>
            </html>
            """,
            "text/html",
        )
