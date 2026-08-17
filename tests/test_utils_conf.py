from __future__ import annotations

from typing import Any

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning, UsageError
from scrapy.settings import BaseSettings, Settings
from scrapy.utils.conf import (
    arglist_to_dict,
    build_component_list,
    closest_scrapy_cfg,
    feed_complete_default_values_from_settings,
    feed_process_params_from_cli,
    get_sources,
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
            ValueError, match=r"Some paths in .* convert to the same object"
        ):
            build_component_list(duplicate_bs, convert=lambda x: x.lower())

    def test_duplicate_components_in_dict(self):
        d = {"one": 1, "ONE": 2}
        with pytest.raises(
            ValueError, match=r"Some paths in .* convert to the same object"
        ):
            build_component_list(d, convert=lambda x: x.lower())

    def test_invalid_value(self):
        d = {"one": "1"}
        with pytest.raises(
            ValueError, match=r"Invalid value 1 for component one, please provide"
        ):
            build_component_list(d, convert=lambda x: x)

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


def test_get_sources():
    assert get_sources() == [*get_sources(use_closest=False), closest_scrapy_cfg()]


def test_arglist_to_dict():
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
            "output.json": {"format": "json", "mode": "overwrite"}
        } == feed_process_params_from_cli(
            settings, [], overwrite_output=["output.json"]
        )

    def test_feed_complete_default_values_mode_from_settings(self):
        settings = Settings({"FEED_MODE": "create"})
        new_feed = feed_complete_default_values_from_settings({}, settings)
        assert new_feed["mode"] == "create"
        assert "overwrite" not in new_feed

    @pytest.mark.parametrize(
        ("mode", "overwrite"),
        [
            ("append", False),
            ("overwrite", True),
        ],
    )
    def test_feed_complete_default_values_mode_sets_overwrite(self, mode, overwrite):
        """The deprecated overwrite feed option is kept in sync for the sake of
        feed storages that predate the mode feed option."""
        settings = Settings({"FEED_MODE": mode})
        new_feed = feed_complete_default_values_from_settings({}, settings)
        assert new_feed["mode"] == mode
        assert new_feed["overwrite"] is overwrite

    @pytest.mark.parametrize(
        ("overwrite", "mode"),
        [
            (True, "overwrite"),
            (False, "append"),
        ],
    )
    def test_feed_complete_default_values_overwrite_deprecated(self, overwrite, mode):
        settings = Settings()
        with pytest.warns(
            ScrapyDeprecationWarning, match="overwrite feed option is deprecated"
        ):
            new_feed = feed_complete_default_values_from_settings(
                {"overwrite": overwrite}, settings
            )
        assert new_feed["mode"] == mode
        assert new_feed["overwrite"] is overwrite

    def test_feed_complete_default_values_overwrite_and_mode(self):
        settings = Settings()
        with (
            pytest.raises(ValueError, match="mutually exclusive"),
            pytest.warns(ScrapyDeprecationWarning),
        ):
            feed_complete_default_values_from_settings(
                {"overwrite": True, "mode": "create"}, settings
            )

    def test_output_and_overwrite_output(self):
        with pytest.raises(UsageError):
            feed_process_params_from_cli(
                Settings(), ["output1.json"], overwrite_output=["output2.json"]
            )

    def test_feed_complete_default_values_from_settings_empty(self):
        feed: dict[str, Any] = {}
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
            "mode": None,
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
            "mode": None,
            "encoding": "other encoding",
            "fields": None,
            "indent": 42,
            "store_empty": True,
            "uri_params": None,
            "batch_item_count": 2,
            "item_export_kwargs": {},
        }
