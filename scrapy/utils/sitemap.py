"""
Module for processing Sitemaps.

Note: The main purpose of this module is to provide support for the
SitemapSpider, its API is subject to change without notice.
"""
from io import BytesIO
import lxml.etree


class Sitemap(object):
    """Class to parse Sitemap (type=urlset) and Sitemap Index
    (type=sitemapindex) files"""

    def __init__(self, xmltext):
        self.xml_iterator = lxml.etree.iterparse(BytesIO(xmltext), remove_comments=True, events=("start", "end"))
        _, self.root = self.xml_iterator.next()
        rt = self.root.tag
        self.type = rt.split('}', 1)[1] if '}' in rt else rt



    def __iter__(self):
        for event, elem in self.xml_iterator:
            d = {}
            for el in elem.getchildren():
                tag = el.tag
                name = tag.split('}', 1)[1] if '}' in tag else tag

                if name == 'link':
                    if 'href' in el.attrib:
                        d.setdefault('alternate', []).append(el.get('href'))
                else:
                    d[name] = el.text.strip() if el.text else ''

            elem.clear()
            if 'loc' in d:
                yield d


def sitemap_urls_from_robots(robots_text):
    """Return an iterator over all sitemap urls contained in the given
    robots.txt file
    """
    for line in robots_text.splitlines():
        if line.lstrip().startswith('Sitemap:'):
            yield line.split(':', 1)[1].strip()
