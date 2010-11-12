"""
Region Extract

Custom extraction for regions in a document
"""
import re
import operator
import copy
import pprint
import cStringIO
from itertools import groupby

from numpy import array

from scrapy.contrib.ibl.descriptor import FieldDescriptor
from scrapy.contrib.ibl.extraction.similarity import (similar_region,
    longest_unique_subsequence, common_prefix)
from scrapy.contrib.ibl.extraction.pageobjects import AnnotationTag, LabelledRegion

def build_extraction_tree(template, type_descriptor, trace=True):
    """Build a tree of region extractors corresponding to the 
    template
    """
    attribute_map = type_descriptor.attribute_map if type_descriptor else None
    extractors = BasicTypeExtractor.create(template.annotations, attribute_map)
    if trace:
        extractors = TraceExtractor.apply(template, extractors)
    for cls in (AdjacentVariantExtractor, RepeatedDataExtractor, AdjacentVariantExtractor, RepeatedDataExtractor,
            RecordExtractor):
        extractors = cls.apply(template, extractors)
        if trace:
            extractors = TraceExtractor.apply(template, extractors)

    return TemplatePageExtractor(template, extractors)

_ID = lambda x: x
_DEFAULT_DESCRIPTOR = FieldDescriptor('none', None)

def _labelled(obj):
    """
    Returns labelled element of the object (extractor or labelled region)
    """
    if hasattr(obj, "annotation"):
        return obj.annotation
    return obj

def _compose(f, g):
    """given unary functions f and g, return a function that computes f(g(x))
    """
    def _exec(x):
        ret = g(x)
        return f(ret) if ret is not None else None
    return _exec

