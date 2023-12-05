# -*- test-case-name: twisted.conch.test.test_window -*-

"""
Simple insults-based widget library

@author: Jp Calderone
"""

import array

from twisted.conch.insults import helper, insults
from twisted.python import text as tptext


class YieldFocus(Exception):
    """
    Input focus manipulation exception
    """


class BoundedTerminalWrapper:
    def __init__(self, terminal, width, height, xoff, yoff):
        self.width = width
        self.height = height
        self.xoff = xoff
        self.yoff = yoff
        self.terminal = terminal
        self.cursorForward = terminal.cursorForward
        self.selectCharacterSet = terminal.selectCharacterSet
        self.selectGraphicRendition = terminal.selectGraphicRendition
        self.saveCursor = terminal.saveCursor
        self.restoreCursor = terminal.restoreCursor

    def cursorPosition(self, x, y):
        return self.terminal.cursorPosition(
            self.xoff + min(self.width, x), self.yoff + min(self.height, y)
        )

    def cursorHome(self):
        return self.terminal.cursorPosition(self.xoff, self.yoff)

    def write(self, data):
        return self.terminal.write(data)


class Widget:
    focused = False
    parent = None
    dirty = False
    width = height = None

    def repaint(self):
        if not self.dirty:
            self.dirty = True
        if self.parent is not None and not self.parent.dirty:
            self.parent.repaint()

    def filthy(self):
        self.dirty = True

    def redraw(self, width, height, terminal):
        self.filthy()
        self.draw(width, height, terminal)

    def draw(self, width, height, terminal):
        if width != self.width or height != self.height or self.dirty:
            self.width = width
            self.height = height
            self.dirty = False
            self.render(width, height, terminal)

    def render(self, width, height, terminal):
        pass

    def sizeHint(self):
        return None

    def keystrokeReceived(self, keyID, modifier):
        if keyID == b"\t":
            self.tabReceived(modifier)
        elif keyID == b"\x7f":
            self.backspaceReceived()
        elif keyID in insults.FUNCTION_KEYS:
            self.functionKeyReceived(keyID, modifier)
        else:
            self.characterReceived(keyID, modifier)

    def tabReceived(self, modifier):
        # XXX TODO - Handle shift+tab
        raise YieldFocus()

    def focusReceived(self):
        """
        Called when focus is being given to this widget.

        May raise YieldFocus is this widget does not want focus.
        """
        self.focused = True
        self.repaint()

    def focusLost(self):
        self.focused = False
        self.repaint()

    def backspaceReceived(self):
        pass

    def functionKeyReceived(self, keyID, modifier):
        name = keyID
        if not isinstance(keyID, str):
            name = name.decode("utf-8")
        func = getattr(self, "func_" + name, None)
        if func is not None:
            func(modifier)

    def characterReceived(self, keyID, modifier):
        pass


class ContainerWidget(Widget):
    """
    @ivar focusedChild: The contained widget which currently has
    focus, or None.
    """

    focusedChild = None
    focused = False

    def __init__(self):
        Widget.__init__(self)
        self.children = []

    def addChild(self, child):
        assert child.parent is None
        child.parent = self
        self.children.append(child)
        if self.focusedChild is None and self.focused:
            try:
                child.focusReceived()
            except YieldFocus:
                pass
            else:
                self.focusedChild = child
        self.repaint()

    def remChild(self, child):
        assert child.parent is self
        child.parent = None
        self.children.remove(child)
        self.repaint()

    def filthy(self):
        for ch in self.children:
            ch.filthy()
        Widget.filthy(self)

    def render(self, width, height, terminal):
        for ch in self.children:
            ch.draw(width, height, terminal)

    def changeFocus(self):
        self.repaint()

        if self.focusedChild is not None:
            self.focusedChild.focusLost()
            focusedChild = self.focusedChild
            self.focusedChild = None
            try:
                curFocus = self.children.index(focusedChild) + 1
            except ValueError:
                raise YieldFocus()
        else:
            curFocus = 0
        while curFocus < len(self.children):
            try:
                self.children[curFocus].focusReceived()
            except YieldFocus:
                curFocus += 1
            else:
                self.focusedChild = self.children[curFocus]
                return
        # None of our children wanted focus
        raise YieldFocus()

    def focusReceived(self):
        self.changeFocus()
        self.focused = True

    def keystrokeReceived(self, keyID, modifier):
        if self.focusedChild is not None:
            try:
                self.focusedChild.keystrokeReceived(keyID, modifier)
            except YieldFocus:
                self.changeFocus()
                self.repaint()
        else:
            Widget.keystrokeReceived(self, keyID, modifier)


