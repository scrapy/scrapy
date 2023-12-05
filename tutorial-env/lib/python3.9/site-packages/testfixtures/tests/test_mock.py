from testfixtures.mock import Mock, call, ANY

from .test_compare import CompareHelper

class TestCall(CompareHelper):

    def test_non_root_call_not_equal(self):
        self.check_raises(
            call.foo().bar(),
            call.baz().bar(),
            '\n'
            "'call.foo().bar()'\n"
            '!=\n'
            "'call.baz().bar()'"
        )

    def test_non_root_attr_not_equal(self):
        self.check_raises(
            call.foo.bar(),
            call.baz.bar(),
            '\n'
            "'call.foo.bar()'\n"
            '!=\n'
            "'call.baz.bar()'"
        )

    def test_non_root_params_not_equal(self):
        self.check_raises(
            call.foo(x=1).bar(),
            call.foo(x=2).bar(),
            '\n'
            "'call.foo(x=1)'\n"
            '!=\n'
            "'call.foo(x=2)'"
        )

    def test_any(self):
        assert call == ANY

    def test_no_len(self):
        assert not call == object()

    def test_two_elements(self):
        m = Mock()
        m(x=1)
        assert m.call_args == ((), {'x': 1})

    def test_other_empty(self):
        assert call == ()

    def test_other_single(self):
        assert call == ((),)
        assert call == ({},)
        assert call == ('',)

    def test_other_double(self):
        assert call == ('', (),)
        assert call == ('', {},)

    def test_other_quad(self):
        assert not call == (1, 2, 3, 4)


class TestMock(CompareHelper):

    def test_non_root_call_not_equal(self):
        m = Mock()
        m.foo().bar()
        self.check_raises(
            m.mock_calls[-1],
            call.baz().bar(),
            '\n'
            "'call.foo().bar()'\n"
            '!=\n'
            "'call.baz().bar()'"
        )

    def test_non_root_attr_not_equal(self):
        m = Mock()
        m.foo.bar()
        self.check_raises(
            m.mock_calls[-1],
            call.baz.bar(),
            '\n'
            "'call.foo.bar()'\n"
            '!=\n'
            "'call.baz.bar()'"
        )

    def test_non_root_params_not_equal(self):
        m = Mock()
        m.foo(x=1).bar()
        # surprising and annoying (and practically unsolvable :-/):
        assert m.mock_calls[-1] == call.foo(y=2).bar()
