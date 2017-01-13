# -*- test-case-name: twisted.conch.test.test_cftp -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation module for the I{cftp} command.
"""
from __future__ import division, print_function
import os, sys, getpass, struct, tty, fcntl, stat
import fnmatch, pwd, glob

from twisted.conch.client import connect, default, options
from twisted.conch.ssh import connection, common
from twisted.conch.ssh import channel, filetransfer
from twisted.protocols import basic
from twisted.internet import reactor, stdio, defer, utils
from twisted.python import log, usage, failure

class ClientOptions(options.ConchOptions):

    synopsis = """Usage:   cftp [options] [user@]host
         cftp [options] [user@]host[:dir[/]]
         cftp [options] [user@]host[:file [localfile]]
"""
    longdesc = ("cftp is a client for logging into a remote machine and "
                "executing commands to send and receive file information")

    optParameters = [
                    ['buffersize', 'B', 32768, 'Size of the buffer to use for sending/receiving.'],
                    ['batchfile', 'b', None, 'File to read commands from, or \'-\' for stdin.'],
                    ['requests', 'R', 5, 'Number of requests to make before waiting for a reply.'],
                    ['subsystem', 's', 'sftp', 'Subsystem/server program to connect to.']]

    compData = usage.Completions(
        descriptions={
            "buffersize": "Size of send/receive buffer (default: 32768)"},
        extraActions=[usage.CompleteUserAtHost(),
                      usage.CompleteFiles(descr="local file")])

    def parseArgs(self, host, localPath=None):
        self['remotePath'] = ''
        if ':' in host:
            host, self['remotePath'] = host.split(':', 1)
            self['remotePath'].rstrip('/')
        self['host'] = host
        self['localPath'] = localPath

def run():
#    import hotshot
#    prof = hotshot.Profile('cftp.prof')
#    prof.start()
    args = sys.argv[1:]
    if '-l' in args: # cvs is an idiot
        i = args.index('-l')
        args = args[i:i+2]+args
        del args[i+2:i+4]
    options = ClientOptions()
    try:
        options.parseOptions(args)
    except usage.UsageError as u:
        print('ERROR: %s' % u)
        sys.exit(1)
    if options['log']:
        realout = sys.stdout
        log.startLogging(sys.stderr)
        sys.stdout = realout
    else:
        log.discardLogs()
    doConnect(options)
    reactor.run()
#    prof.stop()
#    prof.close()

def handleError():
    global exitStatus
    exitStatus = 2
    try:
        reactor.stop()
    except: pass
    log.err(failure.Failure())
    raise

def doConnect(options):
#    log.deferr = handleError # HACK
    if '@' in options['host']:
        options['user'], options['host'] = options['host'].split('@',1)
    host = options['host']
    if not options['user']:
        options['user'] = getpass.getuser()
    if not options['port']:
        options['port'] = 22
    else:
        options['port'] = int(options['port'])
    host = options['host']
    port = options['port']
    conn = SSHConnection()
    conn.options = options
    vhk = default.verifyHostKey
    uao = default.SSHUserAuthClient(options['user'], options, conn)
    connect.connect(host, port, options, vhk, uao).addErrback(_ebExit)

def _ebExit(f):
    #global exitStatus
    if hasattr(f.value, 'value'):
        s = f.value.value
    else:
        s = str(f)
    print(s)
    #exitStatus = "conch: exiting with error %s" % f
    try:
        reactor.stop()
    except: pass

def _ignore(*args): pass

class FileWrapper:

    def __init__(self, f):
        self.f = f
        self.total = 0.0
        f.seek(0, 2) # seek to the end
        self.size = f.tell()

    def __getattr__(self, attr):
        return getattr(self.f, attr)

class StdioClient(basic.LineReceiver):

    _pwd = pwd

    ps = 'cftp> '
    delimiter = '\n'

    reactor = reactor

    def __init__(self, client, f = None):
        self.client = client
        self.currentDirectory = ''
        self.file = f
        self.useProgressBar = (not f and 1) or 0

    def connectionMade(self):
        self.client.realPath('').addCallback(self._cbSetCurDir)

    def _cbSetCurDir(self, path):
        self.currentDirectory = path
        self._newLine()

    def lineReceived(self, line):
        if self.client.transport.localClosed:
            return
        log.msg('got line %s' % repr(line))
        line = line.lstrip()
        if not line:
            self._newLine()
            return
        if self.file and line.startswith('-'):
            self.ignoreErrors = 1
            line = line[1:]
        else:
            self.ignoreErrors = 0
        d = self._dispatchCommand(line)
        if d is not None:
            d.addCallback(self._cbCommand)
            d.addErrback(self._ebCommand)


    def _dispatchCommand(self, line):
        if ' ' in line:
            command, rest = line.split(' ', 1)
            rest = rest.lstrip()
        else:
            command, rest = line, ''
        if command.startswith('!'): # command
            f = self.cmd_EXEC
            rest = (command[1:] + ' ' + rest).strip()
        else:
            command = command.upper()
            log.msg('looking up cmd %s' % command)
            f = getattr(self, 'cmd_%s' % command, None)
        if f is not None:
            return defer.maybeDeferred(f, rest)
        else:
            self._ebCommand(failure.Failure(NotImplementedError(
                "No command called `%s'" % command)))
            self._newLine()

    def _printFailure(self, f):
        log.msg(f)
        e = f.trap(NotImplementedError, filetransfer.SFTPError, OSError, IOError)
        if e == NotImplementedError:
            self.transport.write(self.cmd_HELP(''))
        elif e == filetransfer.SFTPError:
            self.transport.write("remote error %i: %s\n" %
                    (f.value.code, f.value.message))
        elif e in (OSError, IOError):
            self.transport.write("local error %i: %s\n" %
                    (f.value.errno, f.value.strerror))

    def _newLine(self):
        if self.client.transport.localClosed:
            return
        self.transport.write(self.ps)
        self.ignoreErrors = 0
        if self.file:
            l = self.file.readline()
            if not l:
                self.client.transport.loseConnection()
            else:
                self.transport.write(l)
                self.lineReceived(l.strip())

    def _cbCommand(self, result):
        if result is not None:
            self.transport.write(result)
            if not result.endswith('\n'):
                self.transport.write('\n')
        self._newLine()

    def _ebCommand(self, f):
        self._printFailure(f)
        if self.file and not self.ignoreErrors:
            self.client.transport.loseConnection()
        self._newLine()

    def cmd_CD(self, path):
        path, rest = self._getFilename(path)
        if not path.endswith('/'):
            path += '/'
        newPath = path and os.path.join(self.currentDirectory, path) or ''
        d = self.client.openDirectory(newPath)
        d.addCallback(self._cbCd)
        d.addErrback(self._ebCommand)
        return d

    def _cbCd(self, directory):
        directory.close()
        d = self.client.realPath(directory.name)
        d.addCallback(self._cbCurDir)
        return d

    def _cbCurDir(self, path):
        self.currentDirectory = path

    def cmd_CHGRP(self, rest):
        grp, rest = rest.split(None, 1)
        path, rest = self._getFilename(rest)
        grp = int(grp)
        d = self.client.getAttrs(path)
        d.addCallback(self._cbSetUsrGrp, path, grp=grp)
        return d

    def cmd_CHMOD(self, rest):
        mod, rest = rest.split(None, 1)
        path, rest = self._getFilename(rest)
        mod = int(mod, 8)
        d = self.client.setAttrs(path, {'permissions':mod})
        d.addCallback(_ignore)
        return d

    def cmd_CHOWN(self, rest):
        usr, rest = rest.split(None, 1)
        path, rest = self._getFilename(rest)
        usr = int(usr)
        d = self.client.getAttrs(path)
        d.addCallback(self._cbSetUsrGrp, path, usr=usr)
        return d

    def _cbSetUsrGrp(self, attrs, path, usr=None, grp=None):
        new = {}
        new['uid'] = (usr is not None) and usr or attrs['uid']
        new['gid'] = (grp is not None) and grp or attrs['gid']
        d = self.client.setAttrs(path, new)
        d.addCallback(_ignore)
        return d

    def cmd_GET(self, rest):
        remote, rest = self._getFilename(rest)
        if '*' in remote or '?' in remote: # wildcard
            if rest:
                local, rest = self._getFilename(rest)
                if not os.path.isdir(local):
                    return "Wildcard get with non-directory target."
            else:
                local = ''
            d = self._remoteGlob(remote)
            d.addCallback(self._cbGetMultiple, local)
            return d
        if rest:
            local, rest = self._getFilename(rest)
        else:
            local = os.path.split(remote)[1]
        log.msg((remote, local))
        lf = open(local, 'w', 0)
        path = os.path.join(self.currentDirectory, remote)
        d = self.client.openFile(path, filetransfer.FXF_READ, {})
        d.addCallback(self._cbGetOpenFile, lf)
        d.addErrback(self._ebCloseLf, lf)
        return d

    def _cbGetMultiple(self, files, local):
        #if self._useProgressBar: # one at a time
        # XXX this can be optimized for times w/o progress bar
        return self._cbGetMultipleNext(None, files, local)

    def _cbGetMultipleNext(self, res, files, local):
        if isinstance(res, failure.Failure):
            self._printFailure(res)
        elif res:
            self.transport.write(res)
            if not res.endswith('\n'):
                self.transport.write('\n')
        if not files:
            return
        f = files.pop(0)[0]
        lf = open(os.path.join(local, os.path.split(f)[1]), 'w', 0)
        path = os.path.join(self.currentDirectory, f)
        d = self.client.openFile(path, filetransfer.FXF_READ, {})
        d.addCallback(self._cbGetOpenFile, lf)
        d.addErrback(self._ebCloseLf, lf)
        d.addBoth(self._cbGetMultipleNext, files, local)
        return d

    def _ebCloseLf(self, f, lf):
        lf.close()
        return f

    def _cbGetOpenFile(self, rf, lf):
        return rf.getAttrs().addCallback(self._cbGetFileSize, rf, lf)

    def _cbGetFileSize(self, attrs, rf, lf):
        if not stat.S_ISREG(attrs['permissions']):
            rf.close()
            lf.close()
            return "Can't get non-regular file: %s" % rf.name
        rf.size = attrs['size']
        bufferSize = self.client.transport.conn.options['buffersize']
        numRequests = self.client.transport.conn.options['requests']
        rf.total = 0.0
        dList = []
        chunks = []
        startTime = self.reactor.seconds()
        for i in range(numRequests):
            d = self._cbGetRead('', rf, lf, chunks, 0, bufferSize, startTime)
            dList.append(d)
        dl = defer.DeferredList(dList, fireOnOneErrback=1)
        dl.addCallback(self._cbGetDone, rf, lf)
        return dl

    def _getNextChunk(self, chunks):
        end = 0
        for chunk in chunks:
            if end == 'eof':
                return # nothing more to get
            if end != chunk[0]:
                i = chunks.index(chunk)
                chunks.insert(i, (end, chunk[0]))
                return (end, chunk[0] - end)
            end = chunk[1]
        bufSize = int(self.client.transport.conn.options['buffersize'])
        chunks.append((end, end + bufSize))
        return (end, bufSize)

    def _cbGetRead(self, data, rf, lf, chunks, start, size, startTime):
        if data and isinstance(data, failure.Failure):
            log.msg('get read err: %s' % data)
            reason = data
            reason.trap(EOFError)
            i = chunks.index((start, start + size))
            del chunks[i]
            chunks.insert(i, (start, 'eof'))
        elif data:
            log.msg('get read data: %i' % len(data))
            lf.seek(start)
            lf.write(data)
            if len(data) != size:
                log.msg('got less than we asked for: %i < %i' %
                        (len(data), size))
                i = chunks.index((start, start + size))
                del chunks[i]
                chunks.insert(i, (start, start + len(data)))
            rf.total += len(data)
        if self.useProgressBar:
            self._printProgressBar(rf, startTime)
        chunk = self._getNextChunk(chunks)
        if not chunk:
            return
        else:
            start, length = chunk
        log.msg('asking for %i -> %i' % (start, start+length))
        d = rf.readChunk(start, length)
        d.addBoth(self._cbGetRead, rf, lf, chunks, start, length, startTime)
        return d

    def _cbGetDone(self, ignored, rf, lf):
        log.msg('get done')
        rf.close()
        lf.close()
        if self.useProgressBar:
            self.transport.write('\n')
        return "Transferred %s to %s" % (rf.name, lf.name)


    def cmd_PUT(self, rest):
        """
        Do an upload request for a single local file or a globing expression.

        @param rest: Requested command line for the PUT command.
        @type rest: L{str}

        @return: A deferred which fires with L{None} when transfer is done.
        @rtype: L{defer.Deferred}
        """
        local, rest = self._getFilename(rest)

        # FIXME: https://twistedmatrix.com/trac/ticket/7241
        # Use a better check for globbing expression.
        if '*' in local or '?' in local:
            if rest:
                remote, rest = self._getFilename(rest)
                remote = os.path.join(self.currentDirectory, remote)
            else:
                remote = ''

            files = glob.glob(local)
            return self._putMultipleFiles(files, remote)

        else:
            if rest:
                remote, rest = self._getFilename(rest)
            else:
                remote = os.path.split(local)[1]
            return self._putSingleFile(local, remote)


    def _putSingleFile(self, local, remote):
        """
        Perform an upload for a single file.

        @param local: Path to local file.
        @type local: L{str}.

        @param remote: Remote path for the request relative to current working
            directory.
        @type remote: L{str}

        @return: A deferred which fires when transfer is done.
        """
        return self._cbPutMultipleNext(None, [local], remote, single=True)


    def _putMultipleFiles(self, files, remote):
        """
        Perform an upload for a list of local files.

        @param files: List of local files.
        @type files: C{list} of L{str}.

        @param remote: Remote path for the request relative to current working
            directory.
        @type remote: L{str}

        @return: A deferred which fires when transfer is done.
        """
        return self._cbPutMultipleNext(None, files, remote)


    def _cbPutMultipleNext(
            self, previousResult, files, remotePath, single=False):
        """
        Perform an upload for the next file in the list of local files.

        @param previousResult: Result form previous file form the list.
        @type previousResult: L{str}

        @param files: List of local files.
        @type files: C{list} of L{str}

        @param remotePath: Remote path for the request relative to current
            working directory.
        @type remotePath: L{str}

        @param single: A flag which signals if this is a transfer for a single
            file in which case we use the exact remote path
        @type single: L{bool}

        @return: A deferred which fires when transfer is done.
        """
        if isinstance(previousResult, failure.Failure):
            self._printFailure(previousResult)
        elif previousResult:
            self.transport.write(previousResult)
            if not previousResult.endswith('\n'):
                self.transport.write('\n')

        currentFile = None
        while files and not currentFile:
            try:
                currentFile = files.pop(0)
                localStream = open(currentFile, 'r')
            except:
                self._printFailure(failure.Failure())
                currentFile = None

        # No more files to transfer.
        if not currentFile:
            return None

        if single:
            remote = remotePath
        else:
            name = os.path.split(currentFile)[1]
            remote = os.path.join(remotePath, name)
            log.msg((name, remote, remotePath))

        d = self._putRemoteFile(localStream, remote)
        d.addBoth(self._cbPutMultipleNext, files, remotePath)
        return d


    def _putRemoteFile(self, localStream, remotePath):
        """
        Do an upload request.

        @param localStream: Local stream from where data is read.
        @type localStream: File like object.

        @param remotePath: Remote path for the request relative to current working directory.
        @type remotePath: L{str}

        @return: A deferred which fires when transfer is done.
        """
        remote = os.path.join(self.currentDirectory, remotePath)
        flags = (
            filetransfer.FXF_WRITE |
            filetransfer.FXF_CREAT |
            filetransfer.FXF_TRUNC
            )
        d = self.client.openFile(remote, flags, {})
        d.addCallback(self._cbPutOpenFile, localStream)
        d.addErrback(self._ebCloseLf, localStream)
        return d


    def _cbPutOpenFile(self, rf, lf):
        numRequests = self.client.transport.conn.options['requests']
        if self.useProgressBar:
            lf = FileWrapper(lf)
        dList = []
        chunks = []
        startTime = self.reactor.seconds()
        for i in range(numRequests):
            d = self._cbPutWrite(None, rf, lf, chunks, startTime)
            if d:
                dList.append(d)
        dl = defer.DeferredList(dList, fireOnOneErrback=1)
        dl.addCallback(self._cbPutDone, rf, lf)
        return dl

    def _cbPutWrite(self, ignored, rf, lf, chunks, startTime):
        chunk = self._getNextChunk(chunks)
        start, size = chunk
        lf.seek(start)
        data = lf.read(size)
        if self.useProgressBar:
            lf.total += len(data)
            self._printProgressBar(lf, startTime)
        if data:
            d = rf.writeChunk(start, data)
            d.addCallback(self._cbPutWrite, rf, lf, chunks, startTime)
            return d
        else:
            return

    def _cbPutDone(self, ignored, rf, lf):
        lf.close()
        rf.close()
        if self.useProgressBar:
            self.transport.write('\n')
        return 'Transferred %s to %s' % (lf.name, rf.name)

    def cmd_LCD(self, path):
        os.chdir(path)

    def cmd_LN(self, rest):
        linkpath, rest = self._getFilename(rest)
        targetpath, rest = self._getFilename(rest)
        linkpath, targetpath = map(
                lambda x: os.path.join(self.currentDirectory, x),
                (linkpath, targetpath))
        return self.client.makeLink(linkpath, targetpath).addCallback(_ignore)

    def cmd_LS(self, rest):
        # possible lines:
        # ls                    current directory
        # ls name_of_file       that file
        # ls name_of_directory  that directory
        # ls some_glob_string   current directory, globbed for that string
        options = []
        rest = rest.split()
        while rest and rest[0] and rest[0][0] == '-':
            opts = rest.pop(0)[1:]
            for o in opts:
                if o == 'l':
                    options.append('verbose')
                elif o == 'a':
                    options.append('all')
        rest = ' '.join(rest)
        path, rest = self._getFilename(rest)
        if not path:
            fullPath = self.currentDirectory + '/'
        else:
            fullPath = os.path.join(self.currentDirectory, path)
        d = self._remoteGlob(fullPath)
        d.addCallback(self._cbDisplayFiles, options)
        return d

    def _cbDisplayFiles(self, files, options):
        files.sort()
        if 'all' not in options:
            files = [f for f in files if not f[0].startswith('.')]
        if 'verbose' in options:
            lines = [f[1] for f in files]
        else:
            lines = [f[0] for f in files]
        if not lines:
            return None
        else:
            return '\n'.join(lines)

    def cmd_MKDIR(self, path):
        path, rest = self._getFilename(path)
        path = os.path.join(self.currentDirectory, path)
        return self.client.makeDirectory(path, {}).addCallback(_ignore)

    def cmd_RMDIR(self, path):
        path, rest = self._getFilename(path)
        path = os.path.join(self.currentDirectory, path)
        return self.client.removeDirectory(path).addCallback(_ignore)

    def cmd_LMKDIR(self, path):
        os.system("mkdir %s" % path)

    def cmd_RM(self, path):
        path, rest = self._getFilename(path)
        path = os.path.join(self.currentDirectory, path)
        return self.client.removeFile(path).addCallback(_ignore)

    def cmd_LLS(self, rest):
        os.system("ls %s" % rest)

    def cmd_RENAME(self, rest):
        oldpath, rest = self._getFilename(rest)
        newpath, rest = self._getFilename(rest)
        oldpath, newpath = map (
                lambda x: os.path.join(self.currentDirectory, x),
                (oldpath, newpath))
        return self.client.renameFile(oldpath, newpath).addCallback(_ignore)

    def cmd_EXIT(self, ignored):
        self.client.transport.loseConnection()

    cmd_QUIT = cmd_EXIT

    def cmd_VERSION(self, ignored):
        return "SFTP version %i" % self.client.version

    def cmd_HELP(self, ignored):
        return """Available commands:
