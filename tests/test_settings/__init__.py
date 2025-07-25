# pylint: disable=unsubscriptable-object,unsupported-membership-test,use-implicit-booleaness-not-comparison
# (too many false positives)

import warnings
from unittest import mock

import pytest

from scrapy.core.downloader.handlers.file import FileDownloadHandler
from scrapy.settings import (
    SETTINGS_PRIORITIES,
    BaseSettings,
    Settings,
    SettingsAttribute,
    get_settings_priority,
)
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler

from . import default_settings


class TestSettingsGlobalFuncs:
    def test_get_settings_priority(self):
        for prio_str, prio_num in SETTINGS_PRIORITIES.items():
            assert get_settings_priority(prio_str) == prio_num
        assert get_settings_priority(99) == 99


class TestSettingsAttribute:
    def setup_method(self):
        self.attribute = SettingsAttribute("value", 10)

    def test_set_greater_priority(self):
        self.attribute.set("value2", 20)
        assert self.attribute.value == "value2"
        assert self.attribute.priority == 20

    def test_set_equal_priority(self):
        self.attribute.set("value2", 10)
        assert self.attribute.value == "value2"
        assert self.attribute.priority == 10

    def test_set_less_priority(self):
        self.attribute.set("value2", 0)
        assert self.attribute.value == "value"
        assert self.attribute.priority == 10

    def test_overwrite_basesettings(self):
        original_dict = {"one": 10, "two": 20}
        original_settings = BaseSettings(original_dict, 0)
        attribute = SettingsAttribute(original_settings, 0)

        new_dict = {"three": 11, "four": 21}
        attribute.set(new_dict, 10)
        assert isinstance(attribute.value, BaseSettings)
        assert set(attribute.value) == set(new_dict)
        assert set(original_settings) == set(original_dict)

        new_settings = BaseSettings({"five": 12}, 0)
        attribute.set(new_settings, 0)  # Insufficient priority
        assert set(attribute.value) == set(new_dict)
        attribute.set(new_settings, 10)
        assert set(attribute.value) == set(new_settings)

    def test_repr(self):
        assert repr(self.attribute) == "<SettingsAttribute value='value' priority=10>"


