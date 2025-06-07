import pytest
from scrapy.cmdline import ScrapyArgumentParser

class TestScrapyArgumentParser:
    def test_parse_optional(self):
        parser = ScrapyArgumentParser()
        assert parser._parse_optional("-:foo") is None      
        assert parser._parse_optional("--foo") is not None 
        assert parser._parse_optional("-foo") is not None  
        assert parser._parse_optional("foo") is None   