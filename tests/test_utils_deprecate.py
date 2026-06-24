import inspect
import warnings
from unittest import mock

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.deprecate import create_deprecated_class, update_classpath


class MyWarning(UserWarning):
    pass


class SomeBaseClass:
    pass


class NewName(SomeBaseClass):
    pass


class TestWarnWhenSubclassed:
    def test_no_warning_on_definition(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", category=ScrapyDeprecationWarning)
            create_deprecated_class("Deprecated", NewName)

    def test_subclassing_warning_message(self):
        msg = (
            r"tests\.test_utils_deprecate\.UserClass inherits from "
            r"deprecated class tests\.test_utils_deprecate\.Deprecated, "
            r"please inherit from tests\.test_utils_deprecate\.NewName."
            r" \(warning only on first subclass, there may be others\)"
        )
        Deprecated = create_deprecated_class(
            "Deprecated", NewName, warn_category=MyWarning
        )
        with pytest.warns(MyWarning, match=msg) as w:

            class UserClass(Deprecated):
                pass

        assert w[0].lineno == inspect.getsourcelines(UserClass)[1]

    def test_custom_class_paths(self):
        Deprecated = create_deprecated_class(
            "Deprecated",
            NewName,
            new_class_path="foo.NewClass",
            old_class_path="bar.OldClass",
            warn_category=MyWarning,
        )

        with pytest.warns(
            MyWarning,
            match=r"UserClass inherits from deprecated class bar\.OldClass, please inherit from foo\.NewClass",
        ):

            class UserClass(Deprecated):
                pass

        with pytest.warns(
            MyWarning,
            match=r"bar\.OldClass is deprecated, instantiate foo\.NewClass instead",
        ):
            _ = Deprecated()

    def test_subclassing_warns_only_on_direct_children(self):
        Deprecated = create_deprecated_class(
            "Deprecated", NewName, warn_once=False, warn_category=MyWarning
        )

        with pytest.warns(
            MyWarning,
            match="UserClass inherits from deprecated class",
        ):

            class UserClass(Deprecated):
                pass

        with warnings.catch_warnings():
            warnings.simplefilter("error", MyWarning)

            class NoWarnOnMe(UserClass):
                pass

    def test_subclassing_warns_once_by_default(self):
        Deprecated = create_deprecated_class(
            "Deprecated", NewName, warn_category=MyWarning
        )

        with pytest.warns(
            MyWarning,
            match="UserClass inherits from deprecated class",
        ):

            class UserClass(Deprecated):
                pass

        with warnings.catch_warnings():
            warnings.simplefilter("error", MyWarning)

            class FooClass(Deprecated):
                pass

            class BarClass(Deprecated):
                pass

    def test_warning_on_instance(self):
        Deprecated = create_deprecated_class(
            "Deprecated", NewName, warn_category=MyWarning
        )

        with pytest.warns(MyWarning) as w:
            _, lineno = Deprecated(), inspect.getlineno(inspect.currentframe())

        w = [x for x in w if x.category is MyWarning]
        assert len(w) == 1
        assert (
            str(w[0].message) == "tests.test_utils_deprecate.Deprecated is deprecated, "
            "instantiate tests.test_utils_deprecate.NewName instead."
        )
        assert w[0].lineno == lineno

        # ignore subclassing warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", MyWarning)

            class UserClass(Deprecated):
                pass

        with warnings.catch_warnings():
            warnings.simplefilter("error", MyWarning)
            UserClass()  # subclass instances don't warn

    def test_warning_auto_message(self):
        Deprecated = create_deprecated_class("Deprecated", NewName)
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"UserClass2 inherits from deprecated class tests\.test_utils_deprecate\.Deprecated, please inherit from tests\.test_utils_deprecate\.NewName",
        ):

            class UserClass2(Deprecated):
                pass

    def test_issubclass(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            DeprecatedName = create_deprecated_class("DeprecatedName", NewName)

            class UpdatedUserClass1(NewName):
                pass

            class UpdatedUserClass1a(NewName):
                pass

            class OutdatedUserClass1(DeprecatedName):
                pass

            class OutdatedUserClass1a(DeprecatedName):
                pass

            class UnrelatedClass:
                pass

        assert issubclass(UpdatedUserClass1, NewName)
        assert issubclass(UpdatedUserClass1a, NewName)
        assert issubclass(UpdatedUserClass1, DeprecatedName)
        assert issubclass(UpdatedUserClass1a, DeprecatedName)
        assert issubclass(OutdatedUserClass1, DeprecatedName)
        assert not issubclass(UnrelatedClass, DeprecatedName)
        assert not issubclass(OutdatedUserClass1, OutdatedUserClass1a)
        assert not issubclass(OutdatedUserClass1a, OutdatedUserClass1)

        with pytest.raises(TypeError):
            issubclass(object(), DeprecatedName)

    def test_isinstance(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            DeprecatedName = create_deprecated_class("DeprecatedName", NewName)

            class UpdatedUserClass2(NewName):
                pass

            class UpdatedUserClass2a(NewName):
                pass

            class OutdatedUserClass2(DeprecatedName):
                pass

            class OutdatedUserClass2a(DeprecatedName):
                pass

            class UnrelatedClass:
                pass

        assert isinstance(UpdatedUserClass2(), NewName)
        assert isinstance(UpdatedUserClass2a(), NewName)
        assert isinstance(UpdatedUserClass2(), DeprecatedName)
        assert isinstance(UpdatedUserClass2a(), DeprecatedName)
        assert isinstance(OutdatedUserClass2(), DeprecatedName)
        assert isinstance(OutdatedUserClass2a(), DeprecatedName)
        assert not isinstance(OutdatedUserClass2a(), OutdatedUserClass2)
        assert not isinstance(OutdatedUserClass2(), OutdatedUserClass2a)
        assert not isinstance(UnrelatedClass(), DeprecatedName)

    def test_clsdict(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            Deprecated = create_deprecated_class("Deprecated", NewName, {"foo": "bar"})

        assert Deprecated.foo == "bar"

    def test_deprecate_a_class_with_custom_metaclass(self):
        Meta1 = type("Meta1", (type,), {})
        New = Meta1("New", (), {})
        create_deprecated_class("Deprecated", New)

    def test_deprecate_subclass_of_deprecated_class(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", MyWarning)
            Deprecated = create_deprecated_class(
                "Deprecated", NewName, warn_category=MyWarning
            )
            AlsoDeprecated = create_deprecated_class(
                "AlsoDeprecated",
                Deprecated,
                new_class_path="foo.Bar",
                warn_category=MyWarning,
            )

        with pytest.warns(
            MyWarning,
            match=r"AlsoDeprecated is deprecated, instantiate foo\.Bar instead",
        ):
            AlsoDeprecated()

        with pytest.warns(
            MyWarning,
            match=r"UserClass inherits from deprecated class tests\.test_utils_deprecate\.AlsoDeprecated, please inherit from foo\.Bar",
        ):

            class UserClass(AlsoDeprecated):
                pass

    def test_inspect_stack(self):
        with (
            mock.patch("inspect.stack", side_effect=IndexError),
            pytest.warns(UserWarning, match="Error detecting parent module"),
        ):
            create_deprecated_class("DeprecatedName", NewName)


@mock.patch(
    "scrapy.utils.deprecate.DEPRECATION_RULES",
    [
        ("scrapy.contrib.pipeline.", "scrapy.pipelines."),
        ("scrapy.contrib.", "scrapy.extensions."),
    ],
)
class TestUpdateClassPath:
    def test_old_path_gets_fixed(self):
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="`scrapy.contrib.debug.Debug` class is deprecated, use `scrapy.extensions.debug.Debug` instead",
        ):
            output = update_classpath("scrapy.contrib.debug.Debug")
        assert output == "scrapy.extensions.debug.Debug"

    def test_sorted_replacement(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            output = update_classpath("scrapy.contrib.pipeline.Pipeline")
        assert output == "scrapy.pipelines.Pipeline"

    def test_unmatched_path_stays_the_same(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            output = update_classpath("scrapy.unmatched.Path")
        assert output == "scrapy.unmatched.Path"

    def test_returns_nonstring(self):
        for notastring in [None, True, [1, 2, 3], object()]:
            assert update_classpath(notastring) == notastring
