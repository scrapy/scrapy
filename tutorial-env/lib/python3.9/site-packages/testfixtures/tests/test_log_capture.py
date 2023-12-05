from logging import getLogger, ERROR
from unittest import TestCase

from testfixtures.shouldraise import ShouldAssert
from testfixtures.mock import patch

from testfixtures import (
    log_capture, compare, Comparison as C, LogCapture
)

root = getLogger()
one = getLogger('one')
two = getLogger('two')
child = getLogger('one.child')


class TestLog_Capture(TestCase):

    @log_capture('two', 'one.child')
    @log_capture('one')
    @log_capture()
    def test_logging(self, l1, l2, l3):
        # we can now log as normal
        root.info('1')
        one.info('2')
        two.info('3')
        child.info('4')
        # and later check what was logged
        l1.check(
            ('root', 'INFO', '1'),
            ('one', 'INFO', '2'),
            ('two', 'INFO', '3'),
            ('one.child', 'INFO', '4'),
            )
        l2.check(
            ('one', 'INFO', '2'),
            ('one.child', 'INFO', '4')
            )
        l3.check(
            ('two', 'INFO', '3'),
            ('one.child', 'INFO', '4')
            )
        # each logger also exposes the real
        # log records should anything else be neeeded
        compare(l3.records, [
            C('logging.LogRecord'),
            C('logging.LogRecord'),
            ])

    @log_capture(ensure_checks_above=ERROR)
    def test_simple_strict(self, l):
        root.error('during')
        l.check(("root", "ERROR", "during"))

    def test_uninstall_properly(self):
        root = getLogger()
        child = getLogger('child')
        before_root = root.handlers[:]
        before_child = child.handlers[:]
        try:
            old_root_level = root.level
            root.setLevel(49)
            old_child_level = child.level
            child.setLevel(69)

            @log_capture('child')
            @log_capture()
            def test_method(l1, l2):
                root = getLogger()
                root.info('1')
                self.assertEqual(root.level, 1)
                child = getLogger('child')
                self.assertEqual(child.level, 1)
                child.info('2')
                l1.check(
                    ('root', 'INFO', '1'),
                    ('child', 'INFO', '2'),
                    )
                l2.check(
                    ('child', 'INFO', '2'),
                    )

            test_method()

            self.assertEqual(root.level, 49)
            self.assertEqual(child.level, 69)

            self.assertEqual(root.handlers, before_root)
            self.assertEqual(child.handlers, before_child)

        finally:
            root.setLevel(old_root_level)
            child.setLevel(old_child_level)

    @log_capture()
    def test_decorator_returns_logcapture(self, l):
        # check for what we get, so we only have to write
        # tests in test_logcapture.py
        self.assertTrue(isinstance(l, LogCapture))

    def test_remove_existing_handlers(self):
        logger = getLogger()
        # get original handlers
        original = logger.handlers
        try:
            # put in a stub which will blow up if used
            logger.handlers = start = [object()]

            @log_capture()
            def test_method(l):
                logger.info('during')
                l.check(('root', 'INFO', 'during'))

            test_method()

            compare(logger.handlers, start)

        finally:
            logger.handlers = original

    def test_clear_global_state(self):
        from logging import _handlers, _handlerList
        capture = LogCapture()
        capture.uninstall()
        self.assertFalse(capture in _handlers)
        self.assertFalse(capture in _handlerList)

    def test_no_propogate(self):
        logger = getLogger('child')
        # paranoid check
        compare(logger.propagate, True)

        @log_capture('child', propagate=False)
        def test_method(l):
            logger.info('a log message')
            l.check(('child', 'INFO', 'a log message'))

        with LogCapture() as global_log:
            test_method()

        global_log.check()
        compare(logger.propagate, True)

    def test_different_attributes(self):
        with LogCapture(attributes=('funcName', 'processName')) as log:
            getLogger().info('oh hai')
        log.check(
            ('test_different_attributes', 'MainProcess')
        )

    def test_missing_attribute(self):
        with LogCapture(attributes=('msg', 'lolwut')) as log:
            getLogger().info('oh %s', 'hai')
        log.check(
            ('oh %s', None)
        )

    def test_single_attribute(self):
        # one which isn't a string, to boot!
        with LogCapture(attributes=['msg']) as log:
            getLogger().info(dict(foo='bar', baz='bob'))
        log.check(
            dict(foo='bar', baz='bob'),
        )

    def test_callable_instead_of_attribute(self):
        def extract_msg(record):
            return {k: v for (k, v) in record.msg.items()
                    if k != 'baz'}
        with LogCapture(attributes=extract_msg) as log:
            getLogger().info(dict(foo='bar', baz='bob'))
        log.check(
            dict(foo='bar'),
        )

    def test_msg_is_none(self):
        with LogCapture(attributes=('msg', 'foo')) as log:
            getLogger().info(None, extra=dict(foo='bar'))
        log.check(
            (None, 'bar')
        )

    def test_normal_check(self):
        with LogCapture() as log:
            getLogger().info('oh hai')

        with ShouldAssert(
            "sequence not as expected:\n\n"
            "same:\n"
            "()\n\n"
            "expected:\n"
            "(('root', 'INFO', 'oh noez'),)\n\n"
            "actual:\n"
            "(('root', 'INFO', 'oh hai'),)"
        ):
            log.check(('root', 'INFO', 'oh noez'))

    def test_recursive_check(self):

        with LogCapture(recursive_check=True) as log:
            getLogger().info('oh hai')

        with ShouldAssert(
            "sequence not as expected:\n\n"
            "same:\n()\n\n"
            "expected:\n(('root', 'INFO', 'oh noez'),)\n\n"
            "actual:\n(('root', 'INFO', 'oh hai'),)\n\n"
            "While comparing [0]: sequence not as expected:\n\n"
            "same:\n('root', 'INFO')\n\n"
            "expected:\n"
            "('oh noez',)\n\n"
            "actual:\n"
            "('oh hai',)\n\n"
            "While comparing [0][2]: 'oh noez' (expected) != 'oh hai' (actual)"
        ):
            log.check(('root', 'INFO', 'oh noez'))

    @log_capture()
    @patch('testfixtures.tests.sample1.SampleClassA')
    def test_patch_then_log(self, a1, a2):
        actual = [type(c).__name__ for c in (a1, a2)]
        compare(actual, expected=['MagicMock', 'LogCaptureForDecorator'])

    @patch('testfixtures.tests.sample1.SampleClassA')
    @log_capture()
    def test_log_then_patch(self, a1, a2):
        actual = [type(c).__name__ for c in (a1, a2)]
        compare(actual, expected=['LogCaptureForDecorator', 'MagicMock'])


class BaseCaptureTest(TestCase):
    a = 33

    @log_capture()
    def test_logs_if_a_smaller_than_44(self, logs):
        logger = getLogger()
        if self.a < 44:
            logger.info('{} is smaller than 44'.format(self.a))

        logs.check(
            ('root', 'INFO', '{} is smaller than 44'.format(self.a)),
        )


class SubclassCaptureTest(BaseCaptureTest):
    a = 2
