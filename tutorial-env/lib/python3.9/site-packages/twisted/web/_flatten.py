# -*- test-case-name: twisted.web.test.test_flatten,twisted.web.test.test_template -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Context-free flattener/serializer for rendering Python objects, possibly
complex or arbitrarily nested, as strings.
"""


from inspect import iscoroutine
from io import BytesIO
from sys import exc_info
from traceback import extract_tb
from types import GeneratorType
from typing import (
    Any,
    Callable,
    Coroutine,
    Generator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from twisted.internet.defer import Deferred, ensureDeferred
from twisted.python.compat import nativeString
from twisted.python.failure import Failure
from twisted.web._stan import CDATA, CharRef, Comment, Tag, slot, voidElements
from twisted.web.error import FlattenerError, UnfilledSlot, UnsupportedType
from twisted.web.iweb import IRenderable, IRequest

T = TypeVar("T")

FlattenableRecursive = Any
"""
For documentation purposes, read C{FlattenableRecursive} as L{Flattenable}.
However, since mypy doesn't support recursive type definitions (yet?),
we'll put Any in the actual definition.
"""

Flattenable = Union[
    bytes,
    str,
    slot,
    CDATA,
    Comment,
    Tag,
    Tuple[FlattenableRecursive, ...],
    List[FlattenableRecursive],
    Generator[FlattenableRecursive, None, None],
    CharRef,
    Deferred[FlattenableRecursive],
    Coroutine[Deferred[FlattenableRecursive], object, FlattenableRecursive],
    IRenderable,
]
"""
Type alias containing all types that can be flattened by L{flatten()}.
"""

# The maximum number of bytes to synchronously accumulate in the flattener
# buffer before delivering them onwards.
BUFFER_SIZE = 2 ** 16


def escapeForContent(data: Union[bytes, str]) -> bytes:
    """
    Escape some character or UTF-8 byte data for inclusion in an HTML or XML
    document, by replacing metacharacters (C{&<>}) with their entity
    equivalents (C{&amp;&lt;&gt;}).

    This is used as an input to L{_flattenElement}'s C{dataEscaper} parameter.

    @param data: The string to escape.

    @return: The quoted form of C{data}.  If C{data} is L{str}, return a utf-8
        encoded string.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    data = data.replace(b"&", b"&amp;").replace(b"<", b"&lt;").replace(b">", b"&gt;")
    return data


def attributeEscapingDoneOutside(data: Union[bytes, str]) -> bytes:
    """
    Escape some character or UTF-8 byte data for inclusion in the top level of
    an attribute.  L{attributeEscapingDoneOutside} actually passes the data
    through unchanged, because L{writeWithAttributeEscaping} handles the
    quoting of the text within attributes outside the generator returned by
    L{_flattenElement}; this is used as the C{dataEscaper} argument to that
    L{_flattenElement} call so that that generator does not redundantly escape
    its text output.

    @param data: The string to escape.

    @return: The string, unchanged, except for encoding.
    """
    if isinstance(data, str):
        return data.encode("utf-8")
    return data


