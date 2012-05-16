from twisted.trial import unittest

from scrapy.utils.test import libxml2debug
from scrapy import optional_features


class Libxml2Test(unittest.TestCase):

    skip = 'libxml2' not in optional_features

    @libxml2debug
    def test_libxml2_bug_2_6_27(self):
        # this test will fail in version 2.6.27 but passes on 2.6.29+
        import libxml2
        html = "<td>1<b>2</b>3</td>"
        node = libxml2.htmlParseDoc(html, 'utf-8')
        result = [str(r) for r in node.xpathEval('//text()')]
        self.assertEquals(result, ['1', '2', '3'])
        node.freeDoc()

