#! /usr/bin/env python
"""
a remote python shell

for injection into startserver.py
"""
import os
import select
import socket
import sys
from threading import Thread
from traceback import print_exc


def clientside():
    print("client side starting")
    host, port = sys.argv[1].split(":")
    port = int(port)
    myself = open(os.path.abspath(sys.argv[0])).read()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.sendall(repr(myself) + "\n")
    print("send boot string")
    inputlist = [sock, sys.stdin]
    try:
        while 1:
            r, w, e = select.select(inputlist, [], [])
            if sys.stdin in r:
                line = raw_input()
                sock.sendall(line + "\n")
            if sock in r:
                line = sock.recv(4096)
                sys.stdout.write(line)
                sys.stdout.flush()
    except BaseException:
        import traceback

        print(traceback.print_exc())

    sys.exit(1)


class promptagent(Thread):
    def __init__(self, clientsock):
        print("server side starting")
        super.__init__()
        self.clientsock = clientsock

    def run(self):
        print("Entering thread prompt loop")
        clientfile = self.clientsock.makefile("w")

        filein = self.clientsock.makefile("r")
        loc = self.clientsock.getsockname()

        while 1:
            try:
                clientfile.write("%s %s >>> " % loc)
                clientfile.flush()
                line = filein.readline()
                if not line:
                    raise EOFError("nothing")
                if line.strip():
                    oldout, olderr = sys.stdout, sys.stderr
                    sys.stdout, sys.stderr = clientfile, clientfile
                    try:
                        try:
                            exec(compile(line + "\n", "<remote pyin>", "single"))
                        except BaseException:
                            print_exc()
                    finally:
                        sys.stdout = oldout
                        sys.stderr = olderr
                clientfile.flush()
            except EOFError:
                sys.stderr.write("connection close, prompt thread returns")
                break

        self.clientsock.close()


sock = globals().get("clientsock")
if sock is not None:
    prompter = promptagent(sock)
    prompter.start()
    print("promptagent - thread started")
else:
    clientside()
