import logging
from typing import Any, Dict, Tuple


class SpiderLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: Dict) -> Tuple[str, Dict[str, Any]]:
        """Method that augments logging with additional 'extra' data"""
        extra = kwargs.get("extra")
        if not isinstance(extra, dict):
            kwargs["extra"] = self.extra
        elif isinstance(self.extra, dict):
            kwargs["extra"].update(self.extra)

        return msg, kwargs
