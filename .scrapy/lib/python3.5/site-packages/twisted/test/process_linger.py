
"""Write to a file descriptor and then close it, waiting a few seconds before
quitting. This serves to make sure SIGCHLD is actually being noticed.
"""

import os, sys, time

print("here is some text")
time.sleep(1)
print("goodbye")
os.close(1)
os.close(2)

time.sleep(2)

sys.exit(0)
