from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.curl import curl_to_request_kwargs


class Command(ScrapyCommand):

    def syntax(self):
        return '[-s] "<curl_command>"'

    def short_desc(self):
        return "Print the equivalent scrapy.Request syntax from a cURL command"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option(
            "--strict", "-s", dest="strict", action="store_true",
            help="raise an error when cURL options are unsupported or unknown"
        )

    def run(self, args, opts):
        if len(args) < 1 or not args[0]:
            raise UsageError()
        elif len(args) > 1:
            raise UsageError(
                "it is only possible to pass one cURL command and it must be "
                "between quotation marks"
            )

        ignore_unknown_options = not opts.strict

        try:
            kwargs = curl_to_request_kwargs(args[0], ignore_unknown_options=ignore_unknown_options)
            request_kwargs_str = ["%s=%s" % (name, repr(value)) for name, value in kwargs.items()]
            print("Request(%s)" % ', '.join(request_kwargs_str))
        except Exception as e:
            raise UsageError(e)
