"""
Page objects

This module contains objects representing pages and parts of pages (e.g. tokens
and annotations) used in the instance based learning algorithm.
"""
from numpy import array, ndarray

from scrapy.contrib.ibl.htmlpage import HtmlTagType

class TokenType(object):
    """constants for token types"""
    WORD = 0
    OPEN_TAG = HtmlTagType.OPEN_TAG
    CLOSE_TAG = HtmlTagType.CLOSE_TAG
    NON_PAIRED_TAG = HtmlTagType.UNPAIRED_TAG

class TokenDict(object):
    """Mapping from parse tokens to integers
    
    >>> d = TokenDict()
    >>> d.tokenid('i')
    0
    >>> d.tokenid('b')
    1
    >>> d.tokenid('i')
    0

    Tokens can be searched for by id
    >>> d.find_token(1)
    'b'

    The lower 24 bits store the token reference and the higher bits the type.
    """
    
    def __init__(self):
        self.token_ids = {}

    def tokenid(self, token, token_type=TokenType.WORD):
        """create an integer id from the token and token type passed"""
        tid = self.token_ids.setdefault(token, len(self.token_ids))
        return tid | (token_type << 24)
    
    @staticmethod
    def token_type(token):
        """extract the token type from the token id passed"""
        return token >> 24

    def find_token(self, tid):
        """Search for a tag with the given ID

        This is O(N) and is only intended for debugging
        """
        tid &= 0xFFFFFF
        if tid >= len(self.token_ids) or tid < 0:
            raise ValueError("tag id %s out of range" % tid)

        for (token, token_id) in self.token_ids.items():
            if token_id == tid:
                return token
        assert False, "token dictionary is corrupt"

    def token_string(self, tid):
        """create a string representation of a token

        This is O(N).
        """
        templates = ["%s", "<%s>", "</%s>", "<%s/>"]
        return templates[tid >> 24] % self.find_token(tid)

class Page(object):
    """Basic representation of a page. This consists of a reference to a
    dictionary of tokens and an array of raw token ids
    """

    __slots__ = ('token_dict', 'page_tokens')

    def __init__(self, token_dict, page_tokens):
        self.token_dict = token_dict
        # use a numpy array becuase we can index/slice easily and efficiently
        if not isinstance(page_tokens, ndarray):
            page_tokens = array(page_tokens)
        self.page_tokens = page_tokens

class TemplatePage(Page):
    __slots__ = ('annotations', 'id', 'ignored_regions', 'extra_required_attrs')

    def __init__(self, token_dict, page_tokens, annotations, template_id=None, \
            ignored_regions=None, extra_required=None):
        Page.__init__(self, token_dict, page_tokens)
        # ensure order is the same as start tag order in the original page
        annotations = sorted(annotations, key=lambda x: x.end_index, reverse=True)
        self.annotations = sorted(annotations, key=lambda x: x.start_index)
        self.id = template_id
        self.ignored_regions = ignored_regions or []
        self.extra_required_attrs = set(extra_required or [])

    def __str__(self):
        summary = []
        for index, token in enumerate(self.page_tokens):
            text = "%s: %s" % (index, self.token_dict.find_token(token))
            summary.append(text)
        return "TemplatePage\n============\nTokens: (index, token)\n%s\nAnnotations: %s\n" % \
                ('\n'.join(summary), '\n'.join(map(str, self.annotations)))

