import logging
import os
import sys
import tempfile
import unittest
import zlib

from testfixtures import LogCapture
from twisted.python.failure import Failure

from scrapy.extensions import telnet
from scrapy.utils.log import (
    LogCounterHandler,
    StreamLogger,
    TopLevelFormatter,
    failure_to_exc_info,
)
from scrapy.utils.test import get_crawler


class FailureToExcInfoTest(unittest.TestCase):
    def test_failure(self):
        try:
            0 / 0
        except ZeroDivisionError:
            exc_info = sys.exc_info()
            failure = Failure()

        self.assertTupleEqual(exc_info, failure_to_exc_info(failure))

    def test_non_failure(self):
        self.assertIsNone(failure_to_exc_info("test"))


class TopLevelFormatterTest(unittest.TestCase):
    def setUp(self):
        self.handler = LogCapture()
        self.handler.addFilter(TopLevelFormatter(["test"]))

    def test_top_level_logger(self):
        logger = logging.getLogger("test")
        with self.handler as log:
            logger.warning("test log msg")
        log.check(("test", "WARNING", "test log msg"))

    def test_children_logger(self):
        logger = logging.getLogger("test.test1")
        with self.handler as log:
            logger.warning("test log msg")
        log.check(("test", "WARNING", "test log msg"))

    def test_overlapping_name_logger(self):
        logger = logging.getLogger("test2")
        with self.handler as log:
            logger.warning("test log msg")
        log.check(("test2", "WARNING", "test log msg"))

    def test_different_name_logger(self):
        logger = logging.getLogger("different")
        with self.handler as log:
            logger.warning("test log msg")
        log.check(("different", "WARNING", "test log msg"))


class LogCounterHandlerTest(unittest.TestCase):
    def setUp(self):
        settings = {"LOG_LEVEL": "WARNING"}
        if not telnet.TWISTED_CONCH_AVAILABLE:
            # disable it to avoid the extra warning
            settings["TELNETCONSOLE_ENABLED"] = False
        self.logger = logging.getLogger("test")
        self.logger.setLevel(logging.NOTSET)
        self.logger.propagate = False
        self.crawler = get_crawler(settings_dict=settings)
        self.handler = LogCounterHandler(self.crawler)
        self.logger.addHandler(self.handler)

    def tearDown(self):
        self.logger.propagate = True
        self.logger.removeHandler(self.handler)

    def test_init(self):
        self.assertIsNone(self.crawler.stats.get_value("log_count/DEBUG"))
        self.assertIsNone(self.crawler.stats.get_value("log_count/INFO"))
        self.assertIsNone(self.crawler.stats.get_value("log_count/WARNING"))
        self.assertIsNone(self.crawler.stats.get_value("log_count/ERROR"))
        self.assertIsNone(self.crawler.stats.get_value("log_count/CRITICAL"))

    def test_accepted_level(self):
        self.logger.error("test log msg")
        self.assertEqual(self.crawler.stats.get_value("log_count/ERROR"), 1)

    def test_filtered_out_level(self):
        self.logger.debug("test log msg")
        self.assertIsNone(self.crawler.stats.get_value("log_count/INFO"))


class StreamLoggerTest(unittest.TestCase):
    def setUp(self):
        self.stdout = sys.stdout
        logger = logging.getLogger("test")
        logger.setLevel(logging.WARNING)
        sys.stdout = StreamLogger(logger, logging.ERROR)

    def tearDown(self):
        sys.stdout = self.stdout

    def test_redirect(self):
        with LogCapture() as log:
            print("test log msg")
        log.check(("test", "ERROR", "test log msg"))


def make_temp_file(*args, **kwargs):
    fd, fn = tempfile.mkstemp(*args, **kwargs)
    os.close(fd)
    return fn


