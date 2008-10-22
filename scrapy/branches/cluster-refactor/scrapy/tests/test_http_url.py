import unittest
from scrapy.http import Url

class UrlClassTest(unittest.TestCase):

    def test_url_attributes(self):
        u = Url("http://scrapy.org/wiki/info")
        self.assertEqual("scrapy.org", u.hostname)
        self.assertEqual("/wiki/info", u.path)
        self.assertEqual(None, u.username)
        self.assertEqual(None, u.password)

        u = Url("http://someuser:somepass@example.com/ticket/query?owner=pablo")
        self.assertEqual("someuser", u.username)
        self.assertEqual("somepass", u.password)
        self.assertEqual("example.com", u.hostname)
        self.assertEqual("/ticket/query", u.path)
        self.assertEqual("owner=pablo", u.query)

        u = Url("http://example.com/somepage.html#fragment-1")
        self.assertEqual("fragment-1", u.fragment)

        u = Url("file:///home/pablo/file.txt")
        self.assertEqual("/home/pablo/file.txt", u.path)

if __name__ == "__main__":
    unittest.main()

