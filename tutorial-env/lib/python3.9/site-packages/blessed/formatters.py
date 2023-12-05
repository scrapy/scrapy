"""Sub-module providing sequence-formatting functions."""
# std imports
import platform

# 3rd party
import six

# local
from blessed.colorspace import CGA_COLORS, X11_COLORNAMES_TO_RGB

# isort: off
# curses
if platform.system() == 'Windows':
    import jinxed as curses   # pylint: disable=import-error
else:
    import curses


def _make_colors():
    """
    Return set of valid colors and their derivatives.

    :rtype: set
    :returns: Color names with prefixes
    """
    colors = set()
    # basic CGA foreground color, background, high intensity, and bold
    # background ('iCE colors' in my day).
    for cga_color in CGA_COLORS:
        colors.add(cga_color)
        colors.add('on_' + cga_color)
        colors.add('bright_' + cga_color)
        colors.add('on_bright_' + cga_color)

    # foreground and background VGA color
    for vga_color in X11_COLORNAMES_TO_RGB:
        colors.add(vga_color)
        colors.add('on_' + vga_color)
    return colors


#: Valid colors and their background (on), bright, and bright-background
#: derivatives.
COLORS = _make_colors()

#: Attributes that may be compounded with colors, by underscore, such as
#: 'reverse_indigo'.
COMPOUNDABLES = set('bold underline reverse blink italic standout'.split())


class ParameterizingString(six.text_type):
    r"""
    A Unicode string which can be called as a parameterizing termcap.

    For example::

        >>> from blessed import Terminal
        >>> term = Terminal()
        >>> color = ParameterizingString(term.color, term.normal, 'color')
        >>> color(9)('color #9')
        u'\x1b[91mcolor #9\x1b(B\x1b[m'
    """

    def __new__(cls, cap, normal=u'', name=u'<not specified>'):
        # pylint: disable = missing-return-doc, missing-return-type-doc
        """
        Class constructor accepting 3 positional arguments.

        :arg str cap: parameterized string suitable for curses.tparm()
        :arg str normal: terminating sequence for this capability (optional).
        :arg str name: name of this terminal capability (optional).
        """
        new = six.text_type.__new__(cls, cap)
        new._normal = normal
        new._name = name
        return new

    def __call__(self, *args):
        """
        Returning :class:`FormattingString` instance for given parameters.

        Return evaluated terminal capability (self), receiving arguments
        ``*args``, followed by the terminating sequence (self.normal) into
        a :class:`FormattingString` capable of being called.

        :raises TypeError: Mismatch between capability and arguments
        :raises curses.error: :func:`curses.tparm` raised an exception
        :rtype: :class:`FormattingString` or :class:`NullCallableString`
        :returns: Callable string for given parameters
        """
        try:
            # Re-encode the cap, because tparm() takes a bytestring in Python
            # 3. However, appear to be a plain Unicode string otherwise so
            # concats work.
            attr = curses.tparm(self.encode('latin1'), *args).decode('latin1')
            return FormattingString(attr, self._normal)
        except TypeError as err:
            # If the first non-int (i.e. incorrect) arg was a string, suggest
            # something intelligent:
            if args and isinstance(args[0], six.string_types):
                raise TypeError(
                    "Unknown terminal capability, %r, or, TypeError "
                    "for arguments %r: %s" % (self._name, args, err))
            # Somebody passed a non-string; I don't feel confident
            # guessing what they were trying to do.
            raise
        except curses.error as err:
            # ignore 'tparm() returned NULL', you won't get any styling,
            # even if does_styling is True. This happens on win32 platforms
            # with http://www.lfd.uci.edu/~gohlke/pythonlibs/#curses installed
            if "tparm() returned NULL" not in six.text_type(err):
                raise
            return NullCallableString()


