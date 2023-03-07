import json
import logging
import unittest
from ipaddress import IPv4Address
from socket import gethostbyname
from urllib.parse import urlparse
import scrapy

from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.crawler import CrawlerRunner
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer
from tests.spiders import (
    DelaySpider,
    SimpleSpider,
)


class CrawlTestCase(TestCase):
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    # Test single response
    @defer.inlineCallbacks
    def test_print_average(self):
        settings = {'EXTENSIONS': {
            'scrapy.extensions.averageresponse.ResponseTime': 1000,
            'scrapy.extensions.logstats.LogStats': None,
            'scrapy.extensions.telnet.TelnetConsole': None, 
        },
        "AVERAGERESPOSNE_ENABLED" : True
        }
        crawler = get_crawler(SimpleSpider, settings)
        runner = CrawlerRunner()
        with LogCapture() as log:
            yield runner.crawl(
                crawler,
                self.mockserver.url("/status?n=200"),
                mockserver=self.mockserver,
            )
        self.assertIn("Got response 200", str(log))
        printed = str(log).count("average response time") > 0
        self.assertTrue(printed)

    #Test delay spider response
    @defer.inlineCallbacks
    def test_delayed_response(self):
        settings = {'EXTENSIONS': {
            'scrapy.extensions.averageresponse.ResponseTime': 1000,
            'scrapy.extensions.logstats.LogStats': None,
            'scrapy.extensions.telnet.TelnetConsole': None,
        }, 
        "AVERAGERESPOSNE_ENABLED" : True
        }
        crawler = get_crawler(DelaySpider, settings)
        runner = CrawlerRunner()
        with LogCapture() as log:            
            yield runner.crawl(
                crawler,
                self.mockserver.url("/status?n=200"),
                mockserver=self.mockserver,
            )
        printed= str(log).count("average response time") > 0
        self.assertTrue(printed)

    #Test settings invalid: 
    @defer.inlineCallbacks
    def test_setting_invalid(self):
        settings = {'EXTENSIONS': {
            'scrapy.extensions.averageresponse.ResponseTime': 1000,
            'scrapy.extensions.logstats.LogStats': None,
            'scrapy.extensions.telnet.TelnetConsole': None,
        }, 
        "AVERAGERESPOSNE_ENABLED" : False
        }
        crawler = get_crawler(SimpleSpider, settings)
        runner = CrawlerRunner()
        with LogCapture() as log:
            yield runner.crawl(
                crawler,
                self.mockserver.url("/status?n=200"),
                mockserver=self.mockserver,
            )
        self.assertIn("Got response 200", str(log))
        printed = str(log).count("average response time") > 0
        self.assertFalse(printed)

    # Test disabled settings
    @defer.inlineCallbacks
    def test_setting_disabled(self):

        settings = {'EXTENSIONS': {
            'scrapy.extensions.averageresponse.ResponseTime': None,
            'scrapy.extensions.logstats.LogStats': None,
            'scrapy.extensions.telnet.TelnetConsole': None,
        }, "AVERAGERESPOSNE_ENABLED" : False}
        crawler = get_crawler(SimpleSpider, settings)
        runner = CrawlerRunner()
        with LogCapture() as log:
            yield runner.crawl(
                crawler,
                self.mockserver.url("/status?n=200"),
                mockserver=self.mockserver,
            )
        self.assertIn("Got response 200", str(log))
        printed = str(log).count("average response time") > 0
        self.assertFalse(printed)
        
    # Test no response
    @defer.inlineCallbacks
    def test_no_response(self):
        settings = {'EXTENSIONS': {
            'scrapy.extensions.averageresponse.ResponseTime': 1000,
            'scrapy.extensions.logstats.LogStats': None,
            'scrapy.extensions.telnet.TelnetConsole': None, 
        },
        "AVERAGERESPOSNE_ENABLED" : True
        }
        crawler = get_crawler(SimpleSpider, settings)
        runner = CrawlerRunner()
        with LogCapture() as log:
            yield runner.crawl(
                crawler,
                mockserver=self.mockserver,
            )
        printed = str(log).count("average response time") > 0
        self.assertFalse(printed)