class TopWindow(ContainerWidget):
    """
    A top-level container object which provides focus wrap-around and paint
    scheduling.

    @ivar painter: A no-argument callable which will be invoked when this
    widget needs to be redrawn.

    @ivar scheduler: A one-argument callable which will be invoked with a
    no-argument callable and should arrange for it to invoked at some point in
    the near future.  The no-argument callable will cause this widget and all
    its children to be redrawn.  It is typically beneficial for the no-argument
    callable to be invoked at the end of handling for whatever event is
    currently active; for example, it might make sense to call it at the end of
    L{twisted.conch.insults.insults.ITerminalProtocol.keystrokeReceived}.
    Note, however, that since calls to this may also be made in response to no
    apparent event, arrangements should be made for the function to be called
    even if an event handler such as C{keystrokeReceived} is not on the call
    stack (eg, using
    L{reactor.callLater<twisted.internet.interfaces.IReactorTime.callLater>}
    with a short timeout).
    """

    focused = True

    def __init__(self, painter, scheduler):
        ContainerWidget.__init__(self)
        self.painter = painter
        self.scheduler = scheduler

    _paintCall = None

    def repaint(self):
        if self._paintCall is None:
            self._paintCall = object()
            self.scheduler(self._paint)
        ContainerWidget.repaint(self)

    def _paint(self):
        self._paintCall = None
        self.painter()

    def changeFocus(self):
        try:
            ContainerWidget.changeFocus(self)
        except YieldFocus:
            try:
                ContainerWidget.changeFocus(self)
            except YieldFocus:
                pass

    def keystrokeReceived(self, keyID, modifier):
        try:
            ContainerWidget.keystrokeReceived(self, keyID, modifier)
        except YieldFocus:
            self.changeFocus()


class AbsoluteBox(ContainerWidget):
    def moveChild(self, child, x, y):
        for n in range(len(self.children)):
            if self.children[n][0] is child:
                self.children[n] = (child, x, y)
                break
        else:
            raise ValueError("No such child", child)

    def render(self, width, height, terminal):
        for (ch, x, y) in self.children:
            wrap = BoundedTerminalWrapper(terminal, width - x, height - y, x, y)
            ch.draw(width, height, wrap)


class _Box(ContainerWidget):
    TOP, CENTER, BOTTOM = range(3)

    def __init__(self, gravity=CENTER):
        ContainerWidget.__init__(self)
        self.gravity = gravity

    def sizeHint(self):
        height = 0
        width = 0
        for ch in self.children:
            hint = ch.sizeHint()
            if hint is None:
                hint = (None, None)

            if self.variableDimension == 0:
                if hint[0] is None:
                    width = None
                elif width is not None:
                    width += hint[0]
                if hint[1] is None:
                    height = None
                elif height is not None:
                    height = max(height, hint[1])
            else:
                if hint[0] is None:
                    width = None
                elif width is not None:
                    width = max(width, hint[0])
                if hint[1] is None:
                    height = None
                elif height is not None:
                    height += hint[1]

        return width, height

    def render(self, width, height, terminal):
        if not self.children:
            return

        greedy = 0
        wants = []
        for ch in self.children:
            hint = ch.sizeHint()
            if hint is None:
                hint = (None, None)
            if hint[self.variableDimension] is None:
                greedy += 1
            wants.append(hint[self.variableDimension])

        length = (width, height)[self.variableDimension]
        totalWant = sum(w for w in wants if w is not None)
        if greedy:
            leftForGreedy = int((length - totalWant) / greedy)

        widthOffset = heightOffset = 0

        for want, ch in zip(wants, self.children):
            if want is None:
                want = leftForGreedy

            subWidth, subHeight = width, height
            if self.variableDimension == 0:
                subWidth = want
            else:
                subHeight = want

            wrap = BoundedTerminalWrapper(
                terminal,
                subWidth,
                subHeight,
                widthOffset,
                heightOffset,
            )
            ch.draw(subWidth, subHeight, wrap)
            if self.variableDimension == 0:
                widthOffset += want
            else:
                heightOffset += want


