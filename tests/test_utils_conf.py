from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning, UsageError
from scrapy.settings import BaseSettings, Settings
from scrapy.utils.conf import (
    arglist_to_dict,
    build_component_list,
    closest_config,
    closest_scrapy_cfg,
    feed_complete_default_values_from_settings,
    feed_process_params_from_cli,
    get_config,
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


SETTINGS_TOML = (
    "[tool.scrapy.settings]\n"
    'default = "myproject1.settings"\n'
    'project1 = "myproject1.settings"\n'
    'project2 = "myproject2.settings"\n'
)
SETTINGS_CFG = (
    "[settings]\ndefault = myproject.settings\n[deploy]\nproject = myproject\n"
)


class TestConfig:
    @pytest.fixture(autouse=True)
    def home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Point the deprecated global scrapy.cfg locations (see
        :func:`scrapy.utils.conf.get_sources`) at an initially empty folder."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
        return home

    @pytest.fixture(autouse=True)
    def config_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Point the global configuration file at an initially empty folder.

        platformdirs does not determine the user configuration folder from
        environment variables on every platform, hence the patching.
        """
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        monkeypatch.setattr(
            "scrapy.utils.conf.user_config_dir", lambda *args, **kwargs: str(config_dir)
        )
        return config_dir

    def test_no_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        assert closest_config() == ""

    def test_pyproject_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(SETTINGS_TOML, encoding="utf-8")
        subdir = tmp_path / "a" / "b"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        assert Path(closest_config()) == (tmp_path / "pyproject.toml").resolve()
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            cfg = get_config()
        assert cfg.get("settings", "default") == "myproject1.settings"
        assert cfg.get("settings", "project1") == "myproject1.settings"
        assert cfg.get("settings", "project2") == "myproject2.settings"

    def test_pyproject_toml_preferred(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(SETTINGS_TOML, encoding="utf-8")
        (tmp_path / "scrapy.cfg").write_text(SETTINGS_CFG, encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        assert Path(closest_config()) == (tmp_path / "pyproject.toml").resolve()
        cfg = get_config()
        assert cfg.get("settings", "default") == "myproject1.settings"
        assert not cfg.has_section("deploy")

    def test_closest_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(SETTINGS_TOML, encoding="utf-8")
        subdir = tmp_path / "a"
        subdir.mkdir()
        (subdir / "scrapy.cfg").write_text(SETTINGS_CFG, encoding="utf-8")
        monkeypatch.chdir(subdir)

        assert Path(closest_config()) == (subdir / "scrapy.cfg").resolve()
        with pytest.warns(ScrapyDeprecationWarning, match="scrapy.cfg is deprecated"):
            cfg = get_config()
        assert cfg.get("settings", "default") == "myproject.settings"

    def test_pyproject_toml_without_scrapy_table(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(SETTINGS_TOML, encoding="utf-8")
        subdir = tmp_path / "a"
        subdir.mkdir()
        (subdir / "pyproject.toml").write_text(
            '[project]\nname = "unrelated"\n', encoding="utf-8"
        )
        monkeypatch.chdir(subdir)

        assert Path(closest_config()) == (tmp_path / "pyproject.toml").resolve()

    def test_invalid_pyproject_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.scrapy\nnot valid toml", encoding="utf-8"
        )
        (tmp_path / "scrapy.cfg").write_text(SETTINGS_CFG, encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with pytest.warns(UserWarning, match="Ignoring invalid TOML file"):
            closest = closest_config()
        assert Path(closest) == (tmp_path / "scrapy.cfg").resolve()

    @staticmethod
    def _write_global_config(config_dir: Path, content: str) -> None:
        (config_dir / "config.toml").write_text(content, encoding="utf-8")

    def test_global_config(
        self, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_global_config(config_dir, '[settings]\nshell = "bpython"\n')
        monkeypatch.chdir(tmp_path)

        assert get_config().get("settings", "shell") == "bpython"

    def test_global_config_overridden_by_project(
        self, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_global_config(config_dir, '[settings]\nshell = "bpython"\n')
        (tmp_path / "pyproject.toml").write_text(
            '[tool.scrapy.settings]\nshell = "python"\n', encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)

        assert get_config().get("settings", "shell") == "python"

    def test_global_config_unsupported_options(
        self, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_global_config(
            config_dir,
            '[settings]\nshell = "bpython"\ndefault = "myproject.settings"\n'
            '[deploy]\nproject = "myproject"\nunsupported = 1\n',
        )
        monkeypatch.chdir(tmp_path)

        with pytest.warns(UserWarning, match="settings.default, deploy.project"):
            cfg = get_config()
        assert cfg.get("settings", "shell") == "bpython"
        assert not cfg.has_option("settings", "default")
        assert not cfg.has_section("deploy")

    def test_global_config_non_table(
        self, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_global_config(config_dir, 'shell = "bpython"\n')
        monkeypatch.chdir(tmp_path)

        with pytest.warns(UserWarning, match="Ignoring the following options"):
            cfg = get_config()
        assert not cfg.has_section("settings")

    def test_global_config_preferred_over_global_scrapy_cfg(
        self,
        config_dir: Path,
        home: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (home / "scrapy.cfg").write_text(
            "[settings]\nshell = python\n", encoding="utf-8"
        )
        self._write_global_config(config_dir, '[settings]\nshell = "bpython"\n')
        monkeypatch.chdir(tmp_path)

        with pytest.warns(
            ScrapyDeprecationWarning, match="Global scrapy.cfg files are deprecated"
        ):
            cfg = get_config()
        assert cfg.get("settings", "shell") == "bpython"

    def test_get_sources(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "scrapy.cfg").write_text(SETTINGS_CFG, encoding="utf-8")
        subdir = tmp_path / "a"
        subdir.mkdir()
        monkeypatch.chdir(subdir)

        assert Path(get_sources()[-1]) == (tmp_path / "scrapy.cfg").resolve()

    def test_get_sources_without_scrapy_cfg(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        assert get_sources()[-1] == ""

    def test_global_scrapy_cfg_deprecated(
        self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (home / "scrapy.cfg").write_text(
            "[settings]\nshell = python\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)

        with pytest.warns(
            ScrapyDeprecationWarning, match="Global scrapy.cfg files are deprecated"
        ):
            cfg = get_config()
        assert cfg.get("settings", "shell") == "python"

    def test_closest_scrapy_cfg_deprecated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "scrapy.cfg").write_text(SETTINGS_CFG, encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with pytest.warns(ScrapyDeprecationWarning, match="closest_scrapy_cfg"):
            assert Path(closest_scrapy_cfg()) == (tmp_path / "scrapy.cfg").resolve()


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