class TestBaseSettings:
    def setup_method(self):
        self.settings = BaseSettings()

    def test_setdefault_not_existing_value(self):
        settings = BaseSettings()
        value = settings.setdefault("TEST_OPTION", "value")
        assert settings["TEST_OPTION"] == "value"
        assert value == "value"
        assert value is not None

    def test_setdefault_existing_value(self):
        settings = BaseSettings({"TEST_OPTION": "value"})
        value = settings.setdefault("TEST_OPTION", None)
        assert settings["TEST_OPTION"] == "value"
        assert value == "value"

    def test_set_new_attribute(self):
        self.settings.set("TEST_OPTION", "value", 0)
        assert "TEST_OPTION" in self.settings.attributes

        attr = self.settings.attributes["TEST_OPTION"]
        assert isinstance(attr, SettingsAttribute)
        assert attr.value == "value"
        assert attr.priority == 0

    def test_set_settingsattribute(self):
        myattr = SettingsAttribute(0, 30)  # Note priority 30
        self.settings.set("TEST_ATTR", myattr, 10)
        assert self.settings.get("TEST_ATTR") == 0
        assert self.settings.getpriority("TEST_ATTR") == 30

    def test_set_instance_identity_on_update(self):
        attr = SettingsAttribute("value", 0)
        self.settings.attributes = {"TEST_OPTION": attr}
        self.settings.set("TEST_OPTION", "othervalue", 10)

        assert "TEST_OPTION" in self.settings.attributes
        assert attr is self.settings.attributes["TEST_OPTION"]

    def test_set_calls_settings_attributes_methods_on_update(self):
        attr = SettingsAttribute("value", 10)
        with (
            mock.patch.object(attr, "__setattr__") as mock_setattr,
            mock.patch.object(attr, "set") as mock_set,
        ):
            self.settings.attributes = {"TEST_OPTION": attr}

            for priority in (0, 10, 20):
                self.settings.set("TEST_OPTION", "othervalue", priority)
                mock_set.assert_called_once_with("othervalue", priority)
                assert not mock_setattr.called
                mock_set.reset_mock()
                mock_setattr.reset_mock()

    def test_setitem(self):
        settings = BaseSettings()
        settings.set("key", "a", "default")
        settings["key"] = "b"
        assert settings["key"] == "b"
        assert settings.getpriority("key") == 20
        settings["key"] = "c"
        assert settings["key"] == "c"
        settings["key2"] = "x"
        assert "key2" in settings
        assert settings["key2"] == "x"
        assert settings.getpriority("key2") == 20

    def test_setdict_alias(self):
        with mock.patch.object(self.settings, "set") as mock_set:
            self.settings.setdict({"TEST_1": "value1", "TEST_2": "value2"}, 10)
            assert mock_set.call_count == 2
            calls = [
                mock.call("TEST_1", "value1", 10),
                mock.call("TEST_2", "value2", 10),
            ]
            mock_set.assert_has_calls(calls, any_order=True)

    def test_setmodule_only_load_uppercase_vars(self):
        class ModuleMock:
            UPPERCASE_VAR = "value"
            MIXEDcase_VAR = "othervalue"
            lowercase_var = "anothervalue"

        self.settings.attributes = {}
        self.settings.setmodule(ModuleMock(), 10)
        assert "UPPERCASE_VAR" in self.settings.attributes
        assert "MIXEDcase_VAR" not in self.settings.attributes
        assert "lowercase_var" not in self.settings.attributes
        assert len(self.settings.attributes) == 1

    def test_setmodule_alias(self):
        with mock.patch.object(self.settings, "set") as mock_set:
            self.settings.setmodule(default_settings, 10)
            mock_set.assert_any_call("TEST_DEFAULT", "defvalue", 10)
            mock_set.assert_any_call("TEST_DICT", {"key": "val"}, 10)

    def test_setmodule_by_path(self):
        self.settings.attributes = {}
        self.settings.setmodule(default_settings, 10)
        ctrl_attributes = self.settings.attributes.copy()

        self.settings.attributes = {}
        self.settings.setmodule("tests.test_settings.default_settings", 10)

        assert set(self.settings.attributes) == set(ctrl_attributes)

        for key in ctrl_attributes:
            attr = self.settings.attributes[key]
            ctrl_attr = ctrl_attributes[key]
            assert attr.value == ctrl_attr.value
            assert attr.priority == ctrl_attr.priority

    def test_update(self):
        settings = BaseSettings({"key_lowprio": 0}, priority=0)
        settings.set("key_highprio", 10, priority=50)
        custom_settings = BaseSettings(
            {"key_lowprio": 1, "key_highprio": 11}, priority=30
        )
        custom_settings.set("newkey_one", None, priority=50)
        custom_dict = {"key_lowprio": 2, "key_highprio": 12, "newkey_two": None}

        settings.update(custom_dict, priority=20)
        assert settings["key_lowprio"] == 2
        assert settings.getpriority("key_lowprio") == 20
        assert settings["key_highprio"] == 10
        assert "newkey_two" in settings
        assert settings.getpriority("newkey_two") == 20

        settings.update(custom_settings)
        assert settings["key_lowprio"] == 1
        assert settings.getpriority("key_lowprio") == 30
        assert settings["key_highprio"] == 10
        assert "newkey_one" in settings
        assert settings.getpriority("newkey_one") == 50

        settings.update({"key_lowprio": 3}, priority=20)
        assert settings["key_lowprio"] == 1

    @pytest.mark.xfail(
        raises=TypeError, reason="BaseSettings.update doesn't support kwargs input"
    )
    def test_update_kwargs(self):
        settings = BaseSettings({"key": 0})
        settings.update(key=1)  # pylint: disable=unexpected-keyword-arg

    @pytest.mark.xfail(
        raises=AttributeError,
        reason="BaseSettings.update doesn't support iterable input",
    )
    def test_update_iterable(self):
        settings = BaseSettings({"key": 0})
        settings.update([("key", 1)])

    def test_update_jsonstring(self):
        settings = BaseSettings({"number": 0, "dict": BaseSettings({"key": "val"})})
        settings.update('{"number": 1, "newnumber": 2}')
        assert settings["number"] == 1
        assert settings["newnumber"] == 2
        settings.set("dict", '{"key": "newval", "newkey": "newval2"}')
        assert settings["dict"]["key"] == "newval"
        assert settings["dict"]["newkey"] == "newval2"

    def test_delete(self):
        settings = BaseSettings({"key": None})
        settings.set("key_highprio", None, priority=50)
        settings.delete("key")
        settings.delete("key_highprio")
        assert "key" not in settings
        assert "key_highprio" in settings
        del settings["key_highprio"]
        assert "key_highprio" not in settings
        with pytest.raises(KeyError):
            settings.delete("notkey")
        with pytest.raises(KeyError):
            del settings["notkey"]

    def test_get(self):
        test_configuration = {
            "TEST_ENABLED1": "1",
            "TEST_ENABLED2": True,
            "TEST_ENABLED3": 1,
            "TEST_ENABLED4": "True",
            "TEST_ENABLED5": "true",
            "TEST_ENABLED_WRONG": "on",
            "TEST_DISABLED1": "0",
            "TEST_DISABLED2": False,
            "TEST_DISABLED3": 0,
            "TEST_DISABLED4": "False",
            "TEST_DISABLED5": "false",
            "TEST_DISABLED_WRONG": "off",
            "TEST_INT1": 123,
            "TEST_INT2": "123",
            "TEST_FLOAT1": 123.45,
            "TEST_FLOAT2": "123.45",
            "TEST_LIST1": ["one", "two"],
            "TEST_LIST2": "one,two",
            "TEST_LIST3": "",
            "TEST_STR": "value",
            "TEST_DICT1": {"key1": "val1", "ke2": 3},
            "TEST_DICT2": '{"key1": "val1", "ke2": 3}',
        }
        settings = self.settings
        settings.attributes = {
            key: SettingsAttribute(value, 0)
            for key, value in test_configuration.items()
        }

        assert settings.getbool("TEST_ENABLED1")
        assert settings.getbool("TEST_ENABLED2")
        assert settings.getbool("TEST_ENABLED3")
        assert settings.getbool("TEST_ENABLED4")
        assert settings.getbool("TEST_ENABLED5")
        assert not settings.getbool("TEST_ENABLEDx")
        assert settings.getbool("TEST_ENABLEDx", True)
        assert not settings.getbool("TEST_DISABLED1")
        assert not settings.getbool("TEST_DISABLED2")
        assert not settings.getbool("TEST_DISABLED3")
        assert not settings.getbool("TEST_DISABLED4")
        assert not settings.getbool("TEST_DISABLED5")
        assert settings.getint("TEST_INT1") == 123
        assert settings.getint("TEST_INT2") == 123
        assert settings.getint("TEST_INTx") == 0
        assert settings.getint("TEST_INTx", 45) == 45
        assert settings.getfloat("TEST_FLOAT1") == 123.45
        assert settings.getfloat("TEST_FLOAT2") == 123.45
        assert settings.getfloat("TEST_FLOATx") == 0.0
        assert settings.getfloat("TEST_FLOATx", 55.0) == 55.0
        assert settings.getlist("TEST_LIST1") == ["one", "two"]
        assert settings.getlist("TEST_LIST2") == ["one", "two"]
        assert settings.getlist("TEST_LIST3") == []
        assert settings.getlist("TEST_LISTx") == []
        assert settings.getlist("TEST_LISTx", ["default"]) == ["default"]
        assert settings["TEST_STR"] == "value"
        assert settings.get("TEST_STR") == "value"
        assert settings["TEST_STRx"] is None
        assert settings.get("TEST_STRx") is None
        assert settings.get("TEST_STRx", "default") == "default"
        assert settings.getdict("TEST_DICT1") == {"key1": "val1", "ke2": 3}
        assert settings.getdict("TEST_DICT2") == {"key1": "val1", "ke2": 3}
        assert settings.getdict("TEST_DICT3") == {}
        assert settings.getdict("TEST_DICT3", {"key1": 5}) == {"key1": 5}
        with pytest.raises(
            ValueError,
            match="dictionary update sequence element #0 has length 3; 2 is required|sequence of pairs expected",
        ):
            settings.getdict("TEST_LIST1")
        with pytest.raises(
            ValueError, match="Supported values for boolean settings are"
        ):
            settings.getbool("TEST_ENABLED_WRONG")
        with pytest.raises(
            ValueError, match="Supported values for boolean settings are"
        ):
            settings.getbool("TEST_DISABLED_WRONG")

    def test_getpriority(self):
        settings = BaseSettings({"key": "value"}, priority=99)
        assert settings.getpriority("key") == 99
        assert settings.getpriority("nonexistentkey") is None

    def test_getwithbase(self):
        s = BaseSettings(
            {
                "TEST_BASE": BaseSettings({1: 1, 2: 2}, "project"),
                "TEST": BaseSettings({1: 10, 3: 30}, "default"),
                "HASNOBASE": BaseSettings({3: 3000}, "default"),
            }
        )
        s["TEST"].set(2, 200, "cmdline")
        assert set(s.getwithbase("TEST")) == {1, 2, 3}
        assert set(s.getwithbase("HASNOBASE")) == set(s["HASNOBASE"])
        assert s.getwithbase("NONEXISTENT") == {}

    def test_maxpriority(self):
        # Empty settings should return 'default'
        assert self.settings.maxpriority() == 0
        self.settings.set("A", 0, 10)
        self.settings.set("B", 0, 30)
        assert self.settings.maxpriority() == 30

    def test_copy(self):
        values = {
            "TEST_BOOL": True,
            "TEST_LIST": ["one", "two"],
            "TEST_LIST_OF_LISTS": [
                ["first_one", "first_two"],
                ["second_one", "second_two"],
            ],
        }
        self.settings.setdict(values)
        copy = self.settings.copy()
        self.settings.set("TEST_BOOL", False)
        assert copy.get("TEST_BOOL")

        test_list = self.settings.get("TEST_LIST")
        test_list.append("three")
        assert copy.get("TEST_LIST") == ["one", "two"]

        test_list_of_lists = self.settings.get("TEST_LIST_OF_LISTS")
        test_list_of_lists[0].append("first_three")
        assert copy.get("TEST_LIST_OF_LISTS")[0] == ["first_one", "first_two"]

    def test_copy_to_dict(self):
        s = BaseSettings(
            {
                "TEST_STRING": "a string",
                "TEST_LIST": [1, 2],
                "TEST_BOOLEAN": False,
                "TEST_BASE": BaseSettings({1: 1, 2: 2}, "project"),
                "TEST": BaseSettings({1: 10, 3: 30}, "default"),
                "HASNOBASE": BaseSettings({3: 3000}, "default"),
            }
        )
        assert s.copy_to_dict() == {
            "HASNOBASE": {3: 3000},
            "TEST": {1: 10, 3: 30},
            "TEST_BASE": {1: 1, 2: 2},
            "TEST_LIST": [1, 2],
            "TEST_BOOLEAN": False,
            "TEST_STRING": "a string",
        }

    def test_freeze(self):
        self.settings.freeze()
        with pytest.raises(
            TypeError, match="Trying to modify an immutable Settings object"
        ):
            self.settings.set("TEST_BOOL", False)

    def test_frozencopy(self):
        frozencopy = self.settings.frozencopy()
        assert frozencopy.frozen
        assert frozencopy is not self.settings


