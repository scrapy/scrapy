import os
import shelve
import shutil
import tempfile
import tarfile

from pydispatch import dispatcher

from scrapy.core import signals, log
from scrapy.core.manager import scrapymanager
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings

class Replay(object):
    """
    This is the Replay extension, used to replay a crawling and see if the
    items scraped are the same.
    """

    def __init__(self, repfile, mode='play', usedir=False):
        """
        Available modes: record, play, update

        repfile can be either a dir (is usedir=True) or a tar.gz file (if
        usedir=False)
        """

        # XXX: this is ugly, and should be removed. but how?
        cachemw = 'scrapy.contrib.downloadermiddleware.cache.CacheMiddleware'
        if not cachemw in settings['DOWNLOADER_MIDDLEWARES']:
            raise NotConfigured("Cache middleware must be enabled to use Replay")

        self.recording = mode == 'record'
        self.updating = mode == 'update'
        self.playing = mode == 'play'

        self.options = {}
        self.scraped_old = {}
        self.scraped_new = {}
        self.passed_old = {}
        self.passed_new = {}
        self.responses_old = {}
        self.responses_new = {}

        self._opendb(repfile, usedir)

        settings.overrides['CACHE2_DIR'] = self.cache2dir
        settings.overrides['CACHE2_IGNORE_MISSING'] = self.playing or self.updating
        settings.overrides['CACHE2_SECTORIZE'] = False

        dispatcher.connect(self.engine_started, signal=signals.engine_started)
        dispatcher.connect(self.engine_stopped, signal=signals.engine_stopped)
        dispatcher.connect(self.item_scraped, signal=signals.item_scraped)
        dispatcher.connect(self.item_passed, signal=signals.item_passed)
        dispatcher.connect(self.response_downloaded, signal=signals.response_downloaded)

    def play(self, args=None, opts=None):
        if self.recording:
            raise ValueError("Replay.play() not available in record mode")

        args = args or self.options['args']
        opts = opts or self.options['opts']
        scrapymanager.runonce(*args, **opts)

    def record(self, args=None, opts=None):
        self.options.clear()
        self.options['args'] = args or []
        self.options['opts'] = opts or {}

        if os.path.exists(self.cache2dir):
            shutil.rmtree(self.cache2dir)
        else:
            os.mkdir(self.cache2dir)

    def update(self, args=None, opts=None):
        self.updating = True

        self.play(args, opts)

    def engine_started(self):
        log.msg("Replay: recording session in %s" % self.repfile)

    def engine_stopped(self):
        if self.recording or self.updating:
            log.msg("Replay: recorded in %s: %d/%d scraped/passed items, %d downloaded responses" % \
                (self.repfile, len(self.scraped_old), len(self.passed_old), len(self.responses_old)))
        self._closedb()
        self.cleanup()

    def item_scraped(self, item, spider):
        if self.recording or self.updating:
            self.scraped_old[str(item.guid)] = item.copy()
        else:
            self.scraped_new[str(item.guid)] = item.copy()

    def item_passed(self, item, spider):
        if self.recording or self.updating:
            self.passed_old[str(item.guid)] = item.copy()
        else:
            self.passed_new[str(item.guid)] = item.copy()

    def response_downloaded(self, response, spider):
        #key = response.request.fingerprint()
        key = response.version()
        if self.recording and key:
            self.responses_old[key] = response.copy()
        elif key:
            self.responses_new[key] = response.copy()
        
    def _opendb(self, repfile, usedir):
        if usedir:
            if os.path.isdir(repfile):
                replay_dir = repfile
            elif self.recording:
                os.makedirs(repfile)
                replay_dir = repfile
            else:
                raise IOError("No such dir: " % repfile)
        elif os.path.exists(repfile) and (self.playing or self.updating):
            if tarfile.is_tarfile(repfile):
                replay_dir = tempfile.mkdtemp(prefix="replay-")
                tar = tarfile.open(repfile)
                tar.extractall(replay_dir)
                tar.close()
            else:
                raise IOError("Wrong tarfile: %s" % repfile)
        elif self.recording:
            replay_dir = tempfile.mkdtemp(prefix="replay-")
        else:
            raise IOError("No such file: %s" % repfile)

        self.cache2dir = os.path.join(replay_dir, "httpcache")
        self.replay_dir = replay_dir
        self.repfile = repfile
        self.usedir = usedir

        self.options_path = os.path.join(replay_dir, "options.db")
        self.scraped_path = os.path.join(replay_dir, "items_scraped.db")
        self.passed_path = os.path.join(replay_dir, "items_passed.db")
        self.responses_path = os.path.join(replay_dir, "responses.db")

        if self.updating:
            self.options.update(shelve.open(self.options_path))
            #self.responses_old.update(shelve.open(self.responses_path))
        if self.playing:
            self.options.update(shelve.open(self.options_path))
            self.responses_old.update(shelve.open(self.responses_path))
            self.scraped_old.update(shelve.open(self.scraped_path))
            self.passed_old.update(shelve.open(self.passed_path))

    def _persistdb(self, dict_, filename):
        d = shelve.open(filename)
        d.clear()
        d.update(dict_)
        d.close()
        
    def _closedb(self):
        if self.recording or self.updating:
            d = shelve.open(self.options_path)
            for k, v in self.options.iteritems():
                d[k] = v
            d.close()
            self._persistdb(self.options, self.options_path)
            self._persistdb(self.scraped_old, self.scraped_path)
            self._persistdb(self.passed_old, self.passed_path)
            self._persistdb(self.responses_old, self.responses_path)

            if not self.usedir:
                if self.recording or self.updating:
                    tar = tarfile.open(self.repfile, "w:gz")
                    for name in os.listdir(self.replay_dir):
                        tar.add(os.path.join(self.replay_dir, name), name)
                    tar.close()

    def cleanup(self):
        if not self.usedir and os.path.exists(self.replay_dir):
            shutil.rmtree(self.replay_dir)
