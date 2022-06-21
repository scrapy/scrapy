"""A test extension used to check the settings loading order"""


class TestExtension:

    def __init__(self, settings):
        settings.set('TEST1', f"{settings['TEST1']} + started")

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)


class DummyExtension:
    pass
