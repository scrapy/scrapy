import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from scrapy.item import Field, Item
from scrapy.utils.misc import (
    arg_to_iter,
    build_from_crawler,
    create_instance,
    load_object,
    rel_has_nofollow,
    set_environ,
    walk_modules,
)


class TestUtilsMisc:
    def test_load_object_class(self):
        obj = load_object(Field)
        assert obj is Field
        obj = load_object("scrapy.item.Field")
        assert obj is Field

    def test_load_object_function(self):
        obj = load_object(load_object)
        assert obj is load_object
        obj = load_object("scrapy.utils.misc.load_object")
        assert obj is load_object

    def test_load_object_exceptions(self):
        with pytest.raises(ImportError):
            load_object("nomodule999.mod.function")
        with pytest.raises(NameError):
            load_object("scrapy.utils.misc.load_object999")
        with pytest.raises(TypeError):
            load_object({})

    def test_walk_modules(self):
        mods = walk_modules("tests.test_utils_misc.test_walk_modules")
        expected = [
            "tests.test_utils_misc.test_walk_modules",
            "tests.test_utils_misc.test_walk_modules.mod",
            "tests.test_utils_misc.test_walk_modules.mod.mod0",
            "tests.test_utils_misc.test_walk_modules.mod1",
        ]
        assert {m.__name__ for m in mods} == set(expected)

        mods = walk_modules("tests.test_utils_misc.test_walk_modules.mod")
        expected = [
            "tests.test_utils_misc.test_walk_modules.mod",
            "tests.test_utils_misc.test_walk_modules.mod.mod0",
        ]
        assert {m.__name__ for m in mods} == set(expected)

        mods = walk_modules("tests.test_utils_misc.test_walk_modules.mod1")
        expected = [
            "tests.test_utils_misc.test_walk_modules.mod1",
        ]
        assert {m.__name__ for m in mods} == set(expected)

        with pytest.raises(ImportError):
            walk_modules("nomodule999")

    def test_walk_modules_egg(self):
        egg = str(Path(__file__).parent / "test.egg")
        sys.path.append(egg)
        try:
            mods = walk_modules("testegg")
            expected = [
                "testegg.spiders",
                "testegg.spiders.a",
                "testegg.spiders.b",
                "testegg",
            ]
            assert {m.__name__ for m in mods} == set(expected)
        finally:
            sys.path.remove(egg)

    def test_arg_to_iter(self):
        class TestItem(Item):
            name = Field()

        assert hasattr(arg_to_iter(None), "__iter__")
        assert hasattr(arg_to_iter(100), "__iter__")
        assert hasattr(arg_to_iter("lala"), "__iter__")
        assert hasattr(arg_to_iter([1, 2, 3]), "__iter__")
        assert hasattr(arg_to_iter(c for c in "abcd"), "__iter__")

        assert not list(arg_to_iter(None))
        assert list(arg_to_iter("lala")) == ["lala"]
        assert list(arg_to_iter(100)) == [100]
        assert list(arg_to_iter(c for c in "abc")) == ["a", "b", "c"]
        assert list(arg_to_iter([1, 2, 3])) == [1, 2, 3]
        assert list(arg_to_iter({"a": 1})) == [{"a": 1}]
        assert list(arg_to_iter(TestItem(name="john"))) == [TestItem(name="john")]

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_create_instance(self):
        settings = mock.MagicMock()
        crawler = mock.MagicMock(spec_set=["settings"])
        args = (True, 100.0)
        kwargs = {"key": "val"}

        def _test_with_settings(mock, settings):
            create_instance(mock, settings, None, *args, **kwargs)
            if hasattr(mock, "from_crawler"):
                assert mock.from_crawler.call_count == 0
            if hasattr(mock, "from_settings"):
                mock.from_settings.assert_called_once_with(settings, *args, **kwargs)
                assert mock.call_count == 0
            else:
                mock.assert_called_once_with(*args, **kwargs)

        def _test_with_crawler(mock, settings, crawler):
            create_instance(mock, settings, crawler, *args, **kwargs)
            if hasattr(mock, "from_crawler"):
                mock.from_crawler.assert_called_once_with(crawler, *args, **kwargs)
                if hasattr(mock, "from_settings"):
                    assert mock.from_settings.call_count == 0
                assert mock.call_count == 0
            elif hasattr(mock, "from_settings"):
                mock.from_settings.assert_called_once_with(settings, *args, **kwargs)
                assert mock.call_count == 0
            else:
                mock.assert_called_once_with(*args, **kwargs)

        # Check usage of correct constructor using four mocks:
        #   1. with no alternative constructors
        #   2. with from_settings() constructor
        #   3. with from_crawler() constructor
        #   4. with from_settings() and from_crawler() constructor
        spec_sets = (
            ["__qualname__"],
            ["__qualname__", "from_settings"],
            ["__qualname__", "from_crawler"],
            ["__qualname__", "from_settings", "from_crawler"],
        )
        for specs in spec_sets:
            m = mock.MagicMock(spec_set=specs)
            _test_with_settings(m, settings)
            m.reset_mock()
            _test_with_crawler(m, settings, crawler)

        # Check adoption of crawler settings
        m = mock.MagicMock(spec_set=["__qualname__", "from_settings"])
        create_instance(m, None, crawler, *args, **kwargs)
        m.from_settings.assert_called_once_with(crawler.settings, *args, **kwargs)

        with pytest.raises(
            ValueError, match="Specify at least one of settings and crawler"
        ):
            create_instance(m, None, None)

        m.from_settings.return_value = None
        with pytest.raises(TypeError):
            create_instance(m, settings, None)

    def test_build_from_crawler(self):
        settings = mock.MagicMock()
        crawler = mock.MagicMock(spec_set=["settings"])
        args = (True, 100.0)
        kwargs = {"key": "val"}

        def _test_with_crawler(mock, settings, crawler):
            build_from_crawler(mock, crawler, *args, **kwargs)
            if hasattr(mock, "from_crawler"):
                mock.from_crawler.assert_called_once_with(crawler, *args, **kwargs)
                if hasattr(mock, "from_settings"):
                    assert mock.from_settings.call_count == 0
                assert mock.call_count == 0
            elif hasattr(mock, "from_settings"):
                mock.from_settings.assert_called_once_with(settings, *args, **kwargs)
                assert mock.call_count == 0
            else:
                mock.assert_called_once_with(*args, **kwargs)

        # Check usage of correct constructor using three mocks:
        #   1. with no alternative constructors
        #   2. with from_crawler() constructor
        #   3. with from_settings() and from_crawler() constructor
        spec_sets = (
            ["__qualname__"],
            ["__qualname__", "from_crawler"],
            ["__qualname__", "from_settings", "from_crawler"],
        )
        for specs in spec_sets:
            m = mock.MagicMock(spec_set=specs)
            _test_with_crawler(m, settings, crawler)
            m.reset_mock()

        # Check adoption of crawler
        m = mock.MagicMock(spec_set=["__qualname__", "from_crawler"])
        m.from_crawler.return_value = None
        with pytest.raises(TypeError):
            build_from_crawler(m, crawler, *args, **kwargs)

    def test_set_environ(self):
        assert os.environ.get("some_test_environ") is None
        with set_environ(some_test_environ="test_value"):
            assert os.environ.get("some_test_environ") == "test_value"
        assert os.environ.get("some_test_environ") is None

        os.environ["some_test_environ"] = "test"
        assert os.environ.get("some_test_environ") == "test"
        with set_environ(some_test_environ="test_value"):
            assert os.environ.get("some_test_environ") == "test_value"
        assert os.environ.get("some_test_environ") == "test"

    def test_rel_has_nofollow(self):
        assert rel_has_nofollow("ugc nofollow") is True
        assert rel_has_nofollow("ugc,nofollow") is True
        assert rel_has_nofollow("ugc") is False
        assert rel_has_nofollow("nofollow") is True
        assert rel_has_nofollow("nofollowfoo") is False
        assert rel_has_nofollow("foonofollow") is False
        assert rel_has_nofollow("ugc,  ,  nofollow") is True
