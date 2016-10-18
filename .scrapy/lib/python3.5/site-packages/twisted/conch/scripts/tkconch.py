# -*- test-case-name: twisted.conch.test.test_scripts -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation module for the `tkconch` command.
"""

from __future__ import print_function

import Tkinter, tkFileDialog, tkMessageBox
from twisted.conch import error
from twisted.conch.ui import tkvt100
from twisted.conch.ssh import transport, userauth, connection, common, keys
from twisted.conch.ssh import session, forwarding, channel
from twisted.conch.client.default import isInKnownHosts
from twisted.internet import reactor, defer, protocol, tksupport
from twisted.python import usage, log

import os, sys, getpass, struct, base64, signal

class TkConchMenu(Tkinter.Frame):
    def __init__(self, *args, **params):
        ## Standard heading: initialization
        apply(Tkinter.Frame.__init__, (self,) + args, params)

        self.master.title('TkConch')
        self.localRemoteVar = Tkinter.StringVar()
        self.localRemoteVar.set('local')

        Tkinter.Label(self, anchor='w', justify='left', text='Hostname').grid(column=1, row=1, sticky='w')
        self.host = Tkinter.Entry(self)
        self.host.grid(column=2, columnspan=2, row=1, sticky='nesw')

        Tkinter.Label(self, anchor='w', justify='left', text='Port').grid(column=1, row=2, sticky='w')
        self.port = Tkinter.Entry(self)
        self.port.grid(column=2, columnspan=2, row=2, sticky='nesw')

        Tkinter.Label(self, anchor='w', justify='left', text='Username').grid(column=1, row=3, sticky='w')
        self.user = Tkinter.Entry(self)
        self.user.grid(column=2, columnspan=2, row=3, sticky='nesw')

        Tkinter.Label(self, anchor='w', justify='left', text='Command').grid(column=1, row=4, sticky='w')
        self.command = Tkinter.Entry(self)
        self.command.grid(column=2, columnspan=2, row=4, sticky='nesw')

        Tkinter.Label(self, anchor='w', justify='left', text='Identity').grid(column=1, row=5, sticky='w')
        self.identity = Tkinter.Entry(self)
        self.identity.grid(column=2, row=5, sticky='nesw')
        Tkinter.Button(self, command=self.getIdentityFile, text='Browse').grid(column=3, row=5, sticky='nesw')

        Tkinter.Label(self, text='Port Forwarding').grid(column=1, row=6, sticky='w')
        self.forwards = Tkinter.Listbox(self, height=0, width=0)
        self.forwards.grid(column=2, columnspan=2, row=6, sticky='nesw')
        Tkinter.Button(self, text='Add', command=self.addForward).grid(column=1, row=7)
        Tkinter.Button(self, text='Remove', command=self.removeForward).grid(column=1, row=8)
        self.forwardPort = Tkinter.Entry(self)
        self.forwardPort.grid(column=2, row=7, sticky='nesw')
        Tkinter.Label(self, text='Port').grid(column=3, row=7, sticky='nesw')
        self.forwardHost = Tkinter.Entry(self)
        self.forwardHost.grid(column=2, row=8, sticky='nesw')
        Tkinter.Label(self, text='Host').grid(column=3, row=8, sticky='nesw')
        self.localForward = Tkinter.Radiobutton(self, text='Local', variable=self.localRemoteVar, value='local')
        self.localForward.grid(column=2, row=9)
        self.remoteForward = Tkinter.Radiobutton(self, text='Remote', variable=self.localRemoteVar, value='remote')
        self.remoteForward.grid(column=3, row=9)

        Tkinter.Label(self, text='Advanced Options').grid(column=1, columnspan=3, row=10, sticky='nesw')

        Tkinter.Label(self, anchor='w', justify='left', text='Cipher').grid(column=1, row=11, sticky='w')
        self.cipher = Tkinter.Entry(self, name='cipher')
        self.cipher.grid(column=2, columnspan=2, row=11, sticky='nesw')

        Tkinter.Label(self, anchor='w', justify='left', text='MAC').grid(column=1, row=12, sticky='w')
        self.mac = Tkinter.Entry(self, name='mac')
        self.mac.grid(column=2, columnspan=2, row=12, sticky='nesw')

        Tkinter.Label(self, anchor='w', justify='left', text='Escape Char').grid(column=1, row=13, sticky='w')
        self.escape = Tkinter.Entry(self, name='escape')
        self.escape.grid(column=2, columnspan=2, row=13, sticky='nesw')
        Tkinter.Button(self, text='Connect!', command=self.doConnect).grid(column=1, columnspan=3, row=14, sticky='nesw')

        # Resize behavior(s)
        self.grid_rowconfigure(6, weight=1, minsize=64)
        self.grid_columnconfigure(2, weight=1, minsize=2)

        self.master.protocol("WM_DELETE_WINDOW", sys.exit)


    def getIdentityFile(self):
        r = tkFileDialog.askopenfilename()
        if r:
            self.identity.delete(0, Tkinter.END)
            self.identity.insert(Tkinter.END, r)

    def addForward(self):
        port = self.forwardPort.get()
        self.forwardPort.delete(0, Tkinter.END)
        host = self.forwardHost.get()
        self.forwardHost.delete(0, Tkinter.END)
        if self.localRemoteVar.get() == 'local':
            self.forwards.insert(Tkinter.END, 'L:%s:%s' % (port, host))
        else:
            self.forwards.insert(Tkinter.END, 'R:%s:%s' % (port, host))

    def removeForward(self):
        cur = self.forwards.curselection()
        if cur:
            self.forwards.remove(cur[0])

    def doConnect(self):
        finished = 1
        options['host'] = self.host.get()
        options['port'] = self.port.get()
        options['user'] = self.user.get()
        options['command'] = self.command.get()
        cipher = self.cipher.get()
        mac = self.mac.get()
        escape = self.escape.get()
        if cipher:
            if cipher in SSHClientTransport.supportedCiphers:
                SSHClientTransport.supportedCiphers = [cipher]
            else:
                tkMessageBox.showerror('TkConch', 'Bad cipher.')
                finished = 0

        if mac:
            if mac in SSHClientTransport.supportedMACs:
                SSHClientTransport.supportedMACs = [mac]
            elif finished:
                tkMessageBox.showerror('TkConch', 'Bad MAC.')
                finished = 0

        if escape:
            if escape == 'none':
                options['escape'] = None
            elif escape[0] == '^' and len(escape) == 2:
                options['escape'] = chr(ord(escape[1])-64)
            elif len(escape) == 1:
                options['escape'] = escape
            elif finished:
                tkMessageBox.showerror('TkConch', "Bad escape character '%s'." % escape)
                finished = 0

        if self.identity.get():
            options.identitys.append(self.identity.get())

        for line in self.forwards.get(0,Tkinter.END):
            if line[0]=='L':
                options.opt_localforward(line[2:])
            else:
                options.opt_remoteforward(line[2:])

        if '@' in options['host']:
            options['user'], options['host'] = options['host'].split('@',1)

        if (not options['host'] or not options['user']) and finished:
            tkMessageBox.showerror('TkConch', 'Missing host or username.')
            finished = 0
        if finished:
            self.master.quit()
            self.master.destroy()
            if options['log']:
                realout = sys.stdout
                log.startLogging(sys.stderr)
                sys.stdout = realout
            else:
                log.discardLogs()
            log.deferr = handleError # HACK
            if not options.identitys:
                options.identitys = ['~/.ssh/id_rsa', '~/.ssh/id_dsa']
            host = options['host']
            port = int(options['port'] or 22)
            log.msg((host,port))
            reactor.connectTCP(host, port, SSHClientFactory())
            frame.master.deiconify()
            frame.master.title('%s@%s - TkConch' % (options['user'], options['host']))
        else:
            self.focus()

class GeneralOptions(usage.Options):
    synopsis = """Usage:    tkconch [options] host [command]
 """

    optParameters = [['user', 'l', None, 'Log in using this user name.'],
                    ['identity', 'i', '~/.ssh/identity', 'Identity for public key authentication'],
                    ['escape', 'e', '~', "Set escape character; ``none'' = disable"],
                    ['cipher', 'c', None, 'Select encryption algorithm.'],
                    ['macs', 'm', None, 'Specify MAC algorithms for protocol version 2.'],
                    ['port', 'p', None, 'Connect to this port.  Server must be on the same port.'],
                    ['localforward', 'L', None, 'listen-port:host:port   Forward local port to remote address'],
                    ['remoteforward', 'R', None, 'listen-port:host:port   Forward remote port to local address'],
                    ]

    optFlags = [['tty', 't', 'Tty; allocate a tty even if command is given.'],
                ['notty', 'T', 'Do not allocate a tty.'],
                ['version', 'V', 'Display version number only.'],
                ['compress', 'C', 'Enable compression.'],
                ['noshell', 'N', 'Do not execute a shell or command.'],
                ['subsystem', 's', 'Invoke command (mandatory) as SSH2 subsystem.'],
                ['log', 'v', 'Log to stderr'],
                ['ansilog', 'a', 'Print the received data to stdout']]

    _ciphers = transport.SSHClientTransport.supportedCiphers
    _macs = transport.SSHClientTransport.supportedMACs

    compData = usage.Completions(
        mutuallyExclusive=[("tty", "notty")],
        optActions={
            "cipher": usage.CompleteList(_ciphers),
            "macs": usage.CompleteList(_macs),
            "localforward": usage.Completer(descr="listen-port:host:port"),
            "remoteforward": usage.Completer(descr="listen-port:host:port")},
        extraActions=[usage.CompleteUserAtHost(),
                      usage.Completer(descr="command"),
                      usage.Completer(descr="argument", repeat=True)]
        )

    identitys = []
    localForwards = []
    remoteForwards = []

    def opt_identity(self, i):
        self.identitys.append(i)

    def opt_localforward(self, f):
        localPort, remoteHost, remotePort = f.split(':') # doesn't do v6 yet
        localPort = int(localPort)
        remotePort = int(remotePort)
        self.localForwards.append((localPort, (remoteHost, remotePort)))

    def opt_remoteforward(self, f):
        remotePort, connHost, connPort = f.split(':') # doesn't do v6 yet
        remotePort = int(remotePort)
        connPort = int(connPort)
        self.remoteForwards.append((remotePort, (connHost, connPort)))

    def opt_compress(self):
        SSHClientTransport.supportedCompressions[0:1] = ['zlib']

    def parseArgs(self, *args):
        if args:
            self['host'] = args[0]
            self['command'] = ' '.join(args[1:])
        else:
            self['host'] = ''
            self['command'] = ''

# Rest of code in "run"
options = None
menu = None
exitStatus = 0
frame = None

def deferredAskFrame(question, echo):
    if frame.callback:
        raise ValueError("can't ask 2 questions at once!")
    d = defer.Deferred()
    resp = []
    def gotChar(ch, resp=resp):
        if not ch: return
        if ch=='\x03': # C-c
            reactor.stop()
        if ch=='\r':
            frame.write('\r\n')
            stresp = ''.join(resp)
            del resp
            frame.callback = None
            d.callback(stresp)
            return
        elif 32 <= ord(ch) < 127:
            resp.append(ch)
            if echo:
                frame.write(ch)
        elif ord(ch) == 8 and resp: # BS
            if echo: frame.write('\x08 \x08')
            resp.pop()
    frame.callback = gotChar
    frame.write(question)
    frame.canvas.focus_force()
    return d

def run():
    global menu, options, frame
    args = sys.argv[1:]
    if '-l' in args: # cvs is an idiot
        i = args.index('-l')
        args = args[i:i+2]+args
        del args[i+2:i+4]
    for arg in args[:]:
        try:
            i = args.index(arg)
            if arg[:2] == '-o' and args[i+1][0]!='-':
                args[i:i+2] = [] # suck on it scp
        except ValueError:
            pass
    root = Tkinter.Tk()
    root.withdraw()
    top = Tkinter.Toplevel()
    menu = TkConchMenu(top)
    menu.pack(side=Tkinter.TOP, fill=Tkinter.BOTH, expand=1)
    options = GeneralOptions()
    try:
        options.parseOptions(args)
    except usage.UsageError as u:
        print('ERROR: %s' % u)
        options.opt_help()
        sys.exit(1)
    for k,v in options.items():
        if v and hasattr(menu, k):
            getattr(menu,k).insert(Tkinter.END, v)
    for (p, (rh, rp)) in options.localForwards:
        menu.forwards.insert(Tkinter.END, 'L:%s:%s:%s' % (p, rh, rp))
    options.localForwards = []
    for (p, (rh, rp)) in options.remoteForwards:
        menu.forwards.insert(Tkinter.END, 'R:%s:%s:%s' % (p, rh, rp))
    options.remoteForwards = []
    frame = tkvt100.VT100Frame(root, callback=None)
    root.geometry('%dx%d'%(tkvt100.fontWidth*frame.width+3, tkvt100.fontHeight*frame.height+3))
    frame.pack(side = Tkinter.TOP)
    tksupport.install(root)
    root.withdraw()
    if (options['host'] and options['user']) or '@' in options['host']:
        menu.doConnect()
    else:
        top.mainloop()
    reactor.run()
    sys.exit(exitStatus)

def handleError():
    from twisted.python import failure
    global exitStatus
    exitStatus = 2
    log.err(failure.Failure())
    reactor.stop()
    raise

class SSHClientFactory(protocol.ClientFactory):
    noisy = 1

    def stopFactory(self):
        reactor.stop()

    def buildProtocol(self, addr):
        return SSHClientTransport()

    def clientConnectionFailed(self, connector, reason):
        tkMessageBox.showwarning('TkConch','Connection Failed, Reason:\n %s: %s' % (reason.type, reason.value))

class SSHClientTransport(transport.SSHClientTransport):

    def receiveError(self, code, desc):
        global exitStatus
        exitStatus = 'conch:\tRemote side disconnected with error code %i\nconch:\treason: %s' % (code, desc)

    def sendDisconnect(self, code, reason):
        global exitStatus
        exitStatus = 'conch:\tSending disconnect with error code %i\nconch:\treason: %s' % (code, reason)
        transport.SSHClientTransport.sendDisconnect(self, code, reason)

    def receiveDebug(self, alwaysDisplay, message, lang):
        global options
        if alwaysDisplay or options['log']:
            log.msg('Received Debug Message: %s' % message)

    def verifyHostKey(self, pubKey, fingerprint):
        #d = defer.Deferred()
        #d.addCallback(lambda x:defer.succeed(1))
        #d.callback(2)
        #return d
        goodKey = isInKnownHosts(options['host'], pubKey, {'known-hosts': None})
        if goodKey == 1: # good key
            return defer.succeed(1)
        elif goodKey == 2: # AAHHHHH changed
            return defer.fail(error.ConchError('bad host key'))
        else:
            if options['host'] == self.transport.getPeer()[1]:
                host = options['host']
                khHost = options['host']
            else:
                host = '%s (%s)' % (options['host'],
                                    self.transport.getPeer()[1])
                khHost = '%s,%s' % (options['host'],
                                    self.transport.getPeer()[1])
            keyType = common.getNS(pubKey)[0]
            ques = """The authenticity of host '%s' can't be established.\r
