# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Generic sentence handling tools: hopefully reusable.
"""

from __future__ import absolute_import, division


class _BaseSentence(object):
    """
    A base sentence class for a particular protocol.

    Using this base class, specific sentence classes can almost automatically
    be created for a particular protocol.
    To do this, fill the ALLOWED_ATTRIBUTES class attribute using
    the C{getSentenceAttributes} class method of the producer::

        class FooSentence(BaseSentence):
            \"\"\"
            A sentence for integalactic transmodulator sentences.

            @ivar transmogrificationConstant: The value used in the
                transmogrifier while producing this sentence, corrected for
                gravitational fields.
            @type transmogrificationConstant: C{Tummy}
            \"\"\"
            ALLOWED_ATTRIBUTES = FooProtocol.getSentenceAttributes()

    @ivar presentAttribues: An iterable containing the names of the
        attributes that are present in this sentence.
    @type presentAttributes: iterable of C{str}

    @cvar ALLOWED_ATTRIBUTES: A set of attributes that are allowed in this
        sentence.
    @type ALLOWED_ATTRIBUTES: C{set} of C{str}
    """
    ALLOWED_ATTRIBUTES = set()


    def __init__(self, sentenceData):
        """
        Initializes a sentence with parsed sentence data.

        @param sentenceData: The parsed sentence data.
        @type sentenceData: C{dict} (C{str} -> C{str} or L{None})
        """
        self._sentenceData = sentenceData


    @property
    def presentAttributes(self):
        """
        An iterable containing the names of the attributes that are present in
        this sentence.

        @return: The iterable of names of present attributes.
        @rtype: iterable of C{str}
        """
        return iter(self._sentenceData)


    def __getattr__(self, name):
        """
        Gets an attribute of this sentence.
        """
        if name in self.ALLOWED_ATTRIBUTES:
            return self._sentenceData.get(name, None)
        else:
            className = self.__class__.__name__
            msg = "%s sentences have no %s attributes" % (className, name)
            raise AttributeError(msg)


    def __repr__(self):
        """
        Returns a textual representation of this sentence.

        @return: A textual representation of this sentence.
        @rtype: C{str}
        """
        items = self._sentenceData.items()
        data = ["%s: %s" % (k, v) for k, v in sorted(items) if k != "type"]
        dataRepr = ", ".join(data)

        typeRepr = self._sentenceData.get("type") or "unknown type"
        className = self.__class__.__name__

        return "<%s (%s) {%s}>" % (className, typeRepr, dataRepr)



class _PositioningSentenceProducerMixin(object):
    """
    A mixin for certain protocols that produce positioning sentences.

    This mixin helps protocols that store the layout of sentences that they
    consume in a C{_SENTENCE_CONTENTS} class variable provide all sentence
    attributes that can ever occur. It does this by providing a class method,
    C{getSentenceAttributes}, which iterates over all sentence types and
    collects the possible sentence attributes.
    """
    @classmethod
    def getSentenceAttributes(cls):
        """
        Returns a set of all attributes that might be found in the sentences
        produced by this protocol.

        This is basically a set of all the attributes of all the sentences that
        this protocol can produce.

        @return: The set of all possible sentence attribute names.
        @rtype: C{set} of C{str}
        """
        attributes = set(["type"])
        for attributeList in cls._SENTENCE_CONTENTS.values():
            for attribute in attributeList:
                if attribute is None:
                    continue
                attributes.add(attribute)

        return attributes
