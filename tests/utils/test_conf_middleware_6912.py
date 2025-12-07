from scrapy.downloadermiddlewares.httpauth import HttpAuthMiddleware
from scrapy.utils.conf import build_component_list


def _key_for(cls):
    return f"{cls.__module__}.{cls.__name__}"


def test_middleware_string_key_none_disables():
    compdict = {
        "scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware": None,
    }
    result = build_component_list(compdict)
    assert "scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware" not in result


def test_middleware_class_key_none_disables():
    compdict = {
        HttpAuthMiddleware: None,
    }
    result = build_component_list(compdict)
    assert _key_for(HttpAuthMiddleware) not in result


def test_middleware_class_key_priority_enables():
    compdict = {
        HttpAuthMiddleware: 543,
    }
    result = build_component_list(compdict)
    assert HttpAuthMiddleware in result