class BasicTypeExtractor(object):
    """The BasicTypeExtractor extracts single attributes corresponding to 
    annotations.
    
    For example:
    >>> from scrapy.contrib.ibl.extraction.pageparsing import parse_strings
    >>> template, page = parse_strings( \
        u'<h1 data-scrapy-annotate="{&quot;annotations&quot;: {&quot;content&quot;: &quot;name&quot;}}">x</h1>', u'<h1> a name</h1>')
    >>> ex = BasicTypeExtractor(template.annotations[0])
    >>> ex.extract(page, 0, 1, None)
    [(u'name', u' a name')]

    It supports attribute descriptors
    >>> descriptor = FieldDescriptor('name', None, lambda x: x.strip())
    >>> ex = BasicTypeExtractor(template.annotations[0], {'name': descriptor})
    >>> ex.extract(page, 0, 1, None)
    [(u'name', u'a name')]
    
    It supports ignoring regions
    >>> template, page = parse_strings(\
        u'<div data-scrapy-annotate="{&quot;annotations&quot;: {&quot;content&quot;: &quot;name&quot;}}">x<b> xx</b></div>',\
        u'<div>a name<b> id-9</b></div>')
    >>> ex = BasicTypeExtractor(template.annotations[0])
    >>> ex.extract(page, 0, 3, [LabelledRegion(*(1,2))])
    [(u'name', u'a name')]
    """

    def __init__(self, annotation, attribute_descriptors=None):
        self.annotation = annotation
        if attribute_descriptors is None:
            attribute_descriptors = {}

        if annotation.surrounds_attribute:
            descriptor = attribute_descriptors.get(annotation.surrounds_attribute)
            if descriptor:
                self.content_validate = descriptor.extractor
                self.allow_markup = descriptor.allow_markup
            else:
                self.content_validate = _ID
                self.allow_markup = False
            self.extract = self._extract_content

        if annotation.tag_attributes:
            self.tag_data = []
            for (tag_attr, extraction_attr) in annotation.tag_attributes:
                descriptor = attribute_descriptors.get(extraction_attr)
                extractf = descriptor.extractor if descriptor else _ID
                self.tag_data.append((extractf, tag_attr, extraction_attr))

            self.extract = self._extract_both if \
                    annotation.surrounds_attribute else self._extract_attribute
        
    def _extract_both(self, page, start_index, end_index, ignored_regions=None):
        return self._extract_content(page, start_index, end_index, ignored_regions) + \
            self._extract_attribute(page, start_index, end_index, ignored_regions)

    def _extract_content(self, extraction_page, start_index, end_index, ignored_regions=None):
        # we might want to add opening/closing ul/ol/table if we have the
        # middle of a region. This would require support in the scrapy
        # cleansing.
        complete_data = ""
        start = start_index
        end = ignored_regions[0].start_index if ignored_regions else end_index
        while start is not None:
            if self.allow_markup:
                data = extraction_page.html_between_tokens(start, end)
            else:
                data = extraction_page.text_between_tokens(start, end)
            complete_data += data
            if ignored_regions:
                start = ignored_regions[0].end_index
                ignored_regions.pop(0)
                end = ignored_regions[0].start_index if ignored_regions else end_index
            else:
                start = None
        complete_data = self.content_validate(complete_data)
        return [(self.annotation.surrounds_attribute, complete_data)] if complete_data else []
    
    def _extract_attribute(self, extraction_page, start_index, end_index, ignored_regions=None):
        data = []
        for (f, ta, ea) in self.tag_data:
            tag_value = extraction_page.tag_attribute(start_index, ta)
            if tag_value:
                extracted = f(tag_value)
                if extracted is not None:
                    data.append((ea, extracted))
        return data

    @classmethod
    def create(cls, annotations, attribute_descriptors=None):
        """Create a list of basic extractors from the given annotations
        and attribute descriptors
        """
        if attribute_descriptors is None:
            attribute_descriptors = {}
        return [cls._create_basic_extractor(annotation, attribute_descriptors) \
            for annotation in annotations \
            if annotation.surrounds_attribute or annotation.tag_attributes]
    
    @staticmethod
    def _create_basic_extractor(annotation, attribute_descriptors):
        """Create a basic type extractor for the annotation"""
        text_region = annotation.annotation_text
        if text_region is not None:
            if annotation.match_common_prefix:
                region_extract = TextPrefixRegionDataExtractor(text_region.start_text).extract
            else:
                region_extract = TextRegionDataExtractor(text_region.start_text, 
                    text_region.follow_text).extract
            # copy attribute_descriptors and add the text extractor
            descriptor_copy = dict(attribute_descriptors)
            attr_descr = descriptor_copy.get(annotation.surrounds_attribute, 
                    _DEFAULT_DESCRIPTOR)
            attr_descr = copy.copy(attr_descr)
            attr_descr.extractor = _compose(attr_descr.extractor, region_extract)
            descriptor_copy[annotation.surrounds_attribute] = attr_descr
            attribute_descriptors = descriptor_copy
        return BasicTypeExtractor(annotation, attribute_descriptors)
    
    def extracted_item(self):
        """key used to identify the item extracted"""
        return (self.annotation.surrounds_attribute, self.annotation.tag_attributes)
    
    def __repr__(self):
        return str(self)

    def __str__(self):
        messages = ['BasicTypeExtractor(']
        if self.annotation.surrounds_attribute:
            messages += [self.annotation.surrounds_attribute, ': ', 
                    'html content' if self.allow_markup else 'text content',
            ]
            if self.content_validate != _ID:
                messages += [', extracted with \'', 
                        self.content_validate.__name__, '\'']
        
        if self.annotation.tag_attributes:
            if self.annotation.surrounds_attribute:
                messages.append(';')
            for (f, ta, ea) in self.tag_data:
                messages += [ea, ': tag attribute "', ta, '"']
                if f != _ID:
                    messages += [', validated by ', str(f)]
        messages.append(", template[%s:%s])" % \
                (self.annotation.start_index, self.annotation.end_index))
        return ''.join(messages)

