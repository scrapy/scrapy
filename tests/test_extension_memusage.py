# tests/test_extensions/test_memusage.py
from types import SimpleNamespace
import pytest
import types

import scrapy.extensions.memusage as memusage


# --- small test helpers / fakes ------------------------------------------------
class DummyStats:
    def __init__(self):
        self._d = {}

    def set_value(self, key, value, spider=None):
        self._d[key] = value

    def max_value(self, key, value, spider=None):
        self._d[key] = max(self._d.get(key, 0), value)

    def get_value(self, key, default=None):
        return self._d.get(key, default)


class DummySignals:
    def connect(self, *args, **kwargs):
        # MemoryUsage.__init__ connects signals; no action needed in tests
        return None


class DummyEngine:
    def __init__(self):
        self.spider = None
        self.closed = None
        self.stopped = False

    def close_spider(self, spider, reason):
        self.closed = (spider, reason)

    def stop(self):
        self.stopped = True


class DummyMail:
    def __init__(self):
        self.sent = []

    def send(self, rcpts, subject, body):
        self.sent.append((rcpts, subject, body))


class DummySettings:
    def __init__(self, mapping):
        self._m = dict(mapping)

    def getbool(self, key):
        return bool(self._m.get(key))

    def getlist(self, key):
        return self._m.get(key, [])

    def getint(self, key, default=0):
        return int(self._m.get(key, default))

    def getfloat(self, key, default=0.0):
        return float(self._m.get(key, default))

    def __getitem__(self, key):
        # used for BOT_NAME in messages
        return self._m[key]


def make_crawler(settings_map):
    settings = DummySettings(settings_map)
    stats = DummyStats()
    signals = DummySignals()
    engine = DummyEngine()
    crawler = SimpleNamespace(settings=settings, stats=stats, signals=signals, engine=engine)
    return crawler


# --- actual tests -------------------------------------------------------------
def test_get_virtual_size_linux(monkeypatch):
    """get_virtual_size should use resource.getrusage().ru_maxrss and multiply by 1024 on non-darwin."""
    # arrange
    monkeypatch.setattr(memusage, "MailSender", SimpleNamespace)  # avoid real mail construction
    crawler = make_crawler({
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 0,
        "MEMUSAGE_WARNING_MB": 0,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 1,
        "BOT_NAME": "tests",
    })
    # create instance
    mu = memusage.MemoryUsage(crawler)

    # fake resource with getrusage
    class FakeResource:
        RUSAGE_SELF = 0

        @staticmethod
        def getrusage(_):
            return SimpleNamespace(ru_maxrss=1234)

    mu.resource = FakeResource()
    # pretend platform is linux (non-darwin) so code multiplies by 1024
    monkeypatch.setattr(memusage, "sys", types.SimpleNamespace(platform="linux"))

    # act
    value = mu.get_virtual_size()

    # assert: 1234 * 1024
    assert value == 1234 * 1024


def test_update_sets_max(monkeypatch):
    monkeypatch.setattr(memusage, "MailSender", SimpleNamespace)
    crawler = make_crawler({
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 0,
        "MEMUSAGE_WARNING_MB": 0,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 1,
        "BOT_NAME": "tests",
    })
    mu = memusage.MemoryUsage(crawler)

    # stub get_virtual_size and call update()
    mu.get_virtual_size = lambda: 555
    mu.update()

    assert crawler.stats.get_value("memusage/max") == 555


def test_check_limit_triggers_mail_and_close(monkeypatch):
    # prepare dummy mailer and patch MailSender.from_crawler to return it
    dummy_mail = DummyMail()
    monkeypatch.setattr(memusage, "MailSender", SimpleNamespace)
    # monkeypatch the from_crawler factory to return our dummy mail
    monkeypatch.setattr(memusage.MailSender, "from_crawler", staticmethod(lambda c: dummy_mail))

    crawler = make_crawler({
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 1,        # 1 MB limit
        "MEMUSAGE_WARNING_MB": 0,
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 1,
        "MEMUSAGE_NOTIFY_MAIL": ["a@b.c"],
        "BOT_NAME": "tests",
    })

    mu = memusage.MemoryUsage(crawler)

    # force a big memory reading (2 MB)
    mu.get_virtual_size = lambda: 2 * 1024 * 1024

    # simulate crawler having a spider so close_spider(path) branch is used
    crawler.engine.spider = object()

    # act
    mu._check_limit()

    # assert the limit flag and notification flag are set in stats
    assert crawler.stats.get_value("memusage/limit_reached") == 1
    assert crawler.stats.get_value("memusage/limit_notified") == 1
    # a mail should have been sent via our DummyMail
    assert dummy_mail.sent, "expected a notification email to be sent"
    # close_spider should have been invoked on the engine
    assert crawler.engine.closed is not None


def test_check_warning_only_once(monkeypatch):
    monkeypatch.setattr(memusage, "MailSender", SimpleNamespace)
    monkeypatch.setattr(memusage.MailSender, "from_crawler", staticmethod(lambda c: DummyMail()))

    crawler = make_crawler({
        "MEMUSAGE_ENABLED": True,
        "MEMUSAGE_LIMIT_MB": 0,
        "MEMUSAGE_WARNING_MB": 1,  # warn at 1MB
        "MEMUSAGE_CHECK_INTERVAL_SECONDS": 1,
        "MEMUSAGE_NOTIFY_MAIL": ["a@b.c"],
        "BOT_NAME": "tests",
    })
    mu = memusage.MemoryUsage(crawler)

    # first call: over warning
    mu.get_virtual_size = lambda: 2 * 1024 * 1024
    mu._check_warning()
    assert crawler.stats.get_value("memusage/warning_reached") == 1
    assert mu.warned is True

    # second call: warning should not re-trigger
    # set warned True and call again with larger value
    mu.get_virtual_size = lambda: 10 * 1024 * 1024
    mu._check_warning()
    # still only one warning flag
    assert crawler.stats.get_value("memusage/warning_reached") == 1
