import scrapy
from tests.utils.cmdline import proc


class TestVersionCommand:
    def test_output(self) -> None:
        _, out, _ = proc("version")
        assert out.strip() == f"Scrapy {scrapy.__version__}"

    def test_verbose_output(self) -> None:
        _, out, _ = proc("version", "-v")
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