class RepeatedDataExtractor(object):
    """Data extractor for handling repeated data"""

    def __init__(self, prefix, suffix, extractors):
        self.prefix = array(prefix)
        self.suffix = array(suffix)
        self.extractor = copy.copy(extractors[0])
        self.annotation = copy.copy(self.extractor.annotation)
        self.annotation.end_index = extractors[-1].annotation.end_index

    def extract(self, page, start_index, end_index, ignored_regions):
        """repeatedly find regions bounded by the repeated 
        prefix and suffix and extract them
        """
        prefixlen = len(self.prefix)
        suffixlen = len(self.suffix)
        index = max(0, start_index - prefixlen)
        max_index = min(len(page.page_tokens) - suffixlen, end_index + len(self.suffix))
        max_start_index = max_index - prefixlen
        extracted = []
        while index <= max_start_index:
            prefix_end = index + prefixlen
            if (page.page_tokens[index:prefix_end] == self.prefix).all():
                for peek in xrange(prefix_end, max_index):
                    if (page.page_tokens[peek:peek + suffixlen] \
                            == self.suffix).all():
                        extracted += self.extractor.extract(page, 
                                prefix_end - 1, peek, ignored_regions)
                        index = max(peek, index + 1)
                        break
                else:
                    break
            else:
                index += 1
        return extracted

    @staticmethod
    def apply(template, extractors):
        tokens = template.page_tokens
        output_extractors = []
        group_key = lambda x: x.extracted_item()
        for extr_key, extraction_group in groupby(extractors, group_key):
            extraction_group = list(extraction_group)
            if extr_key is None or len(extraction_group) == 1:
                output_extractors += extraction_group
                continue

            separating_tokens = [ \
                tokens[x.annotation.end_index:y.annotation.start_index+1] \
                for (x, y) in zip(extraction_group[:-1], extraction_group[1:])]
            
            # calculate the common prefix
            group_start = extraction_group[0].annotation.start_index
            prefix_start = max(0, group_start - len(separating_tokens[0]))
            first_prefix = tokens[prefix_start:group_start+1]
            prefixes = [first_prefix] + separating_tokens
            prefix_pattern = list(reversed(
                common_prefix(*map(reversed, prefixes))))
            
            # calculate the common suffix
            group_end = extraction_group[-1].annotation.end_index
            last_suffix = tokens[group_end:group_end + \
                    len(separating_tokens[-1])]
            suffixes = separating_tokens + [last_suffix]
            suffix_pattern = common_prefix(*suffixes)
            
            # create a repeated data extractor, if there is a suitable 
            # prefix and suffix. (TODO: tune this heuristic)
            matchlen = len(prefix_pattern) + len(suffix_pattern)
            if matchlen >= len(separating_tokens):
                group_extractor = RepeatedDataExtractor(prefix_pattern, 
                    suffix_pattern, extraction_group)
                output_extractors.append(group_extractor)
            else:
                output_extractors += extraction_group
        return output_extractors
    
    def extracted_item(self):
        """key used to identify the item extracted"""
        return self.extractor.extracted_item()
    
    def __repr__(self):
        return "Repeat(%r)" % self.extractor

    def __str__(self):
        return "Repeat(%s)" % self.extractor

class TransposedDataExtractor(object):
    """ """
    pass

_namef = operator.itemgetter(0)
_valuef = operator.itemgetter(1)
def _attrs2dict(attributes):
    """convert a list of attributes (name, value) tuples
    into a dict of lists. 

    For example:
    >>> l = [('name', 'sofa'), ('colour', 'red'), ('colour', 'green')]
    >>> _attrs2dict(l) == {'name': ['sofa'], 'colour': ['red', 'green']}
    True
    """
    grouped_data = groupby(sorted(attributes, key=_namef), _namef)
    return dict((name, map(_valuef, data)) for (name, data)  in grouped_data)

