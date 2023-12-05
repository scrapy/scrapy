from __future__ import annotations

from tox.config.loader.ini.factor import extend_factors
from tox.config.loader.section import Section


class IniSection(Section):
    @classmethod
    def test_env(cls, name: str) -> IniSection:
        return cls(TEST_ENV_PREFIX, name)

    @property
    def is_test_env(self) -> bool:
        return self.prefix == TEST_ENV_PREFIX

    @property
    def names(self) -> list[str]:
        return list(extend_factors(self.name))


TEST_ENV_PREFIX = "testenv"
PKG_ENV_PREFIX = "pkgenv"
CORE = IniSection(None, "tox")

__all__ = [
    "IniSection",
    "CORE",
    "TEST_ENV_PREFIX",
    "PKG_ENV_PREFIX",
]
