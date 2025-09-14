import scrapy
from tests.test_commands import TestProjectBase


class TestVersionCommand(TestProjectBase):
    def test_output(self):
        _, out, _ = self.proc("version")
        assert out.strip() == f"Scrapy {scrapy.__version__}"

    def test_verbose_output(self):
        _, out, _ = self.proc("version", "-v")
        headers = [line.partition(":")[0].strip() for line in out.strip().splitlines()]
        assert headers == [
            "Scrapy",
            "lxml",
            "libxml2",
            "cssselect",
            "parsel",
            "w3lib",
            "Twisted",
            "Python",
            "pyOpenSSL",
            "cryptography",
            "Platform",
        ]