class RecordExtractor(object):
    """The RecordExtractor will extract records given annotations.
    
    It looks for a similar region in the target document, using the ibl
    similarity algorithm. The annotations are partitioned by the first similar
    region found and searched recursively.

    Records are represented as dicts mapping attribute names to lists
    containing their values.
    
    For example:
    >>> from scrapy.contrib.ibl.extraction.pageparsing import parse_strings
    >>> template, page = parse_strings( \
            u'<h1 data-scrapy-annotate="{&quot;annotations&quot;: {&quot;content&quot;: &quot;name&quot;}}">x</h1>' + \
            u'<p data-scrapy-annotate="{&quot;annotations&quot;: {&quot;content&quot;: &quot;description&quot;}}">y</p>', \
            u'<h1>name</h1> <p>description</p>')
    >>> basic_extractors = map(BasicTypeExtractor, template.annotations)
    >>> ex = RecordExtractor.apply(template, basic_extractors)[0]
    >>> ex.extract(page)
    [{u'description': [u'description'], u'name': [u'name']}]
    """
    
    def __init__(self, extractors, template_tokens):
        """Construct a RecordExtractor for the given annotations and their
        corresponding region extractors
        """
        self.extractors = extractors
        self.template_tokens = template_tokens
        self.template_ignored_regions = []
        start_index = min(e.annotation.start_index for e in extractors)
        end_index = max(e.annotation.end_index for e in extractors)
        self.annotation = AnnotationTag(start_index, end_index)
    
    def extract(self, page, start_index=0, end_index=None, ignored_regions=None):
        """extract data from an extraction page
        
        The region in the page to be extracted from may be specified using
        start_index and end_index
        """
        ignored_regions = [i if isinstance(i, LabelledRegion) else LabelledRegion(*i) for i in (ignored_regions or [])]
        region_elements = sorted(self.extractors + ignored_regions, key=lambda x: _labelled(x).start_index)
        _, _, attributes = self._doextract(page, region_elements, start_index, 
                end_index)
        # collect variant data, maintaining the order of variants
        variant_ids = []; variants = {}; items = []
        for k, v in attributes:
            if isinstance(k, int):
                if k in variants:
                    variants[k] += v
                else:
                    variant_ids.append(k)
                    variants[k] = v
            else:
                items.append((k, v))
        
        variant_records = [('variants', _attrs2dict(variants[vid])) \
                for vid in variant_ids]
        items += variant_records
        return [_attrs2dict(items)]
    
    def _doextract(self, page, region_elements, start_index, end_index, nested_regions=None, ignored_regions=None):
        """Carry out extraction of records using the given annotations
        in the page tokens bounded by start_index and end_index
        """
        # reorder extractors leaving nested ones for the end and separating
        # ignore regions
        nested_regions = nested_regions or []
        ignored_regions = ignored_regions or []
        first_region, following_regions = region_elements[0], region_elements[1:]
        while following_regions and _labelled(following_regions[0]).start_index \
                < _labelled(first_region).end_index:
            region = following_regions.pop(0)
            labelled = _labelled(region)
            if isinstance(labelled, AnnotationTag) or (nested_regions and \
                    _labelled(nested_regions[-1]).start_index < labelled.start_index \
                    < _labelled(nested_regions[-1]).end_index):
                nested_regions.append(region)
            else:
                ignored_regions.append(region)
        extracted_data = []
        # end_index is inclusive, but similar_region treats it as exclusive
        end_region = None if end_index is None else end_index + 1
        labelled = _labelled(first_region)
        score, pindex, sindex = \
            similar_region(page.page_tokens, self.template_tokens,
                labelled, start_index, end_region)
        if score > 0:
            if isinstance(labelled, AnnotationTag):
                similar_ignored_regions = []
                start = pindex
                for i in ignored_regions:
                    s, p, e = similar_region(page.page_tokens, self.template_tokens, \
                              i, start, sindex)
                    if s > 0:
                        similar_ignored_regions.append(LabelledRegion(*(p, e)))
                        start = e or start
                extracted_data = first_region.extract(page, pindex, sindex, similar_ignored_regions)
                if extracted_data:
                    if first_region.annotation.variant_id:
                        extracted_data = [(first_region.annotation.variant_id, extracted_data)]
            
            if nested_regions:
                _, _, nested_data = self._doextract(page, nested_regions, pindex, sindex)
                extracted_data += nested_data
            if following_regions:
                _, _, following_data = self._doextract(page, following_regions, sindex or start_index, end_index)
                extracted_data += following_data
        
        elif following_regions:
            end_index, _, following_data = self._doextract(page, following_regions, start_index, end_index)
            if end_index is not None:
                pindex, sindex, extracted_data = self._doextract(page, [first_region], start_index, end_index - 1, nested_regions, ignored_regions)
                extracted_data += following_data
        elif nested_regions:
            _, _, nested_data = self._doextract(page, nested_regions, start_index, end_index)
            extracted_data += nested_data
        return pindex, sindex, extracted_data
                
    @classmethod
    def apply(cls, template, extractors):
        return [cls(extractors, template.page_tokens)]
    
    def extracted_item(self):
        return [self.__class__.__name__] + \
                sorted(e.extracted_item() for e in self.extractors)
    
    def __repr__(self):
        return str(self)

    def __str__(self):
        stream = cStringIO.StringIO()
        pprint.pprint(self.extractors, stream)
        stream.seek(0)
        template_data = stream.read()
        if template_data:
            return "%s[\n%s\n]" % (self.__class__.__name__, template_data)
        return "%s[none]" % (self.__class__.__name__)

