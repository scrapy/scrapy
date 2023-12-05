# -*- test-case-name: twisted.web.test.test_domhelpers -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A library for performing interesting tasks with DOM objects.
"""

from io import StringIO

from twisted.web import microdom
from twisted.web.microdom import escape, getElementsByTagName, unescape

# These modules are imported here as a shortcut.
escape
getElementsByTagName


class NodeLookupError(Exception):
    pass


def substitute(request, node, subs):
    """
    Look through the given node's children for strings, and
    attempt to do string substitution with the given parameter.
    """
    for child in node.childNodes:
        if hasattr(child, "nodeValue") and child.nodeValue:
            child.replaceData(0, len(child.nodeValue), child.nodeValue % subs)
        substitute(request, child, subs)


def _get(node, nodeId, nodeAttrs=("id", "class", "model", "pattern")):
    """
    (internal) Get a node with the specified C{nodeId} as any of the C{class},
    C{id} or C{pattern} attributes.
    """

    if hasattr(node, "hasAttributes") and node.hasAttributes():
        for nodeAttr in nodeAttrs:
            if str(node.getAttribute(nodeAttr)) == nodeId:
                return node
    if node.hasChildNodes():
        if hasattr(node.childNodes, "length"):
            length = node.childNodes.length
        else:
            length = len(node.childNodes)
        for childNum in range(length):
            result = _get(node.childNodes[childNum], nodeId)
            if result:
                return result


def get(node, nodeId):
    """
    Get a node with the specified C{nodeId} as any of the C{class},
    C{id} or C{pattern} attributes. If there is no such node, raise
    L{NodeLookupError}.
    """
    result = _get(node, nodeId)
    if result:
        return result
    raise NodeLookupError(nodeId)


def getIfExists(node, nodeId):
    """
    Get a node with the specified C{nodeId} as any of the C{class},
    C{id} or C{pattern} attributes.  If there is no such node, return
    L{None}.
    """
    return _get(node, nodeId)


def getAndClear(node, nodeId):
    """Get a node with the specified C{nodeId} as any of the C{class},
    C{id} or C{pattern} attributes. If there is no such node, raise
    L{NodeLookupError}. Remove all child nodes before returning.
    """
    result = get(node, nodeId)
    if result:
        clearNode(result)
    return result


def clearNode(node):
    """
    Remove all children from the given node.
    """
    node.childNodes[:] = []


def locateNodes(nodeList, key, value, noNesting=1):
    """
    Find subnodes in the given node where the given attribute
    has the given value.
    """
    returnList = []
    if not isinstance(nodeList, type([])):
        return locateNodes(nodeList.childNodes, key, value, noNesting)
    for childNode in nodeList:
        if not hasattr(childNode, "getAttribute"):
            continue
        if str(childNode.getAttribute(key)) == value:
            returnList.append(childNode)
            if noNesting:
                continue
        returnList.extend(locateNodes(childNode, key, value, noNesting))
    return returnList


def superSetAttribute(node, key, value):
    if not hasattr(node, "setAttribute"):
        return
    node.setAttribute(key, value)
    if node.hasChildNodes():
        for child in node.childNodes:
            superSetAttribute(child, key, value)


def superPrependAttribute(node, key, value):
    if not hasattr(node, "setAttribute"):
        return
    old = node.getAttribute(key)
    if old:
        node.setAttribute(key, value + "/" + old)
    else:
        node.setAttribute(key, value)
    if node.hasChildNodes():
        for child in node.childNodes:
            superPrependAttribute(child, key, value)


def superAppendAttribute(node, key, value):
    if not hasattr(node, "setAttribute"):
        return
    old = node.getAttribute(key)
    if old:
        node.setAttribute(key, old + "/" + value)
    else:
        node.setAttribute(key, value)
    if node.hasChildNodes():
        for child in node.childNodes:
            superAppendAttribute(child, key, value)


def gatherTextNodes(iNode, dounescape=0, joinWith=""):
    """Visit each child node and collect its text data, if any, into a string.
    For example::
        >>> doc=microdom.parseString('<a>1<b>2<c>3</c>4</b></a>')
        >>> gatherTextNodes(doc.documentElement)
        '1234'
    With dounescape=1, also convert entities back into normal characters.
    @return: the gathered nodes as a single string
    @rtype: str"""
    gathered = []
    gathered_append = gathered.append
    slice = [iNode]
    while len(slice) > 0:
        c = slice.pop(0)
        if hasattr(c, "nodeValue") and c.nodeValue is not None:
            if dounescape:
                val = unescape(c.nodeValue)
            else:
                val = c.nodeValue
            gathered_append(val)
        slice[:0] = c.childNodes
    return joinWith.join(gathered)


class RawText(microdom.Text):
    """This is an evil and horrible speed hack. Basically, if you have a big
    chunk of XML that you want to insert into the DOM, but you don't want to
    incur the cost of parsing it, you can construct one of these and insert it
    into the DOM. This will most certainly only work with microdom as the API
    for converting nodes to xml is different in every DOM implementation.

    This could be improved by making this class a Lazy parser, so if you
    inserted this into the DOM and then later actually tried to mutate this
    node, it would be parsed then.
    """

    def writexml(
        self,
        writer,
        indent="",
        addindent="",
        newl="",
        strip=0,
        nsprefixes=None,
        namespace=None,
    ):
        writer.write(f"{indent}{self.data}{newl}")


def findNodes(parent, matcher, accum=None):
    if accum is None:
        accum = []
    if not parent.hasChildNodes():
        return accum
    for child in parent.childNodes:
        # print child, child.nodeType, child.nodeName
        if matcher(child):
            accum.append(child)
        findNodes(child, matcher, accum)
    return accum


def findNodesShallowOnMatch(parent, matcher, recurseMatcher, accum=None):
    if accum is None:
        accum = []
    if not parent.hasChildNodes():
        return accum
    for child in parent.childNodes:
        # print child, child.nodeType, child.nodeName
        if matcher(child):
            accum.append(child)
        if recurseMatcher(child):
            findNodesShallowOnMatch(child, matcher, recurseMatcher, accum)
    return accum


def findNodesShallow(parent, matcher, accum=None):
    if accum is None:
        accum = []
    if not parent.hasChildNodes():
        return accum
    for child in parent.childNodes:
        if matcher(child):
            accum.append(child)
        else:
            findNodes(child, matcher, accum)
    return accum


def findElementsWithAttributeShallow(parent, attribute):
    """
    Return an iterable of the elements which are direct children of C{parent}
    and which have the C{attribute} attribute.
    """
    return findNodesShallow(
        parent,
        lambda n: getattr(n, "tagName", None) is not None and n.hasAttribute(attribute),
    )


def findElements(parent, matcher):
    """
    Return an iterable of the elements which are children of C{parent} for
    which the predicate C{matcher} returns true.
    """
    return findNodes(
        parent,
        lambda n, matcher=matcher: getattr(n, "tagName", None) is not None
        and matcher(n),
    )


def findElementsWithAttribute(parent, attribute, value=None):
    if value:
        return findElements(
            parent,
            lambda n, attribute=attribute, value=value: n.hasAttribute(attribute)
            and n.getAttribute(attribute) == value,
        )
    else:
        return findElements(
            parent, lambda n, attribute=attribute: n.hasAttribute(attribute)
        )


def findNodesNamed(parent, name):
    return findNodes(parent, lambda n, name=name: n.nodeName == name)


def writeNodeData(node, oldio):
    for subnode in node.childNodes:
        if hasattr(subnode, "data"):
            oldio.write("" + subnode.data)
        else:
            writeNodeData(subnode, oldio)


def getNodeText(node):
    oldio = StringIO()
    writeNodeData(node, oldio)
    return oldio.getvalue()


def getParents(node):
    l = []
    while node:
        l.append(node)
        node = node.parentNode
    return l


def namedChildren(parent, nodeName):
    """namedChildren(parent, nodeName) -> children (not descendants) of parent
    that have tagName == nodeName
    """
    return [n for n in parent.childNodes if getattr(n, "tagName", "") == nodeName]