class TestSettings:
    def setup_method(self):
        self.settings = Settings()

    @mock.patch.dict("scrapy.settings.SETTINGS_PRIORITIES", {"default": 10})
    @mock.patch("scrapy.settings.default_settings", default_settings)
    def test_initial_defaults(self):
        settings = Settings()
        assert len(settings.attributes) == 2
        assert "TEST_DEFAULT" in settings.attributes

        attr = settings.attributes["TEST_DEFAULT"]
        assert isinstance(attr, SettingsAttribute)
        assert attr.value == "defvalue"
        assert attr.priority == 10

    @mock.patch.dict("scrapy.settings.SETTINGS_PRIORITIES", {})
    @mock.patch("scrapy.settings.default_settings", {})
    def test_initial_values(self):
        settings = Settings({"TEST_OPTION": "value"}, 10)
        assert len(settings.attributes) == 1
        assert "TEST_OPTION" in settings.attributes

        attr = settings.attributes["TEST_OPTION"]
        assert isinstance(attr, SettingsAttribute)
        assert attr.value == "value"
        assert attr.priority == 10

    @mock.patch("scrapy.settings.default_settings", default_settings)
    def test_autopromote_dicts(self):
        settings = Settings()
        mydict = settings.get("TEST_DICT")
        assert isinstance(mydict, BaseSettings)
        assert "key" in mydict
        assert mydict["key"] == "val"
        assert mydict.getpriority("key") == 0

    @mock.patch("scrapy.settings.default_settings", default_settings)
    def test_getdict_autodegrade_basesettings(self):
        settings = Settings()
        mydict = settings.getdict("TEST_DICT")
        assert isinstance(mydict, dict)
        assert len(mydict) == 1
        assert "key" in mydict
        assert mydict["key"] == "val"

    def test_passing_objects_as_values(self):
        class TestPipeline:
            def process_item(self, i, s):
                return i

        settings = Settings(
            {
                "ITEM_PIPELINES": {
                    TestPipeline: 800,
                },
                "DOWNLOAD_HANDLERS": {
                    "ftp": FileDownloadHandler,
                },
            }
        )

        assert "ITEM_PIPELINES" in settings.attributes

        mypipeline, priority = settings.getdict("ITEM_PIPELINES").popitem()
        assert priority == 800
        assert mypipeline == TestPipeline
        assert isinstance(mypipeline(), TestPipeline)
        assert mypipeline().process_item("item", None) == "item"

        myhandler = settings.getdict("DOWNLOAD_HANDLERS").pop("ftp")
        assert myhandler == FileDownloadHandler
        myhandler_instance = build_from_crawler(myhandler, get_crawler())
        assert isinstance(myhandler_instance, FileDownloadHandler)
        assert hasattr(myhandler_instance, "download_request")

    def test_pop_item_with_default_value(self):
        settings = Settings()

        with pytest.raises(KeyError):
            settings.pop("DUMMY_CONFIG")

        dummy_config_value = settings.pop("DUMMY_CONFIG", "dummy_value")
        assert dummy_config_value == "dummy_value"

    def test_pop_item_with_immutable_settings(self):
        settings = Settings(
            {"DUMMY_CONFIG": "dummy_value", "OTHER_DUMMY_CONFIG": "other_dummy_value"}
        )

        assert settings.pop("DUMMY_CONFIG") == "dummy_value"

        settings.freeze()

        with pytest.raises(
            TypeError, match="Trying to modify an immutable Settings object"
        ):
            settings.pop("OTHER_DUMMY_CONFIG")


