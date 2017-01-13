# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
"""
Tests for positioning sentences.
"""

from __future__ import absolute_import, division

import itertools

from twisted.positioning import _sentence
from twisted.trial.unittest import TestCase


sentinelValueOne = "someStringValue"
sentinelValueTwo = "someOtherStringValue"



class DummyProtocol(object):
    """
    A simple, fake protocol.
    """
    @staticmethod
    def getSentenceAttributes():
        return ["type", sentinelValueOne, sentinelValueTwo]



class DummySentence(_sentence._BaseSentence):
    """
    A sentence for L{DummyProtocol}.
    """
    ALLOWED_ATTRIBUTES = DummyProtocol.getSentenceAttributes()



class MixinProtocol(_sentence._PositioningSentenceProducerMixin):
    """
    A simple, fake protocol that declaratively tells you the sentences
    it produces using L{base.PositioningSentenceProducerMixin}.
    """
    _SENTENCE_CONTENTS = {
        None: [
            sentinelValueOne,
            sentinelValueTwo,
            None  # See MixinTests.test_noNoneInSentenceAttributes
        ],
    }



class MixinSentence(_sentence._BaseSentence):
    """
    A sentence for L{MixinProtocol}.
    """
    ALLOWED_ATTRIBUTES = MixinProtocol.getSentenceAttributes()



class SentenceTestsMixin(object):
    """
    Tests for positioning protocols and their respective sentences.
    """
    def test_attributeAccess(self):
        """
        A sentence attribute gets the correct value, and accessing an
        unset attribute (which is specified as being a valid sentence
        attribute) gets L{None}.
        """
        thisSentinel = object()
        sentence = self.sentenceClass({sentinelValueOne: thisSentinel})
        self.assertEqual(getattr(sentence, sentinelValueOne), thisSentinel)
        self.assertIsNone(getattr(sentence, sentinelValueTwo))


    def test_raiseOnMissingAttributeAccess(self):
        """
        Accessing a nonexistent attribute raises C{AttributeError}.
        """
        sentence = self.sentenceClass({})
        self.assertRaises(AttributeError, getattr, sentence, "BOGUS")


    def test_raiseOnBadAttributeAccess(self):
        """
        Accessing bogus attributes raises C{AttributeError}, *even*
        when that attribute actually is in the sentence data.
        """
        sentence = self.sentenceClass({"BOGUS": None})
        self.assertRaises(AttributeError, getattr, sentence, "BOGUS")


    sentenceType = "tummies"
    reprTemplate = "<%s (%s) {%s}>"


    def _expectedRepr(self, sentenceType="unknown type", dataRepr=""):
        """
        Builds the expected repr for a sentence.

        @param sentenceType: The name of the sentence type (e.g "GPGGA").
        @type sentenceType: C{str}
        @param dataRepr: The repr of the data in the sentence.
        @type dataRepr: C{str}
        @return: The expected repr of the sentence.
        @rtype: C{str}
        """
        clsName = self.sentenceClass.__name__
        return self.reprTemplate % (clsName, sentenceType, dataRepr)


    def test_unknownTypeRepr(self):
        """
        Test the repr of an empty sentence of unknown type.
        """
        sentence = self.sentenceClass({})
        expectedRepr = self._expectedRepr()
        self.assertEqual(repr(sentence), expectedRepr)


    def test_knownTypeRepr(self):
        """
        Test the repr of an empty sentence of known type.
        """
        sentence = self.sentenceClass({"type": self.sentenceType})
        expectedRepr = self._expectedRepr(self.sentenceType)
        self.assertEqual(repr(sentence), expectedRepr)



class MixinTests(TestCase, SentenceTestsMixin):
    """
    Tests for protocols deriving from L{base.PositioningSentenceProducerMixin}
    and their sentences.
    """
    def setUp(self):
        self.protocol = MixinProtocol()
        self.sentenceClass = MixinSentence


    def test_noNoneInSentenceAttributes(self):
        """
        L{None} does not appear in the sentence attributes of the
        protocol, even though it's in the specification.

        This is because L{None} is a placeholder for parts of the sentence you
        don't really need or want, but there are some bits later on in the
        sentence that you do want. The alternative would be to have to specify
        things like "_UNUSED0", "_UNUSED1"... which would end up cluttering
        the sentence data and eventually adapter state.
        """
        sentenceAttributes = self.protocol.getSentenceAttributes()
        self.assertNotIn(None, sentenceAttributes)

        sentenceContents = self.protocol._SENTENCE_CONTENTS
        sentenceSpecAttributes = itertools.chain(*sentenceContents.values())
        self.assertIn(None, sentenceSpecAttributes)