class HBox(_Box):
    variableDimension = 0


class VBox(_Box):
    variableDimension = 1


class Packer(ContainerWidget):
    def render(self, width, height, terminal):
        if not self.children:
            return

        root = int(len(self.children) ** 0.5 + 0.5)
        boxes = [VBox() for n in range(root)]
        for n, ch in enumerate(self.children):
            boxes[n % len(boxes)].addChild(ch)
        h = HBox()
        map(h.addChild, boxes)
        h.render(width, height, terminal)


class Canvas(Widget):
    focused = False

    contents = None

    def __init__(self):
        Widget.__init__(self)
        self.resize(1, 1)

    def resize(self, width, height):
        contents = array.array("B", b" " * width * height)
        if self.contents is not None:
            for x in range(min(width, self._width)):
                for y in range(min(height, self._height)):
                    contents[width * y + x] = self[x, y]
        self.contents = contents
        self._width = width
        self._height = height
        if self.x >= width:
            self.x = width - 1
        if self.y >= height:
            self.y = height - 1

    def __getitem__(self, index):
        (x, y) = index
        return self.contents[(self._width * y) + x]

    def __setitem__(self, index, value):
        (x, y) = index
        self.contents[(self._width * y) + x] = value

    def clear(self):
        self.contents = array.array("B", b" " * len(self.contents))

    def render(self, width, height, terminal):
        if not width or not height:
            return

        if width != self._width or height != self._height:
            self.resize(width, height)
        for i in range(height):
            terminal.cursorPosition(0, i)
            text = self.contents[
                self._width * i : self._width * i + self._width
            ].tobytes()
            text = text[:width]
            terminal.write(text)


def horizontalLine(terminal, y, left, right):
    terminal.selectCharacterSet(insults.CS_DRAWING, insults.G0)
    terminal.cursorPosition(left, y)
    terminal.write(b"\161" * (right - left))
    terminal.selectCharacterSet(insults.CS_US, insults.G0)


def verticalLine(terminal, x, top, bottom):
    terminal.selectCharacterSet(insults.CS_DRAWING, insults.G0)
    for n in range(top, bottom):
        terminal.cursorPosition(x, n)
        terminal.write(b"\170")
    terminal.selectCharacterSet(insults.CS_US, insults.G0)


def rectangle(terminal, position, dimension):
    """
    Draw a rectangle

    @type position: L{tuple}
    @param position: A tuple of the (top, left) coordinates of the rectangle.
    @type dimension: L{tuple}
    @param dimension: A tuple of the (width, height) size of the rectangle.
    """
    (top, left) = position
    (width, height) = dimension
    terminal.selectCharacterSet(insults.CS_DRAWING, insults.G0)

    terminal.cursorPosition(top, left)
    terminal.write(b"\154")
    terminal.write(b"\161" * (width - 2))
    terminal.write(b"\153")
    for n in range(height - 2):
        terminal.cursorPosition(left, top + n + 1)
        terminal.write(b"\170")
        terminal.cursorForward(width - 2)
        terminal.write(b"\170")
    terminal.cursorPosition(0, top + height - 1)
    terminal.write(b"\155")
    terminal.write(b"\161" * (width - 2))
    terminal.write(b"\152")

    terminal.selectCharacterSet(insults.CS_US, insults.G0)


class Border(Widget):
    def __init__(self, containee):
        Widget.__init__(self)
        self.containee = containee
        self.containee.parent = self

    def focusReceived(self):
        return self.containee.focusReceived()

    def focusLost(self):
        return self.containee.focusLost()

    def keystrokeReceived(self, keyID, modifier):
        return self.containee.keystrokeReceived(keyID, modifier)

    def sizeHint(self):
        hint = self.containee.sizeHint()
        if hint is None:
            hint = (None, None)
        if hint[0] is None:
            x = None
        else:
            x = hint[0] + 2
        if hint[1] is None:
            y = None
        else:
            y = hint[1] + 2
        return x, y

    def filthy(self):
        self.containee.filthy()
        Widget.filthy(self)

    def render(self, width, height, terminal):
        if self.containee.focused:
            terminal.write(b"\x1b[31m")
        rectangle(terminal, (0, 0), (width, height))
        terminal.write(b"\x1b[0m")
        wrap = BoundedTerminalWrapper(terminal, width - 2, height - 2, 1, 1)
        self.containee.draw(width - 2, height - 2, wrap)


