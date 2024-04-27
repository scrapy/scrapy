import logging
from typing import Any, MutableMapping, Tuple


class SpiderLoggerAdapter(logging.LoggerAdapter):
    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> Tuple[str, MutableMapping[str, Any]]:
        """Method that augments logging with additional 'extra' data"""
        if isinstance(kwargs.get("extra"), MutableMapping):
            kwargs["extra"].update(self.extra)
        else:
            kwargs["extra"] = self.extra

        return msg, kwargs
