from __future__ import annotations

import warnings
from unittest import mock

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.deprecate import attribute, create_deprecated_class, update_classpath


class NewName:
    pass


def test_attribute():
    with pytest.warns(
        ScrapyDeprecationWarning,
        match=r"NewName\.old attribute is deprecated and will be no longer supported"
        r" in Scrapy 1\.0, use NewName\.new attribute instead",
    ):
        attribute(NewName(), "old", "new", version="1.0")


class TestCreateDeprecatedClass:
    def test_warns_about_itself(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match=r"create_deprecated_class\(\) is deprecated"
        ):
            create_deprecated_class("Deprecated", NewName)

    def test_returns_a_working_alias(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            Deprecated = create_deprecated_class(
                "Deprecated", NewName, {"foo": "bar"}, warn_once=False
            )

        assert Deprecated.__module__ == __name__
        assert Deprecated.foo == "bar"  # type: ignore[attr-defined]

        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"tests\.test_utils_deprecate\.UserClass inherits from deprecated"
            r" class tests\.test_utils_deprecate\.Deprecated, please inherit from"
            r" tests\.test_utils_deprecate\.NewName\.",
        ):

            class UserClass(Deprecated):  # type: ignore[misc, valid-type]
                pass

        assert issubclass(UserClass, Deprecated)


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


class TestAttribute:
    class MyClass:
        pass

    def test_default_version(self):
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"MyClass\.old attribute is deprecated and will be no longer "
            r"supported in Scrapy 0\.12, use MyClass\.new attribute instead",
        ):
            attribute(self.MyClass(), "old", "new")

    def test_custom_version(self):
        with pytest.warns(ScrapyDeprecationWarning, match="in Scrapy 3.0"):
            attribute(self.MyClass(), "old", "new", "3.0")
