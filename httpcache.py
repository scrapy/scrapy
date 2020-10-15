import json
import os
import pathlib
import sqlite3
import time

import scrapy.http
import scrapy.utils.project
import scrapy.utils.request

# GOAL:
#   * the built-in file storage makes 10 files per request, which is hard on the filesystem.
#   * the built-in dbm storage is a pain to work with, and is old and slow
#   * neither auto-expire old records from the cache
#   * sqlite is VERY widely understood, and is "good enough" to be an incremental improvement over dbm.
#
#
# GOAL:
#   * scrapy uses pickle, which is widely considered to be FUCKING AWFUL.
#   * standard practice is to use json if the data "fits" into json's worldview.
#   * pickle is only pickling dicts of lists of bytes, which we could JUST ABOUT do
#   * python json only does str, not bytes.
#   * scrapy will get VERY CONFUSED if we force it to use str
#   * can we trick json into dumping bytes and loading bytes back out?


# FIXME: this is still awful.
# Is it sensible to replace this with sqlalchemy, and
# have it write to the same real database as the actual scraped data?
# That feels slightly bad, because this is ONLY a cache, not "real" data.
# Also there is a LOT more of it than the scraped data.
class SqliteCacheStorage:

    def __init__(self, settings):
        self.cachedir = scrapy.utils.project.data_path(settings['HTTPCACHE_DIR'])
        self.expiration_secs = settings.getint('HTTPCACHE_EXPIRATION_SECS')
        self.connections = dict()

    def open_spider(self, spider):
        dbpath = pathlib.Path(self.cachedir).joinpath(f'{spider.name}.sqlite').resolve()
        os.makedirs(dbpath.parent, mode=0o755, exist_ok=True)  # just in case
        # isolation_level=None means "autocommit", the default in C (but not Python).
        # It means we don't have to decide how often to call .commit().
        conn = sqlite3.connect(dbpath, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode = WAL')  # "go faster" stripes, only SLIGHTLY risky.
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS pages(
            -- sqlite is MUCH better at integral PKs
            -- unfortuately SHA-1 is too long to be a sqlite3 INTEGER.
            fingerprint TEXT PRIMARY KEY,
            time        REAL NOT NULL,
            status      INTEGER NOT NULL,
            url         TEXT NOT NULL,
            headers     TEXT NOT NULL,
            body        BLOB NOT NULL
            ) WITHOUT ROWID''')
        self.connections[spider] = conn

    def close_spider(self, spider):
        self.connections[spider].close()
        del self.connections[spider]

    def store_response(self, spider, request, response):
        fingerprint = scrapy.utils.request.request_fingerprint(request)  # Ref. https://bugs.python.org/issue27925
        conn = self.connections[spider]
        conn.execute(
            '''
            REPLACE INTO pages (fingerprint, time, status, url, headers, body)
            VALUES (:fingerprint, :time, :status, :url, json(:headers), :body)
            ''',
            {'fingerprint': fingerprint,
             'time': time.time(),
             'status': response.status,  # an integer (right???)
             'url': response.url,        # a string (right???)
             'headers': json.dumps(
                 # Convert {b'key': [b'val']} to {'key': ['val']}.
                 {key.decode(response.headers.encoding):
                  [value.decode(response.headers.encoding)
                   for value in values]
                  for key, values in response.headers.items()}),
             'body': response.body})

    def retrieve_response(self, spider, request):
        fingerprint = scrapy.utils.request.request_fingerprint(request)
        conn = self.connections[spider]
        try:
            (ts,), = conn.execute('SELECT time FROM pages WHERE fingerprint = ?', (fingerprint,)).fetchall()
        except ValueError:
            return              # not in the cache
        if 0 < self.expiration_secs < (time.time() - float(ts)):
            # Clean up the database, don't just grow it unboundedly.
            conn.execute('DELETE FROM pages WHERE fingerprint = ?', (fingerprint,))
            return              # expired, i.e. nothing in the cache
        row = conn.execute('SELECT * FROM pages WHERE fingerprint = ?', (fingerprint,)).fetchone()
        # This part is largely copy-pasted from DbmCacheStorage with no real understanding.
        url = row['url']
        status = row['status']
        # NOTE: Headers() understands u'' and forces it to b'' as UTF-8.
        #       So *we* don't need to reverse the bytes-to-str from store_response().
        headers = scrapy.http.Headers(json.loads(row['headers']))
        body = row['body']
        response_class = scrapy.responsetypes.responsetypes.from_args(
            headers=headers,
            url=url)
        response_object = response_class(
            url=url,
            headers=headers,
            status=status,
            body=body)
        return response_object
