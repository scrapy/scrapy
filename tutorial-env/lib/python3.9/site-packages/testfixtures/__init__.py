class singleton(object):

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '<%s>' % self.name

    __str__ = __repr__


not_there: singleton = singleton('not_there')


from testfixtures.comparison import (
    Comparison, StringComparison, RoundComparison, compare, diff, RangeComparison,
    SequenceComparison, Subset, Permutation, MappingComparison
)
from testfixtures.datetime import mock_datetime, mock_date, mock_time
from testfixtures.logcapture import LogCapture, log_capture
from testfixtures.outputcapture import OutputCapture
from testfixtures.resolve import resolve
from testfixtures.replace import (
    Replacer,
    Replace,
    replace,
    replace_in_environ,
    replace_on_class,
    replace_in_module,
)
from testfixtures.shouldraise import ShouldRaise, should_raise, ShouldAssert
from testfixtures.shouldwarn import ShouldWarn, ShouldNotWarn
from testfixtures.tempdirectory import TempDirectory, tempdir
from testfixtures.utils import wrap, generator


# backwards compatibility for the old names
test_datetime = mock_datetime
test_datetime.__test__ = False
test_date = mock_date
test_date.__test__ = False
test_time = mock_time
test_time.__test__ = False