@pytest.mark.parametrize(
    ("before", "name", "item", "after"),
    [
        ({}, "FOO", "BAR", {"FOO": ["BAR"]}),
        ({"FOO": []}, "FOO", "BAR", {"FOO": ["BAR"]}),
        ({"FOO": ["BAR"]}, "FOO", "BAZ", {"FOO": ["BAR", "BAZ"]}),
        ({"FOO": ["BAR"]}, "FOO", "BAR", {"FOO": ["BAR"]}),
        ({"FOO": ""}, "FOO", "BAR", {"FOO": ["BAR"]}),
        ({"FOO": "BAR"}, "FOO", "BAR", {"FOO": "BAR"}),
        ({"FOO": "BAR"}, "FOO", "BAZ", {"FOO": ["BAR", "BAZ"]}),
        ({"FOO": "BAR,BAZ"}, "FOO", "BAZ", {"FOO": "BAR,BAZ"}),
        ({"FOO": "BAR,BAZ"}, "FOO", "QUX", {"FOO": ["BAR", "BAZ", "QUX"]}),
    ],
)
def test_add_to_list(before, name, item, after):
    settings = BaseSettings(before, priority=0)
    settings.add_to_list(name, item)
    expected_priority = settings.getpriority(name) or 0
    expected_settings = BaseSettings(after, priority=expected_priority)
    assert settings == expected_settings, (
        f"{settings[name]=} != {expected_settings[name]=}"
    )
    assert settings.getpriority(name) == expected_settings.getpriority(name)


