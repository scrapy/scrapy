import pytest

from scrapy.exceptions import UsageError
from scrapy.settings import BaseSettings, Settings
from scrapy.utils.conf import (
    arglist_to_dict,
    build_component_list,
    feed_complete_default_values_from_settings,
    feed_process_params_from_cli,
)


class TestBuildComponentList:
    def test_build_dict(self):
        d = {"one": 1, "two": None, "three": 8, "four": 4}
        assert build_component_list(d, convert=lambda x: x) == ["one", "four", "three"]

    def test_duplicate_components_in_basesettings(self):
        # Higher priority takes precedence
        duplicate_bs = BaseSettings({"one": 1, "two": 2}, priority=0)
        duplicate_bs.set("ONE", 4, priority=10)
        assert build_component_list(duplicate_bs, convert=lambda x: x.lower()) == [
            "two",
            "one",
        ]
        duplicate_bs.set("one", duplicate_bs["one"], priority=20)
        assert build_component_list(duplicate_bs, convert=lambda x: x.lower()) == [
            "one",
            "two",
        ]
        # Same priority raises ValueError
        duplicate_bs.set("ONE", duplicate_bs["ONE"], priority=20)
        with pytest.raises(
            ValueError, match="Some paths in .* convert to the same object"
        ):
            build_component_list(duplicate_bs, convert=lambda x: x.lower())

    def test_valid_numbers(self):
        # work well with None and numeric values
        d = {"a": 10, "b": None, "c": 15, "d": 5.0}
        assert build_component_list(d, convert=lambda x: x) == ["d", "a", "c"]
        d = {
            "a": 33333333333333333333,
            "b": 11111111111111111111,
            "c": 22222222222222222222,
        }
        assert build_component_list(d, convert=lambda x: x) == ["b", "c", "a"]


class TestUtilsConf:
    def test_arglist_to_dict(self):
        assert arglist_to_dict(["arg1=val1", "arg2=val2"]) == {
            "arg1": "val1",
            "arg2": "val2",
        }


class TestFeedExportConfig:
    def test_feed_export_config_invalid_format(self):
        settings = Settings()
        with pytest.raises(UsageError):
            feed_process_params_from_cli(settings, ["items.dat"])

    def test_feed_export_config_mismatch(self):
        settings = Settings()
        with pytest.raises(UsageError):
            feed_process_params_from_cli(settings, ["items1.dat", "items2.dat"])

    def test_feed_export_config_explicit_formats(self):
        settings = Settings()
        assert {
            "items_1.dat": {"format": "json"},
            "items_2.dat": {"format": "xml"},
            "items_3.dat": {"format": "csv"},
        } == feed_process_params_from_cli(
            settings, ["items_1.dat:json", "items_2.dat:xml", "items_3.dat:csv"]
        )

    def test_feed_export_config_implicit_formats(self):
        settings = Settings()
        assert {
            "items_1.json": {"format": "json"},
            "items_2.xml": {"format": "xml"},
            "items_3.csv": {"format": "csv"},
        } == feed_process_params_from_cli(
            settings, ["items_1.json", "items_2.xml", "items_3.csv"]
        )

    def test_feed_export_config_stdout(self):
        settings = Settings()
        assert {"stdout:": {"format": "pickle"}} == feed_process_params_from_cli(
            settings, ["-:pickle"]
        )

    def test_feed_export_config_overwrite(self):
        settings = Settings()
        assert {
            "output.json": {"format": "json", "overwrite": True}
        } == feed_process_params_from_cli(
            settings, [], overwrite_output=["output.json"]
        )

    def test_output_and_overwrite_output(self):
        with pytest.raises(UsageError):
            feed_process_params_from_cli(
                Settings(), ["output1.json"], overwrite_output=["output2.json"]
            )

    def test_feed_complete_default_values_from_settings_empty(self):
        feed = {}
        settings = Settings(
            {
                "FEED_EXPORT_ENCODING": "custom encoding",
                "FEED_EXPORT_FIELDS": ["f1", "f2", "f3"],
                "FEED_EXPORT_INDENT": 42,
                "FEED_STORE_EMPTY": True,
                "FEED_URI_PARAMS": (1, 2, 3, 4),
                "FEED_EXPORT_BATCH_ITEM_COUNT": 2,
            }
        )
        new_feed = feed_complete_default_values_from_settings(feed, settings)
        assert new_feed == {
            "encoding": "custom encoding",
            "fields": ["f1", "f2", "f3"],
            "indent": 42,
            "store_empty": True,
            "uri_params": (1, 2, 3, 4),
            "batch_item_count": 2,
            "item_export_kwargs": {},
        }

    def test_feed_complete_default_values_from_settings_non_empty(self):
        feed = {
            "encoding": "other encoding",
            "fields": None,
        }
        settings = Settings(
            {
                "FEED_EXPORT_ENCODING": "custom encoding",
                "FEED_EXPORT_FIELDS": ["f1", "f2", "f3"],
                "FEED_EXPORT_INDENT": 42,
                "FEED_STORE_EMPTY": True,
                "FEED_EXPORT_BATCH_ITEM_COUNT": 2,
            }
        )
        new_feed = feed_complete_default_values_from_settings(feed, settings)
        assert new_feed == {
            "encoding": "other encoding",
            "fields": None,
            "indent": 42,
            "store_empty": True,
            "uri_params": None,
            "batch_item_count": 2,
            "item_export_kwargs": {},
        }
