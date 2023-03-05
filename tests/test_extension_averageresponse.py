import json
import logging
import unittest
from ipaddress import IPv4Address
from socket import gethostbyname
from urllib.parse import urlparse
import scrapy

from pytest import mark
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.internet.ssl import Certificate
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase
from scrapy.extensions.averageresponse import ResponseTime

from scrapy import signals
from scrapy.crawler import CrawlerRunner
from scrapy.exceptions import NotConfigured, StopDownload
from scrapy.http import Request
from scrapy.http.response import Response
from scrapy.utils.python import to_unicode
from scrapy.utils.test import get_crawler
from tests import NON_EXISTING_RESOLVABLE
from tests.mockserver import MockServer
from tests.spiders import (
    AsyncDefAsyncioGenComplexSpider,
    AsyncDefAsyncioGenExcSpider,
    AsyncDefAsyncioGenLoopSpider,
    AsyncDefAsyncioGenSpider,
    AsyncDefAsyncioReqsReturnSpider,
    AsyncDefAsyncioReturnSingleElementSpider,
    AsyncDefAsyncioReturnSpider,
    AsyncDefAsyncioSpider,
    AsyncDefDeferredDirectSpider,
    AsyncDefDeferredMaybeWrappedSpider,
    AsyncDefDeferredWrappedSpider,
    AsyncDefSpider,
    BrokenStartRequestsSpider,
    BytesReceivedCallbackSpider,
    BytesReceivedErrbackSpider,
    CrawlSpiderWithAsyncCallback,
    CrawlSpiderWithAsyncGeneratorCallback,
    CrawlSpiderWithErrback,
    CrawlSpiderWithParseMethod,
    CrawlSpiderWithProcessRequestCallbackKeywordArguments,
    DelaySpider,
    DuplicateStartRequestsSpider,
    FollowAllSpider,
    HeadersReceivedCallbackSpider,
    HeadersReceivedErrbackSpider,
    SimpleSpider,
    SingleRequestSpider,
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
