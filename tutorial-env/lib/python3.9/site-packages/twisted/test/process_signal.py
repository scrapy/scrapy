import signal
import sys

signal.signal(signal.SIGINT, signal.SIG_DFL)
if getattr(signal, "SIGHUP", None) is not None:
    signal.signal(signal.SIGHUP, signal.SIG_DFL)
print("ok, signal us")
sys.stdin.read()
sys.exit(1)