class ParameterizingProxyString(six.text_type):
    r"""
    A Unicode string which can be called to proxy missing termcap entries.

    This class supports the function :func:`get_proxy_string`, and mirrors
    the behavior of :class:`ParameterizingString`, except that instead of
    a capability name, receives a format string, and callable to filter the
    given positional ``*args`` of :meth:`ParameterizingProxyString.__call__`
    into a terminal sequence.

    For example::

        >>> from blessed import Terminal
        >>> term = Terminal('screen')
        >>> hpa = ParameterizingString(term.hpa, term.normal, 'hpa')
        >>> hpa(9)
        u''
        >>> fmt = u'\x1b[{0}G'
        >>> fmt_arg = lambda *arg: (arg[0] + 1,)
        >>> hpa = ParameterizingProxyString((fmt, fmt_arg), term.normal, 'hpa')
        >>> hpa(9)
        u'\x1b[10G'
    """

    def __new__(cls, fmt_pair, normal=u'', name=u'<not specified>'):
        # pylint: disable = missing-return-doc, missing-return-type-doc
        """
        Class constructor accepting 4 positional arguments.

        :arg tuple fmt_pair: Two element tuple containing:
            - format string suitable for displaying terminal sequences
            - callable suitable for receiving  __call__ arguments for formatting string
        :arg str normal: terminating sequence for this capability (optional).
        :arg str name: name of this terminal capability (optional).
        """
        assert isinstance(fmt_pair, tuple), fmt_pair
        assert callable(fmt_pair[1]), fmt_pair[1]
        new = six.text_type.__new__(cls, fmt_pair[0])
        new._fmt_args = fmt_pair[1]
        new._normal = normal
        new._name = name
        return new

    def __call__(self, *args):
        """
        Returning :class:`FormattingString` instance for given parameters.

        Arguments are determined by the capability.  For example, ``hpa``
        (move_x) receives only a single integer, whereas ``cup`` (move)
        receives two integers.  See documentation in terminfo(5) for the
        given capability.

        :rtype: FormattingString
        :returns: Callable string for given parameters
        """
        return FormattingString(self.format(*self._fmt_args(*args)),
                                self._normal)


class FormattingString(six.text_type):
    r"""
    A Unicode string which doubles as a callable.

    This is used for terminal attributes, so that it may be used both
    directly, or as a callable.  When used directly, it simply emits
    the given terminal sequence.  When used as a callable, it wraps the
    given (string) argument with the 2nd argument used by the class
    constructor::

        >>> from blessed import Terminal
        >>> term = Terminal()
        >>> style = FormattingString(term.bright_blue, term.normal)
        >>> print(repr(style))
        u'\x1b[94m'
        >>> style('Big Blue')
        u'\x1b[94mBig Blue\x1b(B\x1b[m'
    """

    def __new__(cls, sequence, normal=u''):
        # pylint: disable = missing-return-doc, missing-return-type-doc
        """
        Class constructor accepting 2 positional arguments.

        :arg str sequence: terminal attribute sequence.
        :arg str normal: terminating sequence for this attribute (optional).
        """
        new = six.text_type.__new__(cls, sequence)
        new._normal = normal
        return new

    def __call__(self, *args):
        """
        Return ``text`` joined by ``sequence`` and ``normal``.

        :raises TypeError: Not a string type
        :rtype: str
        :returns: Arguments wrapped in sequence and normal
        """
        # Jim Allman brings us this convenience of allowing existing
        # unicode strings to be joined as a call parameter to a formatting
        # string result, allowing nestation:
        #
        # >>> t.red('This is ', t.bold('extremely'), ' dangerous!')
        for idx, ucs_part in enumerate(args):
            if not isinstance(ucs_part, six.string_types):
                expected_types = ', '.join(_type.__name__ for _type in six.string_types)
                raise TypeError(
                    "TypeError for FormattingString argument, "
                    "%r, at position %s: expected type %s, "
                    "got %s" % (ucs_part, idx, expected_types,
                                type(ucs_part).__name__))
        postfix = u''
        if self and self._normal:
            postfix = self._normal
            _refresh = self._normal + self
            args = [_refresh.join(ucs_part.split(self._normal))
                    for ucs_part in args]

        return self + u''.join(args) + postfix


class FormattingOtherString(six.text_type):
    r"""
    A Unicode string which doubles as a callable for another sequence when called.

    This is used for the :meth:`~.Terminal.move_up`, ``down``, ``left``, and ``right()``
    family of functions::

        >>> from blessed import Terminal
        >>> term = Terminal()
        >>> move_right = FormattingOtherString(term.cuf1, term.cuf)
        >>> print(repr(move_right))
        u'\x1b[C'
        >>> print(repr(move_right(666)))
        u'\x1b[666C'
        >>> print(repr(move_right()))
        u'\x1b[C'
    """

    def __new__(cls, direct, target):
        # pylint: disable = missing-return-doc, missing-return-type-doc
        """
        Class constructor accepting 2 positional arguments.

        :arg str direct: capability name for direct formatting, eg ``('x' + term.right)``.
        :arg str target: capability name for callable, eg ``('x' + term.right(99))``.
        """
        new = six.text_type.__new__(cls, direct)
        new._callable = target
        return new

    def __getnewargs__(self):
        # return arguments used for the __new__ method upon unpickling.
        return six.text_type.__new__(six.text_type, self), self._callable

    def __call__(self, *args):
        """Return ``text`` by ``target``."""
        return self._callable(*args) if args else self


