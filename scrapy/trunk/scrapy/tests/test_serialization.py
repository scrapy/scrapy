from twisted.trial import unittest

class SerializationTest(unittest.TestCase):

    def setUp(self):
        try:
            import simplejson
        except ImportError, e:
            raise unittest.SkipTest(e)

    def test_string_serialization(self):
        """Test simple string serialization"""
        from scrapy.utils.serialization import serialize, unserialize, serialize_funcs

        s = "string to serialize"
        for format in serialize_funcs.iterkeys():
            self.assertEqual(s, unserialize(serialize(s)))

    def test_dict_serialization(self):
        """Test dict serialization"""
        from scrapy.utils.serialization import serialize, unserialize, serialize_funcs

        # using only string keys/values since it's the only data type that
        # works with all serializers
        d = {'one': 'item one', 'two': 'item two'}
        for format in serialize_funcs.iterkeys():
            self.assertEqual(d, unserialize(serialize(d)))
        
if __name__ == "__main__":
    unittest.main()
