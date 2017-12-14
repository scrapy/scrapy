import unittest

from scrapy import FormRequest


class Issue2919Test(unittest.TestCase):

    def test_form_request(self):
        """
        Validate formdata overrides url params.
        """
        assert FormRequest('http://example.com/?id=1,id2=2', method='GET', formdata={'id': '11', 'id2': '12'}).url \
            == 'http://example.com/?id=11&id2=12'
