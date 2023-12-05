import os
import subprocess
import sys

if __name__ == "__main__":
    directory = os.path.dirname(os.path.abspath(sys.argv[0]))
    script = os.path.join(directory, "socketserver.py")
    while 1:
        cmdlist = ["python", script]
        cmdlist.extend(sys.argv[1:])
        text = "starting subcommand: " + " ".join(cmdlist)
        print(text)
        process = subprocess.Popen(cmdlist)
        process.wait()
