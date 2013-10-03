import urllib2
import sys
import re
from w3lib.url import is_url

from scrapy.exceptions import UsageError
from scrapy.command import ScrapyCommand


class Command(ScrapyCommand):

    requires_project = False
    default_settings = {'LOG_ENABLED': False}
    
    #List of User-Agents
    UserAgent = ['Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)',
                  #'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/28.0.1500.71 Chrome/28.0.1500.71 Safari/537.36',
                  #'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.2.10) Gecko/20100915 Ubuntu/10.04 (lucid) Firefox/3.6.10'
                  'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.8.1.6) Gecko/20070725 Firefox/2.0.0.6'
    ]
    
    #List of Accept media type
    Accept = ['text/html',
              #'text/*',
              #'*/*',
              #'application/xml;q=0.9',
              #'*/*;q=0.8',
              'application/xhtml+xml'
    ]
    
    #List of natural languages that are preferred
    AcceptLanguage = ['en;q=0.5',
                      'en-us',
                      'en'
    ]
    
    #List of character sets are acceptable for the response
    AcceptCharset = ['ISO-8859-1',
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
            
  
    # TODO
    # change all code to accept agrs
    # add documentation this function will generate set of header
    # create a better wait to build headers, to many fors try use a dictionary
    def combination_HTTP_headers(self, url, text):
        #Build each dictionary to test
        for charset in self.AcceptCharset:
            for lag in self.AcceptLanguage:
                for value_agent in self.UserAgent:
                    for value_accept in self.Accept:
                        # Add each vakue of dictionaryto header
                        headers = {'Accept' : value_accept,
                                   'User-Agent' : value_agent,
                                   'Accept-Language' : lag,
                                   'Accept-Charset' : charset,
                        }
                        # Check if search string is on page
                        if self.verefy_if_math(url, headers, text):
                            sys.exit()
    # TODO
    # To add documentation this function will verefy if generated headers
    # check if necessary return of just need print the header
    def verefy_if_math(self, url, header, text):
        try:
            # Build the curent request
            req = urllib2.Request(url, None, header)
            response = urllib2.urlopen(req)
            # Get page content
            the_page = response.read()
            # Check if the search string is in page and print the 
            # header if true and exit
            if re.search(text, the_page):
                print 'Found set of working headers:'
                print header
                return header
        except HTTPError, e:
            print e.code    #print core error from http responce 401
            print e.read()  #print cathed error
