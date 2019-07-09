import argparse
from shlex import split
from six.moves.http_cookies import SimpleCookie
from six import string_types, iteritems


class CurlParser(argparse.ArgumentParser):
    def error(self, message):
        error_msg = 'There was an error parsing the CURL command: {}'.format(message)
        raise ValueError(error_msg)


curl_parser = CurlParser()
curl_parser.add_argument('url')
curl_parser.add_argument('-H', '--header', dest='headers', action='append')
curl_parser.add_argument('-X', '--request', dest='method', default='get')
curl_parser.add_argument('-d', '--data', dest='data')
curl_parser.add_argument('--compressed', action='store_true')


def curl_to_request_kwargs(curl_args):
    """Convert CURL command syntax to Request kwargs

    :param curl_args: string containing the CURL command
    :return: dictionary of Request kwargs
    """

    if isinstance(curl_args, string_types):
        curl_args = split(curl_args)
    parsed_args, argv = curl_parser.parse_known_args(curl_args[1:])
    if argv:
        msg = 'Unrecognized arguments: %s'
        raise ValueError(msg % (argv,))

    result = {
        'method': parsed_args.method.upper(),
        'url': parsed_args.url,
    }

    headers = []
    cookies = []
    for h in parsed_args.headers or ():
        name, val = h.split(':', 1)
        name = name.strip().title()
        val = val.strip()
        if name == 'Cookie':
            for name, morsel in iteritems(SimpleCookie(val)):
                cookies.append((name, morsel.value))
        else:
            headers.append((name, val))
    if headers:
        result['headers'] = headers
    if cookies:
        result['cookies'] = dict(cookies)
    if parsed_args.data:
        result['body'] = parsed_args.data
    return result
