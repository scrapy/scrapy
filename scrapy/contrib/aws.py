import os
import re
import time
import hmac
import base64
import hashlib
from urlparse import urlsplit
from scrapy.conf import settings


METADATA_PREFIX = 'x-amz-meta-'
AMAZON_HEADER_PREFIX = 'x-amz-'


# generates the aws canonical string for the given parameters
def canonical_string(method, path, headers, expires=None):
    interesting_headers = {}
    for key in headers:
        lk = key.lower()
        if lk in set(['content-md5', 'content-type', 'date']) or lk.startswith(AMAZON_HEADER_PREFIX):
            interesting_headers[lk] = headers[key].strip()

    # these keys get empty strings if they don't exist
    interesting_headers.setdefault('content-type', '')
    interesting_headers.setdefault('content-md5', '')

    # just in case someone used this.  it's not necessary in this lib.
    if 'x-amz-date' in interesting_headers:
        interesting_headers['date'] = ''

    # if you're using expires for query string auth, then it trumps date
    # (and x-amz-date)
    if expires:
        interesting_headers['date'] = str(expires)

    sorted_header_keys = interesting_headers.keys()
    sorted_header_keys.sort()

    buf = "%s\n" % method
    for key in sorted_header_keys:
        if key.startswith(AMAZON_HEADER_PREFIX):
            buf += "%s:%s\n" % (key, interesting_headers[key])
        else:
            buf += "%s\n" % interesting_headers[key]

    # don't include anything after the first ? in the resource...
    buf += "%s" % path.split('?')[0]

    # ...unless there is an acl or torrent parameter
    if re.search("[&?]acl($|=|&)", path):
        buf += "?acl"
    elif re.search("[&?]logging($|=|&)", path):
        buf += "?logging"
    elif re.search("[&?]torrent($|=|&)", path):
        buf += "?torrent"
    elif re.search("[&?]location($|=|&)", path):
        buf += "?location"

    return buf



def sign_request(req, accesskey, secretkey):
    if 'Date' not in req.headers:
        req.headers['Date'] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())

    parsed = urlsplit(req.url)
    bucket = parsed.hostname.replace('.s3.amazonaws.com','')
    key = '%s?%s' % (parsed.path, parsed.query) if parsed.query else parsed.path
    fqkey = '/%s%s' % (bucket, key)

    c_string = canonical_string(req.method, fqkey, req.headers)
    _hmac = hmac.new(secretkey, digestmod=hashlib.sha1)
    _hmac.update(c_string)
    b64_hmac = base64.encodestring(_hmac.digest()).strip()
    req.headers['Authorization'] = "AWS %s:%s" % (accesskey, b64_hmac)


class AWSMiddleware(object):
    def __init__(self):
        self.access_key = settings['AWS_ACCESS_KEY_ID'] or os.environ.get('AWS_ACCESS_KEY_ID')
        self.secret_key = settings['AWS_SECRET_ACCESS_KEY'] or os.environ.get('AWS_SECRET_ACCESS_KEY')

    def process_request(self, request, spider):
        if spider.domain_name == 's3.amazonaws.com' \
                or (request.url.hostname and request.url.hostname.endswith('s3.amazonaws.com')):
            request.headers['Date'] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
            sign_request(request, self.access_key, self.secret_key)