class NullCallableString(six.text_type):
    """
    A dummy callable Unicode alternative to :class:`FormattingString`.

    This is used for colors on terminals that do not support colors, it is just a basic form of
    unicode that may also act as a callable.
    """

    def __new__(cls):
        """Class constructor."""
        return six.text_type.__new__(cls, u'')

    def __call__(self, *args):
        """
        Allow empty string to be callable, returning given string, if any.

        When called with an int as the first arg, return an empty Unicode. An
        int is a good hint that I am a :class:`ParameterizingString`, as there
        are only about half a dozen string-returning capabilities listed in
        terminfo(5) which accept non-int arguments, they are seldom used.

        When called with a non-int as the first arg (no no args at all), return
        the first arg, acting in place of :class:`FormattingString` without
        any attributes.
        """
        if not args or isinstance(args[0], int):
            # As a NullCallableString, even when provided with a parameter,
            # such as t.color(5), we must also still be callable, fe:
            #
            # >>> t.color(5)('shmoo')
            #
            # is actually simplified result of NullCallable()() on terminals
            # without color support, so turtles all the way down: we return
            # another instance.
            return NullCallableString()
        return u''.join(args)


def get_proxy_string(term, attr):
    """
    Proxy and return callable string for proxied attributes.

    :arg Terminal term: :class:`~.Terminal` instance.
    :arg str attr: terminal capability name that may be proxied.
    :rtype: None or :class:`ParameterizingProxyString`.
    :returns: :class:`ParameterizingProxyString` for some attributes
        of some terminal types that support it, where the terminfo(5)
        database would otherwise come up empty, such as ``move_x``
        attribute for ``term.kind`` of ``screen``.  Otherwise, None.
    """
    # normalize 'screen-256color', or 'ansi.sys' to its basic names
    term_kind = next(iter(_kind for _kind in ('screen', 'ansi',)
                          if term.kind.startswith(_kind)), term)
    _proxy_table = {  # pragma: no cover
        'screen': {
            # proxy move_x/move_y for 'screen' terminal type, used by tmux(1).
            'hpa': ParameterizingProxyString(
                (u'\x1b[{0}G', lambda *arg: (arg[0] + 1,)), term.normal, attr),
            'vpa': ParameterizingProxyString(
                (u'\x1b[{0}d', lambda *arg: (arg[0] + 1,)), term.normal, attr),
        },
        'ansi': {
            # proxy show/hide cursor for 'ansi' terminal type.  There is some
            # demand for a richly working ANSI terminal type for some reason.
            'civis': ParameterizingProxyString(
                (u'\x1b[?25l', lambda *arg: ()), term.normal, attr),
            'cnorm': ParameterizingProxyString(
                (u'\x1b[?25h', lambda *arg: ()), term.normal, attr),
            'hpa': ParameterizingProxyString(
                (u'\x1b[{0}G', lambda *arg: (arg[0] + 1,)), term.normal, attr),
            'vpa': ParameterizingProxyString(
                (u'\x1b[{0}d', lambda *arg: (arg[0] + 1,)), term.normal, attr),
            'sc': '\x1b[s',
            'rc': '\x1b[u',
        }
    }
    return _proxy_table.get(term_kind, {}).get(attr, None)


def split_compound(compound):
    """
    Split compound formating string into segments.

    >>> split_compound('bold_underline_bright_blue_on_red')
    ['bold', 'underline', 'bright_blue', 'on_red']

    :arg str compound: a string that may contain compounds, separated by
        underline (``_``).
    :rtype: list
    :returns: List of formating string segments
    """
    merged_segs = []
    # These occur only as prefixes, so they can always be merged:
    mergeable_prefixes = ['on', 'bright', 'on_bright']
    for segment in compound.split('_'):
        if merged_segs and merged_segs[-1] in mergeable_prefixes:
            merged_segs[-1] += '_' + segment
        else:
            merged_segs.append(segment)
    return merged_segs


def resolve_capability(term, attr):
    """
    Resolve a raw terminal capability using :func:`tigetstr`.

    :arg Terminal term: :class:`~.Terminal` instance.
    :arg str attr: terminal capability name.
    :returns: string of the given terminal capability named by ``attr``,
       which may be empty (u'') if not found or not supported by the
       given :attr:`~.Terminal.kind`.
    :rtype: str
    """
    if not term.does_styling:
        return u''
    val = curses.tigetstr(term._sugar.get(attr, attr))  # pylint: disable=protected-access
    # Decode sequences as latin1, as they are always 8-bit bytes, so when
    # b'\xff' is returned, this is decoded as u'\xff'.
    return u'' if val is None else val.decode('latin1')


