"""
You don't really want to use this module. Try insults.py instead.
"""

from __future__ import print_function

from twisted.internet import protocol

class InsultsClient(protocol.Protocol):

    escapeTimeout = 0.2

    def __init__(self):
        self.width = self.height = None
        self.xpos = self.ypos = 0
        self.commandQueue = []
        self.inEscape = ''

    def setSize(self, width, height):
        call = 0
        if self.width:
            call = 1
        self.width = width
        self.height = height
        if call:
            self.windowSizeChanged()

    def dataReceived(self, data):
        from twisted.internet import reactor
        for ch in data:
            if ch == '\x1b':
                if self.inEscape:
                    self.keyReceived(ch)
                    self.inEscape = ''
                else:
                    self.inEscape = ch
                    self.escapeCall = reactor.callLater(self.escapeTimeout,
                                                        self.endEscape)
            elif ch in 'ABCD' and self.inEscape:
                self.inEscape = ''
                self.escapeCall.cancel()
                if ch == 'A':
                    self.keyReceived('<Up>')
                elif ch == 'B':
                    self.keyReceived('<Down>')
                elif ch == 'C':
                    self.keyReceived('<Right>')
                elif ch == 'D':
                    self.keyReceived('<Left>')
            elif self.inEscape:
                self.inEscape += ch
            else:
                self.keyReceived(ch)

    def endEscape(self):
        ch = self.inEscape
        self.inEscape = ''
        self.keyReceived(ch)

    def initScreen(self):
        self.transport.write('\x1b=\x1b[?1h')

    def gotoXY(self, x, y):
        """Go to a position on the screen.
        """
        self.xpos = x
        self.ypos = y
        self.commandQueue.append(('gotoxy', x, y))

    def writeCh(self, ch):
        """Write a character to the screen.  If we're at the end of the row,
        ignore the write.
        """
        if self.xpos < self.width - 1:
            self.commandQueue.append(('write', ch))
            self.xpos += 1

    def writeStr(self, s):
        """Write a string to the screen.  This does not wrap a the edge of the
        screen, and stops at \\r and \\n.
        """
        s = s[:self.width-self.xpos]
        if '\n' in s:
            s=s[:s.find('\n')]
        if '\r' in s:
            s=s[:s.find('\r')]
        self.commandQueue.append(('write', s))
        self.xpos += len(s)

    def eraseToLine(self):
        """Erase from the current position to the end of the line.
        """
        self.commandQueue.append(('eraseeol',))

    def eraseToScreen(self):
        """Erase from the current position to the end of the screen.
        """
        self.commandQueue.append(('eraseeos',))
    
    def clearScreen(self):
        """Clear the screen, and return the cursor to 0, 0.
        """
        self.commandQueue = [('cls',)]
        self.xpos = self.ypos = 0

    def setAttributes(self, *attrs):
        """Set the attributes for drawing on the screen.
        """
        self.commandQueue.append(('attributes', attrs))

    def refresh(self):
        """Redraw the screen.
        """
        redraw = ''
        for command in self.commandQueue:
            if command[0] == 'gotoxy':
                redraw += '\x1b[%i;%iH' % (command[2]+1, command[1]+1)
            elif command[0] == 'write':
                redraw += command[1]
            elif command[0] == 'eraseeol':
                redraw += '\x1b[0K'
            elif command[0] == 'eraseeos':
                redraw += '\x1b[OJ'
            elif command[0] == 'cls':
                redraw += '\x1b[H\x1b[J'
            elif command[0] == 'attributes':
                redraw += '\x1b[%sm' % ';'.join(map(str, command[1]))
            else:
                print(command)
        self.commandQueue = []
        self.transport.write(redraw)

    def windowSizeChanged(self):
        """Called when the size of the window changes.
        Might want to redraw the screen here, or something.
        """

    def keyReceived(self, key):
        """Called when the user hits a key.
        """
