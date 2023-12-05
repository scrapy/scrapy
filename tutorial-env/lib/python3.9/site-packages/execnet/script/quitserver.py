"""

  send a "quit" signal to a remote server

"""
from __future__ import annotations

import socket
import sys


host, port = sys.argv[1].split(":")
hostport = (host, int(port))

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(hostport)
sock.sendall(b'"raise KeyboardInterrupt"\n')