@pytest.mark.parametrize(
    ("before", "name", "item", "after"),
    [
        ({}, "FOO", "BAR", ValueError),
        ({"FOO": ["BAR"]}, "FOO", "BAR", {"FOO": []}),
        ({"FOO": ["BAR"]}, "FOO", "BAZ", ValueError),
        ({"FOO": ["BAR", "BAZ"]}, "FOO", "BAR", {"FOO": ["BAZ"]}),
        ({"FOO": ""}, "FOO", "BAR", ValueError),
        ({"FOO": "[]"}, "FOO", "BAR", ValueError),
        ({"FOO": "BAR"}, "FOO", "BAR", {"FOO": []}),
        ({"FOO": "BAR"}, "FOO", "BAZ", ValueError),
        ({"FOO": "BAR,BAZ"}, "FOO", "BAR", {"FOO": ["BAZ"]}),
    ],
)
def test_remove_from_list(before, name, item, after):
    settings = BaseSettings(before, priority=0)

    if isinstance(after, type) and issubclass(after, Exception):
        with pytest.raises(after):
            settings.remove_from_list(name, item)
        return

    settings.remove_from_list(name, item)
    expected_priority = settings.getpriority(name) or 0
    expected_settings = BaseSettings(after, priority=expected_priority)
    assert settings == expected_settings, (
        f"{settings[name]=} != {expected_settings[name]=}"
    )
    assert settings.getpriority(name) == expected_settings.getpriority(name)


def test_deprecated_concurrent_requests_per_ip_setting():
    with warnings.catch_warnings(record=True) as warns:
        settings = Settings({"CONCURRENT_REQUESTS_PER_IP": 1})
        settings.get("CONCURRENT_REQUESTS_PER_IP")

    assert (
        str(warns[0].message)
        == "The CONCURRENT_REQUESTS_PER_IP setting is deprecated, use CONCURRENT_REQUESTS_PER_DOMAIN instead."
    )


