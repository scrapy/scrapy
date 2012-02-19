import collections, hashlib, random, re, time, urlparse

def md5_digest(x):
    if isinstance(x, str):
        x = x.encode('utf-8')
    return hashlib.md5(x).hexdigest()

def sha_digest(x):
    if isinstance(x, str):
        x = x.encode('utf-8')
    return hashlib.sha1(x).hexdigest()

HASH_ALGOS = {
    'MD5': md5_digest,
    'SHA': sha_digest
}

def parse_uri(url):
    parsed = urlparse.urlparse(url)
    uri = parsed.path
    
    if parsed.path:
        return '%s?%s' % (parsed.path, parsed.query)
    else:
        return parsed.path

class HttpDigestMiddleware(object):
    def __init__(self):
        self.nonce_counts = collections.defaultdict(int)
        self.auth_info = {}
    
    def authorize_request(self, request, spider):
        info = self.auth_info[spider.name]
        hasher = HASH_ALGOS[info['algo']]
        ha1 = hasher(':'.join([info['username'], info['realm'], info['password']]))
        uri = parse_uri(request.url)
        qop = 'auth-int' if 'auth-int' in info['qops'] else 'auth'
        
        if qop == 'auth-int':
            ha2 = hasher(':'.join([request.method, uri, hasher(request.body)]))
        else:
            ha2 = hasher(':'.join([request.method, uri]))
        
        auth_items = [(k, info[k]) for k in ['username', 'realm', 'nonce']]
        auth_items.extend([('uri', uri), ('qop', qop)])
        
        if not info['qops']:
            resp = hasher(':'.join([ha1, info['nonce'], ha2]))
        else: # auth or auth-int
            # nonce_count must always increase
            self.nonce_counts[spider.name] += 1
            nonce_count = self.nonce_counts[spider.name]
            nc = '%08x' % nonce_count # zero fill nonce_count so it's 8 digits long
            # cnonce is a 16 char hash of a random string
            cnonce = hasher(''.join([str(nonce_count), info['nonce'], time.ctime()] + [chr(random.randrange(32, 128)) for i in range(8)]).encode('utf-8'))[:16]
            resp = hasher(':'.join([ha1, info['nonce'], nc, cnonce, qop, ha2]))
            auth_items.extend([('nc', nc), ('cnonce', cnonce)])
        
        auth_items.append(('response', resp))
        if info['opaque']: auth_items.append(('opaque', info['opaque']))
        headers = request.headers.copy()
        headers['Authorization'] = 'Digest %s' % ', '.join(['%s="%s"' % t for t in auth_items])
        return request.replace(headers=headers)
    
    def process_request(self, request, spider):
        # return None to continue
        if spider.name not in self.auth_info or 'Authorization' in request.headers:
            return None
        
        return self.authorize_request(request, spider)
    
    def process_response(self, request, response, spider):
        if response.status != 401: return response
        www_auth = response.headers.get('WWW-Authenticate', '')
        if not www_auth or 'Digest' not in www_auth: return response
        
        usr = getattr(spider, 'digest_user', '')
        pwd = getattr(spider, 'digest_pass', '')
        if not usr or not pwd: return response
        
        parts = dict([p.split('=') for p in re.split(',\s*', www_auth[7:].strip())])
        algo = parts.get('algorithm', 'MD5').strip('"').upper()
        if algo not in HASH_ALGOS: return response
        
        realm, nonce = parts['realm'].strip('"'), parts['nonce'].strip('"')
        qops = parts.get('qop', '').strip('"').split(',')
        opaque = parts.get('opaque', '').strip('"')
        
        self.auth_info[spider.name] = {
            'username': usr, 'password': pwd, 'algo': algo, 'realm': realm,
            'nonce': nonce, 'qops': qops, 'opaque': opaque
        }
        
        return self.authorize_request(request, spider)
