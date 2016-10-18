# -*- test-case-name: twisted.test.test_text -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Miscellany of text-munging functions.
"""


def stringyString(object, indentation=''):
    """
    Expansive string formatting for sequence types.

    C{list.__str__} and C{dict.__str__} use C{repr()} to display their
    elements.  This function also turns these sequence types
    into strings, but uses C{str()} on their elements instead.

    Sequence elements are also displayed on separate lines, and nested
    sequences have nested indentation.
    """
    braces = ''
    sl = []

    if type(object) is dict:
        braces = '{}'
        for key, value in object.items():
            value = stringyString(value, indentation + '   ')
            if isMultiline(value):
                if endsInNewline(value):
                    value = value[:-len('\n')]
                sl.append("%s %s:\n%s" % (indentation, key, value))
            else:
                # Oops.  Will have to move that indentation.
                sl.append("%s %s: %s" % (indentation, key,
                                         value[len(indentation) + 3:]))

    elif type(object) is tuple or type(object) is list:
        if type(object) is tuple:
            braces = '()'
        else:
            braces = '[]'

        for element in object:
            element = stringyString(element, indentation + ' ')
            sl.append(element.rstrip() + ',')
    else:
        sl[:] = map(lambda s, i=indentation: i + s,
                   str(object).split('\n'))

    if not sl:
        sl.append(indentation)

    if braces:
        sl[0] = indentation + braces[0] + sl[0][len(indentation) + 1:]
        sl[-1] = sl[-1] + braces[-1]

    s = "\n".join(sl)

    if isMultiline(s) and not endsInNewline(s):
        s = s + '\n'

    return s


def isMultiline(s):
    """
    Returns C{True} if this string has a newline in it.
    """
    return (s.find('\n') != -1)


def endsInNewline(s):
    """
    Returns C{True} if this string ends in a newline.
    """
    return (s[-len('\n'):] == '\n')


def greedyWrap(inString, width=80):
    """
    Given a string and a column width, return a list of lines.

    Caveat: I'm use a stupid greedy word-wrapping
    algorythm.  I won't put two spaces at the end
    of a sentence.  I don't do full justification.
    And no, I've never even *heard* of hypenation.
    """

    outLines = []

    #eww, evil hacks to allow paragraphs delimited by two \ns :(
    if inString.find('\n\n') >= 0:
        paragraphs = inString.split('\n\n')
        for para in paragraphs:
            outLines.extend(greedyWrap(para, width) + [''])
        return outLines
    inWords = inString.split()

    column = 0
    ptr_line = 0
    while inWords:
        column = column + len(inWords[ptr_line])
        ptr_line = ptr_line + 1

        if (column > width):
            if ptr_line == 1:
                # This single word is too long, it will be the whole line.
                pass
            else:
                # We've gone too far, stop the line one word back.
                ptr_line = ptr_line - 1
            (l, inWords) = (inWords[0:ptr_line], inWords[ptr_line:])
            outLines.append(' '.join(l))

            ptr_line = 0
            column = 0
        elif not (len(inWords) > ptr_line):
            # Clean up the last bit.
            outLines.append(' '.join(inWords))
            del inWords[:]
        else:
            # Space
            column = column + 1
    # next word

    return outLines


wordWrap = greedyWrap


def removeLeadingBlanks(lines):
    ret = []
    for line in lines:
        if ret or line.strip():
            ret.append(line)
    return ret


def removeLeadingTrailingBlanks(s):
    lines = removeLeadingBlanks(s.split('\n'))
    lines.reverse()
    lines = removeLeadingBlanks(lines)
    lines.reverse()
    return '\n'.join(lines)+'\n'


def splitQuoted(s):
    """
    Like a string split, but don't break substrings inside quotes.

    >>> splitQuoted('the "hairy monkey" likes pie')
    ['the', 'hairy monkey', 'likes', 'pie']

    Another one of those "someone must have a better solution for
    this" things.  This implementation is a VERY DUMB hack done too
    quickly.
    """
    out = []
    quot = None
    phrase = None
    for word in s.split():
        if phrase is None:
            if word and (word[0] in ("\"", "'")):
                quot = word[0]
                word = word[1:]
                phrase = []

        if phrase is None:
            out.append(word)
        else:
            if word and (word[-1] == quot):
                word = word[:-1]
                phrase.append(word)
                out.append(" ".join(phrase))
                phrase = None
            else:
                phrase.append(word)

    return out


def strFile(p, f, caseSensitive=True):
    """
    Find whether string C{p} occurs in a read()able object C{f}.

    @rtype: C{bool}
    """
    buf = type(p)()
    buf_len = max(len(p), 2**2**2**2)
    if not caseSensitive:
        p = p.lower()
    while 1:
        r = f.read(buf_len-len(p))
        if not caseSensitive:
            r = r.lower()
        bytes_read = len(r)
        if bytes_read == 0:
            return False
        l = len(buf)+bytes_read-buf_len
        if l <= 0:
            buf = buf + r
        else:
            buf = buf[l:] + r
        if buf.find(p) != -1:
            return True

