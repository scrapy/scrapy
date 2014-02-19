"""
Module for processing Sitemaps.

Note: The main purpose of this module is to provide support for the
SitemapSpider, its API is subject to change without notice.
"""
import lxml.etree as ET
from cStringIO import StringIO


class Sitemap(object):
    """Class to parse Sitemap (type=urlset) and Sitemap Index
    (type=sitemapindex) files"""

    def __init__(self, xmltext):
        io = StringIO(xmltext)

        # Skipping emptiness in the beginning of the file
        pos = xmltext.find('<')
        io.seek(pos)

        # Getting type of sitemap
        xml_iterator = ET.iterparse(io, events=("start", ),
                                    remove_comments=True)
        _, self.root = xml_iterator.next()
        rt = self.root.tag
        self.type = rt.split('}', 1)[1] if '}' in rt else rt

        # Rewind the stream to the beginning of xml
        io.seek(pos)

        self.xml_iterator = ET.iterparse(io, events=("end", ),
                                         remove_comments=True)

    def __iter__(self):
        for event, elem in self.xml_iterator:

            tag = elem.tag.split('}', 1)[1] if '}' in elem.tag else elem.tag
            if tag not in ["url", "sitemap"]:
                continue

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
