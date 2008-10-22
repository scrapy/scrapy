import unittest
from scrapy.utils.serialization import serialize, unserialize, serialize_funcs

class SerializationTest(unittest.TestCase):
    def test_string_serialization(self):
        """Test simple string serialization"""

        s = "string to serialize"
        for format in serialize_funcs.iterkeys():
            self.assertEqual(s, unserialize(serialize(s)))

    def test_dict_serialization(self):
        """Test dict serialization"""

        # using only string keys/values since it's the only data type that
        # works with all serializers
        d = {'one': 'item one', 'two': 'item two'}
        for format in serialize_funcs.iterkeys():
            self.assertEqual(d, unserialize(serialize(d)))
        
if __name__ == "__main__":
    unittest.main()