class ExtractionPage(Page):
    """Parsed data belonging to a web page upon which we wish to perform
    extraction.
    """
    __slots__ = ('text', 
            'token_start_indexes', # index in text of the start of a token
            'token_follow_indexes', # index in text of data following token
            'tag_attributes'        # a map from token index to tag attributes
        )

    def __init__(self, text, token_dict, page_tokens, token_start_indexes, 
            token_follow_indexes, tag_attributes):
        Page.__init__(self, token_dict, page_tokens)
        self.text = text
        self.token_start_indexes = token_start_indexes
        self.token_follow_indexes = token_follow_indexes
        self.tag_attributes = tag_attributes

    def token_html(self, token_index):
        """The raw html for a page token at the given index in the page_tokens
        list
        """
        text_start = self.token_start_indexes[token_index]
        text_end = self.token_follow_indexes[token_index]
        return self.text[text_start:text_end]

    def html_between_tokens(self, start_token_index, end_token_index):
        """The raw html between the tokens at the specified indexes in the 
        page_tokens list

        This assumes start_token_index <= end_token_index
        """
        text_start = self.token_follow_indexes[start_token_index]
        text_end = self.token_start_indexes[end_token_index]
        return self.text[text_start:text_end]
    
    def text_between_tokens(self, start_token_index, end_token_index, 
            tag_replacement=u' '):
        """The text between the  the tokens at the specified indexes in the 
        page_tokens list. Tags are replaced by tag_replacement (default one space 
        character)
        """
        return tag_replacement.join([self.text[
            self.token_follow_indexes[i]:self.token_start_indexes[i+1]] \
            for i in xrange(start_token_index, end_token_index)])

    def tag_attribute(self, token_index, attribute):
        """The value of a tag attribute. The tag is identified by its 
        corresponding token index.

        If the tag or attribute is not present, None is returned
        """
        return self.tag_attributes.get(token_index, {}).get(attribute) 
    
    def __str__(self):
        summary = []
        for (token, start, follow) in zip(self.page_tokens, self.token_start_indexes, 
                self.token_follow_indexes):
            text = "%s %s-%s (%s)" % (self.token_dict.find_token(token), start, follow, 
                    self.text[start:follow])
            summary.append(text)
        return "ExtractionPage\n==============\nTokens: %s\n\nRaw text: %s\n\n" \
                "Tag attributes: %s\n" % ('\n'.join(summary), self.text, 
                        self.tag_attributes)

class AnnotationText(object):
    __slots__ = ('start_text', 'follow_text')

    def __init__(self, start_text=None, follow_text=None):
        self.start_text = start_text
        self.follow_text = follow_text

    def __str__(self):
        return "AnnotationText(%s..%s)" % \
                (repr(self.start_text), repr(self.follow_text))

class AnnotationTag(object):
    """A tag that annotates part of the document

    It has the following properties:
        start_index - index of the token for the opening tag
        end_index - index of the token for the closing tag
        surrounds_attribute - the attribute name surrounded by this tag
        tag_attributes - list of (tag attribute, extracted attribute) tuples
                         for each item to be extracted from a tag attribute
        annotation_text - text prefix and suffix for the attribute to be extracted
        match_common_prefix - use this annotation for calculating across-template prefixes
        metadata - dict with annotation data not used by IBL extractor
    """
    __slots__ = ('surrounds_attribute', 'start_index', 'end_index',
            'tag_attributes', 'annotation_text', 'variant_id', 
            'surrounds_variant','match_common_prefix', 'metadata')
    
    def __init__(self, start_index, end_index, surrounds_attribute=None, 
            annotation_text=None, tag_attributes=None, variant_id=None,
            surrounds_variant=None, match_common_prefix=False):
        self.start_index = start_index
        self.end_index = end_index
        self.surrounds_attribute = surrounds_attribute
        self.annotation_text = annotation_text
        self.tag_attributes = tag_attributes or []
        self.variant_id = variant_id
        self.surrounds_variant = surrounds_variant
        self.match_common_prefix = match_common_prefix
        self.metadata = {}

    def __str__(self):
        return "AnnotationTag(%s)" % ", ".join(
                ["%s=%s" % (s, getattr(self, s)) \
                for s in self.__slots__ if getattr(self, s)])

    def __repr__(self):
        return str(self)

class LabelledRegion(object):
    __slots__ = ('start_index', 'end_index')
    
    def __init__(self, start, end):
        self.start_index = start
        self.end_index = end
        
    def __str__(self):
        return "LabelledRegion (%s, %s)" % (self.start_index, self.end_index)
    
    def __repr__(self):
        return str(self)

