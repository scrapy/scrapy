import os
from argparse import ArgumentParser

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer


def main():
    parser = ArgumentParser()
    parser.add_argument('-d', '--directory')
    args = parser.parse_args()

    authorizer = DummyAuthorizer()
    authorizer.add_anonymous(args.directory, perm='elradfmwMT')
    handler = FTPHandler
    handler.authorizer = authorizer
    address = ('127.0.0.1', 2121)
    server = FTPServer(address, handler)
    server.serve_forever()


if __name__ == '__main__':
    main()
