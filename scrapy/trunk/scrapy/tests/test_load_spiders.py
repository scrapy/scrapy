from unittest import TestCase, main
from scrapy.spider import spiders

class ScrapySpidersTest(TestCase):
    def test_load_spiders(self):
        """ Simple test that forces to load the spiders
        checks for syntax errors that block the whole framework
        """
        spiders.asdict()

if __name__ == "__main__":
    main()

