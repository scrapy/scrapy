"""
Page parsing

Parsing of web pages for extraction task.
"""
from collections import defaultdict
from numpy import array

from scrapy.utils.py26 import json

from scrapy.contrib.ibl.htmlpage import HtmlTagType, HtmlTag, HtmlPage
from scrapy.contrib.ibl.extraction.pageobjects import (AnnotationTag, 
        TemplatePage, ExtractionPage, AnnotationText, TokenDict)

def parse_strings(template_html, extraction_html):
    """Create a template and extraction page from raw strings

    this is useful for testing purposes
    """
    t = TokenDict()
    template_page = HtmlPage(body=template_html)
    extraction_page = HtmlPage(body=extraction_html)
    return (parse_template(t, template_page), 
            parse_extraction_page(t, extraction_page))

def parse_template(token_dict, template_html):
    """Create an TemplatePage object by parsing the annotated html"""
    parser = TemplatePageParser(token_dict)
    parser.feed(template_html)
    return parser.to_template()

def parse_extraction_page(token_dict, page_html):
    """Create an ExtractionPage object by parsing the html"""
    parser = ExtractionPageParser(token_dict)
    parser.feed(page_html)
    return parser.to_extraction_page()

class InstanceLearningParser(object):
    """Base parser for instance based learning algorithm
    
    This does not require correct HTML and the parsing method should not alter
    the original tag order. It is important that parsing results do not vary.
    """
    def __init__(self, token_dict):
        self.token_dict = token_dict
        self.token_list = []
    
    def _add_token(self, token, token_type, start, end):
        tid = self.token_dict.tokenid(token, token_type)
        self.token_list.append(tid)

    def feed(self, html_page):
        self.html_page = html_page
        self.previous_element_class = None
        for data in html_page.parsed_body:
            if isinstance(data, HtmlTag):
                self._add_token(data.tag, data.tag_type, data.start, data.end)
                self.handle_tag(data)
            else:
                self.handle_data(data)
            self.previous_element_class = data.__class__

    def handle_data(self, html_data_fragment):
        pass

    def handle_tag(self, html_tag):
        pass

_END_UNPAIREDTAG_TAGS = ["form", "div", "p", "table", "tr", "td"]

