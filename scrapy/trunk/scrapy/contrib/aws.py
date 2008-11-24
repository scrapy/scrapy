import re
import time
import hmac
import base64
import hashlib


METADATA_PREFIX = 'x-amz-meta-'
AMAZON_HEADER_PREFIX = 'x-amz-'


# generates the aws canonical string for the given parameters
def canonical_string(method, path, headers, expires=None):
    interesting_headers = {}
    for key in headers:
        lk = key.lower()
        if lk in ['content-md5', 'content-type', 'date'] or lk.startswith(AMAZON_HEADER_PREFIX):
            interesting_headers[lk] = headers[key].strip()

    # these keys get empty strings if they don't exist
    if not interesting_headers.has_key('content-type'):
        interesting_headers['content-type'] = ''
    if not interesting_headers.has_key('content-md5'):
        interesting_headers['content-md5'] = ''

    # just in case someone used this.  it's not necessary in this lib.
    if interesting_headers.has_key('x-amz-date'):
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


def merge_meta(headers, metadata):
    final_headers = headers.copy()
    for k in metadata.keys():
        if k.lower() in ['content-md5', 'content-type', 'date']:
            final_headers[k] = metadata[k]
        else:
            final_headers[METADATA_PREFIX + k] = metadata[k]

    return final_headers

def get_aws_metadata(headers):
    metadata = {}
    for hkey in headers.keys():
        if hkey.lower().startswith(METADATA_PREFIX):
            metadata[hkey[len(METADATA_PREFIX):]] = headers[hkey]
            del headers[hkey]
    return metadata


def add_aws_auth_header(headers, method, path):
    if not headers.has_key('Date'):
        headers['Date'] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())

    c_string = canonical_string(method, path, headers)
    _hmac = hmac.new(settings.AWS_SECRET_ACCESS_KEY, digestmod=hashlib.sha1)
    _hmac.update(c_string)
    b64_hmac = base64.encodestring(_hmac.digest()).strip()
    headers['Authorization'] = "AWS %s:%s" % (settings.AWS_ACCESS_KEY_ID, b64_hmac)