cd path                         Change remote directory to 'path'.
chgrp gid path                  Change gid of 'path' to 'gid'.
chmod mode path                 Change mode of 'path' to 'mode'.
chown uid path                  Change uid of 'path' to 'uid'.
exit                            Disconnect from the server.
get remote-path [local-path]    Get remote file.
help                            Get a list of available commands.
lcd path                        Change local directory to 'path'.
lls [ls-options] [path]         Display local directory listing.
lmkdir path                     Create local directory.
ln linkpath targetpath          Symlink remote file.
lpwd                            Print the local working directory.
ls [-l] [path]                  Display remote directory listing.
mkdir path                      Create remote directory.
progress                        Toggle progress bar.
put local-path [remote-path]    Put local file.
pwd                             Print the remote working directory.
quit                            Disconnect from the server.
rename oldpath newpath          Rename remote file.
rmdir path                      Remove remote directory.
rm path                         Remove remote file.
version                         Print the SFTP version.
?                               Synonym for 'help'.
"""

    def cmd_PWD(self, ignored):
        return self.currentDirectory

    def cmd_LPWD(self, ignored):
        return os.getcwd()

    def cmd_PROGRESS(self, ignored):
        self.useProgressBar = not self.useProgressBar
        return "%ssing progess bar." % (self.useProgressBar and "U" or "Not u")

    def cmd_EXEC(self, rest):
        """
        Run C{rest} using the user's shell (or /bin/sh if they do not have
        one).
        """
        shell = self._pwd.getpwnam(getpass.getuser())[6]
        if not shell:
            shell = '/bin/sh'
        if rest:
            cmds = ['-c', rest]
            return utils.getProcessOutput(shell, cmds, errortoo=1)
        else:
            os.system(shell)

    # accessory functions

    def _remoteGlob(self, fullPath):
        log.msg('looking up %s' % fullPath)
        head, tail = os.path.split(fullPath)
        if '*' in tail or '?' in tail:
            glob = 1
        else:
            glob = 0
        if tail and not glob: # could be file or directory
            # try directory first
            d = self.client.openDirectory(fullPath)
            d.addCallback(self._cbOpenList, '')
            d.addErrback(self._ebNotADirectory, head, tail)
        else:
            d = self.client.openDirectory(head)
            d.addCallback(self._cbOpenList, tail)
        return d

    def _cbOpenList(self, directory, glob):
        files = []
        d = directory.read()
        d.addBoth(self._cbReadFile, files, directory, glob)
        return d

    def _ebNotADirectory(self, reason, path, glob):
        d = self.client.openDirectory(path)
        d.addCallback(self._cbOpenList, glob)
        return d

    def _cbReadFile(self, files, l, directory, glob):
        if not isinstance(files, failure.Failure):
            if glob:
                l.extend([f for f in files if fnmatch.fnmatch(f[0], glob)])
            else:
                l.extend(files)
            d = directory.read()
            d.addBoth(self._cbReadFile, l, directory, glob)
            return d
        else:
            reason = files
            reason.trap(EOFError)
            directory.close()
            return l

    def _abbrevSize(self, size):
        # from http://mail.python.org/pipermail/python-list/1999-December/018395.html
        _abbrevs = [
            (1<<50, 'PB'),
            (1<<40, 'TB'),
            (1<<30, 'GB'),
            (1<<20, 'MB'),
            (1<<10, 'kB'),
            (1, 'B')
            ]

        for factor, suffix in _abbrevs:
            if size > factor:
                break
        return '%.1f' % (size/factor) + suffix

    def _abbrevTime(self, t):
        if t > 3600: # 1 hour
            hours = int(t / 3600)
            t -= (3600 * hours)
            mins = int(t / 60)
            t -= (60 * mins)
            return "%i:%02i:%02i" % (hours, mins, t)
        else:
            mins = int(t/60)
            t -= (60 * mins)
            return "%02i:%02i" % (mins, t)


    def _printProgressBar(self, f, startTime):
        """
        Update a console progress bar on this L{StdioClient}'s transport, based
        on the difference between the start time of the operation and the
        current time according to the reactor, and appropriate to the size of
        the console window.

        @param f: a wrapper around the file which is being written or read
        @type f: L{FileWrapper}

        @param startTime: The time at which the operation being tracked began.
        @type startTime: L{float}
        """
        diff = self.reactor.seconds() - startTime
        total = f.total
        try:
            winSize = struct.unpack('4H',
                fcntl.ioctl(0, tty.TIOCGWINSZ, '12345679'))
        except IOError:
            winSize = [None, 80]
        if diff == 0.0:
            speed = 0.0
        else:
            speed = total / diff
        if speed:
            timeLeft = (f.size - total) / speed
        else:
            timeLeft = 0
        front = f.name
        if f.size:
            percentage = (total / f.size) * 100
        else:
            percentage = 100
        back = '%3i%% %s %sps %s ' % (percentage,
                                      self._abbrevSize(total),
                                      self._abbrevSize(speed),
                                      self._abbrevTime(timeLeft))
        spaces = (winSize[1] - (len(front) + len(back) + 1)) * ' '
        self.transport.write('\r%s%s%s' % (front, spaces, back))


    def _getFilename(self, line):
        """
        Parse line received as command line input and return first filename
        together with the remaining line.

        @param line: Arguments received from command line input.
        @type line: L{str}

        @return: Tupple with filename and rest. Return empty values when no path was not found.
        @rtype: C{tupple}
        """
        line = line.strip()
        if not line:
            return '', ''
        if line[0] in '\'"':
            ret = []
            line = list(line)
            try:
                for i in range(1,len(line)):
                    c = line[i]
                    if c == line[0]:
                        return ''.join(ret), ''.join(line[i+1:]).lstrip()
                    elif c == '\\': # quoted character
                        del line[i]
                        if line[i] not in '\'"\\':
                            raise IndexError("bad quote: \\%s" % (line[i],))
                        ret.append(line[i])
                    else:
                        ret.append(line[i])
            except IndexError:
                raise IndexError("unterminated quote")
        ret = line.split(None, 1)
        if len(ret) == 1:
            return ret[0], ''
        else:
            return ret[0], ret[1]

StdioClient.__dict__['cmd_?'] = StdioClient.cmd_HELP

class SSHConnection(connection.SSHConnection):
    def serviceStarted(self):
        self.openChannel(SSHSession())

class SSHSession(channel.SSHChannel):

    name = 'session'

    def channelOpen(self, foo):
        log.msg('session %s open' % self.id)
        if self.conn.options['subsystem'].startswith('/'):
            request = 'exec'
        else:
            request = 'subsystem'
        d = self.conn.sendRequest(self, request, \
            common.NS(self.conn.options['subsystem']), wantReply=1)
        d.addCallback(self._cbSubsystem)
        d.addErrback(_ebExit)

    def _cbSubsystem(self, result):
        self.client = filetransfer.FileTransferClient()
        self.client.makeConnection(self)
        self.dataReceived = self.client.dataReceived
        f = None
        if self.conn.options['batchfile']:
            fn = self.conn.options['batchfile']
            if fn != '-':
                f = open(fn)
        self.stdio = stdio.StandardIO(StdioClient(self.client, f))

    def extReceived(self, t, data):
        if t==connection.EXTENDED_DATA_STDERR:
            log.msg('got %s stderr data' % len(data))
            sys.stderr.write(data)
            sys.stderr.flush()

    def eofReceived(self):
        log.msg('got eof')
        self.stdio.loseWriteConnection()

    def closeReceived(self):
        log.msg('remote side closed %s' % self)
        self.conn.sendClose(self)

    def closed(self):
        try:
            reactor.stop()
        except:
            pass

    def stopWriting(self):
        self.stdio.pauseProducing()

    def startWriting(self):
        self.stdio.resumeProducing()

if __name__ == '__main__':
    run()

