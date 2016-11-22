from __future__ import print_function
import sys
import platform

import twisted
import OpenSSL

import scrapy
from scrapy.commands import ScrapyCommand


class Command(ScrapyCommand):

    default_settings = {'LOG_ENABLED': False}

    def syntax(self):
        return "[-v]"

    def short_desc(self):
        return "Print Scrapy version"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--verbose", "-v", dest="verbose", action="store_true",
            help="also display twisted/python/platform info (useful for bug reports)")

    def run(self, args, opts):
        if opts.verbose:
            import cssselect
            import parsel
            import lxml.etree
            import w3lib

            lxml_version = ".".join(map(str, lxml.etree.LXML_VERSION))
            libxml2_version = ".".join(map(str, lxml.etree.LIBXML_VERSION))

            try:
                w3lib_version = w3lib.__version__
            except AttributeError:
                w3lib_version = "<1.14.3"

            print("Scrapy    : %s" % scrapy.__version__)
            print("lxml      : %s" % lxml_version)
            print("libxml2   : %s" % libxml2_version)
            print("cssselect : %s" % cssselect.__version__)
            print("parsel    : %s" % parsel.__version__)
            print("w3lib     : %s" % w3lib_version)
            print("Twisted   : %s" % twisted.version.short())
            print("Python    : %s" % sys.version.replace("\n", "- "))
            print("pyOpenSSL : %s" % self._get_openssl_version())
            print("Platform  : %s" % platform.platform())
        else:
            print("Scrapy %s" % scrapy.__version__)

    def _get_openssl_version(self):
        try:
            openssl = OpenSSL.SSL.SSLeay_version(OpenSSL.SSL.SSLEAY_VERSION)\
                .decode('ascii', errors='replace')
        # pyOpenSSL 0.12 does not expose openssl version
        except AttributeError:
            openssl = 'Unknown OpenSSL version'

        return '{} ({})'.format(OpenSSL.version.__version__, openssl)