def resolve_color(term, color):
    """
    Resolve a simple color name to a callable capability.

    This function supports :func:`resolve_attribute`.

    :arg Terminal term: :class:`~.Terminal` instance.
    :arg str color: any string found in set :const:`COLORS`.
    :returns: a string class instance which emits the terminal sequence
        for the given color, and may be used as a callable to wrap the
        given string with such sequence.
    :returns: :class:`NullCallableString` when
        :attr:`~.Terminal.number_of_colors` is 0,
        otherwise :class:`FormattingString`.
    :rtype: :class:`NullCallableString` or :class:`FormattingString`
    """
    # pylint: disable=protected-access
    if term.number_of_colors == 0:
        return NullCallableString()

    # fg/bg capabilities terminals that support 0-256+ colors.
    vga_color_cap = (term._background_color if 'on_' in color else
                     term._foreground_color)

    base_color = color.rsplit('_', 1)[-1]
    if base_color in CGA_COLORS:
        # curses constants go up to only 7, so add an offset to get at the
        # bright colors at 8-15:
        offset = 8 if 'bright_' in color else 0
        base_color = color.rsplit('_', 1)[-1]
        attr = 'COLOR_%s' % (base_color.upper(),)
        fmt_attr = vga_color_cap(getattr(curses, attr) + offset)
        return FormattingString(fmt_attr, term.normal)

    assert base_color in X11_COLORNAMES_TO_RGB, (
        'color not known', base_color)
    rgb = X11_COLORNAMES_TO_RGB[base_color]

    # downconvert X11 colors to CGA, EGA, or VGA color spaces
    if term.number_of_colors <= 256:
        fmt_attr = vga_color_cap(term.rgb_downconvert(*rgb))
        return FormattingString(fmt_attr, term.normal)

    # Modern 24-bit color terminals are written pretty basically.  The
    # foreground and background sequences are:
    # - ^[38;2;<r>;<g>;<b>m
    # - ^[48;2;<r>;<g>;<b>m
    fgbg_seq = ('48' if 'on_' in color else '38')
    assert term.number_of_colors == 1 << 24
    fmt_attr = u'\x1b[' + fgbg_seq + ';2;{0};{1};{2}m'
    return FormattingString(fmt_attr.format(*rgb), term.normal)


def resolve_attribute(term, attr):
    """
    Resolve a terminal attribute name into a capability class.

    :arg Terminal term: :class:`~.Terminal` instance.
    :arg str attr: Sugary, ordinary, or compound formatted terminal
        capability, such as "red_on_white", "normal", "red", or
        "bold_on_black".
    :returns: a string class instance which emits the terminal sequence
        for the given terminal capability, or may be used as a callable to
        wrap the given string with such sequence.
    :returns: :class:`NullCallableString` when
        :attr:`~.Terminal.number_of_colors` is 0,
        otherwise :class:`FormattingString`.
    :rtype: :class:`NullCallableString` or :class:`FormattingString`
    """
    if attr in COLORS:
        return resolve_color(term, attr)

    # A direct compoundable, such as `bold' or `on_red'.
    if attr in COMPOUNDABLES:
        sequence = resolve_capability(term, attr)
        return FormattingString(sequence, term.normal)

    # Given `bold_on_red', resolve to ('bold', 'on_red'), RECURSIVE
    # call for each compounding section, joined and returned as
    # a completed completed FormattingString.
    formatters = split_compound(attr)
    if all((fmt in COLORS or fmt in COMPOUNDABLES) for fmt in formatters):
        resolution = (resolve_attribute(term, fmt) for fmt in formatters)
        return FormattingString(u''.join(resolution), term.normal)

    # otherwise, this is our end-game: given a sequence such as 'csr'
    # (change scrolling region), return a ParameterizingString instance,
    # that when called, performs and returns the final string after curses
    # capability lookup is performed.
    tparm_capseq = resolve_capability(term, attr)
    if not tparm_capseq:
        # and, for special terminals, such as 'screen', provide a Proxy
        # ParameterizingString for attributes they do not claim to support,
        # but actually do! (such as 'hpa' and 'vpa').
        proxy = get_proxy_string(term,
                                 term._sugar.get(attr, attr))  # pylint: disable=protected-access
        if proxy is not None:
            return proxy

    return ParameterizingString(tparm_capseq, term.normal, attr)
