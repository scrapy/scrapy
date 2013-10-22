#!/usr/bin/env python
"""
Example script to control a Scrapy server using its JSON-RPC web service.

It only provides a reduced functionality as its main purpose is to illustrate
how to write a web service client. Feel free to improve or write you own.

Also, keep in mind that the JSON-RPC API is not stable. The recommended way for
controlling a Scrapy server is through the execution queue (see the "queue"
command).

"""

from __future__ import print_function
import sys, optparse, urllib, json
from urlparse import urljoin

from scrapy.utils.jsonrpc import jsonrpc_client_call, JsonRpcError

def get_commands():
    return {
        'help': cmd_help,
        'stop': cmd_stop,
        'list-available': cmd_list_available,
        'list-running': cmd_list_running,
        'list-resources': cmd_list_resources,
        'get-global-stats': cmd_get_global_stats,
        'get-spider-stats': cmd_get_spider_stats,
    }

def cmd_help(args, opts):
    """help - list available commands"""
    print("Available commands:")
    for _, func in sorted(get_commands().items()):
        print("  ", func.__doc__)

def cmd_stop(args, opts):
    """stop <spider> - stop a running spider"""
    jsonrpc_call(opts, 'crawler/engine', 'close_spider', args[0])

def cmd_list_running(args, opts):
    """list-running - list running spiders"""
    for x in json_get(opts, 'crawler/engine/open_spiders'):
        print(x)

def cmd_list_available(args, opts):
    """list-available - list name of available spiders"""
    for x in jsonrpc_call(opts, 'crawler/spiders', 'list'):
        print(x)

def cmd_list_resources(args, opts):
    """list-resources - list available web service resources"""
    for x in json_get(opts, '')['resources']:
        print(x)

def cmd_get_spider_stats(args, opts):
    """get-spider-stats <spider> - get stats of a running spider"""
    stats = jsonrpc_call(opts, 'stats', 'get_stats', args[0])
    for name, value in stats.items():
        print("%-40s %s" % (name, value))

def cmd_get_global_stats(args, opts):
    """get-global-stats - get global stats"""
    stats = jsonrpc_call(opts, 'stats', 'get_stats')
    for name, value in stats.items():
        print("%-40s %s" % (name, value))

def get_wsurl(opts, path):
    return urljoin("http://%s:%s/"% (opts.host, opts.port), path)

def jsonrpc_call(opts, path, method, *args, **kwargs):
    url = get_wsurl(opts, path)
    return jsonrpc_client_call(url, method, *args, **kwargs)

def json_get(opts, path):
    url = get_wsurl(opts, path)
    return json.loads(urllib.urlopen(url).read())

def parse_opts():
    usage = "%prog [options] <command> [arg] ..."
    description = "Scrapy web service control script. Use '%prog help' " \
        "to see the list of available commands."
    op = optparse.OptionParser(usage=usage, description=description)
    op.add_option("-H", dest="host", default="localhost", \
        help="Scrapy host to connect to")
    op.add_option("-P", dest="port", type="int", default=6080, \
        help="Scrapy port to connect to")
    opts, args = op.parse_args()
    if not args:
        op.print_help()
        sys.exit(2)
    cmdname, cmdargs, opts = args[0], args[1:], opts
    commands = get_commands()
    if cmdname not in commands:
        sys.stderr.write("Unknown command: %s\n\n" % cmdname)
        cmd_help(None, None)
        sys.exit(1)
    return commands[cmdname], cmdargs, opts

def main():
    cmd, args, opts = parse_opts()
    try:
        cmd(args, opts)
    except IndexError:
        print(cmd.__doc__)
    except JsonRpcError as e:
        print(str(e))
        if e.data:
            print("Server Traceback below:")
            print(e.data)


if __name__ == '__main__':
    main()
