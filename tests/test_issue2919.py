import unittest

from scrapy import FormRequest


class Issue2919Test(unittest.TestCase):

    def test_form_request(self):
        """
        Validate formdata overrides url params.
        """
        url = FormRequest('http://example.com/?id=1&id2=2&id4=4', method='GET', formdata={'id': '11', 'id2': '12', 'id3': '13'}).url
        params = url[url.find('?') + 1:].split('&')
        for param in params:
            key = param.split('=')[0]
            value = param.split('=')[1]

            if key =='id':
                assert value == '11'
            elif key == 'id2':
                assert value == '12'
            elif key == 'id3':
                assert value == '13'
            elif key == 'id4':
                assert value == '4'