def writeWithAttributeEscaping(
    write: Callable[[bytes], object]
) -> Callable[[bytes], None]:
    """
    Decorate a C{write} callable so that all output written is properly quoted
    for inclusion within an XML attribute value.

    If a L{Tag <twisted.web.template.Tag>} C{x} is flattened within the context
    of the contents of another L{Tag <twisted.web.template.Tag>} C{y}, the
    metacharacters (C{<>&"}) delimiting C{x} should be passed through
    unchanged, but the textual content of C{x} should still be quoted, as
    usual.  For example: C{<y><x>&amp;</x></y>}.  That is the default behavior
    of L{_flattenElement} when L{escapeForContent} is passed as the
    C{dataEscaper}.

    However, when a L{Tag <twisted.web.template.Tag>} C{x} is flattened within
    the context of an I{attribute} of another L{Tag <twisted.web.template.Tag>}
    C{y}, then the metacharacters delimiting C{x} should be quoted so that it
    can be parsed from the attribute's value.  In the DOM itself, this is not a
    valid thing to do, but given that renderers and slots may be freely moved
    around in a L{twisted.web.template} template, it is a condition which may
    arise in a document and must be handled in a way which produces valid
    output.  So, for example, you should be able to get C{<y attr="&lt;x /&gt;"
    />}.  This should also be true for other XML/HTML meta-constructs such as
    comments and CDATA, so if you were to serialize a L{comment
    <twisted.web.template.Comment>} in an attribute you should get C{<y
    attr="&lt;-- comment --&gt;" />}.  Therefore in order to capture these
    meta-characters, flattening is done with C{write} callable that is wrapped
    with L{writeWithAttributeEscaping}.

    The final case, and hopefully the much more common one as compared to
    serializing L{Tag <twisted.web.template.Tag>} and arbitrary L{IRenderable}
    objects within an attribute, is to serialize a simple string, and those
    should be passed through for L{writeWithAttributeEscaping} to quote
    without applying a second, redundant level of quoting.

    @param write: A callable which will be invoked with the escaped L{bytes}.

    @return: A callable that writes data with escaping.
    """

    def _write(data: bytes) -> None:
        write(escapeForContent(data).replace(b'"', b"&quot;"))

    return _write


def escapedCDATA(data: Union[bytes, str]) -> bytes:
    """
    Escape CDATA for inclusion in a document.

    @param data: The string to escape.

    @return: The quoted form of C{data}. If C{data} is unicode, return a utf-8
        encoded string.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return data.replace(b"]]>", b"]]]]><![CDATA[>")


def escapedComment(data: Union[bytes, str]) -> bytes:
    """
    Escape a comment for inclusion in a document.

    @param data: The string to escape.

    @return: The quoted form of C{data}. If C{data} is unicode, return a utf-8
        encoded string.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    data = data.replace(b"--", b"- - ").replace(b">", b"&gt;")
    if data and data[-1:] == b"-":
        data += b" "
    return data


def _getSlotValue(
    name: str,
    slotData: Sequence[Optional[Mapping[str, Flattenable]]],
    default: Optional[Flattenable] = None,
) -> Flattenable:
    """
    Find the value of the named slot in the given stack of slot data.
    """
    for slotFrame in slotData[::-1]:
        if slotFrame is not None and name in slotFrame:
            return slotFrame[name]
    else:
        if default is not None:
            return default
        raise UnfilledSlot(name)


def _fork(d: Deferred[T]) -> Deferred[T]:
    """
    Create a new L{Deferred} based on C{d} that will fire and fail with C{d}'s
    result or error, but will not modify C{d}'s callback type.
    """
    d2: Deferred[T] = Deferred(lambda _: d.cancel())

    def callback(result: T) -> T:
        d2.callback(result)
        return result

    def errback(failure: Failure) -> Failure:
        d2.errback(failure)
        return failure

    d.addCallbacks(callback, errback)
    return d2


