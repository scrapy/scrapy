import pathlib
import pickle
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


# FIXME: this is still really awful.
# FIXME: this is still using pickle which is DEEPLY INSECURE and generally just awful.
# Is it sensible to replace this with sqlalchemy, and
# have it write to the same real database as the actual scraped data?
# That feels slightly bad, because this is ONLY a cache, not "real" data.
# Also there is a LOT more of it than the scraped data.
class SqliteCacheStorage:

    def __init__(self, settings):
        self.cachedir = scrapy.utils.project.data_path(settings['HTTPCACHE_DIR'])
        self.expiration_secs = settings.getint('HTTPCACHE_EXPIRATION_SECS')

    def open_spider(self, spider):
        dbpath = pathlib.Path(self.cachedir).joinpath(f'{spider.name}.sqlite')
        # isolation_level=None means "autocommit", the default in C (but not Python).
        # It means we don't have to decide how often to call .commit().
        self.conn = sqlite3.connect(dbpath, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode = WAL')  # "go faster" stripes, only SLIGHTLY risky.
        self.conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS pages(
            -- sqlite is MUCH better at integral PKs
            -- unfortuately SHA-1 is too long to be a sqlite3 INTEGER.
            fingerprint TEXT PRIMARY KEY,
            time        REAL NOT NULL,
            status      INTEGER NOT NULL,
            url         TEXT NOT NULL,
            headers     BLOB NOT NULL,  -- FIXME: stop pickling
            body        BLOB NOT NULL   -- FIXME: stop pickling
            ) WITHOUT ROWID''')

    def close_spider(self, spider):
        self.conn.close()

    def store_response(self, spider, request, response):
        fingerprint = scrapy.utils.request.request_fingerprint(request)  # Ref. https://bugs.python.org/issue27925
        self.conn.execute(
            '''
            REPLACE INTO pages (fingerprint, time, status, url, headers, body)
            VALUES (:fingerprint, :time, :status, :url, :headers, :body)
            ''',
            {'fingerprint': fingerprint,
             'time': time.time(),
             'status': response.status,  # an integer (right???)
             'url': response.url,        # a string (right???)
             'headers': pickle.dumps(dict(response.headers), protocol=4),
             'body': pickle.dumps(response.body, protocol=4)})

    def retrieve_response(self, spider, request):
        fingerprint = scrapy.utils.request.request_fingerprint(request)
        try:
            (ts,), = self.conn.execute('SELECT time FROM pages WHERE fingerprint = ?', (fingerprint,)).fetchall()
        except ValueError:
            return              # not in the cache
        if 0 < self.expiration_secs < (time.time() - float(ts)):
            # Clean up the database, don't just grow it unboundedly.
            self.conn.execute('DELETE FROM pages WHERE fingerprint = ?', (fingerprint,))
            return              # expired, i.e. nothing in the cache
        row = self.conn.execute('SELECT * FROM pages WHERE fingerprint = ?', (fingerprint,)).fetchone()
        # This part is largely copy-pasted from DbmCacheStorage with no real understanding.
        url = row['url']
        status = row['status']
        headers = scrapy.http.Headers(pickle.loads(row['headers']))
        body = pickle.loads(row['body'])
        response_class = scrapy.responsetypes.responsetypes.from_args(
            headers=headers,
            url=url)
        response_object = response_class(
            url=url,
            headers=headers,
            status=status,
            body=body)
        return response_object
