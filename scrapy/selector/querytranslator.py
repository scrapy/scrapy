"""
Example: How the code would look like using the DmozSpider example in the docs
"""
import scrapy


class DmozSpider(scrapy.Spider):
    name = "dmoz"
    allowed_domains = ["dmoz.org"]
    start_urls = [
        "http://www.dmoz.org/Computers/Programming/Languages/Python/Books/",
        "http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/"
    ]

    # parse using attributes dictionary
    def parse(self, response):
        for x in response.find('li', {'class': 'list-item'}):
            title = response.inside(x).value_of('a', {'class': 'title'}, QueryComparison.contains).as_text()
            link = response.inside(x).attr_of('a', {'class': 'url'}, 'href').as_text()
            price = response.inside(x).value_of('span', {'class': 'price'}).as_float()
            print title, link, price

# """ End of example """ #

import re
from enum import Enum
from lxml import html


class QueryComparison(Enum):
    contains = 1
    starts_with = 2
    ends_with = 3
    equals = 4


class QueryTranslator:
    def __init__(self, markup):
        self.root = html.fromstring(markup)

    @staticmethod
    def generate_condition(attr, value, comparison):
        prefix = '^' if comparison == QueryComparison.starts_with or comparison == QueryComparison.equals else ''
        suffix = '$' if comparison == QueryComparison.ends_with or comparison == QueryComparison.equals else ''
        return 're:test(@{0}, \'{1}{2}{3}\')'.format(attr, prefix, value, suffix)

    @staticmethod
    def generate_xpath(tag, attrs, comparison):
        conditions = []
        for x in attrs:
            conditions.append(QueryTranslator.generate_condition(x, attrs[x], comparison))
        xpath = '//{0}'.format(tag)
        if len(conditions) > 0:
            xpath += '[{0}]'.format(' and '.join(conditions))
        return xpath

    def find(self, tag, attrs, comparison=QueryComparison.contains):
        ns = 'http://exslt.org/regular-expressions'
        expr = QueryTranslator.generate_xpath(tag, attrs, comparison)
        elements = self.root.xpath(expr, namespaces={'re': ns})
        return elements

    def inside(self, element):
        self.root = html.fromstring(html.tostring(element))
        return self

    def value(self):
        element = QueryElement(self.root.text_content())
        return element

    def attr(self, name):
        element = QueryElement(self.root.attrib[name])
        return element

    def value_of(self, tag, attrs):
        elements = self.find(tag, attrs)
        if len(elements) > 0:
            return self.inside(elements[0]).value()
        else:
            return QueryElement.empty()

    def attr_of(self, tag, attrs, name):
        elements = self.find(tag, attrs)
        if len(elements) > 0:
            return self.inside(elements[0]).attr(name)
        else:
            return QueryElement.empty()


class QueryElement:
    def __init__(self, element):
        self.element = element

    def as_text(self):
        result = str(self.element)
        return result

    def as_clean_text(self):
        result = self.as_text().strip("\\r \\n \\t")
        result = re.sub(r"(\\r|\\n|\\t){2,}", " ", result)
        return result

    def as_float(self):
        try:
            result = self.as_clean_text().replace(",", "")
            return float(result)
        except ValueError:
            return float('nan')

    @staticmethod
    def empty():
        return QueryElement('')
