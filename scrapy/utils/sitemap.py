"""
Module for processing Sitemaps.

Note: The main purpose of this module is to provide support for the
SitemapSpider, its API is subject to change without notice.
"""
import lxml.etree


class Sitemap(object):
    """Class to parse Sitemap (type=urlset) and Sitemap Index
    (type=sitemapindex) files"""

    def __init__(self, xmltext):
        xmlp = lxml.etree.XMLParser(recover=True, remove_comments=True)
        self._root = lxml.etree.fromstring(xmltext, parser=xmlp)
        rt = self._root.tag
        self.type = self._root.tag.split('}', 1)[1] if '}' in rt else rt

    def __iter__(self):
        for elem in self._root.getchildren():
            d = xml_to_dict(elem)
            if 'loc' in d:
                yield d


def sitemap_urls_from_robots(robots_text):
    """Return an iterator over all sitemap urls contained in the given
    robots.txt file
    """
    for line in robots_text.splitlines():
        if line.lstrip().startswith('Sitemap:'):
            yield line.split(':', 1)[1].strip()


def xml_to_dict(doc):
    dic = {}
    for el in doc:
        tag = el.tag
        name = tag.split('}', 1)[1] if '}' in tag else tag
        if name == 'link':
            if 'href' in el.attrib:
                dic.setdefault('alternate', []).append(el.get('href'))
        # Recursive for ancestors
        if len(el) == 0:
            if el.text and el.text.strip():
                dic[name] = el.text.strip()
        else:
            sub_dic = xml_to_dict(el)
            if sub_dic:
                dic[name] = sub_dic
    return dic
