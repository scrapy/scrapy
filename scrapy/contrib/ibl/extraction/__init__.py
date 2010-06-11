"""
IBL module

This contains an extraction algorithm based on the paper Extracting Web Data
Using Instance-Based Learning by Yanhong Zhai and Bing Liu.

It defines the InstanceBasedLearningExtractor class, which implements this
extraction algorithm.

Main departures from the original algorithm:
    * there is no limit in prefix or suffix size
    * we have "attribute adaptors" that allow generic post processing and may
      affect the extraction process. For example, a price field may require a 
      numeric value to be present.
    * tags can be inserted to extract regions not wrapped by html tags. These
      regions are then identified using the longest unique character prefix and
      suffix.
"""
from operator import itemgetter
from .regionextract import build_extraction_tree
from .pageparsing import parse_template, parse_extraction_page
from .pageobjects import TokenDict, AnnotationText
from .similarity import common_prefix

class InstanceBasedLearningExtractor(object):
    """Implementation of the instance based learning algorithm to 
    extract data from web pages.
    """

    def __init__(self, templates, type_descriptor=None, trace=False):
        """Initialise this extractor

        templates should contain a sequence of strings, each containing 
        annotated html that will be used as templates for extraction.

        Tags surrounding areas to be extracted must contain a 
        'data-scrapy-annotate' attribute and the value must be the name
        of the attribute. If the tag was inserted and was not present in the 
        original page, the data-scrapy-generated attribute must be present.
        
        type_descriptor may contain a type descriptor describing the item
        to be extracted.
        
        if trace is true, the returned extracted data will have a 'trace'
        property that contains a trace of the extraction execution.
        """
        self.token_dict = TokenDict()
        parsed_plus_templates = [(parse_template(self.token_dict, t), t) for t in templates]
        parsed_plus_epages = [(p, parse_extraction_page(self.token_dict, t)) for p, t \
               in parsed_plus_templates if _annotation_count(p)]
        parsed_templates = map(itemgetter(0), parsed_plus_epages)
        
        # calculate common text prefixes for annotations of same field across all templates
        extracted_text = {}
        extraction_pages = map(itemgetter(1), parsed_plus_epages)
        for i, parsed in enumerate(parsed_templates):
            for annot in parsed.annotations:
                if annot.match_common_prefix:
                    field = annot.surrounds_attribute
                    if field is not None:
                        descriptor = type_descriptor.attribute_map.get(field) if type_descriptor else None
                        allow_markup = descriptor.allow_markup if descriptor else False
                        start, end = annot.start_index, annot.end_index
                        if allow_markup:
                            text = extraction_pages[i].html_between_tokens(start, end)
                        else:
                            text = extraction_pages[i].text_between_tokens(start, end)
                        extracted_text.setdefault(field, []).append(text)
        common_prefixes = {}
        for field, data in extracted_text.iteritems():
            if len(data) > 1:
                cprefix = common_prefix(*data)
                if cprefix:
                    common_prefixes[field] = "".join(cprefix).strip()
        # now apply common prefixes to annotations
        for i, parsed in enumerate(parsed_templates):
            for annot in parsed.annotations:
                for field, prefix in common_prefixes.iteritems():
                    if annot.surrounds_attribute == field and not annot.annotation_text:
                        annot.annotation_text = AnnotationText(prefix)
        
        # templates with more attributes are considered first
        sorted_templates = sorted(parsed_templates, key=_annotation_count, reverse=True)
        self.extraction_trees = [build_extraction_tree(t, type_descriptor, 
            trace) for t in sorted_templates]
        self.validated = type_descriptor.validated if type_descriptor else \
                self._filter_not_none

    def extract(self, html, pref_template_id=None, useone=False):
        """extract data from an html page
        
        If pref_template_url is specified, the template with that url will be 
        used first.
        if useone is True and no data was extracted, no additional template will
        be tried. If False and no data was extracted, try with rest of item templates
        """
        extraction_page = parse_extraction_page(self.token_dict, html)
        if pref_template_id is not None:
            if useone:
                extraction_trees = [x for x in self.extraction_trees if x.template.id == pref_template_id]
            else:
                extraction_trees = sorted(self.extraction_trees, 
                    key=lambda x: x.template.id != pref_template_id)
        else:
            extraction_trees = self.extraction_trees

        for extraction_tree in extraction_trees:
            extracted = extraction_tree.extract(extraction_page)
            correctly_extracted = self.validated(extracted)
            extra_required = extraction_tree.template.extra_required_attrs
            correctly_extracted = [c for c in correctly_extracted if \
                extra_required.intersection(c.keys()) == extra_required ]
            if len(correctly_extracted) > 0:
                return correctly_extracted, extraction_tree.template
        return None, None

    def __str__(self):
        return "InstanceBasedLearningExtractor[\n%s\n]" % \
                (',\n'.join(map(str, self.extraction_trees)))
    
    @staticmethod
    def _filter_not_none(items):
        return [d for d in items if d is not None]

def _annotation_count(template):
    return len(template.annotations)