class Component1:
    pass


Component1Alias = Component1


class Component1Subclass(Component1):
    pass


Component1SubclassAlias = Component1Subclass


class Component2:
    pass


class Component3:
    pass


class Component4:
    pass


@pytest.mark.parametrize(
    ("before", "name", "old_cls", "new_cls", "priority", "after"),
    [
        ({}, "FOO", Component1, Component2, None, KeyError),
        (
            {"FOO": {Component1: 1}},
            "FOO",
            Component1,
            Component2,
            None,
            {"FOO": {Component2: 1}},
        ),
        (
            {"FOO": {Component1: 1}},
            "FOO",
            Component1,
            Component2,
            2,
            {"FOO": {Component2: 2}},
        ),
        (
            {"FOO": {"tests.test_settings.Component1": 1}},
            "FOO",
            Component1,
            Component2,
            None,
            {"FOO": {Component2: 1}},
        ),
        (
            {"FOO": {Component1Alias: 1}},
            "FOO",
            Component1,
            Component2,
            None,
            {"FOO": {Component2: 1}},
        ),
        (
            {"FOO": {Component1Alias: 1}},
            "FOO",
            Component1,
            Component2,
            2,
            {"FOO": {Component2: 2}},
        ),
        (
            {"FOO": {"tests.test_settings.Component1Alias": 1}},
            "FOO",
            Component1,
            Component2,
            None,
            {"FOO": {Component2: 1}},
        ),
        (
            {"FOO": {"tests.test_settings.Component1Alias": 1}},
            "FOO",
            Component1,
            Component2,
            2,
            {"FOO": {Component2: 2}},
        ),
        (
            {
                "FOO": {
                    "tests.test_settings.Component1": 1,
                    "tests.test_settings.Component1Alias": 2,
                }
            },
            "FOO",
            Component1,
            Component2,
            None,
            {"FOO": {Component2: 2}},
        ),
        (
            {
                "FOO": {
                    "tests.test_settings.Component1": 1,
                    "tests.test_settings.Component1Alias": 2,
                }
            },
            "FOO",
            Component1,
            Component2,
            3,
            {"FOO": {Component2: 3}},
        ),
        (
            {"FOO": '{"tests.test_settings.Component1": 1}'},
            "FOO",
            Component1,
            Component2,
            None,
            {"FOO": {Component2: 1}},
        ),
        (
            {"FOO": '{"tests.test_settings.Component1": 1}'},
            "FOO",
            Component1,
            Component2,
            2,
            {"FOO": {Component2: 2}},
        ),
        (
            {"FOO": '{"tests.test_settings.Component1Alias": 1}'},
            "FOO",
            Component1,
            Component2,
            None,
            {"FOO": {Component2: 1}},
        ),
        (
            {"FOO": '{"tests.test_settings.Component1Alias": 1}'},
            "FOO",
            Component1,
            Component2,
            2,
            {"FOO": {Component2: 2}},
        ),
        (
            {
                "FOO": '{"tests.test_settings.Component1": 1, "tests.test_settings.Component1Alias": 2}'
            },
            "FOO",
            Component1,
            Component2,
            None,
            {"FOO": {Component2: 2}},
        ),
        (
            {
                "FOO": '{"tests.test_settings.Component1": 1, "tests.test_settings.Component1Alias": 2}'
            },
            "FOO",
            Component1,
            Component2,
            3,
            {"FOO": {Component2: 3}},
        ),
        # If old_cls has None as value, raise KeyError.
        (
            {"FOO": {Component1: None}},
            "FOO",
            Component1,
            Component2,
            None,
            KeyError,
        ),
        (
            {"FOO": '{"tests.test_settings.Component1": null}'},
            "FOO",
            Component1,
            Component2,
            None,
            KeyError,
        ),
        (
            {"FOO": {Component1: None, "tests.test_settings.Component1": None}},
            "FOO",
            Component1,
            Component2,
            None,
            KeyError,
        ),
        (
            {"FOO": {Component1: 1, "tests.test_settings.Component1": None}},
            "FOO",
            Component1,
            Component2,
            None,
            KeyError,
        ),
        (
            {"FOO": {Component1: None, "tests.test_settings.Component1": 1}},
            "FOO",
            Component1,
            Component2,
            None,
            KeyError,
        ),
        # Unrelated components are kept as is, as expected.
        (
            {
                "FOO": {
                    Component1: 1,
                    "tests.test_settings.Component2": 2,
                    Component3: 3,
                }
            },
            "FOO",
            Component3,
            Component4,
            None,
            {
                "FOO": {
                    Component1: 1,
                    "tests.test_settings.Component2": 2,
                    Component4: 3,
                }
            },
        ),
    ],
)
def test_replace_in_component_priority_dict(
    before, name, old_cls, new_cls, priority, after
):
    settings = BaseSettings(before, priority=0)

    if isinstance(after, type) and issubclass(after, Exception):
        with pytest.raises(after):
            settings.replace_in_component_priority_dict(
                name, old_cls, new_cls, priority
            )
        return

    expected_priority = settings.getpriority(name) or 0
    settings.replace_in_component_priority_dict(name, old_cls, new_cls, priority)
    expected_settings = BaseSettings(after, priority=expected_priority)
    assert settings == expected_settings
    assert settings.getpriority(name) == expected_settings.getpriority(name)