class TemplatePageParser(InstanceLearningParser):
    """Template parsing for instance based learning algorithm"""

    def __init__(self, token_dict):
        InstanceLearningParser.__init__(self, token_dict)
        self.annotations = []
        self.ignored_regions = []
        self.extra_required_attrs = []
        self.ignored_tag_stacks = defaultdict(list)
        # tag names that have not been completed
        self.labelled_tag_stacks = defaultdict(list)
        self.replacement_stacks = defaultdict(list)
        self.unpairedtag_stack = []
        self.variant_stack = []
        self.prev_data = None
        self.last_text_region = None
        self.next_tag_index = 0

    def handle_tag(self, html_tag):
        if self.last_text_region:
            self._process_text('')
        
        if html_tag.tag_type == HtmlTagType.OPEN_TAG:
            self._handle_open_tag(html_tag)
        elif html_tag.tag_type == HtmlTagType.CLOSE_TAG:
            self._handle_close_tag(html_tag)
        else:
            # the tag is not paired, it can contain only attribute annotations
            self._handle_unpaired_tag(html_tag)
    
    @staticmethod
    def _read_template_annotation(html_tag):
        template_attr = html_tag.attributes.get('data-scrapy-annotate')
        if template_attr is None:
            return None
        unescaped = template_attr.replace('&quot;', '"')
        return json.loads(unescaped)
    
    @staticmethod
    def _read_bool_template_attribute(html_tag, attribute):
        return html_tag.attributes.get("data-scrapy-" + attribute) == "true"
    
    def _close_unpaired_tag(self):
        self.unpairedtag_stack[0].end_index = self.next_tag_index
        self.unpairedtag_stack = []

    def _handle_unpaired_tag(self, html_tag):
        if self._read_bool_template_attribute(html_tag, "ignore") and html_tag.tag == "img":
            self.ignored_regions.append((self.next_tag_index, self.next_tag_index + 1))
        elif self._read_bool_template_attribute(html_tag, "ignore-beneath"):
            self.ignored_regions.append((self.next_tag_index, None))
        jannotation = self._read_template_annotation(html_tag)
        if jannotation:
            if self.unpairedtag_stack:
                self._close_unpaired_tag()
                
            annotation = AnnotationTag(self.next_tag_index, self.next_tag_index + 1)
            attribute_annotations = jannotation.pop('annotations', {}).items()
            for extract_attribute, tag_value in attribute_annotations:
                if extract_attribute == 'content':
                    annotation.surrounds_attribute = tag_value
                    self.unpairedtag_stack.append(annotation)
                else:
                    annotation.tag_attributes.append((extract_attribute, tag_value))
            self.annotations.append(annotation)

            self.extra_required_attrs.extend(jannotation.pop('required', []))
            annotation.metadata = jannotation

        self.next_tag_index += 1

    def _handle_open_tag(self, html_tag):
        if self._read_bool_template_attribute(html_tag, "ignore"):
            if html_tag.tag == "img":
                self.ignored_regions.append((self.next_tag_index, self.next_tag_index + 1))
            else:
                self.ignored_regions.append((self.next_tag_index, None))
                self.ignored_tag_stacks[html_tag.tag].append(html_tag)
                
        elif self.ignored_tag_stacks.get(html_tag.tag):
            self.ignored_tag_stacks[html_tag.tag].append(None)
        if self._read_bool_template_attribute(html_tag, "ignore-beneath"):
            self.ignored_regions.append((self.next_tag_index, None))
        
        replacement = html_tag.attributes.pop("data-scrapy-replacement", None)
        if replacement:
            self.token_list.pop()
            self._add_token(replacement, html_tag.tag_type, html_tag.start, html_tag.end)
            self.replacement_stacks[html_tag.tag].append(replacement)
        elif html_tag.tag in self.replacement_stacks:
            self.replacement_stacks[html_tag.tag].append(None)

        if self.unpairedtag_stack:
            if html_tag.tag in _END_UNPAIREDTAG_TAGS:
                self._close_unpaired_tag()
            else:
                self.unpairedtag_stack.append(html_tag.tag)
            
        # can't be a p inside another p. Also, an open p element closes
        # a previous open p element.
        if html_tag.tag == "p" and html_tag.tag in self.labelled_tag_stacks:
            annotation = self.labelled_tag_stacks.pop(html_tag.tag)[0]
            annotation.end_index = self.next_tag_index
            self.annotations.append(annotation)
                
        jannotation = self._read_template_annotation(html_tag)
        if not jannotation:
            if html_tag.tag in self.labelled_tag_stacks:
                # add this tag to the stack to match correct end tag
                self.labelled_tag_stacks[html_tag.tag].append(None)
            self.next_tag_index += 1
            return
        
        annotation = AnnotationTag(self.next_tag_index, None)
        if jannotation.pop('generated', False):
            self.token_list.pop()
            annotation.start_index -= 1
            if self.previous_element_class == HtmlTag:
                annotation.annotation_text = AnnotationText('')
            else:
                annotation.annotation_text = AnnotationText(self.prev_data)
            if self._read_bool_template_attribute(html_tag, "ignore") \
                    or self._read_bool_template_attribute(html_tag, "ignore-beneath"):
                ignored = self.ignored_regions.pop()
                self.ignored_regions.append((ignored[0]-1, ignored[1]))
                
        self.extra_required_attrs.extend(jannotation.pop('required', []))
        
        attribute_annotations = jannotation.pop('annotations', {}).items()
        for extract_attribute, tag_value in attribute_annotations:
            if extract_attribute == 'content':
                annotation.surrounds_attribute = tag_value
            else:
                annotation.tag_attributes.append((extract_attribute, tag_value))
 
        variant_id = jannotation.pop('variant', 0)
        if variant_id > 0:
            if annotation.surrounds_attribute is not None:
                self.variant_stack.append(variant_id)
            else:
                annotation.variant_id = variant_id
       
        annotation.metadata = jannotation

        if annotation.annotation_text is None:
            self.next_tag_index += 1
        if self.variant_stack and annotation.variant_id is None:
            variant_id = self.variant_stack[-1]
            if variant_id == '0':
                variant_id = None
            annotation.variant_id = variant_id
        
        # look for a closing tag if the content is important
        if annotation.surrounds_attribute:
            self.labelled_tag_stacks[html_tag.tag].append(annotation)
        else:
            annotation.end_index = annotation.start_index + 1
            self.annotations.append(annotation)

    def _handle_close_tag(self, html_tag):
        
        if self.unpairedtag_stack:
            if html_tag.tag == self.unpairedtag_stack[-1]:
                self.unpairedtag_stack.pop()
            else:
                self._close_unpaired_tag()
        ignored_tags = self.ignored_tag_stacks.get(html_tag.tag)
        if ignored_tags is not None:
            tag = ignored_tags.pop()
            if isinstance(tag, HtmlTag):
                for i in range(-1, -len(self.ignored_regions) - 1, -1):
                    if self.ignored_regions[i][1] is None:
                        self.ignored_regions[i] = (self.ignored_regions[i][0], self.next_tag_index)
                        break
            if len(ignored_tags) == 0:
                del self.ignored_tag_stacks[html_tag.tag]

        if html_tag.tag in self.replacement_stacks:
            replacement = self.replacement_stacks[html_tag.tag].pop()
            if replacement:
                self.token_list.pop()
                self._add_token(replacement, html_tag.tag_type, html_tag.start, html_tag.end)
            if len(self.replacement_stacks[html_tag.tag]) == 0:
                del self.replacement_stacks[html_tag.tag]

        labelled_tags = self.labelled_tag_stacks.get(html_tag.tag)
        if labelled_tags is None:
            self.next_tag_index += 1
            return
        annotation = labelled_tags.pop()
        if annotation is None:
            self.next_tag_index += 1
        else:
            annotation.end_index = self.next_tag_index
            self.annotations.append(annotation)
            if annotation.annotation_text is not None:
                self.token_list.pop()
                self.last_text_region = annotation
            else:
                self.next_tag_index += 1
            if len(labelled_tags) == 0:
                del self.labelled_tag_stacks[html_tag.tag]
            if annotation.variant_id and self.variant_stack:
                prev = self.variant_stack.pop()
                if prev != annotation.variant_id:
                    raise ValueError("unbalanced variant annotation tags")
                    
    def handle_data(self, html_data_fragment):
        fragment_text = self.html_page.fragment_data(html_data_fragment)
        self._process_text(fragment_text)

    def _process_text(self, text):
        if self.last_text_region is not None:
            self.last_text_region.annotation_text.follow_text = text
            self.last_text_region = None
        self.prev_data = text

    def to_template(self):
        """create a TemplatePage from the data fed to this parser"""
        return TemplatePage(self.token_dict, self.token_list, self.annotations,
                self.html_page.page_id, self.ignored_regions, self.extra_required_attrs)

class ExtractionPageParser(InstanceLearningParser):
    """Parse an HTML page for extraction using the instance based learning
    algorithm

    This needs to extract the tokens in a similar way to LabelledPageParser,
    it needs to also maintain a mapping from token index to the original content
    so that once regions are identified, the original content can be extracted.
    """
    def __init__(self, token_dict):
        InstanceLearningParser.__init__(self, token_dict)
        self.page_data = []
        self.token_start_index = []
        self.token_follow_index = []
        self.tag_attrs = {}

    def _add_token(self, token, token_type, start, end):
        InstanceLearningParser._add_token(self, token, token_type, start, end)
        self.token_start_index.append(start)
        self.token_follow_index.append(end)

    def handle_tag(self, html_tag):
        if html_tag.attributes:
            self.tag_attrs[len(self.token_list) - 1] = html_tag.attributes
    
    def to_extraction_page(self):
        return ExtractionPage(self.html_page.body, self.token_dict, array(self.token_list), 
                self.token_start_index, self.token_follow_index, self.tag_attrs)