%s key fingerprint is %s.""" % (host,
                                {'ssh-dss':'DSA', 'ssh-rsa':'RSA'}[keyType],
                                fingerprint)
            ques+='\r\nAre you sure you want to continue connecting (yes/no)? '
            return deferredAskFrame(ques, 1).addCallback(self._cbVerifyHostKey, pubKey, khHost, keyType)

    def _cbVerifyHostKey(self, ans, pubKey, khHost, keyType):
        if ans.lower() not in ('yes', 'no'):
            return deferredAskFrame("Please type  'yes' or 'no': ",1).addCallback(self._cbVerifyHostKey, pubKey, khHost, keyType)
        if ans.lower() == 'no':
            frame.write('Host key verification failed.\r\n')
            raise error.ConchError('bad host key')
        try:
            frame.write("Warning: Permanently added '%s' (%s) to the list of known hosts.\r\n" % (khHost, {'ssh-dss':'DSA', 'ssh-rsa':'RSA'}[keyType]))
            with open(os.path.expanduser('~/.ssh/known_hosts'), 'a') as known_hosts:
                encodedKey = base64.encodestring(pubKey).replace('\n', '')
                known_hosts.write('\n%s %s %s' % (khHost, keyType, encodedKey))
        except:
            log.deferr()
            raise error.ConchError

    def connectionSecure(self):
        if options['user']:
            user = options['user']
        else:
            user = getpass.getuser()
        self.requestService(SSHUserAuthClient(user, SSHConnection()))

class SSHUserAuthClient(userauth.SSHUserAuthClient):
    usedFiles = []

    def getPassword(self, prompt = None):
        if not prompt:
            prompt = "%s@%s's password: " % (self.user, options['host'])
        return deferredAskFrame(prompt,0)

    def getPublicKey(self):
        files = [x for x in options.identitys if x not in self.usedFiles]
        if not files:
            return None
        file = files[0]
        log.msg(file)
        self.usedFiles.append(file)
        file = os.path.expanduser(file)
        file += '.pub'
        if not os.path.exists(file):
            return
        try:
            return keys.Key.fromFile(file).blob()
        except:
            return self.getPublicKey() # try again

    def getPrivateKey(self):
        file = os.path.expanduser(self.usedFiles[-1])
        if not os.path.exists(file):
            return None
        try:
            return defer.succeed(keys.Key.fromFile(file).keyObject)
        except keys.BadKeyError as e:
            if e.args[0] == 'encrypted key with no password':
                prompt = "Enter passphrase for key '%s': " % \
                       self.usedFiles[-1]
                return deferredAskFrame(prompt, 0).addCallback(self._cbGetPrivateKey, 0)
    def _cbGetPrivateKey(self, ans, count):
        file = os.path.expanduser(self.usedFiles[-1])
        try:
            return keys.Key.fromFile(file, password = ans).keyObject
        except keys.BadKeyError:
            if count == 2:
                raise
            prompt = "Enter passphrase for key '%s': " % \
                   self.usedFiles[-1]
            return deferredAskFrame(prompt, 0).addCallback(self._cbGetPrivateKey, count+1)

class SSHConnection(connection.SSHConnection):
    def serviceStarted(self):
        if not options['noshell']:
            self.openChannel(SSHSession())
        if options.localForwards:
            for localPort, hostport in options.localForwards:
                reactor.listenTCP(localPort,
                            forwarding.SSHListenForwardingFactory(self,
                                hostport,
                                forwarding.SSHListenClientForwardingChannel))
        if options.remoteForwards:
            for remotePort, hostport in options.remoteForwards:
                log.msg('asking for remote forwarding for %s:%s' %
                        (remotePort, hostport))
                data = forwarding.packGlobal_tcpip_forward(
                    ('0.0.0.0', remotePort))
                self.sendGlobalRequest('tcpip-forward', data)
                self.remoteForwards[remotePort] = hostport

class SSHSession(channel.SSHChannel):

    name = 'session'

    def channelOpen(self, foo):
        #global globalSession
        #globalSession = self
        # turn off local echo
        self.escapeMode = 1
        c = session.SSHSessionClient()
        if options['escape']:
            c.dataReceived = self.handleInput
        else:
            c.dataReceived = self.write
        c.connectionLost = self.sendEOF
        frame.callback = c.dataReceived
        frame.canvas.focus_force()
        if options['subsystem']:
            self.conn.sendRequest(self, 'subsystem', \
                common.NS(options['command']))
        elif options['command']:
            if options['tty']:
                term = os.environ.get('TERM', 'xterm')
                #winsz = fcntl.ioctl(fd, tty.TIOCGWINSZ, '12345678')
                winSize = (25,80,0,0) #struct.unpack('4H', winsz)
                ptyReqData = session.packRequest_pty_req(term, winSize, '')
                self.conn.sendRequest(self, 'pty-req', ptyReqData)
            self.conn.sendRequest(self, 'exec', \
                common.NS(options['command']))
        else:
            if not options['notty']:
                term = os.environ.get('TERM', 'xterm')
                #winsz = fcntl.ioctl(fd, tty.TIOCGWINSZ, '12345678')
                winSize = (25,80,0,0) #struct.unpack('4H', winsz)
                ptyReqData = session.packRequest_pty_req(term, winSize, '')
                self.conn.sendRequest(self, 'pty-req', ptyReqData)
            self.conn.sendRequest(self, 'shell', '')
        self.conn.transport.transport.setTcpNoDelay(1)

    def handleInput(self, char):
        #log.msg('handling %s' % repr(char))
        if char in ('\n', '\r'):
            self.escapeMode = 1
            self.write(char)
        elif self.escapeMode == 1 and char == options['escape']:
            self.escapeMode = 2
        elif self.escapeMode == 2:
            self.escapeMode = 1 # so we can chain escapes together
            if char == '.': # disconnect
                log.msg('disconnecting from escape')
                reactor.stop()
                return
            elif char == '\x1a': # ^Z, suspend
                # following line courtesy of Erwin@freenode
                os.kill(os.getpid(), signal.SIGSTOP)
                return
            elif char == 'R': # rekey connection
                log.msg('rekeying connection')
                self.conn.transport.sendKexInit()
                return
            self.write('~' + char)
        else:
            self.escapeMode = 0
            self.write(char)

    def dataReceived(self, data):
        if options['ansilog']:
            print(repr(data))
        frame.write(data)

    def extReceived(self, t, data):
        if t==connection.EXTENDED_DATA_STDERR:
            log.msg('got %s stderr data' % len(data))
            sys.stderr.write(data)
            sys.stderr.flush()

    def eofReceived(self):
        log.msg('got eof')
        sys.stdin.close()

    def closed(self):
        log.msg('closed %s' % self)
        if len(self.conn.channels) == 1: # just us left
            reactor.stop()

    def request_exit_status(self, data):
        global exitStatus
        exitStatus = int(struct.unpack('>L', data)[0])
        log.msg('exit status: %s' % exitStatus)

    def sendEOF(self):
        self.conn.sendEOF(self)

if __name__=="__main__":
    run()
