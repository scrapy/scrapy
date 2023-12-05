# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#

"""Module to emulate a VT100 terminal in Tkinter.

Maintainer: Paul Swartz
"""

import string
import tkinter as Tkinter
import tkinter.font as tkFont

from . import ansi

ttyFont = None  # tkFont.Font(family = 'Courier', size = 10)
fontWidth, fontHeight = (
    None,
    None,
)  # max(map(ttyFont.measure, string.letters+string.digits)), int(ttyFont.metrics()['linespace'])

colorKeys = (
    "b",
    "r",
    "g",
    "y",
    "l",
    "m",
    "c",
    "w",
    "B",
    "R",
    "G",
    "Y",
    "L",
    "M",
    "C",
    "W",
)

colorMap = {
    "b": "#000000",
    "r": "#c40000",
    "g": "#00c400",
    "y": "#c4c400",
    "l": "#000080",
    "m": "#c400c4",
    "c": "#00c4c4",
    "w": "#c4c4c4",
    "B": "#626262",
    "R": "#ff0000",
    "G": "#00ff00",
    "Y": "#ffff00",
    "L": "#0000ff",
    "M": "#ff00ff",
    "C": "#00ffff",
    "W": "#ffffff",
}


class VT100Frame(Tkinter.Frame):
    def __init__(self, *args, **kw):
        global ttyFont, fontHeight, fontWidth
        ttyFont = tkFont.Font(family="Courier", size=10)
        fontWidth = max(map(ttyFont.measure, string.ascii_letters + string.digits))
        fontHeight = int(ttyFont.metrics()["linespace"])
        self.width = kw.get("width", 80)
        self.height = kw.get("height", 25)
        self.callback = kw["callback"]
        del kw["callback"]
        kw["width"] = w = fontWidth * self.width
        kw["height"] = h = fontHeight * self.height
        Tkinter.Frame.__init__(self, *args, **kw)
        self.canvas = Tkinter.Canvas(bg="#000000", width=w, height=h)
        self.canvas.pack(side=Tkinter.TOP, fill=Tkinter.BOTH, expand=1)
        self.canvas.bind("<Key>", self.keyPressed)
        self.canvas.bind("<1>", lambda x: "break")
        self.canvas.bind("<Up>", self.upPressed)
        self.canvas.bind("<Down>", self.downPressed)
        self.canvas.bind("<Left>", self.leftPressed)
        self.canvas.bind("<Right>", self.rightPressed)
        self.canvas.focus()

        self.ansiParser = ansi.AnsiParser(ansi.ColorText.WHITE, ansi.ColorText.BLACK)
        self.ansiParser.writeString = self.writeString
        self.ansiParser.parseCursor = self.parseCursor
        self.ansiParser.parseErase = self.parseErase
        # for (a, b) in colorMap.items():
        #    self.canvas.tag_config(a, foreground=b)
        #    self.canvas.tag_config('b'+a, background=b)
        # self.canvas.tag_config('underline', underline=1)

        self.x = 0
        self.y = 0
        self.cursor = self.canvas.create_rectangle(
            0, 0, fontWidth - 1, fontHeight - 1, fill="green", outline="green"
        )

    def _delete(self, sx, sy, ex, ey):
        csx = sx * fontWidth + 1
        csy = sy * fontHeight + 1
        cex = ex * fontWidth + 3
        cey = ey * fontHeight + 3
        items = self.canvas.find_overlapping(csx, csy, cex, cey)
        for item in items:
            self.canvas.delete(item)

    def _write(self, ch, fg, bg):
        if self.x == self.width:
            self.x = 0
            self.y += 1
            if self.y == self.height:
                [self.canvas.move(x, 0, -fontHeight) for x in self.canvas.find_all()]
                self.y -= 1
        canvasX = self.x * fontWidth + 1
        canvasY = self.y * fontHeight + 1
        items = self.canvas.find_overlapping(canvasX, canvasY, canvasX + 2, canvasY + 2)
        if items:
            [self.canvas.delete(item) for item in items]
        if bg:
            self.canvas.create_rectangle(
                canvasX,
                canvasY,
                canvasX + fontWidth - 1,
                canvasY + fontHeight - 1,
                fill=bg,
                outline=bg,
            )
        self.canvas.create_text(
            canvasX, canvasY, anchor=Tkinter.NW, font=ttyFont, text=ch, fill=fg
        )
        self.x += 1

    def write(self, data):
        self.ansiParser.parseString(data)
        self.canvas.delete(self.cursor)
        canvasX = self.x * fontWidth + 1
        canvasY = self.y * fontHeight + 1
        self.cursor = self.canvas.create_rectangle(
            canvasX,
            canvasY,
            canvasX + fontWidth - 1,
            canvasY + fontHeight - 1,
            fill="green",
            outline="green",
        )
        self.canvas.lower(self.cursor)

    def writeString(self, i):
        if not i.display:
            return
        fg = colorMap[i.fg]
        bg = i.bg != "b" and colorMap[i.bg]
        for ch in i.text:
            b = ord(ch)
            if b == 7:  # bell
                self.bell()
            elif b == 8:  # BS
                if self.x:
                    self.x -= 1
            elif b == 9:  # TAB
                [self._write(" ", fg, bg) for index in range(8)]
            elif b == 10:
                if self.y == self.height - 1:
                    self._delete(0, 0, self.width, 0)
                    [
                        self.canvas.move(x, 0, -fontHeight)
                        for x in self.canvas.find_all()
                    ]
                else:
                    self.y += 1
            elif b == 13:
                self.x = 0
            elif 32 <= b < 127:
                self._write(ch, fg, bg)

    def parseErase(self, erase):
        if ";" in erase:
            end = erase[-1]
            parts = erase[:-1].split(";")
            [self.parseErase(x + end) for x in parts]
            return
        start = 0
        x, y = self.x, self.y
        if len(erase) > 1:
            start = int(erase[:-1])
        if erase[-1] == "J":
            if start == 0:
                self._delete(x, y, self.width, self.height)
            else:
                self._delete(0, 0, self.width, self.height)
                self.x = 0
                self.y = 0
        elif erase[-1] == "K":
            if start == 0:
                self._delete(x, y, self.width, y)
            elif start == 1:
                self._delete(0, y, x, y)
                self.x = 0
            else:
                self._delete(0, y, self.width, y)
                self.x = 0
        elif erase[-1] == "P":
            self._delete(x, y, x + start, y)

    def parseCursor(self, cursor):
        # if ';' in cursor and cursor[-1]!='H':
        #    end = cursor[-1]
        #    parts = cursor[:-1].split(';')
        #    [self.parseCursor(x+end) for x in parts]
        #    return
        start = 1
        if len(cursor) > 1 and cursor[-1] != "H":
            start = int(cursor[:-1])
        if cursor[-1] == "C":
            self.x += start
        elif cursor[-1] == "D":
            self.x -= start
        elif cursor[-1] == "d":
            self.y = start - 1
        elif cursor[-1] == "G":
            self.x = start - 1
        elif cursor[-1] == "H":
            if len(cursor) > 1:
                y, x = map(int, cursor[:-1].split(";"))
                y -= 1
                x -= 1
            else:
                x, y = 0, 0
            self.x = x
            self.y = y

    def keyPressed(self, event):
        if self.callback and event.char:
            self.callback(event.char)
        return "break"

    def upPressed(self, event):
        self.callback("\x1bOA")

    def downPressed(self, event):
        self.callback("\x1bOB")

    def rightPressed(self, event):
        self.callback("\x1bOC")

    def leftPressed(self, event):
        self.callback("\x1bOD")