def _flattenElement(
    request: Optional[IRequest],
    root: Flattenable,
    write: Callable[[bytes], object],
    slotData: List[Optional[Mapping[str, Flattenable]]],
    renderFactory: Optional[IRenderable],
    dataEscaper: Callable[[Union[bytes, str]], bytes],
    # This is annotated as Generator[T, None, None] instead of Iterator[T]
    # because mypy does not consider an Iterator to be an instance of
    # GeneratorType.
) -> Generator[Union[Generator, Deferred[Flattenable]], None, None]:
    """
    Make C{root} slightly more flat by yielding all its immediate contents as
    strings, deferreds or generators that are recursive calls to itself.

    @param request: A request object which will be passed to
        L{IRenderable.render}.

    @param root: An object to be made flatter.  This may be of type C{unicode},
        L{str}, L{slot}, L{Tag <twisted.web.template.Tag>}, L{tuple}, L{list},
        L{types.GeneratorType}, L{Deferred}, or an object that implements
        L{IRenderable}.

    @param write: A callable which will be invoked with each L{bytes} produced
        by flattening C{root}.

    @param slotData: A L{list} of L{dict} mapping L{str} slot names to data
        with which those slots will be replaced.

    @param renderFactory: If not L{None}, an object that provides
        L{IRenderable}.

    @param dataEscaper: A 1-argument callable which takes L{bytes} or
        L{unicode} and returns L{bytes}, quoted as appropriate for the
        rendering context.  This is really only one of two values:
        L{attributeEscapingDoneOutside} or L{escapeForContent}, depending on
        whether the rendering context is within an attribute or not.  See the
        explanation in L{writeWithAttributeEscaping}.

    @return: An iterator that eventually writes L{bytes} to C{write}.
        It can yield other iterators or L{Deferred}s; if it yields another
        iterator, the caller will iterate it; if it yields a L{Deferred},
        the result of that L{Deferred} will be another generator, in which
        case it is iterated.  See L{_flattenTree} for the trampoline that
        consumes said values.
    """

    def keepGoing(
        newRoot: Flattenable,
        dataEscaper: Callable[[Union[bytes, str]], bytes] = dataEscaper,
        renderFactory: Optional[IRenderable] = renderFactory,
        write: Callable[[bytes], object] = write,
    ) -> Generator[Union[Generator, Deferred[Generator]], None, None]:
        return _flattenElement(
            request, newRoot, write, slotData, renderFactory, dataEscaper
        )

    def keepGoingAsync(result: Deferred[Flattenable]) -> Deferred[Flattenable]:
        return result.addCallback(keepGoing)

    if isinstance(root, (bytes, str)):
        write(dataEscaper(root))
    elif isinstance(root, slot):
        slotValue = _getSlotValue(root.name, slotData, root.default)
        yield keepGoing(slotValue)
    elif isinstance(root, CDATA):
        write(b"<![CDATA[")
        write(escapedCDATA(root.data))
        write(b"]]>")
    elif isinstance(root, Comment):
        write(b"<!--")
        write(escapedComment(root.data))
        write(b"-->")
    elif isinstance(root, Tag):
        slotData.append(root.slotData)
        rendererName = root.render
        if rendererName is not None:
            if renderFactory is None:
                raise ValueError(
                    f'Tag wants to be rendered by method "{rendererName}" '
                    f"but is not contained in any IRenderable"
                )
            rootClone = root.clone(False)
            rootClone.render = None
            renderMethod = renderFactory.lookupRenderMethod(rendererName)
            result = renderMethod(request, rootClone)
            yield keepGoing(result)
            slotData.pop()
            return

        if not root.tagName:
            yield keepGoing(root.children)
            return

        write(b"<")
        if isinstance(root.tagName, str):
            tagName = root.tagName.encode("ascii")
        else:
            tagName = root.tagName
        write(tagName)
        for k, v in root.attributes.items():
            if isinstance(k, str):
                k = k.encode("ascii")
            write(b" " + k + b'="')
            # Serialize the contents of the attribute, wrapping the results of
            # that serialization so that _everything_ is quoted.
            yield keepGoing(
                v, attributeEscapingDoneOutside, write=writeWithAttributeEscaping(write)
            )
            write(b'"')
        if root.children or nativeString(tagName) not in voidElements:
            write(b">")
            # Regardless of whether we're in an attribute or not, switch back
            # to the escapeForContent dataEscaper.  The contents of a tag must
            # be quoted no matter what; in the top-level document, just so
            # they're valid, and if they're within an attribute, they have to
            # be quoted so that after applying the *un*-quoting required to re-
            # parse the tag within the attribute, all the quoting is still
            # correct.
            yield keepGoing(root.children, escapeForContent)
            write(b"</" + tagName + b">")
        else:
            write(b" />")

    elif isinstance(root, (tuple, list, GeneratorType)):
        for element in root:
            yield keepGoing(element)
    elif isinstance(root, CharRef):
        escaped = "&#%d;" % (root.ordinal,)
        write(escaped.encode("ascii"))
    elif isinstance(root, Deferred):
        yield keepGoingAsync(_fork(root))
    elif iscoroutine(root):
        yield keepGoingAsync(
            Deferred.fromCoroutine(
                cast(Coroutine[Deferred[Flattenable], object, Flattenable], root)
            )
        )
    elif IRenderable.providedBy(root):
        result = root.render(request)
        yield keepGoing(result, renderFactory=root)
    else:
        raise UnsupportedType(root)


