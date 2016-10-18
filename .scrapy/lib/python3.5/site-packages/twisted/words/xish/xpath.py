# -*- test-case-name: twisted.words.test.test_xpath -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
XPath query support.

This module provides L{XPathQuery} to match
L{domish.Element<twisted.words.xish.domish.Element>} instances against
XPath-like expressions.
"""

from __future__ import absolute_import, division

from io import StringIO

from twisted.python.compat import StringType, unicode

class LiteralValue(unicode):
    def value(self, elem):
        return self


class IndexValue:
    def __init__(self, index):
        self.index = int(index) - 1

    def value(self, elem):
        return elem.children[self.index]


class AttribValue:
    def __init__(self, attribname):
        self.attribname = attribname
        if self.attribname == "xmlns":
            self.value = self.value_ns

    def value_ns(self, elem):
        return elem.uri

    def value(self, elem):
        if self.attribname in elem.attributes:
            return elem.attributes[self.attribname]
        else:
            return None


class CompareValue:
    def __init__(self, lhs, op, rhs):
        self.lhs = lhs
        self.rhs = rhs
        if op == "=":
            self.value = self._compareEqual
        else:
            self.value = self._compareNotEqual

    def _compareEqual(self, elem):
        return self.lhs.value(elem) == self.rhs.value(elem)

    def _compareNotEqual(self, elem):
        return self.lhs.value(elem) != self.rhs.value(elem)


class BooleanValue:
    """
    Provide boolean XPath expression operators.

    @ivar lhs: Left hand side expression of the operator.
    @ivar op: The operator. One of C{'and'}, C{'or'}.
    @ivar rhs: Right hand side expression of the operator.
    @ivar value: Reference to the method that will calculate the value of
                 this expression given an element.
    """
    def __init__(self, lhs, op, rhs):
        self.lhs = lhs
        self.rhs = rhs
        if op == "and":
            self.value = self._booleanAnd
        else:
            self.value = self._booleanOr

    def _booleanAnd(self, elem):
        """
        Calculate boolean and of the given expressions given an element.

        @param elem: The element to calculate the value of the expression from.
        """
        return self.lhs.value(elem) and self.rhs.value(elem)

    def _booleanOr(self, elem):
        """
        Calculate boolean or of the given expressions given an element.

        @param elem: The element to calculate the value of the expression from.
        """
        return self.lhs.value(elem) or self.rhs.value(elem)


def Function(fname):
    """
    Internal method which selects the function object
    """
    klassname = "_%s_Function" % fname
    c = globals()[klassname]()
    return c


class _not_Function:
    def __init__(self):
        self.baseValue = None

    def setParams(self, baseValue):
        self.baseValue = baseValue

    def value(self, elem):
        return not self.baseValue.value(elem)


class _text_Function:
    def setParams(self):
        pass

    def value(self, elem):
        return unicode(elem)


class _Location:
    def __init__(self):
        self.predicates = []
        self.elementName  = None
        self.childLocation = None

    def matchesPredicates(self, elem):
        if self.elementName != None and self.elementName != elem.name:
            return 0

        for p in self.predicates:
            if not p.value(elem):
                return 0

        return 1

    def matches(self, elem):
        if not self.matchesPredicates(elem):
            return 0

        if self.childLocation != None:
            for c in elem.elements():
                if self.childLocation.matches(c):
                    return 1
        else:
            return 1

        return 0

    def queryForString(self, elem, resultbuf):
        if not self.matchesPredicates(elem):
            return

        if self.childLocation != None:
            for c in elem.elements():
                self.childLocation.queryForString(c, resultbuf)
        else:
            resultbuf.write(unicode(elem))

    def queryForNodes(self, elem, resultlist):
        if not self.matchesPredicates(elem):
            return

        if self.childLocation != None:
            for c in elem.elements():
                self.childLocation.queryForNodes(c, resultlist)
        else:
            resultlist.append(elem)

    def queryForStringList(self, elem, resultlist):
        if not self.matchesPredicates(elem):
            return

        if self.childLocation != None:
            for c in elem.elements():
                self.childLocation.queryForStringList(c, resultlist)
        else:
            for c in elem.children:
                if isinstance(c, StringType):
                    resultlist.append(c)


class _AnyLocation:
    def __init__(self):
        self.predicates = []
        self.elementName = None
        self.childLocation = None

    def matchesPredicates(self, elem):
        for p in self.predicates:
            if not p.value(elem):
                return 0
        return 1

    def listParents(self, elem, parentlist):
        if elem.parent != None:
            self.listParents(elem.parent, parentlist)
        parentlist.append(elem.name)

    def isRootMatch(self, elem):
        if (self.elementName == None or self.elementName == elem.name) and \
           self.matchesPredicates(elem):
            if self.childLocation != None:
                for c in elem.elements():
                    if self.childLocation.matches(c):
                        return True
            else:
                return True
        return False

    def findFirstRootMatch(self, elem):
        if (self.elementName == None or self.elementName == elem.name) and \
           self.matchesPredicates(elem):
            # Thus far, the name matches and the predicates match,
            # now check into the children and find the first one
            # that matches the rest of the structure
            # the rest of the structure
            if self.childLocation != None:
                for c in elem.elements():
                    if self.childLocation.matches(c):
                        return c
                return None
            else:
                # No children locations; this is a match!
                return elem
        else:
            # Ok, predicates or name didn't match, so we need to start
            # down each child and treat it as the root and try
            # again
            for c in elem.elements():
                if self.matches(c):
                    return c
            # No children matched...
            return None

    def matches(self, elem):
        if self.isRootMatch(elem):
            return True
        else:
            # Ok, initial element isn't an exact match, walk
            # down each child and treat it as the root and try
            # again
            for c in elem.elements():
                if self.matches(c):
                    return True
            # No children matched...
            return False

    def queryForString(self, elem, resultbuf):
        raise NotImplementedError(
            "queryForString is not implemented for any location")

    def queryForNodes(self, elem, resultlist):
        # First check to see if _this_ element is a root
        if self.isRootMatch(elem):
            resultlist.append(elem)

        # Now check each child
        for c in elem.elements():
            self.queryForNodes(c, resultlist)


    def queryForStringList(self, elem, resultlist):
        if self.isRootMatch(elem):
            for c in elem.children:
                if isinstance(c, StringType):
                    resultlist.append(c)
        for c in elem.elements():
            self.queryForStringList(c, resultlist)


class XPathQuery:
    def __init__(self, queryStr):
        self.queryStr = queryStr
        # Prevent a circular import issue, as xpathparser imports this module.
        from twisted.words.xish.xpathparser import (XPathParser,
                                                    XPathParserScanner)
        parser = XPathParser(XPathParserScanner(queryStr))
        self.baseLocation = getattr(parser, 'XPATH')()

    def __hash__(self):
        return self.queryStr.__hash__()

    def matches(self, elem):
        return self.baseLocation.matches(elem)

    def queryForString(self, elem):
        result = StringIO()
        self.baseLocation.queryForString(elem, result)
        return result.getvalue()

    def queryForNodes(self, elem):
        result = []
        self.baseLocation.queryForNodes(elem, result)
        if len(result) == 0:
            return None
        else:
            return result

    def queryForStringList(self, elem):
        result = []
        self.baseLocation.queryForStringList(elem, result)
        if len(result) == 0:
            return None
        else:
            return result


__internedQueries = {}

def internQuery(queryString):
    if queryString not in __internedQueries:
        __internedQueries[queryString] = XPathQuery(queryString)
    return __internedQueries[queryString]


def matches(xpathstr, elem):
    return internQuery(xpathstr).matches(elem)


def queryForStringList(xpathstr, elem):
    return internQuery(xpathstr).queryForStringList(elem)


def queryForString(xpathstr, elem):
    return internQuery(xpathstr).queryForString(elem)


def queryForNodes(xpathstr, elem):
    return internQuery(xpathstr).queryForNodes(elem)
