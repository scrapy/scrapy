import os
import unittest

from decobot.utils.link_extraction import extract_urls

class LinkExtractionTest(unittest.TestCase):
    def setUp(self):
        self.datadir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "sample_data", "link_extraction")

    def test_extract_urls(self):
        text = open(os.path.join(self.datadir, "extract_urls.html")).read()
        links_expected = {'/products/eco-mattress-protector.html': 'Eco Mattress Protector',
                          '/products.html': 'Our Products', 
                          '/products/eco-duvet.html': 'Eco Duvet', 
                          '/terms-and-conditions.html': 'Terms &amp; Conditions', 
                          '/returns-policy.html': 'Returns Policy', 
                          '/products/eco-pillow.html': 'Eco Pillow', 
                          '/': 'Home', 
                          '/privacy-policy.html': 'Privacy Policy', 
                          '/eco-friendly.html': 'Eco-Friendly', 
                          '/faqs.html': 'FAQs', 
                          '/contact-us.html': 'Contact Us'}
        self.assertEqual(links_expected, extract_urls(text))

if __name__ == "__main__":
    unittest.main()
