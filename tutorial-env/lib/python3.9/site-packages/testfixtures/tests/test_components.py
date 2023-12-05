from testfixtures.mock import Mock, call
from testfixtures import Replacer, compare
from testfixtures.components import TestComponents
from unittest import TestCase

from warnings import catch_warnings


class ComponentsTests(TestCase):

    def test_atexit(self):
        m = Mock()
        with Replacer() as r:
            r.replace('atexit.register', m.register)

            c = TestComponents()

            expected = [call.register(c.atexit)]

            compare(expected, m.mock_calls)

            with catch_warnings(record=True) as w:
                c.atexit()
                self.assertTrue(len(w), 1)
                compare(str(w[0].message), (  # pragma: no branch
                    "TestComponents instances not uninstalled by shutdown!"
                    ))

            c.uninstall()

            compare(expected, m.mock_calls)

            # check re-running has no ill effects
            c.atexit()

            compare(expected, m.mock_calls)
