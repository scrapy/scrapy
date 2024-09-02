"""
The Extension Manager

See documentation in docs/topics/extensions.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.middleware import MiddlewareManager
from scrapy.utils.conf import build_component_list

if TYPE_CHECKING:
    from scrapy.settings import Settings


class ExtensionManager(MiddlewareManager):
    component_name = "extension"

    @classmethod
    def _get_mwlist_from_settings(cls, settings: Settings) -> list[Any]:
        return build_component_list(settings.getwithbase("EXTENSIONS"))
