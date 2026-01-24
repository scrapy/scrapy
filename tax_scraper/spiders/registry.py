"""
Spider registry for auto-discovery and management.
"""

from typing import Dict, List, Optional, Type
from ..core.base_spider import BaseTaxSpider


class SpiderRegistry:
    """
    Registry for managing available spiders.

    Spiders are registered by name and can be retrieved for crawling.
    """

    _spiders: Dict[str, Type[BaseTaxSpider]] = {}

    @classmethod
    def register(cls, spider_class: Type[BaseTaxSpider]) -> Type[BaseTaxSpider]:
        """
        Register a spider class. Can be used as a decorator.

        Args:
            spider_class: Spider class to register

        Returns:
            The same spider class (for decorator use)
        """
        name = getattr(spider_class, "name", spider_class.__name__.lower())
        cls._spiders[name] = spider_class
        return spider_class

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseTaxSpider]]:
        """
        Get a spider class by name.

        Args:
            name: Spider name

        Returns:
            Spider class or None
        """
        return cls._spiders.get(name)

    @classmethod
    def list_all(cls) -> List[Dict[str, str]]:
        """
        List all registered spiders with their metadata.

        Returns:
            List of dicts with spider info
        """
        result = []
        for name, spider_class in cls._spiders.items():
            result.append({
                "name": name,
                "class": spider_class.__name__,
                "domains": getattr(spider_class, "allowed_domains", []),
                "description": spider_class.__doc__ or "No description",
            })
        return result

    @classmethod
    def names(cls) -> List[str]:
        """Get list of all spider names."""
        return list(cls._spiders.keys())


# Convenience functions
def get_spider(name: str) -> Optional[Type[BaseTaxSpider]]:
    """Get a spider class by name."""
    return SpiderRegistry.get(name)


def list_spiders() -> List[Dict[str, str]]:
    """List all available spiders."""
    return SpiderRegistry.list_all()