async def _flattenTree(
    request: Optional[IRequest], root: Flattenable, write: Callable[[bytes], object]
) -> None:
    """
    Make C{root} into an iterable of L{bytes} and L{Deferred} by doing a depth
    first traversal of the tree.

    @param request: A request object which will be passed to
        L{IRenderable.render}.

    @param root: An object to be made flatter.  This may be of type C{unicode},
        L{bytes}, L{slot}, L{Tag <twisted.web.template.Tag>}, L{tuple},
        L{list}, L{types.GeneratorType}, L{Deferred}, or something providing
        L{IRenderable}.

    @param write: A callable which will be invoked with each L{bytes} produced
        by flattening C{root}.

    @return: A C{Deferred}-returning coroutine that resolves to C{None}.
    """
    buf = []
    bufSize = 0

    # Accumulate some bytes up to the buffer size so that we don't annoy the
    # upstream writer with a million tiny string.
    def bufferedWrite(bs: bytes) -> None:
        nonlocal bufSize
        buf.append(bs)
        bufSize += len(bs)
        if bufSize >= BUFFER_SIZE:
            flushBuffer()

    # Deliver the buffered content to the upstream writer as a single string.
    # This is how a "big enough" buffer gets delivered, how a buffer of any
    # size is delivered before execution is suspended to wait for an
    # asynchronous value, and how anything left in the buffer when we're
    # finished is delivered.
    def flushBuffer() -> None:
        nonlocal bufSize
        if bufSize > 0:
            write(b"".join(buf))
            del buf[:]
            bufSize = 0

    stack: List[Generator] = [
        _flattenElement(request, root, bufferedWrite, [], None, escapeForContent)
    ]

    while stack:
        try:
            frame = stack[-1].gi_frame
            element = next(stack[-1])
            if isinstance(element, Deferred):
                # Before suspending flattening for an unknown amount of time,
                # flush whatever data we have collected so far.
                flushBuffer()
                element = await element
        except StopIteration:
            stack.pop()
        except Exception as e:
            stack.pop()
            roots = []
            for generator in stack:
                roots.append(generator.gi_frame.f_locals["root"])
            roots.append(frame.f_locals["root"])
            raise FlattenerError(e, roots, extract_tb(exc_info()[2]))
        else:
            stack.append(element)

    # Flush any data that remains in the buffer before finishing.
    flushBuffer()


def flatten(
    request: Optional[IRequest], root: Flattenable, write: Callable[[bytes], object]
) -> Deferred[None]:
    """
    Incrementally write out a string representation of C{root} using C{write}.

    In order to create a string representation, C{root} will be decomposed into
    simpler objects which will themselves be decomposed and so on until strings
    or objects which can easily be converted to strings are encountered.

    @param request: A request object which will be passed to the C{render}
        method of any L{IRenderable} provider which is encountered.

    @param root: An object to be made flatter.  This may be of type L{str},
        L{bytes}, L{slot}, L{Tag <twisted.web.template.Tag>}, L{tuple},
        L{list}, L{types.GeneratorType}, L{Deferred}, or something that
        provides L{IRenderable}.

    @param write: A callable which will be invoked with each L{bytes} produced
        by flattening C{root}.

    @return: A L{Deferred} which will be called back with C{None} when C{root}
        has been completely flattened into C{write} or which will be errbacked
        if an unexpected exception occurs.
    """
    return ensureDeferred(_flattenTree(request, root, write))


def flattenString(request: Optional[IRequest], root: Flattenable) -> Deferred[bytes]:
    """
    Collate a string representation of C{root} into a single string.

    This is basically gluing L{flatten} to an L{io.BytesIO} and returning
    the results. See L{flatten} for the exact meanings of C{request} and
    C{root}.

    @return: A L{Deferred} which will be called back with a single UTF-8 encoded
        string as its result when C{root} has been completely flattened or which
        will be errbacked if an unexpected exception occurs.
    """
    io = BytesIO()
    d = flatten(request, root, io.write)
    d.addCallback(lambda _: io.getvalue())
    return cast(Deferred[bytes], d)