class AdjacentVariantExtractor(RecordExtractor):
    """Extractor for variants

    This simply extends the RecordExtractor to output data in a "variants"
    attribute.

    The "apply" method will only apply to variants whose items are all adjacent and 
    it will appear as one record so that it can be handled by the RepeatedDataExtractor. 
    """

    def extract(self, page, start_index=0, end_index=None, ignored_regions=None):
        records = RecordExtractor.extract(self, page, start_index, end_index, ignored_regions)
        return [('variants', r['variants'][0]) for r in records if r]
    
    @classmethod
    def apply(cls, template, extractors):
        adjacent_variants = set([])
        variantf = lambda x: x.annotation.variant_id
        for vid, egroup in groupby(extractors, variantf):
            if not vid:
                continue
            if vid in adjacent_variants:
                adjacent_variants.remove(vid)
            else:
                adjacent_variants.add(vid)
        new_extractors = []
        for variant, group_seq in groupby(extractors, variantf):
            group_seq = list(group_seq)
            if variant in adjacent_variants:
                record_extractor = AdjacentVariantExtractor(group_seq, template.page_tokens)
                new_extractors.append(record_extractor)
            else:
                new_extractors += group_seq
        return new_extractors

    def __repr__(self):
        return str(self)

class TraceExtractor(object):
    """Extractor that wraps other extractors and prints an execution
    trace of the extraction process to aid debugging
    """

    def __init__(self, traced, template):
        self.traced = traced
        self.annotation = traced.annotation
        tstart = traced.annotation.start_index
        tend = traced.annotation.end_index
        self.tprefix = " ".join([template.token_dict.token_string(t)
            for t in template.page_tokens[tstart-4:tstart+1]])
        self.tsuffix = " ".join([template.token_dict.token_string(t)
            for t in template.page_tokens[tend:tend+5]])
    
    def summarize_trace(self, page, start, end, ret):
        text_start = page.token_follow_indexes[start]
        text_end = page.token_start_indexes[end or -1]
        page_snippet = "(...%s)%s(%s...)" % (
                page.text[text_start-50:text_start].replace('\n', ' '), 
                page.text[text_start:text_end], 
                page.text[text_end:text_end+50].replace('\n', ' '))
        pre_summary = "\nstart %s page[%s:%s]\n" % (self.traced.__class__.__name__, start, end)
        post_summary = """
%s page[%s:%s] 

html
%s

annotation
...%s
%s
%s...

extracted
%s
        """ % (self.traced.__class__.__name__, start, end, page_snippet, 
                self.tprefix, self.annotation, self.tsuffix, [r for r in ret if 'trace' not in r])
        return pre_summary, post_summary

    def extract(self, page, start, end, ignored_regions):
        ret = self.traced.extract(page, start, end, ignored_regions)
        if not ret:
            return []

        # handle records by inserting a trace and combining with variant traces
        if len(ret) == 1 and isinstance(ret[0], dict):
            item = ret[0]
            trace = item.pop('trace', [])
            variants = item.get('variants', ())
            for variant in variants:
                trace += variant.pop('trace', [])
            pre_summary, post_summary = self.summarize_trace(page, start, end, ret)
            item['trace'] = [pre_summary] + trace + [post_summary]
            return ret
        
        pre_summary, post_summary = self.summarize_trace(page, start, end, ret)
        return [('trace', pre_summary)] + ret + [('trace', post_summary)]
    
    @staticmethod
    def apply(template, extractors):
        output = []
        for extractor in extractors:
            if not isinstance(extractor, TraceExtractor):
                extractor = TraceExtractor(extractor, template)
            output.append(extractor)
        return output
    
    def extracted_item(self):
        return self.traced.extracted_item()

    def __repr__(self):
        return "Trace(%s)" % repr(self.traced)

