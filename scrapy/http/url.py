"""
The Url class is similar to the urlparse.ParseResult class (it has the same
attributes) with the following differences:

- it inherits from str
- it's lazy, so it only parses the url when needed
"""

import urlparse

class Url(str):

    @property
    def parsedurl(self):
        if not hasattr(self, '_parsedurl'):
            self._parsedurl = urlparse.urlparse(self)
        return self._parsedurl

    @property
    def scheme(self):
        return self.parsedurl.scheme

    @property
    def netloc(self):
        return self.parsedurl.netloc

    @property
    def path(self):
        return self.parsedurl.path

    @property
    def params(self):
        return self.parsedurl.params

    @property
    def query(self):
        return self.parsedurl.query

    @property
    def fragment(self):
        return self.parsedurl.fragment

    @property
    def username(self):
        return self.parsedurl.username

    @property
    def password(self):
        return self.parsedurl.password

    @property
    def hostname(self):
        return self.parsedurl.hostname

    @property
    def port(self):
        return self.parsedurl.port