class Button(Widget):
    def __init__(self, label, onPress):
        Widget.__init__(self)
        self.label = label
        self.onPress = onPress

    def sizeHint(self):
        return len(self.label), 1

    def characterReceived(self, keyID, modifier):
        if keyID == b"\r":
            self.onPress()

    def render(self, width, height, terminal):
        terminal.cursorPosition(0, 0)
        if self.focused:
            terminal.write(b"\x1b[1m" + self.label + b"\x1b[0m")
        else:
            terminal.write(self.label)


class TextInput(Widget):
    def __init__(self, maxwidth, onSubmit):
        Widget.__init__(self)
        self.onSubmit = onSubmit
        self.maxwidth = maxwidth
        self.buffer = b""
        self.cursor = 0

    def setText(self, text):
        self.buffer = text[: self.maxwidth]
        self.cursor = len(self.buffer)
        self.repaint()

    def func_LEFT_ARROW(self, modifier):
        if self.cursor > 0:
            self.cursor -= 1
            self.repaint()

    def func_RIGHT_ARROW(self, modifier):
        if self.cursor < len(self.buffer):
            self.cursor += 1
            self.repaint()

    def backspaceReceived(self):
        if self.cursor > 0:
            self.buffer = self.buffer[: self.cursor - 1] + self.buffer[self.cursor :]
            self.cursor -= 1
            self.repaint()

    def characterReceived(self, keyID, modifier):
        if keyID == b"\r":
            self.onSubmit(self.buffer)
        else:
            if len(self.buffer) < self.maxwidth:
                self.buffer = (
                    self.buffer[: self.cursor] + keyID + self.buffer[self.cursor :]
                )
                self.cursor += 1
                self.repaint()

    def sizeHint(self):
        return self.maxwidth + 1, 1

    def render(self, width, height, terminal):
        currentText = self._renderText()
        terminal.cursorPosition(0, 0)
        if self.focused:
            terminal.write(currentText[: self.cursor])
            cursor(terminal, currentText[self.cursor : self.cursor + 1] or b" ")
            terminal.write(currentText[self.cursor + 1 :])
            terminal.write(b" " * (self.maxwidth - len(currentText) + 1))
        else:
            more = self.maxwidth - len(currentText)
            terminal.write(currentText + b"_" * more)

    def _renderText(self):
        return self.buffer


class PasswordInput(TextInput):
    def _renderText(self):
        return "*" * len(self.buffer)


class TextOutput(Widget):
    text = b""

    def __init__(self, size=None):
        Widget.__init__(self)
        self.size = size

    def sizeHint(self):
        return self.size

    def render(self, width, height, terminal):
        terminal.cursorPosition(0, 0)
        text = self.text[:width]
        terminal.write(text + b" " * (width - len(text)))

    def setText(self, text):
        self.text = text
        self.repaint()

    def focusReceived(self):
        raise YieldFocus()


class TextOutputArea(TextOutput):
    WRAP, TRUNCATE = range(2)

    def __init__(self, size=None, longLines=WRAP):
        TextOutput.__init__(self, size)
        self.longLines = longLines

    def render(self, width, height, terminal):
        n = 0
        inputLines = self.text.splitlines()
        outputLines = []
        while inputLines:
            if self.longLines == self.WRAP:
                line = inputLines.pop(0)
                if not isinstance(line, str):
                    line = line.decode("utf-8")
                wrappedLines = []
                for wrappedLine in tptext.greedyWrap(line, width):
                    if not isinstance(wrappedLine, bytes):
                        wrappedLine = wrappedLine.encode("utf-8")
                    wrappedLines.append(wrappedLine)
                outputLines.extend(wrappedLines or [b""])
            else:
                outputLines.append(inputLines.pop(0)[:width])
            if len(outputLines) >= height:
                break
        for n, L in enumerate(outputLines[:height]):
            terminal.cursorPosition(0, n)
            terminal.write(L)