class TemplatePageExtractor(object):
    """Top level extractor for a template page"""

    def __init__(self, template, extractors):
        # fixme: handle multiple items per page
        self.extractor = extractors[0]
        self.template = template

    def extract(self, page, start_index=0, end_index=None):
        return self.extractor.extract(page, start_index, end_index, self.template.ignored_regions)
    
    def __repr__(self):
        return repr(self.extractor)

    def __str__(self):
        return str(self.extractor)

# Based on nltk's WordPunctTokenizer
_tokenize = re.compile(r'\w+|[^\w\s]+', re.UNICODE | re.MULTILINE | re.DOTALL).findall

class TextRegionDataExtractor(object):
    """Data Extractor for extracting text fragments from within a larger
    body of text. It extracts based on the longest unique prefix and suffix.

    for example:
    >>> extractor = TextRegionDataExtractor('designed by ', '.')
    >>> extractor.extract("by Marc Newson.")
    'Marc Newson'

    Both prefix and suffix are optional:
    >>> extractor = TextRegionDataExtractor('designed by ')
    >>> extractor.extract("by Marc Newson.")
    'Marc Newson.'
    >>> extractor = TextRegionDataExtractor(suffix='.')
    >>> extractor.extract("by Marc Newson.")
    'by Marc Newson'

    It requires a minimum match of at least one word or punctuation character:
    >>> extractor = TextRegionDataExtractor('designed by')
    >>> extractor.extract("y Marc Newson.") is None
    True
    """
    def __init__(self, prefix=None, suffix=None):
        self.prefix = (prefix or '')[::-1]
        self.suffix = suffix or ''
        self.minprefix = self.minmatch(self.prefix)
        self.minsuffix = self.minmatch(self.suffix)
 
    @staticmethod
    def minmatch(matchstring):
        """the minimum number of characters that should match in order
        to consider it a match for that string.

        This uses the last word of punctuation character
        """
        tokens = _tokenize(matchstring or '')
        return len(tokens[0]) if tokens else 0

    def extract(self, text):
        """attempt to extract a substring from the text"""
        pref_index = 0
        if self.minprefix > 0:
            rev_idx, plen = longest_unique_subsequence(text[::-1], self.prefix)
            if plen < self.minprefix:
                return None
            pref_index = -rev_idx
        if self.minsuffix == 0:
            return text[pref_index:]
        sidx, slen = longest_unique_subsequence(text[pref_index:], self.suffix)
        if slen < self.minsuffix:
            return None
        return text[pref_index:pref_index + sidx]

class TextPrefixRegionDataExtractor(object):
    """
    Data extractor for extracting text fragment from within a
    larger body of text, based on a fixed prefix.
    >>> extractor = TextPrefixRegionDataExtractor("&pounds;")
    >>> extractor.extract("&pounds; 17.00")
    ' 17.00'
    >>> extractor.extract("&euro; 17.00") is None
    True
    >>> extractor.extract("$ 17.00") is None
    True
    >>> extractor.extract(" &pounds; 17.00 ")
    ' 17.00 '
    """
    def __init__(self, prefix):
        self.prefix = prefix
    def extract(self, text):
        text = text.lstrip()
        # attempt to extract a substring from the text
        if text.startswith(self.prefix):
            return text.replace(self.prefix, '')
    
