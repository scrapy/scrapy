import unittest
import warnings
import six

from scrapy.link import Link


class LinkTest(unittest.TestCase):

    def _assert_same_links(self, link1, link2):
        self.assertEqual(link1, link2)
        self.assertEqual(hash(link1), hash(link2))

    def _assert_different_links(self, link1, link2):
        self.assertNotEqual(link1, link2)
        self.assertNotEqual(hash(link1), hash(link2))

    def test_eq_and_hash(self):
        l1 = Link("http://www.example.com")
        l2 = Link("http://www.example.com/other")
        l3 = Link("http://www.example.com")

        self._assert_same_links(l1, l1)
        self._assert_different_links(l1, l2)
        self._assert_same_links(l1, l3)

        l4 = Link("http://www.example.com", text="test")
        l5 = Link("http://www.example.com", text="test2")
        l6 = Link("http://www.example.com", text="test")

        self._assert_same_links(l4, l4)
        self._assert_different_links(l4, l5)
        self._assert_same_links(l4, l6)

        l7 = Link("http://www.example.com", text="test", fragment='something', nofollow=False)
        l8 = Link("http://www.example.com", text="test", fragment='something', nofollow=False)
        l9 = Link("http://www.example.com", text="test", fragment='something', nofollow=True)
        l10 = Link("http://www.example.com", text="test", fragment='other', nofollow=False)
        self._assert_same_links(l7, l8)
        self._assert_different_links(l7, l9)
        self._assert_different_links(l7, l10)

    def test_repr(self):
        l1 = Link("http://www.example.com", text="test", fragment='something', nofollow=True)
        l2 = eval(repr(l1))
        self._assert_same_links(l1, l2)

    def test_non_str_url_py2(self):
        if six.PY2:
            with warnings.catch_warnings(record=True) as w:
                link = Link(u"http://www.example.com/\xa3")
                self.assertIsInstance(link.url, str)
                self.assertEqual(link.url, b'http://www.example.com/\xc2\xa3')
            assert len(w) == 1, "warning not issued"
        else:
            with self.assertRaises(TypeError):
                Link(b"http://www.example.com/\xc2\xa3")