class Viewport(Widget):
    _xOffset = 0
    _yOffset = 0

    @property
    def xOffset(self):
        return self._xOffset

    @xOffset.setter
    def xOffset(self, value):
        if self._xOffset != value:
            self._xOffset = value
            self.repaint()

    @property
    def yOffset(self):
        return self._yOffset

    @yOffset.setter
    def yOffset(self, value):
        if self._yOffset != value:
            self._yOffset = value
            self.repaint()

    _width = 160
    _height = 24

    def __init__(self, containee):
        Widget.__init__(self)
        self.containee = containee
        self.containee.parent = self

        self._buf = helper.TerminalBuffer()
        self._buf.width = self._width
        self._buf.height = self._height
        self._buf.connectionMade()

    def filthy(self):
        self.containee.filthy()
        Widget.filthy(self)

    def render(self, width, height, terminal):
        self.containee.draw(self._width, self._height, self._buf)

        # XXX /Lame/
        for y, line in enumerate(
            self._buf.lines[self._yOffset : self._yOffset + height]
        ):
            terminal.cursorPosition(0, y)
            n = 0
            for n, (ch, attr) in enumerate(line[self._xOffset : self._xOffset + width]):
                if ch is self._buf.void:
                    ch = b" "
                terminal.write(ch)
            if n < width:
                terminal.write(b" " * (width - n - 1))


class _Scrollbar(Widget):
    def __init__(self, onScroll):
        Widget.__init__(self)
        self.onScroll = onScroll
        self.percent = 0.0

    def smaller(self):
        self.percent = min(1.0, max(0.0, self.onScroll(-1)))
        self.repaint()

    def bigger(self):
        self.percent = min(1.0, max(0.0, self.onScroll(+1)))
        self.repaint()


class HorizontalScrollbar(_Scrollbar):
    def sizeHint(self):
        return (None, 1)

    def func_LEFT_ARROW(self, modifier):
        self.smaller()

    def func_RIGHT_ARROW(self, modifier):
        self.bigger()

    _left = "\N{BLACK LEFT-POINTING TRIANGLE}"
    _right = "\N{BLACK RIGHT-POINTING TRIANGLE}"
    _bar = "\N{LIGHT SHADE}"
    _slider = "\N{DARK SHADE}"

    def render(self, width, height, terminal):
        terminal.cursorPosition(0, 0)
        n = width - 3
        before = int(n * self.percent)
        after = n - before
        me = (
            self._left
            + (self._bar * before)
            + self._slider
            + (self._bar * after)
            + self._right
        )
        terminal.write(me.encode("utf-8"))


class VerticalScrollbar(_Scrollbar):
    def sizeHint(self):
        return (1, None)

    def func_UP_ARROW(self, modifier):
        self.smaller()

    def func_DOWN_ARROW(self, modifier):
        self.bigger()

    _up = "\N{BLACK UP-POINTING TRIANGLE}"
    _down = "\N{BLACK DOWN-POINTING TRIANGLE}"
    _bar = "\N{LIGHT SHADE}"
    _slider = "\N{DARK SHADE}"

    def render(self, width, height, terminal):
        terminal.cursorPosition(0, 0)
        knob = int(self.percent * (height - 2))
        terminal.write(self._up.encode("utf-8"))
        for i in range(1, height - 1):
            terminal.cursorPosition(0, i)
            if i != (knob + 1):
                terminal.write(self._bar.encode("utf-8"))
            else:
                terminal.write(self._slider.encode("utf-8"))
        terminal.cursorPosition(0, height - 1)
        terminal.write(self._down.encode("utf-8"))


