from unittest import TestCase

from testfixtures import Replacer, ShouldRaise


class TestReplacer(TestCase):

    def test_function(self):
        from testfixtures.tests import sample1
        assert sample1.z() == 'original z'

        def test_z():
          return 'replacement z'

        r = Replacer()
        r.replace('testfixtures.tests.sample1.z',test_z)

        assert sample1.z() == 'replacement z'

        r.restore()

        assert sample1.z() == 'original z'

    def test_class(self):
        from testfixtures.tests import sample1
        x = sample1.X()
        assert x.__class__.__name__ == 'X'

        class XReplacement(sample1.X): pass

        r = Replacer()
        r.replace('testfixtures.tests.sample1.X', XReplacement)

        x = sample1.X()
        assert x.__class__.__name__ == 'XReplacement'
        assert sample1.X().y() == 'original y'

        r.restore()

        x = sample1.X()
        assert x.__class__.__name__ == 'X'

    def test_method(self):
        from testfixtures.tests import sample1
        assert sample1.X().y() == 'original y'

        def test_y(self):
          return 'replacement y'

        r = Replacer()
        r.replace('testfixtures.tests.sample1.X.y',test_y)

        assert sample1.X().y()[:38] == 'replacement y'

        r.restore()

        assert sample1.X().y() == 'original y'

    def test_class_method(self):
        from testfixtures.tests import sample1
        c = sample1.X
        assert sample1.X.aMethod() is c

        def rMethod(cls):
          return cls, 1

        r = Replacer()
        r.replace('testfixtures.tests.sample1.X.aMethod',rMethod)

        sample1.X.aMethod()
        assert sample1.X.aMethod() == (c, 1)

        r.restore()

        sample1.X.aMethod()
        assert sample1.X.aMethod() is c

    def test_multiple_replace(self):
        from testfixtures.tests import sample1
        assert sample1.z() == 'original z'
        assert sample1.X().y() == 'original y'

        def test_y(self):
          return self.__class__.__name__
        def test_z():
          return 'replacement z'

        r = Replacer()
        r.replace('testfixtures.tests.sample1.z',test_z)
        r.replace('testfixtures.tests.sample1.X.y',test_y)

        assert sample1.z() == 'replacement z'
        assert sample1.X().y() == 'X'

        r.restore()

        assert sample1.z() == 'original z'
        assert sample1.X().y() == 'original y'

    def test_gotcha(self):
        # Just because you replace an object in one context:

        from testfixtures.tests import sample1
        from testfixtures.tests import sample2
        assert sample1.z() == 'original z'

        def test_z():
          return 'replacement z'

        r = Replacer()
        r.replace('testfixtures.tests.sample1.z',test_z)

        assert sample1.z() == 'replacement z'

        # Doesn't meant that it's replaced in all contexts:

        assert sample2.z() == 'original z'

        r.restore()

    def test_remove_called_twice(self):
        from testfixtures.tests import sample1

        def test_z(): pass

        r = Replacer()
        r.replace('testfixtures.tests.sample1.z',test_z)

        r.restore()
        assert sample1.z() == 'original z'

        r.restore()
        assert sample1.z() == 'original z'

    def test_with_statement(self):
        from testfixtures.tests import sample1
        assert sample1.z() == 'original z'

        def test_z():
          return 'replacement z'

        with Replacer() as r:
            r.replace('testfixtures.tests.sample1.z',test_z)
            assert sample1.z() == 'replacement z'

        assert sample1.z() == 'original z'

    def test_not_there(self):
        def test_bad(): pass

        with Replacer() as r:
            with ShouldRaise(AttributeError("Original 'bad' not found")):
                r.replace('testfixtures.tests.sample1.bad', test_bad)
