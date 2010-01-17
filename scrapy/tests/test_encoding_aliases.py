import unittest

import scrapy # adds encoding aliases (if not added before)

class EncodingAliasesTestCase(unittest.TestCase):

    def test_encoding_aliases(self):
        """Test common encdoing aliases not included in Python"""

        uni = u'\u041c\u041e\u0421K\u0412\u0410'
        str = uni.encode('windows-1251')
        self.assertEqual(uni.encode('windows-1251'), uni.encode('win-1251'))
        self.assertEqual(str.decode('windows-1251'), str.decode('win-1251'))

        text = u'\u8f6f\u4ef6\u540d\u79f0'
        str = uni.encode('gb2312')
        self.assertEqual(uni.encode('gb2312'), uni.encode('zh-cn'))
        self.assertEqual(str.decode('gb2312'), str.decode('zh-cn'))

if __name__ == "__main__":
    unittest.main()