@pytest.mark.parametrize(
    ("before", "name", "cls", "priority", "after"),
    [
        # Set
        ({}, "FOO", Component1, None, {"FOO": {Component1: None}}),
        ({}, "FOO", Component1, 0, {"FOO": {Component1: 0}}),
        ({}, "FOO", Component1, 1, {"FOO": {Component1: 1}}),
        # Add
        (
            {"FOO": {Component1: 0}},
            "FOO",
            Component2,
            None,
            {"FOO": {Component1: 0, Component2: None}},
        ),
        (
            {"FOO": {Component1: 0}},
            "FOO",
            Component2,
            0,
            {"FOO": {Component1: 0, Component2: 0}},
        ),
        (
            {"FOO": {Component1: 0}},
            "FOO",
            Component2,
            1,
            {"FOO": {Component1: 0, Component2: 1}},
        ),
        # Replace
        (
            {
                "FOO": {
                    Component1: None,
                    "tests.test_settings.Component1": 0,
                    "tests.test_settings.Component1Alias": 1,
                    Component1Subclass: None,
                    "tests.test_settings.Component1Subclass": 0,
                    "tests.test_settings.Component1SubclassAlias": 1,
                }
            },
            "FOO",
            Component1,
            None,
            {
                "FOO": {
                    Component1: None,
                    Component1Subclass: None,
                    "tests.test_settings.Component1Subclass": 0,
                    "tests.test_settings.Component1SubclassAlias": 1,
                }
            },
        ),
        (
            {
                "FOO": {
                    Component1: 0,
                    "tests.test_settings.Component1": 1,
                    "tests.test_settings.Component1Alias": None,
                    Component1Subclass: 0,
                    "tests.test_settings.Component1Subclass": 1,
                    "tests.test_settings.Component1SubclassAlias": None,
                }
            },
            "FOO",
            Component1,
            0,
            {
                "FOO": {
                    Component1: 0,
                    Component1Subclass: 0,
                    "tests.test_settings.Component1Subclass": 1,
                    "tests.test_settings.Component1SubclassAlias": None,
                }
            },
        ),
        (
            {
                "FOO": {
                    Component1: 1,
                    "tests.test_settings.Component1": None,
                    "tests.test_settings.Component1Alias": 0,
                    Component1Subclass: 1,
                    "tests.test_settings.Component1Subclass": None,
                    "tests.test_settings.Component1SubclassAlias": 0,
                }
            },
            "FOO",
            Component1,
            1,
            {
                "FOO": {
                    Component1: 1,
                    Component1Subclass: 1,
                    "tests.test_settings.Component1Subclass": None,
                    "tests.test_settings.Component1SubclassAlias": 0,
                }
            },
        ),
        # String-based setting values
        (
            {"FOO": '{"tests.test_settings.Component1": 0}'},
            "FOO",
            Component2,
            None,
            {"FOO": {"tests.test_settings.Component1": 0, Component2: None}},
        ),
        (
            {
                "FOO": """{
                    "tests.test_settings.Component1": 0,
                    "tests.test_settings.Component1Alias": 1,
                    "tests.test_settings.Component1Subclass": 0,
                    "tests.test_settings.Component1SubclassAlias": 1
                }"""
            },
            "FOO",
            Component1,
            None,
            {
                "FOO": {
                    Component1: None,
                    "tests.test_settings.Component1Subclass": 0,
                    "tests.test_settings.Component1SubclassAlias": 1,
                }
            },
        ),
    ],
)
def test_set_in_component_priority_dict(before, name, cls, priority, after):
    settings = BaseSettings(before, priority=0)
    expected_priority = settings.getpriority(name) or 0
    settings.set_in_component_priority_dict(name, cls, priority)
    expected_settings = BaseSettings(after, priority=expected_priority)
    assert settings == expected_settings
    assert settings.getpriority(name) == expected_settings.getpriority(name), (
        f"{settings.getpriority(name)=} != {expected_settings.getpriority(name)=}"
    )


