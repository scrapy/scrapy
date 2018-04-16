from scrapy.http.headers import Headers
import json

h = Headers({ "X-Foo": "bar" })
print(h)
print(h.values())
#print(json.dumps(h, indent=3))