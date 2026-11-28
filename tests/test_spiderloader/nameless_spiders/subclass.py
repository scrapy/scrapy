from tests.test_spiderloader.nameless_spiders.base import NamelessBaseSpider


class NamedSubclassSpider(NamelessBaseSpider):
    name = "named_subclass"
