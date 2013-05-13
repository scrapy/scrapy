import optparse

class SpiderOption(optparse.Option):
    _dummy = True

class ScrapyComandOptionParser(optparse.OptionParser):
    def parse_args(self, args=None, values=None):
        (options, args) = optparse.OptionParser.parse_args(self, args, values)
        for option in self._get_all_options():
            if isinstance(option, SpiderOption):
                spider_options = getattr(options, 'spideropts', None)
                if not spider_options:
                    spider_options = optparse.Values()
                    setattr(options, 'spideropts', spider_options)
                setattr(spider_options, option.dest, getattr(options, option.dest))
        return (options, args)

make_option = SpiderOption
