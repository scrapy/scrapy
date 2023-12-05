
#Attempt to add JsonResponse class

from scrapy.http.response.text import TextResponse
import json

class JsonResponse(TextResponse):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        try:
            self._json = json.loads(self.body_as_unicode())
        except ValueError:
            self._json = None


    def json(self):
        return self._json