import urllib2
import sys
import re
from w3lib.url import is_url
from urllib2 import HTTPError

from scrapy.exceptions import UsageError
from scrapy.command import ScrapyCommand


class Command(ScrapyCommand):

    requires_project = False
    default_settings = {'LOG_ENABLED': False}

    #List of well known User-Agents
    userAgent = ['Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)',
                    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36' \
                        ' (KHTML, like Gecko) Chrome/29.0.1547.66 ' \
                        'Safari/537.36',
                    'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:23.0) ' \
                        'Gecko/20100101 Firefox/23.0',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_4) ' \
                        'AppleWebKit/536.30.1 (KHTML, like Gecko) ' \
                        'Version/6.0.5 Safari/536.30.1',
                    'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; ' \
                        'WOW64; Trident/6.0)',
                    'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; ' \
                        'rv:1.8.1.6) Gecko/20070725 Firefox/2.0.0.6'
    ]
    #List of well known Accept media type
    accept = ['text/html',
                'application/xhtml+xml',
                'text/*',
                '*/*',
                'application/xml;q=0.9',
                '*/*;q=0.8'
                
    ]
    #List of natural languages that are preferred
    acceptLanguage = ['en;q=0.5',
                      'en-us',
                      'en'
    ]
    #List of character sets are acceptable for the response
    acceptCharset = ['ISO-8859-1',
                     'utf-8;q=0.7',
                     '*;q=0.7'
    ]

    def syntax(self):
        return "[url][text]"

    def short_desc(self):
        return "Returns a HTTP header where the text found in the content"

    def long_desc(self):
        return "probe command will try several of combinations of HTTP headers "\
            "and return a header that page content have search string"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)

    def run(self, args, opts):
        if len(args) != 2 or not is_url(args[0]):
            raise UsageError()
        
        url = args[0]
        text = args[1]
        #ready to start build headers
        self.combination_HTTP_headers(url, text)

    # Builds dictionaries of headers, and sends dictionaries to check
    # if content have the search string
    def combination_HTTP_headers(self, url, text):
        # Get common fields parameter
        for value_charset in self.acceptCharset:
            for value_charset in self.acceptLanguage:
                for value_agent in self.userAgent:
                    for value_accept in self.accept:
                        # Add each value to dictionaries header 
                        header = {'Accept' : value_accept,
                                   'User-Agent' : value_agent,
                                   'Accept-Language' : value_charset,
                                   'Accept-Charset' : value_charset,
                        }
                        # Check if search string is on page
                        if self.verify_if_match(url, header, text):
                            sys.exit()
        # Send message if not found and exit
        sys.exit('Not Found set of working headers')

    # Check if the search string is in page, if true print header
    # and return it
    def verify_if_match(self, url, header, text):
        try:
            # Build the curent request
            req = urllib2.Request(url, None, header)
            response = urllib2.urlopen(req)
            # Get page content
            the_page = response.read()
            # Check if the search string is in page and print the header
            if re.search(text, the_page):
                print 'Found set of working headers:'
                print header
                return header
        except HTTPError, e:
            print e.code    #print core error from http responce sample 401
            print e.read()  #print cathed error
