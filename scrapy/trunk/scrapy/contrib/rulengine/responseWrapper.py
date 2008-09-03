"""
This class serve as wrapper of the response object. 
The object created by this class are not response, but are objects that contains a response a a lot of useful information about the response.
"""

import re

from BeautifulSoup import Tag

def extractText(soup):
    text_in_tags = soup.findAll(text=True)
    res = []
    for tag in text_in_tags:
        if isinstance(tag.parent, Tag) and tag.parent.name not in('script'):
            res.append(tag)
    return res

class ResponseWrapper(object):
    def __init__(self, response):
        self._response = response        
        self.__soup_bodytext = extractText(response.soup.body) if response else None
        self.__soup_headtext = extractText(response.soup.head) if response else None        
        self._soup = None
        self._bodytext = None
        self._headtext = None
        self._cleanbodytext = None
    
    def __cleantext(self, souptext):
        return filter(lambda x:re.search('\w+', x), souptext)

    @property
    def soup(self):        
        if (self._soup):
            self._soup = self._response.soup
        return self._response.soup

    @property
    def bodytext(self):
        if not self._bodytext:
            self._bodytext = self.__cleantext(self.__soup_bodytext)
        return self._bodytext

    @property
    def headtext(self):
        if not self._headtext:
            self._headtext = self.__cleantext(self.__soup_headtext)
        return self._headtext

    @property
    def cleanbodytext(self):
        if not self._cleanbodytext:
            text = ' '.join(self.bodytext)
            text = text.lower()
            text = text.replace('\n', '')
            text = text.replace('\t', '')
            text = re.sub('&.*?;', '', text)
            self._cleanbodytext = text
        return self._cleanbodytext