class ScrolledArea(Widget):
    """
    A L{ScrolledArea} contains another widget wrapped in a viewport and
    vertical and horizontal scrollbars for moving the viewport around.
    """

    def __init__(self, containee):
        Widget.__init__(self)
        self._viewport = Viewport(containee)
        self._horiz = HorizontalScrollbar(self._horizScroll)
        self._vert = VerticalScrollbar(self._vertScroll)

        for w in self._viewport, self._horiz, self._vert:
            w.parent = self

    def _horizScroll(self, n):
        self._viewport.xOffset += n
        self._viewport.xOffset = max(0, self._viewport.xOffset)
        return self._viewport.xOffset / 25.0

    def _vertScroll(self, n):
        self._viewport.yOffset += n
        self._viewport.yOffset = max(0, self._viewport.yOffset)
        return self._viewport.yOffset / 25.0

    def func_UP_ARROW(self, modifier):
        self._vert.smaller()

    def func_DOWN_ARROW(self, modifier):
        self._vert.bigger()

    def func_LEFT_ARROW(self, modifier):
        self._horiz.smaller()

    def func_RIGHT_ARROW(self, modifier):
        self._horiz.bigger()

    def filthy(self):
        self._viewport.filthy()
        self._horiz.filthy()
        self._vert.filthy()
        Widget.filthy(self)

    def render(self, width, height, terminal):
        wrapper = BoundedTerminalWrapper(terminal, width - 2, height - 2, 1, 1)
        self._viewport.draw(width - 2, height - 2, wrapper)
        if self.focused:
            terminal.write(b"\x1b[31m")
        horizontalLine(terminal, 0, 1, width - 1)
        verticalLine(terminal, 0, 1, height - 1)
        self._vert.draw(
            1, height - 1, BoundedTerminalWrapper(terminal, 1, height - 1, width - 1, 0)
        )
        self._horiz.draw(
            width, 1, BoundedTerminalWrapper(terminal, width, 1, 0, height - 1)
        )
        terminal.write(b"\x1b[0m")


def cursor(terminal, ch):
    terminal.saveCursor()
    terminal.selectGraphicRendition(str(insults.REVERSE_VIDEO))
    terminal.write(ch)
    terminal.restoreCursor()
    terminal.cursorForward()


class Selection(Widget):
    # Index into the sequence
    focusedIndex = 0

    # Offset into the displayed subset of the sequence
    renderOffset = 0

    def __init__(self, sequence, onSelect, minVisible=None):
        Widget.__init__(self)
        self.sequence = sequence
        self.onSelect = onSelect
        self.minVisible = minVisible
        if minVisible is not None:
            self._width = max(map(len, self.sequence))

    def sizeHint(self):
        if self.minVisible is not None:
            return self._width, self.minVisible

    def func_UP_ARROW(self, modifier):
        if self.focusedIndex > 0:
            self.focusedIndex -= 1
            if self.renderOffset > 0:
                self.renderOffset -= 1
            self.repaint()

    def func_PGUP(self, modifier):
        if self.renderOffset != 0:
            self.focusedIndex -= self.renderOffset
            self.renderOffset = 0
        else:
            self.focusedIndex = max(0, self.focusedIndex - self.height)
        self.repaint()

    def func_DOWN_ARROW(self, modifier):
        if self.focusedIndex < len(self.sequence) - 1:
            self.focusedIndex += 1
            if self.renderOffset < self.height - 1:
                self.renderOffset += 1
            self.repaint()

    def func_PGDN(self, modifier):
        if self.renderOffset != self.height - 1:
            change = self.height - self.renderOffset - 1
            if change + self.focusedIndex >= len(self.sequence):
                change = len(self.sequence) - self.focusedIndex - 1
            self.focusedIndex += change
            self.renderOffset = self.height - 1
        else:
            self.focusedIndex = min(
                len(self.sequence) - 1, self.focusedIndex + self.height
            )
        self.repaint()

    def characterReceived(self, keyID, modifier):
        if keyID == b"\r":
            self.onSelect(self.sequence[self.focusedIndex])

    def render(self, width, height, terminal):
        self.height = height
        start = self.focusedIndex - self.renderOffset
        if start > len(self.sequence) - height:
            start = max(0, len(self.sequence) - height)

        elements = self.sequence[start : start + height]

        for n, ele in enumerate(elements):
            terminal.cursorPosition(0, n)
            if n == self.renderOffset:
                terminal.saveCursor()
                if self.focused:
                    modes = str(insults.REVERSE_VIDEO), str(insults.BOLD)
                else:
                    modes = (str(insults.REVERSE_VIDEO),)
                terminal.selectGraphicRendition(*modes)
            text = ele[:width]
            terminal.write(text + (b" " * (width - len(text))))
            if n == self.renderOffset:
                terminal.restoreCursor()