@pytest.mark.parametrize(
    ("before", "name", "cls", "priority", "after"),
    [
        # Set
        ({}, "FOO", Component1, None, {"FOO": {Component1: None}}),
        ({}, "FOO", Component1, 0, {"FOO": {Component1: 0}}),
        ({}, "FOO", Component1, 1, {"FOO": {Component1: 1}}),
        # Add
        (
            {"FOO": {Component1: 0}},
            "FOO",
            Component2,
            None,
            {"FOO": {Component1: 0, Component2: None}},
        ),
        (
            {"FOO": {Component1: 0}},
            "FOO",
            Component2,
            0,
            {"FOO": {Component1: 0, Component2: 0}},
        ),
        (
            {"FOO": {Component1: 0}},
            "FOO",
            Component2,
            1,
            {"FOO": {Component1: 0, Component2: 1}},
        ),
        # Keep
        (
            {
                "FOO": {
                    Component1: None,
                    "tests.test_settings.Component1": 0,
                    "tests.test_settings.Component1Alias": 1,
                    Component1Subclass: None,
                    "tests.test_settings.Component1Subclass": 0,
                    "tests.test_settings.Component1SubclassAlias": 1,
                }
            },
            "FOO",
            Component1,
            None,
            {
                "FOO": {
                    Component1: None,
                    "tests.test_settings.Component1": 0,
                    "tests.test_settings.Component1Alias": 1,
                    Component1Subclass: None,
                    "tests.test_settings.Component1Subclass": 0,
                    "tests.test_settings.Component1SubclassAlias": 1,
                }
            },
        ),
        (
            {
                "FOO": {
                    Component1: 0,
                    "tests.test_settings.Component1": 1,
                    "tests.test_settings.Component1Alias": None,
                    Component1Subclass: 0,
                    "tests.test_settings.Component1Subclass": 1,
                    "tests.test_settings.Component1SubclassAlias": None,
                }
            },
            "FOO",
            Component1,
            0,
            {
                "FOO": {
                    Component1: 0,
                    "tests.test_settings.Component1": 1,
                    "tests.test_settings.Component1Alias": None,
                    Component1Subclass: 0,
                    "tests.test_settings.Component1Subclass": 1,
                    "tests.test_settings.Component1SubclassAlias": None,
                }
            },
        ),
        (
            {
                "FOO": {
                    Component1: 1,
                    "tests.test_settings.Component1": None,
                    "tests.test_settings.Component1Alias": 0,
                    Component1Subclass: 1,
                    "tests.test_settings.Component1Subclass": None,
                    "tests.test_settings.Component1SubclassAlias": 0,
                }
            },
            "FOO",
            Component1,
            1,
            {
                "FOO": {
                    Component1: 1,
                    "tests.test_settings.Component1": None,
                    "tests.test_settings.Component1Alias": 0,
                    Component1Subclass: 1,
                    "tests.test_settings.Component1Subclass": None,
                    "tests.test_settings.Component1SubclassAlias": 0,
                }
            },
        ),
        # String-based setting values
        (
            {"FOO": '{"tests.test_settings.Component1": 0}'},
            "FOO",
            Component2,
            None,
            {"FOO": {"tests.test_settings.Component1": 0, Component2: None}},
        ),
        (
            {
                "FOO": """{
                    "tests.test_settings.Component1": 0,
                    "tests.test_settings.Component1Alias": 1,
                    "tests.test_settings.Component1Subclass": 0,
                    "tests.test_settings.Component1SubclassAlias": 1
                }"""
            },
            "FOO",
            Component1,
            None,
            {
                "FOO": """{
                    "tests.test_settings.Component1": 0,
                    "tests.test_settings.Component1Alias": 1,
                    "tests.test_settings.Component1Subclass": 0,
                    "tests.test_settings.Component1SubclassAlias": 1
                }"""
            },
        ),
    ],
)
def test_setdefault_in_component_priority_dict(before, name, cls, priority, after):
    settings = BaseSettings(before, priority=0)
    expected_priority = settings.getpriority(name) or 0
    settings.setdefault_in_component_priority_dict(name, cls, priority)
    expected_settings = BaseSettings(after, priority=expected_priority)
    assert settings == expected_settings
    assert settings.getpriority(name) == expected_settings.getpriority(name)
