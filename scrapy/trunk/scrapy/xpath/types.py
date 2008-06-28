class XPath(object):
    """A XPath expression"""

    def __init__(self, xpath_expr):
        self.expr = xpath_expr

    def __repr__(self):
        return "XPath(%s)" % repr(self.expr)

    def __str__(self):
        return self.expr