class RotatingFileHandlerTest(unittest.TestCase):
    message_num = 0

    def setUp(self):
        self.fn = make_temp_file(".log", "test_logging-2-")
        self.rmfiles = []

    def tearDown(self):
        for fn in self.rmfiles:
            os.unlink(fn)
        if os.path.exists(self.fn):
            os.unlink(self.fn)

    def assertLogFile(self, filename):
        "Assert a log file is there and register it for deletion"
        self.assertTrue(
            os.path.exists(filename), msg="Log file %r does not exist" % filename
        )
        self.rmfiles.append(filename)

    def next_rec(self):
        return logging.LogRecord(
            "n", logging.DEBUG, "p", 1, self.next_message(), None, None, None
        )

    def next_message(self):
        """Generate a message consisting solely of an auto-incrementing
        integer."""
        self.message_num += 1
        return "%d" % self.message_num

    def test_should_not_rollover(self):
        # If maxbytes is zero rollover never occurs
        rh = logging.handlers.RotatingFileHandler(self.fn, encoding="utf-8", maxBytes=0)
        self.assertFalse(rh.shouldRollover(None))
        rh.close()
        # bpo-45401 - test with special file
        # We set maxBytes to 1 so that rollover would normally happen, except
        # for the check for regular files
        rh = logging.handlers.RotatingFileHandler(
            os.devnull, encoding="utf-8", maxBytes=1
        )
        self.assertFalse(rh.shouldRollover(self.next_rec()))
        rh.close()

    def test_should_rollover(self):
        rh = logging.handlers.RotatingFileHandler(self.fn, encoding="utf-8", maxBytes=1)
        self.assertTrue(rh.shouldRollover(self.next_rec()))
        rh.close()

    def test_file_created(self):
        # checks that the file is created and assumes it was created
        # by us
        rh = logging.handlers.RotatingFileHandler(self.fn, encoding="utf-8")
        rh.emit(self.next_rec())
        self.assertLogFile(self.fn)
        rh.close()

    def test_rollover_filenames(self):
        def namer(name):
            return name + ".test"

        rh = logging.handlers.RotatingFileHandler(
            self.fn, encoding="utf-8", backupCount=2, maxBytes=1
        )
        rh.namer = namer
        rh.emit(self.next_rec())
        self.assertLogFile(self.fn)
        rh.emit(self.next_rec())
        self.assertLogFile(namer(self.fn + ".1"))
        rh.emit(self.next_rec())
        self.assertLogFile(namer(self.fn + ".2"))
        self.assertFalse(os.path.exists(namer(self.fn + ".3")))
        rh.close()

    def test_namer_rotator_inheritance(self):
        class HandlerWithNamerAndRotator(logging.handlers.RotatingFileHandler):
            def namer(self, name):
                return name + ".test"

            def rotator(self, source, dest):
                if os.path.exists(source):
                    os.replace(source, dest + ".rotated")

        rh = HandlerWithNamerAndRotator(
            self.fn, encoding="utf-8", backupCount=2, maxBytes=1
        )
        self.assertEqual(rh.namer(self.fn), self.fn + ".test")
        rh.emit(self.next_rec())
        self.assertLogFile(self.fn)
        rh.emit(self.next_rec())
        self.assertLogFile(rh.namer(self.fn + ".1") + ".rotated")
        self.assertFalse(os.path.exists(rh.namer(self.fn + ".1")))
        rh.close()

    def test_rotator(self):
        def namer(name):
            return name + ".gz"

        def rotator(source, dest):
            with open(source, "rb") as sf:
                data = sf.read()
                compressed = zlib.compress(data, 9)
                with open(dest, "wb") as df:
                    df.write(compressed)
            os.remove(source)

        rh = logging.handlers.RotatingFileHandler(
            self.fn, encoding="utf-8", backupCount=2, maxBytes=1
        )
        rh.rotator = rotator
        rh.namer = namer
        m1 = self.next_rec()
        rh.emit(m1)
        self.assertLogFile(self.fn)
        m2 = self.next_rec()
        rh.emit(m2)
        fn = namer(self.fn + ".1")
        self.assertLogFile(fn)
        newline = os.linesep
        with open(fn, "rb") as f:
            compressed = f.read()
            data = zlib.decompress(compressed)
            self.assertEqual(data.decode("ascii"), m1.msg + newline)
        rh.emit(self.next_rec())
        fn = namer(self.fn + ".2")
        self.assertLogFile(fn)
        with open(fn, "rb") as f:
            compressed = f.read()
            data = zlib.decompress(compressed)
            self.assertEqual(data.decode("ascii"), m1.msg + newline)
        rh.emit(self.next_rec())
        fn = namer(self.fn + ".2")
        with open(fn, "rb") as f:
            compressed = f.read()
            data = zlib.decompress(compressed)
            self.assertEqual(data.decode("ascii"), m2.msg + newline)
        self.assertFalse(os.path.exists(namer(self.fn + ".3")))
        rh.close()
