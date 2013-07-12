import unittest

from scrapy.contrib.linkfilters import Canonicalize, Allow, Disallow, \
        AllowDomains, DisallowDomains, Unique


def pipe(values, *cmds):
    '''pipe(a,b,c,d, ...) -> yield from ...d(c(b(a())))
    '''
    gen = cmds[0](values)
    for cmd in cmds[1:]:
        gen = cmd(gen)
        for x in gen:
            yield x


class TestLinkFilters(unittest.TestCase):

    def setUp(self):
        self.urls = ['http://scrapy.org', 'http://scrapy.org/',
                'http://doc.scrapy.org', 'http://doc.scrapy.org',
                'http://scrapinghub.com']

    def test_canonicalize(self):
        canonicalize = Canonicalize()
        self.assertEqual(list(canonicalize(self.urls)), ['http://scrapy.org/',
            'http://scrapy.org/', 'http://doc.scrapy.org/',
            'http://doc.scrapy.org/', 'http://scrapinghub.com/'])

    def test_allow(self):
        allow = Allow('scrapinghub')
        self.assertEqual(list(allow(self.urls)), ['http://scrapinghub.com'])

    def test_disallow(self):
        disallow = Disallow('scrapy')
        self.assertAlmostEqual(list(disallow(self.urls)),
                ['http://scrapinghub.com'])

    def test_allow_domains(self):
        allow_domains = AllowDomains('com')
        self.assertEqual(list(allow_domains(self.urls)),
                ['http://scrapinghub.com'])

    def test_disallow_domains(self):
        disallow_domains = DisallowDomains('org')
        self.assertEqual(list(disallow_domains(self.urls)),
                ['http://scrapinghub.com'])

    def test_unique(self):
        unique = Unique()
        self.assertEqual(list(unique(self.urls)),
                ['http://scrapy.org', 'http://scrapy.org/',
                    'http://doc.scrapy.org', 'http://scrapinghub.com'])

    def test_piping(self):
        unique = Unique()
        canonicalize = Canonicalize()
        self.assertEqual(list(unique(canonicalize(self.urls))),
                ['http://scrapy.org/', 'http://doc.scrapy.org/',
                    'http://scrapinghub.com/'])
